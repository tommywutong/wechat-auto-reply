"""macOS 微信自动回复 —— 走辅助功能 API。

为什么这条路值得单独做：微信支持手机和 Mac 同时在线，消息是同一份。
Mac 端自动回复，效果上就等于替你的 iPhone 回了消息，而且不需要越狱、
不需要 Mac 长期插着手机、不会被 iOS 沙盒挡住。对大多数人这是
Apple 生态里最省事的方案。

前提：
  1. macOS 版微信已登录
  2. 系统设置 → 隐私与安全性 → 辅助功能 → 勾选终端（或你跑脚本的 App）
  3. pip install pyobjc-framework-ApplicationServices requests

用法：
    export WXAUTO_SERVER=http://127.0.0.1:8848
    export WXAUTO_TOKEN=<和服务端一致>
    export WXAUTO_ACCOUNT=私人号   # 跑多个微信号时用来区分，见下
    python macos/wechat_mac_bot.py --dry-run
    python macos/wechat_mac_bot.py

关于 WXAUTO_ACCOUNT：限流和去重是按「账号」隔离的，不是按平台。
  - 两个不同的微信号分别跑在 Mac 和安卓上 → 填不同的值（或都留空）
  - 同一个微信号在 Mac 和安卓同时登录 → 两端填相同的值，避免重复回复
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
import time
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("wechat-mac")

# AppleScript 片段。微信 Mac 版没有开放 AppleScript 字典，只能通过
# System Events 走辅助功能树。控件层级随版本会变，改版本时调这里。
_LIST_UNREAD = """
tell application "System Events"
    if not (exists process "WeChat") then return "ERR:微信未运行"
    tell process "WeChat"
        if (count of windows) = 0 then return "ERR:微信没有打开的窗口"
        set out to ""
        try
            set convRows to rows of table 1 of scroll area 1 of splitter group 1 of window 1
        on error
            return "ERR:找不到会话列表，可能是微信版本变了"
        end try
        repeat with r in convRows
            try
                set labels to value of static texts of UI element 1 of r
                set desc to description of r
                -- 未读会话的辅助功能描述里会带未读条数
                if desc contains "未读" or desc contains "unread" then
                    set out to out & (item 1 of labels) & "\\n"
                end if
            end try
        end repeat
        return out
    end tell
end tell
"""

_OPEN_AND_READ = """
on run argv
    set targetName to item 1 of argv
    tell application "System Events"
        tell process "WeChat"
            set convRows to rows of table 1 of scroll area 1 of splitter group 1 of window 1
            repeat with r in convRows
                try
                    set labels to value of static texts of UI element 1 of r
                    if (item 1 of labels) is targetName then
                        select r
                        delay 0.6
                        exit repeat
                    end if
                end try
            end repeat

            -- 消息区最后一条静态文本即最新消息
            try
                set msgTexts to value of static texts of UI element 1 of ¬
                    (last row of table 1 of scroll area 1 of splitter group 2 of splitter group 1 of window 1)
                return item 1 of msgTexts
            on error
                return "ERR:读不到消息内容"
            end try
        end tell
    end tell
end run
"""

_SEND = """
on run argv
    set targetName to item 1 of argv
    set replyText to item 2 of argv
    tell application "System Events"
        tell process "WeChat"
            set frontmost to true
            delay 0.3

            -- 发之前必须重新选中目标会话。
            -- 读消息和发送之间隔着 3-12 秒的随机延迟，这期间用户完全
            -- 可能切到别的聊天；直接 keystroke 会把话打进别人的对话框
            -- 然后发出去。宁可不发，也不能发错人。
            set found to false
            try
                set convRows to rows of table 1 of scroll area 1 of splitter group 1 of window 1
                repeat with r in convRows
                    try
                        set labels to value of static texts of UI element 1 of r
                        if (item 1 of labels) is targetName then
                            select r
                            delay 0.5
                            set found to true
                            exit repeat
                        end if
                    end try
                end repeat
            end try
            if not found then
                return "ERR:发送前找不到会话「" & targetName & "」，已放弃，没有发出任何内容"
            end if

            -- 尽量把焦点明确放进输入框。找不到就退回直接键入——
            -- 但此时会话已经确认选中，风险可控。
            try
                set inputArea to text area 1 of scroll area 2 of splitter group 2 of splitter group 1 of window 1
                set focused of inputArea to true
                delay 0.2
            end try

            keystroke replyText
            delay 0.3
            key code 36  -- Return
        end tell
    end tell
    return "OK"
