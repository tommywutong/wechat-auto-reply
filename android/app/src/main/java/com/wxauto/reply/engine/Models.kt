package com.wxauto.reply.engine

/**
 * 内嵌规则引擎的数据结构。
 *
 * 这一层刻意不依赖任何 Android API，方便单独做单元测试，
 * 也方便和 Python 版引擎（core/engine.py）保持行为一致。
 */

data class Message(
    val chatId: String,
    val chatName: String,
    val text: String,
    val senderName: String = "",
    val isGroup: Boolean = false,
    val mentionedMe: Boolean = false,
)

private val MEMBER_COUNT = Regex("""[（(]\s*\d+\s*[)）]\s*$""")

/**
 * 归一化会话名，用于和用户填的名单比对。
 *
 * 用户手打名字时很容易多个空格、大小写不一致；而这里比对失败的后果是
 * 「名单里的人收不到回复」或者「名单外的人收到了」——两种都很糟，
 * 而且都不会报错，用户只会觉得程序坏了。所以比对前统一归一化。
 *
 * 刻意不做模糊匹配（比如包含关系）：那会把「小王他哥」也算成「小王」。
 */
fun normalizeChatName(name: String): String =
    MEMBER_COUNT.replace(name, "").trim().lowercase()

data class Decision(
    val shouldReply: Boolean,
    val reason: String,
    val text: String? = null,
    val delayMillis: Long = 0L,
    val ruleName: String? = null,
) {
    companion object {
        fun skip(reason: String) = Decision(shouldReply = false, reason = reason)
    }
}

enum class GroupPolicy {
    NEVER,        // 群消息一律不回
    ONLY_AT_ME,   // 只在被 @ 时回
    ALWAYS;       // 群里任何消息都回（很容易刷屏，慎用）

    companion object {
        fun from(raw: String?): GroupPolicy =
            entries.firstOrNull { it.name.equals(raw, ignoreCase = true) } ?: ONLY_AT_ME
    }
}

/**
 * 一条规则。keywords 命中任意一个即可；pattern 是正则。
 * 两者都为空表示「全部匹配」。
 */
data class Rule(
    val name: String,
    val keywords: List<String> = emptyList(),
    val pattern: String? = null,
    val replies: List<String> = emptyList(),
) {
    /** 正则只编译一次；写错了就当这条规则永不命中，而不是让整个引擎崩掉。 */
    private val regex: Regex? = pattern
        ?.takeIf { it.isNotBlank() }
        ?.let { runCatching { Regex(it) }.getOrNull() }

    fun matches(text: String): Boolean {
        if (keywords.isEmpty() && pattern.isNullOrBlank()) return true
        if (keywords.any { it.isNotBlank() && text.contains(it) }) return true
        return regex?.containsMatchIn(text) == true
    }
}

enum class ReplyMode {
    KEYWORD,   // 本机关键词匹配：免费、不联网、装完即用
    AI;        // 交给模型按人设生成

    companion object {
        fun from(raw: String?): ReplyMode =
            entries.firstOrNull { it.name.equals(raw, ignoreCase = true) } ?: KEYWORD
    }
}

/** AI 怎么接。 */
enum class AiSource {
    OWN_KEY,   // 自己注册的 key，独立使用不依赖别人
    RELAY;     // 用别人给的地址，人设和 key 都在对方那边

    companion object {
        fun from(raw: String?): AiSource =
            entries.firstOrNull { it.name.equals(raw, ignoreCase = true) } ?: OWN_KEY
    }
}

data class AiExample(val them: String, val me: String)

/**
 * 人设与应对攻略。
 *
 * 这是「像真人」和「像 QQ 自动回复」的分界线：这里描述的是判断依据，
 * 不是问答对。你不用穷举别人可能说什么。
 */
data class PersonaConfig(
    val identity: String = "",
    val tone: String = "",
    val playbook: String = "",
    val boundaries: List<String> = emptyList(),
    val maxChars: Int = 35,
    val examples: List<AiExample> = emptyList(),
) {
    /** 没写人设就别用 AI——空人设生成出来只会是客服腔。 */
    fun isConfigured(): Boolean = identity.isNotBlank() || playbook.isNotBlank()
}

data class AiConfig(
    val source: AiSource = AiSource.OWN_KEY,
    val baseUrl: String = "",
    val apiKey: String = "",
    val model: String = "",
    val relayUrl: String = "",
    val relayToken: String = "",
)

data class EngineConfig(
    /** 总开关。关掉之后引擎对任何消息都返回「不回复」。 */
    val enabled: Boolean = false,

    val signature: String = "（自动回复）",

    /** 自动回复时段，单位是「距零点的分钟数」。都为 -1 表示全天。 */
    val activeFromMinute: Int = -1,
    val activeToMinute: Int = -1,

    val replyToPrivate: Boolean = true,
    val groupPolicy: GroupPolicy = GroupPolicy.ONLY_AT_ME,

    /** 非空时只对这些人生效。 */
    val allowContacts: List<String> = emptyList(),
    val blockContacts: List<String> = emptyList(),
    val blockKeywords: List<String> = emptyList(),

    val cooldownSeconds: Int = 1800,

    /** 每日总量上限。只有每小时上限的话，跑满一天是 720 条。 */
    val maxPerDay: Int = 100,

    /**
     * 两条回复之间的最小间隔（跨会话），单位秒。
     *
     * 这一条是所有限流里最重要的：冷却是按会话算的，所以三十个人同时
     * 发消息时，程序会在几十秒内挨个回完。真人不可能一秒切一个会话，
     * 这是最容易被识别的机器特征。命中时把发送时间往后推，不丢消息。
     */
    val minIntervalSeconds: Int = 45,

    /** 按回复长度追加的「打字时间」，单位毫秒/字。 */
    val typingMillisPerChar: Int = 120,
    val maxPerChatPerDay: Int = 5,
    val maxPerHour: Int = 30,
    val minDelaySeconds: Int = 3,
    val maxDelaySeconds: Int = 12,

    val replyMode: ReplyMode = ReplyMode.KEYWORD,
    val persona: PersonaConfig = PersonaConfig(),
    val ai: AiConfig = AiConfig(),

    val rules: List<Rule> = emptyList(),

    /** 所有规则都没命中时回这句；留空表示不回。 */
    val fallbackText: String = "",
)
