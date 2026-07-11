#!/usr/bin/env python3
"""guard_log.py — the single tamper-evident writer for the core-engineering guards.

git-guard.py, env-guard.py, and write-scope-guard.py all record their permission
decisions to one append-only ledger, `.claude/ce-guard-log.jsonl`. This module is
the SINGLE writer: every guard routes its decision through `append_entry()`, so
each line carries an UNKEYED sha256 hash chain over the previous raw line.
`--verify <file>` re-derives that chain and reports the first break. It proves
ONLY that the file on disk is internally self-consistent: it catches accidental
corruption and a NAIVE edit / deletion / reorder that leaves a later line's
`prev` dangling. It does NOT — and an unkeyed public chain cannot — detect
tampering by an actor who ALSO recomputes the downstream `prev` values, nor a
wholesale re-genesis of the file (see "What the chain proves — and does not").

Each JSONL entry:
  ts             UTC ISO-8601 (seconds) — when the decision was recorded
  guard          the writing hook: "git-guard" | "env-guard" | "write-scope-guard"
  decision       the permission verdict: "ask" | "deny" | "allow"
  reason         the human-readable deny/ask message
  session_id     the harness session id from the hook payload ("" if absent)
  tool           actor field: the tool_name the guard screened ("" if unknown)
  hook_event     actor field: the hook event name (default "PreToolUse")
  payload_sha256 sha256 over json.dumps(tool_input, sort_keys=True) — binds the
                 logged decision to the exact tool call that provoked it
  prev           sha256 of the previous raw JSONL line ("" at genesis)

Contracts:
  * `append_entry` NEVER raises — a logging failure must not change a permission
    decision (the guards call it on the deny/ask path). It swallows every error.
  * `--verify <file>` exits 0 (chain valid) / 1 (chain broken) / 2 (could not
    run) — the portability_check exit contract for a standalone hook script.

What the chain proves — and does not. The chain is UNKEYED: `prev` is a plain,
public sha256 over the previous raw line — no secret, no external anchor. So
`--verify` alone is CORRUPTION-evidence, not ADVERSARY-evidence:

  * It CATCHES a naive edit, deletion, or reorder — one that changes a line but
    leaves the following line's `prev` pointing at the pre-change hash (that first
    mismatch is the reported break). This is the accidental-damage / careless-
    tamperer case, and it is the only case `--verify` closes on its own.
  * It does NOT catch an actor with write access who edits / deletes / reorders a
    line and then recomputes every downstream `prev` walking forward from the
    change. The re-chained file is internally consistent, so `--verify` returns 0.
    The algorithm is public and deterministic, so re-chaining is a few lines of
    code — available to the very agent this log audits.
  * It does NOT catch wholesale re-genesis: replacing the whole file with a fresh
    forged genesis line (`prev == ""`) — of any length, shorter, equal, or longer
    than the real history. Nothing binds the genesis line to any prior state.
  * There is no genesis binding and no chain-length floor: an EMPTY (0-entry) file
    and a SINGLE genesis line both verify as a "valid chain" (exit 0).

Real tamper-evidence therefore lives OUT OF BAND, not in this file. The chain head
(the last raw line's sha256 plus the entry count) must be recorded and RETAINED BY
AN INDEPENDENT PARTY — git-committed, shipped to CI, or delivered to the auditor —
and a later log diffed against it; only that external comparison detects a
re-chained edit / delete / reorder, a re-genesis, or a tail-truncation. The disk-
local record does not itself provide this: a chain head written back onto the same
agent-writable tree is re-writable too and anchors nothing (the evidence pack
records a chain head, but it has anti-tamper value only once a human or external
process archives it off this disk and compares). `--verify` stays useful for its
honest job — confirming the on-disk chain is self-consistent — but the external
prior-head comparison is load-bearing for ALL adversarial tamper detection. The
hooks/README.md honest-limitations note carries the same statement.

Concurrency: writes are best-effort and assume one guard writes at a time. Two
guards deciding on the very same tool call in parallel could interleave; the
verifier would then flag the interleave as a chain break rather than lose it
silently. Stdlib-only, no packaging — guards import this by inserting their own
directory on sys.path (same-dir sibling import, loaded by path).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

GUARD_LOG = ".claude/ce-guard-log.jsonl"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _last_raw_line(path: str) -> str:
    """The last newline-terminated record already in the log, WITHOUT its
    terminator — the exact string whose sha256 becomes the next entry's `prev`.
    Empty string if the file is absent or empty (genesis)."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return ""
    return lines[-1] if lines else ""


