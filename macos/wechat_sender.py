"""用 macOS 原生界面能力向已确认的微信会话发送一条文字（可含 emoji）。

微信 4.x 不稳定暴露辅助功能树，因此这里不依赖控件路径：
用快捷键搜索会话，用窗口截图 + Vision OCR 确认目标，再按窗口相对位置
点击输入区。任何一个确认步骤失败都会抛出 ``SenderError``，调用方不得发送。

这个模块不读取微信数据库、不注入微信进程，也不使用 Codex Computer Use。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("wechat-sender")


class SenderError(RuntimeError):
    """微信界面发送失败，并标记是否已经尝试过最终发送动作。"""

    def __init__(self, message: str, *, send_attempted: bool = False) -> None:
        super().__init__(message)
        self.send_attempted = send_attempted


@dataclass(frozen=True)
class WindowBounds:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class OCRObservation:
    text: str
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class OCRResult:
    width: int
    height: int
    observations: tuple[OCRObservation, ...]


_ACTIVATE_AND_SEARCH = r'''
tell application "System Events"
    if not (exists process "WeChat") then error "微信未运行"
    tell process "WeChat"
        set frontmost to true
        if (count of windows) = 0 then error "微信没有主窗口"
        keystroke "f" using {command down}
    end tell
end tell
'''

_ACTIVATE_ONLY = r'''
tell application "System Events"
    if not (exists process "WeChat") then error "微信未运行"
    tell process "WeChat"
        set frontmost to true
        if (count of windows) = 0 then error "微信没有主窗口"
    end tell
end tell
'''

_GET_BOUNDS = r'''
tell application "System Events"
    if not (exists process "WeChat") then error "微信未运行"
    tell process "WeChat"
        if (count of windows) = 0 then error "微信没有主窗口"
        set p to position of window 1
        set s to size of window 1
        return ((item 1 of p) as text) & "," & ((item 2 of p) as text) & "," & ¬
            ((item 1 of s) as text) & "," & ((item 2 of s) as text)
    end tell
end tell
'''

_PASTE_ONLY = r'''
tell application "System Events"
    if not (exists process "WeChat") then error "微信未运行"
    tell process "WeChat"
        set frontmost to true
        key code 0 using {command down}
        key code 9 using {command down}
    end tell
end tell
'''

_CLEAR_INPUT = r'''
tell application "System Events"
    tell process "WeChat"
        key code 0 using {command down}
        key code 51
    end tell
end tell
'''

_GET_FRONTMOST_PROCESS = r'''
tell application "System Events"
    try
        return name of first process whose frontmost is true
    on error
        return ""
    end try
end tell
'''

_RESTORE_FRONTMOST_PROCESS = r'''
on run argv
    set targetName to item 1 of argv
    tell application "System Events"
        try
            if exists process targetName then
                set frontmost of process targetName to true
            end if
        end try
    end tell
end run
'''


def _run_osascript(
    script: str,
    *,
    timeout: float = 15.0,
    args: tuple[str, ...] = (),
) -> str:
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-", *args],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SenderError("macOS 界面脚本执行失败") from exc
    if result.returncode != 0:
        detail = result.stderr.strip().lower()
        if "not allowed assistive access" in detail or "assistive" in detail:
            raise SenderError("未授予终端或运行程序辅助功能权限")
        if "微信没有主窗口" in result.stderr:
            raise SenderError("微信进程在运行但没有主窗口，请先打开微信主窗口")
        if "微信未运行" in result.stderr:
            raise SenderError("微信未运行")
        raise SenderError("微信界面脚本执行失败")
    return result.stdout.strip()


def _frontmost_process() -> str:
    try:
        return _run_osascript(_GET_FRONTMOST_PROCESS, timeout=5).strip()
    except SenderError:
        return ""


def _restore_frontmost_process(process_name: str) -> None:
    if not process_name or process_name == "WeChat":
        return
    try:
        _run_osascript(
            _RESTORE_FRONTMOST_PROCESS,
            timeout=5,
            args=(process_name,),
        )
    except SenderError:
        logger.debug("发送完成后无法恢复前台应用：%s", process_name)


def _open_wechat_app() -> None:
    """确保微信主窗口有机会出现；窗口关闭时仅激活进程是不够的。"""

    try:
        result = subprocess.run(
            ["/usr/bin/open", "-a", "WeChat"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SenderError("无法打开微信应用") from exc
    if result.returncode != 0:
        raise SenderError("无法打开微信应用")


def _window_bounds() -> WindowBounds:
    value = _run_osascript(_GET_BOUNDS)
    try:
        x, y, width, height = (int(float(part)) for part in value.split(","))
    except (TypeError, ValueError) as exc:
        raise SenderError("无法读取微信窗口位置") from exc
    if width < 300 or height < 300:
        raise SenderError("微信主窗口尺寸异常")
    return WindowBounds(x, y, width, height)


def _clipboard_write(text: str) -> None:
    try:
        result = subprocess.run(
            ["/usr/bin/pbcopy"],
            input=text,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SenderError("无法写入系统剪贴板") from exc
    if result.returncode != 0:
        raise SenderError("无法写入系统剪贴板")


def _clipboard_read() -> str:
    try:
        result = subprocess.run(
            ["/usr/bin/pbpaste"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout if result.returncode == 0 else ""


def _screenshot(bounds: WindowBounds, path: Path) -> None:
    # 截取窗口区域，OCR 坐标天然和下面的窗口相对点击坐标一致。
    try:
        result = subprocess.run(
            [
                "/usr/sbin/screencapture",
                "-x",
                "-R",
                f"{bounds.x},{bounds.y},{bounds.width},{bounds.height}",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SenderError("无法截取微信窗口，请检查屏幕录制权限") from exc
    if result.returncode != 0 or not path.exists() or path.stat().st_size == 0:
        raise SenderError("无法截取微信窗口，请检查屏幕录制权限")


def _ocr(image: Path, binary: Path) -> OCRResult:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise SenderError("找不到 OCR 辅助程序，请先运行 build-macos-helpers.sh")
    try:
        result = subprocess.run(
            [str(binary), str(image)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SenderError("OCR 执行失败") from exc
    if result.returncode != 0:
        raise SenderError("OCR 执行失败")
    try:
        payload = json.loads(result.stdout)
        observations = tuple(
            OCRObservation(
                text=str(item.get("text", "")),
                x=float(item.get("x", 0)),
                y=float(item.get("y", 0)),
                width=float(item.get("width", 0)),
                height=float(item.get("height", 0)),
            )
            for item in payload.get("observations", [])
            if str(item.get("text", "")).strip()
        )
        return OCRResult(
            width=int(payload["width"]),
            height=int(payload["height"]),
            observations=observations,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SenderError("OCR 返回格式无效") from exc


def _compact(value: str) -> str:
    return "".join((value or "").split()).casefold()


def _is_emoji_char(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x1F000 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
        or codepoint in {0xFE0E, 0xFE0F, 0x200D, 0x20E3}
        or 0x1F3FB <= codepoint <= 0x1F3FF
    )


def _without_emoji(value: str) -> str:
    return "".join(char for char in value if not _is_emoji_char(char))


def _emoji_only(value: str) -> bool:
    return bool(value.strip()) and not _without_emoji(value).strip()


_MEMBER_COUNT_SUFFIX = re.compile(r"[（(]\d+[）)]$")


def _compact_name(value: str) -> str:
    """比较会话名时允许微信标题追加的群成员数量。"""

    compact = re.sub(r"[…⋯·\.]+$", "", _compact(value))
    return _MEMBER_COUNT_SUFFIX.sub("", compact)


def _has_exact(
    observations: Iterable[OCRObservation],
    target: str,
    *,
    x_min: float = 0.0,
    x_max: float = 1.0,
    y_min: float = 0.0,
    y_max: float = 1.0,
) -> bool:
    wanted = _compact_name(target)
    if not wanted:
        return False
    selected = [
        item
        for item in observations
        if x_min <= item.x <= x_max and y_min <= item.y <= y_max
    ]
    if any(_compact_name(item.text) == wanted for item in selected):
        return True

    # Vision 有时会把一行拆成多个 observation。只接受「同一行拼接后
    # 恰好等于目标」的情况，不能用 substring，否则 Biscoffee2 也会被
    # 当成 Biscoffee，搜索错人时可能造成误发。
    selected.sort(key=lambda item: (item.y, item.x))
    lines: list[list[OCRObservation]] = []
    for item in selected:
        if not lines or abs(item.y - lines[-1][0].y) > 0.045:
            lines.append([item])
        else:
            lines[-1].append(item)
    return any(_compact_name(" ".join(item.text for item in line)) == wanted for line in lines)


def _find_exact(observations: Iterable[OCRObservation], target: str, *, y_min: float = 0.0, y_max: float = 1.0) -> OCRObservation | None:
    wanted = _compact(target)
    for item in observations:
        if y_min <= item.y <= y_max and _compact(item.text) == wanted:
            return item
    return None


def _find_search_target(
    observations: Iterable[OCRObservation],
    target: str,
    *,
    is_group: bool = False,
) -> OCRObservation | None:
    """找搜索结果中的目标；群聊允许成员数后缀和长名称截断。"""

    wanted = _compact_name(target) if is_group else _compact(target)
    selected = [item for item in observations if 0.03 <= item.y <= 0.82]
    selected.sort(key=lambda item: (item.y, item.x))
    lines: list[list[OCRObservation]] = []
    for item in selected:
        if not lines or abs(item.y - lines[-1][0].y) > 0.045:
            lines.append([item])
        else:
            lines[-1].append(item)

    candidates: list[tuple[int, float, OCRObservation]] = []
    for line in lines:
        line.sort(key=lambda item: item.x)
        for start in range(len(line)):
            combined = ""
            for end in range(start, len(line)):
                combined += line[end].text
                value = _compact_name(combined) if is_group else _compact(combined)
                score = 0
                if value == wanted:
                    score = 4
                elif not is_group and value.endswith(wanted) and len(value) - len(wanted) <= 2:
                    score = 3
                elif is_group:
                    comparable = min(len(value), len(wanted))
                    ratio = comparable / max(len(value), len(wanted), 1)
                    truncated = any(mark in combined for mark in "…⋯·.")
                    if (
                        len(value) >= 6
                        and ratio >= (0.50 if truncated else 0.65)
                        and (wanted.startswith(value) or value.startswith(wanted))
                    ):
                        score = 2
                if score:
                    group = line[start : end + 1]
                    x_min = min(item.x for item in group)
                    y_min = min(item.y for item in group)
                    x_max = max(item.x + item.width for item in group)
                    y_max = max(item.y + item.height for item in group)
                    candidates.append(
                        (
                            score,
                            -y_min,
                            OCRObservation(combined, x_min, y_min, x_max - x_min, y_max - y_min),
                        )
                    )
                if len(value) > len(wanted) + 4:
                    break
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def _sidebar_fingerprint(observations: Iterable[OCRObservation]) -> tuple[str, ...]:
    """提取当前可见会话列表指纹，用于判断滚轮是否真的翻动。"""

    visible = [
        (_compact_name(item.text), round(item.y, 2))
        for item in observations
        if 0.10 <= item.x <= 0.40 and 0.05 <= item.y <= 0.97 and _compact_name(item.text)
    ]
    visible.sort(key=lambda item: (item[1], item[0]))
    return tuple(f"{text}@{y:.2f}" for text, y in visible)


def _find_sidebar_target(observations: Iterable[OCRObservation], target: str) -> OCRObservation | None:
    """在左侧会话列表找联系人，支持长群名被 Vision 拆成多段。"""

    wanted = _compact_name(target)
    selected = [
        item
        for item in observations
        if 0.10 <= item.x <= 0.40
        and 0.05 <= item.y <= 0.97
    ]
    selected.sort(key=lambda item: (item.y, item.x))
    lines: list[list[OCRObservation]] = []
    for item in selected:
        if not lines or abs(item.y - lines[-1][0].y) > 0.045:
            lines.append([item])
        else:
            lines[-1].append(item)

    partial_candidates: list[tuple[float, OCRObservation]] = []
    for line in lines:
        line.sort(key=lambda item: item.x)
        for start in range(len(line)):
            combined = ""
            for end in range(start, len(line)):
                combined += line[end].text
                compact = _compact_name(combined)
                if compact == wanted:
                    group = line[start : end + 1]
                    x_min = min(item.x for item in group)
                    y_min = min(item.y for item in group)
                    x_max = max(item.x + item.width for item in group)
                    y_max = max(item.y + item.height for item in group)
                    return OCRObservation(
                        text=target,
                        x=x_min,
                        y=y_min,
                        width=x_max - x_min,
                        height=y_max - y_min,
                    )
                comparable = min(len(compact), len(wanted))
                ratio = comparable / max(len(compact), len(wanted), 1)
                truncated = any(mark in combined for mark in "…⋯·.")
                prefix_match = (
                    wanted.startswith(compact)
                    or compact.startswith(wanted)
                    or any(wanted[offset:].startswith(compact) for offset in (1, 2))
                )
                # 列表列宽不足时，微信会把长群名截断。只接受较长的
                # 前缀/完整包含关系，之后还必须进入右侧标题二次确认。
                if (
                    len(compact) >= 6
                    and ratio >= (0.50 if truncated else 0.55)
                    and prefix_match
                ):
                    group = line[start : end + 1]
                    x_min = min(item.x for item in group)
                    y_min = min(item.y for item in group)
                    x_max = max(item.x + item.width for item in group)
                    y_max = max(item.y + item.height for item in group)
                    partial_candidates.append(
                        (
                            ratio,
                            OCRObservation(
                                text=combined,
                                x=x_min,
                                y=y_min,
                                width=x_max - x_min,
                                height=y_max - y_min,
                            ),
                        )
                    )
                if len(compact) > len(wanted) + 2:
                    break
    if not partial_candidates:
        return None
    return max(partial_candidates, key=lambda item: (item[0], -item[1].y))[1]


def _contains_text(
    observations: Iterable[OCRObservation],
    target: str,
    *,
    x_min: float = 0.0,
    x_max: float = 1.0,
    y_min: float = 0.0,
    y_max: float = 1.0,
) -> bool:
    wanted = _compact(target)
    if not wanted:
        return False
    selected = [
        item
        for item in observations
        if x_min <= item.x <= x_max and y_min <= item.y <= y_max
    ]
    selected.sort(key=lambda item: (item.y, item.x))
    observed = _compact(" ".join(item.text for item in selected))
    if wanted in observed:
        return True

    # Vision 可能漏掉括号、逗号等标点。仅在去除标点后仍完整包含目标时
    # 通过，避免单个短词误判为已粘贴成功。
    wanted_core = "".join(
        char for char in _without_emoji(wanted)
        if char.isalnum() or "\u4e00" <= char <= "\u9fff"
    )
    observed_core = "".join(char for char in observed if char.isalnum() or "\u4e00" <= char <= "\u9fff")
    return bool(wanted_core and wanted_core in observed_core)


def _find_send_button(observations: Iterable[OCRObservation]) -> OCRObservation | None:
    """只在窗口右下输入区寻找精确的“发送”按钮文字。"""

    candidates = [
        item
        for item in observations
        if 0.60 <= item.y <= 0.99
        and 0.55 <= item.x <= 0.99
        and _compact(item.text).endswith("发送")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.x, item.y))


def _input_region_from_button(button: OCRObservation) -> tuple[float, float, float, float]:
    """根据发送按钮 OCR 框推导输入编辑器的相对区域。"""

    # 输入框在发送按钮左侧、上方；使用按钮实际位置而非窗口固定比例。
    x_min = max(0.20, button.x - 0.66)
    x_max = min(0.95, button.x + 0.02)
    y_min = max(0.45, button.y - 0.30)
    y_max = min(0.99, button.y + 0.01)
    return x_min, x_max, y_min, y_max


class WeChatSender:
    """带目标会话确认的微信文字发送器。"""

    # 白名单会话通常位于列表前部；只做有限的小步滚动，避免把用户的
    # 列表位置大幅改变，也避免在错误会话上长时间操作。
    _SIDEBAR_SCROLL_DELTAS = (6, 6, 6, 6, 6, -6, -6, -6, -6, -6, -6)

    def __init__(self, *, repo_dir: str | Path | None = None, settle_seconds: float = 0.8) -> None:
        root = Path(repo_dir) if repo_dir else Path(__file__).resolve().parents[1]
        self._ocr_binary = root / ".build" / "vision-ocr"
        self._click_binary = root / ".build" / "mouse-click"
        self._scroll_binary = root / ".build" / "mouse-scroll"
        self._settle_seconds = settle_seconds
        self._failure_dir = root / "var" / "wechat-sender-failures"

    def _click(self, bounds: WindowBounds) -> None:
        if not self._click_binary.is_file() or not os.access(self._click_binary, os.X_OK):
            raise SenderError("找不到鼠标辅助程序，请先运行 build-macos-helpers.sh")
        # 输入区位于微信主窗口下方约 90% 处；坐标基于实时窗口位置和尺寸，
        # 不依赖固定屏幕分辨率或用户的窗口摆放位置。
        x = bounds.x + int(bounds.width * 0.68)
        y = bounds.y + int(bounds.height * 0.91)
        self._click_point(x, y, "微信输入区")

    def _click_point(self, x: int, y: int, label: str) -> None:
        try:
            result = subprocess.run(
                [str(self._click_binary), str(x), str(y)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SenderError(f"无法点击{label}") from exc
        if result.returncode != 0:
            raise SenderError(f"无法点击{label}，请检查辅助功能权限")

    def _scroll_sidebar(self, bounds: WindowBounds, delta: int) -> None:
        """在左侧列表发送独立滚轮事件，不用按住鼠标拖动列表。"""

        if not self._scroll_binary.is_file() or not os.access(self._scroll_binary, os.X_OK):
            raise SenderError("找不到滚动辅助程序，请先运行 build-macos-helpers.sh")
        x = bounds.x + int(bounds.width * 0.20)
        y = bounds.y + int(bounds.height * 0.55)
        try:
            result = subprocess.run(
                [str(self._scroll_binary), str(x), str(y), str(delta)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SenderError("无法滚动微信会话列表") from exc
        if result.returncode != 0:
            raise SenderError("无法滚动微信会话列表，请检查辅助功能权限")

    def _save_failure_artifact(
        self,
        image: Path,
        ocr_result: OCRResult,
        *,
        target_name: str,
        reason: str,
    ) -> None:
        """保留最近失败的窗口截图和 OCR 元数据，便于定位布局差异。"""

        try:
            self._failure_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self._failure_dir, 0o700)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            prefix = self._failure_dir / f"{stamp}-{int(time.time() * 1000) % 1000:03d}"
            shutil.copy2(image, prefix.with_suffix(".png"))
            payload = {
                "target_name": target_name,
                "reason": reason,
                "width": ocr_result.width,
                "height": ocr_result.height,
                "observations": [item.__dict__ for item in ocr_result.observations],
            }
            prefix.with_suffix(".json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.chmod(prefix.with_suffix(".json"), 0o600)
            logger.info("已保存发送诊断截图：%s.png", prefix)
        except OSError:
            logger.debug("保存发送诊断截图失败", exc_info=True)

    def _confirm_target_title(self, bounds: WindowBounds, target_name: str, phase: str) -> None:
        """只接受窗口顶部的精确标题，避免正文中的同名文字造成错会话。"""

        for attempt in range(2):
            with tempfile.TemporaryDirectory(prefix="wxauto-title-") as temp_dir:
                image = Path(temp_dir) / "title.png"
                _screenshot(bounds, image)
                title_ocr = _ocr(image, self._ocr_binary)
                if _has_exact(
                    title_ocr.observations,
                    target_name,
                    x_min=0.30,
                    x_max=0.90,
                    y_min=0.0,
                    y_max=0.20,
                ):
                    return
                if attempt == 0:
                    time.sleep(0.25)
                    continue
                self._save_failure_artifact(
                    image,
                    title_ocr,
                    target_name=target_name,
                    reason=f"{phase}未确认顶部会话标题",
                )
        raise SenderError(f"{phase}未确认到目标标题，已放弃发送")

    def _sidebar_snapshot(
        self, bounds: WindowBounds, target_name: str
    ) -> tuple[OCRObservation | None, tuple[str, ...]]:
        with tempfile.TemporaryDirectory(prefix="wxauto-sidebar-") as temp_dir:
            image = Path(temp_dir) / "sidebar.png"
            _screenshot(bounds, image)
            sidebar_ocr = _ocr(image, self._ocr_binary)
        return (
            _find_sidebar_target(sidebar_ocr.observations, target_name),
            _sidebar_fingerprint(sidebar_ocr.observations),
        )

    def _is_current_target(self, bounds: WindowBounds, target_name: str) -> bool:
        """如果右侧已经是目标会话，避免为了再次定位而打开搜索浮层。"""

        try:
            with tempfile.TemporaryDirectory(prefix="wxauto-current-title-") as temp_dir:
                image = Path(temp_dir) / "current-title.png"
                _screenshot(bounds, image)
                title_ocr = _ocr(image, self._ocr_binary)
            return _has_exact(
                title_ocr.observations,
                target_name,
                x_min=0.30,
                x_max=0.90,
                y_min=0.0,
                y_max=0.20,
            )
        except SenderError:
            return False

    def _click_sidebar_target(self, bounds: WindowBounds, target_name: str) -> bool:
        # 首先检查当前可见列表，然后只做几次小步滚动。私信和群聊都走
        # 这条路径；找到会话后立即停止，不会继续滚动或拖动列表。
        previous_fingerprint: tuple[str, ...] | None = None
        unchanged_by_direction: dict[int, int] = {1: 0, -1: 0}
        for attempt, delta in enumerate((None, *self._SIDEBAR_SCROLL_DELTAS)):
            if attempt and delta is not None:
                try:
                    self._scroll_sidebar(bounds, delta)
                except SenderError:
                    logger.debug("滚动会话列表失败", exc_info=True)
                    return False
                time.sleep(0.35)
                try:
                    bounds = _window_bounds()
                except SenderError:
                    return False

            target, fingerprint = self._sidebar_snapshot(bounds, target_name)
            if delta is not None and fingerprint and fingerprint == previous_fingerprint:
                direction = 1 if delta > 0 else -1
                unchanged_by_direction[direction] += 1
                if unchanged_by_direction[direction] >= 2:
                    logger.info("会话列表在当前方向已到边界")
                    continue
            elif delta is not None:
                unchanged_by_direction[1 if delta > 0 else -1] = 0
            previous_fingerprint = fingerprint
            if target is None:
                continue
            # 点击会话名称所在行的稳定区域，不在头像上按压，也不拖动。
            click_ratio = max(0.16, min(0.29, target.x + target.width / 2))
            click_x = bounds.x + int(click_ratio * bounds.width)
            click_y = bounds.y + int((target.y + target.height / 2) * bounds.height)
            self._click_point(click_x, click_y, "左侧会话列表")
            # 列表 OCR 可能只看到了群名长前缀。点击后重新截图右侧标题，
            # 只有完整标题匹配才算选中了目标，否则交给最后的搜索兜底。
            for _ in range(3):
                time.sleep(0.25)
                try:
                    after_click_bounds = _window_bounds()
                except SenderError:
                    continue
                if self._is_current_target(after_click_bounds, target_name):
                    return True
            logger.warning("左侧列表点击后未确认目标标题：%s", target_name)
            return False
        return False

    def _input_click_candidates(self, bounds: WindowBounds) -> list[tuple[int, int]]:
        """从实际发送按钮位置推导输入区点击点，兼容窗口移动、缩放和多屏。"""

        try:
            with tempfile.TemporaryDirectory(prefix="wxauto-layout-") as temp_dir:
                image = Path(temp_dir) / "layout.png"
                _screenshot(bounds, image)
                layout_ocr = _ocr(image, self._ocr_binary)
            button = _find_send_button(layout_ocr.observations)
        except SenderError:
            button = None
        if button is not None:
            # 发送按钮左侧是编辑器，向左约 18% 窗口宽度取安全点击点。
            x_ratio = max(0.32, min(0.78, button.x - 0.18))
            y_ratio = max(0.60, min(0.92, button.y - 0.08))
            return [(bounds.x + int(bounds.width * x_ratio), bounds.y + int(bounds.height * y_ratio))]
        # 只有按钮 OCR 暂时不可用时才退回少量相对候选点。
        return [
            (bounds.x + int(bounds.width * x_ratio), bounds.y + int(bounds.height * y_ratio))
            for x_ratio, y_ratio in ((0.62, 0.84), (0.68, 0.88), (0.58, 0.90))
        ]

    def _paste_and_confirm(self, bounds: WindowBounds, target_name: str, text: str) -> None:
        # 每次根据当前窗口截图重新估计输入区，窗口移动到外接显示器也不影响。
        for click_x, click_y in self._input_click_candidates(bounds):
            self._confirm_target_title(bounds, target_name, "粘贴前")
            self._click_point(click_x, click_y, "微信输入区")
            try:
                _run_osascript(_CLEAR_INPUT)
            except SenderError:
                # 清理失败时仍可尝试下一位置；最终 OCR 是硬性门槛。
                continue
            _clipboard_write(text)
            _run_osascript(_PASTE_ONLY)
            time.sleep(0.35)
            with tempfile.TemporaryDirectory(prefix="wxauto-ocr-") as temp_dir:
                image = Path(temp_dir) / "draft.png"
                _screenshot(bounds, image)
                draft_ocr = _ocr(image, self._ocr_binary)
                # 回复后缀较长时，微信可能把输入内容折成多行；输入区
                # 只要完整包含目标文本即可，联系人标题此前已单独确认。
                button = _find_send_button(draft_ocr.observations)
                if button is not None:
                    x_min, x_max, y_min, y_max = _input_region_from_button(button)
                else:
                    x_min, x_max, y_min, y_max = 0.25, 0.95, 0.60, 0.99
                if _contains_text(
                    draft_ocr.observations,
                    text,
                    x_min=x_min,
                    x_max=x_max,
                    y_min=y_min,
                    y_max=y_max,
                ):
                    return
                # Vision OCR 不会返回纯 emoji。会话标题、输入框焦点和粘贴
                # 动作都已在前面确认，此时用剪贴板回读兜底，避免把合法的
                # 「😂」当成粘贴失败而重复尝试。
                if _emoji_only(text) and _clipboard_read() == text:
                    return
                self._save_failure_artifact(
                    image,
                    draft_ocr,
                    target_name=target_name,
                    reason="根据发送按钮推导的输入区未识别完整回复",
                )
        raise SenderError("回复未确认进入输入区，已放弃发送")

    def _draft_present(self, bounds: WindowBounds, text: str) -> bool | None:
        """返回输入区是否仍有回复；None 表示截图/OCR 无法安全判断。"""

        try:
            with tempfile.TemporaryDirectory(prefix="wxauto-send-check-") as temp_dir:
                image = Path(temp_dir) / "after-send.png"
                _screenshot(bounds, image)
                result = _ocr(image, self._ocr_binary)
            button = _find_send_button(result.observations)
            if button is None:
                return None
            x_min, x_max, y_min, y_max = _input_region_from_button(button)
            return _contains_text(
                result.observations,
                text,
                x_min=x_min,
                x_max=x_max,
                y_min=y_min,
                y_max=y_max,
            )
        except SenderError:
            logger.warning("发送后无法通过 OCR 判断输入区是否清空")
            return None

    def _post_send_check(self, bounds: WindowBounds, text: str) -> bool | None:
        """发送动作后延迟复查；复查只用于记录，不决定是否重发。"""

        last_status: bool | None = None
        for attempt, pause in enumerate((0.35, 0.55, 0.85), start=1):
            time.sleep(pause)
            last_status = self._draft_present(bounds, text)
            if last_status is False:
                logger.info("发送动作后已确认输入框清空（第 %d 次复查）", attempt)
                return False
            if last_status is True:
                logger.info("发送动作后第 %d 次复查仍识别到输入内容", attempt)
            else:
                logger.info("发送动作后第 %d 次复查暂时无法判断输入区", attempt)
        logger.warning("发送动作已执行，但界面清空状态未确认；不会自动重发")
        return last_status

    def _click_send_button(self, bounds: WindowBounds, target_name: str, text: str) -> None:
        with tempfile.TemporaryDirectory(prefix="wxauto-button-") as temp_dir:
            image = Path(temp_dir) / "button.png"
            _screenshot(bounds, image)
            button_ocr = _ocr(image, self._ocr_binary)
            button = _find_send_button(button_ocr.observations)
            if button is None:
                self._save_failure_artifact(
                    image,
                    button_ocr,
                    target_name=target_name,
                    reason="回车后未识别到右下角发送按钮",
                )
                raise SenderError("回车未发送且未识别到发送按钮", send_attempted=True)
            click_x = bounds.x + int((button.x + button.width / 2) * bounds.width)
            click_y = bounds.y + int((button.y + button.height / 2) * bounds.height)
        try:
            self._confirm_target_title(bounds, target_name, "点击发送按钮前")
            self._click_point(click_x, click_y, "微信发送按钮")
        except SenderError as exc:
            raise SenderError(str(exc), send_attempted=True) from exc
        logger.info("发送按钮已点击，已确认发送动作")
        self._post_send_check(bounds, text)
        logger.info("回车未生效，已改用微信发送按钮完成发送")

    def _search_queries(self, target_name: str, is_group: bool) -> tuple[str, ...]:
        if not is_group:
            return (target_name,)
        compact = "".join(target_name.split())
        prefix = compact[: max(6, min(10, len(compact)))]
        return tuple(dict.fromkeys((target_name, prefix)))

    def _search_and_select(
        self, bounds: WindowBounds, target_name: str, *, is_group: bool
    ) -> bool:
        """搜索只作为列表兜底；群聊失败时再尝试足够长的名称前缀。"""

        for query in self._search_queries(target_name, is_group):
            _run_osascript(_ACTIVATE_AND_SEARCH)
            time.sleep(self._settle_seconds)
            _run_osascript(_CLEAR_INPUT)
            _clipboard_write(query)
            _run_osascript(_PASTE_ONLY)
            target_observation = None
            current_bounds = bounds
            for _ in range(3):
                time.sleep(0.35)
                current_bounds = _window_bounds()
                with tempfile.TemporaryDirectory(prefix="wxauto-search-") as temp_dir:
                    image = Path(temp_dir) / "search.png"
                    _screenshot(current_bounds, image)
                    search_ocr = _ocr(image, self._ocr_binary)
                target_observation = _find_search_target(
                    search_ocr.observations, target_name, is_group=is_group
                )
                if target_observation is not None:
                    break
            if target_observation is None:
                continue
            click_x = current_bounds.x + int(
                (target_observation.x + target_observation.width / 2) * current_bounds.width
            )
            click_y = current_bounds.y + int(
                (target_observation.y + target_observation.height / 2) * current_bounds.height
            )
            self._click_point(click_x, click_y, "搜索结果")
            time.sleep(self._settle_seconds)
            try:
                self._confirm_target_title(_window_bounds(), target_name, "搜索进入会话后")
                return True
            except SenderError:
                logger.warning("搜索结果标题不匹配，继续尝试：%s", query)
        return False

    def send(self, target_name: str, text: str, *, is_group: bool = False) -> None:
        if not target_name.strip():
            raise SenderError("目标会话名为空")
        if not text.strip():
            raise SenderError("回复内容为空")

        old_clipboard = _clipboard_read()
        previous_frontmost = _frontmost_process()
        try:
            # 微信已经有可用主窗口时直接激活，避免每条消息都重复等待
            # ``open -a`` 的启动稳定时间；窗口不存在时仍走完整启动校验。
            try:
                _run_osascript(_ACTIVATE_ONLY, timeout=5)
            except SenderError:
                _open_wechat_app()
                time.sleep(max(self._settle_seconds, 1.2))
                _run_osascript(_ACTIVATE_ONLY)
                time.sleep(self._settle_seconds)
            bounds = _window_bounds()
            selected_from_sidebar = self._is_current_target(bounds, target_name)
            if selected_from_sidebar:
                logger.info("当前已在目标会话，跳过列表点击和搜索：%s", target_name)
            else:
                selected_from_sidebar = self._click_sidebar_target(bounds, target_name)
            if not selected_from_sidebar:
                if not self._search_and_select(bounds, target_name, is_group=is_group):
                    raise SenderError("搜索结果未确认到目标会话，已放弃发送")
            time.sleep(self._settle_seconds)
            bounds = _window_bounds()
            self._confirm_target_title(bounds, target_name, "进入会话后")

            self._paste_and_confirm(bounds, target_name, text)
            try:
                _run_osascript(
                    r'''
tell application "System Events"
    tell process "WeChat"
        key code 36
    end tell
end tell
'''
                )
            except SenderError as exc:
                raise SenderError("按回车发送失败", send_attempted=True) from exc
            time.sleep(0.55)
            remaining = self._draft_present(bounds, text)
            if remaining is True:
                logger.warning("回车后输入区仍保留回复，尝试点击发送按钮")
                self._click_send_button(bounds, target_name, text)
            elif remaining is None:
                logger.warning("已按回车，但界面清空状态未确认；不再重复发送")
            else:
                logger.info("已向已确认会话按下发送键")
        finally:
            # 尽量恢复用户原来的剪贴板；恢复失败不影响已经完成的发送。
            try:
                _clipboard_write(old_clipboard)
            except SenderError:
                logger.debug("恢复剪贴板失败")
            _restore_frontmost_process(previous_frontmost)
