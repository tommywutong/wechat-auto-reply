package com.wxauto.reply.engine

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

/**
 * 配置与状态的落盘。用 SharedPreferences + JSON，不引任何第三方库——
 * 这个 App 权限很大（能读所有通知），依赖越少越容易被审查。
 */
object Storage {

    private const val PREFS = "wxauto_engine"

    private const val KEY_CONFIG = "config_json"
    private const val KEY_STATE = "state_json"
    private const val KEY_ANSWERS = "wizard_answers_json"

    fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    // ------------------------------------------------------------------ 配置

    fun loadConfig(context: Context): EngineConfig {
        val raw = prefs(context).getString(KEY_CONFIG, null)
            ?: return defaultConfig()
        return runCatching { parseConfig(JSONObject(raw)) }.getOrElse {
            // 配置损坏时回到默认值而不是崩溃；总开关默认是关的，所以安全
            defaultConfig()
        }
    }

    fun saveConfig(context: Context, config: EngineConfig) {
        prefs(context).edit().putString(KEY_CONFIG, serializeConfig(config).toString()).apply()
    }

    /** 只翻总开关，不动其他配置。给快捷开关用。 */
    fun setEnabled(context: Context, enabled: Boolean) {
        saveConfig(context, loadConfig(context).copy(enabled = enabled))
    }

    fun defaultConfig(): EngineConfig = EngineConfig(
        // 默认关闭：装完不会立刻开始替用户发消息，
        // 必须由用户主动打开开关。
        enabled = false,
        activeFromMinute = -1,
        activeToMinute = -1,
        replyToPrivate = true,
        groupPolicy = GroupPolicy.NEVER,   // 群消息默认全关，避免刷屏
        // Android 与 Mac 端一致：默认不附加机器标记。是否启用自动回复由用户自行决定，
        // 不应该每条消息都被固定尾注破坏原本语气。
        signature = "",
        cooldownSeconds = 1800,
        maxPerChatPerDay = 5,
        maxPerHour = 30,
        minDelaySeconds = 3,
        maxDelaySeconds = 12,
        rules = listOf(
            Rule(
                name = "问在不在",
                keywords = listOf("在吗", "在么", "在不在", "忙吗"),
                replies = listOf(
                    "在的，我这会儿有点事，稍后回你",
                    "在，手上忙着，等下详细说",
                ),
            ),
        ),
        fallbackText = "我现在不方便，看到会尽快回你",

        // 默认走关键词：不联网、不花钱、装完即用。
        // AI 要填 key，得用户自己决定。
        replyMode = ReplyMode.KEYWORD,

        // 人设先给一份通用的。空人设生成出来只会是客服腔，
        // 而让一个不写代码的人从零开始写人设，多半就放弃了。
        persona = PersonaConfig(
            identity = "我平时挺忙的，微信经常隔一会儿才看，看到会回。",
            tone = "句子短，一般一两句话。口语，不用敬语，不说「您」，不用感叹号，" +
                "熟人之间那种随便的语气。",
            playbook = listOf(
                "有人问在不在、忙不忙：说在，但说明手上有事，等下回。",
                "有人约时间、约见面：说要确认一下日程，等我本人回，不要当场答应任何时间点。",
                "有人问什么时候能好、进度怎么样：给个模糊的时间感觉，不给具体日期，不打包票。",
                "纯闲聊、发表情、分享链接：随便接一两句，别太热情也别冷场。",
                "推销、拉群、发广告、求点赞投票：客气但明确地拒绝，一句话结束。",
                "看不懂对方在说什么，或者事情比较重要：直接说等我本人回你，不要硬猜着接话。",
            ).joinToString("\n"),
            maxChars = 30,
            examples = listOf(
                AiExample("在吗", "在，怎么了"),
                AiExample("明天下午有空不，一起吃个饭", "我看下日程，晚点回你"),
                AiExample("哈哈哈哈太逗了", "确实"),
            ),
        ),
    )

