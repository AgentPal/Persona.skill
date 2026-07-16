#!/usr/bin/env python3
"""Detect generic assistant, project-manager, and AI-written tone in persona replies."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence


CHECKER_CONTRACT_VERSION = 4
ANTI_HEADING_RE = re.compile(r"^###\s+(ANTI-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
EXPR_HEADING_RE = re.compile(r"^###\s+(EXPR-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
BEHAV_HEADING_RE = re.compile(r"^##\s+(BEHAV-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
CARD_HEADING_RE = re.compile(r"^##\s+([A-Z0-9][A-Z0-9-]*-\d{4})\s*$", re.MULTILINE | re.IGNORECASE)
AI_PHRASES = (
    "综合来看", "综上所述", "基于以上", "基于上述", "需要注意的是", "值得注意的是",
    "接下来我们", "总体而言", "从这个角度", "在此基础上", "为了确保", "建议你",
)
GENERIC_OPENINGS = ("好的", "明白", "没问题", "可以的", "收到", "当然可以")
SEQUENCE_MARKERS = ("首先", "其次", "先", "再", "然后", "接着", "最后", "下一步")
PM_TERMS = (
    "目标", "范围", "方案", "流程", "路径", "优先级", "推进", "覆盖", "确认",
    "执行", "进行", "当前状态", "下一步", "交付", "计划",
)
CHOICE_PATTERNS = (
    r"由你(?:来)?决定", r"你可以选择", r"看你(?:想|要)", r"你最在意.*?就",
    r"要不要继续.*?你", r"你来选", r"交给你选择",
)
ORAL_MARKERS = ("……", "…", "！", "？", "?!", "!?", "等等", "不对", "我是说", "嗯", "诶", "哎")
INTERNAL_PROCESS_PATTERNS = (
    r"(?:我|这边)?先.{0,24}?(?:读取|加载|检索|选择|抽取|取出?|找).{0,20}?(?:原文卡|对白卡|场景卡|角色核心|声纹规则)",
    r"(?:先|正在|接下来).{0,16}?(?:运行|调用).{0,20}?(?:select_dialogues|选择器|检查器|内部脚本|命令)",
    r"(?:先|正在|接下来).{0,12}?(?:分析|思考).{0,20}?(?:再|然后|之后).{0,12}?(?:回答|回复)",
)
HESITATION_PATTERNS = (r"(?<!\w)嗯+(?!\w)", r"(?<!\w)呃+(?!\w)", r"那个[，,。.…… ]", r"怎么说呢", r"哈哈+")
STAGE_DIRECTION_PATTERNS = (
    r"\*[^*\n]{1,30}\*", r"（(?:笑|叹气|歪头|眨眼|拍拍|递给|端来|坐到)[^）]{0,20}）",
    r"\[(?:笑|叹气|歪头|眨眼|拍拍|递给|端来|坐到)[^\]]{0,20}\]",
)
FABRICATED_SENSORY_PATTERNS = (
    r"我(?:正)?看(?:见|到)你", r"我听(?:见|到)你", r"我闻到", r"我坐到你(?:身边|旁边)",
    r"我给你(?:端|递|拿)(?:来|了)", r"拍拍你的(?:肩|头)",
)
GENERIC_CONSULTING_PATTERNS = (
    r"先别急(?:着)?",
    r"第一(?:步|件事).{0,24}(?:是|要|什么)",
    r"(?:先|先别).{0,48}(?:再|然后|之后|我们就|就能)",
    r"(?:给谁用|要解决什么|最重要的是).{0,40}(?:先|定|确认)",
)
WORKFLOW_FRAME_RE = re.compile(r"先.{0,70}(?:再|然后|之后|我们|就能)|(?:先|再|然后|最后).*(?:先|再|然后|最后)")
QUESTION_END_RE = re.compile(r"[？?][”’\"']?\s*$")
ALLOWED_VISIBLE_SIGNAL_KINDS = {
    "judgment", "emotion", "relationship", "rhetoric", "rhythm", "background", "initiative",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def field_value(block: str, field: str) -> str:
    match = re.search(rf"^-\s*{re.escape(field)}[：:]\s*(.+?)\s*$", block, re.MULTILINE)
    return match.group(1).strip() if match else ""


def iter_anti_blocks(text: str) -> Iterable[tuple[str, str]]:
    matches = list(ANTI_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end]


def iter_blocks(text: str, pattern: re.Pattern[str]) -> Iterable[tuple[str, str]]:
    matches = list(pattern.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end]


def asset_version(root: Path) -> int:
    path = root / "references" / "01-角色核心.md"
    if not path.is_file():
        return 1
    raw = field_value(read_text(path), "人格资产版本")
    return int(raw) if raw.isdigit() else 1


def expression_profile(root: Path) -> dict[str, object]:
    path = root / "references" / "11-心理机制与表达策略.md"
    profiles: list[str] = []
    if path.is_file():
        profiles = [field_value(block, "篇幅档").lower() for _, block in iter_blocks(read_text(path), EXPR_HEADING_RE)]
    return {
        "verbosity_profiles": sorted(set(profile for profile in profiles if profile)),
        "allows_extended_prose": any(profile in {"extended", "rambling-characteristic"} for profile in profiles),
        "allows_characteristic_repetition": any(profile == "rambling-characteristic" for profile in profiles),
    }


def source_card_texts(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    references = root / "references"
    if not references.is_dir():
        return result
    for path in references.rglob("*对白库*.md"):
        if not path.is_file() or "索引" in path.name:
            continue
        for card_id, block in iter_blocks(read_text(path), CARD_HEADING_RE):
            result[card_id] = field_value(block, "原文")
    return result


def source_card_metadata(root: Path) -> dict[str, dict[str, str]]:
    """Return auditable card fields used by the v2 trace contract."""
    result: dict[str, dict[str, str]] = {}
    references = root / "references"
    if not references.is_dir():
        return result
    for path in references.rglob("*对白库*.md"):
        if not path.is_file() or "索引" in path.name:
            continue
        for card_id, block in iter_blocks(read_text(path), CARD_HEADING_RE):
            result[card_id] = {
                "text": field_value(block, "原文"),
                "quote_use": field_value(block, "引用方式").lower(),
                "version_layer": field_value(block, "版本层").lower(),
            }
    return result


def rule_and_background_ids(root: Path) -> tuple[set[str], set[str]]:
    """Load known local rule/BIO identifiers for traceability validation."""
    known_rules: set[str] = set()
    references = root / "references"
    for path in references.glob("*.md") if references.is_dir() else []:
        text = read_text(path)
        known_rules.update(rule_id for rule_id, _ in iter_blocks(text, EXPR_HEADING_RE))
        known_rules.update(rule_id for rule_id, _ in iter_blocks(text, BEHAV_HEADING_RE))
        known_rules.update(rule_id for rule_id, _ in iter_blocks(text, ANTI_HEADING_RE))
        # CORE/VOICE/MICRO/MODE/MIND share the same stable heading convention;
        # keeping this local avoids importing the mother validator at runtime.
        for prefix in ("CORE", "VOICE", "MICRO", "MODE", "MIND"):
            known_rules.update(
                match.group(1).upper()
                for match in re.finditer(rf"^###\s+({prefix}-\d{{2}})\s+\|", text, re.MULTILINE | re.IGNORECASE)
            )
    bio_path = references / "10-人物背景档案.md"
    known_bio = {
        bio_id for bio_id, _ in iter_blocks(read_text(bio_path), re.compile(r"^###\s+(BIO-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE))
    } if bio_path.is_file() else set()
    return known_rules, known_bio


def visible_prose(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    # Strip only a short speaker label such as “千束：”. A colon inside the
    # actual first sentence must not erase the reaction before it.
    text = re.sub(r"^\s*[^\n：:。！？!?，,；;]{1,16}[：:]\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def sentence_lengths(text: str) -> list[int]:
    return [len(item.strip()) for item in re.split(r"[。！？!?；;\n]+", text) if item.strip()]


def add_finding(findings: list[dict[str, object]], code: str, weight: int, detail: str) -> None:
    findings.append({"code": code, "weight": weight, "detail": detail})


def unique_literal_hits(text: str, phrases: Sequence[str]) -> list[str]:
    candidates: list[tuple[int, int, str]] = []
    for phrase in phrases:
        candidates.extend((match.start(), match.end(), phrase) for match in re.finditer(re.escape(phrase), text))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    chosen: list[tuple[int, int, str]] = []
    for candidate in candidates:
        start, end, _ = candidate
        if any(start < old_end and end > old_start for old_start, old_end, _ in chosen):
            continue
        chosen.append(candidate)
    return [phrase for _, _, phrase in chosen]


def unique_pattern_hits(text: str, patterns: Sequence[str]) -> list[str]:
    candidates: list[tuple[int, int, str]] = []
    for pattern in patterns:
        candidates.extend((match.start(), match.end(), match.group(0)) for match in re.finditer(pattern, text))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    chosen: list[tuple[int, int, str]] = []
    for candidate in candidates:
        start, end, _ = candidate
        if any(start < old_end and end > old_start for old_start, old_end, _ in chosen):
            continue
        chosen.append(candidate)
    return [matched for _, _, matched in chosen]


def analyze(text: str, root: Path, trace: dict[str, object] | None = None) -> dict[str, object]:
    prose = visible_prose(text)
    findings: list[dict[str, object]] = []
    profile = expression_profile(root)

    opening = next((item for item in GENERIC_OPENINGS if prose.startswith(item)), "")
    if opening:
        add_finding(findings, "generic_opening", 15, opening)

    process_hits = unique_pattern_hits(prose, INTERNAL_PROCESS_PATTERNS)
    if process_hits:
        add_finding(findings, "internal_process_preamble", 60, " / ".join(process_hits))

    hesitation_hits = unique_pattern_hits(prose, HESITATION_PATTERNS)
    if len(hesitation_hits) >= 4:
        add_finding(findings, "performed_hesitation_density", 30, f"命中 {len(hesitation_hits)} 个犹豫或笑声填充")

    stage_hits = unique_pattern_hits(text, STAGE_DIRECTION_PATTERNS)
    if len(stage_hits) >= 2:
        add_finding(findings, "stage_direction_density", 30, f"命中 {len(stage_hits)} 个舞台动作")

    sensory_hits = unique_pattern_hits(prose, FABRICATED_SENSORY_PATTERNS)
    if sensory_hits:
        add_finding(findings, "unverified_sensory_claim", 45, " / ".join(sensory_hits))

    ai_hits = [item for item in AI_PHRASES if item in prose]
    if ai_hits:
        add_finding(findings, "ai_written_connectors", min(30, 12 * len(ai_hits)), " / ".join(ai_hits))

    consulting_hits = unique_pattern_hits(prose, GENERIC_CONSULTING_PATTERNS)
    profiled_expression = bool((trace or {}).get("expression_rule_ids"))
    if len(consulting_hits) >= 2 or (
        consulting_hits
        and WORKFLOW_FRAME_RE.search(prose)
        and not profiled_expression
        and not bool(profile["allows_extended_prose"])
    ):
        add_finding(findings, "generic_consulting_frame", 45, " / ".join(consulting_hits))
    elif consulting_hits:
        profiled_long_form = bool(profile["allows_extended_prose"]) and len(prose) >= 80
        add_finding(
            findings, "generic_consulting_tendency",
            8 if (profiled_expression or profiled_long_form) else 14,
            consulting_hits[0],
        )

    sequence_hits = unique_literal_hits(prose, SEQUENCE_MARKERS)
    if len(sequence_hits) >= 3:
        add_finding(findings, "mechanical_sequence", 25, " / ".join(sequence_hits))
    elif len(sequence_hits) == 2:
        add_finding(findings, "sequence_tendency", 8, " / ".join(sequence_hits))

    pm_hits = [item for item in PM_TERMS if item in prose]
    if len(pm_hits) >= 4:
        add_finding(findings, "project_manager_density", 25, " / ".join(pm_hits))
    elif len(pm_hits) >= 2:
        add_finding(findings, "project_manager_tendency", 10, " / ".join(pm_hits))

    choice_hits = unique_pattern_hits(prose, CHOICE_PATTERNS)
    if len(choice_hits) >= 2:
        add_finding(findings, "choice_handoff_repeated", 25, f"命中 {len(choice_hits)} 个交还选择权结构")
    elif choice_hits:
        add_finding(findings, "choice_handoff", 5, "命中 1 个交还选择权结构")

    lengths = sentence_lengths(prose)
    average_length = round(sum(lengths) / len(lengths), 1) if lengths else 0.0
    oral_hits = [item for item in ORAL_MARKERS if item in prose]
    short_sentences = sum(length <= 10 for length in lengths)
    desired_length = str((trace or {}).get("desired_length", "auto")).lower()
    long_form_allowed = bool(profile["allows_extended_prose"]) and desired_length not in {"brief"}
    if len(lengths) >= 3 and average_length >= 30 and not oral_hits and short_sentences == 0 and not long_form_allowed:
        add_finding(findings, "uniform_written_sentences", 20, f"平均句长 {average_length}，没有可见口语断点")

    trace_findings: list[dict[str, object]] = []
    # A single response is still useful when the caller only wants the
    # profile-aware AI-tone check.  The trace contract belongs to generated
    # batches (or to an explicit trace supplied by a caller), not to every
    # ad-hoc ``--text`` invocation.  This keeps the checker compatible with
    # old runtime hooks while preserving strict validation whenever a trace
    # was actually requested.
    trace_contract_requested = trace is not None
    current_asset_version = asset_version(root)
    if current_asset_version >= 2 and trace_contract_requested:
        trace = trace or {}
        presence = trace.get("character_presence")
        if isinstance(presence, str):
            presence_values = [presence] if presence.strip() else []
        elif isinstance(presence, list):
            presence_values = [str(item) for item in presence if str(item).strip()]
        else:
            presence_values = []
        mind_ids = [str(item) for item in trace.get("mind_rule_ids", [])] if isinstance(trace.get("mind_rule_ids"), list) else []
        expression_ids = [str(item) for item in trace.get("expression_rule_ids", [])] if isinstance(trace.get("expression_rule_ids"), list) else []
        behavior_ids = [str(item) for item in trace.get("behavior_rule_ids", [])] if isinstance(trace.get("behavior_rule_ids"), list) else []
        known_rules, known_bio = rule_and_background_ids(root)
        # During an incomplete v2 build the strategy file may not exist yet;
        # the mother Skill will stop the build at validation, but the checker
        # remains usable for the draft's first pass.  Once the strategy file
        # exists, every traced MIND/EXPR ID must be real.
        strategy_path = root / "references" / "11-心理机制与表达策略.md"
        strategy_text = read_text(strategy_path) if strategy_path.is_file() else ""
        strategy_ready = bool(strategy_text.strip()) and not re.search(r"\[待填写|\{\{[A-Z0-9_]+\}\}|\b(?:TODO|TBD)\b", strategy_text, re.IGNORECASE)
        if strategy_ready:
            unknown_rules = sorted(
                item.upper() for item in (*mind_ids, *expression_ids, *behavior_ids)
                if item.upper() not in known_rules
            )
            if unknown_rules:
                trace_findings.append({"code": "trace_rule_id_unknown", "detail": "未知规则编号：" + " / ".join(unknown_rules)})
        trace_background_ids = trace.get("background_ids", [])
        if isinstance(trace_background_ids, list):
            unknown_bio = sorted(item.upper() for item in map(str, trace_background_ids) if item.upper() not in known_bio)
            if unknown_bio:
                trace_findings.append({"code": "trace_background_id_unknown", "detail": "未知背景编号：" + " / ".join(unknown_bio)})
        if current_asset_version >= 3:
            if trace.get("contract_version") != 3:
                trace_findings.append({"code": "trace_v3_contract_missing", "detail": "人物资产 v3 的 generation_trace.contract_version 必须为 3"})
            if not behavior_ids:
                trace_findings.append({"code": "behavior_contract_missing", "detail": "缺少 BEHAV 行为合同追溯"})
            visible_signals = trace.get("visible_character_signals")
            if not isinstance(visible_signals, list) or len(visible_signals) < 2:
                trace_findings.append({"code": "visible_character_signals_low", "detail": "至少需要两个回答内可见角色信号"})
                visible_signals = []
            signal_kinds: set[str] = set()
            for signal in visible_signals:
                if not isinstance(signal, dict):
                    trace_findings.append({"code": "visible_character_signal_invalid", "detail": "可见角色信号必须是对象"})
                    continue
                kind = str(signal.get("kind") or "").strip().lower()
                excerpt = str(signal.get("excerpt") or "").strip()
                rule_id = str(signal.get("rule_id") or "").strip().upper()
                signal_kinds.add(kind)
                if kind not in ALLOWED_VISIBLE_SIGNAL_KINDS:
                    trace_findings.append({"code": "visible_character_signal_kind_invalid", "detail": f"未知信号类型：{kind or 'empty'}"})
                if len(excerpt) < 2 or excerpt not in text:
                    trace_findings.append({"code": "visible_character_signal_not_visible", "detail": f"信号片段未逐字出现在回答中：{excerpt or 'empty'}"})
                if rule_id not in known_rules:
                    trace_findings.append({"code": "visible_character_signal_rule_unknown", "detail": f"信号引用未知规则：{rule_id or 'empty'}"})
            if not signal_kinds.intersection({"judgment", "emotion", "relationship", "initiative"}):
                trace_findings.append({"code": "visible_character_stance_missing", "detail": "缺少人物判断、情绪、关系或主动性片段"})
            if not signal_kinds.intersection({"rhetoric", "rhythm", "background"}):
                trace_findings.append({"code": "visible_character_expression_missing", "detail": "缺少修辞、节奏或背景联想片段"})
            if not str(trace.get("generic_near_miss_avoided") or "").strip():
                trace_findings.append({"code": "generic_contrast_missing", "detail": "没有记录如何避开通用助手近失样本"})
            if not str(trace.get("similar_role_boundary") or "").strip():
                trace_findings.append({"code": "similar_role_boundary_missing", "detail": "没有记录目标人物与相似人物的区别性边界"})
        elif not presence_values or not (mind_ids or expression_ids):
            trace_findings.append({"code": "character_presence_missing", "detail": "缺少人物判断、情绪或关系动作及其 MIND/EXPR 追溯"})
        exact_quotes = trace.get("exact_quotes", [])
        if exact_quotes and not isinstance(exact_quotes, list):
            trace_findings.append({"code": "exact_quote_trace_invalid", "detail": "exact_quotes 必须是数组"})
        elif isinstance(exact_quotes, list):
            card_texts = source_card_texts(root)
            card_metadata = source_card_metadata(root)
            for quote in exact_quotes:
                if not isinstance(quote, dict):
                    trace_findings.append({"code": "exact_quote_trace_invalid", "detail": "精确引文轨迹不是对象"})
                    continue
                quote_text = str(quote.get("text", ""))
                card_id = str(quote.get("card_id", "")).upper()
                metadata = card_metadata.get(card_id, {})
                if metadata and metadata.get("quote_use") not in {"exact-quote", ""}:
                    trace_findings.append({"code": "exact_quote_policy_mismatch", "detail": f"{card_id or 'unknown'} 的卡片不是 exact-quote 使用方式"})
                if not quote_text or quote_text not in prose or card_texts.get(card_id) != quote_text:
                    trace_findings.append({"code": "exact_quote_unverified", "detail": f"{card_id or 'unknown'} 的精确引文未逐字对应原文卡"})
        if trace_findings:
            add_finding(findings, "trace_contract_failed", 60, " / ".join(str(item["code"]) for item in trace_findings))

    anti_path = root / "references" / "09-反角色对照.md"
    anti_hits: list[dict[str, object]] = []
    if anti_path.is_file():
        for rule_id, block in iter_anti_blocks(read_text(anti_path)):
            raw_signals = field_value(block, "检测信号")
            signals = [
                item.strip(" `\"'“”‘’")
                for item in re.split(r"\s+/\s+|[,，;；]", raw_signals)
                if item.strip() and "待填写" not in item
            ]
            matched = [signal for signal in signals if signal in prose]
            if matched:
                anti_hits.append({"rule_id": rule_id, "signals": matched})
        if anti_hits:
            add_finding(
                findings,
                "character_anti_rule",
                min(30, 12 * len(anti_hits)),
                " / ".join(str(item["rule_id"]) for item in anti_hits),
            )

    score = min(100, sum(int(item["weight"]) for item in findings))
    status = "pass" if score < 40 else ("review" if score < 60 else "fail")
    return {
        "checker_contract_version": CHECKER_CONTRACT_VERSION,
        "status": status,
        "ai_tone_score": score,
        "prose_length": len(prose),
        "average_sentence_length": average_length,
        "short_sentence_count": short_sentences,
        "oral_markers": oral_hits,
        "findings": findings,
        "anti_rule_hits": anti_hits,
        "profile": profile,
        "trace_findings": trace_findings,
        "note": "分数同时检查通用腔与人物存在轨迹；长句、古文或角色式重复只在 EXPR 篇幅档支持时放行。",
    }


def analyze_batch(entries: Sequence[object], root: Path) -> dict[str, object]:
    normalized_entries: list[dict[str, object]] = []
    for entry in entries:
        if isinstance(entry, str):
            normalized_entries.append({"response": entry, "generation_trace": {}})
        elif isinstance(entry, dict):
            normalized_entries.append({
                "response": str(entry.get("response") or entry.get("text") or ""),
                "generation_trace": entry.get("generation_trace") if isinstance(entry.get("generation_trace"), dict) else {},
            })
    texts = [str(entry["response"]) for entry in normalized_entries if str(entry["response"]).strip()]
    traces = [entry["generation_trace"] for entry in normalized_entries if str(entry["response"]).strip()]
    results = [analyze(text, root, trace if isinstance(trace, dict) else {}) for text, trace in zip(texts, traces)]
    prose_items = [visible_prose(text) for text in texts]
    workflow_indices = [index for index, prose in enumerate(prose_items) if WORKFLOW_FRAME_RE.search(prose)]
    we_indices = [index for index, prose in enumerate(prose_items) if "我们" in prose]
    openings = [re.sub(r"[^\w\u4e00-\u9fff]+", "", prose)[:4] for prose in prose_items if prose]
    repeated_openings = {opening: count for opening, count in Counter(openings).items() if opening and count >= 2}
    prose_lengths = [len(prose) for prose in prose_items if prose]
    sentence_counts = [len(sentence_lengths(prose)) for prose in prose_items if prose]
    question_end_indices = [index for index, prose in enumerate(prose_items) if QUESTION_END_RE.search(prose)]

    def response_shape(prose: str, trace: dict[str, object]) -> str:
        traced = str(trace.get("response_shape", "")).strip().lower()
        if traced:
            return traced
        if WORKFLOW_FRAME_RE.search(prose):
            return "workflow"
        if re.match(r"^(?:不行|不对|等等|等一下|先停|别动|不能)", prose):
            return "direct-interrupt"
        if re.search(r"(?:不是你|别怪自己|没关系|没事).{0,24}(?:我们|再|先)", prose):
            return "reassure-then-act"
        if QUESTION_END_RE.search(prose):
            return "question-close"
        if re.search(r"(?:结论|结果|总之|所以).{0,36}$", prose):
            return "summary-close"
        return "other"

    shapes = [response_shape(prose, trace if isinstance(trace, dict) else {}) for prose, trace in zip(prose_items, traces) if prose]
    shape_counts = Counter(shapes)
    repeated_shapes = {
        shape: count for shape, count in shape_counts.items()
        if shape != "other" and count >= max(3, (len(shapes) + 1) // 2)
    }
    findings: list[dict[str, object]] = []
    required_repetition = max(3, (len(texts) + 1) // 2)
    repeated_workflow_count = len(workflow_indices) if len(workflow_indices) >= required_repetition else 0
    if len(workflow_indices) >= required_repetition:
        add_finding(
            findings, "batch_workflow_skeleton_repeated", 55,
            f"{len(workflow_indices)}/{len(texts)} 条重复使用先做再做或先做我们再推进的流程骨架",
        )
    if len(texts) >= 4 and len(we_indices) * 100 >= len(texts) * 60:
        add_finding(findings, "batch_collective_assistant_voice", 25, f"{len(we_indices)}/{len(texts)} 条依赖“我们”推进")
    if repeated_openings:
        add_finding(
            findings, "batch_opening_repeated", 20,
            " / ".join(f"{opening}×{count}" for opening, count in sorted(repeated_openings.items())),
        )
    if len(prose_lengths) >= 5:
        length_spread = max(prose_lengths) - min(prose_lengths)
        mean_length = sum(prose_lengths) / len(prose_lengths)
        if length_spread <= max(18, mean_length * 0.35):
            add_finding(
                findings, "batch_uniform_response_length", 22,
                f"{len(prose_lengths)} 条回复长度集中在 {min(prose_lengths)}–{max(prose_lengths)} 字",
            )
        if len(set(sentence_counts)) == 1:
            add_finding(
                findings, "batch_uniform_sentence_count", 18,
                f"{len(sentence_counts)} 条回复均为 {sentence_counts[0]} 个句段",
            )
    if len(texts) >= 5 and len(question_end_indices) * 100 >= len(texts) * 70:
        add_finding(
            findings, "batch_question_closure_repeated", 35,
            f"{len(question_end_indices)}/{len(texts)} 条以追问收尾；真实对话允许陈述后自然停住",
        )
    if repeated_shapes:
        add_finding(
            findings, "batch_response_shape_repeated", 35,
            " / ".join(f"{shape}×{count}" for shape, count in sorted(repeated_shapes.items())),
        )
    non_pass = sum(result["status"] != "pass" for result in results)
    if non_pass:
        add_finding(
            findings,
            "batch_individual_failures",
            60,
            f"{non_pass}/{len(texts)} 条单条检查未通过；正式批量验收不允许隐藏 review 或 fail 样本",
        )
    current_asset_version = asset_version(root)
    v2 = current_asset_version >= 2
    v3 = current_asset_version >= 3
    valid_traces = [trace for trace in traces if isinstance(trace, dict)]
    def signal_kinds(trace: dict[str, object]) -> set[str]:
        signals = trace.get("visible_character_signals")
        if not isinstance(signals, list):
            return set()
        return {
            str(item.get("kind") or "").strip().lower()
            for item in signals if isinstance(item, dict)
        }

    if v3:
        presence_count = sum(
            bool(trace.get("behavior_rule_ids"))
            and bool(signal_kinds(trace).intersection({"judgment", "emotion", "relationship", "initiative"}))
            and bool(signal_kinds(trace).intersection({"rhetoric", "rhythm", "background"}))
            for trace in valid_traces
        )
        emotional_count = sum(bool(signal_kinds(trace).intersection({"emotion", "relationship"})) for trace in valid_traces)
        proactive_count = sum("initiative" in signal_kinds(trace) for trace in valid_traces)
        traceable_count = sum(bool(trace.get("behavior_rule_ids")) for trace in valid_traces)
    else:
        presence_count = sum(bool(trace.get("character_presence")) and bool(trace.get("mind_rule_ids") or trace.get("expression_rule_ids")) for trace in valid_traces)
        emotional_count = sum(trace.get("emotional_response") is True for trace in valid_traces)
        proactive_count = sum(trace.get("proactive_expression") is True for trace in valid_traces)
        traceable_count = sum(bool(trace.get("mind_rule_ids") or trace.get("expression_rule_ids")) for trace in valid_traces)
    behavior_rule_ids = {
        str(rule_id).upper()
        for trace in valid_traces
        for rule_id in (trace.get("behavior_rule_ids") if isinstance(trace.get("behavior_rule_ids"), list) else [])
    }
    background_ids = [
        str(background_id)
        for trace in valid_traces
        for background_id in (trace.get("background_ids") if isinstance(trace.get("background_ids"), list) else [])
    ]
    repeated_background_ids = {key: value for key, value in Counter(background_ids).items() if value > 3}
    length_adapted = 0
    for prose, trace in zip(prose_items, valid_traces):
        desired = str(trace.get("desired_length", "auto")).lower()
        length = len(prose)
        if desired == "brief":
            length_adapted += int(length <= 120)
        elif desired == "extended":
            length_adapted += int(length >= 120)
        else:
            length_adapted += 1
    sample_count = max(len(texts), 1)
    presence_coverage = round(presence_count * 100 / sample_count)
    emotional_coverage = round(emotional_count * 100 / sample_count)
    proactive_coverage = round(proactive_count * 100 / sample_count)
    traceability_coverage = round(traceable_count * 100 / sample_count)
    length_coverage = round(length_adapted * 100 / sample_count)
    if v2 and presence_coverage < 90:
        add_finding(findings, "batch_character_presence_low", 60, f"人物存在覆盖 {presence_coverage}% 低于 90%")
    if v2 and emotional_coverage < 60:
        add_finding(findings, "batch_emotional_response_low", 45, f"情绪回应覆盖 {emotional_coverage}% 低于 60%")
    if v2 and proactive_coverage < 40:
        add_finding(findings, "batch_proactive_expression_low", 45, f"主动表达覆盖 {proactive_coverage}% 低于 40%")
    if v2 and traceability_coverage < 90:
        add_finding(findings, "batch_traceability_low", 60, f"人物轨迹追溯覆盖 {traceability_coverage}% 低于 90%")
    if v2 and length_coverage < 90:
        add_finding(findings, "batch_length_adaptation_low", 45, f"篇幅适配覆盖 {length_coverage}% 低于 90%")
    if v2 and repeated_background_ids:
        add_finding(findings, "batch_background_callback_repeated", 35, " / ".join(f"{key}×{value}" for key, value in sorted(repeated_background_ids.items())))
    if v3 and len(behavior_rule_ids) < 10:
        add_finding(
            findings, "batch_behavior_rule_coverage_low", 60,
            f"实际连续对话只覆盖 {len(behavior_rule_ids)} 个 BEHAV 机制，至少需要 10 个",
        )
    score = min(100, sum(int(item["weight"]) for item in findings))
    status = "pass" if score < 40 else ("review" if score < 60 else "fail")
    return {
        "checker_contract_version": CHECKER_CONTRACT_VERSION,
        "status": status,
        "ai_tone_score": score,
        "sample_count": len(texts),
        "workflow_frame_count": len(workflow_indices),
        "workflow_skeleton_count": repeated_workflow_count,
        "collective_assistant_voice_count": len(we_indices),
        "repeated_openings": repeated_openings,
        "repeated_shapes": repeated_shapes,
        "question_closure_count": len(question_end_indices),
        "response_length_range": [min(prose_lengths), max(prose_lengths)] if prose_lengths else [],
        "sentence_counts": sentence_counts,
        "character_presence_coverage": presence_coverage,
        "emotional_response_coverage": emotional_coverage,
        "proactive_expression_coverage": proactive_coverage,
        "traceability_coverage": traceability_coverage,
        "behavior_rule_coverage_count": len(behavior_rule_ids),
        "behavior_rule_ids": sorted(behavior_rule_ids),
        "length_adaptation_coverage": length_coverage,
        "background_callback_count": len(background_ids),
        "repeated_background_ids": repeated_background_ids,
        "quotation_trace_count": sum(
            len(trace.get("exact_quotes")) for trace in valid_traces if isinstance(trace.get("exact_quotes"), list)
        ),
        "findings": findings,
        "responses": results,
        "note": "批量检查用于发现单条看似自然、合起来却反复使用同一开发助手骨架的退化。",
    }


def read_batch(path: Path) -> list[object]:
    payload = json.loads(read_text(path))
    if not isinstance(payload, list):
        raise SystemExit("错误：批量文件必须是 JSON 数组")
    result: list[object] = []
    for item in payload:
        if isinstance(item, str):
            value = item
        elif isinstance(item, dict):
            value = item
        else:
            value = ""
        candidate = value if isinstance(value, str) else str(value.get("response") or value.get("text") or "")
        if candidate.strip():
            result.append(value)
    if not result:
        raise SystemExit("错误：批量文件中没有可检查的回复")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查人格回复中的项目经理腔、AI 书面腔和反角色模式。")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="角色 Skill 根目录")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text", default="", help="要检查的回复文本")
    source.add_argument("--file", help="从 UTF-8 文件读取回复文本")
    source.add_argument("--batch-file", help="从 UTF-8 JSON 数组读取多条回复并检查重复骨架")
    parser.add_argument("--strict", action="store_true", help="review 或 fail 时返回非零退出码")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    if args.batch_file:
        batch_path = Path(args.batch_file).expanduser().resolve()
        result = analyze_batch(read_batch(batch_path), Path(args.root).expanduser().resolve())
        result["batch_file"] = str(batch_path)
        result["batch_file_sha256"] = hashlib.sha256(batch_path.read_bytes()).hexdigest()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if args.strict and result["status"] != "pass" else 0
    if args.file:
        text = read_text(Path(args.file).expanduser().resolve())
    elif args.text:
        text = args.text
    else:
        text = sys.stdin.read()
    if not text.strip():
        raise SystemExit("错误：没有提供要检查的回复文本")
    result = analyze(text, Path(args.root).expanduser().resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.strict and result["status"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
