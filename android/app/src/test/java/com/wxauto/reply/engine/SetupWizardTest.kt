package com.wxauto.reply.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 开场问答的单测，对应 core/tests/test_wizard.py。
 *
 * 重点不是「生成的话好不好听」——那没法测——而是：
 *   1. 不管用户怎么答（包括根本没答），生成的东西都能直接喂给引擎
 *   2. 有几条底线不受回答影响，永远在
 *   3. 答案确实影响输出，而不是摆设
 */
class SetupWizardTest {

    private fun answers(vararg overrides: Pair<String, List<String>>): Map<String, List<String>> {
        val base = mutableMapOf(
            "who" to listOf("work", "friend"),
            "busy" to listOf("hands"),
            "style" to listOf("casual"),
            "emoji" to listOf("none"),
            "appointment" to listOf("hold"),
            "progress" to listOf("rough"),
            "stranger" to listOf("polite"),
            "greeting" to listOf(""),
            "never" to emptyList(),
        )
        overrides.forEach { (k, v) -> base[k] = v }
        return base
    }

    private val styles = listOf("casual", "polite", "warm", "brief")

    // ------------------------------------------------------------ 问题本身

    @Test
    fun questionIdsAreUnique() {
        val ids = SetupWizard.QUESTIONS.map { it.id }
        assertEquals(ids.size, ids.toSet().size)
    }

    @Test
    fun optionIdsAreUniqueWithinEachQuestion() {
        SetupWizard.QUESTIONS.forEach { q ->
            assertEquals(q.id, q.options.size, q.options.map { it.id }.toSet().size)
        }
    }

    @Test
    fun choiceQuestionsHaveOptionsAndTextQuestionsDoNot() {
        SetupWizard.QUESTIONS.forEach { q ->
            if (q.kind == QuestionKind.TEXT) {
                assertTrue(q.id, q.options.isEmpty())
                // 强制一个不懂技术的人写自由文本，是最容易让他卡住的一步
                assertTrue(q.id, q.optional)
            } else {
                assertTrue(q.id, q.options.size >= 2)
            }
        }
    }

    @Test
    fun bothImplementationsAskTheSameQuestions() {
        // Python 版（core/wizard.py）必须问一模一样的题，否则两边生成的
        // 人设会不一样，同一个人在电脑和手机上的语气就对不上了
        assertEquals(
            listOf(
                "who", "busy", "style", "greeting",
                "appointment", "progress", "stranger", "emoji",
                "night", "never", "only_for",
            ),
            SetupWizard.QUESTIONS.map { it.id },
        )
    }

    // ------------------------------------------------------------ 底线

    @Test
    fun playbookAlwaysKeepsTheEscapeHatch() {
        // 「看不懂就交给本人」是最重要的一条，任何回答组合下都必须在
        for (style in styles) {
            for (appointment in listOf("hold", "refuse", "ask")) {
                for (stranger in listOf("polite", "blunt", "later")) {
                    val result = SetupWizard.build(
                        answers(
                            "style" to listOf(style),
                            "appointment" to listOf(appointment),
                            "stranger" to listOf(stranger),
                        )
                    )
                    assertTrue(result.persona.playbook.contains("等我本人回你"))
                }
            }
        }
    }

    @Test
    fun generatedPersonaIsAlwaysConsideredConfigured() {
        // 没配人设时引擎会拒绝走 AI，问答生成的必须过得去
        assertTrue(SetupWizard.build(emptyMap()).persona.isConfigured())
        assertTrue(SetupWizard.build(answers()).persona.isConfigured())
    }

    @Test
    fun everyGeneratedRuleIsUsable() {
        for (style in styles) {
            val result = SetupWizard.build(answers("style" to listOf(style)))
            result.rules.forEach { rule ->
                // 空回复会被引擎跳过，等于这条规则白写
                assertTrue(rule.name, rule.replies.isNotEmpty())
                assertTrue(rule.name, rule.replies.all { it.isNotBlank() })
                assertTrue(rule.name, rule.keywords.isNotEmpty())
            }
        }
    }

    @Test
    fun unknownAnswersFallBackInsteadOfCrashing() {
        // 旧版本存下来的答案、或者被改坏的数据，不该让 App 崩在启动页上
        val result = SetupWizard.build(
            answers(
                "style" to listOf("不存在"),
                "appointment" to listOf("乱写"),
                "busy" to listOf("???"),
            )
        )
        assertTrue(result.persona.tone.isNotBlank())
        assertTrue(result.persona.playbook.isNotBlank())
        assertTrue(result.persona.maxChars > 0)
        assertTrue(result.fallbackText.isNotBlank())
    }

