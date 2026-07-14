from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import persona_tool  # noqa: E402


TOKEN_RE = re.compile(r"\[待填写[^\]]*\]")
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".txt", ".json"}


def write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def card_text(
    index: int,
    persona_type: str,
    source_id: str,
    scene_count: int,
    signature_count: int,
    context_type: str = "对话场景",
    medium: str = "视听",
) -> str:
    card_id = f"TESTROLE-{index:04d}"
    task_states = ("start", "progress", "waiting", "failed", "risk", "complete", "blocked", "issue")
    user_states = ("normal", "tired", "upset", "excited")
    emotions = ("cheerful", "caring", "serious", "alert", "calm", "confident", "apologetic", "teasing")
    intents = ("encourage", "report", "warn", "comfort", "explain", "apologize", "clarify", "celebrate")
    task_state = task_states[(index - 1) % len(task_states)]
    risk = "high" if index % 10 == 0 else "low"
    existing = persona_type in {"existing-character", "real-person-simulation"}
    source_type = (
        "本人公开表达" if persona_type == "real-person-simulation"
        else ("原作明确" if existing else "用户补充")
    )
    context_card_types = {
        "内心独白": "原文独白", "访谈回答": "原文采访回答", "演讲发言": "原文发言",
        "博客文章": "原文文章", "社交媒体": "原文帖子", "书信": "原文书信",
    }
    card_type = context_card_types.get(context_type, "原文对白") if existing else "原创规范对白"
    original_quality = (
        "原创确认" if not existing else ("原始版式核验" if medium == "文字" else ("原语言文本核验" if medium == "公开表达" else "原声核验"))
    )
    scene_number = ((index - 1) % max(scene_count, 1)) + 1
    recognition = "核心" if index <= signature_count else "补充"
    annotation_styles = ("追问", "转折", "邀请", "拒绝", "缓和", "确认", "自修正", "短促收束")
    annotation_style = annotation_styles[(index - 1) % len(annotation_styles)]
    positions = ("发起", "接话", "追问", "打断", "跟进", "收束", "自言自语", "接话后转折")
    initiatives = ("主动发起", "回应", "跟进", "打断", "收束", "自我修正", "回应后接手", "主动回访")
    speech_act = intents[(index - 1) % 8]
    speech_act_tags = f"{speech_act}/greet" if index == 1 else speech_act
    emotion = emotions[(index - 1) % 8]
    if context_type in {"演讲发言", "博客文章", "社交媒体", "书信"}:
        completeness = "语境充分"
        previous_text = "不适用"
        trigger_text = f"{annotation_style}公开主题 {index}"
        next_text = "不适用"
        target = "公众或读者"
    elif context_type in {"叙事场景", "内心独白"}:
        completeness = "语境充分"
        previous_text = f"{annotation_style}相邻叙事 {index}"
        trigger_text = f"{annotation_style}章节事件 {index}"
        next_text = f"{annotation_style}后续叙事 {index}"
        target = "自己"
    else:
        completeness = "完整"
        previous_text = f"{annotation_style}前一句测试原文 {index}"
        trigger_text = f"{annotation_style}触发话语 {index}"
        next_text = f"{annotation_style}后一句测试原文 {index}"
        target = "熟悉的同伴"
    return f"""## {card_id}

- 原作检索标签：speech_act={speech_act_tags}; trigger={task_state}; interaction={speech_act_tags}; position=reply; relation=familiar; emotion={emotion}; initiative=response
- 标签依据：speech_act=原文可见; trigger=上下文可见; interaction=上下文可见; position=上下文可见; relation=上下文可见; emotion=原文可见; initiative=上下文可见
- 卡片类型：{card_type}
- 原文：{'原作逐字原句' if existing else '原创规范原句'} {index}
- 原文语言：zh-CN
- 原文质量：{original_quality}
- 中文参考译文：不适用
- 说话人：测试角色
- 来源类型：{source_type}
- 来源位置：{source_id}，测试定位 {index}
- 作品定位：测试作品第 {scene_number} 场，位置 {index}
- 语境类型：{context_type if existing else '原创设定'}
- 场景编号：SCENE-{scene_number:04d}
- 场景完整度：{completeness if existing else '原创设定'}
- 前置原文：{previous_text}
- 触发话语：{trigger_text}
- 后续原文：{next_text}
- 对话对象：{target}
- 关系距离：familiar
- 交流目的：{intents[(index - 1) % 8]}
- 互动功能：{intents[(index - 1) % 8]}-{index}
- 角色即时反应：{annotation_style}后立即回应当前触发 {index}
- 互动位置：{positions[(index - 1) % len(positions)]}
- 主动性：{initiatives[(index - 1) % len(initiatives)]}
- 主要情绪：{emotions[(index - 1) % 8]}
- 情绪强度：2
- 情绪转折：{annotation_style}情绪变化 {index}
- 非语言反应：{annotation_style}动作观察 {index}
- 画面锚点：{annotation_style}物件与空间观察 {index}
- 语音表现：{annotation_style}原声语速重音观察 {index}
- 词汇标记：{annotation_style}词汇标记 {index}
- 语法标记：{annotation_style}语法标记 {index}
- 语气标记：{annotation_style}语气标记 {index}
- 口语现象：{annotation_style}口语现象观察 {index}
- 句式与节奏：{annotation_style}句式节奏观察 {index}
- 识别度：{recognition}
- 可直接使用：视场景
- 不适用场景：事实未确认时
- 重复限制：最近五轮不重复
"""


