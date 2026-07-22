#!/usr/bin/env python3
"""review-gate.py — the merge bar's review-evidence gate for one spec dir.

Reads the machine-readable review summary `/core-engineering:ce-review` writes
(`<spec_dir>/review-summary.json`, schema in this skill's artifact-template.md)
and turns its precomputed gate key — `blocking_high`, the count of findings
where severity == high AND confidence == confirmed AND lens ∈ {correctness,
security} — into the house 0/1/2 verdict. Before trusting that key, it requires a
non-negative integer and cross-checks the summary's `status` (`pass` / `blocked`)
against it. A blocked summary may also carry the precomputed `blocking_route`:
`implement` or `plan-conflict`. Automation requires that route and the gate
cross-checks a plan-conflict route against its confirmed Security finding. It
never re-derives the blocking count or re-reviews code.

Registered in merge-policy.json as an ADVISORY gate: a `blocking_high > 0`
reports a yellow advisory line but never fails the merge verdict, and a missing
review artifact is a degradation the bar surfaces, not a block. An adopter who
wants review evidence to be mandatory promotes it to `required_integrity_gates`
in a local policy override — then exit 1 fails the bar, mechanically.

Stdlib-only, offline, Claude-free — it reads one committed JSON file.

Exit codes (house contract):
    0  PASS   — review-summary.json present and blocking_high == 0
    1  FAIL   — review-summary.json present and blocking_high > 0
    2  ERROR  — no/unreadable/malformed/contradictory review-summary.json for
                this spec dir, or usage error — could-not-run is loud, never a
                silent pass
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SUMMARY_NAME = "review-summary.json"
SUMMARY_STATUSES = {"pass", "blocked"}
BLOCKING_ROUTES = {"implement", "plan-conflict"}
PLAN_CONFLICT_ESCALATION = "/core-engineering:ce-plan"
_MISSING = object()


def _security_high_findings(data: dict) -> list[dict]:
    findings = data.get("findings")
    if not isinstance(findings, list):
        return []
    return [
        row
        for row in findings
        if isinstance(row, dict)
        and row.get("lens") == "security"
        and row.get("severity") == "high"
        and row.get("confidence") == "confirmed"
    ]


def _plan_conflict_candidates(data: dict) -> list[dict]:
    """Return any blocking finding carrying either half of the route signal."""
    return [
        row
        for row in _security_high_findings(data)
        if "plan_conflict" in str(row.get("observation", ""))
        or row.get("suggested_escalation") == PLAN_CONFLICT_ESCALATION
    ]


def _plan_conflict_findings(data: dict) -> list[dict]:
    """Return blocking findings carrying the complete plan-conflict contract."""
    return [
        row
        for row in _plan_conflict_candidates(data)
        if "plan_conflict" in str(row.get("observation", ""))
        and row.get("suggested_escalation") == PLAN_CONFLICT_ESCALATION
    ]


def validate_summary(
    data: object, *, require_blocking_route: bool = False
) -> list[str]:
    """Validate the verdict fields and the optional/required repair route."""
    if not isinstance(data, dict):
        return ["top level must be an object"]

    errors: list[str] = []
    blocking = data.get("blocking_high")
    if type(blocking) is not int or blocking < 0:
        errors.append("blocking_high must be a non-negative integer")

    status = data.get("status")
    if not isinstance(status, str) or status not in SUMMARY_STATUSES:
        errors.append("status must be 'pass' or 'blocked'")

    if not errors:
        expected = "blocked" if blocking > 0 else "pass"
        if status != expected:
            errors.append(
                f"status is {status!r}, expected {expected!r} for "
                f"blocking_high {blocking}"
            )

    route = data.get("blocking_route", _MISSING)
    plan_conflict_candidates = _plan_conflict_candidates(data)
    plan_conflicts = _plan_conflict_findings(data)
    if route is _MISSING:
        if require_blocking_route:
            errors.append(
                "blocking_route is required for automation and must be null, "
                "'implement', or 'plan-conflict'"
            )
    elif route is not None and (
        not isinstance(route, str) or route not in BLOCKING_ROUTES
    ):
        errors.append(
            "blocking_route must be null, 'implement', or 'plan-conflict'"
        )

    if type(blocking) is int and blocking >= 0 and route is not _MISSING:
        if blocking == 0 and route is not None:
            errors.append("blocking_route must be null when blocking_high is 0")
        elif blocking > 0 and (
            not isinstance(route, str) or route not in BLOCKING_ROUTES
        ):
            errors.append(
                "blocking_route must be 'implement' or 'plan-conflict' when "
                "blocking_high is positive"
            )
    if route == "plan-conflict" and not plan_conflicts:
        errors.append(
            "blocking_route 'plan-conflict' requires a confirmed Security High "
            "whose observation names plan_conflict and whose "
            "suggested_escalation is /core-engineering:ce-plan"
        )
    if plan_conflict_candidates and route != "plan-conflict":
        errors.append(
            "a confirmed Security High carrying a plan_conflict marker or "
            "ce-plan escalation requires blocking_route "
            "'plan-conflict'; it cannot be missing, null, or routed to implement"
        )
    return errors


def _emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2))
        return
    status = result["status"].upper()
    print(f"review-gate [{result.get('spec_dir', '?')}]: {status}")
    for line in result.get("hard_failures", []):
        print(f"  x {line}")
    for line in result.get("advisory", []):
        print(f"  ! {line}")
    if result.get("message"):
        print(f"  {result['message']}")


def evaluate(
    spec_dir: Path, *, require_blocking_route: bool = False
) -> tuple[int, dict]:
    """Return (exit_code, verdict_dict) for one spec dir. The verdict mirrors the
    other gate scripts' shape (status / hard_failures / advisory) so the
    merge-runner renders and cross-checks it uniformly."""
    summary_path = spec_dir / SUMMARY_NAME
    base = {"schema_version": 1, "spec_dir": str(spec_dir),
            "hard_failures": [], "advisory": []}

    if not summary_path.is_file():
        return 2, {**base, "status": "error", "blocking_high": None,
                   "message": f"no review evidence for this spec dir "
                              f"({SUMMARY_NAME} missing under {spec_dir}) — run "
                              f"/core-engineering:ce-review before gating on it"}
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return 2, {**base, "status": "error", "blocking_high": None,
                   "message": f"cannot read review evidence "
                              f"{summary_path}: {e}"}
    schema_errors = validate_summary(
        data, require_blocking_route=require_blocking_route
    )
    if schema_errors:
        return 2, {**base, "status": "error", "blocking_high": None,
                   "message": f"review evidence {summary_path} has invalid schema: "
                              + "; ".join(schema_errors)}

    blocking = data["blocking_high"]
    route = data.get("blocking_route")
    if "blocking_route" not in data:
        route = "implement" if blocking > 0 else None
    result = {**base, "blocking_high": blocking, "blocking_route": route,
              "feature_id": data.get("feature_id"),
              "reviewed_at": data.get("reviewed_at")}
    if blocking > 0:
        result["status"] = "fail"
        result["hard_failures"] = [
            f"{blocking} unresolved confirmed-High review finding(s) "
            f"(correctness/security) — see {spec_dir / 'code-review.md'}"
        ]
        return 1, result
    result["status"] = "pass"
    result["advisory"] = [f"review evidence clean (blocking_high == 0) for "
                          f"{spec_dir}"]
    return 0, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge-bar review-evidence gate: read a spec dir's "
                    "review-summary.json and gate on its blocking_high count.")
    parser.add_argument("spec_dir", metavar="SPEC_DIR",
                        help="spec dir holding review-summary.json "
                             "(docs/plans/<slug>/specs/<id>)")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable verdict on stdout")
    parser.add_argument(
        "--require-blocking-route",
        action="store_true",
        help="require the current blocking_route contract (used by automation)",
    )
    args = parser.parse_args(argv)

    exit_code, result = evaluate(
        Path(args.spec_dir), require_blocking_route=args.require_blocking_route
    )
    _emit(result, args.json)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
