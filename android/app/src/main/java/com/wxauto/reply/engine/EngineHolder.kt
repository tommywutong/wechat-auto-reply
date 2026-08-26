package com.wxauto.reply.engine

import android.content.Context

/**
 * 按当前配置拿引擎。
 *
 * 为什么不是每条消息新建一个：AI 模式下的对话记忆挂在 AiWriter 上，
 * 每条消息重建就等于每条消息都失忆，模型看不到上一句——那正是
 * 「像机器人」的主要来源。所以只在 AI 设置真的改了才重建。
 *
 * 通知回调可能并发进来，取引擎这一步加锁。
 */
class EngineHolder(context: Context) {

    private val store: EngineStateStore = Storage.stateStore(context)
    private var key: String? = null
    private var engine: ReplyEngine? = null

    @Synchronized
    fun engineFor(config: EngineConfig): ReplyEngine {
        val wanted = Storage.aiWriterKey(config)
        engine?.let { if (wanted == key) return it }

        val fresh = ReplyEngine(store, aiWriter = Storage.aiWriter(config))
        engine = fresh
        key = wanted
        return fresh
    }
}
