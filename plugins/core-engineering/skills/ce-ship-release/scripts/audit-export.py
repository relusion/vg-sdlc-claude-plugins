#!/usr/bin/env python3
"""
audit-export.py — compile a plan's pipeline evidence into one structured JSON.

Deterministic evidence COMPILATION, not a compliance attestation and not a
verdict: it gathers what the pipeline already recorded — plan.json, per-feature
spec/tasks/verification/review artifacts, the .metrics.jsonl stream, run
reports, the patch lane's eligibility.json — into a single machine-readable
audit document a reviewer or an external compliance process can consume.

Read-only over every source. Writes nothing unless --out is given, and --out
is REFUSED (exit 1) if it would overwrite any source it reads — the generated
artifact must never destroy a source of truth. The dated convention
docs/plans/<slug>/audit-export/<date>-audit-export.json keeps exports
never-overwritten.

Every absence is reported honestly (present: false / gaps[]), never silently
zeroed. Unparseable metrics lines are counted and reported, never skipped
silently.

Usage:
    python3 audit-export.py <plan-dir>              # JSON to stdout
    python3 audit-export.py <plan-dir> --out FILE   # write FILE
    python3 audit-export.py <plan-dir> --since YYYY-MM-DD [--until YYYY-MM-DD]

Windowing (`--since` / `--until`) filters ONLY the `metrics` block — the one thing
derived from the dated event stream. Every other block is current on-disk state with
no timestamp and stays as-of-now; the `windowing` manifest names both sets so a
narrator cannot present a static number as windowed. Bounds are inclusive and
day-granular (the stream's `ts` has no time component). An undated line is excluded
from the window, COUNTED under `window.stream_lines.undated`, and reported in
`gaps[]` — never dropped silently. Without a window, `ts` is never read and the
output is byte-identical to the unwindowed export.

Exit codes:
    0  export produced
    1  plan dir invalid (no plan.json and no specs/), or --out would clobber a source
    2  unexpected internal error, or a malformed/inverted --since/--until (usage)

Stdlib-only by design (the portability guarantee): no Claude Code, no network.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

# --- windowing (--since / --until) -------------------------------------------
#
# ONLY the `metrics` block is derived from the dated event stream, so only it can
# be honestly filtered. Every other block is current on-disk state with no
# timestamp; presenting one as windowed would be a fabrication. The export says so
# machine-readably (the `windowing` manifest) so a narrator cannot claim otherwise.
WINDOWED_BLOCKS = ("metrics",)
AS_OF_NOW_BLOCKS = (
    "plan", "features", "testability", "evidence", "complexity_drift",
    "run_reports", "plan_artifacts", "diagnosis_present", "decisions_ledger",
    "patch_lane",
)
WINDOWING_NOTE = (
    "Only the blocks in windowed_blocks reflect --since/--until. Every block in "
    "as_of_now_blocks is current on-disk state at generated_at and is NOT filtered "
    "— narrating one as windowed is a fabrication."
)
WINDOW_LIMITATIONS = (
    "Day granularity: --since/--until are INCLUSIVE date bounds compared as "
    "YYYY-MM-DD. The stream's ts carries no time, so same-day events are unordered, "
    "a sprint boundary falling mid-day is unrepresentable, and two adjacent windows "
    "that share an endpoint both count that day's events.",
    "complexity_drift.retries is FULL-STREAM even here: it joins a lifetime "
    "task_count against a retry count, so a windowed retry tally would make drift "
    "shrink as the window narrows — a misleading number, not a sharper one.",
)

# A TC test-case heading in ce-spec.md carries its verification tag on the same
# structured line, e.g.
#   ### TC-1  (proves AC-1) — modality: http · verification: auto
# This matches that one structured line only — never free-form prose — so the
# testability signal is derived, not guessed. (ce-spec.md is not in the
# "referenced by presence, not parsed" set; verification.md/code-review.md are.)
TC_VERIFICATION_RE = re.compile(
    r"^#{1,6}\s+TC\b.*\bverification:\s*"
    r"(auto|manual:harness-gap|manual:judgment)\b",
    re.IGNORECASE,
)
_TESTABILITY_KEY = {
    "auto": "auto",
    "manual:harness-gap": "harness_gap",
    "manual:judgment": "judgment",
}

HONEST_LIMITATIONS = [
    "Evidence compilation, not a compliance attestation: this export proves what "
    "artifacts exist and what the pipeline recorded — a human or external process "
    "renders any compliance judgment.",
    "Markdown artifacts (verification.md, code-review.md, diagnosis.md, the "
    "decisions ledger in shared-context.md) are referenced by presence, not "
    "parsed: their content is free-form and is not re-judged here.",
    "Completeness equals pipeline completeness: metrics emission is best-effort "
    "and never gates a run, so a crashed or interactive-only run is under-counted "
    "(reported as gaps, never silently).",
    "Token figures in the metrics stream are producer-labeled estimates, never "
    "billing-grade.",
    "Testability counts read only the structured TC verification: tag in "
    "ce-spec.md (a single machine-readable line), not the free-form case body; "
    "complexity_drift joins the planned final_complexity against built signals "
    "(task count + retries) descriptively — it is a number to interpret, never a "
    "verdict that a feature was mis-planned.",
    "The evidence axis (stamped/fresh/stale/unstamped) verdicts each done task's "
    "recorded commit_sha against HEAD's ancestry via git: fresh = the proving "
    "commit is in this checkout's history, stale = it is not (reverted / rebased "
    "away), unstamped = no stamp or no commit or no git here. It is commit-ancestry "
    "only — the transient test_run_digest marker is not re-read at audit time — and "
    "degrades to all-unstamped when git is unavailable, never a false stale.",
]


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None


def safe_spec_dir(plan_dir: Path, fid: str):
    """specs/<fid> only if it stays inside plan_dir/specs; else None (no traversal)."""
    if not fid or fid in (".", "..") or "/" in fid or "\\" in fid or ".." in fid:
        return None
    specs = plan_dir / "specs"
    cand = specs / fid
    try:
        cand_r, specs_r = cand.resolve(), specs.resolve()
    except OSError:
        return None
    if cand_r == specs_r or specs_r not in cand_r.parents:
        return None
    return cand


# --- freshness axis (WS3-T4): audit-layer read of tasks.json evidence stamps ------
# git shell-outs, each guarded — a missing git binary or a non-repo plan_dir must
# degrade to "unverifiable" (unstamped bucket), never crash or fabricate a stale.

def _git_toplevel(start: Path):
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _head_sha(repo):
    if repo is None:
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
            capture_output=True, text=True)
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


def _is_ancestor(repo, sha) -> bool:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", sha, "HEAD"],
            capture_output=True, text=True)
        return out.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def task_evidence_counts(tasks, repo, head) -> dict:
    """Per-feature evidence rollup (WS3-T4). `stamped`/`unstamped` is one axis (did
    the done task carry a WS3-T3 evidence stamp); `fresh`/`stale` is the freshness of
    a stamped-and-committed task's commit_sha vs HEAD. Each done task lands in exactly
    one of fresh/stale/unstamped (they partition `done`); `stamped` is the overlapping
    count of done tasks that went through the stamp at all."""
    ev = {"stamped": 0, "fresh": 0, "stale": 0, "unstamped": 0}
    for t in (tasks or []):
        if not isinstance(t, dict) or t.get("status") != "done":
            continue
        stamped = "completed_at" in t
        if stamped:
            ev["stamped"] += 1
        commit = t.get("commit_sha")
        if not stamped or not commit:
            ev["unstamped"] += 1          # legacy, or stamped-but-uncommitted
        elif repo is None or head is None:
            ev["unstamped"] += 1          # committed but no git here to verify
        elif _is_ancestor(repo, commit):
            ev["fresh"] += 1              # proving commit is in HEAD's history
        else:
            ev["stale"] += 1             # commit not in HEAD's ancestry — downgrade
    return ev


def spec_testability(spec_dir: Path) -> dict:
    """Count TC verification tags in the feature's spec markdown.

    Reads the structured TC heading line (never free-form prose) and tallies
    auto / manual:harness-gap / manual:judgment. ce-spec.md is the canonical
    spec name; legacy spec.md is accepted. A spec with no parseable TC line
    yields all-zero (honest "no data"), never a fabricated count.
    """
    out = {"total": 0, "auto": 0, "harness_gap": 0, "judgment": 0}
    spec_file = None
    for name in ("ce-spec.md", "spec.md"):
        cand = spec_dir / name
        if cand.is_file():
            spec_file = cand
            break
    if spec_file is None:
        return out
    try:
        text = spec_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        m = TC_VERIFICATION_RE.match(line.strip())
        if not m:
            continue
        out["total"] += 1
        out[_TESTABILITY_KEY[m.group(1).lower()]] += 1
    return out


def feature_evidence(plan_dir: Path, feature: dict, gaps: list,
                     repo=None, head=None) -> dict:
    fid = str(feature.get("id", ""))
    out = {
        "id": fid,
        "title": str(feature.get("title", "")),
        "ship_order": feature.get("ship_order"),
        "final_complexity": feature.get("final_complexity"),
        "spec_present": False,
        "tasks": {"present": False, "total": 0, "done": 0},
        "verification_present": False,
        "review": {"present": False},
        "diagnosis_present": False,
        "testability": {"total": 0, "auto": 0, "harness_gap": 0, "judgment": 0},
        "evidence": {"stamped": 0, "fresh": 0, "stale": 0, "unstamped": 0},
    }

    spec_dir = safe_spec_dir(plan_dir, fid)
    if spec_dir is None:
        out["invalid_id"] = True
        gaps.append(f"{fid!r}: unsafe/empty feature id — artifacts not read")
        return out

    tasks_obj = load_json(spec_dir / "tasks.json")
    tasks = tasks_obj.get("tasks") if isinstance(tasks_obj, dict) else None
    if isinstance(tasks_obj, dict) and not isinstance(tasks, list):
        gaps.append(f"{fid}: tasks.json present but 'tasks' is not a list")
    total = len(tasks) if isinstance(tasks, list) else 0
    done = sum(1 for t in (tasks or [])
               if isinstance(t, dict) and t.get("status") == "done")
    verification = (spec_dir / "verification.md").is_file()
    review_path = spec_dir / "review-summary.json"
    review = load_json(review_path)

    out.update({
        # ce-spec.md is the canonical spec artifact name; legacy spec.md accepted.
        "spec_present": ((spec_dir / "ce-spec.md").is_file()
                         or (spec_dir / "spec.md").is_file()),
        "tasks": {"present": tasks_obj is not None, "total": total, "done": done},
        "verification_present": verification,
        "review": {"present": isinstance(review, dict)},
        "diagnosis_present": (spec_dir / "diagnosis.md").is_file(),
        "testability": spec_testability(spec_dir),
        "evidence": task_evidence_counts(tasks, repo, head),
    })
    if out["evidence"]["stale"]:
        gaps.append(f"{fid}: {out['evidence']['stale']} done task(s) STALE — recorded "
                    f"done but the proving commit_sha is not in HEAD's ancestry "
                    f"(reverted / rebased away); done-ness downgraded")
    if isinstance(review, dict):
        for key in ("blocking_high", "findings_total", "suppressed", "by_severity"):
            if key in review:
                out["review"][key] = review[key]
    elif review_path.is_file():
        out["review"]["unreadable"] = True
        gaps.append(f"{fid}: review-summary.json present but unreadable")

    if out["spec_present"] and total and done == total and not verification:
        gaps.append(f"{fid}: all {total} tasks done but no verification.md")
    if verification and not isinstance(review, dict) and not review_path.is_file():
        gaps.append(f"{fid}: verified but no review-summary.json (review gate "
                    f"off, or interactive run — see Honest Limitations)")
    return out


ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iso_date(raw):
    """A metrics `ts` -> date, or None when it is absent/unparseable.

    The stream's canonical ts is DATE-ONLY (`YYYY-MM-DD`). A ts that carries an
    accidental time component is truncated to its date; anything else is undated
    and is COUNTED, never silently dropped (the lines_unparseable precedent).
    """
    if not isinstance(raw, str):
        return None
    head = raw[:10]
    if not ISO_DATE_RE.match(head):
        return None
    try:
        return date.fromisoformat(head)
    except ValueError:
        return None


def in_window(ev_date, since, until) -> bool:
    """Inclusive on both bounds. Day granularity — see WINDOW_LIMITATIONS."""
    if since is not None and ev_date < since:
        return False
    if until is not None and ev_date > until:
        return False
    return True


def metrics_summary(plan_dir: Path, since=None, until=None) -> dict:
    """Tally the stream. With a window, only lines whose `ts` falls inside it are
    counted; undated lines are excluded but counted under `window_lines.undated`.

    Without a window (since=until=None) `ts` is never read and the output is
    byte-identical to the unwindowed export — the backward-compatibility contract.
    """
    windowed = since is not None or until is not None
    path = plan_dir / ".metrics.jsonl"
    out = {
        "present": path.is_file(),
        "lines_total": 0,
        "lines_unparseable": 0,
        "events_by_type": {},
        "gates": {"pass": 0, "fail": 0},
        "escalations": [],
        "parks": 0,
        "retries": 0,
        "retries_by_feature": {},
        "circuit_breaks": 0,
        "attestations": {
            "confirms": 0,
            "overrides": 0,
            "edits": 0,
            "loops": 0,
            "by_gate": {},
        },
    }
    if windowed:
        out["windowed"] = True
        out["window_lines"] = {"in_window": 0, "out_of_window": 0, "undated": 0}
    if not out["present"]:
        return out
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        out["present"] = False
        return out
    for line in raw_lines:
        if not line.strip():
            continue
        out["lines_total"] += 1
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            out["lines_unparseable"] += 1
            continue
        if not isinstance(ev, dict):
            out["lines_unparseable"] += 1
            continue
        if windowed:
            ev_date = parse_iso_date(ev.get("ts"))
            if ev_date is None:
                out["window_lines"]["undated"] += 1
                continue  # counted, never silently dropped
            if not in_window(ev_date, since, until):
                out["window_lines"]["out_of_window"] += 1
                continue
            out["window_lines"]["in_window"] += 1
        etype = str(ev.get("event", "unknown"))
        out["events_by_type"][etype] = out["events_by_type"].get(etype, 0) + 1
        if etype == "gate" and ev.get("gate") in ("pass", "fail"):
            out["gates"][ev["gate"]] += 1
        elif etype == "escalation":
            out["escalations"].append({
                "feature": ev.get("feature"),
                "stage": ev.get("stage"),
                "escalation_type": ev.get("escalation_type"),
                "detail": ev.get("detail"),
            })
        elif etype == "park":
            out["parks"] += 1
        elif etype == "retry":
            out["retries"] += 1
            fkey = ev.get("feature")
            if fkey is not None:
                fkey = str(fkey)
                out["retries_by_feature"][fkey] = (
                    out["retries_by_feature"].get(fkey, 0) + 1)
        elif etype == "circuit-break":
            out["circuit_breaks"] += 1
        elif etype == "attestation":
            # One HITL-gate decision per line: gate holds the gate NAME here
            # (not pass/fail), and gate_index is the R5 "Gate N of M" locator.
            att = out["attestations"]
            gate_name = str(ev.get("gate") or "unknown")
            per = att["by_gate"].setdefault(
                gate_name, {"confirm": 0, "override": 0, "edit": 0, "loop": 0})
            action = ev.get("action")
            top = {"confirm": "confirms", "override": "overrides",
                   "edit": "edits", "loop": "loops"}.get(action)
            if top:
                att[top] += 1
                per[action] += 1
            # An unrecognized action still surfaces its gate (by_gate entry
            # created above) but moves no typed counter — never silently zeroed.
    return out


def discover_eligibility(plan_dir: Path, gaps: list):
    """Find the patch lane's eligibility.json (present by FILE EXISTENCE).

    A patch plan has exactly one specs/00-<slug>/; if more than one
    eligibility.json exists that is itself a finding, not a silent first-pick.
    """
    specs = plan_dir / "specs"
    if not specs.is_dir():
        return {"present": False}
    hits = sorted(p for p in specs.glob("*/eligibility.json") if p.is_file())
    if not hits:
        return {"present": False}
    if len(hits) > 1:
        gaps.append(f"multiple eligibility.json files: "
                    f"{', '.join(str(h.relative_to(plan_dir)) for h in hits)}")
    chosen = hits[0]
    parsed = load_json(chosen)
    out = {"present": True, "path": str(chosen.relative_to(plan_dir))}
    if parsed is None:
        out["unreadable"] = True
        gaps.append(f"{out['path']}: present but unparseable")
    else:
        out["eligibility"] = parsed
    return out


def sort_key(rec: dict):
    so = rec.get("ship_order")
    if so is None:
        return (2, 0.0, "", rec["id"])
    if isinstance(so, bool):
        so = int(so)
    if isinstance(so, (int, float)):
        return (0, float(so), "", rec["id"])
    return (1, 0.0, str(so), rec["id"])


def out_would_clobber_source(out_path: Path, plan_dir: Path) -> bool:
    """True if --out resolves onto a source this tool reads.

    Refuses plan.json, .metrics.jsonl, shared-context.md, and anything under
    specs/ — but ALLOWS the dated audit-export/ convention inside plan_dir.
    """
    try:
        out_r = out_path.resolve()
        plan_r = plan_dir.resolve()
    except OSError:
        return False
    protected = {
        (plan_r / "plan.json"),
        (plan_r / ".metrics.jsonl"),
        (plan_r / "shared-context.md"),
    }
    if out_r in protected:
        return True
    specs_r = (plan_r / "specs")
    if specs_r == out_r or specs_r in out_r.parents:
        return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Compile a plan's pipeline evidence into one audit JSON")
    ap.add_argument("plan_dir", help="docs/plans/<slug> directory")
    ap.add_argument("--out", help="write to FILE instead of stdout")
    ap.add_argument("--since", metavar="YYYY-MM-DD",
                    help="window the metrics stream: include events on/after this "
                         "date (inclusive). Static artifact blocks stay as-of-now.")
    ap.add_argument("--until", metavar="YYYY-MM-DD",
                    help="window the metrics stream: include events on/before this "
                         "date (inclusive)")
    args = ap.parse_args(argv)

    since = until = None
    for name in ("since", "until"):
        raw = getattr(args, name)
        if raw is None:
            continue
        parsed = parse_iso_date(raw)
        if parsed is None:
            print(f"audit-export: --{name} must be YYYY-MM-DD (got {raw!r})",
                  file=sys.stderr)
            return 2
        if name == "since":
            since = parsed
        else:
            until = parsed
    if since is not None and until is not None and since > until:
        print(f"audit-export: --since {since} is after --until {until} — "
              f"an empty window is a usage error, not an empty report",
              file=sys.stderr)
        return 2

    plan_dir = Path(args.plan_dir)
    plan = load_json(plan_dir / "plan.json")
    if not isinstance(plan, dict) and not (plan_dir / "specs").is_dir():
        print(f"audit-export: {plan_dir} has no plan.json and no specs/ — "
              f"nothing to export", file=sys.stderr)
        return 1

    if args.out and out_would_clobber_source(Path(args.out), plan_dir):
        print(f"audit-export: refusing --out {args.out} — it would overwrite a "
              f"source artifact this export reads (use the dated "
              f"audit-export/<date>-audit-export.json convention)", file=sys.stderr)
        return 1

    gaps: list = []
    features_src = plan.get("features") if isinstance(plan, dict) else None
    if not isinstance(features_src, list):
        features_src = []
        gaps.append("plan.json missing or malformed — feature list is empty; "
                    "only stream-level evidence exported")

    # Resolve the repo once for the freshness axis (WS3-T4). None when plan_dir is
    # not inside a git checkout or git is absent — freshness degrades to unstamped.
    repo = _git_toplevel(plan_dir)
    head = _head_sha(repo)
    features = [feature_evidence(plan_dir, f, gaps, repo, head)
                for f in features_src if isinstance(f, dict)]
    windowed = since is not None or until is not None
    metrics = metrics_summary(plan_dir, since, until)
    if metrics["lines_unparseable"]:
        gaps.append(f".metrics.jsonl: {metrics['lines_unparseable']} "
                    f"unparseable line(s) (counted, not skipped silently)")
    if windowed and metrics.get("window_lines", {}).get("undated"):
        gaps.append(
            f".metrics.jsonl: {metrics['window_lines']['undated']} line(s) have a "
            f"missing/unparseable ts — excluded from the --since/--until window "
            f"(counted, not skipped silently); the windowed tally under-counts by "
            f"that many lines")

    # complexity_drift joins a LIFETIME task_count against retries, so its retry
    # column must come from the FULL stream even under a window (see
    # WINDOW_LIMITATIONS). Recompute it unwindowed rather than reuse the tally.
    retries_lifetime = (
        metrics_summary(plan_dir)["retries_by_feature"] if windowed
        else metrics["retries_by_feature"])

    # Criteria-testability rate — TC verification tags summed across specs.
    testability = {"total": 0, "auto": 0, "harness_gap": 0, "judgment": 0}
    for f in features:
        t = f.get("testability") or {}
        for k in testability:
            testability[k] += t.get(k, 0)

    # Done-ness freshness (WS3-T4) — stamped/fresh/stale/unstamped summed across
    # features, so a stale count rolls up to the pack's one place to look.
    evidence = {"stamped": 0, "fresh": 0, "stale": 0, "unstamped": 0}
    for f in features:
        fe = f.get("evidence") or {}
        for k in evidence:
            evidence[k] += fe.get(k, 0)

    # Complexity-vs-actual drift — planned final_complexity vs the built
    # signals (task count + retry events), joined per feature. The human reads
    # the drift; the export never labels a feature "over/under-planned".
    complexity_drift = [
        {
            "id": f["id"],
            "final_complexity": f.get("final_complexity"),
            "task_count": f["tasks"]["total"],
            "retries": retries_lifetime.get(f["id"], 0),
        }
        for f in features
    ]

    run_dir = plan_dir / "auto-build"
    export = {
        "schema_version": SCHEMA_VERSION,
        "tool": "core-engineering audit-export",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan_dir": str(plan_dir),
        "plan_slug": plan_dir.name,
        "plan": {
            "present": isinstance(plan, dict),
            "feature_count": len(features),
            "ship_order": [f["id"] for f in sorted(features, key=sort_key)],
        },
        "features": features,
        "testability": testability,
        "evidence": evidence,
        "complexity_drift": complexity_drift,
        "metrics": metrics,
        "run_reports": sorted(p.name for p in run_dir.glob("*-run.md"))
        if run_dir.is_dir() else [],
        "plan_artifacts": {
            "shared_context_present": (plan_dir / "shared-context.md").is_file(),
            "threat_model_present": (plan_dir / "threat-model.md").is_file(),
            "interaction_contract_present": (plan_dir / "interaction-contract.md").is_file(),
            "note": "read-only plan-root re-projections; presence-only, not machine-parsed",
        },
        # Plan-root diagnosis.md is /ce-debug's INTERACTIVE output (cumulative
        # across the plan's features); the per-feature specs/<id>/diagnosis.md
        # (auto-build) is reported per feature above. Both locations covered;
        # presence-only, not machine-parsed.
        "diagnosis_present": (plan_dir / "diagnosis.md").is_file(),
        "decisions_ledger": {
            "shared_context_present": (plan_dir / "shared-context.md").is_file(),
            "note": "free-form markdown (Resolved Project Decisions); "
                    "referenced, not machine-parsed",
        },
        "patch_lane": discover_eligibility(plan_dir, gaps),
        "gaps": gaps,
        "honest_limitations": HONEST_LIMITATIONS,
    }

    # Windowing keys appear ONLY under a window, so the no-flag export stays
    # byte-identical to every prior run (no schema_version bump: purely additive,
    # and window.applied is a stronger, self-describing signal than a version).
    if windowed:
        export["window"] = {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "applied": True,
            "granularity": "day",
            "bounds_inclusive": True,
            "stream_lines": metrics.get("window_lines"),
            "limitations": list(WINDOW_LIMITATIONS),
        }
        export["windowing"] = {
            "windowed_blocks": list(WINDOWED_BLOCKS),
            "as_of_now_blocks": list(AS_OF_NOW_BLOCKS),
            "note": WINDOWING_NOTE,
        }

    text = json.dumps(export, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"audit-export: wrote {out_path}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — could-not-run must exit 2, never 1
        print(f"audit-export: unexpected error: {type(e).__name__}: {e}",
              file=sys.stderr)
        sys.exit(2)
