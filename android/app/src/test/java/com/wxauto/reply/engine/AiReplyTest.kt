package com.wxauto.reply.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random

/**
 * AI 模式的单测。
 *
 * 这里最要紧的一类断言不是「回得像不像人」——那测不了——
 * 而是「哪些消息**根本不该走到模型面前**」。
 * 安全判断必须在引擎里做完，不能指望提示词里写一句「不要答应转账」
 * 就万事大吉：那是个概率性的东西，而转账消息回错一次的代价太高。
 */
class AiReplyTest {

    private class FakeClock(var now: Long = 1_700_000_000_000L) : () -> Long {
        override fun invoke(): Long = now
        fun advance(ms: Long) { now += ms }
    }

    /** 记录都被喂了什么，用来断言「没被喂过」。 */
    private class RecordingWriter(
        private val reply: String? = "在，怎么了",
        private val boom: Boolean = false,
    ) : AiWriter {
        val seen = mutableListOf<String>()

        override fun write(message: Message, config: EngineConfig): String? {
            seen += message.text
            if (boom) throw IllegalStateException("接口炸了")
            return reply
        }
    }

    private val persona = PersonaConfig(
        identity = "我是做独立开发的，白天基本在写代码",
        tone = "句子短，口语，不用敬语",
        playbook = "有人约时间就说要确认日程",
        boundaries = listOf("不谈具体报价"),
        maxChars = 30,
        examples = listOf(AiExample("在吗", "在，怎么了")),
    )

    private fun config(
        enabled: Boolean = true,
        groupPolicy: GroupPolicy = GroupPolicy.ONLY_AT_ME,
        cooldownSeconds: Int = 600,
        signature: String = "",
        blockContacts: List<String> = emptyList(),
    ) = EngineConfig(
        enabled = enabled,
        signature = signature,
        groupPolicy = groupPolicy,
        cooldownSeconds = cooldownSeconds,
        maxPerChatPerDay = 10,
        maxPerHour = 20,
        minDelaySeconds = 1,
        maxDelaySeconds = 2,
        replyMode = ReplyMode.AI,
        persona = persona,
        blockContacts = blockContacts,
        // 规则和兜底都填上：AI 模式下它们必须完全不生效
        rules = listOf(Rule(name = "在吗", keywords = listOf("在吗"), replies = listOf("规则回的"))),
        fallbackText = "兜底回的",
    )

    private fun engineWith(writer: AiWriter?, clock: FakeClock = FakeClock()) =
        ReplyEngine(InMemoryStateStore(), clock, Random(42), writer)

    private fun msg(
        text: String,
        chatName: String = "小王",
        isGroup: Boolean = false,
        mentionedMe: Boolean = false,
    ) = Message(
        chatId = chatName,
        chatName = chatName,
        text = text,
        isGroup = isGroup,
        mentionedMe = mentionedMe,
    )

    // ------------------------------------------------ 哪些消息不该走到模型面前

    @Test
    fun sensitiveMessageNeverReachesModel() {
        val writer = RecordingWriter()
        val engine = engineWith(writer)
        for (text in listOf("帮我转账500", "验证码发我一下", "借钱应急", "把银行卡号给我")) {
            val d = engine.decide(config(), msg(text))
            assertFalse("「$text」不该被自动回复", d.shouldReply)
        }
        assertTrue("敏感消息一个字都不该发给模型，实际发了 ${writer.seen}", writer.seen.isEmpty())
    }

    @Test
    fun blockedContactNeverReachesModel() {
        val writer = RecordingWriter()
        val d = engineWith(writer).decide(
            config(blockContacts = listOf("老板")),
            msg("在吗", chatName = "老板"),
        )
        assertFalse(d.shouldReply)
        assertTrue(writer.seen.isEmpty())
    }

    @Test
    fun groupMessageBlockedByPolicyNeverReachesModel() {
        val writer = RecordingWriter()
        val d = engineWith(writer).decide(
            config(groupPolicy = GroupPolicy.NEVER),
            msg("在吗", chatName = "项目组", isGroup = true, mentionedMe = true),
        )
        assertFalse(d.shouldReply)
        assertTrue(writer.seen.isEmpty())
    }