end run
"""

# 诊断用：把微信的辅助功能树整棵打出来。
#
# 原来这里是「按写死的路径逐段探测」，断在哪就报哪一段。那样只能回答
# 「我猜的路径对不对」，回答不了真正要紧的那个问题：这棵树里到底有没有
# 东西。微信 Mac 4.x 是重写过的客户端，有的版本除了窗口那三个红黄绿
# 按钮之外什么都不暴露——这种情况下换选择器是白费力气，得先分清楚是
# 「路径写错了」还是「压根没有树」。
#
# 所以改成递归遍历，并统计有多少个表格/滚动区/文本框。
# 深度和条数都设了上限，免得在大界面上跑到超时。
_DOCTOR = """
global gOut, gCount, gTables, gScrolls, gTextAreas, gStatics

on dumpEl(el, depth)
    -- 顶层已经 global 过一次了，处理器里再声明一次是稳妥写法：
    -- 少了它，下面的赋值会变成处理器内的局部变量，统计永远是 0
    global gOut, gCount, gTables, gScrolls, gTextAreas, gStatics

    if gCount > 120 then return
    set gCount to gCount + 1

    set pad to ""
    repeat depth times
        set pad to pad & "  "
    end repeat
    set entryLine to pad & "- "

    tell application "System Events"
        set klass to "?"
        try
            set klass to (class of el as text)
        end try
        set entryLine to entryLine & klass

        if klass contains "table" then set gTables to gTables + 1
        if klass contains "scroll" then set gScrolls to gScrolls + 1
        if klass contains "text area" then set gTextAreas to gTextAreas + 1
        if klass contains "static text" then set gStatics to gStatics + 1

        try
            set d to (description of el) as text
            if d is not "" then set entryLine to entryLine & " desc=" & d
        end try
        try
            set nm to (name of el) as text
            if nm is not "" then set entryLine to entryLine & " name=" & nm
        end try
        try
            set vs to (value of el) as text
            if length of vs > 24 then set vs to (text 1 thru 24 of vs) & "…"
            if vs is not "" then set entryLine to entryLine & " value=" & vs
        end try

        set kids to {}
        if depth < 5 then
            try
                set kids to UI elements of el
            end try
        end if
    end tell

    set gOut to gOut & entryLine & return

    repeat with k in kids
        dumpEl(k, depth + 1)
    end repeat
end dumpEl


set gOut to ""
set gCount to 0
set gTables to 0
set gScrolls to 0
set gTextAreas to 0
set gStatics to 0

tell application "System Events"
    if not (exists process "WeChat") then
        return "微信没在运行。先打开并登录 macOS 版微信。"
    end if
    set winCount to count of windows of process "WeChat"
    set gOut to "微信进程: 在运行" & return & "窗口数: " & winCount & return
    if winCount = 0 then
        return gOut & return & "微信在运行但没有打开的窗口——点一下 Dock 里的微信图标把主窗口调出来。"
    end if

    -- 有些重写过的客户端（Electron、自研跨平台框架）默认不生成完整的
    -- 辅助功能树，只有被明确要求时才生成。这是两个已知的开关，
    -- 平时由读屏软件负责打开。试一下，成不成都不影响后面。
    set switchNote to "没打开（这个版本不认这两个开关）"
    try
        set value of attribute "AXManualAccessibility" of application process "WeChat" to true
        set switchNote to "AXManualAccessibility 打开了"
    end try
    try
        set value of attribute "AXEnhancedUserInterface" of application process "WeChat" to true
        set switchNote to switchNote & " / AXEnhancedUserInterface 打开了"
    end try
    delay 1.5
    set gOut to gOut & "辅助功能增强开关: " & switchNote & return

    set w to window 1 of process "WeChat"
    try
        set gOut to gOut & "窗口1 名称: " & (name of w) & return
    end try
end tell

set gOut to gOut & return & "=== 界面树（最多 5 层 / 120 个元素）===" & return
dumpEl(w, 0)

set gOut to gOut & return & "=== 统计 ===" & return
set gOut to gOut & "  元素总数: " & gCount & return
set gOut to gOut & "  表格(table): " & gTables & return
set gOut to gOut & "  滚动区(scroll area): " & gScrolls & return
set gOut to gOut & "  输入框(text area): " & gTextAreas & return
set gOut to gOut & "  文字(static text): " & gStatics & return

if gCount <= 6 or (gTables = 0 and gStatics = 0) then
    set gOut to gOut & return & "VERDICT:EMPTY" & return
else
    set gOut to gOut & return & "VERDICT:HASTREE" & return
end if

