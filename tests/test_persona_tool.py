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
    original_quality = "原声核验" if existing else "原创确认"
    scene_number = ((index - 1) % max(scene_count, 1)) + 1
    recognition = "核心" if index <= signature_count else "补充"
    return f"""## {card_id}

- 检索标签：task_state={task_state}; user_state={user_states[(index - 1) % 4]}; emotion={emotions[(index - 1) % 8]}; intent={intents[(index - 1) % 8]}; relation=familiar; risk={risk}; language=zh-CN; speech_act={intents[(index - 1) % 8]}; trigger={task_state}
- 卡片类型：{card_type}
- 原文：{'原作逐字原句' if existing else '原创规范原句'} {index}
- 原文语言：zh-CN
- 原文质量：{original_quality}
- 中文参考译文：不适用
- 说话人：测试角色
- 来源类型：{source_type}
- 来源位置：{source_id}，测试定位 {index}
- 作品定位：测试作品第 {scene_number} 场，位置 {index}
- 场景编号：SCENE-{scene_number:04d}
- 前置原文：前一句测试原文 {index}
- 触发话语：测试触发 {index}
- 后续原文：后一句测试原文 {index}
- 对话对象：熟悉的同伴
- 关系距离：familiar
- 交流目的：{intents[(index - 1) % 8]}
- 互动功能：{intents[(index - 1) % 8]}-{index}
- 主要情绪：{emotions[(index - 1) % 8]}
- 情绪强度：2
- 情绪转折：情绪变化 {index}
- 非语言反应：动作观察 {index}
- 语音表现：原声语速重音观察 {index}
- 词汇标记：词汇标记 {index}
- 语法标记：语法标记 {index}
- 语气标记：语气标记 {index}
- 句式与节奏：句式节奏观察 {index}
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
        text = re.sub(
            r"- 原作媒介：\[待填写[^\]]*\]",
            f"- 原作媒介：{'原创' if persona_type in {'original-persona', 'composite-original'} else '视听'}",
            text,
        )
        text = re.sub(r"- 作品原始语言：\[待填写[^\]]*\]", "- 作品原始语言：zh-CN", text)
        text = TOKEN_RE.sub("已填写", text)
        write_text(path, text)

    cases_path = target / "references" / "07-验证用例.md"
    cases_text = cases_path.read_text(encoding="utf-8")
    fidelity_cases = {
        "CASE-18": """## CASE-18 | 去名盲测

- 样本数：12
- 正确识别数：10
- 评估记录：测试盲测记录
- 验证状态：通过
""",
        "CASE-19": """## CASE-19 | 相似角色与通用助手区分

- 样本数：10
- 正确区分数：8
- 对照对象：通用助手和相似角色
- 区分证据：CORE、VOICE 与原文卡映射
- 验证状态：通过
""",
        "CASE-20": """## CASE-20 | 原文与声纹证据追溯

- 抽查数：6
- 可追溯数：6
- 召回相关数：5
- 追溯记录：六个测试场景的完整映射
- 验证状态：通过
""",
    }
    for case_id, replacement in fidelity_cases.items():
        cases_text = re.sub(
            rf"^## {case_id}\s+\|.*?(?=^## CASE-|\Z)",
            replacement + "\n",
            cases_text,
            flags=re.MULTILINE | re.DOTALL,
        )
    write_text(cases_path, cases_text.rstrip() + "\n")

    cards = []
    index_rows = []
    for index in range(1, card_count + 1):
        if persona_type in {"existing-character", "real-person-simulation"}:
            source_id = f"SRC-{((index - 1) % 3) + 1:04d}"
        else:
            source_id = "SRC-0001"
        cards.append(card_text(index, persona_type, source_id, scene_count or card_count, signature_count))
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

    evidence_count = max(card_count, 1)
    core_count = 12 if persona_type in {"existing-character", "real-person-simulation"} else 8
    core_layers = (
        "value", "judgment", "desire", "bias", "boundary", "behavior", "relationship",
        "emotion", "identity", "anti-core", "value", "judgment",
    )
    core_entries = []
    for index in range(1, core_count + 1):
        first = ((index - 1) * 2 % evidence_count) + 1
        second = (first % evidence_count) + 1
        core_entries.append(
            f"""### CORE-{index:02d} | 测试核心 {index}

