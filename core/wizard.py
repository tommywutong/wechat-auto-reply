"""开场问几个问题，把整套回复内容生成出来。

为什么要有这个：人设是这套系统里最难写的东西。让一个不写代码的人
面对「identity / tone / playbook」三个空框，多半就放弃了，或者随手
填几个「友好」「专业」这种空词——那生成出来必然是客服腔。

但同样这个人，你问他「有人约你吃饭你一般怎么回」，他张口就能答。

所以这里把「写人设」翻译成十来个具体问题。答案不是拿去喂模型润色的
（那样每次跑出来的东西都不一样，也没法测），而是按确定的规则拼装成
人设、关键词规则和兜底话术——**问题本身就是人设**。

同一套问题和拼装规则在安卓端也有一份
（android/.../engine/SetupWizard.kt），两边结果必须一致。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from .providers import PROVIDERS

Answer = Union[str, list[str]]


@dataclass
class Option:
    id: str
    label: str


@dataclass
class Question:
    id: str
    prompt: str
    kind: str  # single | multi | text
    options: list[Option] = field(default_factory=list)
    hint: str = ""
    optional: bool = False
    placeholder: str = ""


# ---------------------------------------------------------------- 问题

QUESTIONS: list[Question] = [
    Question(
        id="who",
        prompt="平时主要是谁给你发微信？",
        kind="multi",
        hint="可以多选，用逗号隔开",
        options=[
            Option("work", "同事、工作上的人"),
            Option("client", "客户、甲方、合作方"),
            Option("friend", "朋友"),
            Option("family", "家里人"),
        ],
    ),
    Question(
        id="busy",
        prompt="你一般为什么没马上回消息？",
        kind="multi",
        hint="可以多选，用逗号隔开",
        options=[
            Option("work", "在上班或上课，手机不方便看"),
            Option("hands", "手上忙着别的事，腾不开"),
            Option("out", "经常在外面、在路上"),
            Option("later", "看到了，但不太想马上回"),
            Option("unsure", "有些消息不知道怎么回，想想再说"),
        ],
    ),
    Question(
        id="style",
        prompt="别人发「在吗」，下面哪句最像你会回的？",
        kind="single",
        hint="选不出来就挑个最接近的，下一题可以自己写",
        options=[
            Option("casual", "在，怎么了"),
            Option("polite", "在的，您说"),
            Option("warm", "在呢！咋啦"),
            Option("brief", "在"),
        ],
    ),
    Question(
        id="greeting",
        prompt="上面那句不太像的话，你自己会怎么回「在吗」？",
        kind="text",
        hint="像的话直接回车跳过。写了的话以你写的为准",
        optional=True,
    ),
    Question(
        id="appointment",
        prompt="别人说「明天下午有空不，一起吃个饭」，你想怎么处理？",
        kind="single",
        hint="下面只是示意，实际发出去的话会用你自己的语气",
        options=[
            Option("hold", "「我看下日程，晚点回你」—— 先拖住"),
            Option("refuse", "「最近有点排不开，下次吧」—— 直接推掉"),
            Option("ask", "「什么事啊，你先说说」—— 先问清楚"),
        ],
    ),
    Question(
        id="progress",
        prompt="别人催「那个东西弄得怎么样了」呢？",
        kind="single",
        options=[
            Option("rough", "「在弄了，这两天给你结果」—— 给个大概"),
            Option("working", "「在弄着呢」—— 不给时间"),
            Option("person", "「这个我等下本人回你」—— 交给自己"),
        ],
    ),
    Question(
        id="stranger",
        prompt="别人发「加个群呗，有福利」这种呢？",
        kind="single",
        options=[
            Option("polite", "「这个我不太需要，谢谢」—— 客气拒绝"),
            Option("blunt", "「不需要」—— 干脆"),
            Option("later", "「我晚点看看」—— 不表态"),
        ],
    ),
    Question(
        id="emoji",
        prompt="别人发「哈哈哈哈太逗了」，你回哪个？",
        kind="single",
        hint="看的是符号，不是内容",
        options=[
            Option("none", "确实"),
            Option("emoji", "确实 😂"),
            Option("mark", "确实！"),
            Option("both", "确实！😂"),
        ],
    ),
    Question(
        id="night",
        prompt="晚上 11 点有人给你发消息，你希望它怎么办？",
        kind="single",
        options=[
            Option("day", "别回，等我第二天自己看"),
            Option("always", "照回，我本来也常半夜回消息"),
            Option("work", "只在白天上班时间回（9 点到 6 点）"),
        ],
    ),
    Question(
        id="never",
        prompt="有什么是绝对不能替你答应的？",
        kind="multi",
        hint="可以多选，也可以一个都不选",
        options=[
            Option("money", "不谈钱、不谈价格"),
            Option("gossip", "不评价别人、不聊八卦"),
            Option("favor", "不答应帮忙投票、点赞、转发"),
            Option("meet", "不答应任何见面、吃饭的邀约"),
            Option("work", "不对工作上的具体安排表态"),
        ],
    ),
    Question(
        id="only_for",
        prompt="先只对哪几个人开？",
        kind="text",
        hint="强烈建议先填三五个熟人。多个用逗号隔开",
        optional=True,
        placeholder=(
            "填你在微信里看到的那个名字——设了备注就填备注名，没设就填昵称，"
            "不是微信号。空格和大小写不影响。"
            "不确定叫什么？装完双击「查看联系人名字」就能照抄。"
            "留空 = 对所有人开，风险高很多"
        ),
    ),
]


# ---------------------------------------------------------------- 语气表
#
# 四种说话方式 × 四类常见情况。这十六句话是整套东西的地基：
# 模型模仿的是这些句子，关键词模式直接发的也是这些句子。
# 写的时候一律用「人真的会打出来的字」，不要用书面语。

_VOICE: dict[str, dict[str, str]] = {
    "casual": {
        "tone": "句子短，一般就一两句话。口语，该省的字就省。"
        "不用敬语，不说「您」。熟人之间那种随便的语气。",
        "greeting": "在，怎么了",
        "chat": "确实",
    },
    "polite": {
        "tone": "说话客气，称呼对方用「您」，但不啰嗦。不用网络用语和缩写。",
        "greeting": "在的，您说",
        "chat": "是挺有意思的",
    },
    "warm": {
        "tone": "语气热情，愿意多聊两句，可以开点玩笑。别显得敷衍。",
        "greeting": "在呢！咋啦",
        "chat": "哈哈是吧，我也这么觉得",
    },
    "brief": {
        "tone": "能少说就少说，经常一两个字就完事。不寒暄，不解释。",
        "greeting": "在",
        "chat": "嗯",
    },
}

_APPOINTMENT: dict[str, dict[str, str]] = {
    "hold": {
        "line": "有人约时间、约见面：说要确认一下日程，等我本人回，"
        "不要当场答应任何时间点。",
        "casual": "我看下日程，晚点回你",
        "polite": "我看一下安排，稍后回复您",
        "warm": "我瞅一眼日程啊，一会儿回你",
        "brief": "我看下日程",
    },
    "refuse": {
        "line": "有人约时间、约见面：说最近排不开，客气地推掉，不要答应。",
        "casual": "最近有点排不开，下次吧",
        "polite": "最近安排比较满，实在抱歉",
        "warm": "哎最近真排不开，下回一定",
        "brief": "最近排不开",
    },
    "ask": {
        "line": "有人约时间、约见面：先问清楚是什么事、大概什么时候，"
        "不要当场答应。",
        "casual": "什么事啊，你先说说",
        "polite": "方便先说下是什么事吗",
        "warm": "啥事呀，你先说说看",
        "brief": "什么事",
    },
}

_PROGRESS: dict[str, dict[str, str]] = {
    "rough": {
        "line": "有人问进度、催什么时候好：给个模糊的时间感觉"
        "（今天之内、这两天），绝对不给具体日期，也不打包票。",
        "casual": "在弄了，这两天给你结果",
        "polite": "正在处理，这两天给您答复",
        "warm": "在弄啦，这两天就给你信儿",
        "brief": "在弄，这两天",
    },
    "working": {
        "line": "有人问进度、催什么时候好：说在弄了，不要给任何时间点。",
        "casual": "在弄着呢",
        "polite": "正在处理中",
        "warm": "在弄啦，别急",
        "brief": "在弄",
    },
    "person": {
        "line": "有人问进度、催什么时候好：说等我本人回你，不要自己答。",
        "casual": "这个我等下本人回你",
        "polite": "这个稍后我本人回复您",
        "warm": "这个我等会儿亲自回你哈",
        "brief": "等下回你",
    },
}

_STRANGER: dict[str, dict[str, str]] = {
    "polite": {
        "line": "推销、拉群、发广告、求点赞投票：客气但明确地拒绝，一句话结束。",
        "casual": "这个我不太需要，谢谢",
        "polite": "谢谢，这个我暂时不需要",
        "warm": "谢谢啦，这个我先不用",
        "brief": "不需要，谢谢",
    },
    "blunt": {
        "line": "推销、拉群、发广告、求点赞投票：直接说不需要，一句话，不解释。",
        "casual": "不需要",
        "polite": "不需要，谢谢",
        "warm": "这个就不用啦",
        "brief": "不需要",
    },
    "later": {
        "line": "推销、拉群、发广告、求点赞投票：说我晚点看，不表任何态、"
        "不答应任何事。",
        "casual": "我晚点看看",
        "polite": "我稍后看一下",
        "warm": "行我晚点瞅瞅",
        "brief": "晚点看",
    },
}

_WHO_LABEL = {
    "work": "同事和工作上的人",
    "client": "客户、甲方这类合作方",
    "friend": "朋友",
    "family": "家里人",
}

_BUSY_LINE = {
    "work": "白天要上班，手机不太方便看",
    "hands": "手上常忙着别的事，腾不开",
    "out": "经常在外面、在路上",
    "later": "消息看得到，但常常不太想马上回",
    "unsure": "有些消息我得想想怎么回，就先放着了",
}

# 兜底文案只用一条理由，多选时取第一条
_BUSY_ORDER = ("work", "hands", "out", "later", "unsure")

# 回复长度上限直接从说话风格推断，不再单独问一题：
# 选了「在」的人不会突然写三句话，问了也是多余的一道题。
_MAX_CHARS_BY_STYLE = {"brief": 20, "casual": 30, "polite": 40, "warm": 45}

# 勾选的边界 → 写进提示词的硬性要求。
# 原来这题是个空框，让人对着它想「有什么绝对不能答应」——
# 那是最难答的一种题，多数人会直接跳过，于是这一段就永远是空的。
_NEVER_LINE = {
    "money": "不谈钱和价格，一律说等我本人聊",
    "gossip": "不评价任何第三方的人和公司",
    "favor": "不答应帮忙投票、点赞、转发这类请求",
    "meet": "不答应任何见面、吃饭的邀约",
    "work": "不对工作上的具体安排表态，说等我本人回",
}

# 几点回。深夜自动回复本身就可疑，默认避开。
_ACTIVE_HOURS = {
    "day": ["09:00-23:00"],
    "always": [],
    "work": ["09:00-18:00"],
}

# 表情和感叹号是两回事：有人爱发表情但从不用感叹号。
# 之前把它们混成一个「用不用」的程度问题，是设计错误。
_EMOJI_LINE = {
    "none": "不用感叹号，也不发表情。",
    "emoji": "会发表情，但不用感叹号。",
    "mark": "会用感叹号，但基本不发表情。",
    "both": "感叹号和表情都会用，但别过头。",
}

# 旧版本存下来的答案，映射到新的选项上，免得重装一次人设就变了
_EMOJI_LEGACY = {"some": "emoji", "lots": "both"}


def _uses_exclaim(emoji: str) -> bool:
    return emoji in ("mark", "both")


def _uses_emoji(emoji: str) -> bool:
    return emoji in ("emoji", "both")


@dataclass
class WizardResult:
    """问答生成的整套回复内容。"""

    identity: str
    tone: str
    playbook: str
    boundaries: list[str]
    max_chars: int
    examples: list[dict[str, str]]
    rules: list[dict[str, object]]
    fallback_text: str

    active_hours: list[str] = field(default_factory=lambda: ["09:00-23:00"])
    """只在这些时段自动回。空 = 全天。深夜自动回复本身就可疑，默认避开。"""

    allow_contacts: list[str] = field(default_factory=list)
    """只对这些人自动回复。空 = 对所有人。

    这是所有防风控手段里最有效的一条：被举报是真正会出事的路径，
    而熟人不会举报你。技术上的限流再怎么做，也不如「只对不会举报你的人开」。
    """


def _pick(answers: dict[str, Answer], qid: str, default: str) -> str:
    value = answers.get(qid)
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value) if value else default


def _split_lines(raw: str) -> list[str]:
    """中英文逗号、顿号、换行都当分隔符——用户不该被要求分清全角半角。"""
    text = raw.replace("，", "\n").replace(",", "\n").replace("、", "\n")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _tune(text: str, emoji: str) -> str:
    """说了不用感叹号，就别在示范里塞感叹号。

    示范和语气说明自相矛盾时，模型会照着示范走——示范的分量更重。
    注意只管感叹号：爱发表情和爱用感叹号是两回事。
    """
    if _uses_exclaim(emoji):
        return text
    return text.replace("！", "").replace("!", "")


def build_result(answers: dict[str, Answer]) -> WizardResult:
    """答案 → 整套回复内容。纯函数，没有随机、没有网络，因此可测。"""
    style = _pick(answers, "style", "casual")
    if style not in _VOICE:
        style = "casual"
    voice = _VOICE[style]

    # busy 是多选：「在上班」和「不知道怎么回」可以同时成立
    busy_raw = answers.get("busy") or []
    busy_ids = [b for b in (busy_raw if isinstance(busy_raw, list) else [busy_raw])
                if b in _BUSY_LINE]
    if not busy_ids:
        busy_ids = ["hands"]

    emoji = _pick(answers, "emoji", "none")
    emoji = _EMOJI_LEGACY.get(emoji, emoji)
    if emoji not in _EMOJI_LINE:
        emoji = "none"
    appointment = _APPOINTMENT.get(_pick(answers, "appointment", "hold"), _APPOINTMENT["hold"])
    progress = _PROGRESS.get(_pick(answers, "progress", "rough"), _PROGRESS["rough"])
    stranger = _STRANGER.get(_pick(answers, "stranger", "polite"), _STRANGER["polite"])

    def say(table: dict[str, str]) -> str:
        return _tune(table.get(style, table["casual"]), emoji)

    # ---- 我是谁 ----
    who_raw = answers.get("who") or []
    who_ids = who_raw if isinstance(who_raw, list) else [who_raw]
    labels = [_WHO_LABEL[w] for w in who_ids if w in _WHO_LABEL]
    identity_parts = []
    if labels:
        identity_parts.append(f"平时给我发消息的主要是{'、'.join(labels)}。")
    reasons = [_BUSY_LINE[b] for b in _BUSY_ORDER if b in busy_ids]
    identity_parts.append("我" + "；".join(reasons) + "。")
    identity_parts.append("微信经常隔一会儿才翻一次，看到会回。")
    identity = "".join(identity_parts)

    # ---- 我说话的方式 ----
    tone_parts = [voice["tone"], _EMOJI_LINE.get(emoji, _EMOJI_LINE["none"])]
    if style == "brief":
        tone_parts.append("一句话能说完就别说两句。")
    elif style in ("polite", "warm"):
        tone_parts.append("最多两三句，别写成段落。")
    tone = "".join(tone_parts)

    # ---- 应对攻略 ----
    # 前三条是所有人都要有的基线，后三条按回答替换。
    # 最后一条（看不懂就交给本人）是最重要的兜底，必须永远在。
    playbook_lines = [
        "有人问在不在、忙不忙：说在，但说明手上有事，等下回。",
        appointment["line"],
        progress["line"],
        stranger["line"],
        "纯闲聊、发表情、分享链接：随便接一两句，别太热情也别冷场。",
        "看不懂对方在说什么，或者事情比较重要：直接说等我本人回你，"
        "不要硬猜着接话。",
    ]
    if "client" in who_ids:
        # 选了客户、甲方，说明回错的代价高，攻略要更保守
        playbook_lines.append(
            "涉及工作、报价、交付时间的事：一律不表态，说等我本人回。"
        )
    if "unsure" in busy_ids:
        # 用户自己说了「有些消息不知道怎么回」——那就把模型也调保守些，
        # 拿不准时先拖住，别替他现编一个答案
        playbook_lines.append(
            "凡是拿不准该怎么回的：宁可先拖着，说等我本人回你，"
            "绝对不要自己编一个答案。"
        )
    playbook = "\n".join(playbook_lines)

    # ---- 绝对不能答应的 ----
    never_raw = answers.get("never") or []
    never_ids = never_raw if isinstance(never_raw, list) else [never_raw]
    boundaries = [_NEVER_LINE[n] for n in _NEVER_LINE if n in never_ids]

    # ---- 示范语气 ----
    # 用户自己写的那句优先级最高：那是他真实的声音，
    # 比我们按风格挑的任何一句都准。
    greeting_raw = answers.get("greeting")
    if isinstance(greeting_raw, str) and greeting_raw.strip():
        greeting = greeting_raw.strip()
    else:
        greeting = _tune(voice["greeting"], emoji)

    examples = [
        {"them": "在吗", "me": greeting},
        {
            "them": "明天下午有空不，一起吃个饭",
            "me": say(appointment),
            "note": "约时间一律不当场答应",
        },
        {"them": "那个东西弄得怎么样了", "me": say(progress)},
        {
            # 爱发表情的人，示范里也得有表情——不然示范和语气说明打架，
            # 模型会照着示范走
            "them": "哈哈哈哈太逗了",
            "me": _tune(voice["chat"], emoji) + ("😂" if _uses_emoji(emoji) else ""),
            "note": "闲聊就随便接，别过度热情",
        },
    ]

    # ---- 关键词规则（给不用 AI 的人）----
    # 同一批答案同时生成两套东西：选关键词模式的人也能直接用，
    # 不用再自己想文案。
    rules: list[dict[str, object]] = [
        {
            "name": "问在不在",
            "keywords": ["在吗", "在么", "在不在", "忙吗", "忙不忙"],
            "replies": [greeting],
        },
        {
            "name": "约时间",
            "keywords": ["有空", "有时间", "见个面", "见面", "吃饭", "约个"],
            "replies": [say(appointment)],
        },
        {
            "name": "问进度",
            "keywords": ["什么时候", "进度", "好了吗", "做完", "弄完", "怎么样了"],
            "replies": [say(progress)],
        },
        {
            "name": "推销拉群",
            "keywords": ["了解一下", "推广", "加个群", "投票", "点赞", "帮忙转发"],
            "replies": [say(stranger)],
        },
    ]

    # ---- 兜底 ----
    busy_text = "我" + next(_BUSY_LINE[b] for b in _BUSY_ORDER if b in busy_ids)
    if style == "polite":
        fallback_text = f"{busy_text}，看到会尽快回复您"
    elif style == "brief":
        fallback_text = f"{busy_text}，晚点回"
    else:
        fallback_text = f"{busy_text}，看到会尽快回你"

    only_for = answers.get("only_for")
    allow_contacts = (
        _split_lines(str(only_for)) if isinstance(only_for, str) and only_for.strip() else []
    )

    return WizardResult(
        identity=identity,
        tone=tone,
        playbook=playbook,
        boundaries=boundaries,
        max_chars=_MAX_CHARS_BY_STYLE.get(style, 30),
        examples=examples,
        rules=rules,
        fallback_text=fallback_text,
        allow_contacts=allow_contacts,
        active_hours=_ACTIVE_HOURS.get(_pick(answers, "night", "day"), _ACTIVE_HOURS["day"]),
    )


# ---------------------------------------------------------------- 输出

def _block(text: str, indent: str) -> str:
    """YAML 块标量。保留换行，用户之后用文本编辑器改起来也直观。"""
    lines = text.split("\n")
    return "|\n" + "\n".join(f"{indent}{line}" for line in lines)


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_yaml(
    result: WizardResult,
    reply_mode: str = "rules_then_ai",
    provider: str = "doubao",
) -> str:
    """渲染成 config.yaml。

    手写而不是 yaml.safe_dump：dump 会把注释全丢掉，而这份文件的读者
    是要照着注释自己改的人。
    """
    lines: list[str] = [
        "# 这份配置是「开场问答」生成的。",
        "# 想改就直接改——下面每一段都是人话，不用懂 YAML。",
        "# 想重新答一遍：python3 -m core.wizard",
        "",
        "enabled: true",
        f"reply_mode: {reply_mode}     # ai / rules / rules_then_ai",
        "",
        'signature: "（自动回复）"      # 留个尾巴，让对方知道不是你本人在回',
        "",
        "# 只在这些时段自动回，其余时间收到消息也不回。",
        "# 深夜自动回复本身就是个可疑信号，默认避开。留空 = 全天。",
        "active_hours:"
        + ("" if result.active_hours else " []"),
        *[f'  - "{r}"' for r in result.active_hours],
        "",
        "scope:",
        "  reply_to_private: true",
        "  reply_to_group: only_at_me",
        "  block_contacts: []        # 写在这里的人永远不自动回",
    ]

    if result.allow_contacts:
        lines.append("  # 只对下面这些人自动回复，其他人一律不回。")
        lines.append("  # 这是最有效的防风控手段——真正会出事的路径是被举报，")
        lines.append("  # 而熟人不会举报你。想放开时把这几行删掉即可。")
        lines.append("  allow_contacts:")
        lines.extend(f"    - {_quote(name)}" for name in result.allow_contacts)
    else:
        lines.append("  # allow_contacts 非空时，只对名单里的人自动回复。")
        lines.append("  # 强烈建议先填三五个熟人跑几天，确认没问题再放开。")
        lines.append("  allow_contacts: []")

    lines += [
        "",
        "limits:",
        "  per_chat_cooldown_seconds: 1800",
        "  max_replies_per_chat_per_day: 5",
        "  global_max_replies_per_hour: 30",
        "  min_delay_seconds: 3",
        "  max_delay_seconds: 12",
        "",
        "persona:",
        f"  identity: {_block(result.identity, '    ')}",
        "",
        f"  tone: {_block(result.tone, '    ')}",
        "",
        f"  playbook: {_block(result.playbook, '    ')}",
        "",
    ]

    if result.boundaries:
        lines.append("  boundaries:")
        lines.extend(f"    - {_quote(b)}" for b in result.boundaries)
    else:
        lines.append("  boundaries: []            # 绝对不能替你答应的事，一行一条")
    lines.append("")

    lines.append(f"  max_chars: {result.max_chars}")
    lines.append("")
    lines.append("  # 这几组是照着你的回答写的。改成你自己真会说的话，效果会更好。")
    lines.append("  examples:")
    for ex in result.examples:
        lines.append(f"    - them: {_quote(ex['them'])}")
        lines.append(f"      me: {_quote(ex['me'])}")
        if ex.get("note"):
            lines.append(f"      note: {_quote(ex['note'])}")
    lines.append("")

    lines.append("# 下面这些只在 reply_mode 是 rules 或 rules_then_ai 时生效。")
    lines.append("rules:")
    for rule in result.rules:
        lines.append(f"  - name: {rule['name']}")
        keywords = ", ".join(_quote(str(k)) for k in rule["keywords"])  # type: ignore[arg-type]
        lines.append(f"    match: {{type: keyword, any: [{keywords}]}}")
        lines.append("    reply:")
        for reply in rule["replies"]:  # type: ignore[union-attr]
            lines.append(f"      - {_quote(str(reply))}")
    lines.append("")

    lines.append("fallback:")
    lines.append("  type: text                # text / llm / none")
    lines.append(f"  text: {_quote(result.fallback_text)}")
    lines.append("")
    lines.append("# 只有 reply_mode 是 ai 或 rules_then_ai + fallback.type=llm 时才用得上。")
    lines.append("llm:")
    lines.append(f"  provider: {provider}")

    known = PROVIDERS.get(provider)
    if known is not None:
        lines.append(f"  # {known.name}")
        lines.append(f"  # key 从环境变量读：export {known.api_key_env}=你的key")
        if known.note:
            lines.append(f"  # {known.note}")
        lines.append(f"  model: {known.model}")
    else:
        lines.append("  # Claude，需要 export ANTHROPIC_API_KEY=...")
        lines.append("  model: claude-opus-5")
        lines.append("  effort: low             # 自动回复要低延迟，不需要深度推理")

    lines.append("  max_tokens: 300")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------- 终端问答

def _ask(question: Question) -> Answer:
    print()
    print(f"  {question.prompt}")
    if question.hint:
        print(f"  （{question.hint}）")

    if question.kind == "text":
        if question.placeholder:
            print(f"  {question.placeholder}")
        return input("  > ").strip()

    for index, option in enumerate(question.options, start=1):
        print(f"    {index}. {option.label}")

    while True:
        raw = input("  > ").strip()
        picks = [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]

        if not picks:
            if question.optional:
                return [] if question.kind == "multi" else ""
            print("  这题得选一个")
            continue

        chosen: list[str] = []
        bad = False
        for pick in picks:
            if not pick.isdigit() or not (1 <= int(pick) <= len(question.options)):
                print(f"  没有第 {pick} 项，重新选")
                bad = True
                break
            chosen.append(question.options[int(pick) - 1].id)
        if bad:
            continue

        if question.kind == "single":
            return chosen[0]
        return chosen


def _preview(result: WizardResult) -> None:
    print()
    print("─" * 56)
    print("  根据你的回答，生成了这些：")
    print("─" * 56)
    print()
    print("  别人说「在吗」        → " + result.examples[0]["me"])
    print("  别人约你吃饭          → " + result.examples[1]["me"])
    print("  别人问事情办得怎样    → " + result.examples[2]["me"])
    print("  别人推销、拉群        → " + result.rules[3]["replies"][0])  # type: ignore[index]
    print("  其他都没匹配上        → " + result.fallback_text)
    print()
    print(f"  回复长度上限：{result.max_chars} 字")
    if result.boundaries:
        print("  绝对不答应：" + "、".join(result.boundaries))
    print()

    # 这一条单独强调：它比其他所有限流加起来都管用
    if result.allow_contacts:
        print("  ✅ 只对这几个人开：" + "、".join(result.allow_contacts))
        print("     其他所有人一律不自动回复。")
    else:
        print("  ⚠️  会对所有人自动回复。")
        print("     真正会出事的路径是被举报，而熟人不会举报你。")
        print("     建议重答一遍，在最后一题填三五个熟人先跑几天。")
        print()
        print("     不确定该填什么名字？先装完，然后运行：")
        print("       python3 macos/wechat_mac_bot.py --contacts")
        print("     它会把程序看到的会话名原样列出来，照抄就行。")
    print()
    print("  开了 AI 模式的话，上面这些是「示范」，")
    print("  AI 会照着这个语气自己判断该说什么，不是只会回这几句。")
    print()


def _ask_engine() -> tuple[str, str]:
    """最后再问「用哪种方式回」和「接哪家模型」。

    放在最后而不是开头：前面十道题答完，用户已经看到生成的话长什么样，
    这时候他才有依据判断「这几句够不够用」。一上来就问「你要不要接 AI」，
    对一个还不知道差别在哪的人来说是没法回答的。
    """
    print("─" * 56)
    print("  最后两个问题")
    print("─" * 56)
    print()
    print("  怎么回消息？")
    print("    1. 就用上面这几句（不联网、不花钱、不用注册）")
    print("    2. 让 AI 照着这个语气现写（像真人，需要一个 key）")

    mode = "rules"
    while True:
        raw = input("  > ").strip()
        if raw in ("1", ""):
            return mode, "doubao"
        if raw == "2":
            break
        print("  输 1 或 2")

    print()
    print("  接哪家的模型？")
    ids = list(PROVIDERS)
    for i, pid in enumerate(ids, start=1):
        marker = "（推荐，聊天的中文语气最自然）" if pid == "doubao" else ""
        print(f"    {i}. {PROVIDERS[pid].name}{marker}")
    print(f"    {len(ids) + 1}. Claude（国内不好注册，谨慎选）")

    while True:
        raw = input("  > ").strip()
        if raw == "":
            return "ai", "doubao"
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(ids):
                return "ai", ids[n - 1]
            if n == len(ids) + 1:
                return "ai", "anthropic"
        print(f"  输 1 到 {len(ids) + 1}")


def run(config_path: Optional[str] = None) -> int:
    target = Path(config_path or "core/config.yaml")

    print()
    print("=" * 56)
    print("  先问你几个问题，然后把回复内容整套生成出来")
    print("=" * 56)
    print()
    print(f"  一共 {len(QUESTIONS)} 题，都是选择题，一分钟能答完。")
    print("  答完你会先看到生成的结果，不满意可以重来。")
    print("  这一步不会发任何消息。")

    answers: dict[str, Answer] = {}
    for index, question in enumerate(QUESTIONS, start=1):
        print()
        print(f"  ── 第 {index} 题 / 共 {len(QUESTIONS)} 题 ──")
        answers[question.id] = _ask(question)

    result = build_result(answers)
    _preview(result)

    confirm = input("  就用这套吗？(回车=是，输 n=重新答一遍) > ").strip().lower()
    if confirm in ("n", "no", "否"):
        return run(config_path)

    reply_mode, provider = _ask_engine()

    if target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, backup)
        print(f"  原来的配置备份到了 {backup}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        to_yaml(result, reply_mode=reply_mode, provider=provider), encoding="utf-8"
    )

    print()
    print(f"  ✅ 写好了：{target}")
    print()
    print("  下一步：")
    if reply_mode != "rules":
        known = PROVIDERS.get(provider)
        if known is not None:
            print(f"    1) 去 {known.name} 拿一个 API Key，然后：")
            print(f"       export {known.api_key_env}=你的key")
            print("    2) python3 -m core.preview   # 打字试试，不会真的发出去")
        else:
            print("    1) export ANTHROPIC_API_KEY=你的key")
            print("    2) python3 -m core.preview   # 打字试试，不会真的发出去")
    else:
        print("    python3 -m core.preview      # 打字试试，不会真的发出去")
    print()
    print("  觉得哪句话不对，直接用文本编辑器改上面那个文件，")
    print("  或者重跑 python3 -m core.wizard 重新答一遍。")
    print()
    return 0


if __name__ == "__main__":
    import sys

    try:
        sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else None))
    except (KeyboardInterrupt, EOFError):
        print("\n  取消了，什么都没改。")
        sys.exit(1)
