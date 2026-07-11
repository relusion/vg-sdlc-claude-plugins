#!/usr/bin/env python3
"""Preflight git-worktree parallelism for /ce-auto-build.

This script is conservative by design. It proves only what can be derived from
the local repo and the plan's own artifacts. If MODIFY reach data is absent or
ambiguous, it keeps features sequential rather than treating a hard-dependency
antichain as enough for safe parallelism.

WHERE REACH COMES FROM, and why the order matters:

  1. an explicit reach key on the plan.json feature (`modify_reach` / `modifies` /
     `modify_paths` / `touched_paths`) — a hand- or tool-authored override; or
  2. the union of `files[]` across `specs/<id>/tasks.json` — the closest thing to
     path-level truth the pipeline produces, and available only AFTER /ce-spec has
     run for that feature; else
  3. None -> the pair stays sequential.

Consequence, stated plainly: `/ce-plan` writes no reach key, so before specs exist
reach is genuinely underivable and grouping degrades to singletons. That is CORRECT,
not a bug — a plan-time guess at which files a feature will touch is not proof, and
this script's contract is to prove. Post-spec (a human dividing work, or any caller
that specs before it groups) real path-level groups become derivable.

Reach is a floor, never a safety proof: a task that edits a file its `files[]` never
declared can still collide. The mechanical backstop is worktree-merge.py, which
aborts on conflict and never resolves.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(root: Path, *args: str) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


def feature_id(feature: dict) -> str:
    return str(feature.get("id") or feature.get("feature_id") or "")


def hard_deps(feature: dict) -> set[str]:
    deps: set[str] = set()
    raw = feature.get("depends_on")
    if isinstance(raw, list):
        deps.update(str(item) for item in raw if isinstance(item, (str, int)))
    dependencies = feature.get("dependencies")
    if isinstance(dependencies, dict):
        hard = dependencies.get("hard")
        if isinstance(hard, list):
            for item in hard:
                if isinstance(item, dict) and item.get("id"):
                    deps.add(str(item["id"]))
                elif isinstance(item, (str, int)):
                    deps.add(str(item))
    return deps


def modify_reach(feature: dict) -> set[str] | None:
    """An explicit reach key on the plan.json feature, if any."""
    for key in ("modify_reach", "modifies", "modify_paths", "touched_paths"):
        raw = feature.get(key)
        if isinstance(raw, list):
            values = {str(item) for item in raw if isinstance(item, (str, int)) and str(item)}
            return values
    return None


def safe_feature_dir(specs_root: Path, fid: str) -> Path | None:
    """Resolve specs/<fid>/ without letting a crafted id escape the specs tree."""
    if not fid or fid in (".", "..") or "/" in fid or "\\" in fid:
        return None
    candidate = (specs_root / fid).resolve()
    try:
        candidate.relative_to(specs_root.resolve())
    except ValueError:
        return None
    return candidate


def tasks_reach(specs_root: Path | None, fid: str) -> set[str] | None:
    """Union of `files[]` across specs/<fid>/tasks.json — path-level truth, and the
    only place it exists. Returns None when no spec has been written for the
    feature, or when its tasks declare no files at all (an empty set would falsely
    read as 'touches nothing', which would make everything look independent)."""
    if specs_root is None:
        return None
    feature_dir = safe_feature_dir(specs_root, fid)
    if feature_dir is None:
        return None
    tasks_path = feature_dir / "tasks.json"
    if not tasks_path.is_file():
        return None
    try:
        data = json.loads(tasks_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list):
        return None
    files: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            continue
        raw = task.get("files")
        if isinstance(raw, list):
            files.update(str(item) for item in raw
                         if isinstance(item, (str, int)) and str(item))
    return files or None


def resolve_reach(features: list[dict], specs_root: Path | None) -> tuple[dict, dict]:
    """(reach, sources) per feature id. plan.json key wins; else tasks.json; else None."""
    reach: dict[str, set[str] | None] = {}
    sources: dict[str, str] = {}
    for feature in features:
        fid = feature_id(feature)
        if not fid:
            continue
        explicit = modify_reach(feature)
        if explicit is not None:
            reach[fid], sources[fid] = explicit, "plan.json"
            continue
        derived = tasks_reach(specs_root, fid)
        if derived is not None:
            reach[fid], sources[fid] = derived, "tasks.json"
            continue
        reach[fid], sources[fid] = None, "none"
    return reach, sources


def transitive_deps(features: list[dict]) -> dict[str, set[str]]:
    direct = {feature_id(f): hard_deps(f) for f in features}
    resolved: dict[str, set[str]] = {}

    def walk(fid: str, seen: set[str]) -> set[str]:
        if fid in resolved:
            return set(resolved[fid])
        out: set[str] = set()
        for dep in direct.get(fid, set()):
            if dep in seen:
                continue
            out.add(dep)
            out.update(walk(dep, seen | {dep}))
        resolved[fid] = set(out)
        return out

    for fid in direct:
        walk(fid, {fid})
    return resolved


def independent(a: dict, b: dict, deps: dict[str, set[str]],
                reach: dict) -> tuple[bool, str]:
    aid, bid = feature_id(a), feature_id(b)
    if not aid or not bid:
        return False, "feature missing id"
    if bid in deps.get(aid, set()) or aid in deps.get(bid, set()):
        return False, "hard-dependency path"
    amod = reach.get(aid)
    bmod = reach.get(bid)
    if amod is None or bmod is None:
        return False, "missing MODIFY reach"
    overlap = sorted(amod & bmod)
    if overlap:
        return False, f"MODIFY overlap: {', '.join(overlap[:5])}"
    return True, "independent"


def compute_groups(features: list[dict],
                   specs_root: Path | None = None) -> tuple[list[list[str]], list[str], dict]:
    ordered = sorted(features, key=lambda f: (int(f.get("ship_order", 9999)), feature_id(f)))
    deps = transitive_deps(ordered)
    reach, sources = resolve_reach(ordered, specs_root)
    groups: list[list[dict]] = []
    warnings: list[str] = []

    for feature in ordered:
        placed = False
        for group in groups:
            decisions = [independent(feature, other, deps, reach) for other in group]
            if all(ok for ok, _reason in decisions):
                group.append(feature)
                placed = True
                break
        if not placed:
            groups.append([feature])
            fid = feature_id(feature)
            if reach.get(fid) is None:
                warnings.append(
                    f"{fid} lacks MODIFY reach (no plan.json reach key and no "
                    f"specs/{fid}/tasks.json files[]); kept conservative"
                )

    grouped = [[feature_id(f) for f in group if feature_id(f)] for group in groups]
    return grouped, warnings, sources


def load_plan(path: Path) -> tuple[list[dict], list[str]]:
    if not path.is_file():
        return [], [f"plan not found: {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [], [f"cannot read plan: {exc}"]
    features = data.get("features")
    if not isinstance(features, list):
        return [], ["plan.json has no features array"]
    usable = [item for item in features if isinstance(item, dict)]
    if len(usable) != len(features):
        return usable, ["plan.json contains non-object feature entries"]
    return usable, []


def git_preflight(root: Path, skip_git: bool) -> tuple[dict, list[str], list[str]]:
    if skip_git:
        return {"skipped": True}, [], []
    errors: list[str] = []
    warnings: list[str] = []
    code, top, err = run(root, "rev-parse", "--show-toplevel")
    inside = code == 0 and bool(top)
    code_wt, out_wt, err_wt = run(root, "worktree", "list", "--porcelain")
    code_status, status, _err_status = run(root, "status", "--porcelain")
    if not inside:
        errors.append("not inside a git work tree")
    if code_wt != 0:
        errors.append(f"git worktree unsupported or unavailable: {err_wt or out_wt}")
    if code_status == 0 and status:
        warnings.append("working tree is dirty; auto-build clean-tree gate must consent or clean first")
    return {
        "skipped": False,
        "inside_work_tree": inside,
        "top_level": top or None,
        "worktree_supported": code_wt == 0,
        "dirty": bool(status) if code_status == 0 else None,
    }, errors, warnings


def build_result(root: Path, plan: Path | None, skip_git: bool) -> dict:
    git, errors, warnings = git_preflight(root, skip_git)
    features: list[dict] = []
    groups: list[list[str]] = []
    reach_sources: dict = {}
    if plan:
        features, plan_errors = load_plan(plan)
        errors.extend(plan_errors)
        if features:
            # specs/ sits beside plan.json; absent before /ce-spec has run.
            specs_root = plan.parent / "specs"
            groups, group_warnings, reach_sources = compute_groups(
                features, specs_root if specs_root.is_dir() else None)
            warnings.extend(group_warnings)

    if errors:
        status = "blocked"
    elif warnings:
        status = "degraded"
    else:
        status = "pass"

    if groups and all(len(group) == 1 for group in groups):
        warnings.append("no safe parallel group found; run sequentially")
        if status == "pass":
            status = "degraded"

    return {
        "schema_version": 1,
        "status": status,
        "git": git,
        "plan": str(plan) if plan else None,
        "feature_count": len(features),
        "parallel_groups": groups,
        "reach_sources": reach_sources,
        "errors": errors,
        "warnings": warnings,
        "honest_limitations": [
            "Runtime isolation for ports, databases, and ephemeral services is not machine-proven here.",
            "Missing MODIFY reach forces conservative sequential grouping.",
            "MODIFY reach is read from a plan.json reach key when present, else from "
            "the union of specs/<id>/tasks.json files[] — which exists only after "
            "/ce-spec has run. Before specs exist reach is underivable and every "
            "feature is its own group; reach_sources says which source each feature used.",
            "Reach is a floor, not a safety proof: a task that edits a file its "
            "files[] never declared can still collide. worktree-merge.py's "
            "conflict-abort is the mechanical backstop, not this preflight.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight /ce-auto-build worktree mode")
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--plan", help="path to docs/plans/<slug>/plan.json")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument("--skip-git", action="store_true", help="skip git capability checks")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    plan = (root / args.plan).resolve() if args.plan and not Path(args.plan).is_absolute() else (
        Path(args.plan).resolve() if args.plan else None
    )
    result = build_result(root, plan, args.skip_git)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    sys.exit(main())
