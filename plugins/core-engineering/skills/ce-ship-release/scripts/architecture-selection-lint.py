#!/usr/bin/env python3
"""Deterministic lint for a plan-root ``architecture-selection.json``.

The artifact binds one human architecture-direction decision to the exact
durable evaluation frame, exploration input hash, evidence inventory, option
set, scorecard, and selected option. A bounded technical fork is carried in
``blocking_decision`` only for a transient ``requires-decision`` result, so its
ce-decide handoff never depends on lost conversation prose. This checker
validates structure and integrity, not whether the architecture judgment is
correct.

Canonical JSON hashes use UTF-8 encoded JSON with sorted object keys, compact
separators, Unicode preserved, and no NaN/Infinity values:

    json.dumps(value, sort_keys=True, separators=(",", ":"),
               ensure_ascii=False, allow_nan=False).encode("utf-8")

Hash scopes:

* ``source_input_sha256`` hashes the canonical decision-relevant exploration
  input reconstructed from this artifact. Parent gate locator fields are
  deliberately excluded because they affect presentation, not the evaluated
  architecture frame.
* ``evidence_fingerprint`` hashes the complete, path-sorted ``sources`` array.
* ``option_sha256`` hashes its option object with only that field removed.
* ``option_set_sha256`` hashes an object containing ordered option id/hash
  bindings plus the complete, ordered ``eliminated_options`` ledger.
* schema v2 ``architecture_options_report.sha256`` binds the exact sibling
  ``architecture-options.md`` bytes the human reviewed before selection.

By default only durable plan-artifact statuses are accepted.  The explicit
``--allow-incomplete`` mode additionally accepts bounded exploration results
that stopped before selection (requires-evidence / requires-decision / blocked /
human-aborted).  Those transient results may omit evaluation sections and can
never claim a selected option or human decision.

Legacy schemas and the one-option reportless adoption shape remain readable only
for explicit migration diagnostics. Active plan and consumer paths use
``--require-current-schema``, which requires schema v2 and a present hash-bound
comparison report for every selected direction.

Exit codes:
  0  PASS  — the artifact is structurally valid and fresh
  1  FAIL  — the artifact loaded but violates the contract
  2  ERROR — the artifact or repository root could not be loaded
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path


SCHEMA_VERSIONS = {1, 2}
CURRENT_SCHEMA_VERSION = 2
EXPLORATION_INPUT_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
PROJECT_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
OPTION_ID_RE = re.compile(r"^A0[1-4]$")

CRITERIA = (
    "requirements-fit",
    "quality-attribute-fit",
    "repository-fit",
    "evolvability",
    "operability",
    "delivery-feasibility",
)
REQUIRED_DRIVER_IDS = (
    "explicit-architecture-deliverable",
    "multi-runtime-or-deployment-boundary",
    "cross-feature-durable-or-async-flow",
    "shared-data-ownership-or-migration",
    "trust-residency-or-sensitive-boundary",
    "shared-protocol-or-schema",
    "platform-or-topology-choice",
    "architecture-determining-nfr",
    "contested-cross-feature-owner",
)
RECOMMENDATION_DRIVER_IDS = (
    "team-policy-recommendation",
    "planned-reuse-recommendation",
    "baseline-preference",
)
DRIVER_IDS = REQUIRED_DRIVER_IDS + RECOMMENDATION_DRIVER_IDS
DRIVER_VERDICTS = {"positive", "negative", "unknown"}
ARCHITECTURE_APPLICABILITY = {"required", "recommended", "not-required"}
EVIDENCE_STATES = {"recorded", "observed", "inferred", "unknown"}
CONSTRAINT_VERDICTS = {"pass", "fail", "unknown"}
CONFIDENCE_STATES = {"high", "medium", "low"}
OPTION_CONFIDENCE_STATES = CONFIDENCE_STATES | {"not-applicable"}
SENSITIVITY_STATES = {"stable", "unstable", "not-applicable"}
SELECTED_STATUSES = {"direction-selected", "adopted-existing"}
UNSELECTED_STATUSES = {"not-applicable", "deferred"}
FINAL_STATUSES = SELECTED_STATUSES | UNSELECTED_STATUSES
TRANSIENT_STATUSES = {
    "requires-evidence", "requires-decision", "blocked", "human-aborted",
}

TOP_KEYS_V1 = {
    "schema_version",
    "project_slug",
    "exploration_id",
    "source_capability_revision",
    "source_exploration_attempt",
    "source_input_sha256",
    "evaluation_frame",
    "blocking_decision",
    "sources",
    "evidence_fingerprint",
    "criteria",
    "hard_constraints",
    "options",
    "eliminated_options",
    "option_set_sha256",
    "recommendation",
    "selection",
    "next_owner",
}
TOP_KEYS_V2 = TOP_KEYS_V1 | {"architecture_options_report"}
TRANSIENT_REQUIRED_TOP_KEYS = {
    "schema_version",
    "project_slug",
    "exploration_id",
    "source_capability_revision",
    "source_exploration_attempt",
    "source_input_sha256",
    "blocking_decision",
    "sources",
    "evidence_fingerprint",
    "selection",
    "next_owner",
}
SOURCE_KEYS = {"path", "sha256", "kind"}
SOURCE_KINDS = {"brief", "brief-sidecar", "adr", "repository", "planning-input"}
EVALUATION_FRAME_KEYS = {
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
}
DECISION_OWNER_KEYS = {"identity_or_role", "authority_basis"}
DRIVER_KEYS = {"id", "verdict", "basis", "evidence"}
ACCEPTED_DECISION_KEYS = {"ref", "summary"}
MATERIAL_GAP_KEYS = {"id", "statement", "cost_if_wrong", "next_check"}
CAPABILITY_KEYS = {"id", "outcome", "actors", "data", "integrations", "observable"}
JOURNEY_KEYS = {
    "id", "outcome", "actors", "capability_refs", "steps", "observable",
}
QUALITY_SCENARIO_KEYS = {
    "id",
    "attribute",
    "stimulus",
    "environment",
    "response",
    "target",
    "priority",
    "evidence",
}
BLOCKING_DECISION_KEYS = {
    "question", "options", "constraints", "evidence", "cost_if_wrong",
}
BLOCKING_OPTION_KEYS = {"id", "title", "consequence", "reversibility"}
CRITERION_KEYS = {"id", "weight", "basis"}
HARD_CONSTRAINT_KEYS = {"id", "statement", "basis", "authority"}
OPTION_ARRAY_KEYS = (
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
)
OPTION_KEYS = {
    "option_id",
    "title",
    "summary",
    *OPTION_ARRAY_KEYS,
    "constraint_verdicts",
    "scores",
    "weighted_score",
    "confidence",
    "option_sha256",
}
CONSTRAINT_VERDICT_KEYS = {"constraint_id", "verdict", "basis"}
SCORE_KEYS = {"criterion_id", "score", "basis", "evidence_state", "evidence"}
ELIMINATED_KEYS = {"option_id", "constraint_ids", "reason"}
RECOMMENDATION_KEYS = {
    "option_id", "confidence", "sensitivity", "sensitivity_witness", "basis",
}
SENSITIVITY_WITNESS_KEYS = {
    "scenario", "criterion_id", "challenger_option_id", "evidence_bounds",
    "condition",
}
SENSITIVITY_WITNESS_SCENARIOS = {
    "base-score", "evidence-range", "weight-minus-25", "weight-plus-25",
}
SENSITIVITY_EVIDENCE_BOUND_KEYS = {"recommended", "challenger"}
SENSITIVITY_EVIDENCE_BOUNDS = {"exact", "lower", "upper"}
SELECTION_KEYS = {
    "status", "option_id", "option_sha256", "decided_by", "approved_by",
    "rationale",
}
REPORT_BINDING_KEYS = {"schema_version", "status", "path", "sha256", "reason"}
REPORT_BINDING_STATUSES = {"present", "not-produced"}
REPORT_REQUIRED_HEADINGS = (
    "## What Needs Your Decision",
    "## Evaluation Frame",
    "## Hard-Constraint Screen",
    "## Weighted Comparison",
    "## Eliminated, Unresolved, and Uncarried Directions",
    "## Evidence Sources",
    "## Decision Workbench Audit",
    "## Machine-Readable Comparison Projection",
    "## Human Decision",
    "## Integrity",
)
REPORT_DECISION_FIELDS = (
    "Decision",
    "Why now",
    "Recommendation",
    "Recommendation basis",
    "Confidence / sensitivity",
    "Decision owner / authority",
    "Cost if wrong",
    "Material gaps and inferences",
)
REPORT_AUDIT_HEADER = (
    "Revision",
    "Event",
    "Human input / question",
    "Response or resulting change",
    "Prior report SHA-256",
)
REPORT_AUDIT_EVENTS = {
    "question",
    "frame-change-requested",
    "frame-change",
    "option-change",
    "alternative-added",
}
REPORT_HIDDEN_HTML_PATTERNS = (
    (
        "collapsed or non-rendered HTML container",
        re.compile(r"<\s*(?:details|template|dialog|script|style|noscript)\b", re.IGNORECASE),
    ),
    (
        "hidden HTML attribute",
        re.compile(r"<[^>\n]*\s(?:hidden|inert)(?:\s|=|/?>)", re.IGNORECASE),
    ),
    (
        "aria-hidden HTML attribute",
        re.compile(
            r"<[^>\n]*\baria-hidden\s*=\s*(?:[\"']\s*true\s*[\"']|true(?:\s|/?>))",
            re.IGNORECASE,
        ),
    ),
    (
        "hidden HTML input",
        re.compile(
            r"<\s*input\b[^>\n]*\btype\s*=\s*(?:[\"']\s*hidden\s*[\"']|hidden(?:\s|/?>))",
            re.IGNORECASE,
        ),
    ),
    (
        "CSS hiding declaration",
        re.compile(
            r"<[^>\n]*\bstyle\s*=\s*[\"'][^\"']*"
            r"(?:display\s*:\s*none|visibility\s*:\s*hidden|"
            r"content-visibility\s*:\s*hidden|"
            r"opacity\s*:\s*0(?:\.0+)?\s*(?:;|[\"']))",
            re.IGNORECASE,
        ),
    ),
    (
        "common hidden CSS class",
        re.compile(
            r"<[^>\n]*\bclass\s*=\s*[\"'][^\"']*"
            r"\b(?:d-none|sr-only|visually-hidden)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "raw HTML element (escape it as Markdown text)",
        re.compile(r"<\s*/?\s*[A-Za-z][^>\n]*>", re.IGNORECASE),
    ),
)


class SelectionLintError(Exception):
    """The artifact cannot be loaded at all (exit 2)."""


def canonical_bytes(value: object) -> bytes:
    """Return the one canonical byte representation used by every JSON hash."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def option_hash(option: dict) -> str:
    payload = {key: value for key, value in option.items() if key != "option_sha256"}
    return canonical_sha256(payload)


def source_input_payload(data: dict) -> dict:
    """Reconstruct the decision-relevant Stage 1A exploration input.

    Parent gate index/total are intentionally absent: they are caller UI state,
    while the attempt identity and every field that can alter architecture
    eligibility or ranking remain hash-bound.
    """
    frame = data.get("evaluation_frame")
    frame = frame if isinstance(frame, dict) else {}
    return {
        "schema_version": EXPLORATION_INPUT_SCHEMA_VERSION,
        "project_slug": data.get("project_slug"),
        "capability_revision": data.get("source_capability_revision"),
        "exploration_attempt": data.get("source_exploration_attempt"),
        "project_intent": frame.get("project_intent"),
        "non_goals": frame.get("non_goals"),
        "decision_owner": frame.get("decision_owner"),
        "architecture_applicability": frame.get("architecture_applicability"),
        "driver_screen": frame.get("driver_screen"),
        "accepted_decisions": frame.get("accepted_decisions"),
        "material_gaps": frame.get("material_gaps"),
        "capabilities": frame.get("capabilities"),
        "journeys": frame.get("journeys"),
        "hard_constraints": data.get("hard_constraints"),
        "quality_attribute_scenarios": frame.get("quality_attribute_scenarios"),
        "criteria": data.get("criteria"),
        "sources": data.get("sources"),
    }


