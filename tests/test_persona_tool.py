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


def card_text(
    index: int,
    persona_type: str,
    source_id: str,
    scene_count: int,
    signature_count: int,
) -> str:
    card_id = f"TESTROLE-{index:04d}"
    task_states = ("start", "progress", "waiting", "failed", "risk", "complete", "blocked", "issue")
    user_states = ("normal", "tired", "upset", "excited")
    emotions = ("cheerful", "caring", "serious", "alert", "calm", "confident", "apologetic", "teasing")
    intents = ("encourage", "report", "warn", "comfort", "explain", "apologize", "clarify", "celebrate")
    task_state = task_states[(index - 1) % len(task_states)]
    risk = "high" if index % 10 == 0 else "low"
    existing = persona_type in {"existing-character", "real-person-simulation"}
    source_type = "原作明确" if existing else "用户补充"
    card_type = "原文对白" if existing else "原创规范对白"
    scene_number = ((index - 1) % max(scene_count, 1)) + 1
    recognition = "核心" if index <= signature_count else "补充"
    return f"""## {card_id}

- 检索标签：task_state={task_state}; user_state={user_states[(index - 1) % 4]}; emotion={emotions[(index - 1) % 8]}; intent={intents[(index - 1) % 8]}; relation=familiar; risk={risk}; language=zh-CN
- 卡片类型：{card_type}
- 原文：{'原作逐字原句' if existing else '原创规范原句'} {index}
- 原文语言：zh-CN
- 中文参考译文：不适用
- 说话人：测试角色
- 来源类型：{source_type}
- 来源位置：{source_id}，测试定位 {index}
- 作品定位：测试作品第 {scene_number} 场，位置 {index}
- 场景编号：SCENE-{scene_number:04d}
- 前置语境：测试语境 {index}
- 触发话语：测试触发 {index}
- 对话对象：熟悉的同伴
- 关系距离：familiar
- 交流目的：{intents[(index - 1) % 8]}
- 主要情绪：{emotions[(index - 1) % 8]}
- 情绪强度：2
- 口语特征：短句，先回应情绪再行动
- 句式与节奏：回应场景，再说明行动
- 识别度：{recognition}
- 可直接使用：视场景
- 不适用场景：事实未确认时
- 重复限制：最近五轮不重复
"""