    @Test
    fun rateLimitedMessageNeverReachesModel() {
        val writer = RecordingWriter()
        val engine = engineWith(writer)
        assertTrue(engine.decide(config(), msg("在吗")).shouldReply)
        // 冷却期内的第二条不该再调接口——每次调用都是钱
        assertFalse(engine.decide(config(), msg("那明天呢")).shouldReply)
        assertEquals(listOf("在吗"), writer.seen)
    }

    @Test
    fun switchOffNeverReachesModel() {
        val writer = RecordingWriter()
        assertFalse(engineWith(writer).decide(config(enabled = false), msg("在吗")).shouldReply)
        assertTrue(writer.seen.isEmpty())
    }

    // ------------------------------------------------------------ 正常路径

    @Test
    fun aiReplyBypassesRulesAndFallback() {
        val d = engineWith(RecordingWriter("在，怎么了")).decide(config(), msg("在吗"))
        assertTrue(d.shouldReply)
        // 规则里明明有「在吗」，但 AI 模式下规则不参与
        assertEquals("在，怎么了", d.text)
        assertEquals("AI 生成", d.reason)
    }

    @Test
    fun aiReplyStillGetsSignature() {
        val d = engineWith(RecordingWriter("在，怎么了"))
            .decide(config(signature = "（自动回复）"), msg("在吗"))
        assertEquals("在，怎么了（自动回复）", d.text)
    }

    @Test
    fun aiReplyIsDelayed() {
        val d = engineWith(RecordingWriter()).decide(config(), msg("在吗"))
        assertTrue("秒回是最明显的机器特征", d.delayMillis >= 1000)
    }

    // ------------------------------------------------------------ 失败退化

    @Test
    fun modelFailureSkipsInsteadOfFallingBackToRules() {
        val d = engineWith(RecordingWriter(boom = true)).decide(config(), msg("在吗"))
        // 关键：不能悄悄退回规则文案。用户选了 AI 就说明他不想发罐头话，
        // 宁可这条不回，也不要冒出一句风格完全不同的句子。
        assertFalse(d.shouldReply)
        assertTrue(d.reason.contains("AI 生成失败"))
    }

    @Test
    fun modelReturningNothingSkips() {
        val d = engineWith(RecordingWriter(reply = null)).decide(config(), msg("在吗"))
        assertFalse(d.shouldReply)
    }

    @Test
    fun aiModeWithoutWriterSkips() {
        val d = engineWith(null).decide(config(), msg("在吗"))
        assertFalse(d.shouldReply)
        assertTrue(d.reason.contains("没有配置 AI 接口"))
    }

    @Test
    fun failureDoesNotBurnTheDailyQuota() {
        // 接口挂了一阵子又恢复，是很常见的情况。
        // 如果失败也被记进「今天已经回过 N 条」，恢复之后就白白哑掉了。
        val writer = object : AiWriter {
            var broken = true
            override fun write(message: Message, config: EngineConfig): String? {
                if (broken) throw IllegalStateException("接口炸了")
                return "在，怎么了"
            }
        }
        val clock = FakeClock()
        val engine = ReplyEngine(InMemoryStateStore(), clock, Random(42), writer)
        val cfg = config(cooldownSeconds = 0).copy(maxPerChatPerDay = 2)

        repeat(3) {
            assertFalse(engine.decide(cfg, msg("在吗")).shouldReply)
            clock.advance(1000)
        }

        writer.broken = false
        assertTrue("失败不该被记进每日配额", engine.decide(cfg, msg("在吗")).shouldReply)
    }

    // ------------------------------------------------------------ 提示词

    @Test
    fun promptCarriesPersonaAndHardRules() {
        val prompt = buildSystemPrompt(persona)
        assertTrue(prompt.contains("我是做独立开发的"))
        assertTrue(prompt.contains("句子短，口语，不用敬语"))
        assertTrue(prompt.contains("有人约时间就说要确认日程"))
        assertTrue(prompt.contains("不谈具体报价"))
        assertTrue(prompt.contains("30 个字以内"))
        // 内置边界必须始终在，不受用户配置影响
        assertTrue(prompt.contains("不答应任何转账"))
        assertTrue(prompt.contains("不要自称 AI"))
        // 示范放最后，模型对靠近末尾的内容模仿得更紧
        assertTrue(prompt.indexOf("在，怎么了") > prompt.indexOf("硬性要求"))
    }

