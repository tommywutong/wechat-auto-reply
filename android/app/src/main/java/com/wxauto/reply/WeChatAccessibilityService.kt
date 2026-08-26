package com.wxauto.reply

import android.accessibilityservice.AccessibilityService
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.wxauto.reply.engine.EngineHolder
import com.wxauto.reply.engine.Message
import com.wxauto.reply.engine.Storage
import java.util.concurrent.Executors

/**
 * 兜底方案：直接操作微信界面。
 *
 * 什么时候需要它：
 *   - 定制 ROM 剥掉了通知里的 RemoteInput
 *   - 会话开了免打扰，压根不弹通知
 *   - 消息太长，通知里被截断
 *
 * 代价：需要无障碍权限（权限很大，用户要清楚自己授了什么），
 * 而且必须让微信保持在前台的聊天页面，否则找不到输入框。
 * 能用通知方案就别用这个。
 */
class WeChatAccessibilityService : AccessibilityService() {

    private val executor = Executors.newSingleThreadExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())
    private lateinit var engines: EngineHolder

    /** 记住上次处理过的消息，避免同一条被界面刷新触发多次。 */
    private var lastHandled: String? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        engines = EngineHolder(this)
        Storage.recordEvent(this, "无障碍兜底已开启")
        Log.i(TAG, "无障碍服务已连接")
    }

    override fun onDestroy() {
        executor.shutdown()
        super.onDestroy()
    }

    override fun onInterrupt() {}

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null || event.packageName != WECHAT_PACKAGE) return
        if (event.eventType != AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED &&
            event.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
        ) return

        val root = rootInActiveWindow ?: return
        val chatName = readChatTitle(root) ?: return
        val incoming = readLastIncomingMessage(root) ?: return

        val fingerprint = "$chatName|$incoming"
        if (fingerprint == lastHandled) return
        lastHandled = fingerprint

        executor.execute { handle(chatName, incoming) }
    }

    private fun handle(chatName: String, text: String) {
        // 和通知那条路一样：先记下会话名，再判断回不回。
        // 少了这一行，用户开着无障碍兜底时，界面上的联系人勾选列表
        // 会一直是空的——他会以为程序根本没收到消息。
        Storage.rememberSeenChat(this, chatName)

        val isGroup = Regex("""\(\d+\)$""").containsMatchIn(chatName)
        val config = Storage.loadConfig(this)
        val decision = engines.engineFor(config).decide(
            config,
            Message(
                chatId = chatName,
                chatName = chatName,
                text = text,
                senderName = chatName,
                isGroup = isGroup,
                mentionedMe = text.contains("@"),
            ),
        )

        if (!decision.shouldReply || decision.text == null) {
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

        // 等待期间用户可能把开关关了，发之前再确认一次（和通知那条路保持一致）
        if (!Storage.loadConfig(this).enabled) {
            Storage.recordEvent(this, "「$chatName」等待期间开关被关掉了，没发")
            return
        }

        // UI 操作必须回主线程。
        // 这里用 Handler 而不是 Context.mainExecutor：后者要 API 28，
        // 而我们的 minSdk 是 26——安卓 8 的机器上会直接崩。
        mainHandler.post { typeAndSend(chatName, decision.text) }
    }

    /** 聊天页标题栏就是会话名。 */
    private fun readChatTitle(root: AccessibilityNodeInfo): String? =
        root.findAccessibilityNodeInfosByViewId("$WECHAT_PACKAGE:id/kn")
            ?.firstOrNull()?.text?.toString()
            ?: root.findAccessibilityNodeInfosByViewId("$WECHAT_PACKAGE:id/g3")
                ?.firstOrNull()?.text?.toString()

    /**
     * 读最后一条对方发来的消息。
     *
     * 和 iOS 方案同理：靠气泡在屏幕上的水平位置区分收发。
     * 微信的 viewId 每个版本都变，位置判据反而更耐用。
     */
    private fun readLastIncomingMessage(root: AccessibilityNodeInfo): String? {
        val screenWidth = resources.displayMetrics.widthPixels
        val candidates = mutableListOf<Pair<Int, String>>()

        fun walk(node: AccessibilityNodeInfo?) {
            if (node == null) return
            val text = node.text?.toString()
            if (!text.isNullOrBlank() && node.className == "android.widget.TextView") {
                val bounds = android.graphics.Rect()
                node.getBoundsInScreen(bounds)
                candidates += bounds.centerX() to text
            }
            for (i in 0 until node.childCount) walk(node.getChild(i))
        }
        walk(root)

        // 中心点在左半屏 = 对方发的
        return candidates.lastOrNull { it.first < screenWidth / 2 }?.second
    }

    /**
     * 往输入框里填字并点发送。
     *
     * 这条路每一步都可能失败（页面已经切走、微信改了控件、点击被拦），
     * 而且失败得毫无声响。所以每一步的结果都要记进事件日志——
     * 那是用户在手机上唯一能自查的东西。
     * 尤其不能像原来那样：点完就记「已发送」，实际根本没发出去。
     */
    private fun typeAndSend(chatName: String, text: String) {
        val root = rootInActiveWindow
        if (root == null) {
            Storage.recordEvent(this, "「$chatName」没发出去：微信已经不在前台了")
            return
        }

        val input = findEditable(root)
        if (input == null) {
            Storage.recordEvent(this, "「$chatName」没发出去：找不到输入框（可能已经不在聊天页）")
            Log.w(TAG, "找不到输入框，可能不在聊天页")
            return
        }

        val args = Bundle().apply {
            putCharSequence(
                AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text
            )
        }
        if (!input.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) {
            Storage.recordEvent(this, "「$chatName」没发出去：文字填不进输入框")
            return
        }

        val sendButton = root.findAccessibilityNodeInfosByText("发送")
            ?.firstOrNull { it.isClickable }
        if (sendButton == null) {
            // 文字已经在输入框里了，如实说清楚：用户自己按一下发送就行
            Storage.recordEvent(this, "「$chatName」文字已填好，但找不到发送按钮，没点出去")
            Log.w(TAG, "找不到发送按钮，文本已填入但未发出")
            return
        }

        if (sendButton.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
            Storage.recordEvent(this, "已回复「$chatName」：$text")
            Log.i(TAG, "已发送：$text")
        } else {
            Storage.recordEvent(this, "「$chatName」文字已填好，但发送按钮点不动")
        }
    }

    private fun findEditable(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (node == null) return null
        if (node.isEditable) return node
        for (i in 0 until node.childCount) {
            findEditable(node.getChild(i))?.let { return it }
        }
        return null
    }

    companion object {
        private const val TAG = "WeChatA11yService"
        private const val WECHAT_PACKAGE = "com.tencent.mm"
    }
}
