#!/usr/bin/env python3
"""Profile a repository for the core-engineering first-run setup skill.

The script is intentionally heuristic and stdlib-only. It gives /core-engineering:ce-init a
machine-readable floor: common languages, package managers, commands, CI,
API/data/security/infrastructure surfaces, and starter policy templates. It
never edits production code. With --write it creates missing docs/plans setup
artifacts and skips existing human-authored files unless --force is explicit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "node_modules", "dist", "build", "target",
    "__pycache__", ".tox", ".idea", ".vscode",
}

LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "dotnet",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".tf": "terraform",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".sql": "sql",
    ".sh": "shell",
}

API_HINTS = (
    "openapi", "swagger", "routes", "router", "controller", "controllers",
    "api", "app.py", "server", "handlers",
)
DATA_HINTS = ("migration", "migrations", "schema.sql", "models", "repository", "repositories")
SECURITY_HINTS = ("auth", "login", "jwt", "oauth", "session", "permission", "rbac", "secrets")
INFRA_HINTS = ("Dockerfile", "docker-compose", "terraform", ".tf", "k8s", "kubernetes", "helm")


def rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def iter_files(root: Path, limit: int = 5000) -> list[Path]:
    files: list[Path] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        base = Path(current)
        for name in names:
            path = base / name
            files.append(path)
            if len(files) >= limit:
                return files
    return files


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def run_git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def detect_git(root: Path) -> dict:
    top = run_git(root, "rev-parse", "--show-toplevel")
    branch = run_git(root, "branch", "--show-current")
    commit = run_git(root, "rev-parse", "--short", "HEAD")
    default_ref = run_git(root, "symbolic-ref", "refs/remotes/origin/HEAD")
    status = run_git(root, "status", "--porcelain")
    return {
        "inside_work_tree": bool(top),
        "top_level": top,
        "branch": branch or None,
        "commit": commit or None,
        "default_branch": default_ref.rsplit("/", 1)[-1] if default_ref else None,
        "dirty": bool(status),
    }


def count_languages(root: Path, files: list[Path]) -> dict:
    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    for path in files:
        lang = LANG_BY_EXT.get(path.suffix)
        if not lang:
            continue
        counts[lang] = counts.get(lang, 0) + 1
        examples.setdefault(lang, [])
        if len(examples[lang]) < 5:
            examples[lang].append(rel(root, path))
    return {
        "counts": dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))),
        "examples": examples,
    }


def package_managers(root: Path) -> list[dict]:
    found: list[dict] = []

    package_json = root / "package.json"
    if package_json.is_file():
        data = read_json(package_json)
        scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
        manager = "npm"
        if (root / "pnpm-lock.yaml").is_file():
            manager = "pnpm"
        elif (root / "yarn.lock").is_file():
            manager = "yarn"
        elif (root / "bun.lockb").is_file() or (root / "bun.lock").is_file():
            manager = "bun"
        found.append({
            "ecosystem": "node",
            "manager": manager,
            "manifest": "package.json",
            "scripts": sorted(scripts),
        })

    if (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file() or (root / "setup.py").is_file():
        manifest = "pyproject.toml" if (root / "pyproject.toml").is_file() else (
            "requirements.txt" if (root / "requirements.txt").is_file() else "setup.py"
        )
        found.append({"ecosystem": "python", "manager": "pip", "manifest": manifest})

    for manifest, ecosystem, manager in (
        ("go.mod", "go", "go"),
        ("Cargo.toml", "rust", "cargo"),
        ("pom.xml", "java", "maven"),
        ("build.gradle", "java", "gradle"),
        ("build.gradle.kts", "kotlin", "gradle"),
        ("Gemfile", "ruby", "bundler"),
    ):
        if (root / manifest).is_file():
            found.append({"ecosystem": ecosystem, "manager": manager, "manifest": manifest})

    csproj = sorted(root.glob("*.csproj"))
    if csproj:
        found.append({"ecosystem": "dotnet", "manager": "dotnet", "manifest": csproj[0].name})

    return found


def has_make_target(root: Path, target: str) -> bool:
    makefile = root / "Makefile"
    if not makefile.is_file():
        return False
    try:
        text = makefile.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return bool(re.search(rf"^{re.escape(target)}\s*:", text, re.MULTILINE))


def derive_commands(root: Path, managers: list[dict]) -> dict:
    commands: dict[str, list[dict]] = {"test": [], "lint": [], "build": [], "start": []}

    for target in commands:
        if has_make_target(root, target):
            commands[target].append({"command": f"make {target}", "confidence": "detected"})

    package_json = root / "package.json"
    if package_json.is_file():
        data = read_json(package_json)
        scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
        manager = next((m["manager"] for m in managers if m.get("ecosystem") == "node"), "npm")
        run = {
            "npm": "npm run",
            "pnpm": "pnpm",
            "yarn": "yarn",
            "bun": "bun run",
        }.get(manager, "npm run")
        for kind, script_names in {
            "test": ("test", "test:unit"),
            "lint": ("lint", "typecheck"),
            "build": ("build",),
            "start": ("dev", "start"),
        }.items():
            for script in script_names:
                if script in scripts:
                    command = f"{run} {script}" if not (manager in {"pnpm", "yarn"} and script == "start") else f"{manager} {script}"
                    commands[kind].append({"command": command, "confidence": "detected"})
                    break

    if any(m.get("ecosystem") == "python" for m in managers):
        if (root / "tests").is_dir() or (root / "pytest.ini").is_file():
            commands["test"].append({"command": "python3 -m pytest", "confidence": "inferred"})
        if (root / "ruff.toml").is_file() or (root / ".ruff.toml").is_file():
            commands["lint"].append({"command": "python3 -m ruff check .", "confidence": "detected"})
        if (root / "pyproject.toml").is_file():
            commands["build"].append({"command": "python3 -m build", "confidence": "inferred"})

    if (root / "go.mod").is_file():
        commands["test"].append({"command": "go test ./...", "confidence": "detected"})
        commands["build"].append({"command": "go build ./...", "confidence": "detected"})
    if (root / "Cargo.toml").is_file():
        commands["test"].append({"command": "cargo test", "confidence": "detected"})
        commands["build"].append({"command": "cargo build", "confidence": "detected"})
        commands["lint"].append({"command": "cargo clippy", "confidence": "inferred"})
    if (root / "pom.xml").is_file():
        commands["test"].append({"command": "mvn test", "confidence": "detected"})
        commands["build"].append({"command": "mvn package", "confidence": "inferred"})
    if (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file():
        gradle = "./gradlew" if (root / "gradlew").is_file() else "gradle"
        commands["test"].append({"command": f"{gradle} test", "confidence": "detected"})
        commands["build"].append({"command": f"{gradle} build", "confidence": "detected"})

    return commands


def detect_ci(root: Path) -> list[dict]:
    checks: list[dict] = []
    gh = root / ".github" / "workflows"
    if gh.is_dir():
        for path in sorted(list(gh.glob("*.yml")) + list(gh.glob("*.yaml"))):
            checks.append({"provider": "github-actions", "path": rel(root, path)})
    for name, provider in (
        ("azure-pipelines.yml", "azure-pipelines"),
        (".gitlab-ci.yml", "gitlab-ci"),
        ("Jenkinsfile", "jenkins"),
        (".circleci/config.yml", "circleci"),
    ):
        path = root / name
        if path.is_file():
            checks.append({"provider": provider, "path": name})
    return checks


def path_contains(path: Path, hints: tuple[str, ...]) -> bool:
    lowered = path.as_posix().lower()
    return any(hint.lower() in lowered for hint in hints)


def detect_surfaces(root: Path, files: list[Path]) -> dict:
    surfaces = {"api": [], "data": [], "security": [], "infra": []}
    for path in files:
        r = rel(root, path)
        if len(r) > 240:
            continue
        if path_contains(path, API_HINTS):
            surfaces["api"].append(r)
        if path_contains(path, DATA_HINTS) or path.suffix == ".sql":
            surfaces["data"].append(r)
        if path_contains(path, SECURITY_HINTS):
            surfaces["security"].append(r)
        if path_contains(path, INFRA_HINTS):
            surfaces["infra"].append(r)
    return {k: sorted(v)[:25] for k, v in surfaces.items()}


def detect_ownership(root: Path) -> dict:
    paths = {}
    for name in ("CODEOWNERS", ".github/CODEOWNERS", "CONTRIBUTING.md", "AGENTS.md", "CLAUDE.md"):
        path = root / name
        if path.is_file():
            paths[name] = rel(root, path)
    return paths


def build_profile(root: Path) -> dict:
    files = iter_files(root)
    managers = package_managers(root)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "root": str(root),
        "git": detect_git(root),
        "inventory": {
            "files_scanned": len(files),
            "truncated": len(files) >= 5000,
        },
        "languages": count_languages(root, files),
        "package_managers": managers,
        "commands": derive_commands(root, managers),
        "ci": detect_ci(root),
        "surfaces": detect_surfaces(root, files),
        "ownership": detect_ownership(root),
        "confidence_notes": [
            "Static profile only; commands are detected or inferred, not executed.",
            "Human policy wins over scanner output.",
        ],
    }


def write_if_missing(path: Path, content: str, force: bool, written: list[str], skipped: list[str]) -> None:
    if path.exists() and not force:
        skipped.append(path.as_posix())
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    written.append(path.as_posix())


def command_block(profile: dict, kind: str) -> str:
    items = profile["commands"].get(kind, [])
    if not items:
        return "- TBD (not detected)\n"
    return "".join(f"- `{item['command']}` ({item['confidence']})\n" for item in items)


def vc_policy(profile: dict) -> str:
    git = profile.get("git", {})
    default_branch = git.get("default_branch") or "main"
    branch = git.get("branch") or "unknown"
    return f"""# Version-Control Policy