def build_fixture(
    target: Path,
    persona_type: str,
    card_count: int,
    scene_count: int = 0,
    signature_count: int = 0,
    research_status: str = "达标",
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
        if persona_type in {"existing-character", "real-person-simulation"}:
            source_id = f"SRC-{((index - 1) % 3) + 1:04d}"
        else:
            source_id = "SRC-0001"
        cards.append(card_text(index, persona_type, source_id, scene_count, signature_count))
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
    if research_status == "已穷尽":
        coverage = """## 调研覆盖记录

- 调研状态：已穷尽
- 初始检索范围：官方角色页与作品页
- 扩大范围记录：继续检查分集资料、访谈、别名和多语言页面
- 检查的站点与资料类型：官方页、剧情页、访谈、对白资料
- 检查的版本、别名与语言：动画与漫画版本、中日英名称
- 各轮新增结果：首轮 12 张，扩大后新增 8 张，此后无新增
- 未达到目标的指标与原因：公开可核查资料总量不足，逐字原文卡与场景覆盖未达目标

### RESEARCH-01 | 初始范围

- 查询词、站点、资料类型与语言：角色名、官方页、中文和日文
- 新增来源与卡片：新增 12 张
- 未覆盖指标：逐字原文卡和原作场景不足

### RESEARCH-02 | 扩大范围

- 查询词、站点、资料类型与语言：别名、英文名、访谈、分集资料和对白
- 新增来源与卡片：新增 8 张，此后无新增
- 未覆盖指标：全网合理可访问资料仍不足
"""
    else:
        coverage = """## 调研覆盖记录

- 调研状态：达标
- 初始检索范围：官方资料与可核查场景
- 扩大范围记录：无（初始范围已达标）
- 检查的站点与资料类型：官方页、剧情页、对白资料
- 检查的版本、别名与语言：主要版本与中日文名称
- 各轮新增结果：首轮达到全部资料目标
- 未达到目标的指标与原因：无

### RESEARCH-01 | 初始范围

- 查询词、站点、资料类型与语言：角色名、官方页、剧情页、中文和日文
- 新增来源与卡片：达到全部资料目标
- 未覆盖指标：无
"""
    write_text(
        target / "references" / "08-来源索引.md",
        "# 测试角色来源索引\n\n" + coverage + "\n" + "\n".join(source_entries),
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
            self.assertEqual(result["metrics"]["exact_original_cards"], 80)
            self.assertEqual(result["metrics"]["distinct_source_scenes"], 40)
            self.assertEqual(result["metrics"]["signature_cards"], 20)
            self.assertEqual(result["metrics"]["derived_cards"], 0)
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
            self.assertTrue(all(item["original_text"] for item in first["selected"]))

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

    def test_existing_character_below_target_requires_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "small-role"
            build_fixture(role, "existing-character", 20, 10, 5)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.too_few", codes)
            self.assertIn("dialogue.exact_original_cards_low", codes)
            self.assertIn("dialogue.source_scenes_low", codes)
            self.assertIn("dialogue.signature_cards_low", codes)

    def test_exhausted_research_releases_all_available_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "exhausted-role"
            build_fixture(role, "existing-character", 20, 10, 5, research_status="已穷尽")
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            self.assertEqual(result["metrics"]["version"], "正式版")
            self.assertEqual(result["metrics"]["research_status"], "已穷尽")
            self.assertEqual(result["metrics"]["coverage_path"], "exhausted")
            warning_codes = {
                issue["code"] for issue in result["issues"] if issue["severity"] == "warning"
            }
            self.assertIn("dialogue.too_few", warning_codes)
            self.assertIn("dialogue.exact_original_cards_low", warning_codes)

    def test_exhausted_status_requires_real_expansion_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "false-exhaustion"
            build_fixture(role, "existing-character", 20, 10, 5, research_status="已穷尽")
            source_path = role / "references" / "08-来源索引.md"
            source_text = source_path.read_text(encoding="utf-8")
            write_text(
                source_path,
                source_text.replace(
                    "- 扩大范围记录：继续检查分集资料、访谈、别名和多语言页面",
                    "- 扩大范围记录：无",
                ),
            )
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("research.exhaustion_incomplete", codes)

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
            self.assertIn("dialogue.exact_original_cards_low", codes)

    def test_existing_character_rejects_missing_original_and_work_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "fake-original"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 原文：原作逐字原句 1", "- 原文：无", 1)
            text = text.replace(
                "- 重复限制：最近五轮不重复",
                "- 工作改写示例：测试角色：这是预写的工作话术\n- 重复限制：最近五轮不重复",
                1,
            )
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.original_text_missing", codes)
            self.assertIn("dialogue.prewritten_rewrite_forbidden", codes)

    def test_existing_character_rejects_non_original_and_duplicate_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "derived-dialogue"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("- 卡片类型：原文对白", "- 卡片类型：原创规范对白", 1)
            text = text.replace("- 原文：原作逐字原句 3", "- 原文：原作逐字原句 2", 1)
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.non_original_card", codes)
            self.assertIn("dialogue.duplicate_original_text", codes)

    def test_original_persona_can_release_with_twenty_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "original-role"
            build_fixture(role, "original-persona", 20)
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])

    def test_creator_enforces_name_gate_prefix_and_formal_only_delivery(self) -> None:
        creator = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("第一条回复只能显示下面的二选一提示", creator)
        self.assertIn("在收到 `1` 或 `2 + 自定义名称` 前", creator)
        self.assertIn("创建过程中的所有 Agent 自然语言消息都必须以 `<角色名>：` 开头", creator)
        self.assertIn("最终版本始终为正式版", creator)
        self.assertIn("不按版权类别、文本长度或资料完整度限制收集", creator)
        self.assertIn("对白库禁止加入官方角色介绍", creator)
        self.assertIn("逐字原文卡", creator)
        self.assertNotIn("官方角色原文", persona_tool.EXACT_CARD_TYPES)
        self.assertNotIn("试用版", creator)


if __name__ == "__main__":
    unittest.main()
