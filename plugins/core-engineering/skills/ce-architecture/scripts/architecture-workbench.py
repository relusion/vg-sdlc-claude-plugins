#!/usr/bin/env python3
"""Author a decision-ready architecture workbench without hand-building hashes.

The model supplies only semantic option judgments.  This helper inherits the
planning-owned frame from ``architecture-exploration.json``, derives every
mechanical field, renders ``architecture-options.md``, and returns a complete
schema-v2 ``awaiting-selection`` checkpoint.

Commands:

  architecture-workbench.py template --json
  architecture-workbench.py render --exploration PATH --draft PATH|- \
      --output PATH --repo-root DIR --json
      [--previous-report PATH --expected-previous-sha256 SHA256]
  architecture-workbench.py resume-frame-change --report PATH \
      --repo-root DIR \
      (--expected-report-sha256 SHA256 | --recover-persisted) --json

Exit codes:
  0  template emitted or a lint-valid report was written
  1  semantic input or the rendered contract is invalid
  2  a path, file, or runtime dependency could not be handled safely
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
from decimal import Decimal
from pathlib import Path


MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 10 * 1024 * 1024
MAX_RECEIPT_BYTES = 64 * 1024
MAX_TEXT = 4000
MAX_ARRAY_ITEMS = 12
FRAME_CHANGE_RECEIPT_NAME = ".architecture-frame-change-receipt.json"

DECISION_KEYS = {
    "decision",
    "why_now",
    "current_constraints",
    "key_tradeoff",
    "cost_if_wrong",
    "material_gaps_and_inferences",
}
OPTION_SEMANTIC_KEYS = {
    "option_id",
    "title",
    "summary",
    "responsibilities_and_boundaries",
    "runtime_and_deployment",
    "data_ownership",
    "integrations_and_failure",
    "trust_residency_and_security",
    "quality_tactics",
    "migration_and_evolution",
    "capability_implications",
    "assumptions",
    "irreversible_commitments",
    "constraint_verdicts",
    "scores",
    "elimination_reason",
}
VERDICT_KEYS = {"constraint_id", "verdict", "basis"}
SCORE_KEYS = {"criterion_id", "score", "basis", "evidence_state", "evidence"}
RECOMMENDATION_KEYS = {"option_id", "basis"}
UNCARRIED_KEYS = {
    "label",
    "disposition",
    "reason",
    "evidence_or_next_check",
}
SUPERSESSION_KEYS = {"prior_option_id", "reason"}
AUDIT_KEYS = {"event", "human_input", "response"}
INITIAL_KEYS = {
    "schema_version",
    "decision",
    "options",
    "uncarried_options",
    "recommendation",
    "audit_event",
}
FULL_REVISION_KEYS = INITIAL_KEYS | {"supersession_reasons"}
INHERIT_KEYS = {"schema_version", "inherit_comparison", "audit_event"}
PENDING_REVISION_KEYS = {
    "schema_version",
    "inherit_comparison",
    "frame_change_pending",
}
FRAME_CHANGE_PENDING_KEYS = {"request", "delta"}
FRAME_CHANGE_VALUE_KEYS = {"before", "after"}
FRAME_CHANGE_REQUIREMENT_KEYS = {"field", "before", "after"}
FRAME_CHANGE_WEIGHT_KEYS = {"criterion_id", "before", "after"}
FRAME_CHANGE_COLLECTION_KEYS = {
    "hard_constraints": ("constraint_id", "id"),
    "driver_screen": ("driver_id", "id"),
    "sources": ("path", "path"),
    "quality_attribute_scenarios": ("scenario_id", "id"),
}
FRAME_CHANGE_REQUIREMENT_FIELDS = {
    "project_intent",
    "non_goals",
    "architecture_applicability",
    "accepted_decisions",
    "material_gaps",
    "capabilities",
    "journeys",
}
FRAME_CHANGE_REQUIREMENT_TYPES = {
    "project_intent": str,
    "non_goals": list,
    "architecture_applicability": str,
    "accepted_decisions": list,
    "material_gaps": list,
    "capabilities": list,
    "journeys": list,
}
FRAME_CHANGE_OWNER_KEYS = {"identity_or_role", "authority_basis"}
FRAME_CHANGE_RECEIPT_KEYS = {
    "schema_version",
    "report_path",
    "prior_report_sha256",
    "pending_report_sha256",
    "request_sha256",
    "delta_sha256",
    "pending_id",
}
SEMANTIC_UNCARRIED_DISPOSITIONS = {"dominance-pruned", "uncarried"}
REPORT_UNCARRIED_DISPOSITIONS = SEMANTIC_UNCARRIED_DISPOSITIONS | {"superseded"}
MARKDOWN_ESCAPABLE = frozenset("\\`*_[ ]{}()#+!|>~".replace(" ", ""))
DIMENSIONS = (
    ("Responsibilities and boundaries", "responsibilities_and_boundaries"),
    ("Runtime and deployment", "runtime_and_deployment"),
    ("Data ownership", "data_ownership"),
    ("Integrations and failure behavior", "integrations_and_failure"),
    ("Trust, residency, and security", "trust_residency_and_security"),
    ("Quality tactics", "quality_tactics"),
    ("Migration and evolution", "migration_and_evolution"),
    ("Capability implications", "capability_implications"),
    ("Assumptions", "assumptions"),
    ("Irreversible commitments", "irreversible_commitments"),
)


class WorkbenchInputError(ValueError):
    """Semantic authoring input failed a bounded contract."""

    def __init__(self, failures: list[str] | str):
        if isinstance(failures, str):
            failures = [failures]
        self.failures = failures
        super().__init__("; ".join(failures))


class WorkbenchIOError(RuntimeError):
    """An artifact could not be loaded or written safely."""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise WorkbenchIOError(f"could not load runtime dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - broken shipped dependency is exit 2
        raise WorkbenchIOError(
            f"could not load runtime dependency {path.name}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return module


SCRIPT_DIR = Path(__file__).resolve().parent
sl = _load_module(
    "ce_architecture_workbench_selection_lint",
    SCRIPT_DIR / "architecture-selection-lint.py",
)
ol = _load_module(
    "ce_architecture_workbench_options_lint",
    SCRIPT_DIR / "architecture-options-lint.py",
)


def _strict_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _strict_json(payload: bytes, label: str) -> object:
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {value!r}")
            ),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise WorkbenchInputError(f"{label} is not strict UTF-8 JSON: {exc}") from exc


def _inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except (OSError, ValueError):
        return False


def _safe_regular_bytes(
    path: Path,
    *,
    label: str,
    max_bytes: int = MAX_INPUT_BYTES,
) -> bytes:
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
    except OSError as exc:
        raise WorkbenchIOError(f"could not open {label} safely: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise WorkbenchIOError(f"{label} must be a regular file")
        if info.st_nlink != 1:
            raise WorkbenchIOError(f"{label} must not be hard-linked")
        if info.st_size > max_bytes:
            raise WorkbenchIOError(f"{label} exceeds {max_bytes} bytes")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise WorkbenchIOError(f"{label} exceeds {max_bytes} bytes")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _canonical_paths(
    exploration_arg: Path,
    output_arg: Path,
    repo_root_arg: Path,
) -> tuple[Path, Path, Path, str]:
    root = repo_root_arg.resolve()
    if not root.is_dir():
        raise WorkbenchIOError(f"repository root not found: {root}")
    exploration = (
        exploration_arg
        if exploration_arg.is_absolute()
        else (Path.cwd() / exploration_arg)
    ).absolute()
    output = (
        output_arg if output_arg.is_absolute() else (Path.cwd() / output_arg)
    ).absolute()
    try:
        exploration_rel = exploration.relative_to(root)
        output_rel = output.relative_to(root)
    except ValueError as exc:
        raise WorkbenchIOError("exploration and output must be beneath repository root") from exc

    expected_prefix = ("docs", "plans", ".drafts")
    if (
        len(exploration_rel.parts) != 5
        or exploration_rel.parts[:3] != expected_prefix
        or exploration_rel.parts[4] != "architecture-exploration.json"
    ):
        raise WorkbenchIOError(
            "exploration path must equal "
            "docs/plans/.drafts/<slug>/architecture-exploration.json"
        )
    slug = exploration_rel.parts[3]
    if sl.PROJECT_SLUG_RE.fullmatch(slug) is None:
        raise WorkbenchIOError("exploration path contains a non-canonical slug")
    expected_output = exploration.with_name("architecture-options.md")
    if output != expected_output:
        raise WorkbenchIOError(
            "output must be the architecture-options.md sibling of the exploration input"
        )
    if output_rel.parts[:4] != exploration_rel.parts[:4]:
        raise WorkbenchIOError("output draft directory does not match exploration input")
    for candidate, label in (
        (exploration, "exploration path"),
        (output.parent, "output directory"),
    ):
        if sl._symlink_components(root, candidate):
            raise WorkbenchIOError(f"{label} must not contain symlinks")
    if not output.parent.is_dir():
        raise WorkbenchIOError(f"output directory not found: {output.parent}")
    if output.exists():
        if output.is_symlink() or not output.is_file():
            raise WorkbenchIOError("existing output must be a regular non-symlink file")
        try:
            if output.stat().st_nlink != 1:
                raise WorkbenchIOError("existing output must not be hard-linked")
        except OSError as exc:
            raise WorkbenchIOError(f"could not inspect existing output: {exc}") from exc
    return root, exploration, output, slug


def _read_draft(path_value: str) -> dict:
    if path_value == "-":
        payload = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(payload) > MAX_INPUT_BYTES:
            raise WorkbenchIOError(f"semantic draft exceeds {MAX_INPUT_BYTES} bytes")
    else:
        payload = _safe_regular_bytes(
            Path(path_value).absolute(),
            label="semantic comparison draft",
        )
    value = _strict_json(payload, "semantic comparison draft")
    if not isinstance(value, dict):
        raise WorkbenchInputError("semantic comparison draft must be a JSON object")
    return value


def _exact_keys(
    value: dict,
    expected: set[str],
    label: str,
    failures: list[str],
) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing:
        failures.append(f"{label} missing key(s): {', '.join(missing)}")
    if extra:
        failures.append(f"{label} has unknown key(s): {', '.join(extra)}")


def _text(
    value: object,
    label: str,
    failures: list[str],
    *,
    max_length: int = MAX_TEXT,
) -> str:
    if not isinstance(value, str) or not value.strip():
        failures.append(f"{label} must be a non-empty string")
        return ""
    if len(value) > max_length:
        failures.append(f"{label} exceeds {max_length} characters")
    if "\x00" in value:
        failures.append(f"{label} must not contain NUL")
    return value.strip()


def _string_array(
    value: object,
    label: str,
    failures: list[str],
    *,
    min_items: int = 1,
    max_items: int = MAX_ARRAY_ITEMS,
) -> list[str]:
    if not isinstance(value, list):
        failures.append(f"{label} must be an array")
        return []
    if not min_items <= len(value) <= max_items:
        failures.append(
            f"{label} must contain between {min_items} and {max_items} entries"
        )
    return [
        _text(item, f"{label}[{index}]", failures)
        for index, item in enumerate(value)
    ]


def _validate_audit(
    value: object,
    *,
    initial: bool,
    failures: list[str],
) -> dict:
    if not isinstance(value, dict):
        failures.append("audit_event must be an object")
        return {}
    _exact_keys(value, AUDIT_KEYS, "audit_event", failures)
    event = _text(value.get("event"), "audit_event.event", failures, max_length=80)
    expected = "initial-synthesis" if initial else None
    if expected is not None and event != expected:
        failures.append("initial audit_event.event must equal `initial-synthesis`")
    allowed_revision_events = sl.REPORT_AUDIT_EVENTS - {"frame-change-pending"}
    if not initial and event not in allowed_revision_events:
        failures.append(
            "revision audit_event.event must be one of "
            + ", ".join(sorted(allowed_revision_events))
        )
    return {
        "event": event,
        "human_input": _text(
            value.get("human_input"), "audit_event.human_input", failures
        ),
        "response": _text(value.get("response"), "audit_event.response", failures),
    }


def _json_value(
    value: object,
    expected_type: type,
    label: str,
    failures: list[str],
) -> object:
    if not isinstance(value, expected_type) or (
        expected_type in {int, float} and isinstance(value, bool)
    ):
        failures.append(f"{label} must be a {expected_type.__name__}")
    return copy.deepcopy(value)


def _before_after_object(
    value: object,
    *,
    label: str,
    failures: list[str],
    nullable: bool,
) -> dict | None:
    if value is None and nullable:
        return None
    if not isinstance(value, dict):
        suffix = " or null" if nullable else ""
        failures.append(f"{label} must be an object{suffix}")
        return None
    return copy.deepcopy(value)


def _typed_frame_change_delta(
    value: object,
    failures: list[str],
    *,
    prior_input: dict | None = None,
) -> dict:
    if not isinstance(value, dict):
        failures.append("frame_change_pending.delta must be an object")
        value = {}
    else:
        _exact_keys(
            value,
            sl.FRAME_CHANGE_DELTA_KEYS,
            "frame_change_pending.delta",
            failures,
        )

    clean: dict = {}
    has_change = False

    requirements = value.get("requirements")
    if not isinstance(requirements, list):
        failures.append("frame_change_pending.delta.requirements must be an array")
        requirements = []
    elif len(requirements) > MAX_ARRAY_ITEMS:
        failures.append(
            "frame_change_pending.delta.requirements may contain at most "
            f"{MAX_ARRAY_ITEMS} entries"
        )
    clean_requirements: list[dict] = []
    requirement_fields: list[str] = []
    for index, row in enumerate(requirements):
        label = f"frame_change_pending.delta.requirements[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{label} must be an object")
            continue
        _exact_keys(row, FRAME_CHANGE_REQUIREMENT_KEYS, label, failures)
        field = _text(row.get("field"), f"{label}.field", failures, max_length=80)
        if field not in FRAME_CHANGE_REQUIREMENT_FIELDS:
            failures.append(
                f"{label}.field must be one of "
                + ", ".join(sorted(FRAME_CHANGE_REQUIREMENT_FIELDS))
            )
            expected_type = object
        else:
            requirement_fields.append(field)
            expected_type = FRAME_CHANGE_REQUIREMENT_TYPES[field]
        before = (
            copy.deepcopy(row.get("before"))
            if expected_type is object
            else _json_value(
                row.get("before"), expected_type, f"{label}.before", failures
            )
        )
        after = (
            copy.deepcopy(row.get("after"))
            if expected_type is object
            else _json_value(
                row.get("after"), expected_type, f"{label}.after", failures
            )
        )
        if before == after:
            failures.append(f"{label} must change the authoritative value")
        if (
            prior_input is not None
            and field in FRAME_CHANGE_REQUIREMENT_FIELDS
            and before != prior_input.get(field)
        ):
            failures.append(
                f"{label}.before does not match the selectable H1 frame"
            )
        clean_requirements.append(
            {"field": field, "before": before, "after": after}
        )
    duplicates = sorted(
        {field for field in requirement_fields if requirement_fields.count(field) > 1}
    )
    if duplicates:
        failures.append(
            "frame_change_pending.delta.requirements contains duplicate field(s): "
            + ", ".join(duplicates)
        )
    clean["requirements"] = clean_requirements
    has_change = has_change or bool(clean_requirements)

    weights = value.get("criterion_weights")
    if not isinstance(weights, list):
        failures.append(
            "frame_change_pending.delta.criterion_weights must be an array"
        )
        weights = []
    elif len(weights) > MAX_ARRAY_ITEMS:
        failures.append(
            "frame_change_pending.delta.criterion_weights may contain at most "
            f"{MAX_ARRAY_ITEMS} entries"
        )
    prior_weights = {
        row.get("id"): row.get("weight")
        for row in (prior_input or {}).get("criteria", [])
        if isinstance(row, dict)
    }
    clean_weights: list[dict] = []
    criterion_ids: list[str] = []
    for index, row in enumerate(weights):
        label = f"frame_change_pending.delta.criterion_weights[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{label} must be an object")
            continue
        _exact_keys(row, FRAME_CHANGE_WEIGHT_KEYS, label, failures)
        criterion_id = _text(
            row.get("criterion_id"),
            f"{label}.criterion_id",
            failures,
            max_length=80,
        )
        criterion_ids.append(criterion_id)
        before = row.get("before")
        after = row.get("after")
        for key, item in (("before", before), ("after", after)):
            if (
                not isinstance(item, (int, float))
                or isinstance(item, bool)
                or not 0 <= item <= 1
            ):
                failures.append(
                    f"{label}.{key} must be a finite number from 0 through 1"
                )
        if before == after:
            failures.append(f"{label} must change the criterion weight")
        if prior_input is not None:
            if criterion_id not in prior_weights:
                failures.append(
                    f"{label}.criterion_id is absent from the selectable H1 frame"
                )
            elif before != prior_weights[criterion_id]:
                failures.append(
                    f"{label}.before does not match the selectable H1 weight"
                )
        clean_weights.append(
            {
                "criterion_id": criterion_id,
                "before": copy.deepcopy(before),
                "after": copy.deepcopy(after),
            }
        )
    duplicates = sorted(
        {
            criterion_id
            for criterion_id in criterion_ids
            if criterion_ids.count(criterion_id) > 1
        }
    )
    if duplicates:
        failures.append(
            "frame_change_pending.delta.criterion_weights contains duplicate "
            "criterion_id(s): " + ", ".join(duplicates)
        )
    clean["criterion_weights"] = clean_weights
    has_change = has_change or bool(clean_weights)

    for delta_key, (identity_key, object_identity_key) in (
        FRAME_CHANGE_COLLECTION_KEYS.items()
    ):
        rows = value.get(delta_key)
        if not isinstance(rows, list):
            failures.append(
                f"frame_change_pending.delta.{delta_key} must be an array"
            )
            rows = []
        elif len(rows) > MAX_ARRAY_ITEMS:
            failures.append(
                f"frame_change_pending.delta.{delta_key} may contain at most "
                f"{MAX_ARRAY_ITEMS} entries"
            )
        prior_rows = (prior_input or {}).get(delta_key, [])
        prior_by_id = {
            row.get(object_identity_key): row
            for row in prior_rows
            if isinstance(row, dict)
        }
        clean_rows: list[dict] = []
        identities: list[str] = []
        for index, row in enumerate(rows):
            label = f"frame_change_pending.delta.{delta_key}[{index}]"
            if not isinstance(row, dict):
                failures.append(f"{label} must be an object")
                continue
            _exact_keys(
                row,
                {identity_key, *FRAME_CHANGE_VALUE_KEYS},
                label,
                failures,
            )
            identity = _text(
                row.get(identity_key),
                f"{label}.{identity_key}",
                failures,
                max_length=400,
            )
            identities.append(identity)
            before = _before_after_object(
                row.get("before"),
                label=f"{label}.before",
                failures=failures,
                nullable=True,
            )
            after = _before_after_object(
                row.get("after"),
                label=f"{label}.after",
                failures=failures,
                nullable=True,
            )
            if before is None and after is None:
                failures.append(f"{label} must add, remove, or replace one row")
            if before == after:
                failures.append(f"{label} must change the authoritative row")
            for side, item in (("before", before), ("after", after)):
                if (
                    isinstance(item, dict)
                    and item.get(object_identity_key) != identity
                ):
                    failures.append(
                        f"{label}.{side}.{object_identity_key} must equal "
                        f"{identity!r}"
                    )
            if prior_input is not None:
                actual_before = prior_by_id.get(identity)
                if before != actual_before:
                    failures.append(
                        f"{label}.before does not match the selectable H1 row"
                    )
            clean_rows.append(
                {
                    identity_key: identity,
                    "before": before,
                    "after": after,
                }
            )
        duplicates = sorted(
            {identity for identity in identities if identities.count(identity) > 1}
        )
        if duplicates:
            failures.append(
                f"frame_change_pending.delta.{delta_key} contains duplicate "
                f"{identity_key}(s): " + ", ".join(duplicates)
            )
        clean[delta_key] = clean_rows
        has_change = has_change or bool(clean_rows)

    decision_owner = value.get("decision_owner")
    if decision_owner is None:
        clean["decision_owner"] = None
    elif not isinstance(decision_owner, dict):
        failures.append(
            "frame_change_pending.delta.decision_owner must be null or an "
            "object with before and after"
        )
        clean["decision_owner"] = None
    else:
        _exact_keys(
            decision_owner,
            FRAME_CHANGE_VALUE_KEYS,
            "frame_change_pending.delta.decision_owner",
            failures,
        )
        before = _before_after_object(
            decision_owner.get("before"),
            label="frame_change_pending.delta.decision_owner.before",
            failures=failures,
            nullable=False,
        )
        after = _before_after_object(
            decision_owner.get("after"),
            label="frame_change_pending.delta.decision_owner.after",
            failures=failures,
            nullable=False,
        )
        for side, owner in (("before", before), ("after", after)):
            if isinstance(owner, dict):
                _exact_keys(
                    owner,
                    FRAME_CHANGE_OWNER_KEYS,
                    f"frame_change_pending.delta.decision_owner.{side}",
                    failures,
                )
                for key in sorted(FRAME_CHANGE_OWNER_KEYS):
                    _text(
                        owner.get(key),
                        (
                            "frame_change_pending.delta.decision_owner."
                            f"{side}.{key}"
                        ),
                        failures,
                    )
        if before == after:
            failures.append(
                "frame_change_pending.delta.decision_owner must change the "
                "authoritative owner"
            )
        if (
            prior_input is not None
            and before != prior_input.get("decision_owner")
        ):
            failures.append(
                "frame_change_pending.delta.decision_owner.before does not "
                "match the selectable H1 owner"
            )
        clean["decision_owner"] = {"before": before, "after": after}
        has_change = True

    clean["human_reason"] = _text(
        value.get("human_reason"),
        "frame_change_pending.delta.human_reason",
        failures,
    )
    if not has_change:
        failures.append(
            "frame_change_pending.delta must contain at least one requested change"
        )
    return clean


def _validate_frame_change_pending(
    value: object,
    failures: list[str],
    *,
    prior_input: dict | None = None,
) -> dict:
    if not isinstance(value, dict):
        failures.append("frame_change_pending must be an object")
        return {}
    _exact_keys(
        value,
        FRAME_CHANGE_PENDING_KEYS,
        "frame_change_pending",
        failures,
    )
    request = _text(
        value.get("request"),
        "frame_change_pending.request",
        failures,
    )
    delta = _typed_frame_change_delta(
        value.get("delta"),
        failures,
        prior_input=prior_input,
    )
    return {"request": request, "delta": delta}


def _validate_semantic_draft(
    draft: dict,
    exploration: dict,
    *,
    initial: bool,
) -> dict:
    failures: list[str] = []
    if draft.get("schema_version") != 1:
        failures.append("semantic draft schema_version must equal 1")

    if "frame_change_pending" in draft:
        _exact_keys(
            draft,
            PENDING_REVISION_KEYS,
            "semantic draft",
            failures,
        )
        if draft.get("inherit_comparison") is not True:
            failures.append(
                "frame_change_pending requires inherit_comparison: true"
            )
        if initial:
            failures.append(
                "frame_change_pending requires --previous-report with a valid "
                "selectable revision"
            )
        pending = _validate_frame_change_pending(
            draft.get("frame_change_pending"),
            failures,
            prior_input=exploration,
        )
        if failures:
            raise WorkbenchInputError(failures)
        return {
            "inherit_comparison": True,
            "frame_change_pending": pending,
            "audit_event": None,
        }

    if draft.get("inherit_comparison") is True:
        _exact_keys(draft, INHERIT_KEYS, "semantic draft", failures)
        if initial:
            failures.append(
                "inherit_comparison requires --previous-report with a valid prior revision"
            )
        audit = _validate_audit(draft.get("audit_event"), initial=False, failures=failures)
        if failures:
            raise WorkbenchInputError(failures)
        return {
            "inherit_comparison": True,
            "frame_change_pending": None,
            "audit_event": audit,
        }

    _exact_keys(
        draft,
        INITIAL_KEYS if initial else FULL_REVISION_KEYS,
        "semantic draft",
        failures,
    )
    decision = draft.get("decision")
    if not isinstance(decision, dict):
        failures.append("decision must be an object")
        decision = {}
    else:
        _exact_keys(decision, DECISION_KEYS, "decision", failures)
    clean_decision: dict[str, str] = {}
    for key in sorted(DECISION_KEYS):
        label = f"decision.{key}"
        text = _text(decision.get(key), label, failures)
        if text and ol.decision_surface_placeholder(text):
            failures.append(
                f"{label} must be decision-ready text, not a "
                "TBD/unknown/template placeholder"
            )
        clean_decision[key] = text

    hard_constraints = exploration.get("hard_constraints")
    constraint_ids = [
        row.get("id")
        for row in hard_constraints
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    ] if isinstance(hard_constraints, list) else []
    criteria = exploration.get("criteria")
    criterion_ids = [
        row.get("id")
        for row in criteria
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    ] if isinstance(criteria, list) else []
    source_paths = {
        row.get("path")
        for row in exploration.get("sources", [])
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }

    raw_options = draft.get("options")
    if not isinstance(raw_options, list):
        failures.append("options must be an array")
        raw_options = []
    elif not 2 <= len(raw_options) <= 4:
        failures.append("options must contain between 2 and 4 complete directions")
    options: list[dict] = []
    ids: list[str] = []
    for index, raw in enumerate(raw_options):
        label = f"options[{index}]"
        if not isinstance(raw, dict):
            failures.append(f"{label} must be an object")
            continue
        _exact_keys(raw, OPTION_SEMANTIC_KEYS, label, failures)
        oid = _text(raw.get("option_id"), f"{label}.option_id", failures, max_length=3)
        if sl.OPTION_ID_RE.fullmatch(oid) is None:
            failures.append(f"{label}.option_id must be A01 through A04")
        ids.append(oid)
        option = {
            "option_id": oid,
            "title": _text(raw.get("title"), f"{label}.title", failures, max_length=200),
            "summary": _text(raw.get("summary"), f"{label}.summary", failures),
        }
        for key in sl.OPTION_ARRAY_KEYS:
            option[key] = _string_array(raw.get(key), f"{label}.{key}", failures)

        raw_verdicts = raw.get("constraint_verdicts")
        if not isinstance(raw_verdicts, list):
            failures.append(f"{label}.constraint_verdicts must be an array")
            raw_verdicts = []
        verdicts: list[dict] = []
        for verdict_index, row in enumerate(raw_verdicts):
            row_label = f"{label}.constraint_verdicts[{verdict_index}]"
            if not isinstance(row, dict):
                failures.append(f"{row_label} must be an object")
                continue
            _exact_keys(row, VERDICT_KEYS, row_label, failures)
            verdict = _text(
                row.get("verdict"), f"{row_label}.verdict", failures, max_length=20
            )
            if verdict not in {"pass", "fail"}:
                failures.append(
                    f"{row_label}.verdict must be `pass` or `fail`; unresolved "
                    "hard constraints return requires-evidence before a selectable report"
                )
            verdicts.append({
                "constraint_id": _text(
                    row.get("constraint_id"),
                    f"{row_label}.constraint_id",
                    failures,
                    max_length=40,
                ),
                "verdict": verdict,
                "basis": _text(row.get("basis"), f"{row_label}.basis", failures),
            })
        if [row["constraint_id"] for row in verdicts] != constraint_ids:
            failures.append(
                f"{label}.constraint_verdicts must cover the exploration hard "
                "constraints once in canonical order"
            )
        option["constraint_verdicts"] = verdicts
        eligible = bool(verdicts or not constraint_ids) and all(
            row["verdict"] == "pass" for row in verdicts
        )

        raw_scores = raw.get("scores")
        if not isinstance(raw_scores, list):
            failures.append(f"{label}.scores must be an array")
            raw_scores = []
        scores: list[dict] = []
        for score_index, row in enumerate(raw_scores):
            row_label = f"{label}.scores[{score_index}]"
            if not isinstance(row, dict):
                failures.append(f"{row_label} must be an object")
                continue
            _exact_keys(row, SCORE_KEYS, row_label, failures)
            score = row.get("score")
            if (
                not isinstance(score, int)
                or isinstance(score, bool)
                or not 1 <= score <= 5
            ):
                failures.append(f"{row_label}.score must be an integer from 1 to 5")
            state = _text(
                row.get("evidence_state"),
                f"{row_label}.evidence_state",
                failures,
                max_length=20,
            )
            if state not in sl.EVIDENCE_STATES:
                failures.append(
                    f"{row_label}.evidence_state must be one of "
                    + ", ".join(sorted(sl.EVIDENCE_STATES))
                )
            evidence = _string_array(
                row.get("evidence"),
                f"{row_label}.evidence",
                failures,
                min_items=1,
                max_items=8,
            )
            if state == "unknown":
                invalid = [
                    item
                    for item in evidence
                    if item not in source_paths
                    and re.fullmatch(r"unknown:\s*\S.*", item, re.I) is None
                ]
            else:
                invalid = [item for item in evidence if item not in source_paths]
            if invalid:
                failures.append(
                    f"{row_label}.evidence contains values outside exploration "
                    f"sources: {', '.join(invalid)}"
                )
            scores.append({
                "criterion_id": _text(
                    row.get("criterion_id"),
                    f"{row_label}.criterion_id",
                    failures,
                    max_length=80,
                ),
                "score": score,
                "basis": _text(row.get("basis"), f"{row_label}.basis", failures),
                "evidence_state": state,
                "evidence": evidence,
            })
        if eligible and [row["criterion_id"] for row in scores] != criterion_ids:
            failures.append(
                f"{label}.scores must cover all six exploration criteria once "
                "in canonical order"
            )
        if not eligible and scores:
            failures.append(f"{label}.scores must be empty when a hard constraint fails")
        option["scores"] = scores
        elimination_reason = raw.get("elimination_reason")
        if eligible:
            if elimination_reason is not None:
                failures.append(
                    f"{label}.elimination_reason must be null for an eligible option"
                )
            option["_elimination_reason"] = None
        else:
            option["_elimination_reason"] = _text(
                elimination_reason,
                f"{label}.elimination_reason",
                failures,
            )
        options.append(option)

    if ids != sorted(ids):
        failures.append("options must be sorted by option_id")
    duplicates = sorted({oid for oid in ids if ids.count(oid) > 1})
    if duplicates:
        failures.append("options contains duplicate id(s): " + ", ".join(duplicates))

    raw_uncarried = draft.get("uncarried_options")
    if not isinstance(raw_uncarried, list):
        failures.append("uncarried_options must be an array")
        raw_uncarried = []
    elif len(raw_uncarried) > 8:
        failures.append("uncarried_options may contain at most 8 entries")
    uncarried: list[dict] = []
    for index, row in enumerate(raw_uncarried):
        label = f"uncarried_options[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{label} must be an object")
            continue
        _exact_keys(row, UNCARRIED_KEYS, label, failures)
        disposition = _text(
            row.get("disposition"), f"{label}.disposition", failures, max_length=40
        )
        if disposition not in SEMANTIC_UNCARRIED_DISPOSITIONS:
            failures.append(
                f"{label}.disposition must be `dominance-pruned` or `uncarried`"
            )
        uncarried.append({
            "label": _text(row.get("label"), f"{label}.label", failures, max_length=200),
            "disposition": disposition,
            "reason": _text(row.get("reason"), f"{label}.reason", failures),
            "evidence_or_next_check": _text(
                row.get("evidence_or_next_check"),
                f"{label}.evidence_or_next_check",
                failures,
            ),
        })

    raw_recommendation = draft.get("recommendation")
    if not isinstance(raw_recommendation, dict):
        failures.append("recommendation must be an object")
        raw_recommendation = {}
    else:
        _exact_keys(
            raw_recommendation,
            RECOMMENDATION_KEYS,
            "recommendation",
            failures,
        )
    recommendation = {
        "option_id": _text(
            raw_recommendation.get("option_id"),
            "recommendation.option_id",
            failures,
            max_length=3,
        ),
        "basis": _text(
            raw_recommendation.get("basis"),
            "recommendation.basis",
            failures,
        ),
    }
    supersession_reasons: dict[str, str] = {}
    if not initial:
        raw_reasons = draft.get("supersession_reasons")
        if not isinstance(raw_reasons, list):
            failures.append("supersession_reasons must be an array")
            raw_reasons = []
        elif len(raw_reasons) > 4:
            failures.append("supersession_reasons may contain at most 4 entries")
        for index, row in enumerate(raw_reasons):
            label = f"supersession_reasons[{index}]"
            if not isinstance(row, dict):
                failures.append(f"{label} must be an object")
                continue
            _exact_keys(row, SUPERSESSION_KEYS, label, failures)
            prior_id = _text(
                row.get("prior_option_id"),
                f"{label}.prior_option_id",
                failures,
                max_length=3,
            )
            if sl.OPTION_ID_RE.fullmatch(prior_id) is None:
                failures.append(f"{label}.prior_option_id must be A01 through A04")
            if prior_id in supersession_reasons:
                failures.append(
                    f"supersession_reasons contains duplicate prior_option_id {prior_id}"
                )
            supersession_reasons[prior_id] = _text(
                row.get("reason"), f"{label}.reason", failures
            )
    audit = _validate_audit(
        draft.get("audit_event"), initial=initial, failures=failures
    )
    if failures:
        raise WorkbenchInputError(failures)
    return {
        "inherit_comparison": False,
        "frame_change_pending": None,
        "decision": clean_decision,
        "options": options,
        "uncarried_options": uncarried,
        "recommendation": recommendation,
        "supersession_reasons": supersession_reasons,
        "audit_event": audit,
    }


def _evaluation_frame(exploration: dict) -> dict:
    keys = (
        "project_intent",
        "non_goals",
        "decision_owner",
        "architecture_applicability",
        "driver_screen",
        "accepted_decisions",
        "material_gaps",
        "capabilities",
        "journeys",
        "quality_attribute_scenarios",
    )
    return {key: exploration.get(key) for key in keys}


def _decimal_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _derive_sensitivity(
    *,
    recommended_id: str,
    eligible: list[dict],
    weights: dict[str, Decimal],
) -> tuple[str, dict | None]:
    if len(eligible) == 1:
        return "not-applicable", None
    score_maps = {
        option["option_id"]: {
            row["criterion_id"]: Decimal(str(row["score"]))
            for row in option["scores"]
        }
        for option in eligible
    }
    state_maps = {
        option["option_id"]: {
            row["criterion_id"]: row["evidence_state"]
            for row in option["scores"]
        }
        for option in eligible
    }
    for scenario, criterion_id, vector in sl._sensitivity_weight_vectors(weights):
        recommended_low = sum(
            vector[cid]
            * sl._score_bounds(
                score_maps[recommended_id][cid],
                state_maps[recommended_id][cid],
            )[0]
            for cid in sl.CRITERIA
        )
        for option in eligible:
            challenger_id = option["option_id"]
            if challenger_id == recommended_id:
                continue
            challenger_high = sum(
                vector[cid]
                * sl._score_bounds(
                    score_maps[challenger_id][cid],
                    state_maps[challenger_id][cid],
                )[1]
                for cid in sl.CRITERIA
            )
            if challenger_high < recommended_low:
                continue
            recommended_exact = sum(
                vector[cid] * score_maps[recommended_id][cid]
                for cid in sl.CRITERIA
            )
            challenger_exact = sum(
                vector[cid] * score_maps[challenger_id][cid]
                for cid in sl.CRITERIA
            )
            exact_flip = challenger_exact >= recommended_exact
            witness_scenario = (
                "evidence-range"
                if scenario == "base-score" and not exact_flip
                else scenario
            )
            bounds = (
                {"recommended": "exact", "challenger": "exact"}
                if exact_flip
                else {"recommended": "lower", "challenger": "upper"}
            )
            witness_criterion = (
                criterion_id
                if witness_scenario.startswith("weight-")
                else None
            )
            return "unstable", {
                "scenario": witness_scenario,
                "criterion_id": witness_criterion,
                "challenger_option_id": challenger_id,
                "evidence_bounds": bounds,
                "condition": sl._sensitivity_condition(
                    scenario=witness_scenario,
                    criterion_id=witness_criterion,
                    recommended_id=recommended_id,
                    challenger_id=challenger_id,
                    evidence_bounds=bounds,
                ),
            }
    return "stable", None


def _build_comparison(exploration: dict, semantic: dict) -> tuple[dict, list[dict]]:
    weights = {
        row["id"]: Decimal(str(row["weight"]))
        for row in exploration["criteria"]
    }
    options: list[dict] = []
    eligible: list[dict] = []
    eliminated: list[dict] = []
    for source in semantic["options"]:
        option = {
            key: value
            for key, value in source.items()
            if not key.startswith("_")
        }
        is_eligible = all(
            row["verdict"] == "pass" for row in option["constraint_verdicts"]
        )
        if is_eligible:
            total = sum(
                weights[row["criterion_id"]] * Decimal(str(row["score"]))
                for row in option["scores"]
            )
            option["weighted_score"] = _decimal_number(total)
            states = {row["evidence_state"] for row in option["scores"]}
            option["confidence"] = (
                "low"
                if "unknown" in states
                else "high"
                if states <= {"recorded", "observed"}
                else "medium"
            )
            eligible.append(option)
        else:
            option["weighted_score"] = None
            option["confidence"] = "not-applicable"
            eliminated.append({
                "option_id": option["option_id"],
                "constraint_ids": [
                    row["constraint_id"]
                    for row in option["constraint_verdicts"]
                    if row["verdict"] == "fail"
                ],
                "reason": source["_elimination_reason"],
            })
        options.append(option)

    if not eligible:
        raise WorkbenchInputError(
            "at least one option must pass every hard constraint before selection"
        )
    recommended_id = semantic["recommendation"]["option_id"]
    eligible_by_id = {row["option_id"]: row for row in eligible}
    if recommended_id not in eligible_by_id:
        raise WorkbenchInputError(
            "recommendation.option_id must reference an eligible option"
        )
    best = max(Decimal(str(row["weighted_score"])) for row in eligible)
    if Decimal(str(eligible_by_id[recommended_id]["weighted_score"])) != best:
        leaders = [
            row["option_id"]
            for row in eligible
            if Decimal(str(row["weighted_score"])) == best
        ]
        raise WorkbenchInputError(
            "recommendation.option_id must reference a highest weighted-score "
            "eligible option; leader(s): " + ", ".join(leaders)
        )
    sensitivity, witness = _derive_sensitivity(
        recommended_id=recommended_id,
        eligible=eligible,
        weights=weights,
    )
    recommended = eligible_by_id[recommended_id]
    if sensitivity == "unstable":
        recommended["confidence"] = "low"
        confidence = "low"
    else:
        states = {row["evidence_state"] for row in recommended["scores"]}
        confidence = "high" if states <= {"recorded", "observed"} else "medium"

    for option in options:
        option["option_sha256"] = sl.option_hash(option)
    option_set_sha256 = sl.option_set_hash(options, eliminated)
    data = {
        "project_slug": exploration["project_slug"],
        "exploration_id": f"AEX-{option_set_sha256[:12]}",
        "source_capability_revision": exploration["capability_revision"],
        "source_exploration_attempt": exploration["exploration_attempt"],
        "source_input_sha256": "",
        "evaluation_frame": _evaluation_frame(exploration),
        "blocking_decision": None,
        "sources": exploration["sources"],
        "evidence_fingerprint": sl.canonical_sha256(exploration["sources"]),
        "criteria": exploration["criteria"],
        "hard_constraints": exploration["hard_constraints"],
        "options": options,
        "eliminated_options": eliminated,
        "option_set_sha256": option_set_sha256,
        "recommendation": {
            "option_id": recommended_id,
            "confidence": confidence,
            "sensitivity": sensitivity,
            "sensitivity_witness": witness,
            "basis": semantic["recommendation"]["basis"],
        },
    }
    data["source_input_sha256"] = sl.source_input_hash(data)
    has_rank_changing_unknown = (
        sensitivity == "unstable"
        and any(
            score["evidence_state"] == "unknown"
            for option in eligible
            for score in option["scores"]
        )
    )
    if (
        has_rank_changing_unknown
        and re.search(
            r"\bunknown\b",
            semantic["decision"]["material_gaps_and_inferences"],
            flags=re.IGNORECASE,
        )
        is None
    ):
        raise WorkbenchInputError(
            "rank-changing unknown score evidence must be explicit in "
            "decision.material_gaps_and_inferences"
        )
    return data, semantic["uncarried_options"]


def _pending_frame_change_payload(
    semantic: dict,
    *,
    prior_report_sha256: str,
    gate_index: int,
    gate_total: int,
) -> dict:
    request = semantic["request"]
    delta = semantic["delta"]
    request_sha256 = hashlib.sha256(request.encode("utf-8")).hexdigest()
    delta_sha256 = sl.canonical_sha256(delta)
    pending_id = "FCP-" + sl.canonical_sha256(
        {
            "request_sha256": request_sha256,
            "delta_sha256": delta_sha256,
            "prior_report_sha256": prior_report_sha256,
        }
    )[:12]
    return {
        "schema_version": 1,
        "pending_id": pending_id,
        "request": request,
        "request_sha256": request_sha256,
        "delta": delta,
        "delta_sha256": delta_sha256,
        "prior_report_sha256": prior_report_sha256,
        "resume_locator": (
            f"Gate {gate_index} of {gate_total} — "
            "Architecture Direction Selection"
        ),
    }


def _expected_input_after_frame_delta(
    previous_data: dict,
    delta: dict,
) -> dict:
    prior = sl.source_input_payload(previous_data)
    failures: list[str] = []
    clean_delta = _typed_frame_change_delta(
        delta,
        failures,
        prior_input=prior,
    )
    if failures:
        raise WorkbenchInputError(
            ["pending decision-frame delta is not bound to selectable H1", *failures]
        )

    expected = copy.deepcopy(prior)
    for row in clean_delta["requirements"]:
        expected[row["field"]] = copy.deepcopy(row["after"])

    weight_updates = {
        row["criterion_id"]: copy.deepcopy(row["after"])
        for row in clean_delta["criterion_weights"]
    }
    expected["criteria"] = [
        (
            {**copy.deepcopy(row), "weight": weight_updates[row["id"]]}
            if row.get("id") in weight_updates
            else copy.deepcopy(row)
        )
        for row in expected["criteria"]
    ]

    for delta_key, (identity_key, object_identity_key) in (
        FRAME_CHANGE_COLLECTION_KEYS.items()
    ):
        rows_by_id = {
            row[object_identity_key]: copy.deepcopy(row)
            for row in expected[delta_key]
        }
        for row in clean_delta[delta_key]:
            identity = row[identity_key]
            if row["after"] is None:
                rows_by_id.pop(identity, None)
            else:
                rows_by_id[identity] = copy.deepcopy(row["after"])
        if delta_key == "driver_screen":
            ordered_identities = [
                identity
                for identity in sl.DRIVER_IDS
                if identity in rows_by_id
            ]
            ordered_identities.extend(
                sorted(set(rows_by_id) - set(ordered_identities))
            )
        else:
            # H1 is already canonical. Sorting preserves the relative order of
            # retained rows and places additions according to each collection's
            # lexicographic id/path contract.
            ordered_identities = sorted(rows_by_id)
        expected[delta_key] = [
            rows_by_id[identity] for identity in ordered_identities
        ]

    owner_delta = clean_delta["decision_owner"]
    if owner_delta is not None:
        expected["decision_owner"] = copy.deepcopy(owner_delta["after"])
    return expected


def _prove_frame_delta_applied(
    *,
    previous_data: dict,
    current_exploration: dict,
    delta: dict,
) -> None:
    current = ol._current_exploration_payload(current_exploration)
    expected = _expected_input_after_frame_delta(previous_data, delta)
    prior_revision = previous_data.get("source_capability_revision")
    prior_attempt = previous_data.get("source_exploration_attempt")
    current_revision = current.get("capability_revision")
    current_attempt = current.get("exploration_attempt")
    if (
        not isinstance(current_revision, int)
        or isinstance(current_revision, bool)
        or not isinstance(current_attempt, int)
        or isinstance(current_attempt, bool)
        or not isinstance(prior_revision, int)
        or isinstance(prior_revision, bool)
        or not isinstance(prior_attempt, int)
        or isinstance(prior_attempt, bool)
        or current_revision <= prior_revision
        or current_attempt <= prior_attempt
    ):
        raise WorkbenchInputError(
            "recomputed frame must increase both capability_revision and "
            "exploration_attempt beyond selectable H1"
        )
    expected["capability_revision"] = current_revision
    expected["exploration_attempt"] = current_attempt
    mismatched = sorted(
        key
        for key in expected
        if expected.get(key) != current.get(key)
    )
    extra = sorted(set(current) - set(expected))
    if mismatched or extra:
        fields = ", ".join([*mismatched, *extra])
        raise WorkbenchInputError(
            "recomputed exploration must exactly equal selectable H1 plus every "
            "durable decision-frame delta member; unrelated frame mutation is "
            f"forbidden (mismatched field(s): {fields})"
        )


def _json_block(value: object) -> list[str]:
    return [
        "```json",
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]


def _markdown_escape(value: object) -> str:
    """Render one untrusted scalar without creating Markdown structure."""
    text = str(value).strip()
    rendered: list[str] = []
    for character in text:
        if character == "\r":
            rendered.append("&#13;")
        elif character == "\n":
            rendered.append("&#10;")
        elif character == "&":
            rendered.append("&amp;")
        elif character == "<":
            rendered.append("&lt;")
        elif character == ">":
            rendered.append("&gt;")
        elif character in MARKDOWN_ESCAPABLE:
            rendered.append("\\" + character)
        else:
            rendered.append(character)
    return "".join(rendered)


def _markdown_unescape(value: str) -> str:
    """Reverse ``_markdown_escape`` for carried workbench rows."""
    text = html.unescape(value)
    rendered: list[str] = []
    index = 0
    while index < len(text):
        if (
            text[index] == "\\"
            and index + 1 < len(text)
            and text[index + 1] in MARKDOWN_ESCAPABLE
        ):
            rendered.append(text[index + 1])
            index += 2
            continue
        rendered.append(text[index])
        index += 1
    return "".join(rendered)


def _inline(value: object) -> str:
    return _markdown_escape(value)


def _cell(value: object) -> str:
    return _inline(value)


def _join(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "None"
    return "; ".join(_cell(item) for item in value)


def _extract_previous(
    report: Path,
    *,
    repo_root: Path,
    expected_sha256: str | None,
) -> tuple[dict, dict, list[list[str]], list[dict], int, str, str, dict | None]:
    report_bytes = _safe_regular_bytes(
        report, label="previous architecture options report", max_bytes=MAX_OUTPUT_BYTES
    )
    actual_report_hash = hashlib.sha256(report_bytes).hexdigest()
    if (
        expected_sha256 is not None
        and actual_report_hash != expected_sha256
    ):
        raise WorkbenchInputError(
            "previous report SHA-256 does not match --expected-previous-sha256: "
            f"expected {expected_sha256}, actual {actual_report_hash}"
        )
    try:
        text = report_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise WorkbenchInputError(
            f"previous architecture options report is not UTF-8: {exc}"
        ) from exc
    status_matches = re.findall(
        r"^>\s*Decision status:\s*(\S+)\s*$",
        text,
        flags=re.MULTILINE,
    )
    if len(status_matches) != 1 or status_matches[0] not in {
        "awaiting-selection",
        "frame-change-pending",
    }:
        raise WorkbenchInputError(
            "previous report must have one supported Decision status"
        )
    report_status = status_matches[0]
    projection_matches = ol.PROJECTION_PATTERN.findall(text)
    if len(projection_matches) != 1:
        raise WorkbenchInputError(
            "previous report must contain one machine-readable comparison projection"
        )
    projection = _strict_json(
        projection_matches[0].encode("utf-8"),
        "previous report comparison projection",
    )
    if not isinstance(projection, dict):
        raise WorkbenchInputError(
            "previous report comparison projection must be an object"
        )
    data = {
        key: value
        for key, value in projection.items()
        if key != "report_projection_schema_version"
    }
    checkpoint = _checkpoint_result(
        data,
        report,
        selection_status=report_status,
    )
    failures = sl.validate_document(
        checkpoint,
        artifact_path=report.with_name("architecture-selection.json"),
        repo_root=repo_root,
        allow_incomplete=True,
        check_source_freshness=False,
    )
    if failures:
        raise WorkbenchInputError(
            [
                "previous report is not a self-contained workbench checkpoint",
                *failures[:20],
            ]
        )
    pending_failures: list[str] = []
    pending_frame_change = (
        sl.pending_frame_change_from_report(text, pending_failures)
        if report_status == "frame-change-pending"
        else None
    )
    if pending_failures:
        raise WorkbenchInputError(
            ["previous pending frame change is invalid", *pending_failures[:20]]
        )
    if pending_frame_change is not None:
        typed_failures: list[str] = []
        clean_delta = _typed_frame_change_delta(
            pending_frame_change.get("delta"),
            typed_failures,
            prior_input=sl.source_input_payload(data),
        )
        if clean_delta != pending_frame_change.get("delta"):
            typed_failures.append(
                "pending delta is not in canonical typed form"
            )
        if typed_failures:
            raise WorkbenchInputError(
                [
                    "previous pending frame change is not exactly bound to H1",
                    *typed_failures[:20],
                ]
            )
    revision_matches = re.findall(
        r"^>\s*Workbench revision:\s*([1-9][0-9]*)\s*$",
        text,
        flags=re.MULTILINE,
    )
    if len(revision_matches) != 1:
        raise WorkbenchInputError("previous report has no unique Workbench revision")
    revision = int(revision_matches[0])

    decision_section = sl._report_section_body(text, "## What Needs Your Decision") or ""
    labels = {
        "decision": "Decision",
        "why_now": "Why now",
        "current_constraints": "Current constraints",
        "key_tradeoff": "Key trade-off",
        "cost_if_wrong": "Cost if wrong",
        "material_gaps_and_inferences": "Material gaps and inferences",
    }
    decision: dict[str, str] = {}
    for key, label in labels.items():
        matches = re.findall(
            rf"^\s*-\s+\*\*{re.escape(label)}:\*\*\s*(.*?)\s*$",
            decision_section,
            flags=re.MULTILINE,
        )
        if len(matches) != 1:
            raise WorkbenchInputError(
                f"previous report is missing decision summary field {label!r}"
            )
        decision[key] = _markdown_unescape(matches[0])

    audit_body = sl._report_section_body(text, "## Decision Workbench Audit") or ""
    audit_rows: list[list[str]] = []
    for line in audit_body.splitlines():
        cells = sl._markdown_table_cells(line)
        if (
            cells is not None
            and len(cells) == len(sl.REPORT_AUDIT_HEADER)
            and cells[0].isdigit()
        ):
            audit_rows.append([_markdown_unescape(cell) for cell in cells])
    if len(audit_rows) != revision:
        raise WorkbenchInputError("previous report audit rows do not match its revision")

    eliminated_ids = {
        row.get("option_id")
        for row in projection.get("eliminated_options", [])
        if isinstance(row, dict)
    }
    uncarried: list[dict] = []
    section = (
        sl._report_section_body(
            text, "## Eliminated, Unresolved, and Uncarried Directions"
        )
        or ""
    )
    for line in section.splitlines():
        cells = sl._markdown_table_cells(line)
        if cells is None or len(cells) != 4:
            continue
        label, disposition, reason, evidence = cells
        if label in eliminated_ids or disposition not in REPORT_UNCARRIED_DISPOSITIONS:
            continue
        uncarried.append({
            "label": _markdown_unescape(label),
            "disposition": disposition,
            "reason": _markdown_unescape(reason),
            "evidence_or_next_check": _markdown_unescape(evidence),
        })
    return (
        data,
        decision,
        audit_rows,
        uncarried,
        revision,
        actual_report_hash,
        report_status,
        pending_frame_change,
    )


def _merge_considered_alternatives(
    *,
    previous_data: dict,
    next_data: dict,
    previous_uncarried: list[dict],
    requested_uncarried: list[dict],
    supersession_reasons: dict[str, str],
) -> list[dict]:
    """Carry prior alternatives and archive every changed/removed option."""
    next_by_id = {
        row.get("option_id"): row
        for row in next_data.get("options", [])
        if isinstance(row, dict)
    }
    superseded: list[dict] = []
    changed_ids: list[str] = []
    for prior in previous_data.get("options", []):
        if not isinstance(prior, dict):
            continue
        prior_id = prior.get("option_id")
        if not isinstance(prior_id, str):
            continue
        current = next_by_id.get(prior_id)
        if (
            isinstance(current, dict)
            and current.get("option_sha256") == prior.get("option_sha256")
        ):
            continue
        changed_ids.append(prior_id)
        reason = supersession_reasons.get(prior_id)
        if not isinstance(reason, str) or not reason.strip():
            continue
        superseded.append({
            "label": f"{prior_id} — {prior.get('title')}",
            "disposition": "superseded",
            "reason": (
                f"{reason} Prior direction summary: {prior.get('summary')}"
            ),
            "evidence_or_next_check": (
                f"Prior option SHA-256: {prior.get('option_sha256')}"
            ),
        })

    missing_reasons = sorted(set(changed_ids) - set(supersession_reasons))
    extra_reasons = sorted(set(supersession_reasons) - set(changed_ids))
    failures: list[str] = []
    if missing_reasons:
        failures.append(
            "supersession_reasons must explain every removed or materially "
            "changed prior option: " + ", ".join(missing_reasons)
        )
    if extra_reasons:
        failures.append(
            "supersession_reasons references unchanged or unknown prior option(s): "
            + ", ".join(extra_reasons)
        )
    if failures:
        raise WorkbenchInputError(failures)

    result: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in [*previous_uncarried, *requested_uncarried, *superseded]:
        key = (
            row["label"],
            row["disposition"],
            row["reason"],
            row["evidence_or_next_check"],
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _render_report(
    *,
    data: dict,
    decision: dict,
    uncarried: list[dict],
    audit_rows: list[list[str]],
    workbench_revision: int,
    gate_index: int,
    gate_total: int,
    decision_status: str = "awaiting-selection",
    pending_frame_change: dict | None = None,
) -> str:
    options = data["options"]
    option_by_id = {row["option_id"]: row for row in options}
    recommendation = data["recommendation"]
    recommended = option_by_id[recommendation["option_id"]]
    owner = data["evaluation_frame"]["decision_owner"]

    lines = [
        f"# Solution Architecture Options — {data['project_slug']}",
        "",
        f"> Decision status: {decision_status}",
        f"> Workbench revision: {workbench_revision}",
        "",
        (
            "Selection is disabled until planning applies the pending "
            "decision-frame change and the comparison is recomputed."
            if decision_status == "frame-change-pending"
            else "Review this report before answering "
            "**Architecture Direction Selection**."
        ),
        "",
        "## What Needs Your Decision",
        "",
        f"- **Decision:** {_inline(decision['decision'])}",
        f"- **Why now:** {_inline(decision['why_now'])}",
        (
            f"- **Recommendation:** {recommended['option_id']} — "
            f"{_inline(recommended['title'])}"
        ),
        f"- **Recommendation basis:** {_inline(recommendation['basis'])}",
        (
            "- **Confidence / sensitivity:** "
            f"{recommendation['confidence']} / {recommendation['sensitivity']}"
        ),
        (
            "- **Decision owner / authority:** "
            f"{_inline(owner['identity_or_role'])} — "
            f"{_inline(owner['authority_basis'])}"
        ),
        f"- **Current constraints:** {_inline(decision['current_constraints'])}",
        f"- **Key trade-off:** {_inline(decision['key_tradeoff'])}",
        f"- **Cost if wrong:** {_inline(decision['cost_if_wrong'])}",
        (
            "- **Material gaps and inferences:** "
            f"{_inline(decision['material_gaps_and_inferences'])}"
        ),
        "",
        "## Evaluation Frame",
        "",
        f"**Intent:** {_inline(data['evaluation_frame']['project_intent'])}",
        "",
        (
            "**Decision owner:** "
            f"{_inline(owner['identity_or_role'])} — {_inline(owner['authority_basis'])}"
        ),
        "",
        "**Complete frame projection:**",
        "",
        *_json_block(data["evaluation_frame"]),
        "",
        "## Hard-Constraint Screen",
        "",
    ]
    constraints = data["hard_constraints"]
    if constraints:
        headers = ["Constraint", "Authority and basis", *[
            row["option_id"] for row in options
        ]]
        lines.extend([
            "| " + " | ".join(headers) + " |",
            "|" + "|".join("---" for _ in headers) + "|",
        ])
        verdict_by_option = {
            option["option_id"]: {
                row["constraint_id"]: row
                for row in option["constraint_verdicts"]
            }
            for option in options
        }
        for constraint in constraints:
            row = [
                f"{constraint['id']} — {_cell(constraint['statement'])}",
                f"{_cell(constraint['authority'])} — {_cell(constraint['basis'])}",
            ]
            for option in options:
                verdict = verdict_by_option[option["option_id"]][constraint["id"]]
                row.append(
                    f"{verdict['verdict']} — {_cell(verdict['basis'])}"
                )
            lines.append("| " + " | ".join(row) + " |")
    else:
        lines.append("None — the planning frame records no hard constraint.")
    lines.extend([
        "",
        "## Weighted Comparison",
        "",
    ])
    score_maps = {
        option["option_id"]: {
            row["criterion_id"]: row for row in option["scores"]
        }
        for option in options
    }
    headers = ["Criterion", "Weight / basis", *[
        row["option_id"] for row in options
    ]]
    lines.extend([
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ])
    for criterion in data["criteria"]:
        row = [
            criterion["id"],
            f"{criterion['weight']} — {_cell(criterion['basis'])}",
        ]
        for option in options:
            score = score_maps[option["option_id"]].get(criterion["id"])
            if score is None:
                row.append("N/A — hard-constraint eliminated")
            else:
                row.append(
                    f"{score['score']} — {_cell(score['basis'])} — "
                    f"{score['evidence_state']} — {_join(score['evidence'])}"
                )
        lines.append("| " + " | ".join(row) + " |")
    composite = ["**Composite**", "**1.0**"]
    composite.extend(
        f"**{option['weighted_score']}**"
        if option["weighted_score"] is not None
        else "**N/A**"
        for option in options
    )
    lines.append("| " + " | ".join(composite) + " |")
    sensitivity_text = (
        (
            f"{recommendation['sensitivity']} — "
            f"{recommendation['sensitivity_witness']['scenario']} — "
            f"{recommendation['sensitivity_witness']['condition']}"
        )
        if recommendation["sensitivity_witness"] is not None
        else recommendation["sensitivity"]
    )
    lines.extend([
        "",
        f"**Sensitivity:** {_inline(sensitivity_text)}",
        "",
        (
            "**Recommendation confidence and basis:** "
            f"{recommendation['confidence']} — {_inline(recommendation['basis'])}"
        ),
        "",
    ])
    eliminated_ids = {
        row["option_id"] for row in data["eliminated_options"]
    }
    for option in options:
        eligibility = (
            "eligible"
            if option["option_id"] not in eliminated_ids
            else "eliminated by "
            + ", ".join(
                row["constraint_id"]
                for row in option["constraint_verdicts"]
                if row["verdict"] == "fail"
            )
        )
        lines.extend([
            f"## Direction {option['option_id']} — {_inline(option['title'])}",
            "",
            f"**Eligibility:** {eligibility}  ",
            f"**Option hash:** `{option['option_sha256']}`  ",
            f"**Confidence:** {option['confidence']}  ",
            f"**Summary:** {_inline(option['summary'])}",
            "",
            "| Architecture dimension | Complete direction detail |",
            "|---|---|",
        ])
        for label, key in DIMENSIONS:
            lines.append(f"| {label} | {_join(option[key])} |")
        lines.append("")

    lines.extend([
        "## Eliminated, Unresolved, and Uncarried Directions",
        "",
        "| Direction | Disposition | Reason | Evidence or next check |",
        "|---|---|---|---|",
    ])
    eliminated_by_id = {
        row["option_id"]: row for row in data["eliminated_options"]
    }
    if not eliminated_by_id and not uncarried:
        lines.append(
            "| None | none | No eliminated, unresolved, or uncarried direction. | None |"
        )
    for option in options:
        row = eliminated_by_id.get(option["option_id"])
        if row is not None:
            lines.append(
                f"| {option['option_id']} | eliminated | "
                f"{_cell(row['reason'])} | "
                f"{_join(row['constraint_ids'])} |"
            )
    for row in uncarried:
        lines.append(
            f"| {_cell(row['label'])} | {row['disposition']} | "
            f"{_cell(row['reason'])} | {_cell(row['evidence_or_next_check'])} |"
        )
    lines.extend([
        "",
        "**Exact eliminated-options projection:**",
        "",
        *_json_block(data["eliminated_options"]),
        "",
        "## Evidence Sources",
        "",
        "| Path | Kind | SHA-256 |",
        "|---|---|---|",
    ])
    for source in data["sources"]:
        lines.append(
            f"| {_cell(source['path'])} | {source['kind']} | "
            f"`{source['sha256']}` |"
        )
    lines.extend([
        "",
        "## Decision Workbench Audit",
        "",
        (
            "| Revision | Event | Human input / question | "
            "Response or resulting change | Prior report SHA-256 |"
        ),
        "|---:|---|---|---|---|",
    ])
    for row in audit_rows:
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
    if pending_frame_change is not None:
        lines.extend([
            "",
            "## Pending Decision-Frame Change",
            "",
            *_json_block(pending_frame_change),
            "",
            "This exact delta is durable but non-selectable. Planning must apply "
            "it before architecture recomputes the comparison.",
        ])
    lines.extend([
        "",
        "## Machine-Readable Comparison Projection",
        "",
        *_json_block(sl.options_report_projection(data)),
        "",
        "## Human Decision",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Status | {decision_status} |",
        "| Selected direction | Not selected |",
        "| Selected option hash | Not selected |",
        "| Decided by | Not selected |",
        "| Approved by | Not selected |",
        (
            "| Rationale | Planning must apply and recompute the pending "
            "decision-frame change before selection. |"
            if decision_status == "frame-change-pending"
            else "| Rationale | Review the comparison above before choosing. |"
        ),
        "",
        "## Integrity",
        "",
        "| Field | Value |",
        "|---|---|",
        "| Report schema | 1 |",
        f"| Workbench revision | `{workbench_revision}` |",
        f"| Project slug | `{data['project_slug']}` |",
        f"| Capability revision | `{data['source_capability_revision']}` |",
        f"| Exploration attempt | `{data['source_exploration_attempt']}` |",
        f"| Exploration id | `{data['exploration_id']}` |",
        f"| Source input SHA-256 | `{data['source_input_sha256']}` |",
        f"| Evidence fingerprint | `{data['evidence_fingerprint']}` |",
        f"| Option-set SHA-256 | `{data['option_set_sha256']}` |",
        (
            f"| Gate locator | `Gate {gate_index} of {gate_total} — "
            "Architecture Direction Selection` |"
        ),
        "| Report file SHA-256 | Printed by the workbench helper after re-read. |",
        "",
    ])
    return "\n".join(lines)


def _atomic_replace(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    if len(payload) > MAX_OUTPUT_BYTES:
        raise WorkbenchIOError(f"rendered report exceeds {MAX_OUTPUT_BYTES} bytes")
    fd, temporary_name = tempfile.mkstemp(
        prefix=".architecture-options.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _frame_change_receipt_path(report: Path) -> Path:
    return report.with_name(FRAME_CHANGE_RECEIPT_NAME)


def _frame_change_receipt(
    *,
    repo_root: Path,
    report: Path,
    prior_report_sha256: str,
    pending_report_sha256: str,
    pending: dict,
) -> dict:
    return {
        "schema_version": 1,
        "report_path": report.relative_to(repo_root).as_posix(),
        "prior_report_sha256": prior_report_sha256,
        "pending_report_sha256": pending_report_sha256,
        "request_sha256": pending["request_sha256"],
        "delta_sha256": pending["delta_sha256"],
        "pending_id": pending["pending_id"],
    }


def _atomic_create_frame_change_receipt(path: Path, payload: bytes) -> None:
    """Publish a complete control receipt without replacing any existing path."""
    if len(payload) > MAX_RECEIPT_BYTES:
        raise WorkbenchIOError(
            f"frame-change control receipt exceeds {MAX_RECEIPT_BYTES} bytes"
        )
    fd, temporary_name = tempfile.mkstemp(
        prefix=".architecture-frame-change-receipt.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    published = False
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            # A hard-link publishes the already-fsynced bytes atomically and,
            # unlike replace/rename, fails rather than overwriting any file or
            # symlink created after the earlier read-only checks.
            os.link(temporary, path, follow_symlinks=False)
            published = True
        except FileExistsError as exc:
            raise WorkbenchIOError(
                "frame-change control receipt already exists; it was preserved"
            ) from exc
        temporary.unlink()
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        if published and os.path.lexists(path):
            try:
                path.unlink()
            except OSError:
                pass
        raise
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_frame_change_receipt(
    *,
    repo_root: Path,
    report: Path,
) -> tuple[Path, dict]:
    receipt_path = _frame_change_receipt_path(report)
    raw = _safe_regular_bytes(
        receipt_path,
        label="frame-change control receipt",
        max_bytes=MAX_RECEIPT_BYTES,
    )
    value = _strict_json(raw, "frame-change control receipt")
    failures: list[str] = []
    if not isinstance(value, dict):
        raise WorkbenchInputError(
            "frame-change control receipt must be a JSON object"
        )
    _exact_keys(
        value,
        FRAME_CHANGE_RECEIPT_KEYS,
        "frame-change control receipt",
        failures,
    )
    if value.get("schema_version") != 1:
        failures.append("frame-change control receipt schema_version must equal 1")
    expected_path = report.relative_to(repo_root).as_posix()
    if value.get("report_path") != expected_path:
        failures.append(
            "frame-change control receipt report_path does not name the "
            "canonical architecture-options.md"
        )
    for key in (
        "prior_report_sha256",
        "pending_report_sha256",
        "request_sha256",
        "delta_sha256",
    ):
        if not sl._sha(value.get(key)):
            failures.append(
                f"frame-change control receipt {key} must be 64 lowercase hex characters"
            )
    if (
        not isinstance(value.get("pending_id"), str)
        or re.fullmatch(r"FCP-[0-9a-f]{12}", value["pending_id"]) is None
    ):
        failures.append(
            "frame-change control receipt pending_id must match FCP-[0-9a-f]{12}"
        )
    if failures:
        raise WorkbenchInputError(failures)
    return receipt_path, value


def _validate_receipt_binding(
    *,
    receipt: dict,
    report_sha256: str,
    pending: dict,
) -> None:
    expected = {
        "prior_report_sha256": pending.get("prior_report_sha256"),
        "pending_report_sha256": report_sha256,
        "request_sha256": pending.get("request_sha256"),
        "delta_sha256": pending.get("delta_sha256"),
        "pending_id": pending.get("pending_id"),
    }
    mismatched = sorted(
        key for key, value in expected.items() if receipt.get(key) != value
    )
    if mismatched:
        raise WorkbenchInputError(
            "frame-change control receipt does not bind the validated pending "
            "report field(s): " + ", ".join(mismatched)
        )


def _remove_frame_change_receipt(path: Path) -> None:
    raw = _safe_regular_bytes(
        path,
        label="frame-change control receipt",
        max_bytes=MAX_RECEIPT_BYTES,
    )
    removed = False
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise WorkbenchIOError(
                "frame-change control receipt must remain a regular, "
                "non-hard-linked file"
            )
        path.unlink()
        removed = True
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileNotFoundError as exc:
        raise WorkbenchIOError(
            "frame-change control receipt disappeared before it could be consumed"
        ) from exc
    except Exception:
        if removed and not os.path.lexists(path):
            _atomic_create_frame_change_receipt(path, raw)
        raise


def _restore(path: Path, previous: bytes | None) -> None:
    if previous is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    _atomic_replace(path, previous)


def _checkpoint_result(
    data: dict,
    report: Path,
    *,
    selection_status: str = "awaiting-selection",
) -> dict:
    report_hash = hashlib.sha256(report.read_bytes()).hexdigest()
    return {
        "schema_version": 2,
        **data,
        "architecture_options_report": {
            "schema_version": 1,
            "status": "present",
            "path": "architecture-options.md",
            "sha256": report_hash,
            "reason": None,
        },
        "selection": {
            "status": selection_status,
            "option_id": None,
            "option_sha256": None,
            "decided_by": None,
            "approved_by": None,
            "rationale": (
                "Planning must apply and architecture must recompute the pending "
                "decision-frame change before selection."
                if selection_status == "frame-change-pending"
                else "Awaiting an explicit human choice at Architecture "
                "Direction Selection."
            ),
        },
        "next_owner": "ce-plan",
    }


def _render_command(args) -> dict:
    root, exploration_path, output, slug = _canonical_paths(
        args.exploration, args.output, args.repo_root
    )
    exploration_value = _strict_json(
        _safe_regular_bytes(exploration_path, label="architecture exploration input"),
        "architecture exploration input",
    )
    if not isinstance(exploration_value, dict):
        raise WorkbenchInputError("architecture exploration input must be a JSON object")
    if exploration_value.get("project_slug") != slug:
        raise WorkbenchInputError(
            "architecture exploration project_slug does not match its draft directory"
        )
    receipt_path = _frame_change_receipt_path(output)
    receipt_exists = os.path.lexists(receipt_path)
    draft = _read_draft(args.draft)
    previous_arg = args.previous_report
    expected_previous_hash = args.expected_previous_sha256
    if previous_arg is None and expected_previous_hash is not None:
        raise WorkbenchInputError(
            "--expected-previous-sha256 requires --previous-report"
        )
    if previous_arg is not None:
        if not isinstance(expected_previous_hash, str) or not sl._sha(
            expected_previous_hash
        ):
            raise WorkbenchInputError(
                "--previous-report requires --expected-previous-sha256 as "
                "64 lowercase hex characters"
            )
    initial = previous_arg is None
    semantic = _validate_semantic_draft(
        draft, exploration_value, initial=initial
    )

    previous_bytes = (
        _safe_regular_bytes(output, label="existing output", max_bytes=MAX_OUTPUT_BYTES)
        if output.exists()
        else None
    )
    if initial and previous_bytes is not None:
        raise WorkbenchInputError(
            "output already exists; pass --previous-report for a deliberate revision"
        )

    audit_rows: list[list[str]]
    decision_status = "awaiting-selection"
    pending_frame_change: dict | None = None
    applied_pending_id: str | None = None
    receipt_to_consume: Path | None = None
    current_input_hash = sl.canonical_sha256(
        ol._current_exploration_payload(exploration_value)
    )
    if previous_arg is not None:
        previous = (
            previous_arg
            if previous_arg.is_absolute()
            else (Path.cwd() / previous_arg)
        ).absolute()
        if previous != output:
            raise WorkbenchIOError(
                "--previous-report must name the exact output file being revised"
            )
        (
            previous_data,
            previous_decision,
            audit_rows,
            previous_uncarried,
            previous_revision,
            previous_hash,
            previous_status,
            previous_pending_frame_change,
        ) = _extract_previous(
            previous,
            repo_root=root,
            expected_sha256=expected_previous_hash,
        )
        requested_pending = semantic["frame_change_pending"]
        if requested_pending is not None:
            if previous_status != "awaiting-selection":
                raise WorkbenchInputError(
                    "a frame-change-pending checkpoint can only follow a "
                    "selectable awaiting-selection report"
                )
            if previous_data["source_input_sha256"] != current_input_hash:
                raise WorkbenchInputError(
                    "cannot checkpoint a frame change from a stale comparison; "
                    "the current exploration input no longer matches the prior report"
                )
            if receipt_exists:
                raise WorkbenchInputError(
                    "a frame-change control receipt already exists; run "
                    "resume-frame-change --recover-persisted before creating "
                    "another pending checkpoint"
                )
            # Revalidate every durable `before` value against the exact H1
            # projection rather than trusting only the current exploration file.
            _expected_input_after_frame_delta(
                previous_data,
                requested_pending["delta"],
            )
            data = previous_data
            decision = previous_decision
            uncarried = previous_uncarried
            pending_frame_change = _pending_frame_change_payload(
                requested_pending,
                prior_report_sha256=previous_hash,
                gate_index=exploration_value["parent_gate_index"],
                gate_total=exploration_value["parent_gate_total"],
            )
            decision_status = "frame-change-pending"
        elif previous_status == "frame-change-pending":
            if semantic["inherit_comparison"]:
                raise WorkbenchInputError(
                    "frame-change-pending cannot inherit again; planning must "
                    "apply the durable delta and provide a complete recomputed comparison"
                )
            if previous_pending_frame_change is None:
                raise WorkbenchInputError(
                    "previous frame-change-pending report has no validated pending delta"
                )
            receipt_to_consume, receipt = _load_frame_change_receipt(
                repo_root=root,
                report=output,
            )
            _validate_receipt_binding(
                receipt=receipt,
                report_sha256=previous_hash,
                pending=previous_pending_frame_change,
            )
            _prove_frame_delta_applied(
                previous_data=previous_data,
                current_exploration=exploration_value,
                delta=previous_pending_frame_change["delta"],
            )
            applied_pending_id = previous_pending_frame_change["pending_id"]
            event = semantic["audit_event"]
            if event["event"] != "frame-change":
                raise WorkbenchInputError(
                    "recomputation after frame-change-pending requires "
                    "audit_event.event `frame-change`"
                )
            if event["human_input"] != previous_pending_frame_change["request"]:
                raise WorkbenchInputError(
                    "recomputed frame-change audit_event.human_input must exactly "
                    "match the durable pending request"
                )
            data, requested_uncarried = _build_comparison(
                exploration_value, semantic
            )
            uncarried = _merge_considered_alternatives(
                previous_data=previous_data,
                next_data=data,
                previous_uncarried=previous_uncarried,
                requested_uncarried=requested_uncarried,
                supersession_reasons=semantic["supersession_reasons"],
            )
            decision = semantic["decision"]
        elif semantic["inherit_comparison"]:
            if receipt_exists:
                raise WorkbenchInputError(
                    "an unconsumed frame-change control receipt exists; run "
                    "resume-frame-change --recover-persisted before revising "
                    "the selectable report"
                )
            data = previous_data
            decision = previous_decision
            uncarried = previous_uncarried
        else:
            if receipt_exists:
                raise WorkbenchInputError(
                    "an unconsumed frame-change control receipt exists; run "
                    "resume-frame-change --recover-persisted before revising "
                    "the selectable report"
                )
            data, requested_uncarried = _build_comparison(
                exploration_value, semantic
            )
            uncarried = _merge_considered_alternatives(
                previous_data=previous_data,
                next_data=data,
                previous_uncarried=previous_uncarried,
                requested_uncarried=requested_uncarried,
                supersession_reasons=semantic["supersession_reasons"],
            )
            decision = semantic["decision"]
        workbench_revision = previous_revision + 1
        event = (
            {
                "event": "frame-change-pending",
                "human_input": pending_frame_change["request"],
                "response": (
                    "Persisted exact pending decision-frame delta "
                    f"{pending_frame_change['pending_id']}; planning has not applied it."
                ),
            }
            if pending_frame_change is not None
            else (
                {
                    **semantic["audit_event"],
                    "response": (
                        f"{semantic['audit_event']['response']} "
                        "Applied durable decision-frame change "
                        f"{applied_pending_id}."
                    ),
                }
                if applied_pending_id is not None
                else semantic["audit_event"]
            )
        )
        audit_rows.append([
            str(workbench_revision),
            event["event"],
            event["human_input"],
            event["response"],
            previous_hash,
        ])
    else:
        if receipt_exists:
            raise WorkbenchInputError(
                "an unconsumed frame-change control receipt exists; run "
                "resume-frame-change --recover-persisted before initial rendering"
            )
        if semantic["inherit_comparison"]:
            raise WorkbenchInputError("initial render cannot inherit a comparison")
        data, uncarried = _build_comparison(exploration_value, semantic)
        decision = semantic["decision"]
        workbench_revision = 1
        if semantic["frame_change_pending"] is not None:
            raise WorkbenchInputError(
                "initial render cannot create a pending frame change"
            )
        event = semantic["audit_event"]
        audit_rows = [[
            "1",
            event["event"],
            event["human_input"],
            event["response"],
            "None — initial revision",
        ]]

    report = _render_report(
        data=data,
        decision=decision,
        uncarried=uncarried,
        audit_rows=audit_rows,
        workbench_revision=workbench_revision,
        gate_index=exploration_value["parent_gate_index"],
        gate_total=exploration_value["parent_gate_total"],
        decision_status=decision_status,
        pending_frame_change=pending_frame_change,
    )
    payload = report.encode("utf-8")
    created_receipt = False
    try:
        if pending_frame_change is not None:
            pending_report_sha256 = hashlib.sha256(payload).hexdigest()
            receipt = _frame_change_receipt(
                repo_root=root,
                report=output,
                prior_report_sha256=previous_hash,
                pending_report_sha256=pending_report_sha256,
                pending=pending_frame_change,
            )
            receipt_payload = (
                json.dumps(
                    receipt,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
            _atomic_create_frame_change_receipt(receipt_path, receipt_payload)
            created_receipt = True
        _atomic_replace(output, payload)
        if decision_status == "awaiting-selection":
            projection, failures = ol.validate_file(output, repo_root=root)
            if projection is None or failures:
                raise WorkbenchInputError(
                    [
                        "rendered report failed architecture-options-lint",
                        *failures[:20],
                    ]
                )
        result = _checkpoint_result(
            data,
            output,
            selection_status=decision_status,
        )
        selection_failures = sl.validate_document(
            result,
            artifact_path=output.with_name("architecture-selection.json"),
            repo_root=root,
            allow_incomplete=True,
        )
        if selection_failures:
            raise WorkbenchInputError(
                [
                    f"{decision_status} checkpoint failed "
                    "architecture-selection-lint",
                    *selection_failures[:20],
                ]
            )
    except Exception:
        _restore(output, previous_bytes)
        if created_receipt and os.path.lexists(receipt_path):
            _remove_frame_change_receipt(receipt_path)
        raise
    if receipt_to_consume is not None:
        # H3 is committed only after both linters pass. Receipt cleanup is a
        # separate control-state transition: a cleanup error must leave the
        # validated H3 in place for `--recover-persisted`, never roll back to H2.
        _remove_frame_change_receipt(receipt_to_consume)

    return {
        "status": "pass",
        "report": str(output.relative_to(root)),
        "report_sha256": result["architecture_options_report"]["sha256"],
        "workbench_revision": workbench_revision,
        "decision_status": decision_status,
        "selection_enabled": decision_status == "awaiting-selection",
        "exploration_id": data["exploration_id"],
        "eligible_option_ids": (
            [
                option["option_id"]
                for option in data["options"]
                if all(
                    verdict["verdict"] == "pass"
                    for verdict in option["constraint_verdicts"]
                )
            ]
            if decision_status == "awaiting-selection"
            else []
        ),
        "recommendation": data["recommendation"],
        "frame_change_pending": pending_frame_change,
        "result": result,
    }


def _resume_frame_change_command(args) -> dict:
    report = (
        args.report
        if args.report.is_absolute()
        else (Path.cwd() / args.report)
    ).absolute()
    root, _, report, _ = _canonical_paths(
        report.with_name("architecture-exploration.json"),
        report,
        args.repo_root,
    )
    expected = getattr(args, "expected_report_sha256", None)
    recover_persisted = bool(getattr(args, "recover_persisted", False))
    if expected is not None and not sl._sha(expected):
        raise WorkbenchInputError(
            "--expected-report-sha256 must be 64 lowercase hex characters"
        )
    if (expected is None) == (not recover_persisted):
        raise WorkbenchInputError(
            "resume-frame-change requires exactly one of "
            "--expected-report-sha256 or --recover-persisted"
        )

    receipt_path, receipt = _load_frame_change_receipt(
        repo_root=root,
        report=report,
    )
    report_bytes = _safe_regular_bytes(
        report,
        label="architecture options report",
        max_bytes=MAX_OUTPUT_BYTES,
    )
    report_hash = hashlib.sha256(report_bytes).hexdigest()

    if report_hash == receipt["prior_report_sha256"]:
        if not recover_persisted:
            raise WorkbenchInputError(
                "the control receipt was persisted but H2 was not; use "
                "--recover-persisted to validate H1 and discard the "
                "unactivated receipt"
            )
        (
            data,
            _,
            audit_rows,
            _,
            workbench_revision,
            actual_hash,
            decision_status,
            pending,
        ) = _extract_previous(
            report,
            repo_root=root,
            expected_sha256=receipt["prior_report_sha256"],
        )
        projection, failures = ol.validate_file(report, repo_root=root)
        if (
            decision_status != "awaiting-selection"
            or pending is not None
            or projection is None
            or failures
        ):
            raise WorkbenchInputError(
                [
                    "receipt-before-report recovery did not find a valid "
                    "unchanged selectable H1",
                    *failures[:20],
                ]
            )
        _remove_frame_change_receipt(receipt_path)
        return {
            "status": "pass",
            "recovery_state": "prepared-receipt-discarded",
            "report": str(report.relative_to(root)),
            "report_sha256": actual_hash,
            "selectable_prior_report_sha256": actual_hash,
            "unpublished_pending_report_sha256": receipt[
                "pending_report_sha256"
            ],
            "workbench_revision": workbench_revision,
            "decision_status": decision_status,
            "selection_enabled": True,
            "source_capability_revision": data["source_capability_revision"],
            "source_exploration_attempt": data["source_exploration_attempt"],
            "audit_revisions": len(audit_rows),
            "frame_change_pending": None,
            "control_receipt_consumed": True,
        }

    if report_hash == receipt["pending_report_sha256"]:
        if expected is not None and expected != receipt["pending_report_sha256"]:
            raise WorkbenchInputError(
                "--expected-report-sha256 does not match the independently "
                "persisted control receipt H2"
            )
        (
            data,
            _,
            audit_rows,
            _,
            workbench_revision,
            actual_hash,
            decision_status,
            pending,
        ) = _extract_previous(
            report,
            repo_root=root,
            expected_sha256=receipt["pending_report_sha256"],
        )
        if decision_status != "frame-change-pending" or pending is None:
            raise WorkbenchInputError(
                "resume-frame-change requires a validated frame-change-pending report"
            )
        _validate_receipt_binding(
            receipt=receipt,
            report_sha256=actual_hash,
            pending=pending,
        )
        return {
            "status": "pass",
            "recovery_state": (
                "persisted-pending-recovered"
                if recover_persisted
                else "persisted-pending-validated"
            ),
            "report": str(report.relative_to(root)),
            "report_sha256": actual_hash,
            "pending_report_sha256": actual_hash,
            "selectable_prior_report_sha256": pending["prior_report_sha256"],
            "next_expected_previous_sha256": actual_hash,
            "workbench_revision": workbench_revision,
            "decision_status": decision_status,
            "selection_enabled": False,
            "source_capability_revision": data["source_capability_revision"],
            "source_exploration_attempt": data["source_exploration_attempt"],
            "audit_revisions": len(audit_rows),
            "frame_change_pending": pending,
            "control_receipt_consumed": False,
        }

    if not recover_persisted:
        raise WorkbenchInputError(
            "architecture-options.md matches neither H1 nor H2 in the "
            "independent frame-change control receipt"
        )

    # A crash may occur after a validated H3 replaces H2 but before the
    # receipt is removed. Prove that exact transition from the H3 report's
    # lint-valid surface and terminal audit row before consuming the receipt.
    (
        data,
        _,
        audit_rows,
        _,
        workbench_revision,
        actual_hash,
        decision_status,
        pending,
    ) = _extract_previous(
        report,
        repo_root=root,
        expected_sha256=report_hash,
    )
    projection, failures = ol.validate_file(report, repo_root=root)
    if projection is None or failures:
        raise WorkbenchInputError(
            [
                "stale-receipt recovery found an invalid candidate H3",
                *failures[:20],
            ]
        )
    last = audit_rows[-1] if audit_rows else []
    audit_matches = (
        decision_status == "awaiting-selection"
        and pending is None
        and len(last) == len(sl.REPORT_AUDIT_HEADER)
        and last[1] == "frame-change"
        and last[4] == receipt["pending_report_sha256"]
        and hashlib.sha256(last[2].encode("utf-8")).hexdigest()
        == receipt["request_sha256"]
        and receipt["pending_id"] in last[3]
    )
    if not audit_matches:
        raise WorkbenchInputError(
            "stale-receipt recovery could not prove that the selectable report "
            "is the validated H3 successor of receipt-bound H2"
        )
    _remove_frame_change_receipt(receipt_path)
    return {
        "status": "pass",
        "recovery_state": "validated-h3-receipt-consumed",
        "report": str(report.relative_to(root)),
        "report_sha256": actual_hash,
        "pending_report_sha256": receipt["pending_report_sha256"],
        "selectable_prior_report_sha256": receipt["prior_report_sha256"],
        "workbench_revision": workbench_revision,
        "decision_status": decision_status,
        "selection_enabled": True,
        "source_capability_revision": data["source_capability_revision"],
        "source_exploration_attempt": data["source_exploration_attempt"],
        "audit_revisions": len(audit_rows),
        "frame_change_pending": None,
        "control_receipt_consumed": True,
    }


def _template_contract() -> dict:
    return {
        "status": "pass",
        "contract": {
            "schema_version": 1,
            "initial_keys": [
                "schema_version",
                "decision",
                "options",
                "uncarried_options",
                "recommendation",
                "audit_event",
            ],
            "decision": {
                key: "non-empty string"
                for key in (
                    "decision",
                    "why_now",
                    "current_constraints",
                    "key_tradeoff",
                    "cost_if_wrong",
                    "material_gaps_and_inferences",
                )
            },
            "options": (
                "repeat option_prototype 2..4 times, sorted A01..A04; cover every "
                "inherited constraint and criterion in inherited order"
            ),
            "option_prototype": {
                "option_id": "A01",
                "title": "non-empty string",
                "summary": "non-empty string",
                **{
                    key: ["one or more non-empty strings"]
                    for _, key in DIMENSIONS
                },
                "constraint_verdicts": [{
                    "constraint_id": "inherited HC id",
                    "verdict": "pass | fail",
                    "basis": "option-specific non-empty string",
                }],
                "scores": [{
                    "criterion_id": "inherited canonical criterion id",
                    "score": "integer 1..5",
                    "basis": "option-specific non-empty string",
                    "evidence_state": "recorded | observed | inferred | unknown",
                    "evidence": [
                        "inherited source path, or unknown: reason"
                    ],
                }],
                "elimination_reason": (
                    "null when all constraints pass; non-empty string on fail"
                ),
            },
            "uncarried_option": {
                "label": "non-empty string",
                "disposition": "dominance-pruned | uncarried",
                "reason": "non-empty string",
                "evidence_or_next_check": "non-empty string",
            },
            "recommendation": {
                "option_id": "highest-scoring eligible Axx",
                "basis": "non-empty string",
            },
            "audit_event": {
                "event": "initial-synthesis initially; allowed event on revision",
                "human_input": "exact non-empty human request",
                "response": "non-empty result",
            },
            "full_revision_addition": {
                "supersession_reasons": [{
                    "prior_option_id": "every removed or hash-changed prior Axx",
                    "reason": "why it was removed or hash-changed",
                }]
            },
            "derived": [
                "inherited frame and evidence",
                "weighted totals, eliminations, confidence and sensitivity witness",
                "hashes/ids, safe Markdown, audit chain and v2 awaiting-selection result",
            ],
            "limits": {
                "options": "2..4",
                "option_array_items": "1..12",
                "uncarried_options": "0..8",
                "text": "1..4000 characters",
            },
        },
        "inherit_revision_skeleton": {
            "schema_version": 1,
            "inherit_comparison": True,
            "audit_event": {
                "event": "question",
                "human_input": "exact question",
                "response": "evidence-qualified answer; comparison unchanged",
            },
        },
        "frame_change_pending_revision_skeleton": {
            "schema_version": 1,
            "inherit_comparison": True,
            "frame_change_pending": {
                "request": "exact request",
                "delta": {
                    **{key: [] for key in sl.FRAME_CHANGE_LIST_KEYS},
                    "decision_owner": None,
                    "human_reason": "exact reason",
                },
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a deterministic architecture direction workbench"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    template = subparsers.add_parser(
        "template", help="print the compact semantic authoring contract"
    )
    template.add_argument("--json", action="store_true")
    render = subparsers.add_parser(
        "render", help="render and lint architecture-options.md"
    )
    render.add_argument("--exploration", required=True, type=Path)
    render.add_argument(
        "--draft",
        required=True,
        help="semantic comparison JSON path, or - for stdin",
    )
    render.add_argument("--output", required=True, type=Path)
    render.add_argument("--repo-root", required=True, type=Path)
    render.add_argument("--previous-report", type=Path)
    render.add_argument("--expected-previous-sha256")
    render.add_argument("--json", action="store_true")
    resume = subparsers.add_parser(
        "resume-frame-change",
        help="validate and extract a durable non-selectable frame-change checkpoint",
    )
    resume.add_argument("--report", required=True, type=Path)
    resume.add_argument("--repo-root", required=True, type=Path)
    resume_mode = resume.add_mutually_exclusive_group(required=True)
    resume_mode.add_argument("--expected-report-sha256")
    resume_mode.add_argument("--recover-persisted", action="store_true")
    resume.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.command == "template":
            result = _template_contract()
        elif args.command == "resume-frame-change":
            result = _resume_frame_change_command(args)
        else:
            result = _render_command(args)
    except WorkbenchInputError as exc:
        payload = {"status": "fail", "hard_failures": exc.failures}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    except (OSError, WorkbenchIOError) as exc:
        payload = {"status": "error", "message": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:  # noqa: BLE001 - unexpected is never a PASS
        payload = {
            "status": "error",
            "message": f"unexpected: {type(exc).__name__}: {exc}",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
