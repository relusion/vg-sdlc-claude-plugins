#!/usr/bin/env python3
"""Create and check a current, release-consumable verification receipt.

`create` derives `verification-summary.json` from the canonical plan,
verification report, feature authorities, specs, tasks, implementation evidence,
task-declared implementation files, and the complete reviewable repository
state. `check` re-derives those inputs and rejects stale or contradictory
evidence before evaluating the selected feature verdicts.

The summary is evidence, not approval. A current receipt can still return FAIL
when behavior is unverified, implementation is incomplete, or stakeholder
acceptance is rejected/deferred.

Exit codes:
    0  CREATE succeeded, or CHECK found current passing evidence
    1  CHECK found current evidence with a failing release predicate
    2  missing, malformed, unsafe, stale, or otherwise unprovable evidence
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


SCHEMA_VERSION = 1
SUMMARY_NAME = "verification-summary.json"
REPORT_NAME = "verification-report.md"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
FEATURE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOP_KEYS = {
    "schema_version",
    "plan_slug",
    "plan_revision",
    "plan_sha256",
    "evaluated_commit",
    "repository_state_sha256",
    "verification_report",
    "features",
}
REPORT_KEYS = {"path", "sha256"}
FEATURE_KEYS = {
    "feature_id",
    "feature_path",
    "feature_sha256",
    "spec_path",
    "spec_revision",
    "spec_sha256",
    "tasks_path",
    "tasks_sha256",
    "implementation_verification_path",
    "implementation_verification_sha256",
    "implementation_files_sha256",
    "implementation_status",
    "verdict",
    "acceptance",
}
VERDICTS = {"verified", "partial", "failed"}
ACCEPTANCE = {"accepted", "not-required", "rejected", "deferred", "unknown"}
IMPLEMENTATION_STATES = {"implemented", "in-progress"}


class VerificationGateError(RuntimeError):
    """Evidence cannot be derived or trusted."""


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except OSError as exc:
        raise VerificationGateError(f"could not hash {path}: {exc}") from exc
    return digest.hexdigest()


def regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise VerificationGateError(
            f"{label} must be a regular non-symlink file: {path}"
        )
    try:
        if path.stat().st_nlink != 1:
            raise VerificationGateError(f"{label} must not be hard-linked: {path}")
    except OSError as exc:
        raise VerificationGateError(f"could not inspect {label}: {path}: {exc}") from exc
    return path


def load_json_object(path: Path, label: str) -> dict:
    regular_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise VerificationGateError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise VerificationGateError(f"{label} must contain one JSON object")
    return value


def inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_relative(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerificationGateError(f"{label} must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = normalized.split("/")
    if (
        normalized.startswith("/")
        or not normalized
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise VerificationGateError(
            f"{label} must be normalized and repository-relative: {value!r}"
        )
    return normalized


def git_toplevel(path: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerificationGateError(f"Git repository discovery failed: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise VerificationGateError(
            f"verification freshness requires a Git worktree: {detail or path}"
        )
    return Path(result.stdout.strip()).resolve()


def resolve_commit(repo_root: Path, revision: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{revision}^{{commit}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerificationGateError(f"could not resolve evaluated commit: {exc}") from exc
    candidate = result.stdout.strip().lower()
    if result.returncode != 0 or COMMIT_RE.fullmatch(candidate) is None:
        detail = result.stderr.strip() or result.stdout.strip()
        raise VerificationGateError(
            f"evaluated commit {revision!r} is not a commit: {detail or 'unresolved'}"
        )
    return candidate


def commit_is_ancestor(repo_root: Path, recorded: str, current: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", recorded, current],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerificationGateError(f"could not compare evaluated commits: {exc}") from exc
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    detail = result.stderr.strip() or result.stdout.strip()
    raise VerificationGateError(
        f"could not compare evaluated commits: {detail or result.returncode}"
    )


def review_evidence_excluded(relative: str, plan_relative_root: str) -> bool:
    """Exclude only workflow evidence expected after behavior was evaluated."""
    path = Path(relative)
    if ".git" in path.parts:
        return True
    prefix = Path(plan_relative_root)
    try:
        plan_relative = path.relative_to(prefix)
    except ValueError:
        return False
    parts = plan_relative.parts
    if parts in {
        (".metrics.jsonl",),
        ("STATUS.md",),
        (REPORT_NAME,),
        (SUMMARY_NAME,),
        ("code-review.md",),
        ("review-learnings.md",),
    }:
        return True
    if parts and parts[0] in {"ce-auto-build", "evidence"}:
        return True
    if (
        len(parts) >= 3
        and parts[0] == "specs"
        and parts[2] == "evidence"
    ):
        return True
    return (
        len(parts) == 3
        and parts[0] == "specs"
        and parts[2] in {"review-summary.json", "code-review.md"}
    )


def repository_state_records(repo_root: Path, plan_dir: Path) -> list[dict]:
    try:
        plan_relative_root = plan_dir.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise VerificationGateError(
            f"plan directory escapes repository root: {plan_dir}"
        ) from exc
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise VerificationGateError(f"repository-state file listing failed: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise VerificationGateError(
            f"repository-state file listing failed: {detail or result.returncode}"
        )
    paths = sorted(
        value
        for value in result.stdout.split("\0")
        if value and not review_evidence_excluded(value, plan_relative_root)
    )
    records: list[dict] = []
    for relative in paths:
        path = repo_root / relative
        if not inside(repo_root, path):
            raise VerificationGateError(
                f"repository-state path escapes root: {relative}"
            )
        if path.is_symlink():
            try:
                target = os.readlink(path)
            except OSError as exc:
                raise VerificationGateError(
                    f"repository-state symlink is unreadable: {relative}: {exc}"
                ) from exc
            records.append({"path": relative, "state": "symlink", "target": target})
        elif path.is_file():
            records.append(
                {
                    "path": relative,
                    "state": "file",
                    "sha256": file_sha256(path),
                    "executable": bool(path.stat().st_mode & 0o111),
                }
            )
        elif not path.exists():
            # Index-tracked files deleted from the worktree are absent from the
            # evaluated state, matching a materialized tree after deletion.
            continue
        else:
            raise VerificationGateError(
                f"repository-state path changed while hashing: {relative}"
            )
    return records


def worktree_commit_differences(
    repo_root: Path, plan_dir: Path, evaluated_commit: str
) -> list[str]:
    """Return non-evidence paths whose worktree state differs from the commit.

    Receipt hashes are derived from the worktree because verification itself may
    produce uncommitted evidence. Release checking must additionally prove that
    every non-evidence byte being hashed materializes the explicitly evaluated
    commit; commit ancestry alone does not establish that relationship.
    """
    try:
        plan_relative_root = (
            plan_dir.resolve().relative_to(repo_root.resolve()).as_posix()
        )
    except ValueError as exc:
        raise VerificationGateError(
            f"plan directory escapes repository root: {plan_dir}"
        ) from exc

    commands = (
        (
            "tracked",
            [
                "git",
                "-C",
                str(repo_root),
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--ignore-submodules=none",
                "--name-only",
                "-z",
                evaluated_commit,
                "--",
            ],
        ),
        (
            "untracked",
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
            ],
        ),
    )
    differences: set[str] = set()
    for label, command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise VerificationGateError(
                f"could not compare {label} worktree state to evaluated commit: {exc}"
            ) from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise VerificationGateError(
                f"could not compare {label} worktree state to evaluated commit: "
                f"{detail or result.returncode}"
            )
        try:
            decoded = result.stdout.decode("utf-8")
        except UnicodeError as exc:
            raise VerificationGateError(
                f"{label} worktree path listing is not valid UTF-8: {exc}"
            ) from exc
        differences.update(
            relative
            for relative in decoded.split("\0")
            if relative
            and not review_evidence_excluded(relative, plan_relative_root)
        )
    return sorted(differences)


def require_worktree_materializes_commit(
    repo_root: Path, plan_dir: Path, evaluated_commit: str
) -> None:
    differences = worktree_commit_differences(
        repo_root, plan_dir, evaluated_commit
    )
    if not differences:
        return
    preview = ", ".join(repr(path) for path in differences[:20])
    remainder = len(differences) - 20
    suffix = f" (+{remainder} more)" if remainder > 0 else ""
    raise VerificationGateError(
        "verification binding is stale or mismatched: worktree does not "
        "materialize evaluated commit for non-evidence "
        f"path(s): {preview}{suffix}"
    )


def implementation_file_records(tasks: dict, repo_root: Path) -> list[dict]:
    rows = tasks.get("tasks")
    if not isinstance(rows, list) or not rows:
        raise VerificationGateError("tasks.json tasks must be a non-empty array")
    declared: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise VerificationGateError(f"tasks.json tasks[{index}] must be an object")
        files = row.get("files")
        if not isinstance(files, list) or not files:
            raise VerificationGateError(
                f"tasks.json tasks[{index}].files must be a non-empty array"
            )
        for file_index, value in enumerate(files):
            declared.add(
                safe_relative(
                    value,
                    label=f"tasks.json tasks[{index}].files[{file_index}]",
                )
            )
    records: list[dict] = []
    for relative in sorted(declared):
        path = repo_root / relative
        if not inside(repo_root, path):
            raise VerificationGateError(
                f"task-declared implementation file escapes root: {relative}"
            )
        if path.is_symlink():
            raise VerificationGateError(
                f"task-declared implementation file must not be a symlink: {relative}"
            )
        if not path.exists():
            records.append({"path": relative, "state": "missing", "sha256": None})
        elif not path.is_file():
            raise VerificationGateError(
                f"task-declared implementation path is not a file: {relative}"
            )
        else:
            records.append(
                {
                    "path": relative,
                    "state": "file",
                    "sha256": file_sha256(path),
                    "executable": bool(path.stat().st_mode & 0o111),
                }
            )
    return records


def split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    body = stripped[1:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in body:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def normalize_verdict(value: str) -> str:
    lowered = re.sub(r"[*_`]", "", value).strip().lower()
    if lowered in {"yes", "verified", "pass", "passed"}:
        return "verified"
    if lowered.startswith("partial"):
        return "partial"
    if lowered in {"no", "failed", "fail", "blocked"}:
        return "failed"
    raise VerificationGateError(
        f"unrecognized Per-Feature Status Verified value: {value!r}"
    )


def normalize_acceptance(value: str) -> str:
    lowered = re.sub(r"[*_`]", "", value).strip().lower()
    if lowered in {"yes", "accepted", "accept"}:
        return "accepted"
    if lowered in {"n-a", "n/a", "na", "not-required", "not required"}:
        return "not-required"
    if lowered in {"no", "rejected", "reject"}:
        return "rejected"
    if lowered in {"deferred", "defer"}:
        return "deferred"
    if lowered in {"unknown", "pending", ""}:
        return "unknown"
    raise VerificationGateError(
        f"unrecognized Per-Feature Status Accepted value: {value!r}"
    )


def parse_feature_status(report_path: Path) -> dict[str, dict[str, str]]:
    regular_file(report_path, REPORT_NAME)
    try:
        text = report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise VerificationGateError(
            f"{REPORT_NAME} is not readable UTF-8: {exc}"
        ) from exc
    matches = list(
        re.finditer(r"^## Per-Feature Status(?:\s+.*)?$", text, re.MULTILINE)
    )
    if len(matches) != 1:
        raise VerificationGateError(
            f"{REPORT_NAME} must contain exactly one Per-Feature Status section"
        )
    start = matches[0].end()
    next_heading = re.search(r"^##\s+", text[start:], re.MULTILINE)
    section = text[start : start + next_heading.start()] if next_heading else text[start:]
    table_lines = [line for line in section.splitlines() if line.strip().startswith("|")]
    if len(table_lines) < 3:
        raise VerificationGateError(
            f"{REPORT_NAME} Per-Feature Status must contain a header and feature rows"
        )
    header = [re.sub(r"\s+", " ", cell).strip().lower() for cell in split_markdown_row(table_lines[0])]
    required = ["feature", "implemented", "journeys pass", "criteria ok", "accepted", "verified"]
    if header != required:
        raise VerificationGateError(
            f"{REPORT_NAME} Per-Feature Status header must be {required!r}"
        )
    separator = split_markdown_row(table_lines[1])
    if len(separator) != len(required) or any(
        re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) is None
        for cell in separator
    ):
        raise VerificationGateError(
            f"{REPORT_NAME} Per-Feature Status separator is malformed"
        )
    result: dict[str, dict[str, str]] = {}
    for line in table_lines[2:]:
        cells = split_markdown_row(line)
        if len(cells) != len(required):
            raise VerificationGateError(
                f"{REPORT_NAME} Per-Feature Status row has {len(cells)} cells, "
                f"expected {len(required)}: {line!r}"
            )
        feature_id = re.sub(r"[*_`]", "", cells[0]).strip()
        if FEATURE_ID_RE.fullmatch(feature_id) is None:
            raise VerificationGateError(
                f"invalid feature id in Per-Feature Status: {feature_id!r}"
            )
        if feature_id in result:
            raise VerificationGateError(
                f"duplicate feature row in Per-Feature Status: {feature_id}"
            )
        result[feature_id] = {
            "verdict": normalize_verdict(cells[5]),
            "acceptance": normalize_acceptance(cells[4]),
        }
    if not result:
        raise VerificationGateError(
            f"{REPORT_NAME} Per-Feature Status contains no feature rows"
        )
    return result


def derive_feature(
    *,
    plan_dir: Path,
    repo_root: Path,
    manifest_row: dict,
    status: dict[str, str],
) -> dict:
    feature_id = manifest_row.get("id")
    if not isinstance(feature_id, str) or FEATURE_ID_RE.fullmatch(feature_id) is None:
        raise VerificationGateError(f"plan feature has invalid id: {feature_id!r}")
    feature_rel = safe_relative(
        manifest_row.get("file"), label=f"plan feature {feature_id}.file"
    )
    feature_path = plan_dir / feature_rel
    if not inside(plan_dir, feature_path):
        raise VerificationGateError(
            f"plan feature path escapes plan directory: {feature_rel}"
        )
    regular_file(feature_path, f"feature authority {feature_id}")

    spec_rel = f"specs/{feature_id}/ce-spec.md"
    tasks_rel = f"specs/{feature_id}/tasks.json"
    verification_rel = f"specs/{feature_id}/verification.md"
    spec_path = regular_file(plan_dir / spec_rel, f"{feature_id} ce-spec.md")
    tasks_path = regular_file(plan_dir / tasks_rel, f"{feature_id} tasks.json")
    verification_path = regular_file(
        plan_dir / verification_rel, f"{feature_id} implementation verification.md"
    )
    tasks = load_json_object(tasks_path, f"{feature_id} tasks.json")
    if tasks.get("feature_id") != feature_id:
        raise VerificationGateError(
            f"{feature_id} tasks.json feature_id does not match its spec directory"
        )
    revision = tasks.get("spec_revision")
    if type(revision) is not int or revision < 1:
        raise VerificationGateError(
            f"{feature_id} tasks.json spec_revision must be an integer >= 1"
        )
    task_rows = tasks.get("tasks")
    implemented = (
        isinstance(task_rows, list)
        and bool(task_rows)
        and all(
            isinstance(row, dict) and row.get("status") == "done"
            for row in task_rows
        )
    )
    implementation_files = implementation_file_records(tasks, repo_root)
    return {
        "feature_id": feature_id,
        "feature_path": feature_rel,
        "feature_sha256": file_sha256(feature_path),
        "spec_path": spec_rel,
        "spec_revision": revision,
        "spec_sha256": file_sha256(spec_path),
        "tasks_path": tasks_rel,
        "tasks_sha256": file_sha256(tasks_path),
        "implementation_verification_path": verification_rel,
        "implementation_verification_sha256": file_sha256(verification_path),
        "implementation_files_sha256": canonical_sha256(implementation_files),
        "implementation_status": "implemented" if implemented else "in-progress",
        "verdict": status["verdict"],
        "acceptance": status["acceptance"],
    }


def derive_summary(
    plan_dir: Path,
    *,
    repo_root: Path,
    evaluated_commit: str,
) -> dict:
    plan_dir = plan_dir.resolve()
    repo_root = repo_root.resolve()
    if git_toplevel(repo_root) != repo_root:
        raise VerificationGateError(
            f"--repo-root must be the Git worktree root: {repo_root}"
        )
    if not inside(repo_root, plan_dir):
        raise VerificationGateError(
            f"plan directory escapes repository root: {plan_dir}"
        )
    plan_path = plan_dir / "plan.json"
    manifest = load_json_object(plan_path, "plan.json")
    slug = manifest.get("project_slug")
    if not isinstance(slug, str) or slug != plan_dir.name:
        raise VerificationGateError(
            "plan.json project_slug must match the plan directory name"
        )
    revision = manifest.get("plan_revision")
    if type(revision) is not int or revision < 1:
        raise VerificationGateError("plan.json plan_revision must be an integer >= 1")
    rows = manifest.get("features")
    if not isinstance(rows, list) or not rows:
        raise VerificationGateError("plan.json features must be a non-empty array")
    by_id: dict[str, dict] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise VerificationGateError(f"plan.json features[{index}] must be an object")
        feature_id = row.get("id")
        if not isinstance(feature_id, str) or FEATURE_ID_RE.fullmatch(feature_id) is None:
            raise VerificationGateError(
                f"plan.json features[{index}].id is invalid: {feature_id!r}"
            )
        if feature_id in by_id:
            raise VerificationGateError(f"duplicate plan feature id: {feature_id}")
        by_id[feature_id] = row

    report_path = plan_dir / REPORT_NAME
    report_status = parse_feature_status(report_path)
    unknown = sorted(set(report_status) - set(by_id))
    if unknown:
        raise VerificationGateError(
            f"{REPORT_NAME} references feature(s) absent from plan.json: "
            + ", ".join(unknown)
        )
    features = [
        derive_feature(
            plan_dir=plan_dir,
            repo_root=repo_root,
            manifest_row=row,
            status=report_status[feature_id],
        )
        for feature_id, row in by_id.items()
        if feature_id in report_status
    ]
    if not features:
        raise VerificationGateError("no plan feature has verification status evidence")

    return {
        "schema_version": SCHEMA_VERSION,
        "plan_slug": slug,
        "plan_revision": revision,
        "plan_sha256": file_sha256(plan_path),
        "evaluated_commit": evaluated_commit,
        "repository_state_sha256": canonical_sha256(
            repository_state_records(repo_root, plan_dir)
        ),
        "verification_report": {
            "path": REPORT_NAME,
            "sha256": file_sha256(report_path),
        },
        "features": features,
    }


def validate_summary_shape(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["summary must contain one JSON object"]
    errors: list[str] = []
    missing = sorted(TOP_KEYS - set(data))
    extra = sorted(set(data) - TOP_KEYS)
    if missing:
        errors.append("summary missing key(s): " + ", ".join(missing))
    if extra:
        errors.append("summary has unknown key(s): " + ", ".join(extra))
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must equal {SCHEMA_VERSION}")
    if not isinstance(data.get("plan_slug"), str) or not data.get("plan_slug"):
        errors.append("plan_slug must be non-empty")
    if type(data.get("plan_revision")) is not int or data.get("plan_revision", 0) < 1:
        errors.append("plan_revision must be an integer >= 1")
    for key in ("plan_sha256", "repository_state_sha256"):
        value = data.get(key)
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            errors.append(f"{key} must be 64 lowercase hex")
    commit = data.get("evaluated_commit")
    if not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None:
        errors.append("evaluated_commit must be a 40-64 lowercase hex commit id")
    report = data.get("verification_report")
    if not isinstance(report, dict):
        errors.append("verification_report must be an object")
    else:
        if set(report) != REPORT_KEYS:
            errors.append(
                "verification_report must contain exactly path and sha256"
            )
        if report.get("path") != REPORT_NAME:
            errors.append(f"verification_report.path must equal {REPORT_NAME!r}")
        digest = report.get("sha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            errors.append("verification_report.sha256 must be 64 lowercase hex")
    features = data.get("features")
    if not isinstance(features, list) or not features:
        errors.append("features must be a non-empty array")
        return errors
    seen: set[str] = set()
    for index, row in enumerate(features):
        label = f"features[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{label} must be an object")
            continue
        if set(row) != FEATURE_KEYS:
            missing_row = sorted(FEATURE_KEYS - set(row))
            extra_row = sorted(set(row) - FEATURE_KEYS)
            if missing_row:
                errors.append(f"{label} missing key(s): " + ", ".join(missing_row))
            if extra_row:
                errors.append(f"{label} has unknown key(s): " + ", ".join(extra_row))
        feature_id = row.get("feature_id")
        if (
            not isinstance(feature_id, str)
            or FEATURE_ID_RE.fullmatch(feature_id) is None
        ):
            errors.append(f"{label}.feature_id is invalid")
        elif feature_id in seen:
            errors.append(f"duplicate feature_id: {feature_id}")
        else:
            seen.add(feature_id)
        for key in (
            "feature_sha256",
            "spec_sha256",
            "tasks_sha256",
            "implementation_verification_sha256",
            "implementation_files_sha256",
        ):
            value = row.get(key)
            if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
                errors.append(f"{label}.{key} must be 64 lowercase hex")
        for key in (
            "feature_path",
            "spec_path",
            "tasks_path",
            "implementation_verification_path",
        ):
            try:
                safe_relative(row.get(key), label=f"{label}.{key}")
            except VerificationGateError as exc:
                errors.append(str(exc))
        if type(row.get("spec_revision")) is not int or row.get("spec_revision", 0) < 1:
            errors.append(f"{label}.spec_revision must be an integer >= 1")
        if row.get("implementation_status") not in IMPLEMENTATION_STATES:
            errors.append(
                f"{label}.implementation_status must be one of "
                f"{sorted(IMPLEMENTATION_STATES)}"
            )
        if row.get("verdict") not in VERDICTS:
            errors.append(f"{label}.verdict must be one of {sorted(VERDICTS)}")
        if row.get("acceptance") not in ACCEPTANCE:
            errors.append(
                f"{label}.acceptance must be one of {sorted(ACCEPTANCE)}"
            )
    return errors


def compare_current(recorded: dict, current: dict) -> list[str]:
    differences: list[str] = []
    for key in TOP_KEYS - {"evaluated_commit"}:
        if recorded.get(key) != current.get(key):
            differences.append(key)
    return sorted(differences)


def atomic_write_summary(output: Path, summary: dict) -> None:
    """Replace the canonical receipt without following an output symlink.

    `mkstemp` creates an unpredictable sibling with O_CREAT|O_EXCL. The complete
    payload is flushed before `os.replace` atomically installs that inode at the
    destination name; replacing a raced-in symlink replaces the link itself
    rather than opening its target.
    """
    payload = (
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=str(output.parent),
        )
        temporary = Path(temporary_name)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise VerificationGateError(
                f"verification summary temporary is not an exclusive regular file: "
                f"{temporary}"
            )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        installed = temporary.lstat()
        if (
            not stat.S_ISREG(installed.st_mode)
            or installed.st_nlink != 1
            or installed.st_dev != opened.st_dev
            or installed.st_ino != opened.st_ino
        ):
            raise VerificationGateError(
                "verification summary temporary changed before atomic replace"
            )
        os.replace(temporary, output)
        temporary = None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def create_summary(
    plan_dir: Path,
    *,
    repo_root: Path,
    output: Path,
    evaluated_commit: str,
) -> tuple[int, dict]:
    try:
        current_commit = resolve_commit(repo_root, evaluated_commit)
        summary = derive_summary(
            plan_dir,
            repo_root=repo_root,
            evaluated_commit=current_commit,
        )
        expected = plan_dir.resolve() / SUMMARY_NAME
        if output.resolve() != expected:
            raise VerificationGateError(
                f"verification summary output must be the canonical path: {expected}"
            )
        if output.is_symlink():
            raise VerificationGateError(
                f"verification summary output must not be a symlink: {output}"
            )
        if output.exists():
            regular_file(output, SUMMARY_NAME)
        atomic_write_summary(output, summary)
        regular_file(output, SUMMARY_NAME)
        reread = load_json_object(output, SUMMARY_NAME)
        if reread != summary:
            raise VerificationGateError(
                "verification summary changed during the write transaction"
            )
    except (OSError, VerificationGateError) as exc:
        return 2, {
            "status": "error",
            "summary": str(output),
            "message": str(exc),
        }
    return 0, {
        "status": "created",
        "summary": str(output),
        "plan_slug": summary["plan_slug"],
        "evaluated_commit": current_commit,
        "repository_state_sha256": summary["repository_state_sha256"],
        "features": [
            {
                "feature_id": row["feature_id"],
                "implementation_status": row["implementation_status"],
                "verdict": row["verdict"],
                "acceptance": row["acceptance"],
            }
            for row in summary["features"]
        ],
    }


def check_summary(
    plan_dir: Path,
    *,
    repo_root: Path,
    summary_path: Path,
    selected_features: list[str],
    evaluated_commit: str,
) -> tuple[int, dict]:
    base = {"summary": str(summary_path), "plan_dir": str(plan_dir)}
    try:
        recorded = load_json_object(summary_path, SUMMARY_NAME)
        shape_errors = validate_summary_shape(recorded)
        if shape_errors:
            raise VerificationGateError(
                "verification summary has invalid schema: " + "; ".join(shape_errors)
            )
        current_commit = resolve_commit(repo_root, evaluated_commit)
        recorded_commit = recorded["evaluated_commit"]
        if not commit_is_ancestor(repo_root, recorded_commit, current_commit):
            raise VerificationGateError(
                f"recorded evaluated commit {recorded_commit} is not an ancestor "
                f"of {current_commit}"
            )
        require_worktree_materializes_commit(
            repo_root, plan_dir, current_commit
        )
        current = derive_summary(
            plan_dir,
            repo_root=repo_root,
            evaluated_commit=current_commit,
        )
        # Recheck after hashing so a concurrent checkout cannot silently make
        # the derived worktree binding refer to a different candidate commit.
        require_worktree_materializes_commit(
            repo_root, plan_dir, current_commit
        )
        differences = compare_current(recorded, current)
        if differences:
            raise VerificationGateError(
                "verification binding is stale or mismatched for: "
                + ", ".join(differences)
            )
        by_id = {row["feature_id"]: row for row in recorded["features"]}
        targets = selected_features or list(by_id)
        if len(targets) != len(set(targets)):
            raise VerificationGateError("--feature contains duplicate feature ids")
        missing = sorted(set(targets) - set(by_id))
        if missing:
            raise VerificationGateError(
                "verification summary does not cover requested feature(s): "
                + ", ".join(missing)
            )
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        VerificationGateError,
    ) as exc:
        return 2, {
            **base,
            "status": "error",
            "message": str(exc),
        }

    rows = [by_id[feature_id] for feature_id in targets]
    hard_failures: list[str] = []
    for row in rows:
        feature_id = row["feature_id"]
        if row["implementation_status"] != "implemented":
            hard_failures.append(f"{feature_id}: implementation is not complete")
        if row["verdict"] != "verified":
            hard_failures.append(
                f"{feature_id}: verification verdict is {row['verdict']}"
            )
        if row["acceptance"] not in {"accepted", "not-required"}:
            hard_failures.append(
                f"{feature_id}: acceptance is {row['acceptance']}"
            )
    result = {
        **base,
        "status": "fail" if hard_failures else "pass",
        "plan_slug": recorded["plan_slug"],
        "plan_revision": recorded["plan_revision"],
        "evaluated_commit": current_commit,
        "recorded_evaluated_commit": recorded["evaluated_commit"],
        "repository_state_sha256": recorded["repository_state_sha256"],
        "binding_status": "current",
        "features": [
            {
                "feature_id": row["feature_id"],
                "implementation_status": row["implementation_status"],
                "verdict": row["verdict"],
                "acceptance": row["acceptance"],
            }
            for row in rows
        ],
        "hard_failures": hard_failures,
    }
    return (1 if hard_failures else 0), result


def emit(result: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, sort_keys=True))
    else:
        status = str(result.get("status", "error")).upper()
        print(f"verification-gate: {status} — {result.get('message', '')}".rstrip())
        for item in result.get("hard_failures", []):
            print(f"- {item}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or check a current verification-summary.json receipt."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "check"):
        sub = subparsers.add_parser(name)
        sub.add_argument("plan_dir", type=Path)
        sub.add_argument("--repo-root", type=Path, default=Path("."))
        sub.add_argument(
            "--evaluated-commit",
            default="HEAD",
            help="exact release/verification commit-ish (default HEAD)",
        )
        sub.add_argument("--json", action="store_true")
        if name == "create":
            sub.add_argument("--output", type=Path)
        else:
            sub.add_argument("--summary", type=Path)
            sub.add_argument(
                "--feature",
                action="append",
                default=[],
                help="feature id required for this release range; repeat as needed",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan_dir = args.plan_dir.resolve()
    repo_root = args.repo_root.resolve()
    if args.command == "create":
        output = (
            args.output.resolve()
            if args.output is not None
            else plan_dir / SUMMARY_NAME
        )
        code, result = create_summary(
            plan_dir,
            repo_root=repo_root,
            output=output,
            evaluated_commit=args.evaluated_commit,
        )
    else:
        summary = (
            args.summary.resolve()
            if args.summary is not None
            else plan_dir / SUMMARY_NAME
        )
        code, result = check_summary(
            plan_dir,
            repo_root=repo_root,
            summary_path=summary,
            selected_features=args.feature,
            evaluated_commit=args.evaluated_commit,
        )
    emit(result, as_json=args.json)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
