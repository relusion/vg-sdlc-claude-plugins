#!/usr/bin/env python3
"""disposition-lint.py — validate the merge-bar finding-disposition ledger.

The ledger (.merge-bar/dispositions.json) is the accepted-risk register the advisory
gates (secrets-guard, sca-guard) read to stop re-alarming a consciously-accepted finding
without hiding it. This lint holds its contract so a malformed or lapsed ledger surfaces
loudly instead of silently mis-suppressing: every disposition needs a unique id, a known
gate, a well-formed match, a `reason`, an `accepted_by` human stamp (a tool may not
accept a risk alone — the scan-lint H9 discipline), and a future `expires` date (an
expired disposition is CI-red, and its finding re-alarms through the consuming gate — the
eval-coverage ratchet's "defer, never forget" semantics).

Runs two ways: a human CLI over a repo (`disposition-lint.py --repo .`) and an ADVISORY
merge-bar gate (registered in merge-policy.json, `--repo {head_tree} --json`) that judges
the ledger AS COMMITTED at head. An absent ledger is a clean pass (no-op), reported not
silently green. Stdlib-only.

Exit codes: 0 = valid or absent · 1 = ledger has errors (malformed / expired / unstamped)
· 2 = could not run (repo not found).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import merge_disposition  # noqa: E402  (dir-local reader + validator)


def eprint(*a):
    print(*a, file=sys.stderr)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate .merge-bar/dispositions.json.")
    parser.add_argument("--repo", default=".", help="repository root holding the ledger")
    parser.add_argument("--today", help="override today for expiry (YYYY-MM-DD; tests)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    repo = os.path.abspath(args.repo)
    if not os.path.isdir(repo):
        eprint(f"disposition-lint: ERROR — repo not found: {repo}")
        return 2
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        eprint(f"disposition-lint: ERROR — bad --today {args.today!r}")
        return 2

    path = os.path.join(repo, merge_disposition.LEDGER_RELPATH)
    entries, parse_err = merge_disposition.read_ledger_file(path)
    errors = [parse_err] if parse_err else merge_disposition.validate(entries, today)

    result = {
        "schema_version": 1,
        "status": "fail" if errors else "pass",
        "ledger_present": os.path.isfile(path),
        "dispositions": len(entries),
        "hard_failures": errors,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if not result["ledger_present"]:
            print("disposition-lint: no .merge-bar/dispositions.json (nothing to validate).")
        elif errors:
            print(f"disposition-lint: {len(errors)} error(s) in {len(entries)} disposition(s).")
            for e in errors:
                print(f"  ✗ {e}")
        else:
            print(f"disposition-lint: {len(entries)} disposition(s) valid.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
