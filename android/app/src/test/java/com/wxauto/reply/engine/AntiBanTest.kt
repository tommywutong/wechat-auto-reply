package com.wxauto.reply.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random

/**
 * 防风控相关行为的单测，对应 core/tests/test_antiban.py。
 *
 * 这些机制的共同点是：平时看不出效果，出事时才知道有没有。
 * 所以必须有测试钉住，否则以后随手改一行限流逻辑就悄悄没了。
 *
 * 这里测的不是「能不能回」，而是「回得像不像人」：
 * 间隔、节奏、内容重复度。
 */
class AntiBanTest {

    private class FakeClock(var now: Long = 1_700_000_000_000L) : () -> Long {
        override fun invoke(): Long = now
        fun advance(ms: Long) { now += ms }
    }

    private fun engine(clock: FakeClock = FakeClock()) =
        ReplyEngine(InMemoryStateStore(), clock, Random(42)) to clock

    private fun config(
        minDelaySeconds: Int = 0,
        maxDelaySeconds: Int = 0,
        typingMillisPerChar: Int = 0,
        minIntervalSeconds: Int = 45,
        cooldownSeconds: Int = 600,
        maxPerChatPerDay: Int = 100,
        maxPerHour: Int = 1000,
        maxPerDay: Int = 1000,
        rules: List<Rule> = listOf(
            Rule(name = "在吗", keywords = listOf("在吗"), replies = listOf("在的")),
        ),
    ) = EngineConfig(
        enabled = true,
        signature = "",
        cooldownSeconds = cooldownSeconds,
        maxPerChatPerDay = maxPerChatPerDay,
        maxPerHour = maxPerHour,
        maxPerDay = maxPerDay,
        minDelaySeconds = minDelaySeconds,
        maxDelaySeconds = maxDelaySeconds,
        minIntervalSeconds = minIntervalSeconds,
        typingMillisPerChar = typingMillisPerChar,
        rules = rules,
        fallbackText = "稍后回复",
    )

    private fun msg(text: String = "在吗", chat: String = "小王") =
        Message(chatId = chat, chatName = chat, text = text)

    // -------------------------------------------------- 跨会话最小间隔

    @Test
    fun repliesToDifferentPeopleAreSpacedOut() {
        // 三十个人同时发消息时，不能在几十秒内挨个回完。
        // 冷却是按会话算的，挡不住这种情况。
        val (e, _) = engine()
        val cfg = config()

        val first = e.decide(cfg, msg(chat = "甲"))
        val second = e.decide(cfg, msg(chat = "乙"))
        val third = e.decide(cfg, msg(chat = "丙"))

        assertTrue(first.shouldReply && second.shouldReply && third.shouldReply)
        assertEquals(0L, first.delayMillis)
        assertEquals(45_000L, second.delayMillis)
        assertEquals(90_000L, third.delayMillis)
    }

    @Test
    fun spacingShrinksAsRealTimePasses() {
        // 消息本来就是隔开来的，就不该额外等待
        val (e, clock) = engine()
        val cfg = config()

        e.decide(cfg, msg(chat = "甲"))
        clock.advance(100_000)
        assertEquals(0L, e.decide(cfg, msg(chat = "乙")).delayMillis)
    }

    @Test
    fun spacingDelaysButNeverDrops() {
        // 丢掉的话，群发场景下大部分人永远收不到回复，而用户毫不知情
        val (e, _) = engine()
        val cfg = config(minIntervalSeconds = 60)

        val delays = (0 until 5).map { i ->
            val d = e.decide(cfg, msg(chat = "联系人$i"))
            assertTrue(d.shouldReply)
            d.delayMillis
        }

        assertEquals(delays.sorted(), delays)
        assertTrue(delays.last() >= 4 * 60_000L)
    }

    @Test
    fun spacingCanBeTurnedOff() {
        val (e, _) = engine()
        val cfg = config(minIntervalSeconds = 0)
        assertEquals(0L, e.decide(cfg, msg(chat = "甲")).delayMillis)
        assertEquals(0L, e.decide(cfg, msg(chat = "乙")).delayMillis)
    }

    // -------------------------------------------------- 打字时间

    @Test
    fun longerRepliesTakeLongerToSend() {
        // 真人打一句 30 字的话比打「嗯」慢得多
        val (e, _) = engine()
        val cfg = config(
            typingMillisPerChar = 100,
            minIntervalSeconds = 0,
            rules = listOf(
                Rule(name = "短", keywords = listOf("短"), replies = listOf("嗯")),
                Rule(
                    name = "长",
                    keywords = listOf("长"),
                    replies = listOf("我这会儿手上有点事，等下忙完了详细跟你说"),
                ),
            ),
        )

        val short = e.decide(cfg, msg("短", chat = "甲"))
        val long = e.decide(cfg, msg("长", chat = "乙"))

        assertEquals(100L, short.delayMillis)
        assertTrue(long.delayMillis > short.delayMillis)
        assertEquals(20 * 100L, long.delayMillis)
    }