    private fun serializeConfig(c: EngineConfig): JSONObject = JSONObject().apply {
        put("enabled", c.enabled)
        put("signature", c.signature)
        put("activeFromMinute", c.activeFromMinute)
        put("activeToMinute", c.activeToMinute)
        put("replyToPrivate", c.replyToPrivate)
        put("groupPolicy", c.groupPolicy.name)
        put("selfNicknames", JSONArray(c.selfNicknames))
        put("allowContacts", JSONArray(c.allowContacts))
        put("blockContacts", JSONArray(c.blockContacts))
        put("blockKeywords", JSONArray(c.blockKeywords))
        put("cooldownSeconds", c.cooldownSeconds)
        put("maxPerDay", c.maxPerDay)
        put("minIntervalSeconds", c.minIntervalSeconds)
        put("typingMillisPerChar", c.typingMillisPerChar)
        put("maxPerChatPerDay", c.maxPerChatPerDay)
        put("maxPerHour", c.maxPerHour)
        put("minDelaySeconds", c.minDelaySeconds)
        put("maxDelaySeconds", c.maxDelaySeconds)
        put("fallbackText", c.fallbackText)
        put("replyMode", c.replyMode.name)
        put("persona", JSONObject().apply {
            put("identity", c.persona.identity)
            put("tone", c.persona.tone)
            put("playbook", c.persona.playbook)
            put("boundaries", JSONArray(c.persona.boundaries))
            put("maxChars", c.persona.maxChars)
            put("stylePreset", c.persona.stylePreset)
            put("examples", JSONArray().apply {
                c.persona.examples.forEach {
                    put(JSONObject().put("them", it.them).put("me", it.me))
                }
            })
        })
        put("styleProfiles", JSONArray().apply {
            c.styleProfiles.forEach { profile ->
                put(JSONObject().apply {
                    put("displayName", profile.displayName)
                    put("summary", profile.summary)
                    put("sampleCount", profile.sampleCount)
                    put("examples", JSONArray().apply {
                        profile.examples.forEach { example ->
                            put(JSONObject().put("them", example.them).put("me", example.me))
                        }
                    })
                })
            }
        })
        put("ai", JSONObject().apply {
            put("source", c.ai.source.name)
            put("baseUrl", c.ai.baseUrl)
            put("apiKey", c.ai.apiKey)
            put("model", c.ai.model)
            put("relayUrl", c.ai.relayUrl)
            put("relayToken", c.ai.relayToken)
        })
        put("rules", JSONArray().apply {
            c.rules.forEach { r ->
                put(JSONObject().apply {
                    put("name", r.name)
                    put("keywords", JSONArray(r.keywords))
                    put("pattern", r.pattern ?: "")
                    put("replies", JSONArray(r.replies))
                })
            }
        })
    }