Generated by `/core-engineering:ce-init` from a static repository profile. Review before relying
on it for release work.

## Branches

- Protected branch: `{default_branch}` (inferred)
- Current branch at profiling time: `{branch}`
- Shared-history operations (`git push`, PR creation/merge, protected-branch
  commits) stay human-owned.

## Release Profile

- Base branch: `{default_branch}`
- Release branch naming and creation remain human-owned.

## Working Tree

- `/core-engineering:ce-auto-build` requires a clean tree before kickoff.
- Generated SDLC artifacts under `docs/plans/` are project documents and may be
  committed after human review.
"""


def review_policy(profile: dict) -> str:
    return """# Review Policy

Generated by `/core-engineering:ce-init` as a starter calibration. Edit this file to match the
team's real bar.

## Bar

- Block on confirmed high-severity correctness or security findings.
- Treat suspected findings as review evidence unless reproduced.
- Prefer fewer, higher-signal findings over style noise.

## Skip / Calibrate

- Do not review vendored, generated, or third-party code unless the change
  touches its generation or trust boundary.
- Record dismissed recurring finding shapes in `review-learnings.md`; do not
  suppress silently.

## Required Evidence

- Every finding cites `file:line`.
- Security findings name the trust boundary or data class when known.
- Performance findings separate measured evidence from inferred risk.
"""


def patterns(profile: dict) -> str:
    surfaces = profile.get("surfaces", {})
    lines = [
        "# Known Patterns And Hazards",
        "",
        "Generated by `/core-engineering:ce-init`. Entries below are seeded/unverified until a",
        "maintainer confirms them.",
        "",
        "## Seeded Signals",
        "",
    ]
    for name in ("api", "data", "security", "infra"):
        items = surfaces.get(name, [])
        if items:
            lines.append(f"- `{name}` surface detected in: {', '.join(items[:5])}")
        else:
            lines.append(f"- `{name}` surface: not detected by static scan")
    lines.extend([
        "",
        "## Human-Maintained Hazards",
        "",
        "- Add flaky suites, fragile modules, migration caveats, generated paths,",
        "  and known integration risks here.",
    ])
    return "\n".join(lines) + "\n"


def write_artifacts(root: Path, profile: dict, force: bool) -> dict:
    base = root / "docs" / "plans"
    written: list[str] = []
    skipped: list[str] = []
    write_if_missing(
        base / "repo-profile.json",
        json.dumps(profile, indent=2, sort_keys=True) + "\n",
        force,
        written,
        skipped,
    )
    write_if_missing(base / "vc-policy.md", vc_policy(profile), force, written, skipped)
    write_if_missing(base / "review-policy.md", review_policy(profile), force, written, skipped)
    write_if_missing(base / "patterns.md", patterns(profile), force, written, skipped)
    return {
        "written": [rel(root, Path(p)) if Path(p).is_absolute() else p for p in written],
        "skipped_existing": [rel(root, Path(p)) if Path(p).is_absolute() else p for p in skipped],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile a repository for /core-engineering:ce-init")
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--json", action="store_true", help="print profile JSON")
    parser.add_argument("--write", action="store_true", help="write missing docs/plans setup artifacts")
    parser.add_argument("--force", action="store_true", help="overwrite existing setup artifacts")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"repo-profile: root not found: {root}", file=sys.stderr)
        return 2
    profile = build_profile(root)
    if args.write:
        profile["artifact_writes"] = write_artifacts(root, profile, args.force)
    if args.json or not args.write:
        print(json.dumps(profile, indent=2, sort_keys=True))
    else:
        writes = profile.get("artifact_writes", {})
        print(json.dumps(writes, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
