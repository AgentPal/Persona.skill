import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("migrate_asset_v2", ROOT / "scripts" / "migrate_asset_v2.py")
MIGRATE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MIGRATE)


class MigrateAssetV2Tests(unittest.TestCase):
    def test_structural_migration_is_explicit_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            role = Path(temporary) / "persona-example"
            references = role / "references"
            references.mkdir(parents=True)
            (role / "SKILL.md").write_text(
                "---\nname: persona-example\ndescription: test\n---\n\n# Example\n",
                encoding="utf-8",
            )
            (references / "01-角色核心.md").write_text(
                "# 示例角色核心\n\n## 身份\n\n- 版本：正式版\n- 作品原始语言：zh-CN\n- 当前角色显示名：示例\n",
                encoding="utf-8",
            )
            (references / "06-对白库.md").write_text(
                "# 对白库\n\n## EXAMPLE-0001\n\n"
                "- 卡片类型：原文对白\n"
                "- 交流目的：接住问题\n"
                "- 主要情绪：认真\n"
                "- 后续原文：事情办成了\n"
                "- 语法标记：先判断再解释\n",
                encoding="utf-8",
            )
            (references / "08-来源索引.md").write_text(
                "# 来源\n\n## SRC-0001\n\n- 来源类型：原作明确\n",
                encoding="utf-8",
            )
            (references / "10-人物背景档案.md").write_text(
                "# 背景\n\n### BIO-01 | 身份\n\n"
                "- 角色视角回答要点：我知道自己是谁\n"
                "- 适用问题：身份 / 来历\n",
                encoding="utf-8",
            )

            result = MIGRATE.migrate(role, ROOT / "assets" / "角色人格模板", False, False)
            first = {path.name: path.read_text(encoding="utf-8") for path in references.iterdir()}
            result_again = MIGRATE.migrate(role, ROOT / "assets" / "角色人格模板", False, False)
            second = {path.name: path.read_text(encoding="utf-8") for path in references.iterdir()}

            self.assertEqual(result, {"role_id": "persona-example", "display_name": "示例", "asset_version": 2})
            self.assertEqual(result_again, result)
            self.assertEqual(first, second)
            self.assertIn("- 人格资产版本：2", first["01-角色核心.md"])
            self.assertIn("- 版本层：primary", first["06-对白库.md"])
            self.assertIn("- 引用方式：exact-quote", first["06-对白库.md"])
            self.assertIn("禁止用模型印象补写", first["06-对白库.md"])
            self.assertIn("- 版本层：primary", first["08-来源索引.md"])
            self.assertIn("- 主观解释：我知道自己是谁", first["10-人物背景档案.md"])
            self.assertIn("待根据角色证据补充", first["10-人物背景档案.md"])

            MIGRATE.sync_runtime_assets(
                role, ROOT / "assets" / "角色人格模板", "persona-example", "示例",
            )
            synced_skill = (role / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("{{CARD_PREFIX}}", synced_skill)
            self.assertNotIn("[原始语言]", synced_skill)
            self.assertIn("--exclude EXAMPLE-0001", synced_skill)
            self.assertIn("--source-language zh-CN", synced_skill)
            self.assertTrue((role / "scripts" / "select_dialogues.py").is_file())

            migrate_v3 = ROOT / "scripts" / "migrate_asset_v3.py"
            first_v3 = subprocess.run(
                [sys.executable, str(migrate_v3), str(role), "--no-sync-runtime-assets"],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(first_v3.returncode, 0, first_v3.stdout + first_v3.stderr)
            self.assertIn("MIGRATION_STATE=INCOMPLETE", first_v3.stdout)
            self.assertIn("MUST_CONTINUE=true", first_v3.stdout)
            v3_snapshot = {
                "core": (references / "01-角色核心.md").read_text(encoding="utf-8"),
                "behavior": (references / "12-行为辨识模型.md").read_text(encoding="utf-8"),
            }
            second_v3 = subprocess.run(
                [sys.executable, str(migrate_v3), str(role), "--no-sync-runtime-assets"],
                check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(second_v3.returncode, 0, second_v3.stdout + second_v3.stderr)
            self.assertEqual(v3_snapshot["core"], (references / "01-角色核心.md").read_text(encoding="utf-8"))
            self.assertEqual(v3_snapshot["behavior"], (references / "12-行为辨识模型.md").read_text(encoding="utf-8"))
            self.assertIn("- 人格资产版本：3", v3_snapshot["core"])
            self.assertIn("BEHAV-01", v3_snapshot["behavior"])


if __name__ == "__main__":
    unittest.main()