    private fun parseConfig(o: JSONObject): EngineConfig {
        val fallback = defaultConfig()
        // v1 默认把“（自动回复）”硬编码进每条消息。现在默认不加尾注，
        // 因此只迁移这一个旧默认值；用户手动填写的其他尾注保持原样。
        val storedSignature = o.optString("signature", fallback.signature)
        val signature = if (storedSignature == "（自动回复）") "" else storedSignature
        return EngineConfig(
            enabled = o.optBoolean("enabled", false),
            signature = signature,
            activeFromMinute = o.optInt("activeFromMinute", -1),
            activeToMinute = o.optInt("activeToMinute", -1),
            replyToPrivate = o.optBoolean("replyToPrivate", true),
            groupPolicy = GroupPolicy.from(o.optString("groupPolicy")),
            selfNicknames = o.optJSONArray("selfNicknames").toStringList(),
            allowContacts = o.optJSONArray("allowContacts").toStringList(),
            blockContacts = o.optJSONArray("blockContacts").toStringList(),
            blockKeywords = o.optJSONArray("blockKeywords").toStringList(),
            cooldownSeconds = o.optInt("cooldownSeconds", fallback.cooldownSeconds),
            maxPerDay = o.optInt("maxPerDay", fallback.maxPerDay),
            minIntervalSeconds = o.optInt("minIntervalSeconds", fallback.minIntervalSeconds),
            typingMillisPerChar = o.optInt("typingMillisPerChar", fallback.typingMillisPerChar),
            maxPerChatPerDay = o.optInt("maxPerChatPerDay", fallback.maxPerChatPerDay),
            maxPerHour = o.optInt("maxPerHour", fallback.maxPerHour),
            minDelaySeconds = o.optInt("minDelaySeconds", fallback.minDelaySeconds),
            maxDelaySeconds = o.optInt("maxDelaySeconds", fallback.maxDelaySeconds),
            fallbackText = o.optString("fallbackText", fallback.fallbackText),
            replyMode = ReplyMode.from(o.optString("replyMode")),
            persona = o.optJSONObject("persona").let { pj ->
                if (pj == null) PersonaConfig() else PersonaConfig(
                    identity = pj.optString("identity"),
                    tone = pj.optString("tone"),
                    playbook = pj.optString("playbook"),
                    boundaries = pj.optJSONArray("boundaries").toStringList(),
                    maxChars = pj.optInt("maxChars", 35),
                    stylePreset = pj.optString("stylePreset").trim().lowercase(),
                    examples = pj.optJSONArray("examples").let { arr ->
                        if (arr == null) emptyList() else (0 until arr.length()).mapNotNull { i ->
                            arr.optJSONObject(i)?.let { e ->
                                val them = e.optString("them")
                                val me = e.optString("me")
                                if (them.isBlank() || me.isBlank()) null else AiExample(them, me)
                            }
                        }
                    },
                )
            },
            styleProfiles = parseStoredStyleProfiles(o.optJSONArray("styleProfiles")),
            ai = o.optJSONObject("ai").let { aj ->
                if (aj == null) AiConfig() else AiConfig(
                    source = AiSource.from(aj.optString("source")),
                    baseUrl = aj.optString("baseUrl"),
                    apiKey = aj.optString("apiKey"),
                    model = aj.optString("model"),
                    relayUrl = aj.optString("relayUrl"),
                    relayToken = aj.optString("relayToken"),
                )
            },
            rules = o.optJSONArray("rules").let { arr ->
                if (arr == null) fallback.rules
                else (0 until arr.length()).mapNotNull { i ->
                    arr.optJSONObject(i)?.let { r ->
                        Rule(
                            name = r.optString("name", "规则"),
                            keywords = r.optJSONArray("keywords").toStringList(),
                            pattern = r.optString("pattern").takeIf { it.isNotBlank() },
                            replies = r.optJSONArray("replies").toStringList(),
                        )
                    }
                }
            },
        )
    }

    private fun JSONArray?.toStringList(): List<String> {
        if (this == null) return emptyList()
        return (0 until length()).mapNotNull { optString(it).takeIf { s -> s.isNotBlank() } }
    }

    private fun parseStoredStyleProfiles(array: JSONArray?): List<StyleProfile> {
        if (array == null) return emptyList()
        return (0 until array.length()).mapNotNull { index ->
            array.optJSONObject(index)?.let(::parseStyleProfile)
        }.distinctBy { normalizeChatName(it.displayName) }
    }