def source_input_hash(data: dict) -> str:
    return canonical_sha256(source_input_payload(data))


def option_set_hash(options: list[dict], eliminated_options: list[dict]) -> str:
    payload = {
        "options": [
            {
                "option_id": option.get("option_id"),
                "option_sha256": option.get("option_sha256"),
            }
            for option in options
        ],
        "eliminated_options": eliminated_options,
    }
    return canonical_sha256(payload)


def infer_repo_root(artifact_path: Path) -> Path:
    """Infer root for the canonical docs/plans/<slug>/ artifact location."""
    plan_dir = artifact_path.parent
    if plan_dir.parent.name == "plans" and plan_dir.parent.parent.name == "docs":
        return plan_dir.parent.parent.parent.resolve()
    return plan_dir.resolve()


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON number {value!r} is not permitted")


def load_artifact(path: Path) -> dict:
    if path.is_dir():
        path = path / "architecture-selection.json"
    if path.is_symlink() or not path.is_file():
        raise SelectionLintError(
            f"architecture-selection.json not found as a regular non-symlink file: {path}"
        )
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"), parse_constant=_reject_constant
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise SelectionLintError(f"could not parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SelectionLintError("architecture-selection.json must be a JSON object")
    return data


def _inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except (OSError, ValueError):
        return False


def _symlink_components(base: Path, candidate: Path) -> list[str]:
    try:
        relative = candidate.absolute().relative_to(base.absolute())
    except ValueError:
        return [str(candidate)]
    found: list[str] = []
    current = base.absolute()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            found.append(current.relative_to(base.absolute()).as_posix())
    return found


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _decimal(value: object) -> Decimal | None:
    if not _is_number(value):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


PLACEHOLDER_VALUES = {
    "-",
    "authority",
    "authority basis",
    "decision maker",
    "decision-maker",
    "human",
    "identity or role",
    "n/a",
    "na",
    "none",
    "null",
    "pending",
    "person or role",
    "someone",
    "tbc",
    "tbd",
    "to be confirmed",
    "to be determined",
    "todo",
    "unknown",
    "unspecified",
}
PLACEHOLDER_PATTERN = re.compile(
    r"(?:<[^>\n]+>|\{\{[^}\n]+\}\}|\$\{[^}\n]+\})"
)


def _substantive(value: object) -> bool:
    """Return whether an authority field is populated beyond a placeholder."""
    if not _nonempty(value):
        return False
    text = value.strip()
    return (
        text.casefold() not in PLACEHOLDER_VALUES
        and PLACEHOLDER_PATTERN.search(text) is None
    )


def _sha(value: object) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def _exact_keys(value: dict, expected: set[str], label: str, failures: list[str]) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing:
        failures.append(f"{label} missing key(s): {', '.join(missing)}")
    if extra:
        failures.append(f"{label} has unknown key(s): {', '.join(extra)}")


def _string_array(value: object, label: str, failures: list[str], *, nonempty=True) -> list[str]:
    if not isinstance(value, list):
        failures.append(f"{label} must be an array of non-empty strings")
        return []
    if nonempty and not value:
        failures.append(f"{label} must not be empty")
    if any(not _nonempty(item) for item in value):
        failures.append(f"{label} must contain only non-empty strings")
        return []
    return [item.strip() for item in value]


def _validate_sources(
    value: object,
    repo_root: Path,
    failures: list[str],
) -> list[dict]:
    if not isinstance(value, list) or not value:
        failures.append("sources must be a non-empty array")
        return []
    sources: list[dict] = []
    paths: list[str] = []
    for index, row in enumerate(value):
        label = f"sources[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{label} must be an object")
            continue
        _exact_keys(row, SOURCE_KEYS, label, failures)
        rel_value = row.get("path")
        expected_hash = row.get("sha256")
        kind = row.get("kind")
        if not _nonempty(rel_value):
            failures.append(f"{label}.path must be a non-empty repository-relative path")
            continue
        rel_text = rel_value.strip()
        rel = Path(rel_text)
        if (
            rel.is_absolute()
            or ".." in rel.parts
            or "\\" in rel_text
            or rel.as_posix() != rel_text
        ):
            failures.append(f"{label}.path is not a canonical repository-relative path")
            continue
        paths.append(rel_text)
        if not _sha(expected_hash):
            failures.append(f"{label}.sha256 must be 64 lowercase hex characters")
        if kind not in SOURCE_KINDS:
            failures.append(
                f"{label}.kind must be one of {sorted(SOURCE_KINDS)}"
            )
        candidate = repo_root / rel
        symlinks = _symlink_components(repo_root, candidate)
        if not _inside(repo_root, candidate) or symlinks:
            failures.append(
                f"{label}.path must resolve beneath the repository without symlinks"
            )
        elif not candidate.is_file():
            failures.append(f"{label}.path does not resolve to a regular file: {rel_text}")
        elif _sha(expected_hash):
            actual = file_sha256(candidate)
            if actual != expected_hash:
                failures.append(
                    f"{label}.sha256 is stale for {rel_text}: expected {expected_hash}, actual {actual}"
                )
        sources.append(row)
    if paths != sorted(paths):
        failures.append("sources must be sorted lexicographically by path")
    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    if duplicates:
        failures.append("sources contains duplicate path(s): " + ", ".join(duplicates))
    return sources


def _evidence_paths(
    value: object,
    label: str,
    source_paths: set[str],
    failures: list[str],
    *,
    nonempty: bool = True,
) -> list[str]:
    paths = _string_array(value, label, failures, nonempty=nonempty)
    missing = sorted(set(paths) - source_paths)
    if missing:
        failures.append(
            f"{label} references path(s) absent from top-level sources: "
            + ", ".join(missing)
        )
    return paths


