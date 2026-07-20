#!/usr/bin/env python3
"""
status-board.py — regenerate a plan's STATUS.md supervision board.

A read-mostly projection: derives each feature's status from the SAME on-disk
checks the auto-build gates and Resume use (ce-spec.md present — legacy
spec.md accepted, tasks.json
all-done, verification.md present, review-summary.json blocking_high) — disk
wins, claims are never trusted. The only states that have no disk artifact of
their own (parked / failed) are overlaid from the newest (by mtime)
ce-auto-build/<date>-state.json when one exists, and are labeled as such.

STATUS.md is GENERATED, never hand-edited — it is a projection over the
artifacts, not a second source of truth. The board never gates anything;
generation is best-effort and a failure here must never block a run, so every
per-feature hazard (a bad id, a corrupt review file, an off-schema field)
degrades that ONE row loudly and the board still renders.

When plan.json is absent (a light plan) but the dir has a specs/ subdir or a
feature-plan.md, the board degrades instead of failing: it lists specs/<id>/
dirs and derives states from disk only, labeled
`degraded (no plan.json — states only, no ship order)`. Every board — normal
or degraded — ends with exactly one `Next:` footer line naming the first
actionable feature (/core-engineering:ce-spec, /core-engineering:ce-implement, or /core-engineering:ce-verify); it is a
suggestion — a projection, never a gate.

Usage:
    python3 status-board.py <plan-dir>            # print board to stdout
    python3 status-board.py <plan-dir> --write    # write <plan-dir>/STATUS.md

Exit codes:
    0  board generated (full or degraded)
    1  plan dir invalid (no usable plan.json AND no specs/ AND no feature-plan.md)
    2  unexpected internal error (could-not-run; never impersonates a FAIL)

Stdlib-only by design (the portability guarantee): no Claude Code, no network.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATUS_ORDER = [
    "queued", "specced", "in-progress", "implementing", "implemented",
    "reviewed", "gate-blocked", "parked", "failed", "invalid-id",
]

DEGRADED_LABEL = "degraded (no plan.json — states only, no ship order)"
FOOTER_SUFFIX = "  (suggestion — a projection, never a gate)"


def load_json(path: Path):
    """Best-effort JSON read: None on any miss (absence is data here, not an error)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None


def safe_spec_dir(plan_dir: Path, fid: str):
    """specs/<fid> only if it stays inside plan_dir/specs; else None.

    A feature id is an on-disk directory name, never a path: reject anything
    with a separator or a parent ref, and confirm the resolved candidate is a
    child of specs/ — so a crafted id like `../../../etc` can't make the board
    read and attribute artifacts from outside the plan tree.
    """
    if not fid or fid in (".", "..") or "/" in fid or "\\" in fid or ".." in fid:
        return None
    specs = plan_dir / "specs"
    cand = specs / fid
    try:
        cand_r, specs_r = cand.resolve(), specs.resolve()
    except OSError:
        return None
    if cand_r != specs_r and specs_r not in cand_r.parents:
        return None
    if cand_r == specs_r:
        return None
    return cand


def task_counts(tasks_obj):
    """(done, total, malformed) from a tasks.json object.

    malformed=True when the file is present but `tasks` is not a list — so the
    caller can flag it rather than silently reporting total 0 (which would pull
    a built feature's status back to 'specced').
    """
    if not isinstance(tasks_obj, dict):
        return 0, 0, False
    tasks = tasks_obj.get("tasks")
    if not isinstance(tasks, list):
        return 0, 0, tasks is not None
    total = len(tasks)
    done = sum(1 for t in tasks if isinstance(t, dict) and t.get("status") == "done")
    return done, total, False


def latest_state_overlay(plan_dir: Path) -> dict:
    """{feature_id: 'parked'|'failed'} from the newest run-state *-state.json.

    The canonical location is `ce-auto-build/` (the path SKILL.md names and
    run-state.py owns); the legacy `auto-build/` dir is read only as labeled
    back-compat when no canonical state dir exists, so an old run still renders.

    'Newest' means by modification time (matches the word, and survives
    non-ISO names); ties broken by name. The state file is a convenience cache
    (run-state.py owns its writes; disk still wins), so read it liberally and
    consume ONLY parked/failed — every other status is derived from disk
    artifacts, which win.
    """
    cand = list((plan_dir / "ce-auto-build").glob("*-state.json"))
    if not cand:                                   # labeled back-compat: legacy dir
        cand = list((plan_dir / "auto-build").glob("*-state.json"))
    if not cand:
        return {}
    try:
        newest = max(cand, key=lambda p: (p.stat().st_mtime, p.name))
    except OSError:
        newest = sorted(cand)[-1]
    data = load_json(newest)
    if not isinstance(data, dict):
        return {}
    entries = data.get("features") if isinstance(data.get("features"), dict) else data
    overlay = {}
    if isinstance(entries, dict):
        for fid, val in entries.items():
            status = val if isinstance(val, str) else (
                val.get("status") if isinstance(val, dict) else None
            )
            if status in ("parked", "failed"):
                overlay[str(fid)] = status
    return overlay