    /**
     * 导入 Mac 导出的脱敏画像。格式有意很窄：
     *
     * {"version":1,"profiles":[{"displayName":"...","summary":"...",
     * "sampleCount":12,"examples":[{"them":"...","me":"..."}]}]}
     *
     * 稳定 talker、Token、完整聊天记录和任意未知字段都不接受。
     */
    fun importStyleProfiles(raw: String): StyleProfileImportResult = try {
        val root = JSONObject(raw)
        val rootKeys = root.keys().asSequence().toSet()
        if (rootKeys != setOf("version", "profiles")) {
            return StyleProfileImportResult(emptyList(), "画像文件字段不正确，只能包含 version 和 profiles")
        }
        if (root.optInt("version", -1) != 1) {
            return StyleProfileImportResult(emptyList(), "不支持这个画像文件版本")
        }
        val array = root.optJSONArray("profiles")
            ?: return StyleProfileImportResult(emptyList(), "画像文件缺少 profiles")
        if (array.length() > MAX_STYLE_PROFILES) {
            return StyleProfileImportResult(emptyList(), "画像数量超过 $MAX_STYLE_PROFILES 条上限")
        }

        val profiles = ArrayList<StyleProfile>(array.length())
        val names = HashSet<String>()
        for (index in 0 until array.length()) {
            val profile = array.optJSONObject(index)
                ?: return StyleProfileImportResult(emptyList(), "第 ${index + 1} 条画像不是对象")
            val parsed = parseStyleProfile(profile, strict = true)
                ?: return StyleProfileImportResult(emptyList(), "第 ${index + 1} 条画像格式不正确")
            if (!names.add(normalizeChatName(parsed.displayName))) {
                return StyleProfileImportResult(emptyList(), "画像中有重复的会话显示名")
            }
            profiles += parsed
        }
        StyleProfileImportResult(profiles)
    } catch (_: Exception) {
        StyleProfileImportResult(emptyList(), "不是可读取的画像 JSON 文件")
    }

    private fun parseStyleProfile(object_: JSONObject, strict: Boolean = false): StyleProfile? {
        if (strict) {
            val allowed = setOf("displayName", "summary", "sampleCount", "examples")
            if (!object_.keys().asSequence().all { it in allowed }) return null
            if (!setOf("displayName", "summary", "sampleCount", "examples").all(object_::has)) return null
        }
        val displayName = object_.optString("displayName").trim()
        val summary = object_.optString("summary").trim()
        val sampleCount = object_.optInt("sampleCount", 0)
        val examples = object_.optJSONArray("examples") ?: return null
        if (displayName.isBlank() || displayName.length > MAX_STYLE_NAME_LENGTH ||
            summary.length > MAX_STYLE_SUMMARY_LENGTH || sampleCount !in 0..MAX_STYLE_SAMPLE_COUNT ||
            examples.length() > MAX_STYLE_EXAMPLES
        ) return null
        val parsedExamples = ArrayList<AiExample>(examples.length())
        for (index in 0 until examples.length()) {
            val example = examples.optJSONObject(index) ?: return null
            if (strict && (example.keys().asSequence().toSet() != setOf("them", "me"))) return null
            val them = example.optString("them").trim()
            val me = example.optString("me").trim()
            if (them.isBlank() || me.isBlank() ||
                them.length > MAX_STYLE_EXAMPLE_LENGTH || me.length > MAX_STYLE_EXAMPLE_LENGTH
            ) return null
            parsedExamples += AiExample(them, me)
        }
        return StyleProfile(displayName, summary, parsedExamples, sampleCount)
    }

    // ------------------------------------------------------------------ 连接状态

    private const val MAX_STYLE_PROFILES = 120
    private const val MAX_STYLE_NAME_LENGTH = 80
    private const val MAX_STYLE_SUMMARY_LENGTH = 600
    private const val MAX_STYLE_SAMPLE_COUNT = 5_000
    private const val MAX_STYLE_EXAMPLES = 48
    private const val MAX_STYLE_EXAMPLE_LENGTH = 240

    private const val KEY_CONNECTED = "listener_connected"

    /**
     * 监听服务是不是真的连上了。
     *
     * 为什么要单独存一个：系统设置里的那个开关只表示「用户授权过」，
     * 不表示「服务现在活着」。覆盖安装或重启之后，权限还开着但服务
     * 已经死了是很常见的情况。只查权限就显示「正在工作中」，
     * 是在骗用户——他会以为程序在跑，实际上一条消息都收不到。
     */
    fun setListenerConnected(context: Context, connected: Boolean) {
        prefs(context).edit().putBoolean(KEY_CONNECTED, connected).apply()
    }

    fun isListenerConnected(context: Context): Boolean =
        prefs(context).getBoolean(KEY_CONNECTED, false)