def _validate_evaluation_frame(
    value: object,
    *,
    source_paths: set[str],
    repo_root: Path,
    failures: list[str],
) -> dict:
    if not isinstance(value, dict):
        failures.append("evaluation_frame must be an object")
        return {}
    _exact_keys(value, EVALUATION_FRAME_KEYS, "evaluation_frame", failures)
    if not _nonempty(value.get("project_intent")):
        failures.append("evaluation_frame.project_intent must be non-empty")
    _string_array(
        value.get("non_goals"),
        "evaluation_frame.non_goals",
        failures,
        nonempty=False,
    )
    decision_owner = value.get("decision_owner")
    if not isinstance(decision_owner, dict):
        failures.append("evaluation_frame.decision_owner must be an object")
    else:
        _exact_keys(
            decision_owner,
            DECISION_OWNER_KEYS,
            "evaluation_frame.decision_owner",
            failures,
        )
        for key in ("identity_or_role", "authority_basis"):
            if not _substantive(decision_owner.get(key)):
                failures.append(
                    f"evaluation_frame.decision_owner.{key} must be a "
                    "non-placeholder value"
                )

    applicability = value.get("architecture_applicability")
    if applicability not in ARCHITECTURE_APPLICABILITY:
        failures.append(
            "evaluation_frame.architecture_applicability must be one of "
            f"{sorted(ARCHITECTURE_APPLICABILITY)}"
        )

    driver_screen = value.get("driver_screen")
    driver_verdicts: dict[str, str] = {}
    driver_ids: list[object] = []
    if not isinstance(driver_screen, list):
        failures.append("evaluation_frame.driver_screen must be an array")
    else:
        for index, row in enumerate(driver_screen):
            label = f"evaluation_frame.driver_screen[{index}]"
            if not isinstance(row, dict):
                failures.append(f"{label} must be an object")
                continue
            _exact_keys(row, DRIVER_KEYS, label, failures)
            did = row.get("id")
            driver_ids.append(did)
            verdict = row.get("verdict")
            if verdict not in DRIVER_VERDICTS:
                failures.append(
                    f"{label}.verdict must be one of {sorted(DRIVER_VERDICTS)}"
                )
            elif isinstance(did, str):
                driver_verdicts[did] = verdict
            if not _nonempty(row.get("basis")):
                failures.append(f"{label}.basis must be non-empty")
            _evidence_paths(
                row.get("evidence"), f"{label}.evidence", source_paths, failures
            )
        if tuple(driver_ids) != DRIVER_IDS:
            failures.append(
                "evaluation_frame.driver_screen must contain every canonical driver "
                f"exactly once in order {list(DRIVER_IDS)}"
            )
    if set(driver_verdicts) == set(DRIVER_IDS):
        required_verdicts = [driver_verdicts[did] for did in REQUIRED_DRIVER_IDS]
        recommendation_verdicts = [
            driver_verdicts[did] for did in RECOMMENDATION_DRIVER_IDS
        ]
        if any(verdict in {"positive", "unknown"} for verdict in required_verdicts):
            expected_applicability = "required"
        elif "unknown" in recommendation_verdicts:
            expected_applicability = None
            failures.append(
                "evaluation_frame recommendation-driver verdicts must resolve to "
                "positive or negative once all load-bearing drivers are negative"
            )
        elif "positive" in recommendation_verdicts:
            expected_applicability = "recommended"
        else:
            expected_applicability = "not-required"
        if (
            expected_applicability is not None
            and applicability in ARCHITECTURE_APPLICABILITY
            and applicability != expected_applicability
        ):
            failures.append(
                "evaluation_frame.architecture_applicability contradicts driver_screen "
                f"(expected {expected_applicability!r})"
            )

    accepted = value.get("accepted_decisions")
    accepted_refs: list[str] = []
    if not isinstance(accepted, list):
        failures.append("evaluation_frame.accepted_decisions must be an array")
    else:
        for index, row in enumerate(accepted):
            label = f"evaluation_frame.accepted_decisions[{index}]"
            if not isinstance(row, dict):
                failures.append(f"{label} must be an object")
                continue
            _exact_keys(row, ACCEPTED_DECISION_KEYS, label, failures)
            ref = row.get("ref")
            if not _nonempty(ref):
                failures.append(f"{label}.ref must be non-empty")
            else:
                ref = ref.strip()
                accepted_refs.append(ref)
                rel = Path(ref)
                if (
                    rel.is_absolute()
                    or ".." in rel.parts
                    or not ref.startswith("docs/adr/")
                    or rel.suffix.lower() != ".md"
                ):
                    failures.append(
                        f"{label}.ref must be a canonical repository-relative docs/adr/*.md path"
                    )
                if ref not in source_paths:
                    failures.append(f"{label}.ref must also occur in top-level sources")
                adr_path = repo_root / rel
                if adr_path.is_file() and not adr_path.is_symlink():
                    text = adr_path.read_text(encoding="utf-8", errors="replace")
                    if re.search(r"^\s*Status\s*:\s*accepted\s*$", text, re.I | re.M) is None:
                        failures.append(f"{label}.ref does not record `Status: accepted`")
            if not _nonempty(row.get("summary")):
                failures.append(f"{label}.summary must be non-empty")
        if accepted_refs != sorted(accepted_refs):
            failures.append("evaluation_frame.accepted_decisions must be sorted by ref")
        duplicates = sorted(
            {ref for ref in accepted_refs if accepted_refs.count(ref) > 1}
        )
        if duplicates:
            failures.append(
                "evaluation_frame.accepted_decisions contains duplicate ref(s): "
                + ", ".join(duplicates)
            )

    gaps = value.get("material_gaps")
    gap_ids: list[str] = []
    if not isinstance(gaps, list):
        failures.append("evaluation_frame.material_gaps must be an array")
    else:
        for index, row in enumerate(gaps):
            label = f"evaluation_frame.material_gaps[{index}]"
            if not isinstance(row, dict):
                failures.append(f"{label} must be an object")
                continue
            _exact_keys(row, MATERIAL_GAP_KEYS, label, failures)
            gid = row.get("id")
            if not isinstance(gid, str) or re.fullmatch(r"G[0-9]{2}", gid) is None:
                failures.append(f"{label}.id must match G[0-9]{{2}}")
            else:
                gap_ids.append(gid)
            for key in ("statement", "cost_if_wrong", "next_check"):
                if not _nonempty(row.get(key)):
                    failures.append(f"{label}.{key} must be non-empty")
        if gap_ids != sorted(gap_ids):
            failures.append("evaluation_frame.material_gaps must be sorted by id")
        duplicates = sorted({gid for gid in gap_ids if gap_ids.count(gid) > 1})
        if duplicates:
            failures.append(
                "evaluation_frame.material_gaps contains duplicate id(s): "
                + ", ".join(duplicates)
            )

    capabilities = value.get("capabilities")
    capability_ids: list[str] = []
    if not isinstance(capabilities, list) or not capabilities:
        failures.append("evaluation_frame.capabilities must be a non-empty array")
    else:
        for index, row in enumerate(capabilities):
            label = f"evaluation_frame.capabilities[{index}]"
            if not isinstance(row, dict):
                failures.append(f"{label} must be an object")
                continue
            _exact_keys(row, CAPABILITY_KEYS, label, failures)
            cid = row.get("id")
            if not isinstance(cid, str) or re.fullmatch(r"C[0-9]{2}", cid) is None:
                failures.append(f"{label}.id must match C[0-9]{{2}}")
            else:
                capability_ids.append(cid)
            for key in ("outcome", "observable"):
                if not _nonempty(row.get(key)):
                    failures.append(f"{label}.{key} must be non-empty")
            for key in ("actors", "data", "integrations"):
                _string_array(row.get(key), f"{label}.{key}", failures)
        if capability_ids != sorted(capability_ids):
            failures.append("evaluation_frame.capabilities must be sorted by id")
        duplicates = sorted(
            {cid for cid in capability_ids if capability_ids.count(cid) > 1}
        )
        if duplicates:
            failures.append(
                "evaluation_frame.capabilities contains duplicate id(s): "
                + ", ".join(duplicates)
            )

    journeys = value.get("journeys")
    journey_ids: list[str] = []
    if not isinstance(journeys, list) or not journeys:
        failures.append("evaluation_frame.journeys must be a non-empty array")
    else:
        for index, row in enumerate(journeys):
            label = f"evaluation_frame.journeys[{index}]"
            if not isinstance(row, dict):
                failures.append(f"{label} must be an object")
                continue
            _exact_keys(row, JOURNEY_KEYS, label, failures)
            jid = row.get("id")
            if not isinstance(jid, str) or re.fullmatch(r"J[0-9]{2}", jid) is None:
                failures.append(f"{label}.id must match J[0-9]{{2}}")
            else:
                journey_ids.append(jid)
            for key in ("outcome", "observable"):
                if not _nonempty(row.get(key)):
                    failures.append(f"{label}.{key} must be non-empty")
            _string_array(row.get("actors"), f"{label}.actors", failures)
            refs = _string_array(
                row.get("capability_refs"), f"{label}.capability_refs", failures
            )
            unknown_refs = sorted(set(refs) - set(capability_ids))
            if unknown_refs:
                failures.append(
                    f"{label}.capability_refs contains unresolved id(s): "
                    + ", ".join(unknown_refs)
                )
            _string_array(row.get("steps"), f"{label}.steps", failures)
        if journey_ids != sorted(journey_ids):
            failures.append("evaluation_frame.journeys must be sorted by id")
        duplicates = sorted({jid for jid in journey_ids if journey_ids.count(jid) > 1})
        if duplicates:
            failures.append(
                "evaluation_frame.journeys contains duplicate id(s): "
                + ", ".join(duplicates)
            )

    scenarios = value.get("quality_attribute_scenarios")
    scenario_ids: list[str] = []
    if not isinstance(scenarios, list):
        failures.append("evaluation_frame.quality_attribute_scenarios must be an array")
    else:
        for index, row in enumerate(scenarios):
            label = f"evaluation_frame.quality_attribute_scenarios[{index}]"
            if not isinstance(row, dict):
                failures.append(f"{label} must be an object")
                continue
            _exact_keys(row, QUALITY_SCENARIO_KEYS, label, failures)
            qid = row.get("id")
            if not isinstance(qid, str) or re.fullmatch(r"QA[0-9]{2}", qid) is None:
                failures.append(f"{label}.id must match QA[0-9]{{2}}")
            else:
                scenario_ids.append(qid)
            for key in (
                "attribute", "stimulus", "environment", "response", "target", "priority"
            ):
                if not _nonempty(row.get(key)):
                    failures.append(f"{label}.{key} must be non-empty")
            _evidence_paths(
                row.get("evidence"), f"{label}.evidence", source_paths, failures
            )
        if scenario_ids != sorted(scenario_ids):
            failures.append(
                "evaluation_frame.quality_attribute_scenarios must be sorted by id"
            )
        duplicates = sorted(
            {qid for qid in scenario_ids if scenario_ids.count(qid) > 1}
        )
        if duplicates:
            failures.append(
                "evaluation_frame.quality_attribute_scenarios contains duplicate id(s): "
                + ", ".join(duplicates)
            )
    return value


def _validate_criteria(value: object, failures: list[str], *, required: bool) -> tuple[list[dict], dict[str, Decimal]]:
    if not isinstance(value, list):
        failures.append("criteria must be an array")
        return [], {}
    if not value and not required:
        return [], {}
    if len(value) != len(CRITERIA):
        failures.append(f"criteria must contain exactly the six canonical ids {list(CRITERIA)}")
    rows: list[dict] = []
    weights: dict[str, Decimal] = {}
    ids: list[object] = []
    for index, row in enumerate(value):
        label = f"criteria[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{label} must be an object")
            continue
        _exact_keys(row, CRITERION_KEYS, label, failures)
        cid = row.get("id")
        ids.append(cid)
        weight = _decimal(row.get("weight"))
        if weight is None or weight < 0 or weight > 1:
            failures.append(f"{label}.weight must be a finite number >= 0 and <= 1")
        elif isinstance(cid, str):
            weights[cid] = weight
        if not _nonempty(row.get("basis")):
            failures.append(f"{label}.basis must be non-empty")
        rows.append(row)
    if tuple(ids) != CRITERIA:
        failures.append(f"criteria ids must appear exactly once in canonical order {list(CRITERIA)}")
    if len(weights) == len(CRITERIA):
        total = sum(weights.values(), Decimal("0"))
        if abs(total - Decimal("1")) > Decimal("0.000000001"):
            failures.append(f"criteria weights must sum to 1 (found {total})")
    return rows, weights


def _validate_constraints(value: object, failures: list[str]) -> tuple[list[dict], list[str]]:
    if not isinstance(value, list):
        failures.append("hard_constraints must be an array")
        return [], []
    rows: list[dict] = []
    ids: list[str] = []
    for index, row in enumerate(value):
        label = f"hard_constraints[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{label} must be an object")
            continue
        _exact_keys(row, HARD_CONSTRAINT_KEYS, label, failures)
        cid = row.get("id")
        if not isinstance(cid, str) or re.fullmatch(r"HC[0-9]{2}", cid) is None:
            failures.append(f"{label}.id must match HC[0-9]{{2}}")
        else:
            ids.append(cid)
        for key in ("statement", "basis", "authority"):
            if not _nonempty(row.get(key)):
                failures.append(f"{label}.{key} must be non-empty")
        rows.append(row)
    duplicates = sorted({cid for cid in ids if ids.count(cid) > 1})
    if duplicates:
        failures.append("hard_constraints contains duplicate id(s): " + ", ".join(duplicates))
    if ids != sorted(ids):
        failures.append("hard_constraints must be sorted by id")
    return rows, ids


def _validate_scores(
    value: object,
    option_label: str,
    weights: dict[str, Decimal],
    source_paths: set[str],
    failures: list[str],
    *,
    eligible: bool,
) -> tuple[dict[str, Decimal], dict[str, str]]:
    if not isinstance(value, list):
        failures.append(f"{option_label}.scores must be an array")
        return {}, {}
    if not eligible:
        if value:
            failures.append(
                f"{option_label}.scores must be empty because hard-constraint "
                "gating made the option ineligible"
            )
        return {}, {}
    ids: list[object] = []
    scores: dict[str, Decimal] = {}
    evidence_states: dict[str, str] = {}
    for index, row in enumerate(value):
        label = f"{option_label}.scores[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{label} must be an object")
            continue
        _exact_keys(row, SCORE_KEYS, label, failures)
        cid = row.get("criterion_id")
        ids.append(cid)
        score = _decimal(row.get("score"))
        if score is None or score != score.to_integral_value() or score < 1 or score > 5:
            failures.append(f"{label}.score must be an integer from 1 through 5")
        elif isinstance(cid, str):
            scores[cid] = score
        evidence_state = row.get("evidence_state")
        if not isinstance(evidence_state, str) or evidence_state not in EVIDENCE_STATES:
            failures.append(
                f"{label}.evidence_state must be one of {sorted(EVIDENCE_STATES)}"
            )
        elif isinstance(cid, str):
            evidence_states[cid] = evidence_state
        evidence = _string_array(row.get("evidence"), f"{label}.evidence", failures)
        if evidence_state == "unknown":
            invalid = sorted(
                item
                for item in evidence
                if item not in source_paths
                and re.fullmatch(r"unknown:\s*\S.*", item, re.I) is None
            )
            if invalid:
                failures.append(
                    f"{label}.evidence unknown entries must be source paths or "
                    "`unknown: <reason>`"
                )
        elif isinstance(evidence_state, str) and evidence_state in EVIDENCE_STATES:
            missing = sorted(set(evidence) - source_paths)
            if missing:
                failures.append(
                    f"{label}.evidence references path(s) absent from top-level "
                    "sources: " + ", ".join(missing)
                )
        if not _nonempty(row.get("basis")):
            failures.append(f"{label}.basis must be non-empty")
    if tuple(ids) != CRITERIA:
        failures.append(
            f"{option_label}.scores must contain all six criteria once in canonical order"
        )
    if weights and set(scores) != set(weights):
        failures.append(f"{option_label}.scores does not match the criterion weight set")
    return scores, evidence_states