def derive(plan_dir: Path, feature: dict, overlay: dict) -> dict:
    fid = str(feature.get("id", ""))
    row = {
        "id": fid,
        "title": str(feature.get("title", "")),
        "ship_order": feature.get("ship_order"),
        "status": "queued",
        "tasks": "—",
        "verified": "—",
        "review_high": "—",
        "note": "",
        # Footer facts (not rendered as columns): None = unknowable, skip.
        "spec_present": None,
        "implemented_on_disk": None,
    }

    spec_dir = safe_spec_dir(plan_dir, fid)
    if spec_dir is None:
        row["status"] = "invalid-id"
        row["note"] = "unsafe/empty feature id — artifacts not read"
        return row

    # ce-spec.md is the canonical spec artifact name; legacy spec.md accepted.
    spec_present = ((spec_dir / "ce-spec.md").is_file()
                    or (spec_dir / "spec.md").is_file())
    done, total, tasks_malformed = task_counts(load_json(spec_dir / "tasks.json"))
    verified = (spec_dir / "verification.md").is_file()
    review_path = spec_dir / "review-summary.json"
    review = load_json(review_path)
    review_unreadable = review_path.is_file() and not isinstance(review, dict)

    notes = []
    if tasks_malformed:
        notes.append("tasks.json malformed (tasks not a list)")

    if not spec_present:
        status = "queued"
    elif total == 0 or done == 0:
        status = "specced"
    elif done < total or not verified:
        status = "implementing"
    else:
        status = "implemented"
        if isinstance(review, dict):
            blocking = review.get("blocking_high")
            try:
                blocking_n = int(blocking)
            except (TypeError, ValueError):
                blocking_n = None
            if blocking_n is None:
                status = "gate-blocked?"
                notes.append("unparseable blocking_high — treat as blocked")
            elif blocking_n > 0:
                status = "gate-blocked"
            else:
                status = "reviewed"
        elif review_unreadable:
            notes.append("review-summary.json present but unreadable")

    if fid in overlay:           # parked/failed exist only in the state cache
        status = overlay[fid]
        notes.append("per state.json")

    high = ""
    if isinstance(review, dict):
        by_sev = review.get("by_severity")
        if isinstance(by_sev, dict) and isinstance(by_sev.get("high"), dict):
            h = by_sev["high"]
            high = f"{h.get('confirmed', 0)}c/{h.get('suspected', 0)}s"

    row.update({
        "status": status,
        "tasks": f"{done}/{total}" if total else "—",
        "verified": "yes" if verified else "—",
        "review_high": high or "—",
        "note": "; ".join(notes),
        "spec_present": spec_present,
        "implemented_on_disk": total > 0 and done == total and verified,
    })
    return row


def derive_degraded(plan_dir: Path) -> list:
    """Rows from listing specs/<id>/ dirs alone — the no-plan.json fallback.

    States come only from disk (spec file → specced; tasks all done +
    verification.md → implemented; anything else → in-progress). No plan.json
    means no ship order and no titles; listing order (sorted dir names) stands
    in. Malformed per-feature inputs degrade that ONE row with a visible
    marker — they never raise.
    """
    specs = plan_dir / "specs"
    try:
        entries = sorted(p for p in specs.iterdir() if p.is_dir()) \
            if specs.is_dir() else []
    except OSError:
        entries = []
    rows = []
    for d in entries:
        # ce-spec.md is the canonical spec artifact name; legacy spec.md accepted.
        spec_present = ((d / "ce-spec.md").is_file() or (d / "spec.md").is_file())
        tasks_path = d / "tasks.json"
        tasks_obj = load_json(tasks_path)
        done, total, tasks_malformed = task_counts(tasks_obj)
        verified = (d / "verification.md").is_file()

        notes = []
        if tasks_path.is_file() and tasks_obj is None:
            notes.append("tasks.json unreadable — state degraded")
        if tasks_malformed:
            notes.append("tasks.json malformed (tasks not a list)")

        implemented = total > 0 and done == total and verified
        if implemented:
            status = "implemented"
        elif spec_present and done == 0:
            status = "specced"
        else:
            status = "in-progress"

        rows.append({
            "id": d.name,
            "title": "",
            "ship_order": None,
            "status": status,
            "tasks": f"{done}/{total}" if total else "—",
            "verified": "yes" if verified else "—",
            "review_high": "—",
            "note": "; ".join(notes),
            "spec_present": spec_present,
            "implemented_on_disk": implemented,
        })
    return rows


