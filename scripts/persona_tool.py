#!/usr/bin/env python3
"""Create and statically validate Persona.skill character skill folders."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
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
PLACEHOLDER_RE = re.compile(
    r"\{\{[A-Z0-9_]+\}\}|\[待填写[^\]]*\]|\b(?:TODO|TBD)\b", re.IGNORECASE
)

REQUIRED_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/select_dialogues.py",
    "references/01-角色核心.md",
    "references/02-语言声纹.md",
    "references/03-情绪与关系.md",
    "references/04-工作场景迁移.md",
    "references/05-对白索引.md",
    "references/07-验证用例.md",
    "references/08-来源索引.md",
)

REQUIRED_CARD_FIELDS = (
    "检索标签",
    "来源类型",
    "来源位置",
    "原场景",
    "对话对象",
    "关系距离",
    "交流目的",
    "主要情绪",
    "情绪强度",
    "语言特征",
    "代表性短句",
    "表达结构",
    "适用工作场景",
    "迁移方式",
    "工作改写示例",
    "不适用场景",
    "重复限制",
)

ALLOWED_SOURCE_TYPES = {"原作明确", "用户补充", "公开资料", "合理推导", "Persona.skill 补齐"}
ALLOWED_PERSONA_TYPES = {
    "existing-character",
    "original-persona",
    "real-person-simulation",
    "composite-original",
}
ALLOWED_INDEX_SOURCE_TYPES = ALLOWED_SOURCE_TYPES
ALLOWED_MIGRATIONS = {"直接使用", "修改后使用", "仅作风格参考"}
REQUIRED_TAGS = {"task_state", "user_state", "emotion", "intent", "relation", "risk", "language"}

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

REQUIRED_SKILL_TERMS = ("回复前缀", "每条由 Agent 编写", "每轮加载", "对白使用", "事实保护", "停用与恢复")
REQUIRED_CORE_TERMS = ("身份", "版本", "回复前缀", "创建后当前会话默认启用", "人格内核", "与用户的关系", "基本声纹", "工作边界")
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


def has_representative_short_line(value: str | None) -> bool:
    if not value or PLACEHOLDER_RE.search(value):
        return False
    normalized = value.strip().strip("`'\"“”‘’").lower()
    return bool(normalized) and normalized not in {"无", "none", "n/a", "不适用"} and not normalized.startswith("无（")


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
        "original_cards": 0,
        "original_dialogue_cards": 0,
        "derived_cards": 0,
        "distinct_emotions_and_intents": 0,
        "work_scenes": 0,
        "validation_cases": 0,
        "sources": 0,
        "original_sources": 0,
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
    metrics["persona_type"] = persona_type
    metrics["version"] = formal_version

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
    original_short_card_ids: set[str] = set()
    for path in library_paths:
        text = read_text(path)
        for card_id, block in iter_card_blocks(text):
            all_ids.append(card_id)
            if card_id in seen_ids:
                add_issue(issues, "error", "dialogue.duplicate_id", f"对白编号重复：{card_id}", path, root)
            else:
                seen_ids[card_id] = path
            for field in REQUIRED_CARD_FIELDS:
                value = field_value(block, field)
                if value is None:
                    add_issue(issues, "error", "dialogue.field_missing", f"{card_id} 缺少字段：{field}", path, root)
                elif field in {"交流目的", "主要情绪"}:
                    dimensions.update(split_values(value))
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
            if source_type == "原作明确":
                if has_representative_short_line(field_value(block, "代表性短句")):
                    original_short_card_ids.add(card_id)
            migration = field_value(block, "迁移方式")
            if migration and not PLACEHOLDER_RE.search(migration) and migration not in ALLOWED_MIGRATIONS:
                add_issue(
                    issues,
                    "error",
                    "dialogue.migration_invalid",
                    f"{card_id} 的迁移方式无效：{migration}",
                    path,
                    root,
                )
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
            tags = field_value(block, "检索标签")
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
            source_location = field_value(block, "来源位置")
            source_refs = set(re.findall(r"\bSRC-\d{4}\b", source_location or "", re.IGNORECASE))
            normalized_source_refs = {item.upper() for item in source_refs}
            referenced_source_ids.update(normalized_source_refs)
            if source_type == "原作明确":
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

    metrics["cards"] = len(all_ids)
    metrics["distinct_emotions_and_intents"] = len(dimensions)
    release_thresholds = {
        "existing-character": (80, 12),
        "real-person-simulation": (40, 10),
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
            f"对白卡片为 {len(all_ids)} 张，{persona_type} 正式版收集目标为 {min_cards} 张",
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

    scene_path = root / "references" / "04-工作场景迁移.md"
    scenes: set[str] = set()
    if scene_path.is_file():
        scenes = set(SCENE_HEADING_RE.findall(read_text(scene_path)))
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
    metrics["work_scenes"] = len(scenes & REQUIRED_SCENES)

    cases_path = root / "references" / "07-验证用例.md"
    case_count = len(CASE_HEADING_RE.findall(read_text(cases_path))) if cases_path.is_file() else 0
    metrics["validation_cases"] = case_count
    if case_count < 15:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "tests.too_few_cases",
            f"验证用例仅 {case_count} 个，至少需要 15 个",
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
        source_type = field_value(block, "来源类型")
        if source_type == "原作明确":
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
    supporting_original_sources = original_source_ids & original_referenced_source_ids
    verified_original_card_ids = {
        card_id for card_id, source_refs in original_card_sources.items() if source_refs & original_source_ids
    }
    verified_original_dialogue_ids = verified_original_card_ids & original_short_card_ids
    metrics["original_cards"] = len(verified_original_card_ids)
    metrics["original_dialogue_cards"] = len(verified_original_dialogue_ids)
    metrics["derived_cards"] = len(all_ids) - len(verified_original_card_ids)
    metrics["original_sources"] = len(supporting_original_sources)
    unverified_original_card_ids = sorted(set(original_card_sources) - verified_original_card_ids)
    if unverified_original_card_ids:
        add_issue(
            issues,
            "error" if level == "release" else "warning",
            "dialogue.original_source_mismatch",
            f"有 {len(unverified_original_card_ids)} 张原作明确卡未引用原作明确来源："
            + ", ".join(unverified_original_card_ids[:5]),
            sources_path,
            root,
        )
    if level == "release" and persona_type == "existing-character":
        if len(verified_original_card_ids) < 40:
            add_issue(
                issues,
                target_severity,
                "dialogue.original_cards_low",
                f"经来源核对的原作明确场景卡仅 {len(verified_original_card_ids)} 张，现有作品角色正式版收集目标为 40 张",
                root / "references",
                root,
            )
        if len(verified_original_dialogue_ids) < 20:
            add_issue(
                issues,
                target_severity,
                "dialogue.original_quotes_low",
                f"经来源核对且含代表性原作短句的卡片仅 {len(verified_original_dialogue_ids)} 张，现有作品角色正式版收集目标为 20 张",
                root / "references",
                root,
            )
        if source_count < 5:
            add_issue(
                issues,
                target_severity,
                "sources.too_few",
                f"来源条目仅 {source_count} 个，现有作品角色正式版收集目标为 5 个",
                sources_path,
                root,
            )
        if len(supporting_original_sources) < 3:
            add_issue(
                issues,
                target_severity,
                "sources.original_too_few",
                f"被原作卡片实际引用的原作明确来源仅 {len(supporting_original_sources)} 个，现有作品角色正式版收集目标为 3 个",
                sources_path,
                root,
            )
    target_met = False
    if persona_type == "existing-character":
        target_met = (
            len(all_ids) >= 80
            and len(dimensions) >= 12
            and len(verified_original_card_ids) >= 40
            and len(verified_original_dialogue_ids) >= 20
            and source_count >= 5
            and len(supporting_original_sources) >= 3
        )
    elif persona_type == "real-person-simulation":
        target_met = len(all_ids) >= 40 and len(dimensions) >= 10
    elif persona_type in {"original-persona", "composite-original"}:
        target_met = len(all_ids) >= 20 and len(dimensions) >= 8
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
            f"cards={metrics['cards']} original_cards={metrics['original_cards']} "
            f"original_dialogue_cards={metrics['original_dialogue_cards']} "
            f"derived_cards={metrics['derived_cards']} "
            f"dimensions={metrics['distinct_emotions_and_intents']} "
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
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