    @Test
    fun emptyAnswersStillProduceAWorkingSet() {
        val result = SetupWizard.build(emptyMap())
        assertTrue(result.persona.identity.isNotBlank())
        assertTrue(result.persona.tone.isNotBlank())
        assertEquals(4, result.persona.examples.size)
        assertEquals(4, result.rules.size)
        assertTrue(result.fallbackText.isNotBlank())
    }

    // ------------------------------------------------------------ 答案有效

    @Test
    fun styleChangesTheVoice() {
        val voices = styles.map {
            SetupWizard.build(answers("style" to listOf(it))).persona.examples[0].me
        }
        assertEquals(voices.size, voices.toSet().size)
        assertTrue(voices[1].contains("您"))
        assertTrue(voices[3].length <= voices[0].length)
    }

    @Test
    fun noExclamationWhenUserSaidTheyDoNotUseThem() {
        // 热情风格自带感叹号，但用户说了不用——示范必须跟着改。
        // 示范和语气说明打架时，模型照着示范走。
        val result = SetupWizard.build(
            answers("style" to listOf("warm"), "emoji" to listOf("none"))
        )
        result.persona.examples.forEach { assertFalse(it.me, it.me.contains("！")) }
        assertTrue(result.persona.tone.contains("不用感叹号"))
    }

    @Test
    fun exclamationKeptWhenUserLikesThem() {
        val result = SetupWizard.build(
            answers("style" to listOf("warm"), "emoji" to listOf("both"))
        )
        assertTrue(result.persona.examples.any { it.me.contains("！") })
    }

    @Test
    fun replyLengthFollowsTheChosenVoice() {
        // 长度不再单独问一题——选了「在」的人不会突然写三句话。
        // 少一道题，而且推断出来的比用户自己估的准。
        assertEquals(20, SetupWizard.build(answers("style" to listOf("brief"))).persona.maxChars)
        assertEquals(30, SetupWizard.build(answers("style" to listOf("casual"))).persona.maxChars)
        assertEquals(45, SetupWizard.build(answers("style" to listOf("warm"))).persona.maxChars)
    }

    @Test
    fun ownWordsBeatTheTemplate() {
        // 用户自己写的那句是他真实的声音，比我们按风格挑的任何一句都准
        val result = SetupWizard.build(answers("greeting" to listOf("咋了老铁")))
        assertEquals("咋了老铁", result.persona.examples[0].me)
        // 关键词规则里也要用同一句，两种模式下表现才一致
        assertEquals(listOf("咋了老铁"), result.rules.first { it.name == "问在不在" }.replies)
    }

    @Test
    fun appointmentChoiceChangesBothPlaybookAndExamples() {
        val hold = SetupWizard.build(answers("appointment" to listOf("hold")))
        val refuse = SetupWizard.build(answers("appointment" to listOf("refuse")))
        assertNotEquals(hold.persona.playbook, refuse.persona.playbook)
        assertNotEquals(hold.persona.examples[1].me, refuse.persona.examples[1].me)
        assertTrue(hold.persona.examples[1].me.contains("日程"))
    }

    @Test
    fun boundariesComeFromCheckboxes() {
        // 原来这题是个空框，让人对着它想「有什么绝对不能答应」。
        // 那是最难答的一种题，多数人直接跳过，于是这一段永远是空的。
        val result = SetupWizard.build(answers("never" to listOf("money", "favor")))
        assertEquals(2, result.persona.boundaries.size)
        assertTrue(result.persona.boundaries.any { it.contains("价格") })
        assertTrue(result.persona.boundaries.any { it.contains("投票") })
    }

    @Test
    fun nightChoiceControlsActiveHours() {
        // 深夜自动回复本身就是可疑信号，所以这题得问，而且要好答
        assertEquals(9 * 60 to 23 * 60, SetupWizard.build(answers("night" to listOf("day"))).activeHours)
        assertEquals(9 * 60 to 18 * 60, SetupWizard.build(answers("night" to listOf("work"))).activeHours)
        assertEquals(-1 to -1, SetupWizard.build(answers("night" to listOf("always"))).activeHours)
    }

    @Test
    fun activeHoursReachTheConfig() {
        val config = SetupWizard.applyTo(
            EngineConfig(enabled = true),
            SetupWizard.build(answers("night" to listOf("work"))),
        )
        assertEquals(9 * 60, config.activeFromMinute)
        assertEquals(18 * 60, config.activeToMinute)
    }

    @Test
    fun clientMakesThePlaybookMoreCareful() {
        // 选了客户、甲方说明回错的代价高，这题就该真的改变行为
        val withClient = SetupWizard.build(answers("who" to listOf("client")))
        val without = SetupWizard.build(answers("who" to listOf("friend")))
        assertTrue(withClient.persona.playbook.contains("报价"))
        assertFalse(without.persona.playbook.contains("报价"))
    }