def next_action(rows: list, slug: str) -> str:
    """The one `Next:` footer line — first actionable feature, or verify.

    Walks rows in the order given (ship order normally, listing order when
    degraded): first feature with no spec → /core-engineering:ce-spec, first specced-but-not-
    implemented → /core-engineering:ce-implement, all terminal → /core-engineering:ce-verify <slug>. Rows whose
    artifacts couldn't be read (invalid-id) are skipped, never guessed at.
    A suggestion only — a projection, never a gate.
    """
    for r in rows:
        if r.get("spec_present") is None:
            continue
        if not r["spec_present"]:
            return f"Next: /core-engineering:ce-spec {r['id']}{FOOTER_SUFFIX}"
        if not r.get("implemented_on_disk"):
            return f"Next: /core-engineering:ce-implement {r['id']}{FOOTER_SUFFIX}"
    return f"Next: /core-engineering:ce-verify {slug}{FOOTER_SUFFIX}"


def sort_key(r: dict):
    """Total-orderable sort key — a bad ship_order type must never abort the board.

    None last; numeric (int/float) first, by value; any other type after the
    numerics, by string. Never compares int to str directly.
    """
    so = r["ship_order"]
    if so is None:
        return (2, 0.0, "", r["id"])
    if isinstance(so, bool):
        so = int(so)
    if isinstance(so, (int, float)):
        return (0, float(so), "", r["id"])
    return (1, 0.0, str(so), r["id"])


def render(plan_dir: Path, rows: list, degraded_label: str = None) -> str:
    counts = {}
    for r in rows:
        counts[r["status"].rstrip("?")] = counts.get(r["status"].rstrip("?"), 0) + 1
    summary = " · ".join(
        f"{s}: {counts[s]}" for s in STATUS_ORDER if s in counts
    ) or "no features"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Surface stringified-id collisions instead of rendering silent twins.
    seen = {}
    for r in rows:
        seen[r["id"]] = seen.get(r["id"], 0) + 1
    for r in rows:
        if seen[r["id"]] > 1:
            r["note"] = ("; ".join(filter(None, [r["note"], "duplicate id"])))

    head = f"_Generated {stamp}_ · **{summary}**"
    if degraded_label:
        head = f"_Generated {stamp}_ · **{degraded_label}** · {summary}"

    lines = [
        "<!-- GENERATED by core-engineering status-board.py — DO NOT EDIT.",
        "     A projection over the plan's on-disk artifacts (disk wins);",
        "     parked/failed overlay from auto-build state.json when present.",
        f"     Regenerate: python3 .../ce-auto-build/scripts/status-board.py {plan_dir.name} --write -->",
        "",
        f"# Status board — {plan_dir.name}",
        "",
        head,
        "",
        "| # | Feature | Status | Tasks | Verified | High findings (c/s) | Note |",
        "|---|---------|--------|-------|----------|---------------------|------|",
    ]
    for r in rows:
        order = r["ship_order"] if r["ship_order"] is not None else "—"
        lines.append(
            f"| {order} | `{r['id']}` {r['title']} | **{r['status']}** "
            f"| {r['tasks']} | {r['verified']} | {r['review_high']} | {r['note']} |"
        )
    lines += [
        "",
        "Legend: queued → specced → implementing → implemented → reviewed; "
        "gate-blocked = confirmed-high review finding; parked/failed come from "
        "the auto-build state cache and resolve at the end-review; invalid-id / "
        "`gate-blocked?` flag a degraded read (see Note).",
        "",
        next_action(rows, plan_dir.name),
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Regenerate a plan's STATUS.md board")
    ap.add_argument("plan_dir", help="docs/plans/<slug> directory")
    ap.add_argument("--write", action="store_true",
                    help="write <plan-dir>/STATUS.md instead of stdout")
    args = ap.parse_args(argv)

    plan_dir = Path(args.plan_dir)
    plan = load_json(plan_dir / "plan.json")
    if isinstance(plan, dict) and isinstance(plan.get("features"), list):
        overlay = latest_state_overlay(plan_dir)
        rows = [derive(plan_dir, f, overlay) for f in plan["features"]
                if isinstance(f, dict)]
        rows.sort(key=sort_key)
        board = render(plan_dir, rows)
    elif (plan_dir / "specs").is_dir() or (plan_dir / "feature-plan.md").is_file():
        # Light plan: no usable plan.json, but there IS a plan on disk —
        # serve the returning user a reduced board instead of a hard fail.
        label = DEGRADED_LABEL if not (plan_dir / "plan.json").is_file() else \
            "degraded (unreadable plan.json — states only, no ship order)"
        board = render(plan_dir, derive_degraded(plan_dir), degraded_label=label)
    else:
        print(f"status-board: {plan_dir / 'plan.json'} missing or malformed "
              f"(need a plan.json object with a features[] array), and no "
              f"specs/ dir or feature-plan.md to degrade to", file=sys.stderr)
        return 1

    if args.write:
        (plan_dir / "STATUS.md").write_text(board, encoding="utf-8")
        print(f"status-board: wrote {plan_dir / 'STATUS.md'} "
              f"({len(rows)} feature(s))")
    else:
        print(board)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — could-not-run must exit 2, never 1
        print(f"status-board: unexpected error: {type(e).__name__}: {e}",
              file=sys.stderr)
        sys.exit(2)
