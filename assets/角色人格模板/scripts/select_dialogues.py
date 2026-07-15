#!/usr/bin/env python3
"""Retrieve source-grounded dialogue evidence and delivery guidance."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


CARD_HEADING_RE = re.compile(
    r"^##\s+([A-Z0-9][A-Z0-9-]*-\d{4})\s*$", re.MULTILINE | re.IGNORECASE
)
RULE_HEADING_RE = re.compile(r"^###\s+((?:CORE|VOICE|MICRO|MODE|ANTI)-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
SCENE_HEADING_RE = re.compile(r"^##\s+([a-z][a-z-]*)\s+\|", re.MULTILINE)
TAG_RE = re.compile(r"\b([a-z_]+)\s*=\s*([^;；]+)", re.IGNORECASE)
MAPPING_RE = re.compile(r"\b([A-Z0-9][A-Z0-9-]*-\d{4})\s*=>\s*([^;；]+)", re.IGNORECASE)

# Only source-scene semantics are scored. Work state, user state, and risk are
# first routed through references/04-工作场景迁移.md and never stored as proof
# inside an original dialogue card.
WEIGHTS = {
    "speech_act": 11,
    "trigger": 10,
    "interaction": 9,
    "position": 7,
    "relation": 6,
    "emotion": 5,
    "initiative": 4,
}
STRONG_KEYS = {"speech_act", "trigger", "interaction"}
SIGNATURE_LEVELS = {"核心", "常用"}
VERIFIED_LABEL_EVIDENCE = {"原文可见", "上下文可见", "来源明确", "用户确认"}
VERIFIED_ORIGINAL_QUALITIES = {"原声核验", "原语言文本核验", "可靠转写核验", "原始版式核验", "原创确认"}
COMPLETE_SCENES = {"完整", "语境充分", "原创设定"}
CONVERSATIONAL_CONTEXTS = {"对话场景", "访谈回答"}
NARRATIVE_CONTEXTS = {"叙事场景", "内心独白"}
SELF_CONTAINED_CONTEXTS = {"演讲发言", "博客文章", "社交媒体", "书信"}
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
HIGH_RISKS = {"high", "critical", "danger", "severe"}
LOCATOR_ONLY_CONTEXT_MARKERS = (
    "以话数与场景标题定位", "资料说明可定位", "由同一官方场景条目定位",
    "见来源页", "见来源索引", "官方场景页以", "定位（", "定位(",
)


@dataclass(frozen=True)
class Card:
    card_id: str
    source_file: str
    block: str
    tags: Dict[str, Set[str]]
    source_type: str
    card_type: str
    original_text: str
    original_language: str
    original_quality: str
    recognition: str
    scene_id: str
    scene_completeness: str
    context_type: str
    interaction_function: str
    reaction: str
    interaction_position: str
    initiative: str
    visual_anchor: str
    label_evidence: Dict[str, str]
    previous_text: str
    trigger_text: str
    next_text: str
    dialogue_target: str
    direct_use: str


@dataclass(frozen=True)
class Match:
    card: Card
    score: int
    matched: Tuple[str, ...]
    tier: int
    evidence_level: str
    evidence_gaps: Tuple[str, ...]


@dataclass(frozen=True)
class WorkRoute:
    scene_id: str
    query: Dict[str, Set[str]]
    block: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def split_values(value: str) -> Set[str]:
    return {
        item.strip().lower()
        for item in re.split(r"[/,，、|]", value)
        if item.strip()
    }


def field_value(block: str, field: str) -> str:
    match = re.search(rf"^-\s*{re.escape(field)}[：:]\s*(.+?)\s*$", block, re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_tag_value(value: str) -> Dict[str, Set[str]]:
    return {key.lower(): split_values(raw) for key, raw in TAG_RE.findall(value)}


def parse_tags(block: str) -> Dict[str, Set[str]]:
    # Legacy fallback keeps old characters runnable, but release validation
    # requires 原作检索标签 and rejects work-domain tags in the source card.
    return parse_tag_value(field_value(block, "原作检索标签") or field_value(block, "检索标签"))


def parse_label_evidence(block: str) -> Dict[str, str]:
    return {
        key.lower(): raw.strip()
        for key, raw in TAG_RE.findall(field_value(block, "标签依据"))
    }


def parse_evidence_mapping(block: str) -> Dict[str, str]:
    return {card_id.upper(): source_field.strip() for card_id, source_field in MAPPING_RE.findall(field_value(block, "证据映射"))}


def split_mapping_observation(value: str) -> Tuple[str, str]:
    match = re.match(r"^([^=：]+?)(?:[=：](.+))?$", value.strip())
    if not match:
        return value.strip(), ""
    return match.group(1).strip(), (match.group(2) or "").strip()


def context_is_missing(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or any(
        marker in normalized
        for marker in ("缺失", "未知", "不明", "未提供", "未逐句标出", "无法确认", "无法定位", "不适用")
    )


def context_is_grounded(value: str) -> bool:
    normalized = value.strip().lower()
    return not context_is_missing(value) and not any(
        marker in normalized for marker in LOCATOR_ONLY_CONTEXT_MARKERS
    )


def iter_card_blocks(text: str) -> Iterable[Tuple[str, str]]:
    matches = list(CARD_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end].strip()


def iter_rule_blocks(text: str) -> Iterable[Tuple[str, str]]:
    matches = list(RULE_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).upper(), text[match.end() : end].strip()


def iter_scene_blocks(text: str) -> Iterable[Tuple[str, str]]:
    matches = list(SCENE_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).lower(), text[match.end() : end].strip()


def load_cards(root: Path) -> List[Card]:
    references = root / "references"
    paths = sorted(
        path
        for path in references.rglob("*对白库*.md")
        if path.is_file() and "索引" not in path.name
    )
    cards: List[Card] = []
    seen: Set[str] = set()
    for path in paths:
        for card_id, block in iter_card_blocks(read_text(path)):
            if card_id in seen:
                continue
            seen.add(card_id)
            cards.append(
                Card(
                    card_id=card_id,
                    source_file=path.relative_to(root).as_posix(),
                    block=block,
                    tags=parse_tags(block),
                    source_type=field_value(block, "来源类型"),
                    card_type=field_value(block, "卡片类型"),
                    original_text=field_value(block, "原文"),
                    original_language=field_value(block, "原文语言"),
                    original_quality=field_value(block, "原文质量"),
                    recognition=field_value(block, "识别度"),
                    scene_id=field_value(block, "场景编号"),
                    scene_completeness=field_value(block, "场景完整度"),
                    context_type=field_value(block, "语境类型"),
                    interaction_function=field_value(block, "互动功能"),
                    reaction=field_value(block, "角色即时反应"),
                    interaction_position=field_value(block, "互动位置"),
                    initiative=field_value(block, "主动性"),
                    visual_anchor=field_value(block, "画面锚点"),
                    label_evidence=parse_label_evidence(block),
                    previous_text=field_value(block, "前置原文"),
                    trigger_text=field_value(block, "触发话语"),
                    next_text=field_value(block, "后续原文"),
                    dialogue_target=field_value(block, "对话对象"),
                    direct_use=field_value(block, "可直接使用"),
                )
            )
    return cards


def load_work_route(root: Path, task_state: str) -> WorkRoute:
    if not task_state:
        return WorkRoute("", {}, "")
    path = root / "references" / "04-工作场景迁移.md"
    if not path.is_file():
        return WorkRoute(task_state.lower(), {}, "")
    for scene_id, block in iter_scene_blocks(read_text(path)):
        if scene_id == task_state.lower():
            return WorkRoute(scene_id, parse_tag_value(field_value(block, "目标检索")), block)
    return WorkRoute(task_state.lower(), {}, "")


def effective_query(args: argparse.Namespace, route: WorkRoute) -> Dict[str, str]:
    direct = {
        "speech_act": args.speech_act or args.intent,
        "trigger": args.trigger,
        "interaction": args.interaction,
        "position": args.position,
        "relation": args.relation,
        "emotion": args.emotion,
        "initiative": args.initiative,
    }
    result: Dict[str, str] = {}
    for key in WEIGHTS:
        if direct.get(key, "").strip():
            result[key] = direct[key].strip().lower()
        elif route.query.get(key):
            result[key] = sorted(route.query[key])[0]
        else:
            result[key] = ""
    result["source_language"] = args.source_language
    result["micro_function"] = args.micro_function.strip().lower()
    return result


def language_matches(query: str, value: str) -> bool:
    if not query or not value:
        return True
    normalized = query.lower()
    base = normalized.split("-", 1)[0]
    candidate = value.lower()
    return candidate == normalized or candidate.split("-", 1)[0] == base


def evidence_for_match(card: Card, matched: Set[str]) -> Tuple[str, Tuple[str, ...]]:
    gaps: List[str] = []
    direct_only = (
        card.scene_completeness not in COMPLETE_SCENES
        and card.direct_use in {"是", "仅短句"}
        and "speech_act" in matched
        and matched <= {"speech_act", "interaction", "position"}
    )
    for key in sorted(matched):
        evidence = card.label_evidence.get(key, "")
        if not evidence:
            gaps.append(f"{key}:missing-evidence")
        elif evidence not in VERIFIED_LABEL_EVIDENCE:
            gaps.append(f"{key}:{evidence}")
    if "trigger" in matched and not context_is_grounded(card.trigger_text):
        gaps.append("trigger:missing-context")
    if "relation" in matched and not context_is_grounded(card.dialogue_target):
        gaps.append("relation:missing-target")
    if card.original_quality not in VERIFIED_ORIGINAL_QUALITIES:
        gaps.append("original:unverified")
    if card.scene_completeness not in COMPLETE_SCENES and not direct_only:
        gaps.append("scene:incomplete")

    if gaps:
        return "low", tuple(sorted(set(gaps)))
    if direct_only:
        # A verified, self-contained catchphrase may answer an exact surface
        # act.  It remains medium and cannot support generalized rules because
        # release validation requires complete context for those rules.
        return "medium", ("scope:direct-only",)
    verified_count = sum(card.label_evidence.get(key) in VERIFIED_LABEL_EVIDENCE for key in matched)
    context_count = sum(
        context_is_grounded(value)
        for value in (card.previous_text, card.trigger_text, card.next_text, card.dialogue_target)
    )
    if card.context_type in CONVERSATIONAL_CONTEXTS:
        required_for_high, required_for_medium = 3, 2
    elif card.context_type in NARRATIVE_CONTEXTS:
        required_for_high, required_for_medium = 2, 1
    elif card.context_type in SELF_CONTAINED_CONTEXTS:
        required_for_high, required_for_medium = 1, 1
    else:
        required_for_high, required_for_medium = 3, 2
    if verified_count >= 3 and context_count >= required_for_high:
        return "high", ()
    if verified_count >= 2 and context_count >= required_for_medium:
        return "medium", ()
    return "low", ("semantic-context-too-thin",)


def score_card(card: Card, query: Dict[str, str]) -> Optional[Match]:
    if query.get("source_language") and not language_matches(query["source_language"], card.original_language):
        return None

    score = 0
    matched: List[str] = []
    for key, weight in WEIGHTS.items():
        wanted = query.get(key, "").strip().lower()
        if not wanted:
            continue
        values = card.tags.get(key, set())
        if wanted in values or "any" in values or "all" in values:
            score += weight
            matched.append(key)

    if card.source_type in {"原作明确", "可靠转写", "本人公开表达"}:
        score += 2
    if card.original_quality == "原声核验":
        score += 3
    elif card.original_quality in VERIFIED_ORIGINAL_QUALITIES:
        score += 2
    if card.recognition in SIGNATURE_LEVELS:
        score += 1

    matched_set = set(matched)
    if matched_set & STRONG_KEYS and len(matched_set) >= 2:
        tier = 3
    elif matched_set & STRONG_KEYS or len(matched_set) >= 2:
        tier = 2
    elif matched_set:
        tier = 1
    else:
        tier = 0
    evidence_level, evidence_gaps = evidence_for_match(card, matched_set)
    return Match(card, score, tuple(matched), tier, evidence_level, evidence_gaps)


def choose_matches(matches: Sequence[Match], limit: int, allow_low_evidence: bool = False) -> List[Match]:
    ranked = sorted(
        matches,
        key=lambda item: (
            -min(item.tier, CONFIDENCE_RANK[item.evidence_level] + 1),
            -CONFIDENCE_RANK[item.evidence_level],
            -item.tier,
            -item.score,
            item.card.card_id,
        ),
    )
    eligible = [
        item for item in ranked
        if allow_low_evidence or (item.tier >= 2 and item.evidence_level in {"medium", "high"})
    ]
    if not eligible:
        return []
    top_score = eligible[0].score
    # Do not pad retrieval with weak tail cards merely to hit the requested count.
    eligible = [item for item in eligible if item.score >= max(7, top_score - 8)]
    chosen: List[Match] = []
    used_scenes: Set[str] = set()
    for candidate in eligible:
        scene = candidate.card.scene_id
        if scene and scene in used_scenes:
            continue
        chosen.append(candidate)
        if scene:
            used_scenes.add(scene)
        if len(chosen) >= limit:
            break
    return chosen


def parse_excludes(values: Sequence[str]) -> Set[str]:
    result: Set[str] = set()
    for value in values:
        result.update(item.strip().upper() for item in re.split(r"[,，;；\s]+", value) if item.strip())
    return result


def condition_match_count(conditions: Dict[str, Set[str]], query: Dict[str, str]) -> int:
    count = 0
    for key, values in conditions.items():
        wanted = query.get(key, "")
        if wanted and (wanted in values or "any" in values or "all" in values):
            count += 1
    return count


def related_rules(
    root: Path, selected: Sequence[Match], query: Dict[str, str], limit: int = 2
) -> Dict[str, List[Dict[str, object]]]:
    selected_levels = {item.card.card_id: item.evidence_level for item in selected}
    selected_ids = set(selected_levels)
    references = {
        "core": (root / "references" / "01-角色核心.md", "CORE-"),
        "voice": (root / "references" / "02-语言声纹.md", "VOICE-"),
        "micro": (root / "references" / "02-语言声纹.md", "MICRO-"),
        "modes": (root / "references" / "03-情绪与关系.md", "MODE-"),
        "anti": (root / "references" / "09-反角色对照.md", "ANTI-"),
    }
    result: Dict[str, List[Dict[str, object]]] = {key: [] for key in references}
    query_has_semantics = any(query.get(key) for key in WEIGHTS)
    for key, (path, prefix) in references.items():
        if not path.is_file():
            continue
        if key == "micro" and not query.get("micro_function"):
            continue
        candidates: List[Tuple[int, str, str, List[str], Dict[str, str], int]] = []
        for rule_id, block in iter_rule_blocks(read_text(path)):
            if not rule_id.startswith(prefix):
                continue
            if key == "micro" and query.get("micro_function"):
                if (field_value(block, "功能") or "").strip().lower() != query["micro_function"]:
                    continue
            mappings = parse_evidence_mapping(block)
            matched_ids = sorted(
                card_id for card_id in selected_ids & set(mappings)
                if selected_levels[card_id] in {"medium", "high"}
            )
            conditions = parse_tag_value(field_value(block, "检索条件"))
            condition_matches = condition_match_count(conditions, query)
            if matched_ids and (not query_has_semantics or condition_matches > 0):
                candidates.append(
                    (len(matched_ids) * 5 + condition_matches, rule_id, block, matched_ids, mappings, condition_matches)
                )
        candidates.sort(key=lambda item: (-item[0], item[1]))
        result[key] = [
            {
                "rule_id": rule_id,
                "matched_card_ids": matched_ids,
                "supporting_card_ids": sorted(mappings),
                "evidence_mapping": {card_id: mappings[card_id] for card_id in matched_ids},
                "condition_matches": condition_matches,
                "content": block,
            }
            for _, rule_id, block, matched_ids, mappings, condition_matches in candidates[:limit]
        ]
    return result


def composition_guidance(
    cards: Sequence[Card], selected: Sequence[Match], rules: Dict[str, List[Dict[str, object]]],
    query: Dict[str, str],
) -> Dict[str, object]:
    cards_by_id = {card.card_id: card for card in cards}
    selected_ids = {item.card.card_id for item in selected}
    support_ids: List[str] = []
    used_units = {item.card.scene_id for item in selected if item.card.scene_id}
    for group in ("micro", "voice", "core", "modes"):
        for rule in rules.get(group, []):
            for card_id in rule.get("supporting_card_ids", []):
                card = cards_by_id.get(str(card_id))
                if not card or card.card_id in selected_ids or card.card_id in support_ids:
                    continue
                if card.scene_id and card.scene_id in used_units:
                    continue
                support_ids.append(card.card_id)
                if card.scene_id:
                    used_units.add(card.scene_id)
                if len(support_ids) >= 3:
                    break
            if len(support_ids) >= 3:
                break
        if len(support_ids) >= 3:
            break

    # A rule may only cite two evidence units. When the current reply needs a
    # fuller voice sample, add semantically matching verified cards instead of
    # pretending the single retrieved card proves the whole answer style.
    if len(support_ids) < 2:
        query_values = {
            key: split_values(value) for key, value in query.items()
            if key in WEIGHTS and value.strip()
        }
        candidates: List[Tuple[int, str]] = []
        for card in cards:
            if card.card_id in selected_ids or card.card_id in support_ids:
                continue
            if card.scene_id and card.scene_id in used_units:
                continue
            matched_keys = {
                key for key, values in query_values.items()
                if values and values.intersection(card.tags.get(key, set()))
            }
            if not matched_keys.intersection(STRONG_KEYS) or len(matched_keys) < 2:
                continue
            if card.original_quality not in VERIFIED_ORIGINAL_QUALITIES:
                continue
            candidates.append((sum(WEIGHTS[key] for key in matched_keys), card.card_id))
        for _, card_id in sorted(candidates, key=lambda item: (-item[0], item[1])):
            card = cards_by_id[card_id]
            if card.scene_id and card.scene_id in used_units:
                continue
            support_ids.append(card_id)
            if card.scene_id:
                used_units.add(card.scene_id)
            if len(support_ids) >= 2:
                break

    style_exemplars = []
    for card_id in support_ids:
        card = cards_by_id[card_id]
        style_exemplars.append(
            {
                "card_id": card_id,
                "scene_id": card.scene_id,
                "original_text": card.original_text,
                "reaction": card.reaction,
                "oral_observation": field_value(card.block, "口语现象"),
                "rhythm_observation": field_value(card.block, "句式与节奏"),
            }
        )

    micro_required = bool(query.get("micro_function"))
    slots = {
        "current_reaction": bool(selected),
        "micro_interaction": bool(rules.get("micro")) if micro_required else True,
        "voice_structure": bool(rules.get("voice")),
        "stance_or_relation": bool(rules.get("core") or rules.get("modes")),
        "anti_pattern_check": bool(rules.get("anti")),
        "cross_unit_style_support": len(style_exemplars) >= 2,
    }
    filled = sum(bool(value) for value in slots.values())
    readiness = "high" if all(slots.values()) else ("medium" if bool(selected) and filled >= 4 else "low")
    warnings: List[str] = []
    if micro_required and not rules.get("micro"):
        warnings.append("当前是短对话，但没有命中对应微互动规则；不要用通用问候或客服句补齐")
    if len(style_exemplars) < 2:
        warnings.append("跨证据单元的声纹示例不足；召回置信度不能当作成品角色还原度")
    if not rules.get("anti"):
        warnings.append("没有命中反角色规则；发送前必须额外检查项目经理与客服骨架")
    return {
        "generation_readiness": readiness,
        "retrieval_is_not_fidelity": True,
        "micro_function": query.get("micro_function", ""),
        "slots": slots,
        "direct_match_card_ids": sorted(selected_ids),
        "style_exemplars": style_exemplars,
        "warnings": warnings,
        "assembly_order": [
            "从当前匹配卡提取角色面对触发时的即时反应",
            "从微互动或声纹规则提取开场、断句、接话和收束方式",
            "从角色核心或情绪关系规则确定立场与主动性",
            "嵌入准确工作事实；不得套用通用助手的先做再做骨架",
            "去掉名称和专有词后执行反角色检查",
        ],
    }


def delivery_guidance(
    selected: Sequence[Match], rules: Dict[str, List[Dict[str, object]]], route: WorkRoute,
    risk: str, turns_since_presence: int, turns_since_initiative: int,
    last_user_focus: str, open_thread: str, previous_shape: str,
) -> Dict[str, object]:
    high_risk = risk.lower() in HIGH_RISKS
    if high_risk:
        presence_status = "serious-only"
        initiative_status = "protective-only"
    else:
        presence_status = "due" if turns_since_presence >= 3 else ("hold" if turns_since_presence >= 0 else "optional")
        initiative_status = "due" if turns_since_initiative >= 4 else ("hold" if turns_since_initiative >= 0 else "optional")
    anchors = []
    for item in selected:
        if item.card.visual_anchor and not context_is_missing(item.card.visual_anchor):
            anchors.append({"card_id": item.card.card_id, "visual_anchor": item.card.visual_anchor})
    mode_cues = []
    for rule in rules.get("modes", []):
        block = str(rule["content"])
        mode_cues.append(
            {
                "rule_id": rule["rule_id"],
                "micro_reaction": field_value(block, "临场信号"),
                "visual_expression": field_value(block, "画面表达"),
                "proactive_expression": field_value(block, "主动表达"),
                "cooldown": field_value(block, "触发与冷却"),
            }
        )
    return {
        "presence_status": presence_status,
        "initiative_status": initiative_status,
        "max_presence_beats": 1,
        "source_anchors": anchors[:2],
        "mode_cues": mode_cues,
        "work_scene": route.scene_id,
        "work_presence_strategy": field_value(route.block, "临场表达策略"),
        "work_initiative_condition": field_value(route.block, "主动表达条件"),
        "work_cooldown": field_value(route.block, "冷却与重复"),
        "no_fabrication": field_value(route.block, "禁止虚构"),
        "conversation_continuity": {
            "last_user_focus": last_user_focus,
            "open_thread": open_thread,
            "previous_shape": previous_shape,
            "must_react_to_visible_focus": bool(last_user_focus),
            "must_continue_open_thread": bool(open_thread),
            "avoid_repeating_previous_shape": bool(previous_shape),
            "question_is_optional": True,
            "natural_stop_allowed": True,
            "human_beat": "用一句有证据的即时反应、改口、立场或回访形成对话脉冲；不额外编造动作",
        },
        "principles": [
            "召回置信度只说明卡片找得准，不说明最终回答已经像角色",
            "回答必须组合即时反应、声纹结构、角色立场或关系模式及反角色检查，不能用一张卡给通用助手骨架背书",
            "直接给用户需要的内容，并在同一条消息中自然表现角色",
            "画面只来自当前可见工作对象、已发生事件或原作证据，不虚构现实动作与感官",
            "一次最多一个临场动作或主动表达；连续几轮不要重复",
            "短应声、停顿词和语气词只能沿用角色证据，不能为了像人而堆叠",
            "不要把每轮都收束成问题、下一步或行动号召；信息已足够时允许自然停住",
            "连续几轮不得使用相同句数、相同开场和相同反应—解释—推进形状",
        ],
    }


def retrieval_diagnostics(
    selected: Sequence[Match], all_matches: Sequence[Match], query: Dict[str, str]
) -> Dict[str, object]:
    high_count = sum(item.tier == 3 for item in selected)
    medium_count = sum(item.tier >= 2 for item in selected)
    match_confidence = "high" if selected and high_count >= min(2, len(selected)) else ("medium" if selected and medium_count == len(selected) else "low")
    high_evidence_count = sum(item.evidence_level == "high" for item in selected)
    medium_evidence_count = sum(item.evidence_level in {"medium", "high"} for item in selected)
    evidence_confidence = "high" if selected and high_evidence_count >= min(2, len(selected)) else ("medium" if selected and medium_evidence_count == len(selected) else "low")
    confidence = min((match_confidence, evidence_confidence), key=lambda value: CONFIDENCE_RANK[value])
    requested = {key for key in WEIGHTS if query.get(key, "").strip()}
    covered = {key for item in selected for key in item.matched}
    gaps = sorted(requested - covered)
    evidence_gaps = sorted({gap for item in all_matches for gap in item.evidence_gaps})
    warnings: List[str] = []
    if not selected:
        warnings.append("没有达到中等相关性且证据完整的卡片；返回空结果，不用弱卡凑数")
    if gaps:
        warnings.append("部分查询维度未覆盖")
    return {
        "confidence": confidence,
        "match_confidence": match_confidence,
        "evidence_confidence": evidence_confidence,
        "selected_cards": len(selected),
        "candidate_cards": len(all_matches),
        "dropped_weak_cards": len(all_matches) - len(selected),
        "high_signal_cards": high_count,
        "high_evidence_cards": high_evidence_count,
        "query_gaps": gaps,
        "evidence_gaps": evidence_gaps,
        "warning": "；".join(warnings),
        "scope_note": "这些置信度只评价召回卡的相关性与证据完整度，不评价最终回答是否像角色",
    }


def markdown_output(
    matches: Sequence[Match], card_count: int, rules: Dict[str, List[Dict[str, object]]],
    retrieval: Dict[str, object], route: WorkRoute, delivery: Dict[str, object], composition: Dict[str, object],
) -> str:
    lines = [
        f"<!-- selected={len(matches)} library_cards={card_count} confidence={retrieval['confidence']} -->",
        f"- 工作路由：{route.scene_id or '无'}",
        f"- 召回置信度：{retrieval['confidence']}",
        f"- 标签匹配置信度：{retrieval['match_confidence']}",
        f"- 证据完整度：{retrieval['evidence_confidence']}",
        f"- 生成准备度：{composition['generation_readiness']}（与召回置信度分开）",
        f"- 临场表达：{delivery['presence_status']}；主动表达：{delivery['initiative_status']}",
    ]
    continuity = delivery.get("conversation_continuity", {})
    if continuity.get("last_user_focus"):
        lines.append(f"- 本轮必须接住：{continuity['last_user_focus']}")
    if continuity.get("open_thread"):
        lines.append(f"- 本轮必须延续：{continuity['open_thread']}")
    if continuity.get("previous_shape"):
        lines.append(f"- 本轮避免重复形状：{continuity['previous_shape']}")
    lines.append("- 允许自然收束：是；追问和下一步不是默认结尾")
    slot_summary = "；".join(
        f"{name}={'ready' if ready else 'missing'}"
        for name, ready in composition.get("slots", {}).items()
    )
    if slot_summary:
        lines.append(f"- 生成槽位：{slot_summary}")
    if retrieval["warning"]:
        lines.append(f"- 警告：{retrieval['warning']}")
    for warning in composition.get("warnings", []):
        lines.append(f"- 生成警告：{warning}")
    for item in matches:
        lines.extend(
            [
                "", f"## {item.card.card_id}", f"- 匹配分：{item.score}",
                f"- 相关层级：{'high' if item.tier == 3 else 'medium'}",
                f"- 证据完整度：{item.evidence_level}",
                f"- 命中维度：{', '.join(item.matched)}",
                f"- 对白库文件：{item.card.source_file}", item.card.block,
            ]
        )
    exemplars = composition.get("style_exemplars", [])
    if exemplars:
        lines.extend(["", "# 跨证据单元风格支持（不是当前场景召回）"])
        for exemplar in exemplars:
            lines.extend(
                [
                    "",
                    f"## {exemplar['card_id']} | {exemplar.get('scene_id') or '未标场景'}",
                    f"- 原文：{exemplar.get('original_text') or '无'}",
                    f"- 即时反应观察：{exemplar.get('reaction') or '无'}",
                    f"- 口语观察：{exemplar.get('oral_observation') or '无'}",
                    f"- 节奏观察：{exemplar.get('rhythm_observation') or '无'}",
                ]
            )
    for label, key in (("角色核心规则", "core"), ("声纹规律", "voice"), ("微互动规则", "micro"), ("情绪关系模式", "modes"), ("反角色规则", "anti")):
        if not rules[key]:
            continue
        lines.extend(["", f"# 命中的{label}"])
        for rule in rules[key]:
            lines.extend(["", f"## {rule['rule_id']}", f"- 命中证据卡：{', '.join(rule['matched_card_ids'])}", str(rule["content"])])
    return "\n".join(lines).rstrip() + "\n"


def json_output(
    matches: Sequence[Match], card_count: int, rules: Dict[str, List[Dict[str, object]]],
    retrieval: Dict[str, object], route: WorkRoute, delivery: Dict[str, object],
    composition: Dict[str, object], query: Dict[str, str],
) -> str:
    payload = {
        "library_cards": card_count,
        "work_route": {"scene_id": route.scene_id, "effective_query": query},
        "retrieval": retrieval,
        "composition_guidance": composition,
        "delivery_guidance": delivery,
        "selected": [
            {
                "card_id": item.card.card_id,
                "score": item.score,
                "relevance": "high" if item.tier == 3 else "medium",
                "evidence_confidence": item.evidence_level,
                "evidence_gaps": list(item.evidence_gaps),
                "matched": list(item.matched),
                "source_file": item.card.source_file,
                "source_type": item.card.source_type,
                "card_type": item.card.card_type,
                "original_text": item.card.original_text,
                "original_language": item.card.original_language,
                "original_quality": item.card.original_quality,
                "recognition": item.card.recognition,
                "scene_id": item.card.scene_id,
                "scene_completeness": item.card.scene_completeness,
                "context_type": item.card.context_type,
                "interaction_function": item.card.interaction_function,
                "reaction": item.card.reaction,
                "interaction_position": item.card.interaction_position,
                "initiative": item.card.initiative,
                "visual_anchor": item.card.visual_anchor,
                "content": item.card.block,
            }
            for item in matches
        ],
        "related_rules": rules,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从原作证据链返回最多 1–6 张真正匹配的对白卡；证据不足时可以返回 0 张。")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="角色 Skill 根目录")
    parser.add_argument("--task-state", default="", help="工作事件；先通过工作迁移表转成原作语义")
    parser.add_argument("--user-state", default="", help="仅供运行时判断，不直接匹配原作卡")
    parser.add_argument("--emotion", default="")
    parser.add_argument("--intent", default="", help="兼容参数；未给 speech-act 时作为其别名")
    parser.add_argument("--speech-act", default="")
    parser.add_argument("--trigger", default="")
    parser.add_argument("--interaction", default="")
    parser.add_argument("--position", default="")
    parser.add_argument("--initiative", default="")
    parser.add_argument("--relation", default="")
    parser.add_argument("--risk", default="")
    parser.add_argument("--language", default="", help="输出语言；不用于过滤原语言语料")
    parser.add_argument("--source-language", default="", help="仅在需要时限制原文语言")
    parser.add_argument(
        "--micro-function", default="",
        choices=("", "greeting", "acknowledgement", "gratitude", "apology", "surprise", "closing"),
        help="问候、应答、感谢、道歉、惊讶或告别等短对话功能；任务对话留空",
    )
    parser.add_argument("--limit", type=int, default=5, choices=range(1, 7), metavar="1..6")
    parser.add_argument("--exclude", action="append", default=[], help="排除编号，可重复或用逗号分隔")
    parser.add_argument("--allow-low-evidence", action="store_true", help="仅用于调试；允许返回低证据卡")
    parser.add_argument("--turns-since-presence", type=int, default=-1, help="距上次临场画面表达的轮数；未知为 -1")
    parser.add_argument("--turns-since-initiative", type=int, default=-1, help="距上次主动表达的轮数；未知为 -1")
    parser.add_argument("--last-user-focus", default="", help="用户上一句话中本轮需要直接接住的具体词或短语")
    parser.add_argument("--open-thread", default="", help="前文尚未收束、需要自然延续的话题；没有则留空")
    parser.add_argument(
        "--previous-shape", default="",
        choices=("", "question", "directive", "reassurance", "summary", "celebration", "refusal", "explanation"),
        help="上一条回复的主要形状，用于避免连续重复",
    )
    parser.add_argument("--format", choices=("markdown", "json", "ids"), default="markdown")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    cards = load_cards(root)
    if not cards:
        raise SystemExit(f"错误：{root / 'references'} 中没有可读取的对白卡片")

    route = load_work_route(root, args.task_state)
    query = effective_query(args, route)
    excluded = parse_excludes(args.exclude)
    matches = [
        match
        for card in cards
        if card.card_id not in excluded
        for match in [score_card(card, query)]
        if match is not None
    ]
    selected = choose_matches(matches, min(args.limit, len(matches)), args.allow_low_evidence)
    rules = related_rules(root, selected, query)
    retrieval = retrieval_diagnostics(selected, matches, query)
    composition = composition_guidance(cards, selected, rules, query)
    delivery = delivery_guidance(
        selected, rules, route, args.risk, args.turns_since_presence, args.turns_since_initiative,
        args.last_user_focus, args.open_thread, args.previous_shape,
    )
    if args.format == "json":
        print(json_output(selected, len(cards), rules, retrieval, route, delivery, composition, query), end="")
    elif args.format == "ids":
        print("\n".join(item.card.card_id for item in selected))
    else:
        print(markdown_output(selected, len(cards), rules, retrieval, route, delivery, composition), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
