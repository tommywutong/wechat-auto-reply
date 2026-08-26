package com.wxauto.reply

import android.app.Notification
import android.app.PendingIntent
import android.app.RemoteInput
import android.content.Intent
import android.os.Bundle
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import com.wxauto.reply.engine.EngineHolder
import com.wxauto.reply.engine.Message
import com.wxauto.reply.engine.Storage
import java.util.concurrent.Executors

/**
 * 安卓自动回复的全部实现。
 *
 * 原理：微信的消息通知自带「回复」快捷操作（RemoteInput），
 * 系统允许通知监听器往里灌文字并触发。整个过程不碰微信界面、
 * 不需要 root、不需要无障碍权限，微信也不用切到前台。
 *
 * 规则引擎跑在本机（com.wxauto.reply.engine），不需要任何服务器——
 * 装完 APK 打开开关就能用。
 *
 * 局限：
 *   - 只能处理会弹通知的消息，免打扰的会话拿不到
 *   - 通知里的文本可能被系统截断，很长的消息读不全
 *   - 少数定制 ROM 会剥掉 RemoteInput，这时回落到无障碍方案
 *
 * 需要用户手动授予：设置 → 通知 → 通知使用权 → 打开本应用。
 */
class WeChatNotificationService : NotificationListenerService() {

    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var engines: EngineHolder

    override fun onCreate() {
        super.onCreate()
        engines = EngineHolder(this)
    }

    /**
     * 系统真正把通知流接给我们时才会回调这个。
     *
     * 记一笔是为了区分两种「没反应」：服务压根没连上（权限没给、
     * 或者被系统杀了），还是连上了但每条消息都被判断为不回。
     * 这两种的排查方向完全不同。
     */
    override fun onListenerConnected() {
        super.onListenerConnected()
        Storage.setListenerConnected(this, true)
        Storage.recordEvent(this, "已连接上通知，开始监听微信消息")
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        Storage.setListenerConnected(this, false)
        Storage.recordEvent(this, "通知监听断开了（可能被系统省电策略杀掉）")
    }

    override fun onDestroy() {
        executor.shutdown()
        super.onDestroy()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        // 收到任何一条通知（不限微信）都说明监听是活的。
        // 光靠 onListenerConnected 不够保险：个别 ROM 上它不一定回调，
        // 那样界面会一直显示「监听没连上」，反过来又是在误导用户。
        if (!Storage.isListenerConnected(this)) Storage.setListenerConnected(this, true)

        if (sbn.packageName != WECHAT_PACKAGE) return

        val notification = sbn.notification ?: return
        val extras = notification.extras ?: return

        // 汇总通知（「x 个联系人发来 y 条消息」）定位不到具体会话，跳过
        if (notification.flags and Notification.FLAG_GROUP_SUMMARY != 0) return

        val chatName = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val rawText = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty()
        if (chatName.isEmpty()) {
            Storage.recordEvent(this, "收到一条微信通知，但读不到是谁发的")
            return
        }

        // 先记下会话名，再判断能不能回。
        //
        // 这行原来在 handle() 里，而 handle() 只有在找得到回复入口时才会执行——
        // 于是在 ROM 剥掉 RemoteInput 的机器上，不但不回复，连白名单列表都
        // 一直是空的，用户会以为「程序根本没收到消息」。两个症状同一个原因。
        Storage.rememberSeenChat(this, chatName)

        if (rawText.isEmpty()) {
            Storage.recordEvent(
                this,
                "「$chatName」读不到消息内容 —— 多半是微信里关了「显示消息详情」",
            )
            return
        }

        val replyAction = findReplyAction(notification)
        if (replyAction == null) {
            Storage.recordEvent(
                this,
                "「$chatName」这条通知没有「回复」按钮，没法回。可以试试开无障碍兜底",
            )
            Log.i(TAG, "「$chatName」的通知没有回复入口，跳过")
            return
        }

        val (isGroup, senderName, text) = splitGroupMessage(extras, chatName, rawText)

        // 引擎判断和延迟发送都不能占用通知回调线程
        executor.execute {
            handle(replyAction, chatName, senderName, text, isGroup)
        }
    }

