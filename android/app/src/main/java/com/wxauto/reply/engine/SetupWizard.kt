package com.wxauto.reply.engine

/**
 * 开场问答 —— core/wizard.py 的 Kotlin 版。
 *
 * 人设是这套系统里最难写的东西。让一个不写代码的人面对
 * 「我是谁 / 我说话的方式 / 应对攻略」三个空框，多半就放弃了，
 * 或者随手填几个「友好」「专业」这种空词——那生成出来必然是客服腔。
 *
 * 但同样这个人，你问他「有人约你吃饭你一般怎么回」，他张口就能答。
 *
 * 所以这里把「写人设」翻译成十道具体的题。答案不是拿去喂模型润色的
 * （那样每次跑出来的都不一样，也没法测），而是按确定的规则拼装成
 * 人设、关键词规则和兜底话术——**问题本身就是人设**。
 *
 * 这一层刻意不依赖任何 Android API，方便单独做单元测试，
 * 也方便和 Python 版对照。两边的文案必须保持一致。
 */

enum class QuestionKind { SINGLE, MULTI, TEXT }

data class WizardOption(val id: String, val label: String)

data class WizardQuestion(
    val id: String,
    val prompt: String,
    val kind: QuestionKind,
    val options: List<WizardOption> = emptyList(),
    val hint: String = "",
    val optional: Boolean = false,
    val placeholder: String = "",
)

/** 问答生成的整套回复内容。 */
data class WizardResult(
    val persona: PersonaConfig,
    val rules: List<Rule>,
    val fallbackText: String,
    /**
     * 只对这些人自动回复。空 = 对所有人。
     *
     * 这是所有防风控手段里最有效的一条：真正会出事的路径是被举报，
     * 而熟人不会举报你。技术上的限流再怎么做，也不如「只对不会举报你的人开」。
     */
    val allowContacts: List<String> = emptyList(),
    /** 自动回复时段，距零点的分钟数。(-1, -1) = 全天。 */
    val activeHours: Pair<Int, Int> = 9 * 60 to 23 * 60,
)

object SetupWizard {

