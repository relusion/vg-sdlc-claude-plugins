#!/usr/bin/env python3
"""task-evidence.py — stamp evidence-bound done-ness onto a feature's tasks.json.

`/core-engineering:ce-implement` marks a task `done` when its tests are green. A bare status flag is
cheap to lie to (a reverted commit leaves `done` behind) and carries no proof. This
script replaces the bare flip with an EVIDENCE STAMP: when a task reaches done it also
records WHERE it was proven and WITH WHAT — three additive fields on the task object.

  completed_at     UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`) — when the stamp was written.
  commit_sha       the commit the proven change landed in (resolved to a full sha):
                   the per-task commit under `per-task` VC granularity, else `null`
                   until the Stage-3 feature commit, then filled by `stamp --all-done
                   --commit HEAD`. WS3-T4's `check` subcommand later reads this to
                   verdict a `done` task `fresh` vs `stale` against HEAD's ancestry.
  test_run_digest  `sha256:<hex>` — the test-run evidence fingerprint. DERIVED, source
                   of truth first: the `snapshot_sha256` of this task's PASS marker in
                   WS4-T4's `.test-guard/<feature-id>/passes.json` ledger, projected
                   VERBATIM (that ledger is what proves the task captured a red baseline
                   and reached green without weakening it). No marker (a manual-only
                   task, or a ledger this checkout doesn't hold) falls back to a sha256
                   over `--test-log` if given, else `null` — never a fabricated digest.

Two forms of the one `stamp` subcommand (mutually exclusive selector):

  stamp <tasks.json> --task T-1 [--commit <ref>] [--test-log <file>] \
        [--passes <passes.json>] [--repo <path>]
      Mark T-1 `done` and write all three fields. This IS the done-recording step —
      it sets `status: "done"`, so it replaces the bare status flip in the task loop.
      An unknown task id is refused (exit 1) and nothing is written.

  stamp <tasks.json> --all-done --commit <ref> [--repo <path>]
      Stage-3 finalizer for `per-feature` / `none` granularity: fill `commit_sha` on
      every `done` task that still has none (the per-task loop left it `null`). Already
      -stamped tasks keep their per-task sha untouched — provenance is never clobbered.

The `check` subcommand (WS3-T4) is the CONSUMER side — it verdicts recorded done-ness
against THIS checkout and NEVER writes:

  check <tasks.json> [--repo <path>] [--passes <passes.json>] [--strict] [--json]
      For every `done` task, one verdict from a closed set:
        fresh      commit_sha is an ancestor of HEAD — the proving commit is in this
                   checkout's history (and test_run_digest still matches the current
                   PASS marker, when one is resolvable);
        stale      commit_sha is NOT in HEAD's ancestry (reverted, rebased away, or on
                   a branch this checkout doesn't hold), or test_run_digest no longer
                   matches the marker — the `done` flag points at code this tree does
                   not contain: stranded evidence, exactly what this stamp exists to
                   catch;
        unstamped  not affirmatively verifiable — legacy (pre-stamp, no completed_at),
                   stamped-but-uncommitted (commit_sha null), or no git HEAD here.
      By default, exit 0 when no `done` task is stale and 1 when any is; unstamped
      remains warning-only so legacy consumers do not brick. With `--strict`, exit 1
      when any `done` task is stale OR unstamped, allowing release callers to require
      affirmative freshness without changing the compatibility default. The three
      done-ness consumers ship byte-identical fork copies (fork-manifest):
      `/core-engineering:ce-implement` resume and `/core-engineering:ce-verify` may use the warning-compatible
      default, while `/core-engineering:ce-ship-release` rule 2 uses `--strict` and never treats
      unverifiable done-ness as release-ready.

The write is ATOMIC (tmp + rename) so a crash mid-stamp never truncates tasks.json.
The three fields are additive: `/core-engineering:ce-spec` writes `status: "todo"` and no evidence
fields; they are IMPLEMENT-written, so spec-lint.py's H1-H4 (which read `id`,
`verifies`, `status`) are unaffected by their presence.

Exit codes (the house 0/1/2 contract, so callers gate uniformly):
    0  OK      — the stamp was written (stamp); no `done` task is stale (check),
                 and under `check --strict` every `done` task is affirmatively fresh.
    1  REFUSED — `--task <id>` names a task not in tasks.json (stamp; nothing written)
                 / at least one `done` task is STALE (check), or STALE/UNSTAMPED
                 under `check --strict` (a downgrade signal, not an execution error).
    2  ERROR   — tasks.json missing / unparseable / wrong shape, an unresolvable
                 --commit, a missing --test-log, or an IO error; the caller falls
                 back to recording done-ness by hand (loudly).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


class TaskEvidenceError(Exception):
    """Inputs cannot be loaded / written -> exit 2, caller records done-ness by hand."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- tasks.json load / atomic write -------------------------------------------------

