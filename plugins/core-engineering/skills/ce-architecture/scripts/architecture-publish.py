#!/usr/bin/env python3
"""Transactionally publish one reviewed ce-architecture schema-v2 package.

The helper verifies deterministic review bytes and digests, enforces revision
and human approval identity/authority/reference, copies the exact five files
into a same-parent stage, and changes only ``lifecycle_status`` plus the strict
approval receipt.  The swap uses two same-filesystem renames, so it has a known
crash window between backup and install; orphan transaction paths make recovery
explicit. A final lint failure restores the prior package (or first-publish
absence).

Exit codes:
  0  PUBLISHED — the canonical package passed its final lint.
  1  REFUSED / ROLLED BACK — a deterministic precondition or lint failed and
     the previous state was preserved.
  2  ERROR — the operation could not run or rollback could not be proven.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
ARCHITECTURE_SCHEMA_VERSION = 2
ARCHITECTURE_SCHEMA_URN = "urn:vg-sdlc:ce-architecture:architecture:v2"
PACKAGE_FILES = {
    "solution-architecture.md",
    "views.md",
    "data-and-integrations.md",
    "quality-attributes.md",
    "architecture.json",
}
PUBLISHED_STATUSES = {
    "accepted-for-specification",
    "accepted-for-specification-with-gaps",
}
RESET_FIELD = "revision_reset"
RESET_GATE = "Invalid Architecture Package Recovery"
FINAL_APPROVAL_GATE = "Final Architecture Approval"
PENDING_APPROVAL = {
    "decision": "pending",
    "recorded_by": "pending",
    "recorded_at": None,
    "authority": None,
    "reference": None,
    "gate": FINAL_APPROVAL_GATE,
    "review_payload_sha256": None,
    "receipt_sha256": None,
}
TRANSACTION_PREFIX = ".architecture-publish-"
TRANSACTION_LOCK = f"{TRANSACTION_PREFIX}lock"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINT_TIMEOUT_SECONDS = 30
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
RFC3339_UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
APPROVAL_PLACEHOLDER_RE = re.compile(
    r"^(?:pending|human|unknown|tbd|todo|placeholder|<[^>]+>)$",
    re.IGNORECASE,
)


class PublishInputError(Exception):
    """A deterministic publication precondition was not met (exit 1)."""


class PublishRuntimeError(Exception):
    """The publication helper could not safely complete (exit 2)."""


def _strict_manifest_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise PublishInputError(f"duplicate architecture.json key: {key}")
        result[key] = value
    return result


def _strict_manifest_loads(payload: str) -> object:
    return json.loads(payload, object_pairs_hook=_strict_manifest_pairs)


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except (OSError, ValueError):
        return False


def _symlink_components(base: Path, candidate: Path) -> list[str]:
    """List symlink components below a resolved repository root."""
    try:
        relative = candidate.relative_to(base)
    except ValueError:
        return [str(candidate)]
    current = base
    found: list[str] = []
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            found.append(current.relative_to(base).as_posix())
    return found


def _remove_path(path: Path) -> None:
    """Remove one known transaction path without following a symlink."""
    if not _lexists(path):
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _read_manifest(path: Path, *, label: str) -> dict:
    manifest_path = path / "architecture.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PublishInputError(f"{label} architecture.json must be a regular file")
    try:
        data = _strict_manifest_loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishInputError(f"{label} architecture.json is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise PublishInputError(f"{label} architecture.json must contain an object")
    return data


def _package_shape(path: Path) -> dict:
    """Return exact-file-set facts without following package entries."""
    if path.is_symlink() or not path.is_dir():
        return {
            "is_directory": False,
            "missing": sorted(PACKAGE_FILES),
            "extra": [],
            "symlinks": [path.name] if path.is_symlink() else [],
            "non_regular": [],
        }
    try:
        entries = list(path.iterdir())
    except OSError as exc:
        raise PublishRuntimeError(f"cannot inspect package directory {path}: {exc}") from exc
    names = {entry.name for entry in entries}
    symlinks: list[str] = []
    non_regular: list[str] = []
    for entry in entries:
        try:
            mode = entry.lstat().st_mode
        except OSError as exc:
            raise PublishRuntimeError(f"cannot inspect package entry {entry}: {exc}") from exc
        if stat.S_ISLNK(mode):
            symlinks.append(entry.name)
        elif not stat.S_ISREG(mode):
            non_regular.append(entry.name)
    return {
        "is_directory": True,
        "missing": sorted(PACKAGE_FILES - names),
        "extra": sorted(names - PACKAGE_FILES),
        "symlinks": sorted(symlinks),
        "non_regular": sorted(non_regular),
    }


def _require_exact_scratch(path: Path) -> tuple[dict, dict[str, bytes]]:
    if not path.is_absolute():
        path = path.resolve()
    shape = _package_shape(path)
    problems: list[str] = []
    if not shape["is_directory"]:
        problems.append("scratch path is not a real directory")
    if shape["missing"]:
        problems.append(f"missing: {', '.join(shape['missing'])}")
    if shape["extra"]:
        problems.append(f"unexpected: {', '.join(shape['extra'])}")
    if shape["symlinks"]:
        problems.append(f"symlink entries: {', '.join(shape['symlinks'])}")
    if shape["non_regular"]:
        problems.append(f"non-regular entries: {', '.join(shape['non_regular'])}")
    if problems:
        raise PublishInputError(
            "scratch package must contain exactly five regular files; "
            + "; ".join(problems)
        )
    try:
        snapshot = {
            name: (path / name).read_bytes()
            for name in sorted(PACKAGE_FILES)
        }
    except OSError as exc:
        raise PublishInputError(f"cannot snapshot scratch package: {exc}") from exc
    if _package_shape(path) != shape:
        raise PublishInputError("scratch package changed while it was being inspected")
    try:
        manifest = _strict_manifest_loads(
            snapshot["architecture.json"].decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishInputError(f"scratch architecture.json is unreadable: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PublishInputError("scratch architecture.json must contain an object")
    return manifest, snapshot


def _lint_runtime_error(
    phase: str,
    error: object,
    *,
    process_exit_code: int | None = None,
) -> dict:
    try:
        detail = f"{type(error).__name__}: {error}"
    except Exception:
        detail = type(error).__name__
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "error",
        "hard_failures": [],
        "advisory": [],
        "blocking_hard": 0,
        "error": f"{phase}: {detail}",
        "exit_code": 2,
    }
    if (
        isinstance(process_exit_code, int)
        and not isinstance(process_exit_code, bool)
    ):
        result["process_exit_code"] = process_exit_code
    return result


def run_lint(
    package: Path,
    repo_root: Path,
    *,
    allow_proposed: bool = False,
) -> dict:
    """Run the sibling lint and retain its structured result."""
    script = Path(__file__).resolve().with_name("architecture-lint.py")
    if not script.is_file():
        return _lint_runtime_error(
            "linter execution failed",
            FileNotFoundError(f"sibling linter not found: {script}"),
        )
    try:
        command = [
            sys.executable,
            str(script),
            str(package),
            "--repo-root",
            str(repo_root),
            "--json",
        ]
        if allow_proposed:
            command.append("--allow-proposed")
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=LINT_TIMEOUT_SECONDS,
            cwd=repo_root,
        )
    except Exception as exc:
        return _lint_runtime_error("linter execution failed", exc)
    try:
        process_exit_code = proc.returncode
    except Exception as exc:
        return _lint_runtime_error("linter result decoding failed", exc)
    if not isinstance(process_exit_code, int) or isinstance(process_exit_code, bool):
        return _lint_runtime_error(
            "linter result decoding failed",
            TypeError("linter process returncode was not an integer"),
        )
    try:
        payload = json.loads(proc.stdout)
    except Exception as exc:
        return _lint_runtime_error(
            "linter result decoding failed",
            exc,
            process_exit_code=process_exit_code,
        )
    if not isinstance(payload, dict):
        return _lint_runtime_error(
            "linter result decoding failed",
            TypeError("linter result was not an object"),
            process_exit_code=process_exit_code,
        )
    return {**payload, "exit_code": process_exit_code}


def _load_renderer():
    script = Path(__file__).resolve().with_name("architecture-render.py")
    spec = importlib.util.spec_from_file_location(
        "ce_architecture_publish_renderer", script
    )
    if spec is None or spec.loader is None:
        raise PublishRuntimeError(f"could not load deterministic renderer: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_render_check(package: Path) -> dict:
    try:
        renderer = _load_renderer()
        result, exit_code = renderer.check_package(package)
    except Exception as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "error",
            "mismatches": [],
            "message": f"renderer check failed: {type(exc).__name__}: {exc}",
            "exit_code": 2,
        }
    if not isinstance(result, dict):
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "error",
            "mismatches": [],
            "message": "renderer check returned a non-object",
            "exit_code": 2,
        }
    return {**result, "exit_code": exit_code}


def _assess_render_result(result: object) -> dict:
    if not isinstance(result, dict):
        return {"outcome": "error", "message": "render result must be an object"}
    exit_code = result.get("exit_code")
    status = result.get("status")
    mismatches = result.get("mismatches")
    if (
        not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or exit_code not in {0, 1, 2}
        or not isinstance(status, str)
        or not isinstance(mismatches, list)
        or any(not isinstance(item, str) for item in mismatches)
    ):
        return {"outcome": "error", "message": "invalid renderer result contract"}
    if exit_code == 0 and status == "pass" and not mismatches:
        return {"outcome": "pass", "message": "coherent pass"}
    if exit_code == 1 and status == "mismatch" and mismatches:
        return {
            "outcome": "fail",
            "message": "; ".join(mismatches),
        }
    message = result.get("message")
    return {
        "outcome": "error",
        "message": message if isinstance(message, str) else "renderer check error",
    }


def _validate_reset_record(manifest: dict) -> str:
    reset = manifest.get(RESET_FIELD)
    if not isinstance(reset, dict) or set(reset) != {"reason", "recorded_by", "gate"}:
        raise PublishInputError(
            f"malformed prior recovery requires {RESET_FIELD} with exactly "
            "reason, recorded_by, and gate"
        )
    reason = reset.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise PublishInputError(f"{RESET_FIELD}.reason must be non-empty")
    if reset.get("recorded_by") != "human":
        raise PublishInputError(f"{RESET_FIELD}.recorded_by must be 'human'")
    if reset.get("gate") != RESET_GATE:
        raise PublishInputError(f"{RESET_FIELD}.gate must be {RESET_GATE!r}")
    return reason.strip()


def _manifest_revision(manifest: dict, *, label: str) -> int:
    value = manifest.get("architecture_revision")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise PublishInputError(f"{label} architecture_revision must be an integer >= 1")
    return value


def _freshness_only_failure(lint: dict) -> bool:
    """A stale but readable prior still owns its monotonic revision number."""
    failures = lint.get("hard_failures")
    if lint.get("exit_code") != 1 or not isinstance(failures, list) or not failures:
        return False
    allowed = ("H3 source_plan_revision", "H4 stale source hash")
    return all(isinstance(item, str) and item.startswith(allowed) for item in failures)


def _lint_failure_detail(lint: dict) -> str:
    failures = lint.get("hard_failures")
    if isinstance(failures, list):
        useful = [item for item in failures if isinstance(item, str) and item]
        if useful:
            return "; ".join(useful)
    error = lint.get("error")
    return error if isinstance(error, str) and error else "no failure detail emitted"


def _assess_lint_result(lint: object) -> dict:
    """Require the linter's exit code and JSON contract to agree."""
    problems: list[str] = []
    if not isinstance(lint, dict):
        return {
            "outcome": "error",
            "coherent": False,
            "message": "lint result must be an object",
        }

    schema = lint.get("schema_version")
    if not isinstance(schema, int) or isinstance(schema, bool) or schema != SCHEMA_VERSION:
        problems.append(f"schema_version must be {SCHEMA_VERSION}")
    exit_code = lint.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool) or exit_code not in {0, 1, 2}:
        problems.append("exit_code must be one of 0, 1, or 2")
    status = lint.get("status")
    if not isinstance(status, str) or status not in {"pass", "fail", "error"}:
        problems.append("status must be pass, fail, or error")
    hard = lint.get("hard_failures")
    if not isinstance(hard, list) or not all(isinstance(item, str) for item in hard):
        problems.append("hard_failures must be a list of strings")
        hard = []
    advisory = lint.get("advisory")
    if not isinstance(advisory, list) or not all(
        isinstance(item, str) for item in advisory
    ):
        problems.append("advisory must be a list of strings")
    blocking = lint.get("blocking_hard")
    if not isinstance(blocking, int) or isinstance(blocking, bool) or blocking < 0:
        problems.append("blocking_hard must be a non-negative integer")
    elif blocking != len(hard):
        problems.append("blocking_hard must equal len(hard_failures)")

    if not problems:
        if exit_code == 0 and status == "pass" and blocking == 0 and hard == []:
            return {"outcome": "pass", "coherent": True, "message": "coherent pass"}
        if exit_code == 1 and status == "fail" and blocking > 0 and hard:
            return {"outcome": "fail", "coherent": True, "message": "coherent fail"}
        if exit_code == 2 and status == "error" and blocking == 0 and hard == []:
            error = lint.get("error")
            if isinstance(error, str) and error:
                return {
                    "outcome": "error",
                    "coherent": True,
                    "message": f"coherent linter error: {error}",
                }
            problems.append("status=error requires a non-empty error string")
        else:
            problems.append("exit_code, status, blocking_hard, and hard_failures disagree")

    return {
        "outcome": "error",
        "coherent": False,
        "message": "invalid lint result: " + "; ".join(problems),
    }


