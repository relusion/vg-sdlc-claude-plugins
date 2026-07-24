#!/usr/bin/env python3
"""Derive and verify the architecture context bound into a feature specification.

The context is deliberately small and deterministic. It binds the producer-verified
package receipt from the current consumer-linted architecture manifest, the exact
plan/feature/direction/ADR authority contract, the plan and architecture revisions,
and one normalized per-feature id slice. When no package is applicable, the same
schema records a typed absence without dropping source authority or identity.

Commands:

  architecture_context.py derive <plan-dir> <feature-id> --json
  architecture_context.py check <spec-dir> [--plan-dir ...] [--feature ...] --json
  architecture_context.py review-binding <spec-dir> [...] --json

Exit codes follow the repository's 0/1/2 gate contract:

  0  valid/current
  1  structurally valid inputs were checked and differ
  2  inputs could not be read or trusted
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


CONTEXT_SCHEMA_VERSION = 2
MAPPING_KEYS = (
    "drivers",
    "actors",
    "components",
    "relationships",
    "deployments",
    "data",
    "flows",
    "dynamic",
    "transitions",
    "security",
    "contracts",
    "quality",
    "operations",
    "decisions",
    "questions",
    "risks",
    "gaps",
)
V2_MAPPING_ID_FIELDS = (
    "direction_realization_ids",
    "driver_ids",
    "actor_ids",
    "context_relationship_ids",
    "component_ids",
    "relationship_ids",
    "deployment_node_ids",
    "deployment_ids",
    "deployment_connection_ids",
    "data_ids",
    "integration_ids",
    "dynamic_scenario_ids",
    "trust_boundary_ids",
    "security_realization_ids",
    "contract_realization_ids",
    "transition_ids",
    "quality_ids",
    "operation_ids",
    "decision_ids",
    "open_question_ids",
    "risk_ids",
    "gap_ids",
)
CONTEXT_MODES = {
    "package",
    "not-required",
    "recommended-absent",
}
CONTEXT_KEYS = {
    "schema_version",
    "project_slug",
    "feature_id",
    "plan_contract_sha256",
    "mode",
    "package_path",
    "plan_revision",
    "architecture_revision",
    "package_receipt_sha256",
    "feature_mapping_sha256",
    "mapped_ids",
    "reason",
}
BINDING_KEYS = {
    "plan_sha256",
    "feature_sha256",
    "spec_sha256",
    "tasks_sha256",
    "architecture_context_sha256",
    "architecture_package_receipt_sha256",
    "implementation_files_sha256",
    "repository_state_sha256",
    "commit_sha",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SELECTED_DIRECTION_STATUS = "direction-selected"
COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
PROJECT_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_CONTEXT_RE = re.compile(
    r"(?ms)^## Architecture Context[ \t]*\n+"
    r"```json[ \t]+architecture-context[ \t]*\n"
    r"(.*?)\n```[ \t]*$"
)
class ContextError(Exception):
    """The architecture context could not be derived or checked."""


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def object_sha256(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ContextError(f"{label} must be a regular non-symlink file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContextError(f"{label} is unreadable or invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ContextError(f"{label} must contain a JSON object")
    return value


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _repo_relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ContextError(f"path escapes repository root: {path}") from exc


def _occupies(path: Path) -> bool:
    """Lstat-style namespace occupancy, including broken symlinks."""
    return path.exists() or path.is_symlink()


def _regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ContextError(f"{label} must be a regular non-symlink file: {path}")
    return path


def _full_plan_contract_sha256(
    *,
    plan: dict,
    plan_path: Path,
    plan_dir: Path,
    repo_root: Path,
    project_slug: str,
    feature_id: str,
) -> str:
    """Bind every full-plan authority that can invalidate a feature spec.

    Stage-0 plan/selection lint establishes semantic validity. This digest makes
    that exact validated state durable, including changes which do not bump the
    manually maintained plan revision.
    """
    features = plan.get("features")
    if not isinstance(features, list):
        raise ContextError("plan.json features must be a list")
    matches = [
        row
        for row in features
        if isinstance(row, dict) and row.get("id") == feature_id
    ]
    if len(matches) != 1:
        raise ContextError(
            f"plan feature {feature_id!r} must occur exactly once (found {len(matches)})"
        )
    feature_rel = matches[0].get("file")
    if not isinstance(feature_rel, str) or not feature_rel.strip():
        raise ContextError("plan feature file must be a non-empty relative path")
    feature_relative = Path(feature_rel)
    feature_path = plan_dir / feature_relative
    if (
        feature_relative.is_absolute()
        or ".." in feature_relative.parts
        or not _inside(plan_dir, feature_path)
    ):
        raise ContextError(f"plan feature path is unsafe: {feature_rel!r}")
    _regular_file(feature_path, "feature authority")

    selection_path = _regular_file(
        plan_dir / "architecture-selection.json",
        "architecture-selection.json",
    )
    posture = plan.get("architecture_disposition")
    if not isinstance(posture, dict):
        raise ContextError("full plan requires architecture_disposition")
    convergence = posture.get("convergence")
    if not isinstance(convergence, dict):
        raise ContextError("architecture_disposition.convergence must be an object")
    decision_refs = convergence.get("decision_refs")
    if not isinstance(decision_refs, list):
        raise ContextError(
            "architecture_disposition.convergence.decision_refs must be a list"
        )
    ref_records: list[dict] = []
    seen_refs: set[str] = set()
    for raw in decision_refs:
        if not isinstance(raw, str) or not raw.strip():
            raise ContextError("decision_refs entries must be non-empty strings")
        relative = Path(raw)
        candidate = repo_root / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or raw in seen_refs
            or not _inside(repo_root, candidate)
        ):
            raise ContextError(f"decision_refs path is unsafe or duplicated: {raw!r}")
        _regular_file(candidate, "accepted ADR")
        seen_refs.add(raw)
        ref_records.append({"path": raw, "sha256": file_sha256(candidate)})

    contract = {
        "project_slug": project_slug,
        "feature_id": feature_id,
        "plan": {
            "path": _repo_relative(repo_root, plan_path),
            "sha256": file_sha256(plan_path),
        },
        "feature": {
            "path": _repo_relative(repo_root, feature_path),
            "sha256": file_sha256(feature_path),
        },
        "architecture_disposition_sha256": object_sha256(posture),
        "architecture_selection": {
            "path": _repo_relative(repo_root, selection_path),
            "sha256": file_sha256(selection_path),
        },
        "decision_refs": ref_records,
    }
    return object_sha256(contract)


def feature_mapping(data: dict, feature_id: str) -> dict:
    """Return the exact canonical schema-v2 feature mapping row."""
    if data.get("schema_version") != 2:
        raise ContextError(
            "downstream architecture provenance requires architecture schema_version 2"
        )
    mappings = data.get("feature_mappings")
    if not isinstance(mappings, list):
        raise ContextError("architecture.json feature_mappings must be a list")
    matches = [
        row for row in mappings
        if isinstance(row, dict) and row.get("feature_id") == feature_id
    ]
    if len(matches) != 1:
        raise ContextError(
            f"architecture feature mapping for {feature_id!r} must occur exactly once "
            f"(found {len(matches)})"
        )
    return matches[0]


def mapped_ids(mapping: dict) -> dict[str, list[str]]:
    """Aggregate only canonical schema-v2 mapping arrays into consumer categories."""
    for field in V2_MAPPING_ID_FIELDS:
        values = mapping.get(field)
        if not isinstance(values, list):
            raise ContextError(
                f"feature mapping canonical field {field!r} must be a list"
            )
        if any(not isinstance(item, str) or not item.strip() for item in values):
            raise ContextError(
                f"feature mapping {field!r} must contain non-empty strings"
            )
    field_groups = {
        "drivers": ("driver_ids",),
        "actors": ("actor_ids",),
        "components": ("component_ids",),
        "relationships": ("context_relationship_ids", "relationship_ids"),
        "deployments": (
            "deployment_node_ids",
            "deployment_ids",
            "deployment_connection_ids",
        ),
        "data": ("data_ids",),
        "flows": ("integration_ids",),
        "dynamic": ("dynamic_scenario_ids",),
        "transitions": ("transition_ids",),
        "security": ("trust_boundary_ids", "security_realization_ids"),
        "contracts": ("contract_realization_ids",),
        "quality": ("quality_ids",),
        "operations": ("operation_ids",),
        "decisions": ("direction_realization_ids", "decision_ids"),
        "questions": ("open_question_ids",),
        "risks": ("risk_ids",),
        "gaps": ("gap_ids",),
    }
    result: dict[str, list[str]] = {}
    for context_key, fields in field_groups.items():
        combined: list[str] = []
        for field in fields:
            values = mapping.get(field)
            assert isinstance(values, list)
            combined.extend(values)
        result[context_key] = sorted(set(combined))
    return result


def _run_architecture_consumer_lint(
    architecture_dir: Path, repo_root: Path, script_dir: Path
) -> dict:
    script = script_dir / "architecture-lint.py"
    if script.is_symlink() or not script.is_file():
        raise ContextError(f"colocated architecture-lint.py is missing: {script}")
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                str(architecture_dir),
                "--repo-root",
                str(repo_root),
                "--consumer",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContextError(
            f"architecture consumer lint could not run: {exc}"
        ) from exc
    detail = proc.stdout.strip() or proc.stderr.strip() or f"exit {proc.returncode}"
    if proc.returncode != 0:
        raise ContextError(f"architecture consumer lint did not pass: {detail}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ContextError(
            f"architecture consumer lint returned invalid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("status") != "pass":
        raise ContextError(
            "architecture consumer lint exit 0 did not return status 'pass'"
        )
    if payload.get("architecture_schema_version") != 2:
        raise ContextError(
            "architecture consumer lint did not verify architecture schema_version 2"
        )
    receipt = payload.get("package_receipt_sha256")
    if not isinstance(receipt, str) or SHA256_RE.fullmatch(receipt) is None:
        raise ContextError(
            "architecture consumer lint did not return a verified "
            "package_receipt_sha256"
        )
    return payload


def _empty_mapping() -> dict[str, list[str]]:
    return {key: [] for key in MAPPING_KEYS}


def _no_package_context(
    *,
    project_slug: str,
    feature_id: str,
    plan_contract_sha256: str,
    mode: str,
    plan_revision: int | None,
    reason: str,
) -> dict:
    return {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "project_slug": project_slug,
        "feature_id": feature_id,
        "plan_contract_sha256": plan_contract_sha256,
        "mode": mode,
        "package_path": None,
        "plan_revision": plan_revision,
        "architecture_revision": None,
        "package_receipt_sha256": None,
        "feature_mapping_sha256": None,
        "mapped_ids": _empty_mapping(),
        "reason": reason,
    }


def _architecture_outcome(plan: dict) -> tuple[str, str]:
    """Return the only valid disposition outcome for downstream consumption.

    Required and converged recommendations must carry direction status
    ``direction-selected`` and therefore require a governed package. A
    recommendation may omit the package only when both convergence and
    direction are explicitly deferred.
    """
    posture = plan.get("architecture_disposition")
    if not isinstance(posture, dict):
        raise ContextError("full plan requires architecture_disposition")
    decision = posture.get("decision")
    if decision not in {"required", "recommended", "not-required"}:
        raise ContextError(f"unknown architecture disposition: {decision!r}")
    convergence = posture.get("convergence")
    if not isinstance(convergence, dict):
        raise ContextError("architecture_disposition.convergence must be an object")
    convergence_status = convergence.get("status")
    direction = posture.get("direction")
    if not isinstance(direction, dict):
        raise ContextError("architecture_disposition.direction must be an object")
    direction_status = direction.get("status")

    if decision == "required":
        if (
            convergence_status != "converged"
            or direction_status != SELECTED_DIRECTION_STATUS
        ):
            raise ContextError(
                "required architecture must have direction status "
                "`direction-selected` and convergence status `converged`"
            )
        return decision, "selected"
    if decision == "recommended":
        if (
            convergence_status == "converged"
            and direction_status == SELECTED_DIRECTION_STATUS
        ):
            return decision, "selected"
        if convergence_status == "deferred" and direction_status == "deferred":
            return decision, "deferred"
        raise ContextError(
            "recommended architecture must be `direction-selected` and "
            "converged or explicitly deferred"
        )
    if (
        convergence_status != "not-applicable"
        or direction_status != "not-applicable"
    ):
        raise ContextError(
            "not-required architecture must have convergence and direction "
            "status `not-applicable`"
        )
    return decision, "not-applicable"


def derive_context(
    plan_dir: Path,
    feature_id: str,
    *,
    repo_root: Path,
    script_dir: Path | None = None,
    lint_package: bool = True,
) -> dict:
    requested_plan_dir = plan_dir
    repo_root = repo_root.resolve()
    plan_dir = plan_dir.resolve()
    script_dir = script_dir or Path(__file__).resolve().parent
    if requested_plan_dir.is_symlink():
        raise ContextError(
            f"plan directory must not be a symlink: {requested_plan_dir}"
        )
    if not _inside(repo_root, plan_dir):
        raise ContextError(f"plan directory escapes repository root: {plan_dir}")
    if not isinstance(feature_id, str) or not feature_id.strip():
        raise ContextError("feature id must be non-empty")

    project_slug = plan_dir.name
    if PROJECT_SLUG_RE.fullmatch(project_slug) is None:
        raise ContextError("plan-directory name must be lowercase kebab-case")
    plan_path = plan_dir / "plan.json"
    plan = _load_json(plan_path, "plan.json")
    project_slug = plan.get("project_slug")
    if (
        not isinstance(project_slug, str)
        or PROJECT_SLUG_RE.fullmatch(project_slug) is None
        or project_slug != plan_dir.name
    ):
        raise ContextError(
            "plan.json project_slug must be lowercase kebab-case and match "
            "the plan-directory name"
        )
    revision = plan.get("plan_revision", 1)
    if type(revision) is not int or revision < 1:
        raise ContextError("plan.json plan_revision must be an integer >= 1")
    contract_sha256 = _full_plan_contract_sha256(
        plan=plan,
        plan_path=plan_path,
        plan_dir=plan_dir,
        repo_root=repo_root,
        project_slug=project_slug,
        feature_id=feature_id,
    )
    decision, outcome = _architecture_outcome(plan)
    architecture_dir = plan_dir / "architecture"
    if architecture_dir.exists() or architecture_dir.is_symlink():
        if outcome != "selected":
            raise ContextError(
                f"architecture package is incompatible with {decision} "
                f"outcome {outcome}"
            )
        lint_identity = None
        if lint_package:
            lint_identity = _run_architecture_consumer_lint(
                architecture_dir, repo_root, script_dir
            )
        architecture = _load_json(
            architecture_dir / "architecture.json", "architecture.json"
        )
        architecture_revision = architecture.get("architecture_revision")
        source_plan_revision = architecture.get("source_plan_revision")
        if type(architecture_revision) is not int or architecture_revision < 1:
            raise ContextError("architecture_revision must be an integer >= 1")
        if source_plan_revision != revision:
            raise ContextError(
                "architecture source_plan_revision does not match current plan revision"
            )
        if architecture.get("project_slug") != project_slug:
            raise ContextError(
                "architecture project_slug does not match the current plan"
            )
        mapping = feature_mapping(architecture, feature_id)
        ids = mapped_ids(mapping)
        approval = architecture.get("approval")
        receipt_sha256 = (
            approval.get("receipt_sha256") if isinstance(approval, dict) else None
        )
        if (
            not isinstance(receipt_sha256, str)
            or SHA256_RE.fullmatch(receipt_sha256) is None
        ):
            raise ContextError(
                "consumer-linted architecture package is missing "
                "approval.receipt_sha256"
            )
        if lint_identity is not None:
            expected_identity = {
                "project_slug": project_slug,
                "architecture_revision": architecture_revision,
                "source_plan_revision": revision,
                "package_receipt_sha256": receipt_sha256,
            }
            differing = sorted(
                field for field, expected in expected_identity.items()
                if lint_identity.get(field) != expected
            )
            if differing:
                raise ContextError(
                    "consumer-lint package identity disagrees with architecture.json "
                    "for: " + ", ".join(differing)
                )
        return {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "project_slug": project_slug,
            "feature_id": feature_id,
            "plan_contract_sha256": contract_sha256,
            "mode": "package",
            "package_path": _repo_relative(repo_root, architecture_dir),
            "plan_revision": revision,
            "architecture_revision": architecture_revision,
            "package_receipt_sha256": receipt_sha256,
            "feature_mapping_sha256": object_sha256(mapping),
            "mapped_ids": ids,
            "reason": None,
        }

    posture = plan["architecture_disposition"]
    rationale = posture.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ContextError("architecture_disposition.rationale must be non-empty")
    if outcome == "selected":
        raise ContextError(
            f"{decision} selected and converged architecture package is absent"
        )
    mode_by_decision = {
        "recommended": "recommended-absent",
        "not-required": "not-required",
    }
    mode = mode_by_decision.get(decision)
    if mode is None:
        raise ContextError(f"unknown architecture disposition: {decision!r}")
    return _no_package_context(
        project_slug=project_slug,
        feature_id=feature_id,
        plan_contract_sha256=contract_sha256,
        mode=mode,
        plan_revision=revision,
        reason=rationale.strip(),
    )


def validate_context_shape(value: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["architecture_context must be an object"]
    missing = sorted(CONTEXT_KEYS - set(value))
    extra = sorted(set(value) - CONTEXT_KEYS)
    if missing:
        errors.append("architecture_context missing key(s): " + ", ".join(missing))
    if extra:
        errors.append("architecture_context has unknown key(s): " + ", ".join(extra))
    if value.get("schema_version") != CONTEXT_SCHEMA_VERSION:
        errors.append(
            f"architecture_context.schema_version must be {CONTEXT_SCHEMA_VERSION}"
        )
    project_slug = value.get("project_slug")
    if (
        not isinstance(project_slug, str)
        or PROJECT_SLUG_RE.fullmatch(project_slug) is None
    ):
        errors.append(
            "architecture_context.project_slug must be lowercase kebab-case"
        )
    feature_id = value.get("feature_id")
    if not isinstance(feature_id, str) or not feature_id.strip():
        errors.append("architecture_context.feature_id must be non-empty")
    plan_contract = value.get("plan_contract_sha256")
    if (
        not isinstance(plan_contract, str)
        or SHA256_RE.fullmatch(plan_contract) is None
    ):
        errors.append(
            "architecture_context.plan_contract_sha256 must be 64 lowercase hex"
        )
    mode = value.get("mode")
    if mode not in CONTEXT_MODES:
        errors.append(
            f"architecture_context.mode must be one of {sorted(CONTEXT_MODES)}"
        )
    mapped = value.get("mapped_ids")
    if not isinstance(mapped, dict):
        errors.append("architecture_context.mapped_ids must be an object")
    else:
        missing_ids = sorted(set(MAPPING_KEYS) - set(mapped))
        extra_ids = sorted(set(mapped) - set(MAPPING_KEYS))
        if missing_ids:
            errors.append("mapped_ids missing key(s): " + ", ".join(missing_ids))
        if extra_ids:
            errors.append("mapped_ids has unknown key(s): " + ", ".join(extra_ids))
        for key in MAPPING_KEYS:
            ids = mapped.get(key)
            if (
                not isinstance(ids, list)
                or any(not isinstance(item, str) or not item.strip() for item in ids)
                or ids != sorted(set(ids or []))
            ):
                errors.append(
                    f"architecture_context.mapped_ids.{key} must be a sorted "
                    "unique list of non-empty strings"
                )

    plan_revision = value.get("plan_revision")
    if type(plan_revision) is not int or plan_revision < 1:
        errors.append("full-plan architecture_context.plan_revision must be >= 1")

    package_fields = (
        "package_path",
        "architecture_revision",
        "package_receipt_sha256",
        "feature_mapping_sha256",
    )
    if mode == "package":
        path = value.get("package_path")
        if (
            not isinstance(path, str)
            or not path.startswith("docs/plans/")
            or not path.endswith("/architecture")
        ):
            errors.append("package mode requires canonical package_path")
        revision = value.get("architecture_revision")
        if type(revision) is not int or revision < 1:
            errors.append("package mode requires architecture_revision >= 1")
        for field in ("package_receipt_sha256", "feature_mapping_sha256"):
            digest = value.get(field)
            if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
                errors.append(f"package mode requires {field} as 64 lowercase hex")
        if value.get("reason") is not None:
            errors.append("package mode reason must be null")
    else:
        for field in package_fields:
            if value.get(field) is not None:
                errors.append(f"{mode} mode requires {field} to be null")
        reason = value.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"{mode} mode requires a non-empty reason")
        if isinstance(mapped, dict) and any(mapped.get(key) for key in MAPPING_KEYS):
            errors.append(f"{mode} mode requires every mapped_ids list to be empty")
    return errors


def parse_markdown_context(spec_text: str) -> dict:
    matches = list(MARKDOWN_CONTEXT_RE.finditer(spec_text))
    if len(matches) != 1:
        raise ContextError(
            "ce-spec.md must contain exactly one `## Architecture Context` JSON block"
        )
    try:
        value = json.loads(matches[0].group(1))
    except json.JSONDecodeError as exc:
        raise ContextError(
            f"ce-spec.md Architecture Context block is invalid JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ContextError("ce-spec.md Architecture Context must contain an object")
    return value


def validate_spec_context(
    *,
    spec_text: str,
    tasks: dict,
    spec_dir: Path,
    repo_root: Path,
    plan_dir: Path | None = None,
    feature_id: str | None = None,
    script_dir: Path | None = None,
    check_freshness: bool = True,
) -> tuple[list[str], dict | None]:
    hard: list[str] = []
    context = tasks.get("architecture_context")
    hard.extend(validate_context_shape(context))
    if hard:
        return hard, None
    assert isinstance(context, dict)
    try:
        markdown = parse_markdown_context(spec_text)
    except ContextError as exc:
        hard.append(str(exc))
        return hard, None
    if markdown != context:
        hard.append(
            "ce-spec.md Architecture Context must exactly equal "
            "tasks.json architecture_context"
        )
    if not check_freshness:
        return hard, context

    task_feature = tasks.get("feature_id")
    if not isinstance(task_feature, str) or not task_feature.strip():
        hard.append("tasks.json feature_id must be a non-empty string")
        return hard, context
    resolved_feature = feature_id or spec_dir.name
    if task_feature != resolved_feature:
        hard.append(
            "tasks.json feature_id does not match the requested/spec-directory "
            "feature identity"
        )
        return hard, context
    resolved_plan = (plan_dir or spec_dir.parent.parent).resolve()
    if context.get("feature_id") != resolved_feature:
        hard.append(
            "architecture_context.feature_id does not match the requested/spec "
            "feature identity"
        )
    if context.get("project_slug") != resolved_plan.name:
        hard.append(
            "architecture_context.project_slug does not match the owning plan"
        )
    if hard:
        return hard, context
    try:
        expected = derive_context(
            resolved_plan,
            resolved_feature,
            repo_root=repo_root,
            script_dir=script_dir,
        )
    except ContextError as exc:
        hard.append(f"current architecture context could not be derived: {exc}")
        return hard, context
    if context != expected:
        hard.append(
            "persisted architecture_context is stale or mismatched against the "
            "current consumer-linted plan/package"
        )
    return hard, context


def review_binding(
    spec_dir: Path,
    *,
    repo_root: Path,
    git_root: Path | None = None,
    plan_dir: Path | None = None,
    feature_id: str | None = None,
    script_dir: Path | None = None,
) -> dict:
    repo_root = repo_root.resolve()
    spec_dir = spec_dir.resolve()
    spec_path = spec_dir / "ce-spec.md"
    if not spec_path.is_file() and (spec_dir / "spec.md").is_file():
        spec_path = spec_dir / "spec.md"
    tasks_path = spec_dir / "tasks.json"
    tasks = _load_json(tasks_path, "tasks.json")
    if spec_path.is_symlink() or not spec_path.is_file():
        raise ContextError(f"ce-spec.md must be a regular file: {spec_path}")
    spec_text = spec_path.read_text(encoding="utf-8")
    resolved_feature = feature_id or spec_dir.name
    resolved_plan = (plan_dir or spec_dir.parent.parent).resolve()
    hard, context = validate_spec_context(
        spec_text=spec_text,
        tasks=tasks,
        spec_dir=spec_dir,
        repo_root=repo_root,
        plan_dir=resolved_plan,
        feature_id=resolved_feature,
        script_dir=script_dir,
        check_freshness=True,
    )
    if hard or context is None:
        raise ContextError("; ".join(hard))

    plan_path = resolved_plan / "plan.json"
    plan_authority = plan_path
    feature_path = resolved_plan / "features" / f"{resolved_feature}.md"
    if (
        plan_authority.is_symlink()
        or not plan_authority.is_file()
        or feature_path.is_symlink()
        or not feature_path.is_file()
    ):
        raise ContextError("plan or feature authority is missing/unreadable")

    implementation_files = implementation_file_records(tasks, repo_root)
    repository_state = repository_state_records(repo_root)

    commit_sha: str | None = None
    commit_root = (git_root or repo_root).resolve()
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=commit_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode == 0:
        candidate = proc.stdout.strip().lower()
        if COMMIT_RE.fullmatch(candidate):
            commit_sha = candidate

    return {
        "plan_sha256": file_sha256(plan_authority),
        "feature_sha256": file_sha256(feature_path),
        "spec_sha256": file_sha256(spec_path),
        "tasks_sha256": file_sha256(tasks_path),
        "architecture_context_sha256": object_sha256(context),
        "architecture_package_receipt_sha256": context.get(
            "package_receipt_sha256"
        ),
        "implementation_files_sha256": object_sha256(implementation_files),
        "repository_state_sha256": object_sha256(repository_state),
        "commit_sha": commit_sha,
    }


def implementation_file_records(tasks: dict, repo_root: Path) -> list[dict]:
    """Return a deterministic content record for every task-declared file.

    The record is intentionally limited to the spec's mechanical Scope Lock.
    Missing paths are represented explicitly so a reviewed deletion is stable.
    Symlinks and non-files are rejected instead of being followed.
    """
    rows = tasks.get("tasks")
    if not isinstance(rows, list):
        raise ContextError("tasks.json tasks must be a list")
    declared: set[str] = set()
    for index, task in enumerate(rows):
        if not isinstance(task, dict):
            raise ContextError(f"tasks.json task at index {index} must be an object")
        files = task.get("files")
        if not isinstance(files, list) or not files:
            raise ContextError(
                f"tasks.json task {task.get('id', index)!r} requires a non-empty "
                "files list for review provenance"
            )
        for raw in files:
            if not isinstance(raw, str) or not raw.strip():
                raise ContextError("tasks.json files entries must be non-empty strings")
            normalized = raw.replace("\\", "/")
            while normalized.startswith("./"):
                normalized = normalized[2:]
            parts = normalized.split("/")
            if (
                not normalized
                or normalized.startswith("/")
                or any(part in {"", ".", ".."} for part in parts)
            ):
                raise ContextError(
                    f"tasks.json file path must be normalized and repository-relative: "
                    f"{raw!r}"
                )
            declared.add(normalized)
    if not declared:
        raise ContextError(
            "tasks.json declares no implementation files; review provenance "
            "cannot bind an unknown implementation scope"
        )

    records: list[dict] = []
    for relative in sorted(declared):
        path = repo_root / relative
        if not _inside(repo_root, path):
            raise ContextError(f"task-declared file escapes repository root: {relative}")
        if path.is_symlink():
            raise ContextError(
                f"task-declared implementation file must not be a symlink: {relative}"
            )
        if not path.exists():
            records.append({"path": relative, "state": "missing", "sha256": None})
        elif not path.is_file():
            raise ContextError(
                f"task-declared implementation path is not a file: {relative}"
            )
        else:
            records.append(
                {"path": relative, "state": "file", "sha256": file_sha256(path)}
            )
    return records


def _review_state_excluded(relative: str) -> bool:
    path = Path(relative)
    parts = path.parts
    if ".git" in parts:
        return True
    if len(parts) < 4 or parts[:2] != ("docs", "plans"):
        return False

    # Review output and auto-build supervision are deliberately written after
    # the binding is calculated. Scope every exclusion to the canonical plan
    # artifact tree so an application source file with the same basename stays
    # review-bound.
    plan_relative = parts[3:]
    if plan_relative in {
        (".metrics.jsonl",),
        ("STATUS.md",),
        ("code-review.md",),
        ("review-learnings.md",),
        ("verification-report.md",),
        ("verification-summary.json",),
    }:
        return True
    if plan_relative and plan_relative[0] in {"ce-auto-build", "evidence"}:
        return True
    if (
        len(plan_relative) >= 3
        and plan_relative[0] == "specs"
        and plan_relative[2] == "evidence"
    ):
        return True
    return (
        len(plan_relative) == 3
        and plan_relative[0] == "specs"
        and plan_relative[2] in {"review-summary.json", "code-review.md"}
    )


def repository_state_records(repo_root: Path) -> list[dict]:
    """Bind the complete reviewable repository state, excluding only evidence
    which is expected to be written after the binding is calculated.

    A Git worktree includes tracked and non-ignored untracked files. A
    materialized committed tree has no `.git`, so the filesystem fallback
    produces the same committed path/content records.
    """
    repo_root = repo_root.resolve()
    paths: list[str] | None = None
    try:
        top = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContextError(f"repository-state Git discovery failed: {exc}") from exc
    if top.returncode == 0 and Path(top.stdout.strip()).resolve() == repo_root:
        try:
            listed = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_root),
                    "ls-files",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                    "-z",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ContextError(f"repository-state file listing failed: {exc}") from exc
        if listed.returncode != 0:
            detail = listed.stderr.strip() or listed.stdout.strip()
            raise ContextError(
                f"repository-state file listing failed: {detail or listed.returncode}"
            )
        paths = sorted(
            value
            for value in listed.stdout.split("\0")
            if value and not _review_state_excluded(value)
        )
    if paths is None:
        paths = sorted(
            path.relative_to(repo_root).as_posix()
            for path in repo_root.rglob("*")
            if (path.is_file() or path.is_symlink())
            and not _review_state_excluded(path.relative_to(repo_root).as_posix())
        )

    records: list[dict] = []
    for relative in paths:
        path = repo_root / relative
        if not _inside(repo_root, path):
            raise ContextError(f"repository-state path escapes root: {relative}")
        if path.is_symlink():
            try:
                target = os.readlink(path)
            except OSError as exc:
                raise ContextError(
                    f"repository-state symlink is unreadable: {relative}: {exc}"
                ) from exc
            records.append(
                {"path": relative, "state": "symlink", "target": target}
            )
        elif path.is_file():
            records.append(
                {
                    "path": relative,
                    "state": "file",
                    "sha256": file_sha256(path),
                    "executable": bool(path.stat().st_mode & 0o111),
                }
            )
        elif not _occupies(path):
            # `git ls-files --cached` includes an index-tracked path deleted
            # from the current worktree. The review seal represents the current
            # tree, so absence is expressed by omitting that path—the same
            # record set a materialized committed tree produces after deletion.
            continue
        else:
            raise ContextError(
                f"repository-state path changed while hashing: {relative}"
            )
    return records


def worktree_commit_differences(
    repo_root: Path, evaluated_commit: str
) -> list[str]:
    """Return non-evidence paths that do not materialize evaluated_commit.

    Review receipts intentionally hash the worktree so the producer can write
    uncommitted review evidence. A release consumer must separately prove that
    all other worktree bytes are the bytes in the explicitly evaluated commit.
    """
    repo_root = repo_root.resolve()
    commands = (
        (
            "tracked",
            [
                "git",
                "-C",
                str(repo_root),
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--ignore-submodules=none",
                "--name-only",
                "-z",
                evaluated_commit,
                "--",
            ],
        ),
        (
            "untracked",
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
            ],
        ),
    )
    differences: set[str] = set()
    for label, command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ContextError(
                f"could not compare {label} worktree state to evaluated commit: "
                f"{exc}"
            ) from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ContextError(
                f"could not compare {label} worktree state to evaluated commit: "
                f"{detail or result.returncode}"
            )
        try:
            decoded = result.stdout.decode("utf-8")
        except UnicodeError as exc:
            raise ContextError(
                f"{label} worktree path listing is not valid UTF-8: {exc}"
            ) from exc
        differences.update(
            relative
            for relative in decoded.split("\0")
            if relative and not _review_state_excluded(relative)
        )
    return sorted(differences)


def validate_binding_shape(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["binding must be an object"]
    errors: list[str] = []
    missing = sorted(BINDING_KEYS - set(value))
    extra = sorted(set(value) - BINDING_KEYS)
    if missing:
        errors.append("binding missing key(s): " + ", ".join(missing))
    if extra:
        errors.append("binding has unknown key(s): " + ", ".join(extra))
    for field in (
        "plan_sha256",
        "feature_sha256",
        "spec_sha256",
        "tasks_sha256",
        "architecture_context_sha256",
        "implementation_files_sha256",
        "repository_state_sha256",
    ):
        digest = value.get(field)
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            errors.append(f"binding.{field} must be 64 lowercase hex")
    package = value.get("architecture_package_receipt_sha256")
    if package is not None and (
        not isinstance(package, str) or SHA256_RE.fullmatch(package) is None
    ):
        errors.append(
            "binding.architecture_package_receipt_sha256 must be null or "
            "64 lowercase hex"
        )
    commit = value.get("commit_sha")
    if commit is not None and (
        not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None
    ):
        errors.append("binding.commit_sha must be null or a 40-64 lowercase hex id")
    return errors


def _payload(status: str, **values: object) -> dict:
    return {"schema_version": 1, "status": status, **values}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="derive/check feature-spec architecture context"
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)

    derive = sub.add_parser("derive")
    derive.add_argument("plan_dir", type=Path)
    derive.add_argument("feature_id")
    derive.add_argument("--json", action="store_true")

    check = sub.add_parser("check")
    check.add_argument("spec_dir", type=Path)
    check.add_argument("--plan-dir", type=Path)
    check.add_argument("--feature")
    check.add_argument("--json", action="store_true")

    binding = sub.add_parser("review-binding")
    binding.add_argument("spec_dir", type=Path)
    binding.add_argument("--plan-dir", type=Path)
    binding.add_argument("--feature")
    binding.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        repo_root = args.repo_root.resolve()
        if not repo_root.is_dir():
            raise ContextError(f"repository root not found: {repo_root}")
        if args.command == "derive":
            context = derive_context(
                args.plan_dir,
                args.feature_id,
                repo_root=repo_root,
                script_dir=Path(__file__).resolve().parent,
            )
            payload = _payload("pass", architecture_context=context)
        elif args.command == "check":
            spec_dir = args.spec_dir.resolve()
            spec_path = spec_dir / "ce-spec.md"
            if not spec_path.is_file() and (spec_dir / "spec.md").is_file():
                spec_path = spec_dir / "spec.md"
            tasks = _load_json(spec_dir / "tasks.json", "tasks.json")
            if spec_path.is_symlink() or not spec_path.is_file():
                raise ContextError(f"ce-spec.md must be a regular file: {spec_path}")
            hard, context = validate_spec_context(
                spec_text=spec_path.read_text(encoding="utf-8"),
                tasks=tasks,
                spec_dir=spec_dir,
                repo_root=repo_root,
                plan_dir=args.plan_dir,
                feature_id=args.feature,
                script_dir=Path(__file__).resolve().parent,
            )
            payload = _payload(
                "fail" if hard else "pass",
                architecture_context=context,
                hard_failures=hard,
            )
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                print(f"architecture-context: {payload['status'].upper()}")
                for item in hard:
                    print(f"HARD: {item}")
            return 1 if hard else 0
        else:
            current = review_binding(
                args.spec_dir,
                repo_root=repo_root,
                plan_dir=args.plan_dir,
                feature_id=args.feature,
                script_dir=Path(__file__).resolve().parent,
            )
            payload = _payload("pass", binding=current)
    except (
        ContextError,
        OSError,
        UnicodeError,
        subprocess.SubprocessError,
        ValueError,
    ) as exc:
        payload = _payload("error", error=str(exc))
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"architecture-context: ERROR — {exc}", file=sys.stderr)
        return 2

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload.get("architecture_context", payload), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