    val QUESTIONS: List<WizardQuestion> = listOf(
        WizardQuestion(
            id = "who",
            prompt = "平时主要是谁给你发微信？",
            kind = QuestionKind.MULTI,
            hint = "可以多选",
            options = listOf(
                WizardOption("work", "同事、工作上的人"),
                WizardOption("client", "客户、甲方、合作方"),
                WizardOption("friend", "朋友"),
                WizardOption("family", "家里人"),
            ),
        ),
        WizardQuestion(
            id = "busy",
            prompt = "你一般为什么没马上回消息？",
            kind = QuestionKind.MULTI,
            hint = "可以多选",
            options = listOf(
                WizardOption("work", "在上班或上课，手机不方便看"),
                WizardOption("hands", "手上忙着别的事，腾不开"),
                WizardOption("out", "经常在外面、在路上"),
                WizardOption("later", "看到了，但不太想马上回"),
                WizardOption("unsure", "有些消息不知道怎么回，想想再说"),
            ),
        ),
        WizardQuestion(
            id = "style",
            prompt = "别人发「在吗」，下面哪句最像你会回的？",
            kind = QuestionKind.SINGLE,
            hint = "选不出来就挑个最接近的，下一题可以自己写",
            options = listOf(
                WizardOption("casual", "在，怎么了"),
                WizardOption("polite", "在的，您说"),
                WizardOption("warm", "在呢！咋啦"),
                WizardOption("brief", "在"),
            ),
        ),
        WizardQuestion(
            id = "greeting",
            prompt = "上面那句不太像的话，你自己会怎么回「在吗」？",
            kind = QuestionKind.TEXT,
            hint = "像的话直接跳过。写了的话以你写的为准",
            optional = true,
        ),
        WizardQuestion(
            id = "appointment",
            prompt = "别人说「明天下午有空不，一起吃个饭」，你想怎么处理？",
            kind = QuestionKind.SINGLE,
            hint = "下面只是示意，实际发出去的话会用你自己的语气",
            options = listOf(
                WizardOption("hold", "「我看下日程，晚点回你」—— 先拖住"),
                WizardOption("refuse", "「最近有点排不开，下次吧」—— 直接推掉"),
                WizardOption("ask", "「什么事啊，你先说说」—— 先问清楚"),
            ),
        ),
        WizardQuestion(
            id = "progress",
            prompt = "别人催「那个东西弄得怎么样了」呢？",
            kind = QuestionKind.SINGLE,
            options = listOf(
                WizardOption("rough", "「在弄了，这两天给你结果」—— 给个大概"),
                WizardOption("working", "「在弄着呢」—— 不给时间"),
                WizardOption("person", "「这个我等下本人回你」—— 交给自己"),
            ),
        ),
        WizardQuestion(
            id = "stranger",
            prompt = "别人发「加个群呗，有福利」这种呢？",
            kind = QuestionKind.SINGLE,
            options = listOf(
                WizardOption("polite", "「这个我不太需要，谢谢」—— 客气拒绝"),
                WizardOption("blunt", "「不需要」—— 干脆"),
                WizardOption("later", "「我晚点看看」—— 不表态"),
            ),
        ),
        WizardQuestion(
            id = "emoji",
            prompt = "别人发「哈哈哈哈太逗了」，你回哪个？",
            kind = QuestionKind.SINGLE,
            hint = "看的是符号，不是内容",
            options = listOf(
                WizardOption("none", "确实"),
                WizardOption("emoji", "确实 😂"),
                WizardOption("mark", "确实！"),
                WizardOption("both", "确实！😂"),
            ),
        ),
        WizardQuestion(
            id = "night",
            prompt = "晚上 11 点有人给你发消息，你希望它怎么办？",
            kind = QuestionKind.SINGLE,
            options = listOf(
                WizardOption("day", "别回，等我第二天自己看"),
                WizardOption("always", "照回，我本来也常半夜回消息"),
                WizardOption("work", "只在白天上班时间回（9 点到 6 点）"),
            ),
        ),
        WizardQuestion(
            id = "never",
            prompt = "有什么是绝对不能替你答应的？",
            kind = QuestionKind.MULTI,
            hint = "可以多选，也可以一个都不选",
            options = listOf(
                WizardOption("money", "不谈钱、不谈价格"),
                WizardOption("gossip", "不评价别人、不聊八卦"),
                WizardOption("favor", "不答应帮忙投票、点赞、转发"),
                WizardOption("meet", "不答应任何见面、吃饭的邀约"),
                WizardOption("work", "不对工作上的具体安排表态"),
            ),
        ),
        WizardQuestion(
            id = "only_for",
            prompt = "先只对哪几个人开？",
            kind = QuestionKind.TEXT,
            hint = "强烈建议先填三五个熟人。留空 = 对所有人开，风险高很多",
            optional = true,
            placeholder = "答完在设置页里可以直接勾选，不用在这里打字",
        ),
    )

    // ------------------------------------------------------------ 语气表
    //
    // 四种说话方式 × 四类常见情况。这十六句话是整套东西的地基：
    // 模型模仿的是这些句子，关键词模式直接发的也是这些句子。
    // 一律用「人真的会打出来的字」，不要用书面语。

    private val VOICE = mapOf(
        "casual" to mapOf(
            "tone" to "句子短，一般就一两句话。口语，该省的字就省。" +
                "不用敬语，不说「您」。熟人之间那种随便的语气。",
            "greeting" to "在，怎么了",
            "chat" to "确实",
        ),
        "polite" to mapOf(
            "tone" to "说话客气，称呼对方用「您」，但不啰嗦。不用网络用语和缩写。",
            "greeting" to "在的，您说",
            "chat" to "是挺有意思的",
        ),
        "warm" to mapOf(
            "tone" to "语气热情，愿意多聊两句，可以开点玩笑。别显得敷衍。",
            "greeting" to "在呢！咋啦",
            "chat" to "哈哈是吧，我也这么觉得",
        ),
        "brief" to mapOf(
            "tone" to "能少说就少说，经常一两个字就完事。不寒暄，不解释。",
            "greeting" to "在",
            "chat" to "嗯",
        ),
    )

