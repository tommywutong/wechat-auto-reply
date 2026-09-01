package com.wxauto.reply.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class StyleProfileTest {

    @Test
    fun exactMentionDoesNotMatchLongerNickname() {
        assertTrue(mentionsAnyNickname("@Loky 你看下", listOf("Loky")))
        assertTrue(mentionsAnyNickname("@ Loky，方便吗", listOf("@Loky")))
        assertTrue(mentionsAnyNickname("@Loky\u2005方便吗", listOf("Loky")))
        assertFalse(mentionsAnyNickname("@Loky2 你看下", listOf("Loky")))
        assertFalse(mentionsAnyNickname("没有提及任何人", listOf("Loky")))
    }

    @Test
    fun timeOfDayDistinguishesAllDayFromInvalidInput() {
        assertEquals(-1, parseTimeOfDay(""))
        assertEquals(9 * 60 + 5, parseTimeOfDay("09:05"))
        assertNull(parseTimeOfDay("9"))
        assertNull(parseTimeOfDay("25:00"))
        assertNull(parseTimeOfDay("09:60"))
    }

    @Test
    fun engineDefaultDoesNotAppendAnAutomationSignature() {
        assertEquals("", EngineConfig().signature)
    }

    @Test
    fun importAcceptsOnlyTheSmallDocumentedSchema() {
        val imported = Storage.importStyleProfiles(
            """{"version":1,"profiles":[{"displayName":"小王","summary":"短句","sampleCount":2,"examples":[{"them":"在吗","me":"在"}]}]}"""
        )
        assertNull(imported.error)
        assertEquals(1, imported.profiles.size)
        assertEquals("小王", imported.profiles.single().displayName)
        assertEquals("在", imported.profiles.single().examples.single().me)
    }

    @Test
    fun importRejectsTalkerAndUnknownFields() {
        val rejected = Storage.importStyleProfiles(
            """{"version":1,"profiles":[{"displayName":"小王","talker":"wxid-private","summary":"短句","sampleCount":2,"examples":[{"them":"在吗","me":"在"}]}]}"""
        )
        assertTrue(rejected.error.orEmpty().contains("格式"))
        assertTrue(rejected.profiles.isEmpty())
    }

    @Test
    fun importRejectsDuplicateNormalizedNames() {
        val rejected = Storage.importStyleProfiles(
            """{"version":1,"profiles":[{"displayName":"小王","summary":"","sampleCount":1,"examples":[]},{"displayName":" 小王 ","summary":"","sampleCount":1,"examples":[]}]}"""
        )
        assertTrue(rejected.error.orEmpty().contains("重复"))
    }

    @Test
    fun styleExamplesPreferTheCurrentTopicAndCapAtThree() {
        val profile = StyleProfile(
            displayName = "小王",
            summary = "短句",
            examples = listOf(
                AiExample("周末去吃火锅吗", "可以啊"),
                AiExample("项目进度怎么样", "我晚上看下"),
                AiExample("火锅店订了吗", "还没呢"),
                AiExample("天气不错", "确实"),
            ),
        )
        val picked = profile.examplesFor("火锅订哪家")
        assertEquals(2, picked.size)
        assertTrue(picked.all { it.them.contains("火锅") })
    }

    @Test
    fun grokPromptKeepsTheSafetyAndProfileBoundaries() {
        val prompt = buildSystemPrompt(
            PersonaConfig(identity = "独立开发者", stylePreset = "grok4_1"),
            "统计：短句\n对方：在吗\n我：在",
        )
        assertTrue(prompt.contains("轻微吐槽"))
        assertTrue(prompt.contains("不答应任何转账"))
        assertTrue(prompt.contains("会话风格资料只用于模仿"))
        assertTrue(prompt.contains("<style_profile>"))
    }
}