def load_tasks(path: Path) -> dict:
    if not path.is_file():
        raise TaskEvidenceError(f"tasks.json not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise TaskEvidenceError(f"tasks.json is not readable JSON: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise TaskEvidenceError("tasks.json must be an object with a `tasks` array")
    return data


def atomic_write_json(path: Path, data: dict) -> None:
    """tmp + rename — a crash never leaves a half-written tasks.json on disk."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        raise TaskEvidenceError(f"could not write {path}: {e}") from e


# --- git plumbing (subprocess only; degrades when git is absent) --------------------

def _git_toplevel(start: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def resolve_commit(ref: str, repo: Path | None) -> str:
    """Resolve a commit-ish (`HEAD`, a short sha, a branch) to a full sha via
    `git rev-parse`, so WS3-T4's `git merge-base --is-ancestor <commit_sha> HEAD`
    freshness check gets an immutable reference. If git cannot resolve it but the
    value is already a hex sha (a caller that pre-resolved), keep it. Otherwise it is
    unusable -> exit 2 rather than storing a ref that won't survive."""
    if repo is not None:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            capture_output=True, text=True,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", ref):
        return ref
    raise TaskEvidenceError(
        f"--commit {ref!r} does not resolve to a commit (no git repo here, or an "
        f"unknown ref that is not a hex sha) — pass a real commit sha, or run inside "
        f"the repo so `git rev-parse` can resolve it."
    )


# --- test_run_digest derivation (marker = source of truth; --test-log = fallback) ---

def resolve_passes_path(args, tasks_path: Path, tasks: dict) -> Path | None:
    """Locate `.test-guard/<feature-id>/passes.json` — WS4-T4's PASS-marker ledger,
    the SOURCE OF TRUTH for test_run_digest. `--passes` wins; else
    `<repo>/.test-guard/<feature-id>/passes.json`, where repo is `--repo` or the git
    toplevel of tasks.json's directory, and feature-id is tasks.json's `feature_id`
    (else the spec-dir name — the same fallback test-guard.py --verify-passes uses)."""
    if args.passes:
        return Path(args.passes)
    repo = Path(args.repo) if args.repo else _git_toplevel(tasks_path.resolve().parent)
    if repo is None:
        return None
    feature_id = tasks.get("feature_id") or tasks_path.resolve().parent.name
    return repo / ".test-guard" / feature_id / "passes.json"


def marker_digest(passes_path: Path | None, task_id: str) -> str | None:
    """This task's `snapshot_sha256` from the PASS-marker ledger, projected VERBATIM
    into test_run_digest. Returns the LATEST matching entry's digest (the ledger is
    append-only, so the last entry for the task is the most recent PASS), or None if
    the ledger or the entry is absent/unreadable — a missing marker is not an error
    here: it degrades to --test-log or null, and the honor gap is surfaced separately
    by test-guard.py --verify-passes, not fabricated over."""
    if passes_path is None or not passes_path.is_file():
        return None
    try:
        ledger = json.loads(passes_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entries = (ledger.get("passes") if isinstance(ledger, dict) else []) or []
    digest = None
    for e in entries:
        if isinstance(e, dict) and e.get("task_id") == task_id and e.get("snapshot_sha256"):
            digest = e["snapshot_sha256"]  # last wins (append-only ledger)
    return digest


def testlog_digest(test_log: Path) -> str:
    """`sha256:<hex>` over the captured test-run output file — the fallback evidence
    fingerprint for a task with no PASS marker (e.g. a manual-only task)."""
    if not test_log.is_file():
        raise TaskEvidenceError(f"--test-log file not found: {test_log}")
    try:
        raw = test_log.read_bytes()
    except OSError as e:
        raise TaskEvidenceError(f"--test-log unreadable: {e}") from e
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def resolve_digest(args, tasks_path: Path, tasks: dict, task_id: str) -> str | None:
    """test_run_digest resolution, source-of-truth first:
      1. the task's PASS-marker `snapshot_sha256` (verbatim);
      2. else `sha256:` over `--test-log` if supplied;
      3. else None (never a fabricated digest)."""
    digest = marker_digest(resolve_passes_path(args, tasks_path, tasks), task_id)
    if digest:
        return digest
    if args.test_log:
        return testlog_digest(Path(args.test_log))
    return None


# --- the stamp subcommand -----------------------------------------------------------

def emit(result: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result, indent=2))
        return result["exit"]
    if result["exit"] == 1:
        print(f"task-evidence: REFUSED — {result['message']}", file=sys.stderr)
        return 1
    print(f"task-evidence [stamp]: {result['message']}")
    return 0


def cmd_stamp(args) -> int:
    tasks_path = Path(args.tasks)
    tasks = load_tasks(tasks_path)
    entries = tasks["tasks"]
    repo = Path(args.repo) if args.repo else _git_toplevel(tasks_path.resolve().parent)

    if args.all_done:
        commit = resolve_commit(args.commit, repo)
        filled, already = [], []
        for t in entries:
            if not isinstance(t, dict) or t.get("status") != "done":
                continue
            if t.get("commit_sha"):
                already.append(t.get("id"))
                continue
            t["commit_sha"] = commit
            filled.append(t.get("id"))
        atomic_write_json(tasks_path, tasks)
        msg = (f"filled commit_sha={commit} on {len(filled)} done task(s) "
               f"({', '.join(x for x in filled if x) or 'none'}); "
               f"{len(already)} already stamped left untouched")
        return emit({"exit": 0, "message": msg, "commit_sha": commit,
                     "filled": filled, "already_stamped": already}, args.json)

    # single-task stamp — the done-recording step.
    task_id = args.task
    match = next((t for t in entries
                  if isinstance(t, dict) and t.get("id") == task_id), None)
    if match is None:
        known = [t.get("id") for t in entries if isinstance(t, dict)]
        return emit({"exit": 1,
                     "message": f"task id {task_id!r} not found in {tasks_path} "
                                f"(known: {', '.join(x for x in known if x) or 'none'})"},
                    args.json)

    commit = resolve_commit(args.commit, repo) if args.commit else None
    digest = resolve_digest(args, tasks_path, tasks, task_id)
    match["status"] = "done"
    match["completed_at"] = args.now or _utc_now_iso()
    match["commit_sha"] = commit
    match["test_run_digest"] = digest
    atomic_write_json(tasks_path, tasks)
    msg = (f"stamped {task_id} done — completed_at={match['completed_at']}, "
           f"commit_sha={commit}, test_run_digest={digest}")
    return emit({"exit": 0, "message": msg, "task": task_id,
                 "completed_at": match["completed_at"], "commit_sha": commit,
                 "test_run_digest": digest}, args.json)


# --- the check subcommand (WS3-T4): verdict recorded done-ness vs this checkout ----

def head_sha(repo: Path | None) -> str | None:
    """Full sha of HEAD, or None when no HEAD resolves (empty repo / no git). Freshness
    cannot be judged without a HEAD to test ancestry against — that case degrades to
    the `unstamped` (unverifiable, warn-not-block) bucket, never a false `stale`."""
    if repo is None:
        return None
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
        capture_output=True, text=True,
    )
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def is_ancestor(repo: Path, sha: str) -> bool:
    """True iff <sha> is an ancestor of HEAD (reachable in this checkout's history).
    Any non-zero exit — sha reachable-but-not-ancestor (1) or unknown to this repo's
    object DB (128) — both mean the proving commit is not in this tree's history, so
    both read as NOT fresh (the point of the check)."""
    out = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", sha, "HEAD"],
        capture_output=True, text=True,
    )
    return out.returncode == 0