def build_fixture(
    target: Path,
    persona_type: str,
    card_count: int,
    scene_count: int = 0,
    signature_count: int = 0,
    research_status: str = "达标",
    medium: str | None = None,
    context_type: str = "对话场景",
) -> None:
    shutil.copytree(ROOT / "assets" / "角色人格模板", target)
    selected_medium = medium or ("原创" if persona_type in {"original-persona", "composite-original"} else ("公开表达" if persona_type == "real-person-simulation" else "视听"))
    replacements = {
        "{{PERSONA_NAME}}": "测试角色",
        "{{PERSONA_SLUG}}": "test-role",
        "{{CARD_PREFIX}}": "TESTROLE",
    }
    for path in target.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8-sig")
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"- 人格来源类型：\[待填写[^\]]*\]", f"- 人格来源类型：{persona_type}", text)
        text = re.sub(
            r"- 原作媒介：\[待填写[^\]]*\]",
            f"- 原作媒介：{selected_medium}",
            text,
        )
        text = re.sub(r"- 作品原始语言：\[待填写[^\]]*\]", "- 作品原始语言：zh-CN", text)
        text = TOKEN_RE.sub("已填写", text)
        write_text(path, text)

    cases_path = target / "references" / "07-验证用例.md"
    cases_text = cases_path.read_text(encoding="utf-8")
    biography_case_last = 12 if persona_type in {"existing-character", "real-person-simulation"} else 8
    fidelity_cases = {
        "CASE-18": """## CASE-18 | 去名盲测

- 样本数：12
- 正确识别数：10
- 评估者类型：independent-context
- 评估者标识：隔离评测上下文 A
- 隐藏信息：隐藏角色名、前缀、口头禅和作品名
- 失败样本记录：2 个误识别样本，见原始记录
- 原始记录位置：tests/blind-record-a
- 验证状态：通过
""",
        "CASE-19": """## CASE-19 | 相似角色与通用助手区分

- 样本数：10
- 正确区分数：8
- 对照对象：通用助手和相似角色
- 评估者类型：independent-agent
- 评估者标识：独立评测 Agent B
- 区分证据：CORE、VOICE 与原文卡映射
- 失败样本记录：2 个混淆样本，见原始记录
- 原始记录位置：tests/contrast-record-b
- 验证状态：通过
""",
        "CASE-20": """## CASE-20 | 原文与声纹证据追溯

- 抽查数：6
- 可追溯数：6
- 召回相关数：5
- 证据映射抽查数：12
- 证据映射成立数：10
- 评估者类型：independent-context
- 评估者标识：隔离证据审计上下文 C
- 追溯记录：六个测试场景的完整映射
- 原始记录位置：tests/evidence-map-record-c
- 验证状态：通过
""",
        "CASE-21": """## CASE-21 | 身份与人物小传问答

- 输入：你是谁
- 背景条目：BIO-01
- 固定事实：姓名、身份和当前版本
- 角色输出：以第一人称自然说明身份
- 追溯记录：BIO-01、SRC-0001、CORE-01、VOICE-01
- 验证状态：通过
""",
        "CASE-22": f"""## CASE-22 | 人物关系与未知事实边界

- 输入：你和同伴是什么关系，还有哪些没说过的过去
- 背景条目：BIO-04、BIO-{biography_case_last:02d}
- 未知边界：关系按作品阶段回答，来源未说明的过去保持未知
- 角色输出：说明已知关系并明确不编造未知经历
- 追溯记录：BIO-04、BIO-{biography_case_last:02d}、SRC-0001、CORE-01、VOICE-01
- 验证状态：通过
""",
        "CASE-23": """## CASE-23 | 批量结构退化与生成准备度

- 样本数：10
- 检查器：scripts/check_response.py --batch-file tests/responses.json
- 检查结果：pass
- 重复流程骨架数：1
- 重复开场骨架数：1
- 同一回答形状样本数：3
- 追问收尾样本数：4
- 长度与句数异常集中：否
- 低生成准备度样本数：0
- 原始记录位置：tests/batch-response-record-d
- 验证状态：通过
""",
    }
    for case_id, replacement in fidelity_cases.items():
        cases_text = re.sub(
            rf"^## {case_id}\s+\|.*?(?=^## CASE-|\Z)",
            replacement + "\n",
            cases_text,
            flags=re.MULTILINE | re.DOTALL,
        )
    write_text(cases_path, cases_text.rstrip() + "\n")

    cards = []
    index_rows = []
    for index in range(1, card_count + 1):
        if persona_type in {"existing-character", "real-person-simulation"}:
            source_id = f"SRC-{((index - 1) % 3) + 1:04d}"
        else:
            source_id = "SRC-0001"
        cards.append(card_text(index, persona_type, source_id, scene_count or card_count, signature_count, context_type, selected_medium))
        index_rows.append(
            f"| scene-{index} | normal | {'high' if index % 10 == 0 else 'low'} | "
            f"TESTROLE-{index:04d} | `06-对白库.md` | test |"
        )
    write_text(target / "references" / "06-对白库.md", "# 测试角色对白库\n\n" + "\n".join(cards))
    write_text(
        target / "references" / "05-对白索引.md",
        "# 测试角色对白索引\n\n| 场景 | 用户 | 风险 | 卡片编号 | 文件 | 备注 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(index_rows)
        + "\n",
    )

    evidence_count = max(card_count, 1)
    task_states = ("start", "progress", "waiting", "failed", "risk", "complete", "blocked", "issue")
    emotions = ("cheerful", "caring", "serious", "alert", "calm", "confident", "apologetic", "teasing")
    intents = ("encourage", "report", "warn", "comfort", "explain", "apologize", "clarify", "celebrate")
    core_count = 12 if persona_type in {"existing-character", "real-person-simulation"} else 8
    core_layers = (
        "value", "judgment", "desire", "bias", "boundary", "behavior", "relationship",
        "emotion", "identity", "anti-core", "value", "judgment",
    )
    core_entries = []
    core_conclusions = (
        "遇到危险时把人的安全放在规则之前", "面对命令时先确认是否符合自己的判断", "希望同伴能按自己的意愿行动",
        "偏向当下可见的人而不是抽象效率", "拒绝以伤害换取更快完成", "看到卡点会主动靠近并接手一部分",
        "对熟人会用追问缩短关系距离", "高兴时先直接分享再邀请同行", "把帮助具体的人视为自我身份",
        "不会用中立话术掩盖明确偏好", "判断失误时会承认并立刻调整", "等待时会把注意力转向仍可做的事",
    )
    core_behaviors = (
        "先阻止危险动作再解释原因", "用反问确认决定是否出自本人", "给出空间但不替同伴做选择",
        "先处理眼前求助再讨论流程", "直接说不并保留恢复路径", "主动提出共同完成一个具体动作",
        "先接住情绪再追问真正顾虑", "用短感叹表达高兴并马上邀约", "反复选择帮助普通人的任务",
        "明确表达喜欢与不喜欢", "说清自己错在哪里并改动作", "等待结果时寻找可并行的小任务",
    )
    core_conditions = (
        "生命或数据不可逆风险出现时", "权威命令与个人判断冲突时", "同伴犹豫或被迫选择时", "效率与具体求助冲突时",
        "方案可能造成不可逆伤害时", "同伴被明确障碍卡住时", "熟人情绪低落但愿意交流时", "共同任务取得可见进展时",
        "需要说明为何主动帮助时", "回答容易退化成中立助手时", "自身理解或操作出现错误时", "外部构建或网络尚未返回时",
    )
    for index in range(1, core_count + 1):
        first = ((index - 1) * 2 % evidence_count) + 1
        second = (first % evidence_count) + 1
        core_entries.append(
            f"""### CORE-{index:02d} | 测试核心 {index}

- 层级：{core_layers[index - 1]}
- 结论：{core_conclusions[index - 1]}
- 可观察行为：{core_behaviors[index - 1]}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 证据映射：TESTROLE-{first:04d}=>角色即时反应={core_behaviors[index - 1]}；TESTROLE-{second:04d}=>互动功能={core_conclusions[index - 1]}
- 检索条件：speech_act={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}; trigger={task_states[(first - 1) % 8]}/{task_states[(second - 1) % 8]}; interaction={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}
- 其他来源：SRC-0001
- 反证或边界：核心边界 {index}
- 适用条件：{core_conditions[index - 1]}
- 置信度：高
"""
        )
    core_path = target / "references" / "01-角色核心.md"
    core_text = core_path.read_text(encoding="utf-8")
    core_text = re.sub(r"### CORE-01\s+\|.*?(?=\n## 与用户的关系)", "", core_text, flags=re.DOTALL)
    write_text(core_path, core_text + "\n" + "\n".join(core_entries))

    voice_count = 12 if persona_type in {"existing-character", "real-person-simulation"} else 8
    voice_layers = (
        "lexicon", "syntax", "ending", "orality", "interaction", "emotion", "relation",
        "translation", "anti-voice", "lexicon", "syntax", "interaction",
    )
    voice_entries = []
    voice_patterns = (
        "偏好使用具体动作词而不是抽象流程名词", "常用短句接长句并以追问推动对话", "句尾会在邀请与直接判断之间切换",
        "可见停顿多出现在自我修正和转折之前", "接话时先回应对方最后一个具体词", "轻快状态会缩短解释并增加邀请",
        "面对熟人与陌生人采用不同称呼距离", "跨语言时保留反应在前和短句断开", "避免完整客服安抚和无立场总结",
        "表达偏好时重复关键动作词", "反对时先给短否定再补事实", "邀请合作时用共同动作替代任务分派",
    )
    voice_boundaries = (
        "技术名词必须准确时不强行替换", "复杂事实需要完整句时允许变长", "严肃风险时句尾不使用玩笑",
        "原文没有停顿符号时不推测语音停顿", "对方问题需要直答时不故意转话题", "失败状态不维持过强兴奋",
        "关系未知时不用亲密称呼", "无法保留语尾时优先保留互动功能", "正式文档正文不套角色口语",
        "重复会造成歧义时只保留一次", "事实尚未确认时不作绝对判断", "用户明确单人执行时不虚构共同操作",
    )
    voice_conditions = (
        "低风险日常和普通协作", "需要解释后继续追问", "邀请、拒绝和确认场景", "原文含省略或转折标记时",
        "对方刚给出具体事件时", "成功、日常与轻松等待时", "关系信息已有来源支持时", "输出语言不同于原文时",
        "长回复发送前的反模板检查", "强调喜好或行动优先级时", "不同意方案且要保留事实时", "希望与熟悉同伴共同推进时",
    )
    for index in range(1, voice_count + 1):
        first = ((index - 1) * 2 % evidence_count) + 1
        second = (first % evidence_count) + 1
        voice_entries.append(
            f"""### VOICE-{index:02d} | 测试声纹 {index}

- 层级：{voice_layers[index - 1]}
- 规律：{voice_patterns[index - 1]}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 证据映射：TESTROLE-{first:04d}=>口语现象={voice_patterns[index - 1]}；TESTROLE-{second:04d}=>句式与节奏={voice_conditions[index - 1]}
- 检索条件：speech_act={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}; trigger={task_states[(first - 1) % 8]}/{task_states[(second - 1) % 8]}; interaction={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}
- 反证或边界：{voice_boundaries[index - 1]}
- 适用条件：{voice_conditions[index - 1]}
- 置信度：高
"""
        )
    micro_functions = ("greeting", "acknowledgement", "gratitude", "apology", "surprise", "closing")
    micro_reactions = (
        "先用角色惯用的见面反应认出对方", "先对刚收到的具体信息作短回应", "先直接接住感谢而不使用客服客套",
        "先明确承认自己造成的偏差", "先出现短促惊讶再追问触发点", "先回应共同经历再自然收住",
    )
    micro_openings = (
        "短感叹接一句贴近关系的问句", "复述对方最后一个具体词后停顿", "短句接受后轻轻转回对方",
        "直接认错且不加铺垫", "惊叹短句后接省略或反问", "短句回望当前结果后结束",
    )
    micro_closings = (
        "按关系证据决定是否追问，不默认问今天做什么", "有行动就接住，没有行动就收住", "回应关系而不承诺服务",
        "说明改正动作后收住", "只追问最具体的异常", "不追加通用随时找我",
    )
    micro_anti_generic = (
        "禁止用你好请问有什么可以帮你代替角色见面反应",
        "禁止用收到我来处理代替对具体信息的接话",
        "禁止用不客气很高兴帮助你代替关系回应",
        "禁止用抱歉给你带来不便代替明确认错",
        "禁止用这是一个值得关注的问题抹平惊讶",
        "禁止用还有别的问题吗代替自然结束",
    )
    micro_entries = []
    for index, function in enumerate(micro_functions, start=1):
        first = index
        second = (index % evidence_count) + 1
        first_intent = intents[(first - 1) % len(intents)]
        if function == "greeting":
            first_intent = "greet/encourage"
        micro_entries.append(
            f"""### MICRO-{index:02d} | 测试微互动 {index}

- 功能：{function}
- 触发：{function} 对应的短话语
- 即时反应：{micro_reactions[index - 1]}
- 开场节奏：{micro_openings[index - 1]}
- 追问或收束：{micro_closings[index - 1]}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 证据映射：TESTROLE-{first:04d}=>角色即时反应={micro_reactions[index - 1]}；TESTROLE-{second:04d}=>句式与节奏={micro_openings[index - 1]}
- 检索条件：speech_act={first_intent}; position=reply; relation=familiar
- 禁止通用替代：{micro_anti_generic[index - 1]}
- 置信度：高
"""
        )
    write_text(
        target / "references" / "02-语言声纹.md",
        "# 测试角色语言声纹\n\n" + "\n".join(voice_entries + micro_entries),
    )

    mode_count = 12 if persona_type in {"existing-character", "real-person-simulation"} else 8
    mode_emotions = ("cheerful", "caring", "serious", "alert", "calm", "confident", "apologetic", "teasing")
    mode_entries = []
    for index in range(1, mode_count + 1):
        first = ((index - 1) * 2 % evidence_count) + 1
        second = (first % evidence_count) + 1
        mode_entries.append(
            f"""### MODE-{index:02d} | 测试模式 {index}

- 情绪：{mode_emotions[(index - 1) % len(mode_emotions)]}
- 触发：{mode_emotions[(index - 1) % len(mode_emotions)]} 状态由具体事件触发
- 关系：关系条件 {index}
- 角色即时反应：先出现 {mode_emotions[(index - 1) % len(mode_emotions)]} 的可观察短反应
- 语言变化：{mode_emotions[(index - 1) % len(mode_emotions)]} 时调整句长和追问强度
- 响应形态：采用 {mode_emotions[(index - 1) % len(mode_emotions)]} 对应的不同组织形态
- 口语节奏：保留 {mode_emotions[(index - 1) % len(mode_emotions)]} 的断句与转折位置
- 临场信号：先接住当前具体词再出现短反应 {index}
- 画面表达：只借当前可见测试对象形成一个画面 {index}
- 主动表达：间隔足够时主动回访一个已出现的顾虑 {index}
- 触发与冷却：低风险且至少间隔三轮 {index}
- 禁止结构：禁止固定骨架 {index}
- 行动倾向：行动倾向 {index}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 证据映射：TESTROLE-{first:04d}=>角色即时反应={mode_emotions[(index - 1) % len(mode_emotions)]}即时反应；TESTROLE-{second:04d}=>非语言反应={mode_emotions[(index - 1) % len(mode_emotions)]}非语言变化
- 检索条件：speech_act={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}; trigger={task_states[(first - 1) % 8]}/{task_states[(second - 1) % 8]}; interaction={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}
- 反证或边界：模式边界 {index}
"""
        )
    write_text(target / "references" / "03-情绪与关系.md", "# 测试角色情绪与关系\n\n" + "\n".join(mode_entries))

    anti_count = 8 if persona_type in {"existing-character", "real-person-simulation"} else 6
    anti_entries = []
    anti_modes = ("AI书面连接", "客服完整安抚", "项目经理任务分派", "机械三段式", "过度交还选择权", "伪口语填充", "单一情绪句型", "技术名词堆叠")
    anti_signals = ("综合来看 / 基于以上", "感谢理解 / 为你服务", "推进计划 / 确认范围", "首先 / 其次 / 最后", "由你决定 / 你来选择", "嗯嗯 / 搭档呀", "固定短反应 / 固定追问", "能力边界 / 流程闭环")
    anti_reasons = ("抹掉即时偏向", "把关系写成服务关系", "把合作写成任务管理", "每次使用同一答题骨架", "角色主动性被反复移交", "语气词没有原文结构支持", "不同情绪无法区分", "具体反应被抽象术语覆盖")
    anti_alternatives = ("直接反应后接具体事实", "用关系证据中的真实回应", "用共同动作替代任务分派", "按触发选择不同响应形态", "给出偏好后保留用户决定", "使用省略和自我修正等证据", "切换情绪对应句长与收束", "先说具体对象再说技术事实")
    for index in range(1, anti_count + 1):
        first = ((index - 1) * 2 % evidence_count) + 1
        second = (first % evidence_count) + 1
        anti_entries.append(
            f"""### ANTI-{index:02d} | 测试反角色 {index}

- 模式：{anti_modes[index - 1]}
- 检测信号：{anti_signals[index - 1]}
- 为什么不像：{anti_reasons[index - 1]}
- 角色替代结构：{anti_alternatives[index - 1]}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 证据映射：TESTROLE-{first:04d}=>句式与节奏={anti_alternatives[index - 1]}；TESTROLE-{second:04d}=>互动功能={anti_reasons[index - 1]}
- 检索条件：speech_act={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}; trigger={task_states[(first - 1) % 8]}/{task_states[(second - 1) % 8]}; interaction={intents[(first - 1) % 8]}/{intents[(second - 1) % 8]}
- 适用场景：测试场景 {index}
- 例外：精确技术事实保留 {index}
"""
        )
    write_text(target / "references" / "09-反角色对照.md", "# 测试角色反角色对照\n\n" + "\n".join(anti_entries))

    scene_entries = []
    presence_strategies = (
        "用当前报错行形成一个短画面", "用停住的进度条表现等待", "用并排方案形成选择画面", "用刚保存的文件表现收束",
        "用变绿的测试表现松气", "用重复失败的同一点表现卡住", "用备份副本表现保护", "用待办减少表现推进",
    )
    initiative_conditions = (
        "用户重复同一顾虑时主动回访", "等待超过一轮时提出可并行小事", "阶段完成时分享一个相关联想", "发现遗漏时主动补上",
        "用户疲惫时接手一个明确小动作", "选择摇摆时复述真实偏好", "风险出现时主动阻止并给恢复路", "问题解决后回看最初目标",
    )
    for index, scene_id in enumerate(sorted(persona_tool.REQUIRED_SCENES), start=1):
        first = ((index - 1) % evidence_count) + 1
        second = (first % evidence_count) + 1
        voice_id = ((index - 1) % voice_count) + 1
        first_intent = intents[(first - 1) % len(intents)]
        first_trigger = task_states[(first - 1) % len(task_states)]
        first_emotion = emotions[(first - 1) % len(emotions)]
        scene_entries.append(
            f"""## {scene_id} | 测试场景

- 触发：{scene_id} 场景出现可观察事件
- 目标检索：speech_act={first_intent}; trigger={first_trigger}; interaction={first_intent}; position=reply; relation=familiar; emotion={first_emotion}; initiative=response
- 原作互动功能：使用 {scene_id} 对应的互动功能
- 角色即时反应：先产生 {scene_id} 场景特有的反应
- 候选原文卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 候选声纹规律：VOICE-{voice_id:02d}
- 事实嵌入方式：把事实放入 {scene_id} 场景的反应之后
- 临场表达策略：{presence_strategies[(index - 1) % len(presence_strategies)]}
- 主动表达条件：{initiative_conditions[(index - 1) % len(initiative_conditions)]}
- 冷却与重复：至少间隔三轮并排除最近卡 {index}
- 禁止虚构：不声称看见或听见未发生的现实动作 {index}
- 禁止退化：避免 {scene_id} 场景退化成统一助手模板
"""
        )
    write_text(target / "references" / "04-工作场景迁移.md", "# 测试角色场景迁移\n\n" + "\n".join(scene_entries))

    if persona_type == "existing-character":
        source_types = ("原作明确", "原作明确", "原作明确", "公开资料", "合理推导")
    elif persona_type == "real-person-simulation":
        source_types = ("本人公开表达", "本人公开表达", "本人公开表达", "公开资料", "公开资料")
    else:
        source_types = ("用户补充",)
    source_entries = []
    for index, source_type in enumerate(source_types, start=1):
        support_value = f"TESTROLE-{index:04d}" if source_type in {"原作明确", "本人公开表达", "用户补充"} else f"角色设定结论 {index}"
        source_entries.append(
            f"""## SRC-{index:04d}

- 来源类型：{source_type}
- 位置：测试来源 {index}
- 原始媒介与版本：测试原声版本 {index}
- 原始语言：zh-CN
- 核验方式：{'原声比对' if persona_type in {'existing-character', 'real-person-simulation'} else '原创确认'}
- 可用范围：仅测试
- 内容摘要：测试摘要
- 可靠性：已核对
- 支持的结论或卡片：{support_value}
"""
        )
    research_profile = "稀缺" if research_status == "已穷尽" else ("丰富" if card_count >= 80 else "一般")
    candidate_count = card_count + 12
    if research_status == "已穷尽":
        coverage = f"""## 调研覆盖记录

- 调研状态：已穷尽
- 资料丰度：{research_profile}
- 资料丰度判定依据：扩大到多语言与多类来源后仍只有当前可核查资料
- 候选表达数：{candidate_count}
- 正式原文卡数：{card_count}
- 待核验表达数：2
- 排除表达数：10
- 排除原因摘要：重复定位、无原文或无法回查
- 覆盖维度：身份、日常、失败、风险、关系、情绪与选择
- 最近两轮新增率：4%, 0%
- 饱和结论：合理可访问范围已穷尽
- 初始检索范围：官方角色页与作品页
- 扩大范围记录：继续检查分集资料、访谈、别名和多语言页面
- 检查的站点与资料类型：官方页、剧情页、访谈、对白资料
- 检查的版本、别名与语言：动画与漫画版本、中日英名称
- 各轮新增结果：首轮 12 张，扩大后新增 8 张，此后无新增
- 未达到目标的指标与原因：公开可核查资料总量不足，逐字原文卡与场景覆盖未达目标

### RESEARCH-01 | 初始范围

- 查询词、站点、资料类型与语言：角色名、官方页、中文和日文
- 新增来源与卡片：新增 12 张
- 未覆盖指标：逐字原文卡和原作场景不足

### RESEARCH-02 | 扩大范围

- 查询词、站点、资料类型与语言：别名、英文名、访谈、分集资料和对白
- 新增来源与卡片：新增 8 张，此后无新增
- 未覆盖指标：全网合理可访问资料仍不足
"""
    else:
        extra_round = "" if research_profile == "一般" else """
### RESEARCH-03 | 低增量复查

- 查询词、站点、资料类型与语言：遗漏别名、跨语言索引与长尾场景复查
- 新增来源与卡片：新增 2% 的可核查卡片
- 未覆盖指标：无
"""
        coverage = f"""## 调研覆盖记录

- 调研状态：达标
- 资料丰度：{research_profile}
- 资料丰度判定依据：存在多轮、跨场景、跨资料类型的可核查原始表达
- 候选表达数：{candidate_count}
- 正式原文卡数：{card_count}
- 待核验表达数：2
- 排除表达数：10
- 排除原因摘要：重复定位、无原文或无法回查
- 覆盖维度：身份、日常、失败、风险、关系、情绪、选择、冲突、问候与告别
- 最近两轮新增率：4%, 2%
- 饱和结论：已饱和
- 初始检索范围：官方资料与可核查场景
- 扩大范围记录：继续扩大到别名、多语言索引与不同资料类型，直到连续两轮低增量
- 检查的站点与资料类型：官方页、剧情页、对白资料
- 检查的版本、别名与语言：主要版本与中日文名称
- 各轮新增结果：首轮建立基线，第二轮补齐缺口，最后两轮新增率降至 4% 与 2%
- 未达到目标的指标与原因：无

### RESEARCH-01 | 初始范围

- 查询词、站点、资料类型与语言：角色名、官方页、剧情页、中文和日文
- 新增来源与卡片：建立首轮候选与正式卡
- 未覆盖指标：仍需扩大场景与语言范围

### RESEARCH-02 | 扩大范围

- 查询词、站点、资料类型与语言：别名、多语言索引、访谈、场景资料与可靠转写
- 新增来源与卡片：补齐高识别表达和关系场景，新增率 4%
- 未覆盖指标：无
{extra_round}"""
    write_text(
        target / "references" / "08-来源索引.md",
        "# 测试角色来源索引\n\n" + coverage + "\n" + "\n".join(source_entries),
    )

    bio_count = 12 if persona_type in {"existing-character", "real-person-simulation"} else 8
    bio_categories = (
        "identity", "gender", "background", "timeline", "relationship", "ability", "preference", "worldview",
        "faq", "relationship", "timeline", "ability",
    )
    bio_topics = (
        "姓名与身份", "性别身份与称谓", "成长背景", "首次重要经历", "与同伴的关系", "擅长的能力",
        "日常偏好", "看待规则的方式", "为何参与当前行动", "称呼熟悉同伴", "关键转折后的变化", "能力限制",
    )
    bio_facts = (
        "公开身份是测试角色并使用该姓名", "性别身份为女性并使用资料明确的女性称谓", "成长经历解释了当前的行动倾向",
        "第一次关键事件改变了任务方向", "把主要同伴视为可共同决定的人", "擅长观察局面并快速采取行动",
        "空闲时更喜欢轻松的日常活动", "规则与具体的人冲突时会重新判断", "参与行动是为了保护眼前的重要对象",
        "对熟悉同伴采用较近的称呼", "关键转折后更愿意表达自己的判断", "能力有明确范围且不能解决所有问题",
    )
    bio_perspectives = (
        "用第一人称直接报出姓名和当前身份", "采用资料中的女性自称与称谓，不额外套用刻板语气", "只承认来源明确的成长经历",
        "按当时阶段讲述事件而不提前剧透", "说明重视对方但不虚构额外亲密关系", "可以自信说明擅长事项并承认限制",
        "用自然口吻表达喜欢而非列偏好表", "先说自己的判断再解释规则位置", "说明自己的主动选择和保护对象",
        "沿用资料中的称呼与关系距离", "区分转折前后的自己", "明确说出做不到的部分",
    )
    bio_questions = (
        "你是谁/你叫什么", "你的性别/怎么称呼你/用什么代词", "你从哪里来/你的过去", "你第一次经历什么/早期经历",
        "你和同伴什么关系/你怎么看她", "你会什么/你擅长什么", "你喜欢什么/平时做什么", "你怎么看规则/为什么不服从",
        "你为什么做这件事/你的目标", "你怎么称呼同伴/你们熟吗", "后来你变了吗/哪个事件改变你", "你有什么弱点/你做不到什么",
    )
    bio_boundaries = (
        "不同版本名称不一致时注明版本", "没有来源的性别表达差异不补写", "没有来源的童年细节不补写",
        "回答按用户允许的剧透范围", "不把合作关系自动写成恋爱关系", "不得把作品能力扩展成现实工具能力",
        "不从单句对白推导永久偏好", "只陈述跨场景可见的价值判断", "不把模型解释冒充角色亲口设定",
        "关系阶段变化时注明时间点", "不同作品阶段分开回答", "精确能力上限未知时说明未知",
    )
    bio_entries = []
    for index in range(1, bio_count + 1):
        source_index = ((index - 1) % len(source_types)) + 1
        bio_entries.append(
            f"""### BIO-{index:02d} | {bio_topics[index - 1]}

- 类别：{bio_categories[index - 1]}
- 主题：{bio_topics[index - 1]}
- 事实：{bio_facts[index - 1]}
- 角色视角回答要点：{bio_perspectives[index - 1]}
- 适用问题：{bio_questions[index - 1]}
- 时间或版本：测试作品阶段 {index}
- 来源：SRC-{source_index:04d}
- 置信度：高
- 边界：{bio_boundaries[index - 1]}
"""
        )
    write_text(
        target / "references" / "10-人物背景档案.md",
        """# 测试角色人物背景档案

## 常驻身份基线

- 姓名与原名：测试角色 / Test Role
- 性别身份：女
- 性别相关称谓与代词：第一人称“我”，第三人称“她”
- 年龄或生命阶段：测试作品青年阶段
- 物种或存在类型：人类
- 社会身份或职业：测试行动成员
- 所属或阵营：测试组织
- 当前时间点或版本：测试作品正式版
- 自我认知：把自己视为会主动帮助同伴的行动者
- 基线来源：SRC-0001

""" + "\n".join(bio_entries),
    )