def _validate_verdicts(
    value: object,
    option_label: str,
    constraint_ids: list[str],
    failures: list[str],
) -> dict[str, str]:
    if not isinstance(value, list):
        failures.append(f"{option_label}.constraint_verdicts must be an array")
        return {}
    ids: list[object] = []
    verdicts: dict[str, str] = {}
    for index, row in enumerate(value):
        label = f"{option_label}.constraint_verdicts[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{label} must be an object")
            continue
        _exact_keys(row, CONSTRAINT_VERDICT_KEYS, label, failures)
        cid = row.get("constraint_id")
        ids.append(cid)
        verdict = row.get("verdict")
        if not isinstance(verdict, str) or verdict not in CONSTRAINT_VERDICTS:
            failures.append(f"{label}.verdict must be one of {sorted(CONSTRAINT_VERDICTS)}")
        elif isinstance(cid, str):
            verdicts[cid] = verdict
        if not _nonempty(row.get("basis")):
            failures.append(f"{label}.basis must be non-empty")
    if ids != constraint_ids:
        failures.append(
            f"{option_label}.constraint_verdicts must cover every hard constraint once in canonical order"
        )
    return verdicts


def _validate_options(
    value: object,
    constraint_ids: list[str],
    weights: dict[str, Decimal],
    source_paths: set[str],
    failures: list[str],
    *,
    selection_status: str | None,
) -> tuple[
    list[dict],
    dict[str, dict],
    dict[str, dict[str, str]],
    dict[str, dict[str, Decimal]],
    dict[str, dict[str, str]],
]:
    if not isinstance(value, list):
        failures.append("options must be an array")
        return [], {}, {}, {}, {}
    selected = selection_status in SELECTED_STATUSES
    if selected and not 1 <= len(value) <= 4:
        failures.append("selected direction artifacts must contain between 1 and 4 options")
    if selection_status == "direction-selected" and len(value) == 1:
        failures.append(
            "direction-selected exploration must retain at least two genuine "
            "directions; hard-constraint eliminations remain explicit options"
        )
    if len(value) > 4:
        failures.append("options may contain at most 4 entries")
    options: list[dict] = []
    by_id: dict[str, dict] = {}
    verdicts_by_id: dict[str, dict[str, str]] = {}
    scores_by_id: dict[str, dict[str, Decimal]] = {}
    evidence_states_by_id: dict[str, dict[str, str]] = {}
    ids: list[str] = []
    for index, option in enumerate(value):
        label = f"options[{index}]"
        if not isinstance(option, dict):
            failures.append(f"{label} must be an object")
            continue
        _exact_keys(option, OPTION_KEYS, label, failures)
        oid = option.get("option_id")
        if not isinstance(oid, str) or OPTION_ID_RE.fullmatch(oid) is None:
            failures.append(f"{label}.option_id must be one of A01 through A04")
            oid_label = label
        else:
            ids.append(oid)
            oid_label = f"option {oid}"
            by_id[oid] = option
        for key in ("title", "summary"):
            if not _nonempty(option.get(key)):
                failures.append(f"{oid_label}.{key} must be non-empty")
        for key in OPTION_ARRAY_KEYS:
            _string_array(option.get(key), f"{oid_label}.{key}", failures)
        verdicts = _validate_verdicts(
            option.get("constraint_verdicts"), oid_label, constraint_ids, failures
        )
        if isinstance(oid, str):
            verdicts_by_id[oid] = verdicts
        if selected and any(verdict == "unknown" for verdict in verdicts.values()):
            failures.append(
                f"{oid_label} retains an unknown hard-constraint verdict in a "
                "selected-direction artifact; return requires-evidence"
            )
        eligible_for_weighting = (
            set(verdicts) == set(constraint_ids)
            and all(verdict == "pass" for verdict in verdicts.values())
        )
        scores, evidence_states = _validate_scores(
            option.get("scores"),
            oid_label,
            weights,
            source_paths,
            failures,
            eligible=eligible_for_weighting,
        )
        if isinstance(oid, str):
            scores_by_id[oid] = scores
            evidence_states_by_id[oid] = evidence_states
        weighted_value = option.get("weighted_score")
        weighted = _decimal(weighted_value)
        if not eligible_for_weighting:
            if weighted_value is not None:
                failures.append(
                    f"{oid_label}.weighted_score must be null when any hard "
                    "constraint is fail or unknown"
                )
        elif weighted is None:
            failures.append(
                f"{oid_label}.weighted_score must be a finite number for an eligible option"
            )
        elif set(weights) == set(CRITERIA) and set(scores) == set(CRITERIA):
            expected = sum(weights[cid] * scores[cid] for cid in CRITERIA)
            if abs(weighted - expected) > Decimal("0.000001"):
                failures.append(
                    f"{oid_label}.weighted_score must equal the weighted score vector "
                    f"(expected {expected}, found {weighted})"
                )
        confidence = option.get("confidence")
        if not isinstance(confidence, str) or confidence not in OPTION_CONFIDENCE_STATES:
            failures.append(
                f"{oid_label}.confidence must be one of "
                f"{sorted(OPTION_CONFIDENCE_STATES)}"
            )
        elif eligible_for_weighting and confidence == "not-applicable":
            failures.append(
                f"{oid_label}.confidence cannot be not-applicable for an eligible option"
            )
        elif not eligible_for_weighting and confidence != "not-applicable":
            failures.append(
                f"{oid_label}.confidence must be not-applicable when hard-constraint "
                "gating made the option ineligible"
            )
        elif confidence == "high" and any(
            state in {"inferred", "unknown"} for state in evidence_states.values()
        ):
            failures.append(
                f"{oid_label}.confidence cannot be high when a scoring basis is "
                "inferred or unknown"
            )
        supplied_hash = option.get("option_sha256")
        if not _sha(supplied_hash):
            failures.append(f"{oid_label}.option_sha256 must be 64 lowercase hex characters")
        else:
            expected_hash = option_hash(option)
            if supplied_hash != expected_hash:
                failures.append(
                    f"{oid_label}.option_sha256 mismatch: expected {expected_hash}"
                )
        options.append(option)
    duplicates = sorted({oid for oid in ids if ids.count(oid) > 1})
    if duplicates:
        failures.append("options contains duplicate option_id(s): " + ", ".join(duplicates))
    if ids != sorted(ids):
        failures.append("options must be sorted by option_id")
    return options, by_id, verdicts_by_id, scores_by_id, evidence_states_by_id


def _validate_eliminated(
    value: object,
    by_id: dict[str, dict],
    verdicts_by_id: dict[str, dict[str, str]],
    failures: list[str],
) -> list[dict]:
    if not isinstance(value, list):
        failures.append("eliminated_options must be an array")
        return []
    rows: list[dict] = []
    ids: list[str] = []
    for index, row in enumerate(value):
        label = f"eliminated_options[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{label} must be an object")
            continue
        _exact_keys(row, ELIMINATED_KEYS, label, failures)
        oid = row.get("option_id")
        if not isinstance(oid, str) or oid not in by_id:
            failures.append(f"{label}.option_id must reference an option")
        else:
            ids.append(oid)
        constraint_ids = _string_array(
            row.get("constraint_ids"), f"{label}.constraint_ids", failures
        )
        if not _nonempty(row.get("reason")):
            failures.append(f"{label}.reason must be non-empty")
        if isinstance(oid, str) and oid in verdicts_by_id:
            expected = [
                cid for cid, verdict in verdicts_by_id[oid].items() if verdict == "fail"
            ]
            if constraint_ids != expected:
                failures.append(
                    f"{label}.constraint_ids must equal the option's failing constraints {expected}"
                )
        rows.append(row)
    if ids != sorted(ids):
        failures.append("eliminated_options must be sorted by option_id")
    duplicates = sorted({oid for oid in ids if ids.count(oid) > 1})
    if duplicates:
        failures.append(
            "eliminated_options contains duplicate option_id(s): " + ", ".join(duplicates)
        )
    expected_ids = sorted(
        oid
        for oid, verdicts in verdicts_by_id.items()
        if any(verdict == "fail" for verdict in verdicts.values())
    )
    if ids != expected_ids:
        failures.append(
            f"eliminated_options must exactly cover options with failing constraints {expected_ids}"
        )
    return rows


def _eligible(oid: object, verdicts_by_id: dict[str, dict[str, str]]) -> bool:
    return (
        isinstance(oid, str)
        and oid in verdicts_by_id
        and all(verdict == "pass" for verdict in verdicts_by_id[oid].values())
    )


def _sensitivity_weight_vectors(
    weights: dict[str, Decimal],
) -> list[tuple[str, str | None, dict[str, Decimal]]]:
    """Return named deterministic base and +/-25% weight scenarios."""
    if set(weights) != set(CRITERIA):
        return []
    vectors = [("base-score", None, dict(weights))]
    seen = [dict(weights)]
    one = Decimal("1")
    for criterion_id in CRITERIA:
        original = weights[criterion_id]
        if original <= 0:
            continue
        others_total = one - original
        if others_total <= 0:
            continue
        for factor, scenario in (
            (Decimal("0.75"), "weight-minus-25"),
            (Decimal("1.25"), "weight-plus-25"),
        ):
            target = min(one, original * factor)
            remainder = one - target
            vector = {
                cid: (
                    target
                    if cid == criterion_id
                    else weights[cid] * remainder / others_total
                )
                for cid in CRITERIA
            }
            if vector not in seen:
                seen.append(vector)
                vectors.append((scenario, criterion_id, vector))
    return vectors


def _score_bounds(score: Decimal, evidence_state: str) -> tuple[Decimal, Decimal]:
    if evidence_state == "unknown":
        return Decimal("1"), Decimal("5")
    if evidence_state == "inferred":
        return max(Decimal("1"), score - 1), min(Decimal("5"), score + 1)
    return score, score


def _sensitivity_condition(
    *,
    scenario: str,
    criterion_id: str | None,
    recommended_id: str,
    challenger_id: str,
    evidence_bounds: dict[str, str],
) -> str:
    """Return the canonical human-readable statement for a computed witness."""
    if scenario == "base-score":
        prefix = "At base weights with exact scores"
    elif scenario == "evidence-range":
        prefix = (
            f"At base weights with {recommended_id} at lower evidence bounds "
            f"and {challenger_id} at upper evidence bounds"
        )
    else:
        direction = "decreased" if scenario == "weight-minus-25" else "increased"
        prefix = f"With {criterion_id} weight {direction} by 25%"
        if evidence_bounds["recommended"] == "exact":
            prefix += " and exact scores"
        else:
            prefix += (
                f", {recommended_id} at lower evidence bounds, and "
                f"{challenger_id} at upper evidence bounds"
            )
    return f"{prefix}, {challenger_id} ties or exceeds {recommended_id}."


