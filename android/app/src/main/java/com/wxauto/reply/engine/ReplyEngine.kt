package com.wxauto.reply.engine

import java.time.Instant
import java.time.ZoneId
import kotlin.random.Random

/**
 * 内嵌规则引擎 —— core/engine.py 的 Kotlin 版。
 *
 * 为什么要有这一份：手机上跑不了 Python 服务，而要求普通用户去装
 * Termux 敲命令是不现实的。把引擎搬进 App，装完 APK 打开开关就能用，
 * 不需要服务器、不需要电脑、不需要局域网。
 *
 * 行为必须和 Python 版保持一致，尤其是**判断顺序**：
 * 安全类判断（敏感词、黑名单）永远排在频率限制之前，
 * 这样即使把冷却调成 0 也不会误回转账类消息。
 *
 * 线程安全：通知回调可能并发进来，decide() 整体加锁。
 */
class ReplyEngine(
    private val store: EngineStateStore,
    private val clock: () -> Long = System::currentTimeMillis,
    private val random: Random = Random.Default,
    /**
     * AI 生成器。为 null 时即使配了 AI 模式也会退回不回复——
     * 宁可漏回，不可乱发。测试里注入假实现。
     */
    private val aiWriter: AiWriter? = null,
) {

    companion object {
        private const val DAY_MILLIS = 24 * 60 * 60 * 1000L
        private const val HOUR_MILLIS = 60 * 60 * 1000L

        /**
         * 命中即永不自动回复，不受任何配置影响。
         * 自动回一句「好的」给转账或验证码消息的代价，
         * 远高于漏回一条正常消息。
         */
        val HARD_BLOCK_KEYWORDS = listOf(
            "转账", "红包", "验证码", "银行卡", "身份证",
            "密码", "借钱", "急用钱", "汇款", "付款码",
        )
    }

    @Synchronized
    fun decide(config: EngineConfig, message: Message): Decision {
        val now = clock()
        val text = message.text.trim()

        if (!config.enabled) return Decision.skip("自动回复已关闭")
        if (text.isEmpty()) return Decision.skip("空消息")

        // ---- 安全类判断（永远优先） ----
        HARD_BLOCK_KEYWORDS.firstOrNull { text.contains(it) }?.let {
            return Decision.skip("含敏感词「$it」，交给你本人处理")
        }

        // 归一化后比对：用户手打的名字常有多余空格或大小写差异，
        // 而比对失败是静默的——名单形同虚设，用户还不知道
        val name = normalizeChatName(message.chatName)
        if (config.blockContacts.any { normalizeChatName(it) == name }) {
            return Decision.skip("${message.chatName} 在不回复名单里")
        }

        config.blockKeywords.firstOrNull { it.isNotBlank() && text.contains(it) }?.let {
            return Decision.skip("含屏蔽词「$it」")
        }

        val allow = config.allowContacts.filter { it.isNotBlank() }
        if (allow.isNotEmpty() && allow.none { normalizeChatName(it) == name }) {
            return Decision.skip("${message.chatName} 不在指定名单里")
        }

        // ---- 会话类型 ----
        if (message.isGroup) {
            when (config.groupPolicy) {
                GroupPolicy.NEVER -> return Decision.skip("群消息不回")
                GroupPolicy.ONLY_AT_ME ->
                    if (!message.mentionedMe) return Decision.skip("群消息没 @ 我")
                GroupPolicy.ALWAYS -> Unit
            }
        } else if (!config.replyToPrivate) {
            return Decision.skip("私聊不回")
        }

        // ---- 时段 ----
        if (!withinActiveHours(config, now)) {
            return Decision.skip("不在自动回复时段内")
        }

        val identity = identityOf(message)

        // ---- 频率限制 ----
        rateLimitReason(config, identity, now)?.let { return Decision.skip(it) }

        // ---- AI 模式：整段交给模型 ----
        // 注意这里的位置：安全判断（敏感词、黑名单、群聊策略）在上面
        // 已经全部做完了。模型只负责「说什么」，不负责「该不该说」——
        // 后者不能交给一个概率性的东西。
        if (config.replyMode == ReplyMode.AI) {
            if (aiWriter == null) return Decision.skip("没有配置 AI 接口")
            val generated = try {
                aiWriter.write(message.copy(text = text), config)
            } catch (e: Exception) {
                // 生成失败绝不能拖垮整条链路
                return Decision.skip("AI 生成失败：${e.message}")
            }
            if (generated.isNullOrBlank()) return Decision.skip("AI 没返回可用内容")
            return commit(config, identity, generated, "AI 生成", null, now)
        }

        // ---- 命中规则 ----
        for (rule in config.rules) {
            if (rule.replies.none { it.isNotBlank() }) continue
            if (rule.matches(text)) {
                val reply = pickReply(rule)
                return commit(config, identity, reply, "命中规则「${rule.name}」", rule.name, now)
            }
        }

        // ---- 兜底 ----
        if (config.fallbackText.isBlank()) {
            return Decision.skip("没有匹配的规则")
        }
        return commit(config, identity, config.fallbackText, "默认回复", null, now)
    }

    // ------------------------------------------------------------------ 内部

    /**
     * 会话身份。用归一化的会话名而不是通知给的 key：
     * 同一个人的通知 key 可能因为消息类型而变，用名字更稳。
     * 群名后面的成员数会变，不能算进身份。
     */
    private fun identityOf(message: Message): String {
        val name = normalizeChatName(message.chatName)
        return if (message.isGroup) "group:$name" else "private:$name"
    }

    private fun withinActiveHours(config: EngineConfig, now: Long): Boolean {
        val from = config.activeFromMinute
        val to = config.activeToMinute
        if (from < 0 || to < 0) return true

        // 用传进来的时刻，不要用 LocalTime.now()：
        // 引擎接了 clock 参数就该一路用到底，否则时段判断没法测，
        // 而且和 Python 版（用的是注入时钟）行为不一致。
        val nowTime = Instant.ofEpochMilli(now).atZone(ZoneId.systemDefault()).toLocalTime()
        val current = nowTime.hour * 60 + nowTime.minute
        // 支持跨零点，例如 22:00-02:00
        return if (from <= to) current in from..to else current >= from || current <= to
    }

    private fun rateLimitReason(config: EngineConfig, identity: String, now: Long): String? {
        val last = store.lastReplyAt(identity)
        if (last != null && now - last < config.cooldownSeconds * 1000L) {
            val remainMinutes = ((config.cooldownSeconds * 1000L - (now - last)) / 60000L) + 1
            return "刚回过，${remainMinutes} 分钟内不再回"
        }

        val today = store.chatReplyTimes(identity).filter { now - it < DAY_MILLIS }
        store.setChatReplyTimes(identity, today)
        if (today.size >= config.maxPerChatPerDay) {
            return "今天已经回过 ${config.maxPerChatPerDay} 条了"
        }

        // 只保留一份 24 小时的记录，小时窗口和天窗口都从它算，
        // 免得两份列表各裁各的、对不上
        val recent = store.recentReplyTimes().filter { now - it < DAY_MILLIS }
        store.setRecentReplyTimes(recent)

        if (recent.count { now - it < HOUR_MILLIS } >= config.maxPerHour) {
            return "一小时内回复数已达上限 ${config.maxPerHour} 条"
        }
        if (recent.size >= config.maxPerDay) {
            return "今天回复总数已达上限 ${config.maxPerDay} 条"
        }

        return null
    }

    /**
     * 轮换文案。
     *
     * 计数是全局的（只按规则名），不按会话分开。按会话算的话，每个人
     * 拿到的都是第一句——一百个人收到一模一样的一句话，那正是批量发送
     * 最容易被认出来的地方。
     */
    private fun pickReply(rule: Rule): String {
        val usable = rule.replies.filter { it.isNotBlank() }
        val index = store.rotationIndex(rule.name) + 1
        store.setRotationIndex(rule.name, index)
        return usable[index.mod(usable.size)]
    }

    private fun commit(
        config: EngineConfig,
        identity: String,
        rawText: String,
        reason: String,
        ruleName: String?,
        now: Long,
    ): Decision {
        val text = if (config.signature.isNotBlank()) rawText + config.signature else rawText

        store.setLastReplyAt(identity, now)
        store.setChatReplyTimes(identity, store.chatReplyTimes(identity) + now)
        store.setRecentReplyTimes(store.recentReplyTimes() + now)

        // ---- 延迟 ----
        // 三部分：基础随机延迟（秒回是最明显的机器特征）、
        // 按字数算的打字时间（真人打 30 个字比打「嗯」慢）、
        // 以及跨会话的最小间隔。
        val minMs = config.minDelaySeconds.coerceAtLeast(0) * 1000L
        val maxMs = config.maxDelaySeconds.coerceAtLeast(config.minDelaySeconds) * 1000L
        var delay = if (maxMs > minMs) random.nextLong(minMs, maxMs) else minMs
        delay += text.length * config.typingMillisPerChar.coerceAtLeast(0)

        // 冷却是按会话算的，挡不住「三十个人同时发消息、几十秒内挨个回完」。
        // 这里把发送时刻往后推，让多条回复依次排开，而不是丢掉消息。
        val earliest = store.lastSendAt() + config.minIntervalSeconds * 1000L
        val sendAt = maxOf(now + delay, earliest)
        delay = sendAt - now
        store.setLastSendAt(sendAt)

        store.flush()

        return Decision(
            shouldReply = true,
            reason = reason,
            text = text,
            delayMillis = delay,
            ruleName = ruleName,
        )
    }
}