return gOut
"""


def run_applescript(script: str, *args: str, timeout: float = 30) -> str:
    """执行 AppleScript。失败返回以 ERR: 开头的字符串，绝不抛给主循环。"""
    try:
        result = subprocess.run(
            ["osascript", "-", *args],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "ERR:AppleScript 执行超时"

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not allowed assistive access" in stderr:
            return "ERR:未授予辅助功能权限，去 系统设置→隐私与安全性→辅助功能 勾选终端"
        return f"ERR:{stderr}"
    return result.stdout.strip()


class EngineClient:
    def __init__(self, base_url: str, token: str, account: str = "") -> None:
        self._url = base_url.rstrip("/") + "/reply"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._account = account

    def decide(self, chat_name: str, text: str, is_group: bool, mentioned_me: bool) -> Optional[dict]:
        try:
            resp = requests.post(
                self._url,
                json={
                    "chat_id": f"macos:{chat_name}",
                    "chat_name": chat_name,
                    "text": text,
                    "sender_name": chat_name,
                    "is_group": is_group,
                    "mentioned_me": mentioned_me,
                    "platform": "macos",
                    "account": self._account,
                },
                headers=self._headers,
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("规则服务不可用，本轮跳过: %s", exc)
            return None


def tick(engine: EngineClient, dry_run: bool) -> None:
    listing = run_applescript(_LIST_UNREAD)
    if listing.startswith("ERR:"):
        logger.warning(listing[4:])
        return

    names = [n.strip() for n in listing.splitlines() if n.strip()]
    if not names:
        return

    for name in names[:5]:
        text = run_applescript(_OPEN_AND_READ, name)
        if text.startswith("ERR:") or not text:
            logger.info("「%s」读取失败：%s", name, text[4:] or "空内容")
            continue

        logger.info("「%s」最后一条: %s", name, text)

        is_group = bool(re.search(r"\(\d+\)$", name))
        decision = engine.decide(
            chat_name=re.sub(r"\(\d+\)$", "", name),
            text=text,
            is_group=is_group,
            mentioned_me="@" in text,
        )

        if not decision or not decision["should_reply"]:
            logger.info("  不回复：%s", decision["reason"] if decision else "服务不可用")
            continue

        reply = decision["text"]
        delay = decision.get("delay_seconds", 0)
        if dry_run:
            logger.info("  [DRY-RUN] 本应回复: %s（延迟 %.1fs）", reply, delay)
            continue

        logger.info("  等待 %.1fs 后回复: %s", delay, reply)
        time.sleep(delay)
        # 把会话名一起传进去：发之前要重新选中，否则等待期间用户
        # 切走了就会发错人
        result = run_applescript(_SEND, name, reply)
        if result.startswith("ERR:"):
            logger.error("  发送失败：%s", result[4:])
        else:
            logger.info("  已发送")


_LIST_CONTACTS = """
tell application "System Events"
    if not (exists process "WeChat") then return "ERR:微信没在运行"
    tell process "WeChat"
        if (count of windows) = 0 then return "ERR:微信没有打开的窗口"
        set out to ""
        try
            set convRows to rows of table 1 of scroll area 1 of splitter group 1 of window 1
        on error
            return "ERR:读不到会话列表，先跑 --doctor 看看"
        end try
        repeat with r in convRows
            try
                set labels to value of static texts of UI element 1 of r
                set out to out & (item 1 of labels) & "\\n"
            end try
        end repeat
        return out
    end tell