def _validate_ranking_integrity(
    recommendation: dict,
    by_id: dict[str, dict],
    verdicts_by_id: dict[str, dict[str, str]],
    scores_by_id: dict[str, dict[str, Decimal]],
    evidence_states_by_id: dict[str, dict[str, str]],
    weights: dict[str, Decimal],
    failures: list[str],
) -> None:
    """Recompute the recommended leader, sensitivity, and confidence bounds."""
    recommended_id = recommendation.get("option_id")
    eligible_ids = [
        oid
        for oid in sorted(by_id)
        if _eligible(oid, verdicts_by_id)
        and set(scores_by_id.get(oid, {})) == set(CRITERIA)
        and set(evidence_states_by_id.get(oid, {})) == set(CRITERIA)
    ]
    if not isinstance(recommended_id, str) or recommended_id not in eligible_ids:
        return
    if set(weights) != set(CRITERIA):
        return

    totals = {
        oid: sum(
            weights[cid] * scores_by_id[oid][cid]
            for cid in CRITERIA
        )
        for oid in eligible_ids
    }
    best_total = max(totals.values())
    if totals[recommended_id] < best_total:
        leaders = ", ".join(
            oid for oid in eligible_ids if totals[oid] == best_total
        )
        failures.append(
            "recommendation.option_id must reference a highest weighted-score "
            f"eligible option (leader(s): {leaders})"
        )

    expected_witness: dict[str, object] | None = None
    if len(eligible_ids) == 1:
        expected_sensitivity = "not-applicable"
    else:
        stable = True
        for scenario, criterion_id, vector in _sensitivity_weight_vectors(weights):
            recommended_low = sum(
                vector[cid]
                * _score_bounds(
                    scores_by_id[recommended_id][cid],
                    evidence_states_by_id[recommended_id][cid],
                )[0]
                for cid in CRITERIA
            )
            for oid in eligible_ids:
                if oid == recommended_id:
                    continue
                competitor_high = sum(
                    vector[cid]
                    * _score_bounds(
                        scores_by_id[oid][cid],
                        evidence_states_by_id[oid][cid],
                    )[1]
                    for cid in CRITERIA
                )
                if competitor_high >= recommended_low:
                    stable = False
                    witness_scenario = scenario
                    recommended_exact = sum(
                        vector[cid] * scores_by_id[recommended_id][cid]
                        for cid in CRITERIA
                    )
                    competitor_exact = sum(
                        vector[cid] * scores_by_id[oid][cid]
                        for cid in CRITERIA
                    )
                    exact_flip = competitor_exact >= recommended_exact
                    if scenario == "base-score" and not exact_flip:
                        witness_scenario = "evidence-range"
                    evidence_bounds = (
                        {"recommended": "exact", "challenger": "exact"}
                        if exact_flip
                        else {"recommended": "lower", "challenger": "upper"}
                    )
                    witness_criterion = (
                        criterion_id
                        if witness_scenario.startswith("weight-")
                        else None
                    )
                    expected_witness = {
                        "scenario": witness_scenario,
                        "criterion_id": witness_criterion,
                        "challenger_option_id": oid,
                        "evidence_bounds": evidence_bounds,
                        "condition": _sensitivity_condition(
                            scenario=witness_scenario,
                            criterion_id=witness_criterion,
                            recommended_id=recommended_id,
                            challenger_id=oid,
                            evidence_bounds=evidence_bounds,
                        ),
                    }
                    break
            if not stable:
                break
        expected_sensitivity = "stable" if stable else "unstable"

    supplied_sensitivity = recommendation.get("sensitivity")
    if supplied_sensitivity != expected_sensitivity:
        failures.append(
            "recommendation.sensitivity does not match the deterministic "
            f"weight/evidence range test (expected {expected_sensitivity})"
        )

    supplied_witness = recommendation.get("sensitivity_witness")
    if expected_witness is None:
        if supplied_witness is not None:
            failures.append(
                "recommendation.sensitivity_witness must be null when the "
                "deterministic sensitivity result is stable or not-applicable"
            )
    elif isinstance(supplied_witness, dict):
        for key, expected in expected_witness.items():
            if supplied_witness.get(key) != expected:
                failures.append(
                    f"recommendation.sensitivity_witness.{key} does not match "
                    f"the first deterministic leader-changing scenario "
                    f"(expected {expected!r})"
                )

    recommendation_confidence = recommendation.get("confidence")
    recommended_states = evidence_states_by_id[recommended_id].values()
    if recommendation_confidence == "high" and any(
        state in {"inferred", "unknown"} for state in recommended_states
    ):
        failures.append(
            "recommendation.confidence cannot be high when a recommended-option "
            "scoring basis is inferred or unknown"
        )
    if expected_sensitivity == "unstable":
        if recommendation_confidence != "low":
            failures.append(
                "recommendation.confidence must be low when sensitivity is unstable"
            )
        if by_id[recommended_id].get("confidence") != "low":
            failures.append(
                f"option {recommended_id}.confidence must be low when its "
                "recommendation is sensitivity-unstable"
            )


def _validate_blocking_decision(
    value: object,
    *,
    status: object,
    failures: list[str],
) -> None:
    if status != "requires-decision":
        if value is not None:
            failures.append(
                "blocking_decision must be null unless selection.status is "
                "requires-decision"
            )
        return
    if not isinstance(value, dict):
        failures.append(
            "requires-decision must supply a blocking_decision object"
        )
        return
    _exact_keys(value, BLOCKING_DECISION_KEYS, "blocking_decision", failures)
    if not _nonempty(value.get("question")):
        failures.append("blocking_decision.question must be non-empty")
    if not _nonempty(value.get("cost_if_wrong")):
        failures.append("blocking_decision.cost_if_wrong must be non-empty")
    _string_array(
        value.get("constraints"), "blocking_decision.constraints", failures
    )
    _string_array(value.get("evidence"), "blocking_decision.evidence", failures)
    options = value.get("options")
    option_ids: list[str] = []
    if not isinstance(options, list) or not 2 <= len(options) <= 4:
        failures.append("blocking_decision.options must contain between 2 and 4 options")
        return
    for index, option in enumerate(options):
        label = f"blocking_decision.options[{index}]"
        if not isinstance(option, dict):
            failures.append(f"{label} must be an object")
            continue
        _exact_keys(option, BLOCKING_OPTION_KEYS, label, failures)
        oid = option.get("id")
        if not _nonempty(oid):
            failures.append(f"{label}.id must be non-empty")
        else:
            option_ids.append(oid.strip())
        for key in ("title", "consequence", "reversibility"):
            if not _nonempty(option.get(key)):
                failures.append(f"{label}.{key} must be non-empty")
    duplicates = sorted({oid for oid in option_ids if option_ids.count(oid) > 1})
    if duplicates:
        failures.append(
            "blocking_decision.options contains duplicate id(s): "
            + ", ".join(duplicates)
        )


def _validate_recommendation(
    value: object,
    by_id: dict[str, dict],
    verdicts_by_id: dict[str, dict[str, str]],
    failures: list[str],
    *,
    selected: bool,
) -> dict:
    if not isinstance(value, dict):
        failures.append("recommendation must be an object")
        return {}
    _exact_keys(value, RECOMMENDATION_KEYS, "recommendation", failures)
    oid = value.get("option_id")
    if selected and not isinstance(oid, str):
        failures.append("selected direction artifacts require recommendation.option_id")
    if oid is not None:
        if not isinstance(oid, str) or oid not in by_id:
            failures.append("recommendation.option_id must reference an option or be null")
        elif not _eligible(oid, verdicts_by_id):
            failures.append(
                "recommendation.option_id cannot reference an option with a fail/unknown hard constraint"
            )
    if not isinstance(value.get("confidence"), str) or value.get("confidence") not in CONFIDENCE_STATES:
        failures.append(
            f"recommendation.confidence must be one of {sorted(CONFIDENCE_STATES)}"
        )
    if not isinstance(value.get("sensitivity"), str) or value.get("sensitivity") not in SENSITIVITY_STATES:
        failures.append(
            f"recommendation.sensitivity must be one of {sorted(SENSITIVITY_STATES)}"
        )
    witness = value.get("sensitivity_witness")
    if value.get("sensitivity") == "unstable":
        if not isinstance(witness, dict):
            failures.append(
                "unstable recommendation requires a sensitivity_witness object"
            )
        else:
            _exact_keys(
                witness,
                SENSITIVITY_WITNESS_KEYS,
                "recommendation.sensitivity_witness",
                failures,
            )
            scenario = witness.get("scenario")
            if scenario not in SENSITIVITY_WITNESS_SCENARIOS:
                failures.append(
                    "recommendation.sensitivity_witness.scenario must be one of "
                    f"{sorted(SENSITIVITY_WITNESS_SCENARIOS)}"
                )
            criterion_id = witness.get("criterion_id")
            if scenario in {"weight-minus-25", "weight-plus-25"}:
                if criterion_id not in CRITERIA:
                    failures.append(
                        "a weight sensitivity witness requires a canonical "
                        "criterion_id"
                    )
            elif criterion_id is not None:
                failures.append(
                    "a base-score or evidence-range sensitivity witness requires "
                    "criterion_id null"
                )
            evidence_bounds = witness.get("evidence_bounds")
            if not isinstance(evidence_bounds, dict):
                failures.append(
                    "recommendation.sensitivity_witness.evidence_bounds must be "
                    "an object"
                )
            else:
                _exact_keys(
                    evidence_bounds,
                    SENSITIVITY_EVIDENCE_BOUND_KEYS,
                    "recommendation.sensitivity_witness.evidence_bounds",
                    failures,
                )
                for role in sorted(SENSITIVITY_EVIDENCE_BOUND_KEYS):
                    if evidence_bounds.get(role) not in SENSITIVITY_EVIDENCE_BOUNDS:
                        failures.append(
                            "recommendation.sensitivity_witness.evidence_bounds."
                            f"{role} must be one of "
                            f"{sorted(SENSITIVITY_EVIDENCE_BOUNDS)}"
                        )
            challenger = witness.get("challenger_option_id")
            if not isinstance(challenger, str) or challenger not in by_id:
                failures.append(
                    "recommendation.sensitivity_witness.challenger_option_id "
                    "must reference an option"
                )
            elif challenger == oid:
                failures.append(
                    "recommendation.sensitivity_witness.challenger_option_id "
                    "must differ from recommendation.option_id"
                )
            if not _nonempty(witness.get("condition")):
                failures.append(
                    "recommendation.sensitivity_witness.condition must be non-empty"
                )
    elif witness is not None:
        failures.append(
            "recommendation.sensitivity_witness must be null unless sensitivity "
            "is unstable"
        )
    if oid is None and value.get("sensitivity") != "not-applicable":
        failures.append(
            "recommendation.sensitivity must be not-applicable when "
            "recommendation.option_id is null"
        )
    if not _nonempty(value.get("basis")):
        failures.append("recommendation.basis must be non-empty")
    return value


def _validate_selection(
    value: object,
    by_id: dict[str, dict],
    verdicts_by_id: dict[str, dict[str, str]],
    failures: list[str],
    *,
    allow_incomplete: bool,
    decision_owner: dict | None = None,
) -> tuple[str | None, bool]:
    if not isinstance(value, dict):
        failures.append("selection must be an object")
        return None, False
    status = value.get("status")
    transient = allow_incomplete and status in TRANSIENT_STATUSES
    if transient:
        extra = sorted(set(value) - SELECTION_KEYS)
        if extra:
            failures.append("selection has unknown key(s): " + ", ".join(extra))
        for key in ("option_id", "option_sha256", "approved_by"):
            if value.get(key) is not None:
                failures.append(f"transient selection.{key} must be null")
        if value.get("decided_by") is not None:
            failures.append("transient selection.decided_by must be null")
        if not _nonempty(value.get("rationale")):
            failures.append("transient selection.rationale must be non-empty")
        return status, True

    _exact_keys(value, SELECTION_KEYS, "selection", failures)
    if status not in FINAL_STATUSES:
        failures.append(f"selection.status must be one of {sorted(FINAL_STATUSES)}")
    selected = status in SELECTED_STATUSES
    oid = value.get("option_id")
    selected_hash = value.get("option_sha256")
    if selected:
        if not isinstance(oid, str) or oid not in by_id:
            failures.append("selected selection.option_id must reference an option")
        else:
            if not _eligible(oid, verdicts_by_id):
                failures.append(
                    "selected option has a fail/unknown hard constraint and is ineligible"
                )
            expected_hash = by_id[oid].get("option_sha256")
            if selected_hash != expected_hash:
                failures.append(
                    "selection.option_sha256 must match the selected option's canonical hash"
                )
        if not _sha(selected_hash):
            failures.append("selected selection.option_sha256 must be 64 lowercase hex characters")
    else:
        if oid is not None or selected_hash is not None:
            failures.append(
                "not-applicable/deferred selections require null option_id and option_sha256"
            )
    if value.get("decided_by") != "human":
        failures.append("final selection.decided_by must be 'human'")
    approved_by = value.get("approved_by")
    if selected:
        owner_identity = (
            decision_owner.get("identity_or_role")
            if isinstance(decision_owner, dict)
            else None
        )
        if not _substantive(approved_by):
            failures.append(
                "selected selection.approved_by must be a non-placeholder "
                "human identity or role"
            )
        elif isinstance(owner_identity, str) and approved_by != owner_identity:
            failures.append(
                "selected selection.approved_by must exactly match "
                "evaluation_frame.decision_owner.identity_or_role; delegation "
                "requires revising the decision owner before selection"
            )
    elif approved_by is not None:
        failures.append(
            "not-applicable/deferred selections require selection.approved_by null"
        )
    if not _nonempty(value.get("rationale")):
        failures.append("selection.rationale must be non-empty")
    return status if isinstance(status, str) else None, False