/**
 * 引擎状态（冷却、配额、文案轮换下标）的存取。
 * 抽成接口是为了让引擎本身不依赖 Android，方便单测。
 */
interface EngineStateStore {
    fun lastReplyAt(identity: String): Long?
    fun setLastReplyAt(identity: String, at: Long)

    fun chatReplyTimes(identity: String): List<Long>
    fun setChatReplyTimes(identity: String, times: List<Long>)

    fun recentReplyTimes(): List<Long>
    fun setRecentReplyTimes(times: List<Long>)

    fun rotationIndex(key: String): Int
    fun setRotationIndex(key: String, index: Int)

    /** 上一条回复的「预计发出时刻」，用来拉开跨会话的间隔。 */
    fun lastSendAt(): Long
    fun setLastSendAt(at: Long)

    /** 把内存里的改动落盘。 */
    fun flush()
}

/** 纯内存实现，单测用；App 里用 SharedPreferences 版。 */
class InMemoryStateStore : EngineStateStore {
    private val last = HashMap<String, Long>()
    private val perChat = HashMap<String, List<Long>>()
    private var recent: List<Long> = ArrayList()
    private val rotation = HashMap<String, Int>()
    private var lastSend: Long = 0L

    override fun lastReplyAt(identity: String) = last[identity]
    override fun setLastReplyAt(identity: String, at: Long) { last[identity] = at }
    override fun chatReplyTimes(identity: String) = perChat[identity] ?: emptyList()
    override fun setChatReplyTimes(identity: String, times: List<Long>) { perChat[identity] = times }
    override fun recentReplyTimes() = recent
    override fun setRecentReplyTimes(times: List<Long>) { recent = times }
    override fun rotationIndex(key: String) = rotation[key] ?: -1
    override fun setRotationIndex(key: String, index: Int) { rotation[key] = index }
    override fun lastSendAt() = lastSend
    override fun setLastSendAt(at: Long) { lastSend = at }
    override fun flush() = Unit
}
