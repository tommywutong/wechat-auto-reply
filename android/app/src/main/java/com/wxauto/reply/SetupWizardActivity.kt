package com.wxauto.reply

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.TextView
import com.wxauto.reply.engine.QuestionKind
import com.wxauto.reply.engine.SetupWizard
import com.wxauto.reply.engine.Storage
import com.wxauto.reply.engine.WizardQuestion
import com.wxauto.reply.engine.WizardResult

/**
 * 开场问答。装完第一次打开会自动进这里。
 *
 * 一屏一题，选完就跳下一题——十道题里八道是单选，全程不用打字。
 * 最后一屏先把生成的话摆出来给他看，确认了才写进配置。
 *
 * 为什么不做成设置页里的一堆输入框：那样等于让用户自己写人设，
 * 而「面对空框不知道填什么」正是这件事最容易劝退人的地方。
 */
class SetupWizardActivity : Activity() {

    private val answers = HashMap<String, MutableList<String>>()
    private var index = 0

    private lateinit var container: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 之前答过就带出来，改一两题不用从头再来
        Storage.loadWizardAnswers(this).forEach { (k, v) -> answers[k] = v.toMutableList() }

        container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(32), dp(24), dp(32))
        }
        setContentView(ScrollView(this).apply {
            addView(container, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        })

        render()
    }

    override fun onBackPressed() {
        // 返回键当「上一题」用；在第一题上才真的退出
        if (index > 0) {
            index--
            render()
        } else {
            super.onBackPressed()
        }
    }

    // ------------------------------------------------------------------ 渲染

    private fun render() {
        container.removeAllViews()
        if (index >= SetupWizard.QUESTIONS.size) {
            renderSummary()
        } else {
            renderQuestion(SetupWizard.QUESTIONS[index])
        }
    }

    private fun renderQuestion(question: WizardQuestion) {
        val total = SetupWizard.QUESTIONS.size
        container.addView(TextView(this).apply {
            text = "第 ${index + 1} 题 / 共 $total 题"
            textSize = 13f
            setTextColor(Color.parseColor("#9E9E9E"))
            setPadding(0, 0, 0, dp(8))
        })

        container.addView(TextView(this).apply {
            text = question.prompt
            textSize = 22f
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, dp(4))
        })

        if (question.hint.isNotBlank()) {
            container.addView(TextView(this).apply {
                text = question.hint
                textSize = 14f
                setTextColor(Color.parseColor("#757575"))
                setPadding(0, 0, 0, dp(16))
            })
        } else {
            container.addView(spacer(dp(16)))
        }

        when (question.kind) {
            QuestionKind.SINGLE -> renderSingle(question)
            QuestionKind.MULTI -> renderMulti(question)
            QuestionKind.TEXT -> renderText(question)
        }

        if (index > 0) {
            container.addView(spacer(dp(16)))
            container.addView(Button(this).apply {
                text = "← 上一题"
                setOnClickListener { index--; render() }
            })
        }
    }

    private fun renderSingle(question: WizardQuestion) {
        val current = answers[question.id]?.firstOrNull()
        val group = RadioGroup(this).apply { orientation = RadioGroup.VERTICAL }

        question.options.forEachIndexed { position, option ->
            group.addView(RadioButton(this).apply {
                id = View.generateViewId()
                text = option.label
                textSize = 17f
                setPadding(dp(8), dp(14), dp(8), dp(14))
                isChecked = option.id == current
                setOnClickListener {
                    answers[question.id] = mutableListOf(option.id)
                    // 选完直接进下一题：十道题里八道是单选，
                    // 每题再点一次「下一步」是纯粹的多余动作
                    index++
                    render()
                }
            })
            if (position < question.options.size - 1) group.addView(thinDivider())
        }
        container.addView(group)
    }

    private fun renderMulti(question: WizardQuestion) {
        val chosen = answers.getOrPut(question.id) { mutableListOf() }

        question.options.forEach { option ->
            container.addView(CheckBox(this).apply {
                text = option.label
                textSize = 17f
                setPadding(dp(8), dp(14), dp(8), dp(14))
                isChecked = option.id in chosen
                setOnCheckedChangeListener { _, checked ->
                    if (checked) {
                        if (option.id !in chosen) chosen += option.id
                    } else {
                        chosen -= option.id
                    }
                }
            })
        }

        container.addView(spacer(dp(16)))
        container.addView(primaryButton("下一题 →") { index++; render() })
    }

    private fun renderText(question: WizardQuestion) {
        if (question.placeholder.isNotBlank()) {
            container.addView(TextView(this).apply {
                text = question.placeholder
                textSize = 13f
                setTextColor(Color.parseColor("#9E9E9E"))
                setPadding(0, 0, 0, dp(8))
            })
        }

        val field = EditText(this).apply {
            setText(answers[question.id]?.firstOrNull().orEmpty())
            textSize = 17f
            minLines = 2
            gravity = Gravity.TOP or Gravity.START
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        }
        container.addView(field)

        container.addView(spacer(dp(16)))
        container.addView(primaryButton("下一题 →") {
            answers[question.id] = mutableListOf(field.text.toString().trim())
            index++
            render()
        })

        if (question.optional) {
            container.addView(Button(this).apply {
                text = "这题跳过"
                setOnClickListener {
                    answers[question.id] = mutableListOf("")
                    index++
                    render()
                }
            })
        }
    }

    // ------------------------------------------------------------------ 结果

    private fun renderSummary() {
        val result = SetupWizard.build(answers)

        container.addView(TextView(this).apply {
            text = "根据你的回答，生成了这些"
            textSize = 22f
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, dp(16))
        })

        line("别人说「在吗」", result.persona.examples[0].me)
        line("别人约你吃饭", result.persona.examples[1].me)
        line("别人问事情办得怎样", result.persona.examples[2].me)
        line("别人推销、拉群", result.rules[3].replies.first())
        line("其他都没匹配上", result.fallbackText)

        container.addView(spacer(dp(16)))

        container.addView(TextView(this).apply {
            text = "回复长度上限：${result.persona.maxChars} 字"
            textSize = 14f
            setTextColor(Color.parseColor("#757575"))
        })
        if (result.persona.boundaries.isNotEmpty()) {
            container.addView(TextView(this).apply {
                text = "绝对不答应：${result.persona.boundaries.joinToString("、")}"
                textSize = 14f
                setTextColor(Color.parseColor("#757575"))
            })
        }

        container.addView(spacer(dp(16)))

        // 单独强调这一条：它比其他所有限流加起来都管用
        container.addView(TextView(this).apply {
            if (result.allowContacts.isEmpty()) {
                text = "⚠️ 会对所有人自动回复。\n\n" +
                    "真正可能导致封号的是「被人举报」，而熟人不会举报你。" +
                    "建议点下面「重新答一遍」，在最后一题填三五个熟人，先跑几天。"
                setTextColor(Color.parseColor("#EF6C00"))
            } else {
                text = "✅ 只对这几个人开：${result.allowContacts.joinToString("、")}\n" +
                    "其他所有人一律不自动回复。"
                setTextColor(Color.parseColor("#2E7D32"))
            }
            textSize = 14f
            setPadding(dp(4), dp(8), dp(4), dp(8))
        })

        container.addView(spacer(dp(20)))

        container.addView(TextView(this).apply {
            text = "开了 AI 模式的话，上面这几句是「示范」——" +
                "AI 会照着这个语气自己判断该说什么，不是只会回这几句。\n\n" +
                "用关键词模式的话，收到对应的词就直接发上面这几句。"
            textSize = 14f
            setTextColor(Color.parseColor("#757575"))
            setPadding(0, 0, 0, dp(20))
        })

        container.addView(primaryButton("就用这套") { save(result) })

        container.addView(Button(this).apply {
            text = "重新答一遍"
            setOnClickListener { index = 0; render() }
        })

        container.addView(TextView(this).apply {
            text = "存下来之后，在设置页里还能一句一句地改。"
            textSize = 13f
            setTextColor(Color.parseColor("#9E9E9E"))
            setPadding(0, dp(12), 0, 0)
        })
    }

    private fun save(result: WizardResult) {
        // 只覆盖人设、规则、兜底这三样；总开关和限流这些一概不动，
        // 免得重答一遍问答把用户之前的设置冲掉
        Storage.saveConfig(this, SetupWizard.applyTo(Storage.loadConfig(this), result))
        Storage.saveWizardAnswers(this, answers)
        setResult(RESULT_OK)
        finish()
    }

    // ------------------------------------------------------------------ 小工具

    private fun line(label: String, value: String) {
        container.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(8), 0, dp(8))
            addView(TextView(this@SetupWizardActivity).apply {
                text = label
                textSize = 13f
                setTextColor(Color.parseColor("#9E9E9E"))
            })
            addView(TextView(this@SetupWizardActivity).apply {
                text = value
                textSize = 17f
                setTextColor(Color.parseColor("#2E7D32"))
            })
        })
    }

    private fun primaryButton(label: String, onClick: () -> Unit) = Button(this).apply {
        text = label
        textSize = 17f
        setPadding(dp(8), dp(16), dp(8), dp(16))
        setOnClickListener { onClick() }
    }

    private fun spacer(height: Int) = View(this).apply {
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, height)
    }

    private fun thinDivider() = View(this).apply {
        setBackgroundColor(Color.parseColor("#EEEEEE"))
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1))
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