def _inspect_prior(
    target: Path,
    repo_root: Path,
    slug: str,
    *,
    allow_extra_cleanup: bool,
) -> dict:
    if not _lexists(target):
        return {
            "state": "absent",
            "revision": None,
            "lint": None,
            "lint_validation": None,
            "shape": None,
        }

    shape = _package_shape(target)
    if shape["extra"] and not allow_extra_cleanup:
        raise PublishInputError(
            "existing architecture package has unexpected entries; explicit "
            "--allow-extra-cleanup is required: " + ", ".join(shape["extra"])
        )

    manifest: dict | None = None
    revision: int | None = None
    manifest_error: str | None = None
    if shape["is_directory"] and "architecture.json" not in shape["missing"] \
            and "architecture.json" not in shape["symlinks"] \
            and "architecture.json" not in shape["non_regular"]:
        try:
            manifest = _read_manifest(target, label="existing")
            revision = _manifest_revision(manifest, label="existing")
        except PublishInputError as exc:
            manifest_error = str(exc)

    exact_safe = (
        shape["is_directory"]
        and not shape["missing"]
        and not shape["extra"]
        and not shape["symlinks"]
        and not shape["non_regular"]
    )
    lint = (
        run_lint(target, repo_root)
        if exact_safe and manifest is not None and revision is not None
        else None
    )
    lint_validation = _assess_lint_result(lint) if lint is not None else None
    if (
        lint_validation is not None
        and lint_validation["outcome"] == "error"
        and not lint_validation["coherent"]
    ):
        raise PublishRuntimeError(
            "existing architecture lint could not be trusted: "
            + lint_validation["message"]
        )
    if manifest is not None and revision is not None:
        slug_matches = manifest.get("project_slug") == slug
        if lint_validation is not None and lint_validation["outcome"] == "pass" and slug_matches:
            return {
                "state": "valid",
                "revision": revision,
                "lint": lint,
                "lint_validation": lint_validation,
                "shape": shape,
            }
        if lint_validation is not None and slug_matches and _freshness_only_failure(lint):
            return {
                "state": "stale",
                "revision": revision,
                "lint": lint,
                "lint_validation": lint_validation,
                "shape": shape,
            }
        return {
            "state": "invalid-readable",
            "revision": revision,
            "lint": lint,
            "lint_validation": lint_validation,
            "shape": shape,
            "manifest_error": (
                None
                if slug_matches
                else (
                    f"existing project_slug {manifest.get('project_slug')!r} "
                    f"does not match {slug!r}"
                )
            ),
        }

    return {
        "state": "malformed",
        "revision": None,
        "lint": lint,
        "lint_validation": lint_validation,
        "shape": shape,
        "manifest_error": manifest_error,
    }


