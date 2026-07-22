#!/usr/bin/env python3
"""Safely inventory or retire one obsolete ce-architecture package.

The target is constructed internally as
``<repo>/docs/plans/<strict-slug>/architecture``.  The helper never follows a
symlink while inspecting or removing that tree.  Retirement requires the
stable SHA-256 token returned by a prior inventory, serializes against the
architecture publisher, rechecks the token while holding its lock, and then
removes only the inventoried entries from the leaves upward.

Exit codes:
  0  READY / ABSENT / RETIRED — inventory completed or retirement completed.
  1  REFUSED — a deterministic precondition failed; no deletion was started.
  2  ERROR — the operation could not complete safely.  Inspect ``removed_paths``
     because an operating-system failure during bottom-up removal can be partial.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


SCHEMA_VERSION = 1
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")
TRANSACTION_PREFIX = ".architecture-publish-"
TRANSACTION_LOCK = f"{TRANSACTION_PREFIX}lock"


class RetirementRefused(Exception):
    """A deterministic retirement precondition failed (exit 1)."""


class RetirementRuntimeError(Exception):
    """The helper could not safely complete an operation (exit 2)."""


def _target_relative(slug: str) -> str:
    return f"docs/plans/{slug}/architecture"


def _entry_type(mode: int) -> str:
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "regular-file"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode):
        return "character-device"
    if stat.S_ISBLK(mode):
        return "block-device"
    return "other"


def _platform_safety_check() -> None:
    missing: list[str] = []
    if not hasattr(os, "O_NOFOLLOW"):
        missing.append("O_NOFOLLOW")
    if not hasattr(os, "O_DIRECTORY"):
        missing.append("O_DIRECTORY")
    if os.scandir not in os.supports_fd:
        missing.append("scandir(fd)")
    for function in (os.open, os.stat, os.unlink, os.rmdir, os.readlink):
        if function not in os.supports_dir_fd:
            missing.append(f"{function.__name__}(dir_fd)")
    if missing:
        raise RetirementRuntimeError(
            "platform lacks required no-follow filesystem primitives: "
            + ", ".join(missing)
        )


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def _file_flags() -> int:
    return os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _same_object(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
    )


def _open_exact_plan(repo_root: Path, slug: str) -> tuple[Path, Path, int]:
    """Open the exact plan directory after rejecting symlinked components."""
    _platform_safety_check()
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise RetirementRefused(
            "plan slug must match [a-z0-9]+(?:-[a-z0-9]+)*"
        )

    repo = Path(repo_root).absolute()
    try:
        repo_stat = repo.lstat()
    except OSError as exc:
        raise RetirementRefused(f"repository root is unavailable: {repo}: {exc}") from exc
    if stat.S_ISLNK(repo_stat.st_mode) or not stat.S_ISDIR(repo_stat.st_mode):
        raise RetirementRefused("repository root must be a real directory, not a symlink")

    current = repo
    for part in ("docs", "plans", slug):
        current = current / part
        try:
            component = current.lstat()
        except OSError as exc:
            raise RetirementRefused(
                f"required plan path component is unavailable: {current}: {exc}"
            ) from exc
        if stat.S_ISLNK(component.st_mode):
            raise RetirementRefused(
                f"required plan path component must not be a symlink: {current}"
            )
        if not stat.S_ISDIR(component.st_mode):
            raise RetirementRefused(
                f"required plan path component is not a directory: {current}"
            )

    try:
        plan_fd = os.open(current, _directory_flags())
    except OSError as exc:
        raise RetirementRuntimeError(f"cannot safely open plan directory: {exc}") from exc
    return repo, current, plan_fd


def _names(dir_fd: int) -> list[str]:
    try:
        with os.scandir(dir_fd) as scan:
            return sorted(entry.name for entry in scan)
    except OSError as exc:
        raise RetirementRuntimeError(f"cannot list directory safely: {exc}") from exc


def _hash_regular_at(
    parent_fd: int,
    name: str,
    expected_stat: os.stat_result,
) -> tuple[str, int]:
    try:
        file_fd = os.open(name, _file_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise RetirementRuntimeError(f"cannot open regular file {name!r}: {exc}") from exc
    try:
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or not _same_object(before, expected_stat):
            raise RetirementRuntimeError(
                f"entry {name!r} changed type or identity during inventory"
            )
        digest = hashlib.sha256()
        while True:
            chunk = os.read(file_fd, 65536)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(file_fd)
        if (
            not _same_object(before, after)
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise RetirementRuntimeError(
                f"regular file {name!r} changed while it was hashed"
            )
        return digest.hexdigest(), after.st_size
    except OSError as exc:
        raise RetirementRuntimeError(f"cannot hash regular file {name!r}: {exc}") from exc
    finally:
        os.close(file_fd)


def _entry_at(
    parent_fd: int,
    name: str,
    relative: str,
    entry_stat: os.stat_result,
) -> dict[str, object]:
    kind = _entry_type(entry_stat.st_mode)
    item: dict[str, object] = {"path": relative, "type": kind}
    if kind == "regular-file":
        digest, size = _hash_regular_at(parent_fd, name, entry_stat)
        item["sha256"] = digest
        item["size"] = size
    elif kind == "symlink":
        try:
            item["link_target"] = os.readlink(name, dir_fd=parent_fd)
        except OSError as exc:
            raise RetirementRuntimeError(
                f"cannot read symlink {relative!r} without following it: {exc}"
            ) from exc
    return item


def _scan_directory(
    dir_fd: int,
    prefix: str,
    entries: list[dict[str, object]],
) -> None:
    for name in _names(dir_fd):
        relative = f"{prefix}/{name}" if prefix else name
        try:
            entry_stat = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        except OSError as exc:
            raise RetirementRuntimeError(
                f"cannot lstat architecture entry {relative!r}: {exc}"
            ) from exc
        item = _entry_at(dir_fd, name, relative, entry_stat)
        entries.append(item)
        if item["type"] != "directory":
            continue
        try:
            child_fd = os.open(name, _directory_flags(), dir_fd=dir_fd)
        except OSError as exc:
            raise RetirementRuntimeError(
                f"cannot safely open architecture directory {relative!r}: {exc}"
            ) from exc
        try:
            opened = os.fstat(child_fd)
            if not _same_object(opened, entry_stat):
                raise RetirementRuntimeError(
                    f"architecture directory {relative!r} changed during inventory"
                )
            _scan_directory(child_fd, relative, entries)
        finally:
            os.close(child_fd)


def _inventory_payload(
    target: str,
    entries: list[dict[str, object]],
) -> dict[str, object]:
    ordered = sorted(entries, key=lambda item: str(item["path"]))
    material = {
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "entries": ordered,
    }
    encoded = json.dumps(
        material,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return {
        "token": hashlib.sha256(encoded).hexdigest(),
        "entry_count": len(ordered),
        "entries": ordered,
    }


def _inventory_from_plan_fd(plan_fd: int, target: str) -> dict[str, object]:
    """Inventory ``architecture`` relative to an already-safe plan fd."""
    try:
        root_stat = os.stat("architecture", dir_fd=plan_fd, follow_symlinks=False)
    except FileNotFoundError:
        return {
            "present": False,
            "target_type": "absent",
            "retireable": False,
            "inventory": None,
        }
    except OSError as exc:
        raise RetirementRuntimeError(f"cannot lstat architecture root: {exc}") from exc

    root_item = _entry_at(plan_fd, "architecture", ".", root_stat)
    entries = [root_item]
    root_type = str(root_item["type"])
    if root_type != "directory":
        return {
            "present": True,
            "target_type": root_type,
            "retireable": False,
            "inventory": _inventory_payload(target, entries),
        }

    try:
        root_fd = os.open("architecture", _directory_flags(), dir_fd=plan_fd)
    except OSError as exc:
        raise RetirementRuntimeError(
            f"cannot safely open architecture root: {exc}"
        ) from exc
    try:
        opened = os.fstat(root_fd)
        if not _same_object(opened, root_stat):
            raise RetirementRuntimeError(
                "architecture root changed while it was being opened"
            )
        _scan_directory(root_fd, "", entries)
    finally:
        os.close(root_fd)
    return {
        "present": True,
        "target_type": "directory",
        "retireable": True,
        "inventory": _inventory_payload(target, entries),
    }


def _transaction_siblings(plan_fd: int) -> list[dict[str, str]]:
    siblings: list[dict[str, str]] = []
    for name in _names(plan_fd):
        if not name.startswith(TRANSACTION_PREFIX):
            continue
        try:
            item_stat = os.stat(name, dir_fd=plan_fd, follow_symlinks=False)
        except OSError as exc:
            raise RetirementRuntimeError(
                f"cannot lstat transaction sibling {name!r}: {exc}"
            ) from exc
        siblings.append({"name": name, "type": _entry_type(item_stat.st_mode)})
    return siblings


def _base_payload(operation: str, slug: object) -> dict[str, object]:
    target = (
        _target_relative(slug)
        if isinstance(slug, str) and SLUG_RE.fullmatch(slug)
        else None
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "operation": operation,
        "status": "error",
        "target": target,
        "present": None,
        "target_type": None,
        "inventory": None,
        "transaction_siblings": [],
        "removed_paths": [],
        "message": "operation did not complete",
    }


def _apply_state(payload: dict[str, object], state: dict[str, object]) -> None:
    payload["present"] = state.get("present")
    payload["target_type"] = state.get("target_type")
    payload["inventory"] = state.get("inventory")


def inventory_architecture(repo_root: Path, slug: str) -> tuple[dict[str, object], int]:
    """Return a deterministic no-follow inventory of the canonical target."""
    payload = _base_payload("inventory", slug)
    plan_fd: int | None = None
    try:
        _, _, plan_fd = _open_exact_plan(repo_root, slug)
        siblings = _transaction_siblings(plan_fd)
        payload["transaction_siblings"] = siblings
        if siblings:
            raise RetirementRefused(
                "architecture transaction sibling(s) require explicit recovery: "
                + ", ".join(item["name"] for item in siblings)
            )
        state = _inventory_from_plan_fd(plan_fd, str(payload["target"]))
        _apply_state(payload, state)
        if not state["present"]:
            payload["status"] = "absent"
            payload["message"] = "canonical architecture target is absent"
            return payload, 0
        if not state["retireable"]:
            raise RetirementRefused(
                "architecture root is present but retirement requires a real directory; "
                f"found {state['target_type']}"
            )
        payload["status"] = "ready"
        payload["message"] = "architecture inventory is ready for explicit review"
        return payload, 0
    except RetirementRefused as exc:
        payload["status"] = "refused"
        payload["message"] = str(exc)
        return payload, 1
    except (OSError, RetirementRuntimeError, TypeError, ValueError) as exc:
        payload["status"] = "error"
        payload["message"] = str(exc)
        return payload, 2
    finally:
        if plan_fd is not None:
            os.close(plan_fd)


def _acquire_lock(plan_fd: int, target: str) -> tuple[os.stat_result, dict[str, object]]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        lock_fd = os.open(TRANSACTION_LOCK, flags, 0o600, dir_fd=plan_fd)
    except FileExistsError as exc:
        raise RetirementRefused(
            f"transaction lock already exists: {TRANSACTION_LOCK}"
        ) from exc
    except OSError as exc:
        raise RetirementRuntimeError(f"cannot acquire transaction lock: {exc}") from exc
    try:
        owner = {
            "operation": "architecture-retire",
            "pid": os.getpid(),
            "target": target,
        }
        encoded = (json.dumps(owner, sort_keys=True) + "\n").encode("utf-8")
        os.write(lock_fd, encoded)
        os.fsync(lock_fd)
        lock_stat = os.fstat(lock_fd)
    except OSError as exc:
        raise RetirementRuntimeError(f"cannot initialize transaction lock: {exc}") from exc
    finally:
        os.close(lock_fd)
    return lock_stat, owner


def _assert_owned_lock(plan_fd: int, lock_stat: os.stat_result) -> None:
    try:
        current = os.stat(
            TRANSACTION_LOCK,
            dir_fd=plan_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise RetirementRuntimeError(f"transaction lock ownership was lost: {exc}") from exc
    if not stat.S_ISREG(current.st_mode) or not _same_object(current, lock_stat):
        raise RetirementRuntimeError("transaction lock was replaced during retirement")


def _release_lock(plan_fd: int, lock_stat: os.stat_result) -> None:
    _assert_owned_lock(plan_fd, lock_stat)
    try:
        os.unlink(TRANSACTION_LOCK, dir_fd=plan_fd)
    except OSError as exc:
        raise RetirementRuntimeError(f"cannot release transaction lock: {exc}") from exc


def _expected_children(
    entries: dict[str, dict[str, object]],
    prefix: str,
) -> list[str]:
    names: list[str] = []
    for relative in entries:
        if relative == ".":
            continue
        if "/" in relative:
            parent, name = relative.rsplit("/", 1)
        else:
            parent, name = "", relative
        if parent == prefix:
            names.append(name)
    return sorted(names)


def _remove_directory_contents(
    dir_fd: int,
    prefix: str,
    expected: dict[str, dict[str, object]],
    removed: list[str],
) -> None:
    wanted_names = _expected_children(expected, prefix)
    actual_names = _names(dir_fd)
    if actual_names != wanted_names:
        raise RetirementRuntimeError(
            f"architecture tree changed before removal at {prefix or '.'!r}: "
            f"expected {wanted_names!r}, found {actual_names!r}"
        )

    for name in wanted_names:
        relative = f"{prefix}/{name}" if prefix else name
        wanted = expected[relative]
        try:
            current_stat = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        except OSError as exc:
            raise RetirementRuntimeError(
                f"cannot lstat approved retirement entry {relative!r}: {exc}"
            ) from exc
        current = _entry_at(dir_fd, name, relative, current_stat)
        if current != wanted:
            raise RetirementRuntimeError(
                f"architecture entry changed after token recheck: {relative!r}"
            )

        if wanted["type"] == "directory":
            try:
                child_fd = os.open(name, _directory_flags(), dir_fd=dir_fd)
            except OSError as exc:
                raise RetirementRuntimeError(
                    f"cannot safely open approved directory {relative!r}: {exc}"
                ) from exc
            try:
                opened = os.fstat(child_fd)
                if not _same_object(opened, current_stat):
                    raise RetirementRuntimeError(
                        f"architecture directory changed after token recheck: {relative!r}"
                    )
                _remove_directory_contents(child_fd, relative, expected, removed)
            finally:
                os.close(child_fd)
            try:
                os.rmdir(name, dir_fd=dir_fd)
            except OSError as exc:
                raise RetirementRuntimeError(
                    f"cannot remove approved directory {relative!r}: {exc}"
                ) from exc
        else:
            try:
                os.unlink(name, dir_fd=dir_fd)
            except OSError as exc:
                raise RetirementRuntimeError(
                    f"cannot unlink approved entry {relative!r}: {exc}"
                ) from exc
        removed.append(relative)


def _remove_inventory(
    plan_fd: int,
    inventory: dict[str, object],
    removed: list[str],
) -> None:
    raw_entries = inventory.get("entries")
    if not isinstance(raw_entries, list):
        raise RetirementRuntimeError("approved inventory entries are unavailable")
    expected = {
        str(item["path"]): item
        for item in raw_entries
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    if len(expected) != len(raw_entries) or expected.get(".", {}).get("type") != "directory":
        raise RetirementRuntimeError("approved inventory is malformed")

    try:
        root_stat = os.stat("architecture", dir_fd=plan_fd, follow_symlinks=False)
        root_fd = os.open("architecture", _directory_flags(), dir_fd=plan_fd)
    except OSError as exc:
        raise RetirementRuntimeError(f"cannot open approved architecture root: {exc}") from exc
    try:
        opened = os.fstat(root_fd)
        if not _same_object(opened, root_stat):
            raise RetirementRuntimeError(
                "architecture root changed after token recheck"
            )
        _remove_directory_contents(root_fd, "", expected, removed)
        final_stat = os.stat(
            "architecture",
            dir_fd=plan_fd,
            follow_symlinks=False,
        )
        if not _same_object(final_stat, opened):
            raise RetirementRuntimeError(
                "architecture root was replaced during retirement"
            )
        os.rmdir("architecture", dir_fd=plan_fd)
        removed.append(".")
    except OSError as exc:
        raise RetirementRuntimeError(f"cannot remove architecture root: {exc}") from exc
    finally:
        os.close(root_fd)


def retire_architecture(
    repo_root: Path,
    slug: str,
    expected_token: object,
) -> tuple[dict[str, object], int]:
    """Retire the exact canonical target after a locked token comparison."""
    payload = _base_payload("retire", slug)
    plan_fd: int | None = None
    lock_stat: os.stat_result | None = None
    code = 2
    try:
        if not isinstance(expected_token, str) or not TOKEN_RE.fullmatch(expected_token):
            raise RetirementRefused(
                "--expected-token must be the explicit 64-character lowercase "
                "SHA-256 token from inventory"
            )
        _, _, plan_fd = _open_exact_plan(repo_root, slug)
        before_lock = _transaction_siblings(plan_fd)
        payload["transaction_siblings"] = before_lock
        if before_lock:
            raise RetirementRefused(
                "architecture transaction sibling(s) require explicit recovery: "
                + ", ".join(item["name"] for item in before_lock)
            )

        lock_stat, owner = _acquire_lock(plan_fd, str(payload["target"]))
        payload["lock"] = {
            "path": TRANSACTION_LOCK,
            "disposition": "acquired",
            "owner": owner,
        }
        after_lock = [
            item
            for item in _transaction_siblings(plan_fd)
            if item["name"] != TRANSACTION_LOCK
        ]
        payload["transaction_siblings"] = after_lock
        if after_lock:
            raise RetirementRefused(
                "architecture transaction sibling appeared while acquiring the lock: "
                + ", ".join(item["name"] for item in after_lock)
            )
        _assert_owned_lock(plan_fd, lock_stat)

        first = _inventory_from_plan_fd(plan_fd, str(payload["target"]))
        _apply_state(payload, first)
        if not first["present"]:
            raise RetirementRefused("canonical architecture target is already absent")
        if not first["retireable"]:
            raise RetirementRefused(
                "architecture root is present but retirement requires a real directory; "
                f"found {first['target_type']}"
            )
        first_inventory = first["inventory"]
        if not isinstance(first_inventory, dict):
            raise RetirementRuntimeError("architecture inventory is unavailable")
        if first_inventory.get("token") != expected_token:
            raise RetirementRefused(
                "architecture inventory token changed; review a fresh inventory before retrying"
            )

        # A second complete inventory immediately before removal makes the
        # locked check explicit and detects changes during the first hash pass.
        second = _inventory_from_plan_fd(plan_fd, str(payload["target"]))
        _apply_state(payload, second)
        second_inventory = second.get("inventory")
        if (
            not second.get("retireable")
            or not isinstance(second_inventory, dict)
            or second_inventory.get("token") != expected_token
            or second_inventory != first_inventory
        ):
            raise RetirementRefused(
                "architecture inventory changed during the locked token recheck"
            )
        _assert_owned_lock(plan_fd, lock_stat)
        late_siblings = [
            item
            for item in _transaction_siblings(plan_fd)
            if item["name"] != TRANSACTION_LOCK
        ]
        payload["transaction_siblings"] = late_siblings
        if late_siblings:
            raise RetirementRefused(
                "architecture transaction sibling appeared before removal: "
                + ", ".join(item["name"] for item in late_siblings)
            )

        _remove_inventory(plan_fd, second_inventory, payload["removed_paths"])
        final = _inventory_from_plan_fd(plan_fd, str(payload["target"]))
        if final["present"]:
            raise RetirementRuntimeError(
                "architecture root remains present after retirement"
            )
        payload["present"] = False
        payload["target_type"] = "absent"
        payload["status"] = "retired"
        payload["message"] = "canonical architecture package retired"
        code = 0
    except RetirementRefused as exc:
        payload["status"] = "refused"
        payload["message"] = str(exc)
        code = 1
    except (OSError, RetirementRuntimeError, TypeError, ValueError) as exc:
        payload["status"] = "error"
        payload["message"] = str(exc)
        code = 2
    finally:
        if plan_fd is not None and lock_stat is not None:
            try:
                _release_lock(plan_fd, lock_stat)
                if isinstance(payload.get("lock"), dict):
                    payload["lock"]["disposition"] = "released"
            except (OSError, RetirementRuntimeError) as exc:
                payload["status"] = "error"
                payload["message"] = str(exc)
                code = 2
        if plan_fd is not None:
            os.close(plan_fd)
    return payload, code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inventory or retire one canonical ce-architecture package"
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--plan-slug", required=True)
    parser.add_argument("--retire", action="store_true")
    parser.add_argument("--expected-token")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.retire:
        payload, code = retire_architecture(
            args.repo_root,
            args.plan_slug,
            args.expected_token,
        )
    elif args.expected_token is not None:
        payload = _base_payload("inventory", args.plan_slug)
        payload["status"] = "refused"
        payload["message"] = "--expected-token is valid only with --retire"
        code = 1
    else:
        payload, code = inventory_architecture(args.repo_root, args.plan_slug)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        stream = sys.stdout if code == 0 else sys.stderr
        print(
            f"architecture-retire: {str(payload['status']).upper()} — "
            f"{payload['message']}",
            file=stream,
        )
        inventory = payload.get("inventory")
        if isinstance(inventory, dict):
            print(f"token: {inventory.get('token')}", file=stream)
            for item in inventory.get("entries", []):
                print(f"{item.get('type')}: {item.get('path')}", file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
