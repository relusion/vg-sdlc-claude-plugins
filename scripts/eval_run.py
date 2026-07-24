#!/usr/bin/env python3
"""Run Claude Code eval scenarios against isolated fixture copies.

Default mode is a dry run: print the planned invocations and make no model
calls. Use --execute plus an explicit --max-budget-usd to run Claude Code.

Outputs are written as:
    evals/runs/<run-id>/<scenario-id>.md
    evals/runs/<run-id>/<scenario-id>.final.md  # exact final assistant result
    evals/runs/<run-id>/metadata.json
    evals/runs/<run-id>/summary.json
    evals/runs/<run-id>/work/<scenario-id>/...  # copied fixture repo

The runner deliberately copies fixtures before execution. Skills such as
/core-engineering:ce-plan, /core-engineering:ce-implement, and /core-engineering:ce-patch
may write files; eval runs must never mutate the source fixture corpus.

Scenarios may declare context-checked ``scripted_turns``. Those runs use Claude
JSON output, verify gate/context anchors before each supplied answer, resume the
same session, and hash-bind every decision event to the preceding response.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from eval_check import (
    IGNORED_STATE_EXCLUDED_DIRS,
    PROFILES,
    grade_artifact_target,
    is_finite_positive_number,
    load_scenarios,
    rel,
    validate_catalog,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 900
CLI_VERSION_TIMEOUT_SECONDS = 10
BUDGET_EXCEEDED_MARKERS = (
    "Exceeded USD budget",
    "Reached maximum budget",
    "error_max_budget_usd",
    "budget_exhausted",
)
BUDGET_EXCEEDED_SUBTYPES = {"error_max_budget_usd"}
BUDGET_EXCEEDED_TERMINAL_REASONS = {"budget_exhausted"}
AUTH_REQUIRED = "Not logged in"
EVAL_PLUGIN_DIRS = (Path("plugins/core-engineering"),)


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
        selected = [
            s
            for s in all_scenarios
            if isinstance(s, dict) and s.get("profile") in profiles
        ]
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


def capture_claude_cli_provenance(args, root: Path) -> dict:
    """Best-effort version evidence for the CLI used by an executed run."""
    provenance = {
        "binary": args.claude_bin,
        "status": "unavailable",
        "version": None,
        "reason": "not-probed-dry-run",
    }
    if args.dry_run:
        return provenance

    try:
        proc = subprocess.run(
            [args.claude_bin, "--version"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=CLI_VERSION_TIMEOUT_SECONDS,
            env=fixture_process_env(),
        )
    except subprocess.TimeoutExpired:
        provenance["reason"] = "version-probe-timeout"
        return provenance
    except OSError:
        provenance["reason"] = "version-probe-error"
        return provenance

    if proc.returncode != 0:
        provenance["reason"] = f"version-probe-exited-{proc.returncode}"
        return provenance
    output = proc.stdout.strip() or proc.stderr.strip()
    if not output:
        provenance["reason"] = "version-probe-empty-output"
        return provenance

    provenance.update({
        "status": "resolved",
        "version": output.splitlines()[0][:256],
        "reason": None,
    })
    return provenance


def capture_plugin_manifest_provenance(root: Path) -> list[dict]:
    """Read versions for the local plugin directories supplied to Claude."""
    records = []
    for relative_dir in EVAL_PLUGIN_DIRS:
        plugin_dir = root / relative_dir
        manifest = plugin_dir / ".claude-plugin" / "plugin.json"
        record = {
            "source": "--plugin-dir",
            "plugin_dir": rel(root, plugin_dir),
            "manifest": rel(root, manifest),
            "status": "unavailable",
            "name": None,
            "version": None,
            "reason": None,
        }
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except FileNotFoundError:
            record["reason"] = "manifest-missing"
        except (OSError, json.JSONDecodeError):
            record["reason"] = "manifest-unreadable"
        else:
            name = data.get("name") if isinstance(data, dict) else None
            version = data.get("version") if isinstance(data, dict) else None
            if isinstance(name, str) and name and isinstance(version, str) and version:
                record.update({
                    "status": "resolved",
                    "name": name,
                    "version": version,
                })
            else:
                record["reason"] = "name-or-version-missing"
        records.append(record)
    return records


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


def build_claude_cmd(
    args,
    root: Path,
    scenario: dict,
    *,
    prompt: str | None = None,
    resume_session_id: str | None = None,
    max_budget_usd: float | None = None,
) -> list[str]:
    scripted = bool(scenario.get("scripted_turns"))
    if prompt is None:
        prompt = f"{scenario['invocation']} {scenario['prompt']}"
    cmd = [
        args.claude_bin,
        "-p",
    ]
    if args.bare:
        cmd.append("--bare")
    for relative_dir in EVAL_PLUGIN_DIRS:
        cmd.extend(["--plugin-dir", str(root / relative_dir)])
    cmd.extend([
        "--permission-mode",
        args.permission_mode,
        "--append-system-prompt",
        (
            "This is a controlled eval run in an isolated fixture copy. "
            "Treat the current working directory as the whole target repo. "
            "Do not read or write outside it unless the invoked skill explicitly requires it."
        ),
    ])
    if scripted:
        cmd.extend(["--output-format", "json"])
        if resume_session_id is not None:
            cmd.extend(["--resume", resume_session_id])
    else:
        cmd.append("--no-session-persistence")
    budget = args.max_budget_usd if max_budget_usd is None else max_budget_usd
    if budget is not None:
        cmd.extend(["--max-budget-usd", str(budget)])
    if args.model:
        cmd.extend(["--model", args.model])
    if args.effort:
        cmd.extend(["--effort", args.effort])
    cmd.append(prompt)
    return cmd


def parse_scripted_response(stdout: str) -> tuple[str, str, float]:
    """Return (assistant text, session id, turn cost) from Claude JSON output."""
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude scripted output is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Claude scripted output must be one JSON object")
    result = payload.get("result")
    session_id = payload.get("session_id")
    cost = payload.get("total_cost_usd")
    if not isinstance(result, str) or not result.strip():
        raise ValueError("Claude scripted output is missing non-empty result text")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Claude scripted output is missing a resumable session_id")
    if (
        not isinstance(cost, (int, float))
        or isinstance(cost, bool)
        or not math.isfinite(cost)
        or cost < 0
    ):
        raise ValueError("Claude scripted output is missing a non-negative total_cost_usd")
    return result, session_id, float(cost)


def parse_claude_json_payload(stdout: str) -> dict | None:
    """Best-effort parse of Claude's JSON success or error envelope."""
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def payload_reported_cost(payload: dict | None) -> float | None:
    """Return a finite non-negative invocation cost when Claude reported one."""
    if payload is None:
        return None
    cost = payload.get("total_cost_usd")
    if (
        not isinstance(cost, (int, float))
        or isinstance(cost, bool)
        or not math.isfinite(cost)
        or cost < 0
    ):
        return None
    return float(cost)