    // ------------------------------------------------------------------ 运行记录

    private const val KEY_EVENTS = "events_json"
    private const val MAX_EVENTS = 40

    /**
     * 记一条「刚才发生了什么」。
     *
     * 为什么需要：安卓端在手机上是个彻底的黑盒。不回复的时候用户看到的
     * 只有「没反应」，而原因可能是没授权、没有回复按钮、被白名单挡了、
     * 在冷却里、不在时段内……这些全都写在 logcat 里，而普通用户
     * 一辈子也不会去看 logcat。
     *
     * 只记会话名和判断结果，不记消息内容。
     */
    fun recordEvent(context: Context, text: String) {
        val stamp = java.time.LocalTime.now().withNano(0).toString()
        val events = loadEvents(context).toMutableList()
        events.add(0, "$stamp  $text")
        while (events.size > MAX_EVENTS) events.removeAt(events.size - 1)
        prefs(context).edit().putString(KEY_EVENTS, JSONArray(events).toString()).apply()
    }

    fun loadEvents(context: Context): List<String> {
        val raw = prefs(context).getString(KEY_EVENTS, null) ?: return emptyList()
        return runCatching { JSONArray(raw).toStringList() }.getOrElse { emptyList() }
    }

    fun clearEvents(context: Context) {
        prefs(context).edit().remove(KEY_EVENTS).apply()
    }

    // ------------------------------------------------------------------ 最近联系人

    private const val KEY_SEEN = "seen_chats_json"
    private const val MAX_SEEN = 30

    /**
     * 记下最近有消息进来的会话名。
     *
     * 为什么需要：白名单要用户填名字，但「填哪个名字」本身就不好回答——
     * 微信号？昵称？备注？而第三方 App 读不到微信的通讯录（那是微信的
     * 私有数据）。能拿到的只有「给你发过消息的人」，那恰好就够用了：
     * 设置页把这些名字列成勾选框，用户点一下就行，不用打字也不会填错。
     *
     * 只存会话名，不存任何消息内容。
     */
    fun rememberSeenChat(context: Context, chatName: String) {
        if (chatName.isBlank()) return
        val seen = loadSeenChats(context).toMutableList()
        // 已经有了就挪到最前面，保持「最近联系」的顺序
        seen.removeAll { normalizeChatName(it) == normalizeChatName(chatName) }
        seen.add(0, chatName)
        while (seen.size > MAX_SEEN) seen.removeAt(seen.size - 1)
        prefs(context).edit().putString(KEY_SEEN, JSONArray(seen).toString()).apply()
    }

    fun loadSeenChats(context: Context): List<String> {
        val raw = prefs(context).getString(KEY_SEEN, null) ?: return emptyList()
        return runCatching { JSONArray(raw).toStringList() }.getOrElse { emptyList() }
    }

    // ------------------------------------------------------------------ 开场问答

    /** 答过一次就不再自动弹问答页。 */
    fun isWizardDone(context: Context): Boolean = prefs(context).contains(KEY_ANSWERS)

    /** 存答案本身（不只是生成结果），这样重答时能把上次的选择带出来。 */
    fun saveWizardAnswers(context: Context, answers: Map<String, List<String>>) {
        val json = JSONObject()
        answers.forEach { (key, values) -> json.put(key, JSONArray(values)) }
        prefs(context).edit().putString(KEY_ANSWERS, json.toString()).apply()
    }

    fun loadWizardAnswers(context: Context): Map<String, List<String>> {
        val raw = prefs(context).getString(KEY_ANSWERS, null) ?: return emptyMap()
        return runCatching {
            val json = JSONObject(raw)
            val out = HashMap<String, List<String>>()
            json.keys().forEach { key -> out[key] = json.optJSONArray(key).toStringList() }
            out as Map<String, List<String>>
        }.getOrElse { emptyMap() }  // 存坏了就当没答过，大不了重答一遍
    }

    // ------------------------------------------------------------------ 状态

