#!/usr/bin/env python3
"""Create and statically validate Persona.skill character skill folders."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


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

ALLOWED_SOURCE_TYPES = {"原作明确", "本人公开表达", "用户补充", "公开资料", "合理推导", "Persona.skill 补齐"}
PRIMARY_SOURCE_TYPES = {"原作明确", "本人公开表达"}
EXACT_CARD_TYPES = {
    "原文对白", "原文口头禅", "原文独白", "原文发言", "原文采访回答",
    "原文文章", "原文帖子", "原文书信",
}
AUTHORED_CARD_TYPES = {"原创规范对白"}
ALLOWED_CARD_TYPES = EXACT_CARD_TYPES | AUTHORED_CARD_TYPES
SIGNATURE_LEVELS = {"核心", "常用"}
ALLOWED_ORIGINAL_QUALITIES = {"原声核验", "原语言文本核验", "原始版式核验"}
ALLOWED_QUALITIES = ALLOWED_ORIGINAL_QUALITIES | {"译本参考", "原创确认"}
ALLOWED_MEDIA = {"视听", "文字", "混合", "公开表达", "原创"}
ALLOWED_PERSONA_TYPES = {
    "existing-character",
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
ALLOWED_BIO_CATEGORIES = {
    "identity", "gender", "background", "timeline", "relationship", "ability", "preference", "worldview", "faq",
}
REQUIRED_BIO_BASELINE_FIELDS = (
    "姓名与原名", "性别身份", "性别相关称谓与代词", "年龄或生命阶段", "物种或存在类型",
    "社会身份或职业", "所属或阵营", "当前时间点或版本", "自我认知", "基线来源",
)

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
    "临场感与主动表达", "delivery_guidance", "证据映射", "事实保护", "停用与恢复",
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


def cmd_init(args: argparse.Namespace) -> int:
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

    replacements = {
        "{{PERSONA_NAME}}": args.name.strip(),
        "{{PERSONA_SLUG}}": args.slug,
        "{{CARD_PREFIX}}": card_prefix(args.slug),
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

    print(f"已创建角色人格 Skill 工作目录：{target}")
    print("下一步：填写全部 [待填写] 内容，完成并扩大调研直到达标或已穷尽，然后运行 release 校验。")
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
    path: Path, root: Path, level: str, code_prefix: str,
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
        card_block = card_blocks.get(card_id)
        if card_block is not None and not has_substantive_value(field_value(card_block, source_field), allow_none=True):
            add_issue(
                issues, "error" if level == "release" else "warning",
                f"{code_prefix}.evidence_mapping_empty",
                f"{rule_id} 映射到 {card_id} 的“{source_field}”，但该字段没有可用证据", path, root,
            )
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
        "research_status": "unknown",
        "coverage_path": "unknown",
        "research_expansion_recorded": False,
        "research_rounds": 0,
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
            if not metadata.get("description", "").strip():
                add_issue(issues, "error", "frontmatter.description", "description 不能为空", skill_path, root)
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
                "人格来源类型必须是 existing-character、original-persona、real-person-simulation 或 composite-original",
                core_path,
                root,
            )
        raw_version = field_value(core_text, "版本")
        if raw_version and not PLACEHOLDER_RE.search(raw_version):
            formal_version = raw_version.strip()
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
    metrics["original_medium"] = original_medium
    metrics["original_language"] = original_language

    sources_path = root / "references" / "08-来源索引.md"
    sources_text = read_text(sources_path) if sources_path.is_file() else ""
    research_status = field_value(sources_text, "调研状态") or "unknown"
    research_blocks = list(iter_research_blocks(sources_text))
    research_rounds = len(research_blocks)
    research_rounds_complete = all(
        all(
            has_substantive_value(field_value(block, field), allow_none=True)
            for field in ("查询词、站点、资料类型与语言", "新增来源与卡片", "未覆盖指标")
        )
        for _, block in research_blocks
    )
    expansion_record = field_value(sources_text, "扩大范围记录")
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
        and research_rounds >= 2
        and research_rounds_complete
        and all(has_substantive_value(value) for value in research_fields.values())
    )
    if level == "release" and research_status not in {"达标", "已穷尽"}:
        add_issue(
            issues,
            "error",
            "research.status_invalid",
            "调研状态必须是“达标”或“已穷尽”",
            sources_path,
            root,
        )
    if level == "release" and research_status == "已穷尽" and not exhaustion_complete:
        missing = [name for name, value in research_fields.items() if not has_substantive_value(value)]
        if not expansion_recorded:
            missing.insert(0, "扩大范围记录")
        if research_rounds < 2:
            missing.insert(0, "至少两个 RESEARCH 调研轮次")
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
    metrics["research_status"] = research_status
    metrics["research_expansion_recorded"] = expansion_recorded
    metrics["research_rounds"] = research_rounds

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
    normalized_original_owners: dict[str, str] = {}
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
            if card_type and not PLACEHOLDER_RE.search(card_type) and card_type not in ALLOWED_CARD_TYPES:
                add_issue(
                    issues,
                    "error",
                    "dialogue.card_type_invalid",
                    f"{card_id} 的卡片类型无效：{card_type}",
                    path,
                    root,
                )
            if persona_type in {"existing-character", "real-person-simulation"}:
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
                    previous = normalized_original_owners.get(normalized)
                    if previous:
                        add_issue(
                            issues,
                            "error" if level == "release" else "warning",
                            "dialogue.duplicate_original_text",
                            f"{card_id} 与 {previous} 保存了相同原文；重复出现应合并来源定位，不能重复计数",
                            path,
                            root,
                        )
                        noncanonical_card_ids.add(card_id)
                    else:
                        normalized_original_owners[normalized] = card_id
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
            complete_context_count = sum(not context_is_missing(value) for value in context_values)
            context_is_countable = False
            if context_type in CONVERSATIONAL_CONTEXT_TYPES:
                context_is_countable = (
                    complete_context_count >= 3
                    and not context_is_missing(field_value(block, "触发话语"))
                    and not context_is_missing(field_value(block, "对话对象"))
                )
            elif context_type in NARRATIVE_CONTEXT_TYPES:
                context_is_countable = (
                    complete_context_count >= 2
                    and not (
                        context_is_missing(field_value(block, "前置原文"))
                        and context_is_missing(field_value(block, "触发话语"))
                    )
                )
            elif context_type in SELF_CONTAINED_CONTEXT_TYPES:
                context_is_countable = (
                    complete_context_count >= 1
                    and has_substantive_value(field_value(block, "来源位置"))
                    and (
                        not context_is_missing(field_value(block, "触发话语"))
                        or not context_is_missing(field_value(block, "对话对象"))
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
                persona_type in {"existing-character", "real-person-simulation"}
                and source_type
                and not PLACEHOLDER_RE.search(source_type)
                and not (
                    (persona_type == "existing-character" and source_type == "原作明确")
                    or (persona_type == "real-person-simulation" and source_type in PRIMARY_SOURCE_TYPES)
                )
            ):
                add_issue(
                    issues,
                    "error",
                    "dialogue.source_not_original",
                    f"{card_id} 的来源类型是“{source_type}”；已有角色只接受原作明确内容，现实人物只接受本人可核查的公开表达",
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
            if persona_type in {"existing-character", "real-person-simulation"}:
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
    metrics["derived_cards"] = len(noncanonical_card_ids)
    metrics["distinct_emotions_and_intents"] = len(dimensions)
    for annotation_field, entries in annotation_values.items():
        counts = Counter(value for value, _, _ in entries if value)
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
    release_thresholds = {
        "existing-character": (24, 6),
        "real-person-simulation": (24, 6),
        "original-persona": (20, 8),
        "composite-original": (20, 8),
    }
    min_cards, min_dimensions = release_thresholds.get(persona_type, (20, 8)) if level == "release" else (1, 1)
    target_severity = "warning" if exhaustion_complete else ("error" if level == "release" else "warning")
    if len(all_ids) < min_cards:
        add_issue(
            issues,
            target_severity,
            "dialogue.too_few",
            f"原始表达卡为 {len(all_ids)} 张，{persona_type} 正式版最低覆盖目标为 {min_cards} 张",
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
        index_ids = set(re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", index_text))
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
    if case_count < 23:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "tests.too_few_cases",
            f"验证用例仅 {case_count} 个，至少需要 23 个",
            cases_path,
            root,
        )
    required_case_ids = {"CASE-18", "CASE-19", "CASE-20", "CASE-21", "CASE-22", "CASE-23"}
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
            "样本数", "检查器", "检查结果", "重复流程骨架数", "重复开场骨架数",
            "同一回答形状样本数", "追问收尾样本数", "长度与句数异常集中",
            "低生成准备度样本数", "原始记录位置", "验证状态",
        ),
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
    for case_id in ("CASE-18", "CASE-19", "CASE-20"):
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
    fidelity_thresholds = (
        (blind_samples is not None and blind_samples >= 12, "tests.blind_samples_low", "CASE-18 去名盲测至少需要 12 个样本"),
        (blind_correct is not None and blind_correct >= 10 and blind_samples is not None and blind_correct <= blind_samples, "tests.blind_correct_low", "CASE-18 至少需要正确识别 10 个样本，且不能超过样本数"),
        (contrast_samples is not None and contrast_samples > 0, "tests.contrast_samples_invalid", "CASE-19 样本数必须大于 0"),
        (contrast_correct is not None and contrast_samples is not None and contrast_correct <= contrast_samples and contrast_correct * 100 >= contrast_samples * 80, "tests.contrast_rate_low", "CASE-19 相似角色区分率必须至少 80%"),
        (trace_samples is not None and trace_samples >= 6, "tests.trace_samples_low", "CASE-20 至少抽查 6 个场景"),
        (trace_correct is not None and trace_samples is not None and trace_correct <= trace_samples and trace_correct * 100 >= trace_samples * 80, "tests.trace_rate_low", "CASE-20 证据追溯率必须至少 80%"),
        (retrieval_correct is not None and trace_samples is not None and retrieval_correct <= trace_samples and retrieval_correct * 100 >= trace_samples * 80, "tests.retrieval_rate_low", "CASE-20 召回相关率必须至少 80%"),
        (mapping_samples is not None and mapping_samples >= 12, "tests.evidence_mapping_samples_low", "CASE-20 至少独立抽查 12 条规则证据映射"),
        (mapping_correct is not None and mapping_samples is not None and mapping_correct <= mapping_samples and mapping_correct * 100 >= mapping_samples * 80, "tests.evidence_mapping_rate_low", "CASE-20 规则证据映射语义成立率必须至少 80%"),
        (batch_samples is not None and batch_samples >= 8, "tests.batch_samples_low", "CASE-23 批量结构退化检查至少需要 8 个样本"),
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
    supporting_original_sources = original_source_ids & original_referenced_source_ids
    verified_original_card_ids = {
        card_id for card_id, source_refs in original_card_sources.items() if source_refs & original_source_ids
    }
    verified_fidelity_card_ids = verified_original_card_ids & original_language_card_ids
    verified_performance_card_ids = verified_fidelity_card_ids & performance_verified_card_ids
    verified_layout_card_ids = verified_fidelity_card_ids & layout_verified_card_ids
    metrics["exact_original_cards"] = len(verified_fidelity_card_ids)
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
            f"有 {len(unverified_original_card_ids)} 张原始表达卡未引用原作明确来源或本人公开表达来源："
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
    if level == "release" and persona_type in {"existing-character", "real-person-simulation"} and missing_required_voice_layers:
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
        validate_rule_evidence_mapping(
            issues, anti_id, block, card_blocks_by_id, anti_path, root, level, "anti"
        )
    metrics["anti_rules"] = len(anti_blocks)
    metrics["anti_evidence_cards"] = len(anti_evidence_ids & evidence_card_ids)
    metrics["rule_evidence_mappings"] = sum(
        len(parse_evidence_mapping(field_value(block, "证据映射")))
        for _, block in core_blocks + voice_blocks + mode_blocks + anti_blocks
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
        if persona_type in {"existing-character", "real-person-simulation"}
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

    if level == "release" and persona_type in {"existing-character", "real-person-simulation"}:
        min_expression_cards = 24
        min_evidence_units = 8
        min_signature_cards = 8
        min_sources = 3 if persona_type == "real-person-simulation" else 1
        min_primary_sources = 2 if persona_type == "real-person-simulation" else 1
        if len(verified_fidelity_card_ids) < min_expression_cards:
            add_issue(
                issues,
                target_severity,
                "dialogue.exact_original_cards_low",
                f"经来源核对且含逐字原文的原始表达卡仅 {len(verified_fidelity_card_ids)} 张，正式版最低覆盖目标为 {min_expression_cards} 张",
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
    target_met = False
    if persona_type == "existing-character":
        target_met = (
            len(all_ids) >= 24
            and len(dimensions) >= 6
            and len(verified_fidelity_card_ids) >= 24
            and len(distinct_source_scenes) >= 8
            and len(signature_card_ids) >= 8
            and source_count >= 1
            and len(supporting_original_sources) >= 1
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
            and case_count >= 23
            and metrics["semantic_diversity_failures"] == 0
        )
    elif persona_type == "real-person-simulation":
        target_met = (
            len(all_ids) >= 24
            and len(dimensions) >= 6
            and len(verified_fidelity_card_ids) >= 24
            and len(distinct_source_scenes) >= 8
            and len(signature_card_ids) >= 8
            and source_count >= 3
            and len(supporting_original_sources) >= 2
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
            and case_count >= 23
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
        try:
            compile(read_text(response_checker_path), str(response_checker_path), "exec")
        except SyntaxError as exc:
            add_issue(
                issues,
                "error",
                "response_checker.syntax_error",
                f"回复检测器无法解析：{exc.msg}（第 {exc.lineno} 行）",
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
            f"cards={metrics['cards']} exact_original_cards={metrics['exact_original_cards']} "
            f"performance_verified_cards={metrics['performance_verified_cards']} "
            f"distinct_evidence_units={metrics['distinct_evidence_units']} "
            f"context_complete_cards={metrics['context_complete_cards']} "
            f"signature_cards={metrics['signature_cards']} "
            f"canonical_authored_cards={metrics['canonical_authored_cards']} "
            f"derived_cards={metrics['derived_cards']} "
            f"dimensions={metrics['distinct_emotions_and_intents']} "
            f"core_rules={metrics['core_rules']} core_layers={metrics['core_layers']} "
            f"core_evidence_cards={metrics['core_evidence_cards']} "
            f"voice_rules={metrics['voice_rules']} voice_layers={metrics['voice_layers']} "
            f"voice_evidence_cards={metrics['voice_evidence_cards']} "
            f"anti_rules={metrics['anti_rules']} anti_evidence_cards={metrics['anti_evidence_cards']} "
            f"rule_evidence_mappings={metrics['rule_evidence_mappings']} "
            f"biography_entries={metrics['biography_entries']} "
            f"biography_categories={metrics['biography_categories']} "
            f"biography_baseline_complete={metrics['biography_baseline_complete']} "
            f"semantic_diversity_failures={metrics['semantic_diversity_failures']} "
            f"emotion_modes={metrics['emotion_modes']} mode_dimensions={metrics['mode_dimensions']} "
            f"scenes={metrics['work_scenes']} cases={metrics['validation_cases']} "
            f"sources={metrics['sources']} original_sources={metrics['original_sources']}"
        )
        for item in result["issues"]:
            location = f" ({item['file']})" if item["file"] else ""
            print(f"{item['severity'].upper()} {item['code']}: {item['message']}{location}")
    return 0 if result["valid"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="创建并静态校验 Persona.skill 生成的角色人格 Skill。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="从标准模板创建角色人格 Skill 工作目录")
    init_parser.add_argument("--name", required=True, help="角色显示名")
    init_parser.add_argument("--slug", required=True, help="小写连字符 Skill 标识")
    init_parser.add_argument("--output", required=True, help="要创建的目标目录；必须不存在")
    init_parser.set_defaults(func=cmd_init)

    validate_parser = subparsers.add_parser("validate", help="校验角色人格 Skill")
    validate_parser.add_argument("path", help="角色人格 Skill 目录")
    validate_parser.add_argument(
        "--level", choices=("draft", "release"), default="release", help="校验级别；draft 仅供内部迭代，最终只能交付 release"
    )
    validate_parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    validate_parser.set_defaults(func=cmd_validate)
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
