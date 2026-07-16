#!/usr/bin/env python3
"""Create and statically validate Persona.skill character skill folders."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import runtime_lifecycle as lifecycle
import quality_loop as quality


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "角色人格模板"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n", re.DOTALL)
CARD_HEADING_RE = re.compile(
    r"^##\s+([A-Z0-9][A-Z0-9-]*-\d{4})\s*$", re.MULTILINE | re.IGNORECASE
)
SCENE_HEADING_RE = re.compile(r"^##\s+([a-z][a-z-]*)\s+\|", re.MULTILINE)
CASE_HEADING_RE = re.compile(r"^##\s+CASE-\d{2}\s+\|", re.MULTILINE)
SOURCE_HEADING_RE = re.compile(r"^##\s+(SRC-\d{4})\s*$", re.MULTILINE | re.IGNORECASE)
RESEARCH_HEADING_RE = re.compile(r"^###\s+(RESEARCH-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
VOICE_HEADING_RE = re.compile(r"^###\s+(VOICE-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
MICRO_HEADING_RE = re.compile(r"^###\s+(MICRO-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
MODE_HEADING_RE = re.compile(r"^###\s+(MODE-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
CORE_HEADING_RE = re.compile(r"^###\s+(CORE-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
ANTI_HEADING_RE = re.compile(r"^###\s+(ANTI-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
BIO_HEADING_RE = re.compile(r"^###\s+(BIO-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
MIND_HEADING_RE = re.compile(r"^###\s+(MIND-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
EXPR_HEADING_RE = re.compile(r"^###\s+(EXPR-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
BEHAV_HEADING_RE = re.compile(r"^##\s+(BEHAV-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
COMPOSITE_WORK_HEADING_RE = re.compile(
    r"^###\s+(WORK-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE
)
PLACEHOLDER_RE = re.compile(
    r"\{\{[A-Z0-9_]+\}\}|\[待填写[^\]]*\]|\b(?:TODO|TBD)\b", re.IGNORECASE
)

REQUIRED_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/select_dialogues.py",
    "scripts/check_response.py",
    "references/01-角色核心.md",
    "references/02-语言声纹.md",
    "references/03-情绪与关系.md",
    "references/04-工作场景迁移.md",
    "references/05-对白索引.md",
    "references/07-验证用例.md",
    "references/08-来源索引.md",
    "references/09-反角色对照.md",
    "references/10-人物背景档案.md",
)

REQUIRED_CARD_FIELDS = (
    "原作检索标签",
    "标签依据",
    "卡片类型",
    "原文",
    "原文语言",
    "原文质量",
    "中文参考译文",
    "说话人",
    "来源类型",
    "来源位置",
    "作品定位",
    "语境类型",
    "场景编号",
    "场景完整度",
    "前置原文",
    "触发话语",
    "后续原文",
    "对话对象",
    "关系距离",
    "交流目的",
    "互动功能",
    "角色即时反应",
    "互动位置",
    "主动性",
    "主要情绪",
    "情绪强度",
    "情绪转折",
    "非语言反应",
    "画面锚点",
    "语音表现",
    "词汇标记",
    "语法标记",
    "语气标记",
    "口语现象",
    "句式与节奏",
    "识别度",
    "可直接使用",
    "不适用场景",
    "重复限制",
)

ALLOWED_SOURCE_TYPES = {
    "原作明确", "可靠转写", "本人公开表达", "用户补充", "公开资料", "合理推导", "Persona.skill 补齐",
}
EXISTING_EXPRESSION_SOURCE_TYPES = {"原作明确", "可靠转写"}
REAL_PERSON_EXPRESSION_SOURCE_TYPES = {"本人公开表达", "可靠转写"}
PRIMARY_SOURCE_TYPES = EXISTING_EXPRESSION_SOURCE_TYPES | REAL_PERSON_EXPRESSION_SOURCE_TYPES
EXACT_CARD_TYPES = {
    "原文对白", "原文口头禅", "原文独白", "原文发言", "原文采访回答",
    "原文文章", "原文帖子", "原文书信",
}
AUTHORED_CARD_TYPES = {"原创规范对白"}
ALLOWED_CARD_TYPES = EXACT_CARD_TYPES | AUTHORED_CARD_TYPES
SIGNATURE_LEVELS = {"核心", "常用"}
ALLOWED_ORIGINAL_QUALITIES = {"原声核验", "原语言文本核验", "可靠转写核验", "原始版式核验"}
ALLOWED_QUALITIES = ALLOWED_ORIGINAL_QUALITIES | {"译本参考", "原创确认"}
ALLOWED_MEDIA = {"视听", "文字", "混合", "公开表达", "原创"}
ALLOWED_PERSONA_TYPES = {
    "existing-character",
    "composite-character",
    "original-persona",
    "real-person-simulation",
    "composite-original",
}
ALLOWED_INDEX_SOURCE_TYPES = ALLOWED_SOURCE_TYPES
REQUIRED_TAGS = {"speech_act", "trigger", "interaction", "position", "relation", "emotion", "initiative"}
FORBIDDEN_SOURCE_TAGS = {"task_state", "user_state", "intent", "risk", "language"}
REQUIRED_LABEL_EVIDENCE = REQUIRED_TAGS
ALLOWED_LABEL_EVIDENCE = {"原文可见", "上下文可见", "来源明确", "用户确认", "合理推导", "缺失"}
ALLOWED_CONTEXT_TYPES = {
    "对话场景", "叙事场景", "内心独白", "访谈回答", "演讲发言",
    "博客文章", "社交媒体", "书信", "原创设定",
}
CONVERSATIONAL_CONTEXT_TYPES = {"对话场景", "访谈回答"}
NARRATIVE_CONTEXT_TYPES = {"叙事场景", "内心独白"}
SELF_CONTAINED_CONTEXT_TYPES = {"演讲发言", "博客文章", "社交媒体", "书信"}
ALLOWED_SCENE_COMPLETENESS = {"完整", "语境充分", "片段", "孤立摘录", "原创设定"}
COUNTABLE_SCENE_COMPLETENESS = {"完整", "语境充分", "原创设定"}
ALLOWED_EVALUATOR_TYPES = {"human", "independent-agent", "independent-context"}
REQUIRED_VOICE_FIELDS = ("层级", "规律", "证据卡", "证据映射", "检索条件", "反证或边界", "适用条件", "置信度")
REQUIRED_VOICE_LAYERS = {
    "lexicon", "syntax", "ending", "orality", "interaction", "emotion", "relation",
    "translation", "anti-voice",
}
MINIMUM_VOICE_LAYERS = {"lexicon", "syntax", "ending", "orality", "interaction", "anti-voice"}
ALLOWED_VOICE_LAYERS = REQUIRED_VOICE_LAYERS | {"prosody"}
REQUIRED_MICRO_FIELDS = (
    "功能", "触发", "即时反应", "开场节奏", "追问或收束", "证据卡", "证据映射",
    "检索条件", "禁止通用替代", "置信度",
)
REQUIRED_MICRO_FUNCTIONS = {"greeting", "acknowledgement", "gratitude", "apology", "surprise", "closing"}
REQUIRED_MODE_FIELDS = (
    "情绪", "触发", "关系", "角色即时反应", "语言变化", "响应形态", "口语节奏",
    "临场信号", "画面表达", "主动表达", "触发与冷却", "禁止结构", "行动倾向",
    "证据卡", "证据映射", "检索条件", "反证或边界",
)
REQUIRED_ANTI_FIELDS = (
    "模式", "检测信号", "为什么不像", "角色替代结构", "证据卡", "证据映射", "检索条件", "适用场景", "例外",
)
REQUIRED_CORE_RULE_FIELDS = (
    "层级", "结论", "可观察行为", "证据卡", "证据映射", "检索条件", "其他来源", "反证或边界", "适用条件", "置信度",
)
REQUIRED_CORE_LAYERS = {
    "value", "judgment", "desire", "bias", "boundary", "behavior", "relationship",
    "emotion", "identity", "anti-core",
}
REQUIRED_SCENE_FIELDS = (
    "触发", "目标检索", "原作互动功能", "角色即时反应", "候选原文卡", "候选声纹规律",
    "事实嵌入方式", "临场表达策略", "主动表达条件", "冷却与重复", "禁止虚构", "禁止退化",
)
ALLOWED_EVIDENCE_FIELDS = {
    "原文", "交流目的", "互动功能", "角色即时反应", "互动位置", "主动性", "主要情绪",
    "情绪转折", "非语言反应", "画面锚点", "词汇标记", "语法标记", "语气标记", "口语现象", "句式与节奏",
}
REQUIRED_SOURCE_FIELDS = (
    "来源类型", "位置", "原始媒介与版本", "原始语言", "核验方式", "可用范围", "内容摘要", "可靠性", "支持的结论或卡片",
)
REQUIRED_BIO_FIELDS = (
    "类别", "主题", "事实", "角色视角回答要点", "适用问题", "时间或版本", "来源", "置信度", "边界",
)
V2_BIO_FIELDS = ("主观解释", "情绪印记", "联想触发", "可迁移意象", "愿谈程度")
V2_CARD_FIELDS = (
    "版本层", "引用方式", "表面情绪", "内在情绪", "当前目的", "担心的损失", "隐藏内容", "场景结果", "修辞手段",
)
ALLOWED_VERSION_LAYERS = {"primary", "secondary", "popular"}
ALLOWED_QUOTE_USES = {"exact-quote", "paraphrase", "allusion"}
ALLOWED_EFFECT_MATRIX_STATES = {"丰富", "可用", "稀少", "推导", "未知"}
REQUIRED_EFFECT_MATRIX_DIMENSIONS = {
    "背景", "价值", "心理", "情绪", "关系", "声纹", "比喻", "引用", "篇幅", "主动性", "未知边界",
}
REQUIRED_MIND_FIELDS = (
    "触发", "第一判断", "价值或欲望冲突", "担心或防御", "自尊来源", "对用户的真实意图",
    "潜台词", "外在表达", "行动倾向", "证据卡", "背景条目", "证据映射", "边界", "置信度",
)
REQUIRED_EXPR_FIELDS = (
    "解释手法", "比喻或意象来源", "经历回调", "典故或名句政策", "幽默与讽刺", "篇幅档", "绕话与重复",
    "主动表达习惯", "适用触发", "证据卡", "背景条目", "证据映射", "禁用条件", "置信度",
)
REQUIRED_BEHAVIOR_FIELDS = (
    "行为功能", "触发族", "第一反应", "核心取舍", "对用户的关系动作", "情绪轨迹", "话语动作序列",
    "反直觉切入", "人物推理次序", "顾问骨架禁用", "去名识别锚点",
    "形状候选", "可见角色信号", "最小实现", "强度升级", "通用助手近失样本", "相似人物近失样本",
    "区别性边界", "禁用与事实边界", "检索条件", "证据卡", "证据映射", "连接资产", "失败归因", "置信度",
)
REQUIRED_BEHAVIOR_FUNCTIONS = {
    "connect", "explain", "reassure", "disagree", "admit-error", "celebrate",
    "wait", "warn", "clarify", "refuse", "identity", "close",
}
ALLOWED_FAILURE_ATTRIBUTION_LAYERS = {
    "source", "behavior-model", "retrieval", "generation", "runtime", "evaluation",
}
MIND_COVERAGE_MARKERS = {
    "value_conflict": ("价值", "欲望", "取舍"),
    "defense": ("防御", "担心", "害怕"),
    "relationship_intent": ("关系", "用户的真实意图", "靠近", "陪伴"),
    "conflict": ("冲突", "分歧", "不同意"),
    "vulnerability": ("脆弱", "易受伤", "自尊"),
    "unknown_boundary": ("未知", "边界", "不确定", "无法确认"),
}
ALLOWED_VERBOSITY_PROFILES = {"brief", "normal", "extended", "rambling-characteristic"}
ALLOWED_BIO_CATEGORIES = {
    "identity", "gender", "background", "timeline", "relationship", "ability", "preference", "worldview", "faq",
}
REQUIRED_BIO_BASELINE_FIELDS = (
    "姓名与原名", "性别身份", "性别相关称谓与代词", "年龄或生命阶段", "物种或存在类型",
    "社会身份或职业", "所属或阵营", "当前时间点或版本", "自我认知", "基线来源",
)

# Existing people and characters differ greatly in how much source material is
# reasonably available.  "丰富" is the only normal successful target for an
# existing character or real person.  Lower profiles describe work in progress
# and are never eligible for activation: a role may be reported as exhausted
# for audit purposes, but the user-facing Skill must still reach the rich corpus
# floor before it can be distilled, enabled, or presented as complete.
RESEARCH_PROFILES = {
    "丰富": {
        "cards": 80, "unique": 60, "evidence_units": 24, "signature": 12,
        "dimensions": 10, "sources": 3, "primary_sources": 2, "rounds": 3,
    },
    "一般": {
        "cards": 40, "unique": 30, "evidence_units": 15, "signature": 10,
        "dimensions": 8, "sources": 2, "primary_sources": 2, "rounds": 2,
    },
    "稀缺": {
        "cards": 24, "unique": 18, "evidence_units": 8, "signature": 8,
        "dimensions": 6, "sources": 1, "primary_sources": 1, "rounds": 2,
    },
}
RICH_CORPUS_MIN_CARDS = 80
RICH_CORPUS_RECOMMENDED_MAX_CARDS = 300
RESPONSE_CHECKER_CONTRACT_VERSION = 5
RICH_CORPUS_TYPES = {"existing-character", "composite-character", "real-person-simulation"}
REQUIRED_RESEARCH_AUDIT_FIELDS = (
    "资料丰度判定依据", "资料丰度边界说明", "候选表达数", "正式原文卡数", "待核验表达数", "排除表达数",
    "排除原因摘要", "覆盖维度", "最近两轮新增率", "饱和结论",
)
REQUIRED_RESEARCH_ROUND_FIELDS = (
    "查询词、站点、资料类型与语言", "本轮新增检索范围", "本轮候选数", "本轮正式收录数", "本轮待核验数",
    "本轮排除数", "本轮新增率", "新增来源与卡片", "未覆盖指标",
)
MIN_EXHAUSTION_ROUNDS = 4
COMPOSITE_WORK_MIN_COUNT = 2
COMPOSITE_WORK_MIN_CARDS = 4
COMPOSITE_WORK_MIN_UNIQUE = 4
COMPOSITE_WORK_MIN_EVIDENCE_UNITS = 2
COMPOSITE_WORK_MIN_SCENE_DIMENSIONS = 4
COMPOSITE_MAX_SINGLE_WORK_SHARE = 0.45
NON_EXPANSION_SCOPE_RE = re.compile(
    r"^(?:无|没有|未扩大|同上|相同|重复|仅复查|继续复查|既有范围|原范围|不适用|none|n/a)[。.!！]?$",
    re.IGNORECASE,
)
LOCATOR_ONLY_CONTEXT_MARKERS = (
    "以话数与场景标题定位", "资料说明可定位", "由同一官方场景条目定位",
    "见来源页", "见来源索引", "官方场景页以", "定位（", "定位(",
)
TEMPLATED_CONTEXT_MARKERS = (
    "段落记录了与", "中出现当前变化后", "以该卡所录短句回应",
    "相邻转写条目继续记录", "同一事件的发展与其他人的反应",
    "听见当前变化后表态", "当前变化使", "继续行动或给出回应",
)
GENERIC_MAPPING_OBSERVATIONS = {
    "短促直接的说法", "先接住对象再推进", "可见的情绪词", "在事件中采取对应立场",
    "自然的短句反应", "把判断交回具体关系", "短句中的立场表达", "在对话中落实判断",
    "当前字段支持该结论", "该卡支持此规律", "与结论一致", "符合角色风格",
}

REQUIRED_SCENES = {
    "start",
    "clarify",
    "progress",
    "waiting",
    "issue",
    "failed",
    "mistake",
    "tired",
    "disagree",
    "risk",
    "decision",
    "blocked",
    "milestone",
    "complete",
    "close",
}

REQUIRED_SKILL_TERMS = (
    "回复前缀", "每条实际发送的 Agent", "可见消息规则", "每轮加载", "人物背景档案", "对白使用",
    "临场感与主动表达", "delivery_guidance", "证据映射", "事实保护", "停用与恢复", "连续状态",
)
REQUIRED_CORE_TERMS = (
    "身份", "版本", "还原优先级", "原作媒介", "作品原始语言", "回复前缀",
    "创建后当前会话默认启用", "人格内核", "与用户的关系", "声纹摘要", "工作边界",
)
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".txt", ".json"}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    file: str | None = None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str | None]:
    match = FRONTMATTER_RE.search(text)
    if not match:
        return {}, "缺少以 --- 包围的 YAML frontmatter"
    values: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            return {}, f"无法解析 frontmatter 行：{raw_line}"
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return values, None


def card_prefix(slug: str) -> str:
    value = re.sub(r"[^A-Z0-9]", "", slug.upper())[:12]
    return value or "ROLE"


def _clean_name(value: str | None) -> str:
    return (value or "").strip()


def cmd_name_gate(args: argparse.Namespace) -> int:
    """Require an explicit two-choice display-name decision before creation.

    The natural-language skill must show this gate as its first visible action.
    Keeping the check in the deterministic tool also prevents ``init`` from
    being used as an accidental bypass when an agent starts scaffolding first.
    """
    source_name = _clean_name(args.source_name)

    if args.choice is None:
        if not source_name:
            if args.custom_name is not None:
                display_name = _clean_name(args.custom_name)
                if not display_name:
                    print("错误：custom-name 不能为空。", file=sys.stderr)
                    return 2
                print("NAME_GATE_STATUS=accepted")
                print("SOURCE_NAME=")
                print(f"DISPLAY_NAME={display_name}")
                print("NAME_CHOICE=none")
                print("NAME_GATE_REQUIRED=false")
                print("MUST_WAIT_FOR_NAME_CHOICE=false")
                print("CREATE_LOOP_LOCK=active")
                print("RESPONSE_MODE=CONTINUE_TOOL_LOOP")
                print("FEEDBACK_REQUIRED=true")
                print("FEEDBACK_STAGE=名称确认")
                print("NEXT_FEEDBACK=阶段：名称确认；已完成：自定义人物名已确定；下一步：进入资料盘点并开始逐轮采集。")
                return 0
            print("NAME_GATE_STATUS=awaiting-name")
            print("当前创建请求没有指定人物名，创建前必须先设定人物名。")
            print("请直接输入人物名：")
            print("NAME_GATE_REQUIRED=true")
            print("MUST_WAIT_FOR_NAME=true")
            print("CREATE_LOOP_LOCK=waiting-for-user-name")
            print("RESPONSE_MODE=WAIT_FOR_NAME")
            print("FEEDBACK_REQUIRED=true")
            print("FEEDBACK_STAGE=名称确认")
            print("NEXT_FEEDBACK=阶段：名称确认；已完成：发现请求未给人物名；下一步：等待用户先设定人物名，之后才允许调研。")
            print("禁止在设定人物名之前联网、读取资料、初始化目录、蒸馏或生成角色。")
            return 0
        print("NAME_GATE_STATUS=awaiting-choice")
        print(f"原角色名：{source_name}")
        print("创建角色前必须先选择名称：")
        print("1、直接使用原角色名")
        print("2、自定义角色名（用户直接输入名字）")
        print("NAME_GATE_REQUIRED=true")
        print("MUST_WAIT_FOR_NAME_CHOICE=true")
        print("CREATE_LOOP_LOCK=waiting-for-user-name-choice")
        print("RESPONSE_MODE=WAIT_FOR_NAME_CHOICE")
        print("FEEDBACK_REQUIRED=true")
        print("FEEDBACK_STAGE=名称确认")
        print("NEXT_FEEDBACK=阶段：名称确认；已完成：识别到原角色名；下一步：等待用户选择原名或自定义名，之后才允许调研。")
        print("禁止在选择前联网、读取资料、初始化目录、蒸馏或生成角色。")
        return 0

    if not source_name:
        print("错误：没有原角色名时不使用 1/2 选择；请直接提供 custom-name。", file=sys.stderr)
        return 2

    if args.choice == "1":
        if args.custom_name:
            print("错误：选择 1 时不能同时提供 custom-name；请直接使用原角色名。", file=sys.stderr)
            return 2
        display_name = source_name
    else:
        display_name = _clean_name(args.custom_name)
        if not display_name:
            print("错误：选择 2 后必须提供 custom-name（用户直接输入名字）。", file=sys.stderr)
            return 2

    print("NAME_GATE_STATUS=accepted")
    print(f"SOURCE_NAME={source_name}")
    print(f"DISPLAY_NAME={display_name}")
    print(f"NAME_CHOICE={args.choice}")
    print("NAME_GATE_REQUIRED=false")
    print("MUST_WAIT_FOR_NAME_CHOICE=false")
    print("CREATE_LOOP_LOCK=active")
    print("RESPONSE_MODE=CONTINUE_TOOL_LOOP")
    print("FEEDBACK_REQUIRED=true")
    print("FEEDBACK_STAGE=名称确认")
    print("NEXT_FEEDBACK=阶段：名称确认；已完成：显示名已锁定；下一步：进入资料盘点与逐轮采集。")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    source_name = _clean_name(args.source_name)
    selected_name = _clean_name(args.name)
    if args.name_choice not in {"1", "2", "none"}:
        print("错误：创建前必须先完成名称闸门：有原名时选择 1/2；没有原名时先设定人物名。请先运行 name-gate。", file=sys.stderr)
        return 2
    if args.name_choice in {"1", "2"} and not source_name:
        print("错误：选择 1/2 时必须提供 source-name。", file=sys.stderr)
        return 2
    if args.name_choice == "1" and selected_name != source_name:
        print("错误：name-choice=1 时，name 必须与 source-name 相同。", file=sys.stderr)
        return 2
    if args.name_choice == "2" and not selected_name:
        print("错误：name-choice=2 时必须提供自定义 name。", file=sys.stderr)
        return 2
    if args.name_choice == "none" and source_name:
        print("错误：没有指定人物名的流程不能填写 source-name；请直接设定 name。", file=sys.stderr)
        return 2
    if not selected_name:
        print("错误：name 不能为空。", file=sys.stderr)
        return 2
    if not SLUG_RE.fullmatch(args.slug) or len(args.slug) >= 64:
        print("错误：slug 只能包含小写字母、数字和单个连字符，且必须少于 64 字符。", file=sys.stderr)
        return 2

    target = Path(args.output).expanduser().resolve()
    if target.exists():
        print(f"错误：目标已存在，拒绝覆盖：{target}", file=sys.stderr)
        return 2
    if not TEMPLATE_ROOT.is_dir():
        print(f"错误：找不到角色人格模板：{TEMPLATE_ROOT}", file=sys.stderr)
        return 2

    role_slug = args.slug[8:] if args.slug.startswith("persona-") else args.slug
    if not role_slug:
        print("错误：slug 缺少角色标识。", file=sys.stderr)
        return 2
    replacements = {
        "{{PERSONA_NAME}}": selected_name,
        "{{PERSONA_SLUG}}": role_slug,
        "{{PERSONA_SKILL_ID}}": "persona-" + role_slug,
        "{{CARD_PREFIX}}": card_prefix(role_slug),
    }
    if not replacements["{{PERSONA_NAME}}"]:
        print("错误：name 不能为空。", file=sys.stderr)
        return 2

    created = False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(TEMPLATE_ROOT, target)
        created = True
        for path in target.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                text = read_text(path)
                for old, new in replacements.items():
                    text = text.replace(old, new)
                with path.open("w", encoding="utf-8", newline="\n") as handle:
                    handle.write(text)
    except Exception as exc:  # pragma: no cover - cleanup path is environment-specific
        if created and target.exists():
            shutil.rmtree(target)
        print(f"错误：创建失败：{exc}", file=sys.stderr)
        return 1

    print(f"PERSONA_WORKDIR={target}")
    print("PERSONA_BUILD_STATE=INCOMPLETE")
    print("MUST_CONTINUE=true")
    print("CREATE_LOOP_LOCK=active")
    print("RESPONSE_MODE=CONTINUE_TOOL_LOOP")
    print("TERMINAL_ALLOWED=false")
    print("USER_REPORT_ALLOWED=false")
    print("FINAL_REPORT_ALLOWED=false")
    print("STATUS_REPLY_ALLOWED=true")
    print("LOOP_STAGE=RESEARCH")
    print("FEEDBACK_REQUIRED=true")
    print("FEEDBACK_STAGE=初始化")
    print("NEXT_FEEDBACK=阶段：初始化；已完成：角色工作目录与模板已建立；下一步：资料盘点，然后按轮次收集候选、核验、排除并回报数量。")
    print("NEXT_ACTION=立即继续调研并只填写人物身份基线、来源索引与原始表达卡；每批运行 research-gate。闸门通过前禁止批量生成规则、工作迁移和测试。")
    print(f"STAGE_GATE_COMMAND=python scripts/persona_tool.py research-gate \"{target}\"")
    print("禁止在初始化后结束当前任务、等待用户说继续，或把此目录当作已创建的人格 Skill 交付。")
    return 0


def add_issue(
    issues: list[Issue], severity: str, code: str, message: str, path: Path | None, root: Path
) -> None:
    file_value: str | None = None
    if path is not None:
        try:
            file_value = path.relative_to(root).as_posix()
        except ValueError:
            file_value = str(path)
    issues.append(Issue(severity, code, message, file_value))


def placeholder_severity(level: str) -> str:
    return "error" if level == "release" else "warning"


def split_values(value: str) -> set[str]:
    values = re.split(r"[/,，;；、|]", value)
    return {item.strip().lower() for item in values if item.strip() and "待填写" not in item}


def field_value(block: str, field: str) -> str | None:
    match = re.search(rf"^-\s*{re.escape(field)}[：:]\s*(.+?)\s*$", block, re.MULTILINE)
    return match.group(1).strip() if match else None


def field_occurrences(block: str, field: str) -> list[str]:
    return [
        item.strip()
        for item in re.findall(
            rf"^-\s*{re.escape(field)}[：:]\s*(.+?)\s*$", block, re.MULTILINE
        )
    ]


def iter_card_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(CARD_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end]


def iter_source_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(SOURCE_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end]


def iter_research_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(RESEARCH_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end]


def iter_voice_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(VOICE_HEADING_RE.finditer(text))
    boundaries = sorted(item.start() for pattern in (VOICE_HEADING_RE, MICRO_HEADING_RE) for item in pattern.finditer(text))
    for match in matches:
        end = next((position for position in boundaries if position > match.start()), len(text))
        yield match.group(1).upper(), text[match.end() : end]


def iter_micro_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(MICRO_HEADING_RE.finditer(text))
    boundaries = sorted(item.start() for pattern in (VOICE_HEADING_RE, MICRO_HEADING_RE) for item in pattern.finditer(text))
    for match in matches:
        end = next((position for position in boundaries if position > match.start()), len(text))
        yield match.group(1).upper(), text[match.end() : end]


def iter_mode_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(MODE_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end]


def iter_core_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(CORE_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end]


def iter_anti_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(ANTI_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end]


def iter_bio_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(BIO_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end]


def iter_mind_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(MIND_HEADING_RE.finditer(text))
    boundaries = sorted(item.start() for pattern in (MIND_HEADING_RE, EXPR_HEADING_RE) for item in pattern.finditer(text))
    for match in matches:
        end = next((position for position in boundaries if position > match.start()), len(text))
        yield match.group(1).upper(), text[match.end() : end]


def iter_expr_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(EXPR_HEADING_RE.finditer(text))
    boundaries = sorted(item.start() for pattern in (MIND_HEADING_RE, EXPR_HEADING_RE) for item in pattern.finditer(text))
    for match in matches:
        end = next((position for position in boundaries if position > match.start()), len(text))
        yield match.group(1).upper(), text[match.end() : end]


def iter_behavior_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(BEHAV_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end]


def iter_composite_work_blocks(text: str) -> Iterable[tuple[str, str]]:
    """Yield explicit per-work coverage records for composite characters."""
    matches = list(COMPOSITE_WORK_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end]


def iter_scene_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(SCENE_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).lower(), text[match.end() : end]


def iter_case_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(CASE_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        case_id = re.search(r"CASE-\d{2}", match.group(0), re.IGNORECASE)
        if case_id:
            yield case_id.group(0).upper(), text[match.end() : end]


def integer_field(block: str, field: str) -> int | None:
    value = field_value(block, field)
    match = re.fullmatch(r"\s*(\d+)\s*", value or "")
    return int(match.group(1)) if match else None


def percentage_values(block: str, field: str) -> list[float]:
    """Read comma-separated percentages such as ``4%, 2%``."""
    value = field_value(block, field) or ""
    return [float(item) for item in re.findall(r"(\d+(?:\.\d+)?)\s*%", value)]


def parse_tags(value: str | None) -> dict[str, set[str]]:
    if not value:
        return {}
    result: dict[str, set[str]] = {}
    for key, raw in re.findall(r"\b([a-z_]+)\s*=\s*([^;；]+)", value, re.IGNORECASE):
        result[key.lower()] = split_values(raw)
    return result


def parse_label_evidence(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    return {
        key.lower(): raw.strip()
        for key, raw in re.findall(r"\b([a-z_]+)\s*=\s*([^;；]+)", value, re.IGNORECASE)
    }


def parse_evidence_mapping(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    return {
        card_id.upper(): source_field.strip()
        for card_id, source_field in re.findall(
            r"\b([A-Z0-9][A-Z0-9-]*-\d{4})\s*=>\s*([^;；]+)", value, re.IGNORECASE
        )
    }


def split_mapping_observation(value: str) -> tuple[str, str]:
    match = re.match(r"^([^=：]+?)(?:[=：](.+))?$", value.strip())
    if not match:
        return value.strip(), ""
    return match.group(1).strip(), (match.group(2) or "").strip()


def validate_rule_evidence_mapping(
    issues: list[Issue], rule_id: str, block: str, card_blocks: dict[str, str],
    path: Path, root: Path, level: str, code_prefix: str, require_retrieval: bool = True,
) -> None:
    evidence_ids = set(re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", field_value(block, "证据卡") or ""))
    mappings = parse_evidence_mapping(field_value(block, "证据映射"))
    mapped_ids = set(mappings)
    if evidence_ids != mapped_ids:
        missing = sorted(evidence_ids - mapped_ids)
        extra = sorted(mapped_ids - evidence_ids)
        detail = []
        if missing:
            detail.append("缺少映射=" + ", ".join(missing))
        if extra:
            detail.append("额外映射=" + ", ".join(extra))
        add_issue(
            issues, "error" if level == "release" else "warning",
            f"{code_prefix}.evidence_mapping_mismatch",
            f"{rule_id} 的证据卡与证据映射不一致：" + "；".join(detail), path, root,
        )
    for card_id, mapping_value in mappings.items():
        source_field, observation = split_mapping_observation(mapping_value)
        if source_field not in ALLOWED_EVIDENCE_FIELDS:
            add_issue(
                issues, "error" if level == "release" else "warning",
                f"{code_prefix}.evidence_mapping_field_invalid",
                f"{rule_id} 把 {card_id} 映射到无效原始字段：{source_field}", path, root,
            )
            continue
        if not has_substantive_value(observation) or len(observation) < 4:
            add_issue(
                issues, "error" if level == "release" else "warning",
                f"{code_prefix}.evidence_mapping_observation_missing",
                f"{rule_id} 对 {card_id} 只写了字段名，没有记录该字段中支持结论的具体观察；使用“字段=观察”格式",
                path, root,
            )
        normalized_observation = normalize_template_text(observation)
        if observation.strip() in GENERIC_MAPPING_OBSERVATIONS or normalized_observation in {
            normalize_template_text(item) for item in GENERIC_MAPPING_OBSERVATIONS
        }:
            add_issue(
                issues, "error" if level == "release" else "warning",
                f"{code_prefix}.evidence_mapping_observation_generic",
                f"{rule_id} 对 {card_id} 的观察“{observation}”是可批量套用的空泛标签；必须写出该卡字段里实际出现的词、句法、互动或情绪证据",
                path, root,
            )
        card_block = card_blocks.get(card_id)
        if card_block is not None and not has_substantive_value(field_value(card_block, source_field), allow_none=True):
            add_issue(
                issues, "error" if level == "release" else "warning",
                f"{code_prefix}.evidence_mapping_empty",
                f"{rule_id} 映射到 {card_id} 的“{source_field}”，但该字段没有可用证据", path, root,
            )
    if not require_retrieval:
        return
    conditions = parse_tags(field_value(block, "检索条件"))
    if not conditions:
        add_issue(
            issues, "error" if level == "release" else "warning",
            f"{code_prefix}.retrieval_conditions_missing",
            f"{rule_id} 缺少结构化检索条件", path, root,
        )
    invalid_conditions = sorted(set(conditions) - REQUIRED_TAGS)
    if invalid_conditions:
        add_issue(
            issues, "error" if level == "release" else "warning",
            f"{code_prefix}.retrieval_conditions_invalid",
            f"{rule_id} 的检索条件含工作域或未知标签：{', '.join(invalid_conditions)}", path, root,
        )


def has_exact_original_text(value: str | None) -> bool:
    if not value or PLACEHOLDER_RE.search(value):
        return False
    normalized = value.strip().strip("`'\"“”‘’").lower()
    return bool(normalized) and normalized not in {"无", "none", "n/a", "不适用"} and not normalized.startswith("无（")


def normalize_original_text(value: str) -> str:
    """Normalize only for duplicate detection; keep the stored original untouched."""
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def normalize_template_text(value: str) -> str:
    """Remove serial numbers and quoted payloads so copy-filled prose cannot fake diversity."""
    text = value.casefold()
    text = re.sub(r"[“”‘’\"'`][^“”‘’\"'`]*[“”‘’\"'`]", " 引文 ", text)
    text = re.sub(r"\b(?:core|voice|mode|anti|src|case)-\d+\b", " 编号 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[a-z0-9][a-z0-9-]*-\d{4}\b", " 卡片 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+\b|[０-９]+", " 数字 ", text)
    for layer in sorted(REQUIRED_CORE_LAYERS | ALLOWED_VOICE_LAYERS, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(layer)}\b", " 层级 ", text, flags=re.IGNORECASE)
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def normalize_research_scope(value: str | None) -> str:
    """Normalize a research scope for repeated-round detection."""
    if not value:
        return ""
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def is_substantive_research_expansion(value: str | None) -> bool:
    """A later round must name a new source family, language, version or query scope."""
    if not has_substantive_value(value):
        return False
    return not bool(NON_EXPANSION_SCOPE_RE.fullmatch((value or "").strip()))


def context_is_missing(value: str | None) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    if normalized in {"无", "none", "n/a", "不适用"} or normalized.startswith("无（"):
        return True
    return any(
        marker in normalized
        for marker in ("缺失", "未知", "不明", "未提供", "未逐句标出", "无法确认", "无法定位")
    )


def context_is_grounded(value: str | None) -> bool:
    """Return true only for actual quoted context or a concrete scene summary.

    A source locator belongs in 来源位置/作品定位.  Repeating that a page can
    locate the scene is not itself the preceding line, trigger, or aftermath.
    """
    if context_is_missing(value):
        return False
    normalized = (value or "").strip().lower()
    return not any(
        marker in normalized
        for marker in LOCATOR_ONLY_CONTEXT_MARKERS + TEMPLATED_CONTEXT_MARKERS
    )


def structured_record_value(text: str, key: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def structured_record_int(text: str, key: str) -> int | None:
    value = structured_record_value(text, key)
    return int(value) if value and value.isdigit() else None


def structured_record_items(text: str) -> list[tuple[str, dict[str, object]]]:
    """Parse ``ITEM-01: {json}`` rows without accepting bare pass markers."""
    result: list[tuple[str, dict[str, object]]] = []
    for match in re.finditer(r"^(ITEM-\d+)[：:]\s*(.+?)\s*$", text, re.MULTILINE):
        raw = match.group(2).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            result.append((match.group(1).upper(), payload))
    return result


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def persona_bundle_sha256(root: Path) -> str:
    """Hash the persona implementation while excluding mutable evaluation artifacts."""
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in {"tests", "__pycache__"}:
            continue
        # Validation cases describe how the persona is tested; they are not part
        # of the persona behavior being evaluated.  Keeping them out of the
        # subject hash lets an evaluator record scores without invalidating its
        # own attestation.
        if relative.as_posix() == "references/07-验证用例.md":
            continue
        if "__pycache__" in relative.parts or path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def read_runtime_samples(path: Path) -> list[dict[str, str]]:
    try:
        payload = json.loads(read_text(path))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    result: list[dict[str, str]] = []
    for index, item in enumerate(payload, start=1):
        if isinstance(item, str):
            prompt, response = f"sample-{index}", item
            conversation_id, turn, previous_turn = "", "", ""
        elif isinstance(item, dict):
            prompt = str(item.get("prompt") or item.get("input") or "")
            response = str(item.get("response") or item.get("text") or "")
            conversation_id = str(item.get("conversation_id") or "").strip()
            turn = str(item.get("turn") or "").strip()
            previous_turn = str(item.get("previous_turn") or "").strip()
        else:
            continue
        if prompt.strip() and response.strip():
            result.append(
                {
                    "prompt": prompt.strip(),
                    "response": response.strip(),
                    "generation_readiness": str(item.get("generation_readiness") or "unknown").strip().lower()
                    if isinstance(item, dict) else "unknown",
                    "conversation_id": conversation_id,
                    "turn": turn,
                    "previous_turn": previous_turn,
                    "structured": "yes" if isinstance(item, dict) else "no",
                }
            )
    return result


def is_label_like_prompt(value: str) -> bool:
    """Reject test labels that cannot establish a real user situation."""
    text = re.sub(r"\s+", " ", value.strip())
    if not text:
        return True
    # A single ASCII token (hello, risk, pause, CASE-01, ...) is a fixture
    # label, not a natural-language turn.  Real English requests contain
    # multiple words or punctuation/context; Chinese prompts are checked by
    # the minimum substantive length below.
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,40}", text):
        return True
    compact = re.sub(r"[\W_]", "", text, flags=re.UNICODE)
    return len(compact) < 4


def normalized_evaluation_reason(value: str) -> str:
    text = re.sub(r"ITEM[-_]?\d+|第\s*\d+\s*条?", "", value.casefold())
    text = re.sub(r"(?:样本|话轮|评估|检查器|记录)\s*\d+", "", text)
    text = re.sub(r"\d+", "", text)
    text = re.sub(r"\s+", "", text)
    return text.strip()


def response_fragments(value: str) -> list[str]:
    """Return substantive sentence fragments for mechanical-repetition checks."""
    text = re.sub(r"^[^：:]{1,40}[：:]", "", value.strip())
    fragments = []
    for part in re.split(r"[。！？!?；;\n]+", text):
        normalized = re.sub(r"\s+", "", part).strip("，,、:：\"'“”‘’")
        if len(normalized) >= 4:
            fragments.append(normalized.casefold())
    return fragments


def resolve_record_path(root: Path, value: str | None) -> Path | None:
    if not has_substantive_value(value):
        return None
    candidate = Path(value or "")
    if candidate.is_absolute():
        return None
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return None
    return resolved


def extract_claimed_card_ids(value: str | None) -> set[str]:
    if not value:
        return set()
    result = {item.upper() for item in re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", value, re.IGNORECASE)}
    range_re = re.compile(
        r"\b([A-Z0-9][A-Z0-9-]*)-(\d{4})\s*(?:至|到|~|～|—|–)\s*(?:([A-Z0-9][A-Z0-9-]*)-)?(\d{4})\b",
        re.IGNORECASE,
    )
    for match in range_re.finditer(value):
        first_prefix, first_raw, second_prefix, second_raw = match.groups()
        prefix = first_prefix.upper()
        if second_prefix and second_prefix.upper() != prefix:
            continue
        first, second = int(first_raw), int(second_raw)
        if second < first or second - first > 1000:
            continue
        result.update(f"{prefix}-{index:04d}" for index in range(first, second + 1))
    return result


def add_semantic_diversity_issues(
    issues: list[Issue],
    blocks: list[tuple[str, str]],
    fields: tuple[str, ...],
    code: str,
    label: str,
    path: Path,
    root: Path,
    level: str,
) -> int:
    if len(blocks) < 4:
        return 0
    minimum = max(3, (len(blocks) + 1) // 2)
    failures: list[str] = []
    for field in fields:
        values = [
            normalize_template_text(field_value(block, field) or "")
            for _, block in blocks
            if has_substantive_value(field_value(block, field), allow_none=True)
        ]
        unique_count = len({value for value in values if value})
        if unique_count < minimum:
            failures.append(f"{field}={unique_count}/{len(blocks)}")
    if failures:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            code,
            f"{label}存在批量模板化，至少需要 {minimum} 种实质不同表达；" + "，".join(failures),
            path,
            root,
        )
        return 1
    return 0


def has_substantive_value(value: str | None, allow_none: bool = False) -> bool:
    if not value or PLACEHOLDER_RE.search(value):
        return False
    normalized = value.strip().lower()
    if not normalized:
        return False
    if normalized in {"已填写", "待填写", "待确认", "unknown"}:
        return False
    if not allow_none and (normalized in {"无", "none", "n/a", "不适用"} or normalized.startswith("无（")):
        return False
    return True


def extract_reply_prefix(text: str) -> str | None:
    match = re.search(r"^\s*-\s*(?:固定)?回复前缀[：:]\s*(.+?)\s*$", text, re.MULTILINE)
    return match.group(1).strip().strip("`") if match else None


def validate_skill(root: Path, level: str) -> dict[str, object]:
    issues: list[Issue] = []
    metrics = {
        "persona_type": "unknown",
        "version": "unknown",
        "persona_asset_version": 1,
        "research_status": "unknown",
        "coverage_path": "unknown",
        "research_expansion_recorded": False,
        "research_rounds": 0,
        "research_expansion_rounds": 0,
        "research_candidates": 0,
        "research_formal": 0,
        "research_pending": 0,
        "research_rejected": 0,
        "research_round_summary": [],
        "rich_corpus_ready": False,
        "rich_corpus_recommended_max_cards": RICH_CORPUS_RECOMMENDED_MAX_CARDS,
        "cards": 0,
        "exact_original_cards": 0,
        "performance_verified_cards": 0,
        "canonical_authored_cards": 0,
        "distinct_source_scenes": 0,
        "distinct_evidence_units": 0,
        "context_complete_cards": 0,
        "signature_cards": 0,
        "derived_cards": 0,
        "distinct_emotions_and_intents": 0,
        "voice_rules": 0,
        "voice_layers": 0,
        "voice_evidence_cards": 0,
        "micro_rules": 0,
        "micro_functions": 0,
        "anti_rules": 0,
        "anti_evidence_cards": 0,
        "core_rules": 0,
        "core_layers": 0,
        "core_evidence_cards": 0,
        "emotion_modes": 0,
        "mode_dimensions": 0,
        "work_scenes": 0,
        "validation_cases": 0,
        "sources": 0,
        "original_sources": 0,
        "biography_entries": 0,
        "biography_categories": 0,
        "biography_baseline_complete": False,
        "mind_rules": 0,
        "expression_rules": 0,
        "behavior_rules": 0,
        "behavior_functions": 0,
        "behavior_function_coverage_complete": False,
        "quality_loop_pass": False,
        "quality_loop_status": "missing",
        "quality_loop_prompt_count": 0,
        "quality_loop_blind_target_count": 0,
        "quality_loop_generic_control_count": 0,
        "quality_loop_similar_role_count": 0,
        "quality_loop_total_score": 0,
        "subjective_memory_entries": 0,
        "analogy_domains": 0,
        "quotation_policy_complete": False,
        "verbosity_profile_complete": False,
        "character_presence_coverage": 0,
        "effect_matrix_rows": 0,
        "effect_matrix_complete": False,
        "composite_work_count": 0,
        "composite_work_coverage_complete": False,
        "composite_work_cards_min": 0,
        "composite_work_evidence_min": 0,
        "composite_work_scene_dimensions_min": 0,
        "composite_work_card_share_max": 0.0,
        "composite_work_gaps": [],
        "composite_detected_work_counts": [],
        "independent_quality_pass": False,
        "runtime_prompt_count": 0,
        "runtime_prompt_natural_count": 0,
        "runtime_prompt_unique_ratio": 0.0,
        "runtime_repeated_fragment_max": 0,
        "evaluation_reason_unique_ratio": 0.0,
        "independent_report_consistent": True,
        "semantic_diversity_failures": 0,
        "rule_evidence_mappings": 0,
    }

    if not root.is_dir():
        add_issue(issues, "error", "path.not_directory", "目标不是目录或不存在", root, root)
        return {"valid": False, "level": level, "path": str(root), "metrics": metrics, "issues": [asdict(x) for x in issues]}

    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file():
            add_issue(issues, "error", "file.missing", f"缺少必要文件：{relative}", path, root)

    skill_path = root / "SKILL.md"
    skill_prefix: str | None = None
    if skill_path.is_file():
        skill_text = read_text(skill_path)
        metadata, metadata_error = parse_frontmatter(skill_text)
        if metadata_error:
            add_issue(issues, "error", "frontmatter.invalid", metadata_error, skill_path, root)
        else:
            keys = set(metadata)
            if keys != {"name", "description"}:
                add_issue(
                    issues,
                    "error",
                    "frontmatter.keys",
                    "frontmatter 必须且只能包含 name 和 description",
                    skill_path,
                    root,
                )
            name = metadata.get("name", "")
            if not SLUG_RE.fullmatch(name) or len(name) >= 64:
                add_issue(issues, "error", "frontmatter.name", "name 必须是少于 64 字符的小写连字符标识", skill_path, root)
            elif not lifecycle.ROLE_ID_RE.fullmatch(name):
                add_issue(
                    issues,
                    "error",
                    "frontmatter.persona_id",
                    "生成角色的 name 必须使用 persona-<ascii-slug> 稳定 ID",
                    skill_path,
                    root,
                )
            description = metadata.get("description", "").strip()
            if not description:
                add_issue(issues, "error", "frontmatter.description", "description 不能为空", skill_path, root)
            elif len(description) > 1024:
                add_issue(issues, "error", "frontmatter.description_length", "description 不能超过 1024 字符", skill_path, root)
        for term in REQUIRED_SKILL_TERMS:
            if term not in skill_text:
                add_issue(issues, "error", "skill.section_missing", f"SKILL.md 缺少运行章节：{term}", skill_path, root)
        skill_prefix = extract_reply_prefix(skill_text)
        if not skill_prefix:
            add_issue(issues, "error", "persona.prefix_missing", "SKILL.md 缺少固定回复前缀", skill_path, root)
        elif not skill_prefix.endswith("："):
            add_issue(issues, "error", "persona.prefix_format", "固定回复前缀必须以全角冒号：结尾", skill_path, root)

    core_path = root / "references" / "01-角色核心.md"
    core_prefix: str | None = None
    persona_type = "unknown"
    formal_version = "unknown"
    persona_asset_version = 1
    original_medium = "unknown"
    original_language = "unknown"
    core_text = ""
    if core_path.is_file():
        core_text = read_text(core_path)
        for term in REQUIRED_CORE_TERMS:
            if term not in core_text:
                add_issue(issues, "error", "core.section_missing", f"角色核心缺少章节：{term}", core_path, root)
        core_prefix = extract_reply_prefix(core_text)
        if not core_prefix:
            add_issue(issues, "error", "persona.core_prefix_missing", "角色核心缺少回复前缀", core_path, root)
        raw_persona_type = field_value(core_text, "人格来源类型")
        if raw_persona_type and not PLACEHOLDER_RE.search(raw_persona_type):
            persona_type = raw_persona_type.strip().lower()
        if persona_type not in ALLOWED_PERSONA_TYPES:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "persona.type_invalid",
                "人格来源类型必须是 existing-character、composite-character、original-persona、real-person-simulation 或 composite-original",
                core_path,
                root,
            )
        raw_version = field_value(core_text, "版本")
        if raw_version and not PLACEHOLDER_RE.search(raw_version):
            formal_version = raw_version.strip()
        raw_asset_version = field_value(core_text, "人格资产版本")
        if raw_asset_version and not PLACEHOLDER_RE.search(raw_asset_version):
            try:
                persona_asset_version = int(raw_asset_version)
            except ValueError:
                persona_asset_version = 0
        if persona_asset_version not in {1, 2, 3}:
            add_issue(
                issues, "error" if level == "release" else "warning", "persona.asset_version_invalid",
                "人格资产版本必须是 1、2 或 3", core_path, root,
            )
        elif persona_asset_version == 1:
            add_issue(
                issues, "warning", "persona.asset_v1_legacy",
                "当前角色仍使用人物资产 v1；保持兼容，但建议迁移心理机制、主观记忆与表达策略", core_path, root,
            )
        if level == "release" and formal_version != "正式版":
            add_issue(
                issues,
                "error",
                "persona.version_invalid",
                "最终角色人格的版本必须明确写为“正式版”",
                core_path,
                root,
            )
        raw_medium = field_value(core_text, "原作媒介")
        if raw_medium and not PLACEHOLDER_RE.search(raw_medium):
            original_medium = raw_medium.strip()
        if original_medium not in ALLOWED_MEDIA:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "persona.medium_invalid",
                "原作媒介必须是视听、文字、混合、公开表达或原创",
                core_path,
                root,
            )
        raw_language = field_value(core_text, "作品原始语言")
        if raw_language and not PLACEHOLDER_RE.search(raw_language):
            original_language = raw_language.strip()
        if level == "release" and not has_substantive_value(raw_language):
            add_issue(issues, "error", "persona.original_language_missing", "缺少作品原始语言", core_path, root)
        fidelity_priority = field_value(core_text, "还原优先级")
        if level == "release" and fidelity_priority != "角色还原第一":
            add_issue(
                issues,
                "error",
                "persona.fidelity_priority_missing",
                "还原优先级必须明确写为“角色还原第一”",
                core_path,
                root,
            )
    metrics["persona_type"] = persona_type
    metrics["version"] = formal_version
    metrics["persona_asset_version"] = persona_asset_version
    metrics["original_medium"] = original_medium
    metrics["original_language"] = original_language
    metrics["composite_work_coverage_complete"] = persona_type != "composite-character"

    strategy_path = root / "references" / "11-心理机制与表达策略.md"
    if persona_asset_version >= 2 and not strategy_path.is_file():
        add_issue(
            issues, "error", "file.missing_v2", "人物资产 v2 缺少 references/11-心理机制与表达策略.md",
            strategy_path, root,
        )
    behavior_path = root / "references" / "12-行为辨识模型.md"
    if persona_asset_version >= 3 and not behavior_path.is_file():
        add_issue(
            issues, "error", "file.missing_v3", "人物资产 v3 缺少 references/12-行为辨识模型.md",
            behavior_path, root,
        )
    if persona_asset_version == 2:
        add_issue(
            issues, "warning", "persona.asset_v2_legacy",
            "当前角色使用人物资产 v2；保持兼容，但新建角色应迁移到可执行行为辨识与真实质量循环 v3", core_path, root,
        )

    sources_path = root / "references" / "08-来源索引.md"
    sources_text = read_text(sources_path) if sources_path.is_file() else ""
    research_status = field_value(sources_text, "调研状态") or "unknown"
    research_profile = field_value(sources_text, "资料丰度") or "unknown"
    profile_targets = RESEARCH_PROFILES.get(research_profile)
    research_blocks = list(iter_research_blocks(sources_text))
    research_rounds = len(research_blocks)
    research_rounds_complete = all(
        all(
            has_substantive_value(field_value(block, field), allow_none=True)
            for field in REQUIRED_RESEARCH_ROUND_FIELDS
        )
        and all(
            integer_field(block, field) is not None
            for field in ("本轮候选数", "本轮正式收录数", "本轮待核验数", "本轮排除数")
        )
        and len(percentage_values(block, "本轮新增率")) == 1
        for _, block in research_blocks
    )
    research_scope_values = [field_value(block, "本轮新增检索范围") for _, block in research_blocks]
    substantive_expansion_scopes = [
        value for index, value in enumerate(research_scope_values)
        if index == 0 or is_substantive_research_expansion(value)
    ]
    normalized_expansion_scopes = [
        normalize_research_scope(value) for value in substantive_expansion_scopes if value
    ]
    repeated_expansion_scopes = sorted(
        scope for scope, count in Counter(normalized_expansion_scopes).items() if scope and count > 1
    )
    later_rounds_without_expansion = [
        research_blocks[index][0]
        for index, value in enumerate(research_scope_values)
        if index > 0 and not is_substantive_research_expansion(value)
    ]
    expansion_record = field_value(sources_text, "扩大范围记录")
    research_audit_values = {
        field: field_value(sources_text, field) for field in REQUIRED_RESEARCH_AUDIT_FIELDS
    }
    research_audit_complete = all(
        has_substantive_value(value) for value in research_audit_values.values()
    )
    candidate_material_count = integer_field(sources_text, "候选表达数")
    declared_formal_cards = integer_field(sources_text, "正式原文卡数")
    pending_material_count = integer_field(sources_text, "待核验表达数")
    rejected_material_count = integer_field(sources_text, "排除表达数")
    saturation_rates = percentage_values(sources_text, "最近两轮新增率")
    saturation_conclusion = research_audit_values["饱和结论"] or ""
    saturation_complete = (
        len(saturation_rates) >= 2
        and max(saturation_rates[-2:]) <= 5.0
        and ("已饱和" in saturation_conclusion or "已穷尽" in saturation_conclusion)
    )
    research_fields = {
        "初始检索范围": field_value(sources_text, "初始检索范围"),
        "检查的站点与资料类型": field_value(sources_text, "检查的站点与资料类型"),
        "检查的版本、别名与语言": field_value(sources_text, "检查的版本、别名与语言"),
        "各轮新增结果": field_value(sources_text, "各轮新增结果"),
        "未达到目标的指标与原因": field_value(sources_text, "未达到目标的指标与原因"),
    }
    expansion_recorded = has_substantive_value(expansion_record)
    exhaustion_complete = (
        research_status == "已穷尽"
        and expansion_recorded
        and research_rounds >= MIN_EXHAUSTION_ROUNDS
        and research_rounds_complete
        and not later_rounds_without_expansion
        and not repeated_expansion_scopes
        and research_audit_complete
        and all(has_substantive_value(value) for value in research_fields.values())
    )
    if level == "release" and research_status not in {"进行中", "达标", "已穷尽"}:
        add_issue(
            issues,
            "error",
            "research.status_invalid",
            "调研状态必须是“进行中”“达标”或“已穷尽”",
            sources_path,
            root,
        )
    if level == "release" and research_status == "已穷尽" and not exhaustion_complete:
        missing = [name for name, value in research_fields.items() if not has_substantive_value(value)]
        if not expansion_recorded:
            missing.insert(0, "扩大范围记录")
        if research_rounds < MIN_EXHAUSTION_ROUNDS:
            missing.insert(0, f"至少 {MIN_EXHAUSTION_ROUNDS} 个实质扩展的 RESEARCH 调研轮次")
        elif not research_rounds_complete:
            missing.insert(0, "RESEARCH 调研轮次的查询、结果或缺口字段")
        add_issue(
            issues,
            "error",
            "research.exhaustion_incomplete",
            "已穷尽必须包含至少一次实质扩大及完整覆盖记录，缺少：" + ", ".join(missing),
            sources_path,
            root,
        )
    if level == "release" and persona_type in {"existing-character", "composite-character", "real-person-simulation"}:
        first_research_heading = RESEARCH_HEADING_RE.search(sources_text)
        research_header = sources_text[: first_research_heading.start()] if first_research_heading else sources_text
        for field in ("调研状态", "资料丰度", *REQUIRED_RESEARCH_AUDIT_FIELDS):
            occurrences = field_occurrences(research_header, field)
            if len(occurrences) > 1:
                add_issue(
                    issues,
                    "error",
                    "research.duplicate_audit_field",
                    f"调研覆盖记录中的“{field}”重复出现 {len(occurrences)} 次；必须保留唯一、可审计的结论",
                    sources_path,
                    root,
                )
        if research_profile not in RESEARCH_PROFILES:
            add_issue(
                issues, "error", "research.profile_invalid",
                "资料丰度必须是“丰富”“一般”或“稀缺”", sources_path, root,
            )
        if not research_audit_complete:
            missing = [name for name, value in research_audit_values.items() if not has_substantive_value(value)]
            add_issue(
                issues, "error", "research.audit_incomplete",
                "调研审计缺少：" + ", ".join(missing), sources_path, root,
            )
        if research_status == "达标" and research_profile != "丰富":
            add_issue(
                issues, "error", "research.non_rich_cannot_pass",
                "现有角色或现实人物只有“丰富”档可以标为达标；“一般”或“稀缺”必须继续扩大范围，确实无资料后走“已穷尽”路径",
                sources_path, root,
            )
        downgrade_text = " ".join(
            filter(
                None,
                (
                    research_audit_values.get("资料丰度判定依据"),
                    research_audit_values.get("资料丰度边界说明"),
                ),
            )
        )
        missing_medium_evidence = re.search(
            r"(?:未取得|未获得|没有|缺少|无法取得|无法获得).{0,18}(?:字幕|剧本|音频|原声|连续对话)"
            r"|(?:字幕|剧本|音频|原声|连续对话).{0,18}(?:未取得|未获得|没有|缺少|无法取得|无法获得)",
            downgrade_text,
        )
        if research_profile != "丰富" and missing_medium_evidence:
            add_issue(
                issues,
                "error",
                "research.profile_downgraded_by_missing_medium",
                "不得因为缺少字幕、剧本、音频、原声或连续话轮把资料丰度降档；必须按实际可得表达规模和覆盖范围判定",
                sources_path,
                root,
            )
        required_rounds = int((profile_targets or {}).get("rounds", 2))
        if research_status == "达标" and research_rounds < required_rounds:
            add_issue(
                issues, "error", "research.rounds_low",
                f"{research_profile}资料至少需要 {required_rounds} 个有记录的调研轮次，当前为 {research_rounds}",
                sources_path, root,
            )
        if research_status == "达标" and not saturation_complete:
            add_issue(
                issues, "error", "research.not_saturated",
                "达标前必须记录最近两轮新增率且均不高于 5%，并明确写出“已饱和”；不能因达到最低数量立即停止",
                sources_path, root,
            )
        if research_status == "达标" and pending_material_count not in {None, 0}:
            add_issue(
                issues, "error", "research.pending_unresolved",
                f"达标时仍有 {pending_material_count} 条待核验表达；必须继续核验、明确排除，或在确实穷尽后改走“已穷尽”路径",
                sources_path, root,
            )
        if persona_type == "composite-character" and research_status == "已穷尽" and pending_material_count not in {None, 0}:
            add_issue(
                issues, "error", "research.pending_unresolved",
                f"跨作品集合标记已穷尽但仍有 {pending_material_count} 条待核验表达；必须逐片核验或明确排除，不能用未处理候选掩盖作品覆盖缺口",
                sources_path, root,
            )
        if research_blocks and not research_rounds_complete:
            add_issue(
                issues, "error", "research.round_audit_incomplete",
                "每个 RESEARCH 轮次都必须记录查询范围、新增检索范围、本轮候选/正式/待核验/排除数量、本轮新增率、新增内容和未覆盖指标",
                sources_path, root,
            )
        if later_rounds_without_expansion:
            add_issue(
                issues, "error", "research.round_no_expansion",
                "后续调研轮次必须明确新增来源类别、站点域、语言、版本、别名或场景范围；以下轮次只是复查或未扩大："
                + ", ".join(later_rounds_without_expansion),
                sources_path, root,
            )
        if repeated_expansion_scopes:
            add_issue(
                issues, "error", "research.round_scope_repeated",
                "不同调研轮次重复声明相同的新增检索范围；重复复查不能算新的扩展轮次",
                sources_path, root,
            )
        round_rates = [
            percentage_values(block, "本轮新增率")[0]
            for _, block in research_blocks
            if len(percentage_values(block, "本轮新增率")) == 1
        ]
        if len(round_rates) >= 2 and len(saturation_rates) >= 2 and round_rates[-2:] != saturation_rates[-2:]:
            add_issue(
                issues, "error", "research.saturation_rate_mismatch",
                "调研覆盖记录中的最近两轮新增率必须与最后两个 RESEARCH 轮次的本轮新增率一致",
                sources_path, root,
            )
        if None in {candidate_material_count, declared_formal_cards, pending_material_count, rejected_material_count}:
            add_issue(
                issues, "error", "research.counts_invalid",
                "候选表达数、正式原文卡数、待核验表达数和排除表达数必须填写为整数",
                sources_path, root,
            )
        elif candidate_material_count != (declared_formal_cards + pending_material_count + rejected_material_count):
            add_issue(
                issues, "error", "research.counts_inconsistent",
                "候选表达数必须等于正式、待核验与排除资料数之和，避免遗漏或重复统计",
                sources_path, root,
            )
    metrics["research_status"] = research_status
    metrics["research_profile"] = research_profile
    metrics["research_saturated"] = saturation_complete
    metrics["research_candidates"] = candidate_material_count or 0
    metrics["research_formal"] = declared_formal_cards or 0
    metrics["research_pending"] = pending_material_count or 0
    metrics["research_rejected"] = rejected_material_count or 0
    metrics["research_expansion_recorded"] = expansion_recorded
    metrics["research_rounds"] = research_rounds
    metrics["research_expansion_rounds"] = len(normalized_expansion_scopes)
    metrics["research_round_summary"] = [
        f"{round_id}:候选{integer_field(block, '本轮候选数') or 0}/正式{integer_field(block, '本轮正式收录数') or 0}/"
        f"待核验{integer_field(block, '本轮待核验数') or 0}/排除{integer_field(block, '本轮排除数') or 0}/"
        f"新增率{(percentage_values(block, '本轮新增率') or [0])[0]:g}%"
        for round_id, block in research_blocks
    ]

    if skill_prefix and core_prefix and skill_prefix != core_prefix:
        add_issue(
            issues,
            "error",
            "persona.prefix_mismatch",
            f"SKILL.md 与角色核心的回复前缀不一致：{skill_prefix} / {core_prefix}",
            core_path,
            root,
        )

    all_text_paths = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES]
    placeholder_count = 0
    for path in all_text_paths:
        text = read_text(path)
        count = len(PLACEHOLDER_RE.findall(text))
        if count:
            placeholder_count += count
            add_issue(
                issues,
                placeholder_severity(level),
                "content.placeholder",
                f"仍有 {count} 个模板占位符",
                path,
                root,
            )

    library_paths = sorted(
        path
        for path in (root / "references").rglob("*对白库*.md")
        if path.is_file() and "索引" not in path.name
    ) if (root / "references").is_dir() else []
    if not library_paths:
        add_issue(issues, "error", "dialogue.library_missing", "没有找到对白库文件", root / "references", root)

    seen_ids: dict[str, Path] = {}
    all_ids: list[str] = []
    dimensions: set[str] = set()
    referenced_source_ids: set[str] = set()
    original_referenced_source_ids: set[str] = set()
    original_card_sources: dict[str, set[str]] = {}
    card_source_refs: dict[str, set[str]] = {}
    exact_original_card_ids: set[str] = set()
    original_language_card_ids: set[str] = set()
    performance_verified_card_ids: set[str] = set()
    layout_verified_card_ids: set[str] = set()
    canonical_authored_card_ids: set[str] = set()
    distinct_source_scenes: set[str] = set()
    context_complete_card_ids: set[str] = set()
    card_scene_ids: dict[str, str] = {}
    card_blocks_by_id: dict[str, str] = {}
    card_qualities: dict[str, str] = {}
    signature_card_ids: set[str] = set()
    normalized_original_owners: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    noncanonical_card_ids: set[str] = set()
    annotation_values: dict[str, list[tuple[str, str, Path]]] = defaultdict(list)
    missing_label_evidence_cards: list[tuple[str, Path]] = []
    for path in library_paths:
        text = read_text(path)
        for card_id, block in iter_card_blocks(text):
            all_ids.append(card_id)
            card_blocks_by_id[card_id] = block
            if card_id in seen_ids:
                add_issue(issues, "error", "dialogue.duplicate_id", f"对白编号重复：{card_id}", path, root)
            else:
                seen_ids[card_id] = path
            for field in REQUIRED_CARD_FIELDS:
                value = field_value(block, field)
                if value is None:
                    if field == "标签依据":
                        missing_label_evidence_cards.append((card_id, path))
                    else:
                        add_issue(issues, "error", "dialogue.field_missing", f"{card_id} 缺少字段：{field}", path, root)
                elif field in {"交流目的", "主要情绪"}:
                    dimensions.update(split_values(value))
            card_type = field_value(block, "卡片类型")
            if persona_asset_version >= 2:
                for field in V2_CARD_FIELDS:
                    if field_value(block, field) is None:
                        add_issue(
                            issues, "error" if level == "release" else "warning", "dialogue.v2_field_missing",
                            f"{card_id} 缺少人物资产 v2 字段：{field}；无法确认时也必须明确写缺失或未知", path, root,
                        )
                version_layer = (field_value(block, "版本层") or "").strip().lower()
                quote_use = (field_value(block, "引用方式") or "").strip().lower()
                if version_layer and not PLACEHOLDER_RE.search(version_layer) and version_layer not in ALLOWED_VERSION_LAYERS:
                    add_issue(
                        issues, "error" if level == "release" else "warning", "dialogue.version_layer_invalid",
                        f"{card_id} 的版本层无效：{version_layer}", path, root,
                    )
                if quote_use and not PLACEHOLDER_RE.search(quote_use) and quote_use not in ALLOWED_QUOTE_USES:
                    add_issue(
                        issues, "error" if level == "release" else "warning", "dialogue.quote_use_invalid",
                        f"{card_id} 的引用方式无效：{quote_use}", path, root,
                    )
                if card_type in EXACT_CARD_TYPES and quote_use and not PLACEHOLDER_RE.search(quote_use) and quote_use != "exact-quote":
                    add_issue(
                        issues, "error" if level == "release" else "warning", "dialogue.exact_card_quote_use_invalid",
                        f"{card_id} 保存逐字原文，引用方式必须是 exact-quote", path, root,
                    )
            if card_type and not PLACEHOLDER_RE.search(card_type) and card_type not in ALLOWED_CARD_TYPES:
                add_issue(
                    issues,
                    "error",
                    "dialogue.card_type_invalid",
                    f"{card_id} 的卡片类型无效：{card_type}",
                    path,
                    root,
                )
            if persona_type in {"existing-character", "composite-character", "real-person-simulation"}:
                if card_type and not PLACEHOLDER_RE.search(card_type) and card_type not in EXACT_CARD_TYPES:
                    add_issue(
                        issues,
                        "error",
                        "dialogue.non_original_card",
                        f"{card_id} 不是逐字原文卡；现有角色对白库禁止用摘要、推导或工作改写充数",
                        path,
                        root,
                    )
                    noncanonical_card_ids.add(card_id)
            elif card_type and not PLACEHOLDER_RE.search(card_type) and card_type not in AUTHORED_CARD_TYPES:
                add_issue(
                    issues,
                    "error",
                    "dialogue.noncanonical_authored_card",
                    f"{card_id} 不是原创人格的规范对白卡",
                    path,
                    root,
                )
                noncanonical_card_ids.add(card_id)

            original_text = field_value(block, "原文")
            card_language = field_value(block, "原文语言")
            original_quality = field_value(block, "原文质量")
            if original_quality:
                card_qualities[card_id] = original_quality
            if (
                original_quality
                and not PLACEHOLDER_RE.search(original_quality)
                and original_quality not in ALLOWED_QUALITIES
            ):
                add_issue(
                    issues,
                    "error",
                    "dialogue.original_quality_invalid",
                    f"{card_id} 的原文质量无效：{original_quality}",
                    path,
                    root,
                )
            if card_type in EXACT_CARD_TYPES:
                if not has_exact_original_text(original_text):
                    add_issue(
                        issues,
                        "error",
                        "dialogue.original_text_missing",
                        f"{card_id} 没有可用的逐字原文；场景摘要不能替代原文",
                        path,
                        root,
                    )
                    noncanonical_card_ids.add(card_id)
                else:
                    normalized = normalize_original_text(original_text or "")
                    duplicate_scene = (field_value(block, "场景编号") or "").strip()
                    duplicate_location = (field_value(block, "来源位置") or "").strip()
                    previous_occurrence = next(
                        (
                            owner for owner in normalized_original_owners.get(normalized, [])
                            if owner[1] == duplicate_scene and owner[2] == duplicate_location
                        ),
                        None,
                    )
                    if previous_occurrence:
                        add_issue(
                            issues,
                            "error" if level == "release" else "warning",
                            "dialogue.duplicate_original_text",
                            f"{card_id} 与 {previous_occurrence[0]} 保存了同一场景、同一定位的相同原文，不能重复计数",
                            path,
                            root,
                        )
                        noncanonical_card_ids.add(card_id)
                    else:
                        normalized_original_owners[normalized].append(
                            (card_id, duplicate_scene, duplicate_location)
                        )
                        exact_original_card_ids.add(card_id)
                        if (
                            card_language
                            and original_language != "unknown"
                            and card_language.lower() == original_language.lower()
                            and original_quality in ALLOWED_ORIGINAL_QUALITIES
                        ):
                            original_language_card_ids.add(card_id)
                        if original_quality == "原声核验":
                            performance_verified_card_ids.add(card_id)
                        if original_quality == "原始版式核验":
                            layout_verified_card_ids.add(card_id)
            elif card_type in AUTHORED_CARD_TYPES and has_exact_original_text(original_text):
                if original_quality == "原创确认":
                    canonical_authored_card_ids.add(card_id)

            scene_id = field_value(block, "场景编号")
            if has_substantive_value(scene_id):
                card_scene_ids[card_id] = (scene_id or "").strip()
            scene_completeness = field_value(block, "场景完整度")
            context_type = field_value(block, "语境类型")
            if (
                context_type
                and not PLACEHOLDER_RE.search(context_type)
                and context_type not in ALLOWED_CONTEXT_TYPES
            ):
                add_issue(
                    issues, "error", "dialogue.context_type_invalid",
                    f"{card_id} 的语境类型无效：{context_type}", path, root,
                )
            if (
                scene_completeness
                and not PLACEHOLDER_RE.search(scene_completeness)
                and scene_completeness not in ALLOWED_SCENE_COMPLETENESS
            ):
                add_issue(
                    issues, "error", "dialogue.scene_completeness_invalid",
                    f"{card_id} 的场景完整度无效：{scene_completeness}", path, root,
                )
            context_values = (
                field_value(block, "前置原文"), field_value(block, "触发话语"),
                field_value(block, "后续原文"), field_value(block, "对话对象"),
            )
            locator_only_fields = [
                field for field in ("前置原文", "触发话语", "后续原文")
                if not context_is_missing(field_value(block, field))
                and not context_is_grounded(field_value(block, field))
            ]
            if locator_only_fields:
                add_issue(
                    issues, "error" if level == "release" else "warning",
                    "dialogue.context_locator_only",
                    f"{card_id} 的“{'、'.join(locator_only_fields)}”只是来源定位说明，不是实际话轮或具体场景摘要",
                    path, root,
                )
            complete_context_count = sum(context_is_grounded(value) for value in context_values)
            context_is_countable = False
            if context_type in CONVERSATIONAL_CONTEXT_TYPES:
                context_is_countable = (
                    complete_context_count >= 3
                    and context_is_grounded(field_value(block, "触发话语"))
                    and context_is_grounded(field_value(block, "对话对象"))
                )
            elif context_type in NARRATIVE_CONTEXT_TYPES:
                context_is_countable = (
                    complete_context_count >= 2
                    and not (
                        not context_is_grounded(field_value(block, "前置原文"))
                        and not context_is_grounded(field_value(block, "触发话语"))
                    )
                )
            elif context_type in SELF_CONTAINED_CONTEXT_TYPES:
                context_is_countable = (
                    complete_context_count >= 1
                    and has_substantive_value(field_value(block, "来源位置"))
                    and (
                        context_is_grounded(field_value(block, "触发话语"))
                        or context_is_grounded(field_value(block, "对话对象"))
                    )
                )
            elif context_type == "原创设定":
                context_is_countable = scene_completeness == "原创设定" and complete_context_count >= 1
            if (
                card_id in (exact_original_card_ids | canonical_authored_card_ids)
                and has_substantive_value(scene_id)
                and scene_completeness in COUNTABLE_SCENE_COMPLETENESS
                and context_is_countable
            ):
                distinct_source_scenes.add((scene_id or "").strip())
                context_complete_card_ids.add(card_id)
            elif scene_completeness in {"完整", "语境充分"} and not context_is_countable:
                add_issue(
                    issues, "error" if level == "release" else "warning",
                    "dialogue.complete_scene_context_missing",
                    f"{card_id} 标为{scene_completeness}，但“{context_type or '未填写'}”所需的来源、触发、对象或上下文不足",
                    path, root,
                )
            recognition = field_value(block, "识别度")
            if card_id in exact_original_card_ids and recognition in SIGNATURE_LEVELS:
                signature_card_ids.add(card_id)

            for forbidden_field in ("工作改写示例", "适用工作场景", "迁移方式"):
                if field_value(block, forbidden_field) is not None:
                    add_issue(
                        issues,
                        "error",
                        "dialogue.prewritten_rewrite_forbidden",
                        f"{card_id} 含旧字段“{forbidden_field}”；工作迁移必须在运行时完成，不得写进原文对白库",
                        path,
                        root,
                    )
            source_type = field_value(block, "来源类型")
            if source_type and not PLACEHOLDER_RE.search(source_type) and source_type not in ALLOWED_SOURCE_TYPES:
                add_issue(
                    issues,
                    "error",
                    "dialogue.source_type_invalid",
                    f"{card_id} 的来源类型无效：{source_type}",
                    path,
                    root,
                )
            if (
                persona_type in {"existing-character", "composite-character", "real-person-simulation"}
                and source_type
                and not PLACEHOLDER_RE.search(source_type)
                and not (
                    (persona_type in {"existing-character", "composite-character"} and source_type in EXISTING_EXPRESSION_SOURCE_TYPES)
                    or (persona_type == "real-person-simulation" and source_type in REAL_PERSON_EXPRESSION_SOURCE_TYPES)
                )
            ):
                add_issue(
                    issues,
                    "error",
                    "dialogue.source_not_original",
                    f"{card_id} 的来源类型是“{source_type}”；表达卡只接受原作/本人原始表达或可回查到具体位置的可靠转写",
                    path,
                    root,
                )
                noncanonical_card_ids.add(card_id)
            intensity = field_value(block, "情绪强度")
            if intensity and not PLACEHOLDER_RE.search(intensity) and not re.fullmatch(r"[0-3]", intensity):
                add_issue(
                    issues,
                    "error",
                    "dialogue.intensity_invalid",
                    f"{card_id} 的情绪强度必须是 0–3",
                    path,
                    root,
                )
            tags = field_value(block, "原作检索标签")
            label_evidence_value = field_value(block, "标签依据")
            label_evidence = parse_label_evidence(label_evidence_value)
            if tags and not PLACEHOLDER_RE.search(tags):
                present_tags = set(re.findall(r"\b([a-z_]+)\s*=", tags))
                missing_tags = sorted(REQUIRED_TAGS - present_tags)
                if missing_tags:
                    add_issue(
                        issues,
                        "error",
                        "dialogue.tags_missing",
                        f"{card_id} 缺少检索标签：{', '.join(missing_tags)}",
                        path,
                        root,
                    )
                forbidden_tags = sorted(present_tags & FORBIDDEN_SOURCE_TAGS)
                if forbidden_tags:
                    add_issue(
                        issues, "error" if level == "release" else "warning",
                        "dialogue.work_tags_in_source_card",
                        f"{card_id} 把工作域标签写入原作卡：{', '.join(forbidden_tags)}",
                        path, root,
                    )
                missing_label_evidence = sorted(REQUIRED_LABEL_EVIDENCE - set(label_evidence))
                if label_evidence_value is not None and missing_label_evidence:
                    add_issue(
                        issues,
                        "error" if level == "release" else "warning",
                        "dialogue.label_evidence_missing",
                        f"{card_id} 缺少标签依据：{', '.join(missing_label_evidence)}",
                        path,
                        root,
                    )
                invalid_label_evidence = {
                    key: value
                    for key, value in label_evidence.items()
                    if key in REQUIRED_LABEL_EVIDENCE and value not in ALLOWED_LABEL_EVIDENCE
                }
                if invalid_label_evidence:
                    add_issue(
                        issues,
                        "error" if level == "release" else "warning",
                        "dialogue.label_evidence_invalid",
                        f"{card_id} 的标签依据无效："
                        + ", ".join(f"{key}={value}" for key, value in sorted(invalid_label_evidence.items())),
                        path,
                        root,
                    )
                conflict_keys: list[str] = []
                if context_is_missing(field_value(block, "触发话语")) and label_evidence.get("trigger") in {"上下文可见", "来源明确"}:
                    conflict_keys.append("trigger")
                if context_is_missing(field_value(block, "对话对象")) and label_evidence.get("relation") in {"上下文可见", "来源明确"}:
                    conflict_keys.append("relation")
                for label_key, source_field in (
                    ("interaction", "互动功能"), ("position", "互动位置"), ("initiative", "主动性")
                ):
                    if context_is_missing(field_value(block, source_field)) and label_evidence.get(label_key) in {"上下文可见", "来源明确"}:
                        conflict_keys.append(label_key)
                if conflict_keys:
                    add_issue(
                        issues,
                        "error" if level == "release" else "warning",
                        "dialogue.label_evidence_conflict",
                        f"{card_id} 的上下文字段明确缺失，却把这些标签标成已核验：{', '.join(conflict_keys)}",
                        path,
                        root,
                    )
                tag_values = parse_tags(tags)
            if original_quality == "原声核验" and not has_substantive_value(field_value(block, "语音表现")):
                add_issue(
                    issues,
                    "error",
                    "dialogue.performance_missing",
                    f"{card_id} 标为原声核验但没有可用语音表现标注",
                    path,
                    root,
                )
            for annotation_field in (
                "前置原文", "触发话语", "后续原文", "互动功能", "角色即时反应", "互动位置",
                "主动性", "情绪转折", "非语言反应", "画面锚点", "语音表现", "词汇标记",
                "语法标记", "语气标记", "口语现象", "句式与节奏",
            ):
                annotation = field_value(block, annotation_field)
                if context_is_missing(annotation):
                    continue
                if has_substantive_value(annotation, allow_none=True):
                    annotation_values[annotation_field].append(
                        (normalize_template_text(annotation or ""), card_id, path)
                    )
            source_location = field_value(block, "来源位置")
            source_refs = set(re.findall(r"\bSRC-\d{4}\b", source_location or "", re.IGNORECASE))
            normalized_source_refs = {item.upper() for item in source_refs}
            card_source_refs[card_id] = normalized_source_refs
            referenced_source_ids.update(normalized_source_refs)
            if card_id in exact_original_card_ids and source_type in PRIMARY_SOURCE_TYPES:
                original_referenced_source_ids.update(normalized_source_refs)
                original_card_sources[card_id] = normalized_source_refs
            if source_location and not PLACEHOLDER_RE.search(source_location) and not source_refs:
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "dialogue.source_reference_missing",
                    f"{card_id} 的来源位置未引用 SRC-编号",
                    path,
                    root,
                )
            if persona_type in {"existing-character", "composite-character", "real-person-simulation"}:
                if card_id not in exact_original_card_ids:
                    noncanonical_card_ids.add(card_id)
            elif card_id not in canonical_authored_card_ids:
                noncanonical_card_ids.add(card_id)

    if missing_label_evidence_cards:
        missing_ids = [card_id for card_id, _ in missing_label_evidence_cards]
        preview = ", ".join(missing_ids[:5])
        suffix = "…" if len(missing_ids) > 5 else ""
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "dialogue.label_evidence_missing",
            f"有 {len(missing_ids)} 张卡缺少“标签依据”字段：{preview}{suffix}",
            missing_label_evidence_cards[0][1],
            root,
        )

    metrics["cards"] = len(all_ids)
    metrics["exact_original_cards"] = len(exact_original_card_ids)
    metrics["performance_verified_cards"] = len(performance_verified_card_ids)
    metrics["canonical_authored_cards"] = len(canonical_authored_card_ids)
    metrics["distinct_source_scenes"] = len(distinct_source_scenes)
    metrics["distinct_evidence_units"] = len(distinct_source_scenes)
    metrics["context_complete_cards"] = len(context_complete_card_ids)
    metrics["signature_cards"] = len(signature_card_ids)
    metrics["unique_original_expressions"] = len(normalized_original_owners)
    metrics["derived_cards"] = len(noncanonical_card_ids)
    metrics["distinct_emotions_and_intents"] = len(dimensions)
    if persona_type == "composite-character":
        detected_work_counts: Counter[str] = Counter()
        for block in card_blocks_by_id.values():
            location = field_value(block, "作品定位") or ""
            titles = re.findall(r"《[^》]+》", location)
            detected_work_counts[titles[0] if titles else "未识别作品"] += 1
        metrics["composite_detected_work_counts"] = [
            f"{title}={count}" for title, count in detected_work_counts.most_common()
        ]
    for annotation_field, entries in annotation_values.items():
        boilerplate_exempt = {"未核验原声", "不适用", "未知", "缺失"}
        counts = Counter(value for value, _, _ in entries if value and value not in boilerplate_exempt)
        if not counts:
            continue
        repeated_value, repeated_count = counts.most_common(1)[0]
        threshold = max(5, len(all_ids) // 5)
        if repeated_count > threshold:
            example = next(item for item in entries if item[0] == repeated_value)
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "dialogue.annotation_boilerplate",
                f"字段“{annotation_field}”有 {repeated_count} 张卡使用相同标注；必须逐句观察，不能批量复制",
                example[2],
                root,
            )
    if level == "release" and persona_type in {"existing-character", "composite-character", "real-person-simulation"}:
        active_targets = profile_targets or RESEARCH_PROFILES["一般"]
        min_cards = int(active_targets["cards"])
        min_dimensions = int(active_targets["dimensions"])
    elif level == "release":
        active_targets = {}
        min_cards, min_dimensions = 20, 8
    else:
        active_targets = {}
        min_cards, min_dimensions = 1, 1
    target_severity = "warning" if exhaustion_complete else ("error" if level == "release" else "warning")
    if len(all_ids) < min_cards:
        add_issue(
            issues,
            target_severity,
            "dialogue.too_few",
            f"原始表达卡为 {len(all_ids)} 张，{research_profile if profile_targets else '一般'}资料正式版目标为 {min_cards} 张",
            root / "references",
            root,
        )
    if level == "release" and len(dimensions) < min_dimensions:
        add_issue(
            issues,
            target_severity,
            "dialogue.coverage_low",
            f"情绪与交流目的合计仅 {len(dimensions)} 种，{persona_type} 正式版收集目标为 {min_dimensions} 种",
            root / "references",
            root,
        )
    index_path = root / "references" / "05-对白索引.md"
    if index_path.is_file():
        index_text = read_text(index_path).upper()
        missing_from_index = [card_id for card_id in all_ids if card_id not in index_text]
        if missing_from_index:
            preview = ", ".join(missing_from_index[:5])
            suffix = "…" if len(missing_from_index) > 5 else ""
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "dialogue.index_incomplete",
                f"对白索引未包含 {len(missing_from_index)} 个编号：{preview}{suffix}",
                index_path,
                root,
            )
        dialogue_prefixes = {card_id.rsplit("-", 1)[0] for card_id in all_ids}
        index_ids = {
            item for item in re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", index_text)
            if item.rsplit("-", 1)[0] in dialogue_prefixes
        }
        extra_index_ids = sorted(index_ids - set(all_ids))
        if extra_index_ids and level == "release":
            add_issue(
                issues,
                "error",
                "dialogue.index_unknown_id",
                "对白索引包含不存在的编号：" + ", ".join(extra_index_ids[:5]),
                index_path,
                root,
            )

    cases_path = root / "references" / "07-验证用例.md"
    cases_text = read_text(cases_path) if cases_path.is_file() else ""
    case_count = len(CASE_HEADING_RE.findall(cases_text))
    metrics["validation_cases"] = case_count
    if case_count < 24:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "tests.too_few_cases",
            f"验证用例仅 {case_count} 个，至少需要 24 个",
            cases_path,
            root,
        )
    required_case_ids = {"CASE-18", "CASE-19", "CASE-20", "CASE-21", "CASE-22", "CASE-23", "CASE-24"}
    present_case_ids = set(re.findall(r"^##\s+(CASE-\d{2})\s+\|", cases_text, re.MULTILINE))
    missing_fidelity_cases = sorted(required_case_ids - present_case_ids)
    if missing_fidelity_cases:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "tests.fidelity_cases_missing",
            "缺少角色还原验证用例：" + ", ".join(missing_fidelity_cases),
            cases_path,
            root,
        )
    case_blocks = dict(iter_case_blocks(cases_text))
    quality_case_fields = (
        (
            "样本数", "对话数据位置", "评估者类型", "评估者标识", "综合评分", "角色还原",
            "情绪价值", "主动表达", "角色式思考与解释", "连续关系", "事实与风险", "独立结论",
            "原始记录位置", "验证状态",
        )
        if persona_asset_version >= 2 else
        (
            "样本数", "对话数据位置", "评估者类型", "评估者标识", "综合评分", "角色还原",
            "对话连续性", "口语自然度", "回答形态多样性", "事实与风险处理", "独立结论",
            "原始记录位置", "验证状态",
        )
    )
    fidelity_case_fields = {
        "CASE-18": (
            "样本数", "正确识别数", "评估者类型", "评估者标识", "隐藏信息", "失败样本记录", "原始记录位置", "验证状态",
        ),
        "CASE-19": (
            "样本数", "正确区分数", "对照对象", "评估者类型", "评估者标识", "区分证据", "失败样本记录", "原始记录位置", "验证状态",
        ),
        "CASE-20": (
            "抽查数", "可追溯数", "召回相关数", "证据映射抽查数", "证据映射成立数",
            "评估者类型", "评估者标识", "追溯记录", "原始记录位置", "验证状态",
        ),
        "CASE-21": ("输入", "背景条目", "固定事实", "角色输出", "追溯记录", "验证状态"),
        "CASE-22": ("输入", "背景条目", "未知边界", "角色输出", "追溯记录", "验证状态"),
        "CASE-23": (
            "样本数", "批量输入位置", "检查器", "检查输出位置", "检查结果", "重复流程骨架数", "重复开场骨架数",
            "同一回答形状样本数", "追问收尾样本数", "长度与句数异常集中",
            "低生成准备度样本数", "原始记录位置", "验证状态",
        ),
        "CASE-24": quality_case_fields,
    }
    for case_id, fields in fidelity_case_fields.items():
        block = case_blocks.get(case_id, "")
        missing_fields = [field for field in fields if not has_substantive_value(field_value(block, field))]
        if missing_fields:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "tests.fidelity_field_missing",
                f"{case_id} 缺少可用字段：{', '.join(missing_fields)}",
                cases_path,
                root,
            )
        status = field_value(block, "验证状态")
        if level == "release" and status != "通过":
            add_issue(
                issues,
                "error",
                "tests.fidelity_not_passed",
                f"{case_id} 的验证状态必须是“通过”，当前为：{status or '缺失'}",
                cases_path,
                root,
            )
    for case_id in ("CASE-18", "CASE-19", "CASE-20", "CASE-24"):
        block = case_blocks.get(case_id, "")
        evaluator_type = field_value(block, "评估者类型")
        evaluator_id = field_value(block, "评估者标识") or ""
        if evaluator_type and evaluator_type not in ALLOWED_EVALUATOR_TYPES:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "tests.evaluator_type_invalid",
                f"{case_id} 的评估者类型必须是 human、independent-agent 或 independent-context",
                cases_path,
                root,
            )
        if re.search(r"同一|生成者|当前agent|自评|self", evaluator_id, re.IGNORECASE):
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "tests.self_evaluation_forbidden",
                f"{case_id} 不能由生成答案的同一上下文自评：{evaluator_id}",
                cases_path,
                root,
            )
        if evaluator_id.startswith(("待", "尚未", "未")) or "完成后" in evaluator_id:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "tests.evaluator_pending",
                f"{case_id} 的评估者仍是待办描述，不是实际评估者：{evaluator_id}",
                cases_path,
                root,
            )
    blind_samples = integer_field(case_blocks.get("CASE-18", ""), "样本数")
    blind_correct = integer_field(case_blocks.get("CASE-18", ""), "正确识别数")
    contrast_samples = integer_field(case_blocks.get("CASE-19", ""), "样本数")
    contrast_correct = integer_field(case_blocks.get("CASE-19", ""), "正确区分数")
    trace_samples = integer_field(case_blocks.get("CASE-20", ""), "抽查数")
    trace_correct = integer_field(case_blocks.get("CASE-20", ""), "可追溯数")
    retrieval_correct = integer_field(case_blocks.get("CASE-20", ""), "召回相关数")
    mapping_samples = integer_field(case_blocks.get("CASE-20", ""), "证据映射抽查数")
    mapping_correct = integer_field(case_blocks.get("CASE-20", ""), "证据映射成立数")
    batch_samples = integer_field(case_blocks.get("CASE-23", ""), "样本数")
    repeated_workflow = integer_field(case_blocks.get("CASE-23", ""), "重复流程骨架数")
    repeated_opening = integer_field(case_blocks.get("CASE-23", ""), "重复开场骨架数")
    repeated_shape = integer_field(case_blocks.get("CASE-23", ""), "同一回答形状样本数")
    question_closures = integer_field(case_blocks.get("CASE-23", ""), "追问收尾样本数")
    uniform_structure = (field_value(case_blocks.get("CASE-23", ""), "长度与句数异常集中") or "").strip()
    low_readiness = integer_field(case_blocks.get("CASE-23", ""), "低生成准备度样本数")
    batch_checker_status = (field_value(case_blocks.get("CASE-23", ""), "检查结果") or "").strip().lower()
    quality_samples = integer_field(case_blocks.get("CASE-24", ""), "样本数")
    quality_total = integer_field(case_blocks.get("CASE-24", ""), "综合评分")
    quality_role = integer_field(case_blocks.get("CASE-24", ""), "角色还原")
    quality_emotional = integer_field(case_blocks.get("CASE-24", ""), "情绪价值") if persona_asset_version >= 2 else None
    quality_proactive = integer_field(case_blocks.get("CASE-24", ""), "主动表达") if persona_asset_version >= 2 else None
    quality_thinking = integer_field(case_blocks.get("CASE-24", ""), "角色式思考与解释") if persona_asset_version >= 2 else None
    quality_continuity = integer_field(
        case_blocks.get("CASE-24", ""), "连续关系" if persona_asset_version >= 2 else "对话连续性"
    )
    quality_orality = integer_field(case_blocks.get("CASE-24", ""), "口语自然度") if persona_asset_version < 2 else None
    quality_diversity = integer_field(case_blocks.get("CASE-24", ""), "回答形态多样性") if persona_asset_version < 2 else None
    quality_fact_risk = integer_field(
        case_blocks.get("CASE-24", ""), "事实与风险" if persona_asset_version >= 2 else "事实与风险处理"
    )
    quality_verdict = (field_value(case_blocks.get("CASE-24", ""), "独立结论") or "").strip()

    record_expectations = {
        "CASE-18": {
            "counts": {"SAMPLE_COUNT": blind_samples, "PASS_COUNT": blind_correct},
            "minimum_items": blind_samples,
            "evaluator": field_value(case_blocks.get("CASE-18", ""), "评估者标识"),
        },
        "CASE-19": {
            "counts": {"SAMPLE_COUNT": contrast_samples, "PASS_COUNT": contrast_correct},
            "minimum_items": contrast_samples,
            "evaluator": field_value(case_blocks.get("CASE-19", ""), "评估者标识"),
        },
        "CASE-20": {
            "counts": {
                "TRACE_COUNT": trace_samples,
                "TRACE_PASS": trace_correct,
                "RETRIEVAL_PASS": retrieval_correct,
                "MAPPING_COUNT": mapping_samples,
                "MAPPING_PASS": mapping_correct,
            },
            "minimum_items": mapping_samples,
            "evaluator": field_value(case_blocks.get("CASE-20", ""), "评估者标识"),
        },
        "CASE-23": {
            "counts": {"SAMPLE_COUNT": batch_samples},
            "minimum_items": batch_samples,
            "evaluator": None,
        },
        "CASE-24": {
            "counts": ({
                "SAMPLE_COUNT": quality_samples,
                "TOTAL_SCORE": quality_total,
                "ROLE_FIDELITY_SCORE": quality_role,
                "EMOTIONAL_VALUE_SCORE": quality_emotional,
                "PROACTIVE_EXPRESSION_SCORE": quality_proactive,
                "CHARACTER_THINKING_SCORE": quality_thinking,
                "RELATIONSHIP_CONTINUITY_SCORE": quality_continuity,
                "FACT_RISK_SCORE": quality_fact_risk,
            } if persona_asset_version >= 2 else {
                "SAMPLE_COUNT": quality_samples,
                "TOTAL_SCORE": quality_total,
                "ROLE_FIDELITY_SCORE": quality_role,
                "CONTINUITY_SCORE": quality_continuity,
                "ORALITY_SCORE": quality_orality,
                "SHAPE_DIVERSITY_SCORE": quality_diversity,
                "FACT_RISK_SCORE": quality_fact_risk,
            }),
            "minimum_items": quality_samples,
            "evaluator": field_value(case_blocks.get("CASE-24", ""), "评估者标识"),
        },
    }
    record_item_fields = {
        "CASE-18": {"prompt", "anonymous_response", "expected_role", "predicted_role", "verdict", "reason"},
        "CASE-19": {"prompt", "target_response", "generic_response", "similar_role", "similar_response", "verdict", "reason"},
        "CASE-20": {"subject", "evidence", "verdict", "reason"},
        "CASE-23": {"prompt", "response", "status", "reason"},
        "CASE-24": {"prompt", "response", "verdict", "reason"},
    }
    parsed_record_items: dict[str, list[tuple[str, dict[str, object]]]] = {}
    resolved_record_paths: dict[str, Path] = {}
    evaluated_persona_hash = persona_bundle_sha256(root)
    for case_id, expectation in record_expectations.items():
        block = case_blocks.get(case_id, "")
        if field_value(block, "验证状态") != "通过":
            continue
        raw_record_path = field_value(block, "原始记录位置")
        record_path = resolve_record_path(root, raw_record_path)
        if record_path is None:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.record_path_invalid",
                f"{case_id} 的原始记录必须是角色 Skill 目录内的相对路径",
                cases_path, root,
            )
            continue
        if not record_path.is_file():
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.record_missing",
                f"{case_id} 标为通过，但原始记录文件不存在：{raw_record_path}",
                cases_path, root,
            )
            continue
        record_text = read_text(record_path)
        if PLACEHOLDER_RE.search(record_text) or structured_record_value(record_text, "EVAL_RECORD_VERSION") != "2":
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.record_unstructured",
                f"{case_id} 的原始记录必须使用 EVAL_RECORD_VERSION=2 且不得含占位符",
                record_path, root,
            )
        if structured_record_value(record_text, "CASE_ID") != case_id:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.record_case_mismatch",
                f"{case_id} 的原始记录 CASE_ID 不匹配",
                record_path, root,
            )
        evaluator = expectation["evaluator"]
        if evaluator and structured_record_value(record_text, "EVALUATOR_ID") != evaluator:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.record_evaluator_mismatch",
                f"{case_id} 的原始记录没有写入与验证用例一致的 EVALUATOR_ID",
                record_path, root,
            )
        if case_id in {"CASE-18", "CASE-19", "CASE-20", "CASE-24"}:
            if structured_record_value(record_text, "PERSONA_BUNDLE_SHA256") != evaluated_persona_hash:
                add_issue(
                    issues, "error" if level == "release" else "warning",
                    "tests.evaluation_persona_stale",
                    f"{case_id} 的独立评测没有绑定当前人格实现哈希；修改人格后必须重新评测",
                    record_path, root,
                )
        for key, expected in expectation["counts"].items():
            if expected is not None and structured_record_int(record_text, key) != expected:
                add_issue(
                    issues, "error" if level == "release" else "warning",
                    "tests.record_count_mismatch",
                    f"{case_id} 的原始记录 {key} 与验证用例不一致",
                    record_path, root,
                )
        minimum_items = expectation["minimum_items"]
        raw_item_count = len(re.findall(r"^ITEM-\d+[：:]", record_text, re.MULTILINE))
        items = structured_record_items(record_text)
        parsed_record_items[case_id] = items
        resolved_record_paths[case_id] = record_path
        item_count = len(items)
        item_ids = [item_id for item_id, _ in items]
        expected_item_ids = [f"ITEM-{index:02d}" for index in range(1, item_count + 1)]
        if item_ids != expected_item_ids:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.record_item_ids_invalid",
                f"{case_id} 的 ITEM 编号必须唯一并从 ITEM-01 连续递增",
                record_path, root,
            )
        if raw_item_count != item_count:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.record_item_not_structured",
                f"{case_id} 有 {raw_item_count - item_count} 条 ITEM 不是 JSON 对象；禁止只写 pass、分数或一句汇总",
                record_path, root,
            )
        if minimum_items is not None and item_count < minimum_items:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.record_items_low",
                f"{case_id} 声明 {minimum_items} 个样本或映射，但原始记录只有 {item_count} 条 ITEM 记录",
                record_path, root,
            )
        required_item_fields = record_item_fields[case_id]
        for item_id, item in items:
            missing_item_fields = sorted(
                field for field in required_item_fields
                if not has_substantive_value(str(item.get(field, "")), allow_none=True)
            )
            if missing_item_fields:
                add_issue(
                    issues, "error" if level == "release" else "warning",
                    "tests.record_item_fields_missing",
                    f"{case_id} 的 {item_id} 缺少可复核字段：{', '.join(missing_item_fields)}",
                    record_path, root,
                )
            reason = str(item.get("reason", "")).strip()
            if reason and (len(reason) < 12 or reason.lower() in {"pass", "通过", "符合要求", "可复核测试记录"}):
                add_issue(
                    issues, "error" if level == "release" else "warning",
                    "tests.record_item_reason_shallow",
                    f"{case_id} 的 {item_id} 没有保存足以复核判断的具体理由",
                    record_path, root,
                )
            verdict_key = "status" if case_id == "CASE-23" else "verdict"
            allowed_verdicts = {"pass", "review", "fail"} if case_id == "CASE-23" else {"pass", "fail"}
            if str(item.get(verdict_key, "")).strip().lower() not in allowed_verdicts:
                add_issue(
                    issues, "error" if level == "release" else "warning",
                    "tests.record_item_verdict_invalid",
                    f"{case_id} 的 {item_id} 缺少有效的 {verdict_key}",
                    record_path, root,
                )
        if case_id in {"CASE-18", "CASE-19"}:
            item_passes = sum(str(item.get("verdict", "")).lower() == "pass" for _, item in items)
            if structured_record_int(record_text, "PASS_COUNT") != item_passes:
                add_issue(
                    issues, "error" if level == "release" else "warning",
                    "tests.record_pass_count_unverified",
                    f"{case_id} 的 PASS_COUNT 与逐项 verdict 统计不一致",
                    record_path, root,
                )
        if case_id == "CASE-18":
            leaked = [
                item_id for item_id, item in items
                if str(item.get("expected_role", "")).strip()
                and str(item.get("expected_role", "")).strip().lower() in str(item.get("anonymous_response", "")).lower()
            ]
            if leaked:
                add_issue(
                    issues, "error" if level == "release" else "warning",
                    "tests.blind_identity_leaked",
                    "CASE-18 匿名回答泄露目标角色名：" + ", ".join(leaked),
                    record_path, root,
                )
        if case_id == "CASE-19":
            missing_similar = [
                item_id for item_id, item in items
                if not has_substantive_value(str(item.get("similar_role", "")))
                or str(item.get("similar_role", "")).strip().lower() in {"通用助手", "generic assistant"}
            ]
            if missing_similar:
                add_issue(
                    issues, "error" if level == "release" else "warning",
                    "tests.similar_role_missing",
                    "CASE-19 必须逐项包含至少一个非通用助手的相似角色对照：" + ", ".join(missing_similar),
                    record_path, root,
                )
            for field, label in (("generic_response", "通用助手回答"), ("similar_response", "相似角色回答")):
                values = [str(item.get(field, "")).strip() for _, item in items if str(item.get(field, "")).strip()]
                counts = Counter(values)
                if values and max(counts.values()) > max(3, int(len(values) * 0.3 + 0.999)):
                    add_issue(
                        issues, "error" if level == "release" else "warning",
                        "tests.contrast_response_repeated",
                        f"CASE-19 的{label}过度重复；需要逐项生成真实对照回答，而不是复制同一句",
                        record_path, root,
                    )
        if case_id == "CASE-20":
            mapping_signatures = []
            for _, item in items:
                evidence = str(item.get("evidence", ""))
                rules = tuple(sorted(set(re.findall(r"\b(?:CORE|VOICE|MIND|EXPR|MODE|ANTI)-\d{2}\b", evidence, re.IGNORECASE))))
                if rules:
                    mapping_signatures.append(rules)
            if mapping_signatures:
                counts = Counter(mapping_signatures)
                if max(counts.values()) > max(3, int(len(mapping_signatures) * 0.3 + 0.999)):
                    add_issue(
                        issues, "error" if level == "release" else "warning",
                        "tests.trace_mapping_repeated",
                        "CASE-20 的证据映射反复指向同一组 CORE/VOICE/MIND/EXPR 规则；必须逐项对应实际召回与原文证据",
                        record_path, root,
                    )
        if case_id == "CASE-24":
            failed_quality_items = [
                item_id for item_id, item in items if str(item.get("verdict", "")).lower() != "pass"
            ]
            if failed_quality_items:
                add_issue(
                    issues, "error" if level == "release" else "warning",
                    "tests.quality_item_failed",
                    "CASE-24 仍有未通过的真实对话样本：" + ", ".join(failed_quality_items),
                    record_path, root,
                )
        if case_id == "CASE-23" and structured_record_value(record_text, "CHECK_STATUS") != batch_checker_status:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.record_checker_mismatch",
                "CASE-23 的原始记录 CHECK_STATUS 与验证用例不一致",
                record_path, root,
            )

    # A score sheet with twenty copies of one explanation is not an
    # independent evaluation.  Keep this deterministic: evaluators may use a
    # common rubric, but each item must state a different, item-specific reason.
    evaluation_reason_values = [
        normalized_evaluation_reason(str(item.get("reason", "")))
        for case_id in ("CASE-18", "CASE-19", "CASE-20", "CASE-24")
        for _, item in parsed_record_items.get(case_id, [])
        if str(item.get("reason", "")).strip()
    ]
    if evaluation_reason_values:
        reason_counts = Counter(evaluation_reason_values)
        metrics["evaluation_reason_unique_ratio"] = round(
            len(set(evaluation_reason_values)) / len(evaluation_reason_values), 4
        )
        reason_limit = max(2, int(len(evaluation_reason_values) * 0.3 + 0.999))
        repeated_reasons = [
            (reason, count) for reason, count in reason_counts.items() if count > reason_limit
        ]
        if repeated_reasons:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.evaluation_reason_repeated",
                f"独立评测理由过度模板化；同一理由最多只能覆盖 30% 样本，当前最高重复 {max(count for _, count in repeated_reasons)} 条",
                resolved_record_paths.get("CASE-24") or cases_path, root,
            )

    independent_report_path = root / "tests" / "independent-evaluation.md"
    if independent_report_path.is_file():
        report_text = read_text(independent_report_path)
        conclusion_match = re.search(r"最终结论[：:]?(.*?)(?=^##\s|\Z)", report_text, re.MULTILINE | re.DOTALL)
        conclusion_text = conclusion_match.group(1) if conclusion_match else report_text[:800]
        report_not_passed = bool(re.search(r"不通过|NOT\s*PASS|证据不足|仍不能|未通过", conclusion_text, re.IGNORECASE))
        metrics["independent_report_consistent"] = not report_not_passed
        if report_not_passed and quality_verdict == "通过":
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.independent_report_not_passed",
                "独立评测报告仍明确写着不通过或证据不足，不能与 CASE-24 的“通过”结论并存",
                independent_report_path, root,
            )

    batch_input_path = resolve_record_path(root, field_value(case_blocks.get("CASE-23", ""), "批量输入位置"))
    quality_input_path = resolve_record_path(root, field_value(case_blocks.get("CASE-24", ""), "对话数据位置"))
    batch_output_path = resolve_record_path(root, field_value(case_blocks.get("CASE-23", ""), "检查输出位置"))
    runtime_samples: list[dict[str, str]] = []
    if batch_input_path is None or not batch_input_path.is_file():
        add_issue(
            issues, "error" if level == "release" else "warning", "tests.batch_input_missing",
            "CASE-23 必须指向实际运行产生的项目内 JSON 对话数据", cases_path, root,
        )
    else:
        runtime_samples = read_runtime_samples(batch_input_path)
        metrics["runtime_prompt_count"] = len(runtime_samples)
        natural_prompts = [sample["prompt"] for sample in runtime_samples if not is_label_like_prompt(sample["prompt"])]
        metrics["runtime_prompt_natural_count"] = len(natural_prompts)
        metrics["runtime_prompt_unique_ratio"] = round(
            len({re.sub(r"\s+", "", prompt).casefold() for prompt in natural_prompts}) / max(len(runtime_samples), 1),
            4,
        )
        fragment_counts = Counter(
            fragment
            for sample in runtime_samples
            for fragment in response_fragments(sample["response"])
        )
        metrics["runtime_repeated_fragment_max"] = max(fragment_counts.values(), default=0)
        natural_required = max(1, int(len(runtime_samples) * 0.8))
        if len(natural_prompts) < natural_required:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.runtime_prompt_not_natural",
                f"真实连续对话中只有 {len(natural_prompts)}/{len(runtime_samples)} 条是自然语言场景；至少需要 80%，不能用 hello/risk/pause 这类标签冒充用户话轮",
                batch_input_path, root,
            )
        unique_prompt_count = len({re.sub(r"\s+", "", sample["prompt"]).casefold() for sample in runtime_samples})
        if runtime_samples and unique_prompt_count / len(runtime_samples) < 0.8:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.runtime_prompt_diversity_low",
                "真实连续对话的用户话轮重复度过高；至少 80% 的 prompt 必须是不同且有语境的请求",
                batch_input_path, root,
            )
        repetition_limit = max(3, int(len(runtime_samples) * 0.25 + 0.999))
        repeated_fragments = [
            (fragment, count) for fragment, count in fragment_counts.items()
            if count > repetition_limit
        ]
        if repeated_fragments:
            preview = "、".join(f"{fragment}×{count}" for fragment, count in sorted(repeated_fragments, key=lambda item: -item[1])[:3])
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.runtime_mechanical_repetition",
                f"连续对话出现机械重复表达（{preview}）；同一完整片段不得超过样本的 25%",
                batch_input_path, root,
            )
        pause_samples = [
            sample for sample in runtime_samples
            if re.search(r"暂停人格|停止人格|别演|不要角色化|\bpause\b|\bstop persona\b", sample["prompt"], re.IGNORECASE)
        ]
        if skill_prefix and any(sample["response"].lstrip().startswith(skill_prefix) for sample in pause_samples):
            add_issue(
                issues, "error" if level == "release" else "warning",
                "tests.persona_pause_prefix_violation",
                "用户明确暂停人格时，真实对话仍带角色前缀；暂停行为必须由实际回答证明，不能只在规则文件里声明",
                batch_input_path, root,
            )
        if len(runtime_samples) != batch_samples:
            add_issue(
                issues, "error" if level == "release" else "warning", "tests.batch_input_count_mismatch",
                f"CASE-23 声明 {batch_samples} 个样本，但批量输入实际有 {len(runtime_samples)} 个有效问答",
                batch_input_path, root,
            )
        if any(sample.get("structured") != "yes" for sample in runtime_samples):
            add_issue(
                issues, "error" if level == "release" else "warning", "tests.runtime_samples_unstructured",
                "真实连续对话必须使用对象记录，不能用无轮次信息的字符串列表冒充运行记录",
                batch_input_path, root,
            )
        conversation_ids = {sample.get("conversation_id") for sample in runtime_samples if sample.get("conversation_id")}
        turns = [int(sample["turn"]) for sample in runtime_samples if str(sample.get("turn", "")).isdigit()]
        chain_valid = len(conversation_ids) == 1 and turns == list(range(1, len(runtime_samples) + 1))
        for index, sample in enumerate(runtime_samples, start=1):
            previous = str(sample.get("previous_turn", "")).strip().lower()
            expected_previous = str(index - 1)
            if index == 1:
                chain_valid = chain_valid and previous in {"", "0", "none", "null", "start"}
            else:
                chain_valid = chain_valid and previous == expected_previous
        if not chain_valid:
            add_issue(
                issues, "error" if level == "release" else "warning", "tests.runtime_conversation_chain_invalid",
                "真实连续对话必须使用同一 conversation_id，并按 turn=1..N 与 previous_turn 串成连续话轮",
                batch_input_path, root,
            )
        actual_low_readiness = sum(sample.get("generation_readiness") == "low" for sample in runtime_samples)
        if actual_low_readiness != low_readiness:
            add_issue(
                issues, "error" if level == "release" else "warning", "tests.generation_readiness_count_mismatch",
                f"CASE-23 声明 {low_readiness} 个 low 样本，实际对话数据为 {actual_low_readiness} 个",
                batch_input_path, root,
            )
    if quality_input_path is None or not quality_input_path.is_file():
        add_issue(
            issues, "error" if level == "release" else "warning", "tests.quality_input_missing",
            "CASE-24 必须指向同一份实际连续对话数据", cases_path, root,
        )
    elif batch_input_path is not None and quality_input_path.resolve() != batch_input_path.resolve():
        add_issue(
            issues, "error" if level == "release" else "warning", "tests.runtime_dataset_mismatch",
            "CASE-23 批量退化检查和 CASE-24 独立质量评估必须使用同一份真实对话数据",
            cases_path, root,
        )
    if batch_output_path is None or not batch_output_path.is_file():
        add_issue(
            issues, "error" if level == "release" else "warning", "tests.batch_output_missing",
            "CASE-23 必须保存 check_response.py 的完整 JSON 输出", cases_path, root,
        )
    else:
        try:
            batch_output = json.loads(read_text(batch_output_path))
        except json.JSONDecodeError:
            batch_output = None
        if not isinstance(batch_output, dict):
            add_issue(
                issues, "error" if level == "release" else "warning", "tests.batch_output_invalid",
                "CASE-23 检查输出不是有效 JSON 对象", batch_output_path, root,
            )
        else:
            expected_hash = sha256_file(batch_input_path) if batch_input_path and batch_input_path.is_file() else ""
            fresh_batch_output: dict[str, object] | None = None
            canonical_checker = TEMPLATE_ROOT / "scripts" / "check_response.py"
            if batch_input_path and batch_input_path.is_file() and canonical_checker.is_file():
                try:
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(canonical_checker),
                            "--root",
                            str(root),
                            "--batch-file",
                            str(batch_input_path),
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=30,
                    )
                    parsed_fresh = json.loads(completed.stdout) if completed.stdout.strip() else None
                    if completed.returncode == 0 and isinstance(parsed_fresh, dict):
                        fresh_batch_output = parsed_fresh
                except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
                    fresh_batch_output = None
            if fresh_batch_output is None:
                add_issue(
                    issues, "error" if level == "release" else "warning", "tests.batch_recheck_unavailable",
                    "无法使用 Persona.skill 自带的可信检查器重新执行 CASE-23",
                    batch_output_path, root,
                )
            else:
                if fresh_batch_output.get("status") != "pass":
                    add_issue(
                        issues, "error" if level == "release" else "warning", "tests.batch_recheck_failed",
                        f"可信检查器重新执行 CASE-23 的结果为 {fresh_batch_output.get('status')}，不能交付",
                        batch_input_path, root,
                    )
                comparable_keys = {
                    "checker_contract_version", "status", "ai_tone_score", "sample_count",
                    "workflow_skeleton_count", "collective_assistant_voice_count", "repeated_openings",
                    "repeated_shapes", "question_closure_count", "response_length_range", "sentence_counts",
                    "character_presence_coverage", "emotional_response_coverage", "proactive_expression_coverage",
                    "traceability_coverage", "length_adaptation_coverage", "background_callback_count",
                    "repeated_background_ids", "quotation_trace_count", "findings", "responses", "batch_file_sha256",
                }
                if any(batch_output.get(key) != fresh_batch_output.get(key) for key in comparable_keys):
                    add_issue(
                        issues, "error" if level == "release" else "warning", "tests.batch_output_forged_or_stale",
                        "保存的 CASE-23 输出与可信检查器现场重跑结果不一致",
                        batch_output_path, root,
                    )
            if batch_output.get("batch_file_sha256") != expected_hash:
                add_issue(
                    issues, "error" if level == "release" else "warning", "tests.batch_output_stale",
                    "CASE-23 检查输出与当前批量输入哈希不一致，必须对真实对话重新运行检查器",
                    batch_output_path, root,
                )
            if batch_output.get("checker_contract_version") != RESPONSE_CHECKER_CONTRACT_VERSION:
                add_issue(
                    issues, "error" if level == "release" else "warning", "tests.batch_checker_version_stale",
                    "CASE-23 检查输出不是当前严格批量门禁版本；请同步最新 check_response.py 后重跑",
                    batch_output_path, root,
                )
            if persona_asset_version >= 2:
                metrics["character_presence_coverage"] = int(batch_output.get("character_presence_coverage") or 0)
                if metrics["character_presence_coverage"] < 90:
                    add_issue(
                        issues, "error" if level == "release" else "warning", "tests.character_presence_coverage_low",
                        "CASE-23 人物存在覆盖率必须至少为 90%", batch_output_path, root,
                    )
            findings = batch_output.get("findings") if isinstance(batch_output.get("findings"), list) else []
            finding_codes = {
                str(item.get("code")) for item in findings if isinstance(item, dict) and item.get("code")
            }
            actual_repeated_openings = sum(
                max(int(count) - 1, 0)
                for count in (batch_output.get("repeated_openings") or {}).values()
                if isinstance(count, int)
            ) if isinstance(batch_output.get("repeated_openings"), dict) else 0
            actual_repeated_shape = max(
                [int(count) for count in (batch_output.get("repeated_shapes") or {}).values() if isinstance(count, int)] or [0]
            ) if isinstance(batch_output.get("repeated_shapes"), dict) else 0
            comparisons = (
                (batch_output.get("status"), batch_checker_status, "检查结果"),
                (batch_output.get("sample_count"), batch_samples, "样本数"),
                (batch_output.get("workflow_skeleton_count"), repeated_workflow, "重复流程骨架数"),
                (actual_repeated_openings, repeated_opening, "重复开场骨架数"),
                (actual_repeated_shape, repeated_shape, "同一回答形状样本数"),
                (batch_output.get("question_closure_count"), question_closures, "追问收尾样本数"),
                ("是" if {"batch_uniform_response_length", "batch_uniform_sentence_count"} & finding_codes else "否", uniform_structure, "长度与句数异常集中"),
            )
            for actual, declared, label in comparisons:
                if actual != declared:
                    add_issue(
                        issues, "error" if level == "release" else "warning", "tests.batch_metrics_mismatch",
                        f"CASE-23 的“{label}”声明为 {declared}，检查器实际输出为 {actual}",
                        batch_output_path, root,
                    )
            checker_responses = batch_output.get("responses") if isinstance(batch_output.get("responses"), list) else []
            for (item_id, item), checked in zip(parsed_record_items.get("CASE-23", []), checker_responses):
                checked_status = checked.get("status") if isinstance(checked, dict) else None
                if str(item.get("status", "")).strip().lower() != checked_status:
                    add_issue(
                        issues, "error" if level == "release" else "warning", "tests.batch_item_status_mismatch",
                        f"CASE-23 的 {item_id} 状态与检查器逐条结果不一致",
                        resolved_record_paths.get("CASE-23"), root,
                    )
            record_path = resolved_record_paths.get("CASE-23")
            if record_path is not None:
                record_text = read_text(record_path)
                if structured_record_value(record_text, "INPUT_FILE_SHA256") != expected_hash:
                    add_issue(
                        issues, "error" if level == "release" else "warning", "tests.batch_record_input_hash_mismatch",
                        "CASE-23 原始记录没有绑定当前真实对话输入哈希", record_path, root,
                    )
                if structured_record_value(record_text, "CHECK_OUTPUT_SHA256") != sha256_file(batch_output_path):
                    add_issue(
                        issues, "error" if level == "release" else "warning", "tests.batch_record_output_hash_mismatch",
                        "CASE-23 原始记录没有绑定当前检查器输出哈希", record_path, root,
                    )
    for case_id in ("CASE-23", "CASE-24"):
        items = parsed_record_items.get(case_id, [])
        if runtime_samples and items:
            for index, ((item_id, item), sample) in enumerate(zip(items, runtime_samples), start=1):
                if str(item.get("prompt", "")).strip() != sample["prompt"] or str(item.get("response", "")).strip() != sample["response"]:
                    add_issue(
                        issues, "error" if level == "release" else "warning", "tests.runtime_item_mismatch",
                        f"{case_id} 的 {item_id} 与真实对话数据第 {index} 条不一致",
                        resolved_record_paths.get(case_id), root,
                    )
                    break
    quality_record_path = resolved_record_paths.get("CASE-24")
    if quality_record_path is not None and quality_input_path is not None and quality_input_path.is_file():
        if structured_record_value(read_text(quality_record_path), "SUBJECT_FILE_SHA256") != sha256_file(quality_input_path):
            add_issue(
                issues, "error" if level == "release" else "warning", "tests.quality_record_stale",
                "CASE-24 独立评估记录没有绑定当前真实对话数据哈希", quality_record_path, root,
            )
    quality_thresholds = (
        (
            (quality_samples is not None and quality_samples >= 20, "tests.quality_samples_low", "CASE-24 人物资产 v2 至少需要 20 个真实连续对话样本"),
            (quality_total is not None and quality_total >= 85, "tests.quality_total_low", "CASE-24 综合评分至少需要 85/100"),
            (quality_role is not None and 26 <= quality_role <= 30, "tests.quality_role_low", "CASE-24 角色还原至少需要 26/30"),
            (quality_emotional is not None and 16 <= quality_emotional <= 20, "tests.quality_emotional_low", "CASE-24 情绪价值至少需要 16/20"),
            (quality_proactive is not None and 12 <= quality_proactive <= 15, "tests.quality_proactive_low", "CASE-24 主动表达至少需要 12/15"),
            (quality_thinking is not None and 12 <= quality_thinking <= 15, "tests.quality_thinking_low", "CASE-24 角色式思考与解释至少需要 12/15"),
            (quality_continuity is not None and 8 <= quality_continuity <= 10, "tests.quality_continuity_low", "CASE-24 连续关系至少需要 8/10"),
            (quality_fact_risk == 10, "tests.quality_fact_risk_low", "CASE-24 事实与风险必须为 10/10"),
            (
                None not in {quality_total, quality_role, quality_emotional, quality_proactive, quality_thinking, quality_continuity, quality_fact_risk}
                and quality_total == quality_role + quality_emotional + quality_proactive + quality_thinking + quality_continuity + quality_fact_risk,
                "tests.quality_score_inconsistent", "CASE-24 综合评分必须等于六个 v2 分项之和",
            ),
        )
        if persona_asset_version >= 2 else
        (
            (quality_samples is not None and quality_samples >= 12, "tests.quality_samples_low", "CASE-24 真实连续对话质量评估至少需要 12 个样本"),
            (quality_total is not None and quality_total >= 85, "tests.quality_total_low", "CASE-24 综合评分至少需要 85/100"),
            (quality_role is not None and 34 <= quality_role <= 40, "tests.quality_role_low", "CASE-24 角色还原至少需要 34/40"),
            (quality_continuity is not None and 16 <= quality_continuity <= 20, "tests.quality_continuity_low", "CASE-24 对话连续性至少需要 16/20"),
            (quality_orality is not None and 12 <= quality_orality <= 15, "tests.quality_orality_low", "CASE-24 口语自然度至少需要 12/15"),
            (quality_diversity is not None and 12 <= quality_diversity <= 15, "tests.quality_diversity_low", "CASE-24 回答形态多样性至少需要 12/15"),
            (quality_fact_risk is not None and 8 <= quality_fact_risk <= 10, "tests.quality_fact_risk_low", "CASE-24 事实与风险处理至少需要 8/10"),
            (
                None not in {quality_total, quality_role, quality_continuity, quality_orality, quality_diversity, quality_fact_risk}
                and quality_total == quality_role + quality_continuity + quality_orality + quality_diversity + quality_fact_risk,
                "tests.quality_score_inconsistent", "CASE-24 综合评分必须等于五个分项之和",
            ),
        )
    )
    fidelity_thresholds = (
        (blind_samples is not None and blind_samples >= 12, "tests.blind_samples_low", "CASE-18 去名盲测至少需要 12 个样本"),
        (blind_correct is not None and blind_correct >= 10 and blind_samples is not None and blind_correct <= blind_samples, "tests.blind_correct_low", "CASE-18 至少需要正确识别 10 个样本，且不能超过样本数"),
        (contrast_samples is not None and contrast_samples >= 12, "tests.contrast_samples_invalid", "CASE-19 至少需要 12 个通用助手与相似角色对照样本"),
        (contrast_correct is not None and contrast_samples is not None and contrast_correct <= contrast_samples and contrast_correct * 100 >= contrast_samples * 80, "tests.contrast_rate_low", "CASE-19 相似角色区分率必须至少 80%"),
        (trace_samples is not None and trace_samples >= 6, "tests.trace_samples_low", "CASE-20 至少抽查 6 个场景"),
        (trace_correct is not None and trace_samples is not None and trace_correct <= trace_samples and trace_correct * 100 >= trace_samples * 80, "tests.trace_rate_low", "CASE-20 证据追溯率必须至少 80%"),
        (retrieval_correct is not None and trace_samples is not None and retrieval_correct <= trace_samples and retrieval_correct * 100 >= trace_samples * 80, "tests.retrieval_rate_low", "CASE-20 召回相关率必须至少 80%"),
        (mapping_samples is not None and mapping_samples >= 12, "tests.evidence_mapping_samples_low", "CASE-20 至少独立抽查 12 条规则证据映射"),
        (mapping_correct is not None and mapping_samples is not None and mapping_correct <= mapping_samples and mapping_correct * 100 >= mapping_samples * 80, "tests.evidence_mapping_rate_low", "CASE-20 规则证据映射语义成立率必须至少 80%"),
        (batch_samples is not None and batch_samples >= 12, "tests.batch_samples_low", "CASE-23 批量结构退化检查至少需要 12 个真实连续对话样本"),
        (batch_checker_status == "pass", "tests.batch_checker_not_passed", "CASE-23 的批量回复检查器结果必须是 pass"),
        (repeated_workflow is not None and repeated_workflow <= 1, "tests.batch_workflow_repeated", "CASE-23 重复流程骨架最多允许 1 个"),
        (repeated_opening is not None and repeated_opening <= 1, "tests.batch_opening_repeated", "CASE-23 重复开场骨架最多允许 1 个"),
        (repeated_shape is not None and repeated_shape <= 3, "tests.batch_shape_repeated", "CASE-23 同一回答形状最多允许出现在 3 个样本中"),
        (
            question_closures is not None and batch_samples is not None and question_closures <= batch_samples
            and question_closures * 100 < batch_samples * 70,
            "tests.batch_question_closure_repeated", "CASE-23 追问收尾不得达到样本的 70%",
        ),
        (uniform_structure in {"否", "no", "false"}, "tests.batch_uniform_structure", "CASE-23 长度与句数不得异常集中"),
        (low_readiness == 0, "tests.generation_readiness_low", "CASE-23 不允许把生成准备度为 low 的样本计作角色还原通过"),
        *quality_thresholds,
        (quality_verdict == "通过", "tests.quality_verdict_not_passed", "CASE-24 独立结论必须明确为“通过”"),
    )
    for passed, code, message in fidelity_thresholds:
        if not passed:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                code,
                message,
                cases_path,
                root,
            )

    # A role cannot be enabled from a self-declared or stale score sheet.  The
    # independent CASE-24 result is a separate hard gate from the source
    # counts, so a large corpus never masks a weak real-dialogue evaluation.
    quality_threshold_flags = [bool(condition) for condition, _code, _message in quality_thresholds]
    quality_evaluator_type = field_value(case_blocks.get("CASE-24", ""), "评估者类型")
    quality_evaluator_id = field_value(case_blocks.get("CASE-24", ""), "评估者标识") or ""
    quality_evaluator_ready = (
        quality_evaluator_type in ALLOWED_EVALUATOR_TYPES
        and not re.search(r"同一|生成者|当前agent|自评|self|待|尚未|未", quality_evaluator_id, re.IGNORECASE)
    )
    quality_related_error = any(
        issue.severity == "error"
        and (
            issue.code.startswith("tests.quality")
            or issue.code in {
                "tests.evaluator_type_invalid", "tests.self_evaluation_forbidden", "tests.evaluator_pending",
                "tests.runtime_dataset_mismatch", "tests.quality_record_stale", "tests.runtime_item_mismatch",
                "tests.runtime_prompt_not_natural", "tests.runtime_prompt_diversity_low",
                "tests.runtime_mechanical_repetition", "tests.persona_pause_prefix_violation",
                "tests.evaluation_reason_repeated", "tests.independent_report_not_passed",
                "tests.contrast_response_repeated", "tests.trace_mapping_repeated",
            }
        )
        for issue in issues
    )
    metrics["independent_quality_pass"] = bool(
        quality_threshold_flags
        and all(quality_threshold_flags)
        and quality_verdict == "通过"
        and quality_evaluator_ready
        and not quality_related_error
    )
    if not metrics["independent_quality_pass"]:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "tests.independent_quality_gate_required",
            "必须完成独立 CASE-24 真实连续对话评估并达到全部质量门槛后才能启用；当前结果不足、过期或不是独立评估",
            cases_path,
            root,
        )

    source_blocks = list(iter_source_blocks(sources_text)) if sources_text else []
    source_ids = [source_id for source_id, _ in source_blocks]
    source_count = len(source_ids)
    metrics["sources"] = source_count
    if source_count < 1:
        add_issue(issues, "error", "sources.empty", "来源索引至少需要一个来源条目", sources_path, root)
    if len(set(source_ids)) != len(source_ids):
        add_issue(issues, "error", "sources.duplicate_id", "来源索引包含重复的 SRC 编号", sources_path, root)
    original_source_ids: set[str] = set()
    for source_id, block in source_blocks:
        for field in REQUIRED_SOURCE_FIELDS:
            if not has_substantive_value(field_value(block, field)):
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "sources.field_missing",
                    f"{source_id} 缺少可用字段：{field}",
                    sources_path,
                    root,
                )
        if persona_asset_version >= 2:
            version_layer = (field_value(block, "版本层") or "").strip().lower()
            if version_layer not in ALLOWED_VERSION_LAYERS:
                add_issue(
                    issues, "error" if level == "release" else "warning", "sources.version_layer_invalid",
                    f"{source_id} 的版本层必须是 primary、secondary 或 popular", sources_path, root,
                )
        source_type = field_value(block, "来源类型")
        if source_type in PRIMARY_SOURCE_TYPES:
            original_source_ids.add(source_id)
        elif source_type and not PLACEHOLDER_RE.search(source_type) and source_type not in ALLOWED_INDEX_SOURCE_TYPES:
            add_issue(
                issues,
                "error",
                "sources.type_invalid",
                f"{source_id} 的来源类型无效：{source_type}",
                sources_path,
                root,
            )
        claimed_cards = extract_claimed_card_ids(field_value(block, "支持的结论或卡片"))
        if claimed_cards:
            actual_cards = {card_id for card_id, refs in card_source_refs.items() if source_id in refs}
            false_claims = sorted(claimed_cards - actual_cards)
            if false_claims:
                preview = ", ".join(false_claims[:5])
                suffix = "…" if len(false_claims) > 5 else ""
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "sources.card_claim_mismatch",
                    f"{source_id} 声称支持 {len(false_claims)} 张未实际引用该来源的卡：{preview}{suffix}",
                    sources_path,
                    root,
                )
    composite_work_rows = list(iter_composite_work_blocks(sources_text)) if persona_type == "composite-character" else []
    metrics["composite_work_count"] = len(composite_work_rows)
    if persona_asset_version >= 2:
        # The matrix is an evidence index, not merely a list of row names.
        # Validate each row so a copied table with eleven headings cannot make
        # a low-evidence character look complete.  Keep the check tolerant of
        # Markdown alignment rows and additional columns added by a user.
        matrix_rows: dict[str, tuple[str, str, str]] = {}
        matrix_pattern = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)
        for match in matrix_pattern.finditer(sources_text):
            dimension, state, evidence, gap = (item.strip() for item in match.groups())
            if dimension.lower() in {"维度", "---"} or set(dimension) <= {"-"}:
                continue
            # Alignment rows (| --- | --- | ...) have no meaningful state.
            if set(state) <= {"-"}:
                continue
            if dimension in matrix_rows:
                add_issue(
                    issues, "error" if level == "release" else "warning", "sources.effect_matrix_duplicate",
                    f"角色效果矩阵重复维度：{dimension}", sources_path, root,
                )
            matrix_rows[dimension] = (state, evidence, gap)

        metrics["effect_matrix_rows"] = len(matrix_rows)
        missing_matrix = sorted(REQUIRED_EFFECT_MATRIX_DIMENSIONS - set(matrix_rows))
        if missing_matrix:
            add_issue(
                issues, "error" if level == "release" else "warning", "sources.effect_matrix_incomplete",
                "角色效果矩阵缺少维度：" + ", ".join(missing_matrix), sources_path, root,
            )
        unknown_matrix = sorted(set(matrix_rows) - REQUIRED_EFFECT_MATRIX_DIMENSIONS)
        if unknown_matrix:
            add_issue(
                issues, "error" if level == "release" else "warning", "sources.effect_matrix_dimension_invalid",
                "角色效果矩阵包含未知维度：" + ", ".join(unknown_matrix), sources_path, root,
            )

        # Cross-family identifier validation is performed below, after all
        # BIO/CORE/VOICE/MODE/MIND/EXPR blocks have been parsed.  At this
        # point only the row shape and state are available.
        for dimension, (state, evidence, gap) in matrix_rows.items():
            if state not in ALLOWED_EFFECT_MATRIX_STATES:
                add_issue(
                    issues, "error" if level == "release" else "warning", "sources.effect_matrix_state_invalid",
                    f"角色效果矩阵“{dimension}”状态无效：{state}；必须是" + "/".join(sorted(ALLOWED_EFFECT_MATRIX_STATES)),
                    sources_path, root,
                )
            evidence_ids = set(re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{2,4}\b", evidence, re.IGNORECASE))
            if not has_substantive_value(evidence, allow_none=True) or not evidence_ids:
                add_issue(
                    issues, "error" if level == "release" else "warning", "sources.effect_matrix_evidence_missing",
                    f"角色效果矩阵“{dimension}”必须填写至少一个可追溯证据编号", sources_path, root,
                )
            if not has_substantive_value(gap, allow_none=True):
                add_issue(
                    issues, "error" if level == "release" else "warning", "sources.effect_matrix_gap_missing",
                    f"角色效果矩阵“{dimension}”必须说明剩余缺口；没有缺口时写“无”", sources_path, root,
                )
        matrix_rows_for_validation = matrix_rows
    supporting_original_sources = original_source_ids & original_referenced_source_ids
    verified_original_card_ids = {
        card_id for card_id, source_refs in original_card_sources.items() if source_refs & original_source_ids
    }
    verified_fidelity_card_ids = verified_original_card_ids & original_language_card_ids
    verified_performance_card_ids = verified_fidelity_card_ids & performance_verified_card_ids
    verified_layout_card_ids = verified_fidelity_card_ids & layout_verified_card_ids
    metrics["exact_original_cards"] = len(verified_fidelity_card_ids)
    verified_unique_originals = {
        normalized
        for normalized, owners in normalized_original_owners.items()
        if any(owner[0] in verified_fidelity_card_ids for owner in owners)
    }
    metrics["unique_original_expressions"] = len(verified_unique_originals)
    if persona_type in RICH_CORPUS_TYPES:
        rich_profile_ready = research_profile == "丰富"
        rich_card_floor_ready = len(verified_fidelity_card_ids) >= RICH_CORPUS_MIN_CARDS
        metrics["rich_corpus_ready"] = bool(rich_profile_ready and rich_card_floor_ready)
        if level == "release" and not rich_profile_ready:
            add_issue(
                issues,
                "error",
                "research.rich_profile_required",
                "已有角色、跨作品角色集合和现实人物模拟必须达到“丰富”资料档；“一般/稀缺/已穷尽”只能作为调研审计状态，不能进入蒸馏、启用或完成交付",
                sources_path,
                root,
            )
        if level == "release" and not rich_card_floor_ready:
            add_issue(
                issues,
                "error",
                "research.rich_cards_required",
                f"正式原文卡仅 {len(verified_fidelity_card_ids)} 张；角色资料必须至少有 {RICH_CORPUS_MIN_CARDS} 张经原语言、来源和语境核验的代表性原文卡后才能继续",
                root / "references" / "06-对白库.md",
                root,
            )
        if len(verified_fidelity_card_ids) > RICH_CORPUS_RECOMMENDED_MAX_CARDS:
            add_issue(
                issues,
                "warning",
                "dialogue.rich_cards_over_recommended",
                f"正式原文卡 {len(verified_fidelity_card_ids)} 张已超过建议的 {RICH_CORPUS_RECOMMENDED_MAX_CARDS} 张；请继续去重并优先保留跨情绪、关系和工作场景的代表性经典表达",
                root / "references" / "06-对白库.md",
                root,
            )
    if persona_type == "composite-character":
        work_card_owners: dict[str, str] = {}
        work_card_counts: list[int] = []
        work_evidence_counts: list[int] = []
        work_dimension_counts: list[int] = []
        work_gap_messages: list[str] = []
        if len(composite_work_rows) < COMPOSITE_WORK_MIN_COUNT:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "composite.work_matrix_missing",
                f"跨角色集合必须明确列出至少 {COMPOSITE_WORK_MIN_COUNT} 部作品的 WORK 覆盖记录；当前只有 {len(composite_work_rows)} 条",
                sources_path,
                root,
            )
        for work_id, block in composite_work_rows:
            work_name = field_value(block, "作品") or ""
            speaker = field_value(block, "角色/表达者") or ""
            raw_card_text = field_value(block, "原文卡") or ""
            listed_card_ids = {
                card_id.upper()
                for card_id in re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", raw_card_text, re.IGNORECASE)
            }
            declared_unique = integer_field(block, "独特表达数")
            declared_evidence = integer_field(block, "证据单元数")
            scene_dimensions = split_values(field_value(block, "场景维度") or "")
            source_strategy = field_value(block, "来源策略")
            retrieval_gap = field_value(block, "检索缺口")
            row_missing = [
                field for field, value in (
                    ("作品", work_name),
                    ("角色/表达者", speaker),
                    ("原文卡", raw_card_text),
                    ("独特表达数", str(declared_unique) if declared_unique is not None else ""),
                    ("证据单元数", str(declared_evidence) if declared_evidence is not None else ""),
                    ("场景维度", field_value(block, "场景维度") or ""),
                    ("来源策略", source_strategy or ""),
                    ("检索缺口", retrieval_gap or ""),
                ) if not has_substantive_value(value, allow_none=(field == "检索缺口"))
            ]
            if row_missing:
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "composite.work_record_incomplete",
                    f"{work_id}（{work_name or '未命名作品'}）缺少逐作品覆盖字段：" + ", ".join(row_missing),
                    sources_path,
                    root,
                )
                work_gap_messages.append(f"{work_id}:字段缺失")
            verified_ids = listed_card_ids & verified_fidelity_card_ids
            unknown_ids = sorted(listed_card_ids - set(all_ids))
            if unknown_ids:
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "composite.work_card_unknown",
                    f"{work_id} 引用了不存在的原文卡：" + ", ".join(unknown_ids[:8]),
                    sources_path,
                    root,
                )
            unverified_ids = sorted(listed_card_ids & set(all_ids) - verified_fidelity_card_ids)
            if unverified_ids:
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "composite.work_card_not_verified",
                    f"{work_id} 有 {len(unverified_ids)} 张卡尚未完成原语言与来源核验，不能计入逐作品覆盖："
                    + ", ".join(unverified_ids[:8]),
                    sources_path,
                    root,
                )
            for card_id in listed_card_ids:
                previous_work = work_card_owners.get(card_id)
                if previous_work and previous_work != work_id:
                    add_issue(
                        issues,
                        "error" if level == "release" else "warning",
                        "composite.work_card_duplicate",
                        f"原文卡 {card_id} 同时归入 {previous_work} 和 {work_id}；跨作品集合不能重复计数",
                        sources_path,
                        root,
                    )
                work_card_owners[card_id] = work_id
            actual_unique = len({
                normalize_original_text(field_value(card_blocks_by_id[card_id], "原文") or "")
                for card_id in verified_ids
                if card_id in card_blocks_by_id and has_exact_original_text(field_value(card_blocks_by_id[card_id], "原文"))
            })
            actual_evidence = len({card_scene_ids.get(card_id) for card_id in verified_ids if card_scene_ids.get(card_id)})
            work_card_counts.append(len(verified_ids))
            work_evidence_counts.append(actual_evidence)
            work_dimension_counts.append(len(scene_dimensions))
            if len(verified_ids) < COMPOSITE_WORK_MIN_CARDS:
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "composite.work_cards_low",
                    f"{work_id}（{work_name or '未命名作品'}）只有 {len(verified_ids)} 张已核验原文卡，单部作品至少需要 {COMPOSITE_WORK_MIN_CARDS} 张",
                    sources_path,
                    root,
                )
                work_gap_messages.append(f"{work_id}:原文卡 {len(verified_ids)}/{COMPOSITE_WORK_MIN_CARDS}")
            if actual_unique < COMPOSITE_WORK_MIN_UNIQUE or (declared_unique is not None and declared_unique < COMPOSITE_WORK_MIN_UNIQUE):
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "composite.work_unique_low",
                    f"{work_id} 只有 {actual_unique} 条不同已核验表达，单部作品至少需要 {COMPOSITE_WORK_MIN_UNIQUE} 条",
                    sources_path,
                    root,
                )
            if actual_evidence < COMPOSITE_WORK_MIN_EVIDENCE_UNITS or (declared_evidence is not None and declared_evidence < COMPOSITE_WORK_MIN_EVIDENCE_UNITS):
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "composite.work_evidence_low",
                    f"{work_id} 只有 {actual_evidence} 个可由卡片回查的证据单元，单部作品至少需要 {COMPOSITE_WORK_MIN_EVIDENCE_UNITS} 个",
                    sources_path,
                    root,
                )
            if len(scene_dimensions) < COMPOSITE_WORK_MIN_SCENE_DIMENSIONS:
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "composite.work_scene_coverage_low",
                    f"{work_id} 只覆盖 {len(scene_dimensions)} 个场景维度，单部作品至少需要 {COMPOSITE_WORK_MIN_SCENE_DIMENSIONS} 个",
                    sources_path,
                    root,
                )
            if not source_strategy or not has_substantive_value(source_strategy):
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "composite.work_source_strategy_missing",
                    f"{work_id} 必须记录该作品的来源策略和版本层，不能只写作品名",
                    sources_path,
                    root,
                )
        total_matrix_cards = sum(work_card_counts)
        max_share = max(work_card_counts) / max(total_matrix_cards, 1) if work_card_counts else 0.0
        metrics["composite_work_cards_min"] = min(work_card_counts) if work_card_counts else 0
        metrics["composite_work_evidence_min"] = min(work_evidence_counts) if work_evidence_counts else 0
        metrics["composite_work_scene_dimensions_min"] = min(work_dimension_counts) if work_dimension_counts else 0
        metrics["composite_work_card_share_max"] = round(max_share, 4)
        if max_share > COMPOSITE_MAX_SINGLE_WORK_SHARE:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "composite.work_card_share_high",
                f"单部作品占逐作品矩阵卡片的 {max_share:.0%}，不能超过 {COMPOSITE_MAX_SINGLE_WORK_SHARE:.0%}；否则会把集合人格收敛成单一作品",
                sources_path,
                root,
            )
        metrics["composite_work_gaps"] = work_gap_messages
        metrics["composite_work_coverage_complete"] = not any(
            issue.severity == "error" and issue.code.startswith("composite.") for issue in issues
        )
    if (
        level == "release"
        and persona_type in {"existing-character", "composite-character", "real-person-simulation"}
        and declared_formal_cards is not None
        and declared_formal_cards != len(verified_fidelity_card_ids)
    ):
        add_issue(
            issues, "error", "research.formal_count_mismatch",
            f"来源索引声明 {declared_formal_cards} 张正式原文卡，校验器实际确认 {len(verified_fidelity_card_ids)} 张",
            sources_path, root,
        )
    if original_medium in {"视听", "混合"}:
        metrics["performance_verified_cards"] = len(verified_performance_card_ids)
    elif original_medium == "文字":
        metrics["performance_verified_cards"] = len(verified_layout_card_ids)
    else:
        metrics["performance_verified_cards"] = len(canonical_authored_card_ids)
    metrics["original_sources"] = len(supporting_original_sources)
    unverified_original_card_ids = sorted(set(original_card_sources) - verified_original_card_ids)
    if unverified_original_card_ids:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "dialogue.original_source_mismatch",
            f"有 {len(unverified_original_card_ids)} 张原始表达卡未引用原作/本人原始表达或可靠转写来源："
            + ", ".join(unverified_original_card_ids[:5]),
            sources_path,
            root,
        )
    translated_or_unverified_cards = sorted(verified_original_card_ids - verified_fidelity_card_ids)
    if translated_or_unverified_cards:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "dialogue.original_language_unverified",
            f"有 {len(translated_or_unverified_cards)} 张卡不是作品原始语言的已核验原文，不能计入角色还原语料："
            + ", ".join(translated_or_unverified_cards[:5]),
            root / "references",
            root,
        )

    bio_path = root / "references" / "10-人物背景档案.md"
    bio_text = read_text(bio_path) if bio_path.is_file() else ""
    bio_blocks = list(iter_bio_blocks(bio_text))
    bio_ids = {bio_id for bio_id, _ in bio_blocks}
    missing_bio_baseline_fields: list[str] = []
    for field in REQUIRED_BIO_BASELINE_FIELDS:
        allow_none = field in {
            "性别身份", "性别相关称谓与代词", "年龄或生命阶段", "所属或阵营",
        }
        if not has_substantive_value(field_value(bio_text, field), allow_none=allow_none):
            missing_bio_baseline_fields.append(field)
    if missing_bio_baseline_fields:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "biography.baseline_missing",
            "人物背景缺少常驻身份基线字段：" + ", ".join(missing_bio_baseline_fields),
            bio_path,
            root,
        )
    baseline_source_ids = set(
        re.findall(r"\bSRC-\d{4}\b", field_value(bio_text, "基线来源") or "", re.IGNORECASE)
    )
    unknown_baseline_sources = sorted({source_id.upper() for source_id in baseline_source_ids} - set(source_ids))
    if not baseline_source_ids:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "biography.baseline_source_missing",
            "常驻身份基线必须引用至少一个 SRC-来源",
            bio_path,
            root,
        )
    if unknown_baseline_sources:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "biography.baseline_source_invalid",
            "常驻身份基线引用了不存在的来源：" + ", ".join(unknown_baseline_sources),
            bio_path,
            root,
        )
    metrics["biography_baseline_complete"] = not missing_bio_baseline_fields and bool(baseline_source_ids) and not unknown_baseline_sources
    duplicate_bio_ids = sorted(
        bio_id for bio_id, count in Counter(item[0] for item in bio_blocks).items() if count > 1
    )
    if duplicate_bio_ids:
        add_issue(
            issues,
            "error",
            "biography.duplicate_id",
            "人物背景档案编号重复：" + ", ".join(duplicate_bio_ids),
            bio_path,
            root,
        )
    for case_id in ("CASE-21", "CASE-22"):
        referenced_bio_ids = set(re.findall(r"\bBIO-\d{2}\b", field_value(case_blocks.get(case_id, ""), "背景条目") or ""))
        if not referenced_bio_ids:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "tests.biography_reference_missing",
                f"{case_id} 至少需要引用一个 BIO-人物背景条目",
                cases_path,
                root,
            )
        unknown_bio_ids = sorted(referenced_bio_ids - bio_ids)
        if unknown_bio_ids:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "tests.biography_reference_invalid",
                f"{case_id} 引用了不存在的人物背景条目：{', '.join(unknown_bio_ids)}",
                cases_path,
                root,
            )
    bio_categories: set[str] = set()
    subjective_memory_ids: set[str] = set()
    analogy_domain_values: set[str] = set()
    for bio_id, block in bio_blocks:
        for field in REQUIRED_BIO_FIELDS:
            if not has_substantive_value(field_value(block, field)):
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "biography.field_missing",
                    f"{bio_id} 缺少可用字段：{field}",
                    bio_path,
                    root,
                )
        if persona_asset_version >= 2:
            missing_v2_fields = [field for field in V2_BIO_FIELDS if field_value(block, field) is None]
            if missing_v2_fields:
                add_issue(
                    issues, "error" if level == "release" else "warning", "biography.v2_field_missing",
                    f"{bio_id} 缺少人物资产 v2 字段：{', '.join(missing_v2_fields)}", bio_path, root,
                )
            elif all(
                has_substantive_value(field_value(block, field), allow_none=(field in {"情绪印记", "可迁移意象"}))
                for field in V2_BIO_FIELDS
            ):
                subjective_memory_ids.add(bio_id)
            analogy_value = field_value(block, "可迁移意象") or ""
            if has_substantive_value(analogy_value, allow_none=True) and "不使用" not in analogy_value:
                analogy_domain_values.update(split_values(analogy_value))
        category = (field_value(block, "类别") or "").strip().lower()
        if category:
            if category not in ALLOWED_BIO_CATEGORIES:
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "biography.category_invalid",
                    f"{bio_id} 的类别无效：{category}",
                    bio_path,
                    root,
                )
            else:
                bio_categories.add(category)
        bio_source_ids = set(re.findall(r"\bSRC-\d{4}\b", field_value(block, "来源") or "", re.IGNORECASE))
        normalized_bio_sources = {source_id.upper() for source_id in bio_source_ids}
        if not normalized_bio_sources:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "biography.source_missing",
                f"{bio_id} 没有引用 SRC-来源；人物事实不能由模型印象补齐",
                bio_path,
                root,
            )
        unknown_bio_sources = sorted(normalized_bio_sources - set(source_ids))
        if unknown_bio_sources:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "biography.source_invalid",
                f"{bio_id} 引用了不存在的来源：{', '.join(unknown_bio_sources)}",
                bio_path,
                root,
            )
    metrics["biography_entries"] = len(bio_blocks)
    metrics["biography_categories"] = len(bio_categories)
    metrics["subjective_memory_entries"] = len(subjective_memory_ids)
    metrics["semantic_diversity_failures"] += add_semantic_diversity_issues(
        issues,
        bio_blocks,
        ("主题", "事实", "角色视角回答要点", "适用问题", "边界"),
        "biography.semantic_boilerplate",
        "人物背景档案",
        bio_path,
        root,
        level,
    )
    bio_target, bio_category_target = (8, 4)
    if level == "release" and len(bio_blocks) < bio_target:
        add_issue(
            issues,
            target_severity,
            "biography.count_low",
            f"人物背景条目仅 {len(bio_blocks)} 个，正式版收集目标为 {bio_target} 个",
            bio_path,
            root,
        )
    if level == "release" and len(bio_categories) < bio_category_target:
        add_issue(
            issues,
            target_severity,
            "biography.categories_low",
            f"人物背景仅覆盖 {len(bio_categories)} 类，正式版目标为 {bio_category_target} 类",
            bio_path,
            root,
        )
    if level == "release" and persona_asset_version >= 2 and len(subjective_memory_ids) < 6:
        add_issue(
            issues, target_severity, "biography.subjective_memory_low",
            f"可用于普通对话回调的主观背景条目仅 {len(subjective_memory_ids)} 个，人物资产 v2 至少需要 6 个",
            bio_path, root,
        )
    missing_identity_categories = sorted({"identity", "gender", "relationship"} - bio_categories)
    if level == "release" and missing_identity_categories:
        add_issue(
            issues,
            target_severity,
            "biography.identity_coverage_missing",
            "人物背景缺少身份、性别或关系类别：" + ", ".join(missing_identity_categories),
            bio_path,
            root,
        )

    evidence_card_ids = (
        canonical_authored_card_ids
        if persona_type in {"original-persona", "composite-original"}
        else verified_fidelity_card_ids
    )
    strategy_text = read_text(strategy_path) if strategy_path.is_file() else ""
    mind_blocks = list(iter_mind_blocks(strategy_text)) if persona_asset_version >= 2 else []
    expr_blocks = list(iter_expr_blocks(strategy_text)) if persona_asset_version >= 2 else []
    for label, blocks, required_fields, code_prefix in (
        ("心理机制", mind_blocks, REQUIRED_MIND_FIELDS, "mind"),
        ("表达策略", expr_blocks, REQUIRED_EXPR_FIELDS, "expression"),
    ):
        duplicate_ids = sorted(rule_id for rule_id, count in Counter(item[0] for item in blocks).items() if count > 1)
        if duplicate_ids:
            add_issue(
                issues, "error", f"{code_prefix}.duplicate_id",
                f"{label}编号重复：" + ", ".join(duplicate_ids), strategy_path, root,
            )
        for rule_id, block in blocks:
            missing_fields = [
                field for field in required_fields
                if not has_substantive_value(
                    field_value(block, field),
                    allow_none=(field in {"背景条目", "比喻或意象来源", "经历回调", "典故或名句政策"}),
                )
            ]
            if missing_fields:
                add_issue(
                    issues, "error" if level == "release" else "warning", f"{code_prefix}.field_missing",
                    f"{rule_id} 缺少可用字段：{', '.join(missing_fields)}", strategy_path, root,
                )
            evidence_ids = set(re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", field_value(block, "证据卡") or ""))
            if len(evidence_ids) < 2:
                add_issue(
                    issues, "error" if level == "release" else "warning", f"{code_prefix}.evidence_too_few",
                    f"{rule_id} 至少需要两张不同证据单元的表达卡", strategy_path, root,
                )
            elif len({card_scene_ids.get(card_id) for card_id in evidence_ids if card_scene_ids.get(card_id)}) < 2:
                add_issue(
                    issues, "error" if level == "release" else "warning", f"{code_prefix}.evidence_same_scene",
                    f"{rule_id} 的证据卡必须来自至少两个不同证据单元", strategy_path, root,
                )
            unknown_evidence = sorted(evidence_ids - evidence_card_ids)
            if unknown_evidence:
                add_issue(
                    issues, "error" if level == "release" else "warning", f"{code_prefix}.evidence_invalid",
                    f"{rule_id} 引用了不存在、未核验或非原始语言的证据卡：" + ", ".join(unknown_evidence),
                    strategy_path, root,
                )
            background_ids = set(re.findall(r"\bBIO-\d{2}\b", field_value(block, "背景条目") or ""))
            unknown_background = sorted(background_ids - bio_ids)
            if unknown_background:
                add_issue(
                    issues, "error" if level == "release" else "warning", f"{code_prefix}.biography_invalid",
                    f"{rule_id} 引用了不存在的背景条目：" + ", ".join(unknown_background), strategy_path, root,
                )
            validate_rule_evidence_mapping(
                issues, rule_id, block, card_blocks_by_id, strategy_path, root, level, code_prefix,
                require_retrieval=False,
            )

    if persona_asset_version >= 2 and mind_blocks:
        mind_corpus = "\n".join(block for _, block in mind_blocks)
        missing_mind_dimensions = [
            label for label, markers in MIND_COVERAGE_MARKERS.items()
            if not any(marker in mind_corpus for marker in markers)
        ]
        if missing_mind_dimensions:
            add_issue(
                issues, "error" if level == "release" else "warning", "mind.coverage_missing",
                "MIND 规则未覆盖人物心理维度：" + ", ".join(missing_mind_dimensions), strategy_path, root,
            )

    # Finish effect-matrix evidence checks now that every local asset family
    # has been parsed.  This catches stale or fabricated IDs while still
    # allowing a matrix row to cite multiple families (BIO/CORE/MIND/etc.).
    if persona_asset_version >= 2:
        matrix_rows_for_validation = locals().get("matrix_rows_for_validation", {})
        known_matrix_ids = {str(item).upper() for item in source_ids} | {str(item).upper() for item in all_ids}
        # The matrix block is reached before the later family-specific loops
        # assign every local.  Read whichever parsed families are available;
        # the remaining families are checked on the next validation pass after
        # their own parsers run, and do not make this gate crash.
        parsed_families = {
            "bio_blocks": locals().get("bio_blocks", []),
            "core_blocks": locals().get("core_blocks", list(iter_core_blocks(core_text))),
            "voice_blocks": locals().get(
                "voice_blocks", list(iter_voice_blocks(read_text(root / "references" / "02-语言声纹.md")))
                if (root / "references" / "02-语言声纹.md").is_file() else []
            ),
            "mode_blocks": locals().get(
                "mode_blocks", list(iter_mode_blocks(read_text(root / "references" / "03-情绪与关系.md")))
                if (root / "references" / "03-情绪与关系.md").is_file() else []
            ),
            "mind_blocks": locals().get("mind_blocks", []),
            "expr_blocks": locals().get("expr_blocks", []),
        }
        for family in parsed_families.values():
            known_matrix_ids.update(str(item[0]).upper() for item in family)
        for dimension, (_state, evidence, _gap) in matrix_rows_for_validation.items():
            evidence_ids = {
                item.upper()
                for item in re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{2,4}\b", evidence, re.IGNORECASE)
            }
            unknown_ids = sorted(evidence_ids - known_matrix_ids)
            if unknown_ids:
                add_issue(
                    issues, "error" if level == "release" else "warning", "sources.effect_matrix_evidence_invalid",
                    f"角色效果矩阵“{dimension}”引用未知证据编号：" + ", ".join(unknown_ids), sources_path, root,
                )
        metrics["effect_matrix_complete"] = bool(matrix_rows_for_validation) and not any(
            issue.code.startswith("sources.effect_matrix_") and issue.severity == "error"
            for issue in issues
        ) and not (REQUIRED_EFFECT_MATRIX_DIMENSIONS - set(matrix_rows_for_validation))

    quotation_policies = [(field_value(block, "典故或名句政策") or "").strip().lower() for _, block in expr_blocks]
    verbosity_profiles = [(field_value(block, "篇幅档") or "").strip().lower() for _, block in expr_blocks]
    quotation_policy_complete = bool(expr_blocks) and all(
        policy and ("不使用" in policy or any(value in policy for value in ALLOWED_QUOTE_USES))
        for policy in quotation_policies
    )
    verbosity_profile_complete = bool(expr_blocks) and all(profile in ALLOWED_VERBOSITY_PROFILES for profile in verbosity_profiles)
    for _, block in expr_blocks:
        domain = field_value(block, "比喻或意象来源") or ""
        if has_substantive_value(domain, allow_none=True) and "不使用" not in domain:
            analogy_domain_values.update(split_values(domain))
    metrics["mind_rules"] = len(mind_blocks)
    metrics["expression_rules"] = len(expr_blocks)
    metrics["analogy_domains"] = len(analogy_domain_values)
    metrics["quotation_policy_complete"] = quotation_policy_complete
    metrics["verbosity_profile_complete"] = verbosity_profile_complete
    if persona_asset_version >= 2:
        for actual, target, code, message in (
            (len(mind_blocks), 6, "mind.count_low", "心理机制规则"),
            (len(expr_blocks), 6, "expression.count_low", "表达策略规则"),
        ):
            if level == "release" and actual < target:
                add_issue(
                    issues, target_severity, code, f"{message}仅 {actual} 条，人物资产 v2 至少需要 {target} 条",
                    strategy_path, root,
                )
        if level == "release" and not quotation_policy_complete:
            add_issue(
                issues, target_severity, "expression.quotation_policy_incomplete",
                "每条 EXPR- 都必须明确 exact-quote、paraphrase、allusion 或不使用名句", strategy_path, root,
            )
        if level == "release" and not verbosity_profile_complete:
            add_issue(
                issues, target_severity, "expression.verbosity_profile_incomplete",
                "每条 EXPR- 的篇幅档必须是 brief、normal、extended 或 rambling-characteristic",
                strategy_path, root,
            )

    behavior_text = read_text(behavior_path) if behavior_path.is_file() else ""
    behavior_blocks = list(iter_behavior_blocks(behavior_text)) if persona_asset_version >= 3 else []
    behavior_functions: set[str] = set()
    known_connected_ids: set[str] = set()
    if persona_asset_version >= 3:
        references_dir = root / "references"
        for reference_file in references_dir.glob("*.md") if references_dir.is_dir() else []:
            known_connected_ids.update(
                item.upper()
                for item in re.findall(
                    r"\b(?:CORE|MIND|EXPR|VOICE|MODE|MICRO|ANTI|BIO)-\d{2}\b",
                    read_text(reference_file), re.IGNORECASE,
                )
            )
        duplicate_behavior_ids = sorted(
            rule_id for rule_id, count in Counter(item[0] for item in behavior_blocks).items() if count > 1
        )
        if duplicate_behavior_ids:
            add_issue(
                issues, "error", "behavior.duplicate_id",
                "行为辨识编号重复：" + ", ".join(duplicate_behavior_ids), behavior_path, root,
            )
        for rule_id, block in behavior_blocks:
            missing_fields = [
                field for field in REQUIRED_BEHAVIOR_FIELDS
                if not has_substantive_value(field_value(block, field))
            ]
            if missing_fields:
                add_issue(
                    issues, "error" if level == "release" else "warning", "behavior.field_missing",
                    f"{rule_id} 缺少可执行字段：{', '.join(missing_fields)}", behavior_path, root,
                )
            behavior_function = (field_value(block, "行为功能") or "").strip().lower()
            if behavior_function:
                behavior_functions.add(behavior_function)
            if behavior_function not in REQUIRED_BEHAVIOR_FUNCTIONS:
                add_issue(
                    issues, "error" if level == "release" else "warning", "behavior.function_invalid",
                    f"{rule_id} 的行为功能无效：{behavior_function or 'missing'}", behavior_path, root,
                )
            shapes = split_values(field_value(block, "形状候选") or "")
            if len(shapes) < 2:
                add_issue(
                    issues, "error" if level == "release" else "warning", "behavior.shapes_low",
                    f"{rule_id} 至少需要两种不同回答形状", behavior_path, root,
                )
            signals = split_values(field_value(block, "可见角色信号") or "")
            if len(signals) < 2:
                add_issue(
                    issues, "error" if level == "release" else "warning", "behavior.visible_signals_low",
                    f"{rule_id} 至少需要两类内容级可见角色信号", behavior_path, root,
                )
            generic_near_miss = normalize_template_text(field_value(block, "通用助手近失样本") or "")
            similar_near_miss = normalize_template_text(field_value(block, "相似人物近失样本") or "")
            if generic_near_miss and generic_near_miss == similar_near_miss:
                add_issue(
                    issues, "error" if level == "release" else "warning", "behavior.contrast_not_distinct",
                    f"{rule_id} 的通用助手与相似人物近失样本没有实质差异", behavior_path, root,
                )
            evidence_ids = set(re.findall(
                r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", field_value(block, "证据卡") or "", re.IGNORECASE,
            ))
            evidence_ids = {item.upper() for item in evidence_ids}
            if len(evidence_ids) < 3:
                add_issue(
                    issues, "error" if level == "release" else "warning", "behavior.evidence_too_few",
                    f"{rule_id} 至少需要三张表达卡", behavior_path, root,
                )
            elif len({card_scene_ids.get(card_id) for card_id in evidence_ids if card_scene_ids.get(card_id)}) < 3:
                add_issue(
                    issues, "error" if level == "release" else "warning", "behavior.evidence_units_low",
                    f"{rule_id} 的证据必须来自至少三个不同证据单元", behavior_path, root,
                )
            unknown_evidence = sorted(evidence_ids - evidence_card_ids)
            if unknown_evidence:
                add_issue(
                    issues, "error" if level == "release" else "warning", "behavior.evidence_invalid",
                    f"{rule_id} 引用了不存在、未核验或非原始语言的卡片：" + ", ".join(unknown_evidence),
                    behavior_path, root,
                )
            connected_ids = {
                item.upper() for item in re.findall(
                    r"\b(?:CORE|MIND|EXPR|VOICE|MODE|MICRO|ANTI|BIO)-\d{2}\b",
                    field_value(block, "连接资产") or "", re.IGNORECASE,
                )
            }
            if len(connected_ids) < 3:
                add_issue(
                    issues, "error" if level == "release" else "warning", "behavior.connected_assets_low",
                    f"{rule_id} 至少要连接三个已有资产规则", behavior_path, root,
                )
            unknown_connected = sorted(connected_ids - known_connected_ids)
            if unknown_connected:
                add_issue(
                    issues, "error" if level == "release" else "warning", "behavior.connected_assets_invalid",
                    f"{rule_id} 引用了未知连接资产：" + ", ".join(unknown_connected), behavior_path, root,
                )
            failure_layers = {
                item.strip().lower() for item in re.split(r"[/,，、|]", field_value(block, "失败归因") or "") if item.strip()
            }
            invalid_layers = sorted(failure_layers - ALLOWED_FAILURE_ATTRIBUTION_LAYERS)
            if invalid_layers:
                add_issue(
                    issues, "error" if level == "release" else "warning", "behavior.failure_layer_invalid",
                    f"{rule_id} 含未知失败归因层：" + ", ".join(invalid_layers), behavior_path, root,
                )
            validate_rule_evidence_mapping(
                issues, rule_id, block, card_blocks_by_id, behavior_path, root, level, "behavior",
                require_retrieval=True,
            )
        add_semantic_diversity_issues(
            issues,
            behavior_blocks,
            ("第一反应", "核心取舍", "对用户的关系动作", "话语动作序列", "反直觉切入", "人物推理次序", "顾问骨架禁用", "去名识别锚点", "区别性边界"),
            "behavior.semantic_boilerplate",
            "行为辨识模型",
            behavior_path,
            root,
            level,
        )
        missing_functions = sorted(REQUIRED_BEHAVIOR_FUNCTIONS - behavior_functions)
        if level == "release" and len(behavior_blocks) < 12:
            add_issue(
                issues, target_severity, "behavior.count_low",
                f"行为辨识规则仅 {len(behavior_blocks)} 条，人物资产 v3 至少需要 12 条", behavior_path, root,
            )
        if level == "release" and missing_functions:
            add_issue(
                issues, target_severity, "behavior.function_coverage_missing",
                "行为辨识模型未覆盖功能：" + ", ".join(missing_functions), behavior_path, root,
            )
    metrics["behavior_rules"] = len(behavior_blocks)
    metrics["behavior_functions"] = len(behavior_functions)
    metrics["behavior_function_coverage_complete"] = REQUIRED_BEHAVIOR_FUNCTIONS.issubset(behavior_functions)

    core_blocks = list(iter_core_blocks(core_text))
    duplicate_core_ids = sorted(core_id for core_id, count in Counter(item[0] for item in core_blocks).items() if count > 1)
    if duplicate_core_ids:
        add_issue(issues, "error", "core_rule.duplicate_id", "角色核心编号重复：" + ", ".join(duplicate_core_ids), core_path, root)
    core_layers: set[str] = set()
    core_evidence_ids: set[str] = set()
    for core_id, block in core_blocks:
        for field in REQUIRED_CORE_RULE_FIELDS:
            value = field_value(block, field)
            if not has_substantive_value(value, allow_none=(field == "其他来源")):
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "core_rule.field_missing",
                    f"{core_id} 缺少可用字段：{field}",
                    core_path,
                    root,
                )
        layer = field_value(block, "层级")
        if layer and layer not in REQUIRED_CORE_LAYERS:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "core_rule.layer_invalid",
                f"{core_id} 的层级无效：{layer}",
                core_path,
                root,
            )
        elif layer:
            core_layers.add(layer)
        evidence_ids = set(re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", field_value(block, "证据卡") or ""))
        core_evidence_ids.update(evidence_ids)
        if len(evidence_ids) < 2:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "core_rule.evidence_too_few",
                f"{core_id} 至少需要两张跨场景证据卡",
                core_path,
                root,
            )
        elif len({card_scene_ids.get(card_id) for card_id in evidence_ids if card_scene_ids.get(card_id)}) < 2:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "core_rule.evidence_same_scene",
                f"{core_id} 的证据卡必须来自至少两个不同证据单元",
                core_path,
                root,
            )
        unknown_evidence = sorted(evidence_ids - evidence_card_ids)
        if unknown_evidence:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "core_rule.evidence_invalid",
                f"{core_id} 引用了不存在、未核验或非原始语言的证据卡：" + ", ".join(unknown_evidence),
                core_path,
                root,
            )
        incomplete_core_evidence = sorted((evidence_ids & evidence_card_ids) - context_complete_card_ids)
        if incomplete_core_evidence:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "core_rule.evidence_context_incomplete",
                f"{core_id} 的行为结论引用了语境不充分的表达卡：" + ", ".join(incomplete_core_evidence),
                core_path, root,
            )
        validate_rule_evidence_mapping(
            issues, core_id, block, card_blocks_by_id, core_path, root, level, "core_rule"
        )
    metrics["core_rules"] = len(core_blocks)
    metrics["core_layers"] = len(core_layers)
    metrics["core_evidence_cards"] = len(core_evidence_ids & evidence_card_ids)
    metrics["semantic_diversity_failures"] += add_semantic_diversity_issues(
        issues,
        core_blocks,
        ("结论", "可观察行为", "适用条件"),
        "core_rule.semantic_boilerplate",
        "角色核心规则",
        core_path,
        root,
        level,
    )

    voice_path = root / "references" / "02-语言声纹.md"
    voice_text = read_text(voice_path) if voice_path.is_file() else ""
    voice_blocks = list(iter_voice_blocks(voice_text))
    duplicate_voice_ids = sorted(voice_id for voice_id, count in Counter(item[0] for item in voice_blocks).items() if count > 1)
    if duplicate_voice_ids:
        add_issue(issues, "error", "voice.duplicate_id", "声纹编号重复：" + ", ".join(duplicate_voice_ids), voice_path, root)
    voice_ids = {voice_id for voice_id, _ in voice_blocks}
    voice_layers: set[str] = set()
    voice_evidence_ids: set[str] = set()
    for voice_id, block in voice_blocks:
        for field in REQUIRED_VOICE_FIELDS:
            value = field_value(block, field)
            if not has_substantive_value(value):
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "voice.field_missing",
                    f"{voice_id} 缺少可用字段：{field}",
                    voice_path,
                    root,
                )
        layer = field_value(block, "层级")
        if layer and layer not in ALLOWED_VOICE_LAYERS:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "voice.layer_invalid",
                f"{voice_id} 的层级无效：{layer}",
                voice_path,
                root,
            )
        elif layer:
            voice_layers.add(layer)
        evidence_ids = set(re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", field_value(block, "证据卡") or ""))
        voice_evidence_ids.update(evidence_ids)
        if len(evidence_ids) < 2:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "voice.evidence_too_few",
                f"{voice_id} 至少需要两张跨场景证据卡",
                voice_path,
                root,
            )
        elif len({card_scene_ids.get(card_id) for card_id in evidence_ids if card_scene_ids.get(card_id)}) < 2:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "voice.evidence_same_scene",
                f"{voice_id} 的证据卡必须来自至少两个不同证据单元",
                voice_path,
                root,
            )
        unknown_evidence = sorted(evidence_ids - evidence_card_ids)
        if unknown_evidence:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "voice.evidence_invalid",
                f"{voice_id} 引用了不存在、未核验或非原始语言的证据卡：" + ", ".join(unknown_evidence),
                voice_path,
                root,
            )
        incomplete_voice_evidence = sorted((evidence_ids & evidence_card_ids) - context_complete_card_ids)
        if incomplete_voice_evidence:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "voice.evidence_context_incomplete",
                f"{voice_id} 的通用声纹规律引用了语境不充分的表达卡：" + ", ".join(incomplete_voice_evidence),
                voice_path, root,
            )
        validate_rule_evidence_mapping(
            issues, voice_id, block, card_blocks_by_id, voice_path, root, level, "voice"
        )
        if layer == "prosody" and not any(card_qualities.get(card_id) == "原声核验" for card_id in evidence_ids):
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "voice.prosody_without_audio",
                f"{voice_id} 是 prosody 规律，但证据卡没有原声核验；不得从文本推测表演",
                voice_path,
                root,
            )
    metrics["voice_rules"] = len(voice_blocks)
    metrics["voice_layers"] = len(voice_layers)
    metrics["voice_evidence_cards"] = len(voice_evidence_ids & evidence_card_ids)
    metrics["semantic_diversity_failures"] += add_semantic_diversity_issues(
        issues,
        voice_blocks,
        ("规律", "反证或边界", "适用条件"),
        "voice.semantic_boilerplate",
        "语言声纹规则",
        voice_path,
        root,
        level,
    )
    missing_required_voice_layers = sorted(MINIMUM_VOICE_LAYERS - voice_layers)
    if level == "release" and persona_type in {"existing-character", "composite-character", "real-person-simulation"} and missing_required_voice_layers:
        add_issue(
            issues,
            target_severity,
            "voice.required_layers_missing",
            "正式版缺少最低必需的文本声纹层级：" + ", ".join(missing_required_voice_layers),
            voice_path,
            root,
        )

    micro_blocks = list(iter_micro_blocks(voice_text))
    duplicate_micro_ids = sorted(
        micro_id for micro_id, count in Counter(item[0] for item in micro_blocks).items() if count > 1
    )
    if duplicate_micro_ids:
        add_issue(
            issues, "error", "micro.duplicate_id", "微互动编号重复：" + ", ".join(duplicate_micro_ids), voice_path, root,
        )
    micro_functions: set[str] = set()
    for micro_id, block in micro_blocks:
        for field in REQUIRED_MICRO_FIELDS:
            if not has_substantive_value(field_value(block, field)):
                add_issue(
                    issues, "error" if level == "release" else "warning",
                    "micro.field_missing", f"{micro_id} 缺少可用字段：{field}", voice_path, root,
                )
        function = (field_value(block, "功能") or "").strip().lower()
        if function:
            micro_functions.add(function)
        evidence_ids = set(re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", field_value(block, "证据卡") or ""))
        if len(evidence_ids) < 2:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "micro.evidence_too_few", f"{micro_id} 至少需要两张不同证据单元的表达卡", voice_path, root,
            )
        elif len({card_scene_ids.get(card_id) for card_id in evidence_ids if card_scene_ids.get(card_id)}) < 2:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "micro.evidence_same_unit", f"{micro_id} 的证据卡必须来自至少两个不同证据单元", voice_path, root,
            )
        unknown_evidence = sorted(evidence_ids - evidence_card_ids)
        if unknown_evidence:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "micro.evidence_invalid",
                f"{micro_id} 引用了不存在、未核验或非原始语言的证据卡：" + ", ".join(unknown_evidence),
                voice_path, root,
            )
        incomplete_micro_evidence = sorted((evidence_ids & evidence_card_ids) - context_complete_card_ids)
        if incomplete_micro_evidence:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "micro.evidence_context_incomplete",
                f"{micro_id} 的微互动规律引用了语境不充分的表达卡：" + ", ".join(incomplete_micro_evidence),
                voice_path, root,
            )
        validate_rule_evidence_mapping(
            issues, micro_id, block, card_blocks_by_id, voice_path, root, level, "micro"
        )
    metrics["micro_rules"] = len(micro_blocks)
    metrics["micro_functions"] = len(micro_functions)
    metrics["semantic_diversity_failures"] += add_semantic_diversity_issues(
        issues,
        micro_blocks,
        ("即时反应", "开场节奏", "追问或收束", "禁止通用替代"),
        "micro.semantic_boilerplate",
        "微互动规则",
        voice_path,
        root,
        level,
    )
    missing_micro_functions = sorted(REQUIRED_MICRO_FUNCTIONS - micro_functions)
    if level == "release" and len(micro_blocks) < len(REQUIRED_MICRO_FUNCTIONS):
        add_issue(
            issues, target_severity, "micro.rules_low",
            f"微互动规则仅 {len(micro_blocks)} 条，正式版至少需要 {len(REQUIRED_MICRO_FUNCTIONS)} 条",
            voice_path, root,
        )
    if level == "release" and missing_micro_functions:
        add_issue(
            issues, target_severity, "micro.functions_missing",
            "微互动缺少基础功能：" + ", ".join(missing_micro_functions), voice_path, root,
        )

    mode_path = root / "references" / "03-情绪与关系.md"
    mode_text = read_text(mode_path) if mode_path.is_file() else ""
    mode_blocks = list(iter_mode_blocks(mode_text))
    duplicate_mode_ids = sorted(mode_id for mode_id, count in Counter(item[0] for item in mode_blocks).items() if count > 1)
    if duplicate_mode_ids:
        add_issue(issues, "error", "mode.duplicate_id", "情绪模式编号重复：" + ", ".join(duplicate_mode_ids), mode_path, root)
    mode_dimensions: set[str] = set()
    for mode_id, block in mode_blocks:
        for field in REQUIRED_MODE_FIELDS:
            value = field_value(block, field)
            if not has_substantive_value(value):
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "mode.field_missing",
                    f"{mode_id} 缺少可用字段：{field}",
                    mode_path,
                    root,
                )
        emotion = field_value(block, "情绪")
        if has_substantive_value(emotion):
            mode_dimensions.update(split_values(emotion or ""))
        evidence_ids = set(re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", field_value(block, "证据卡") or ""))
        if len(evidence_ids) < 2:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "mode.evidence_too_few",
                f"{mode_id} 至少需要两张跨场景证据卡",
                mode_path,
                root,
            )
        elif len({card_scene_ids.get(card_id) for card_id in evidence_ids if card_scene_ids.get(card_id)}) < 2:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "mode.evidence_same_scene",
                f"{mode_id} 的证据卡必须来自至少两个不同证据单元",
                mode_path,
                root,
            )
        unknown_evidence = sorted(evidence_ids - evidence_card_ids)
        if unknown_evidence:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "mode.evidence_invalid",
                f"{mode_id} 引用了不存在、未核验或非原始语言的证据卡：" + ", ".join(unknown_evidence),
                mode_path,
                root,
            )
        incomplete_mode_evidence = sorted((evidence_ids & evidence_card_ids) - context_complete_card_ids)
        if incomplete_mode_evidence:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "mode.evidence_context_incomplete",
                f"{mode_id} 的情绪互动模式引用了语境不充分的表达卡：" + ", ".join(incomplete_mode_evidence),
                mode_path, root,
            )
        validate_rule_evidence_mapping(
            issues, mode_id, block, card_blocks_by_id, mode_path, root, level, "mode"
        )
    metrics["emotion_modes"] = len(mode_blocks)
    metrics["mode_dimensions"] = len(mode_dimensions)
    metrics["semantic_diversity_failures"] += add_semantic_diversity_issues(
        issues,
        mode_blocks,
        ("触发", "角色即时反应", "语言变化", "响应形态", "口语节奏"),
        "mode.semantic_boilerplate",
        "情绪关系模式",
        mode_path,
        root,
        level,
    )

    anti_path = root / "references" / "09-反角色对照.md"
    anti_text = read_text(anti_path) if anti_path.is_file() else ""
    anti_blocks = list(iter_anti_blocks(anti_text))
    duplicate_anti_ids = sorted(anti_id for anti_id, count in Counter(item[0] for item in anti_blocks).items() if count > 1)
    if duplicate_anti_ids:
        add_issue(issues, "error", "anti.duplicate_id", "反角色编号重复：" + ", ".join(duplicate_anti_ids), anti_path, root)
    anti_evidence_ids: set[str] = set()
    for anti_id, block in anti_blocks:
        for field in REQUIRED_ANTI_FIELDS:
            if not has_substantive_value(field_value(block, field)):
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "anti.field_missing",
                    f"{anti_id} 缺少可用字段：{field}",
                    anti_path,
                    root,
                )
        evidence_ids = set(re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", field_value(block, "证据卡") or ""))
        anti_evidence_ids.update(evidence_ids)
        if len(evidence_ids) < 2:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "anti.evidence_too_few",
                f"{anti_id} 至少需要两张跨场景证据卡说明角色的替代方式",
                anti_path,
                root,
            )
        elif len({card_scene_ids.get(card_id) for card_id in evidence_ids if card_scene_ids.get(card_id)}) < 2:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "anti.evidence_same_scene",
                f"{anti_id} 的证据卡必须来自至少两个不同证据单元",
                anti_path,
                root,
            )
        unknown_evidence = sorted(evidence_ids - evidence_card_ids)
        if unknown_evidence:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "anti.evidence_invalid",
                f"{anti_id} 引用了不存在、未核验或非原始语言的证据卡：" + ", ".join(unknown_evidence),
                anti_path,
                root,
            )
        incomplete_anti_evidence = sorted((evidence_ids & evidence_card_ids) - context_complete_card_ids)
        if incomplete_anti_evidence:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "anti.evidence_context_incomplete",
                f"{anti_id} 的反角色规律引用了语境不充分的表达卡：" + ", ".join(incomplete_anti_evidence),
                anti_path, root,
            )
        validate_rule_evidence_mapping(
            issues, anti_id, block, card_blocks_by_id, anti_path, root, level, "anti"
        )
    metrics["anti_rules"] = len(anti_blocks)
    metrics["anti_evidence_cards"] = len(anti_evidence_ids & evidence_card_ids)
    metrics["rule_evidence_mappings"] = sum(
        len(parse_evidence_mapping(field_value(block, "证据映射")))
        for _, block in core_blocks + voice_blocks + mode_blocks + anti_blocks + mind_blocks + expr_blocks
    )
    metrics["semantic_diversity_failures"] += add_semantic_diversity_issues(
        issues,
        anti_blocks,
        ("模式", "检测信号", "为什么不像", "角色替代结构"),
        "anti.semantic_boilerplate",
        "反角色规则",
        anti_path,
        root,
        level,
    )

    core_target, core_layer_target, core_evidence_target, voice_target, voice_layer_target, voice_evidence_target, mode_target, mode_dimension_target, anti_target = (
        (8, 6, 12, 8, 6, 12, 8, 6, 6)
        if persona_type in {"existing-character", "composite-character", "real-person-simulation"}
        else (8, 6, 12, 8, 6, 12, 8, 6, 6)
    )
    for metric_name, actual, target, code, label, path in (
        ("core_rules", len(core_blocks), core_target, "core_rule.count_low", "角色核心规则", core_path),
        ("core_layers", len(core_layers), core_layer_target, "core_rule.layers_low", "角色核心层级", core_path),
        ("core_evidence_cards", len(core_evidence_ids & evidence_card_ids), core_evidence_target, "core_rule.evidence_coverage_low", "角色核心证据卡", core_path),
        ("voice_rules", len(voice_blocks), voice_target, "voice.rules_low", "声纹规律", voice_path),
        ("voice_layers", len(voice_layers), voice_layer_target, "voice.layers_low", "声纹层级", voice_path),
        ("voice_evidence_cards", len(voice_evidence_ids & evidence_card_ids), voice_evidence_target, "voice.evidence_coverage_low", "声纹证据卡", voice_path),
        ("emotion_modes", len(mode_blocks), mode_target, "mode.count_low", "情绪关系模式", mode_path),
        ("mode_dimensions", len(mode_dimensions), mode_dimension_target, "mode.dimensions_low", "情绪维度", mode_path),
        ("anti_rules", len(anti_blocks), anti_target, "anti.count_low", "反角色规则", anti_path),
    ):
        if level == "release" and actual < target:
            add_issue(
                issues,
                target_severity,
                code,
                f"{label}仅 {actual} 个，正式版收集目标为 {target} 个",
                path,
                root,
            )

    scene_path = root / "references" / "04-工作场景迁移.md"
    scene_text = read_text(scene_path) if scene_path.is_file() else ""
    scene_blocks = list(iter_scene_blocks(scene_text))
    scenes = {scene_id for scene_id, _ in scene_blocks}
    missing_scenes = sorted(REQUIRED_SCENES - scenes)
    if missing_scenes:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "scene.coverage_missing",
            "缺少工作场景：" + ", ".join(missing_scenes),
            scene_path,
            root,
        )
    for scene_id, block in scene_blocks:
        if scene_id not in REQUIRED_SCENES:
            continue
        for field in REQUIRED_SCENE_FIELDS:
            if not has_substantive_value(field_value(block, field)):
                add_issue(
                    issues,
                    "error" if level == "release" else "warning",
                    "scene.field_missing",
                    f"{scene_id} 缺少可用字段：{field}",
                    scene_path,
                    root,
                )
        target_query = parse_tags(field_value(block, "目标检索"))
        invalid_target_keys = sorted(set(target_query) - REQUIRED_TAGS)
        if invalid_target_keys:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "scene.target_query_invalid",
                f"{scene_id} 的目标检索含工作域或未知标签：{', '.join(invalid_target_keys)}",
                scene_path, root,
            )
        if not (set(target_query) & {"speech_act", "trigger", "interaction"}):
            add_issue(
                issues, "error" if level == "release" else "warning",
                "scene.target_query_too_weak",
                f"{scene_id} 的目标检索至少要包含 speech_act、trigger 或 interaction",
                scene_path, root,
            )
        candidate_cards = set(re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", field_value(block, "候选原文卡") or ""))
        if len(candidate_cards) < 2:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "scene.cards_too_few",
                f"{scene_id} 至少需要两张候选原文卡",
                scene_path,
                root,
            )
        elif len({card_scene_ids.get(card_id) for card_id in candidate_cards if card_scene_ids.get(card_id)}) < 2:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "scene.cards_same_scene",
                f"{scene_id} 的候选原文卡必须来自至少两个不同证据单元",
                scene_path,
                root,
            )
        unknown_cards = sorted(candidate_cards - evidence_card_ids)
        if unknown_cards:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "scene.card_invalid",
                f"{scene_id} 引用了不存在、未核验或非原始语言的候选卡：" + ", ".join(unknown_cards),
                scene_path,
                root,
            )
        incomplete_scene_cards = sorted((candidate_cards & evidence_card_ids) - context_complete_card_ids)
        if incomplete_scene_cards:
            add_issue(
                issues, "error" if level == "release" else "warning",
                "scene.card_context_incomplete",
                f"{scene_id} 的候选卡缺少与媒介相适应的可核验语境：" + ", ".join(incomplete_scene_cards),
                scene_path, root,
            )
        candidate_voices = set(re.findall(r"\bVOICE-\d{2}\b", field_value(block, "候选声纹规律") or ""))
        if not candidate_voices:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "scene.voice_missing",
                f"{scene_id} 至少需要一条候选声纹规律",
                scene_path,
                root,
            )
        unknown_voices = sorted(candidate_voices - voice_ids)
        if unknown_voices:
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                "scene.voice_invalid",
                f"{scene_id} 引用了不存在的声纹规律：" + ", ".join(unknown_voices),
                scene_path,
                root,
            )
    metrics["work_scenes"] = len(scenes & REQUIRED_SCENES)
    metrics["semantic_diversity_failures"] += add_semantic_diversity_issues(
        issues,
        [(scene_id, block) for scene_id, block in scene_blocks if scene_id in REQUIRED_SCENES],
        ("触发", "目标检索", "原作互动功能", "角色即时反应", "临场表达策略", "主动表达条件", "事实嵌入方式", "禁止退化"),
        "scene.semantic_boilerplate",
        "工作场景迁移",
        scene_path,
        root,
        level,
    )

    if level == "release" and persona_type in {"existing-character", "composite-character", "real-person-simulation"}:
        active_targets = profile_targets or RESEARCH_PROFILES["一般"]
        min_expression_cards = int(active_targets["cards"])
        min_unique_expressions = int(active_targets["unique"])
        min_evidence_units = int(active_targets["evidence_units"])
        min_signature_cards = int(active_targets["signature"])
        min_sources = int(active_targets["sources"])
        min_primary_sources = int(active_targets["primary_sources"])
        if len(verified_fidelity_card_ids) < min_expression_cards:
            add_issue(
                issues,
                target_severity,
                "dialogue.exact_original_cards_low",
                f"经来源核对且含逐字原文的原始表达卡仅 {len(verified_fidelity_card_ids)} 张，正式版最低覆盖目标为 {min_expression_cards} 张",
                root / "references",
                root,
            )
        if len(verified_unique_originals) < min_unique_expressions:
            add_issue(
                issues,
                target_severity,
                "dialogue.unique_originals_low",
                f"去重后只有 {len(verified_unique_originals)} 条不同原始表达，{research_profile if profile_targets else '一般'}资料目标为 {min_unique_expressions} 条；重复口头禅可保留场景，但不能替代语料广度",
                root / "references",
                root,
            )
        performance_count = metrics["performance_verified_cards"]
        if performance_count < 1:
            verification_label = "原声" if original_medium in {"视听", "混合"} else ("原始版式" if original_medium == "文字" else "原始发布页面")
            add_issue(
                issues,
                "warning",
                "dialogue.performance_cards_low",
                f"尚无完成{verification_label}核验的表达卡；这是可选增强，不阻止正式版，也不得据文本推测未核验表现",
                root / "references",
                root,
            )
        if len(distinct_source_scenes) < min_evidence_units:
            add_issue(
                issues,
                target_severity,
                "dialogue.source_scenes_low",
                f"原始表达仅覆盖 {len(distinct_source_scenes)} 个不同证据单元，正式版最低覆盖目标为 {min_evidence_units} 个；证据单元可来自对话、叙事、独白、访谈、演讲、博客、社交媒体或书信",
                root / "references",
                root,
            )
        if len(signature_card_ids) < min_signature_cards:
            add_issue(
                issues,
                target_severity,
                "dialogue.signature_cards_low",
                f"核心或常用原始表达卡仅 {len(signature_card_ids)} 张，正式版最低覆盖目标为 {min_signature_cards} 张",
                root / "references",
                root,
            )
        if source_count < min_sources:
            add_issue(
                issues,
                target_severity,
                "sources.too_few",
                f"来源条目仅 {source_count} 个，正式版最低覆盖目标为 {min_sources} 个",
                sources_path,
                root,
            )
        if len(supporting_original_sources) < min_primary_sources:
            add_issue(
                issues,
                target_severity,
                "sources.original_too_few",
                f"被表达卡实际引用的一手来源仅 {len(supporting_original_sources)} 个，正式版最低覆盖目标为 {min_primary_sources} 个",
                sources_path,
                root,
            )
    if persona_asset_version >= 3:
        quality_result = quality.status(root)
        quality_metrics = quality_result.get("metrics", {})
        metrics["quality_loop_pass"] = bool(quality_result.get("valid"))
        metrics["quality_loop_status"] = quality_metrics.get("status", "missing")
        metrics["quality_loop_prompt_count"] = int(quality_metrics.get("prompt_count") or 0)
        metrics["quality_loop_blind_target_count"] = int(quality_metrics.get("blind_target_count") or 0)
        metrics["quality_loop_generic_control_count"] = int(quality_metrics.get("generic_control_identified_count") or 0)
        metrics["quality_loop_similar_role_count"] = int(quality_metrics.get("similar_role_distinguished_count") or 0)
        metrics["quality_loop_total_score"] = int(quality_metrics.get("total_score") or 0)
        for item in quality_result.get("issues", []):
            if not isinstance(item, dict):
                continue
            add_issue(
                issues,
                "error" if level == "release" else "warning",
                str(item.get("code") or "quality_loop.invalid"),
                str(item.get("message") or "Persona Quality Loop v4 未通过"),
                root / "tests" / "quality-loop.json",
                root,
            )

    target_met = False
    if persona_type in {"existing-character", "composite-character"}:
        targets = profile_targets or RESEARCH_PROFILES["一般"]
        target_met = (
            research_profile == "丰富"
            and research_status == "达标"
            and saturation_complete
            and len(all_ids) >= int(targets["cards"])
            and len(dimensions) >= int(targets["dimensions"])
            and len(verified_fidelity_card_ids) >= int(targets["cards"])
            and len(verified_unique_originals) >= int(targets["unique"])
            and len(distinct_source_scenes) >= int(targets["evidence_units"])
            and len(signature_card_ids) >= int(targets["signature"])
            and source_count >= int(targets["sources"])
            and len(supporting_original_sources) >= int(targets["primary_sources"])
            and len(core_blocks) >= 8
            and len(core_layers) >= 6
            and len(core_evidence_ids & evidence_card_ids) >= 12
            and len(voice_blocks) >= 8
            and MINIMUM_VOICE_LAYERS.issubset(voice_layers)
            and len(voice_evidence_ids & evidence_card_ids) >= 12
            and len(micro_blocks) >= 6
            and REQUIRED_MICRO_FUNCTIONS.issubset(micro_functions)
            and len(mode_blocks) >= 8
            and len(mode_dimensions) >= 6
            and len(anti_blocks) >= 6
            and len(scenes & REQUIRED_SCENES) == len(REQUIRED_SCENES)
            and len(bio_blocks) >= 8
            and len(bio_categories) >= 4
            and metrics["biography_baseline_complete"]
            and (persona_asset_version < 2 or metrics["effect_matrix_complete"])
            and (persona_asset_version < 2 or (
                len(mind_blocks) >= 6 and len(expr_blocks) >= 6
                and len(subjective_memory_ids) >= 6
                and quotation_policy_complete and verbosity_profile_complete
            ))
            and (persona_asset_version < 3 or (
                len(behavior_blocks) >= 12
                and metrics["behavior_function_coverage_complete"]
                and metrics["quality_loop_pass"]
            ))
            and metrics["independent_quality_pass"]
            and (persona_type != "composite-character" or metrics["composite_work_coverage_complete"])
            and case_count >= 24
            and metrics["semantic_diversity_failures"] == 0
        )
    elif persona_type == "real-person-simulation":
        targets = profile_targets or RESEARCH_PROFILES["一般"]
        target_met = (
            research_profile == "丰富"
            and research_status == "达标"
            and saturation_complete
            and len(all_ids) >= int(targets["cards"])
            and len(dimensions) >= int(targets["dimensions"])
            and len(verified_fidelity_card_ids) >= int(targets["cards"])
            and len(verified_unique_originals) >= int(targets["unique"])
            and len(distinct_source_scenes) >= int(targets["evidence_units"])
            and len(signature_card_ids) >= int(targets["signature"])
            and source_count >= int(targets["sources"])
            and len(supporting_original_sources) >= int(targets["primary_sources"])
            and len(core_blocks) >= 8
            and len(core_layers) >= 6
            and len(core_evidence_ids & evidence_card_ids) >= 12
            and len(voice_blocks) >= 8
            and MINIMUM_VOICE_LAYERS.issubset(voice_layers)
            and len(voice_evidence_ids & evidence_card_ids) >= 12
            and len(micro_blocks) >= 6
            and REQUIRED_MICRO_FUNCTIONS.issubset(micro_functions)
            and len(mode_blocks) >= 8
            and len(mode_dimensions) >= 6
            and len(anti_blocks) >= 6
            and len(scenes & REQUIRED_SCENES) == len(REQUIRED_SCENES)
            and len(bio_blocks) >= 8
            and len(bio_categories) >= 4
            and metrics["biography_baseline_complete"]
            and (persona_asset_version < 2 or metrics["effect_matrix_complete"])
            and (persona_asset_version < 2 or (
                len(mind_blocks) >= 6 and len(expr_blocks) >= 6
                and len(subjective_memory_ids) >= 6
                and quotation_policy_complete and verbosity_profile_complete
            ))
            and (persona_asset_version < 3 or (
                len(behavior_blocks) >= 12
                and metrics["behavior_function_coverage_complete"]
                and metrics["quality_loop_pass"]
            ))
            and metrics["independent_quality_pass"]
            and case_count >= 24
            and metrics["semantic_diversity_failures"] == 0
        )
    elif persona_type in {"original-persona", "composite-original"}:
        target_met = (
            len(all_ids) >= 20
            and len(dimensions) >= 8
            and len(core_blocks) >= 8
            and len(voice_blocks) >= 8
            and len(micro_blocks) >= 6
            and REQUIRED_MICRO_FUNCTIONS.issubset(micro_functions)
            and len(mode_blocks) >= 8
            and len(anti_blocks) >= 6
            and len(bio_blocks) >= 8
            and len(bio_categories) >= 4
            and metrics["biography_baseline_complete"]
            and (persona_asset_version < 2 or metrics["effect_matrix_complete"])
            and (persona_asset_version < 2 or (
                len(mind_blocks) >= 6 and len(expr_blocks) >= 6
                and len(subjective_memory_ids) >= 6
                and quotation_policy_complete and verbosity_profile_complete
            ))
            and (persona_asset_version < 3 or (
                len(behavior_blocks) >= 12
                and metrics["behavior_function_coverage_complete"]
                and metrics["quality_loop_pass"]
            ))
            and case_count >= 23
            and metrics["semantic_diversity_failures"] == 0
        )
    if target_met:
        metrics["coverage_path"] = "target-met"
    elif exhaustion_complete:
        metrics["coverage_path"] = "exhausted"
    else:
        metrics["coverage_path"] = "incomplete"
    unknown_source_ids = sorted(referenced_source_ids - set(source_ids))
    if unknown_source_ids:
        add_issue(
            issues,
            "error",
            "sources.unknown_reference",
            "对白卡片引用了不存在的来源：" + ", ".join(unknown_source_ids),
            sources_path,
            root,
        )

    selector_path = root / "scripts" / "select_dialogues.py"
    if selector_path.is_file():
        try:
            compile(read_text(selector_path), str(selector_path), "exec")
        except SyntaxError as exc:
            add_issue(
                issues,
                "error",
                "selector.syntax_error",
                f"对白选择器无法解析：{exc.msg}（第 {exc.lineno} 行）",
                selector_path,
                root,
            )

    response_checker_path = root / "scripts" / "check_response.py"
    if response_checker_path.is_file():
        response_checker_text = read_text(response_checker_path)
        try:
            compile(response_checker_text, str(response_checker_path), "exec")
        except SyntaxError as exc:
            add_issue(
                issues,
                "error",
                "response_checker.syntax_error",
                f"回复检测器无法解析：{exc.msg}（第 {exc.lineno} 行）",
                response_checker_path,
                root,
            )
        version_match = re.search(r"^CHECKER_CONTRACT_VERSION\s*=\s*(\d+)\s*$", response_checker_text, re.MULTILINE)
        if level == "release" and (not version_match or int(version_match.group(1)) != RESPONSE_CHECKER_CONTRACT_VERSION):
            add_issue(
                issues,
                "error",
                "response_checker.contract_version_stale",
                "回复检测器不是当前严格门禁版本；更新已有角色时必须同步模板中的 check_response.py",
                response_checker_path,
                root,
            )
        canonical_response_checker = TEMPLATE_ROOT / "scripts" / "check_response.py"
        if level == "release" and canonical_response_checker.is_file() and sha256_file(response_checker_path) != sha256_file(canonical_response_checker):
            add_issue(
                issues,
                "error",
                "response_checker.template_mismatch",
                "回复检测器与当前 Persona.skill 模板不一致；不得通过只改版本号保留旧的宽松门禁",
                response_checker_path,
                root,
            )

    openai_path = root / "agents" / "openai.yaml"
    if openai_path.is_file():
        openai_text = read_text(openai_path)
        for key in ("display_name", "short_description", "default_prompt"):
            if not re.search(rf"^\s*{key}:\s*\".+\"\s*$", openai_text, re.MULTILINE):
                add_issue(issues, "error", "openai.field_invalid", f"agents/openai.yaml 缺少带引号的 {key}", openai_path, root)
        short_match = re.search(r'^\s*short_description:\s*"(.+)"\s*$', openai_text, re.MULTILINE)
        if short_match and not 25 <= len(short_match.group(1)) <= 64:
            add_issue(
                issues,
                "error",
                "openai.short_description_length",
                "short_description 必须为 25–64 个字符",
                openai_path,
                root,
            )
        skill_name = ""
        if skill_path.is_file():
            skill_name = parse_frontmatter(read_text(skill_path))[0].get("name", "")
        prompt_match = re.search(r'^\s*default_prompt:\s*"(.+)"\s*$', openai_text, re.MULTILINE)
        if skill_name and prompt_match and f"${skill_name}" not in prompt_match.group(1):
            add_issue(issues, "error", "openai.default_prompt", f"default_prompt 必须明确包含 ${skill_name}", openai_path, root)

    error_count = sum(issue.severity == "error" for issue in issues)
    warning_count = sum(issue.severity == "warning" for issue in issues)
    return {
        "valid": error_count == 0,
        "level": level,
        "path": str(root),
        "metrics": metrics,
        "placeholder_count": placeholder_count,
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": [asdict(issue) for issue in issues],
    }


def cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    result = validate_skill(root, args.level)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if result["valid"] else "FAIL"
        metrics = result["metrics"]
        print(f"[{status}] {result['path']}")
        print(
            f"level={result['level']} persona_type={metrics['persona_type']} "
            f"version={metrics['version']} research_status={metrics['research_status']} "
            f"coverage_path={metrics['coverage_path']} research_rounds={metrics['research_rounds']} "
            f"candidate_expressions={metrics['research_candidates']} formal_expressions={metrics['research_formal']} "
            f"pending_expressions={metrics['research_pending']} rejected_expressions={metrics['research_rejected']} "
            f"cards={metrics['cards']} exact_original_cards={metrics['exact_original_cards']} "
            f"rich_corpus_ready={metrics['rich_corpus_ready']} recommended_max_cards={metrics['rich_corpus_recommended_max_cards']} "
            f"performance_verified_cards={metrics['performance_verified_cards']} "
            f"distinct_evidence_units={metrics['distinct_evidence_units']} "
            f"context_complete_cards={metrics['context_complete_cards']} "
            f"signature_cards={metrics['signature_cards']} "
            f"canonical_authored_cards={metrics['canonical_authored_cards']} "
            f"derived_cards={metrics['derived_cards']} "
            f"dimensions={metrics['distinct_emotions_and_intents']} "
            f"asset_version={metrics['persona_asset_version']} core_rules={metrics['core_rules']} core_layers={metrics['core_layers']} "
            f"core_evidence_cards={metrics['core_evidence_cards']} "
            f"voice_rules={metrics['voice_rules']} voice_layers={metrics['voice_layers']} "
            f"voice_evidence_cards={metrics['voice_evidence_cards']} "
            f"anti_rules={metrics['anti_rules']} anti_evidence_cards={metrics['anti_evidence_cards']} "
            f"rule_evidence_mappings={metrics['rule_evidence_mappings']} "
            f"biography_entries={metrics['biography_entries']} "
            f"biography_categories={metrics['biography_categories']} "
            f"biography_baseline_complete={metrics['biography_baseline_complete']} "
            f"mind_rules={metrics['mind_rules']} expression_rules={metrics['expression_rules']} "
            f"behavior_rules={metrics['behavior_rules']} behavior_functions={metrics['behavior_functions']} "
            f"behavior_function_coverage_complete={metrics['behavior_function_coverage_complete']} "
            f"subjective_memory_entries={metrics['subjective_memory_entries']} analogy_domains={metrics['analogy_domains']} "
            f"quotation_policy_complete={metrics['quotation_policy_complete']} "
            f"verbosity_profile_complete={metrics['verbosity_profile_complete']} "
            f"effect_matrix_rows={metrics['effect_matrix_rows']} "
            f"effect_matrix_complete={metrics['effect_matrix_complete']} "
            f"composite_work_count={metrics['composite_work_count']} "
            f"composite_work_coverage_complete={metrics['composite_work_coverage_complete']} "
            f"composite_work_cards_min={metrics['composite_work_cards_min']} "
            f"composite_work_card_share_max={metrics['composite_work_card_share_max']:.4f} "
            f"composite_detected_work_counts={';'.join(metrics['composite_detected_work_counts']) or 'none'} "
            f"independent_quality_pass={metrics['independent_quality_pass']} "
            f"quality_loop_pass={metrics['quality_loop_pass']} quality_loop_status={metrics['quality_loop_status']} "
            f"quality_loop_prompts={metrics['quality_loop_prompt_count']} "
            f"quality_loop_blind={metrics['quality_loop_blind_target_count']} "
            f"quality_loop_generic={metrics['quality_loop_generic_control_count']} "
            f"quality_loop_similar={metrics['quality_loop_similar_role_count']} "
            f"quality_loop_score={metrics['quality_loop_total_score']} "
            f"runtime_prompt_natural={metrics['runtime_prompt_natural_count']}/{metrics['runtime_prompt_count']} "
            f"runtime_repeated_fragment_max={metrics['runtime_repeated_fragment_max']} "
            f"evaluation_reason_unique_ratio={metrics['evaluation_reason_unique_ratio']} "
            f"character_presence_coverage={metrics['character_presence_coverage']} "
            f"semantic_diversity_failures={metrics['semantic_diversity_failures']} "
            f"emotion_modes={metrics['emotion_modes']} mode_dimensions={metrics['mode_dimensions']} "
            f"scenes={metrics['work_scenes']} cases={metrics['validation_cases']} "
            f"sources={metrics['sources']} original_sources={metrics['original_sources']}"
        )
        for item in result["issues"]:
            location = f" ({item['file']})" if item["file"] else ""
            print(f"{item['severity'].upper()} {item['code']}: {item['message']}{location}")
    return 0 if result["valid"] else 1


def classify_loop_stage(error_codes: list[str]) -> tuple[str, str]:
    quality_routes = (
        ("quality_loop.layer.source", "RESEARCH", "按失败样本补充代表性来源、语境与行为功能覆盖，然后重新冻结人格并生成新隐藏题。"),
        ("quality_loop.layer.behavior-model", "REDISTILL", "根据失败样本重写 BEHAV/MIND/EXPR 的区别性机制和近失对照，然后重新冻结人格。"),
        ("quality_loop.layer.retrieval", "RETRIEVE", "修正选择器检索条件、工作迁移与证据组合，再用新运行记录重测。"),
        ("quality_loop.layer.generation", "REGENERATE", "按 v4 response_contract 修复回答生成、人物推理动作和可见信号实现，再重跑隐藏场景。"),
        ("quality_loop.layer.runtime", "RUNTIME", "核对实际运行时加载、前缀、角色哈希与响应记录后重测。"),
        ("quality_loop.layer.evaluation", "EVALUATE", "换用未参与生成的隔离上下文完成逐条盲评，不能由生成者自评。"),
    )
    for code, stage, action in quality_routes:
        if code in error_codes:
            return stage, action
    priorities = (
        (
            "RESEARCH",
            ("research.", "sources.", "dialogue.", "composite."),
            "继续扩大或核验来源，修正原文卡、真实语境与调研轮次记录；完成后重新运行 iteration-gate。",
        ),
        (
            "REDISTILL",
            ("core_rule.", "voice.", "micro.", "mode.", "anti.", "scene.", "mind.", "expression.", "behavior."),
            "从可计数证据卡重新蒸馏规则，逐条修复证据映射和检索条件；禁止批量套话，完成后重新运行 iteration-gate。",
        ),
        (
            "TEST",
            ("tests.", "quality_loop."),
            "实际运行后冻结隐藏题、真实回答与隔离评估；失败必须按归因层修复后重新生成新一轮测试，不能改分数文件。",
        ),
        (
            "GENERATE",
            ("persona.", "content.", "biography.", "openai.", "skill."),
            "修复人格结构、人物背景、占位内容或 Skill 元数据，然后重新运行 iteration-gate。",
        ),
    )
    for stage, prefixes, action in priorities:
        if any(code.startswith(prefixes) for code in error_codes):
            return stage, action
    return "FIX", "按错误代码修复当前生成物，然后重新运行 iteration-gate。"


LOOP_STAGE_PREFIXES = {
    "RESEARCH": ("research.", "sources.", "dialogue.", "composite."),
    "REDISTILL": ("core_rule.", "voice.", "micro.", "mode.", "anti.", "scene.", "mind.", "expression.", "behavior."),
    "TEST": ("tests.", "quality_loop."),
    "GENERATE": ("persona.", "content.", "biography.", "openai.", "skill."),
}
RESEARCH_IDENTITY_CODES = {
    "persona.type_invalid", "persona.medium_invalid", "persona.original_language_missing",
}


def unique_error_codes(result: dict[str, object], prefixes: tuple[str, ...] | None = None) -> list[str]:
    codes: list[str] = []
    for issue in result["issues"]:
        code = str(issue["code"])
        if issue["severity"] != "error":
            continue
        if prefixes is not None and not code.startswith(prefixes):
            continue
        if code not in codes:
            codes.append(code)
    return codes


def cmd_research_gate(args: argparse.Namespace) -> int:
    """Gate only the source corpus before any rule distillation or testing."""
    root = Path(args.path).expanduser().resolve()
    result = validate_skill(root, "release")
    metrics = result["metrics"]
    research_codes = unique_error_codes(result, LOOP_STAGE_PREFIXES["RESEARCH"])
    for code in unique_error_codes(result):
        if code in RESEARCH_IDENTITY_CODES and code not in research_codes:
            research_codes.append(code)

    rich_targets = RESEARCH_PROFILES["丰富"]
    if research_codes:
        print("PERSONA_RESEARCH_STATE=INCOMPLETE")
        print("RESEARCH_READY=false")
        print("MUST_CONTINUE=true")
        print("CREATE_LOOP_LOCK=active")
        print("RESPONSE_MODE=CONTINUE_TOOL_LOOP")
        print("TERMINAL_ALLOWED=false")
        print("USER_REPORT_ALLOWED=false")
        print("LOOP_STAGE=RESEARCH")
        print("PROGRESS_FEEDBACK_ALLOWED=true")
        print("FEEDBACK_REQUIRED=true")
        print("FEEDBACK_STAGE=资料采集")
        print(f"ACTIVE_STAGE_ERROR_COUNT={len(research_codes)}")
        print("ERROR_CODES=" + ",".join(research_codes[:20]))
        print(f"RESEARCH_PROFILE={metrics['research_profile']}")
        print(f"RESEARCH_STATUS={metrics['research_status']}")
        print(f"CURRENT_CARDS={metrics['cards']}")
        print(f"REQUIRED_CARDS={rich_targets['cards']}")
        print(f"RICH_CORPUS_READY={str(metrics['rich_corpus_ready']).lower()}")
        print(f"RECOMMENDED_MAX_CARDS={metrics['rich_corpus_recommended_max_cards']}")
        print(f"CURRENT_UNIQUE_EXPRESSIONS={metrics['unique_original_expressions']}")
        print(f"REQUIRED_UNIQUE_EXPRESSIONS={rich_targets['unique']}")
        print(f"CURRENT_EVIDENCE_UNITS={metrics['distinct_evidence_units']}")
        print(f"REQUIRED_EVIDENCE_UNITS={rich_targets['evidence_units']}")
        print(f"CURRENT_CONTEXT_COMPLETE_CARDS={metrics['context_complete_cards']}")
        print(f"CURRENT_SIGNATURE_CARDS={metrics['signature_cards']}")
        print(f"CANDIDATE_EXPRESSIONS={metrics['research_candidates']}")
        print(f"FORMAL_EXPRESSIONS={metrics['research_formal']}")
        print(f"PENDING_EXPRESSIONS={metrics['research_pending']}")
        print(f"REJECTED_EXPRESSIONS={metrics['research_rejected']}")
        print(f"COMPOSITE_WORK_COUNT={metrics['composite_work_count']}")
        print(f"COMPOSITE_WORK_COVERAGE_COMPLETE={str(metrics['composite_work_coverage_complete']).lower()}")
        print(f"COMPOSITE_WORK_CARDS_MIN={metrics['composite_work_cards_min']}")
        print(f"COMPOSITE_WORK_GAPS={';'.join(metrics['composite_work_gaps']) or 'none'}")
        print("AUTO_DETECTED_WORKS=" + ";".join(metrics["composite_detected_work_counts"]))
        print(f"RESEARCH_ROUNDS={metrics['research_rounds']}")
        print(f"EXPANSION_ROUNDS={metrics['research_expansion_rounds']}")
        print("RESEARCH_ROUND_SUMMARY=" + ";".join(metrics["research_round_summary"]))
        print("NEXT_ACTION=继续调研原始表达与完整语境；每轮必须扩大新的来源类别、站点、语言、版本、别名或场景范围。已有角色类必须达到至少 80 张已核验卡和丰富档后才能重跑 research-gate 进入蒸馏；已穷尽只能记录缺口，不能放行。")
        print(f"RETRY_COMMAND=python scripts/persona_tool.py research-gate \"{root}\"")
        print("NEXT_FEEDBACK=阶段：资料采集；已完成：本轮校验和缺口盘点；下一步：扩展新的作品/版本/站点/场景并完成核验，然后再次回报每轮数量。")
        return 1

    print("PERSONA_RESEARCH_STATE=READY")
    print("RESEARCH_READY=true")
    print("MUST_CONTINUE=true")
    print("CREATE_LOOP_LOCK=active")
    print("RESPONSE_MODE=CONTINUE_TOOL_LOOP")
    print("TERMINAL_ALLOWED=false")
    print("USER_REPORT_ALLOWED=false")
    print("LOOP_STAGE=REDISTILL")
    print("PROGRESS_FEEDBACK_ALLOWED=true")
    print("FEEDBACK_REQUIRED=true")
    print("FEEDBACK_STAGE=资料采集")
    print(f"RESEARCH_PROFILE={metrics['research_profile']}")
    research_path = "exhausted" if metrics["research_status"] == "已穷尽" else "target-met"
    print(f"RESEARCH_PATH={research_path}")
    print(f"CURRENT_CARDS={metrics['cards']}")
    print(f"RICH_CORPUS_READY={str(metrics['rich_corpus_ready']).lower()}")
    print(f"RECOMMENDED_MAX_CARDS={metrics['rich_corpus_recommended_max_cards']}")
    print(f"CURRENT_EVIDENCE_UNITS={metrics['distinct_evidence_units']}")
    print(f"COMPOSITE_WORK_COUNT={metrics['composite_work_count']}")
    print(f"COMPOSITE_WORK_COVERAGE_COMPLETE={str(metrics['composite_work_coverage_complete']).lower()}")
    print(f"COMPOSITE_WORK_CARDS_MIN={metrics['composite_work_cards_min']}")
    print(f"COMPOSITE_WORK_CARD_SHARE_MAX={metrics['composite_work_card_share_max']:.4f}")
    print(f"COMPOSITE_WORK_GAPS={';'.join(metrics['composite_work_gaps']) or 'none'}")
    print("AUTO_DETECTED_WORKS=" + ";".join(metrics["composite_detected_work_counts"]))
    print("RESEARCH_ROUND_SUMMARY=" + ";".join(metrics["research_round_summary"]))
    print("NEXT_ACTION=资料闸门已通过；现在才从原文证据与真实语境蒸馏角色核心、声纹、微互动、情绪模式、反角色规则和工作迁移，然后运行 iteration-gate。")
    print("NEXT_FEEDBACK=阶段：资料采集；已完成：逐作品覆盖和资料闸门通过；下一步：蒸馏规则、生成候选回答并进行真实对话测试。")
    return 0


def runtime_paths_from_args(args: argparse.Namespace) -> lifecycle.RuntimePaths:
    home_value = getattr(args, "home", None)
    home = Path(home_value).expanduser().resolve() if home_value else None
    env = None
    if home is not None:
        env = dict(os.environ)
        for key in lifecycle.RUNTIME_PATH_ENV_KEYS:
            env.pop(key, None)
    runtime, _ = lifecycle.detect_runtime(
        getattr(args, "runtime", "auto"), home=home, env=env, skill_root=SKILL_ROOT
    )
    return lifecycle.resolve_runtime_paths(runtime, home=home, env=env, skill_root=SKILL_ROOT)


def role_registration_metadata(root: Path, validation: dict[str, object], args: argparse.Namespace) -> dict[str, object]:
    skill_text = read_text(root / "SKILL.md")
    metadata, error = parse_frontmatter(skill_text)
    if error:
        raise lifecycle.LifecycleError(error)
    role_id = metadata.get("name", "")
    if not lifecycle.ROLE_ID_RE.fullmatch(role_id):
        raise lifecycle.LifecycleError("生成角色的 Skill ID 必须是 persona-<ascii-slug>：%s" % role_id)
    prefix = extract_reply_prefix(skill_text) or ""
    prefix_name = prefix[:-1] if prefix.endswith("：") else prefix
    display_name = (getattr(args, "display_name", None) or prefix_name).strip()
    if not display_name:
        heading = re.search(r"^#\s+(.+?)人格\s*$", skill_text, re.MULTILINE)
        display_name = heading.group(1).strip() if heading else role_id
    core_text = read_text(root / "references" / "01-角色核心.md")
    source_match = re.search(r"^-\s*原角色或参考身份[：:]\s*(.+?)\s*$", core_text, re.MULTILINE)
    source_identity = getattr(args, "source_identity", None) or (source_match.group(1).strip() if source_match else display_name)
    aliases = list(getattr(args, "alias", None) or [])
    return {
        "role_id": role_id,
        "display_name": display_name,
        "reply_prefix": prefix or (display_name + "："),
        "aliases": aliases,
        "persona_type": str(validation["metrics"].get("persona_type", "unknown")),
        "source_identity": source_identity,
        "validation_hash": lifecycle.directory_hash(root),
        "manager_tool": str((SKILL_ROOT / "scripts" / "persona_tool.py").resolve()),
    }


def print_lifecycle_error(exc: Exception) -> int:
    print("错误：%s" % exc, file=sys.stderr)
    return 1


def emit_gate(
    root: Path,
    activation_status: str,
    command_name: str,
    runtime: str = "auto",
    home: str | None = None,
) -> int:
    result = validate_skill(root, "release")
    if not result["valid"]:
        error_codes = unique_error_codes(result)
        stage, action = classify_loop_stage(error_codes)
        stage_prefixes = LOOP_STAGE_PREFIXES.get(stage)
        stage_codes = unique_error_codes(result, stage_prefixes) if stage_prefixes else error_codes
        deferred_codes = [code for code in error_codes if code not in stage_codes]
        print("PERSONA_BUILD_STATE=INCOMPLETE")
        print("MUST_CONTINUE=true")
        print("CREATE_LOOP_LOCK=active")
        print("RESPONSE_MODE=CONTINUE_TOOL_LOOP")
        print("TERMINAL_ALLOWED=false")
        print("USER_REPORT_ALLOWED=false")
        print("FINAL_REPORT_ALLOWED=false")
        print("STATUS_REPLY_ALLOWED=true")
        print("PROGRESS_FEEDBACK_ALLOWED=true")
        print("FEEDBACK_REQUIRED=true")
        print(f"FEEDBACK_STAGE={stage}")
        print(f"LOOP_STAGE={stage}")
        print(f"ACTIVE_STAGE_ERROR_COUNT={len(stage_codes)}")
        print(f"DEFERRED_ERROR_COUNT={len(deferred_codes)}")
        print("ERROR_CODES=" + ",".join(stage_codes[:20]))
        print(f"NEXT_ACTION={action}")
        print(f"NEXT_FEEDBACK=阶段：{stage}；已完成：本轮门禁已定位 {len(stage_codes)} 个当前阶段问题；下一步：按上述动作修复并继续运行工具，不在此处结束创建。")
        if stage == "RESEARCH":
            print(f"STAGE_GATE_COMMAND=python scripts/persona_tool.py research-gate \"{root}\"")
        runtime_args = "" if runtime == "auto" else f" --runtime {runtime}"
        home_args = "" if not home else f' --home "{home}"'
        print(f"RETRY_COMMAND=python scripts/persona_tool.py {command_name} \"{root}\" --activation-status {activation_status}{runtime_args}{home_args}")
        return 1
    if activation_status == "pending":
        try:
            pending_paths = runtime_paths_from_args(argparse.Namespace(runtime=runtime, home=home))
        except lifecycle.LifecycleError:
            pending_paths = None
        print("PERSONA_BUILD_STATE=VALIDATED_NOT_ENABLED")
        print("MUST_CONTINUE=true")
        print("CREATE_LOOP_LOCK=active")
        print("RESPONSE_MODE=CONTINUE_TOOL_LOOP")
        print("TERMINAL_ALLOWED=false")
        print("USER_REPORT_ALLOWED=false")
        print("FINAL_REPORT_ALLOWED=false")
        print("STATUS_REPLY_ALLOWED=true")
        print("PROGRESS_FEEDBACK_ALLOWED=true")
        print("FEEDBACK_REQUIRED=true")
        print("FEEDBACK_STAGE=启用核对")
        print("LOOP_STAGE=ENABLE")
        if pending_paths is not None and not pending_paths.supports_persistent_activation:
            print("NEXT_ACTION=当前运行时只提供 Skill 级加载；运行 register 注册角色，再以 registered 重跑 completion-gate。")
            print("NEXT_FEEDBACK=阶段：启用核对；已完成：正式校验通过；下一步：完成运行时注册并回读绑定回执。")
        else:
            print("NEXT_ACTION=按用户要求启用当前会话或持久作用域；完成后以 enabled 重新运行 completion-gate。")
            print("NEXT_FEEDBACK=阶段：启用核对；已完成：正式校验通过；下一步：写入全局绑定并回读哈希回执。")
        return 1

    if activation_status in {"enabled", "registered"}:
        namespace = argparse.Namespace(runtime=runtime, home=home)
        try:
            paths = runtime_paths_from_args(namespace)
            if activation_status == "enabled":
                verification = lifecycle.verify_activation(
                    paths,
                    role_path=root,
                    expected_role_hash=lifecycle.directory_hash(root),
                )
            elif paths.supports_persistent_activation:
                verification = {
                    "valid": False,
                    "errors": ["该运行时支持持久启用，registered 不能代替可验证的 enabled 回执"],
                }
            else:
                verification = lifecycle.verify_registration(
                    paths,
                    role_path=root,
                    expected_role_hash=lifecycle.directory_hash(root),
                )
        except lifecycle.LifecycleError as exc:
            verification = {"valid": False, "errors": [str(exc)]}
        if not verification["valid"]:
            state = "VALIDATED_ACTIVATION_STALE" if activation_status == "enabled" else "VALIDATED_REGISTRATION_STALE"
            print("PERSONA_BUILD_STATE=" + state)
            print("MUST_CONTINUE=true")
            print("CREATE_LOOP_LOCK=active")
            print("RESPONSE_MODE=CONTINUE_TOOL_LOOP")
            print("TERMINAL_ALLOWED=false")
            print("USER_REPORT_ALLOWED=false")
            print("FINAL_REPORT_ALLOWED=false")
            print("STATUS_REPLY_ALLOWED=true")
            print("PROGRESS_FEEDBACK_ALLOWED=true")
            print("FEEDBACK_REQUIRED=true")
            print("FEEDBACK_STAGE=启用核对")
            print("LOOP_STAGE=ENABLE")
            error_code = "activation.receipt_invalid" if activation_status == "enabled" else "registration.invalid"
            print("ERROR_CODES=" + error_code)
            print("ACTIVATION_ERRORS=" + " | ".join(str(item) for item in verification["errors"]))
            if activation_status == "enabled":
                print(f'NEXT_ACTION=重新运行 enable "{root}"，回读全局绑定并生成新回执，然后重跑 completion-gate。')
                print("NEXT_FEEDBACK=阶段：启用核对；已完成：发现启用回执或绑定已过期；下一步：重新启用并核对实际文件哈希。")
            else:
                print(f'NEXT_ACTION=重新运行 register "{root}"，核对角色路径与哈希，然后重跑 completion-gate。')
                print("NEXT_FEEDBACK=阶段：启用核对；已完成：发现注册回执失效；下一步：重新注册并核对角色路径与哈希。")
            return 1

    print("PERSONA_BUILD_STATE=COMPLETE")
    print("MUST_CONTINUE=false")
    print("CREATE_LOOP_LOCK=released")
    print("RESPONSE_MODE=FINAL_REPORT")
    print("TERMINAL_ALLOWED=true")
    print("USER_REPORT_ALLOWED=true")
    print("FINAL_REPORT_ALLOWED=true")
    print("STATUS_REPLY_ALLOWED=true")
    print("PROGRESS_FEEDBACK_ALLOWED=false")
    print("FEEDBACK_REQUIRED=false")
    print("FEEDBACK_STAGE=完成")
    print("LOOP_STAGE=COMPLETE")
    print(f"ACTIVATION_STATUS={activation_status}")
    print(f"PERSONA_PATH={root}")
    return 0


def cmd_iteration_gate(args: argparse.Namespace) -> int:
    """Return the next mandatory stage for an active persona build."""
    root = Path(args.path).expanduser().resolve()
    return emit_gate(root, args.activation_status, "iteration-gate", args.runtime, args.home)


def cmd_completion_gate(args: argparse.Namespace) -> int:
    """Provide a deterministic final-answer gate for persona creation tasks."""
    root = Path(args.path).expanduser().resolve()
    return emit_gate(root, args.activation_status, "completion-gate", args.runtime, args.home)


def _print_quality_progress(stage: str, completed: str, next_action: str) -> None:
    print("PERSONA_BUILD_STATE=INCOMPLETE")
    print("MUST_CONTINUE=true")
    print("CREATE_LOOP_LOCK=active")
    print("RESPONSE_MODE=CONTINUE_TOOL_LOOP")
    print("TERMINAL_ALLOWED=false")
    print("FINAL_REPORT_ALLOWED=false")
    print("FEEDBACK_REQUIRED=true")
    print(f"FEEDBACK_STAGE={stage}")
    print(f"NEXT_FEEDBACK=阶段：{stage}；已完成：{completed}；下一步：{next_action}")


def cmd_quality_init(args: argparse.Namespace) -> int:
    try:
        result = quality.init_run(
            Path(args.path).expanduser().resolve(), args.generator_context_id, args.runtime,
            args.runtime_mode, args.iteration, args.seed,
        )
        print(f"QUALITY_RUN_ID={result['run_id']}")
        print(f"QUALITY_CHALLENGE={result['challenge_path']}")
        print(f"PERSONA_BUNDLE_SHA256={result['persona_bundle_sha256']}")
        print(f"PROMPT_COUNT={result['prompt_count']}")
        print("LOOP_STAGE=RUNTIME-TEST")
        _print_quality_progress("真实对话测试", "人格已冻结并在冻结后抽取隐藏场景", "让实际 Runtime 逐题生成连续回答，保存 v4 generation_trace 后运行 quality-record。")
        print("NEXT_ACTION=不得预写答案或由静态样例代替；使用 challenge.json 的原始问题在实际 Runtime 中生成同一连续对话。")
        return 0
    except quality.QualityLoopError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


def cmd_quality_record(args: argparse.Namespace) -> int:
    try:
        result = quality.record_responses(
            Path(args.path).expanduser().resolve(), args.run_id,
            Path(args.responses).expanduser().resolve(),
            args.generic_context_id, args.similar_context_id,
            Path(args.binding_receipt).expanduser().resolve() if args.binding_receipt else None,
        )
        print(f"QUALITY_RUN_ID={result['run_id']}")
        print(f"RESPONSES_PATH={result['responses_path']}")
        print(f"BLIND_BUNDLE_PATH={result['blind_bundle_path']}")
        print(f"CHECKER_STATUS={result['checker']['status']}")
        print("LOOP_STAGE=INDEPENDENT-EVALUATION")
        _print_quality_progress("真实对话测试", "目标人格、通用助手和相似人物对照已来自不同上下文，实际回答及可见角色信号已通过可信检查器", "只把 blind-evaluation-bundle.json 交给未参与任何回答生成的隔离上下文逐条盲评，再运行 quality-evaluate。")
        print("NEXT_ACTION=评估者不得读取 blind-evaluation-key.json；逐条把 C1/C2/C3 归为目标、通用和相似人物，并保存回答摘录、理由和失败归因。")
        return 0
    except quality.QualityLoopError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


def cmd_quality_evaluate(args: argparse.Namespace) -> int:
    try:
        result = quality.evaluate_run(
            Path(args.path).expanduser().resolve(), args.run_id,
            Path(args.evaluation).expanduser().resolve(), args.evaluator_context_id,
        )
        evaluation = result.get("evaluation", {})
        print(f"QUALITY_RUN_ID={result['run_id']}")
        print(f"QUALITY_STATUS={result['status']}")
        print(f"TOTAL_SCORE={evaluation.get('total_score', 0)}")
        print(f"BLIND_TARGET_COUNT={evaluation.get('blind_target_count', 0)}")
        print(f"GENERIC_CONTROL_IDENTIFIED_COUNT={evaluation.get('generic_control_identified_count', 0)}")
        print(f"SIMILAR_ROLE_DISTINGUISHED_COUNT={evaluation.get('similar_role_distinguished_count', 0)}")
        if result["status"] == "pass":
            print("LOOP_STAGE=ENABLE")
            _print_quality_progress("独立质量评估", "隐藏场景、角色辨识、相似角色区分、情绪价值和事实风险全部通过", "运行 release validate；通过后立即启用并核对 completion-gate。")
            print("NEXT_ACTION=运行 validate --level release；若人格哈希仍一致，再 enable/register 并运行 completion-gate。")
            return 0
        status_result = quality.status(Path(args.path).expanduser().resolve())
        stage, action = quality.route_status(status_result)
        print(f"LOOP_STAGE={stage}")
        print("FAILURE_LAYERS=" + ",".join(result.get("failure_layers", [])))
        print("REPAIR_TARGETS=" + ",".join(result.get("repair_targets", [])))
        _print_quality_progress("独立质量评估", "逐条盲评已完成但未达到人物效果门槛", action)
        print(f"NEXT_ACTION={action} 修复后必须重新 quality-init，旧隐藏题与旧分数不得复用。")
        return 1
    except quality.QualityLoopError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


def cmd_quality_status(args: argparse.Namespace) -> int:
    result = quality.status(Path(args.path).expanduser().resolve())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 1
    metrics = result["metrics"]
    print(f"QUALITY_STATUS={metrics['status']}")
    print(f"QUALITY_RUN_ID={metrics['run_id']}")
    print(f"PROMPT_COUNT={metrics['prompt_count']}")
    print(f"RUNTIME_GENERATION_PASS={str(metrics['runtime_generation_pass']).lower()}")
    print(f"ISOLATED_EVALUATION_PASS={str(metrics['isolated_evaluation_pass']).lower()}")
    print(f"BLIND_TARGET_COUNT={metrics['blind_target_count']}")
    print(f"GENERIC_CONTROL_IDENTIFIED_COUNT={metrics['generic_control_identified_count']}")
    print(f"SIMILAR_ROLE_DISTINGUISHED_COUNT={metrics['similar_role_distinguished_count']}")
    print(f"TOTAL_SCORE={metrics['total_score']}")
    if result["valid"]:
        print("LOOP_STAGE=ENABLE")
        print("NEXT_ACTION=质量循环已通过；运行 release validate，随后启用并核对 completion-gate。")
        return 0
    stage, action = quality.route_status(result)
    print(f"LOOP_STAGE={stage}")
    print("FAILURE_LAYERS=" + ",".join(metrics["failure_layers"]))
    print("REPAIR_TARGETS=" + ",".join(metrics["repair_targets"]))
    for item in result["issues"]:
        print(f"ERROR {item['code']}: {item['message']}")
    print(f"NEXT_ACTION={action}")
    return 1


def cmd_runtime_detect(args: argparse.Namespace) -> int:
    try:
        paths = runtime_paths_from_args(args)
        payload = {
            "runtime": paths.runtime,
            "config_root": str(paths.config_root),
            "skills_root": str(paths.skills_root),
            "instruction_path": str(paths.instruction_path) if paths.instruction_path is not None else None,
            "registry_path": str(paths.registry_path),
            "supports_persistent_activation": paths.supports_persistent_activation,
            "activation_note": paths.activation_note,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for key, value in payload.items():
                print("%s=%s" % (key.upper(), value))
        return 0
    except lifecycle.LifecycleError as exc:
        return print_lifecycle_error(exc)


def cmd_list_roles(args: argparse.Namespace) -> int:
    try:
        paths = runtime_paths_from_args(args)
        registry = lifecycle.load_registry(paths)
        roles = sorted(registry["roles"].values(), key=lambda item: item["id"])
        payload = {"runtime": paths.runtime, "active_role_id": registry["active_role_id"], "roles": roles}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif not roles:
            print("没有已注册角色。")
        else:
            for role in roles:
                active = " *ACTIVE*" if role["id"] == registry["active_role_id"] else ""
                print("%s\t%s\t%s%s" % (role["id"], role["display_name"], role["path"], active))
        return 0
    except lifecycle.LifecycleError as exc:
        return print_lifecycle_error(exc)


def cmd_status(args: argparse.Namespace) -> int:
    try:
        paths = runtime_paths_from_args(args)
        registry = lifecycle.load_registry(paths)
        verification = lifecycle.verify_activation(paths) if registry["active_role_id"] else {"valid": False, "errors": ["当前没有启用角色"]}
        payload = {
            "runtime": paths.runtime,
            "active_role_id": registry["active_role_id"],
            "instruction_path": str(paths.instruction_path) if paths.instruction_path is not None else None,
            "supports_persistent_activation": paths.supports_persistent_activation,
            "activation_note": paths.activation_note,
            "activation": verification,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("RUNTIME=%s" % paths.runtime)
            print("ACTIVE_ROLE_ID=%s" % (registry["active_role_id"] or "none"))
            print("PERSISTENT_ACTIVATION_SUPPORTED=%s" % str(paths.supports_persistent_activation).lower())
            print("ACTIVATION_VALID=%s" % str(verification["valid"]).lower())
            if verification["errors"]:
                print("ACTIVATION_ERRORS=" + " | ".join(verification["errors"]))
        return 0
    except lifecycle.LifecycleError as exc:
        return print_lifecycle_error(exc)


def validate_for_activation(root: Path) -> dict[str, object]:
    validation = validate_skill(root, "release")
    metrics = validation["metrics"]
    if metrics.get("persona_type") in RICH_CORPUS_TYPES and not metrics.get("rich_corpus_ready"):
        raise lifecycle.LifecycleError(
            f"资料丰度门禁未通过：已有角色类 Skill 必须先收集至少 {RICH_CORPUS_MIN_CARDS} 张已核验代表性原文卡并达到“丰富”档；当前为 {metrics.get('exact_original_cards', 0)} 张、{metrics.get('research_profile', 'unknown')}"
        )
    if not metrics.get("independent_quality_pass"):
        raise lifecycle.LifecycleError(
            "独立质量门禁未通过：必须完成 CASE-24 真实连续对话独立评测并达到全部分项阈值后才能启用"
        )
    if metrics.get("persona_type") == "composite-character" and not metrics.get("composite_work_coverage_complete"):
        raise lifecycle.LifecycleError(
            "跨作品逐片覆盖门禁未通过：请补齐 WORK-逐作品代表性卡片、证据单元和场景维度后才能启用"
        )
    if not validation["valid"]:
        codes = ",".join(unique_error_codes(validation)[:20])
        raise lifecycle.LifecycleError("角色未通过正式校验，不能启用；错误代码：%s" % codes)
    return validation


def cmd_enable(args: argparse.Namespace) -> int:
    try:
        paths = runtime_paths_from_args(args)
        lifecycle.persistent_instruction_path(paths)
        root = Path(args.path).expanduser().resolve()
        validation = validate_for_activation(root)
        metadata = role_registration_metadata(root, validation, args)
        role = lifecycle.register_role(paths, role_path=root, **metadata)
        result = lifecycle.enable_registered_role(paths, role["id"])
        print("ACTIVATION_STATUS=enabled")
        print("RUNTIME=%s" % paths.runtime)
        print("ACTIVE_ROLE_ID=%s" % role["id"])
        print("BINDING_PATH=%s" % paths.instruction_path)
        print("RECEIPT_PATH=%s" % paths.receipt_path)
        print("BINDING_CHANGED=%s" % str(result["binding"]["changed"]).lower())
        return 0
    except lifecycle.LifecycleError as exc:
        return print_lifecycle_error(exc)


def cmd_register(args: argparse.Namespace) -> int:
    try:
        paths = runtime_paths_from_args(args)
        root = Path(args.path).expanduser().resolve()
        validation = validate_for_activation(root)
        metadata = role_registration_metadata(root, validation, args)
        role = lifecycle.register_role(paths, role_path=root, **metadata)
        verification = lifecycle.verify_registration(
            paths, role_path=root, expected_role_hash=metadata["validation_hash"]
        )
        if not verification["valid"]:
            raise lifecycle.LifecycleError("角色注册回读验证失败：%s" % "; ".join(verification["errors"]))
        print("ACTIVATION_STATUS=registered")
        print("RUNTIME=%s" % paths.runtime)
        print("ROLE_ID=%s" % role["id"])
        print("PERSISTENT_ACTIVATION_SUPPORTED=%s" % str(paths.supports_persistent_activation).lower())
        print("REGISTRY_PATH=%s" % paths.registry_path)
        return 0
    except lifecycle.LifecycleError as exc:
        return print_lifecycle_error(exc)


def cmd_switch(args: argparse.Namespace) -> int:
    try:
        paths = runtime_paths_from_args(args)
        registry = lifecycle.load_registry(paths)
        existing = lifecycle.resolve_role(registry, args.query)
        root = Path(existing["path"]).resolve()
        validation = validate_for_activation(root)
        metadata_args = argparse.Namespace(
            display_name=existing["display_name"],
            source_identity=existing.get("source_identity"),
            alias=existing.get("aliases", []),
        )
        metadata = role_registration_metadata(root, validation, metadata_args)
        role = lifecycle.register_role(paths, role_path=root, **metadata)
        lifecycle.enable_registered_role(paths, role["id"])
        print("ACTIVATION_STATUS=enabled")
        print("RUNTIME=%s" % paths.runtime)
        print("ACTIVE_ROLE_ID=%s" % role["id"])
        return 0
    except lifecycle.LifecycleError as exc:
        return print_lifecycle_error(exc)


def cmd_disable(args: argparse.Namespace) -> int:
    try:
        paths = runtime_paths_from_args(args)
        result = lifecycle.disable_active_role(paths)
        print("ACTIVATION_STATUS=disabled")
        print("RUNTIME=%s" % paths.runtime)
        print("PREVIOUS_ROLE_ID=%s" % (result["previous_role_id"] or "none"))
        return 0
    except lifecycle.LifecycleError as exc:
        return print_lifecycle_error(exc)


def cmd_delete(args: argparse.Namespace) -> int:
    if not args.yes:
        print("错误：删除需要 --yes；自然语言代理仅在用户明确要求删除该角色后传入。", file=sys.stderr)
        return 2
    try:
        paths = runtime_paths_from_args(args)
        result = lifecycle.delete_role(paths, args.query)
        print("DELETED_ROLE_ID=%s" % result["deleted_role_id"])
        print("DELETED_PATH=%s" % result["deleted_path"])
        print("WAS_ACTIVE=%s" % str(result["was_active"]).lower())
        return 0
    except lifecycle.LifecycleError as exc:
        return print_lifecycle_error(exc)


def cmd_state_show(args: argparse.Namespace) -> int:
    try:
        paths = runtime_paths_from_args(args)
        role = lifecycle.resolve_role(lifecycle.load_registry(paths), args.query)
        print(json.dumps(lifecycle.load_state(paths, role["id"]), ensure_ascii=False, indent=2))
        return 0
    except lifecycle.LifecycleError as exc:
        return print_lifecycle_error(exc)


def cmd_state_update(args: argparse.Namespace) -> int:
    try:
        paths = runtime_paths_from_args(args)
        role = lifecycle.resolve_role(lifecycle.load_registry(paths), args.query)
        changes = json.loads(args.data)
        if not isinstance(changes, dict):
            raise lifecycle.LifecycleError("--data 必须是 JSON 对象")
        result = lifecycle.update_state(paths, role["id"], changes)
        print("STATE_CHANGED=%s" % str(result["changed"]).lower())
        print(json.dumps(result["state"], ensure_ascii=False, indent=2))
        return 0
    except (ValueError, lifecycle.LifecycleError) as exc:
        return print_lifecycle_error(exc)


def cmd_reset_memory(args: argparse.Namespace) -> int:
    try:
        paths = runtime_paths_from_args(args)
        role = lifecycle.resolve_role(lifecycle.load_registry(paths), args.query)
        lifecycle.reset_state(paths, role["id"])
        print("MEMORY_RESET=true")
        print("ROLE_ID=%s" % role["id"])
        return 0
    except lifecycle.LifecycleError as exc:
        return print_lifecycle_error(exc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="创建并静态校验 Persona.skill 生成的角色人格 Skill。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_runtime_args(command_parser: argparse.ArgumentParser) -> None:
        def runtime_value(value: str) -> str:
            return "auto" if value.strip().lower() == "auto" else lifecycle.normalize_runtime(value)

        command_parser.add_argument(
            "--runtime", type=runtime_value, choices=("auto",) + lifecycle.SUPPORTED_RUNTIMES, default="auto",
            help="目标运行时；auto 仅在存在唯一可靠信号时成功",
        )
        command_parser.add_argument(
            "--home", help="测试或隔离安装使用的用户 HOME；提供后忽略运行时配置目录环境变量",
        )

    name_gate_parser = subparsers.add_parser(
        "name-gate", help="创建前强制完成角色名称选择；不得绕过"
    )
    name_gate_parser.add_argument(
        "--source-name", help="用户已经指定的原角色名；省略时进入只设定人物名的流程"
    )
    name_gate_parser.add_argument(
        "--choice", choices=("1", "2"), help="有原角色名时：1 原名，2 自定义名"
    )
    name_gate_parser.add_argument(
        "--custom-name", help="选择 2 或未指定原名时由用户直接输入的显示名"
    )
    name_gate_parser.set_defaults(func=cmd_name_gate)

    init_parser = subparsers.add_parser("init", help="从标准模板创建角色人格 Skill 工作目录")
    init_parser.add_argument("--name", required=True, help="已通过名称闸门确认的角色显示名")
    init_parser.add_argument(
        "--source-name", help="用户指定的原角色名；name-choice=1/2 时必填"
    )
    init_parser.add_argument(
        "--name-choice", choices=("1", "2", "none"),
        help="名称闸门结果：1 原名，2 自定义名，none 表示请求未指定原名而直接设定人物名",
    )
    init_parser.add_argument("--slug", required=True, help="小写连字符角色标识；persona- 前缀可省略")
    init_parser.add_argument("--output", required=True, help="要创建的目标目录；必须不存在")
    init_parser.set_defaults(func=cmd_init)

    validate_parser = subparsers.add_parser("validate", help="校验角色人格 Skill")
    validate_parser.add_argument("path", help="角色人格 Skill 目录")
    validate_parser.add_argument(
        "--level", choices=("draft", "release"), default="release", help="校验级别；draft 仅供内部迭代，最终只能交付 release"
    )
    validate_parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    validate_parser.set_defaults(func=cmd_validate)

    research_parser = subparsers.add_parser(
        "research-gate", help="在蒸馏规则前单独校验原始资料、来源、语境和真实扩展轮次"
    )
    research_parser.add_argument("path", help="角色人格 Skill 目录")
    research_parser.set_defaults(func=cmd_research_gate)

    iteration_parser = subparsers.add_parser(
        "iteration-gate", help="返回当前创建循环必须继续执行的阶段和下一动作"
    )
    iteration_parser.add_argument("path", help="角色人格 Skill 目录")
    iteration_parser.add_argument(
        "--activation-status",
        choices=("pending", "enabled", "registered", "not-requested"),
        default="pending",
        help="当前状态；创建循环通常保持 pending，完整启用后用 enabled，Skill-only 注册后用 registered",
    )
    add_runtime_args(iteration_parser)
    iteration_parser.set_defaults(func=cmd_iteration_gate)

    gate_parser = subparsers.add_parser(
        "completion-gate", help="创建任务最终回复前的确定性完成门禁"
    )
    gate_parser.add_argument("path", help="角色人格 Skill 目录")
    gate_parser.add_argument(
        "--activation-status",
        choices=("pending", "enabled", "registered", "not-requested"),
        default="pending",
        help="enabled 表示持久启用，registered 表示 Skill-only 注册，not-requested 仅用于明确只创建",
    )
    add_runtime_args(gate_parser)
    gate_parser.set_defaults(func=cmd_completion_gate)

    quality_init_parser = subparsers.add_parser(
        "quality-init", help="冻结人物资产并在冻结后生成 Persona Quality Loop v4 隐藏场景"
    )
    quality_init_parser.add_argument("path", help="角色人格 Skill 目录")
    quality_init_parser.add_argument("--generator-context-id", required=True, help="实际生成回答的任务/上下文稳定标识")
    quality_init_parser.add_argument("--runtime", required=True, choices=lifecycle.SUPPORTED_RUNTIMES)
    quality_init_parser.add_argument("--runtime-mode", choices=tuple(sorted(quality.ALLOWED_RUNTIME_MODES)), default="staged-role")
    quality_init_parser.add_argument("--iteration", type=int, default=1)
    quality_init_parser.add_argument("--seed", default="", help="仅供可重复测试；正式运行省略以生成随机 nonce")
    quality_init_parser.set_defaults(func=cmd_quality_init)

    quality_record_parser = subparsers.add_parser(
        "quality-record", help="记录实际 Runtime 的隐藏场景回答并现场重跑可信检查器"
    )
    quality_record_parser.add_argument("path", help="角色人格 Skill 目录")
    quality_record_parser.add_argument("--run-id", required=True)
    quality_record_parser.add_argument("--responses", required=True, help="实际连续回答 JSON")
    quality_record_parser.add_argument("--generic-context-id", required=True, help="生成通用助手对照的隔离上下文 ID")
    quality_record_parser.add_argument("--similar-context-id", required=True, help="生成相似人物近失对照的隔离上下文 ID")
    quality_record_parser.add_argument("--binding-receipt", help="runtime-mode=installed-role 时必填")
    quality_record_parser.set_defaults(func=cmd_quality_record)

    quality_evaluate_parser = subparsers.add_parser(
        "quality-evaluate", help="校验隔离盲评记录、重算质量分并输出修复归因"
    )
    quality_evaluate_parser.add_argument("path", help="角色人格 Skill 目录")
    quality_evaluate_parser.add_argument("--run-id", required=True)
    quality_evaluate_parser.add_argument("--evaluation", required=True, help="独立评估逐项 JSON")
    quality_evaluate_parser.add_argument("--evaluator-context-id", required=True, help="不得与生成上下文相同")
    quality_evaluate_parser.set_defaults(func=cmd_quality_evaluate)

    quality_status_parser = subparsers.add_parser(
        "quality-status", help="回读 v3 质量链、现场重跑检查器并给出下一修复层"
    )
    quality_status_parser.add_argument("path", help="角色人格 Skill 目录")
    quality_status_parser.add_argument("--json", action="store_true")
    quality_status_parser.set_defaults(func=cmd_quality_status)

    detect_parser = subparsers.add_parser("runtime-detect", help="确定性解析当前运行时的用户级路径")
    add_runtime_args(detect_parser)
    detect_parser.add_argument("--json", action="store_true", help="输出 JSON")
    detect_parser.set_defaults(func=cmd_runtime_detect)

    list_parser = subparsers.add_parser("list", help="列出当前运行时已注册角色")
    add_runtime_args(list_parser)
    list_parser.add_argument("--json", action="store_true", help="输出 JSON")
    list_parser.set_defaults(func=cmd_list_roles)

    status_parser = subparsers.add_parser("status", help="检查活动角色、实际绑定和回执")
    add_runtime_args(status_parser)
    status_parser.add_argument("--json", action="store_true", help="输出 JSON")
    status_parser.set_defaults(func=cmd_status)

    enable_parser = subparsers.add_parser("enable", help="正式校验、注册并全局启用角色")
    enable_parser.add_argument("path", help="角色 Skill 目录")
    enable_parser.add_argument("--display-name", help="可选显示名；默认从角色 Skill 读取")
    enable_parser.add_argument("--alias", action="append", default=[], help="角色精确别名；可重复")
    enable_parser.add_argument("--source-identity", help="来源角色或人物身份")
    add_runtime_args(enable_parser)
    enable_parser.set_defaults(func=cmd_enable)

    register_parser = subparsers.add_parser("register", help="正式校验并注册角色，不伪造全局启用")
    register_parser.add_argument("path", help="角色 Skill 目录")
    register_parser.add_argument("--display-name", help="可选显示名；默认从角色 Skill 读取")
    register_parser.add_argument("--alias", action="append", default=[], help="角色精确别名；可重复")
    register_parser.add_argument("--source-identity", help="来源角色或人物身份")
    add_runtime_args(register_parser)
    register_parser.set_defaults(func=cmd_register)

    switch_parser = subparsers.add_parser("switch", help="按稳定 ID、显示名或别名切换活动角色")
    switch_parser.add_argument("query", help="精确角色稳定 ID、显示名或别名")
    add_runtime_args(switch_parser)
    switch_parser.set_defaults(func=cmd_switch)

    disable_parser = subparsers.add_parser("disable", help="停用当前运行时的全局人格")
    add_runtime_args(disable_parser)
    disable_parser.set_defaults(func=cmd_disable)

    delete_parser = subparsers.add_parser("delete", help="精确匹配并安全删除生成角色")
    delete_parser.add_argument("query", help="精确角色稳定 ID、显示名或别名")
    delete_parser.add_argument("--yes", action="store_true", help="确认用户已明确要求删除")
    add_runtime_args(delete_parser)
    delete_parser.set_defaults(func=cmd_delete)

    state_show_parser = subparsers.add_parser("state-show", help="读取角色的受限连续状态")
    state_show_parser.add_argument("query", help="精确角色稳定 ID、显示名或别名")
    add_runtime_args(state_show_parser)
    state_show_parser.set_defaults(func=cmd_state_show)

    state_update_parser = subparsers.add_parser("state-update", help="发生有意义变化时原子更新连续状态")
    state_update_parser.add_argument("query", help="精确角色稳定 ID、显示名或别名")
    state_update_parser.add_argument("--data", required=True, help="仅含允许字段的 JSON 对象")
    add_runtime_args(state_update_parser)
    state_update_parser.set_defaults(func=cmd_state_update)

    reset_parser = subparsers.add_parser("reset-memory", help="重置角色的关系、情绪、承诺和近期表达状态")
    reset_parser.add_argument("query", help="精确角色稳定 ID、显示名或别名")
    add_runtime_args(reset_parser)
    reset_parser.set_defaults(func=cmd_reset_memory)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
