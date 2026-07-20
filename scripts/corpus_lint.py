#!/usr/bin/env python3
"""Lint the human-authored SDLC corpus for drift that manifests can't see.

This is intentionally a narrow, stdlib-only prose lint. It catches the
maintenance failures that made P0 necessary:

  * stale public names from pre-`ce-*` drafts;
  * `/ce-*` references that do not correspond to a shipped skill;
  * missing canonical `SKILL.md` skeleton sections;
  * broken `${CLAUDE_SKILL_DIR}/...` companion-file references;
  * runtime references to contributor docs that are outside the shipped plugin.

It does not try to prove generated project artifact paths under `docs/` exist;
those are created in user repositories at runtime.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SKILL_HEADINGS = (
    "Runtime Inputs",
    "Execution Contract",
    "Escalation",
    "Honest Limitations",
)

FORBIDDEN_PUBLIC_ALIASES = {
    "UX Chaos": "/ce-ux-audit",
    "ux-chaos": "/ce-ux-audit",
    "sec-probe": "/ce-probe-sec",
    "/security-review": "/ce-review",
}

CE_COMMAND_RE = re.compile(r"(?<![\w/.-])/(ce-[A-Za-z0-9-]+)\b")
SKILL_DIR_REF_RE = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/([A-Za-z0-9_.\-/*<>]+)")
REPO_ONLY_DOC_REF_RE = re.compile(r"docs/contributing/[A-Za-z0-9_./-]+")

def skills_roots(root: Path) -> list[Path]:
    """Every marketplace plugin's skills/ dir — the corpus lint's known-name
    universe is the union across plugins, so a cross-plugin `/ce-idea-score`
    mention stays valid after the idea trio moves to its own plugin."""
    return sorted(p for p in (root / "plugins").glob("*/skills") if p.is_dir())


def corpus_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    patterns = [
        "README.md",
        "CLAUDE.md",
        "docs/**/*.md",
        "plugins/*/agents/*.md",
        "plugins/*/skills/**/*.md",
    ]
    for pattern in patterns:
        paths.extend(sorted(root.glob(pattern)))
    return [p for p in paths if p.is_file()]


def skill_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for skills_root in skills_roots(root):
        files.extend(skills_root.glob("*/SKILL.md"))
    return sorted(files)


def skill_names(root: Path) -> set[str]:
    return {p.parent.name for p in skill_files(root)}


def has_heading(text: str, heading: str) -> bool:
    for line in text.splitlines():
        if not line.startswith("## "):
            continue
        title = line[3:].strip()
        if title == heading:
            return True
        if title.startswith(heading):
            suffix = title[len(heading):].lstrip()
            if suffix and suffix[0] in "(-[—`":
                return True
    return False


def check_required_headings(root: Path, errors: list[str]) -> int:
    checked = 0
    for path in skill_files(root):
        checked += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{rel(root, path)}: cannot read: {exc}")
            continue
        for heading in REQUIRED_SKILL_HEADINGS:
            if not has_heading(text, heading):
                errors.append(f"{rel(root, path)}: missing required heading '## {heading}'")
    return checked


def check_public_names(root: Path, errors: list[str]) -> int:
    names = skill_names(root)
    checked = 0
    alias_patterns = {
        alias: re.compile(rf"(?<![A-Za-z0-9-]){re.escape(alias)}(?![A-Za-z0-9-])")
        for alias in FORBIDDEN_PUBLIC_ALIASES
    }
    for path in corpus_files(root):
        checked += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{rel(root, path)}: cannot read: {exc}")
            continue

        for alias, pattern in alias_patterns.items():
            replacement = FORBIDDEN_PUBLIC_ALIASES[alias]
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{rel(root, path)}:{line}: stale public alias {alias!r}; "
                    f"use {replacement}"
                )

        for match in CE_COMMAND_RE.finditer(text):
            command = match.group(1)
            if command not in names:
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{rel(root, path)}:{line}: references unknown skill '/{command}'"
                )
    return checked


def check_skill_dir_refs(root: Path, errors: list[str]) -> int:
    checked = 0
    docs = [
        (skills_root, path)
        for skills_root in skills_roots(root)
        for path in sorted(skills_root.glob("**/*.md"))
    ]
    for skills_root, path in docs:
        checked += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{rel(root, path)}: cannot read: {exc}")
            continue
        try:
            skill_name = path.relative_to(skills_root).parts[0]
        except ValueError:
            continue
        skill_root = skills_root / skill_name
        for match in REPO_ONLY_DOC_REF_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(
                f"{rel(root, path)}:{line}: references repo-only contributor doc "
                f"{match.group(0)!r}; installed plugins contain only their plugin "
                "subtree, so keep the runtime instruction self-contained and cite "
                "the standard by name"
            )
        for match in SKILL_DIR_REF_RE.finditer(text):
            if "*" in match.group(1) or "<" in match.group(1):
                continue
            target = skill_root / match.group(1)
            if not target.exists():
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{rel(root, path)}:{line}: skill companion reference "
                    f"${{CLAUDE_SKILL_DIR}}/{match.group(1)} does not exist"
                )
    return checked


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint SDLC skill/docs corpus drift")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="repository root")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    errors: list[str] = []
    checked = 0
    if not skill_files(root):
        errors.append("structure: no SKILL.md files found under any plugins/*/skills")
    checked += check_required_headings(root, errors)
    checked += check_public_names(root, errors)
    checked += check_skill_dir_refs(root, errors)

    if errors:
        print(f"corpus-lint: FAIL — {len(errors)} issue(s) across {checked} file(s):", file=sys.stderr)
        for error in errors:
            print(f"  ✗ {error}", file=sys.stderr)
        return 1
    print(f"corpus-lint: OK — {checked} file(s) checked, 0 issues.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
