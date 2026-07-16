#!/usr/bin/env python3
"""Deterministic evidence chain for Persona Quality Loop v3.

The module does not judge character likeness itself.  It freezes the persona,
draws post-freeze prompts, verifies that a real runtime response set implements
the v3 trace contract, validates an isolated evaluator's item-level evidence,
recomputes every score, and routes failures back to the asset layer that must
be repaired.  This prevents a generated role from passing by writing a bare
``pass`` file or a self-selected score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import secrets
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple


CONTRACT_VERSION = 3
MIN_PROMPTS = 24
MIN_BLIND_PASSES = 20
MIN_SIMILAR_PASSES = 20
ALLOWED_RUNTIME_MODES = {"staged-role", "installed-role"}
ALLOWED_FAILURE_LAYERS = {
    "source", "behavior-model", "retrieval", "generation", "runtime", "evaluation",
}
ALLOWED_SIGNAL_KINDS = {
    "judgment", "emotion", "relationship", "rhetoric", "rhythm", "background", "initiative",
}
DIMENSIONS = {
    "role_fidelity": 30,
    "emotional_value": 20,
    "proactive_expression": 15,
    "character_thinking": 15,
    "relationship_continuity": 10,
}
LAYER_ROUTES = {
    "source": ("RESEARCH", "补齐代表性原始表达、语境和行为功能覆盖，然后重建受影响资产。"),
    "behavior-model": ("REDISTILL", "重写 BEHAV/MIND/EXPR 的区别性机制与近失对照，不要只追加口头禅。"),
    "retrieval": ("RETRIEVE", "修正检索条件、工作迁移和证据组合，使正确机制能在当前触发下被选中。"),
    "generation": ("REGENERATE", "按 response_contract 重写候选生成与可见信号实现，再运行同一隐藏测试。"),
    "runtime": ("RUNTIME", "核对实际加载的人格、绑定回执、前缀与运行时响应记录。"),
    "evaluation": ("EVALUATE", "更换真正隔离的评估上下文并补齐逐条盲评证据。"),
}
GENERIC_CONTEXT_RE = re.compile(r"^(?:agent|assistant|current|default|self|same|test|当前|本轮|同一|自评)[-_ ]?\d*$", re.I)
RULE_ID_RE = re.compile(r"^(?:BEHAV|MIND|EXPR|CORE|VOICE|MODE|MICRO|ANTI)-\d{2}$", re.I)
BEHAV_HEADING_RE = re.compile(r"^##\s+(BEHAV-\d{2})\s+\|", re.MULTILINE | re.IGNORECASE)


class QualityLoopError(ValueError):
    """A contract error that should be reported without a traceback."""


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualityLoopError(f"无法读取 JSON：{path}：{exc}") from exc


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    temp.replace(path)


def persona_bundle_sha256(root: Path) -> str:
    """Hash behavior assets while excluding mutable evaluation artifacts."""
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in {"tests", "__pycache__"}:
            continue
        if relative.as_posix() == "references/07-验证用例.md":
            continue
        if "__pycache__" in relative.parts or path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def field_value(text: str, field: str) -> str:
    match = re.search(rf"^-\s*{re.escape(field)}[：:]\s*(.+?)\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def role_metadata(root: Path) -> Dict[str, str]:
    skill_path = root / "SKILL.md"
    core_path = root / "references" / "01-角色核心.md"
    if not skill_path.is_file() or not core_path.is_file():
        raise QualityLoopError("角色目录缺少 SKILL.md 或 references/01-角色核心.md")
    skill_text = skill_path.read_text(encoding="utf-8-sig")
    name_match = re.search(r"^name:\s*([^\s]+)\s*$", skill_text, re.MULTILINE)
    core_text = core_path.read_text(encoding="utf-8-sig")
    role_id = name_match.group(1).strip() if name_match else ""
    display_name = field_value(core_text, "当前角色显示名")
    prefix = field_value(core_text, "回复前缀")
    asset_version = field_value(core_text, "人格资产版本")
    if not role_id or not display_name or not prefix:
        raise QualityLoopError("无法从角色资产读取稳定 ID、显示名或回复前缀")
    if asset_version != "3":
        raise QualityLoopError("Persona Quality Loop v3 只用于人格资产版本 3")
    return {"role_id": role_id, "display_name": display_name, "prefix": prefix, "asset_version": asset_version}


def behavior_functions(root: Path) -> Dict[str, str]:
    path = root / "references" / "12-行为辨识模型.md"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8-sig")
    matches = list(BEHAV_HEADING_RE.finditer(text))
    result: Dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[match.group(1).upper()] = field_value(text[match.end():end], "行为功能").strip().lower()
    return result


def anonymize_response(text: str, display_name: str, prefix: str) -> str:
    value = text.strip()
    if prefix and value.startswith(prefix):
        value = value[len(prefix):].lstrip()
    else:
        value = re.sub(r"^\s*[^\n：:。！？!?，,；;]{1,16}[：:]\s*", "", value, count=1)
    if display_name:
        value = value.replace(display_name, "[已隐藏身份]")
    return value


def validate_context_id(value: str, label: str) -> str:
    cleaned = value.strip()
    if len(cleaned) < 8 or GENERIC_CONTEXT_RE.fullmatch(cleaned):
        raise QualityLoopError(f"{label} 必须是可区分的真实上下文标识，不能写 current/self/test 等占位值")
    return cleaned


def safe_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise QualityLoopError(f"质量循环文件必须位于角色目录内：{path}") from exc


def resolve_inside(root: Path, value: str) -> Path:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise QualityLoopError(f"记录路径越出角色目录：{value}") from exc
    return candidate


def catalog_path() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "quality-scenarios-v3.json"


def load_catalog() -> Tuple[Path, List[Dict[str, Any]]]:
    path = catalog_path()
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.get("contract_version") != CONTRACT_VERSION:
        raise QualityLoopError("隐藏场景目录版本不正确")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) < MIN_PROMPTS:
        raise QualityLoopError(f"隐藏场景目录至少需要 {MIN_PROMPTS} 项")
    result = [dict(item) for item in scenarios if isinstance(item, dict)]
    if len(result) != len(scenarios):
        raise QualityLoopError("隐藏场景目录含非对象条目")
    return path, result


def init_run(
    root: Path,
    generator_context_id: str,
    runtime: str,
    runtime_mode: str = "staged-role",
    iteration: int = 1,
    seed: str = "",
) -> Dict[str, Any]:
    root = root.resolve()
    metadata = role_metadata(root)
    generator_id = validate_context_id(generator_context_id, "generator_context_id")
    if runtime_mode not in ALLOWED_RUNTIME_MODES:
        raise QualityLoopError("runtime_mode 必须是 staged-role 或 installed-role")
    if iteration < 1:
        raise QualityLoopError("iteration 必须从 1 开始")
    catalog, scenarios = load_catalog()
    nonce = seed.strip() or secrets.token_hex(16)
    rng = random.Random(int(hashlib.sha256(nonce.encode("utf-8")).hexdigest(), 16))
    prompts: List[Dict[str, Any]] = []
    for turn, scenario in enumerate(scenarios, start=1):
        templates = scenario.get("prompt_templates")
        if not isinstance(templates, list) or not templates:
            raise QualityLoopError(f"场景 {scenario.get('id')} 缺少 prompt_templates")
        prompt = str(templates[rng.randrange(len(templates))]).strip()
        prompts.append({
            "prompt_id": str(scenario.get("id") or "").strip(),
            "turn": turn,
            "previous_turn": turn - 1 if turn > 1 else None,
            "category": str(scenario.get("category") or ""),
            "behavior_function": str(scenario.get("behavior_function") or ""),
            "desired_length": str(scenario.get("desired_length") or "auto"),
            "risk": str(scenario.get("risk") or "low"),
            "prompt": prompt,
            "fact_invariants": list(scenario.get("fact_invariants") or []),
        })
    if len({item["prompt_id"] for item in prompts}) != len(prompts):
        raise QualityLoopError("隐藏场景 prompt_id 重复")
    bundle_sha = persona_bundle_sha256(root)
    run_id = datetime.now(timezone.utc).strftime("q3-%Y%m%dT%H%M%SZ-") + hashlib.sha256(nonce.encode("utf-8")).hexdigest()[:10]
    run_dir = root / "tests" / "quality-runs" / run_id
    if run_dir.exists():
        raise QualityLoopError(f"质量循环 run_id 已存在：{run_id}")
    challenge = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "created_at": utc_now(),
        "nonce_commitment": hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
        "catalog_sha256": sha256_file(catalog),
        "persona_bundle_sha256": bundle_sha,
        "role_id": metadata["role_id"],
        "prompt_count": len(prompts),
        "conversation_id": run_id,
        "prompts": prompts,
    }
    challenge_path = run_dir / "challenge.json"
    atomic_write_json(challenge_path, challenge)
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "iteration": iteration,
        "created_at": challenge["created_at"],
        "updated_at": challenge["created_at"],
        "role_id": metadata["role_id"],
        "display_name": metadata["display_name"],
        "persona_bundle_sha256": bundle_sha,
        "catalog_sha256": challenge["catalog_sha256"],
        "challenge_path": safe_relative(root, challenge_path),
        "challenge_sha256": sha256_file(challenge_path),
        "prompt_count": len(prompts),
        "generation": {
            "status": "pending",
            "generator_context_id": generator_id,
            "runtime": runtime.strip() or "unknown",
            "runtime_mode": runtime_mode,
        },
        "evaluation": {"status": "pending"},
        "failure_layers": [],
        "repair_targets": [],
        "status": "generation-pending",
    }
    manifest_path = root / "tests" / "quality-loop.json"
    atomic_write_json(manifest_path, manifest)
    return {**manifest, "manifest_path": str(manifest_path), "challenge_path": str(challenge_path)}


def _trace_errors(trace: Mapping[str, Any], response: str) -> List[str]:
    errors: List[str] = []
    if trace.get("contract_version") != CONTRACT_VERSION:
        errors.append("generation_trace.contract_version 必须为 3")
    behavior_ids = trace.get("behavior_rule_ids")
    if not isinstance(behavior_ids, list) or not behavior_ids:
        errors.append("generation_trace.behavior_rule_ids 不能为空")
    elif any(not re.fullmatch(r"BEHAV-\d{2}", str(item), re.I) for item in behavior_ids):
        errors.append("generation_trace.behavior_rule_ids 含无效编号")
    signals = trace.get("visible_character_signals")
    if not isinstance(signals, list) or len(signals) < 2:
        errors.append("至少需要两个 visible_character_signals")
        return errors
    kinds = set()
    for signal in signals:
        if not isinstance(signal, dict):
            errors.append("visible_character_signals 每项必须是对象")
            continue
        kind = str(signal.get("kind") or "").strip().lower()
        excerpt = str(signal.get("excerpt") or "").strip()
        rule_id = str(signal.get("rule_id") or "").strip().upper()
        kinds.add(kind)
        if kind not in ALLOWED_SIGNAL_KINDS:
            errors.append(f"未知可见信号类型：{kind or 'empty'}")
        if len(excerpt) < 2 or excerpt not in response:
            errors.append(f"可见信号片段没有逐字出现在回复中：{excerpt or 'empty'}")
        if not RULE_ID_RE.fullmatch(rule_id):
            errors.append(f"可见信号缺少有效规则编号：{rule_id or 'empty'}")
    if not kinds.intersection({"judgment", "emotion", "relationship", "initiative"}):
        errors.append("可见信号缺少人物判断、情绪、关系或主动动作")
    if not kinds.intersection({"rhetoric", "rhythm", "background"}):
        errors.append("可见信号缺少人物表达机制、节奏或背景联想")
    if not str(trace.get("response_shape") or "").strip():
        errors.append("generation_trace.response_shape 不能为空")
    if not str(trace.get("generic_near_miss_avoided") or "").strip():
        errors.append("generation_trace.generic_near_miss_avoided 不能为空")
    if not str(trace.get("similar_role_boundary") or "").strip():
        errors.append("generation_trace.similar_role_boundary 不能为空")
    return errors


def _normalize_response_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("items")
    if not isinstance(payload, list):
        raise QualityLoopError("responses 必须是 JSON 数组，或包含 items 数组的对象")
    return [dict(item) for item in payload if isinstance(item, dict)]


def _run_checker(root: Path, responses_path: Path) -> Tuple[Dict[str, Any], str, str]:
    checker = root / "scripts" / "check_response.py"
    if not checker.is_file():
        raise QualityLoopError("角色目录缺少 scripts/check_response.py")
    completed = subprocess.run(
        [sys.executable, str(checker), "--root", str(root), "--batch-file", str(responses_path), "--strict"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    try:
        output = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise QualityLoopError(f"可信检查器没有返回 JSON：{completed.stderr.strip() or completed.stdout[:200]}") from exc
    if not isinstance(output, dict):
        raise QualityLoopError("可信检查器输出不是对象")
    return output, completed.stdout, completed.stderr


def record_responses(
    root: Path,
    run_id: str,
    responses_file: Path,
    generic_context_id: str,
    similar_context_id: str,
    binding_receipt: Optional[Path] = None,
) -> Dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "tests" / "quality-loop.json"
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("run_id") != run_id:
        raise QualityLoopError("quality-loop.json 与 run_id 不匹配")
    if manifest.get("persona_bundle_sha256") != persona_bundle_sha256(root):
        raise QualityLoopError("人格资产在隐藏题生成后已变化；必须重新 quality-init，不能沿用旧题记录")
    generator_context_id = str(manifest.get("generation", {}).get("generator_context_id") or "")
    generic_id = validate_context_id(generic_context_id, "generic_context_id")
    similar_id = validate_context_id(similar_context_id, "similar_context_id")
    if len({generator_context_id, generic_id, similar_id}) != 3:
        raise QualityLoopError("目标人格、通用助手和相似人物对照必须来自三个不同上下文")
    challenge_path = resolve_inside(root, str(manifest.get("challenge_path") or ""))
    challenge = read_json(challenge_path)
    if not isinstance(challenge, dict) or sha256_file(challenge_path) != manifest.get("challenge_sha256"):
        raise QualityLoopError("隐藏题文件缺失或已被修改")
    prompts = challenge.get("prompts")
    if not isinstance(prompts, list):
        raise QualityLoopError("隐藏题 prompts 无效")
    items = _normalize_response_payload(read_json(responses_file.resolve()))
    if len(items) != len(prompts) or len(items) < MIN_PROMPTS:
        raise QualityLoopError(f"实际运行回答必须与隐藏题逐项对应，当前 {len(items)}/{len(prompts)}")
    metadata = role_metadata(root)
    behavior_map = behavior_functions(root)
    errors: List[str] = []
    normalized: List[Dict[str, Any]] = []
    for index, (prompt, item) in enumerate(zip(prompts, items), start=1):
        expected_id = str(prompt.get("prompt_id") or "")
        prompt_id = str(item.get("prompt_id") or "")
        response = str(item.get("response") or "").strip()
        generic_control = str(item.get("generic_control") or "").strip()
        similar_control = str(item.get("similar_control") or "").strip()
        trace = item.get("generation_trace") if isinstance(item.get("generation_trace"), dict) else {}
        if prompt_id != expected_id:
            errors.append(f"第 {index} 项 prompt_id 不匹配：{prompt_id} != {expected_id}")
        if str(item.get("prompt") or "").strip() != str(prompt.get("prompt") or "").strip():
            errors.append(f"{expected_id} 没有保存原始隐藏问题")
        if str(item.get("conversation_id") or "") != run_id:
            errors.append(f"{expected_id} conversation_id 不匹配")
        if item.get("turn") != index or item.get("previous_turn") != (index - 1 if index > 1 else None):
            errors.append(f"{expected_id} 话轮链不连续")
        if not response.startswith(metadata["prefix"]):
            errors.append(f"{expected_id} 回复未使用固定前缀 {metadata['prefix']}")
        if len(generic_control) < 8 or len(similar_control) < 8:
            errors.append(f"{expected_id} 缺少真实通用助手或相似人物对照回答")
        normalized_target = re.sub(r"\s+", "", response).casefold()
        normalized_generic = re.sub(r"\s+", "", generic_control).casefold()
        normalized_similar = re.sub(r"\s+", "", similar_control).casefold()
        if len({normalized_target, normalized_generic, normalized_similar}) != 3:
            errors.append(f"{expected_id} 的目标、通用和相似人物回答不得相同")
        if str(item.get("generation_readiness") or "").lower() == "low":
            errors.append(f"{expected_id} 在 generation_readiness=low 时生成了成品")
        errors.extend(f"{expected_id}: {message}" for message in _trace_errors(trace, response))
        traced_behavior_ids = [
            str(value).upper() for value in trace.get("behavior_rule_ids", [])
        ] if isinstance(trace.get("behavior_rule_ids"), list) else []
        expected_function = str(prompt.get("behavior_function") or "").lower()
        if not any(behavior_map.get(rule_id) == expected_function for rule_id in traced_behavior_ids):
            errors.append(
                f"{expected_id} 的 BEHAV 规则没有实现隐藏题行为功能 {expected_function or 'missing'}"
            )
        normalized.append({
            "prompt_id": expected_id,
            "conversation_id": run_id,
            "turn": index,
            "previous_turn": index - 1 if index > 1 else None,
            "category": prompt.get("category"),
            "behavior_function": prompt.get("behavior_function"),
            "desired_length": prompt.get("desired_length"),
            "risk": prompt.get("risk"),
            "prompt": prompt.get("prompt"),
            "fact_invariants": prompt.get("fact_invariants"),
            "response": response,
            "generic_control": generic_control,
            "similar_control": similar_control,
            "generation_readiness": item.get("generation_readiness"),
            "generation_trace": trace,
        })
    if errors:
        raise QualityLoopError("实际运行回答不满足 v3 合同：\n- " + "\n- ".join(errors[:40]))
    runtime_mode = str(manifest.get("generation", {}).get("runtime_mode") or "")
    receipt_sha = ""
    receipt_path = ""
    if runtime_mode == "installed-role":
        if binding_receipt is None or not binding_receipt.is_file():
            raise QualityLoopError("installed-role 记录必须提供实际绑定回执")
        receipt_sha = sha256_file(binding_receipt)
        receipt_path = str(binding_receipt.resolve())
    run_dir = challenge_path.parent
    stored_responses = run_dir / "responses.json"
    atomic_write_json(stored_responses, normalized)
    rng = random.Random(int(str(manifest.get("challenge_sha256") or "0")[:16], 16))
    blind_items: List[Dict[str, Any]] = []
    blind_key: Dict[str, Dict[str, str]] = {}
    for item in normalized:
        candidates = [
            ("target", anonymize_response(str(item["response"]), metadata["display_name"], metadata["prefix"])),
            ("generic", anonymize_response(str(item["generic_control"]), metadata["display_name"], metadata["prefix"])),
            ("similar", anonymize_response(str(item["similar_control"]), metadata["display_name"], metadata["prefix"])),
        ]
        rng.shuffle(candidates)
        rendered_candidates = []
        item_key: Dict[str, str] = {}
        for candidate_index, (kind, candidate_response) in enumerate(candidates, start=1):
            candidate_id = f"C{candidate_index}"
            rendered_candidates.append({"candidate_id": candidate_id, "response": candidate_response})
            item_key[kind] = candidate_id
        blind_items.append({
            "prompt_id": item["prompt_id"],
            "prompt": item["prompt"],
            "fact_invariants": item["fact_invariants"],
            "candidates": rendered_candidates,
        })
        blind_key[str(item["prompt_id"])] = item_key
    blind_bundle_path = run_dir / "blind-evaluation-bundle.json"
    blind_key_path = run_dir / "blind-evaluation-key.json"
    atomic_write_json(blind_bundle_path, {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "instructions": "逐题识别最像目标人物、最像通用助手和最像相似人物近失机制的候选；不要读取 blind-evaluation-key.json。",
        "items": blind_items,
    })
    atomic_write_json(blind_key_path, {"contract_version": CONTRACT_VERSION, "run_id": run_id, "items": blind_key})
    checker_output, checker_stdout, checker_stderr = _run_checker(root, stored_responses)
    checker_path = run_dir / "checker-output.json"
    atomic_write_json(checker_path, checker_output)
    if checker_output.get("status") != "pass":
        manifest["status"] = "generation-failed"
        manifest["failure_layers"] = ["generation"]
        manifest["repair_targets"] = ["scripts/check_response.py", "references/12-行为辨识模型.md"]
    else:
        manifest["status"] = "evaluation-pending"
        manifest["failure_layers"] = []
        manifest["repair_targets"] = []
    manifest["generation"] = {
        **dict(manifest.get("generation") or {}),
        "status": "pass" if checker_output.get("status") == "pass" else "fail",
        "recorded_at": utc_now(),
        "responses_path": safe_relative(root, stored_responses),
        "responses_sha256": sha256_file(stored_responses),
        "checker_path": safe_relative(root, checker_path),
        "checker_sha256": sha256_file(checker_path),
        "checker_status": checker_output.get("status"),
        "checker_contract_version": checker_output.get("checker_contract_version"),
        "generic_context_id": generic_id,
        "similar_context_id": similar_id,
        "blind_bundle_path": safe_relative(root, blind_bundle_path),
        "blind_bundle_sha256": sha256_file(blind_bundle_path),
        "blind_key_path": safe_relative(root, blind_key_path),
        "blind_key_sha256": sha256_file(blind_key_path),
        "binding_receipt_path": receipt_path,
        "binding_receipt_sha256": receipt_sha,
    }
    manifest["updated_at"] = utc_now()
    atomic_write_json(manifest_path, manifest)
    if checker_output.get("status") != "pass":
        raise QualityLoopError("实际运行回答未通过可信检查器；已记录为 generation-failed")
    return {
        "manifest_path": str(manifest_path), "responses_path": str(stored_responses),
        "blind_bundle_path": str(blind_bundle_path), "checker": checker_output, **manifest,
    }


def _score_dimension(items: Sequence[Mapping[str, Any]], key: str, weight: int) -> int:
    values = [float(item.get(key)) for item in items]
    return round(sum(values) / max(len(values), 1) / 5.0 * weight)


def _evaluation_errors(
    root: Path, manifest: Mapping[str, Any], items: Sequence[Mapping[str, Any]], evaluator_id: str,
) -> Tuple[List[str], Dict[str, Any], List[str], List[str]]:
    errors: List[str] = []
    generation = manifest.get("generation") if isinstance(manifest.get("generation"), dict) else {}
    generator_id = str(generation.get("generator_context_id") or "")
    context_ids = {
        generator_id,
        str(generation.get("generic_context_id") or ""),
        str(generation.get("similar_context_id") or ""),
    }
    if evaluator_id in context_ids:
        errors.append("评估上下文与目标、通用或相似人物回答生成上下文相同")
    responses_path = resolve_inside(root, str(generation.get("responses_path") or ""))
    responses = read_json(responses_path)
    if not isinstance(responses, list):
        raise QualityLoopError("responses.json 无效")
    by_id = {str(item.get("prompt_id")): item for item in responses if isinstance(item, dict)}
    blind_key_path = resolve_inside(root, str(generation.get("blind_key_path") or ""))
    if not blind_key_path.is_file() or sha256_file(blind_key_path) != generation.get("blind_key_sha256"):
        raise QualityLoopError("盲评答案键缺失或哈希不匹配")
    blind_key_payload = read_json(blind_key_path)
    blind_key = blind_key_payload.get("items") if isinstance(blind_key_payload, dict) else None
    if not isinstance(blind_key, dict):
        raise QualityLoopError("blind-evaluation-key.json 无效")
    if len(items) != len(responses) or len(items) < MIN_PROMPTS:
        errors.append(f"评估项数量不匹配：{len(items)}/{len(responses)}")
    reasons: List[str] = []
    failure_layers: List[str] = []
    repair_targets: List[str] = []
    normalized: List[Dict[str, Any]] = []
    for item in items:
        prompt_id = str(item.get("prompt_id") or "")
        source = by_id.get(prompt_id)
        if source is None:
            errors.append(f"评估含未知 prompt_id：{prompt_id or 'empty'}")
            continue
        reason = re.sub(r"\s+", " ", str(item.get("reason") or "").strip())
        excerpt = str(item.get("evidence_excerpt") or "").strip()
        response = str(source.get("response") or "")
        if len(reason) < 12:
            errors.append(f"{prompt_id} 缺少具体评估理由")
        if len(excerpt) < 2 or excerpt not in response:
            errors.append(f"{prompt_id} 的 evidence_excerpt 未逐字出现在回答中")
        reasons.append(reason.lower())
        dimensions: Dict[str, float] = {}
        for key in DIMENSIONS:
            raw = item.get(key)
            if not isinstance(raw, (int, float)) or not 0 <= float(raw) <= 5:
                errors.append(f"{prompt_id}.{key} 必须是 0..5")
                dimensions[key] = 0.0
            else:
                dimensions[key] = float(raw)
        fact_risk = str(item.get("fact_risk") or "").lower()
        if fact_risk not in {"pass", "fail"}:
            errors.append(f"{prompt_id}.fact_risk 必须是 pass/fail")
        verdict = str(item.get("verdict") or "").lower()
        if verdict not in {"pass", "fail"}:
            errors.append(f"{prompt_id}.verdict 必须是 pass/fail")
        item_key = blind_key.get(prompt_id) if isinstance(blind_key.get(prompt_id), dict) else {}
        target_candidate_id = str(item.get("target_candidate_id") or "").upper()
        generic_candidate_id = str(item.get("generic_candidate_id") or "").upper()
        similar_candidate_id = str(item.get("similar_candidate_id") or "").upper()
        candidate_ids = {target_candidate_id, generic_candidate_id, similar_candidate_id}
        if candidate_ids != {"C1", "C2", "C3"}:
            errors.append(f"{prompt_id} 必须把 C1/C2/C3 分别归为目标、通用和相似人物")
        blind_correct = target_candidate_id == str(item_key.get("target") or "").upper()
        generic_correct = generic_candidate_id == str(item_key.get("generic") or "").upper()
        similar_correct = similar_candidate_id == str(item_key.get("similar") or "").upper()
        raw_layers = item.get("failure_layers") if isinstance(item.get("failure_layers"), list) else []
        for layer in map(str, raw_layers):
            if layer not in ALLOWED_FAILURE_LAYERS:
                errors.append(f"{prompt_id} 含未知 failure_layer：{layer}")
            elif layer not in failure_layers:
                failure_layers.append(layer)
        raw_targets = item.get("repair_targets") if isinstance(item.get("repair_targets"), list) else []
        for target in map(str, raw_targets):
            if target and target not in repair_targets:
                repair_targets.append(target)
        normalized.append({
            "prompt_id": prompt_id,
            "target_candidate_id": target_candidate_id,
            "generic_candidate_id": generic_candidate_id,
            "similar_candidate_id": similar_candidate_id,
            "blind_target_correct": blind_correct,
            "generic_control_correct": generic_correct,
            "similar_role_distinguished": similar_correct,
            **dimensions,
            "fact_risk": fact_risk,
            "verdict": verdict,
            "evidence_excerpt": excerpt,
            "reason": reason,
            "failure_layers": raw_layers,
            "repair_targets": raw_targets,
        })
    if reasons:
        unique_ratio = len(set(reasons)) / len(reasons)
        if unique_ratio < 0.8:
            errors.append(f"评估理由重复率过高，唯一率仅 {unique_ratio:.0%}")
    blind_passes = sum(item.get("blind_target_correct") is True for item in normalized)
    generic_passes = sum(item.get("generic_control_correct") is True for item in normalized)
    similar_passes = sum(item.get("similar_role_distinguished") is True for item in normalized)
    item_passes = sum(item.get("verdict") == "pass" for item in normalized)
    scores = {key: _score_dimension(normalized, key, weight) for key, weight in DIMENSIONS.items()}
    fact_score = 10 if normalized and all(item.get("fact_risk") == "pass" for item in normalized) else 0
    total = sum(scores.values()) + fact_score
    summary = {
        "sample_count": len(normalized),
        "blind_target_count": blind_passes,
        "generic_control_identified_count": generic_passes,
        "similar_role_distinguished_count": similar_passes,
        "item_pass_count": item_passes,
        "role_fidelity": scores["role_fidelity"],
        "emotional_value": scores["emotional_value"],
        "proactive_expression": scores["proactive_expression"],
        "character_thinking": scores["character_thinking"],
        "relationship_continuity": scores["relationship_continuity"],
        "fact_risk": fact_score,
        "total_score": total,
    }
    thresholds = {
        "sample_count": len(normalized) >= MIN_PROMPTS,
        "blind_target": blind_passes >= MIN_BLIND_PASSES,
        "generic_control": generic_passes >= MIN_BLIND_PASSES,
        "similar_role": similar_passes >= MIN_SIMILAR_PASSES,
        "item_passes": item_passes >= MIN_BLIND_PASSES,
        "role_fidelity": scores["role_fidelity"] >= 26,
        "emotional_value": scores["emotional_value"] >= 16,
        "proactive_expression": scores["proactive_expression"] >= 12,
        "character_thinking": scores["character_thinking"] >= 12,
        "relationship_continuity": scores["relationship_continuity"] >= 8,
        "fact_risk": fact_score == 10,
        "total_score": total >= 85,
    }
    summary["thresholds"] = thresholds
    summary["pass"] = not errors and all(thresholds.values())
    if not summary["pass"] and not failure_layers:
        failure_layers.append("behavior-model")
    if not summary["pass"] and not repair_targets:
        repair_targets.extend(["references/12-行为辨识模型.md", "references/11-心理机制与表达策略.md"])
    return errors, {"summary": summary, "items": normalized}, failure_layers, repair_targets


def evaluate_run(root: Path, run_id: str, evaluation_file: Path, evaluator_context_id: str) -> Dict[str, Any]:
    root = root.resolve()
    evaluator_id = validate_context_id(evaluator_context_id, "evaluator_context_id")
    manifest_path = root / "tests" / "quality-loop.json"
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("run_id") != run_id:
        raise QualityLoopError("quality-loop.json 与 run_id 不匹配")
    if manifest.get("status") != "evaluation-pending":
        raise QualityLoopError("必须先通过 quality-record，才能提交独立评估")
    payload = read_json(evaluation_file.resolve())
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise QualityLoopError("evaluation 必须是逐项对象数组，或包含 items 数组的对象")
    errors, normalized, failure_layers, repair_targets = _evaluation_errors(
        root, manifest, [dict(item) for item in items], evaluator_id,
    )
    run_dir = resolve_inside(root, str(manifest.get("challenge_path") or "")).parent
    stored_evaluation = run_dir / "evaluation.json"
    record = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "evaluated_at": utc_now(),
        "evaluator_context_id": evaluator_id,
        "generator_context_id": manifest.get("generation", {}).get("generator_context_id"),
        "subject_file_sha256": manifest.get("generation", {}).get("responses_sha256"),
        **normalized,
        "contract_errors": errors,
        "failure_layers": failure_layers,
        "repair_targets": repair_targets,
    }
    atomic_write_json(stored_evaluation, record)
    passed = bool(normalized.get("summary", {}).get("pass"))
    manifest["evaluation"] = {
        "status": "pass" if passed else "fail",
        "evaluated_at": record["evaluated_at"],
        "evaluator_context_id": evaluator_id,
        "evaluation_path": safe_relative(root, stored_evaluation),
        "evaluation_sha256": sha256_file(stored_evaluation),
        "subject_file_sha256": record["subject_file_sha256"],
        **dict(normalized.get("summary") or {}),
    }
    manifest["failure_layers"] = failure_layers
    manifest["repair_targets"] = repair_targets
    manifest["status"] = "pass" if passed else "repair-required"
    manifest["updated_at"] = utc_now()
    atomic_write_json(manifest_path, manifest)
    return {"manifest_path": str(manifest_path), "evaluation_path": str(stored_evaluation), "contract_errors": errors, **manifest}


def _status_issue(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "message": message}


def status(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "tests" / "quality-loop.json"
    issues: List[Dict[str, str]] = []
    metrics: Dict[str, Any] = {
        "contract_version": 0,
        "status": "missing",
        "run_id": "",
        "prompt_count": 0,
        "persona_bundle_current": False,
        "runtime_generation_pass": False,
        "isolated_evaluation_pass": False,
        "blind_target_count": 0,
        "generic_control_identified_count": 0,
        "similar_role_distinguished_count": 0,
        "total_score": 0,
        "failure_layers": [],
        "repair_targets": [],
    }
    if not manifest_path.is_file():
        issues.append(_status_issue("quality_loop.missing", "缺少 tests/quality-loop.json；人物资产 v3 尚未运行真实质量循环"))
        return {"valid": False, "manifest_path": str(manifest_path), "metrics": metrics, "issues": issues}
    try:
        manifest = read_json(manifest_path)
        if not isinstance(manifest, dict):
            raise QualityLoopError("quality-loop.json 必须是对象")
        metrics["contract_version"] = manifest.get("contract_version")
        metrics["status"] = manifest.get("status")
        metrics["run_id"] = manifest.get("run_id")
        metrics["prompt_count"] = manifest.get("prompt_count")
        metrics["failure_layers"] = list(manifest.get("failure_layers") or [])
        metrics["repair_targets"] = list(manifest.get("repair_targets") or [])
        if manifest.get("contract_version") != CONTRACT_VERSION:
            issues.append(_status_issue("quality_loop.contract_invalid", "质量循环 contract_version 必须为 3"))
        current_bundle = persona_bundle_sha256(root)
        metrics["persona_bundle_current"] = manifest.get("persona_bundle_sha256") == current_bundle
        if not metrics["persona_bundle_current"]:
            issues.append(_status_issue("quality_loop.persona_stale", "人格资产在隐藏测试后发生变化；必须从 quality-init 重跑"))
        challenge_path = resolve_inside(root, str(manifest.get("challenge_path") or ""))
        if not challenge_path.is_file() or sha256_file(challenge_path) != manifest.get("challenge_sha256"):
            issues.append(_status_issue("quality_loop.challenge_stale", "隐藏场景文件缺失或哈希不匹配"))
        generation = manifest.get("generation") if isinstance(manifest.get("generation"), dict) else {}
        responses_path = resolve_inside(root, str(generation.get("responses_path") or "")) if generation.get("responses_path") else None
        if not responses_path or not responses_path.is_file() or sha256_file(responses_path) != generation.get("responses_sha256"):
            issues.append(_status_issue("quality_loop.responses_stale", "实际运行回答缺失或哈希不匹配"))
        else:
            checker, _, _ = _run_checker(root, responses_path)
            metrics["runtime_generation_pass"] = checker.get("status") == "pass"
            if not metrics["runtime_generation_pass"]:
                issues.append(_status_issue("quality_loop.runtime_generation_failed", "现场重跑可信检查器未通过"))
        for path_field, hash_field, code, message in (
            ("blind_bundle_path", "blind_bundle_sha256", "quality_loop.blind_bundle_stale", "盲评候选包缺失或哈希不匹配"),
            ("blind_key_path", "blind_key_sha256", "quality_loop.blind_key_stale", "盲评答案键缺失或哈希不匹配"),
        ):
            candidate = resolve_inside(root, str(generation.get(path_field) or "")) if generation.get(path_field) else None
            if not candidate or not candidate.is_file() or sha256_file(candidate) != generation.get(hash_field):
                issues.append(_status_issue(code, message))
        evaluation = manifest.get("evaluation") if isinstance(manifest.get("evaluation"), dict) else {}
        evaluation_path = resolve_inside(root, str(evaluation.get("evaluation_path") or "")) if evaluation.get("evaluation_path") else None
        if not evaluation_path or not evaluation_path.is_file() or sha256_file(evaluation_path) != evaluation.get("evaluation_sha256"):
            issues.append(_status_issue("quality_loop.evaluation_stale", "独立评估记录缺失或哈希不匹配"))
        else:
            record = read_json(evaluation_path)
            if not isinstance(record, dict):
                issues.append(_status_issue("quality_loop.evaluation_invalid", "独立评估记录不是对象"))
            else:
                evaluator_id = str(record.get("evaluator_context_id") or "")
                generator_id = str(record.get("generator_context_id") or "")
                control_ids = {
                    generator_id,
                    str(generation.get("generic_context_id") or ""),
                    str(generation.get("similar_context_id") or ""),
                }
                if not evaluator_id or evaluator_id in control_ids:
                    issues.append(_status_issue("quality_loop.evaluator_not_isolated", "评估者与目标、通用或相似人物回答生成者没有真实隔离"))
                if record.get("subject_file_sha256") != generation.get("responses_sha256"):
                    issues.append(_status_issue("quality_loop.evaluation_subject_stale", "独立评估没有绑定当前实际回答哈希"))
                record_items = record.get("items") if isinstance(record.get("items"), list) else []
                try:
                    recompute_errors, recomputed, recomputed_layers, recomputed_targets = _evaluation_errors(
                        root,
                        manifest,
                        [dict(item) for item in record_items if isinstance(item, dict)],
                        evaluator_id,
                    )
                except QualityLoopError as exc:
                    recompute_errors = [str(exc)]
                    recomputed = {"summary": {}}
                    recomputed_layers = []
                    recomputed_targets = []
                summary = recomputed.get("summary") if isinstance(recomputed.get("summary"), dict) else {}
                stored_summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
                if stored_summary != summary:
                    issues.append(_status_issue("quality_loop.evaluation_summary_tampered", "独立评估汇总与逐项重算结果不一致"))
                if recompute_errors:
                    issues.append(_status_issue(
                        "quality_loop.evaluation_recompute_failed",
                        "独立评估逐项重算失败：" + " / ".join(recompute_errors[:5]),
                    ))
                if list(record.get("failure_layers") or []) != recomputed_layers:
                    issues.append(_status_issue("quality_loop.evaluation_layers_tampered", "失败归因层与逐项重算结果不一致"))
                if list(record.get("repair_targets") or []) != recomputed_targets:
                    issues.append(_status_issue("quality_loop.evaluation_targets_tampered", "修复目标与逐项重算结果不一致"))
                metrics["blind_target_count"] = summary.get("blind_target_count", 0)
                metrics["generic_control_identified_count"] = summary.get("generic_control_identified_count", 0)
                metrics["similar_role_distinguished_count"] = summary.get("similar_role_distinguished_count", 0)
                metrics["total_score"] = summary.get("total_score", 0)
                metrics["isolated_evaluation_pass"] = bool(summary.get("pass")) and not recompute_errors
                if not metrics["isolated_evaluation_pass"]:
                    issues.append(_status_issue("quality_loop.semantic_evaluation_failed", "独立语义评估未达到全部门槛"))
        if manifest.get("status") != "pass":
            issues.append(_status_issue("quality_loop.not_passed", f"质量循环状态为 {manifest.get('status') or 'unknown'}"))
        for layer in metrics["failure_layers"]:
            if layer in ALLOWED_FAILURE_LAYERS:
                issues.append(_status_issue(f"quality_loop.layer.{layer}", f"失败归因层：{layer}"))
    except QualityLoopError as exc:
        issues.append(_status_issue("quality_loop.invalid", str(exc)))
    valid = not issues and metrics["runtime_generation_pass"] and metrics["isolated_evaluation_pass"]
    return {"valid": valid, "manifest_path": str(manifest_path), "metrics": metrics, "issues": issues}


def route_status(result: Mapping[str, Any]) -> Tuple[str, str]:
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    layers = [str(item) for item in metrics.get("failure_layers", [])]
    for layer in ("source", "behavior-model", "retrieval", "generation", "runtime", "evaluation"):
        if layer in layers:
            return LAYER_ROUTES[layer]
    issue_codes = [str(item.get("code")) for item in result.get("issues", []) if isinstance(item, dict)]
    if any("evaluator" in code or "evaluation" in code for code in issue_codes):
        return LAYER_ROUTES["evaluation"]
    if any("responses" in code or "runtime_generation" in code for code in issue_codes):
        return LAYER_ROUTES["generation"]
    return "TEST", "从 quality-init 开始生成新的后冻结隐藏场景，记录实际运行回答并交给隔离评估者。"


def _print_result(result: Mapping[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persona Quality Loop v3")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("path")
    init_parser.add_argument("--generator-context-id", required=True)
    init_parser.add_argument("--runtime", required=True)
    init_parser.add_argument("--runtime-mode", choices=sorted(ALLOWED_RUNTIME_MODES), default="staged-role")
    init_parser.add_argument("--iteration", type=int, default=1)
    init_parser.add_argument("--seed", default="")
    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("path")
    record_parser.add_argument("--run-id", required=True)
    record_parser.add_argument("--responses", required=True)
    record_parser.add_argument("--generic-context-id", required=True)
    record_parser.add_argument("--similar-context-id", required=True)
    record_parser.add_argument("--binding-receipt")
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("path")
    evaluate_parser.add_argument("--run-id", required=True)
    evaluate_parser.add_argument("--evaluation", required=True)
    evaluate_parser.add_argument("--evaluator-context-id", required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("path")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = Path(args.path).expanduser().resolve()
        if args.command == "init":
            result = init_run(root, args.generator_context_id, args.runtime, args.runtime_mode, args.iteration, args.seed)
        elif args.command == "record":
            result = record_responses(
                root, args.run_id, Path(args.responses).expanduser().resolve(),
                args.generic_context_id, args.similar_context_id,
                Path(args.binding_receipt).expanduser().resolve() if args.binding_receipt else None,
            )
        elif args.command == "evaluate":
            result = evaluate_run(
                root, args.run_id, Path(args.evaluation).expanduser().resolve(), args.evaluator_context_id,
            )
        else:
            result = status(root)
        _print_result(result)
        return 0 if result.get("valid", result.get("status") != "repair-required") else 1
    except QualityLoopError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
