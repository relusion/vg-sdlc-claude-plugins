#!/usr/bin/env python3
"""Mechanical git-worktree creation + merge-back for /ce-auto-build.

The parallel-worktree mode (gate-worktree.md) runs each provably-independent
feature in its own git worktree, then the orchestrator merges every worktree
branch back onto the run branch. That merge-back was prose-only — the most
operationally fragile step in the pipeline. This script gives it the same
deterministic, stdlib-only, zero-Claude-Code backing the *preflight*
(worktree-preflight.py) already has.

It NEVER resolves a conflict and NEVER commits: on a clean merge it leaves the
result staged-uncommitted for the orchestrator's Checkpoint-Mode commit; on any
conflict it aborts (restoring a clean tree) and reports the conflicting paths.
The orchestrator disposes on the exit code (see gate-worktree.md):

  0  merged cleanly (staged, uncommitted)     -> commit per Checkpoint Mode
  1  merge conflict, aborted (tree clean)     -> stop the group / go sequential
  2  refused or could-not-run                 -> record degradation, go sequential

Subcommands: create, merge, remove, list. Conventions mirror
worktree-preflight.py (the run() subprocess wrapper, --json, schema_version).
Stdlib-only; runs with zero Claude Code present.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = 1


def run(root: Path, *args: str) -> tuple[int, str, str]:
    """Run `git -C <root> <args...>`; return (code, stdout, stderr) stripped."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