    @Test
    fun noBoundariesCheckedStaysEmpty() {
        assertTrue(SetupWizard.build(answers("never" to emptyList())).persona.boundaries.isEmpty())
    }

    @Test
    fun whoAppearsInIdentity() {
        assertTrue(
            SetupWizard.build(answers("who" to listOf("client"))).persona.identity.contains("客户")
        )
        // 一个都没选也得有句像样的自我介绍
        assertTrue(
            SetupWizard.build(answers("who" to emptyList())).persona.identity.isNotBlank()
        )
    }

    // ------------------------------------------------------------ 接进引擎

    @Test
    fun applyToKeepsEverythingElseUntouched() {
        // 重答一遍问答不该把用户的开关、限流、黑名单冲掉
        val existing = EngineConfig(
            enabled = true,
            cooldownSeconds = 999,
            blockContacts = listOf("老板"),
            groupPolicy = GroupPolicy.ALWAYS,
            replyMode = ReplyMode.AI,
            ai = AiConfig(baseUrl = "https://a", apiKey = "k", model = "m"),
        )
        val applied = SetupWizard.applyTo(existing, SetupWizard.build(answers()))

        assertTrue(applied.enabled)
        assertEquals(999, applied.cooldownSeconds)
        assertEquals(listOf("老板"), applied.blockContacts)
        assertEquals(GroupPolicy.ALWAYS, applied.groupPolicy)
        assertEquals(ReplyMode.AI, applied.replyMode)
        assertEquals("k", applied.ai.apiKey)
        // 该换的换掉了
        assertTrue(applied.persona.isConfigured())
        assertEquals(4, applied.rules.size)
    }

    @Test
    fun generatedRulesActuallyFireInTheEngine() {
        // 生成出来但引擎打不中，等于白干
        val config = SetupWizard.applyTo(
            EngineConfig(
                enabled = true,
                signature = "",
                cooldownSeconds = 0,
                maxPerChatPerDay = 50,
                maxPerHour = 50,
                minDelaySeconds = 0,
                maxDelaySeconds = 0,
            ),
            SetupWizard.build(answers()),
        ).copy(activeFromMinute = -1, activeToMinute = -1)   // 时段不是这条要测的
        val engine = ReplyEngine(InMemoryStateStore())

        for ((text, expectedRule) in listOf(
            "在吗" to "问在不在",
            "明天有空吗" to "约时间",
            "那个什么时候好" to "问进度",
            "了解一下我们的产品" to "推销拉群",
        )) {
            val decision = engine.decide(
                config,
                Message(chatId = text, chatName = text, text = text),
            )
            assertTrue("「$text」应该命中规则", decision.shouldReply)
            assertEquals(text, expectedRule, decision.ruleName)
        }
    }

    @Test
    fun generatedPromptCarriesTheAnswers() {
        val result = SetupWizard.build(
            answers(
                "style" to listOf("brief"),
                "appointment" to listOf("refuse"),
                "never" to listOf("money"),
            )
        )
        val prompt = buildSystemPrompt(result.persona)
        assertTrue(prompt.contains("能少说就少说"))
        assertTrue(prompt.contains("最近排不开"))
        assertTrue(prompt.contains("价格"))
        // 内置边界不受问答影响
        assertTrue(prompt.contains("不答应任何转账"))
    }

    @Test
    fun wizardOutputNeverDefeatsTheSafetyRules() {
        // 不管问答生成了什么，敏感词照样拦住
        val config = SetupWizard.applyTo(
            EngineConfig(enabled = true, cooldownSeconds = 0),
            SetupWizard.build(answers()),
        ).copy(activeFromMinute = -1, activeToMinute = -1)   // 时段不是这条要测的
        val decision = ReplyEngine(InMemoryStateStore()).decide(
            config,
            Message(chatId = "x", chatName = "小王", text = "帮我转账500"),
        )
        assertFalse(decision.shouldReply)
        assertTrue(decision.reason.contains("敏感词"))
    }

    // ------------------------------------------------------------ 白名单

    @Test
    fun onlyForBecomesAllowContacts() {
        // 「先只对哪几个人开」是最有效的防风控手段：真正会出事的路径是
        // 被举报，而熟人不会举报你。
        val result = SetupWizard.build(answers("only_for" to listOf("小王，李雷、张三")))
        assertEquals(listOf("小王", "李雷", "张三"), result.allowContacts)
    }

    @Test
    fun blankOnlyForMeansEveryone() {
        assertTrue(SetupWizard.build(answers("only_for" to listOf(""))).allowContacts.isEmpty())
    }

