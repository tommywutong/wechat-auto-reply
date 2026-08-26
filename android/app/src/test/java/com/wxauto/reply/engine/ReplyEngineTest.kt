package com.wxauto.reply.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random

/**
 * 内嵌引擎的单测，对应 core/tests/test_engine.py。
 * 两份实现的行为必须一致，尤其是判断顺序。
 */
class ReplyEngineTest {

    private class FakeClock(var now: Long = 1_700_000_000_000L) : () -> Long {
        override fun invoke(): Long = now
        fun advance(ms: Long) { now += ms }
    }

    private fun engineWith(clock: FakeClock = FakeClock()) =
        ReplyEngine(InMemoryStateStore(), clock, Random(42)) to clock

    private fun config(
        enabled: Boolean = true,
        groupPolicy: GroupPolicy = GroupPolicy.ONLY_AT_ME,
        cooldownSeconds: Int = 600,
        maxPerChatPerDay: Int = 3,
        maxPerHour: Int = 10,
        rules: List<Rule> = listOf(
            Rule(name = "在吗", keywords = listOf("在吗"), replies = listOf("在的"))
        ),
        fallbackText: String = "稍后回复",
        signature: String = "",
        blockContacts: List<String> = emptyList(),
        allowContacts: List<String> = emptyList(),
    ) = EngineConfig(
        enabled = enabled,
        signature = signature,
        groupPolicy = groupPolicy,
        cooldownSeconds = cooldownSeconds,
        maxPerChatPerDay = maxPerChatPerDay,
        maxPerHour = maxPerHour,
        minDelaySeconds = 1,
        maxDelaySeconds = 2,
        rules = rules,
        fallbackText = fallbackText,
        blockContacts = blockContacts,
        allowContacts = allowContacts,
    )

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

    // ------------------------------------------------------------- 基本匹配

    @Test
    fun keywordRuleHits() {
        val (engine, _) = engineWith()
        val d = engine.decide(config(), msg("在吗？"))
        assertTrue(d.shouldReply)
        assertEquals("在的", d.text)
    }

    @Test
    fun fallbackUsedWhenNoRuleMatches() {
        val (engine, _) = engineWith()
        assertEquals("稍后回复", engine.decide(config(), msg("今天天气不错")).text)
    }

    @Test
    fun emptyFallbackSkips() {
        val (engine, _) = engineWith()
        assertFalse(engine.decide(config(fallbackText = ""), msg("随便")).shouldReply)
    }

    @Test
    fun signatureAppended() {
        val (engine, _) = engineWith()
        assertEquals("在的（自动回复）", engine.decide(config(signature = "（自动回复）"), msg("在吗")).text)
    }

    @Test
    fun masterSwitchOffBlocksEverything() {
        val (engine, _) = engineWith()
        assertFalse(engine.decide(config(enabled = false), msg("在吗")).shouldReply)
    }

    @Test
    fun regexRuleMatches() {
        val (engine, _) = engineWith()
        val cfg = config(rules = listOf(
            Rule(name = "价格", pattern = "多少钱|报价", replies = listOf("私聊报价"))
        ))
        assertEquals("私聊报价", engine.decide(cfg, msg("这个多少钱")).text)
    }

    @Test
    fun brokenRegexDoesNotCrash() {
        val (engine, _) = engineWith()
        val cfg = config(rules = listOf(
            Rule(name = "坏正则", pattern = "[", replies = listOf("不该命中"))
        ))
        // 正则编译失败时该规则永不命中，走兜底而不是抛异常
        assertEquals("稍后回复", engine.decide(cfg, msg("随便")).text)
    }

    // ------------------------------------------------------------- 安全优先

    @Test
    fun hardBlockKeywordsNeverReplied() {
        val (engine, _) = engineWith()
        // 即使配成全匹配、冷却为 0，敏感词也必须拦住
        val cfg = config(
            cooldownSeconds = 0,
            rules = listOf(Rule(name = "全匹配", replies = listOf("好的"))),
        )
        for (text in listOf("帮我转账500", "发个红包", "验证码是多少", "借钱应急")) {
            val d = engine.decide(cfg, msg(text))
            assertFalse("「$text」不该被自动回复", d.shouldReply)
            assertTrue(d.reason.contains("敏感词"))
        }
    }