def payload_hash(tool_input) -> str:
    """sha256 over the canonical JSON form of a tool_input: the same call always
    hashes identically, so the logged decision is bound to the exact payload that
    provoked it. `default=str` is a belt for the impossible non-JSON input (the
    payload always arrives via json.load); real inputs hash as a plain
    json.dumps(tool_input, sort_keys=True)."""
    try:
        canonical = json.dumps(tool_input, sort_keys=True, default=str)
    except (TypeError, ValueError):
        canonical = json.dumps(str(tool_input))
    return _sha256(canonical)


def append_entry(root, guard, decision, reason, payload,
                 session_id="", tool="", hook_event="PreToolUse") -> None:
    """Append one hash-chained decision to `<root>/.claude/ce-guard-log.jsonl`.

    NEVER raises: a logging failure must not change a permission decision. Every
    error (an unwritable dir, a race, a serialization problem) is swallowed — the
    guard's decision has already been made by the time this runs.
    """
    try:
        base = str(root) if root else (
            os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        path = os.path.join(base, GUARD_LOG)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        prev = _last_raw_line(path)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "guard": guard,
            "decision": decision,
            "reason": reason,
            "session_id": session_id or "",
            "tool": tool or "",
            "hook_event": hook_event or "PreToolUse",
            "payload_sha256": payload_hash(payload),
            "prev": _sha256(prev) if prev else "",
        }
        line = json.dumps(entry, sort_keys=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def verify(path: str) -> int:
    """Re-derive the hash chain and report the first break.
    Exit 0 (valid) / 1 (broken) / 2 (could-not-run).

    Proves INTERNAL CONSISTENCY ONLY (see the module docstring): a re-chained
    edit / delete / reorder, a wholesale re-genesis, and an empty or single-
    genesis-line file all return 0. Adversarial tamper detection needs the
    out-of-band chain-head comparison, not this call alone."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw_lines = fh.read().splitlines()
    except FileNotFoundError:
        print(f"guard_log: no log at {path} — nothing to verify.", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"guard_log: cannot read {path} ({exc.__class__.__name__}).",
              file=sys.stderr)
        return 2

    expected_prev = ""
    for i, raw in enumerate(raw_lines, start=1):
        if not raw.strip():
            print(f"guard_log: line {i} is blank — chain unverifiable.",
                  file=sys.stderr)
            return 1
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            print(f"guard_log: line {i} is not valid JSON — chain unverifiable.",
                  file=sys.stderr)
            return 1
        if not isinstance(obj, dict) or "prev" not in obj:
            print(f"guard_log: line {i} is not a chained entry (missing `prev`).",
                  file=sys.stderr)
            return 1
        if obj["prev"] != expected_prev:
            print(f"guard_log: chain broken at line {i} — recorded prev "
                  f"{obj['prev']!r} != expected {expected_prev!r}. A preceding "
                  "line was edited, deleted, or reordered.", file=sys.stderr)
            return 1
        expected_prev = _sha256(raw)

    n = len(raw_lines)
    print(f"guard_log: chain valid — {n} entr{'y' if n == 1 else 'ies'} in {path}.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Tamper-evident writer/verifier for the core-engineering guard log")
    parser.add_argument("--verify", metavar="FILE",
                        help="verify the hash chain of a guard-log JSONL file")
    args = parser.parse_args(argv)
    if args.verify:
        return verify(args.verify)
    parser.print_usage(sys.stderr)
    print("guard_log: nothing to do — pass --verify <file> to check a log's hash "
          "chain (this module is otherwise imported by the guard hooks, which "
          "route their decisions through append_entry).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # never a fake FAIL — could-not-run is exit 2
        print(f"guard_log: unexpected error: {exc.__class__.__name__}: {exc}",
              file=sys.stderr)
        sys.exit(2)
