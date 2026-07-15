#!/usr/bin/env python3
"""Mechanically migrate a generated Persona role from asset v1 to v2.

This command only adds explicit schema fields and synchronizes the generic
runtime assets.  It deliberately does not invent character psychology.  The
generated ``11-心理机制与表达策略.md`` remains a template until the author
re-distils evidence-backed MIND/EXPR rules and passes ``persona_tool validate``.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Match


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE_ROOT = REPO_ROOT / "assets" / "角色人格模板"
CARD_HEADING_RE = re.compile(r"^##\s+([A-Z0-9][A-Z0-9-]*-\d{4})\s*$", re.MULTILINE)
SOURCE_HEADING_RE = re.compile(r"^##\s+(SRC-\d{4})\s*$", re.MULTILINE)
BIO_HEADING_RE = re.compile(r"^###\s+(BIO-\d{2})\s+\|", re.MULTILINE)
FRONTMATTER_NAME_RE = re.compile(r"^name:\s*([^\s]+)\s*$", re.MULTILINE)


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, str(path))
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    os.close(fd)
    try:
        shutil.copyfile(str(source), temporary)
        os.replace(temporary, str(target))
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def field_value(block: str, field: str) -> str:
    match = re.search(rf"^-\s*{re.escape(field)}：\s*(.*?)\s*$", block, re.MULTILINE)
    return match.group(1).strip() if match else ""


def append_fields(block: str, values: list[tuple[str, str]]) -> str:
    additions = [(field, value) for field, value in values if not field_value(block, field)]
    if not additions:
        return block
    newline = "\r\n" if "\r\n" in block else "\n"
    body = block.rstrip("\r\n")
    body += newline + newline.join(f"- {field}：{value}" for field, value in additions)
    return body + newline + newline


def transform_blocks(text: str, heading_re: re.Pattern[str], transform: Callable[[str], str]) -> str:
    matches = list(heading_re.finditer(text))
    if not matches:
        return text
    pieces = [text[: matches[0].start()]]
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        pieces.append(transform(text[match.start() : end]))
    return "".join(pieces)


def migrate_cards(text: str) -> str:
    def transform(block: str) -> str:
        card_type = field_value(block, "卡片类型")
        quote_use = "exact-quote" if card_type in {"原文对白", "原文叙事", "逐字稿"} else "paraphrase"
        main_emotion = field_value(block, "主要情绪") or "未知（旧卡未标注）"
        purpose = field_value(block, "交流目的") or "未知（旧卡未标注）"
        grammar = field_value(block, "语法标记") or field_value(block, "口语现象")
        rhetoric = grammar or "未知（旧卡未单独标注修辞）"
        outcome = (
            "相邻原文已保留；场景结果未在旧卡中单独归纳"
            if field_value(block, "后续原文")
            else "未知（旧卡未保存场景结果）"
        )
        return append_fields(
            block,
            [
                ("版本层", "primary"),
                ("引用方式", quote_use),
                ("表面情绪", f"{main_emotion}（沿用旧卡可观察标注）"),
                ("内在情绪", "未知（原文没有直接证实，禁止用模型印象补写）"),
                ("当前目的", purpose),
                ("担心的损失", "未知（旧卡未保存直接证据）"),
                ("隐藏内容", "未知（旧卡未保存直接证据）"),
                ("场景结果", outcome),
                ("修辞手段", rhetoric),
            ],
        )

    return transform_blocks(text, CARD_HEADING_RE, transform)


def migrate_sources(text: str) -> str:
    return transform_blocks(
        text,
        SOURCE_HEADING_RE,
        lambda block: append_fields(block, [("版本层", "primary")]),
    )


def migrate_biography(text: str) -> str:
    def transform(block: str) -> str:
        viewpoint = field_value(block, "角色视角回答要点")
        triggers = field_value(block, "适用问题")
        return append_fields(
            block,
            [
                ("主观解释", viewpoint or "未知（旧档案没有保存角色的主观解释）"),
                ("情绪印记", "未知（旧档案没有直接证据，待重蒸馏）"),
                ("联想触发", triggers or "仅在当前话题直接相关时回调"),
                ("可迁移意象", "未知（待根据角色证据补充，不用模型印象代填）"),
                ("愿谈程度", "被问及或当前工作概念直接命中时自然提起；不反复自述"),
            ],
        )

    return transform_blocks(text, BIO_HEADING_RE, transform)


def role_metadata(role_root: Path) -> tuple[str, str]:
    skill_text = read_text(role_root / "SKILL.md")
    name_match = FRONTMATTER_NAME_RE.search(skill_text)
    if not name_match:
        raise ValueError("SKILL.md frontmatter 缺少 name")
    core_text = read_text(role_root / "references" / "01-角色核心.md")
    display_name = field_value(core_text, "当前角色显示名")
    if not display_name:
        raise ValueError("01-角色核心.md 缺少当前角色显示名")
    return name_match.group(1), display_name


def migrate_core(path: Path) -> None:
    text = read_text(path)
    if re.search(r"^-\s*人格资产版本：", text, re.MULTILINE):
        text = re.sub(r"^-\s*人格资产版本：.*$", "- 人格资产版本：2", text, count=1, flags=re.MULTILINE)
    else:
        version_match = re.search(r"^-\s*版本：.*$", text, re.MULTILINE)
        if not version_match:
            raise ValueError("01-角色核心.md 缺少版本字段")
        newline = "\r\n" if "\r\n" in text else "\n"
        text = text[: version_match.end()] + newline + "- 人格资产版本：2" + text[version_match.end() :]
    atomic_write(path, text)


def sync_runtime_assets(role_root: Path, template_root: Path, role_id: str, display_name: str) -> None:
    template_skill = read_text(template_root / "SKILL.md")
    role_slug = role_id[8:] if role_id.startswith("persona-") else role_id
    card_prefix = re.sub(r"[^A-Z0-9]", "", role_slug.upper())[:12] or "ROLE"
    core_text = read_text(role_root / "references" / "01-角色核心.md")
    original_language = field_value(core_text, "作品原始语言") or "any"
    rendered_skill = (
        template_skill
        .replace("{{PERSONA_SKILL_ID}}", role_id)
        .replace("{{PERSONA_NAME}}", display_name)
        .replace("{{CARD_PREFIX}}", card_prefix)
        .replace("[原始语言]", original_language)
    )
    atomic_write(role_root / "SKILL.md", rendered_skill)
    for name in ("select_dialogues.py", "check_response.py"):
        atomic_copy(template_root / "scripts" / name, role_root / "scripts" / name)


def migrate(role_root: Path, template_root: Path, sync_assets: bool, create_strategy: bool) -> dict[str, object]:
    required = [
        role_root / "SKILL.md",
        role_root / "references" / "01-角色核心.md",
        role_root / "references" / "06-对白库.md",
        role_root / "references" / "08-来源索引.md",
        role_root / "references" / "10-人物背景档案.md",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("缺少迁移所需文件：" + ", ".join(missing))

    role_id, display_name = role_metadata(role_root)
    migrate_core(role_root / "references" / "01-角色核心.md")
    for relative, transform in (
        (Path("references") / "06-对白库.md", migrate_cards),
        (Path("references") / "08-来源索引.md", migrate_sources),
        (Path("references") / "10-人物背景档案.md", migrate_biography),
    ):
        path = role_root / relative
        atomic_write(path, transform(read_text(path)))

    if create_strategy:
        target = role_root / "references" / "11-心理机制与表达策略.md"
        if not target.exists():
            template = read_text(template_root / "references" / "11-心理机制与表达策略.md")
            atomic_write(target, template.replace("{{PERSONA_NAME}}", display_name))
    if sync_assets:
        sync_runtime_assets(role_root, template_root, role_id, display_name)

    return {"role_id": role_id, "display_name": display_name, "asset_version": 2}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将生成的人格 Skill 机械迁移到人物表达资产 v2")
    parser.add_argument("role_root", type=Path, help="生成角色 Skill 的根目录")
    parser.add_argument("--template-root", type=Path, default=DEFAULT_TEMPLATE_ROOT)
    parser.add_argument("--no-sync-runtime-assets", action="store_true")
    parser.add_argument("--no-create-strategy", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = migrate(
        args.role_root.resolve(),
        args.template_root.resolve(),
        not args.no_sync_runtime_assets,
        not args.no_create_strategy,
    )
    print(
        f"MIGRATED role_id={result['role_id']} display_name={result['display_name']} "
        f"asset_version={result['asset_version']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
