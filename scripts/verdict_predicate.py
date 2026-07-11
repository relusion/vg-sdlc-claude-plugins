#!/usr/bin/env python3
"""verdict_predicate.py — project a merge-verdict.json into the minimal, signable
attestation predicate the merge bar attests over.

The problem it closes: a green merge-bar CI check is only as trustworthy as the
workflow file that produced it, and on `pull_request` that workflow runs from
the PR merge ref — so a PR can, in principle, rewrite the very check that gates
it. This script is the transform half of the fix: it reduces the full
`gate_runner.py` verdict to a WHITELISTED predicate that `actions/attest` binds
to the workflow's OIDC identity via a sigstore-signed attestation. Verification
(`gh attestation verify`) then proves a green check judged THESE commits under
THIS policy hash, independently of the workflow that emitted it.

The predicate carries ONLY fields gate_runner already records (verified against
main() in scripts/gate_runner.py) — nothing model-derived, and no filesystem
path (verdict['policy']['path'], verdict['repo'], and each gate run's argv all
carry local absolute paths and are deliberately DROPPED):

    {
      "base_sha": ...,             # from verdict['base_sha']
      "head_sha": ...,             # from verdict['head_sha']
      "policy_sha256": ...,        # from verdict['policy']['sha256'] (nested)
      "status": ...,               # from verdict['status']
      "change_class": ...,         # from verdict['change_class']
      "change_class_source": ...,  # from verdict['change_class_source']
      "validity_required": ...,    # from verdict['validity_required']
      "gates": [                   # from verdict['gates'][*], projected to 3 keys
        {"id": ..., "disposition": ..., "status": ...},
        ...
      ]
    }

Note the ONE field-name difference from a flat read of the verdict:
`policy_sha256` is projected from the NESTED `verdict['policy']['sha256']`
(gate_runner records the policy provenance under a `policy` object, not as a
top-level `policy_sha256` key). Every other field is a top-level verdict key.

Exit codes (house 0/1/2 contract):
    0  the predicate was emitted
    1  reserved — never returned: this is a pure transform, not a gate, so it
       has no "FAIL" verdict of its own; it either projects (0) or cannot (2)
    2  could not run: usage error, unreadable/non-JSON input, a top level that
       is not a JSON object, or a MALFORMED verdict (missing a whitelisted
       field, or a gates entry that is not an object with id/disposition/status)
       — a gate_runner runner-error verdict ({"status":"error","message":...})
       lacks the whitelisted fields and lands here by design: there is no merge
       decision to attest.

Stdlib-only, offline, Claude-free — it runs anywhere Python does.
"""

from __future__ import annotations

import argparse
import json
import sys

# The predicate's SCALAR fields, each read from the identically-named top-level
# verdict key. This IS the whitelist: no other verdict field may enter the
# predicate, so nothing model-derived (and no local filesystem path) leaks into
# the signed attestation.
SCALAR_FIELDS = (
    "base_sha",
    "head_sha",
    "status",
    "change_class",
    "change_class_source",
    "validity_required",
)

# Each gate record is projected to exactly these three keys (the verdict's gate
# records also carry `proves` and a `runs` list whose argv holds absolute paths
# — both DROPPED).
GATE_FIELDS = ("id", "disposition", "status")

# The full, ordered set of predicate keys — the single source the round-trip
# test asserts against so a future field addition is a reviewable diff here.
PREDICATE_KEYS = (
    "base_sha",
    "head_sha",
    "policy_sha256",
    "status",
    "change_class",
    "change_class_source",
    "validity_required",
    "gates",
)


class PredicateError(Exception):
    """The input is not a well-formed gate_runner verdict -> exit 2 (this tool
    never impersonates a gate FAIL)."""


def build_predicate(verdict: object) -> dict:
    """Project a gate_runner verdict object into the minimal signable predicate.

    Raises PredicateError on any malformed input (top level not an object, a
    missing whitelisted field, or a gates entry that is not a projectable
    record)."""
    if not isinstance(verdict, dict):
        raise PredicateError(
            "verdict top level must be a JSON object, got "
            f"{type(verdict).__name__}")

    predicate: dict = {}
    # base_sha / head_sha come first (predicate key order matches PREDICATE_KEYS),
    # then policy_sha256 spliced in from the nested policy object.
    for field in ("base_sha", "head_sha"):
        if field not in verdict:
            raise PredicateError(f"verdict missing required field {field!r}")
        predicate[field] = verdict[field]

    policy = verdict.get("policy")
    if not isinstance(policy, dict) or "sha256" not in policy:
        raise PredicateError(
            "verdict missing verdict['policy']['sha256'] — the policy "
            "provenance the predicate binds")
    predicate["policy_sha256"] = policy["sha256"]

    for field in ("status", "change_class", "change_class_source",
                  "validity_required"):
        if field not in verdict:
            raise PredicateError(f"verdict missing required field {field!r}")
        predicate[field] = verdict[field]

    gates = verdict.get("gates")
    if not isinstance(gates, list):
        raise PredicateError("verdict['gates'] must be a list")
    projected_gates: list = []
    for i, gate in enumerate(gates):
        if not isinstance(gate, dict):
            raise PredicateError(f"verdict['gates'][{i}] must be an object")
        missing = [k for k in GATE_FIELDS if k not in gate]
        if missing:
            raise PredicateError(
                f"verdict['gates'][{i}] missing {', '.join(missing)}")
        projected_gates.append({k: gate[k] for k in GATE_FIELDS})
    predicate["gates"] = projected_gates

    return predicate


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Project a merge-verdict.json into the minimal signable "
                    "attestation predicate (the whitelisted fields only).")
    p.add_argument("--in", dest="in_path", metavar="PATH", default=None,
                   help="merge-verdict.json to read (default: stdin)")
    p.add_argument("--out", dest="out_path", metavar="PATH", default=None,
                   help="write the predicate here (default: stdout)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.in_path is None:
            raw = sys.stdin.read()
        else:
            try:
                with open(args.in_path, encoding="utf-8") as fh:
                    raw = fh.read()
            except (OSError, UnicodeDecodeError) as e:
                raise PredicateError(f"cannot read --in {args.in_path}: {e}") from e
        try:
            verdict = json.loads(raw)
        except ValueError as e:
            raise PredicateError(f"input is not valid JSON: {e}") from e

        predicate = build_predicate(verdict)
        text = json.dumps(predicate, indent=2) + "\n"

        if args.out_path is None:
            sys.stdout.write(text)
        else:
            # Atomic write: tmp + rename so a partial predicate is never signed.
            tmp = args.out_path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(text)
                import os
                os.replace(tmp, args.out_path)
            except OSError as e:
                raise PredicateError(
                    f"cannot write --out {args.out_path}: {e}") from e
        return 0
    except PredicateError as e:
        print(f"verdict-predicate: ERROR — {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — a crash must exit 2, never a fake 1
        print(f"verdict-predicate: ERROR — unexpected "
              f"({type(e).__name__}): {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