def is_budget_exceeded(combined: str, payload: dict | None = None) -> bool:
    """Recognize legacy text and current structured Claude budget failures."""
    if payload is not None and (
        payload.get("subtype") in BUDGET_EXCEEDED_SUBTYPES
        or payload.get("terminal_reason") in BUDGET_EXCEEDED_TERMINAL_REASONS
    ):
        return True
    return any(marker in combined for marker in BUDGET_EXCEEDED_MARKERS)


def regular_file_sha256(path: Path) -> tuple[str | None, str | None]:
    """Hash a regular, non-symlink file or return a stable failure reason."""
    try:
        if path.is_symlink() or not path.is_file():
            return None, "missing or not a regular file"
        return hashlib.sha256(path.read_bytes()).hexdigest(), None
    except OSError as exc:
        return None, str(exc)


def persist_final_output(out_dir: Path, scenario_id: str, text: str) -> dict:
    """Persist exact assistant-result bytes without overwriting prior evidence."""
    filename = f"{scenario_id}.final.md"
    if Path(filename).name != filename:
        raise OSError(f"unsafe scenario id for final-output sidecar: {scenario_id!r}")
    payload = text.encode("utf-8")
    path = out_dir / filename
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return {
        "file": filename,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "word_count": len(text.split()),
        "byte_count": len(payload),
    }