- 层级：{core_layers[index - 1]}
- 结论：可观察角色结论 {index}
- 可观察行为：行为证据 {index}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 其他来源：SRC-0001
- 反证或边界：核心边界 {index}
- 适用条件：核心条件 {index}
- 置信度：高
"""
        )
    core_path = target / "references" / "01-角色核心.md"
    core_text = core_path.read_text(encoding="utf-8")
    core_text = re.sub(r"### CORE-01\s+\|.*?(?=\n## 与用户的关系)", "", core_text, flags=re.DOTALL)
    write_text(core_path, core_text + "\n" + "\n".join(core_entries))

    voice_count = 12 if persona_type in {"existing-character", "real-person-simulation"} else 8
    voice_layers = (
        "lexicon", "syntax", "ending", "prosody", "interaction", "emotion", "relation",
        "translation", "anti-voice", "lexicon", "syntax", "interaction",
    )
    voice_entries = []
    for index in range(1, voice_count + 1):
        first = ((index - 1) * 2 % evidence_count) + 1
        second = (first % evidence_count) + 1
        voice_entries.append(
            f"""### VOICE-{index:02d} | 测试声纹 {index}

- 层级：{voice_layers[index - 1]}
- 规律：从两处原文观察得到的声纹规律 {index}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 反证或边界：边界观察 {index}
- 适用条件：条件 {index}
- 置信度：高
"""
        )
    write_text(target / "references" / "02-语言声纹.md", "# 测试角色语言声纹\n\n" + "\n".join(voice_entries))

    mode_count = 12 if persona_type in {"existing-character", "real-person-simulation"} else 8
    mode_emotions = ("cheerful", "caring", "serious", "alert", "calm", "confident", "apologetic", "teasing")
    mode_entries = []
    for index in range(1, mode_count + 1):
        first = ((index - 1) * 2 % evidence_count) + 1
        second = (first % evidence_count) + 1
        mode_entries.append(
            f"""### MODE-{index:02d} | 测试模式 {index}

- 情绪：{mode_emotions[(index - 1) % len(mode_emotions)]}
- 触发：触发条件 {index}
- 关系：关系条件 {index}
- 角色即时反应：即时反应 {index}
- 语言变化：语言变化 {index}
- 行动倾向：行动倾向 {index}
- 证据卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 反证或边界：模式边界 {index}
"""
        )
    write_text(target / "references" / "03-情绪与关系.md", "# 测试角色情绪与关系\n\n" + "\n".join(mode_entries))

    scene_entries = []
    for index, scene_id in enumerate(sorted(persona_tool.REQUIRED_SCENES), start=1):
        first = ((index - 1) * 2 % evidence_count) + 1
        second = (first % evidence_count) + 1
        voice_id = ((index - 1) % voice_count) + 1
        scene_entries.append(
            f"""## {scene_id} | 测试场景