    @Test
    fun whitelistActuallyBlocksOutsiders() {
        // 生成出来但引擎不认，等于白填
        val config = SetupWizard.applyTo(
            EngineConfig(enabled = true, signature = "", minIntervalSeconds = 0),
            SetupWizard.build(answers("only_for" to listOf("小王"))),
        ).copy(activeFromMinute = -1, activeToMinute = -1)   // 时段不是这条要测的
        val engine = ReplyEngine(InMemoryStateStore())

        val inside = engine.decide(config, Message(chatId = "小王", chatName = "小王", text = "在吗"))
        val outside = engine.decide(
            config, Message(chatId = "陌生人", chatName = "陌生人", text = "在吗")
        )

        assertTrue(inside.shouldReply)
        assertFalse(outside.shouldReply)
        assertTrue(outside.reason, outside.reason.contains("名单"))
    }

    // ------------------------------------------------------------ 表情 ≠ 感叹号

    @Test
    fun emojiAndExclamationAreIndependent() {
        // 有人爱发表情但从不用感叹号。原来把两者混成一个「用不用」的
        // 程度问题，是设计错误：选「偶尔用」的人没法表达「只发表情」。
        val onlyEmoji = SetupWizard.build(
            answers("style" to listOf("warm"), "emoji" to listOf("emoji"))
        )
        val onlyMark = SetupWizard.build(
            answers("style" to listOf("warm"), "emoji" to listOf("mark"))
        )

        assertTrue(onlyEmoji.persona.examples.none { it.me.contains("！") })
        assertTrue(onlyEmoji.persona.examples.any { it.me.contains("😂") })

        assertTrue(onlyMark.persona.examples.any { it.me.contains("！") })
        assertTrue(onlyMark.persona.examples.none { it.me.contains("😂") })
    }

    @Test
    fun legacyEmojiAnswersStillWork() {
        // 旧版本存的答案不该让人设变样——重装一次语气就变了很怪
        assertEquals(
            SetupWizard.build(answers("emoji" to listOf("emoji"))).persona.tone,
            SetupWizard.build(answers("emoji" to listOf("some"))).persona.tone,
        )
        assertEquals(
            SetupWizard.build(answers("emoji" to listOf("both"))).persona.tone,
            SetupWizard.build(answers("emoji" to listOf("lots"))).persona.tone,
        )
    }

    // ------------------------------------------------------------ 没马上回的理由

    @Test
    fun busyAcceptsSeveralReasons() {
        // 「在上班」和「不知道怎么回」可以同时成立，原来只能选一个
        val result = SetupWizard.build(answers("busy" to listOf("work", "unsure")))
        assertTrue(result.persona.identity.contains("上班"))
        assertTrue(result.persona.identity.contains("想想怎么回"))
    }

    @Test
    fun unsureMakesThePlaybookMoreCareful() {
        // 用户自己说了「有些消息不知道怎么回」，模型就该跟着保守
        val careful = SetupWizard.build(answers("busy" to listOf("unsure")))
        val plain = SetupWizard.build(answers("busy" to listOf("work")))
        assertTrue(careful.persona.playbook.contains("绝对不要自己编一个答案"))
        assertFalse(plain.persona.playbook.contains("绝对不要自己编一个答案"))
    }

    @Test
    fun unknownBusyFallsBack() {
        val result = SetupWizard.build(answers("busy" to listOf("乱写")))
        assertTrue(result.persona.identity.isNotBlank())
        assertTrue(result.fallbackText.isNotBlank())
    }

    // ------------------------------------------------------------ 名单比对

    @Test
    fun whitelistToleratesSpacingAndCase() {
        // 用户手打名字常有多余空格。比对失败是静默的，最难查。
        val config = SetupWizard.applyTo(
            EngineConfig(enabled = true, signature = "", minIntervalSeconds = 0),
            SetupWizard.build(answers("only_for" to listOf("  小王 "))),
        ).copy(activeFromMinute = -1, activeToMinute = -1)   // 时段不是这条要测的
        val d = ReplyEngine(InMemoryStateStore())
            .decide(config, Message(chatId = "x", chatName = "小王", text = "在吗"))
        assertTrue(d.reason, d.shouldReply)
    }

    @Test
    fun whitelistDoesNotDoFuzzyMatching() {
        // 「小王他哥」不该被当成「小王」——那会让名单形同虚设
        val config = SetupWizard.applyTo(
            EngineConfig(enabled = true, signature = "", minIntervalSeconds = 0),
            SetupWizard.build(answers("only_for" to listOf("小王"))),
        ).copy(activeFromMinute = -1, activeToMinute = -1)   // 时段不是这条要测的
        val d = ReplyEngine(InMemoryStateStore())
            .decide(config, Message(chatId = "x", chatName = "小王他哥", text = "在吗"))
        assertFalse(d.shouldReply)
    }
}