def check_required_previous_artifacts(
    root: Path,
    scenario_id: str,
    work_dir: Path,
    checks: list[dict],
) -> tuple[list[dict], list[str]]:
    """Validate exact artifacts at a scripted human-answer boundary."""
    receipts: list[dict] = []
    failures: list[str] = []
    for check in checks:
        artifact_type = check["type"]
        relative_path = check["path"]
        path_fragment = Path(relative_path)
        if (
            artifact_type != "architecture_options_lint"
            or path_fragment.is_absolute()
            or ".." in path_fragment.parts
        ):
            failures.append(
                f"{scenario_id}: unsafe or unsupported prior-turn artifact check "
                f"{artifact_type!r}:{relative_path!r}"
            )
            continue
        path = work_dir / path_fragment
        sha256_before, hash_failure = regular_file_sha256(path)
        if hash_failure:
            failures.append(
                f"{scenario_id}: could not hash prior-turn artifact "
                f"{relative_path!r}: {hash_failure}"
            )
            continue
        try:
            check_failures = grade_artifact_target(
                root,
                scenario_id,
                check,
                artifact_type,
                path,
                artifact_repo_root=work_dir,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(
                f"{scenario_id}: prior-turn artifact validation could not run "
                f"for {relative_path!r}: {exc}"
            )
            continue
        if check_failures:
            failures.extend(check_failures)
            continue
        sha256_after, hash_failure = regular_file_sha256(path)
        if hash_failure:
            failures.append(
                f"{scenario_id}: could not hash validated prior-turn artifact "
                f"{relative_path!r}: {hash_failure}"
            )
            continue
        if sha256_after != sha256_before:
            failures.append(
                f"{scenario_id}: prior-turn artifact changed while it was being validated: "
                f"{relative_path!r}"
            )
            continue
        receipts.append({
            "type": artifact_type,
            "path": relative_path,
            "status": "pass",
            "sha256": sha256_after,
        })
    return receipts, failures


def run_scripted_turns(
    args,
    root: Path,
    scenario: dict,
    work_dir: Path,
    out_dir: Path,
    output_file: Path,
    timeout_seconds: int,
    record: dict,
) -> dict:
    """Execute context-checked follow-up answers in one resumable session."""
    scripted_turns = scenario["scripted_turns"]
    commands: list[list[str]] = []
    decisions: list[dict] = []
    transcript: list[str] = []
    stderr_chunks: list[str] = []
    session_id: str | None = None
    next_prompt: str | None = None
    remaining_budget = float(args.max_budget_usd)
    reported_cost = 0.0
    failed_turn_reported_cost: float | None = None
    final_result: str | None = None
    started = time.monotonic()

    def persist() -> None:
        output_file.write_text("\n".join(transcript).rstrip() + "\n", encoding="utf-8")
        if stderr_chunks:
            (out_dir / f"{scenario['id']}.stderr").write_text(
                "\n".join(stderr_chunks).rstrip() + "\n",
                encoding="utf-8",
            )

    def fail(kind: str, message: str, returncode: int | None) -> dict:
        persist()
        record.update({
            "status": "failed",
            "returncode": returncode,
            "failure_kind": kind,
            "failure_message": message,
            "claude_commands": commands,
            "scripted_decisions": decisions,
            "reported_cost_usd": reported_cost,
        })
        if failed_turn_reported_cost is not None:
            record["failed_turn_reported_cost_usd"] = failed_turn_reported_cost
        print(f"{scenario['id']}: {message}", file=sys.stderr)
        return record

    for assistant_turn in range(1, len(scripted_turns) + 2):
        elapsed = time.monotonic() - started
        remaining_timeout = max(1, int(timeout_seconds - elapsed))
        if elapsed >= timeout_seconds:
            return fail(
                "timeout",
                f"Claude scripted scenario timed out after {timeout_seconds} seconds",
                None,
            )
        if remaining_budget <= 0:
            return fail(
                "budget-exceeded",
                "scripted scenario exhausted its aggregate USD budget before the next turn",
                None,
            )

        cmd = build_claude_cmd(
            args,
            root,
            scenario,
            prompt=next_prompt,
            resume_session_id=session_id,
            max_budget_usd=remaining_budget,
        )
        commands.append(cmd)
        try:
            proc = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=remaining_timeout,
                env=fixture_process_env(),
            )
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout or ""
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", errors="replace")
            if partial:
                transcript.extend([
                    f"## Assistant turn {assistant_turn} — partial output",
                    "",
                    partial,
                    "",
                ])
            return fail(
                "timeout",
                f"Claude scripted scenario timed out after {timeout_seconds} seconds",
                None,
            )

        if proc.stderr:
            stderr_chunks.append(f"turn {assistant_turn}:\n{proc.stderr}")
        if proc.returncode != 0:
            combined = "\n".join(
                part.strip() for part in (proc.stdout, proc.stderr) if part.strip()
            )
            first_line = combined.splitlines()[0] if combined else f"claude exited {proc.returncode}"
            error_payload = parse_claude_json_payload(proc.stdout)
            failed_turn_reported_cost = payload_reported_cost(error_payload)
            if failed_turn_reported_cost is not None:
                reported_cost += failed_turn_reported_cost
            kind = "claude-error"
            if is_budget_exceeded(combined, error_payload):
                kind = "budget-exceeded"
            elif AUTH_REQUIRED in combined:
                kind = "auth-error"
            return fail(kind, first_line, proc.returncode)

        try:
            result, response_session_id, turn_cost = parse_scripted_response(proc.stdout)
        except ValueError as exc:
            transcript.extend([
                f"## Assistant turn {assistant_turn} — invalid protocol output",
                "",
                proc.stdout,
                "",
            ])
            return fail("scripted-protocol-error", str(exc), proc.returncode)

        if session_id is not None and response_session_id != session_id:
            return fail(
                "scripted-protocol-error",
                "Claude changed session_id during a scripted resume",
                proc.returncode,
            )
        session_id = response_session_id
        reported_cost += turn_cost
        remaining_budget = max(0.0, float(args.max_budget_usd) - reported_cost)
        transcript.extend([f"## Assistant turn {assistant_turn}", "", result, ""])

        if assistant_turn > len(scripted_turns):
            final_result = result
            break

        scripted = scripted_turns[assistant_turn - 1]
        word_count = len(result.split())
        max_words = scripted.get("max_previous_output_words")
        if max_words is not None and word_count > max_words:
            return fail(
                "scripted-output-limit",
                "refused to send decision event "
                f"{scripted['event_id']}: prior output had {word_count} words, "
                f"exceeding max_previous_output_words={max_words}",
                proc.returncode,
            )
        required = scripted["required_previous_output"]
        missing = [anchor for anchor in required if anchor not in result]
        if missing:
            return fail(
                "scripted-context-mismatch",
                "refused to send decision event "
                f"{scripted['event_id']}: prior output missed context anchor(s): "
                + ", ".join(repr(anchor) for anchor in missing),
                proc.returncode,
            )

        required_artifacts = scripted.get("required_previous_artifacts", [])
        artifact_receipts, artifact_failures = check_required_previous_artifacts(
            root,
            scenario["id"],
            work_dir,
            required_artifacts,
        )
        if artifact_failures:
            return fail(
                "scripted-artifact-precondition",
                "refused to send decision event "
                f"{scripted['event_id']}: prior turn artifact precondition failed: "
                + "; ".join(artifact_failures),
                proc.returncode,
            )

        context_sha256 = hashlib.sha256(result.encode("utf-8")).hexdigest()
        answer = scripted["answer"]
        answer_sha256 = hashlib.sha256(answer.encode("utf-8")).hexdigest()
        decisions.append({
            "event_id": scripted["event_id"],
            "after_assistant_turn": assistant_turn,
            "required_previous_output": required,
            "required_previous_artifacts": artifact_receipts,
            "previous_output_word_count": word_count,
            "context_sha256": context_sha256,
            "answer_sha256": answer_sha256,
            "session_id": session_id,
        })
        transcript.extend([
            f"## Scripted decision event {scripted['event_id']}",
            "",
            f"- Context SHA-256: `{context_sha256}`",
            f"- Answer SHA-256: `{answer_sha256}`",
            f"- Verified context anchors: {', '.join(f'`{anchor}`' for anchor in required)}",
            (
                f"- Previous output words: {word_count}"
                + (
                    f" / {max_words} maximum"
                    if max_words is not None
                    else ""
                )
            ),
            (
                "- Verified previous artifacts: "
                + (
                    ", ".join(
                        f"`{receipt['type']}:{receipt['path']}@{receipt['sha256']}`"
                        for receipt in artifact_receipts
                    )
                    if artifact_receipts
                    else "none required"
                )
            ),
            "",
            answer,
            "",
        ])
        next_prompt = f"[Eval decision event {scripted['event_id']}]\n{answer}"

    if final_result is None:
        return fail(
            "scripted-protocol-error",
            "scripted scenario ended without an exact final assistant result",
            None,
        )
    try:
        final_output_receipt = persist_final_output(
            out_dir, scenario["id"], final_result
        )
    except (OSError, UnicodeError) as exc:
        return fail(
            "final-output-persistence",
            f"could not persist exact final assistant result: {exc}",
            None,
        )
    persist()
    record.update({
        "status": "pass",
        "returncode": 0,
        "claude_commands": commands,
        "scripted_decisions": decisions,
        "reported_cost_usd": reported_cost,
        "session_id": session_id,
        "final_output": final_output_receipt,
    })
    print(
        f"{scenario['id']}: wrote {rel(root, output_file)} "
        f"({len(decisions)} scripted decision event(s))"
    )
    return record


