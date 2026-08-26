package com.wxauto.reply

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.text.TextUtils
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import com.wxauto.reply.engine.AiConfig
import com.wxauto.reply.engine.AiExample
import com.wxauto.reply.engine.AiSource
import com.wxauto.reply.engine.Decision
import com.wxauto.reply.engine.EngineConfig
import com.wxauto.reply.engine.GroupPolicy
import com.wxauto.reply.engine.InMemoryStateStore
import com.wxauto.reply.engine.Message
import com.wxauto.reply.engine.normalizeChatName
import com.wxauto.reply.engine.OpenAiCompatibleWriter
import com.wxauto.reply.engine.PersonaConfig
import com.wxauto.reply.engine.ReplyEngine
import com.wxauto.reply.engine.ReplyMode
import com.wxauto.reply.engine.Rule
import com.wxauto.reply.engine.Storage

/**
 * 唯一的界面。目标是「装完打开、拨一下开关就能用」，
 * 所以默认值都填好了，用户不改任何东西也能正常工作。
 */
class MainActivity : Activity() {

    private lateinit var masterSwitch: Switch
    private lateinit var permissionStatus: TextView
    private lateinit var eventsView: TextView
    private lateinit var groupPolicyGroup: RadioGroup
    private lateinit var fallbackField: EditText
    private lateinit var blockContactsField: EditText
    private lateinit var allowContactsField: EditText
    private lateinit var seenContactsContainer: LinearLayout
    private lateinit var rulesContainer: LinearLayout
    private lateinit var testInput: EditText
    private lateinit var testResult: TextView
    private lateinit var testAsGroup: CheckBox

    // ---- 回复方式 ----
    private lateinit var modeGroup: RadioGroup
    private lateinit var keywordPanel: LinearLayout
    private lateinit var aiPanel: LinearLayout

    // ---- AI：接哪儿 ----
    private lateinit var aiSourceGroup: RadioGroup
    private lateinit var ownKeyPanel: LinearLayout
    private lateinit var relayPanel: LinearLayout
    private lateinit var baseUrlField: EditText
    private lateinit var apiKeyField: EditText
    private lateinit var modelField: EditText
    private lateinit var presetNote: TextView
    private lateinit var relayUrlField: EditText
    private lateinit var relayTokenField: EditText

    // ---- AI：人设 ----
    private lateinit var identityField: EditText
    private lateinit var toneField: EditText
    private lateinit var playbookField: EditText
    private lateinit var maxCharsField: EditText
    private lateinit var examplesContainer: LinearLayout

