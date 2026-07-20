#!/usr/bin/env python3
"""write-lease.py — set or clear the session write lease for a read-only skill.

Read-only-on-code skills call `--set` at their Stage 0 (declaring the only
paths this session may Write/Edit) and `--restore-baseline` at exit. The lease
lives at .claude/ce-write-scope.json, where the write-scope-guard hook
enforces it structurally; the baseline it restores is the deny-only floor
`/core-engineering:ce-init` seeds (git internals and the lease file itself are never
agent-writable).

The lease is cooperative: it makes accidental tool-mediated drift structural
(a "helpful" Edit to source mid-review is denied; the guard's deny message
names the holder, the allowed scope, and the one lift path), it is not an
adversarial sandbox. Replacing a stale lease from a previous session is
correct and is reported, never silent.

Each lease carries a `lease_id` (uuid4) and a `created_at` (UTC ISO) so the
write-scope-guard hook can bind the lease to the session that first uses it and
auto-degrade a lease orphaned by a dead session to the deny-only baseline —
instead of hard-denying the next session's writes until a human hand-deletes
the file. The guard writes the session binding beside the lease; write-lease
only stamps the identity fields (it runs in skill Bash, which is not handed the
host session id).

Usage:
  write-lease.py --set --skill ce-review [--allow GLOB ...] [--root DIR]
  write-lease.py --restore-baseline [--root DIR]

`--set` with no `--allow` means: this session writes nothing (every
Write/Edit target is denied while the lease holds).
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

LEASE_REL = ".claude/ce-write-scope.json"
BASELINE_DENY = [".git/**", LEASE_REL]
BASELINE = {
    "schema_version": 1,
    "enabled": True,
    "mode": "deny-only",
    "reason": (
        "core-engineering baseline: git internals and the write-scope lease "
        "are not agent-writable"
    ),
    "deny": BASELINE_DENY,
}


def lease_path(root: Path) -> Path:
    return root / LEASE_REL


def read_existing(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, FileNotFoundError):
        return None


def write_policy(path: Path, policy: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")


def command_name(skill: str) -> str:
    """Return the installed Claude Code command for a stored skill name."""
    normalized = skill.strip().lstrip("/")
    if ":" not in normalized:
        normalized = f"core-engineering:{normalized}"
    return f"/{normalized}"


def set_lease(root: Path, skill: str, allow: list[str]) -> int:
    path = lease_path(root)
    existing = read_existing(path)
    if existing and existing.get("mode", "lease") == "lease":
        holder = existing.get("skill", "an unknown session")
        print(
            f"write-lease: replacing a stale lease held by {holder} "
            "(previous session did not restore the baseline)",
            file=sys.stderr,
        )
    writes = ", ".join(allow) if allow else "nothing (report is rendered, not written)"
    command = command_name(skill)
    policy = {
        "schema_version": 1,
        "enabled": True,
        "mode": "lease",
        "skill": skill,
        "lease_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reason": (
            f"session write lease set by {command} Stage 0 — this session "
            f"writes only: {writes}"
        ),
        "allow": allow,
        "deny": list(BASELINE_DENY),
    }
    write_policy(path, policy)
    print(f"write-lease: lease set for {command} ({len(allow)} allow pattern(s))")
    return 0


def restore_baseline(root: Path) -> int:
    write_policy(lease_path(root), BASELINE)
    print("write-lease: baseline restored (deny-only floor)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set/clear the session write lease")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--set", action="store_true", help="set a session lease")
    mode.add_argument("--restore-baseline", action="store_true",
                      help="restore the deny-only baseline")
    parser.add_argument("--skill", help="skill name holding the lease (required with --set)")
    parser.add_argument("--allow", action="append", default=[],
                        help="glob this session may write; repeatable; none = writes nothing")
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if args.set:
        if not args.skill:
            print("write-lease: ERROR — --set requires --skill", file=sys.stderr)
            return 2
        return set_lease(root, args.skill.strip().lstrip("/"), args.allow)
    return restore_baseline(root)


if __name__ == "__main__":
    sys.exit(main())
