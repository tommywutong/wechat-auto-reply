"""在终端里试回复效果，不碰微信、不发任何消息。

用来在真正开启之前，把文案和规则调顺。

用法：
    python -m core.preview                      # 用 core/config.yaml
    python -m core.preview core/config.example.yaml

进去之后直接打字模拟别人发来的消息，回车看结果。
特殊命令：
    /group 内容      当作群消息（未 @ 你）
    /at    内容      当作群消息且 @ 了你
    /reload          改完配置文件后重新加载
    /quit            退出
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .engine import ReplyEngine
from .models import IncomingMessage

BANNER = """
============================================================
  回复效果预览  ——  只显示会回什么，不会真的发出去
============================================================
  直接打字 = 模拟别人私聊你
  /group 在吗   = 模拟群消息（没 @ 你）
  /at    在吗   = 模拟群消息（@ 了你）
  /reload       = 改完配置后重新加载
  /quit         = 退出
------------------------------------------------------------"""


def _for_preview(config):
    """预览用的配置副本。

    关掉两样东西，因为它们会掩盖真正要看的文案效果：
      - 总开关：还没启用时也该能试
      - 时段限制：半夜调文案时不该全是「不在时段内」
    其余（敏感词、群聊策略、黑白名单、限流）全部照常，
    否则预览就不能反映真实行为了。
    """
    import copy

    preview = copy.deepcopy(config)
    preview.enabled = True
    preview.active_hours = []
    return preview


def main(argv: list[str]) -> int:
    # 顺序：命令行参数 > WXAUTO_CONFIG（服务端用的就是它）> 默认路径。
    # 跟服务读同一个环境变量，免得预览的和真跑的不是同一份配置。
    if len(argv) > 1:
        path = Path(argv[1])
    else:
        path = Path(os.environ.get("WXAUTO_CONFIG") or "core/config.yaml")

    if not path.exists():
        fallback = Path("core/config.example.yaml")
        if fallback.exists():
            print(f"没找到 {path}，改用 {fallback}")
            path = fallback
        else:
            print(f"找不到配置文件：{path}")
            return 1

    try:
        config = load_config(path)
    except ConfigError as exc:
        print(f"配置有问题：{exc}")
        return 1

    # 关键：不传 state_path，冷却计数只留在内存里，
    # 预览不会占用真实额度，也不会影响正在运行的服务。
    engine = ReplyEngine(_for_preview(config))

    print(BANNER)
    print(f"  当前配置：{path}（{len(config.rules)} 条规则）")
    if config.active_hours:
        print("  预览忽略了「自动回复时段」限制，方便你随时调文案。")
        print("  敏感词、群聊策略、黑白名单这些照常生效。")
    print("------------------------------------------------------------")

    counter = 0
    while True:
        try:
            raw = input("\n对方说> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not raw:
            continue
        if raw in ("/quit", "/exit", "/q"):
            return 0
        if raw == "/reload":
            try:
                config = load_config(path)
                engine = ReplyEngine(_for_preview(config))
                print(f"已重新加载，{len(config.rules)} 条规则")
            except ConfigError as exc:
                print(f"配置有问题，沿用旧的：{exc}")
            continue

        is_group = False
        mentioned = False
        if raw.startswith("/group "):
            is_group, raw = True, raw[len("/group "):]
        elif raw.startswith("/at "):
            is_group, mentioned, raw = True, True, raw[len("/at "):]

        # 每条用不同的会话名，避免被冷却挡住看不到效果
        counter += 1
        message = IncomingMessage(
            chat_id=f"preview-{counter}",
            chat_name=f"测试联系人{counter}",
            text=raw,
            is_group=is_group,
            mentioned_me=mentioned,
        )

        decision = engine.decide(message)

        if decision.should_reply:
            print(f"  ✅ 会回复：{decision.text}")
            print(f"     （{decision.reason}，{decision.delay_seconds:.0f} 秒后发出）")
        else:
            print(f"  ⛔ 不会回复：{decision.reason}")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