def protected_branch(root: Path) -> str:
    """Derive the protected/default branch name.

    Reimplements git-guard.py's protected_branch() locally on purpose — hooks
    and skill scripts deliberately share no files, so the merge guard stays
    self-contained. Same precedence: origin/HEAD symbolic-ref, then
    init.defaultBranch, then the first of main/master that exists.
    """
    _code, out, _err = run(root, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    if out:
        return out.rsplit("/", 1)[-1]
    _code, out, _err = run(root, "config", "--get", "init.defaultBranch")
    if out:
        return out
    for name in ("main", "master"):
        _code, out, _err = run(root, "rev-parse", "--verify", "--quiet", name)
        if out:
            return name
    return ""


def current_branch(root: Path) -> str:
    code, out, _err = run(root, "rev-parse", "--abbrev-ref", "HEAD")
    return out if code == 0 else ""


def is_dirty(root: Path) -> bool | None:
    code, out, _err = run(root, "status", "--porcelain")
    if code != 0:
        return None
    return bool(out)


def inside_work_tree(root: Path) -> bool:
    code, out, _err = run(root, "rev-parse", "--is-inside-work-tree")
    return code == 0 and out == "true"


def path_has_content(path: Path) -> bool:
    """True if the path exists and is a non-empty directory (or a file)."""
    if not path.exists():
        return False
    if path.is_dir():
        return any(path.iterdir())
    return True


def emit(result: dict, exit_code: int, as_json: bool) -> int:
    result.setdefault("schema_version", SCHEMA_VERSION)
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        status = result.get("status", "")
        reason = result.get("reason") or ""
        line = f"{result.get('action', '')}: {status}"
        if reason:
            line += f" — {reason}"
        print(line)
        for c in result.get("conflicts", []) or []:
            print(f"  conflict: {c}")
    return exit_code


# --- subcommands ------------------------------------------------------------


def cmd_create(root: Path, branch: str, path: str, as_json: bool) -> int:
    action = "create"
    if not inside_work_tree(root):
        return emit({"action": action, "status": "refused",
                     "reason": "not inside a git work tree"}, 2, as_json)
    target = Path(path)
    if not target.is_absolute():
        target = (root / path)
    target = target.resolve() if target.exists() else target.absolute()
    if path_has_content(target):
        return emit({"action": action, "status": "refused", "path": str(target),
                     "reason": "target path already exists and is non-empty "
                               "(refusing to reuse a possibly-dirty path)"}, 2, as_json)
    code, _out, err = run(root, "worktree", "add", "-b", branch, str(target))
    if code != 0:
        return emit({"action": action, "status": "error", "branch": branch,
                     "path": str(target), "reason": err or "git worktree add failed"},
                    2, as_json)
    return emit({"action": action, "status": "created", "branch": branch,
                 "path": str(target)}, 0, as_json)


def cmd_merge(root: Path, from_branch: str, into: str, as_json: bool) -> int:
    action = "merge"
    if not inside_work_tree(root):
        return emit({"action": action, "status": "refused",
                     "reason": "not inside a git work tree"}, 2, as_json)

    prot = protected_branch(root)
    if prot and into == prot:
        return emit({"action": action, "status": "refused", "into": into,
                     "from_branch": from_branch,
                     "reason": f"refusing to merge into the protected branch `{prot}` "
                               "— auto-build never writes shared history"}, 2, as_json)

    cur = current_branch(root)
    if cur != into:
        return emit({"action": action, "status": "refused", "into": into,
                     "from_branch": from_branch, "current_branch": cur,
                     "reason": f"target tree is on `{cur}`, not the declared "
                               f"--into `{into}` (refusing to merge into the "
                               "wrong branch)"}, 2, as_json)

    dirty = is_dirty(root)
    if dirty is None:
        return emit({"action": action, "status": "error", "into": into,
                     "from_branch": from_branch,
                     "reason": "could not read target tree status"}, 2, as_json)
    if dirty:
        return emit({"action": action, "status": "refused", "into": into,
                     "from_branch": from_branch,
                     "reason": "target tree is dirty — clean or stash before "
                               "merge-back so the merge is the only staged change"},
                    2, as_json)

    code, _out, err = run(root, "merge", "--no-ff", "--no-commit", from_branch)
    if code == 0:
        return emit({"action": action, "status": "merged", "into": into,
                     "from_branch": from_branch, "staged": True,
                     "note": "merge staged, left uncommitted for Checkpoint-Mode commit"},
                    0, as_json)

    # Non-zero: distinguish a genuine conflict from a non-conflict failure.
    _c, unmerged, _e = run(root, "diff", "--name-only", "--diff-filter=U")
    conflicts = [p for p in unmerged.splitlines() if p.strip()]
    # Always abort to restore a clean tree — this script never leaves a
    # half-merged state and never resolves.
    run(root, "merge", "--abort")
    if conflicts:
        return emit({"action": action, "status": "conflict", "into": into,
                     "from_branch": from_branch, "conflicts": conflicts,
                     "aborted": True,
                     "reason": "merge conflict — aborted, tree restored clean; "
                               "orchestrator STOPS this group (never auto-resolves)"},
                    1, as_json)
    return emit({"action": action, "status": "error", "into": into,
                 "from_branch": from_branch, "aborted": True,
                 "reason": err or "git merge failed for a non-conflict reason"},
                2, as_json)


def cmd_remove(root: Path, path: str, as_json: bool) -> int:
    action = "remove"
    if not inside_work_tree(root):
        return emit({"action": action, "status": "refused",
                     "reason": "not inside a git work tree"}, 2, as_json)
    target = Path(path)
    if not target.is_absolute():
        target = (root / path)
    target = target.absolute()
    code, _out, err = run(root, "worktree", "remove", str(target))
    if code != 0:
        return emit({"action": action, "status": "error", "path": str(target),
                     "reason": err or "git worktree remove failed (dirty or missing?)"},
                    2, as_json)
    return emit({"action": action, "status": "removed", "path": str(target)}, 0, as_json)


def cmd_list(root: Path, as_json: bool) -> int:
    action = "list"
    if not inside_work_tree(root):
        return emit({"action": action, "status": "refused",
                     "reason": "not inside a git work tree"}, 2, as_json)
    code, out, err = run(root, "worktree", "list", "--porcelain")
    if code != 0:
        return emit({"action": action, "status": "error",
                     "reason": err or "git worktree list failed"}, 2, as_json)
    worktrees: list[dict] = []
    current: dict = {}
    for line in out.splitlines():
        if not line.strip():
            if current:
                worktrees.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line[len("worktree "):]}
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):]
        elif line == "detached":
            current["detached"] = True
        elif line == "bare":
            current["bare"] = True
        elif line.startswith("locked"):
            current["locked"] = True
    if current:
        worktrees.append(current)
    return emit({"action": action, "status": "listed", "worktrees": worktrees}, 0, as_json)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mechanical git-worktree create + merge-back for /ce-auto-build"
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=".", help="repository root")
    common.add_argument("--json", action="store_true", help="print JSON")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", parents=[common],
                              help="git worktree add -b <branch> <path>")
    p_create.add_argument("--branch", required=True)
    p_create.add_argument("--path", required=True)

    p_merge = sub.add_parser("merge", parents=[common],
                             help="merge <from-branch> into the run branch (--no-ff --no-commit)")
    p_merge.add_argument("--from-branch", required=True, dest="from_branch")
    p_merge.add_argument("--into", required=True)

    p_remove = sub.add_parser("remove", parents=[common], help="git worktree remove <path>")
    p_remove.add_argument("--path", required=True)

    sub.add_parser("list", parents=[common], help="list worktrees as JSON")

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    if args.cmd == "create":
        return cmd_create(root, args.branch, args.path, args.json)
    if args.cmd == "merge":
        return cmd_merge(root, args.from_branch, args.into, args.json)
    if args.cmd == "remove":
        return cmd_remove(root, args.path, args.json)
    if args.cmd == "list":
        return cmd_list(root, args.json)
    parser.error("unknown subcommand")  # pragma: no cover
    return 2


if __name__ == "__main__":
    sys.exit(main())
