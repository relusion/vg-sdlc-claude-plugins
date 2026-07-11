#!/usr/bin/env python3
"""
run-state.py — the deterministic owner of ce-auto-build's run state.

The auto-build orchestrator used to hand-write its run state in prose: append a
ledger row, tick a retry counter, bump a park counter, re-derive the
circuit-breaker verdict by eye. Every one of those was a place a model could
miscount and a `/ce-retro` reader could not trust. This script makes each
transition a single, atomic, exit-code-checked call so the state is owned by
mechanism, not discipline.

It owns exactly one file per run — `<plan-dir>/ce-auto-build/<date>-state.json`
(the canonical path SKILL.md names; status-board.py reads its parked/failed
overlay) — plus two append-only streams beside/under the plan dir:
  * `<plan-dir>/ce-auto-build/<date>-ledger.jsonl` — the provisional machine
    ledger the Stage-3 end-review confirms;
  * `<plan-dir>/.metrics.jsonl` — the canonical ce-retro stream (schema in
    ce-retro/SKILL.md), one line per state transition so retro inputs are
    trustworthy by construction.

**Authority, not source of truth.** state.json stays a *cache* — SKILL.md's
"disk wins" doctrine is unchanged. This script owns the *writes* (so they are
atomic and counted correctly); it never becomes the authority the resume path
re-derives from artifacts. It only knows what it is told and what it has
persisted; it does not read the plan's spec/verification/review artifacts.

Subcommands
-----------
  init          create the run's state.json (bounds + zeroed counters)
  advance       move a feature along the specced→…→done lattice (illegal → exit 2)
  park          mark a feature parked; bump the consecutive-park counter
  retry         bump a feature's retry count; exit 1 when the cap is reached
  budget-add    add an estimated token cost to the running budget total
  ledger-append append a `provisional (auto-build <date>)`-marked decision row
  breaker-check evaluate the run-level circuit-breaker bounds (exit 1 = break)

Exit codes (the house 0/1/2 contract)
-------------------------------------
  0  the operation succeeded / continue
  1  a bounded signal the caller must act on:
        retry        — the per-feature retry cap was reached
        breaker-check — a run-level bound tripped (circuit-break)
  2  could-not-do-that: an illegal transition, a missing/invalid state file,
     unparseable input, a re-init clash — never a silent success, never a crash

All writes are atomic: state.json via tempfile + os.replace (never a half-written
document); the append-only streams via a single O_APPEND os.write (never a
partial line, never clobbering a concurrent producer). The single deviation from
"tempfile+os.replace for every write" is deliberate — os.replace on an
append-only shared stream would race a concurrent producer's line, so O_APPEND is
the correct atomic primitive there.

Stdlib-only by design (the portability guarantee): no Claude Code, no network.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

# The forward status lattice a feature walks. Optional stages (challenged when
# the Challenger is off, reviewed when review mode is off) may be skipped — a
# transition is legal as long as it moves strictly forward.
LATTICE = [
    "queued", "specced", "challenged", "implementing",
    "verifying", "reviewed", "done",
]
RANK = {s: i for i, s in enumerate(LATTICE)}

# Side/detour states reachable off the forward lattice.
DIAGNOSING = "diagnosing"   # a failed verify/review gate routes here (diagnose mode)
FAILED = "failed"           # terminal failure (advance target)
PARKED = "parked"           # terminal park (set only via the `park` subcommand)

# The full vocabulary `advance` accepts as a target (parked is NOT here — it has
# its own subcommand because it bumps the consecutive-park counter).
ADVANCE_TARGETS = set(LATTICE) | {DIAGNOSING, FAILED}


# --------------------------------------------------------------------------- #
# Atomic IO
# --------------------------------------------------------------------------- #

def atomic_write_json(path: Path, obj) -> None:
    """Write a JSON document atomically (tempfile in the same dir + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_append_line(path: Path, obj) -> None:
    """Append one JSON line atomically via a single O_APPEND os.write.

    O_APPEND makes the write land at end-of-file as one operation, so a
    concurrent producer's line is never clobbered and a partial line is never
    left behind — the correct atomic primitive for an append-only stream (unlike
    os.replace, which would race a concurrent append).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(obj, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)


def load_json(path: Path):
    """Best-effort JSON read: None on any miss."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# State-file location
# --------------------------------------------------------------------------- #

class RunStateError(Exception):
    """A could-not-do-that condition → exit 2 with a JSON reason on stdout."""


def _clean_date(raw: str) -> str:
    """A date token safe to embed in a filename (no separators / parent refs)."""
    if not raw or "/" in raw or "\\" in raw or ".." in raw:
        raise RunStateError(f"unsafe --date token: {raw!r}")
    return raw


def state_dir(plan_dir: Path) -> Path:
    return plan_dir / "ce-auto-build"


def locate_state(args) -> Path:
    """Resolve the active state.json for a non-init subcommand.

    Precedence: an explicit --state path, else the newest `*-state.json` under
    `<plan-dir>/ce-auto-build/` (by mtime, ties by name — matches status-board's
    'newest' rule). Missing → RunStateError (exit 2): you cannot mutate a run
    that was never initialized.
    """
    if getattr(args, "state", None):
        p = Path(args.state)
        if not p.is_file():
            raise RunStateError(f"--state file not found: {p}")
        return p
    if not getattr(args, "plan_dir", None):
        raise RunStateError("need --plan-dir or --state")
    d = state_dir(Path(args.plan_dir))
    cand = list(d.glob("*-state.json")) if d.is_dir() else []
    if not cand:
        raise RunStateError(
            f"no *-state.json under {d} — run `init` first (or pass --state)")
    try:
        return max(cand, key=lambda p: (p.stat().st_mtime, p.name))
    except OSError:
        return sorted(cand)[-1]


def load_state(path: Path) -> dict:
    data = load_json(path)
    if not isinstance(data, dict):
        raise RunStateError(f"state file unreadable or not an object: {path}")
    return data


def plan_dir_of(state_path: Path) -> Path:
    """The `docs/plans/<slug>` dir: parent of the ce-auto-build/ state dir."""
    return state_path.parent.parent


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

def emit_metric(state_path: Path, state: dict, *, feature, event,
                gate=None, escalation_type=None, detail="", tokens=0) -> None:
    """Append one canonical ce-retro metrics line (schema: ce-retro/SKILL.md).

    Best-effort by the stream's own contract — a metrics failure must never
    fail the transition, so it is swallowed (the state write already succeeded).
    """
    line = {
        "ts": state.get("date"),
        "stage": "auto-build",
        "plan": state.get("slug"),
        "feature": feature,
        "event": event,
        "gate": gate,
        "escalation_type": escalation_type,
        "detail": detail,
        "est": {"tokens": int(tokens)},
    }
    try:
        atomic_append_line(plan_dir_of(state_path) / ".metrics.jsonl", line)
    except OSError:
        pass


def feature_entry(state: dict, fid: str) -> dict:
    features = state.setdefault("features", {})
    if not isinstance(features, dict):
        raise RunStateError("state.features is not an object — corrupt state file")
    entry = features.get(fid)
    if not isinstance(entry, dict):
        entry = {"status": "queued", "last_completed_gate": None, "park_class": None}
        features[fid] = entry
    return entry


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #

def cmd_init(args) -> int:
    plan_dir = Path(args.plan_dir)
    if not plan_dir.is_dir():
        raise RunStateError(f"--plan-dir is not an existing directory: {plan_dir}")
    date = _clean_date(args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    sd = state_dir(plan_dir)
    sd.mkdir(parents=True, exist_ok=True)
    path = sd / f"{date}-state.json"
    if path.exists() and not args.force:
        raise RunStateError(
            f"run already initialized: {path} exists "
            f"(use --resume on the orchestrator, not re-init; --force to overwrite)")

    spawn_caps = {}
    for item in args.spawn_cap or []:
        if "=" not in item:
            raise RunStateError(f"--spawn-cap wants NAME=INT, got {item!r}")
        name, _, val = item.partition("=")
        try:
            spawn_caps[name] = int(val)
        except ValueError:
            raise RunStateError(f"--spawn-cap {name} value not an int: {val!r}")

    state = {
        "schema_version": SCHEMA_VERSION,
        "slug": plan_dir.name,
        "date": date,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bounds": {
            "budget": args.budget,
            "retry_cap": args.retry_cap,
            "park_cap": args.park_cap,
            "spawn_caps": spawn_caps,
        },
        "counters": {
            "consecutive_parks": 0,
            "budget_spent": 0,
        },
        "retry_counts": {},
        "features": {},
    }
    atomic_write_json(path, state)
    print(json.dumps({"ok": True, "state": str(path),
                      "slug": state["slug"], "date": date}))
    return 0


def _legal_advance(cur: str, tgt: str) -> bool:
    if tgt not in ADVANCE_TARGETS:
        return False
    if tgt == FAILED:                       # a feature can fail from any live state
        return cur not in ("done", FAILED, PARKED)
    if cur == DIAGNOSING:                   # diagnose(bug) → targeted re-implement
        return tgt == "implementing"
    if tgt == DIAGNOSING:                   # a failed verify/review gate → diagnose
        return cur in ("verifying", "reviewed")
    if cur in RANK and tgt in RANK:         # strictly forward (skips optional stages)
        return RANK[tgt] > RANK[cur]
    return False


def cmd_advance(args) -> int:
    path = locate_state(args)
    state = load_state(path)
    entry = feature_entry(state, args.feature)
    cur = entry.get("status", "queued")
    tgt = args.gate

    if not _legal_advance(cur, tgt):
        print(json.dumps({"error": "illegal-transition", "feature": args.feature,
                          "from": cur, "to": tgt}))
        return 2

    entry["status"] = tgt
    entry["last_completed_gate"] = tgt
    if tgt == "done":
        # A completed feature breaks a park streak (per the plan's reset rule).
        state.setdefault("counters", {})["consecutive_parks"] = 0
    if args.tokens:
        c = state.setdefault("counters", {})
        c["budget_spent"] = int(c.get("budget_spent", 0)) + int(args.tokens)
    atomic_write_json(path, state)

    # Derive the metrics event from the transition (caller may override the
    # detail, and name a diagnose→implement bug escalation via --escalation).
    if args.escalation:
        event, gate, esc = "escalation", None, args.escalation
    elif tgt == "done":
        event, gate, esc = "stage-complete", None, None
    elif tgt == FAILED:
        event, gate, esc = "gate", "fail", None
    elif tgt == DIAGNOSING:
        event, gate, esc = "gate", None, None      # a routing step: neither pass nor fail
    else:
        event, gate, esc = "gate", "pass", None
    emit_metric(path, state, feature=args.feature, event=event, gate=gate,
                escalation_type=esc, detail=args.detail or f"advance:{tgt}",
                tokens=args.tokens or 0)
    print(json.dumps({"ok": True, "feature": args.feature,
                      "from": cur, "to": tgt}))
    return 0


def cmd_park(args) -> int:
    path = locate_state(args)
    state = load_state(path)
    entry = feature_entry(state, args.feature)
    if not args.klass or not args.klass.strip():
        raise RunStateError("--class must be a non-empty park class")

    entry["status"] = PARKED
    entry["last_completed_gate"] = PARKED
    entry["park_class"] = args.klass
    c = state.setdefault("counters", {})
    c["consecutive_parks"] = int(c.get("consecutive_parks", 0)) + 1
    if args.tokens:
        c["budget_spent"] = int(c.get("budget_spent", 0)) + int(args.tokens)
    atomic_write_json(path, state)

    emit_metric(path, state, feature=args.feature, event="park", gate=None,
                escalation_type=None, detail=args.detail or f"park:{args.klass}",
                tokens=args.tokens or 0)
    print(json.dumps({"ok": True, "feature": args.feature, "class": args.klass,
                      "consecutive_parks": c["consecutive_parks"]}))
    return 0


def cmd_retry(args) -> int:
    path = locate_state(args)
    state = load_state(path)
    feature_entry(state, args.feature)        # ensure the feature is tracked
    counts = state.setdefault("retry_counts", {})
    if not isinstance(counts, dict):
        raise RunStateError("state.retry_counts is not an object — corrupt state file")
    n = int(counts.get(args.feature, 0)) + 1
    counts[args.feature] = n
    if args.tokens:
        c = state.setdefault("counters", {})
        c["budget_spent"] = int(c.get("budget_spent", 0)) + int(args.tokens)
    atomic_write_json(path, state)

    cap = int(state.get("bounds", {}).get("retry_cap", 0) or 0)
    emit_metric(path, state, feature=args.feature, event="retry", gate=None,
                escalation_type=None, detail=args.detail or f"retry:{n}/{cap}",
                tokens=args.tokens or 0)
    reached = cap > 0 and n >= cap
    print(json.dumps({"ok": True, "feature": args.feature, "retries": n,
                      "cap": cap, "cap_reached": reached}))
    # exit 1 when the cap is reached so the caller cannot miscount.
    return 1 if reached else 0


def cmd_budget_add(args) -> int:
    path = locate_state(args)
    state = load_state(path)
    c = state.setdefault("counters", {})
    c["budget_spent"] = int(c.get("budget_spent", 0)) + int(args.tokens)
    atomic_write_json(path, state)
    budget = state.get("bounds", {}).get("budget")
    print(json.dumps({"ok": True, "budget_spent": c["budget_spent"],
                      "budget": budget}))
    return 0


def cmd_ledger_append(args) -> int:
    path = locate_state(args)
    state = load_state(path)
    try:
        row = json.loads(args.entry)
    except (json.JSONDecodeError, ValueError) as e:
        raise RunStateError(f"--entry is not valid JSON: {e}")
    if not isinstance(row, dict):
        raise RunStateError("--entry must be a JSON object (one ledger row)")

    date = state.get("date")
    # Mark every auto-build append provisional so the end-review can confirm or
    # revert it (the marker the Stage-3 confirmation looks for).
    row.setdefault("ts", date)
    row["provisional"] = f"auto-build {date}"
    ledger = path.parent / f"{date}-ledger.jsonl"
    atomic_append_line(ledger, row)
    print(json.dumps({"ok": True, "ledger": str(ledger)}))
    return 0


def cmd_breaker_check(args) -> int:
    """Evaluate the run-level circuit-breaker bounds.

    Checks only the RUN-level bounds that are unambiguous from state alone:
    the consecutive-park cap and the token budget. It deliberately does NOT
    re-derive the per-feature retry cap — that is the `retry` subcommand's
    exit-1 signal, disposed by the caller (in diagnose mode a bug that exhausts
    the cap parks rather than halting the run, a control-flow call the caller
    owns).

    Exit 0 continue · 1 circuit-break (JSON reason names the tripped bound) ·
    2 could-not-evaluate.
    """
    path = locate_state(args)
    state = load_state(path)
    bounds = state.get("bounds", {}) if isinstance(state.get("bounds"), dict) else {}
    counters = state.get("counters", {}) if isinstance(state.get("counters"), dict) else {}

    tripped = []
    park_cap = bounds.get("park_cap")
    parks = int(counters.get("consecutive_parks", 0) or 0)
    if isinstance(park_cap, int) and park_cap > 0 and parks >= park_cap:
        tripped.append({"bound": "consecutive-park-cap", "value": parks, "limit": park_cap})

    budget = bounds.get("budget")
    spent = int(counters.get("budget_spent", 0) or 0)
    if isinstance(budget, int) and budget > 0 and spent >= budget:
        tripped.append({"bound": "budget-exhausted", "value": spent, "limit": budget})

    if tripped:
        reason = "; ".join(f"{t['bound']} ({t['value']}/{t['limit']})" for t in tripped)
        print(json.dumps({"verdict": "circuit-break", "reason": reason,
                          "bounds": tripped}))
        return 1
    print(json.dumps({"verdict": "continue",
                      "consecutive_parks": parks, "budget_spent": spent}))
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="run-state.py",
        description="Deterministic owner of ce-auto-build run state")
    sub = ap.add_subparsers(dest="command")

    def add_locator(p):
        p.add_argument("--plan-dir", help="the docs/plans/<slug> directory")
        p.add_argument("--state", help="explicit path to <date>-state.json (overrides --plan-dir)")

    p_init = sub.add_parser("init", help="create the run's state.json")
    p_init.add_argument("--plan-dir", required=True, help="the docs/plans/<slug> directory")
    p_init.add_argument("--date", help="run date (YYYY-MM-DD); default: today UTC")
    p_init.add_argument("--budget", type=int, default=None,
                        help="token/compute budget (estimate); omit for no budget bound")
    p_init.add_argument("--retry-cap", type=int, default=3,
                        help="per-feature verification-retry cap (default 3)")
    p_init.add_argument("--park-cap", type=int, default=3,
                        help="consecutive-park cap (default 3)")
    p_init.add_argument("--spawn-cap", action="append", metavar="NAME=INT",
                        help="per-spawn sub-cap, repeatable")
    p_init.add_argument("--force", action="store_true",
                        help="overwrite an existing state.json for this date")
    p_init.set_defaults(func=cmd_init)

    p_adv = sub.add_parser("advance", help="move a feature along the status lattice")
    p_adv.add_argument("feature")
    p_adv.add_argument("gate", help="target status/gate "
                       "(specced|challenged|implementing|verifying|reviewed|done|diagnosing|failed)")
    add_locator(p_adv)
    p_adv.add_argument("--detail", help="metrics detail string override")
    p_adv.add_argument("--tokens", type=int, default=0,
                       help="estimated token cost of the transition (accrues to budget)")
    p_adv.add_argument("--escalation", metavar="TARGET",
                       help="emit an escalation metric to TARGET (e.g. /ce-implement) instead of a gate line")
    p_adv.set_defaults(func=cmd_advance)

    p_park = sub.add_parser("park", help="mark a feature parked")
    p_park.add_argument("feature")
    p_park.add_argument("--class", dest="klass", required=True,
                        help="park class (spec-gap|structural|surface-defect|product|destructive|...)")
    add_locator(p_park)
    p_park.add_argument("--detail", help="metrics detail string override")
    p_park.add_argument("--tokens", type=int, default=0)
    p_park.set_defaults(func=cmd_park)

    p_retry = sub.add_parser("retry", help="bump a feature's retry count (exit 1 at cap)")
    p_retry.add_argument("feature")
    add_locator(p_retry)
    p_retry.add_argument("--detail", help="metrics detail string override")
    p_retry.add_argument("--tokens", type=int, default=0)
    p_retry.set_defaults(func=cmd_retry)

    p_bud = sub.add_parser("budget-add", help="add an estimated token cost to the running total")
    p_bud.add_argument("--tokens", type=int, required=True)
    add_locator(p_bud)
    p_bud.set_defaults(func=cmd_budget_add)

    p_led = sub.add_parser("ledger-append", help="append a provisional decision row")
    p_led.add_argument("--entry", required=True, help="the ledger row as a JSON object")
    add_locator(p_led)
    p_led.set_defaults(func=cmd_ledger_append)

    p_brk = sub.add_parser("breaker-check", help="evaluate the circuit-breaker bounds")
    add_locator(p_brk)
    p_brk.set_defaults(func=cmd_breaker_check)

    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "command", None):
        ap.print_usage(sys.stderr)
        print("run-state.py: a subcommand is required "
              "(init|advance|park|retry|budget-add|ledger-append|breaker-check)",
              file=sys.stderr)
        return 2
    try:
        return args.func(args)
    except RunStateError as e:
        print(json.dumps({"error": "could-not-run", "reason": str(e)}))
        return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — could-not-run must exit 2, never a fake FAIL
        print(f"run-state: unexpected error: {type(e).__name__}: {e}",
              file=sys.stderr)
        sys.exit(2)
