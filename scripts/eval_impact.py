#!/usr/bin/env python3
"""Map a PR diff to the eval scenarios it could invalidate, and judge freshness.

This is the engine for change-coupled eval gating: "skill X's prose changed" ⇒
"skill X's eval must have a fresh live pass". It reads the same catalog the rest
of the eval system reads (evals/scenarios.json), the fork registry
(plugins/core-engineering/fork-manifest.json), and the coverage-waiver list
(evals/coverage-allowlist.json). Stdlib only; the sole external dependency is a
git subprocess (skipped in --files mode until --check needs commit dates).

Input (exactly one):
    --base <ref>   diff HEAD against <ref> (three-dot: what this branch adds)
    --files A B …  an explicit changed-file list (deterministic, for tests/CI)

Mapping rules (a changed path affects …):
    plugins/<plugin>/skills/<s>/**      → every scenario whose "skill" == <s>
    a fork canonical OR any fork copy   → the scenarios of EVERY consumer skill
                                          (each fork path segment under skills/)
    evals/fixtures/<f>/**               → every scenario whose "fixture" == <f>
    evals/scenarios.json,               → every scenario (the graders/catalog:
    scripts/eval_run.py,                  a change here can re-grade anything)
    scripts/eval_check.py

Output (JSON on stdout):
    {"changed": [...], "affected_scenarios": [...],
     "touched_waived_skills": [...], "stale": [...]}

With --check, each affected scenario is resolved against the committed
evals/results/*.json live passes (the same receipt product_layer_check demands:
dry_run:false, status:pass, returncode:0, run_id). A scenario is STALE when it
has no committed live pass, or when its newest live pass predates the change
(neither dated no-earlier-than the change's commit, nor run against a commit
that already contains the change). Any stale scenario → exit 1 with remediation.
Waived skills that own no scenario are reported, never blocking (the burn-down's
job, not this gate's).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# A change to any of these re-grades or re-runs everything downstream.
CATCHALL_PATHS = {
    "evals/scenarios.json",
    "scripts/eval_run.py",
    "scripts/eval_check.py",
}
SKILL_PATH_RE = re.compile(r"^plugins/[^/]+/skills/([^/]+)/")
FIXTURE_PATH_RE = re.compile(r"^evals/fixtures/([^/]+)/")
RUN_ID_RE = re.compile(r"^(\d{8}-\d{6})Z$")
REMEDIATION = (
    "dispatch eval-live on this branch, distill the summary into "
    "evals/results/, commit it in this PR"
)


# ---------------------------------------------------------------------------
# Loading the corpus
# ---------------------------------------------------------------------------
def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{path} is missing") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc


def load_scenarios(root: Path) -> list[dict]:
    data = _load_json(root / "evals" / "scenarios.json")
    scenarios = data.get("scenarios") if isinstance(data, dict) else None
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("evals/scenarios.json must contain a non-empty scenarios array")
    return [s for s in scenarios if isinstance(s, dict)]


def load_fork_index(root: Path) -> dict[str, set[str]]:
    """path (canonical or copy) → the set of consumer skills sharing that fork.

    Every path in a fork entry maps to the SAME consumer set: the skills derived
    from every path in that entry that lives under a skills/<skill>/ segment. A
    canonical outside skills/ (e.g. scripts/gate_runner.py) contributes no skill
    itself but still resolves to its copies' skills.
    """
    path = root / "plugins" / "core-engineering" / "fork-manifest.json"
    if not path.is_file():
        return {}
    data = _load_json(path)
    index: dict[str, set[str]] = {}
    for entry in data.get("forks", []) if isinstance(data, dict) else []:
        if not isinstance(entry, dict):
            continue
        paths = [entry.get("canonical")] + list(entry.get("copies", []) or [])
        paths = [p for p in paths if isinstance(p, str) and p]
        consumers = {skill_from_path(p) for p in paths}
        consumers.discard(None)
        for p in paths:
            index.setdefault(p, set()).update(consumers)  # type: ignore[arg-type]
    return index


def load_waived_skills(root: Path) -> set[str]:
    path = root / "evals" / "coverage-allowlist.json"
    if not path.is_file():
        return set()
    data = _load_json(path)
    waivers = data.get("waivers", []) if isinstance(data, dict) else []
    return {
        w["skill"] for w in waivers
        if isinstance(w, dict) and isinstance(w.get("skill"), str)
    }


# ---------------------------------------------------------------------------
# Path → skill / fixture
# ---------------------------------------------------------------------------
def skill_from_path(path: str) -> str | None:
    m = SKILL_PATH_RE.match(path)
    return m.group(1) if m else None


def fixture_from_path(path: str) -> str | None:
    m = FIXTURE_PATH_RE.match(path)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Core mapping
# ---------------------------------------------------------------------------
def analyze_changes(
    changed: list[str], scenarios: list[dict], fork_index: dict[str, set[str]]
) -> tuple[dict[str, set[str]], set[str]]:
    """Return (scenario_id → triggering changed paths, affected skill names)."""
    by_skill: dict[str, list[str]] = defaultdict(list)
    by_fixture: dict[str, list[str]] = defaultdict(list)
    all_ids: list[str] = []
    for s in scenarios:
        sid = s.get("id")
        if not sid:
            continue
        all_ids.append(sid)
        if s.get("skill"):
            by_skill[s["skill"]].append(sid)
        if s.get("fixture"):
            by_fixture[s["fixture"]].append(sid)

    scenario_triggers: dict[str, set[str]] = defaultdict(set)
    affected_skills: set[str] = set()

    for p in changed:
        skills: set[str] = set()
        direct = skill_from_path(p)
        if direct:
            skills.add(direct)
        skills |= fork_index.get(p, set())
        for sk in skills:
            affected_skills.add(sk)
            for sid in by_skill.get(sk, []):
                scenario_triggers[sid].add(p)

        fx = fixture_from_path(p)
        if fx:
            for sid in by_fixture.get(fx, []):
                scenario_triggers[sid].add(p)

        if p in CATCHALL_PATHS:
            for sid in all_ids:
                scenario_triggers[sid].add(p)

    return scenario_triggers, affected_skills


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------
def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"git {' '.join(args)} failed to launch: {exc}") from exc
    if check and proc.returncode != 0:
        raise ValueError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def git_changed_files(root: Path, base: str) -> list[str]:
    """Files this branch adds vs base (three-dot: diff against the merge-base)."""
    proc = _git(root, "diff", "--name-only", f"{base}...HEAD")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def git_change_info(root: Path, paths: list[str]) -> tuple[str | None, datetime | None]:
    """(commit sha, committer date) of the newest commit touching any path."""
    if not paths:
        return None, None
    proc = _git(root, "log", "-1", "--format=%H%x00%cI", "--", *sorted(paths), check=False)
    out = proc.stdout.strip()
    if proc.returncode != 0 or not out:
        return None, None
    sha, _, iso = out.partition("\x00")
    return (sha or None), parse_iso(iso)


def git_is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    proc = _git(root, "merge-base", "--is-ancestor", ancestor, descendant, check=False)
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# Freshness
# ---------------------------------------------------------------------------
def parse_run_id(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    m = RUN_ID_RE.match(value.strip())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip().replace("Z", "+00:00")
    dt = None
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        try:
            dt = datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_result_passes(root: Path) -> dict[str, list[dict]]:
    """scenario id → committed live-pass candidates (date + git_head anchor).

    Mirrors product_layer_check.check_live_eval_provenance: a candidate must
    carry status:pass, returncode:0, and a run_id, inside a non-dry summary.
    """
    passes: dict[str, list[dict]] = defaultdict(list)
    results_dir = root / "evals" / "results"
    if not results_dir.is_dir():
        return passes
    for summary in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(summary.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or data.get("dry_run") is not False:
            continue
        top_run_id = data.get("run_id")
        top_git_head = data.get("git_head")
        top_curated = data.get("curated")
        for sc in data.get("scenarios", []):
            if not (isinstance(sc, dict)
                    and sc.get("status") == "pass"
                    and sc.get("returncode") == 0
                    and sc.get("run_id")):
                continue
            date = (parse_run_id(sc.get("run_id"))
                    or parse_run_id(top_run_id)
                    or parse_iso(top_curated))
            git_head = sc.get("git_head") or top_git_head
            passes[sc["id"]].append({
                "date": date,
                "git_head": git_head if isinstance(git_head, str) and git_head else None,
                "source": summary.name,
            })
    return passes


def freshness_for(
    root: Path, triggers: set[str], candidates: list[dict]
) -> dict | None:
    """None if fresh; else a stale record {reason, change_date, result_date}."""
    if not candidates:
        return {"reason": "no committed live pass", "change_date": None, "result_date": None}

    change_commit, change_date = git_change_info(root, list(triggers))

    # git_head anchor: a pass run against a commit that already contains the
    # change is fresh regardless of wall-clock date.
    if change_commit:
        for c in candidates:
            if c["git_head"] and git_is_ancestor(root, change_commit, c["git_head"]):
                return None

    if change_date is None:
        # The change has no resolvable commit history; a live pass exists and we
        # cannot prove it stale — do not block.
        return None

    dated = [c["date"] for c in candidates if c["date"] is not None]
    if not dated:
        # A pass exists but carries no parseable date and no matching git_head —
        # lenient: cannot prove staleness.
        return None
    newest = max(dated)
    if newest >= change_date:
        return None
    return {
        "reason": "live pass predates the change",
        "change_date": change_date.isoformat(),
        "result_date": newest.isoformat(),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Map a diff to affected eval scenarios and judge freshness.")
    parser.add_argument("--root", default=str(ROOT), help="repository root")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--base", help="diff HEAD against this ref (three-dot)")
    source.add_argument("--files", nargs="+", help="explicit changed-file list")
    parser.add_argument("--check", action="store_true",
                        help="resolve freshness of affected scenarios; exit 1 on any stale")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        scenarios = load_scenarios(root)
        fork_index = load_fork_index(root)
        waived = load_waived_skills(root)
        if args.files is not None:
            changed = [p.strip() for p in args.files if p.strip()]
        else:
            changed = git_changed_files(root, args.base)

        scenario_triggers, affected_skills = analyze_changes(changed, scenarios, fork_index)
        sid_to_skill = {s["id"]: s.get("skill") for s in scenarios if s.get("id")}
        skills_with_scenarios = {s["skill"] for s in scenarios if s.get("skill")}

        affected_scenarios = sorted(scenario_triggers)
        touched_waived = sorted(
            sk for sk in affected_skills
            if sk not in skills_with_scenarios and sk in waived
        )

        stale: list[dict] = []
        if args.check:
            passes = load_result_passes(root)
            for sid in affected_scenarios:
                verdict = freshness_for(root, scenario_triggers[sid], passes.get(sid, []))
                if verdict is not None:
                    stale.append({"id": sid, "skill": sid_to_skill.get(sid), **verdict})

        output = {
            "changed": sorted(changed),
            "affected_scenarios": affected_scenarios,
            "touched_waived_skills": touched_waived,
            "stale": stale,
        }
    except ValueError as exc:
        print(f"eval-impact: ERROR — {exc}", file=sys.stderr)
        return 2

    print(json.dumps(output, indent=2))
    if args.check and stale:
        ids = ", ".join(s["id"] for s in stale)
        print(
            f"eval-impact: {len(stale)} affected scenario(s) lack a fresh live pass "
            f"({ids}). Remediation: {REMEDIATION}.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