def _report_table_value(text: str, label: str) -> str | None:
    pattern = re.compile(
        rf"^\|\s*{re.escape(label)}\s*\|\s*(.*?)\s*\|\s*$", re.MULTILINE
    )
    matches = pattern.findall(text)
    return matches[0] if len(matches) == 1 else None


def _report_scalar_values(value: object) -> list[str]:
    """Flatten decision-support scalar values that must remain visible."""
    if isinstance(value, dict):
        result: list[str] = []
        for child in value.values():
            result.extend(_report_scalar_values(child))
        return result
    if isinstance(value, list):
        result = []
        for child in value:
            result.extend(_report_scalar_values(child))
        return result
    if isinstance(value, str) and value.strip():
        return [value]
    if _is_number(value):
        return [str(value)]
    return []


def _normalized_report_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace(r"\|", "|")).strip()


def _report_section_body(text: str, heading: str) -> str | None:
    """Return one level-two report section body, excluding later sections."""
    matches = re.findall(
        rf"^{re.escape(heading)}[ \t]*\r?\n(.*?)(?=^##\s|\Z)",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    return matches[0] if len(matches) == 1 else None


def _markdown_table_cells(line: str) -> list[str] | None:
    """Split one Markdown table row while preserving escaped pipe characters."""
    stripped = line.strip()
    if len(stripped) < 2 or not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells: list[str] = []
    current: list[str] = []
    index = 1
    while index < len(stripped) - 1:
        char = stripped[index]
        if char == "\\" and index + 1 < len(stripped) - 1:
            following = stripped[index + 1]
            if following == "|":
                current.append("|")
                index += 2
                continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    cells.append("".join(current).strip())
    return cells


def _validate_workbench_audit(
    text: str,
    *,
    workbench_revision: int | None,
    failures: list[str],
) -> None:
    """Validate the durable question/adjustment history in the review report."""
    body = _report_section_body(text, "## Decision Workbench Audit")
    if body is None:
        return  # the exact-heading check emits the structural failure
    lines = body.splitlines()
    header_indexes = [
        index
        for index, line in enumerate(lines)
        if tuple(_markdown_table_cells(line) or ()) == REPORT_AUDIT_HEADER
    ]
    if len(header_indexes) != 1:
        failures.append(
            "architecture options report Decision Workbench Audit must contain "
            "exactly one canonical audit table header"
        )
        return

    header_index = header_indexes[0]
    separator_index = header_index + 1
    while separator_index < len(lines) and not lines[separator_index].strip():
        separator_index += 1
    separator = (
        _markdown_table_cells(lines[separator_index])
        if separator_index < len(lines)
        else None
    )
    if (
        separator is None
        or len(separator) != len(REPORT_AUDIT_HEADER)
        or any(re.fullmatch(r":?-{3,}:?", cell) is None for cell in separator)
    ):
        failures.append(
            "architecture options report Decision Workbench Audit must use a "
            "five-column Markdown separator row"
        )
        return

    raw_rows: list[list[str]] = []
    for line in lines[separator_index + 1 :]:
        if not line.strip():
            if raw_rows:
                break
            continue
        cells = _markdown_table_cells(line)
        if cells is None:
            if raw_rows:
                break
            continue
        raw_rows.append(cells)
    if not raw_rows:
        failures.append(
            "architecture options report Decision Workbench Audit must contain "
            "at least the initial-synthesis row"
        )
        return

    revisions: list[int] = []
    for row_index, row in enumerate(raw_rows, start=1):
        label = f"Decision Workbench Audit row {row_index}"
        if len(row) != len(REPORT_AUDIT_HEADER):
            failures.append(f"{label} must contain exactly five cells")
            continue
        revision_text, event, human_input, response, prior_hash = row
        if re.fullmatch(r"[1-9][0-9]*", revision_text) is None:
            failures.append(f"{label} Revision must be a positive integer")
        else:
            revisions.append(int(revision_text))
        event = event.strip("` ")
        if row_index == 1:
            if event != "initial-synthesis":
                failures.append(
                    "Decision Workbench Audit row 1 Event must equal "
                    "`initial-synthesis`"
                )
            if _normalized_report_text(prior_hash) != "None — initial revision":
                failures.append(
                    "Decision Workbench Audit row 1 Prior report SHA-256 must "
                    "equal `None — initial revision`"
                )
        else:
            if event not in REPORT_AUDIT_EVENTS:
                failures.append(
                    f"{label} Event must be one of "
                    f"{sorted(REPORT_AUDIT_EVENTS)}"
                )
            normalized_hash = prior_hash.strip("` ")
            if not _sha(normalized_hash):
                failures.append(
                    f"{label} Prior report SHA-256 must be 64 lowercase hex "
                    "characters"
                )
        if not _substantive(human_input):
            failures.append(f"{label} Human input / question must be substantive")
        if not _substantive(response):
            failures.append(
                f"{label} Response or resulting change must be substantive"
            )

    if workbench_revision is not None:
        expected_revisions = list(range(1, workbench_revision + 1))
        if revisions != expected_revisions:
            failures.append(
                "architecture options report Decision Workbench Audit revisions "
                f"must be contiguous 1..{workbench_revision} and end at the "
                "declared Workbench revision"
            )


def _require_section_projection(
    text: str,
    heading: str,
    projection: object,
    failures: list[str],
    *,
    require_explicit_negative: bool = False,
) -> None:
    """Keep machine JSON from substituting for a human comparison section."""
    body = _report_section_body(text, heading)
    if body is None:
        return  # the exact-heading check emits the structural failure
    normalized_body = _normalized_report_text(body)
    if not normalized_body:
        failures.append(
            f"architecture options report section {heading!r} must not be empty"
        )
        return
    missing = [
        scalar
        for scalar in _report_scalar_values(projection)
        if _normalized_report_text(scalar) not in normalized_body
    ]
    if missing:
        preview = ", ".join(repr(item) for item in missing[:8])
        suffix = " ..." if len(missing) > 8 else ""
        failures.append(
            f"architecture options report section {heading!r} omits "
            f"comparison value(s): {preview}{suffix}"
        )
    if require_explicit_negative and not re.search(
        r"(?:\bnone\b|\bno\s+(?:eliminated|unresolved|uncarried)\b|\[\s*\])",
        normalized_body,
        flags=re.IGNORECASE,
    ):
        failures.append(
            f"architecture options report section {heading!r} must state an "
            "explicit negative when no direction has that disposition"
        )


def _report_rendering_surface(value: str) -> str:
    """Remove Markdown code that cannot act as rendered HTML."""
    lines: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in value.splitlines(keepends=True):
        fence = re.match(r"^[ \t]*(`{3,}|~{3,})", line)
        if fence_character is None:
            if fence is not None:
                marker = fence.group(1)
                fence_character = marker[0]
                fence_length = len(marker)
                lines.append("\n" if line.endswith("\n") else "")
                continue
            lines.append(line)
            continue
        if (
            fence is not None
            and fence.group(1)[0] == fence_character
            and len(fence.group(1)) >= fence_length
            and re.fullmatch(r"[ \t]*(?:`{%d,}|~{%d,})[ \t]*\r?\n?" % (
                fence_length, fence_length
            ), line)
        ):
            fence_character = None
            fence_length = 0
        lines.append("\n" if line.endswith("\n") else "")
    surface = "".join(lines)
    return re.sub(r"`+[^`\n]*`+", " ", surface)


def _is_one_option_legacy_adoption(data: dict) -> bool:
    """Return whether report omission has the sole supported migration shape.

    Schema v2 may preserve a schema-v1 adopted-existing result without
    fabricating a report only when there was no comparison: one option is both
    selected and recommended, both hashes bind that sole option, and no
    eliminated direction is recorded.
    """
    selection = data.get("selection")
    options = data.get("options")
    recommendation = data.get("recommendation")
    eliminated = data.get("eliminated_options")
    if (
        not isinstance(selection, dict)
        or selection.get("status") != "adopted-existing"
        or not isinstance(options, list)
        or len(options) != 1
        or not isinstance(options[0], dict)
        or not isinstance(recommendation, dict)
        or eliminated != []
    ):
        return False
    option = options[0]
    option_id = option.get("option_id")
    option_sha = option.get("option_sha256")
    return (
        isinstance(option_id, str)
        and _sha(option_sha)
        and selection.get("option_id") == option_id
        and selection.get("option_sha256") == option_sha
        and recommendation.get("option_id") == option_id
    )


def options_report_projection(data: dict) -> dict:
    """Return the exact selection-independent object embedded in the report."""
    return {
        "report_projection_schema_version": REPORT_SCHEMA_VERSION,
        "project_slug": data.get("project_slug"),
        "exploration_id": data.get("exploration_id"),
        "source_capability_revision": data.get("source_capability_revision"),
        "source_exploration_attempt": data.get("source_exploration_attempt"),
        "source_input_sha256": data.get("source_input_sha256"),
        "evaluation_frame": data.get("evaluation_frame"),
        "blocking_decision": data.get("blocking_decision"),
        "sources": data.get("sources"),
        "evidence_fingerprint": data.get("evidence_fingerprint"),
        "criteria": data.get("criteria"),
        "hard_constraints": data.get("hard_constraints"),
        "options": data.get("options"),
        "eliminated_options": data.get("eliminated_options"),
        "option_set_sha256": data.get("option_set_sha256"),
        "recommendation": data.get("recommendation"),
    }


def _validate_options_report_binding(
    value: object,
    *,
    data: dict,
    artifact_path: Path,
    repo_root: Path,
    selection_status: object,
    allow_reportless_legacy: bool,
    failures: list[str],
) -> None:
    """Validate schema-v2's exact human-readable sibling report binding."""
    if not isinstance(value, dict):
        failures.append("architecture_options_report must be an object in schema v2")
        return
    _exact_keys(
        value,
        REPORT_BINDING_KEYS,
        "architecture_options_report",
        failures,
    )
    if value.get("schema_version") != REPORT_SCHEMA_VERSION:
        failures.append(
            f"architecture_options_report.schema_version must equal {REPORT_SCHEMA_VERSION}"
        )
    binding_status = value.get("status")
    if binding_status not in REPORT_BINDING_STATUSES:
        failures.append(
            "architecture_options_report.status must be one of "
            f"{sorted(REPORT_BINDING_STATUSES)}"
        )
        return

    report_path_value = value.get("path")
    report_hash = value.get("sha256")
    reason = value.get("reason")
    if binding_status == "not-produced":
        if report_path_value is not None or report_hash is not None:
            failures.append(
                "a not-produced architecture_options_report requires null path and sha256"
            )
        if not _nonempty(reason):
            failures.append(
                "a not-produced architecture_options_report requires a non-empty reason"
            )
        if selection_status == "direction-selected":
            failures.append(
                "schema-v2 direction-selected requires a present architecture options report"
            )
        elif selection_status == "adopted-existing":
            if not allow_reportless_legacy:
                failures.append(
                    "current selected architecture requires a present, hash-bound "
                    "architecture options report; reportless legacy adoption is "
                    "diagnostic-only"
                )
            elif not _is_one_option_legacy_adoption(data):
                failures.append(
                    "schema-v2 adopted-existing without a report is limited to the "
                    "one-option legacy migration shape: the sole option must be selected "
                    "and recommended with matching hashes and no eliminated directions"
                )
        return

    if report_path_value != "architecture-options.md":
        failures.append(
            "a present architecture_options_report.path must equal "
            "'architecture-options.md'"
        )
    if not _sha(report_hash):
        failures.append(
            "a present architecture_options_report.sha256 must be 64 lowercase hex characters"
        )
    if reason is not None:
        failures.append("a present architecture_options_report.reason must be null")
    if report_path_value != "architecture-options.md" or not _sha(report_hash):
        return

    report_path = artifact_path.parent / report_path_value
    symlinks = _symlink_components(repo_root, report_path)
    if not _inside(artifact_path.parent, report_path) or symlinks:
        failures.append(
            "architecture_options_report.path must resolve beside the selection "
            "artifact without symlinks"
        )
        return
    if not report_path.is_file():
        failures.append(
            f"architecture options report is missing as a regular file: {report_path}"
        )
        return
    try:
        if report_path.stat().st_nlink != 1:
            failures.append("architecture options report must not be hard-linked")
            return
        report_bytes = report_path.read_bytes()
        report_text = report_bytes.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        failures.append(f"architecture options report could not be read as UTF-8: {exc}")
        return
    actual_hash = hashlib.sha256(report_bytes).hexdigest()
    if actual_hash != report_hash:
        failures.append(
            "architecture_options_report.sha256 is stale: "
            f"expected {report_hash}, actual {actual_hash}"
        )

    # Comments are not human-visible and therefore cannot satisfy any report
    # structure or content requirement.
    visible_report = re.sub(r"<!--.*?-->", " ", report_text, flags=re.DOTALL)
    rendering_surface = _report_rendering_surface(visible_report)
    for label, pattern in REPORT_HIDDEN_HTML_PATTERNS:
        if pattern.search(rendering_surface):
            failures.append(
                "architecture options report must not hide decision content with "
                f"a {label}"
            )

    slug = data.get("project_slug")
    if isinstance(slug, str):
        expected_title = f"# Solution Architecture Options — {slug}"
        if visible_report.count(expected_title) != 1:
            failures.append(
                "architecture options report must contain its exact project title once"
            )
    status_marker = "> Decision status: awaiting-selection"
    if visible_report.count(status_marker) != 1:
        failures.append(
            "architecture options report must remain the immutable awaiting-selection snapshot"
        )
    for heading in REPORT_REQUIRED_HEADINGS:
        if visible_report.count(heading) != 1:
            failures.append(
                f"architecture options report must contain heading exactly once: {heading}"
            )

    workbench_revision: int | None = None
    workbench_matches = re.findall(
        r"^>\s*Workbench revision:\s*([1-9][0-9]*)\s*$",
        visible_report,
        flags=re.MULTILINE,
    )
    if len(workbench_matches) != 1:
        failures.append(
            "architecture options report must declare one positive Workbench "
            "revision in its visible header"
        )
    else:
        workbench_revision = int(workbench_matches[0])
    _validate_workbench_audit(
        visible_report,
        workbench_revision=workbench_revision,
        failures=failures,
    )

    decision_section_match = re.search(
        r"^## What Needs Your Decision\s*$\n(.*?)(?=^##\s)",
        visible_report,
        flags=re.DOTALL | re.MULTILINE,
    )
    decision_section = decision_section_match.group(1) if decision_section_match else ""
    decision_values: dict[str, str] = {}
    for label in REPORT_DECISION_FIELDS:
        field_pattern = re.compile(
            rf"^[ \t]*-[ \t]+\*\*{re.escape(label)}:\*\*[ \t]*(.*?)[ \t]*$",
            re.MULTILINE,
        )
        matches = field_pattern.findall(decision_section)
        if len(matches) != 1:
            failures.append(
                "architecture options report What Needs Your Decision field "
                f"{label!r} must appear exactly once and be visible"
            )
            continue
        rendered_value = re.sub(r"<[^>\n]*>", " ", matches[0])
        rendered_value = re.sub(r"[*_~]", "", rendered_value).strip()
        if not rendered_value:
            failures.append(
                "architecture options report What Needs Your Decision field "
                f"{label!r} must have a non-empty visible value"
            )
        else:
            decision_values[label] = rendered_value

    report_frame = data.get("evaluation_frame")
    decision_owner = (
        report_frame.get("decision_owner")
        if isinstance(report_frame, dict)
        else None
    )
    owner_summary = decision_values.get("Decision owner / authority", "")
    if isinstance(decision_owner, dict):
        normalized_owner_summary = _normalized_report_text(owner_summary)
        for key in ("identity_or_role", "authority_basis"):
            owner_value = decision_owner.get(key)
            if (
                isinstance(owner_value, str)
                and _normalized_report_text(owner_value)
                not in normalized_owner_summary
            ):
                failures.append(
                    "architecture options report Decision owner / authority "
                    f"must visibly include evaluation_frame.decision_owner.{key}"
                )

    projection_matches = re.findall(
        r"## Machine-Readable Comparison Projection\s+```json\s*\n(.*?)\n```",
        visible_report,
        flags=re.DOTALL,
    )
    if len(projection_matches) != 1:
        failures.append(
            "architecture options report must contain exactly one fenced JSON "
            "Machine-Readable Comparison Projection"
        )
    else:
        try:
            embedded_projection = json.loads(
                projection_matches[0], parse_constant=_reject_constant
            )
        except (ValueError, json.JSONDecodeError) as exc:
            failures.append(
                f"architecture options report comparison projection is invalid JSON: {exc}"
            )
        else:
            expected_projection = options_report_projection(data)
            if embedded_projection != expected_projection:
                failures.append(
                    "architecture options report comparison projection does not "
                    "exactly match architecture-selection.json"
                )

    option_rows_for_sections = (
        [row for row in data.get("options", []) if isinstance(row, dict)]
        if isinstance(data.get("options"), list)
        else []
    )
    _require_section_projection(
        visible_report,
        "## Evaluation Frame",
        data.get("evaluation_frame"),
        failures,
    )
    _require_section_projection(
        visible_report,
        "## Hard-Constraint Screen",
        {
            "hard_constraints": data.get("hard_constraints"),
            "option_verdicts": [
                {
                    "option_id": option.get("option_id"),
                    "constraint_verdicts": option.get("constraint_verdicts"),
                }
                for option in option_rows_for_sections
            ],
        },
        failures,
    )
    _require_section_projection(
        visible_report,
        "## Weighted Comparison",
        {
            "criteria": data.get("criteria"),
            "option_scores": [
                {
                    "option_id": option.get("option_id"),
                    "scores": option.get("scores"),
                    "weighted_score": option.get("weighted_score"),
                    "confidence": option.get("confidence"),
                }
                for option in option_rows_for_sections
            ],
            "recommendation": data.get("recommendation"),
        },
        failures,
    )
    eliminated_for_section = data.get("eliminated_options")
    _require_section_projection(
        visible_report,
        "## Eliminated, Unresolved, and Uncarried Directions",
        eliminated_for_section,
        failures,
        require_explicit_negative=eliminated_for_section == [],
    )
    _require_section_projection(
        visible_report,
        "## Evidence Sources",
        data.get("sources"),
        failures,
    )

    # Require the complete decision-support projection to be visibly present.
    # HTML comments are removed so hidden metadata cannot substitute for a
    # comparison a human can actually inspect. Whitespace and escaped table
    # pipes are normalized, but the values themselves are not paraphrased.
    normalized_report = _normalized_report_text(visible_report)
    projection = {
        "evaluation_frame": data.get("evaluation_frame"),
        "blocking_decision": data.get("blocking_decision"),
        "sources": data.get("sources"),
        "criteria": data.get("criteria"),
        "hard_constraints": data.get("hard_constraints"),
        "options": data.get("options"),
        "eliminated_options": data.get("eliminated_options"),
        "recommendation": data.get("recommendation"),
    }
    missing_visible_values: list[str] = []
    for scalar in _report_scalar_values(projection):
        normalized_scalar = _normalized_report_text(scalar)
        if normalized_scalar and normalized_scalar not in normalized_report:
            missing_visible_values.append(scalar)
    if missing_visible_values:
        preview = ", ".join(repr(item) for item in missing_visible_values[:8])
        suffix = " ..." if len(missing_visible_values) > 8 else ""
        failures.append(
            "architecture options report omits decision-support value(s): "
            f"{preview}{suffix}"
        )

    options = data.get("options")
    option_rows = [row for row in options if isinstance(row, dict)] if isinstance(options, list) else []
    direction_positions: list[tuple[int, dict]] = []
    for option in option_rows:
        oid = option.get("option_id")
        title = option.get("title")
        option_sha = option.get("option_sha256")
        if not isinstance(oid, str) or not isinstance(title, str):
            continue
        heading = f"## Direction {oid} — {title}"
        if visible_report.count(heading) != 1:
            failures.append(
                f"architecture options report must contain exact direction heading {oid}"
            )
            continue
        direction_positions.append((visible_report.index(heading), option))
        if isinstance(option_sha, str) and visible_report.count(
            f"**Option hash:** `{option_sha}`"
        ) != 1:
            failures.append(
                f"architecture options report must contain exact option hash for {oid}"
            )
    direction_positions.sort(key=lambda row: row[0])
    dimension_labels = (
        "Responsibilities and boundaries",
        "Runtime and deployment",
        "Data ownership",
        "Integrations and failure behavior",
        "Trust, residency, and security",
        "Quality tactics",
        "Migration and evolution",
        "Capability implications",
        "Assumptions",
        "Irreversible commitments",
    )
    report_tail = visible_report.find("## Eliminated, Unresolved, and Uncarried Directions")
    for index, (start, option) in enumerate(direction_positions):
        end = (
            direction_positions[index + 1][0]
            if index + 1 < len(direction_positions)
            else report_tail if report_tail > start else len(visible_report)
        )
        section = visible_report[start:end]
        normalized_section = _normalized_report_text(section)
        oid = option.get("option_id")
        for label in dimension_labels:
            if section.count(f"| {label} |") != 1:
                failures.append(
                    f"architecture options report direction {oid} must contain "
                    f"the {label!r} dimension exactly once"
                )
        if "**Confidence:**" not in section:
            failures.append(
                f"architecture options report direction {oid} must state confidence"
            )
        option_projection = {
            key: option.get(key)
            for key in (
                *OPTION_ARRAY_KEYS,
                "constraint_verdicts",
                "scores",
                "weighted_score",
                "confidence",
            )
        }
        missing_option_values = [
            scalar
            for scalar in _report_scalar_values(option_projection)
            if _normalized_report_text(scalar) not in normalized_section
        ]
        if missing_option_values:
            preview = ", ".join(repr(item) for item in missing_option_values[:6])
            suffix = " ..." if len(missing_option_values) > 6 else ""
            failures.append(
                f"architecture options report direction {oid} omits option detail(s): "
                f"{preview}{suffix}"
            )

    integrity_values = {
        "Report schema": str(REPORT_SCHEMA_VERSION),
        "Workbench revision": (
            f"`{workbench_revision}`"
            if workbench_revision is not None
            else None
        ),
        "Project slug": f"`{data.get('project_slug')}`",
        "Capability revision": f"`{data.get('source_capability_revision')}`",
        "Exploration attempt": f"`{data.get('source_exploration_attempt')}`",
        "Exploration id": f"`{data.get('exploration_id')}`",
        "Source input SHA-256": f"`{data.get('source_input_sha256')}`",
        "Evidence fingerprint": f"`{data.get('evidence_fingerprint')}`",
        "Option-set SHA-256": f"`{data.get('option_set_sha256')}`",
    }
    for label, expected in integrity_values.items():
        if expected is None:
            continue
        if _report_table_value(visible_report, label) != expected:
            failures.append(
                f"architecture options report integrity row {label!r} must equal {expected}"
            )

    awaiting_rows = {
        "Status": "awaiting-selection",
        "Selected direction": "Not selected",
        "Selected option hash": "Not selected",
        "Decided by": "Not selected",
        "Approved by": "Not selected",
    }
    for label, expected in awaiting_rows.items():
        if _report_table_value(visible_report, label) != expected:
            failures.append(
                "architecture options report must preserve its pre-approval "
                f"Human Decision row {label!r} as {expected!r}"
            )


def validate_document(
    data: dict,
    *,
    artifact_path: Path,
    repo_root: Path,
    allow_incomplete: bool = False,
    expected_project_slug: str | None = None,
    require_current_schema: bool = False,
) -> list[str]:
    failures: list[str] = []
    selection_value = data.get("selection")
    raw_status = selection_value.get("status") if isinstance(selection_value, dict) else None
    transient = allow_incomplete and raw_status in TRANSIENT_STATUSES

    schema_version = data.get("schema_version")
    top_keys = TOP_KEYS_V2 if schema_version == 2 else TOP_KEYS_V1
    required_keys = TRANSIENT_REQUIRED_TOP_KEYS if transient else set(top_keys)
    if transient and schema_version == 2:
        required_keys = set(required_keys) | {"architecture_options_report"}
    missing = sorted(required_keys - set(data))
    extra = sorted(set(data) - top_keys)
    if missing:
        failures.append("artifact missing key(s): " + ", ".join(missing))
    if extra:
        failures.append("artifact has unknown key(s): " + ", ".join(extra))

    if schema_version not in SCHEMA_VERSIONS:
        failures.append(f"schema_version must be one of {sorted(SCHEMA_VERSIONS)}")
    slug = data.get("project_slug")
    if not isinstance(slug, str) or PROJECT_SLUG_RE.fullmatch(slug) is None:
        failures.append("project_slug must be canonical lowercase kebab-case")
    elif expected_project_slug is not None and slug != expected_project_slug:
        failures.append(
            f"project_slug {slug!r} does not match source plan {expected_project_slug!r}"
        )
    if not _nonempty(data.get("exploration_id")):
        failures.append("exploration_id must be non-empty")
    revision = data.get("source_capability_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        failures.append("source_capability_revision must be an integer >= 1")
    attempt = data.get("source_exploration_attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        failures.append("source_exploration_attempt must be an integer >= 1")
    if not _sha(data.get("source_input_sha256")):
        failures.append("source_input_sha256 must be 64 lowercase hex characters")
    raw_sources = data.get("sources")
    _validate_sources(raw_sources, repo_root, failures)
    source_paths = {
        row.get("path")
        for row in raw_sources
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    } if isinstance(raw_sources, list) else set()
    evidence_hash = data.get("evidence_fingerprint")
    if not _sha(evidence_hash):
        failures.append("evidence_fingerprint must be 64 lowercase hex characters")
    elif isinstance(raw_sources, list) and evidence_hash != canonical_sha256(raw_sources):
        failures.append("evidence_fingerprint does not match canonical sources")
    if data.get("next_owner") != "ce-plan":
        failures.append("next_owner must equal 'ce-plan'")

    _validate_blocking_decision(
        data.get("blocking_decision"), status=raw_status, failures=failures
    )

    if schema_version == 2:
        _validate_options_report_binding(
            data.get("architecture_options_report"),
            data=data,
            artifact_path=artifact_path,
            repo_root=repo_root,
            selection_status=raw_status,
            allow_reportless_legacy=not require_current_schema,
            failures=failures,
        )

    if transient:
        _validate_selection(
            selection_value,
            {},
            {},
            failures,
            allow_incomplete=allow_incomplete,
        )
        return failures

    status = raw_status if isinstance(raw_status, str) else None
    selected = status in SELECTED_STATUSES
    evaluation_frame = _validate_evaluation_frame(
        data.get("evaluation_frame"),
        source_paths=source_paths,
        repo_root=repo_root,
        failures=failures,
    )
    applicability = evaluation_frame.get("architecture_applicability")
    if status == "not-applicable" and applicability != "not-required":
        failures.append(
            "selection.status `not-applicable` requires evaluation-frame "
            "architecture_applicability `not-required`"
        )
    elif status == "deferred" and applicability != "recommended":
        failures.append(
            "selection.status `deferred` requires evaluation-frame "
            "architecture_applicability `recommended`"
        )
    elif selected and applicability == "not-required":
        failures.append(
            "a selected direction requires evaluation-frame applicability "
            "`required` or `recommended`"
        )
    # Every durable terminal artifact comes from a human-confirmed evaluation
    # frame, even when exploration was explicitly deferred or not applicable.
    # Retain all six criteria so downstream consumers can distinguish a
    # deliberate non-exploration disposition from an incomplete result.
    criteria, weights = _validate_criteria(
        data.get("criteria"), failures, required=True
    )
    constraints, constraint_ids = _validate_constraints(
        data.get("hard_constraints"), failures
    )
    supplied_input_hash = data.get("source_input_sha256")
    if _sha(supplied_input_hash):
        expected_input_hash = source_input_hash(data)
        if supplied_input_hash != expected_input_hash:
            failures.append(
                "source_input_sha256 does not match the canonical "
                f"decision-relevant exploration input (expected {expected_input_hash})"
            )
    (
        options,
        by_id,
        verdicts_by_id,
        scores_by_id,
        evidence_states_by_id,
    ) = _validate_options(
        data.get("options"), constraint_ids, weights, source_paths, failures,
        selection_status=status,
    )
    eliminated = _validate_eliminated(
        data.get("eliminated_options"), by_id, verdicts_by_id, failures
    )
    recommendation = _validate_recommendation(
        data.get("recommendation"), by_id, verdicts_by_id, failures, selected=selected
    )
    if isinstance(recommendation.get("option_id"), str):
        _validate_ranking_integrity(
            recommendation,
            by_id,
            verdicts_by_id,
            scores_by_id,
            evidence_states_by_id,
            weights,
            failures,
        )
    if status in {"not-applicable", "deferred"}:
        if options:
            failures.append(
                f"selection.status `{status}` requires an empty options array "
                "because no exploration ran"
            )
        if eliminated:
            failures.append(
                f"selection.status `{status}` requires an empty eliminated_options array"
            )
        if recommendation.get("option_id") is not None:
            failures.append(
                f"selection.status `{status}` requires recommendation.option_id null"
            )
        if recommendation.get("sensitivity") != "not-applicable":
            failures.append(
                f"selection.status `{status}` requires recommendation.sensitivity "
                "`not-applicable`"
            )
    # Re-run selection after option identities and eligibility are available.
    _validate_selection(
        selection_value,
        by_id,
        verdicts_by_id,
        failures,
        allow_incomplete=allow_incomplete,
        decision_owner=evaluation_frame.get("decision_owner"),
    )

    supplied_set_hash = data.get("option_set_sha256")
    if not _sha(supplied_set_hash):
        failures.append("option_set_sha256 must be 64 lowercase hex characters")
    elif isinstance(options, list) and isinstance(eliminated, list):
        expected = option_set_hash(options, eliminated)
        if supplied_set_hash != expected:
            failures.append(f"option_set_sha256 mismatch: expected {expected}")
        elif selected:
            expected_exploration_id = f"AEX-{supplied_set_hash[:12]}"
            if data.get("exploration_id") != expected_exploration_id:
                failures.append(
                    "selected exploration_id must be content-addressed as "
                    f"{expected_exploration_id}"
                )
    return failures


def validate_file(
    artifact_path: Path,
    *,
    repo_root: Path | None = None,
    allow_incomplete: bool = False,
    expected_project_slug: str | None = None,
    require_current_schema: bool = False,
) -> tuple[dict, list[str]]:
    if artifact_path.is_dir():
        artifact_path = artifact_path / "architecture-selection.json"
    data = load_artifact(artifact_path)
    root = (repo_root or infer_repo_root(artifact_path)).resolve()
    if not root.is_dir():
        raise SelectionLintError(f"repository root not found: {root}")
    if not _inside(root, artifact_path):
        raise SelectionLintError(f"artifact must resolve beneath repository root: {root}")
    symlinks = _symlink_components(root, artifact_path)
    if symlinks:
        raise SelectionLintError(
            "artifact path must not contain symlinks: " + ", ".join(symlinks)
        )
    failures = validate_document(
        data,
        artifact_path=artifact_path,
        repo_root=root,
        allow_incomplete=allow_incomplete,
        expected_project_slug=expected_project_slug,
        require_current_schema=require_current_schema,
    )
    if require_current_schema and data.get("schema_version") != CURRENT_SCHEMA_VERSION:
        failures.insert(
            0,
            "fresh exploration output must use current schema_version "
            f"{CURRENT_SCHEMA_VERSION}",
        )
    return data, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a plan-root architecture-selection.json"
    )
    parser.add_argument(
        "artifact",
        type=Path,
        help="architecture-selection.json path, or its containing plan directory",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="repository root for source-path freshness checks (normally inferred)",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="accept explicitly unselected transient exploration-result statuses",
    )
    parser.add_argument(
        "--require-current-schema",
        action="store_true",
        help=(
            "require schema v2 and a present hash-bound comparison report for "
            "selected directions (fresh output and active consumers)"
        ),
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    artifact_path = args.artifact
    if artifact_path.is_dir():
        artifact_path = artifact_path / "architecture-selection.json"
    try:
        data, failures = validate_file(
            artifact_path,
            repo_root=args.repo_root,
            allow_incomplete=args.allow_incomplete,
            require_current_schema=args.require_current_schema,
        )
    except SelectionLintError as exc:
        if args.json:
            print(json.dumps({"status": "error", "message": str(exc)}))
        else:
            print(f"architecture-selection-lint: ERROR — {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — unexpected failures are exit 2, never PASS
        message = f"unexpected: {type(exc).__name__}: {exc}"
        if args.json:
            print(json.dumps({"status": "error", "message": message}))
        else:
            print(f"architecture-selection-lint: ERROR — {message}", file=sys.stderr)
        return 2

    status = "fail" if failures else "pass"
    result = {
        "status": status,
        "artifact": str(artifact_path),
        "selection_status": (
            data.get("selection", {}).get("status")
            if isinstance(data.get("selection"), dict)
            else None
        ),
        "hard_failures": failures,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"architecture-selection-lint: {artifact_path}")
        if failures:
            print(f"  FAIL — {len(failures)} structural-integrity failure(s):")
            for failure in failures:
                print(f"    x {failure}")
        else:
            print("  PASS — selection structure, canonical bindings, and source freshness hold.")
            print("         (checks integrity, not whether the architecture choice is good.)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