    @Test
    fun promptWithoutExamplesStillHasRules() {
        val prompt = buildSystemPrompt(PersonaConfig(identity = "我很忙"))
        assertTrue(prompt.contains("我很忙"))
        assertTrue(prompt.contains("不答应任何转账"))
        assertFalse(prompt.contains("照着这个语气"))
    }

    @Test
    fun emptyPersonaIsNotConsideredConfigured() {
        assertFalse(PersonaConfig().isConfigured())
        assertFalse(PersonaConfig(tone = "只写了语气").isConfigured())
        assertTrue(PersonaConfig(identity = "我是谁").isConfigured())
        assertTrue(PersonaConfig(playbook = "怎么应对").isConfigured())
    }

    // ------------------------------------------------------------ 输出清洗

    @Test
    fun sanitizeStripsWrappingQuotes() {
        assertEquals("在，怎么了", sanitize("「在，怎么了」", 30))
        assertEquals("在，怎么了", sanitize("\"在，怎么了\"", 30))
        assertEquals("在，怎么了", sanitize("  在，怎么了\n", 30))
    }

    @Test
    fun sanitizeDropsEmptyOutput() {
        assertNull(sanitize("   ", 30))
        assertNull(sanitize("「」", 30))
    }

    @Test
    fun sanitizeTruncatesRunawayOutput() {
        // 模型偶尔不听话写一大段。发出去一眼假，截断比原样发好。
        val long = "啊".repeat(200)
        val out = sanitize(long, 30)!!
        assertTrue("实际长度 ${out.length}", out.length <= 61)
        assertTrue(out.endsWith("…"))
    }

    @Test
    fun sanitizeKeepsNormalLengthIntact() {
        val text = "我看下日程，晚点回你"
        assertEquals(text, sanitize(text, 30))
    }

    // ------------------------------------------------------------ 对话记忆

    @Test
    fun memoryKeepsOnlyRecentTurns() {
        val memory = ConversationMemory(maxTurns = 4)
        repeat(10) { memory.remember("小王", Speaker.THEM, "第 $it 条") }
        val turns = memory.recent("小王")
        assertEquals(4, turns.size)
        assertEquals("第 9 条", turns.last().text)
    }

    @Test
    fun memoryExpiresOldTurns() {
        val clock = FakeClock()
        val memory = ConversationMemory(ttlMillis = 60_000, clock = clock)
        memory.remember("小王", Speaker.THEM, "昨天那事")
        clock.advance(61_000)
        memory.remember("小王", Speaker.THEM, "在吗")
        // 太老的上下文反而误导：三天前那事早翻篇了
        assertEquals(listOf("在吗"), memory.recent("小王").map { it.text })
    }

    @Test
    fun memoryIsPerChat() {
        val memory = ConversationMemory()
        memory.remember("小王", Speaker.THEM, "给小王的")
        memory.remember("小李", Speaker.THEM, "给小李的")
        assertEquals(listOf("给小王的"), memory.recent("小王").map { it.text })
        assertEquals(listOf("给小李的"), memory.recent("小李").map { it.text })
    }

    // ------------------------------------------------------------ 报错要能照着做

    @Test
    fun httpErrorsTellTheUserWhatToFix() {
        // 用户不会看 logcat。这些话会经由引擎的 reason 显示在「试一试」里，
        // 所以每一条都得能直接照着做，不能只说「请求失败」。
        assertTrue(explainHttp(401, "").contains("API Key"))
        assertTrue(explainHttp(403, "").contains("API Key"))
        assertTrue(explainHttp(404, "").contains("模型名"))
        assertTrue(explainHttp(402, "").contains("余额"))
        assertTrue(explainHttp(429, "").contains("额度"))
        assertTrue(explainHttp(503, "").contains("服务器"))
    }