    private fun handle(
        action: Notification.Action,
        chatName: String,
        senderName: String,
        text: String,
        isGroup: Boolean,
    ) {
        // 每次都重新读配置：用户在界面上改完或用快捷开关关掉，立刻生效
        val config = Storage.loadConfig(this)

        // AI 模式下这一步会走网络，可能要几秒。executor 是单线程的，
        // 所以消息是排队处理的——回复本来就有频率限制，排队不影响结果，
        // 而且能保证不会有两条回复同时往外发。
        val decision = engines.engineFor(config).decide(
            config,
            Message(
                chatId = chatName,
                chatName = chatName,
                text = text,
                senderName = senderName,
                isGroup = isGroup,
                mentionedMe = text.contains("@"),
            ),
        )

        if (!decision.shouldReply || decision.text == null) {
            // 把原因记下来给用户看。不记的话，「为什么不回」在手机上
            // 是完全查不到的——用户只能看到「没反应」。
            // 带上「群/私聊」：群聊默认不回，而私聊被误判成群是个真实存在的
            // 失败模式，不标出来的话用户只会看到「群消息不回」而莫名其妙
            val kind = if (isGroup) "群" else "私聊"
            Storage.recordEvent(this, "[$kind]「$chatName」不回复：${decision.reason}")
            Log.i(TAG, "不回复「$chatName」：${decision.reason}")
            return
        }

        if (decision.delayMillis > 0) {
            try {
                Thread.sleep(decision.delayMillis)
            } catch (e: InterruptedException) {
                Thread.currentThread().interrupt()
                return
            }
        }

        // 延迟期间用户可能把开关关了，发之前再确认一次
        if (!Storage.loadConfig(this).enabled) {
            Storage.recordEvent(this, "「$chatName」等待期间开关被关掉了，没发")
            Log.i(TAG, "等待期间开关被关闭，放弃回复「$chatName」")
            return
        }

        if (sendReply(action, decision.text)) {
            Storage.recordEvent(this, "已回复「$chatName」：${decision.text}")
            Log.i(TAG, "已回复「$chatName」：${decision.text}")
        } else {
            // 等了几十秒才发，期间对方那条通知可能已经被用户点掉了，
            // 回复入口随之失效。这条路径不算少见，不能记成「已回复」。
            Storage.recordEvent(
                this,
                "「$chatName」没发出去：等待期间那条通知已经失效（多半是你自己点开看过了）",
            )
        }
    }

    /**
     * 判断是不是群消息，并把「张三: 内容」拆成发送人和正文。
     *
     * 判错的代价不对称，所以优先用系统给的确定信息：
     *   - 判成群 → 默认策略是「群消息不回」，于是私聊被静默吞掉
     *   - 判成私聊 → 可能往群里发消息，刷屏且更容易触发风控
     *
     * 所以顺序是：先看系统的 EXTRA_IS_GROUP_CONVERSATION（微信设了就直接用），
     * 再看群名末尾的成员数「(8)」，最后才退回「冒号前像个名字」这个猜测。
     * 最后那条会误伤——私聊里说一句「好的: 明天见」就中招——所以把
     * 前缀限制得严一些：短、且不含句子标点。
     */
    private fun splitGroupMessage(
        extras: Bundle,
        chatName: String,
        rawText: String,
    ): Triple<Boolean, String, String> {
        val colonIndex = rawText.indexOf(": ")
        val prefix = if (colonIndex in 1..20) rawText.substring(0, colonIndex) else null
        // 名字里不会有句末标点，正文里很容易有
        val prefixLooksLikeName = prefix != null &&
            prefix.none { it in "，。？！,.?!；;" }

        // 这个常量是 API 28 才有的，但它只是个字符串常量，编译期就内联进来了，
        // 安卓 8 上不会崩——读不到就是 false，自动退回下面的猜测。
        val systemSaysGroup = extras.getBoolean(Notification.EXTRA_IS_GROUP_CONVERSATION, false)
        val nameHasMemberCount = Regex("""[（(]\s*\d+\s*[)）]\s*$""").containsMatchIn(chatName)
        val isGroup = systemSaysGroup || nameHasMemberCount || prefixLooksLikeName

        return if (isGroup && prefix != null) {
            Triple(true, prefix, rawText.substring(colonIndex + 2))
        } else {
            Triple(isGroup, chatName, rawText)
        }
    }

    /** 在通知的 actions 里找带 RemoteInput 的那个，就是「回复」按钮。 */
    private fun findReplyAction(notification: Notification): Notification.Action? =
        notification.actions?.firstOrNull { it.remoteInputs?.isNotEmpty() == true }

    /**
     * 把文字塞进 RemoteInput 并触发 —— 等价于用户在通知栏里打字回复。
     *
     * 返回是否真的发出去了。调用方必须按这个结果记录，
     * 不能不管三七二十一都记「已回复」——那样日志会骗人，
     * 而这个日志正是用户唯一能自查的东西。
     */
    private fun sendReply(action: Notification.Action, text: String): Boolean {
        val remoteInputs = action.remoteInputs ?: return false
        val bundle = Bundle()
        for (input in remoteInputs) {
            bundle.putCharSequence(input.resultKey, text)
        }

        val intent = Intent()
        RemoteInput.addResultsToIntent(remoteInputs, intent, bundle)

        return try {
            action.actionIntent.send(this, 0, intent)
            true
        } catch (e: PendingIntent.CanceledException) {
            // 通知被划掉或已过期，重发没有意义
            Log.w(TAG, "回复入口已失效：${e.message}")
            false
        }
    }

    companion object {
        private const val TAG = "WeChatNotifService"
        private const val WECHAT_PACKAGE = "com.tencent.mm"
    }
}