    private val APPOINTMENT = mapOf(
        "hold" to mapOf(
            "line" to "有人约时间、约见面：说要确认一下日程，等我本人回，" +
                "不要当场答应任何时间点。",
            "casual" to "我看下日程，晚点回你",
            "polite" to "我看一下安排，稍后回复您",
            "warm" to "我瞅一眼日程啊，一会儿回你",
            "brief" to "我看下日程",
        ),
        "refuse" to mapOf(
            "line" to "有人约时间、约见面：说最近排不开，客气地推掉，不要答应。",
            "casual" to "最近有点排不开，下次吧",
            "polite" to "最近安排比较满，实在抱歉",
            "warm" to "哎最近真排不开，下回一定",
            "brief" to "最近排不开",
        ),
        "ask" to mapOf(
            "line" to "有人约时间、约见面：先问清楚是什么事、大概什么时候，" +
                "不要当场答应。",
            "casual" to "什么事啊，你先说说",
            "polite" to "方便先说下是什么事吗",
            "warm" to "啥事呀，你先说说看",
            "brief" to "什么事",
        ),
    )

    private val PROGRESS = mapOf(
        "rough" to mapOf(
            "line" to "有人问进度、催什么时候好：给个模糊的时间感觉" +
                "（今天之内、这两天），绝对不给具体日期，也不打包票。",
            "casual" to "在弄了，这两天给你结果",
            "polite" to "正在处理，这两天给您答复",
            "warm" to "在弄啦，这两天就给你信儿",
            "brief" to "在弄，这两天",
        ),
        "working" to mapOf(
            "line" to "有人问进度、催什么时候好：说在弄了，不要给任何时间点。",
            "casual" to "在弄着呢",
            "polite" to "正在处理中",
            "warm" to "在弄啦，别急",
            "brief" to "在弄",
        ),
        "person" to mapOf(
            "line" to "有人问进度、催什么时候好：说等我本人回你，不要自己答。",
            "casual" to "这个我等下本人回你",
            "polite" to "这个稍后我本人回复您",
            "warm" to "这个我等会儿亲自回你哈",
            "brief" to "等下回你",
        ),
    )

    private val STRANGER = mapOf(
        "polite" to mapOf(
            "line" to "推销、拉群、发广告、求点赞投票：客气但明确地拒绝，一句话结束。",
            "casual" to "这个我不太需要，谢谢",
            "polite" to "谢谢，这个我暂时不需要",
            "warm" to "谢谢啦，这个我先不用",
            "brief" to "不需要，谢谢",
        ),
        "blunt" to mapOf(
            "line" to "推销、拉群、发广告、求点赞投票：直接说不需要，一句话，不解释。",
            "casual" to "不需要",
            "polite" to "不需要，谢谢",
            "warm" to "这个就不用啦",
            "brief" to "不需要",
        ),
        "later" to mapOf(
            "line" to "推销、拉群、发广告、求点赞投票：说我晚点看，不表任何态、" +
                "不答应任何事。",
            "casual" to "我晚点看看",
            "polite" to "我稍后看一下",
            "warm" to "行我晚点瞅瞅",
            "brief" to "晚点看",
        ),
    )

    private val WHO_LABEL = mapOf(
        "work" to "同事和工作上的人",
        "client" to "客户、甲方这类合作方",
        "friend" to "朋友",
        "family" to "家里人",
    )

    private val BUSY_LINE = mapOf(
        "work" to "白天要上班，手机不太方便看",
        "hands" to "手上常忙着别的事，腾不开",
        "out" to "经常在外面、在路上",
        "later" to "消息看得到，但常常不太想马上回",
        "unsure" to "有些消息我得想想怎么回，就先放着了",
    )

    // 兜底文案只用一条理由，多选时取第一条
    private val BUSY_ORDER = listOf("work", "hands", "out", "later", "unsure")

    // 回复长度上限直接从说话风格推断，不再单独问一题：
    // 选了「在」的人不会突然写三句话，问了也是多余的一道题。
    // 勾选的边界 → 写进提示词的硬性要求。
    // 原来这题是个空框，让人对着它想「有什么绝对不能答应」——
    // 那是最难答的一种题，多数人会直接跳过，于是这一段永远是空的。
    private val NEVER_LINE = linkedMapOf(
        "money" to "不谈钱和价格，一律说等我本人聊",
        "gossip" to "不评价任何第三方的人和公司",
        "favor" to "不答应帮忙投票、点赞、转发这类请求",
        "meet" to "不答应任何见面、吃饭的邀约",
        "work" to "不对工作上的具体安排表态，说等我本人回",
    )

    // 几点回，单位是距零点的分钟数。-1 表示全天。
    // 深夜自动回复本身就可疑，默认避开。
    private val ACTIVE_HOURS = mapOf(
        "day" to (9 * 60 to 23 * 60),
        "always" to (-1 to -1),
        "work" to (9 * 60 to 18 * 60),
    )

