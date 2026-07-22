#!/usr/bin/env python3
"""Validate the offline eval corpus and deterministic golden gates.

This does not run Claude Code. It proves the eval catalog is structurally
usable, fixtures exist, slash-skill references resolve, and any saved golden
artifacts still pass the deterministic gates they claim to exercise.

Optional output grading:
    scripts/eval_check.py --outputs-dir evals/runs/2026-06-27

When an outputs dir is supplied, files named <scenario-id>.md are checked
against the scenario's lightweight deterministic output assertions. Missing
outputs are ignored unless --require-all-outputs is set, so a partial manual
eval run can still be checked while it is in progress.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CITATION_RE = re.compile(r"\b[A-Za-z0-9_./-]+\.[A-Za-z0-9_+-]+:\d+(?:-\d+)?\b")
BUDGET_EXCEEDED = "Exceeded USD budget"
PROFILES = {"smoke", "full", "benchmark"}
MAX_CHECK_SUBSTRING_CHARS = 160
IGNORED_STATE_EXCLUDED_DIRS = frozenset({
    ".cache",
    ".gradle",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
})
OUTPUT_CHECK_KEYS = {
    "forbid_citation",
    "forbidden_regexes",
    "forbidden_substrings",
    "require_citation",
    "required_citations",
    "required_substrings",
    "required_substrings_case_insensitive",
    "forbidden_substrings_case_insensitive",
}
SCRIPTED_TURN_KEYS = {
    "event_id",
    "answer",
    "required_previous_output",
}
GIT_CHECK_KEYS = {
    "head_unchanged",
    "branch_unchanged",
    "refs_unchanged",
    "worktrees_unchanged",
    "local_config_unchanged",
    "changed_paths_exact",
    "allowed_changed_path_globs",
}
ARTIFACT_BASE_KEYS = {"type", "path", "path_glob"}
ARTIFACT_TYPES = {
    "architecture_lint",
    "file_contains",
    "json_fields",
    "jsonl_records",
    "path_absent",
    "spec_lint",
}
ARTIFACT_TYPE_KEYS = {
    "architecture_lint": ARTIFACT_BASE_KEYS,
    "file_contains": ARTIFACT_BASE_KEYS | {"substrings", "forbidden_substrings"},
    "json_fields": ARTIFACT_BASE_KEYS | {"equals", "contains", "min_lengths"},
    "jsonl_records": ARTIFACT_BASE_KEYS | {"where", "equals", "contains", "count"},
    "path_absent": {"type", "path"},
    "spec_lint": ARTIFACT_BASE_KEYS,
}

# Golden-gate (gate_checks) vocabulary — deterministic replays over frozen
# artifacts under evals/golden/, run on every CI push (no model call). Each gate
# names a repo-relative path/dir and asserts the verdict its lint/schema yields.
GATE_TYPES = {"architecture_lint", "spec_lint", "plan_lint", "json_fields"}
GATE_TYPE_KEYS = {
    "architecture_lint": {"type", "architecture_dir", "repo_root"},
    "spec_lint": {"type", "spec_dir"},
    "plan_lint": {"type", "plan_dir"},
    "json_fields": {"type", "path", "equals", "contains", "min_lengths"},
}


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def load_scenarios(root: Path) -> dict:
    path = root / "evals" / "scenarios.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("evals/scenarios.json is missing") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"evals/scenarios.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("evals/scenarios.json top level must be an object")
    if data.get("schema_version") != 1:
        raise ValueError("evals/scenarios.json schema_version must be 1")
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("evals/scenarios.json must contain a non-empty scenarios array")
    return data


def invocation_skill_path(root: Path, invocation: str) -> tuple[str, Path]:
    if not invocation.startswith("/"):
        return "core-engineering", root / "__invalid_skill__"
    command = invocation[1:]
    plugin, separator, skill = command.partition(":")
    if not separator or not plugin or not skill.startswith("ce-"):
        return "core-engineering", root / "__invalid_skill__"
    return plugin, skill_path(root, plugin, skill)


def skill_path(root: Path, plugin: str, skill: str) -> Path:
    return root / "plugins" / plugin / "skills" / skill / "SKILL.md"


def validate_catalog(root: Path, scenarios: list[dict]) -> tuple[list[str], int]:
    errors: list[str] = []
    seen: set[str] = set()
    gate_count = 0

    for idx, scenario in enumerate(scenarios):
        prefix = scenario.get("id") or f"<scenario #{idx + 1}>"
        if not isinstance(scenario, dict):
            errors.append(f"{prefix}: scenario entry must be an object")
            continue

        sid = scenario.get("id")
        if not isinstance(sid, str) or not sid:
            errors.append(f"{prefix}: missing non-empty id")
        elif sid in seen:
            errors.append(f"{sid}: duplicate scenario id")
        else:
            seen.add(sid)

        invocation = scenario.get("invocation")
        if not isinstance(invocation, str) or not invocation.startswith("/"):
            errors.append(f"{prefix}: invocation must be a slash-skill string")
            plugin = "core-engineering"
        else:
            plugin, sp_from_invocation = invocation_skill_path(root, invocation)
            if not sp_from_invocation.is_file():
                errors.append(
                    f"{prefix}: skill file not found for invocation {invocation}: "
                    f"{rel(root, sp_from_invocation)}"
                )

        skill = scenario.get("skill")
        if not isinstance(skill, str) or not skill:
            errors.append(f"{prefix}: missing skill")
        else:
            sp = skill_path(root, plugin, skill)
            if not sp.is_file():
                errors.append(f"{prefix}: skill file not found for {skill}: {rel(root, sp)}")
            if isinstance(invocation, str) and invocation.startswith("/"):
                invoked_skill = invocation.rpartition(":")[2]
                if invoked_skill and invoked_skill != skill:
                    errors.append(
                        f"{prefix}: invocation {invocation} does not match skill '{skill}'"
                    )

        fixture = scenario.get("fixture")
        if not isinstance(fixture, str) or not fixture:
            errors.append(f"{prefix}: missing fixture")
            fixture_dir = root / "__missing_fixture__"
        else:
            fixture_dir = root / "evals" / "fixtures" / fixture
            if not fixture_dir.is_dir():
                errors.append(f"{prefix}: fixture not found: {rel(root, fixture_dir)}")

        contract_paths = scenario.get("contract_paths", [])
        if not isinstance(contract_paths, list):
            errors.append(f"{prefix}: contract_paths must be a list")
        else:
            for path_idx, value in enumerate(contract_paths):
                errors.extend(
                    validate_artifact_path(
                        prefix, f"contract_paths.{path_idx}", value
                    )
                )
                if isinstance(value, str) and not (root / value).exists():
                    errors.append(f"{prefix}: contract path does not exist: {value}")

        prompt = scenario.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            errors.append(f"{prefix}: prompt must be a non-empty string")

        scripted_turns = scenario.get("scripted_turns", [])
        if not isinstance(scripted_turns, list):
            errors.append(f"{prefix}: scripted_turns must be a list")
        else:
            event_ids: set[str] = set()
            for turn_idx, turn in enumerate(scripted_turns):
                label = f"scripted_turns.{turn_idx}"
                if not isinstance(turn, dict):
                    errors.append(f"{prefix}: {label} must be an object")
                    continue
                unknown = sorted(set(turn) - SCRIPTED_TURN_KEYS)
                if unknown:
                    errors.append(
                        f"{prefix}: {label} has unknown key(s): {', '.join(unknown)}"
                    )
                event_id = turn.get("event_id")
                if not isinstance(event_id, str) or not event_id.strip():
                    errors.append(f"{prefix}: {label}.event_id must be a non-empty string")
                elif event_id in event_ids:
                    errors.append(f"{prefix}: duplicate scripted event_id {event_id!r}")
                else:
                    event_ids.add(event_id)
                    if isinstance(sid, str) and sid and not event_id.startswith(f"{sid}-"):
                        errors.append(
                            f"{prefix}: {label}.event_id must start with {sid}- "
                            "so decision provenance is scenario-scoped"
                        )
                answer = turn.get("answer")
                if not isinstance(answer, str) or not answer.strip():
                    errors.append(f"{prefix}: {label}.answer must be a non-empty string")
                required = turn.get("required_previous_output")
                errors.extend(
                    validate_check_strings(
                        prefix,
                        f"{label}.required_previous_output",
                        required,
                    )
                )
                if not required:
                    errors.append(
                        f"{prefix}: {label}.required_previous_output must contain at least "
                        "one gate/context anchor before the answer can be sent"
                    )

        profile = scenario.get("profile")
        if profile not in PROFILES:
            errors.append(f"{prefix}: profile must be one of {sorted(PROFILES)}")

        budget = scenario.get("recommended_budget_usd")
        if not isinstance(budget, (int, float)) or budget <= 0:
            errors.append(f"{prefix}: recommended_budget_usd must be a positive number")

        timeout_seconds = scenario.get("timeout_seconds")
        if timeout_seconds is not None and (
            not isinstance(timeout_seconds, int)
            or isinstance(timeout_seconds, bool)
            or timeout_seconds <= 0
        ):
            errors.append(f"{prefix}: timeout_seconds must be a positive integer")

        expected_files = scenario.get("expected_files", [])
        if not isinstance(expected_files, list):
            errors.append(f"{prefix}: expected_files must be a list")
        else:
            for f in expected_files:
                if not isinstance(f, str) or not f:
                    errors.append(f"{prefix}: expected_files entries must be non-empty strings")
                    continue
                p = fixture_dir / f
                if not p.is_file():
                    errors.append(f"{prefix}: expected fixture file missing: {rel(root, p)}")

        gate_checks = scenario.get("gate_checks", [])
        if not isinstance(gate_checks, list):
            errors.append(f"{prefix}: gate_checks must be a list")
        else:
            for gate in gate_checks:
                gate_count += 1
                errors.extend(run_gate(root, prefix, gate))

        errors.extend(validate_output_checks(prefix, scenario.get("output_checks")))
        errors.extend(validate_artifact_checks(prefix, scenario))
        errors.extend(validate_git_checks(prefix, scenario.get("git_checks")))

        if scenario.get("skill") in {"ce-spec", "ce-implement"}:
            legacy_refs: list[str] = []
            if isinstance(expected_files, list):
                legacy_refs.extend(
                    value for value in expected_files
                    if isinstance(value, str) and Path(value).name == "spec.md"
                )
            output_checks = scenario.get("output_checks")
            if isinstance(output_checks, dict):
                required = output_checks.get("required_substrings", [])
                if isinstance(required, list) and "spec.md" in required:
                    legacy_refs.append("output_checks.required_substrings:spec.md")
            artifact_checks = scenario.get("artifact_checks", [])
            if isinstance(artifact_checks, list):
                for check in artifact_checks:
                    if not isinstance(check, dict):
                        continue
                    value = check.get("path") or check.get("path_glob")
                    if isinstance(value, str) and Path(value).name == "spec.md":
                        legacy_refs.append(value)
            if legacy_refs:
                errors.append(
                    f"{prefix}: uses legacy spec.md in its executable contract "
                    f"({', '.join(legacy_refs)}); current /core-engineering:ce-spec and /core-engineering:ce-implement "
                    "scenarios must use canonical ce-spec.md"
                )

    return errors, gate_count


def validate_check_strings(sid: str, label: str, value: object) -> list[str]:
    errors: list[str] = []
    if value is None:
        return errors
    if not isinstance(value, list):
        return [f"{sid}: {label} must be a list"]
    for idx, item in enumerate(value):
        item_label = f"{label}.{idx}"
        if not isinstance(item, str) or not item:
            errors.append(f"{sid}: {item_label} must be a non-empty string")
            continue
        if "\n" in item or "\r" in item:
            errors.append(f"{sid}: {item_label} must be a single-line anchor")
        if len(item) > MAX_CHECK_SUBSTRING_CHARS:
            errors.append(
                f"{sid}: {item_label} is {len(item)} characters; "
                "prefer smaller deterministic anchors over exact prose"
            )
    return errors


def validate_output_checks(sid: str, checks: object) -> list[str]:
    if not isinstance(checks, dict) or not checks:
        return [f"{sid}: output_checks must be a non-empty object"]

    errors: list[str] = []
    unknown = sorted(set(checks) - OUTPUT_CHECK_KEYS)
    if unknown:
        errors.append(f"{sid}: output_checks has unknown key(s): {', '.join(unknown)}")

    require_citation = checks.get("require_citation", False)
    forbid_citation = checks.get("forbid_citation", False)
    if not isinstance(require_citation, bool):
        errors.append(f"{sid}: output_checks.require_citation must be boolean")
    if not isinstance(forbid_citation, bool):
        errors.append(f"{sid}: output_checks.forbid_citation must be boolean")
    if require_citation and forbid_citation:
        errors.append(f"{sid}: output_checks cannot require and forbid citations")

    errors.extend(validate_check_strings(sid, "output_checks.required_substrings",
                                         checks.get("required_substrings")))
    errors.extend(validate_check_strings(sid, "output_checks.forbidden_substrings",
                                         checks.get("forbidden_substrings")))
    errors.extend(validate_check_strings(
        sid,
        "output_checks.required_substrings_case_insensitive",
        checks.get("required_substrings_case_insensitive"),
    ))
    errors.extend(validate_check_strings(
        sid,
        "output_checks.forbidden_substrings_case_insensitive",
        checks.get("forbidden_substrings_case_insensitive"),
    ))
    errors.extend(validate_check_strings(sid, "output_checks.required_citations",
                                         checks.get("required_citations")))

    regexes = checks.get("forbidden_regexes")
    errors.extend(validate_check_strings(sid, "output_checks.forbidden_regexes", regexes))
    if isinstance(regexes, list):
        for idx, pat in enumerate(regexes):
            if not isinstance(pat, str) or not pat:
                continue
            try:
                re.compile(pat)
            except re.error as exc:
                errors.append(f"{sid}: output_checks.forbidden_regexes.{idx} is invalid: {exc}")

    required_citations = checks.get("required_citations", [])
    if required_citations and not require_citation:
        errors.append(f"{sid}: output_checks.required_citations requires require_citation: true")
    if require_citation and not required_citations:
        errors.append(
            f"{sid}: output_checks.require_citation must pin expected files with required_citations"
        )
    if forbid_citation and required_citations:
        errors.append(f"{sid}: output_checks cannot forbid citations and require citation files")
    if isinstance(required_citations, list):
        for idx, path in enumerate(required_citations):
            if not isinstance(path, str) or not path:
                continue
            if ":" in path:
                errors.append(
                    f"{sid}: output_checks.required_citations.{idx} should be a file path "
                    "without a line suffix"
                )

    has_assertion = any(
        checks.get(key)
        for key in (
            "forbid_citation",
            "forbidden_regexes",
            "forbidden_substrings",
            "forbidden_substrings_case_insensitive",
            "require_citation",
            "required_substrings",
            "required_substrings_case_insensitive",
        )
    )
    if not has_assertion:
        errors.append(f"{sid}: output_checks must contain at least one assertion")

    return errors


def validate_git_checks(sid: str, checks: object) -> list[str]:
    if checks is None:
        return []
    if not isinstance(checks, dict) or not checks:
        return [f"{sid}: git_checks must be a non-empty object"]
    errors: list[str] = []
    unknown = sorted(set(checks) - GIT_CHECK_KEYS)
    if unknown:
        errors.append(f"{sid}: git_checks has unknown key(s): {', '.join(unknown)}")
    for key in (
        "head_unchanged",
        "branch_unchanged",
        "refs_unchanged",
        "worktrees_unchanged",
        "local_config_unchanged",
    ):
        if key in checks and checks[key] is not True:
            errors.append(f"{sid}: git_checks.{key} must be true when present")
    for key in ("changed_paths_exact", "allowed_changed_path_globs"):
        if key not in checks:
            continue
        value = checks[key]
        if not isinstance(value, list):
            errors.append(f"{sid}: git_checks.{key} must be a list")
            continue
        for idx, item in enumerate(value):
            errors.extend(validate_artifact_path(sid, f"git_checks.{key}.{idx}", item))
    if "changed_paths_exact" in checks and "allowed_changed_path_globs" in checks:
        errors.append(
            f"{sid}: git_checks cannot combine changed_paths_exact and "
            "allowed_changed_path_globs"
        )
    if not any(
        key in checks
        for key in (
            "head_unchanged",
            "branch_unchanged",
            "refs_unchanged",
            "worktrees_unchanged",
            "local_config_unchanged",
            "changed_paths_exact",
            "allowed_changed_path_globs",
        )
    ):
        errors.append(f"{sid}: git_checks must contain at least one assertion")
    return errors


def validate_artifact_path(sid: str, label: str, value: object) -> list[str]:
    if not isinstance(value, str) or not value:
        return [f"{sid}: {label} must be a non-empty string"]
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return [f"{sid}: {label} must stay inside the eval work dir: {value!r}"]
    return []


def validate_artifact_checks(sid: str, scenario: dict) -> list[str]:
    checks = scenario.get("artifact_checks", [])
    errors: list[str] = []
    if not isinstance(checks, list):
        return [f"{sid}: artifact_checks must be a list"]
    if scenario.get("profile") == "full" and not checks:
        errors.append(f"{sid}: full-profile scenarios must include artifact_checks")
    for idx, check in enumerate(checks):
        label = f"artifact_checks.{idx}"
        if not isinstance(check, dict):
            errors.append(f"{sid}: {label} must be an object")
            continue
        ctype = check.get("type")
        if ctype not in ARTIFACT_TYPES:
            errors.append(f"{sid}: {label}.type has unsupported value {ctype!r}")
            continue

        unknown = sorted(set(check) - ARTIFACT_TYPE_KEYS[ctype])
        if unknown:
            errors.append(f"{sid}: {label} has unknown key(s): {', '.join(unknown)}")

        has_path = "path" in check
        has_glob = "path_glob" in check
        if has_path == has_glob:
            errors.append(f"{sid}: {label} requires exactly one of path or path_glob")
        else:
            key = "path" if has_path else "path_glob"
            errors.extend(validate_artifact_path(sid, f"{label}.{key}", check.get(key)))

        if ctype == "file_contains":
            errors.extend(validate_check_strings(sid, f"{label}.substrings",
                                                 check.get("substrings")))
            errors.extend(validate_check_strings(sid, f"{label}.forbidden_substrings",
                                                 check.get("forbidden_substrings")))
            if not check.get("substrings") and not check.get("forbidden_substrings"):
                errors.append(
                    f"{sid}: {label} must assert substrings or forbidden_substrings"
                )
        elif ctype == "json_fields":
            errors.extend(validate_json_fields_body(sid, label, check))
        elif ctype == "jsonl_records":
            for key in ("where", "equals", "contains"):
                if key in check and not isinstance(check[key], dict):
                    errors.append(f"{sid}: {label}.{key} must be an object")
            if not check.get("where"):
                errors.append(f"{sid}: {label}.where must select at least one field")
            count = check.get("count")
            if type(count) is not int or count < 0:
                errors.append(f"{sid}: {label}.count must be a non-negative integer")
            for key in ("where", "equals", "contains"):
                body = check.get(key, {})
                if isinstance(body, dict):
                    for dotted in body:
                        if not isinstance(dotted, str) or not dotted:
                            errors.append(
                                f"{sid}: {label}.{key} keys must be non-empty strings"
                            )
            contains = check.get("contains", {})
            if isinstance(contains, dict):
                for dotted, items in contains.items():
                    errors.extend(
                        validate_check_strings(sid, f"{label}.contains.{dotted}", items)
                    )

    return errors


def validate_json_fields_body(sid: str, label: str, check: dict) -> list[str]:
    """Shape-validate a json_fields assertion body (equals/contains/min_lengths).

    Shared by artifact_checks and the deterministic json_fields golden gate so a
    frozen-artifact schema assertion is validated identically in both places.
    """
    errors: list[str] = []
    for key in ("equals", "contains", "min_lengths"):
        if key in check and not isinstance(check[key], dict):
            errors.append(f"{sid}: {label}.{key} must be an object")
    if not check.get("equals") and not check.get("contains") and not check.get("min_lengths"):
        errors.append(f"{sid}: {label} must assert equals, contains, or min_lengths")
    contains = check.get("contains", {})
    if isinstance(contains, dict):
        for dotted, items in contains.items():
            if not isinstance(dotted, str) or not dotted:
                errors.append(f"{sid}: {label}.contains keys must be non-empty strings")
                continue
            errors.extend(validate_check_strings(
                sid, f"{label}.contains.{dotted}", items
            ))
    min_lengths = check.get("min_lengths", {})
    if isinstance(min_lengths, dict):
        for dotted, expected in min_lengths.items():
            if not isinstance(dotted, str) or not dotted:
                errors.append(f"{sid}: {label}.min_lengths keys must be non-empty strings")
            if not isinstance(expected, int) or expected < 0:
                errors.append(
                    f"{sid}: {label}.min_lengths.{dotted} "
                    "must be a non-negative integer"
                )
    return errors


def validate_gate_path(sid: str, label: str, value: object) -> list[str]:
    """A golden-gate path is repo-relative and stays inside the checkout."""
    if not isinstance(value, str) or not value:
        return [f"{sid}: {label} must be a non-empty string"]
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return [f"{sid}: {label} must be a repo-relative path inside the checkout: {value!r}"]
    return []


def run_gate(root: Path, sid: str, gate: object) -> list[str]:
    """Validate and replay one deterministic golden gate over a frozen artifact.

    Both a catalog validator and a runner: shape errors and replay failures come
    back in the same list (empty == the frozen artifact still passes its gate).
    """
    if not isinstance(gate, dict):
        return [f"{sid}: gate check must be an object"]
    gtype = gate.get("type")
    if gtype not in GATE_TYPES:
        return [f"{sid}: unsupported gate type {gtype!r}"]
    unknown = sorted(set(gate) - GATE_TYPE_KEYS[gtype])
    if unknown:
        return [f"{sid}: {gtype} gate has unknown key(s): {', '.join(unknown)}"]
    if gtype == "spec_lint":
        return run_spec_lint_gate(root, sid, gate)
    if gtype == "plan_lint":
        return run_plan_lint_gate(root, sid, gate)
    if gtype == "architecture_lint":
        return run_architecture_lint_gate(root, sid, gate)
    return run_json_fields_gate(root, sid, gate)


def run_spec_lint_gate(root: Path, sid: str, gate: dict) -> list[str]:
    spec_dir = gate.get("spec_dir")
    errors = validate_gate_path(sid, "spec_lint gate spec_dir", spec_dir)
    if errors:
        return errors
    path = root / spec_dir
    if not path.is_dir():
        return [f"{sid}: spec_lint spec_dir not found: {rel(root, path)}"]
    return run_spec_lint(root, sid, path, f"gate {rel(root, path)}")


def run_plan_lint_gate(root: Path, sid: str, gate: dict) -> list[str]:
    plan_dir = gate.get("plan_dir")
    errors = validate_gate_path(sid, "plan_lint gate plan_dir", plan_dir)
    if errors:
        return errors
    path = root / plan_dir
    if not path.is_dir():
        return [f"{sid}: plan_lint plan_dir not found: {rel(root, path)}"]
    return run_plan_lint(root, sid, path, f"gate {rel(root, path)}")


def run_architecture_lint_gate(root: Path, sid: str, gate: dict) -> list[str]:
    architecture_dir = gate.get("architecture_dir")
    repo_root = gate.get("repo_root")
    errors = validate_gate_path(
        sid, "architecture_lint gate architecture_dir", architecture_dir
    )
    errors.extend(
        validate_gate_path(sid, "architecture_lint gate repo_root", repo_root)
    )
    if errors:
        return errors
    path = root / architecture_dir
    source_root = root / repo_root
    if not path.is_dir():
        return [
            f"{sid}: architecture_lint architecture_dir not found: {rel(root, path)}"
        ]
    if not source_root.is_dir():
        return [
            f"{sid}: architecture_lint repo_root not found: {rel(root, source_root)}"
        ]
    return run_architecture_lint(
        root,
        sid,
        path,
        source_root,
        f"gate {rel(root, path)}",
    )


def run_json_fields_gate(root: Path, sid: str, gate: dict) -> list[str]:
    path_str = gate.get("path")
    errors = validate_gate_path(sid, "json_fields gate path", path_str)
    if errors:
        return errors
    errors = validate_json_fields_body(sid, "json_fields gate", gate)
    if errors:
        return errors
    path = root / path_str
    if not path.is_file():
        return [f"{sid}: json_fields gate path not found: {rel(root, path)}"]
    return grade_artifact_target(root, sid, gate, "json_fields", path)


def run_spec_lint(root: Path, sid: str, path: Path, label: str) -> list[str]:
    script = root / "plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(path), "--json"],
        capture_output=True,
        text=True,
        cwd=root,
        timeout=30,
    )
    if proc.returncode != 0:
        detail = (proc.stdout or proc.stderr).strip().splitlines()
        msg = detail[0] if detail else f"exit {proc.returncode}"
        return [f"{sid}: spec_lint failed for {label}: {msg}"]
    return []


def run_plan_lint(root: Path, sid: str, path: Path, label: str) -> list[str]:
    """Replay a frozen plan dir through the canonical plan-lint.py.

    exit 0 = structurally well-formed (PASS); 1 = a hard structural failure;
    2 = un-runnable. Any non-zero exit fails the gate. The first hard failure
    (or error message) is surfaced so a mutated golden names its own break.
    """
    script = root / "plugins/core-engineering/skills/ce-plan-audit/scripts/plan-lint.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(path), "--json"],
        capture_output=True,
        text=True,
        cwd=root,
        timeout=30,
    )
    if proc.returncode == 0:
        return []
    msg = f"exit {proc.returncode}"
    try:
        data = json.loads(proc.stdout)
        if isinstance(data, dict):
            if data.get("hard_failures"):
                msg = str(data["hard_failures"][0])
            elif data.get("message"):
                msg = str(data["message"])
    except (json.JSONDecodeError, ValueError):
        detail = (proc.stdout or proc.stderr).strip().splitlines()
        if detail:
            msg = detail[0]
    return [f"{sid}: plan_lint failed for {label}: {msg}"]


def run_architecture_lint(
    root: Path,
    sid: str,
    path: Path,
    repo_root: Path,
    label: str,
) -> list[str]:
    """Replay a ce-architecture package through its deterministic lint."""
    script = (
        root
        / "plugins/core-engineering/skills/ce-architecture/scripts/architecture-lint.py"
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            str(path),
            "--repo-root",
            str(repo_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=root,
        timeout=30,
    )
    if proc.returncode == 0:
        return []
    msg = f"exit {proc.returncode}"
    try:
        data = json.loads(proc.stdout)
        if isinstance(data, dict):
            if data.get("hard_failures"):
                msg = str(data["hard_failures"][0])
            elif data.get("error"):
                msg = str(data["error"])
    except (json.JSONDecodeError, ValueError):
        detail = (proc.stdout or proc.stderr).strip().splitlines()
        if detail:
            msg = detail[0]
    return [f"{sid}: architecture_lint failed for {label}: {msg}"]


def load_run_records(outputs_dir: Path) -> dict:
    metadata = outputs_dir / "metadata.json"
    if not metadata.is_file():
        return {}
    try:
        data = json.loads(metadata.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    records = data.get("records")
    if not isinstance(records, list):
        return {}
    return {r.get("id"): r for r in records if isinstance(r, dict) and r.get("id")}


def grade_outputs(root: Path, scenarios: list[dict], outputs_dir: Path,
                  require_all: bool) -> tuple[list[str], int]:
    errors: list[str] = []
    graded = 0
    run_records = load_run_records(outputs_dir)
    required_ids = set(run_records) if run_records else {s["id"] for s in scenarios}

    for scenario in scenarios:
        sid = scenario["id"]
        out = outputs_dir / f"{sid}.md"
        if not out.is_file():
            if require_all and sid in required_ids:
                errors.append(f"{sid}: missing output file {rel(root, out)}")
            continue
        record = run_records.get(sid)
        if isinstance(record, dict) and record.get("status") == "failed":
            captured = ""
            try:
                captured = out.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                pass
            captured_first = captured.splitlines()[0] if captured else ""
            kind = record.get("failure_kind") or (
                "budget-exceeded" if BUDGET_EXCEEDED in captured else "claude-error"
            )
            msg = record.get("failure_message") or captured_first or f"returncode {record.get('returncode')}"
            errors.append(f"{sid}: run failed before output grading ({kind}: {msg})")
            continue
        graded += 1
        try:
            text = out.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{sid}: output is not UTF-8: {exc}")
            continue
        checks = scenario.get("output_checks", {})
        if not isinstance(checks, dict):
            errors.append(f"{sid}: output_checks must be an object")
            continue
        errors.extend(grade_one_output(sid, text, checks))
        errors.extend(grade_artifacts(root, outputs_dir, scenario, record))
        errors.extend(grade_git_state(root, outputs_dir, scenario, record))

    return errors, graded


def grade_one_output(sid: str, text: str, checks: dict) -> list[str]:
    errors: list[str] = []
    for item in checks.get("required_substrings", []):
        if item not in text:
            errors.append(f"{sid}: output missing required text {item!r}")
    for item in checks.get("forbidden_substrings", []):
        if item in text:
            errors.append(f"{sid}: output contains forbidden text {item!r}")
    folded_text = text.casefold()
    for item in checks.get("required_substrings_case_insensitive", []):
        if item.casefold() not in folded_text:
            errors.append(f"{sid}: output missing semantic text {item!r}")
    for item in checks.get("forbidden_substrings_case_insensitive", []):
        if item.casefold() in folded_text:
            errors.append(f"{sid}: output contains forbidden semantic text {item!r}")
    for pat in checks.get("forbidden_regexes", []):
        if re.search(pat, text, re.MULTILINE):
            errors.append(f"{sid}: output matched forbidden regex {pat!r}")
    if checks.get("require_citation") and not CITATION_RE.search(text):
        errors.append(f"{sid}: output has no file:line citation")
    for path in checks.get("required_citations", []):
        pat = re.compile(
            rf"(?<![A-Za-z0-9_./-])(?:\./)?{re.escape(path)}:\d+(?:-\d+)?\b"
        )
        if not pat.search(text):
            errors.append(f"{sid}: output missing citation for {path}")
    if checks.get("forbid_citation") and CITATION_RE.search(text):
        errors.append(f"{sid}: output should not contain file:line citations")
    return errors


def capture_git_state(work_dir: Path) -> dict:
    git_env = os.environ.copy()
    for key in [name for name in git_env if name.startswith("GIT_")]:
        del git_env[key]

    def read(*args: str, allow_nonzero: bool = False) -> str:
        proc = subprocess.run(
            ["git", "-C", str(work_dir), *args],
            capture_output=True,
            text=True,
            timeout=30,
            env=git_env,
        )
        if proc.returncode != 0 and not allow_nonzero:
            detail = proc.stderr.strip() or proc.stdout.strip() or f"git exited {proc.returncode}"
            raise ValueError(detail)
        return proc.stdout

    branch = read("symbolic-ref", "--quiet", "--short", "HEAD", allow_nonzero=True).strip() or None
    local_config = read("config", "--local", "--list", "--null")
    changed = {
        path for path in read("diff", "--name-only", "-z", "HEAD").split("\0") if path
    }
    changed.update(
        path
        for path in read("ls-files", "--others", "--exclude-standard", "-z").split("\0")
        if path
    )
    ignored_files_sha256: dict[str, str] = {}
    ignored_paths = (
        path
        for path in read(
            "ls-files", "--others", "--ignored", "--exclude-standard", "-z"
        ).split("\0")
        if path
    )
    for relative_path in ignored_paths:
        if any(
            part in IGNORED_STATE_EXCLUDED_DIRS
            for part in Path(relative_path).parts
        ):
            continue
        path = work_dir / relative_path
        digest = hashlib.sha256()
        try:
            if path.is_symlink():
                digest.update(b"symlink\0")
                digest.update(os.fsencode(os.readlink(path)))
            elif path.is_file():
                digest.update(b"file\0")
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            else:
                continue
        except OSError as exc:
            raise ValueError(
                f"could not hash ignored eval fixture path {relative_path!r}: {exc}"
            ) from exc
        ignored_files_sha256[relative_path] = digest.hexdigest()
    return {
        "head": read("rev-parse", "HEAD").strip(),
        "branch": branch,
        "refs": sorted(
            line
            for line in read("for-each-ref", "--format=%(objectname) %(refname)").splitlines()
            if line
        ),
        "worktrees": [
            line for line in read("worktree", "list", "--porcelain").splitlines() if line
        ],
        "local_config_sha256": hashlib.sha256(local_config.encode("utf-8")).hexdigest(),
        "changed_paths": sorted(changed),
        "ignored_files_sha256": dict(sorted(ignored_files_sha256.items())),
    }


def grade_git_state(root: Path, outputs_dir: Path, scenario: dict, record: object) -> list[str]:
    sid = scenario["id"]
    checks = scenario.get("git_checks")
    if not checks:
        return []
    if not isinstance(record, dict):
        return [f"{sid}: git_checks require eval_run metadata"]
    state = record.get("git_state")
    if not isinstance(state, dict):
        return [f"{sid}: git_checks require git_state metadata"]
    before = state.get("before")
    after = state.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        detail = state.get("capture_error") or "missing before/after snapshot"
        return [f"{sid}: git_state metadata is incomplete ({detail})"]
    base = resolve_artifact_base(root, outputs_dir, sid, record)
    if base is None:
        return [f"{sid}: git_checks require eval_run metadata with work_dir"]
    try:
        current = capture_git_state(base)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return [f"{sid}: could not inspect final Git state: {exc}"]

    errors: list[str] = []
    if current != after:
        errors.append(f"{sid}: worktree changed after the runner captured its final Git state")
    if checks.get("head_unchanged") and current.get("head") != before.get("head"):
        errors.append(f"{sid}: Git HEAD changed during the eval run")
    if checks.get("branch_unchanged") and current.get("branch") != before.get("branch"):
        errors.append(f"{sid}: current Git branch changed during the eval run")
    if checks.get("refs_unchanged") and current.get("refs") != before.get("refs"):
        errors.append(f"{sid}: Git refs changed during the eval run")
    if checks.get("worktrees_unchanged") and current.get("worktrees") != before.get("worktrees"):
        errors.append(f"{sid}: Git worktree set changed during the eval run")
    if (
        checks.get("local_config_unchanged")
        and current.get("local_config_sha256") != before.get("local_config_sha256")
    ):
        errors.append(f"{sid}: local Git config changed during the eval run")

    visible_paths = current.get("changed_paths")
    if not isinstance(visible_paths, list):
        errors.append(f"{sid}: final Git snapshot has no changed_paths list")
        return errors
    before_ignored = before.get("ignored_files_sha256")
    after_ignored = after.get("ignored_files_sha256")
    current_ignored = current.get("ignored_files_sha256")
    if not all(
        isinstance(snapshot, dict)
        for snapshot in (before_ignored, after_ignored, current_ignored)
    ):
        errors.append(
            f"{sid}: Git snapshots have no ignored_files_sha256 map; "
            "ignored-path write coverage is unavailable"
        )
        return errors
    ignored_changed_paths = {
        path
        for path in set(before_ignored) | set(current_ignored)
        if before_ignored.get(path) != current_ignored.get(path)
    }
    actual_paths = sorted(set(visible_paths) | ignored_changed_paths)
    if "changed_paths_exact" in checks:
        expected = sorted(checks.get("changed_paths_exact", []))
        if actual_paths != expected:
            errors.append(
                f"{sid}: final changed paths {actual_paths!r}, expected exactly {expected!r}"
            )
    allowed = checks.get("allowed_changed_path_globs")
    if isinstance(allowed, list):
        unexpected = [
            path for path in actual_paths
            if not any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed)
        ]
        if unexpected:
            errors.append(f"{sid}: final changed paths outside the allowed set: {unexpected!r}")
    return errors


def resolve_artifact_base(root: Path, outputs_dir: Path, sid: str, record: object) -> Path | None:
    if isinstance(record, dict):
        work_dir = record.get("work_dir")
        if isinstance(work_dir, str) and work_dir:
            p = Path(work_dir)
            return p if p.is_absolute() else root / p
    candidate = outputs_dir / "work" / sid
    return candidate if candidate.is_dir() else None


def value_at_path(data, dotted: str):
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError) as exc:
                raise KeyError(dotted) from exc
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(dotted)
    return cur


def artifact_targets(root: Path, sid: str, base: Path, check: dict) -> tuple[list[Path], list[str]]:
    has_path = "path" in check
    has_glob = "path_glob" in check
    if has_path == has_glob:
        return [], [f"{sid}: artifact check requires exactly one of path or path_glob"]

    if has_path:
        rel_path = check.get("path")
        if not isinstance(rel_path, str) or not rel_path:
            return [], [f"{sid}: artifact check requires path"]
        return [base / rel_path], []

    pattern = check.get("path_glob")
    if not isinstance(pattern, str) or not pattern:
        return [], [f"{sid}: artifact check requires path_glob"]
    pattern_path = Path(pattern)
    if pattern_path.is_absolute() or ".." in pattern_path.parts:
        return [], [f"{sid}: artifact path_glob must stay inside the work dir: {pattern!r}"]
    matches = sorted(base.glob(pattern))
    if not matches:
        return [], [f"{sid}: artifact glob matched no files: {rel(root, base / pattern)}"]
    return matches, []


def grade_artifacts(root: Path, outputs_dir: Path, scenario: dict, record: object) -> list[str]:
    sid = scenario["id"]
    checks = scenario.get("artifact_checks", [])
    errors: list[str] = []
    if not checks:
        return errors
    if not isinstance(checks, list):
        return [f"{sid}: artifact_checks must be a list"]
    base = resolve_artifact_base(root, outputs_dir, sid, record)
    if base is None:
        return [f"{sid}: artifact_checks require eval_run metadata with work_dir"]

    for check in checks:
        if not isinstance(check, dict):
            errors.append(f"{sid}: artifact check must be an object")
            continue
        ctype = check.get("type")
        targets, target_errors = artifact_targets(root, sid, base, check)
        errors.extend(target_errors)
        if target_errors:
            continue
        for path in targets:
            errors.extend(
                grade_artifact_target(
                    root,
                    sid,
                    check,
                    ctype,
                    path,
                    artifact_repo_root=base,
                )
            )

    return errors


def grade_artifact_target(
    root: Path,
    sid: str,
    check: dict,
    ctype: object,
    path: Path,
    artifact_repo_root: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    if ctype == "path_absent":
        if path.exists() or path.is_symlink():
            return [
                f"{sid}: artifact path must remain absent before human approval: "
                f"{rel(root, path)}"
            ]
        return []

    if ctype == "architecture_lint":
        if not path.is_dir():
            return [f"{sid}: artifact architecture dir missing: {rel(root, path)}"]
        if artifact_repo_root is None:
            return [f"{sid}: architecture_lint artifact requires an eval work root"]
        return run_architecture_lint(
            root,
            sid,
            path,
            artifact_repo_root,
            f"artifact {rel(root, path)}",
        )

    if ctype == "spec_lint":
        if not path.is_dir():
            return [f"{sid}: artifact spec dir missing: {rel(root, path)}"]
        return run_spec_lint(root, sid, path, f"artifact {rel(root, path)}")

    if ctype == "file_contains":
        if not path.is_file():
            return [f"{sid}: artifact missing: {rel(root, path)}"]
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            return [f"{sid}: artifact {rel(root, path)} is not UTF-8: {exc}"]
        for item in check.get("substrings", []):
            if item not in text:
                errors.append(f"{sid}: artifact {rel(root, path)} missing text {item!r}")
        for item in check.get("forbidden_substrings", []):
            if item in text:
                errors.append(f"{sid}: artifact {rel(root, path)} contains forbidden text {item!r}")
        return errors

    if ctype == "json_fields":
        if not path.is_file():
            return [f"{sid}: artifact missing: {rel(root, path)}"]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return [f"{sid}: artifact {rel(root, path)} is not valid JSON: {exc}"]
        for dotted, expected in check.get("equals", {}).items():
            try:
                actual = value_at_path(data, dotted)
            except KeyError:
                errors.append(f"{sid}: artifact {rel(root, path)} missing JSON field {dotted}")
                continue
            if actual != expected:
                errors.append(
                    f"{sid}: artifact {rel(root, path)} field {dotted} = {actual!r}, "
                    f"expected {expected!r}"
                )
        for dotted, items in check.get("contains", {}).items():
            try:
                actual = str(value_at_path(data, dotted))
            except KeyError:
                errors.append(f"{sid}: artifact {rel(root, path)} missing JSON field {dotted}")
                continue
            for item in items:
                if item not in actual:
                    errors.append(
                        f"{sid}: artifact {rel(root, path)} field {dotted} missing text {item!r}"
                    )
        for dotted, expected in check.get("min_lengths", {}).items():
            try:
                actual = value_at_path(data, dotted)
            except KeyError:
                errors.append(f"{sid}: artifact {rel(root, path)} missing JSON field {dotted}")
                continue
            try:
                actual_len = len(actual)
            except TypeError:
                errors.append(f"{sid}: artifact {rel(root, path)} field {dotted} has no length")
                continue
            if actual_len < expected:
                errors.append(
                    f"{sid}: artifact {rel(root, path)} field {dotted} length {actual_len}, "
                    f"expected at least {expected}"
                )
        return errors

    if ctype == "jsonl_records":
        if not path.is_file():
            return [f"{sid}: artifact missing: {rel(root, path)}"]
        records: list[dict] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            for line_no, line in enumerate(lines, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    return [
                        f"{sid}: artifact {rel(root, path)} line {line_no} "
                        "must be a JSON object"
                    ]
                records.append(value)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return [f"{sid}: artifact {rel(root, path)} is not valid JSONL: {exc}"]

        def matches(record: dict) -> bool:
            for dotted, expected in check.get("where", {}).items():
                try:
                    if value_at_path(record, dotted) != expected:
                        return False
                except KeyError:
                    return False
            return True

        selected = [record for record in records if matches(record)]
        expected_count = check.get("count")
        if len(selected) != expected_count:
            errors.append(
                f"{sid}: artifact {rel(root, path)} matched {len(selected)} JSONL "
                f"record(s), expected {expected_count}"
            )
        for record in selected:
            for dotted, expected in check.get("equals", {}).items():
                try:
                    actual = value_at_path(record, dotted)
                except KeyError:
                    errors.append(
                        f"{sid}: artifact {rel(root, path)} matched record missing "
                        f"field {dotted}"
                    )
                    continue
                if actual != expected:
                    errors.append(
                        f"{sid}: artifact {rel(root, path)} matched record field "
                        f"{dotted} = {actual!r}, expected {expected!r}"
                    )
            for dotted, items in check.get("contains", {}).items():
                try:
                    actual = str(value_at_path(record, dotted))
                except KeyError:
                    errors.append(
                        f"{sid}: artifact {rel(root, path)} matched record missing "
                        f"field {dotted}"
                    )
                    continue
                for item in items:
                    if item not in actual:
                        errors.append(
                            f"{sid}: artifact {rel(root, path)} matched record field "
                            f"{dotted} missing text {item!r}"
                        )
        return errors

    return [f"{sid}: unsupported artifact check type {ctype!r}"]


COVERAGE_ALLOWLIST_REL = Path("evals") / "coverage-allowlist.json"
PLUGINS_REL = Path("plugins")


def all_skill_names(root: Path) -> list[str]:
    """Every shipped skill across every marketplace plugin — the coverage
    ratchet spans plugins, so a second plugin's skills need a scenario or a
    waiver too (waivers are skill-keyed, so they stay valid after a move)."""
    names: set[str] = set()
    for skills_dir in sorted((root / PLUGINS_REL).glob("*/skills")):
        if not skills_dir.is_dir():
            continue
        for entry in skills_dir.iterdir():
            if (entry / "SKILL.md").is_file():
                names.add(entry.name)
    return sorted(names)


def validate_burndown_schedule(raw: object, require: bool, errors: list) -> dict:
    """Validate the staggered waiver-expiry schedule; return {date: max_waivers}.

    The schedule turns the coverage waivers from a single-date cliff into a
    ratchet: every live waiver's expiry must land on one of these dated tiers —
    each keyed to a concrete unblocker — and no tier may carry more waivers than
    its ``max_waivers`` cap. A missing/empty schedule while waivers exist is
    itself an error, so the burn-down can't silently regress to a cliff.
    """
    from datetime import date

    caps: dict = {}
    label = str(COVERAGE_ALLOWLIST_REL)
    schedule = raw.get("burndown_schedule") if isinstance(raw, dict) else None
    if not isinstance(schedule, list) or not schedule:
        if require:
            errors.append(
                f"{label}: burndown_schedule must be a non-empty list of dated "
                "tiers (each with date, unblocker, max_waivers) so waivers "
                "stagger across a schedule instead of forming a single-date cliff"
            )
        return caps
    for idx, tier in enumerate(schedule):
        tlabel = f"{label}: burndown_schedule[{idx}]"
        if not isinstance(tier, dict):
            errors.append(f"{tlabel} must be an object")
            continue
        d = tier.get("date")
        try:
            date.fromisoformat(str(d))
            d_ok = True
        except (TypeError, ValueError):
            errors.append(f"{tlabel}.date must be YYYY-MM-DD (got {d!r})")
            d_ok = False
        unblocker = tier.get("unblocker")
        if not isinstance(unblocker, str) or not unblocker.strip():
            errors.append(f"{tlabel} needs a non-empty unblocker naming what lands the eval")
        cap = tier.get("max_waivers")
        if isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0:
            errors.append(f"{tlabel}.max_waivers must be a positive integer")
            cap = None
        if d_ok:
            if str(d) in caps:
                errors.append(f"{tlabel}.date {d} is duplicated; each tier needs a distinct date")
            elif cap is not None:
                caps[str(d)] = cap
    return caps


def check_skill_coverage(root: Path, scenarios: list, errors: list) -> int:
    """Eval-coverage ratchet: every shipped skill has a scenario, or a waiver
    with a reason and an expiry date in evals/coverage-allowlist.json.

    An expired waiver fails loudly — coverage can only be deferred consciously
    and temporarily, never frozen by a permanent allowlist. A waiver for a
    skill that gained a scenario (or no longer exists) is stale and fails too,
    so the allowlist can only shrink toward zero. Every live waiver's expiry
    must also land on a dated tier in ``burndown_schedule`` and stay within that
    tier's ``max_waivers`` cap, so the burn-down is staggered, not a cliff.
    """
    from datetime import date

    skills = all_skill_names(root)
    if not skills:
        errors.append("coverage: no skills found under plugins/*/skills — glob root missing?")
        return 0
    covered = {s.get("skill") for s in scenarios if isinstance(s, dict)}

    path = root / COVERAGE_ALLOWLIST_REL
    raw: object = {}
    waivers: list = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        waivers = raw.get("waivers", []) if isinstance(raw, dict) else []
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{rel(root, path)}: unreadable: {exc}")

    by_skill: dict = {}
    for waiver in waivers:
        if not isinstance(waiver, dict) or not waiver.get("skill"):
            errors.append(f"{rel(root, path)}: waiver entries must be objects with a skill")
            continue
        by_skill[waiver["skill"]] = waiver

    caps = validate_burndown_schedule(raw, bool(by_skill), errors)

    today = date.today()
    checked = 0
    tier_counts: dict = {}
    for skill in skills:
        checked += 1
        if skill in covered:
            continue
        waiver = by_skill.get(skill)
        if waiver is None:
            errors.append(
                f"coverage: {skill} has no eval scenario and no waiver in "
                f"{COVERAGE_ALLOWLIST_REL} — add a scenario, or a waiver with a "
                "reason and an expires date (the ratchet only defers, never forgets)"
            )
            continue
        reason = waiver.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"coverage: waiver for {skill} has no reason")
        expires = waiver.get("expires")
        try:
            expires_date = date.fromisoformat(str(expires))
        except (TypeError, ValueError):
            errors.append(
                f"coverage: waiver for {skill} needs expires: YYYY-MM-DD (got {expires!r})"
            )
            continue
        if expires_date < today:
            errors.append(
                f"coverage: waiver for {skill} expired {expires} — write the "
                "eval scenario or consciously renew the waiver"
            )
        if caps and str(expires) not in caps:
            errors.append(
                f"coverage: waiver for {skill} expires {expires}, which is not a "
                f"scheduled burn-down tier ({', '.join(sorted(caps))}) — move it "
                "onto a dated tier so coverage stays a ratchet, not a cliff"
            )
        else:
            tier_counts[str(expires)] = tier_counts.get(str(expires), 0) + 1
    for tier_date, count in sorted(tier_counts.items()):
        cap = caps.get(tier_date)
        if cap is not None and count > cap:
            errors.append(
                f"coverage: burn-down tier {tier_date} carries {count} live "
                f"waivers, over its max_waivers cap of {cap} — stagger the "
                "burn-down across more tiers instead of piling onto one date"
            )
    for skill in sorted(by_skill):
        if skill in covered:
            errors.append(
                f"coverage: waiver for {skill} is stale — the skill now has a "
                "scenario; delete the waiver"
            )
        elif skill not in skills:
            errors.append(f"coverage: waiver names unknown skill {skill!r}")
    return checked


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate eval scenario metadata, fixtures, golden gates, and optional saved outputs.")
    parser.add_argument("--root", default=str(ROOT), help="repository root")
    parser.add_argument("--outputs-dir", help="directory containing <scenario-id>.md outputs to grade")
    parser.add_argument("--require-all-outputs", action="store_true",
                        help="with --outputs-dir, fail if any scenario output is missing")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        data = load_scenarios(root)
    except ValueError as exc:
        print(f"eval-check: ERROR — {exc}", file=sys.stderr)
        return 2

    scenarios = data["scenarios"]
    errors, gate_count = validate_catalog(root, scenarios)
    check_skill_coverage(root, scenarios, errors)
    graded = 0
    if args.outputs_dir:
        out_dir = (root / args.outputs_dir).resolve()
        if not out_dir.is_dir():
            errors.append(f"outputs-dir not found: {rel(root, out_dir)}")
        else:
            output_errors, graded = grade_outputs(root, scenarios, out_dir,
                                                  args.require_all_outputs)
            errors.extend(output_errors)

    if errors:
        print(f"eval-check: FAIL — {len(errors)} issue(s):\n", file=sys.stderr)
        for error in errors:
            print(f"  x {error}", file=sys.stderr)
        return 1

    suffix = f", {graded} output(s) graded" if args.outputs_dir else ""
    print(f"eval-check: OK — {len(scenarios)} scenario(s), {gate_count} golden gate(s){suffix}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
