package com.wxauto.reply.engine

enum class Speaker { THEM, ME }

data class Turn(val speaker: Speaker, val text: String, val at: Long)

/**
 * 每个会话保留最近几轮，让模型看得到上下文。
 *
 * 没有上下文是「像机器人」的主要来源：对方说「那明天呢」，
 * 模型看不到前一句就只能瞎猜。
 *
 * 刻意只留很短的窗口并且会过期：聊天内容只在内存里，进程结束就没了，
 * 不落盘；太老的上下文反而会误导（三天前那事早翻篇了）。
 */
class ConversationMemory(
    private val maxTurns: Int = 8,
    private val ttlMillis: Long = 60 * 60 * 1000L,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private val chats = HashMap<String, ArrayDeque<Turn>>()

    @Synchronized
    fun remember(chatKey: String, speaker: Speaker, text: String) {
        val turns = chats.getOrPut(chatKey) { ArrayDeque() }
        turns.addLast(Turn(speaker, text, clock()))
        while (turns.size > maxTurns) turns.removeFirst()
    }

    @Synchronized
    fun recent(chatKey: String): List<Turn> {
        val turns = chats[chatKey] ?: return emptyList()
        val now = clock()
        val fresh = turns.filter { now - it.at <= ttlMillis }
        if (fresh.size != turns.size) {
            chats[chatKey] = ArrayDeque(fresh)
        }
        return fresh
    }

    @Synchronized
    fun forget(chatKey: String) {
        chats.remove(chatKey)
    }
}
