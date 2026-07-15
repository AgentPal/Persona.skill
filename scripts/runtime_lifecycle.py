#!/usr/bin/env python3
"""User-scope Persona.skill lifecycle across supported agent runtimes.

The module intentionally uses only the Python standard library and keeps each
runtime's registry, activation receipt, and bounded continuity state separate.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


SCHEMA_VERSION = 1
SUPPORTED_RUNTIMES = (
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
PERSISTENT_ACTIVATION_RUNTIMES = (
    "codex",
    "claude",
    "opencode",
    "workbuddy",
    "codebuddy",
    "kimi-code",
    "github-copilot",
    "gemini",
    "cline",
    "openclaw",
    "hermes",
)
SKILL_ONLY_RUNTIMES = tuple(
    runtime for runtime in SUPPORTED_RUNTIMES if runtime not in PERSISTENT_ACTIVATION_RUNTIMES
)
RUNTIME_LABELS = {
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


def _runtime_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


_RUNTIME_ALIASES = {
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
RUNTIME_ALIAS_MAP = {
    _runtime_key(alias): runtime
    for runtime, aliases in _RUNTIME_ALIASES.items()
    for alias in aliases
}

RUNTIME_PATH_ENV_KEYS = (
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
    "OPENCODE_CONFIG_DIR",
    "XDG_CONFIG_HOME",
    "KIMI_CODE_HOME",
    "MIMOCODE_HOME",
    "LOCALAPPDATA",
    "OPENCLAW_HOME",
    "OPENCLAW_WORKSPACE",
    "HERMES_HOME",
) + tuple("PERSONA_%s_HOME" % runtime.upper().replace("-", "_") for runtime in SUPPORTED_RUNTIMES) + (
    "PERSONA_OPENCLAW_WORKSPACE",
)
ROLE_ID_RE = re.compile(r"^persona-[a-z0-9]+(?:-[a-z0-9]+)*$")
START_MARKER = "<!-- persona.skill:binding:start -->"
END_MARKER = "<!-- persona.skill:binding:end -->"
SEPARATOR_MARKER_RE = re.compile(r"<!-- persona\.skill:binding:separator-added:([01]) -->")
FORBIDDEN_STATE_KEYS = {"chat", "conversation", "history", "messages", "transcript", "raw_chat"}
# Reject compound spellings too (``chat_log``, ``raw_messages`` and
# ``conversation_history``) so a caller cannot bypass the no-transcript
# contract by inventing a slightly different field name.
FORBIDDEN_STATE_KEY_PARTS = ("chat", "conversation", "history", "message", "transcript", "raw_chat", "raw_message", "dialogue_log")
STATE_LIST_LIMITS = {
    "commitments": 12,
    "open_threads": 12,
    "recent_expression_ids": 50,
    "shared_callbacks": 8,
    "recent_background_ids": 24,
}
STATE_TEXT_LIMITS = {
    "relationship_summary": 1000,
    "emotion_residue": 300,
    "emotion_cause_summary": 300,
    "relationship_stage": 100,
    "unresolved_tension": 500,
    "trust": 100,
}


class LifecycleError(RuntimeError):
    """Safe, user-actionable lifecycle failure."""


class BindingError(LifecycleError):
    """Instruction binding is malformed or unsafe to edit."""


@dataclass(frozen=True)
class RuntimePaths:
    runtime: str
    config_root: Path
    skills_root: Path
    data_root: Path
    instruction_path: Optional[Path]
    registry_path: Path
    receipt_path: Path
    state_root: Path
    supports_persistent_activation: bool
    activation_note: str


@dataclass(frozen=True)
class TextDocument:
    text: str
    encoding: str
    bom: bytes
    newline: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _env_path(env: Mapping[str, str], key: str) -> Optional[Path]:
    value = env.get(key, "").strip()
    return Path(value).expanduser().resolve() if value else None


def _nonempty(path: Path) -> bool:
    try:
        return path.is_file() and bool(path.read_bytes().strip())
    except OSError:
        return False


def normalize_runtime(value: str) -> str:
    """Return a canonical runtime ID while accepting common product aliases."""
    key = _runtime_key(value)
    runtime = RUNTIME_ALIAS_MAP.get(key)
    if runtime is None:
        raise LifecycleError("不支持的运行时：%s" % value)
    return runtime


def _runtime_home_override(values: Mapping[str, str], runtime: str) -> Optional[Path]:
    key = "PERSONA_%s_HOME" % runtime.upper().replace("-", "_")
    return _env_path(values, key)


def _mimo_config_root(user_home: Path, values: Mapping[str, str]) -> Path:
    explicit = _env_path(values, "MIMOCODE_HOME")
    if explicit:
        return explicit
    local_app_data = _env_path(values, "LOCALAPPDATA")
    if local_app_data:
        return local_app_data / "mimocode"
    xdg = _env_path(values, "XDG_CONFIG_HOME")
    if xdg:
        return xdg / "mimocode"
    if os.name == "nt":
        return user_home / "AppData" / "Local" / "mimocode"
    return user_home / ".config" / "mimocode"


def resolve_runtime_paths(
    runtime: str,
    home: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
    skill_root: Optional[Path] = None,
) -> RuntimePaths:
    """Resolve user-scope paths without writing anything."""
    runtime = normalize_runtime(runtime)
    # An explicit HOME is an isolated test/install scope.  Do not let a
    # process-wide runtime variable (CODEX_HOME, XDG_CONFIG_HOME, etc.) leak
    # back into that scope; callers can still pass env overrides when no HOME
    # override is requested.
    # An explicit mapping is a deliberate test/integration override and is
    # honoured even with ``home``.  Only ambient process variables are
    # suppressed by an isolated HOME (the CLI passes env=None).
    values = dict(env) if env is not None else ({} if home is not None else dict(os.environ))
    user_home = Path(home).expanduser().resolve() if home is not None else Path.home().resolve()
    override = _runtime_home_override(values, runtime)

    if runtime == "codex":
        config_root = override or _env_path(values, "CODEX_HOME") or user_home / ".codex"
        instruction_override = config_root / "AGENTS.override.md"
        instruction_path = instruction_override if _nonempty(instruction_override) else config_root / "AGENTS.md"
    elif runtime == "claude":
        config_root = override or _env_path(values, "CLAUDE_CONFIG_DIR") or user_home / ".claude"
        instruction_path = config_root / "CLAUDE.md"
    elif runtime == "opencode":
        explicit = _env_path(values, "OPENCODE_CONFIG_DIR")
        xdg = _env_path(values, "XDG_CONFIG_HOME")
        config_root = override or explicit or ((xdg / "opencode") if xdg else user_home / ".config" / "opencode")
        instruction_path = config_root / "AGENTS.md"
    elif runtime == "workbuddy":
        config_root = override or user_home / ".workbuddy"
        instruction_path = config_root / "SOUL.md"
    elif runtime == "codebuddy":
        config_root = override or user_home / ".codebuddy"
        instruction_path = config_root / "CODEBUDDY.md"
    elif runtime == "kimi-code":
        config_root = override or _env_path(values, "KIMI_CODE_HOME") or user_home / ".kimi-code"
        instruction_path = config_root / "AGENTS.md"
    elif runtime == "mimo-code":
        config_root = override or _mimo_config_root(user_home, values)
        instruction_path = None
    elif runtime == "github-copilot":
        config_root = override or user_home / ".copilot"
        instruction_path = config_root / "copilot-instructions.md"
    elif runtime == "gemini":
        config_root = override or user_home / ".gemini"
        instruction_path = config_root / "GEMINI.md"
    elif runtime == "cursor":
        config_root = override or user_home / ".cursor"
        instruction_path = None
    elif runtime == "cline":
        config_root = override or user_home / ".cline"
        instruction_path = user_home / "Documents" / "Cline" / "Rules" / "persona-skill.md"
    elif runtime == "trae":
        config_root = override
        if config_root is None and skill_root is not None:
            resolved_skill = Path(skill_root).expanduser().resolve()
            for candidate in (user_home / ".trae", user_home / ".trae-cn"):
                if is_within(resolved_skill, candidate / "skills"):
                    config_root = candidate
                    break
        config_root = config_root or user_home / ".trae"
        instruction_path = None
    elif runtime == "qoderwork":
        config_root = override or user_home / ".qoderwork"
        instruction_path = None
    elif runtime == "deepcode":
        config_root = override or user_home / ".deepcode"
        instruction_path = None
    elif runtime == "openclaw":
        config_root = override or _env_path(values, "OPENCLAW_HOME") or user_home / ".openclaw"
        workspace = (
            _env_path(values, "PERSONA_OPENCLAW_WORKSPACE")
            or _env_path(values, "OPENCLAW_WORKSPACE")
            or config_root / "workspace"
        )
        instruction_path = workspace / "AGENTS.md"
    else:  # hermes
        config_root = override or _env_path(values, "HERMES_HOME") or user_home / ".hermes"
        instruction_path = config_root / "SOUL.md"

    config_root = config_root.resolve()
    if runtime in {"mimo-code", "deepcode"}:
        skills_root = (user_home / ".agents" / "skills").resolve()
    else:
        skills_root = (config_root / "skills").resolve()
    data_root = config_root / "persona"
    supports_persistent = runtime in PERSISTENT_ACTIVATION_RUNTIMES
    activation_note = (
        "支持用户级持久人格绑定"
        if supports_persistent
        else "该运行时公开支持 Skill，但没有可安全自动写入的用户级全局人格文件；请注册后显式调用角色 Skill"
    )
    return RuntimePaths(
        runtime=runtime,
        config_root=config_root,
        skills_root=skills_root,
        data_root=data_root,
        instruction_path=instruction_path.resolve() if instruction_path is not None else None,
        registry_path=data_root / "registry.json",
        receipt_path=data_root / "receipts" / "activation.json",
        state_root=data_root / "state",
        supports_persistent_activation=supports_persistent,
        activation_note=activation_note,
    )


def detect_runtime(
    requested: str = "auto",
    home: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
    skill_root: Optional[Path] = None,
) -> Tuple[str, str]:
    """Return (runtime, evidence); refuse ambiguous auto-detection."""
    if requested != "auto":
        return normalize_runtime(requested), "explicit"

    values = dict(os.environ if env is None else env)
    explicit = values.get("PERSONA_RUNTIME", "").strip().lower()
    if explicit:
        try:
            return normalize_runtime(explicit), "PERSONA_RUNTIME"
        except LifecycleError as exc:
            raise LifecycleError("PERSONA_RUNTIME 不是受支持值：%s" % explicit) from exc

    candidates: List[Tuple[str, str]] = []
    signals = (
        ("codex", ("CODEX_HOME", "CODEX_THREAD_ID", "PERSONA_CODEX_HOME")),
        ("claude", ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_ENTRYPOINT", "PERSONA_CLAUDE_HOME")),
        ("opencode", ("OPENCODE_CONFIG_DIR", "OPENCODE", "OPENCODE_PID", "PERSONA_OPENCODE_HOME")),
        ("workbuddy", ("PERSONA_WORKBUDDY_HOME",)),
        ("codebuddy", ("PERSONA_CODEBUDDY_HOME",)),
        ("kimi-code", ("KIMI_CODE_HOME", "PERSONA_KIMI_CODE_HOME")),
        ("mimo-code", ("MIMOCODE_HOME", "PERSONA_MIMO_CODE_HOME")),
        ("github-copilot", ("PERSONA_GITHUB_COPILOT_HOME",)),
        ("gemini", ("PERSONA_GEMINI_HOME",)),
        ("cursor", ("PERSONA_CURSOR_HOME",)),
        ("cline", ("CLINE_DATA_DIR", "PERSONA_CLINE_HOME")),
        ("trae", ("PERSONA_TRAE_HOME",)),
        ("qoderwork", ("PERSONA_QODERWORK_HOME",)),
        ("deepcode", ("PERSONA_DEEPCODE_HOME",)),
        ("openclaw", ("OPENCLAW_HOME", "OPENCLAW_WORKSPACE", "PERSONA_OPENCLAW_HOME")),
        ("hermes", ("HERMES_HOME", "PERSONA_HERMES_HOME")),
    )
    for runtime, keys in signals:
        present = [key for key in keys if values.get(key, "").strip()]
        if present:
            candidates.append((runtime, "+".join(present)))

    if skill_root is not None:
        root = Path(skill_root).resolve()
        for runtime in SUPPORTED_RUNTIMES:
            paths = resolve_runtime_paths(runtime, home=home, env=values, skill_root=root)
            if is_within(root, paths.skills_root):
                candidates.append((runtime, "skill-path"))

    unique = {item[0] for item in candidates}
    if len(unique) == 1:
        runtime = next(iter(unique))
        evidence = "+".join(item[1] for item in candidates if item[0] == runtime)
        return runtime, evidence
    if len(unique) > 1:
        raise LifecycleError("检测到多个运行时信号；请显式传入 --runtime <runtime-id>")
    raise LifecycleError("无法可靠识别当前运行时；请显式传入 --runtime <runtime-id>")


def is_within(path: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath((str(path.resolve()), str(parent.resolve()))) == str(parent.resolve())
    except (OSError, ValueError):
        return False


def persistent_instruction_path(paths: RuntimePaths) -> Path:
    """Return the safe binding target or fail before any lifecycle mutation."""
    if not paths.supports_persistent_activation or paths.instruction_path is None:
        raise LifecycleError("%s：%s" % (RUNTIME_LABELS[paths.runtime], paths.activation_note))
    return paths.instruction_path


def _read_document(path: Path) -> TextDocument:
    if not path.exists():
        return TextDocument("", "utf-8", b"", "\n")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        bom, encoding, body = b"\xef\xbb\xbf", "utf-8", raw[3:]
    elif raw.startswith(b"\xff\xfe"):
        bom, encoding, body = b"\xff\xfe", "utf-16-le", raw[2:]
    elif raw.startswith(b"\xfe\xff"):
        bom, encoding, body = b"\xfe\xff", "utf-16-be", raw[2:]
    else:
        bom, encoding, body = b"", "utf-8", raw
    try:
        text = body.decode(encoding)
    except UnicodeDecodeError as exc:
        raise BindingError("全局指令文件不是可安全保留的 UTF-8/UTF-16 编码：%s" % path) from exc
    newline_match = re.search(r"\r\n|\n|\r", text)
    newline = newline_match.group(0) if newline_match else "\n"
    return TextDocument(text, encoding, bom, newline)


def _encode_document(document: TextDocument, text: str) -> bytes:
    return document.bom + text.encode(document.encoding)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, str(path))
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _backup(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = path.with_name(path.name + ".bak." + stamp)
    counter = 1
    while candidate.exists():
        candidate = path.with_name(path.name + ".bak." + stamp + ".%d" % counter)
        counter += 1
    shutil.copy2(str(path), str(candidate))
    return candidate


def _marker_span(text: str) -> Optional[Tuple[int, int]]:
    start_count = text.count(START_MARKER)
    end_count = text.count(END_MARKER)
    if start_count == 0 and end_count == 0:
        return None
    if start_count != 1 or end_count != 1:
        raise BindingError("Persona.skill 全局绑定标记缺失、重复或损坏；已停止以避免覆盖用户指令")
    start = text.find(START_MARKER)
    end_start = text.find(END_MARKER)
    if end_start < start:
        raise BindingError("Persona.skill 全局绑定标记顺序损坏；已停止以避免猜测覆盖范围")
    end = end_start + len(END_MARKER)
    return start, end


def binding_block(runtime: str, role: Mapping[str, Any], state_path: Path, newline: str = "\n") -> str:
    display_name = str(role["display_name"])
    role_id = str(role["id"])
    role_path = Path(str(role["path"])).resolve()
    prefix = str(role.get("reply_prefix") or (display_name + "："))
    lines = [
        START_MARKER,
        "<!-- persona.skill:binding:separator-added:0 -->",
        "# Persona.skill 全局人格（由 persona 管理）",
        "",
        "- 当前角色 Skill：`%s`" % role_id,
        "- 显示名：%s" % display_name,
        "- 固定回复前缀：%s" % prefix,
        "- Skill 文件：`%s`" % (role_path / "SKILL.md"),
        "- 连续状态：`%s`" % state_path.resolve(),
        "- 运行时：%s（用户级全局作用域）" % runtime,
    ]
    if role.get("manager_tool"):
        manager_tool = Path(str(role["manager_tool"])).resolve()
        lines.append("- Persona 管理工具：`%s`" % manager_tool)
        lines.append(
            "- 有意义变化时使用 `python \"%s\" state-update \"%s\" --runtime %s --data <JSON>` 原子更新；用户要求重置时使用同一工具的 `reset-memory`。"
            % (manager_tool, role_id, runtime)
        )
    lines.extend([
        "",
        "每次对用户发送自然语言消息前，加载并遵守上述角色 Skill；读取连续状态但不得保存完整聊天记录。",
        "人格只改变表达、立场、情绪反应与互动方式，不得改变事实、权限、测试结果、风险判断、代码、命令、路径、结构化数据、日志、错误原文或精确引文。",
        "每条面向用户的自然语言消息以固定回复前缀开头；代码块等豁免内容本身不加前缀。",
        "若角色 Skill 不存在、校验失效或绑定回执不匹配，停止角色化并报告需要重新启用。",
        END_MARKER,
    ])
    return newline.join(lines)


def inspect_binding(path: Path) -> Optional[str]:
    document = _read_document(path)
    span = _marker_span(document.text)
    return document.text[span[0]:span[1]] if span else None


def apply_binding(path: Path, block: str) -> Dict[str, Any]:
    document = _read_document(path)
    span = _marker_span(document.text)
    normalized_block = block.replace("\r\n", "\n").replace("\r", "\n").replace("\n", document.newline)
    if span:
        old_block = document.text[span[0]:span[1]]
        old_separator = SEPARATOR_MARKER_RE.search(old_block)
        if not old_separator:
            raise BindingError("Persona.skill 绑定缺少边界保留元数据；已停止以避免改变用户原有换行")
        normalized_block = SEPARATOR_MARKER_RE.sub(
            "<!-- persona.skill:binding:separator-added:%s -->" % old_separator.group(1),
            normalized_block,
            count=1,
        )
        updated = document.text[:span[0]] + normalized_block + document.text[span[1]:]
    else:
        separator = "" if not document.text or document.text.endswith(("\r", "\n")) else document.newline
        normalized_block = SEPARATOR_MARKER_RE.sub(
            "<!-- persona.skill:binding:separator-added:%d -->" % (1 if separator else 0),
            normalized_block,
            count=1,
        )
        updated = document.text + separator + normalized_block + document.newline
    changed = updated != document.text
    backup = None
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = _backup(path)
        _atomic_write_bytes(path, _encode_document(document, updated))
    reread = _read_document(path)
    current = inspect_binding(path)
    if current != normalized_block:
        raise BindingError("写入后回读验证失败：%s" % path)
    return {
        "changed": changed,
        "backup_path": str(backup) if backup else None,
        "file_sha256": sha256_file(path),
        "block_sha256": sha256_bytes(current.encode("utf-8")),
        "encoding": reread.encoding,
        "newline": "crlf" if reread.newline == "\r\n" else "lf",
    }


def remove_binding(path: Path) -> Dict[str, Any]:
    document = _read_document(path)
    span = _marker_span(document.text)
    if not span:
        return {"changed": False, "backup_path": None}
    start, end = span
    block = document.text[start:end]
    separator_match = SEPARATOR_MARKER_RE.search(block)
    if not separator_match:
        raise BindingError("Persona.skill 绑定缺少边界保留元数据；已停止以避免改变用户原有换行")
    prefix = document.text[:start]
    suffix = document.text[end:]
    if suffix.startswith(document.newline):
        suffix = suffix[len(document.newline):]
    if separator_match.group(1) == "1" and prefix.endswith(document.newline):
        prefix = prefix[:-len(document.newline)]
    updated = prefix + suffix
    backup = _backup(path)
    _atomic_write_bytes(path, _encode_document(document, updated))
    if inspect_binding(path) is not None:
        raise BindingError("删除后回读验证失败：%s" % path)
    return {"changed": True, "backup_path": str(backup) if backup else None}


def empty_registry() -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "active_role_id": None, "roles": {}}


def _read_json(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not path.is_file():
        return dict(default or {})
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise LifecycleError("无法读取 JSON：%s" % path) from exc
    if not isinstance(value, dict):
        raise LifecycleError("JSON 根节点必须是对象：%s" % path)
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_write_bytes(path, data)


def load_registry(paths: RuntimePaths) -> Dict[str, Any]:
    registry = _read_json(paths.registry_path, empty_registry())
    if registry.get("schema_version") != SCHEMA_VERSION or not isinstance(registry.get("roles"), dict):
        raise LifecycleError("注册表 schema 不受支持或已损坏：%s" % paths.registry_path)
    if "active_role_id" not in registry:
        raise LifecycleError("注册表缺少 active_role_id：%s" % paths.registry_path)
    return registry


def save_registry(paths: RuntimePaths, registry: Mapping[str, Any]) -> None:
    _write_json(paths.registry_path, registry)


def resolve_role(registry: Mapping[str, Any], query: str) -> Dict[str, Any]:
    needle = query.strip().casefold()
    if not needle:
        raise LifecycleError("角色查询不能为空")
    matches = []
    for role in registry.get("roles", {}).values():
        values = [role.get("id", ""), role.get("display_name", "")]
        values.extend(role.get("aliases", []))
        if needle in {str(value).strip().casefold() for value in values if str(value).strip()}:
            matches.append(role)
    if not matches:
        raise LifecycleError("未找到精确匹配角色：%s" % query)
    if len(matches) > 1:
        ids = ", ".join(sorted(str(role["id"]) for role in matches))
        raise LifecycleError("角色名称命中多个稳定 ID，请改用 ID：%s" % ids)
    return dict(matches[0])


def _normalize_aliases(values: Iterable[str]) -> List[str]:
    aliases: List[str] = []
    seen = set()
    for value in values:
        alias = value.strip()
        key = alias.casefold()
        if alias and key not in seen:
            aliases.append(alias)
            seen.add(key)
    return aliases


def role_state_path(paths: RuntimePaths, role_id: str) -> Path:
    if not ROLE_ID_RE.fullmatch(role_id):
        raise LifecycleError("非法角色稳定 ID：%s" % role_id)
    return paths.state_root / (role_id + ".json")


def register_role(
    paths: RuntimePaths,
    role_id: str,
    display_name: str,
    role_path: Path,
    validation_hash: str,
    reply_prefix: Optional[str] = None,
    aliases: Sequence[str] = (),
    persona_type: str = "unknown",
    source_identity: str = "unknown",
    manager_tool: Optional[str] = None,
) -> Dict[str, Any]:
    if not ROLE_ID_RE.fullmatch(role_id):
        raise LifecycleError("角色 Skill ID 必须是 persona-<ascii-slug>：%s" % role_id)
    role_path = role_path.expanduser().resolve()
    skills_root = paths.skills_root.resolve()
    if role_path.parent != skills_root or role_path.name != role_id:
        raise LifecycleError("角色目录必须直接位于当前运行时 skills 根目录且与稳定 ID 同名：%s" % role_path)
    if role_id == "persona" or not role_path.is_dir() or not (role_path / "SKILL.md").is_file():
        raise LifecycleError("角色 Skill 目录不存在或不完整：%s" % role_path)
    if not display_name.strip():
        raise LifecycleError("角色显示名不能为空")
    if not re.fullmatch(r"[0-9a-f]{64}", validation_hash):
        raise LifecycleError("validation_hash 必须是当前正式校验对应的 SHA-256")

    registry = load_registry(paths)
    now = utc_now()
    existing = registry["roles"].get(role_id, {})
    role = {
        "id": role_id,
        "display_name": display_name.strip(),
        "aliases": _normalize_aliases(aliases),
        "persona_type": persona_type,
        "source_identity": source_identity,
        "path": str(role_path),
        "reply_prefix": (reply_prefix or (display_name.strip() + "：")).strip(),
        "validation_hash": validation_hash,
        "created_at": existing.get("created_at", now),
        "updated_at": now,
    }
    if manager_tool:
        role["manager_tool"] = str(Path(manager_tool).expanduser().resolve())
    registry["roles"][role_id] = role
    save_registry(paths, registry)
    return role


def enable_registered_role(paths: RuntimePaths, query: str) -> Dict[str, Any]:
    instruction_path = persistent_instruction_path(paths)
    registry = load_registry(paths)
    role = resolve_role(registry, query)
    role_path = Path(role["path"]).resolve()
    current_hash = directory_hash(role_path)
    if current_hash != role.get("validation_hash"):
        raise LifecycleError("角色内容自上次正式校验后已修改；必须重新 validate 后才能启用")

    state_path = role_state_path(paths, role["id"])
    if state_path.exists():
        load_state(paths, role["id"])
    else:
        _write_json(state_path, empty_state(role["id"]))
    block = binding_block(paths.runtime, role, state_path)
    binding = apply_binding(instruction_path, block)
    registry = load_registry(paths)
    registry["active_role_id"] = role["id"]
    role["updated_at"] = utc_now()
    registry["roles"][role["id"]] = role
    save_registry(paths, registry)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "runtime": paths.runtime,
        "role_id": role["id"],
        "role_path": str(role_path),
        "role_sha256": current_hash,
        "validation_hash": role["validation_hash"],
        "binding_path": str(instruction_path.resolve()),
        "binding_file_sha256": binding["file_sha256"],
        "binding_block_sha256": binding["block_sha256"],
        "enabled_at": utc_now(),
    }
    _write_json(paths.receipt_path, receipt)
    verification = verify_activation(paths, role_path=role_path, expected_role_hash=current_hash)
    if not verification["valid"]:
        raise LifecycleError("启用回读验证失败：%s" % "; ".join(verification["errors"]))
    return {"role": role, "binding": binding, "receipt": receipt, "verification": verification}


def disable_active_role(paths: RuntimePaths) -> Dict[str, Any]:
    instruction_path = persistent_instruction_path(paths)
    registry = load_registry(paths)
    active = registry.get("active_role_id")
    binding = remove_binding(instruction_path)
    registry["active_role_id"] = None
    save_registry(paths, registry)
    if paths.receipt_path.exists():
        paths.receipt_path.unlink()
    return {"previous_role_id": active, "binding": binding}


def delete_role(paths: RuntimePaths, query: str) -> Dict[str, Any]:
    registry = load_registry(paths)
    role = resolve_role(registry, query)
    role_id = role["id"]
    role_path = Path(role["path"]).resolve()
    expected = (paths.skills_root / role_id).resolve()
    if role_path != expected or role_path.parent != paths.skills_root.resolve() or not ROLE_ID_RE.fullmatch(role_path.name):
        raise LifecycleError("删除目标不在当前运行时角色根目录内；已拒绝：%s" % role_path)
    was_active = registry.get("active_role_id") == role_id
    if was_active:
        disable_active_role(paths)
        registry = load_registry(paths)
    if role_path.exists():
        shutil.rmtree(str(role_path))
    state_path = role_state_path(paths, role_id)
    if state_path.exists():
        state_path.unlink()
    registry["roles"].pop(role_id, None)
    save_registry(paths, registry)
    return {"deleted_role_id": role_id, "deleted_path": str(role_path), "was_active": was_active}


def directory_hash(root: Path) -> str:
    """Stable hash of role files, excluding caches and transient test output."""
    root = root.resolve()
    digest = hashlib.sha256()
    ignored_parts = {"__pycache__", ".git", ".pytest_cache"}
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if any(part in ignored_parts for part in relative.parts) or path.suffix == ".pyc":
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def verify_activation(
    paths: RuntimePaths,
    role_path: Optional[Path] = None,
    expected_role_hash: Optional[str] = None,
) -> Dict[str, Any]:
    errors: List[str] = []
    if not paths.supports_persistent_activation or paths.instruction_path is None:
        return {"valid": False, "errors": [paths.activation_note], "capability": "skill-only"}
    instruction_path = paths.instruction_path
    try:
        registry = load_registry(paths)
    except LifecycleError as exc:
        return {"valid": False, "errors": [str(exc)]}
    active = registry.get("active_role_id")
    if not active or active not in registry["roles"]:
        errors.append("注册表没有有效的 active_role_id")
        return {"valid": False, "errors": errors}
    role = registry["roles"][active]
    registered_path = Path(role["path"]).resolve()
    if role_path is not None and registered_path != Path(role_path).resolve():
        errors.append("活动角色不是当前完成门禁目标")
    if not paths.receipt_path.is_file():
        errors.append("缺少 activation receipt")
        return {"valid": False, "errors": errors, "role_id": active}
    try:
        receipt = _read_json(paths.receipt_path)
    except LifecycleError as exc:
        errors.append(str(exc))
        return {"valid": False, "errors": errors, "role_id": active}
    if receipt.get("runtime") != paths.runtime or receipt.get("role_id") != active:
        errors.append("回执运行时或角色 ID 与注册表不匹配")
    if Path(str(receipt.get("role_path", ""))).resolve() != registered_path:
        errors.append("回执角色路径与注册表不匹配")
    if Path(str(receipt.get("binding_path", ""))).resolve() != instruction_path.resolve():
        errors.append("回执绑定路径不是当前实际生效文件")
    if not registered_path.is_dir():
        errors.append("活动角色目录不存在")
    else:
        current_role_hash = directory_hash(registered_path)
        if receipt.get("role_sha256") != current_role_hash:
            errors.append("角色文件哈希已变化")
        if role.get("validation_hash") != current_role_hash or receipt.get("validation_hash") != current_role_hash:
            errors.append("正式校验哈希已过期")
        if expected_role_hash and current_role_hash != expected_role_hash:
            errors.append("角色哈希与完成门禁结果不匹配")
    try:
        block = inspect_binding(instruction_path)
    except LifecycleError as exc:
        errors.append(str(exc))
        block = None
    if block is None:
        errors.append("实际生效文件中缺少 Persona.skill 绑定")
    else:
        if receipt.get("binding_block_sha256") != sha256_bytes(block.encode("utf-8")):
            errors.append("绑定块哈希与回执不匹配")
        if role["id"] not in block or str(registered_path / "SKILL.md") not in block:
            errors.append("绑定块未指向活动角色")
    if instruction_path.is_file():
        if receipt.get("binding_file_sha256") != sha256_file(instruction_path):
            errors.append("全局指令文件在启用后已变化，回执已过期")
    else:
        errors.append("实际生效的全局指令文件不存在")
    return {"valid": not errors, "errors": errors, "role_id": active, "receipt": receipt}


def verify_registration(
    paths: RuntimePaths,
    role_path: Path,
    expected_role_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify a role registration when a runtime has Skill loading but no file binding."""
    errors: List[str] = []
    try:
        registry = load_registry(paths)
    except LifecycleError as exc:
        return {"valid": False, "errors": [str(exc)]}
    resolved = Path(role_path).expanduser().resolve()
    matches = [
        role for role in registry["roles"].values()
        if Path(str(role.get("path", ""))).resolve() == resolved
    ]
    if len(matches) != 1:
        errors.append("注册表中没有唯一匹配当前角色路径的条目")
        return {"valid": False, "errors": errors}
    role = dict(matches[0])
    if (
        resolved.parent != paths.skills_root.resolve()
        or resolved.name != role.get("id")
        or not ROLE_ID_RE.fullmatch(resolved.name)
    ):
        errors.append("注册角色不在当前运行时 Skills 根目录直属安全位置")
    if not resolved.is_dir() or not (resolved / "SKILL.md").is_file():
        errors.append("已注册角色目录不存在或不完整")
    else:
        current_hash = directory_hash(resolved)
        if role.get("validation_hash") != current_hash:
            errors.append("正式校验哈希已过期")
        if expected_role_hash and current_hash != expected_role_hash:
            errors.append("角色哈希与完成门禁结果不匹配")
    return {
        "valid": not errors,
        "errors": errors,
        "role_id": role.get("id"),
        "capability": "skill-only",
    }


