#!/usr/bin/env python3
"""Select a small, relevant set of dialogue cards from a Persona skill."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


CARD_HEADING_RE = re.compile(
    r"^##\s+([A-Z0-9][A-Z0-9-]*-\d{4})\s*$", re.MULTILINE | re.IGNORECASE
)
TAG_RE = re.compile(r"\b([a-z_]+)\s*=\s*([^;；]+)", re.IGNORECASE)
WEIGHTS = {
    "task_state": 8,
    "intent": 7,
    "risk": 6,
    "user_state": 4,
    "emotion": 4,
    "relation": 3,
    "language": 2,
}
HIGH_RISKS = {"high", "critical", "danger", "severe"}
LOW_RISKS = {"none", "low"}
EMPTY_SHORT_LINES = {"", "无", "none", "n/a", "不适用"}


@dataclass(frozen=True)
class Card:
    card_id: str
    source_file: str
    block: str
    tags: Dict[str, Set[str]]
    source_type: str
    short_line: str


@dataclass(frozen=True)
class Match:
    card: Card
    score: int
    matched: Tuple[str, ...]


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


def iter_card_blocks(text: str) -> Iterable[Tuple[str, str]]:
    matches = list(CARD_HEADING_RE.finditer(text))
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
                    short_line=field_value(block, "代表性短句"),
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


def score_card(card: Card, query: Dict[str, str]) -> Optional[Match]:
    language = query.get("language", "")
    risk = query.get("risk", "")
    if not language_matches(language, card.tags.get("language", set())):
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
        if key == "language":
            is_match = language_matches(wanted, values)
        else:
            is_match = wanted in values or "any" in values or "all" in values
        if is_match:
            score += weight
            matched.append(key)

    if card.source_type == "原作明确":
        score += 1
    if card.short_line.strip().lower() not in EMPTY_SHORT_LINES:
        score += 1
    return Match(card=card, score=score, matched=tuple(matched))


def choose_matches(matches: Sequence[Match], limit: int) -> List[Match]:
    ranked = sorted(matches, key=lambda item: (-item.score, item.card.card_id))
    if limit < 2:
        return ranked[:limit]

    chosen: List[Match] = []
    competitive = [item for item in ranked if item.score >= ranked[0].score - 8] if ranked else []
    original = next((item for item in competitive if item.card.source_type == "原作明确"), None)
    derived = next((item for item in competitive if item.card.source_type != "原作明确"), None)
    for candidate in (original, derived):
        if candidate is not None and candidate not in chosen:
            chosen.append(candidate)
    for candidate in ranked:
        if candidate not in chosen:
            chosen.append(candidate)
        if len(chosen) >= limit:
            break
    return sorted(chosen[:limit], key=lambda item: (-item.score, item.card.card_id))


def parse_excludes(values: Sequence[str]) -> Set[str]:
    result: Set[str] = set()
    for value in values:
        result.update(item.strip().upper() for item in re.split(r"[,，;；\s]+", value) if item.strip())
    return result


def markdown_output(matches: Sequence[Match], card_count: int) -> str:
    lines = [f"<!-- selected={len(matches)} library_cards={card_count} -->"]
    for item in matches:
        matched = ", ".join(item.matched) if item.matched else "source-priority"
        lines.extend(
            [
                "",
                f"## {item.card.card_id}",
                f"- 匹配分：{item.score}",
                f"- 命中维度：{matched}",
                f"- 对白库文件：{item.card.source_file}",
                item.card.block,
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def json_output(matches: Sequence[Match], card_count: int) -> str:
    payload = {
        "library_cards": card_count,
        "selected": [
            {
                "card_id": item.card.card_id,
                "score": item.score,
                "matched": list(item.matched),
                "source_file": item.card.source_file,
                "source_type": item.card.source_type,
                "content": item.card.block,
            }
            for item in matches
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从 Persona 对白库选择 3–6 张最匹配卡片。")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="角色 Skill 根目录")
    parser.add_argument("--task-state", default="")
    parser.add_argument("--user-state", default="")
    parser.add_argument("--emotion", default="")
    parser.add_argument("--intent", default="")
    parser.add_argument("--relation", default="")
    parser.add_argument("--risk", default="")
    parser.add_argument("--language", default="")
    parser.add_argument("--limit", type=int, default=5, choices=range(3, 7), metavar="3..6")
    parser.add_argument("--exclude", action="append", default=[], help="排除编号，可重复或用逗号分隔")
    parser.add_argument("--format", choices=("markdown", "json", "ids"), default="markdown")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
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
        "relation": args.relation,
        "risk": args.risk,
        "language": args.language,
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
    if args.format == "json":
        print(json_output(selected, len(cards)), end="")
    elif args.format == "ids":
        print("\n".join(item.card.card_id for item in selected))
    else:
        print(markdown_output(selected, len(cards)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
