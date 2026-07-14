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


CHECKER_CONTRACT_VERSION = 2
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


def analyze(text: str, root: Path) -> dict[str, object]:
    prose = visible_prose(text)
    findings: list[dict[str, object]] = []

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
    if len(consulting_hits) >= 2 or (consulting_hits and WORKFLOW_FRAME_RE.search(prose)):
        add_finding(findings, "generic_consulting_frame", 45, " / ".join(consulting_hits))
    elif consulting_hits:
        add_finding(findings, "generic_consulting_tendency", 14, consulting_hits[0])

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
        "checker_contract_version": CHECKER_CONTRACT_VERSION,
        "status": status,
        "ai_tone_score": score,
        "prose_length": len(prose),
        "average_sentence_length": average_length,
        "short_sentence_count": short_sentences,
        "oral_markers": oral_hits,
        "findings": findings,
        "anti_rule_hits": anti_hits,
        "note": "分数检测通用/书面腔与伪人类化风险；自然口语、临场画面和主动表达是否属于角色仍需原文证据、冷却记录和去名盲测。",
    }


def analyze_batch(texts: Sequence[str], root: Path) -> dict[str, object]:
    results = [analyze(text, root) for text in texts]
    prose_items = [visible_prose(text) for text in texts]
    workflow_indices = [index for index, prose in enumerate(prose_items) if WORKFLOW_FRAME_RE.search(prose)]
    we_indices = [index for index, prose in enumerate(prose_items) if "我们" in prose]
    openings = [re.sub(r"[^\w\u4e00-\u9fff]+", "", prose)[:4] for prose in prose_items if prose]
    repeated_openings = {opening: count for opening, count in Counter(openings).items() if opening and count >= 2}
    prose_lengths = [len(prose) for prose in prose_items if prose]
    sentence_counts = [len(sentence_lengths(prose)) for prose in prose_items if prose]
    question_end_indices = [index for index, prose in enumerate(prose_items) if QUESTION_END_RE.search(prose)]

    def response_shape(prose: str) -> str:
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

    shapes = [response_shape(prose) for prose in prose_items if prose]
    shape_counts = Counter(shapes)
    repeated_shapes = {
        shape: count for shape, count in shape_counts.items()
        if shape != "other" and count >= max(3, (len(shapes) + 1) // 2)
    }
    findings: list[dict[str, object]] = []
    required_repetition = max(3, (len(texts) + 1) // 2)
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
    score = min(100, sum(int(item["weight"]) for item in findings))
    status = "pass" if score < 40 else ("review" if score < 60 else "fail")
    return {
        "checker_contract_version": CHECKER_CONTRACT_VERSION,
        "status": status,
        "ai_tone_score": score,
        "sample_count": len(texts),
        "workflow_skeleton_count": len(workflow_indices),
        "collective_assistant_voice_count": len(we_indices),
        "repeated_openings": repeated_openings,
        "repeated_shapes": repeated_shapes,
        "question_closure_count": len(question_end_indices),
        "response_length_range": [min(prose_lengths), max(prose_lengths)] if prose_lengths else [],
        "sentence_counts": sentence_counts,
        "findings": findings,
        "responses": results,
        "note": "批量检查用于发现单条看似自然、合起来却反复使用同一开发助手骨架的退化。",
    }


def read_batch(path: Path) -> list[str]:
    payload = json.loads(read_text(path))
    if not isinstance(payload, list):
        raise SystemExit("错误：批量文件必须是 JSON 数组")
    result: list[str] = []
    for item in payload:
        if isinstance(item, str):
            value = item
        elif isinstance(item, dict):
            value = str(item.get("response") or item.get("text") or "")
        else:
            value = ""
        if value.strip():
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
