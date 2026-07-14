#!/usr/bin/env python3
"""Select a small, relevant set of dialogue cards from a Persona skill."""

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
RULE_HEADING_RE = re.compile(r"^###\s+((?:CORE|VOICE|MODE|ANTI)-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
TAG_RE = re.compile(r"\b([a-z_]+)\s*=\s*([^;；]+)", re.IGNORECASE)
WEIGHTS = {
    "speech_act": 10,
    "trigger": 9,
    "intent": 7,
    "risk": 6,
    "relation": 5,
    "emotion": 5,
    "task_state": 4,
    "user_state": 2,
}
HIGH_RISKS = {"high", "critical", "danger", "severe"}
LOW_RISKS = {"none", "low"}
SIGNATURE_LEVELS = {"核心", "常用"}
VERIFIED_LABEL_EVIDENCE = {"原文可见", "上下文可见", "来源明确", "用户确认"}
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


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
    interaction_function: str
    label_evidence: Dict[str, str]
    previous_text: str
    trigger_text: str
    next_text: str
    dialogue_target: str


@dataclass(frozen=True)
class Match:
    card: Card
    score: int
    matched: Tuple[str, ...]
    tier: int
    evidence_level: str
    evidence_gaps: Tuple[str, ...]


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


def parse_tags(block: str) -> Dict[str, Set[str]]:
    tag_line = field_value(block, "检索标签")
    return {key.lower(): split_values(value) for key, value in TAG_RE.findall(tag_line)}


def parse_label_evidence(block: str) -> Dict[str, str]:
    value = field_value(block, "标签依据")
    return {
        key.lower(): raw.strip()
        for key, raw in TAG_RE.findall(value)
    }


def context_is_missing(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or any(
        marker in normalized
        for marker in ("缺失", "未知", "不明", "未提供", "未逐句标出", "无法确认", "无法定位")
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
                    interaction_function=field_value(block, "互动功能"),
                    label_evidence=parse_label_evidence(block),
                    previous_text=field_value(block, "前置原文"),
                    trigger_text=field_value(block, "触发话语"),
                    next_text=field_value(block, "后续原文"),
                    dialogue_target=field_value(block, "对话对象"),
                )
            )
    return cards


def language_matches(query: str, values: Set[str]) -> bool:
    if not query or not values:
        return True
    normalized = query.lower()
    base = normalized.split("-", 1)[0]
    return "any" in values or "all" in values or any(
        value == normalized or value.split("-", 1)[0] == base for value in values
    )


def risk_allowed(query: str, values: Set[str]) -> bool:
    if not query or not values:
        return True
    normalized = query.lower()
    if normalized in HIGH_RISKS:
        return bool(values & HIGH_RISKS)
    if normalized in LOW_RISKS and values <= HIGH_RISKS:
        return False
    return True


def evidence_for_match(card: Card, matched: Set[str]) -> Tuple[str, Tuple[str, ...]]:
    gaps: List[str] = []
    semantic_keys = matched & {"speech_act", "trigger", "relation", "emotion"}
    for key in sorted(semantic_keys):
        evidence = card.label_evidence.get(key, "")
        if not evidence:
            gaps.append(f"{key}:missing-evidence")
        elif evidence not in VERIFIED_LABEL_EVIDENCE:
            gaps.append(f"{key}:{evidence}")
    if "trigger" in matched and context_is_missing(card.trigger_text):
        gaps.append("trigger:missing-context")
    if "relation" in matched and context_is_missing(card.dialogue_target):
        gaps.append("relation:missing-target")
    if card.original_quality not in {"原声核验", "原语言文本核验", "原始版式核验", "原创确认"}:
        gaps.append("original:unverified")

    if gaps:
        return "low", tuple(sorted(set(gaps)))
    verified_count = sum(card.label_evidence.get(key) in VERIFIED_LABEL_EVIDENCE for key in semantic_keys)
    context_count = sum(
        not context_is_missing(value)
        for value in (card.previous_text, card.trigger_text, card.next_text, card.dialogue_target)
    )
    if verified_count >= 2 and context_count >= 2:
        return "high", ()
    if verified_count >= 1:
        return "medium", ()
    return "low", ("no-semantic-evidence",)


def score_card(card: Card, query: Dict[str, str]) -> Optional[Match]:
    source_language = query.get("source_language", "")
    risk = query.get("risk", "")
    if source_language and not language_matches(source_language, {card.original_language.lower()}):
        return None
    if not risk_allowed(risk, card.tags.get("risk", set())):
        return None

    score = 0
    matched: List[str] = []
    for key, weight in WEIGHTS.items():
        wanted = query.get(key, "").strip().lower()
        if not wanted:
            continue
        values = card.tags.get(key, set())
        is_match = wanted in values or "any" in values or "all" in values
        if is_match:
            score += weight
            matched.append(key)

    if card.source_type == "原作明确":
        score += 2
    if card.original_quality == "原声核验":
        score += 3
    elif card.original_quality in {"原语言文本核验", "原始版式核验", "原创确认"}:
        score += 2
    if card.recognition in SIGNATURE_LEVELS:
        score += 1
    matched_set = set(matched)
    if matched_set & {"speech_act", "trigger"}:
        tier = 3
    elif "intent" in matched_set and matched_set & {"emotion", "relation", "task_state", "user_state"}:
        tier = 2
    elif matched_set & {"intent", "emotion", "relation", "task_state", "user_state"}:
        tier = 1
    else:
        tier = 0
    evidence_level, evidence_gaps = evidence_for_match(card, matched_set)
    return Match(
        card=card,
        score=score,
        matched=tuple(matched),
        tier=tier,
        evidence_level=evidence_level,
        evidence_gaps=evidence_gaps,
    )


def choose_matches(matches: Sequence[Match], limit: int) -> List[Match]:
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
    chosen: List[Match] = []
    used_scenes: Set[str] = set()
    for candidate in ranked:
        scene = candidate.card.scene_id
        if scene and scene in used_scenes:
            continue
        chosen.append(candidate)
        if scene:
            used_scenes.add(scene)
        if len(chosen) >= limit:
            return chosen
    for candidate in ranked:
        if candidate not in chosen:
            chosen.append(candidate)
        if len(chosen) >= limit:
            break
    return chosen


def parse_excludes(values: Sequence[str]) -> Set[str]:
    result: Set[str] = set()
    for value in values:
        result.update(item.strip().upper() for item in re.split(r"[,，;；\s]+", value) if item.strip())
    return result


def related_rules(root: Path, selected: Sequence[Match], limit: int = 2) -> Dict[str, List[Dict[str, object]]]:
    selected_ids = {item.card.card_id for item in selected}
    references = {
        "core": root / "references" / "01-角色核心.md",
        "voice": root / "references" / "02-语言声纹.md",
        "modes": root / "references" / "03-情绪与关系.md",
        "anti": root / "references" / "09-反角色对照.md",
    }
    result: Dict[str, List[Dict[str, object]]] = {key: [] for key in references}
    for key, path in references.items():
        if not path.is_file():
            continue
        candidates: List[Tuple[int, str, str, List[str]]] = []
        for rule_id, block in iter_rule_blocks(read_text(path)):
            evidence_ids = set(re.findall(r"\b[A-Z0-9][A-Z0-9-]*-\d{4}\b", field_value(block, "证据卡")))
            matched_ids = sorted(selected_ids & evidence_ids)
            if matched_ids:
                candidates.append((len(matched_ids), rule_id, block, matched_ids))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        result[key] = [
            {
                "rule_id": rule_id,
                "matched_card_ids": matched_ids,
                "content": block,
            }
            for _, rule_id, block, matched_ids in candidates[:limit]
        ]
    return result


def retrieval_diagnostics(matches: Sequence[Match], query: Dict[str, str]) -> Dict[str, object]:
    high_count = sum(item.tier == 3 for item in matches)
    medium_or_high_count = sum(item.tier >= 2 for item in matches)
    if high_count >= min(3, len(matches)) and matches:
        match_confidence = "high"
    elif medium_or_high_count >= min(3, len(matches)) and matches:
        match_confidence = "medium"
    else:
        match_confidence = "low"
    high_evidence_count = sum(item.evidence_level == "high" for item in matches)
    medium_or_high_evidence_count = sum(item.evidence_level in {"medium", "high"} for item in matches)
    if high_evidence_count >= min(3, len(matches)) and matches:
        evidence_confidence = "high"
    elif medium_or_high_evidence_count >= min(3, len(matches)) and matches:
        evidence_confidence = "medium"
    else:
        evidence_confidence = "low"
    confidence = min((match_confidence, evidence_confidence), key=lambda value: CONFIDENCE_RANK[value])
    requested = {key for key in WEIGHTS if query.get(key, "").strip()}
    covered = {key for item in matches for key in item.matched}
    gaps = sorted(requested - covered)
    evidence_gaps = sorted({gap for item in matches for gap in item.evidence_gaps})
    warnings: List[str] = []
    if match_confidence == "low":
        warnings.append("标签匹配不足")
    if evidence_confidence == "low":
        warnings.append("上下文或标签依据不足")
    warning = "；".join(warnings) + ("；不要把弱相关卡当作角色证据。" if warnings else "")
    return {
        "confidence": confidence,
        "match_confidence": match_confidence,
        "evidence_confidence": evidence_confidence,
        "high_signal_cards": high_count,
        "medium_or_high_cards": medium_or_high_count,
        "high_evidence_cards": high_evidence_count,
        "medium_or_high_evidence_cards": medium_or_high_evidence_count,
        "query_gaps": gaps,
        "evidence_gaps": evidence_gaps,
        "warning": warning,
    }


def markdown_output(
    matches: Sequence[Match], card_count: int, rules: Dict[str, List[Dict[str, object]]],
    retrieval: Dict[str, object],
) -> str:
    lines = [
        f"<!-- selected={len(matches)} library_cards={card_count} confidence={retrieval['confidence']} -->",
        f"- 召回置信度：{retrieval['confidence']}",
        f"- 标签匹配置信度：{retrieval['match_confidence']}",
        f"- 证据完整度：{retrieval['evidence_confidence']}",
    ]
    if retrieval["warning"]:
        lines.append(f"- 警告：{retrieval['warning']}")
    for item in matches:
        matched = ", ".join(item.matched) if item.matched else "source-priority"
        lines.extend(
            [
                "",
                f"## {item.card.card_id}",
                f"- 匹配分：{item.score}",
                f"- 相关层级：{('high' if item.tier == 3 else 'medium' if item.tier == 2 else 'low')}",
                f"- 证据完整度：{item.evidence_level}",
                f"- 证据缺口：{', '.join(item.evidence_gaps) if item.evidence_gaps else '无'}",
                f"- 命中维度：{matched}",
                f"- 对白库文件：{item.card.source_file}",
                item.card.block,
            ]
        )
    for label, key in (("角色核心规则", "core"), ("声纹规律", "voice"), ("情绪关系模式", "modes"), ("反角色规则", "anti")):
        if not rules[key]:
            continue
        lines.extend(["", f"# 命中的{label}"])
        for rule in rules[key]:
            lines.extend(
                [
                    "",
                    f"## {rule['rule_id']}",
                    f"- 命中证据卡：{', '.join(rule['matched_card_ids'])}",
                    str(rule["content"]),
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def json_output(
    matches: Sequence[Match], card_count: int, rules: Dict[str, List[Dict[str, object]]],
    retrieval: Dict[str, object],
) -> str:
    payload = {
        "library_cards": card_count,
        "retrieval": retrieval,
        "selected": [
            {
                "card_id": item.card.card_id,
                "score": item.score,
                "relevance": "high" if item.tier == 3 else ("medium" if item.tier == 2 else "low"),
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
                "interaction_function": item.card.interaction_function,
                "content": item.card.block,
            }
            for item in matches
        ],
        "related_rules": rules,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从 Persona 对白库选择 3–6 张最匹配卡片。")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="角色 Skill 根目录")
    parser.add_argument("--task-state", default="")
    parser.add_argument("--user-state", default="")
    parser.add_argument("--emotion", default="")
    parser.add_argument("--intent", default="")
    parser.add_argument("--speech-act", default="")
    parser.add_argument("--trigger", default="")
    parser.add_argument("--relation", default="")
    parser.add_argument("--risk", default="")
    parser.add_argument("--language", default="", help="输出语言；不用于过滤原语言语料")
    parser.add_argument("--source-language", default="", help="仅在需要时限制原文语言")
    parser.add_argument("--limit", type=int, default=5, choices=range(3, 7), metavar="3..6")
    parser.add_argument("--exclude", action="append", default=[], help="排除编号，可重复或用逗号分隔")
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

    query = {
        "task_state": args.task_state,
        "user_state": args.user_state,
        "emotion": args.emotion,
        "intent": args.intent,
        "speech_act": args.speech_act,
        "trigger": args.trigger,
        "relation": args.relation,
        "risk": args.risk,
        "source_language": args.source_language,
    }
    excluded = parse_excludes(args.exclude)
    matches = [
        match
        for card in cards
        if card.card_id not in excluded
        for match in [score_card(card, query)]
        if match is not None
    ]
    selected = choose_matches(matches, min(args.limit, len(matches)))
    rules = related_rules(root, selected)
    retrieval = retrieval_diagnostics(selected, query)
    if args.format == "json":
        print(json_output(selected, len(cards), rules, retrieval), end="")
    elif args.format == "ids":
        print("\n".join(item.card.card_id for item in selected))
    else:
        print(markdown_output(selected, len(cards), rules, retrieval), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