    @Test
    fun typingTimeStacksOnTopOfBaseDelay() {
        val (e, _) = engine()
        val cfg = config(
            minDelaySeconds = 3,
            maxDelaySeconds = 3,
            typingMillisPerChar = 100,
            minIntervalSeconds = 0,
        )
        // 「在的」两个字 → 3000 + 200
        assertEquals(3_200L, e.decide(cfg, msg()).delayMillis)
    }

    @Test
    fun signatureCountsTowardTypingTime() {
        // 签名也是要打出来的字，不算进去的话长度就对不上
        val (e, _) = engine()
        val cfg = config(typingMillisPerChar = 100, minIntervalSeconds = 0)
            .copy(signature = "（自动回复）")
        // 「在的」+「（自动回复）」= 2 + 6 = 8 个字
        assertEquals(800L, e.decide(cfg, msg()).delayMillis)
    }

    // -------------------------------------------------- 内容重复度

    @Test
    fun differentPeopleGetDifferentWording() {
        // 一百个人收到一模一样的一句话，是批量发送最明显的特征。
        // 轮换计数必须是全局的：按会话分开算的话，每个人拿到的都是第一句。
        val (e, _) = engine()
        val cfg = config(
            minIntervalSeconds = 0,
            rules = listOf(
                Rule(
                    name = "在吗",
                    keywords = listOf("在吗"),
                    replies = listOf("在的", "在，怎么了", "在，稍等"),
                ),
            ),
        )

        val texts = (0 until 3).map { e.decide(cfg, msg(chat = "联系人$it")).text }
        assertEquals("三个人收到了重复内容：$texts", 3, texts.toSet().size)
    }

    @Test
    fun samePersonStillGetsVariationOverTime() {
        val (e, clock) = engine()
        val cfg = config(
            cooldownSeconds = 0,
            minIntervalSeconds = 0,
            rules = listOf(
                Rule(name = "在吗", keywords = listOf("在吗"), replies = listOf("A", "B")),
            ),
        )
        val seen = (0 until 4).map {
            val t = e.decide(cfg, msg()).text
            clock.advance(1000)
            t
        }
        assertEquals(listOf("A", "B", "A", "B"), seen)
    }

    // -------------------------------------------------- 总量

    @Test
    fun dailyGlobalCap() {
        // 只有每小时上限的话，跑满一天是 720 条
        val (e, clock) = engine()
        val cfg = config(cooldownSeconds = 0, maxPerDay = 5, minIntervalSeconds = 0)

        repeat(5) { i ->
            assertTrue(e.decide(cfg, msg(chat = "人$i")).shouldReply)
            clock.advance(10_000)
        }

        val blocked = e.decide(cfg, msg(chat = "第六个人"))
        assertFalse(blocked.shouldReply)
        assertTrue(blocked.reason, blocked.reason.contains("今天回复总数"))
    }

    @Test
    fun dailyCapResetsAfterADay() {
        val (e, clock) = engine()
        val cfg = config(cooldownSeconds = 0, maxPerDay = 2, minIntervalSeconds = 0)

        e.decide(cfg, msg(chat = "甲"))
        e.decide(cfg, msg(chat = "乙"))
        assertFalse(e.decide(cfg, msg(chat = "丙")).shouldReply)

        clock.advance(24 * 60 * 60 * 1000L + 1)
        assertTrue(e.decide(cfg, msg(chat = "丁")).shouldReply)
    }

    @Test
    fun hourlyCapStillAppliesWithinTheDailyBudget() {
        val (e, _) = engine()
        val cfg = config(
            cooldownSeconds = 0,
            maxPerHour = 2,
            maxPerDay = 100,
            minIntervalSeconds = 0,
        )
        e.decide(cfg, msg(chat = "甲"))
        e.decide(cfg, msg(chat = "乙"))
        val blocked = e.decide(cfg, msg(chat = "丙"))
        assertFalse(blocked.shouldReply)
        assertTrue(blocked.reason, blocked.reason.contains("一小时"))
    }

    // -------------------------------------------------- 顺序不能乱

    @Test
    fun sensitiveWordsStillWinOverEverything() {
        // 限流改动不能把安全判断挤到后面去
        val (e, _) = engine()
        val cfg = config()
        e.decide(cfg, msg(chat = "甲"))
        val d = e.decide(cfg, msg("帮我转账500", chat = "甲"))
        assertFalse(d.shouldReply)
        assertTrue(d.reason, d.reason.contains("敏感词"))
    }
}