    private val modeKeywordId = View.generateViewId()
    private val modeAiId = View.generateViewId()
    private val sourceOwnKeyId = View.generateViewId()
    private val sourceRelayId = View.generateViewId()
    private val groupNeverId = View.generateViewId()
    private val groupAtMeId = View.generateViewId()
    private val groupAlwaysId = View.generateViewId()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildUi())
        loadIntoUi(Storage.loadConfig(this))

        // 第一次打开先问几个问题，别一上来就把一屏设置摔在人脸上
        if (!Storage.isWizardDone(this)) openWizard()
    }

    private fun openWizard() {
        startActivityForResult(Intent(this, SetupWizardActivity::class.java), REQUEST_WIZARD)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        // 问答写完配置了，把界面上的内容换成新生成的那套。
        // 只在这里重刷，不在 onResume 里——否则从系统设置页返回时
        // 会把用户还没保存的修改冲掉。
        if (requestCode == REQUEST_WIZARD && resultCode == RESULT_OK) {
            loadIntoUi(Storage.loadConfig(this))
            Toast.makeText(this, "已按你的回答生成好了", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onResume() {
        super.onResume()
        // 授权了但服务没连上就自己修一次。这个状态多半是覆盖安装
        // 或者重启造成的，用户完全看不出来，不该让他自己去点按钮。
        if (isNotificationAccessGranted() && !Storage.isListenerConnected(this)) {
            requestListenerRebind(quiet = true)
        }

        refreshPermissionStatus()
        refreshEvents()

        // 刚有人发消息进来的话，白名单那份勾选列表要跟着长出来。
        // 用界面上当前的选择重建，而不是用存盘的配置——否则用户还没保存的
        // 修改会被这次刷新冲掉。
        renderSeenContacts(
            checkedSeenContacts() + splitList(allowContactsField.text.toString())
        )

        // 只在真的不一致时才改（比如刚用下拉磁贴关掉了）。
        // 无条件赋值会触发 setOnCheckedChangeListener，于是每次切回
        // 这个界面都弹一次「自动回复已开启」，看着像出了什么事。
        val enabled = Storage.loadConfig(this).enabled
        if (masterSwitch.isChecked != enabled) masterSwitch.isChecked = enabled
    }

    // ------------------------------------------------------------------ 界面

    private fun buildUi(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(28), dp(20), dp(28))
        }

        root.addView(title("微信自动回复"))

        // ---- 总开关 ----
        masterSwitch = Switch(this).apply {
            text = "  自动回复"
            textSize = 20f
            setTypeface(null, Typeface.BOLD)
            setPadding(dp(12), dp(16), dp(12), dp(16))
            setOnCheckedChangeListener { _, checked ->
                Storage.setEnabled(this@MainActivity, checked)
                Toast.makeText(
                    this@MainActivity,
                    if (checked) "自动回复已开启" else "自动回复已关闭",
                    Toast.LENGTH_SHORT,
                ).show()
                refreshPermissionStatus()
            }
        }
        root.addView(masterSwitch)

        permissionStatus = TextView(this).apply {
            setPadding(dp(12), 0, dp(12), dp(12))
        }
        root.addView(permissionStatus)

        root.addView(Button(this).apply {
            text = "授予通知使用权（必须）"
            setOnClickListener {
                startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
            }
        })

        root.addView(hint("在打开的页面里找到「微信自动回复」并打开。不给这个权限，程序看不到微信消息。"))

        // 覆盖安装之后，系统经常把已经授权的通知监听服务停掉不再重连，
        // 表现就是「权限明明开着，但一条消息都收不到」。
        // 官方给的补救办法就是 requestRebind，不用让用户去手动关了再开。
        root.addView(Button(this).apply {
            text = "收不到消息？点这里重连"
            setOnClickListener { requestListenerRebind() }
        })
        root.addView(hint(
            "刚更新过 App、或者手机重启过之后，系统有时会把监听停掉。" +
                "下面「最近发生了什么」一直是空的，就点一下这个。"
        ))

        // 兜底方案的入口。原来只在日志里写「可以试试开无障碍兜底」，
        // 却没有任何地方能开——等于没有这条退路。
        // 放在这里而不是更显眼的位置：无障碍权限很大，能不开就别开。
        root.addView(Button(this).apply {
            text = "备用方案：无障碍回复（一般用不上）"
            setOnClickListener {
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }
        })
        root.addView(hint(
            "只有当上面的记录里反复出现「这条通知没有回复按钮」时才需要开它。\n" +
                "⚠️ 无障碍权限能读到屏幕上的全部内容，权限很大；" +
                "而且开了之后必须让微信停在聊天页面才回得了。能不开就别开。"
        ))

        root.addView(divider())

        // ---- 运行记录 ----
        // 安卓端原来是个黑盒：不回复时用户只能看到「没反应」，
        // 而原因全在 logcat 里——普通用户一辈子不会去看那个。
        root.addView(section("最近发生了什么"))
        root.addView(hint(
            "程序每收到一条微信消息都会在这里记一笔，以及为什么回了或者没回。" +
                "觉得「怎么不动」的时候，先看这里。"
        ))

        eventsView = TextView(this).apply {
            textSize = 13f
            setTextColor(Color.parseColor("#455A64"))
            setPadding(dp(12), dp(8), dp(12), dp(8))
            setTextIsSelectable(true)
        }
        root.addView(eventsView)

        root.addView(Button(this).apply {
            text = "刷新"
            setOnClickListener { refreshEvents() }
        })

        root.addView(divider())

        // ---- 重新答问答 ----
        root.addView(section("回复内容"))
        root.addView(Button(this).apply {
            text = "回答几个问题，自动生成"
            setOnClickListener { openWizard() }
        })
        root.addView(hint(
            "十道选择题，一分钟答完，会把下面这些内容整套生成好——" +
                "包括 AI 模式下的人设。答完还能在下面一句一句地改。"
        ))

        root.addView(divider())

        // ---- 回复方式 ----
        root.addView(section("怎么回"))
        modeGroup = RadioGroup(this).apply {
            orientation = RadioGroup.VERTICAL
            addView(RadioButton(context).apply {
                id = modeKeywordId
                text = "按关键词回固定的话"
            })
            addView(RadioButton(context).apply {
                id = modeAiId
                text = "让 AI 按你的说话方式现写"
            })
            setOnCheckedChangeListener { _, _ -> refreshModePanels() }
        }
        root.addView(modeGroup)
        root.addView(hint(
            "关键词：不联网、不花钱，但只能回你事先写好的那几句。\n" +
                "AI：每条消息现写，看得懂对方在说什么，语气像你本人。需要联网，" +
                "并且要下面二选一填一个接口。"
        ))

        keywordPanel = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        aiPanel = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(keywordPanel)
        root.addView(aiPanel)

        buildKeywordPanel(keywordPanel)
        buildAiPanel(aiPanel)

        root.addView(divider())

        // ---- 群聊 ----
        root.addView(section("群聊消息"))
        groupPolicyGroup = RadioGroup(this).apply {
            orientation = RadioGroup.VERTICAL
            addView(RadioButton(context).apply { id = groupNeverId; text = "不回群消息（推荐）" })
            addView(RadioButton(context).apply { id = groupAtMeId; text = "只在别人 @ 我时回" })
            addView(RadioButton(context).apply { id = groupAlwaysId; text = "群里任何消息都回（容易刷屏）" })
        }
        root.addView(groupPolicyGroup)

        root.addView(divider())

        // ---- 白名单 ----
        // 放在黑名单前面，因为它才是真正管用的那条：
        // 会导致封号的主要路径是被举报，而熟人不会举报你。
        root.addView(section("只对这些人自动回复"))
        root.addView(hint(
            "勾上谁，就只有谁会收到自动回复，其他人一律不回。\n\n" +
                "⚠️ 这是最有效的防封号手段。真正可能出事的是「被人举报」，" +
                "而熟人不会举报你。强烈建议先勾三五个熟人跑几天，再考虑放开。"
        ))

        // 从「给你发过消息的人」里勾选。
        // 读不到微信通讯录（那是微信的私有数据），但最近联系过的人
        // 恰好就够用了——而且勾选比手打名字准得多。
        seenContactsContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        root.addView(seenContactsContainer)

        allowContactsField = EditText(this).apply {
            hint = "还没聊过的人，可以在这里手打名字，逗号隔开"
        }
        root.addView(allowContactsField)
        root.addView(hint(
            "上面的勾选框一勾就生效，不用再点保存。\n" +
                "手打的名字要点页面最下面的「保存设置」才算数。\n\n" +
                "手打的话，填你在微信里看到的那个名字——**设了备注就填备注名**，" +
                "没设备注就填昵称。不是微信号。\n" +
                "多余的空格和大小写不影响匹配。"
        ))

        root.addView(divider())

        // ---- 不回复名单 ----
        root.addView(section("这些人永远不自动回"))
        blockContactsField = EditText(this).apply {
            hint = "多个人用逗号隔开，例如：老板，妈妈"
        }
        root.addView(blockContactsField)

        root.addView(divider())

        // ---- 试一试 ----
        // 不真发消息就能看到会回什么。开启之前先在这里把语气调顺，
        // 比让对方当小白鼠强。
        root.addView(section("试一试（不会真的发出去）"))
        testInput = EditText(this).apply {
            hint = "假装别人发来一句话，比如：在吗"
        }
        root.addView(testInput)

        testAsGroup = CheckBox(this).apply { text = "当作群里 @ 我的消息" }
        root.addView(testAsGroup)

        root.addView(Button(this).apply {
            text = "看看会回什么"
            setOnClickListener { runPreview() }
        })

        testResult = TextView(this).apply {
            setPadding(dp(12), dp(8), dp(12), dp(8))
            textSize = 15f
        }
        root.addView(testResult)

        root.addView(hint(
            "用的是你当前填的内容，不用先保存。试的时候不占用「每天最多回几条」的额度。\n" +
                "AI 模式下这里会真的调一次接口，可以顺便验证 key 填对没有。"
        ))

        root.addView(divider())

        root.addView(Button(this).apply {
            text = "保存设置"
            setOnClickListener { saveFromUi() }
        })

        root.addView(hint(
            "小提示：下拉通知栏 → 点编辑（铅笔图标）→ 把「微信自动回复」拖进快捷开关，" +
                "以后下拉一点就能开关，不用每次打开这个 App。"
        ))

        root.addView(hint(
            "安全说明：遇到含「转账、红包、验证码、借钱」等字样的消息，" +
                "程序一律不自动回，交给你本人处理。这条改不了，AI 模式下也一样——" +
                "这类消息压根不会发给模型。\n\n" +
                "每条回复末尾会带「（自动回复）」，让对方知道不是你本人在回。"
        ))

        return ScrollView(this).apply {
            addView(root, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
    }

    // ---------------------------------------------------------- 关键词模式面板

    private fun buildKeywordPanel(panel: LinearLayout) {
        panel.addView(section("收到这些词，就回这句话"))
        rulesContainer = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        panel.addView(rulesContainer)

        panel.addView(Button(this).apply {
            text = "＋ 再加一条"
            setOnClickListener {
                rulesContainer.addView(ruleRow(Rule(name = "规则", replies = listOf(""))))
            }
        })

        panel.addView(section("其他消息统一回"))
        fallbackField = EditText(this).apply { hint = "留空表示不回" }
        panel.addView(fallbackField)
        panel.addView(hint("上面的词都没匹配上时，回这一句。"))
    }

    /** 一条规则的编辑行：关键词 + 回复内容 + 删除按钮。 */
    private fun ruleRow(rule: Rule): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(8), 0, dp(8))
        }

        val keywords = EditText(this).apply {
            hint = "关键词，多个用逗号隔开，例如：在吗，在么"
            setText(rule.keywords.joinToString("，"))
            tag = TAG_KEYWORDS
        }
        val reply = EditText(this).apply {
            hint = "回复内容"
            setText(rule.replies.firstOrNull().orEmpty())
            tag = TAG_REPLY
        }
        val remove = Button(this).apply {
            text = "删除这条"
            setOnClickListener { rulesContainer.removeView(row) }
        }

        row.addView(keywords)
        row.addView(reply)
        row.addView(remove)
        return row
    }

    // ---------------------------------------------------------------- AI 面板

    private fun buildAiPanel(panel: LinearLayout) {
        panel.addView(section("AI 从哪儿来"))
        aiSourceGroup = RadioGroup(this).apply {
            orientation = RadioGroup.VERTICAL
            addView(RadioButton(context).apply {
                id = sourceOwnKeyId
                text = "我自己注册一个（推荐，谁也不依赖）"
            })
            addView(RadioButton(context).apply {
                id = sourceRelayId
                text = "用别人给我的地址"
            })
            setOnCheckedChangeListener { _, _ -> refreshAiSourcePanels() }
        }
        panel.addView(aiSourceGroup)

        // ---- 自己的 key ----
        ownKeyPanel = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        panel.addView(ownKeyPanel)

        ownKeyPanel.addView(hint(
            "去下面任意一家的官网注册，在「API Key」页面点一下新建，" +
                "把那串字符复制过来。国内直接能用，不用翻墙。多数家新注册都送额度，" +
                "自动回复用量很小，基本花不到钱。\n\n" +
                "不知道选哪个就选豆包——聊天的中文语气这几家里它最自然。"
        ))

        // 预设按钮：省掉「接口地址填什么」这个最容易卡住人的问题
        val presetRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        OpenAiCompatibleWriter.PRESETS.forEach { preset ->
            presetRow.addView(Button(this).apply {
                text = preset.name
                setOnClickListener {
                    baseUrlField.setText(preset.baseUrl)
                    modelField.setText(preset.model)
                    presetNote.text = preset.note
                    presetNote.visibility = if (preset.note.isBlank()) View.GONE else View.VISIBLE
                    Toast.makeText(
                        this@MainActivity,
                        "已填好${preset.name}的地址，下面把 key 粘进去就行",
                        Toast.LENGTH_SHORT,
                    ).show()
                }
            })
        }
        ownKeyPanel.addView(HorizontalScrollView(this).apply { addView(presetRow) })
        ownKeyPanel.addView(hint("↑ 先点一下你注册的那家，地址和模型会自动填好"))

        presetNote = hint("").apply { visibility = View.GONE }
        ownKeyPanel.addView(presetNote)

        apiKeyField = EditText(this).apply {
            hint = "把 API Key 粘贴到这里"
            // 用可见密码类型：不走自动纠错和联想，但用户能看清自己粘对没有
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
        }
        ownKeyPanel.addView(apiKeyField)

        baseUrlField = EditText(this).apply {
            hint = "接口地址（点上面的按钮会自动填）"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        ownKeyPanel.addView(baseUrlField)

        modelField = EditText(this).apply { hint = "模型名（点上面的按钮会自动填）" }
        ownKeyPanel.addView(modelField)

        // ---- 别人的地址 ----
        relayPanel = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        panel.addView(relayPanel)

        relayPanel.addView(hint(
            "让对方把他那边的地址和口令发给你，粘进来就行，不用注册任何账号。\n" +
                "注意：这样一来，你收到的消息会经过对方的服务器，回复内容也由那边生成。" +
                "只填你信得过的人给的地址。"
        ))

        relayUrlField = EditText(this).apply {
            hint = "地址，形如 http://1.2.3.4:8848"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        relayPanel.addView(relayUrlField)

        relayTokenField = EditText(this).apply {
            hint = "口令"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
        }
        relayPanel.addView(relayTokenField)

        // ---- 人设 ----
        // 只有自己的 key 才需要填人设；用别人地址时人设在对方那边。
        panel.addView(divider())
        panel.addView(section("你是个什么样的人"))
        panel.addView(hint(
            "这一段决定回复像不像你本人。写的是「怎么判断」，不是「说什么」——" +
                "你不用去猜别人会发什么，AI 会照着这里自己判断。"
        ))

        identityField = multiline("你是谁、平时在忙什么、为什么现在不方便回", 2)
        panel.addView(labeled("我是谁", identityField))

        toneField = multiline("越具体越像。别写「友好」「专业」这种空词", 2)
        panel.addView(labeled("我说话的方式", toneField))

        playbookField = multiline("一行写一种情况，例如：有人约时间，就说要确认日程", 6)
        panel.addView(labeled("各种情况怎么应对（最重要）", playbookField))

        maxCharsField = EditText(this).apply {
            hint = "回复最多多少字"
            inputType = InputType.TYPE_CLASS_NUMBER
        }
        panel.addView(labeled("回复长度上限", maxCharsField))
        panel.addView(hint("真人回微信很少写长段，建议 30 字以内。"))

        panel.addView(section("你平时是怎么说话的"))
        panel.addView(hint(
            "写几组你真的会说的话。这比任何形容词都管用——AI 会直接模仿这里的语气。" +
                "务必用你自己的口气写，别写成客服话术。"
        ))
        examplesContainer = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        panel.addView(examplesContainer)
        panel.addView(Button(this).apply {
            text = "＋ 再加一组"
            setOnClickListener { examplesContainer.addView(exampleRow(AiExample("", ""))) }
        })
    }

    private fun exampleRow(example: AiExample): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(8), 0, dp(8))
        }
        val them = EditText(this).apply {
            hint = "对方说："
            setText(example.them)
            tag = TAG_EX_THEM
        }
        val me = EditText(this).apply {
            hint = "我会回："
            setText(example.me)
            tag = TAG_EX_ME
        }
        val remove = Button(this).apply {
            text = "删除这组"
            setOnClickListener { examplesContainer.removeView(row) }
        }
        row.addView(them)
        row.addView(me)
        row.addView(remove)
        return row
    }

    private fun refreshModePanels() {
        val isAi = modeGroup.checkedRadioButtonId == modeAiId
        keywordPanel.visibility = if (isAi) View.GONE else View.VISIBLE
        aiPanel.visibility = if (isAi) View.VISIBLE else View.GONE
        if (isAi) refreshAiSourcePanels()
    }

    private fun refreshAiSourcePanels() {
        val ownKey = aiSourceGroup.checkedRadioButtonId != sourceRelayId
        ownKeyPanel.visibility = if (ownKey) View.VISIBLE else View.GONE
        relayPanel.visibility = if (ownKey) View.GONE else View.VISIBLE
    }

    // ------------------------------------------------------------------ 读写

    private fun loadIntoUi(config: EngineConfig) {
        masterSwitch.isChecked = config.enabled

        modeGroup.check(if (config.replyMode == ReplyMode.AI) modeAiId else modeKeywordId)
        aiSourceGroup.check(
            if (config.ai.source == AiSource.RELAY) sourceRelayId else sourceOwnKeyId
        )
        refreshModePanels()

        baseUrlField.setText(config.ai.baseUrl)
        apiKeyField.setText(config.ai.apiKey)
        modelField.setText(config.ai.model)

        // 之前选过的那家如果有注意事项，重新打开时也要看得到
        val preset = OpenAiCompatibleWriter.PRESETS.firstOrNull {
            it.baseUrl == config.ai.baseUrl && it.note.isNotBlank()
        }
        presetNote.text = preset?.note.orEmpty()
        presetNote.visibility = if (preset == null) View.GONE else View.VISIBLE
        relayUrlField.setText(config.ai.relayUrl)
        relayTokenField.setText(config.ai.relayToken)

        identityField.setText(config.persona.identity)
        toneField.setText(config.persona.tone)
        playbookField.setText(config.persona.playbook)
        maxCharsField.setText(config.persona.maxChars.toString())

        examplesContainer.removeAllViews()
        config.persona.examples.ifEmpty { listOf(AiExample("", "")) }
            .forEach { examplesContainer.addView(exampleRow(it)) }

        groupPolicyGroup.check(
            when (config.groupPolicy) {
                GroupPolicy.NEVER -> groupNeverId
                GroupPolicy.ONLY_AT_ME -> groupAtMeId
                GroupPolicy.ALWAYS -> groupAlwaysId
            }
        )
        fallbackField.setText(config.fallbackText)
        blockContactsField.setText(config.blockContacts.joinToString("，"))
        renderSeenContacts(config.allowContacts)

        rulesContainer.removeAllViews()
        val rules = config.rules.ifEmpty { listOf(Rule(name = "规则", replies = listOf(""))) }
        rules.forEach { rulesContainer.addView(ruleRow(it)) }
    }

    private fun saveFromUi() {
        val config = buildConfigFromUi()
        Storage.saveConfig(this, config)

        // 保存时就把「配了但填不全」说清楚，别等到真有人发消息才发现不回
        val problem = configProblem(config)
        if (problem == null) {
            Toast.makeText(this, "已保存", Toast.LENGTH_SHORT).show()
        } else {
            Toast.makeText(this, "已保存，但$problem", Toast.LENGTH_LONG).show()
        }
    }

    /** AI 模式下缺东西时的人话说明；没问题返回 null。 */
    private fun configProblem(config: EngineConfig): String? {
        if (config.replyMode != ReplyMode.AI) return null
        return when {
            config.ai.source == AiSource.RELAY && config.ai.relayUrl.isBlank() ->
                "还没填对方给的地址，现在不会回复"
            config.ai.source == AiSource.OWN_KEY && config.ai.apiKey.isBlank() ->
                "还没填 API Key，现在不会回复"
            config.ai.source == AiSource.OWN_KEY && config.ai.baseUrl.isBlank() ->
                "还没选接口，点一下上面的 DeepSeek 之类的按钮"
            config.ai.source == AiSource.OWN_KEY && !config.persona.isConfigured() ->
                "人设是空的，回出来会像客服，建议填一下"
            else -> null
        }
    }

    /** 把界面上当前填的内容组装成配置。保存和「试一试」共用，避免两边不一致。 */
    private fun buildConfigFromUi(): EngineConfig {
        val rules = ArrayList<Rule>()
        for (i in 0 until rulesContainer.childCount) {
            val row = rulesContainer.getChildAt(i) as? ViewGroup ?: continue
            val keywords = (row.findViewWithTag<EditText>(TAG_KEYWORDS))?.text?.toString().orEmpty()
            val reply = (row.findViewWithTag<EditText>(TAG_REPLY))?.text?.toString().orEmpty()
            val words = splitList(keywords)
            if (words.isEmpty() || reply.isBlank()) continue
            rules += Rule(
                name = words.first(),
                keywords = words,
                replies = listOf(reply.trim()),
            )
        }

        val examples = ArrayList<AiExample>()
        for (i in 0 until examplesContainer.childCount) {
            val row = examplesContainer.getChildAt(i) as? ViewGroup ?: continue
            val them = (row.findViewWithTag<EditText>(TAG_EX_THEM))?.text?.toString()?.trim().orEmpty()
            val me = (row.findViewWithTag<EditText>(TAG_EX_ME))?.text?.toString()?.trim().orEmpty()
            if (them.isBlank() || me.isBlank()) continue
            examples += AiExample(them, me)
        }

        val policy = when (groupPolicyGroup.checkedRadioButtonId) {
            groupAtMeId -> GroupPolicy.ONLY_AT_ME
            groupAlwaysId -> GroupPolicy.ALWAYS
            else -> GroupPolicy.NEVER
        }

        return Storage.loadConfig(this).copy(
            enabled = masterSwitch.isChecked,
            groupPolicy = policy,
            rules = rules,
            fallbackText = fallbackField.text.toString().trim(),
            blockContacts = splitList(blockContactsField.text.toString()),
            allowContacts = checkedSeenContacts() + splitList(allowContactsField.text.toString()),
            replyMode = if (modeGroup.checkedRadioButtonId == modeAiId)
                ReplyMode.AI else ReplyMode.KEYWORD,
            ai = AiConfig(
                source = if (aiSourceGroup.checkedRadioButtonId == sourceRelayId)
                    AiSource.RELAY else AiSource.OWN_KEY,
                baseUrl = baseUrlField.text.toString().trim(),
                apiKey = apiKeyField.text.toString().trim(),
                model = modelField.text.toString().trim(),
                relayUrl = relayUrlField.text.toString().trim(),
                relayToken = relayTokenField.text.toString().trim(),
            ),
            persona = PersonaConfig(
                identity = identityField.text.toString().trim(),
                tone = toneField.text.toString().trim(),
                playbook = playbookField.text.toString().trim(),
                maxChars = maxCharsField.text.toString().trim().toIntOrNull()?.coerceIn(10, 200) ?: 30,
                examples = examples,
            ),
        )
    }

    /**
     * 试一试：用一个全新的内存状态跑一次引擎。
     *
     * 用 InMemoryStateStore 而不是真实存储，所以既不会被冷却挡住
     * （否则试第二次就没反应了），也不会吃掉真实的每日额度。
     * 敏感词、群聊策略、黑名单照常生效——那些正是要看的东西。
     */
    private fun runPreview() {
        val text = testInput.text.toString().trim()
        if (text.isEmpty()) {
            showPreview("先在上面输入一句话", "#757575")
            return
        }

        // 忽略总开关和时段，其余全部照常
        val config = buildConfigFromUi().copy(
            enabled = true,
            activeFromMinute = -1,
            activeToMinute = -1,
        )
        configProblem(config)?.let {
            showPreview("⚠️ $it", "#EF6C00")
            return
        }

        val isGroup = testAsGroup.isChecked
        val message = Message(
            chatId = "preview",
            chatName = "测试联系人",
            text = text,
            isGroup = isGroup,
            mentionedMe = isGroup,
        )

        // AI 模式要走网络，绝不能在主线程上做
        if (config.replyMode == ReplyMode.AI) {
            showPreview("正在问 AI…", "#757575")
            Thread {
                val decision = ReplyEngine(
                    InMemoryStateStore(),
                    aiWriter = Storage.aiWriter(config),
                ).decide(config, message)
                runOnUiThread { renderDecision(decision) }
            }.start()
            return
        }

        renderDecision(ReplyEngine(InMemoryStateStore()).decide(config, message))
    }

    private fun renderDecision(decision: Decision) {
        if (decision.shouldReply) {
            showPreview(
                "✅ 会回复：\n${decision.text}\n\n（${decision.reason}，" +
                    "${decision.delayMillis / 1000} 秒后发出）",
                "#2E7D32",
            )
        } else {
            showPreview("⛔ 不会回复\n原因：${decision.reason}", "#D32F2F")
        }
    }

    private fun showPreview(text: String, color: String) {
        testResult.text = text
        testResult.setTextColor(Color.parseColor(color))
    }


    /**
     * 把「给你发过消息的人」列成勾选框。
     *
     * 第三方 App 读不到微信通讯录，那是微信的私有数据。但能拿到发过
     * 消息的人，而这恰好就够用——白名单本来就只该填聊得上的人。
     * 勾选比手打准得多：用户不用纠结填昵称还是备注，也不会打错字。
     */
    private fun renderSeenContacts(selected: List<String>) {
        seenContactsContainer.removeAllViews()
        val seen = Storage.loadSeenChats(this)
        val picked = selected.map { normalizeChatName(it) }.toSet()

        if (seen.isEmpty()) {
            seenContactsContainer.addView(hint(
                "还没人给你发过消息，所以这里是空的。\n" +
                    "等收到几条微信之后再回来，这里会列出他们，勾选就行。"
            ))
        }

        seen.forEach { name ->
            seenContactsContainer.addView(CheckBox(this).apply {
                text = name
                textSize = 16f
                tag = TAG_SEEN
                // 先设好状态再挂监听，否则这一行本身会触发一次「保存」
                isChecked = normalizeChatName(name) in picked
                setPadding(dp(8), dp(10), dp(8), dp(10))
                setOnCheckedChangeListener { _, _ -> saveWhitelistOnly() }
            })
        }

        // 勾选框覆盖不到的名字（手打进来的、或者对方后来改了备注），
        // 仍旧回填到输入框里，免得保存一次就丢了
        val seenNorm = seen.map { normalizeChatName(it) }.toSet()
        allowContactsField.setText(
            selected.filter { normalizeChatName(it) !in seenNorm }.joinToString("，")
        )
    }

    /**
     * 勾选框一勾上就立刻存，不等页面底部那个「保存设置」。
     *
     * 「保存设置」在页面最下面，勾选框在中间。用户勾完几个人，
     * 觉得事儿办完了就退出去——设置一条没存上，而且没有任何提示。
     * 白名单又恰恰是防封号最关键的一项，丢了后果最严重，
     * 所以这里单独即时落盘。
     */
    private fun saveWhitelistOnly() {
        val names = checkedSeenContacts() + splitList(allowContactsField.text.toString())
        Storage.saveConfig(this, Storage.loadConfig(this).copy(allowContacts = names))
    }

    private fun checkedSeenContacts(): List<String> {
        val out = ArrayList<String>()
        for (i in 0 until seenContactsContainer.childCount) {
            val box = seenContactsContainer.getChildAt(i) as? CheckBox ?: continue
            if (box.tag == TAG_SEEN && box.isChecked) out += box.text.toString()
        }
        return out
    }



    /**
     * 请求系统重新绑定通知监听服务。
     *
     * 覆盖安装 APK、或者手机重启之后，系统经常不会自动把已经授权的
     * 监听服务重新拉起来。表现是「权限明明是开着的，但一条消息都收不到」，
     * 而且完全没有任何提示——用户只能看到 App 毫无反应。
     *
     * requestRebind 是官方给的补救接口，省得让用户去系统设置里
     * 手动把开关关掉再打开。
     */
    private fun requestListenerRebind(quiet: Boolean = false) {
        if (!isNotificationAccessGranted()) {
            if (!quiet) {
                Toast.makeText(this, "还没授予通知使用权，先点上面那个按钮", Toast.LENGTH_LONG).show()
            }
            return
        }
        android.service.notification.NotificationListenerService.requestRebind(
            android.content.ComponentName(this, WeChatNotificationService::class.java)
        )
        if (!quiet) {
            Toast.makeText(this, "已请求重连，等几秒再看下面的记录", Toast.LENGTH_LONG).show()
        }
        // 绑定是异步的，过几秒再刷新才看得到结果
        eventsView.postDelayed({
            refreshPermissionStatus()
            refreshEvents()
        }, 3000)
    }

    /**
     * 把运行记录显示出来。
     *
     * 空记录本身就是最重要的一条信息：说明通知根本没进来，
     * 问题在授权或者省电策略上，而不是在回复逻辑上。
     */
    private fun refreshEvents() {
        val events = Storage.loadEvents(this)
        if (events.isEmpty()) {
            eventsView.text = if (isNotificationAccessGranted()) {
                "还没有任何记录。\n\n" +
                    "让人给你发条微信试试。如果发了还是空的，多半是：\n" +
                    "• 通知使用权被系统收回了 —— 去上面重新授权一次\n" +
                    "• 或者手机把这个 App 杀了 —— 把它加进省电白名单"
            } else {
                "还没授予通知使用权，程序看不到任何微信消息。\n" +
                    "点上面那个按钮先授权。"
            }
            eventsView.setTextColor(Color.parseColor("#D32F2F"))
            return
        }
        eventsView.text = events.joinToString("\n")
        eventsView.setTextColor(Color.parseColor("#455A64"))
    }

    /** 中英文逗号都当分隔符——用户不该被要求分清全角半角。 */
    private fun splitList(raw: String): List<String> =
        raw.split(",", "，", "、")
            .map { it.trim() }
            .filter { it.isNotEmpty() }

    // ------------------------------------------------------------------ 状态

    private fun refreshPermissionStatus() {
        val granted = isNotificationAccessGranted()
        val enabled = Storage.loadConfig(this).enabled

        // 授权 ≠ 服务活着。只查授权就说「正在工作中」，在监听已经死掉的
        // 情况下等于骗用户——他会以为程序在跑，实际一条消息都收不到。
        val connected = Storage.isListenerConnected(this)

        val (text, color) = when {
            !granted -> "⚠️ 还没授予通知使用权，现在不会自动回复" to Color.parseColor("#D32F2F")
            !connected ->
                "⚠️ 权限有了，但监听没连上，现在收不到消息 —— 点下面的「重连」" to
                    Color.parseColor("#EF6C00")
            !enabled -> "已授权。开关打开后开始工作。" to Color.parseColor("#757575")
            else -> "✅ 正在工作中" to Color.parseColor("#2E7D32")
        }
        permissionStatus.text = text
        permissionStatus.setTextColor(color)
    }

    private fun isNotificationAccessGranted(): Boolean {
        val flat = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")
        if (TextUtils.isEmpty(flat)) return false
        return flat.split(":").any { it.contains(packageName) }
    }

    // ------------------------------------------------------------------ 小工具

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun multiline(hintText: String, lines: Int) = EditText(this).apply {
        hint = hintText
        minLines = lines
        gravity = android.view.Gravity.TOP or android.view.Gravity.START
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
    }

    private fun labeled(label: String, field: View): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(0, dp(8), 0, 0)
        addView(TextView(this@MainActivity).apply {
            text = label
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            setPadding(dp(12), 0, dp(12), dp(2))
        })
        addView(field)
    }

    private fun title(text: String) = TextView(this).apply {
        this.text = text
        textSize = 24f
        setTypeface(null, Typeface.BOLD)
        setPadding(dp(12), 0, dp(12), dp(16))
    }

    private fun section(text: String) = TextView(this).apply {
        this.text = text
        textSize = 17f
        setTypeface(null, Typeface.BOLD)
        setPadding(dp(12), dp(8), dp(12), dp(4))
    }

    private fun hint(text: String) = TextView(this).apply {
        this.text = text
        textSize = 13f
        setTextColor(Color.parseColor("#757575"))
        setPadding(dp(12), dp(4), dp(12), dp(12))
    }

    private fun divider() = View(this).apply {
        setBackgroundColor(Color.parseColor("#E0E0E0"))
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(1)
        ).apply { setMargins(0, dp(16), 0, dp(16)) }
    }

    companion object {
        private const val REQUEST_WIZARD = 1
        private const val TAG_KEYWORDS = "kw"
        private const val TAG_REPLY = "rp"
        private const val TAG_EX_THEM = "ex_them"
        private const val TAG_EX_ME = "ex_me"
        private const val TAG_SEEN = "seen"
    }
}