    @Test
    fun unknownStatusStillCarriesTheServerMessage() {
        val explained = explainHttp(418, "teapot detail here")
        assertTrue(explained.contains("418"))
        assertTrue(explained.contains("teapot"))
    }

    @Test
    fun writerFailureSurfacesAsAReadableReason() {
        // AiWriterException 的话要一路传到用户眼前，不能被吞成
        // 「AI 没返回可用内容」——那句话没法照着修
        val writer = object : AiWriter {
            override fun write(message: Message, config: EngineConfig): String? =
                throw AiWriterException(explainHttp(404, ""))
        }
        val decision = engineWith(writer).decide(config(), msg("在吗"))
        assertFalse(decision.shouldReply)
        assertTrue(decision.reason, decision.reason.contains("模型名"))
    }

    // ------------------------------------------------------------ 厂商预设

    @Test
    fun doubaoIsOfferedFirst() {
        // 这套东西要的是「聊天像真人」，豆包的中文口语最自然，
        // 而设置页上第一个按钮就是多数人会点的那个
        assertEquals("豆包", OpenAiCompatibleWriter.PRESETS.first().name)
    }

    @Test
    fun everyPresetIsUsableAsIs() {
        OpenAiCompatibleWriter.PRESETS.forEach { preset ->
            assertTrue(preset.name, preset.baseUrl.startsWith("https://"))
            assertTrue(preset.name, preset.model.isNotBlank())
            // 地址不该自带 /chat/completions，那段是调用时拼的
            assertFalse(preset.name, preset.baseUrl.trimEnd('/').endsWith("chat/completions"))
        }
    }

    @Test
    fun doubaoWarnsAboutItsModelIdQuirk() {
        // 火山方舟的 model 既可能是模型 ID 也可能是 ep- 接入点，
        // 而且带日期后缀会变——不说清楚，用户只会看到「不回复」
        val doubao = OpenAiCompatibleWriter.PRESETS.first { it.name == "豆包" }
        assertTrue(doubao.note.contains("模型 ID") || doubao.note.contains("ep-"))
    }

    @Test
    fun presetsHaveDistinctEndpoints() {
        val urls = OpenAiCompatibleWriter.PRESETS.map { it.baseUrl }
        assertEquals(urls.size, urls.toSet().size)
    }

    // ------------------------------------------------------------ 生成器选择

    @Test
    fun writerKeyChangesWhenSettingsChange() {
        val base = config().copy(ai = AiConfig(baseUrl = "https://a", apiKey = "k1", model = "m"))
        val other = base.copy(ai = base.ai.copy(apiKey = "k2"))
        assertNotEquals(Storage.aiWriterKey(base), Storage.aiWriterKey(other))
        assertEquals(Storage.aiWriterKey(base), Storage.aiWriterKey(base.copy()))
    }

    @Test
    fun writerKeyDoesNotLeakCredentials() {
        val cfg = config().copy(
            ai = AiConfig(baseUrl = "https://a", apiKey = "sk-secret", relayToken = "口令")
        )
        val key = Storage.aiWriterKey(cfg)
        assertFalse(key.contains("sk-secret"))
        assertFalse(key.contains("口令"))
    }

    @Test
    fun keywordModeNeverBuildsAWriter() {
        val cfg = config().copy(
            replyMode = ReplyMode.KEYWORD,
            ai = AiConfig(baseUrl = "https://a", apiKey = "k", model = "m"),
        )
        assertNull(Storage.aiWriter(cfg))
    }

    @Test
    fun incompleteAiSettingsBuildNoWriter() {
        // 填一半就该退化成不回复，而不是拿着空 key 去打接口
        assertNull(Storage.aiWriter(config().copy(ai = AiConfig(baseUrl = "https://a"))))
        assertNull(Storage.aiWriter(config().copy(ai = AiConfig(apiKey = "k"))))
        assertNull(
            Storage.aiWriter(config().copy(ai = AiConfig(source = AiSource.RELAY, relayUrl = "")))
        )
    }
}
