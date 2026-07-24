#!/usr/bin/env python3
"""Validate an architecture-options.md snapshot before the human gate.

The report is both a readable decision surface and a container for the exact
selection-independent comparison projection. This checker loads that report,
its exact sibling exploration input, and repository sources named by the
projection. It deliberately does not construct or validate a ``selection``
object: a PASS means the comparison is structurally sound and fresh, never that
a human selected a direction.

Exit codes:
  0  PASS  — report, projection, hashes, sources, and decision surface are valid
  1  FAIL  — the report loaded but violates the pre-approval contract
  2  ERROR — the report or repository root could not be loaded safely
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import sys
from pathlib import Path


class OptionsLintError(Exception):
    """The report cannot be loaded or inspected safely (exit 2)."""


def _load_selection_linter():
    script = Path(__file__).with_name("architecture-selection-lint.py")
    spec = importlib.util.spec_from_file_location(
        "ce_architecture_selection_lint", script
    )
    if spec is None or spec.loader is None:
        raise OptionsLintError(f"could not load sibling selection linter: {script}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 — a broken dependency is an ERROR
        raise OptionsLintError(
            f"could not load sibling selection linter: {type(exc).__name__}: {exc}"
        ) from exc
    return module


sl = _load_selection_linter()

PROJECTION_KEYS = set(sl.options_report_projection({}))
PROJECTION_PATTERN = re.compile(
    r"## Machine-Readable Comparison Projection\s+```json\s*\n(.*?)\n```",
    re.DOTALL,
)
TRIAGE_FIELDS = (
    "Decision",
    "Why now",
    "Recommendation",
    "Recommendation basis",
    "Confidence / sensitivity",
    "Decision owner / authority",
    "Current constraints",
    "Key trade-off",
    "Cost if wrong",
    "Material gaps and inferences",
)
DECISION_PLACEHOLDER_VALUES = {
    "placeholder",
    "tbc",
    "tbd",
    "template",
    "to be confirmed",
    "to be determined",
    "todo",
    "unknown",
}
DECISION_TEMPLATE_PATTERN = re.compile(
    r"(?:"
    r"<\s*[A-Za-z][A-Za-z0-9 _-]{0,80}\s*>"
    r"|\{\{[^}\n]+\}\}"
    r"|\$\{[^}\n]+\}"
    r"|\[\s*(?:insert|placeholder|replace|tbc|tbd|template|todo|unknown)"
    r"\b[^\]\n]*\]"
    r")",
    re.IGNORECASE,
)
MARKDOWN_ESCAPE_PATTERN = re.compile(r"\\([\\`*_\[\]{}()#+!|>~.-])")
HIDDEN_REPORT_PATTERNS = (
    (re.compile(r"<!--|-->", re.IGNORECASE), "HTML comments"),
    (
        re.compile(r"<(?:script|style|template|noscript|details)\b", re.IGNORECASE),
        "hidden or executable HTML containers",
    ),
    (
        re.compile(r"<[^>]+\bhidden(?:\s|=|>)", re.IGNORECASE),
        "the HTML hidden attribute",
    ),
    (
        re.compile(r"<[^>]+\baria-hidden\s*=\s*['\"]?true", re.IGNORECASE),
        "aria-hidden=true",
    ),
    (
        re.compile(
            r"<[^>]+\bstyle\s*=\s*['\"][^'\"]*"
            r"(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0)",
            re.IGNORECASE,
        ),
        "an invisible inline style",
    ),
    (
        re.compile(r"^\s*\[(?://|comment)\]\s*:\s*#", re.IGNORECASE | re.MULTILINE),
        "a hidden Markdown comment definition",
    ),
    (
        re.compile(r"<\s*/?\s*[A-Za-z][^>\n]*>", re.IGNORECASE),
        "a raw HTML element (escape it as Markdown text)",
    ),
)


def decision_surface_placeholder(value: object) -> bool:
    """Return whether visible decision text is only a stub or has a template slot.

    This is deliberately narrower than evidence validation. In particular,
    ``unknown: <reason>`` is substantive evidence text and is not a placeholder.
    """
    if not isinstance(value, str):
        return False
    visible = html.unescape(value)
    visible = MARKDOWN_ESCAPE_PATTERN.sub(r"\1", visible)
    visible = re.sub(r"\s+", " ", visible).strip()
    token = visible.casefold().strip(" \t\r\n.!?;:")
    return (
        token in DECISION_PLACEHOLDER_VALUES
        or DECISION_TEMPLATE_PATTERN.search(visible) is not None
    )


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON number {value!r} is not permitted")


def _exact_projection(report_text: str, failures: list[str]) -> dict | None:
    matches = PROJECTION_PATTERN.findall(report_text)
    if len(matches) != 1:
        failures.append(
            "report must contain exactly one fenced JSON Machine-Readable "
            "Comparison Projection"
        )
        return None
    try:
        projection = json.loads(matches[0], parse_constant=_reject_constant)
    except (ValueError, json.JSONDecodeError) as exc:
        failures.append(f"comparison projection is invalid JSON: {exc}")
        return None
    if not isinstance(projection, dict):
        failures.append("comparison projection must be a JSON object")
        return None
    missing = sorted(PROJECTION_KEYS - set(projection))
    extra = sorted(set(projection) - PROJECTION_KEYS)
    if missing:
        failures.append("comparison projection missing key(s): " + ", ".join(missing))
    if extra:
        failures.append("comparison projection has unknown key(s): " + ", ".join(extra))
    return projection


def _triage_values(report_text: str, failures: list[str]) -> dict[str, str]:
    section_match = re.search(
        r"^## What Needs Your Decision\s*$\n(.*?)(?=^##\s|\Z)",
        report_text,
        re.MULTILINE | re.DOTALL,
    )
    if section_match is None:
        failures.append("report must contain one visible What Needs Your Decision section")
        return {}
    section = section_match.group(1)
    result: dict[str, str] = {}
    for label in TRIAGE_FIELDS:
        matches = re.findall(
            rf"^\s*-\s+\*\*{re.escape(label)}:\*\*\s*(.*?)\s*$",
            section,
            re.MULTILINE,
        )
        if len(matches) != 1 or not matches[0].strip():
            failures.append(
                f"What Needs Your Decision must contain one non-empty {label!r} field"
            )
            continue
        value = matches[0].strip()
        if decision_surface_placeholder(value):
            failures.append(
                f"What Needs Your Decision field {label!r} contains an unfilled placeholder"
            )
        result[label] = value
    return result


def _current_exploration_payload(value: dict) -> dict:
    """Project the current input onto selection-lint's canonical hash scope."""
    return {
        "schema_version": value.get("schema_version"),
        "project_slug": value.get("project_slug"),
        "capability_revision": value.get("capability_revision"),
        "exploration_attempt": value.get("exploration_attempt"),
        "project_intent": value.get("project_intent"),
        "non_goals": value.get("non_goals"),
        "decision_owner": value.get("decision_owner"),
        "architecture_applicability": value.get("architecture_applicability"),
        "driver_screen": value.get("driver_screen"),
        "accepted_decisions": value.get("accepted_decisions"),
        "material_gaps": value.get("material_gaps"),
        "capabilities": value.get("capabilities"),
        "journeys": value.get("journeys"),
        "hard_constraints": value.get("hard_constraints"),
        "quality_attribute_scenarios": value.get("quality_attribute_scenarios"),
        "criteria": value.get("criteria"),
        "sources": value.get("sources"),
    }


