#!/usr/bin/env python3
"""Run Claude Code eval scenarios against isolated fixture copies.

Default mode is a dry run: print the planned invocations and make no model
calls. Use --execute plus an explicit --max-budget-usd to run Claude Code.

Outputs are written as:
    evals/runs/<run-id>/<scenario-id>.md
    evals/runs/<run-id>/metadata.json
    evals/runs/<run-id>/summary.json
    evals/runs/<run-id>/work/<scenario-id>/...  # copied fixture repo

The runner deliberately copies fixtures before execution. Skills such as
/core-engineering:ce-plan, /core-engineering:ce-implement, and /core-engineering:ce-patch
may write files; eval runs must never mutate the source fixture corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from eval_check import IGNORED_STATE_EXCLUDED_DIRS, PROFILES, load_scenarios, rel

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 900
BUDGET_EXCEEDED = "Exceeded USD budget"
AUTH_REQUIRED = "Not logged in"


def select_scenarios(all_scenarios: list[dict], wanted: list[str], profiles: list[str],
                     run_all: bool) -> list[dict]:
    by_id = {s.get("id"): s for s in all_scenarios if isinstance(s, dict)}
    if run_all:
        if wanted or profiles:
            raise ValueError("--all cannot be combined with --scenario or --profile")
        return all_scenarios
    if profiles:
        if wanted:
            raise ValueError("--profile cannot be combined with --scenario")
        unknown = sorted(set(profiles) - PROFILES)
        if unknown:
            raise ValueError(f"unknown profile(s): {', '.join(unknown)}")
        selected = [s for s in all_scenarios if s.get("profile") in profiles]
        if not selected:
            raise ValueError(f"no scenarios matched profile(s): {', '.join(profiles)}")
        return selected
    if not wanted:
        raise ValueError("choose --scenario <id>, --profile <name>, or --all")
    missing = [sid for sid in wanted if sid not in by_id]
    if missing:
        raise ValueError(f"unknown scenario id(s): {', '.join(missing)}")
    return [by_id[sid] for sid in wanted]


def default_run_id() -> str:
    # Microseconds keep parallel/local receipts distinct without sacrificing the
    # timestamp prefix humans use when curating results.
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def copy_fixture(root: Path, scenario: dict, out_dir: Path) -> Path:
    fixture = scenario["fixture"]
    src = root / "evals" / "fixtures" / fixture
    if not src.is_dir():
        raise ValueError(f"{scenario['id']}: fixture not found: {rel(root, src)}")
    dst = out_dir / "work" / scenario["id"]
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git"))
    return dst


def fixture_process_env() -> dict[str, str]:
    """Return the host environment without inherited Git repository state."""
    env = os.environ.copy()
    for key in [name for name in env if name.startswith("GIT_")]:
        del env[key]
    return env


def initialize_fixture_worktree(work_dir: Path) -> None:
    """Create a clean, reproducible Git baseline for a live eval fixture."""
    git_env = fixture_process_env()
    git_env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "Claude Code Eval",
        "GIT_AUTHOR_EMAIL": "claude-code-eval@example.invalid",
        "GIT_COMMITTER_NAME": "Claude Code Eval",
        "GIT_COMMITTER_EMAIL": "claude-code-eval@example.invalid",
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
    })
    def run_git(command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            proc = subprocess.run(
                ["git", "-C", str(work_dir), *command],
                capture_output=True,
                text=True,
                timeout=30,
                env=git_env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f"could not initialize eval fixture Git worktree: {exc}") from exc
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or f"git exited {proc.returncode}"
            raise ValueError(f"could not initialize eval fixture Git worktree: {detail}")
        return proc

    run_git(["init", "--quiet"])
    run_git(["add", "--all"])
    run_git([
        "-c", f"core.hooksPath={os.devnull}", "commit", "--quiet", "--allow-empty", "--no-gpg-sign",
        "-m", "Initialize eval fixture",
    ])
    status = run_git(["status", "--porcelain", "--untracked-files=all"])
    if status.stdout.strip():
        raise ValueError(f"eval fixture Git baseline is not clean: {status.stdout.strip()}")


def capture_git_state(work_dir: Path) -> dict:
    """Capture Git topology and review-relevant visible and ignored changes."""
    git_env = fixture_process_env()

    def read(*args: str, allow_nonzero: bool = False) -> str:
        try:
            proc = subprocess.run(
                ["git", "-C", str(work_dir), *args],
                capture_output=True,
                text=True,
                timeout=30,
                env=git_env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f"could not capture eval fixture Git state: {exc}") from exc
        if proc.returncode != 0 and not allow_nonzero:
            detail = proc.stderr.strip() or proc.stdout.strip() or f"git exited {proc.returncode}"
            raise ValueError(f"could not capture eval fixture Git state: {detail}")
        return proc.stdout

    head = read("rev-parse", "HEAD").strip()
    branch = read("symbolic-ref", "--quiet", "--short", "HEAD", allow_nonzero=True).strip() or None
    refs = sorted(
        line
        for line in read("for-each-ref", "--format=%(objectname) %(refname)").splitlines()
        if line
    )
    worktrees = [
        line for line in read("worktree", "list", "--porcelain").splitlines() if line
    ]
    local_config = read("config", "--local", "--list", "--null")
    changed = {
        path for path in read("diff", "--name-only", "-z", "HEAD").split("\0") if path
    }
    changed.update(
        path
        for path in read("ls-files", "--others", "--exclude-standard", "-z").split("\0")
        if path
    )
    ignored_files_sha256: dict[str, str] = {}
    ignored_paths = (
        path
        for path in read(
            "ls-files", "--others", "--ignored", "--exclude-standard", "-z"
        ).split("\0")
        if path
    )
    for relative_path in ignored_paths:
        if any(
            part in IGNORED_STATE_EXCLUDED_DIRS
            for part in Path(relative_path).parts
        ):
            continue
        path = work_dir / relative_path
        digest = hashlib.sha256()
        try:
            if path.is_symlink():
                digest.update(b"symlink\0")
                digest.update(os.fsencode(os.readlink(path)))
            elif path.is_file():
                digest.update(b"file\0")
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            else:
                continue
        except OSError as exc:
            raise ValueError(
                f"could not hash ignored eval fixture path {relative_path!r}: {exc}"
            ) from exc
        ignored_files_sha256[relative_path] = digest.hexdigest()
    return {
        "head": head,
        "branch": branch,
        "refs": refs,
        "worktrees": worktrees,
        "local_config_sha256": hashlib.sha256(local_config.encode("utf-8")).hexdigest(),
        "changed_paths": sorted(changed),
        "ignored_files_sha256": dict(sorted(ignored_files_sha256.items())),
    }


def build_claude_cmd(args, root: Path, scenario: dict) -> list[str]:
    prompt = f"{scenario['invocation']} {scenario['prompt']}"
    cmd = [
        args.claude_bin,
        "-p",
    ]
    if args.bare:
        cmd.append("--bare")
    cmd.extend([
        "--plugin-dir",
        str(root / "plugins" / "core-engineering"),
        "--permission-mode",
        args.permission_mode,
        "--no-session-persistence",
        "--append-system-prompt",
        (
            "This is a controlled eval run in an isolated fixture copy. "
            "Treat the current working directory as the whole target repo. "
            "Do not read or write outside it unless the invoked skill explicitly requires it."
        ),
    ])
    if args.max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(args.max_budget_usd)])
    if args.model:
        cmd.extend(["--model", args.model])
    if args.effort:
        cmd.extend(["--effort", args.effort])
    cmd.append(prompt)
    return cmd


def check_execute_preconditions(args, scenarios: list[dict]) -> None:
    if args.max_budget_usd is None:
        raise ValueError("--execute requires --max-budget-usd so eval spend is explicit")
    if args.max_budget_usd <= 0:
        raise ValueError("--max-budget-usd must be positive")
    if args.timeout is not None and args.timeout <= 0:
        raise ValueError("--timeout must be positive")
    recommended = max(float(s.get("recommended_budget_usd", 0)) for s in scenarios)
    if args.max_budget_usd < recommended and not args.allow_low_budget:
        ids = ", ".join(s["id"] for s in scenarios if float(s.get("recommended_budget_usd", 0)) == recommended)
        raise ValueError(
            f"--max-budget-usd {args.max_budget_usd:g} is below the selected scenario "
            f"recommendation {recommended:g} ({ids}). Re-run with --max-budget-usd {recommended:g} "
            f"or pass --allow-low-budget to intentionally test budget failure."
        )
    if shutil.which(args.claude_bin) is None:
        raise ValueError(f"Claude Code executable not found: {args.claude_bin}")


def run_one(args, root: Path, scenario: dict, out_dir: Path) -> dict:
    work_dir = copy_fixture(root, scenario, out_dir)
    initial_git_state = None
    if not args.dry_run:
        initialize_fixture_worktree(work_dir)
        initial_git_state = capture_git_state(work_dir)
    output_file = out_dir / f"{scenario['id']}.md"
    cmd = build_claude_cmd(args, root, scenario)
    timeout_seconds = (
        args.timeout
        if args.timeout is not None
        else int(scenario.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    )

    record = {
        "id": scenario["id"],
        "invocation": scenario["invocation"],
        "skill": scenario["skill"],
        "fixture": scenario["fixture"],
        "profile": scenario.get("profile"),
        "recommended_budget_usd": scenario.get("recommended_budget_usd"),
        "timeout_seconds": timeout_seconds,
        "work_dir": rel(root, work_dir),
        "output_file": rel(root, output_file),
        "claude_command": cmd,
        "status": "planned",
    }
    if initial_git_state is not None:
        record["git_state"] = {"before": initial_git_state}

    if args.dry_run:
        budget = scenario.get("recommended_budget_usd")
        budget_note = f" (recommended budget: ${budget:g})" if isinstance(budget, (int, float)) else ""
        print(f"{scenario['id']}: would run in {rel(root, work_dir)}{budget_note}")
        print("  " + " ".join(json.dumps(part) if " " in part else part for part in cmd))
        return record

    try:
        proc = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=fixture_process_env(),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        output_file.write_text(stdout, encoding="utf-8")
        if stderr:
            (out_dir / f"{scenario['id']}.stderr").write_text(stderr, encoding="utf-8")
        record.update({
            "status": "failed",
            "returncode": None,
            "failure_kind": "timeout",
            "failure_message": f"Claude timed out after {timeout_seconds} seconds",
        })
        try:
            record["git_state"]["after"] = capture_git_state(work_dir)
        except ValueError as git_exc:
            record["git_state"]["capture_error"] = str(git_exc)
        print(
            f"{scenario['id']}: Claude timed out after {timeout_seconds} seconds; "
            "partial output and metadata were preserved",
            file=sys.stderr,
        )
        return record
    output_file.write_text(proc.stdout, encoding="utf-8")
    if proc.stderr:
        (out_dir / f"{scenario['id']}.stderr").write_text(proc.stderr, encoding="utf-8")
    record["status"] = "pass" if proc.returncode == 0 else "failed"
    record["returncode"] = proc.returncode
    try:
        record["git_state"]["after"] = capture_git_state(work_dir)
    except ValueError as git_exc:
        record["git_state"]["capture_error"] = str(git_exc)
        if proc.returncode == 0:
            record.update({
                "status": "failed",
                "failure_kind": "git-state-error",
                "failure_message": str(git_exc),
            })
            print(f"{scenario['id']}: final Git-state capture failed: {git_exc}", file=sys.stderr)
    if proc.returncode != 0:
        combined = "\n".join(part.strip() for part in (proc.stdout, proc.stderr) if part.strip())
        first_line = combined.splitlines()[0] if combined else f"claude exited {proc.returncode}"
        record["failure_message"] = first_line
        if BUDGET_EXCEEDED in combined:
            record["failure_kind"] = "budget-exceeded"
            print(
                f"{scenario['id']}: budget exceeded before an eval artifact was produced "
                f"({first_line}). Re-run with a higher --max-budget-usd.",
                file=sys.stderr,
            )
        elif AUTH_REQUIRED in combined:
            record["failure_kind"] = "auth-error"
            hint = " Configure Claude API-key/auth-helper auth"
            if args.bare:
                hint += " for --bare, or rerun without --bare for local subscription auth"
            hint += "."
            print(f"{scenario['id']}: Claude authentication failed ({first_line}).{hint}", file=sys.stderr)
        else:
            record["failure_kind"] = "claude-error"
            print(f"{scenario['id']}: claude exited {proc.returncode}: {first_line}", file=sys.stderr)
    else:
        print(f"{scenario['id']}: wrote {rel(root, output_file)}")
    return record


def source_git_provenance(root: Path) -> dict:
    """Best-effort source commit and cleanliness captured before model calls."""
    env = fixture_process_env()
    try:
        head_proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
            env=env,
        )
        status_proc = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, timeout=10,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return {"git_head": None, "source_clean": None}
    if head_proc.returncode != 0 or status_proc.returncode != 0:
        return {"git_head": None, "source_clean": None}
    return {
        "git_head": head_proc.stdout.strip() or None,
        "source_clean": not bool(status_proc.stdout.strip()),
    }


def write_summary(out_dir: Path, metadata: dict) -> None:
    """Write the small, commit-ready receipt derived from detailed metadata."""
    scenarios = []
    for record in metadata.get("records", []):
        scenario = {
            key: record[key]
            for key in ("id", "skill", "status", "returncode", "failure_kind")
            if key in record
        }
        scenarios.append(scenario)
    summary = {
        key: metadata.get(key)
        for key in (
            "schema_version", "run_id", "started_at", "completed_at", "git_head",
            "source_clean", "dry_run", "bare", "permission_mode", "max_budget_usd",
            "model", "effort", "grade_status", "grade_returncode", "graded_scenarios",
        )
    }
    summary["scenarios"] = scenarios
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def write_metadata(
    out_dir: Path,
    args,
    records: list[dict],
    source_provenance: dict,
    run_id: str,
    started_at: str,
    completed_at: str,
) -> None:
    metadata = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "dry_run": args.dry_run,
        "bare": args.bare,
        "permission_mode": args.permission_mode,
        "max_budget_usd": args.max_budget_usd,
        "model": args.model,
        "effort": args.effort,
        "git_head": source_provenance.get("git_head"),
        "source_clean": source_provenance.get("source_clean"),
        "grade_status": "not-run",
        "grade_returncode": None,
        "graded_scenarios": [],
        "records": records,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    write_summary(out_dir, metadata)


def record_grade_result(out_dir: Path, returncode: int, scenario_ids: list[str]) -> None:
    """Make the deterministic grader result part of the promotable receipt."""
    path = out_dir / "metadata.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["grade_status"] = "pass" if returncode == 0 else "failed"
    metadata["grade_returncode"] = returncode
    metadata["graded_scenarios"] = scenario_ids if returncode == 0 else []
    metadata["completed_at"] = utc_timestamp()
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    write_summary(out_dir, metadata)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run Claude Code eval scenarios.")
    parser.add_argument("--root", default=str(ROOT), help="repository root")
    parser.add_argument("--scenario", action="append", default=[],
                        help="scenario id to run; repeatable")
    parser.add_argument("--profile", action="append", choices=sorted(PROFILES), default=[],
                        help="run every scenario in a profile; repeatable")
    parser.add_argument("--all", action="store_true", help="run every scenario")
    parser.add_argument("--execute", action="store_true",
                        help="make Claude Code model calls; default is dry-run only")
    parser.add_argument("--out-dir", help="output dir (default: evals/runs/<utc timestamp>)")
    parser.add_argument("--claude-bin", default="claude", help="Claude Code executable")
    parser.add_argument("--max-budget-usd", type=float,
                        help="required with --execute; per-scenario cap passed to each claude -p call")
    parser.add_argument("--allow-low-budget", action="store_true",
                        help="allow --execute with a cap below the selected scenario recommendation")
    parser.add_argument("--permission-mode", default="acceptEdits",
                        choices=["acceptEdits", "auto", "bypassPermissions", "default", "dontAsk", "plan"],
                        help="Claude Code permission mode for fixture copies")
    parser.add_argument("--bare", action="store_true",
                        help="pass --bare for deterministic headless runs; requires API-key/auth-helper auth")
    parser.add_argument("--model", help="optional Claude model alias/name")
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                        help="optional effort level")
    parser.add_argument(
        "--timeout",
        type=int,
        help=(
            "override every selected scenario timeout in seconds "
            f"(default: catalog value or {DEFAULT_TIMEOUT_SECONDS})"
        ),
    )
    parser.add_argument("--skip-check", action="store_true",
                        help="do not run eval_check.py over outputs after execution")
    args = parser.parse_args(argv)
    args.dry_run = not args.execute

    root = Path(args.root).resolve()
    try:
        started_at = utc_timestamp()
        run_id = default_run_id()
        data = load_scenarios(root)
        selected = select_scenarios(data["scenarios"], args.scenario, args.profile, args.all)
        if args.execute:
            check_execute_preconditions(args, selected)
        source_provenance = source_git_provenance(root)
        out_dir = Path(args.out_dir) if args.out_dir else root / "evals" / "runs" / run_id
        if not out_dir.is_absolute():
            out_dir = root / out_dir
        if args.execute and out_dir.exists() and any(out_dir.iterdir()):
            raise ValueError(
                f"--execute output directory must be new or empty so run evidence is not overwritten: {out_dir}"
            )
        out_dir.mkdir(parents=True, exist_ok=True)
        records = [run_one(args, root, scenario, out_dir) for scenario in selected]
        final_source = source_git_provenance(root)
        source_provenance["source_clean"] = bool(
            source_provenance.get("source_clean") is True
            and final_source.get("source_clean") is True
            and final_source.get("git_head") == source_provenance.get("git_head")
        )
        write_metadata(
            out_dir, args, records, source_provenance, run_id, started_at, utc_timestamp()
        )
    except (ValueError, subprocess.TimeoutExpired) as exc:
        print(f"eval-run: ERROR — {exc}", file=sys.stderr)
        return 2

    failed = [r for r in records if r.get("status") == "failed"]
    if failed:
        return 1

    if args.execute and not args.skip_check:
        proc = subprocess.run(
            [sys.executable, str(root / "scripts" / "eval_check.py"),
             "--root", str(root), "--outputs-dir", str(out_dir),
             "--require-all-outputs"],
            text=True,
            cwd=root,
        )
        record_grade_result(
            out_dir, proc.returncode, [record["id"] for record in records]
        )
        return proc.returncode

    print(f"eval-run: {'planned' if args.dry_run else 'completed'} {len(records)} scenario(s) in {rel(root, out_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
