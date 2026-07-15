from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import install as installer  # noqa: E402
import runtime_lifecycle as lifecycle  # noqa: E402


class InstallerTests(unittest.TestCase):
    def git(self, root: Path, *arguments: str) -> str:
        process = subprocess.run(
            ["git", *arguments],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        return process.stdout.strip()

    def test_supported_agents_match_runtime_profiles_and_aliases(self) -> None:
        self.assertEqual(installer.SUPPORTED_AGENTS, lifecycle.SUPPORTED_RUNTIMES)
        self.assertEqual(installer.normalize_agent("Codex App"), "codex")
        self.assertEqual(installer.normalize_agent("Claude Code"), "claude")
        self.assertEqual(installer.normalize_agent("MiMoCodex"), "mimo-code")
        self.assertEqual(installer.normalize_agent("GitHub Copilot"), "github-copilot")
        self.assertEqual(installer.parse_agents(["codex,kimicode", "Deep Code"]), ("codex", "kimi-code", "deepcode"))

    def test_all_targets_use_native_roots_and_deduplicate_shared_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            targets = installer.resolve_targets(installer.SUPPORTED_AGENTS, home=home, env={})
            by_path = {target.path: target for target in targets}
            self.assertEqual(len(targets), 16)
            self.assertIn(home / ".codex" / "skills" / "persona", by_path)
            self.assertIn(home / ".claude" / "skills" / "persona", by_path)
            self.assertIn(home / ".config" / "opencode" / "skills" / "persona", by_path)
            self.assertIn(home / ".workbuddy" / "skills" / "persona", by_path)
            self.assertIn(home / ".trae" / "skills" / "persona", by_path)
            self.assertIn(home / ".trae-cn" / "skills" / "persona", by_path)
            shared = by_path[home / ".agents" / "skills" / "persona"]
            self.assertEqual(shared.agents, ("mimo-code", "deepcode"))

    def test_dry_run_does_not_create_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            target = installer.resolve_targets(("codex",), home=home, env={})[0]
            self.assertEqual(installer.install_target(target, "unused", "main", dry_run=True), "would-install")
            self.assertFalse(target.path.exists())

    def test_non_git_target_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            target = installer.resolve_targets(("codex",), home=home, env={})[0]
            target.path.mkdir(parents=True)
            sentinel = target.path / "user-file.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaises(installer.InstallError):
                installer.install_target(target, "unused", "main")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    @unittest.skipUnless(shutil.which("git"), "Git is unavailable")
    def test_local_install_update_and_dirty_checkout_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            origin = root / "origin"
            origin.mkdir()
            self.git(origin, "init")
            self.git(origin, "checkout", "-b", "main")
            self.git(origin, "config", "user.email", "persona-test@example.invalid")
            self.git(origin, "config", "user.name", "Persona Test")
            (origin / "SKILL.md").write_text("---\nname: persona\ndescription: test\n---\nv1\n", encoding="utf-8")
            self.git(origin, "add", "SKILL.md")
            self.git(origin, "commit", "-m", "initial")

            target = installer.resolve_targets(("codex",), home=root / "home", env={})[0]
            self.assertEqual(installer.install_target(target, str(origin), "main"), "installed")
            self.assertIn("v1", (target.path / "SKILL.md").read_text(encoding="utf-8"))

            (origin / "SKILL.md").write_text("---\nname: persona\ndescription: test\n---\nv2\n", encoding="utf-8")
            self.git(origin, "add", "SKILL.md")
            self.git(origin, "commit", "-m", "update")
            self.assertEqual(installer.install_target(target, str(origin), "main"), "updated")
            self.assertIn("v2", (target.path / "SKILL.md").read_text(encoding="utf-8"))

            (target.path / "SKILL.md").write_text("local change\n", encoding="utf-8")
            with self.assertRaises(installer.InstallError):
                installer.install_target(target, str(origin), "main")


if __name__ == "__main__":
    unittest.main()