def _load_current_exploration(report: Path, repo_root: Path) -> dict:
    path = report.with_name("architecture-exploration.json")
    symlinks = sl._symlink_components(repo_root, path)
    if not sl._inside(report.parent, path) or symlinks:
        raise OptionsLintError(
            "architecture-exploration.json must resolve beside the report without symlinks"
        )
    if path.is_symlink() or not path.is_file():
        raise OptionsLintError(
            "architecture-exploration.json not found as a regular non-symlink file: "
            f"{path}"
        )
    try:
        if path.stat().st_nlink != 1:
            raise OptionsLintError("architecture-exploration.json must not be hard-linked")
        data = json.loads(
            path.read_text(encoding="utf-8"), parse_constant=_reject_constant
        )
    except OptionsLintError:
        raise
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise OptionsLintError(
            f"could not parse architecture-exploration.json: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise OptionsLintError("architecture-exploration.json must be a JSON object")
    return data


def _validate_projection(
    projection: dict,
    *,
    repo_root: Path,
    expected_slug: str,
    exploration_input: dict,
) -> list[str]:
    """Validate full comparison integrity without creating approval state."""
    failures: list[str] = []
    if projection.get("report_projection_schema_version") != sl.REPORT_SCHEMA_VERSION:
        failures.append(
            "report_projection_schema_version must equal "
            f"{sl.REPORT_SCHEMA_VERSION}"
        )

    data = {
        key: value
        for key, value in projection.items()
        if key != "report_projection_schema_version"
    }
    slug = data.get("project_slug")
    if not isinstance(slug, str) or sl.PROJECT_SLUG_RE.fullmatch(slug) is None:
        failures.append("project_slug must be canonical lowercase kebab-case")
    elif slug != expected_slug:
        failures.append(
            f"project_slug {slug!r} does not match report directory {expected_slug!r}"
        )
    if not sl._nonempty(data.get("exploration_id")):
        failures.append("exploration_id must be non-empty")
    revision = data.get("source_capability_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        failures.append("source_capability_revision must be an integer >= 1")
    attempt = data.get("source_exploration_attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        failures.append("source_exploration_attempt must be an integer >= 1")

    if exploration_input.get("schema_version") != sl.EXPLORATION_INPUT_SCHEMA_VERSION:
        failures.append(
            "current architecture-exploration.json schema_version must equal "
            f"{sl.EXPLORATION_INPUT_SCHEMA_VERSION}"
        )
    current_bindings = (
        ("project_slug", "project_slug"),
        ("source_capability_revision", "capability_revision"),
        ("source_exploration_attempt", "exploration_attempt"),
    )
    for projection_key, input_key in current_bindings:
        if data.get(projection_key) != exploration_input.get(input_key):
            failures.append(
                f"{projection_key} does not match current architecture-exploration.json "
                f"{input_key}"
            )

    supplied_input_hash = data.get("source_input_sha256")
    if not sl._sha(supplied_input_hash):
        failures.append("source_input_sha256 must be 64 lowercase hex characters")

    raw_sources = data.get("sources")
    sl._validate_sources(raw_sources, repo_root, failures)
    source_paths = (
        {
            row.get("path")
            for row in raw_sources
            if isinstance(row, dict) and isinstance(row.get("path"), str)
        }
        if isinstance(raw_sources, list)
        else set()
    )
    evidence_hash = data.get("evidence_fingerprint")
    if not sl._sha(evidence_hash):
        failures.append("evidence_fingerprint must be 64 lowercase hex characters")
    elif isinstance(raw_sources, list) and evidence_hash != sl.canonical_sha256(raw_sources):
        failures.append("evidence_fingerprint does not match canonical sources")

    # A direction-selection report cannot simultaneously be a bounded
    # pre-option technical decision handoff.
    sl._validate_blocking_decision(
        data.get("blocking_decision"), status=None, failures=failures
    )
    frame = sl._validate_evaluation_frame(
        data.get("evaluation_frame"),
        source_paths=source_paths,
        repo_root=repo_root,
        failures=failures,
    )
    if frame.get("architecture_applicability") not in {"required", "recommended"}:
        failures.append(
            "a pre-prompt direction comparison requires architecture_applicability "
            "required or recommended"
        )
    _, weights = sl._validate_criteria(data.get("criteria"), failures, required=True)
    _, constraint_ids = sl._validate_constraints(data.get("hard_constraints"), failures)

    if sl._sha(supplied_input_hash):
        expected = sl.source_input_hash(data)
        if supplied_input_hash != expected:
            failures.append(
                "source_input_sha256 does not match the canonical "
                f"decision-relevant exploration input (expected {expected})"
            )
        current_hash = sl.canonical_sha256(
            _current_exploration_payload(exploration_input)
        )
        if supplied_input_hash != current_hash:
            failures.append(
                "source_input_sha256 does not match current "
                "architecture-exploration.json "
                f"(expected {current_hash})"
            )

    # ``direction-selected`` here is only the existing validator's strict
    # option-set profile: 2–4 directions, no unresolved hard constraint.  No
    # selection object, option choice, human identity, or rationale is made.
    (
        options,
        by_id,
        verdicts_by_id,
        scores_by_id,
        evidence_states_by_id,
    ) = sl._validate_options(
        data.get("options"),
        constraint_ids,
        weights,
        source_paths,
        failures,
        selection_status="direction-selected",
    )
    eliminated = sl._validate_eliminated(
        data.get("eliminated_options"), by_id, verdicts_by_id, failures
    )
    recommendation = sl._validate_recommendation(
        data.get("recommendation"),
        by_id,
        verdicts_by_id,
        failures,
        selected=True,
    )
    if isinstance(recommendation.get("option_id"), str):
        sl._validate_ranking_integrity(
            recommendation,
            by_id,
            verdicts_by_id,
            scores_by_id,
            evidence_states_by_id,
            weights,
            failures,
        )

    supplied_set_hash = data.get("option_set_sha256")
    if not sl._sha(supplied_set_hash):
        failures.append("option_set_sha256 must be 64 lowercase hex characters")
    elif isinstance(options, list) and isinstance(eliminated, list):
        expected = sl.option_set_hash(options, eliminated)
        if supplied_set_hash != expected:
            failures.append(f"option_set_sha256 mismatch: expected {expected}")
        else:
            expected_exploration_id = f"AEX-{supplied_set_hash[:12]}"
            if data.get("exploration_id") != expected_exploration_id:
                failures.append(
                    "exploration_id must be content-addressed as "
                    f"{expected_exploration_id}"
                )
    return failures


def _canonical_report_path(path: Path, repo_root: Path) -> tuple[Path, str]:
    root = repo_root.resolve()
    if not root.is_dir():
        raise OptionsLintError(f"repository root not found: {root}")
    report = path if path.is_absolute() else Path.cwd() / path
    try:
        relative = report.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise OptionsLintError(f"report must be beneath repository root: {root}") from exc
    if ".." in relative.parts or not sl._inside(root, report):
        raise OptionsLintError(f"report must resolve beneath repository root: {root}")
    symlinks = sl._symlink_components(root, report)
    if symlinks:
        raise OptionsLintError(
            "report path must not contain symlinks: " + ", ".join(symlinks)
        )
    if (
        len(relative.parts) != 5
        or relative.parts[:3] != ("docs", "plans", ".drafts")
        or relative.parts[4] != "architecture-options.md"
        or sl.PROJECT_SLUG_RE.fullmatch(relative.parts[3]) is None
    ):
        raise OptionsLintError(
            "pre-approval report path must equal "
            "docs/plans/.drafts/<canonical-slug>/architecture-options.md"
        )
    if report.is_symlink() or not report.is_file():
        raise OptionsLintError(f"report not found as a regular non-symlink file: {report}")
    try:
        if report.stat().st_nlink != 1:
            raise OptionsLintError("architecture options report must not be hard-linked")
    except OSError as exc:
        raise OptionsLintError(f"could not inspect report: {exc}") from exc
    return report, relative.parts[3]


def validate_file(report_path: Path, *, repo_root: Path) -> tuple[dict | None, list[str]]:
    report, expected_slug = _canonical_report_path(report_path, repo_root)
    exploration_input = _load_current_exploration(report, repo_root.resolve())
    try:
        report_bytes = report.read_bytes()
        report_text = report_bytes.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise OptionsLintError(f"could not read report as UTF-8: {exc}") from exc

    failures: list[str] = []
    # Raw HTML can hide rendered Markdown, but HTML-looking architecture data
    # inside a fenced example is inert and must not become a false positive.
    visibility_surface = re.sub(r"```.*?```", " ", report_text, flags=re.DOTALL)
    for pattern, label in HIDDEN_REPORT_PATTERNS:
        if pattern.search(visibility_surface):
            failures.append(f"report must not use {label} to hide decision content")

    projection = _exact_projection(report_text, failures)
    triage = _triage_values(report_text, failures)
    if projection is None:
        return None, failures

    failures.extend(
        _validate_projection(
            projection,
            repo_root=repo_root.resolve(),
            expected_slug=expected_slug,
            exploration_input=exploration_input,
        )
    )

    gate_index = exploration_input.get("parent_gate_index")
    gate_total = exploration_input.get("parent_gate_total")
    if (
        not isinstance(gate_index, int)
        or isinstance(gate_index, bool)
        or not isinstance(gate_total, int)
        or isinstance(gate_total, bool)
        or gate_index < 1
        or gate_total < 1
        or gate_index > gate_total
    ):
        failures.append(
            "current architecture-exploration.json parent gate index/total "
            "must be positive integers with index <= total"
        )
    else:
        expected_gate = (
            f"`Gate {gate_index} of {gate_total} — "
            "Architecture Direction Selection`"
        )
        if sl._report_table_value(report_text, "Gate locator") != expected_gate:
            failures.append(
                "report Gate locator must match the current exploration input "
                f"({expected_gate})"
            )

    # Reuse the exact post-selection report-content checker with a binding to
    # the bytes just read.  selection_status=None prevents this pre-gate pass
    # from asserting a human choice while retaining all report visibility,
    # integrity-table, heading, option-detail, and path checks.
    data = {
        key: value
        for key, value in projection.items()
        if key != "report_projection_schema_version"
    }
    sl._validate_options_report_binding(
        {
            "schema_version": sl.REPORT_SCHEMA_VERSION,
            "status": "present",
            "path": "architecture-options.md",
            "sha256": sl.file_sha256(report),
            "reason": None,
        },
        data=data,
        artifact_path=report.with_name("architecture-selection.json"),
        repo_root=repo_root.resolve(),
        selection_status=None,
        failures=failures,
    )

    recommendation = projection.get("recommendation")
    options = projection.get("options")
    option_by_id = {
        row.get("option_id"): row
        for row in options
        if isinstance(row, dict) and isinstance(row.get("option_id"), str)
    } if isinstance(options, list) else {}
    if isinstance(recommendation, dict):
        recommended_id = recommendation.get("option_id")
        recommended = option_by_id.get(recommended_id)
        recommendation_text = triage.get("Recommendation", "")
        if isinstance(recommended_id, str):
            if recommended_id not in recommendation_text:
                failures.append(
                    "What Needs Your Decision recommendation must name the exact recommended option id"
                )
            if isinstance(recommended, dict) and isinstance(recommended.get("title"), str):
                if sl._normalized_report_text(
                    recommended["title"]
                ) not in sl._normalized_report_text(recommendation_text):
                    failures.append(
                        "What Needs Your Decision recommendation must name the exact option title"
                    )
        basis = recommendation.get("basis")
        if isinstance(basis, str) and sl._normalized_report_text(basis) not in sl._normalized_report_text(
            triage.get("Recommendation basis", "")
        ):
            failures.append(
                "What Needs Your Decision recommendation basis must include the exact projection basis"
            )
        confidence = recommendation.get("confidence")
        sensitivity = recommendation.get("sensitivity")
        confidence_text = triage.get("Confidence / sensitivity", "")
        if isinstance(confidence, str) and confidence not in confidence_text:
            failures.append(
                "What Needs Your Decision confidence/sensitivity must state recommendation confidence"
            )
        if isinstance(sensitivity, str) and sensitivity not in confidence_text:
            failures.append(
                "What Needs Your Decision confidence/sensitivity must state recommendation sensitivity"
            )
    projection_frame = projection.get("evaluation_frame")
    decision_owner = (
        projection_frame.get("decision_owner")
        if isinstance(projection_frame, dict)
        else None
    )
    owner_text = sl._normalized_report_text(
        triage.get("Decision owner / authority", "")
    )
    if isinstance(decision_owner, dict):
        for key in ("identity_or_role", "authority_basis"):
            value = decision_owner.get(key)
            if (
                isinstance(value, str)
                and sl._normalized_report_text(value) not in owner_text
            ):
                failures.append(
                    "What Needs Your Decision decision owner/authority must "
                    f"include the exact decision_owner.{key}"
                )
    return projection, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate architecture-options.md before human direction selection"
    )
    parser.add_argument("report", type=Path, help="draft architecture-options.md path")
    parser.add_argument(
        "--repo-root",
        required=True,
        type=Path,
        help="repository root used for path and source freshness checks",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        projection, failures = validate_file(args.report, repo_root=args.repo_root)
    except OptionsLintError as exc:
        if args.json:
            print(json.dumps({"status": "error", "message": str(exc)}))
        else:
            print(f"architecture-options-lint: ERROR — {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — unexpected failures are never PASS
        message = f"unexpected: {type(exc).__name__}: {exc}"
        if args.json:
            print(json.dumps({"status": "error", "message": message}))
        else:
            print(f"architecture-options-lint: ERROR — {message}", file=sys.stderr)
        return 2

    status = "fail" if failures else "pass"
    result = {
        "status": status,
        "report": str(args.report),
        "project_slug": projection.get("project_slug") if projection else None,
        "exploration_id": projection.get("exploration_id") if projection else None,
        "hard_failures": failures,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"architecture-options-lint: {args.report}")
        if failures:
            print(f"  FAIL — {len(failures)} pre-approval integrity failure(s):")
            for failure in failures:
                print(f"    x {failure}")
        else:
            print("  PASS — comparison structure, visible report, and source freshness hold.")
            print("         (checks decision readiness; it does not record human approval.)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