class PersonaToolTests(unittest.TestCase):
    def test_init_copies_selector_and_draft_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "new-role"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "persona_tool.py"),
                    "init",
                    "--name",
                    "新角色",
                    "--slug",
                    "new-role",
                    "--output",
                    str(role),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((role / "scripts" / "select_dialogues.py").is_file())
            self.assertTrue((role / "references" / "10-人物背景档案.md").is_file())
            draft = persona_tool.validate_skill(role, "draft")
            self.assertTrue(draft["valid"], draft["issues"])

    def test_existing_character_release_and_selector(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "test-role"
            build_fixture(role, "existing-character", 80, 40, 20)

            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["cards"], 80)
            self.assertEqual(result["metrics"]["exact_original_cards"], 80)
            self.assertEqual(result["metrics"]["distinct_source_scenes"], 40)
            self.assertEqual(result["metrics"]["signature_cards"], 20)
            self.assertEqual(result["metrics"]["derived_cards"], 0)
            self.assertEqual(result["metrics"]["original_sources"], 3)
            self.assertEqual(result["metrics"]["core_rules"], 12)
            self.assertEqual(result["metrics"]["core_layers"], 10)
            self.assertGreaterEqual(result["metrics"]["core_evidence_cards"], 20)
            self.assertEqual(result["metrics"]["biography_entries"], 12)
            self.assertGreaterEqual(result["metrics"]["biography_categories"], 6)
            self.assertTrue(result["metrics"]["biography_baseline_complete"])
            self.assertEqual(result["metrics"]["micro_rules"], 6)
            self.assertEqual(result["metrics"]["micro_functions"], 6)

            selector = role / "scripts" / "select_dialogues.py"
            command = [
                sys.executable,
                str(selector),
                "--root",
                str(role),
                "--task-state",
                "failed",
                "--user-state",
                "tired",
                "--emotion",
                "alert",
                "--intent",
                "comfort",
                "--speech-act",
                "comfort",
                "--trigger",
                "failed",
                "--interaction",
                "comfort",
                "--position",
                "reply",
                "--risk",
                "low",
                "--language",
                "zh-CN",
                "--format",
                "json",
                "--turns-since-presence",
                "3",
                "--turns-since-initiative",
                "4",
            ]
            first = json.loads(subprocess.check_output(command, text=True, encoding="utf-8"))
            self.assertEqual(first["library_cards"], 80)
            self.assertEqual(len(first["selected"]), 5)
            self.assertLess(len(first["selected"]), first["library_cards"])
            self.assertTrue(all(item["original_text"] for item in first["selected"]))
            self.assertGreaterEqual(len(first["related_rules"]["core"]), 1)
            self.assertGreaterEqual(len(first["related_rules"]["voice"]), 1)
            self.assertGreaterEqual(len(first["related_rules"]["modes"]), 1)
            self.assertGreaterEqual(len(first["related_rules"]["anti"]), 1)
            self.assertIn(first["retrieval"]["confidence"], {"high", "medium"})
            self.assertIn(first["retrieval"]["match_confidence"], {"high", "medium"})
            self.assertIn(first["retrieval"]["evidence_confidence"], {"high", "medium"})
            self.assertTrue(
                all(item["evidence_confidence"] in {"high", "medium"} for item in first["selected"])
            )
            selected_ids = {item["card_id"] for item in first["selected"]}
            for group in first["related_rules"].values():
                self.assertTrue(all(set(rule["matched_card_ids"]) <= selected_ids for rule in group))
                self.assertTrue(all(rule["condition_matches"] > 0 for rule in group))
                self.assertTrue(
                    all(set(rule["evidence_mapping"]) == set(rule["matched_card_ids"]) for rule in group)
                )
            self.assertEqual(first["delivery_guidance"]["presence_status"], "due")
            self.assertEqual(first["delivery_guidance"]["initiative_status"], "due")
            self.assertEqual(first["delivery_guidance"]["max_presence_beats"], 1)
            self.assertIn(first["composition_guidance"]["generation_readiness"], {"high", "medium"})
            self.assertTrue(first["retrieval"]["scope_note"])

            excluded = first["selected"][0]["card_id"]
            second = json.loads(
                subprocess.check_output(command + ["--exclude", excluded], text=True, encoding="utf-8")
            )
            self.assertNotIn(excluded, {item["card_id"] for item in second["selected"]})

            high_risk = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(selector),
                        "--root",
                        str(role),
                        "--task-state",
                        "risk",
                        "--risk",
                        "high",
                        "--language",
                        "zh-CN",
                        "--format",
                        "json",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertGreaterEqual(len(high_risk["selected"]), 1)
            self.assertEqual(high_risk["work_route"]["scene_id"], "risk")
            self.assertEqual(high_risk["delivery_guidance"]["presence_status"], "serious-only")
            self.assertTrue(all(item["evidence_confidence"] in {"high", "medium"} for item in high_risk["selected"]))

            micro = json.loads(
                subprocess.check_output(
                    [
                        sys.executable, str(selector), "--root", str(role),
                        "--speech-act", "encourage", "--trigger", "start",
                        "--interaction", "encourage", "--position", "reply",
                        "--relation", "familiar", "--micro-function", "greeting",
                        "--last-user-focus", "你好", "--open-thread", "初次见面",
                        "--previous-shape", "question",
                        "--limit", "1", "--format", "json",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertEqual(len(micro["selected"]), 1)
            self.assertGreaterEqual(len(micro["related_rules"]["micro"]), 1)
            self.assertEqual(micro["composition_guidance"]["generation_readiness"], "high")
            self.assertGreaterEqual(len(micro["composition_guidance"]["style_exemplars"]), 2)
            continuity = micro["delivery_guidance"]["conversation_continuity"]
            self.assertTrue(continuity["must_react_to_visible_focus"])
            self.assertTrue(continuity["must_continue_open_thread"])
            self.assertTrue(continuity["avoid_repeating_previous_shape"])
            self.assertTrue(continuity["natural_stop_allowed"])
            micro_markdown = subprocess.check_output(
                [
                    sys.executable, str(selector), "--root", str(role),
                    "--speech-act", "encourage", "--trigger", "start",
                    "--interaction", "encourage", "--position", "reply",
                    "--relation", "familiar", "--micro-function", "greeting",
                    "--last-user-focus", "你好", "--open-thread", "初次见面",
                    "--previous-shape", "question", "--limit", "1",
                ],
                text=True,
                encoding="utf-8",
            )
            self.assertIn("本轮必须接住：你好", micro_markdown)
            self.assertIn("本轮必须延续：初次见面", micro_markdown)
            self.assertIn("本轮避免重复形状：question", micro_markdown)
            self.assertIn("允许自然收束：是", micro_markdown)
            self.assertIn("跨证据单元风格支持（不是当前场景召回）", micro_markdown)

    def test_novel_character_releases_with_narrative_evidence_units(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "novel-role"
            build_fixture(
                role, "existing-character", 40, 15, 10,
                medium="文字", context_type="内心独白",
            )
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["distinct_evidence_units"], 15)
            self.assertEqual(result["metrics"]["performance_verified_cards"], 40)

    def test_real_person_releases_from_public_posts_without_dialogue_turns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "public-person-role"
            build_fixture(
                role, "real-person-simulation", 40, 15, 10,
                medium="公开表达", context_type="社交媒体",
            )
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["distinct_evidence_units"], 15)
            self.assertEqual(result["metrics"]["original_sources"], 3)

    def test_self_contained_expression_still_requires_publication_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "contextless-post-role"
            build_fixture(
                role, "real-person-simulation", 24, 8, 8,
                medium="公开表达", context_type="社交媒体",
            )
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 触发话语：追问公开主题 1", "- 触发话语：不适用", 1)
            text = text.replace("- 对话对象：公众或读者", "- 对话对象：不适用", 1)
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.complete_scene_context_missing", codes)

    def test_existing_character_below_target_requires_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "small-role"
            build_fixture(role, "existing-character", 12, 4, 3)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.too_few", codes)
            self.assertIn("dialogue.exact_original_cards_low", codes)
            self.assertIn("dialogue.source_scenes_low", codes)
            self.assertIn("dialogue.signature_cards_low", codes)
            self.assertEqual(result["metrics"]["research_profile"], "一般")

    def test_sparse_profile_cannot_be_marked_as_target_met(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "false-sparse-pass"
            build_fixture(role, "existing-character", 24, 8, 8)
            source_path = role / "references" / "08-来源索引.md"
            text = source_path.read_text(encoding="utf-8").replace("- 资料丰度：一般", "- 资料丰度：稀缺", 1)
            write_text(source_path, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("research.sparse_cannot_pass", codes)

    def test_target_met_requires_low_increment_saturation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "unsaturated-role"
            build_fixture(role, "existing-character", 40, 15, 10)
            source_path = role / "references" / "08-来源索引.md"
            text = source_path.read_text(encoding="utf-8").replace(
                "- 最近两轮新增率：4%, 2%", "- 最近两轮新增率：18%, 9%", 1
            )
            write_text(source_path, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("research.not_saturated", codes)

    def test_exhausted_research_releases_all_available_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "exhausted-role"
            build_fixture(role, "existing-character", 12, 4, 3, research_status="已穷尽")
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["version"], "正式版")
            self.assertEqual(result["metrics"]["research_status"], "已穷尽")
            self.assertEqual(result["metrics"]["coverage_path"], "exhausted")
            warning_codes = {
                issue["code"] for issue in result["issues"] if issue["severity"] == "warning"
            }
            self.assertIn("dialogue.too_few", warning_codes)
            self.assertIn("dialogue.exact_original_cards_low", warning_codes)

    def test_exhausted_status_requires_real_expansion_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "false-exhaustion"
            build_fixture(role, "existing-character", 12, 4, 3, research_status="已穷尽")
            source_path = role / "references" / "08-来源索引.md"
            source_text = source_path.read_text(encoding="utf-8")
            write_text(
                source_path,
                source_text.replace(
                    "- 扩大范围记录：继续检查分集资料、访谈、别名和多语言页面",
                    "- 扩大范围记录：无",
                ),
            )
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("research.exhaustion_incomplete", codes)

    def test_original_cards_must_reference_original_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "source-mismatch"
            build_fixture(role, "existing-character", 80, 40, 20)
            source_path = role / "references" / "08-来源索引.md"
            source_text = source_path.read_text(encoding="utf-8")
            write_text(source_path, source_text.replace("- 来源类型：原作明确", "- 来源类型：公开资料", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.original_source_mismatch", codes)

    def test_existing_character_rejects_missing_original_and_work_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "fake-original"
            build_fixture(role, "existing-character", 24, 8, 8)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 原文：原作逐字原句 1", "- 原文：无", 1)
            text = text.replace(
                "- 重复限制：最近五轮不重复",
                "- 工作改写示例：测试角色：这是预写的工作话术\n- 重复限制：最近五轮不重复",
                1,
            )
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.original_text_missing", codes)
            self.assertIn("dialogue.prewritten_rewrite_forbidden", codes)

    def test_existing_character_rejects_non_original_and_duplicate_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "derived-dialogue"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 卡片类型：原文对白", "- 卡片类型：原创规范对白", 1)
            text = text.replace("- 原文：原作逐字原句 3", "- 原文：原作逐字原句 2", 1)
            text = text.replace("- 来源位置：SRC-0003，测试定位 3", "- 来源位置：SRC-0002，测试定位 2", 1)
            text = text.replace("- 场景编号：SCENE-0003", "- 场景编号：SCENE-0002", 1)
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.non_original_card", codes)
            self.assertIn("dialogue.duplicate_original_text", codes)

    def test_repeated_original_in_distinct_scenes_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "repeated-catchphrase"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            write_text(library, text.replace("- 原文：原作逐字原句 3", "- 原文：原作逐字原句 2", 1))
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["exact_original_cards"], 80)
            self.assertEqual(result["metrics"]["unique_original_expressions"], 79)

    def test_reliable_transcript_is_valid_original_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "transcript-role"
            build_fixture(role, "existing-character", 40, 15, 10)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 来源类型：原作明确", "- 来源类型：可靠转写")
            text = text.replace("- 原文质量：原声核验", "- 原文质量：可靠转写核验")
            write_text(library, text)
            source_path = role / "references" / "08-来源索引.md"
            source_text = source_path.read_text(encoding="utf-8").replace(
                "- 来源类型：原作明确", "- 来源类型：可靠转写"
            )
            write_text(source_path, source_text)
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["exact_original_cards"], 40)

    def test_source_locator_text_cannot_fake_scene_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "locator-context-role"
            build_fixture(role, "existing-character", 40, 15, 10)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace(
                "- 前置原文：追问前一句测试原文 1",
                "- 前置原文：官方场景页以话数与场景标题定位",
                1,
            )
            text = text.replace(
                "- 触发话语：追问触发话语 1",
                "- 触发话语：new_arrival；资料说明可定位",
                1,
            )
            text = text.replace(
                "- 后续原文：追问后一句测试原文 1",
                "- 后续原文：该互动的后续由同一官方场景条目定位",
                1,
            )
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.context_locator_only", codes)
            self.assertIn("dialogue.complete_scene_context_missing", codes)

    def test_translated_or_unverified_text_cannot_count_as_original_language(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "translated-corpus"
            build_fixture(role, "existing-character", 24, 8, 8)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            write_text(library, text.replace("- 原文质量：原声核验", "- 原文质量：译本参考", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertEqual(result["metrics"]["exact_original_cards"], 23)
            self.assertIn("dialogue.original_language_unverified", codes)
            self.assertIn("dialogue.exact_original_cards_low", codes)

    def test_original_language_text_can_release_without_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "text-only-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8").replace("- 原文质量：原声核验", "- 原文质量：原语言文本核验")
            text = text.replace("- 语音表现：原声语速重音观察", "- 语音表现：未核验原声；文本口语观察")
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["performance_verified_cards"], 0)
            warning_codes = {item["code"] for item in result["issues"] if item["severity"] == "warning"}
            self.assertIn("dialogue.performance_cards_low", warning_codes)

    def test_boilerplate_observation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "boilerplate-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = re.sub(r"^- 语音表现：.+$", "- 语音表现：统一套用的声纹描述", text, flags=re.MULTILINE)
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.annotation_boilerplate", codes)

    def test_semantic_rule_boilerplate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "semantic-boilerplate"
            build_fixture(role, "existing-character", 80, 40, 20)
            replacements = {
                "01-角色核心.md": ("结论", "可观察行为", "适用条件"),
                "02-语言声纹.md": ("规律", "反证或边界", "适用条件"),
                "03-情绪与关系.md": ("触发", "角色即时反应", "语言变化", "响应形态", "口语节奏"),
                "09-反角色对照.md": ("模式", "检测信号", "为什么不像", "角色替代结构"),
                "04-工作场景迁移.md": ("触发", "原作互动功能", "角色即时反应", "事实嵌入方式", "禁止退化"),
                "10-人物背景档案.md": ("主题", "事实", "角色视角回答要点", "适用问题", "边界"),
            }
            for filename, fields in replacements.items():
                path = role / "references" / filename
                text = path.read_text(encoding="utf-8")
                for field in fields:
                    text = re.sub(
                        rf"^- {re.escape(field)}：.+$",
                        f"- {field}：统一批量生成的模板内容",
                        text,
                        flags=re.MULTILINE,
                    )
                write_text(path, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertEqual(result["metrics"]["semantic_diversity_failures"], 6)
            self.assertTrue(
                {
                    "core_rule.semantic_boilerplate",
                    "voice.semantic_boilerplate",
                    "mode.semantic_boilerplate",
                    "anti.semantic_boilerplate",
                    "scene.semantic_boilerplate",
                    "biography.semantic_boilerplate",
                }
                <= codes
            )

    def test_biography_fact_requires_existing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "invented-biography"
            build_fixture(role, "existing-character", 80, 40, 20)
            biography = role / "references" / "10-人物背景档案.md"
            text = biography.read_text(encoding="utf-8")
            write_text(biography, text.replace("- 来源：SRC-0001", "- 来源：SRC-9999", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("biography.source_invalid", codes)

    def test_biography_baseline_and_gender_category_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "missing-gender-baseline"
            build_fixture(role, "existing-character", 80, 40, 20)
            biography = role / "references" / "10-人物背景档案.md"
            text = biography.read_text(encoding="utf-8")
            text = text.replace("- 性别身份：女\n", "", 1)
            text = text.replace("- 类别：gender", "- 类别：faq", 1)
            write_text(biography, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("biography.baseline_missing", codes)
            self.assertIn("biography.identity_coverage_missing", codes)

    def test_source_card_claim_must_match_card_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "false-source-claim"
            build_fixture(role, "existing-character", 80, 40, 20)
            source_path = role / "references" / "08-来源索引.md"
            text = source_path.read_text(encoding="utf-8")
            write_text(
                source_path,
                text.replace(
                    "- 支持的结论或卡片：TESTROLE-0001",
                    "- 支持的结论或卡片：TESTROLE-0002",
                    1,
                ),
            )
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("sources.card_claim_mismatch", codes)

    def test_missing_context_conflicts_with_verified_label_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "false-label-evidence"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            write_text(library, text.replace("- 触发话语：追问触发话语 1", "- 触发话语：上下文缺失", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.label_evidence_conflict", codes)

    def test_isolated_excerpts_do_not_inflate_scene_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "isolated-scenes"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8").replace("- 场景完整度：完整", "- 场景完整度：孤立摘录")
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertEqual(result["metrics"]["distinct_source_scenes"], 0)
            self.assertEqual(result["metrics"]["context_complete_cards"], 0)
            self.assertIn("dialogue.source_scenes_low", codes)
            self.assertIn("core_rule.evidence_context_incomplete", codes)

    def test_original_cards_reject_work_domain_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "work-tags-in-source"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace(
                "- 原作检索标签：speech_act=encourage;",
                "- 原作检索标签：task_state=failed; risk=high; speech_act=encourage;",
                1,
            )
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            self.assertIn("dialogue.work_tags_in_source_card", {issue["code"] for issue in result["issues"]})

    def test_rule_evidence_mapping_must_cover_cards_and_real_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "bad-evidence-map"
            build_fixture(role, "existing-character", 80, 40, 20)
            core = role / "references" / "01-角色核心.md"
            text = core.read_text(encoding="utf-8")
            text = text.replace(
                "- 证据映射：TESTROLE-0001=>角色即时反应=先阻止危险动作再解释原因；TESTROLE-0002=>互动功能=遇到危险时把人的安全放在规则之前",
                "- 证据映射：TESTROLE-0001=>不存在字段",
                1,
            )
            write_text(core, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("core_rule.evidence_mapping_mismatch", codes)
            self.assertIn("core_rule.evidence_mapping_field_invalid", codes)

    def test_rule_evidence_mapping_requires_concrete_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "field-only-evidence-map"
            build_fixture(role, "existing-character", 80, 40, 20)
            core = role / "references" / "01-角色核心.md"
            text = core.read_text(encoding="utf-8")
            text = text.replace(
                "TESTROLE-0001=>角色即时反应=先阻止危险动作再解释原因",
                "TESTROLE-0001=>角色即时反应",
                1,
            )
            write_text(core, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("core_rule.evidence_mapping_observation_missing", codes)

    def test_selector_downgrades_high_tag_match_with_weak_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "weak-evidence"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = re.sub(
                r"^- 标签依据：.+$",
                "- 标签依据：speech_act=合理推导; trigger=缺失; relation=缺失; emotion=合理推导",
                text,
                flags=re.MULTILINE,
            )
            text = re.sub(r"^- 触发话语：.+$", "- 触发话语：上下文缺失", text, flags=re.MULTILINE)
            text = re.sub(r"^- 对话对象：.+$", "- 对话对象：未知", text, flags=re.MULTILINE)
            write_text(library, text)
            selected = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(role / "scripts" / "select_dialogues.py"),
                        "--root", str(role),
                        "--task-state", "failed",
                        "--user-state", "tired",
                        "--emotion", "alert",
                        "--intent", "comfort",
                        "--speech-act", "comfort",
                        "--trigger", "failed",
                        "--interaction", "comfort",
                        "--position", "reply",
                        "--risk", "low",
                        "--language", "zh-CN",
                        "--format", "json",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertEqual(selected["selected"], [])
            self.assertEqual(selected["retrieval"]["match_confidence"], "low")
            self.assertEqual(selected["retrieval"]["evidence_confidence"], "low")
            self.assertEqual(selected["retrieval"]["confidence"], "low")
            self.assertGreater(selected["retrieval"]["dropped_weak_cards"], 0)
            self.assertIn("不用弱卡凑数", selected["retrieval"]["warning"])

    def test_selector_can_use_verified_short_excerpt_for_exact_surface_act(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "direct-short-expression"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 场景完整度：完整", "- 场景完整度：孤立摘录", 1)
            text = text.replace("- 前置原文：追问前一句测试原文 1", "- 前置原文：不适用", 1)
            text = text.replace("- 触发话语：追问触发话语 1", "- 触发话语：不适用", 1)
            text = text.replace("- 后续原文：追问后一句测试原文 1", "- 后续原文：不适用", 1)
            text = text.replace("- 可直接使用：视场景", "- 可直接使用：仅短句", 1)
            write_text(library, text)
            selected = json.loads(
                subprocess.check_output(
                    [
                        sys.executable, str(role / "scripts" / "select_dialogues.py"),
                        "--root", str(role), "--speech-act", "greet", "--limit", "1", "--format", "json",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertEqual([item["card_id"] for item in selected["selected"]], ["TESTROLE-0001"])
            self.assertEqual(selected["selected"][0]["evidence_confidence"], "medium")
            self.assertIn("scope:direct-only", selected["selected"][0]["evidence_gaps"])

    def test_same_context_self_evaluation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "self-evaluated"
            build_fixture(role, "existing-character", 80, 40, 20)
            cases = role / "references" / "07-验证用例.md"
            text = cases.read_text(encoding="utf-8")
            write_text(cases, text.replace("- 评估者标识：隔离评测上下文 A", "- 评估者标识：生成者本人自评", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.self_evaluation_forbidden", codes)

    def test_voice_and_scene_must_reference_verified_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "invented-voice"
            build_fixture(role, "existing-character", 80, 40, 20)
            voice_path = role / "references" / "02-语言声纹.md"
            voice_text = voice_path.read_text(encoding="utf-8")
            write_text(voice_path, voice_text.replace("TESTROLE-0001、TESTROLE-0002", "UNKNOWN-9999、TESTROLE-0002", 1))
            core_path = role / "references" / "01-角色核心.md"
            core_text = core_path.read_text(encoding="utf-8")
            write_text(core_path, core_text.replace("TESTROLE-0001、TESTROLE-0002", "UNKNOWN-9999、TESTROLE-0002", 1))
            scene_path = role / "references" / "04-工作场景迁移.md"
            scene_text = scene_path.read_text(encoding="utf-8")
            write_text(scene_path, scene_text.replace("VOICE-01", "VOICE-99", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("core_rule.evidence_invalid", codes)
            self.assertIn("voice.evidence_invalid", codes)
            self.assertIn("scene.voice_invalid", codes)

    def test_output_language_does_not_filter_original_language_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "cross-language-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            core_path = role / "references" / "01-角色核心.md"
            write_text(
                core_path,
                core_path.read_text(encoding="utf-8").replace("- 作品原始语言：zh-CN", "- 作品原始语言：ja-JP"),
            )
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 原文语言：zh-CN", "- 原文语言：ja-JP")
            write_text(library, text)
            source_path = role / "references" / "08-来源索引.md"
            write_text(
                source_path,
                source_path.read_text(encoding="utf-8").replace("- 原始语言：zh-CN", "- 原始语言：ja-JP"),
            )
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            selected = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(role / "scripts" / "select_dialogues.py"),
                        "--root", str(role),
                        "--speech-act", "comfort",
                        "--trigger", "failed",
                        "--interaction", "comfort",
                        "--position", "reply",
                        "--emotion", "alert",
                        "--source-language", "ja-JP",
                        "--language", "zh-CN",
                        "--limit", "5",
                        "--format", "json",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertEqual(len(selected["selected"]), 5)
            self.assertTrue(all(item["original_language"] == "ja-JP" for item in selected["selected"]))

    def test_fidelity_tests_must_be_run_and_meet_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "untested-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            cases_path = role / "references" / "07-验证用例.md"
            text = cases_path.read_text(encoding="utf-8")
            text = text.replace("- 正确识别数：10", "- 正确识别数：6", 1)
            text = text.replace("- 验证状态：通过", "- 验证状态：未运行", 1)
            write_text(cases_path, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.fidelity_not_passed", codes)
            self.assertIn("tests.blind_correct_low", codes)

    def test_batch_fidelity_rejects_uniform_shape_and_question_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "uniform-batch-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            cases_path = role / "references" / "07-验证用例.md"
            text = cases_path.read_text(encoding="utf-8")
            text = text.replace("- 同一回答形状样本数：3", "- 同一回答形状样本数：7", 1)
            text = text.replace("- 追问收尾样本数：4", "- 追问收尾样本数：8", 1)
            text = text.replace("- 长度与句数异常集中：否", "- 长度与句数异常集中：是", 1)
            write_text(cases_path, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("tests.batch_shape_repeated", codes)
            self.assertIn("tests.batch_question_closure_repeated", codes)
            self.assertIn("tests.batch_uniform_structure", codes)

    def test_response_checker_flags_ai_and_project_manager_tone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "tone-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            checker = role / "scripts" / "check_response.py"
            generic = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(checker),
                        "--root", str(role),
                        "--text", "好的，基于以上情况，我们先确认目标，再梳理范围，然后确定方案，最后推进下一步，由你决定。",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            spoken = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(checker),
                        "--root", str(role),
                        "--text", "不行，这个我不喜欢。先做副本。要不要继续，你来选。",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            process_preamble = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(checker),
                        "--root", str(role),
                        "--text", "千束：我先按轻松问候场景取几张日语原文卡。",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            fake_presence = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(checker),
                        "--root", str(role),
                        "--text", "*歪头* 嗯，呃，那个……哈哈，我看见你叹气了。*拍拍你的肩*",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            consulting = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(checker),
                        "--root", str(role),
                        "--text", "做网站啊，挺好。先别急着铺一大堆页面：它是给谁用的，对方进来第一件事要完成什么？这两个定下来，我们就能做出第一版。",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            batch_path = role / "tests" / "responses.json"
            batch_path.parent.mkdir(parents=True, exist_ok=True)
            write_text(
                batch_path,
                json.dumps(
                    [
                        "先别急着做页面。先把目标定下来，我们就能继续。",
                        "还没结束。先看错误日志，我们从第一条开始。",
                        "这次我理解反了。我先改需求，再重新整理。",
                        "方案你定了。先确认代价，然后我们推进。",
                        "做得好。先验收，再发布，我们继续。",
                    ],
                    ensure_ascii=False,
                ),
            )
            batch = json.loads(
                subprocess.check_output(
                    [sys.executable, str(checker), "--root", str(role), "--batch-file", str(batch_path)],
                    text=True,
                    encoding="utf-8",
                )
            )
            uniform_path = role / "tests" / "uniform-responses.json"
            write_text(
                uniform_path,
                json.dumps(
                    [
                        "这块你最想改成什么样？",
                        "这个结果你现在满意吗？",
                        "这里你更偏向哪一种呢？",
                        "这一段你希望继续保留吗？",
                        "这次你想先看哪个部分？",
                    ],
                    ensure_ascii=False,
                ),
            )
            uniform = json.loads(
                subprocess.check_output(
                    [sys.executable, str(checker), "--root", str(role), "--batch-file", str(uniform_path)],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertEqual(generic["status"], "fail")
            self.assertGreaterEqual(generic["ai_tone_score"], 60)
            self.assertEqual(spoken["status"], "pass")
            self.assertLess(spoken["ai_tone_score"], 40)
            self.assertEqual(process_preamble["status"], "fail")
            self.assertIn("internal_process_preamble", {item["code"] for item in process_preamble["findings"]})
            fake_codes = {item["code"] for item in fake_presence["findings"]}
            self.assertEqual(fake_presence["status"], "fail")
            self.assertIn("unverified_sensory_claim", fake_codes)
            self.assertIn("stage_direction_density", fake_codes)
            self.assertIn(consulting["status"], {"review", "fail"})
            self.assertIn("generic_consulting_frame", {item["code"] for item in consulting["findings"]})
            self.assertEqual(batch["status"], "fail")
            self.assertIn("batch_workflow_skeleton_repeated", {item["code"] for item in batch["findings"]})
            uniform_codes = {item["code"] for item in uniform["findings"]}
            self.assertEqual(uniform["status"], "fail")
            self.assertIn("batch_question_closure_repeated", uniform_codes)
            self.assertIn("batch_response_shape_repeated", uniform_codes)

    def test_evidence_mapping_audit_is_independent_and_meets_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "weak-map-audit"
            build_fixture(role, "existing-character", 80, 40, 20)
            cases = role / "references" / "07-验证用例.md"
            text = cases.read_text(encoding="utf-8")
            text = text.replace("- 证据映射抽查数：12", "- 证据映射抽查数：6", 1)
            text = text.replace("- 证据映射成立数：10", "- 证据映射成立数：3", 1)
            text = text.replace("- 评估者标识：隔离证据审计上下文 C", "- 评估者标识：生成者本人自评", 1)
            write_text(cases, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("tests.evidence_mapping_samples_low", codes)
            self.assertIn("tests.evidence_mapping_rate_low", codes)
            self.assertIn("tests.self_evaluation_forbidden", codes)

    def test_original_persona_can_release_with_twenty_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "original-role"
            build_fixture(role, "original-persona", 20)
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])

    def test_creator_enforces_name_gate_prefix_and_formal_only_delivery(self) -> None:
        creator = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("第一条回复只能显示下面的二选一提示", creator)
        self.assertIn("用户直接回复一个非空名称时，视为选择 `2`", creator)
        self.assertIn("已经取得自定义名称后不得重复询问", creator)
        self.assertIn("创建过程中的所有 Agent 自然语言消息都必须以 `<角色名>：` 开头", creator)
        self.assertIn("普通问候、闲聊和可立即回答的问题只发送最终回答", creator)
        self.assertIn("默认静默完成角色核心读取", creator)
        self.assertIn("最终版本始终为正式版", creator)
        self.assertIn("不按版权类别、文本长度或资料完整度限制收集", creator)
        self.assertIn("表达库禁止加入人物介绍", creator)
        self.assertIn("本人或角色真实产生的逐字表达", creator)
        self.assertIn("声纹不能由模型自由概括", creator)
        self.assertIn("人物背景档案", creator)
        self.assertIn("原文卡只标来源语义", creator)
        self.assertIn("证据映射", creator)
        self.assertIn("没有可靠卡就返回空结果", creator)
        self.assertIn("临场感和主动表达必须稀疏", creator)
        runtime = (ROOT / "assets" / "角色人格模板" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("10-人物背景档案.md", runtime)
        self.assertIn("用户询问角色个人事实", runtime)
        self.assertIn("性别相关自称、代词、称谓", runtime)
        self.assertIn("去名盲测", creator)
        self.assertNotIn("官方角色原文", persona_tool.EXACT_CARD_TYPES)
        self.assertNotIn("试用版", creator)


if __name__ == "__main__":
    unittest.main()