    @Test
    fun hardBlockBeatsRateLimitOrdering() {
        val (engine, _) = engineWith()
        val cfg = config()
        engine.decide(cfg, msg("在吗"))          // 先占用冷却
        val d = engine.decide(cfg, msg("帮我转账"))
        // 应该报敏感词而不是「刚回过」，否则排查时会被误导
        assertTrue(d.reason.contains("敏感词"))
    }

    @Test
    fun blockedContactSkipped() {
        val (engine, _) = engineWith()
        val cfg = config(blockContacts = listOf("老板"))
        assertFalse(engine.decide(cfg, msg("在吗", chatName = "老板")).shouldReply)
    }

    @Test
    fun allowListExcludesOthers() {
        val (engine, _) = engineWith()
        val cfg = config(allowContacts = listOf("小王"))
        assertTrue(engine.decide(cfg, msg("在吗", chatName = "小王")).shouldReply)
        assertFalse(engine.decide(cfg, msg("在吗", chatName = "小李")).shouldReply)
    }

    // ------------------------------------------------------------- 群聊策略

    @Test
    fun groupPolicyNever() {
        val (engine, _) = engineWith()
        val cfg = config(groupPolicy = GroupPolicy.NEVER)
        assertFalse(engine.decide(cfg, msg("在吗", isGroup = true, mentionedMe = true)).shouldReply)
    }

    @Test
    fun groupPolicyOnlyAtMe() {
        val (engine, _) = engineWith()
        val cfg = config(groupPolicy = GroupPolicy.ONLY_AT_ME)
        assertFalse(engine.decide(cfg, msg("在吗", chatName = "群A", isGroup = true)).shouldReply)
        assertTrue(
            engine.decide(cfg, msg("在吗", chatName = "群B", isGroup = true, mentionedMe = true)).shouldReply
        )
    }

    // ------------------------------------------------------------- 频率限制

    @Test
    fun cooldownBlocksSecondReply() {
        val (engine, clock) = engineWith()
        val cfg = config()
        assertTrue(engine.decide(cfg, msg("在吗")).shouldReply)
        assertFalse(engine.decide(cfg, msg("在吗")).shouldReply)
        clock.advance(601_000)
        assertTrue(engine.decide(cfg, msg("在吗")).shouldReply)
    }

    @Test
    fun dailyCapPerChat() {
        val (engine, clock) = engineWith()
        val cfg = config()
        repeat(3) {
            assertTrue(engine.decide(cfg, msg("在吗")).shouldReply)
            clock.advance(601_000)
        }
        val d = engine.decide(cfg, msg("在吗"))
        assertFalse(d.shouldReply)
        assertTrue(d.reason.contains("今天"))
    }

    @Test
    fun hourlyFuse() {
        val (engine, clock) = engineWith()
        val cfg = config(cooldownSeconds = 0, maxPerChatPerDay = 100, maxPerHour = 2)
        assertTrue(engine.decide(cfg, msg("在吗", chatName = "甲")).shouldReply)
        clock.advance(1000)
        assertTrue(engine.decide(cfg, msg("在吗", chatName = "乙")).shouldReply)
        clock.advance(1000)
        assertFalse(engine.decide(cfg, msg("在吗", chatName = "丙")).shouldReply)
    }

    @Test
    fun cooldownIsPerChat() {
        val (engine, _) = engineWith()
        val cfg = config()
        assertTrue(engine.decide(cfg, msg("在吗", chatName = "甲")).shouldReply)
        assertTrue(engine.decide(cfg, msg("在吗", chatName = "乙")).shouldReply)
    }

