#!/usr/bin/env python3
"""Mechanically scaffold Persona asset v3 without inventing character behavior.

The command upgrades v1 through the existing v2 structural migration, adds the
BEHAV template, synchronizes runtime scripts, and marks the role as v3.  The
result is intentionally incomplete until evidence-backed BEHAV rules and a new
Persona Quality Loop v3 run pass release validation.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional, Sequence

import migrate_asset_v2 as v2


def asset_version(core_text: str) -> int:
    raw = v2.field_value(core_text, "人格资产版本")
    return int(raw) if raw.isdigit() else 1


def set_asset_version(path: Path, version: int) -> None:
    text = v2.read_text(path)
    if re.search(r"^-\s*人格资产版本：", text, re.MULTILINE):
        text = re.sub(
            r"^-\s*人格资产版本：.*$", f"- 人格资产版本：{version}", text,
            count=1, flags=re.MULTILINE,
        )
    else:
        version_match = re.search(r"^-\s*版本：.*$", text, re.MULTILINE)
        if not version_match:
            raise ValueError("01-角色核心.md 缺少版本字段")
        newline = "\r\n" if "\r\n" in text else "\n"
        text = text[:version_match.end()] + newline + f"- 人格资产版本：{version}" + text[version_match.end():]
    v2.atomic_write(path, text)


def migrate(role_root: Path, template_root: Path, sync_assets: bool = True) -> dict[str, object]:
    role_root = role_root.resolve()
    template_root = template_root.resolve()
    core_path = role_root / "references" / "01-角色核心.md"
    if not core_path.is_file():
        raise FileNotFoundError(f"缺少迁移所需文件：{core_path}")
    current = asset_version(v2.read_text(core_path))
    if current < 2:
        v2.migrate(role_root, template_root, sync_assets=False, create_strategy=True)
    role_id, display_name = v2.role_metadata(role_root)
    behavior_target = role_root / "references" / "12-行为辨识模型.md"
    if not behavior_target.exists():
        template = v2.read_text(template_root / "references" / "12-行为辨识模型.md")
        v2.atomic_write(behavior_target, template.replace("{{PERSONA_NAME}}", display_name))
    set_asset_version(core_path, 3)
    if sync_assets:
        v2.sync_runtime_assets(role_root, template_root, role_id, display_name)
    return {
        "role_id": role_id,
        "display_name": display_name,
        "previous_asset_version": current,
        "asset_version": 3,
        "migration_state": "INCOMPLETE",
        "next_action": "按原始证据重蒸馏至少 12 条 BEHAV，覆盖全部行为功能，然后运行 quality-init/record/evaluate；禁止把模板骨架当作通过。",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将生成的人格 Skill 机械迁移到人物表达资产 v3 骨架")
    parser.add_argument("role_root", type=Path)
    parser.add_argument("--template-root", type=Path, default=v2.DEFAULT_TEMPLATE_ROOT)
    parser.add_argument("--no-sync-runtime-assets", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    result = migrate(
        args.role_root.resolve(), args.template_root.resolve(), not args.no_sync_runtime_assets,
    )
    print(
        f"MIGRATED role_id={result['role_id']} display_name={result['display_name']} "
        f"previous_asset_version={result['previous_asset_version']} asset_version=3"
    )
    print("MIGRATION_STATE=INCOMPLETE")
    print("MUST_CONTINUE=true")
    print("CREATE_LOOP_LOCK=active")
    print(f"NEXT_ACTION={result['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
