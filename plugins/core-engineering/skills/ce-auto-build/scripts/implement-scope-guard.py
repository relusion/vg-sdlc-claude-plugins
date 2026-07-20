#!/usr/bin/env python3
"""implement-scope-guard.py — the Scope Lock's file boundary, made mechanical.

`/core-engineering:ce-spec` records each task's declared file set in `tasks.json` (`tasks[].files`);
`/core-engineering:ce-implement` (and the auto-build orchestrator) then implement that spec WITHOUT
widening it (the Scope Lock). This gate makes the file half of that lock checkable:
it FAILS any touched file that lies outside the union of the spec's `tasks[].files`
(plus the sanctioned bookkeeping/promotion writes), the same mechanical scope check
`/core-engineering:ce-patch`'s H9 proves against `frozen_files`. A file the diff touched but no task
named is a **Spec Conflict** — the spec must name every file it changes.

Two modes, one 0/1/2 exit contract:

  * IN-LOOP  `--spec-dir <docs/plans/<slug>/specs/<id>> [--spec-dir <...>]`
    `--base <ref> [--repo .] --json` runs during implementation over the WORKING
    TREE (tracked diff vs `--base` plus untracked new files, the same gather as
    patch-lint). One argument scopes to one feature; repeated arguments union the
    selected specs for a sequential, cumulative working tree.

  * CI       `--all-specs --head-tree <dir> --base <ref> --head <ref> --repo <path> --json`
    is the merge-bar gate. It unions `tasks[].files` across EVERY spec dir found
    under the materialized committed tree `--head-tree` (so the verdict is a pure
    function of the head commit, never the mutable working tree), and diffs the
    two committed refs in `--repo`. `--head-tree` avoids the per-spec-dir fan-out
    the {spec_dir} placeholder would force.

Allowed beyond the task file set (never a Spec Conflict):
  * the plan bookkeeping subtree `docs/plans/<slug>/**` (which holds `specs/<id>/**`
    — spec artifacts, tasks.json stamps, verification.md, .metrics.jsonl);
  * `.test-guard/**` — the transient red-test snapshots + the PASS ledger;
  * `docs/adr/**` — ADR promotion is a sanctioned implement write (record-don't-park).

Posture (matches the prerequisite): **fail-closed when the spec lists files** — a
non-empty task file union is enforced, any stray file FAILS. **Advisory on legacy
specs** — a spec (or, in CI, an entire spec set) that declares NO `tasks[].files`
predates enforcement, so the boundary is not knowable; the gate reports that as an
advisory and PASSES (exit 0) rather than failing every file against an empty set.
spec-lint's H6 enforces file-set CONSISTENCY going forward, so new specs always land
in the fail-closed branch.

LIMITATION (m4, inherited from patch-lint): untracked files are gathered with
`--exclude-standard`, so a write into a `.gitignore`'d path is invisible to the
in-loop diff — a narrow false negative in the dangerous direction. The skill's
manual checklist must cover gitignored writes; this gate cannot.

Exit codes:
    0  PASS  — no file outside the boundary (advisory notes may still print)
    1  FAIL  — >= 1 touched file outside the spec's declared file set (Spec Conflict)
    2  ERROR — inputs missing/unparseable, not a git repo, bad flags; caller applies
               its owning workflow's documented exit-2 disposition (never a pass)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


class ScopeGuardError(Exception):
    """Inputs cannot be loaded / not a git repo -> exit 2, never a pass."""


# --- path + git helpers (self-contained: the fork copy must be byte-identical) ------

def _norm(p: str) -> str:
    # Strip only a literal leading "./" (NOT lstrip("./"), which deletes a
    # character SET and would corrupt dotfile paths like .test-guard/ -> test-guard/).
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise ScopeGuardError(
            f"git {' '.join(args[:2])} failed in {repo}: "
            f"{out.stderr.strip() or 'unknown error'}")
    return out.stdout


def _git_toplevel(start: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        if out.returncode == 0:
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return None


# --- tasks.json file-set loading ----------------------------------------------------

def load_task_files(tasks_path: Path) -> set[str]:
    """Return the normalized union of `tasks[].files` from one tasks.json.
    A malformed tasks.json is an ERROR (exit 2), never a pass."""
    if not tasks_path.is_file():
        raise ScopeGuardError(f"tasks.json not found: {tasks_path}")
    try:
        data = json.loads(tasks_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ScopeGuardError(f"tasks.json is not valid JSON ({tasks_path}): {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ScopeGuardError(
            f"tasks.json must be an object with a `tasks` array ({tasks_path})")
    files: set[str] = set()
    for t in data["tasks"]:
        if not isinstance(t, dict):
            continue
        for f in t.get("files") or []:
            if isinstance(f, str) and f.strip():
                files.add(_norm(f))
    return files


def _plan_dir_prefix(spec_dir_rel: str) -> str | None:
    """Given a repo-relative spec dir `docs/plans/<slug>/specs/<id>`, return the
    plan bookkeeping prefix `docs/plans/<slug>/`. Returns None when the layout is
    not the expected depth (then the caller allows just the spec dir itself)."""
    parts = [p for p in _norm(spec_dir_rel).split("/") if p]
    if len(parts) >= 2:
        return "/".join(parts[:-2]) + "/"
    return None


# --- diff gathering -----------------------------------------------------------------

def gather_worktree_diff(repo: Path, base: str) -> set[str]:
    """In-loop: tracked diff vs `base` PLUS untracked new files, repo-relative.
    Mirrors patch-lint.gather_diff — the same tracked + `ls-files --others
    --exclude-standard` pattern (see the m4 limitation in the module docstring)."""
    try:
        _git(repo, "rev-parse", "--verify", "--quiet", base + "^{commit}")
    except ScopeGuardError:
        raise ScopeGuardError(f"base ref `{base}` does not resolve in this repo")
    changed = {
        _norm(p) for p in _git(repo, "diff", "--name-only", base).splitlines()
        if p.strip()
    }
    changed.update(
        _norm(p) for p in
        _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        if p.strip()
    )
    return changed


def gather_committed_diff(repo: Path, base: str, head: str) -> set[str]:
    """CI: files changed between two committed refs, repo-relative. No untracked —
    the bar judges committed state only (the runner passes resolved SHAs)."""
    for ref, flag in ((base, "--base"), (head, "--head")):
        try:
            _git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
        except ScopeGuardError:
            raise ScopeGuardError(f"{flag} ref `{ref}` does not resolve in {repo}")
    return {
        _norm(p) for p in _git(repo, "diff", "--name-only", base, head).splitlines()
        if p.strip()
    }


# --- the scope check ----------------------------------------------------------------

# Sanctioned writes every implement run makes that are never Spec Conflicts.
BASE_ALLOWED_PREFIXES = (".test-guard/", "docs/adr/")


def _allowed(path: str, task_files: set[str], prefixes: tuple[str, ...]) -> bool:
    if path in task_files:
        return True
    for pre in prefixes:
        # Prefix match ONLY (every prefix ends with "/"): a subtree sanction
        # (`docs/adr/**`, `.test-guard/**`) covers files INSIDE the directory, not
        # a bare FILE whose whole path equals the directory name. The old
        # `path == pre.rstrip("/")` disjunct wrongly passed such a file as in-scope.
        if path.startswith(pre):
            return True
    return False


def check_scope(changed: set[str], task_files: set[str],
                allowed_prefixes: tuple[str, ...], spec_count: int) -> tuple[list, list]:
    """Return (hard_failures, advisory). Fail-closed when task_files is non-empty;
    advisory-only (legacy) when it is empty."""
    hard: list[str] = []
    advisory: list[str] = []
    if not task_files:
        advisory.append(
            f"legacy spec set: no `tasks[].files` declared across {spec_count} "
            f"spec(s) — the implement-scope boundary is not enforceable (spec "
            f"authored before file-set enforcement). Add a `files` list to each "
            f"task (spec-lint H6) to enforce the Scope Lock's file boundary.")
        return hard, advisory
    for f in sorted(changed):
        if not _allowed(f, task_files, allowed_prefixes):
            hard.append(
                f"Spec Conflict: `{f}` was touched but is outside the spec's "
                f"declared file set (`tasks[].files`) — the spec must name every "
                f"file it changes. Add it to a task's `files`, or route to "
                f"/core-engineering:ce-spec if the change genuinely widened the planned boundary.")
    return hard, advisory


# --- modes --------------------------------------------------------------------------

def run_in_loop(spec_dir_args: list[str], base: str, repo_arg: str) -> tuple[list, list]:
    repo = Path(repo_arg).resolve()
    if _git_toplevel(repo) is None:
        raise ScopeGuardError(f"--repo {repo_arg} is not inside a git repository")
    task_files: set[str] = set()
    prefixes = list(BASE_ALLOWED_PREFIXES)
    for spec_dir_arg in spec_dir_args:
        spec_dir = Path(spec_dir_arg)
        spec_dir_abs = spec_dir if spec_dir.is_absolute() else (repo / spec_dir)
        if not spec_dir_abs.is_dir():
            raise ScopeGuardError(f"--spec-dir not found: {spec_dir_abs}")
        task_files |= load_task_files(spec_dir_abs / "tasks.json")

        # Allow plan bookkeeping for every selected spec. If a spec lives outside
        # the repository, add no prefix; its task files still remain explicit.
        try:
            spec_dir_rel = _norm(str(spec_dir_abs.resolve().relative_to(repo)))
            prefixes.append(spec_dir_rel.rstrip("/") + "/")
            plan_pre = _plan_dir_prefix(spec_dir_rel)
            if plan_pre:
                prefixes.append(plan_pre)
        except ValueError:
            pass

    changed = gather_worktree_diff(repo, base)
    return check_scope(
        changed, task_files, tuple(prefixes), spec_count=len(spec_dir_args))


def _committed_spec_dirs(tree_root: Path) -> list[Path]:
    """Spec dirs under a materialized committed tree — mirrors gate_runner's
    committed_spec_dirs (ce-spec.md canonical; legacy spec.md accepted)."""
    return sorted(
        d for d in tree_root.glob("docs/plans/*/specs/*")
        if d.is_dir() and ((d / "ce-spec.md").is_file() or (d / "spec.md").is_file())
    )


def run_all_specs(head_tree_arg: str, base: str, head: str,
                  repo_arg: str) -> tuple[list, list]:
    repo = Path(repo_arg).resolve()
    if _git_toplevel(repo) is None:
        raise ScopeGuardError(f"--repo {repo_arg} is not inside a git repository")
    head_tree = Path(head_tree_arg)
    if not head_tree.is_dir():
        raise ScopeGuardError(f"--head-tree not found or not a directory: {head_tree}")

    spec_dirs = _committed_spec_dirs(head_tree)
    task_files: set[str] = set()
    prefixes = list(BASE_ALLOWED_PREFIXES)
    for sd in spec_dirs:
        tp = sd / "tasks.json"
        if tp.is_file():
            task_files |= load_task_files(tp)
        try:
            sd_rel = _norm(str(sd.resolve().relative_to(head_tree.resolve())))
            plan_pre = _plan_dir_prefix(sd_rel)
            if plan_pre:
                prefixes.append(plan_pre)
        except ValueError:
            pass

    changed = gather_committed_diff(repo, base, head)
    return check_scope(changed, task_files, tuple(prefixes), spec_count=len(spec_dirs))


# --- reporting ----------------------------------------------------------------------

def emit(mode: str, hard: list, advisory: list, as_json: bool) -> int:
    status = "fail" if hard else "pass"
    if as_json:
        print(json.dumps({
            "status": status,
            "mode": mode,
            "hard_failures": hard,
            "advisory": advisory,
        }, indent=2))
        return 1 if hard else 0
    print(f"implement-scope-guard [{mode}]:")
    if hard:
        print(f"\n  FAIL — {len(hard)} file(s) outside the spec's declared boundary:")
        for f in hard:
            print(f"    x {f}")
    else:
        print("\n  PASS — every touched file is within the spec's declared file set.")
    if advisory:
        print(f"\n  advisory ({len(advisory)} — review, non-blocking):")
        for a in advisory:
            print(f"    ! {a}")
    print()
    return 1 if hard else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Scope Lock file-boundary gate: fail any touched file outside "
                    "the union of a spec's tasks[].files.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--spec-dir", action="append",
                      help="IN-LOOP: a spec dir (repeat to union multiple specs) — "
                           "scope their tasks[].files over the working-tree diff")
    mode.add_argument("--all-specs", action="store_true",
                      help="CI: union tasks[].files across every spec dir under "
                           "--head-tree, over the committed base..head diff")
    p.add_argument("--base", required=True, help="diff base ref")
    p.add_argument("--head", default="HEAD",
                   help="diff head ref for --all-specs (default HEAD)")
    p.add_argument("--head-tree",
                   help="materialized committed tree to read spec dirs from "
                        "(required with --all-specs)")
    p.add_argument("--repo", default=".", help="repository root (default: .)")
    p.add_argument("--json", action="store_true", help="machine-readable result")
    args = p.parse_args(argv)

    mode_name = "in-loop" if args.spec_dir else "all-specs"
    try:
        if args.spec_dir:
            hard, advisory = run_in_loop(args.spec_dir, args.base, args.repo)
        else:
            if not args.head_tree:
                raise ScopeGuardError("--all-specs requires --head-tree <dir>")
            hard, advisory = run_all_specs(
                args.head_tree, args.base, args.head, args.repo)
    except ScopeGuardError as e:
        if args.json:
            print(json.dumps({"status": "error", "mode": mode_name, "message": str(e)}))
        else:
            print(f"implement-scope-guard [{mode_name}]: ERROR — could not run: {e}",
                  file=sys.stderr)
            print("  -> follow the owning workflow's exit-2 disposition; never treat this as a pass.",
                  file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — any unexpected failure must honor the
        # exit-2 "could not run" contract, never leak a traceback that
        # exits 1 and impersonates a substantive Spec Conflict to a gating caller.
        if args.json:
            print(json.dumps({"status": "error", "mode": mode_name,
                              "message": f"unexpected: {type(e).__name__}: {e}"}))
        else:
            print(f"implement-scope-guard [{mode_name}]: ERROR — unexpected "
                  f"({type(e).__name__}): {e}", file=sys.stderr)
            print("  -> follow the owning workflow's exit-2 disposition; never treat this as a pass.",
                  file=sys.stderr)
        return 2

    return emit(mode_name, hard, advisory, args.json)


if __name__ == "__main__":
    sys.exit(main())
