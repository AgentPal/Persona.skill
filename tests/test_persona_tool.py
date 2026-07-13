from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import persona_tool  # noqa: E402


TOKEN_RE = re.compile(r"\[待填写[^\]]*\]")
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".txt", ".json"}


def write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def card_text(index: int, source_type: str, source_id: str, with_short_line: bool) -> str:
    card_id = f"TESTROLE-{index:04d}"
    task_states = ("start", "progress", "waiting", "failed", "risk", "complete", "blocked", "issue")
    user_states = ("normal", "tired", "upset", "excited")
    emotions = ("cheerful", "caring", "serious", "alert", "calm", "confident", "apologetic", "teasing")
    intents = ("encourage", "report", "warn", "comfort", "explain", "apologize", "clarify", "celebrate")
    task_state = task_states[(index - 1) % len(task_states)]
    risk = "high" if index % 10 == 0 else "low"
    short_line = f"经典短句 {index}" if with_short_line else "无"
    return f"""## {card_id}

- 检索标签：task_state={task_state}; user_state={user_states[(index - 1) % 4]}; emotion={emotions[(index - 1) % 8]}; intent={intents[(index - 1) % 8]}; relation=familiar; risk={risk}; language=zh-CN
- 来源类型：{source_type}
- 来源位置：{source_id}，测试定位 {index}
- 原场景：测试场景 {index}
- 对话对象：熟悉的同伴
- 关系距离：familiar
- 交流目的：{intents[(index - 1) % 8]}
- 主要情绪：{emotions[(index - 1) % 8]}
- 情绪强度：2
- 语言特征：短句，先回应情绪再行动
- 代表性短句：{short_line}
- 表达结构：回应场景，再说明行动
- 适用工作场景：{task_state}
- 迁移方式：修改后使用
- 工作改写示例：角色名：测试改写 {index}
- 不适用场景：事实未确认时
- 重复限制：最近五轮不重复
"""


def build_fixture(
    target: Path,
    persona_type: str,
    card_count: int,
    original_count: int = 0,
    original_short_lines: int = 0,
) -> None:
    shutil.copytree(ROOT / "assets" / "角色人格模板", target)
    replacements = {
        "{{PERSONA_NAME}}": "测试角色",
        "{{PERSONA_SLUG}}": "test-role",
        "{{CARD_PREFIX}}": "TESTROLE",
    }
    for path in target.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8-sig")
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"- 人格来源类型：\[待填写[^\]]*\]", f"- 人格来源类型：{persona_type}", text)
        text = TOKEN_RE.sub("已填写", text)
        write_text(path, text)

    cards = []
    index_rows = []
    for index in range(1, card_count + 1):
        is_original = index <= original_count
        source_type = "原作明确" if is_original else "合理推导"
        if is_original:
            source_id = f"SRC-{((index - 1) % 3) + 1:04d}"
        else:
            source_id = "SRC-0004" if persona_type == "existing-character" else "SRC-0001"
        cards.append(card_text(index, source_type, source_id, index <= original_short_lines))
        index_rows.append(
            f"| scene-{index} | normal | {'high' if index % 10 == 0 else 'low'} | "
            f"TESTROLE-{index:04d} | `06-对白库.md` | test |"
        )
    write_text(target / "references" / "06-对白库.md", "# 测试角色对白库\n\n" + "\n".join(cards))
    write_text(
        target / "references" / "05-对白索引.md",
        "# 测试角色对白索引\n\n| 场景 | 用户 | 风险 | 卡片编号 | 文件 | 备注 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(index_rows)
        + "\n",
    )

    if persona_type == "existing-character":
        source_types = ("原作明确", "原作明确", "原作明确", "公开资料", "合理推导")
    else:
        source_types = ("用户补充",)
    source_entries = []
    for index, source_type in enumerate(source_types, start=1):
        source_entries.append(
            f"""## SRC-{index:04d}

- 来源类型：{source_type}
- 位置：测试来源 {index}
- 可用范围：仅测试
- 内容摘要：测试摘要
- 可靠性：已核对
- 支持的结论或卡片：TESTROLE-{index:04d}
"""
        )
    write_text(
        target / "references" / "08-来源索引.md",
        "# 测试角色来源索引\n\n" + "\n".join(source_entries),
    )


class PersonaToolTests(unittest.TestCase):
    def test_init_copies_selector_and_draft_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "new-role"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "persona_tool.py"),
                    "init",
                    "--name",
                    "新角色",
                    "--slug",
                    "new-role",
                    "--output",
                    str(role),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((role / "scripts" / "select_dialogues.py").is_file())
            draft = persona_tool.validate_skill(role, "draft")
            self.assertTrue(draft["valid"], draft["issues"])

    def test_existing_character_release_and_selector(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "test-role"
            build_fixture(role, "existing-character", 80, 40, 20)

            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["cards"], 80)
            self.assertEqual(result["metrics"]["original_cards"], 40)
            self.assertEqual(result["metrics"]["original_dialogue_cards"], 20)
            self.assertEqual(result["metrics"]["original_sources"], 3)

            selector = role / "scripts" / "select_dialogues.py"
            command = [
                sys.executable,
                str(selector),
                "--root",
                str(role),
                "--task-state",
                "failed",
                "--user-state",
                "tired",
                "--emotion",
                "caring",
                "--intent",
                "encourage",
                "--risk",
                "low",
                "--language",
                "zh-CN",
                "--format",
                "json",
            ]
            first = json.loads(subprocess.check_output(command, text=True, encoding="utf-8"))
            self.assertEqual(first["library_cards"], 80)
            self.assertEqual(len(first["selected"]), 5)
            self.assertLess(len(first["selected"]), first["library_cards"])

            excluded = first["selected"][0]["card_id"]
            second = json.loads(
                subprocess.check_output(command + ["--exclude", excluded], text=True, encoding="utf-8")
            )
            self.assertNotIn(excluded, {item["card_id"] for item in second["selected"]})

            high_risk = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(selector),
                        "--root",
                        str(role),
                        "--risk",
                        "high",
                        "--language",
                        "zh-CN",
                        "--format",
                        "json",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertGreaterEqual(len(high_risk["selected"]), 3)
            self.assertTrue(all("risk=high" in item["content"] for item in high_risk["selected"]))

    def test_existing_character_with_twenty_cards_is_not_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "small-role"
            build_fixture(role, "existing-character", 20, 10, 5)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.too_few", codes)
            self.assertIn("dialogue.original_cards_low", codes)
            self.assertIn("dialogue.original_quotes_low", codes)

    def test_original_cards_must_reference_original_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "source-mismatch"
            build_fixture(role, "existing-character", 80, 40, 20)
            source_path = role / "references" / "08-来源索引.md"
            source_text = source_path.read_text(encoding="utf-8")
            write_text(source_path, source_text.replace("- 来源类型：原作明确", "- 来源类型：公开资料", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.original_source_mismatch", codes)
            self.assertIn("dialogue.original_cards_low", codes)

    def test_original_persona_can_release_with_twenty_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "original-role"
            build_fixture(role, "original-persona", 20)
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])


if __name__ == "__main__":
    unittest.main()
