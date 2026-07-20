#!/usr/bin/env python3
"""Run Claude Code eval scenarios against isolated fixture copies.

Default mode is a dry run: print the planned invocations and make no model
calls. Use --execute plus an explicit --max-budget-usd to run Claude Code.

Outputs are written as:
    evals/runs/<run-id>/<scenario-id>.md
    evals/runs/<run-id>/metadata.json
    evals/runs/<run-id>/work/<scenario-id>/...  # copied fixture repo

The runner deliberately copies fixtures before execution. Skills such as
/ce-plan, /ce-implement, and /ce-patch
may write files; eval runs must never mutate the source fixture corpus.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from eval_check import PROFILES, load_scenarios, rel

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
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


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
    if not args.dry_run:
        initialize_fixture_worktree(work_dir)
    output_file = out_dir / f"{scenario['id']}.md"
    cmd = build_claude_cmd(args, root, scenario)

    record = {
        "id": scenario["id"],
        "invocation": scenario["invocation"],
        "skill": scenario["skill"],
        "fixture": scenario["fixture"],
        "profile": scenario.get("profile"),
        "recommended_budget_usd": scenario.get("recommended_budget_usd"),
        "work_dir": rel(root, work_dir),
        "output_file": rel(root, output_file),
        "claude_command": cmd,
        "status": "planned",
    }

    if args.dry_run:
        budget = scenario.get("recommended_budget_usd")
        budget_note = f" (recommended budget: ${budget:g})" if isinstance(budget, (int, float)) else ""
        print(f"{scenario['id']}: would run in {rel(root, work_dir)}{budget_note}")
        print("  " + " ".join(json.dumps(part) if " " in part else part for part in cmd))
        return record

    proc = subprocess.run(
        cmd,
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=args.timeout,
        env=fixture_process_env(),
    )
    output_file.write_text(proc.stdout, encoding="utf-8")
    if proc.stderr:
        (out_dir / f"{scenario['id']}.stderr").write_text(proc.stderr, encoding="utf-8")
    record["status"] = "pass" if proc.returncode == 0 else "failed"
    record["returncode"] = proc.returncode
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


def git_head(root: Path) -> str | None:
    """Best-effort commit sha the run executed against.

    Recorded in metadata so a curated results summary can anchor freshness to a
    commit (scripts/eval_impact.py --check) rather than only a wall-clock date.
    Returns None when git is unavailable or the root is not a repo — never fatal.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def write_metadata(out_dir: Path, args, records: list[dict]) -> None:
    metadata = {
        "schema_version": 1,
        "run_id": out_dir.name,
        "dry_run": args.dry_run,
        "bare": args.bare,
        "permission_mode": args.permission_mode,
        "max_budget_usd": args.max_budget_usd,
        "model": args.model,
        "effort": args.effort,
        "git_head": git_head(Path(args.root)),
        "records": records,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


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
                        help="required with --execute; passed to claude -p")
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
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS,
                        help="per-scenario timeout in seconds")
    parser.add_argument("--skip-check", action="store_true",
                        help="do not run eval_check.py over outputs after execution")
    args = parser.parse_args(argv)
    args.dry_run = not args.execute

    root = Path(args.root).resolve()
    try:
        data = load_scenarios(root)
        selected = select_scenarios(data["scenarios"], args.scenario, args.profile, args.all)
        if args.execute:
            check_execute_preconditions(args, selected)
        out_dir = Path(args.out_dir) if args.out_dir else root / "evals" / "runs" / default_run_id()
        if not out_dir.is_absolute():
            out_dir = root / out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        records = [run_one(args, root, scenario, out_dir) for scenario in selected]
        write_metadata(out_dir, args, records)
    except (ValueError, subprocess.TimeoutExpired) as exc:
        print(f"eval-run: ERROR — {exc}", file=sys.stderr)
        return 2

    failed = [r for r in records if r.get("status") == "failed"]
    if failed:
        return 1

    if args.execute and not args.skip_check:
        proc = subprocess.run(
            [sys.executable, str(root / "scripts" / "eval_check.py"),
             "--root", str(root), "--outputs-dir", str(out_dir)],
            text=True,
            cwd=root,
        )
        return proc.returncode

    print(f"eval-run: {'planned' if args.dry_run else 'completed'} {len(records)} scenario(s) in {rel(root, out_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