def _find_orphan_transactions(
    plan_dir: Path,
    *,
    exclude: set[str] | None = None,
) -> list[str]:
    excluded = exclude or set()
    try:
        return sorted(
            entry.name
            for entry in plan_dir.iterdir()
            if entry.name.startswith(TRANSACTION_PREFIX)
            and entry.name not in excluded
        )
    except OSError as exc:
        raise PublishRuntimeError(f"cannot inspect publication transaction paths: {exc}") from exc


def _inspect_lock_owner(lock_path: Path) -> dict:
    if lock_path.is_symlink() or not lock_path.is_file():
        return {"state": "unsafe-or-non-regular"}
    try:
        owner = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"state": "unreadable", "error": str(exc)}
    if not isinstance(owner, dict):
        return {"state": "unreadable", "error": "lock metadata is not an object"}
    return {**owner, "state": "readable"}


def _acquire_transaction_lock(
    plan_dir: Path,
    target_rel: Path,
) -> tuple[Path | None, str | None, dict]:
    """Acquire the same-parent publisher lock without a check/create race."""
    lock_path = plan_dir / TRANSACTION_LOCK
    token = uuid.uuid4().hex
    owner = {
        "schema_version": SCHEMA_VERSION,
        "pid": os.getpid(),
        "created_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "target": target_rel.as_posix(),
        "token": token,
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except FileExistsError:
        return None, None, {
            "path": TRANSACTION_LOCK,
            "disposition": "blocked-existing",
            "owner": _inspect_lock_owner(lock_path),
        }
    except OSError as exc:
        raise PublishRuntimeError(f"cannot acquire publication transaction lock: {exc}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(owner, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, TypeError, ValueError) as exc:
        try:
            _remove_path(lock_path)
        except OSError:
            pass
        raise PublishRuntimeError(f"cannot record publication lock ownership: {exc}") from exc
    return lock_path, token, {
        "path": TRANSACTION_LOCK,
        "disposition": "acquired",
        "owner": {**owner, "state": "readable"},
    }


def _release_transaction_lock(lock_path: Path, token: str) -> None:
    owner = _inspect_lock_owner(lock_path)
    if owner.get("state") != "readable" or owner.get("token") != token:
        raise PublishRuntimeError(
            "publication transaction lock ownership changed; retained for explicit recovery"
        )
    try:
        lock_path.unlink()
    except OSError as exc:
        raise PublishRuntimeError(f"cannot release publication transaction lock: {exc}") from exc


def _copy_to_stage(
    scratch: Path,
    plan_dir: Path,
    reviewed_bytes: dict[str, bytes],
) -> Path:
    stage = Path(tempfile.mkdtemp(prefix=f"{TRANSACTION_PREFIX}stage-", dir=plan_dir))
    try:
        for name in sorted(PACKAGE_FILES):
            source = scratch / name
            mode = source.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise PublishInputError(f"scratch entry changed during publication: {name}")
            shutil.copy2(source, stage / name, follow_symlinks=False)
            if (stage / name).read_bytes() != reviewed_bytes[name]:
                raise PublishInputError(
                    f"scratch entry changed after review; staged bytes differ: {name}"
                )
    except Exception:
        _remove_path(stage)
        raise
    return stage


def _bind_human_approval(
    stage: Path,
    reviewed_manifest: dict,
    reviewed_manifest_bytes: bytes,
    publish_status: str,
    *,
    recorded_by: str,
    approval_authority: str,
    approval_reference: str,
    approval_time: str,
) -> str:
    """Change only lifecycle/approval while preserving reviewed Markdown bytes."""
    expected = copy.deepcopy(reviewed_manifest)
    expected["lifecycle_status"] = "published"
    expected["approval"] = {
        "decision": publish_status,
        "recorded_by": recorded_by,
        "recorded_at": approval_time,
        "authority": approval_authority,
        "reference": approval_reference,
        "gate": FINAL_APPROVAL_GATE,
        "review_payload_sha256": reviewed_manifest["approval"][
            "review_payload_sha256"
        ],
        "receipt_sha256": None,
    }
    manifest_path = stage / "architecture.json"
    if manifest_path.read_bytes() != reviewed_manifest_bytes:
        raise PublishRuntimeError("staged manifest bytes did not preserve the reviewed manifest")
    try:
        staged = _strict_manifest_loads(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishRuntimeError(f"cannot bind approval to staged manifest: {exc}") from exc
    if staged != reviewed_manifest:
        raise PublishRuntimeError("staged manifest bytes did not preserve the reviewed JSON values")
    try:
        renderer = _load_renderer()
        documents = renderer.render_documents(expected)
        for path, expected_bytes in documents.items():
            if (stage / path).read_bytes() != expected_bytes:
                raise PublishRuntimeError(
                    f"approval binding would change reviewed projection bytes: {path}"
                )
        receipt = renderer.receipt_sha256(expected, documents)
    except PublishRuntimeError:
        raise
    except Exception as exc:
        raise PublishRuntimeError(
            f"cannot compute published approval receipt: {type(exc).__name__}: {exc}"
        ) from exc
    expected["approval"]["receipt_sha256"] = receipt
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".architecture.json.", suffix=".tmp", dir=stage
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(expected, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, manifest_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    try:
        rebound = _strict_manifest_loads(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishRuntimeError(f"cannot verify staged approval binding: {exc}") from exc
    if rebound != expected:
        raise PublishRuntimeError(
            "staged manifest changed values beyond lifecycle_status and approval"
        )
    for key in reviewed_manifest.keys() - {"lifecycle_status", "approval"}:
        if rebound.get(key) != reviewed_manifest.get(key):
            raise PublishRuntimeError(
                f"staged manifest changed reviewed field beyond approval: {key}"
            )
    return receipt


def _rollback(target: Path, backup: Path | None, rejected: Path) -> tuple[bool, str | None]:
    """Restore the exact pre-publication target state."""
    try:
        if _lexists(target):
            os.rename(target, rejected)
        if backup is not None:
            if not _lexists(backup):
                return False, "expected prior-package backup is missing"
            os.rename(backup, target)
        _remove_path(rejected)
        return True, None
    except OSError as exc:
        return False, str(exc)


def publish_package(
    scratch: Path,
    repo_root: Path,
    slug: str,
    *,
    publish_status: str,
    recorded_by: str | None = None,
    approval_authority: str | None = None,
    approval_reference: str | None = None,
    approval_time: str | None = None,
    allow_extra_cleanup: bool = False,
    accept_human_approved_reset: bool = False,
) -> tuple[dict, int]:
    repo_root = repo_root.resolve()
    scratch_input = Path(scratch)
    scratch_is_symlink = scratch_input.is_symlink()
    scratch = scratch_input.resolve()
    target_rel = Path("docs") / "plans" / slug / "architecture"
    target = repo_root / target_rel
    result: dict = {
        "schema_version": SCHEMA_VERSION,
        "status": "refused",
        "scratch": str(scratch),
        "target": target_rel.as_posix(),
        "prior": None,
        "prelint": None,
        "prelint_validation": None,
        "pre_render_check": None,
        "pre_render_validation": None,
        "stage_render_check": None,
        "stage_render_validation": None,
        "stage_lint": None,
        "stage_lint_validation": None,
        "final_lint": None,
        "final_lint_validation": None,
        "rollback": {"attempted": False, "restored": None},
        "orphan_transactions": [],
        "transaction": {
            "strategy": "same-filesystem-two-rename-swap",
            "crash_consistent": False,
            "crash_window": "between target-to-backup and stage-to-target renames",
            "lock": {
                "path": TRANSACTION_LOCK,
                "disposition": "not-attempted",
                "owner": None,
            },
        },
        "cleanup": {
            "backup_removed": None,
            "retained_backup": None,
            "warning": None,
        },
        "warnings": [],
        "published_revision": None,
        "package_receipt_sha256": None,
        "publish_status": publish_status,
        "revision_reset": None,
        "message": None,
    }

    stage: Path | None = None
    backup: Path | None = None
    lock_path: Path | None = None
    lock_token: str | None = None
    installed = False
    try:
        if not repo_root.is_dir():
            raise PublishRuntimeError(f"repository root not found: {repo_root}")
        if not SLUG_RE.fullmatch(slug):
            raise PublishInputError("plan slug must contain lowercase letters, digits, and hyphens")
        if scratch_is_symlink:
            raise PublishInputError("scratch package directory must not be a symlink")
        plan_dir = target.parent
        if not plan_dir.is_dir() or plan_dir.is_symlink() or not _inside(repo_root, plan_dir):
            raise PublishInputError(f"canonical plan directory is missing or unsafe: {plan_dir}")
        unsafe_components = _symlink_components(repo_root, plan_dir)
        if unsafe_components:
            raise PublishInputError(
                "canonical plan path contains symlink components: "
                + ", ".join(unsafe_components)
            )
        canonical = repo_root / "docs" / "plans" / slug / "architecture"
        if target != canonical or target.parent != plan_dir:
            raise PublishInputError("target does not match the canonical plan architecture path")
        if scratch == target or _inside(target, scratch):
            raise PublishInputError("scratch package must be outside the canonical target")
        if _inside(repo_root, scratch):
            raise PublishInputError("scratch package must be outside the repository root")

        manifest, reviewed_bytes = _require_exact_scratch(scratch)
        if (
            manifest.get("$schema") != ARCHITECTURE_SCHEMA_URN
            or manifest.get("schema_version") != ARCHITECTURE_SCHEMA_VERSION
        ):
            raise PublishInputError(
                "publisher accepts only ce-architecture schema v2 packages; "
                "regenerate legacy packages"
            )
        if manifest.get("project_slug") != slug:
            raise PublishInputError(
                f"scratch project_slug {manifest.get('project_slug')!r} does not match {slug!r}"
            )
        expected_plan_path = (Path("docs") / "plans" / slug).as_posix()
        if manifest.get("source_plan_path") != expected_plan_path:
            raise PublishInputError(
                f"scratch source_plan_path must be {expected_plan_path!r}"
            )
        if publish_status not in PUBLISHED_STATUSES:
            raise PublishInputError(
                f"publish status must be one of {sorted(PUBLISHED_STATUSES)}"
            )
        if manifest.get("baseline_status") != publish_status:
            raise PublishInputError(
                "publish status must equal the reviewed scratch baseline_status"
            )
        if manifest.get("lifecycle_status") != "proposed":
            raise PublishInputError(
                "reviewed scratch lifecycle_status must be 'proposed'"
            )
        for value, label in (
            (recorded_by, "recorded_by"),
            (approval_authority, "approval_authority"),
            (approval_reference, "approval_reference"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise PublishInputError(f"{label} must be a non-empty string")
            if APPROVAL_PLACEHOLDER_RE.fullmatch(value.strip()):
                raise PublishInputError(
                    f"{label} must be durable approval information, not a placeholder"
                )
        if approval_time is None:
            approval_time = (
                datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
        if not isinstance(approval_time, str) or not RFC3339_UTC_RE.fullmatch(
            approval_time
        ):
            raise PublishInputError("approval_time must be RFC 3339 UTC")
        approval = manifest.get("approval")
        pending_without_review = {
            **PENDING_APPROVAL,
            "review_payload_sha256": (
                approval.get("review_payload_sha256")
                if isinstance(approval, dict)
                else None
            ),
        }
        if (
            not isinstance(approval, dict)
            or approval != pending_without_review
            or not isinstance(approval.get("review_payload_sha256"), str)
            or not SHA_RE.fullmatch(approval["review_payload_sha256"])
        ):
            raise PublishInputError(
                "reviewed scratch approval must be canonical pending with a "
                "deterministic review payload digest"
            )
        new_revision = _manifest_revision(manifest, label="scratch")

        pre_render = run_render_check(scratch)
        result["pre_render_check"] = pre_render
        pre_render_validation = _assess_render_result(pre_render)
        result["pre_render_validation"] = pre_render_validation
        if pre_render_validation["outcome"] == "error":
            raise PublishRuntimeError(
                "scratch renderer check could not be trusted: "
                + pre_render_validation["message"]
            )
        if pre_render_validation["outcome"] == "fail":
            raise PublishInputError(
                "scratch deterministic render check failed: "
                + pre_render_validation["message"]
            )

        prelint = run_lint(scratch, repo_root, allow_proposed=True)
        result["prelint"] = prelint
        prelint_validation = _assess_lint_result(prelint)
        result["prelint_validation"] = prelint_validation
        if prelint_validation["outcome"] == "error":
            raise PublishRuntimeError(
                "scratch architecture lint could not be trusted: "
                + prelint_validation["message"]
            )
        if prelint_validation["outcome"] == "fail":
            raise PublishInputError(
                "scratch architecture lint failed: "
                + _lint_failure_detail(prelint)
            )

        postlint_manifest, postlint_bytes = _require_exact_scratch(scratch)
        if postlint_bytes != reviewed_bytes or postlint_manifest != manifest:
            raise PublishInputError("scratch package changed during pre-publication lint")

        result["transaction"]["lock"]["disposition"] = "acquiring"
        try:
            lock_path, lock_token, lock_result = _acquire_transaction_lock(
                plan_dir, target_rel
            )
        except PublishRuntimeError:
            result["transaction"]["lock"]["disposition"] = "acquisition-error"
            raise
        result["transaction"]["lock"] = lock_result
        if lock_path is None:
            orphans = _find_orphan_transactions(plan_dir)
            result["orphan_transactions"] = orphans
            raise PublishInputError(
                "publication transaction lock already exists; treat it as active "
                "or crash-leftover state and recover or park it before retry"
            )

        # The lock serializes publishers before the orphan scan and prior-package
        # inspection. Excluding our own lock leaves only crash-leftover paths.
        orphans = _find_orphan_transactions(
            plan_dir,
            exclude={lock_path.name},
        )
        result["orphan_transactions"] = orphans
        if orphans:
            raise PublishInputError(
                "orphaned publication transaction paths require explicit crash "
                "recovery; inspect and recover or park them before retry: "
                + ", ".join(orphans)
            )

        prior = _inspect_prior(
            target,
            repo_root,
            slug,
            allow_extra_cleanup=allow_extra_cleanup,
        )
        result["prior"] = prior
        prior_state = prior["state"]
        has_reset = RESET_FIELD in manifest
        if prior_state == "absent":
            if new_revision != 1:
                raise PublishInputError("first publication requires architecture_revision 1")
            if has_reset:
                raise PublishInputError(
                    f"{RESET_FIELD} is not allowed when no prior package exists"
                )
            if accept_human_approved_reset:
                raise PublishInputError(
                    "--accept-human-approved-reset is not valid without a malformed prior"
                )
        elif prior_state in {"valid", "stale", "invalid-readable"}:
            expected_revision = int(prior["revision"]) + 1
            if new_revision != expected_revision:
                raise PublishInputError(
                    f"revision must advance from {prior['revision']} to {expected_revision}"
                )
            if has_reset or accept_human_approved_reset:
                raise PublishInputError(
                    "reset disposition is forbidden for a prior package with a readable revision"
                )
        else:
            if not accept_human_approved_reset:
                raise PublishInputError(
                    "malformed prior package requires --accept-human-approved-reset"
                )
            reason = _validate_reset_record(manifest)
            result["revision_reset"] = {
                "reason": reason,
                "recorded_by": "human",
                "gate": RESET_GATE,
            }
            if new_revision != 1:
                raise PublishInputError(
                    "malformed-prior recovery resets architecture_revision to 1"
                )

        # Scratch was linted before the lock mutation. Package authority and
        # revision checks then ran under that exclusive same-parent lock.
        stage = _copy_to_stage(scratch, plan_dir, reviewed_bytes)
        receipt = _bind_human_approval(
            stage,
            manifest,
            reviewed_bytes["architecture.json"],
            publish_status,
            recorded_by=recorded_by,
            approval_authority=approval_authority,
            approval_reference=approval_reference,
            approval_time=approval_time,
        )
        result["package_receipt_sha256"] = receipt
        stage_render = run_render_check(stage)
        result["stage_render_check"] = stage_render
        stage_render_validation = _assess_render_result(stage_render)
        result["stage_render_validation"] = stage_render_validation
        if stage_render_validation["outcome"] == "error":
            raise PublishRuntimeError(
                "same-parent staged renderer check could not be trusted: "
                + stage_render_validation["message"]
            )
        if stage_render_validation["outcome"] == "fail":
            raise PublishInputError(
                "same-parent staged deterministic render check failed: "
                + stage_render_validation["message"]
            )
        stage_lint = run_lint(stage, repo_root)
        result["stage_lint"] = stage_lint
        stage_lint_validation = _assess_lint_result(stage_lint)
        result["stage_lint_validation"] = stage_lint_validation
        if stage_lint_validation["outcome"] == "error":
            raise PublishRuntimeError(
                "same-parent staged package lint could not be trusted: "
                + stage_lint_validation["message"]
            )
        if stage_lint_validation["outcome"] == "fail":
            raise PublishInputError(
                "same-parent staged package lint failed: "
                + _lint_failure_detail(stage_lint)
            )

        if _lexists(target):
            backup = plan_dir / f".architecture-publish-backup-{uuid.uuid4().hex}"
            os.rename(target, backup)
        os.rename(stage, target)
        stage = None
        installed = True

        final_lint = run_lint(target, repo_root)
        result["final_lint"] = final_lint
        final_lint_validation = _assess_lint_result(final_lint)
        result["final_lint_validation"] = final_lint_validation
        if final_lint_validation["outcome"] != "pass":
            rejected = plan_dir / f".architecture-publish-rejected-{uuid.uuid4().hex}"
            result["rollback"]["attempted"] = True
            restored, error = _rollback(target, backup, rejected)
            result["rollback"].update({"restored": restored, "error": error})
            backup = None if restored else backup
            installed = not restored
            if not restored:
                result.update({
                    "status": "error",
                    "message": "final lint failed and rollback could not be proven",
                })
                return result, 2
            result.update({
                "status": "rolled-back",
                "message": (
                    "final architecture lint did not produce a trusted pass; "
                    "previous package state restored"
                ),
            })
            return result, 1

        if backup is not None:
            backup_to_remove = backup
            try:
                _remove_path(backup_to_remove)
            except Exception as exc:
                warning = (
                    "published target passed final lint, but prior-package backup "
                    f"cleanup failed; inspect retained path {backup_to_remove.name}: {exc}"
                )
                result["cleanup"].update({
                    "backup_removed": False,
                    "retained_backup": backup_to_remove.name,
                    "warning": warning,
                })
                result["warnings"].append(warning)
            else:
                result["cleanup"]["backup_removed"] = True
                backup = None
        result.update({
            "status": "published",
            "published_revision": new_revision,
            "message": (
                "architecture package published with a transactional same-filesystem "
                "swap and final lint passed"
            ),
        })
        if result["warnings"]:
            result["message"] += "; backup cleanup requires operator recovery"
        return result, 0

    except PublishInputError as exc:
        result.update({"status": "refused", "message": str(exc)})
        return result, 1
    except (PublishRuntimeError, OSError, shutil.Error) as exc:
        if installed or backup is not None:
            rejected = target.parent / f".architecture-publish-rejected-{uuid.uuid4().hex}"
            result["rollback"]["attempted"] = True
            restored, error = _rollback(target, backup, rejected)
            result["rollback"].update({"restored": restored, "error": error})
            if not restored:
                result.update({
                    "status": "error",
                    "message": f"publication error and rollback could not be proven: {exc}",
                })
                return result, 2
        result.update({"status": "error", "message": str(exc)})
        return result, 2
    finally:
        if stage is not None:
            try:
                _remove_path(stage)
            except Exception as exc:
                warning = (
                    "staged transaction cleanup failed; explicit recovery required: "
                    f"{exc}"
                )
                result["warnings"].append(warning)
                result["message"] = (
                    (result.get("message") or "publication ended") + "; " + warning
                )
        if lock_path is not None and lock_token is not None:
            try:
                _release_transaction_lock(lock_path, lock_token)
            except PublishRuntimeError as exc:
                warning = str(exc)
                result["transaction"]["lock"]["disposition"] = "retained-cleanup-failure"
                result["warnings"].append(warning)
                result["message"] = (
                    (result.get("message") or "publication ended") + "; " + warning
                )
            else:
                result["transaction"]["lock"]["disposition"] = "released"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Transactionally publish a validated ce-architecture package"
    )
    parser.add_argument("scratch_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--plan-slug", required=True)
    parser.add_argument(
        "--publish-status",
        required=True,
        choices=sorted(PUBLISHED_STATUSES),
        help="human-selected final package status",
    )
    parser.add_argument(
        "--recorded-by",
        required=True,
        help="identity or recorded role of the approving human",
    )
    parser.add_argument(
        "--approval-authority",
        required=True,
        help="human solution/technical architecture approval authority",
    )
    parser.add_argument(
        "--approval-reference",
        required=True,
        help="durable review, ticket, or change-control reference",
    )
    parser.add_argument(
        "--approval-time",
        help="RFC 3339 UTC approval time; defaults to publisher-recorded current UTC",
    )
    parser.add_argument(
        "--allow-extra-cleanup",
        action="store_true",
        help="allow an approved replacement to remove unexpected prior-package entries",
    )
    parser.add_argument(
        "--accept-human-approved-reset",
        action="store_true",
        help="accept a durable human revision_reset record for a malformed prior package",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result, code = publish_package(
        args.scratch_dir,
        args.repo_root,
        args.plan_slug,
        publish_status=args.publish_status,
        recorded_by=args.recorded_by,
        approval_authority=args.approval_authority,
        approval_reference=args.approval_reference,
        approval_time=args.approval_time,
        allow_extra_cleanup=args.allow_extra_cleanup,
        accept_human_approved_reset=args.accept_human_approved_reset,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"architecture-publish: {result['status'].upper()} — {result['message']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
