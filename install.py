#!/usr/bin/env python3
"""Install or update Persona.skill for every supported agent runtime.

The installer uses only the Python standard library plus Git. It never replaces
a non-Git directory and never updates a dirty checkout.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DEFAULT_REPOSITORY = "https://github.com/AgentPal/Persona.skill.git"
DEFAULT_REF = "main"
SUPPORTED_AGENTS = (
    "codex",
    "claude",
    "opencode",
    "workbuddy",
    "codebuddy",
    "kimi-code",
    "mimo-code",
    "github-copilot",
    "gemini",
    "cursor",
    "cline",
    "trae",
    "qoderwork",
    "deepcode",
    "openclaw",
    "hermes",
)
AGENT_LABELS = {
    "codex": "Codex App / CLI",
    "claude": "Claude Code",
    "opencode": "OpenCode",
    "workbuddy": "WorkBuddy",
    "codebuddy": "CodeBuddy",
    "kimi-code": "Kimi Code",
    "mimo-code": "MiMo Code",
    "github-copilot": "GitHub Copilot",
    "gemini": "Gemini CLI",
    "cursor": "Cursor",
    "cline": "Cline",
    "trae": "TRAE",
    "qoderwork": "QoderWork",
    "deepcode": "Deep Code",
    "openclaw": "OpenClaw",
    "hermes": "Hermes",
}


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


_ALIASES = {
    "codex": ("codex", "codex-app", "codex-cli"),
    "claude": ("claude", "claude-code"),
    "opencode": ("opencode", "open-code"),
    "workbuddy": ("workbuddy", "work-buddy"),
    "codebuddy": ("codebuddy", "code-buddy"),
    "kimi-code": ("kimi", "kimi-code", "kimicode"),
    "mimo-code": ("mimo", "mimo-code", "mimocode", "mimo-codex", "mimocodex"),
    "github-copilot": ("copilot", "github-copilot"),
    "gemini": ("gemini", "gemini-cli"),
    "cursor": ("cursor",),
    "cline": ("cline",),
    "trae": ("trae", "trae-cn"),
    "qoderwork": ("qoderwork", "qoder-work"),
    "deepcode": ("deepcode", "deep-code"),
    "openclaw": ("openclaw", "open-claw"),
    "hermes": ("hermes", "hermes-agent"),
}
ALIAS_MAP = {
    _key(alias): agent
    for agent, aliases in _ALIASES.items()
    for alias in aliases
}


class InstallError(RuntimeError):
    """A safe installation failure that should be reported without traceback."""


@dataclass(frozen=True)
class InstallTarget:
    path: Path
    agents: tuple[str, ...]

    @property
    def label(self) -> str:
        return ", ".join(AGENT_LABELS[agent] for agent in self.agents)


def _env_path(env: Mapping[str, str], key: str) -> Path | None:
    value = env.get(key, "").strip()
    return Path(value).expanduser().resolve() if value else None


def _override(env: Mapping[str, str], agent: str) -> Path | None:
    return _env_path(env, "PERSONA_%s_HOME" % agent.upper().replace("-", "_"))


def _root_for(agent: str, home: Path, env: Mapping[str, str]) -> Path:
    if agent in {"mimo-code", "deepcode"}:
        return home / ".agents"
    override = _override(env, agent)
    if override:
        return override
    if agent == "codex":
        return _env_path(env, "CODEX_HOME") or home / ".codex"
    if agent == "claude":
        return _env_path(env, "CLAUDE_CONFIG_DIR") or home / ".claude"
    if agent == "opencode":
        explicit = _env_path(env, "OPENCODE_CONFIG_DIR")
        xdg = _env_path(env, "XDG_CONFIG_HOME")
        return explicit or ((xdg / "opencode") if xdg else home / ".config" / "opencode")
    if agent == "workbuddy":
        return home / ".workbuddy"
    if agent == "codebuddy":
        return home / ".codebuddy"
    if agent == "kimi-code":
        return _env_path(env, "KIMI_CODE_HOME") or home / ".kimi-code"
    if agent == "github-copilot":
        return home / ".copilot"
    if agent == "gemini":
        return home / ".gemini"
    if agent == "cursor":
        return home / ".cursor"
    if agent == "cline":
        return home / ".cline"
    if agent == "trae":
        return home / ".trae"
    if agent == "qoderwork":
        return home / ".qoderwork"
    if agent == "openclaw":
        return _env_path(env, "OPENCLAW_HOME") or home / ".openclaw"
    return _env_path(env, "HERMES_HOME") or home / ".hermes"


def normalize_agent(value: str) -> str:
    agent = ALIAS_MAP.get(_key(value))
    if agent is None:
        raise InstallError("Unsupported agent: %s" % value)
    return agent


def parse_agents(values: Sequence[str]) -> tuple[str, ...]:
    if not values:
        return SUPPORTED_AGENTS
    requested: list[str] = []
    for value in values:
        for item in value.split(","):
            if not item.strip():
                continue
            if _key(item) == "all":
                return SUPPORTED_AGENTS
            agent = normalize_agent(item)
            if agent not in requested:
                requested.append(agent)
    if not requested:
        raise InstallError("No agent was selected")
    return tuple(requested)


def resolve_targets(
    agents: Iterable[str],
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[InstallTarget, ...]:
    # ``--home`` defines an isolated user scope.  Explicitly ignore ambient
    # runtime roots so a test or private install can never write into the
    # operator's CODEX_HOME/XDG/agent config by accident.
    # A supplied mapping is an intentional integration override; suppress
    # only ambient os.environ when an isolated ``--home`` is in use.
    values = dict(env) if env is not None else ({} if home is not None else dict(os.environ))
    user_home = (home or Path.home()).expanduser().resolve()
    grouped: dict[Path, list[str]] = {}
    for agent in agents:
        root = _root_for(agent, user_home, values).expanduser().resolve()
        roots = [root]
        if agent == "trae" and _override(values, agent) is None:
            roots.append((user_home / ".trae-cn").resolve())
        for candidate in roots:
            target = (candidate / "skills" / "persona").resolve()
            grouped.setdefault(target, []).append(agent)
    return tuple(
        InstallTarget(path=path, agents=tuple(agent_ids))
        for path, agent_ids in grouped.items()
    )


def _run_git(arguments: Sequence[str], cwd: Path | None = None) -> str:
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    process = subprocess.run(
        ["git", *arguments],
        cwd=str(cwd) if cwd else None,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout).strip()
        raise InstallError(detail or "git command failed")
    return process.stdout.strip()


def _repository_key(value: str) -> str:
    candidate = Path(value).expanduser()
    if candidate.exists():
        return str(candidate.resolve()).rstrip("/\\").casefold()
    normalized = value.strip().rstrip("/\\")
    if normalized.lower().endswith(".git"):
        normalized = normalized[:-4]
    return normalized.casefold()


def install_target(target: InstallTarget, repository: str, ref: str, dry_run: bool = False) -> str:
    path = target.path
    if dry_run:
        return "would-update" if (path / ".git").is_dir() else "would-install"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and any(path.iterdir()) and not (path / ".git").is_dir():
        raise InstallError("target exists and is not a Git checkout: %s" % path)
    if not path.exists() or not any(path.iterdir()):
        _run_git(["clone", "--depth", "1", "--branch", ref, repository, str(path)])
        return "installed"

    origin = _run_git(["remote", "get-url", "origin"], cwd=path)
    if _repository_key(origin) != _repository_key(repository):
        raise InstallError("existing checkout has a different origin: %s" % origin)
    dirty = _run_git(["status", "--porcelain"], cwd=path)
    if dirty:
        raise InstallError("existing checkout has local changes; update was skipped")
    _run_git(["pull", "--ff-only", "origin", ref], cwd=path)
    return "updated"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install Persona.skill for supported agent runtimes")
    parser.add_argument(
        "--agent",
        action="append",
        default=[],
        help="Agent ID or comma-separated IDs; repeatable. Default: all",
    )
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY, help="Git repository URL or local path")
    parser.add_argument("--ref", default=DEFAULT_REF, help="Git branch or tag (default: main)")
    parser.add_argument("--home", help="Override user home for isolated installs and tests")
    parser.add_argument("--dry-run", action="store_true", help="Print targets without modifying files")
    parser.add_argument("--list", action="store_true", help="List supported agent IDs and exit")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    if args.list:
        for agent in SUPPORTED_AGENTS:
            print("%s\t%s" % (agent, AGENT_LABELS[agent]))
        return 0
    if not args.dry_run and shutil.which("git") is None:
        print("ERROR: Git is required but was not found in PATH", file=sys.stderr)
        return 2
    try:
        agents = parse_agents(args.agent)
        home = Path(args.home).expanduser().resolve() if args.home else None
        targets = resolve_targets(agents, home=home)
    except InstallError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    failures = 0
    for target in targets:
        try:
            action = install_target(target, args.repo, args.ref, dry_run=args.dry_run)
            print("[%s] %s -> %s" % (action, target.label, target.path))
        except (InstallError, OSError) as exc:
            failures += 1
            print("[failed] %s -> %s: %s" % (target.label, target.path, exc), file=sys.stderr)
    if failures:
        print("FAILED_TARGETS=%d" % failures, file=sys.stderr)
        return 1
    print("AGENTS=%d" % len(agents))
    print("TARGETS=%d" % len(targets))
    print("RESULT=%s" % ("dry-run" if args.dry_run else "ok"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
