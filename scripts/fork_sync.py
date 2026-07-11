#!/usr/bin/env python3
"""Verify (or re-sync) the deliberately forked gate scripts against their canonicals.

Some substrate-independent gates are deliberately DUPLICATED on disk: each
consuming skill carries its own copy so it can run without a sibling skill
being reachable (Managed-Agent cookbooks bundle skills separately, and
``${CLAUDE_PLUGIN_ROOT}`` is only guaranteed in hook/MCP contexts — not in
skill Bash calls). Duplication is correct; silent DRIFT is the bug.

The fork registry is machine-readable and lives in
``plugins/core-engineering/fork-manifest.json``. This tool is the one way
copies change:

    python3 scripts/fork_sync.py            # verify — exit 1 on drift/missing
    python3 scripts/fork_sync.py --write    # re-sync copies from canonicals

To add a consumer skill: append its copy path to the fork's ``copies`` list
in the manifest and run ``--write``. Never hand-edit a copy; edit the
canonical. check.py (§5) and supply_chain_check.py enforce the same manifest
in CI, so a drifted copy cannot merge.

Exit codes: 0 in sync (or synced), 1 drift/missing copies (--check only),
2 structural error (manifest missing/invalid, canonical missing).
"""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_REL = "plugins/core-engineering/fork-manifest.json"


def load_forks(root: Path, problems: list[str]) -> list[dict]:
    """Parse and structurally validate the fork manifest.

    Structural problems (unreadable manifest, bad paths, duplicate copies,
    missing canonicals) are appended to *problems*; they are exit-2 material —
    a broken registry must never read as \"in sync\".
    """
    manifest = root / MANIFEST_REL
    if not manifest.is_file():
        problems.append(f"missing manifest: {MANIFEST_REL}")
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"unreadable manifest {MANIFEST_REL}: {exc}")
        return []
    forks = data.get("forks")
    if not isinstance(forks, list) or not forks:
        problems.append(f"{MANIFEST_REL}: 'forks' must be a non-empty list")
        return []

    def bad_path(rel: str, *, is_canonical: bool = False) -> str | None:
        if not isinstance(rel, str) or not rel:
            return "empty path"
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts:
            return "must be repo-relative with no '..'"
        # A COPY always ships inside a plugin (it rides beside a skill so it is
        # reachable via CLAUDE_SKILL_DIR without a sibling being loaded). A
        # CANONICAL may additionally live at repo-root scripts/ — gate_runner.py
        # is the one such: it lives OUTSIDE the plugin (an installed plugin
        # ships no repo-root scripts/), so the plugin forks a byte-identical
        # copy from it. Copies stay plugins-only either way.
        allowed = ("plugins/", "scripts/") if is_canonical else ("plugins/",)
        if not rel.startswith(allowed):
            if is_canonical:
                return "a canonical lives under plugins/ or scripts/"
            return "a forked copy lives under plugins/"
        return None

    canonicals: set[str] = set()
    all_copies: set[str] = set()
    for i, fork in enumerate(forks):
        if not isinstance(fork, dict):
            problems.append(f"{MANIFEST_REL}: forks[{i}] is not an object")
            continue
        canonical = fork.get("canonical", "")
        copies = fork.get("copies")
        if (why := bad_path(canonical, is_canonical=True)) is not None:
            problems.append(f"{MANIFEST_REL}: forks[{i}].canonical {canonical!r}: {why}")
            continue
        if canonical in canonicals:
            problems.append(f"{MANIFEST_REL}: duplicate canonical {canonical}")
        canonicals.add(canonical)
        if not (root / canonical).is_file():
            problems.append(f"canonical missing on disk: {canonical}")
        if not isinstance(copies, list) or not copies:
            problems.append(f"{MANIFEST_REL}: forks[{i}].copies must be a non-empty list")
            continue
        for copy in copies:
            if (why := bad_path(copy)) is not None:
                problems.append(f"{MANIFEST_REL}: forks[{i}] copy {copy!r}: {why}")
                continue
            if copy == canonical:
                problems.append(f"{MANIFEST_REL}: {copy} lists itself as its own copy")
            if copy in all_copies:
                problems.append(f"{MANIFEST_REL}: duplicate copy entry {copy}")
            all_copies.add(copy)
    overlap = canonicals & all_copies
    for path in sorted(overlap):
        problems.append(f"{MANIFEST_REL}: {path} is both a canonical and a copy")
    return forks


def pairs(forks: list[dict]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for fork in forks:
        canonical = fork.get("canonical", "")
        for copy in fork.get("copies") or []:
            if isinstance(canonical, str) and isinstance(copy, str):
                out.append((canonical, copy))
    return out


def check(root: Path, forks: list[dict]) -> list[str]:
    issues: list[str] = []
    for canonical_rel, copy_rel in pairs(forks):
        canonical, copy = root / canonical_rel, root / copy_rel
        if not canonical.is_file():
            continue  # already reported as a structural problem
        if not copy.is_file():
            issues.append(f"missing copy: {copy_rel} (canonical: {canonical_rel})")
        elif not filecmp.cmp(canonical, copy, shallow=False):
            issues.append(f"drift: {copy_rel} differs from {canonical_rel}")
    return issues


def write(root: Path, forks: list[dict]) -> list[str]:
    synced: list[str] = []
    for canonical_rel, copy_rel in pairs(forks):
        canonical, copy = root / canonical_rel, root / copy_rel
        if not canonical.is_file():
            continue  # structural problem; nothing to sync from
        if copy.is_file() and filecmp.cmp(canonical, copy, shallow=False):
            continue
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(canonical, copy)
        synced.append(copy_rel)
    return synced


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="verify or re-sync forked gate scripts from fork-manifest.json"
    )
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="repository root")
    parser.add_argument(
        "--write", action="store_true",
        help="re-sync drifted/missing copies from their canonicals (default: verify only)",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    problems: list[str] = []
    forks = load_forks(root, problems)
    if problems:
        print(f"fork-sync: ERROR — {len(problems)} structural problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  ✗ {problem}", file=sys.stderr)
        return 2

    n_pairs = len(pairs(forks))
    if args.write:
        synced = write(root, forks)
        for copy_rel in synced:
            print(f"  synced: {copy_rel}")
        residue = check(root, forks)
        if residue:  # should be unreachable; never report a broken sync as clean
            print("fork-sync: ERROR — copies still diverge after --write:", file=sys.stderr)
            for issue in residue:
                print(f"  ✗ {issue}", file=sys.stderr)
            return 2
        print(f"fork-sync: OK — {n_pairs} copies in sync ({len(synced)} rewritten).")
        return 0

    issues = check(root, forks)
    if issues:
        print(f"fork-sync: FAIL — {len(issues)} copy issue(s):", file=sys.stderr)
        for issue in issues:
            print(f"  ✗ {issue}", file=sys.stderr)
        print(
            "  fix: edit the CANONICAL, then `python3 scripts/fork_sync.py --write`",
            file=sys.stderr,
        )
        return 1
    print(f"fork-sync: OK — {n_pairs} copies in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
