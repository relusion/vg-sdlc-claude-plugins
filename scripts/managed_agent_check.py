#!/usr/bin/env python3
"""Validate the Managed Agent cookbook surface.

This checker guards the productized CMA layer:

* the expected cookbook slugs exist;
* each cookbook has the required files, matching manifest name, skill paths, and
  steering examples;
* the root cookbook README and orchestration guide list every cookbook;
* scripts/orchestrate.py allowlists the same targets the docs describe.

It is intentionally stdlib-only and structural. `scripts/test-cookbooks.sh`
still proves the deploy manifest transform by dry-running the API payloads.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COOKBOOKS = {
    "spec-author",
    "spec-impl",
    "quality-gate",
    "release-coordinator",
}
REQUIRED_FILES = ("agent.yaml", "system.md", "README.md", "steering-examples.json")
NAME_RE = re.compile(r"^name:\s*([A-Za-z0-9_.-]+)\s*$", re.MULTILINE)
PATH_RE = re.compile(r"path:\s*([^,}\]\n]+)")


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"missing: {rel(root, path)}")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"cannot read: {rel(root, path)}: {exc}")
    return ""


def cookbook_dirs(root: Path) -> set[str]:
    base = root / "managed-agent-cookbooks"
    return {path.name for path in base.iterdir() if path.is_dir()} if base.is_dir() else set()


def check_inventory(root: Path, errors: list[str]) -> int:
    found = cookbook_dirs(root)
    missing = sorted(EXPECTED_COOKBOOKS - found)
    extra = sorted(found - EXPECTED_COOKBOOKS)
    if missing:
        errors.append(f"managed-agent-cookbooks: missing expected cookbook(s): {', '.join(missing)}")
    if extra:
        errors.append(f"managed-agent-cookbooks: unexpected cookbook dir(s): {', '.join(extra)}")
    return 1


def check_one_cookbook(root: Path, slug: str, errors: list[str]) -> int:
    checked = 0
    base = root / "managed-agent-cookbooks" / slug
    for filename in REQUIRED_FILES:
        checked += 1
        path = base / filename
        if not path.is_file():
            errors.append(f"{rel(root, path)}: required cookbook file missing")

    manifest = base / "agent.yaml"
    text = read(root, manifest, errors)
    checked += 1
    match = NAME_RE.search(text)
    if not match:
        errors.append(f"{rel(root, manifest)}: missing top-level name")
    elif match.group(1) != slug:
        errors.append(
            f"{rel(root, manifest)}: name {match.group(1)!r} must match directory {slug!r}"
        )
    if "model:" not in text:
        errors.append(f"{rel(root, manifest)}: missing model")
    if "system:" not in text or "file: ./system.md" not in text:
        errors.append(f"{rel(root, manifest)}: must reference ./system.md")
    if "callable_agents: []" not in text:
        errors.append(f"{rel(root, manifest)}: expected single-process callable_agents: []")

    paths = [p.strip().strip('"').strip("'") for p in PATH_RE.findall(text)]
    skill_paths = [p for p in paths if "plugins/core-engineering/skills" in p]
    if not skill_paths:
        errors.append(f"{rel(root, manifest)}: no core-engineering skill path found")
    for raw in skill_paths:
        checked += 1
        target = (base / raw).resolve()
        if not target.is_dir():
            errors.append(f"{rel(root, manifest)}: skill path not found: {raw}")

    examples = base / "steering-examples.json"
    checked += 1
    try:
        data = json.loads(examples.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing: {rel(root, examples)}")
    except json.JSONDecodeError as exc:
        errors.append(f"{rel(root, examples)}: invalid JSON: {exc}")
    else:
        if not isinstance(data, list) or not data:
            errors.append(f"{rel(root, examples)}: must contain a non-empty list")
        else:
            for idx, item in enumerate(data):
                if not isinstance(item, dict):
                    errors.append(f"{rel(root, examples)}[{idx}]: must be an object")
                    continue
                if not isinstance(item.get("event"), str) or not item["event"].strip():
                    errors.append(f"{rel(root, examples)}[{idx}]: missing non-empty event")
                if not isinstance(item.get("description"), str) or not item["description"].strip():
                    errors.append(f"{rel(root, examples)}[{idx}]: missing non-empty description")

    readme = base / "README.md"
    readme_text = read(root, readme, errors)
    checked += 1
    for needle in ("## Overview", "## Deploy", "## Steering events", "## Security & handoffs"):
        if needle not in readme_text:
            errors.append(f"{rel(root, readme)}: missing section {needle!r}")
    if f"deploy-managed-agent.sh {slug}" not in readme_text:
        errors.append(f"{rel(root, readme)}: missing deploy command for {slug}")

    return checked


def section_after(text: str, heading_prefix: str) -> str:
    """Return the body from a `## ` heading (matched by prefix) to the next `## `.

    Used to scope a needle check to the README's managed-agent cookbook section
    so the `experimental` label can't be satisfied by an unrelated mention.
    """
    idx = text.find(heading_prefix)
    if idx == -1:
        return ""
    rest = text[idx + len(heading_prefix):]
    nxt = rest.find("\n## ")
    return rest if nxt == -1 else rest[:nxt]


def check_docs(root: Path, errors: list[str]) -> int:
    checked = 0
    docs = [
        root / "managed-agent-cookbooks" / "README.md",
        root / "managed-agent-cookbooks" / "ORCHESTRATION.md",
        root / "README.md",
        root / "CLAUDE.md",
    ]
    for doc in docs:
        checked += 1
        text = read(root, doc, errors)
        for slug in sorted(EXPECTED_COOKBOOKS):
            if slug not in text:
                errors.append(f"{rel(root, doc)}: missing cookbook slug {slug!r}")

    orch = root / "managed-agent-cookbooks" / "ORCHESTRATION.md"
    text = read(root, orch, errors)
    checked += 1
    for needle in (
        "spec-author -> spec-impl -> quality-gate -> release-coordinator",
        "Handoff JSON",
        "Host Gates",
        "python3 scripts/managed_agent_check.py",
    ):
        if needle not in text:
            errors.append(f"{rel(root, orch)}: missing orchestration text {needle!r}")

    # WS7-T2: the managed-agent surface is frozen as experimental. Its README
    # cookbook section and this orchestration guide's opening must say so
    # literally, so no marketing site can quietly re-present CMA as co-equal.
    readme = root / "README.md"
    readme_text = read(root, readme, errors)
    checked += 1
    cma_section = section_after(readme_text, "## Managed-agent cookbooks")
    if "experimental" not in cma_section.lower():
        errors.append(
            f"{rel(root, readme)}: the 'Managed-agent cookbooks' section must "
            f"label the surface 'experimental'"
        )

    checked += 1
    orch_opening = "\n".join(text.splitlines()[:10]).lower()
    if "experimental" not in orch_opening:
        errors.append(
            f"{rel(root, orch)}: the opening must label the managed-agent "
            f"surface 'experimental'"
        )
    return checked


def check_orchestrator(root: Path, errors: list[str]) -> int:
    path = root / "scripts" / "orchestrate.py"
    text = read(root, path, errors)
    for slug in sorted(EXPECTED_COOKBOOKS):
        if f'"{slug}"' not in text:
            errors.append(f"{rel(root, path)}: ALLOWED_TARGETS missing {slug!r}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Managed Agent cookbook surface")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    errors: list[str] = []
    checked = 0
    checked += check_inventory(root, errors)
    for slug in sorted(EXPECTED_COOKBOOKS):
        checked += check_one_cookbook(root, slug, errors)
    checked += check_docs(root, errors)
    checked += check_orchestrator(root, errors)

    if errors:
        print(
            f"managed-agent: FAIL - {len(errors)} issue(s) across {checked} check(s):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  x {error}", file=sys.stderr)
        return 1
    print(f"managed-agent: OK - {checked} check(s), 0 issues.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