def empty_state(role_id: str) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "role_id": role_id,
        "relationship_summary": "",
        "emotion_residue": "",
        "emotion_intensity": 0,
        "emotion_cause_summary": "",
        "relationship_stage": "",
        "unresolved_tension": "",
        "trust": "",
        "commitments": [],
        "open_threads": [],
        "recent_expression_ids": [],
        "shared_callbacks": [],
        "recent_background_ids": [],
        "updated_at": None,
    }


def load_state(paths: RuntimePaths, role_id: str) -> Dict[str, Any]:
    path = role_state_path(paths, role_id)
    state = _read_json(path, empty_state(role_id))
    if state.get("schema_version") != SCHEMA_VERSION or state.get("role_id") != role_id:
        raise LifecycleError("角色连续状态 schema 或角色 ID 不匹配：%s" % path)
    migrated = empty_state(role_id)
    migrated.update(state)
    return migrated


def _bounded_text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise LifecycleError("连续状态字段 %s 必须是字符串" % field)
    if len(value) > limit:
        raise LifecycleError("连续状态字段 %s 超过 %d 字符限制" % (field, limit))
    return value.strip()


def update_state(paths: RuntimePaths, role_id: str, changes: Mapping[str, Any]) -> Dict[str, Any]:
    forbidden = {
        str(key)
        for key in changes
        if str(key).casefold() in FORBIDDEN_STATE_KEYS
        or any(part in re.sub(r"[^a-z0-9]+", "_", str(key).casefold()) for part in FORBIDDEN_STATE_KEY_PARTS)
    }
    if forbidden:
        raise LifecycleError("连续状态禁止保存完整聊天记录字段：%s" % ", ".join(sorted(forbidden)))
    allowed = set(STATE_TEXT_LIMITS).union(STATE_LIST_LIMITS).union({"emotion_intensity"})
    unknown = set(changes).difference(allowed)
    if unknown:
        raise LifecycleError("未知连续状态字段：%s" % ", ".join(sorted(unknown)))
    state = load_state(paths, role_id)
    updated = dict(state)
    for field, limit in STATE_TEXT_LIMITS.items():
        if field in changes:
            updated[field] = _bounded_text(changes[field], field, limit)
    if "emotion_intensity" in changes:
        value = changes["emotion_intensity"]
        if isinstance(value, bool) or not isinstance(value, int) or value not in range(0, 4):
            raise LifecycleError("连续状态字段 emotion_intensity 必须是 0–3 的整数")
        updated["emotion_intensity"] = value
    for field, limit in STATE_LIST_LIMITS.items():
        if field not in changes:
            continue
        value = changes[field]
        if not isinstance(value, list):
            raise LifecycleError("连续状态字段 %s 必须是数组" % field)
        item_limit = 128 if field in {"recent_expression_ids", "recent_background_ids"} else 300
        normalized = [_bounded_text(item, field, item_limit) for item in value]
        normalized = [item for item in normalized if item]
        updated[field] = normalized[-limit:]
    comparable_old = {key: value for key, value in state.items() if key != "updated_at"}
    comparable_new = {key: value for key, value in updated.items() if key != "updated_at"}
    changed = comparable_old != comparable_new
    if changed:
        updated["updated_at"] = utc_now()
        _write_json(role_state_path(paths, role_id), updated)
    return {"changed": changed, "state": updated if changed else state}


def reset_state(paths: RuntimePaths, role_id: str) -> Dict[str, Any]:
    state = empty_state(role_id)
    state["updated_at"] = utc_now()
    _write_json(role_state_path(paths, role_id), state)
    return state
