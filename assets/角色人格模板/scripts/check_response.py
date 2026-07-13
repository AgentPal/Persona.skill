#!/usr/bin/env python3
"""Detect generic assistant, project-manager, and AI-written tone in persona replies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Sequence


ANTI_HEADING_RE = re.compile(r"^###\s+(ANTI-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)
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


def visible_prose(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"^\s*[^\n：:]{1,24}[：:]\s*", "", text)
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


def analyze(text: str, root: Path) -> dict[str, object]:
    prose = visible_prose(text)
    findings: list[dict[str, object]] = []

    opening = next((item for item in GENERIC_OPENINGS if prose.startswith(item)), "")
    if opening:
        add_finding(findings, "generic_opening", 15, opening)

    ai_hits = [item for item in AI_PHRASES if item in prose]
    if ai_hits:
        add_finding(findings, "ai_written_connectors", min(30, 12 * len(ai_hits)), " / ".join(ai_hits))

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
    if len(lengths) >= 3 and average_length >= 30 and not oral_hits and short_sentences == 0:
        add_finding(findings, "uniform_written_sentences", 20, f"平均句长 {average_length}，没有可见口语断点")

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
        "status": status,
        "ai_tone_score": score,
        "prose_length": len(prose),
        "average_sentence_length": average_length,
        "short_sentence_count": short_sentences,
        "oral_markers": oral_hits,
        "findings": findings,
        "anti_rule_hits": anti_hits,
        "note": "分数只检测通用/书面腔风险；角色是否真实仍需原文证据和去名盲测。",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查人格回复中的项目经理腔、AI 书面腔和反角色模式。")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="角色 Skill 根目录")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text", default="", help="要检查的回复文本")
    source.add_argument("--file", help="从 UTF-8 文件读取回复文本")
    parser.add_argument("--strict", action="store_true", help="review 或 fail 时返回非零退出码")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
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