end tell
"""


def contacts() -> int:
    """列出会话列表里的名字。

    白名单要填名字，但「填哪个名字」本身就不好回答——微信号？昵称？备注？
    答案是：程序看到的就是会话列表里显示的那个（有备注就是备注名）。
    与其让用户猜，不如直接把程序看到的原样打出来，照抄即可。
    """
    print()
    print("=" * 56)
    print("  最近的会话（白名单就填这里的名字，照抄即可）")
    print("=" * 56)
    print()

    output = run_applescript(_LIST_CONTACTS)
    if output.startswith("ERR:"):
        print(f"  {output[4:]}")
        return 1

    names = [n.strip() for n in output.splitlines() if n.strip()]
    if not names:
        print("  一个会话都没读到。先确认微信开着，或者跑 --doctor 排查。")
        return 1

    for name in names:
        print(f"    {name}")

    print()
    print("  用法：把想自动回复的人抄进 core/config.yaml 的 scope.allow_contacts：")
    print()
    print("    scope:")
    print("      allow_contacts:")
    for name in names[:2]:
        print(f'        - "{name}"')
    print()
    print("  填了之后，只有名单里的人会收到自动回复，其他人一律不回。")
    print("  多余的空格和大小写不影响匹配。")
    print()
    return 0


def wechat_version() -> str:
    """读 Mac 版微信的版本号。

    这条信息比界面树本身还关键：微信 Mac 4.x 是重写过的客户端，
    3.x 和 4.x 的辅助功能暴露程度完全不同。不知道版本号，
    「读不到会话列表」就没法判断是选择器过时了还是这条路本身走不通。
    """
    try:
        result = subprocess.run(
            [
                "defaults",
                "read",
                "/Applications/WeChat.app/Contents/Info.plist",
                "CFBundleShortVersionString",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "读不到"
    return result.stdout.strip() or "读不到"


def doctor() -> int:
    """把微信的界面结构打出来。

    这个方案靠读辅助功能树定位控件，而那个树的结构随微信版本变化。
    出问题时不该让用户对着「找不到会话列表」干瞪眼——把实际看到的
    结构打出来，才有得改。

    但更要紧的是分清两种失败：树在那儿只是路径写错了（能改），
    还是微信压根不暴露界面结构（改不了）。所以这里不再只报
    「断在哪一段」，而是报整棵树有多大。
    """
    print()
    print("=" * 56)
    print("  微信界面结构诊断")
    print("=" * 56)
    print()

    version = wechat_version()
    print(f"  微信版本：{version}")
    print()

    # 遍历整棵树要挨个查属性，元素多的时候比普通调用慢不少，给足时间
    output = run_applescript(_DOCTOR, timeout=120)
    if output.startswith("ERR:"):
        print(f"  执行失败：{output[4:]}")
        print()
        print("  最常见的原因是没授权：")
        print("    系统设置 → 隐私与安全性 → 辅助功能 → 勾选「终端」")
        print("  勾了之后要把终端完全退出（⌘Q）再重开，授权才生效。")
        return 1

    verdict_empty = "VERDICT:EMPTY" in output
    print(output.replace("VERDICT:EMPTY", "").replace("VERDICT:HASTREE", "").rstrip())
    print()

    if verdict_empty:
        print("  " + "=" * 52)
        print("  ❌ 微信没有把界面结构暴露给系统的辅助功能接口。")
        print("  " + "=" * 52)
        print()
        print("  上面除了窗口那几个按钮之外基本什么都没有——会话列表、")
        print("  聊天内容、输入框，一个都读不到。这不是选择器写错了，")
        print("  改几行代码解决不了。")
        print()
        print("  在放弃之前，还有两件事值得试：")
        print()
        print("    1) 确认微信主窗口真的开着（不是缩在 Dock 里、")
        print("       也不是只剩一个小的聊天窗），然后重新跑一次本检查。")
        print()
        print("    2) 如果你装的是微信 4.x，试试装回 3.8.x 版本。")
        print("       4.x 是重写过的客户端，很多自动化都是在它上面失效的。")
        print()
        print("  两条都不行的话，Mac 这条路在你这台机器上就是走不通的，")
        print("  该换方案了——把这个窗口整个截图发给帮你配置的人。")
        return 1

    print("  ✅ 读得到界面结构。把这段输出发给帮你配置的人，")
    print("     对着实际的树把选择器调准，就能继续跑 --dry-run 了。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="macOS 微信自动回复")
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--dry-run", action="store_true", help="只打印不发送")
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="打印微信界面结构，用来排查「读不到会话」这类问题",
    )
    parser.add_argument("--once", action="store_true", help="只扫一轮就退出")
    parser.add_argument(
        "--contacts",
        action="store_true",
        help="列出会话列表里的名字，用来填白名单（allow_contacts）",
    )
    args = parser.parse_args()

    # 诊断和列联系人都不需要连规则服务，也不需要 token
    if args.doctor:
        return doctor()
    if args.contacts:
        return contacts()

    token = os.environ.get("WXAUTO_TOKEN", "")
    if not token:
        logger.error("请设置 WXAUTO_TOKEN，与规则服务保持一致")
        return 1

    account = os.environ.get("WXAUTO_ACCOUNT", "")
    engine = EngineClient(
        os.environ.get("WXAUTO_SERVER", "http://127.0.0.1:8848"), token, account
    )
    if account:
        logger.info("驱动的微信号: %s", account)
    logger.info("启动，每 %.0fs 扫一次%s", args.interval, "（DRY-RUN）" if args.dry_run else "")
    if args.dry_run:
        # 说清楚 dry-run 到底「干」在哪：它不发消息，但读消息这件事
        # 本身要靠点开会话，所以未读会被标成已读。这一点不提前讲，
        # 用户会以为自己被偷看了消息。
        logger.info("DRY-RUN：不会发出任何消息。但读取需要点开会话，未读会被标为已读。")

    try:
        while True:
            tick(engine, args.dry_run)
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("收到中断，退出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