    private val MAX_CHARS_BY_STYLE =
        mapOf("brief" to 20, "casual" to 30, "polite" to 40, "warm" to 45)

    // 表情和感叹号是两回事：有人爱发表情但从不用感叹号。
    // 之前把它们混成一个「用不用」的程度问题，是设计错误。
    private val EMOJI_LINE = mapOf(
        "none" to "不用感叹号，也不发表情。",
        "emoji" to "会发表情，但不用感叹号。",
        "mark" to "会用感叹号，但基本不发表情。",
        "both" to "感叹号和表情都会用，但别过头。",
    )

    // 旧版本存下来的答案，映射到新选项上，免得重装一次人设就变了
    private val EMOJI_LEGACY = mapOf("some" to "emoji", "lots" to "both")

    private fun usesExclaim(emoji: String) = emoji == "mark" || emoji == "both"
    private fun usesEmoji(emoji: String) = emoji == "emoji" || emoji == "both"

    // ------------------------------------------------------------ 拼装

    /**
     * 答案 → 整套回复内容。纯函数，没有随机、没有网络，因此可测。
     *
     * answers 里每个问题都存成字符串列表：单选和填空是单元素，多选是多元素。
     * 认不出来的答案一律退回默认值而不是抛异常——旧版本存的答案、
     * 被改坏的配置，都不该让 App 崩在启动页上。
     */
    fun build(answers: Map<String, List<String>>): WizardResult {
        fun one(id: String, fallback: String): String =
            answers[id]?.firstOrNull()?.takeIf { it.isNotBlank() } ?: fallback

        val style = one("style", "casual").takeIf { VOICE.containsKey(it) } ?: "casual"
        val voice = VOICE.getValue(style)
        // busy 是多选：「在上班」和「不知道怎么回」可以同时成立
        val busyIds = (answers["busy"] ?: emptyList())
            .filter { BUSY_LINE.containsKey(it) }
            .ifEmpty { listOf("hands") }

        val emojiRaw = one("emoji", "none")
        val emoji = (EMOJI_LEGACY[emojiRaw] ?: emojiRaw)
            .takeIf { EMOJI_LINE.containsKey(it) } ?: "none"
        val appointment = APPOINTMENT[one("appointment", "hold")] ?: APPOINTMENT.getValue("hold")
        val progress = PROGRESS[one("progress", "rough")] ?: PROGRESS.getValue("rough")
        val stranger = STRANGER[one("stranger", "polite")] ?: STRANGER.getValue("polite")

        fun say(table: Map<String, String>): String =
            tune(table[style] ?: table.getValue("casual"), emoji)

        // ---- 我是谁 ----
        val labels = (answers["who"] ?: emptyList()).mapNotNull { WHO_LABEL[it] }
        val identity = buildString {
            if (labels.isNotEmpty()) {
                append("平时给我发消息的主要是${labels.joinToString("、")}。")
            }
            append("我" + BUSY_ORDER.filter { it in busyIds }
                .joinToString("；") { BUSY_LINE.getValue(it) } + "。")
            append("微信经常隔一会儿才翻一次，看到会回。")
        }

        // ---- 我说话的方式 ----
        val tone = buildString {
            append(voice.getValue("tone"))
            append(EMOJI_LINE[emoji] ?: EMOJI_LINE.getValue("none"))
            when (style) {
                "brief" -> append("一句话能说完就别说两句。")
                "polite", "warm" -> append("最多两三句，别写成段落。")
            }
        }

        // ---- 应对攻略 ----
        // 首尾两条是所有人都要有的基线，中间三条按回答替换。
        // 最后一条（看不懂就交给本人）是最重要的兜底，必须永远在。
        val playbook = listOf(
            "有人问在不在、忙不忙：说在，但说明手上有事，等下回。",
            appointment.getValue("line"),
            progress.getValue("line"),
            stranger.getValue("line"),
            "纯闲聊、发表情、分享链接：随便接一两句，别太热情也别冷场。",
            "看不懂对方在说什么，或者事情比较重要：直接说等我本人回你，" +
                "不要硬猜着接话。",
        ).toMutableList().apply {
            if ("client" in (answers["who"] ?: emptyList())) {
                // 选了客户、甲方，说明回错的代价高，攻略要更保守
                add("涉及工作、报价、交付时间的事：一律不表态，说等我本人回。")
            }
            if ("unsure" in busyIds) {
                // 用户自己说了「有些消息不知道怎么回」——那就把模型也调保守些，
                // 拿不准时先拖住，别替他现编一个答案
                add(
                    "凡是拿不准该怎么回的：宁可先拖着，说等我本人回你，" +
                        "绝对不要自己编一个答案。"
                )
            }
        }.joinToString("\n")

        val neverIds = answers["never"] ?: emptyList()
        val boundaries = NEVER_LINE.filterKeys { it in neverIds }.values.toList()

        // ---- 示范语气 ----
        // 用户自己写的那句优先级最高：那是他真实的声音，
        // 比我们按风格挑的任何一句都准。
        val greeting = answers["greeting"]?.firstOrNull()?.trim()?.takeIf { it.isNotEmpty() }
            ?: tune(voice.getValue("greeting"), emoji)

        val examples = listOf(
            AiExample("在吗", greeting),
            AiExample("明天下午有空不，一起吃个饭", say(appointment)),
            AiExample("那个东西弄得怎么样了", say(progress)),
            // 爱发表情的人，示范里也得有表情——不然示范和语气说明打架，
            // 模型会照着示范走
            AiExample(
                "哈哈哈哈太逗了",
                tune(voice.getValue("chat"), emoji) + if (usesEmoji(emoji)) "😂" else "",
            ),
        )

        // ---- 关键词规则（给不用 AI 的人）----
        // 同一批答案同时生成两套东西：选关键词模式的人也能直接用，
        // 不用再自己想文案。
        val rules = listOf(
            Rule(
                name = "问在不在",
                keywords = listOf("在吗", "在么", "在不在", "忙吗", "忙不忙"),
                replies = listOf(greeting),
            ),
            Rule(
                name = "约时间",
                keywords = listOf("有空", "有时间", "见个面", "见面", "吃饭", "约个"),
                replies = listOf(say(appointment)),
            ),
            Rule(
                name = "问进度",
                keywords = listOf("什么时候", "进度", "好了吗", "做完", "弄完", "怎么样了"),
                replies = listOf(say(progress)),
            ),
            Rule(
                name = "推销拉群",
                keywords = listOf("了解一下", "推广", "加个群", "投票", "点赞", "帮忙转发"),
                replies = listOf(say(stranger)),
            ),
        )

        val busyText = "我" + BUSY_LINE.getValue(BUSY_ORDER.first { it in busyIds })
        val fallbackText = when (style) {
            "polite" -> "$busyText，看到会尽快回复您"
            "brief" -> "$busyText，晚点回"
            else -> "$busyText，看到会尽快回你"
        }

        return WizardResult(
            persona = PersonaConfig(
                identity = identity,
                tone = tone,
                playbook = playbook,
                boundaries = boundaries,
                maxChars = MAX_CHARS_BY_STYLE[style] ?: 30,
                examples = examples,
            ),
            rules = rules,
            fallbackText = fallbackText,
            allowContacts = splitList(answers["only_for"]?.firstOrNull().orEmpty()),
            activeHours = ACTIVE_HOURS[one("night", "day")] ?: ACTIVE_HOURS.getValue("day"),
        )
    }

    /** 把问答结果套进现有配置，其余设置（开关、限流、黑名单）一概不动。 */
    fun applyTo(config: EngineConfig, result: WizardResult): EngineConfig = config.copy(
        persona = result.persona,
        rules = result.rules,
        fallbackText = result.fallbackText,
        allowContacts = result.allowContacts,
        activeFromMinute = result.activeHours.first,
        activeToMinute = result.activeHours.second,
    )

    /**
     * 选了「基本不用感叹号」就别在示范里塞感叹号。
     *
     * 示范和语气说明自相矛盾时，模型会照着示范走——示范的分量更重。
     */
    private fun tune(text: String, emoji: String): String =
        if (usesExclaim(emoji)) text else text.replace("！", "").replace("!", "")

    /** 中英文逗号、顿号、换行都当分隔符——用户不该被要求分清全角半角。 */
    private fun splitList(raw: String): List<String> =
        raw.split("，", ",", "、", "\n")
            .map { it.trim() }
            .filter { it.isNotEmpty() }
}