def check_execute_preconditions(args, scenarios: list[dict]) -> None:
    if args.max_budget_usd is None:
        raise ValueError("--execute requires --max-budget-usd so eval spend is explicit")
    if not math.isfinite(args.max_budget_usd) or args.max_budget_usd <= 0:
        raise ValueError("--max-budget-usd must be a finite positive number")
    if args.timeout is not None and args.timeout <= 0:
        raise ValueError("--timeout must be positive")
    recommendations: list[tuple[dict, float]] = []
    for scenario in scenarios:
        value = scenario.get("recommended_budget_usd")
        if not is_finite_positive_number(value):
            raise ValueError(
                f"{scenario.get('id', '<unknown>')}: recommended_budget_usd "
                "must be a finite positive number"
            )
        recommendations.append((scenario, float(value)))
    recommended = max(value for _, value in recommendations)
    if args.max_budget_usd < recommended and not args.allow_low_budget:
        ids = ", ".join(
            scenario["id"]
            for scenario, value in recommendations
            if value == recommended
        )
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
    if scenario.get("scripted_turns"):
        record["scripted_turn_count"] = len(scenario["scripted_turns"])
        record["scripted_event_ids"] = [
            turn["event_id"] for turn in scenario["scripted_turns"]
        ]
    if initial_git_state is not None:
        record["git_state"] = {"before": initial_git_state}

    if args.dry_run:
        budget = scenario.get("recommended_budget_usd")
        budget_note = f" (recommended budget: ${budget:g})" if isinstance(budget, (int, float)) else ""
        print(f"{scenario['id']}: would run in {rel(root, work_dir)}{budget_note}")
        print("  " + " ".join(json.dumps(part) if " " in part else part for part in cmd))
        if scenario.get("scripted_turns"):
            print(
                "  then resume with context-checked decision event(s): "
                + ", ".join(record["scripted_event_ids"])
            )
        return record

    if scenario.get("scripted_turns"):
        record = run_scripted_turns(
            args,
            root,
            scenario,
            work_dir,
            out_dir,
            output_file,
            timeout_seconds,
            record,
        )
        try:
            record["git_state"]["after"] = capture_git_state(work_dir)
        except ValueError as git_exc:
            record["git_state"]["capture_error"] = str(git_exc)
            if record.get("status") == "pass":
                record.update({
                    "status": "failed",
                    "failure_kind": "git-state-error",
                    "failure_message": str(git_exc),
                })
                print(
                    f"{scenario['id']}: final Git-state capture failed: {git_exc}",
                    file=sys.stderr,
                )
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
    if proc.returncode == 0:
        try:
            record["final_output"] = persist_final_output(
                out_dir, scenario["id"], proc.stdout
            )
        except (OSError, UnicodeError) as exc:
            record.update({
                "status": "failed",
                "failure_kind": "final-output-persistence",
                "failure_message": f"could not persist exact final assistant result: {exc}",
            })
            print(
                f"{scenario['id']}: could not persist exact final assistant result: {exc}",
                file=sys.stderr,
            )
    try:
        record["git_state"]["after"] = capture_git_state(work_dir)
    except ValueError as git_exc:
        record["git_state"]["capture_error"] = str(git_exc)
        if record.get("status") == "pass":
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
        error_payload = parse_claude_json_payload(proc.stdout)
        failed_cost = payload_reported_cost(error_payload)
        if failed_cost is not None:
            record["reported_cost_usd"] = failed_cost
            record["failed_turn_reported_cost_usd"] = failed_cost
        if is_budget_exceeded(combined, error_payload):
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
    elif record.get("status") == "pass":
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
            "model", "effort", "claude_cli", "plugin_manifests", "grade_status",
            "grade_returncode", "graded_scenarios",
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
    claude_cli: dict,
    plugin_manifests: list[dict],
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
        "claude_cli": claude_cli,
        "plugin_manifests": plugin_manifests,
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
        if args.max_budget_usd is not None and (
            not math.isfinite(args.max_budget_usd) or args.max_budget_usd <= 0
        ):
            raise ValueError("--max-budget-usd must be a finite positive number")
        started_at = utc_timestamp()
        run_id = default_run_id()
        data = load_scenarios(root)
        catalog_errors, _ = validate_catalog(root, data["scenarios"])
        if catalog_errors:
            raise ValueError(
                "eval catalog validation failed:\n- " + "\n- ".join(catalog_errors)
            )
        selected = select_scenarios(
            data["scenarios"], args.scenario, args.profile, args.all
        )
        if args.execute:
            check_execute_preconditions(args, selected)
        claude_cli = capture_claude_cli_provenance(args, root)
        plugin_manifests = capture_plugin_manifest_provenance(root)
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
            out_dir, args, records, source_provenance, run_id, started_at, utc_timestamp(),
            claude_cli, plugin_manifests,
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
