from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import runtime_lifecycle as lifecycle  # noqa: E402


class RuntimeLifecycleTests(unittest.TestCase):
    def paths(self, root: Path, runtime: str = "codex", env=None) -> lifecycle.RuntimePaths:
        return lifecycle.resolve_runtime_paths(runtime, home=root / "home", env={} if env is None else env)

    def make_role(
        self,
        paths: lifecycle.RuntimePaths,
        role_id: str = "persona-alpha",
        display_name: str = "阿尔法",
        aliases=(),
    ):
        role_path = paths.skills_root / role_id
        role_path.mkdir(parents=True)
        (role_path / "SKILL.md").write_text("---\nname: %s\ndescription: test\n---\n# %s\n" % (role_id, display_name), encoding="utf-8")
        role_hash = lifecycle.directory_hash(role_path)
        role = lifecycle.register_role(
            paths,
            role_id=role_id,
            display_name=display_name,
            role_path=role_path,
            validation_hash=role_hash,
            reply_prefix=display_name + "：",
            aliases=aliases,
            persona_type="original-persona",
            source_identity=display_name,
        )
        return role_path, role

    def test_all_runtime_default_paths_are_native_and_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            codex = self.paths(root, "codex")
            claude = self.paths(root, "claude")
            opencode = self.paths(root, "opencode")
            self.assertEqual(codex.skills_root, root / "home" / ".codex" / "skills")
            self.assertEqual(codex.instruction_path, root / "home" / ".codex" / "AGENTS.md")
            self.assertEqual(claude.skills_root, root / "home" / ".claude" / "skills")
            self.assertEqual(claude.instruction_path, root / "home" / ".claude" / "CLAUDE.md")
            self.assertEqual(opencode.skills_root, root / "home" / ".config" / "opencode" / "skills")
            self.assertEqual(opencode.instruction_path, root / "home" / ".config" / "opencode" / "AGENTS.md")
            self.assertEqual(len({codex.registry_path, claude.registry_path, opencode.registry_path}), 3)

    def test_runtime_environment_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            codex = lifecycle.resolve_runtime_paths("codex", home=root, env={"CODEX_HOME": str(root / "cx")})
            claude = lifecycle.resolve_runtime_paths("claude", home=root, env={"CLAUDE_CONFIG_DIR": str(root / "cl")})
            opencode = lifecycle.resolve_runtime_paths("opencode", home=root, env={"XDG_CONFIG_HOME": str(root / "xdg")})
            self.assertEqual(codex.config_root, root / "cx")
            self.assertEqual(claude.config_root, root / "cl")
            self.assertEqual(opencode.config_root, root / "xdg" / "opencode")

    def test_codex_nonempty_override_has_priority_but_empty_override_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            config = root / "home" / ".codex"
            config.mkdir(parents=True)
            override = config / "AGENTS.override.md"
            override.write_text("", encoding="utf-8")
            self.assertEqual(self.paths(root).instruction_path, config / "AGENTS.md")
            override.write_text("custom", encoding="utf-8")
            self.assertEqual(self.paths(root).instruction_path, override)

    def test_runtime_detection_refuses_missing_and_ambiguous_signals(self) -> None:
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.detect_runtime(env={}, home=Path.cwd())
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.detect_runtime(env={"CODEX_HOME": "x", "CLAUDE_CONFIG_DIR": "y"}, home=Path.cwd())
        self.assertEqual(lifecycle.detect_runtime(env={"PERSONA_RUNTIME": "opencode"})[0], "opencode")

    def test_binding_preserves_utf8_bom_crlf_and_original_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "AGENTS.md"
            original = "# 原指令\r\n\r\n保留这一段。\r\n"
            path.write_bytes(b"\xef\xbb\xbf" + original.encode("utf-8"))
            block = lifecycle.binding_block(
                "codex",
                {"id": "persona-alpha", "display_name": "阿尔法", "path": str(root / "persona-alpha")},
                root / "state.json",
            )
            result = lifecycle.apply_binding(path, block)
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            self.assertIn(original.encode("utf-8"), raw)
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
            self.assertTrue(Path(result["backup_path"]).is_file())

    def test_binding_rejects_duplicate_mismatched_and_reversed_markers(self) -> None:
        samples = (
            lifecycle.START_MARKER,
            lifecycle.END_MARKER,
            lifecycle.START_MARKER + "\n" + lifecycle.START_MARKER + "\n" + lifecycle.END_MARKER,
            lifecycle.END_MARKER + "\n" + lifecycle.START_MARKER,
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "AGENTS.md"
            for sample in samples:
                path.write_text(sample, encoding="utf-8")
                with self.assertRaises(lifecycle.BindingError):
                    lifecycle.inspect_binding(path)

    def test_enable_is_idempotent_and_receipt_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.paths(Path(temporary))
            paths.instruction_path.parent.mkdir(parents=True)
            paths.instruction_path.write_text("# Keep\n", encoding="utf-8")
            role_path, role = self.make_role(paths)
            first = lifecycle.enable_registered_role(paths, role["id"])
            second = lifecycle.enable_registered_role(paths, role["id"])
            self.assertTrue(first["binding"]["changed"])
            self.assertFalse(second["binding"]["changed"])
            self.assertTrue(lifecycle.verify_activation(paths, role_path)["valid"])
            self.assertTrue(lifecycle.role_state_path(paths, role["id"]).is_file())
            self.assertEqual(len(list(paths.instruction_path.parent.glob("AGENTS.md.bak.*"))), 1)

    def test_role_or_instruction_change_invalidates_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.paths(Path(temporary))
            role_path, role = self.make_role(paths)
            lifecycle.enable_registered_role(paths, role["id"])
            (role_path / "new.md").write_text("changed", encoding="utf-8")
            check = lifecycle.verify_activation(paths, role_path)
            self.assertFalse(check["valid"])
            self.assertIn("角色文件哈希已变化", check["errors"])
            (role_path / "new.md").unlink()
            lifecycle.enable_registered_role(paths, role["id"])
            with paths.instruction_path.open("a", encoding="utf-8") as handle:
                handle.write("user edit\n")
            check = lifecycle.verify_activation(paths, role_path)
            self.assertFalse(check["valid"])
            self.assertIn("全局指令文件在启用后已变化，回执已过期", check["errors"])

    def test_unicode_display_ascii_id_alias_and_ambiguous_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.paths(Path(temporary))
            _, first = self.make_role(paths, "persona-chisato", "锦木千束", ("千束",))
            self.assertEqual(lifecycle.resolve_role(lifecycle.load_registry(paths), "千束")["id"], first["id"])
            self.make_role(paths, "persona-other", "另一个", ("千束",))
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.resolve_role(lifecycle.load_registry(paths), "千束")
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.register_role(
                    paths, "人格-非法", "非法", paths.skills_root / "人格-非法", "0" * 64
                )

    def test_disable_removes_only_persona_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.paths(Path(temporary))
            paths.instruction_path.parent.mkdir(parents=True)
            paths.instruction_path.write_text("before\nafter\n", encoding="utf-8")
            _, role = self.make_role(paths)
            lifecycle.enable_registered_role(paths, role["id"])
            lifecycle.disable_active_role(paths)
            text = paths.instruction_path.read_text(encoding="utf-8")
            self.assertEqual(text, "before\nafter\n")
            self.assertIsNone(lifecycle.load_registry(paths)["active_role_id"])
            self.assertFalse(paths.receipt_path.exists())

    def test_delete_active_role_disables_and_removes_only_registered_role(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.paths(Path(temporary))
            mother = paths.skills_root / "persona"
            mother.mkdir(parents=True)
            (mother / "SKILL.md").write_text("mother", encoding="utf-8")
            role_path, role = self.make_role(paths)
            lifecycle.enable_registered_role(paths, role["id"])
            lifecycle.update_state(paths, role["id"], {"emotion_residue": "开心"})
            result = lifecycle.delete_role(paths, "阿尔法")
            self.assertTrue(result["was_active"])
            self.assertFalse(role_path.exists())
            self.assertTrue(mother.exists())
            self.assertNotIn(role["id"], lifecycle.load_registry(paths)["roles"])

    def test_delete_rejects_registry_path_traversal_or_external_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self.paths(root)
            role_path, role = self.make_role(paths)
            registry = lifecycle.load_registry(paths)
            external = root / "external"
            external.mkdir()
            registry["roles"][role["id"]]["path"] = str(external)
            lifecycle.save_registry(paths, registry)
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.delete_role(paths, role["id"])
            self.assertTrue(external.exists())
            self.assertTrue(role_path.exists())

    def test_state_updates_atomically_only_on_change_and_caps_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.paths(Path(temporary))
            _, role = self.make_role(paths)
            payload = {
                "relationship_summary": "已经一起完成一次测试",
                "emotion_residue": "放松",
                "commitments": ["承诺%d" % index for index in range(20)],
                "recent_expression_ids": ["CARD-%03d" % index for index in range(80)],
            }
            first = lifecycle.update_state(paths, role["id"], payload)
            second = lifecycle.update_state(paths, role["id"], payload)
            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])
            self.assertEqual(len(first["state"]["commitments"]), 12)
            self.assertEqual(len(first["state"]["recent_expression_ids"]), 50)
            self.assertNotIn("messages", json.dumps(first["state"], ensure_ascii=False))

    def test_state_rejects_transcripts_and_reset_clears_bounded_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.paths(Path(temporary))
            _, role = self.make_role(paths)
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.update_state(paths, role["id"], {"messages": ["full chat"]})
            lifecycle.update_state(paths, role["id"], {"open_threads": ["待办"]})
            reset = lifecycle.reset_state(paths, role["id"])
            self.assertEqual(reset["open_threads"], [])
            self.assertEqual(reset["relationship_summary"], "")

    def test_each_runtime_full_isolated_lifecycle(self) -> None:
        for runtime in lifecycle.SUPPORTED_RUNTIMES:
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as temporary:
                paths = self.paths(Path(temporary).resolve(), runtime)
                first_path, first = self.make_role(paths, "persona-first", "角色一", ("一号",))
                second_path, second = self.make_role(paths, "persona-second", "角色二", ("二号",))
                lifecycle.enable_registered_role(paths, first["id"])
                self.assertTrue(lifecycle.verify_activation(paths, first_path)["valid"])
                lifecycle.enable_registered_role(paths, lifecycle.resolve_role(lifecycle.load_registry(paths), "二号")["id"])
                registry = lifecycle.load_registry(paths)
                self.assertEqual(registry["active_role_id"], second["id"])
                self.assertTrue(lifecycle.verify_activation(paths, second_path)["valid"])
                lifecycle.disable_active_role(paths)
                self.assertIsNone(lifecycle.load_registry(paths)["active_role_id"])
                result = lifecycle.delete_role(paths, "角色一")
                self.assertEqual(result["deleted_role_id"], first["id"])
                self.assertFalse(first_path.exists())


if __name__ == "__main__":
    unittest.main()