def verdict_for_task(task: dict, repo: Path | None, head: str | None,
                     current_digest: str | None) -> tuple[str, str]:
    """(verdict, reason) for one `done` task, from the closed set fresh/stale/unstamped
    (see the module docstring). `current_digest` is this task's marker digest re-derived
    NOW (None when no marker is resolvable — absence never flags stale, only a real
    mismatch does)."""
    if "completed_at" not in task:
        return "unstamped", "legacy: no evidence stamp (pre-WS3-T3 done flag)"
    commit = task.get("commit_sha")
    if not commit:
        return ("unstamped",
                "stamped but not bound to a commit (uncommitted / `none` granularity)")
    if repo is None or head is None:
        return "unstamped", "no git HEAD here to verify commit_sha against"
    if not is_ancestor(repo, commit):
        return ("stale", f"commit_sha {commit[:12]} is not in HEAD's ancestry "
                         f"(reverted / rebased away / a checkout without it)")
    stamped_digest = task.get("test_run_digest")
    if stamped_digest and current_digest is not None and stamped_digest != current_digest:
        return "stale", "test_run_digest no longer matches the current PASS marker"
    return "fresh", "commit_sha is an ancestor of HEAD"


def cmd_check(args) -> int:
    tasks_path = Path(args.tasks)
    tasks = load_tasks(tasks_path)
    entries = tasks["tasks"]
    repo = Path(args.repo) if args.repo else _git_toplevel(tasks_path.resolve().parent)
    head = head_sha(repo)
    passes_path = resolve_passes_path(args, tasks_path, tasks)

    results, stamped = [], 0
    counts = {"done": 0, "fresh": 0, "stale": 0, "unstamped": 0}
    for t in entries:
        if not isinstance(t, dict) or t.get("status") != "done":
            continue
        counts["done"] += 1
        if "completed_at" in t:
            stamped += 1
        tid = t.get("id")
        current_digest = marker_digest(passes_path, tid) if tid else None
        verdict, reason = verdict_for_task(t, repo, head, current_digest)
        counts[verdict] += 1
        results.append({"id": tid, "verdict": verdict,
                        "commit_sha": t.get("commit_sha"), "reason": reason})

    stale_ids = [r["id"] for r in results if r["verdict"] == "stale"]
    unstamped_ids = [r["id"] for r in results if r["verdict"] == "unstamped"]
    blocking_ids = [
        r["id"] for r in results
        if r["verdict"] == "stale" or (args.strict and r["verdict"] == "unstamped")
    ]
    exit_code = 1 if blocking_ids else 0
    payload = {
        "tool": "task-evidence check",
        "tasks_path": str(tasks_path),
        "feature_id": tasks.get("feature_id") or tasks_path.resolve().parent.name,
        "repo": str(repo) if repo else None,
        "head": head,
        "counts": counts,
        "stamped": stamped,
        "strict": args.strict,
        "stale": stale_ids,
        "unstamped": unstamped_ids,
        "blocking": blocking_ids,
        "tasks": results,
        "exit": exit_code,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return exit_code
    print(f"task-evidence [check]: {counts['done']} done — {counts['fresh']} fresh, "
          f"{counts['stale']} stale, {counts['unstamped']} unstamped")
    for r in results:
        if r["verdict"] != "fresh":
            mark = ("STALE" if r["verdict"] == "stale" else
                    "BLOCK" if args.strict else "warn ")
            print(f"  {mark} {r['id']}: {r['reason']}")
    if blocking_ids:
        if args.strict:
            print(f"  -> {len(blocking_ids)} non-fresh task(s): strict mode requires "
                  f"every `done` task to be affirmatively fresh — treat them as NOT "
                  f"release-ready.", file=sys.stderr)
        else:
            print(f"  -> {len(stale_ids)} stale task(s): the `done` flag points at code "
                  f"this checkout does not contain — treat them as NOT done.",
                  file=sys.stderr)
    return exit_code


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Stamp (and verify) evidence-bound done-ness (completed_at / "
                    "commit_sha / test_run_digest) on a feature's tasks.json.")
    sub = p.add_subparsers(dest="command", required=True)

    st = sub.add_parser("stamp", help="record a task done with its evidence fields")
    st.add_argument("tasks", help="path to the feature's tasks.json")
    sel = st.add_mutually_exclusive_group(required=True)
    sel.add_argument("--task", metavar="ID", help="the task id to stamp done")
    sel.add_argument("--all-done", action="store_true",
                     help="fill commit_sha on every done task lacking one (Stage-3 finalizer)")
    st.add_argument("--commit", metavar="REF",
                    help="commit-ish for commit_sha (resolved to a full sha); required with --all-done")
    st.add_argument("--test-log", metavar="FILE",
                    help="captured test-run output; sha256'd as the test_run_digest fallback when no PASS marker exists")
    st.add_argument("--passes", metavar="FILE",
                    help="explicit path to .test-guard/<feature-id>/passes.json (else derived from --repo + feature_id)")
    st.add_argument("--repo", metavar="PATH", help="repo root (default: git toplevel of tasks.json's dir)")
    st.add_argument("--now", metavar="ISO", help="override completed_at (test hook; default: UTC now)")
    st.add_argument("--json", action="store_true", help="machine-readable result")
    st.set_defaults(func=cmd_stamp)

    ck = sub.add_parser("check",
                        help="verdict each done task fresh/stale/unstamped vs HEAD (never writes)")
    ck.add_argument("tasks", help="path to the feature's tasks.json")
    ck.add_argument("--repo", metavar="PATH", help="repo root (default: git toplevel of tasks.json's dir)")
    ck.add_argument("--passes", metavar="FILE",
                    help="explicit path to .test-guard/<feature-id>/passes.json (for the test_run_digest re-check)")
    ck.add_argument("--strict", action="store_true",
                    help="fail when any done task is stale or unstamped (release-ready mode)")
    ck.add_argument("--json", action="store_true", help="machine-readable result")
    ck.set_defaults(func=cmd_check)

    args = p.parse_args(argv)

    if getattr(args, "all_done", False) and not args.commit:
        p.error("--all-done requires --commit <ref> (the Stage-3 feature commit)")

    try:
        return args.func(args)
    except TaskEvidenceError as e:
        if getattr(args, "json", False):
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            print(f"task-evidence: ERROR — could not run: {e}", file=sys.stderr)
            print("  -> fall back to recording done-ness by hand (loudly).", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — any unexpected failure honors the exit-2
        # contract, never a traceback that exits 1 and impersonates a REFUSED to a
        # gating caller.
        if getattr(args, "json", False):
            print(json.dumps({"status": "error", "message": f"unexpected: {type(e).__name__}: {e}"}))
        else:
            print(f"task-evidence: ERROR — unexpected failure ({type(e).__name__}): {e}", file=sys.stderr)
            print("  -> fall back to recording done-ness by hand (loudly).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