    fun stateStore(context: Context): EngineStateStore = PrefsStateStore(prefs(context))

    /**
     * 按配置造出 AI 生成器。配置不全时返回 null，
     * 引擎会因此退化成「不回复」而不是乱发。
     */
    fun aiWriter(config: EngineConfig): AiWriter? = when {
        config.replyMode != ReplyMode.AI -> null
        config.ai.source == AiSource.RELAY ->
            config.ai.relayUrl.takeIf { it.isNotBlank() }
                ?.let { RelayWriter(it, config.ai.relayToken) }
        else ->
            if (config.ai.baseUrl.isNotBlank() && config.ai.apiKey.isNotBlank())
                OpenAiCompatibleWriter(config.ai.baseUrl, config.ai.apiKey, config.ai.model)
            else null
    }

    /**
     * 标识「当前该用哪个 AI 生成器」。只要这个值没变就可以复用同一个实例，
     * 从而保住对话记忆（见 EngineHolder）。
     *
     * key 和口令只取哈希：这个字符串会在内存里留存，不该出现明文凭据。
     */
    fun aiWriterKey(config: EngineConfig): String = listOf(
        config.replyMode.name,
        config.ai.source.name,
        config.ai.baseUrl,
        config.ai.model,
        config.ai.apiKey.hashCode().toString(),
        config.ai.relayUrl,
        config.ai.relayToken.hashCode().toString(),
    ).joinToString("|")

    private class PrefsStateStore(private val prefs: SharedPreferences) : EngineStateStore {
        private val last = HashMap<String, Long>()
        private val perChat = HashMap<String, List<Long>>()
        private var recent: List<Long> = emptyList()
        private val rotation = HashMap<String, Int>()
        private var lastSend: Long = 0L

        init {
            runCatching {
                val o = JSONObject(prefs.getString(KEY_STATE, "{}") ?: "{}")
                o.optJSONObject("last")?.let { j ->
                    j.keys().forEach { k -> last[k] = j.optLong(k) }
                }
                o.optJSONObject("perChat")?.let { j ->
                    j.keys().forEach { k -> perChat[k] = j.optJSONArray(k).toLongList() }
                }
                recent = o.optJSONArray("recent").toLongList()
                o.optJSONObject("rotation")?.let { j ->
                    j.keys().forEach { k -> rotation[k] = j.optInt(k) }
                }
            }  // 状态损坏就从空开始，代价只是冷却计数清零
        }

        override fun lastReplyAt(identity: String) = last[identity]
        override fun setLastReplyAt(identity: String, at: Long) { last[identity] = at }
        override fun chatReplyTimes(identity: String) = perChat[identity] ?: emptyList()
        override fun setChatReplyTimes(identity: String, times: List<Long>) {
            perChat[identity] = times
        }
        override fun recentReplyTimes() = recent
        override fun setRecentReplyTimes(times: List<Long>) { recent = times }
        override fun rotationIndex(key: String) = rotation[key] ?: -1
        override fun setRotationIndex(key: String, index: Int) { rotation[key] = index }
        // 只影响未来几十秒的排队，不落盘：重启后最多让第一条早发一点
        override fun lastSendAt() = lastSend
        override fun setLastSendAt(at: Long) { lastSend = at }

        override fun flush() {
            val o = JSONObject().apply {
                put("last", JSONObject().apply { last.forEach { (k, v) -> put(k, v) } })
                put("perChat", JSONObject().apply {
                    perChat.forEach { (k, v) -> put(k, JSONArray().apply { v.forEach { put(it) } }) }
                })
                put("recent", JSONArray().apply { recent.forEach { put(it) } })
                put("rotation", JSONObject().apply { rotation.forEach { (k, v) -> put(k, v) } })
            }
            prefs.edit().putString(KEY_STATE, o.toString()).apply()
        }

        private fun JSONArray?.toLongList(): List<Long> {
            if (this == null) return emptyList()
            return (0 until length()).map { optLong(it) }
        }
    }
}