- 触发：场景触发 {index}
- 原作互动功能：原作功能 {index}
- 角色即时反应：角色反应 {index}
- 候选原文卡：TESTROLE-{first:04d}、TESTROLE-{second:04d}
- 候选声纹规律：VOICE-{voice_id:02d}
- 事实嵌入方式：事实嵌入 {index}
- 禁止退化：禁止通用助手表达 {index}
"""
        )
    write_text(target / "references" / "04-工作场景迁移.md", "# 测试角色场景迁移\n\n" + "\n".join(scene_entries))

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
- 原始媒介与版本：测试原声版本 {index}
- 原始语言：zh-CN
- 核验方式：{'原声比对' if persona_type in {'existing-character', 'real-person-simulation'} else '原创确认'}
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
            self.assertEqual(result["metrics"]["core_rules"], 12)
            self.assertEqual(result["metrics"]["core_layers"], 10)
            self.assertGreaterEqual(result["metrics"]["core_evidence_cards"], 20)

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
            self.assertGreaterEqual(len(first["related_rules"]["core"]), 1)
            self.assertGreaterEqual(len(first["related_rules"]["voice"]), 1)
            self.assertGreaterEqual(len(first["related_rules"]["modes"]), 1)
            selected_ids = {item["card_id"] for item in first["selected"]}
            for group in first["related_rules"].values():
                self.assertTrue(all(set(rule["matched_card_ids"]) <= selected_ids for rule in group))

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

    def test_translated_or_unverified_text_cannot_count_as_original_language(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "translated-corpus"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            write_text(library, text.replace("- 原文质量：原声核验", "- 原文质量：译本参考", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertEqual(result["metrics"]["exact_original_cards"], 79)
            self.assertIn("dialogue.original_language_unverified", codes)
            self.assertIn("dialogue.exact_original_cards_low", codes)

    def test_boilerplate_observation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "boilerplate-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = re.sub(r"^- 语音表现：.+$", "- 语音表现：统一套用的声纹描述", text, flags=re.MULTILINE)
            write_text(library, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("dialogue.annotation_boilerplate", codes)

    def test_voice_and_scene_must_reference_verified_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "invented-voice"
            build_fixture(role, "existing-character", 80, 40, 20)
            voice_path = role / "references" / "02-语言声纹.md"
            voice_text = voice_path.read_text(encoding="utf-8")
            write_text(voice_path, voice_text.replace("TESTROLE-0001、TESTROLE-0002", "UNKNOWN-9999、TESTROLE-0002", 1))
            core_path = role / "references" / "01-角色核心.md"
            core_text = core_path.read_text(encoding="utf-8")
            write_text(core_path, core_text.replace("TESTROLE-0001、TESTROLE-0002", "UNKNOWN-9999、TESTROLE-0002", 1))
            scene_path = role / "references" / "04-工作场景迁移.md"
            scene_text = scene_path.read_text(encoding="utf-8")
            write_text(scene_path, scene_text.replace("VOICE-01", "VOICE-99", 1))
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("core_rule.evidence_invalid", codes)
            self.assertIn("voice.evidence_invalid", codes)
            self.assertIn("scene.voice_invalid", codes)

    def test_output_language_does_not_filter_original_language_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "cross-language-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            core_path = role / "references" / "01-角色核心.md"
            write_text(
                core_path,
                core_path.read_text(encoding="utf-8").replace("- 作品原始语言：zh-CN", "- 作品原始语言：ja-JP"),
            )
            library = role / "references" / "06-对白库.md"
            text = library.read_text(encoding="utf-8")
            text = text.replace("language=zh-CN", "language=ja-JP").replace("- 原文语言：zh-CN", "- 原文语言：ja-JP")
            write_text(library, text)
            source_path = role / "references" / "08-来源索引.md"
            write_text(
                source_path,
                source_path.read_text(encoding="utf-8").replace("- 原始语言：zh-CN", "- 原始语言：ja-JP"),
            )
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])
            selected = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        str(role / "scripts" / "select_dialogues.py"),
                        "--root", str(role),
                        "--source-language", "ja-JP",
                        "--language", "zh-CN",
                        "--limit", "5",
                        "--format", "json",
                    ],
                    text=True,
                    encoding="utf-8",
                )
            )
            self.assertEqual(len(selected["selected"]), 5)
            self.assertTrue(all(item["original_language"] == "ja-JP" for item in selected["selected"]))

    def test_fidelity_tests_must_be_run_and_meet_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "untested-role"
            build_fixture(role, "existing-character", 80, 40, 20)
            cases_path = role / "references" / "07-验证用例.md"
            text = cases_path.read_text(encoding="utf-8")
            text = text.replace("- 正确识别数：10", "- 正确识别数：6", 1)
            text = text.replace("- 验证状态：通过", "- 验证状态：未运行", 1)
            write_text(cases_path, text)
            result = persona_tool.validate_skill(role, "release")
            codes = {issue["code"] for issue in result["issues"]}
            self.assertFalse(result["valid"])
            self.assertIn("tests.fidelity_not_passed", codes)
            self.assertIn("tests.blind_correct_low", codes)

    def test_original_persona_can_release_with_twenty_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "original-role"
            build_fixture(role, "original-persona", 20)
            result = persona_tool.validate_skill(role, "release")
            self.assertTrue(result["valid"], result["issues"])

    def test_creator_enforces_name_gate_prefix_and_formal_only_delivery(self) -> None:
        creator = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("第一条回复只能显示下面的二选一提示", creator)
        self.assertIn("用户直接回复一个非空名称时，视为选择 `2`", creator)
        self.assertIn("已经取得自定义名称后不得重复询问", creator)
        self.assertIn("创建过程中的所有 Agent 自然语言消息都必须以 `<角色名>：` 开头", creator)
        self.assertIn("最终版本始终为正式版", creator)
        self.assertIn("不按版权类别、文本长度或资料完整度限制收集", creator)
        self.assertIn("对白库禁止加入官方角色介绍", creator)
        self.assertIn("原语言逐字原文", creator)
        self.assertIn("声纹不能由模型自由概括", creator)
        self.assertIn("去名盲测", creator)
        self.assertNotIn("官方角色原文", persona_tool.EXACT_CARD_TYPES)
        self.assertNotIn("试用版", creator)


if __name__ == "__main__":
    unittest.main()