    @Test
    fun groupMemberCountNotPartOfIdentity() {
        val (engine, _) = engineWith()
        val cfg = config(groupPolicy = GroupPolicy.ALWAYS)
        assertTrue(engine.decide(cfg, msg("在吗", chatName = "项目组(8)", isGroup = true)).shouldReply)
        // 人数变了不该被当成新会话
        assertFalse(engine.decide(cfg, msg("在吗", chatName = "项目组(9)", isGroup = true)).shouldReply)
    }

    @Test
    fun groupAndPrivateSameNameAreSeparate() {
        val (engine, _) = engineWith()
        val cfg = config(groupPolicy = GroupPolicy.ALWAYS)
        assertTrue(engine.decide(cfg, msg("在吗", chatName = "小王")).shouldReply)
        assertTrue(engine.decide(cfg, msg("在吗", chatName = "小王", isGroup = true)).shouldReply)
    }

    // ------------------------------------------------------------- 文案轮换

    @Test
    fun repliesRotate() {
        val (engine, clock) = engineWith()
        val cfg = config(
            cooldownSeconds = 0,
            maxPerChatPerDay = 100,
            maxPerHour = 100,
            rules = listOf(Rule(name = "多文案", keywords = listOf("在吗"), replies = listOf("A", "B"))),
        )
        val got = (1..4).map {
            val t = engine.decide(cfg, msg("在吗")).text
            clock.advance(1000)
            t
        }
        assertEquals(listOf("A", "B", "A", "B"), got)
    }

    // ------------------------------------------------------------- 延迟

    @Test
    fun replyIsDelayed() {
        val (engine, _) = engineWith()
        val d = engine.decide(config(), msg("在吗"))
        // 秒回是最明显的机器特征，必须有延迟
        assertTrue("延迟应在 1-2 秒之间，实际 ${d.delayMillis}ms", d.delayMillis >= 1000)
    }

    // ------------------------------------------------------------- 时段

    private fun millisAtLocal(hour: Int, minute: Int = 0): Long =
        java.time.LocalDate.of(2026, 1, 15).atTime(hour, minute)
            .atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli()

    @Test
    fun activeHoursUseTheInjectedClock() {
        // 这里原来用的是 LocalTime.now()，于是「在不在时段内」取决于
        // 机器当时几点——测不了，CI 换个时间跑就挂，而且和 Python 版
        // （一直用注入时钟）行为不一致。
        val cfg = config().copy(activeFromMinute = 9 * 60, activeToMinute = 23 * 60)

        val clock = FakeClock(millisAtLocal(10))
        assertTrue(ReplyEngine(InMemoryStateStore(), clock, Random(42))
            .decide(cfg, msg("在吗")).shouldReply)

        val night = FakeClock(millisAtLocal(3))
        val d = ReplyEngine(InMemoryStateStore(), night, Random(42)).decide(cfg, msg("在吗"))
        assertFalse(d.shouldReply)
        assertTrue(d.reason, d.reason.contains("时段"))
    }

    @Test
    fun activeHoursCanCrossMidnight() {
        // 22:00-02:00 这种跨零点的写法必须成立
        val cfg = config().copy(activeFromMinute = 22 * 60, activeToMinute = 2 * 60)
        for (hour in listOf(23, 1)) {
            assertTrue(
                "凌晨 $hour 点应该在 22:00-02:00 内",
                ReplyEngine(InMemoryStateStore(), FakeClock(millisAtLocal(hour)), Random(42))
                    .decide(cfg, msg("在吗")).shouldReply,
            )
        }
        assertFalse(
            ReplyEngine(InMemoryStateStore(), FakeClock(millisAtLocal(12)), Random(42))
                .decide(cfg, msg("在吗")).shouldReply,
        )
    }

    @Test
    fun noActiveHoursMeansAllDay() {
        val cfg = config()   // 默认 -1/-1
        for (hour in listOf(3, 12, 23)) {
            assertTrue(
                ReplyEngine(InMemoryStateStore(), FakeClock(millisAtLocal(hour)), Random(42))
                    .decide(cfg, msg("在吗")).shouldReply,
            )
        }
    }
}
