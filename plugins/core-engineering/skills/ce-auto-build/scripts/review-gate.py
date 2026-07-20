#!/usr/bin/env python3
"""review-gate.py — the merge bar's review-evidence gate for one spec dir.

Reads the machine-readable review summary `/core-engineering:ce-review` writes
(`<spec_dir>/review-summary.json`, schema in this skill's artifact-template.md)
and turns its ONE precomputed gate key — `blocking_high`, the count of findings
where severity == high AND confidence == confirmed AND lens ∈ {correctness,
security} — into the house 0/1/2 verdict. Before trusting that key, it requires a
non-negative integer and cross-checks the summary's `status` (`pass` / `blocked`)
against it. It never re-derives the predicate or re-reviews code.

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


def validate_summary(data: object) -> list[str]:
    """Validate only the two fields that determine the review gate verdict."""
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


def evaluate(spec_dir: Path) -> tuple[int, dict]:
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
    schema_errors = validate_summary(data)
    if schema_errors:
        return 2, {**base, "status": "error", "blocking_high": None,
                   "message": f"review evidence {summary_path} has invalid schema: "
                              + "; ".join(schema_errors)}

    blocking = data["blocking_high"]
    result = {**base, "blocking_high": blocking,
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
    args = parser.parse_args(argv)

    exit_code, result = evaluate(Path(args.spec_dir))
    _emit(result, args.json)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
