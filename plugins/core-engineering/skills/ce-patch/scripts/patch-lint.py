#!/usr/bin/env python3
"""Deterministic admission and diff checks for the express-only `/ce-patch` lane.

The checker accepts a transient JSON candidate stub:

    {"files": ["src/widget.py", "tests/test_widget.py"], "desc": "fix widget"}

Default mode runs conservative pre-write admission. ``--post --base <ref>`` reruns
admission and checks the actual working-tree diff. ``--express`` remains an accepted
no-op alias for callers written before the lane became express-only.

Exit contract:
    0  pass
    1  policy refusal; route to /ce-plan
    2  invalid/inconclusive input or tooling; route to /ce-plan
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


class PatchLintError(Exception):
    """Admission cannot be decided confidently (exit 2)."""


EXPRESS_FILE_CAP = 2

# Reviewer-owned or security-sensitive path segments. Prefix matching is
# intentionally conservative: ``authorization`` and ``paymentService`` both trip.
REVIEWER_TRIGGER_PATH = re.compile(
    r"(^|/)("
    r"auth|login|logout|signin|signup|session|oauth|oidc|saml|jwt|sso"
    r"|secret|credential|token|password|passwd|crypto|keystore|vault"
    r"|payment|billing|checkout|invoice|charge|stripe|paypal|wallet"
    r"|delet|erase|purge|retention|privacy|pii|gdpr"
    r"|i18n|l10n|locale|translation"
    r"|a11y|accessibility|aria"
    r")",
    re.I,
)

REVIEWER_TRIGGER_CONTENT = re.compile(
    r"\b("
    r"auth\w*|login|logout|sign[- ]?in|sign[- ]?up|oauth|oidc|saml|jwt|sso|session"
    r"|secret\w*|credential\w*|password\w*|token|crypto\w*|encrypt\w*|decrypt\w*"
    r"|payment\w*|billing|checkout|invoice|charge|stripe|paypal"
    r"|delet\w*|eras\w*|purg\w*|retention|privacy|pii|gdpr"
    r"|i18n|l10n|locale\w*|translat\w*"
    r"|a11y|accessibilit\w*|aria"
    r")\b",
    re.I,
)

DEP_MANIFEST = re.compile(
    r"(^|/)("
    r"package(-lock)?\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml"
    r"|requirements[^/]*\.txt|Pipfile(\.lock)?|poetry\.lock|pyproject\.toml"
    r"|setup\.py|setup\.cfg|constraints[^/]*\.txt"
    r"|Gemfile(\.lock)?|go\.mod|go\.sum|Cargo\.(toml|lock)"
    r"|pom\.xml|build\.gradle(\.kts)?|ivy\.xml"
    r"|composer\.(json|lock)|packages\.config|paket\.dependencies"
    r")$|\.(csproj|fsproj|vbproj)$",
    re.I,
)

# Durable state/schema files and common persistence writes.
DURABLE_FILE = re.compile(
    r"(^|/)(migrations?|migrate)/|\.(sql|ddl)$|schema\.(prisma|sql|rb)$"
    r"|\b\d{10,}[-_].*\.(js|ts|py|rb)$",
    re.I,
)
DURABLE_LINE = re.compile(
    r"\bCREATE\s+TABLE\b|\bALTER\s+TABLE\b|\bCREATE\s+INDEX\b"
    r"|\bINSERT\s+INTO\b|\bUPDATE\s+\w+\s+SET\b"
    r"|\bcreate_table\b|\badd_column\b|\bSchema\s*\("
    r"|\.(save|saveChanges|saveChangesAsync|persist|insert|insertOne|insertMany"
    r"|create|createMany|upsert|bulkCreate)\s*\("
    r"|\b(session|db|ctx|context|em|entityManager|repo|repository)\."
    r"(add|addAsync|merge|commit)\b"
    r"|\.Add(Async|Range)?\s*\("
    r"|\b(write_file|writeFile|writeFileSync|appendFile|appendFileSync)\b"
    r"|\bfs\.(write|append)"
    r"|\b(localStorage|sessionStorage|redis|cache|kv|store)\."
    r"(set|setItem|put)\s*\("
    r"|\bmigrations?\.(create|add)\b",
    re.I,
)

DESTRUCTIVE_LINE = re.compile(
    r"\bDROP\s+TABLE\b|\bDROP\s+DATABASE\b|\bDROP\s+COLLECTION\b"
    r"|\bTRUNCATE\b|\bDELETE\s+FROM\b|\bdrop_table\b|\bdropCollection\b"
    r"|\.(delete|deleteOne|deleteMany|destroy|drop|remove)\s*\("
    r"|\b(os\.(remove|unlink|rmdir)|shutil\.rmtree|File\.Delete|Directory\.Delete)\b"
    r"|\b(unlink|unlinkSync|rm|rmSync|rmdir|rmdirSync)\s*\("
    r"|\brm\s+-rf\b|\brmtree\b",
    re.I,
)

PUBLIC_CONTRACT_PATH = re.compile(
    r"(^|/)(api|routes?|endpoints?|controllers?|cli|commands?|public|contracts?"
    r"|proto|openapi|graphql|config)(/|$)"
    r"|(^|/)(openapi|swagger)\.(json|ya?ml)$|\.proto$",
    re.I,
)
PUBLIC_CONTRACT_CONTENT = re.compile(
    r"\b(public\s+(api|interface|contract)|api\s+(route|endpoint|response)"
    r"|endpoint|response\s+shape|request\s+shape|cli\s+(flag|option|command)"
    r"|command[- ]line\s+(flag|option)|config(uration)?\s+(key|contract)"
    r"|environment\s+variable|wire\s+format|protocol|openapi|graphql|protobuf)\b",
    re.I,
)
NEW_SURFACE_LINE = re.compile(
    r"^\s*export\s+(?!type\b|interface\b|//)"
    r"|^\s*public\s+(?!class\b|abstract\b)"
    r"|@(app|router|route|api|blueprint|bp)\."
    r"(get|post|put|patch|delete|route)\b"
    r"|\.(add_argument|addArgument|add_option|option|addOption|addCommand)\s*\(",
    re.I,
)

DURABLE_INTENT_CONTENT = re.compile(
    r"\b(schema|migration|database|persist\w*|durable\s+state|stored?\s+field"
    r"|queue|event\s+(schema|contract)|cache\s+write|write\s+to\s+disk)\b",
    re.I,
)


def _norm(path: str) -> str:
    path = path.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PatchLintError(f"git {' '.join(args)} could not run: {exc}") from exc
    if result.returncode != 0:
        raise PatchLintError(
            f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout


def _git_toplevel(start: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def load_candidate(arg: Path) -> tuple[list[str], str, Path]:
    """Load ``express.json`` from a file or a directory containing that file."""
    stub = arg / "express.json" if arg.is_dir() else arg
    if not stub.is_file():
        raise PatchLintError(f"candidate stub not found: {stub}")
    try:
        data = json.loads(stub.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PatchLintError(f"candidate stub is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise PatchLintError(f"candidate stub could not be read: {exc}") from exc
    if not isinstance(data, dict):
        raise PatchLintError("candidate stub must be a JSON object with `files` and `desc`")
    files = data.get("files")
    if not isinstance(files, list) or not files:
        raise PatchLintError("candidate `files` must be a non-empty list")
    if not all(isinstance(path, str) and path.strip() for path in files):
        raise PatchLintError("candidate `files` entries must be non-empty path strings")
    desc = data.get("desc")
    if not isinstance(desc, str) or not desc.strip():
        raise PatchLintError("candidate `desc` must be a non-empty string")
    return [_norm(path) for path in files], " ".join(desc.split()), stub.resolve()


def resolve_repo(stub: Path) -> Path:
    repo = _git_toplevel(stub.parent) or _git_toplevel(Path.cwd())
    if repo is None:
        raise PatchLintError(
            "no git worktree found; ownership and post-diff checks are inconclusive"
        )
    return repo


def check_paths(files: list[str]) -> list[str]:
    hard: list[str] = []
    if len(files) > EXPRESS_FILE_CAP:
        hard.append(
            f"E1: patch admits at most {EXPRESS_FILE_CAP} candidate files; got {len(files)}"
        )
    if len(set(files)) != len(files):
        hard.append("E1: candidate paths must be unique")
    for path in files:
        pure = PurePosixPath(path)
        if not path or pure.is_absolute() or ".." in pure.parts or path == ".":
            hard.append(f"E1: `{path}` is not a safe repository-relative path")
        if pure.parts and pure.parts[0] == ".git":
            hard.append(f"E1: `{path}` targets git metadata")
    return hard


def _safe_repo_path(path: str) -> bool:
    pure = PurePosixPath(path)
    return (
        bool(path)
        and not pure.is_absolute()
        and ".." not in pure.parts
        and path != "."
        and not (pure.parts and pure.parts[0] == ".git")
    )


def check_collisions(repo: Path, files: list[str]) -> list[str]:
    """Refuse ownership collisions; malformed ownership data is inconclusive."""
    plans = repo / "docs" / "plans"
    if not plans.is_dir():
        return []
    candidates = set(files)
    hard: list[str] = []
    for tasks_path in sorted(plans.glob("*/specs/*/tasks.json")):
        try:
            data = json.loads(tasks_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PatchLintError(
                f"E2 ownership data cannot be read confidently at {tasks_path}: {exc}"
            ) from exc
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if not isinstance(tasks, list):
            raise PatchLintError(f"E2 ownership data has no tasks array: {tasks_path}")
        for task in tasks:
            if not isinstance(task, dict):
                raise PatchLintError(f"E2 ownership data has a non-object task: {tasks_path}")
            owned = task.get("files", [])
            if not isinstance(owned, list) or not all(isinstance(p, str) for p in owned):
                raise PatchLintError(
                    f"E2 ownership data has an invalid files array: {tasks_path}"
                )
            for path in sorted(candidates & {_norm(p) for p in owned}):
                rel = tasks_path.relative_to(repo)
                hard.append(
                    f"E2: candidate `{path}` is already owned by task "
                    f"{task.get('id', '?')} in {rel}"
                )
    return hard


def check_ignored(repo: Path, files: list[str]) -> list[str]:
    hard: list[str] = []
    for path in files:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), "check-ignore", "-q", "--", path],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PatchLintError(f"git check-ignore could not classify `{path}`: {exc}") from exc
        if result.returncode == 0:
            hard.append(
                f"E1: candidate `{path}` is ignored by git, so the diff gate cannot observe it"
            )
        elif result.returncode not in (1,):
            raise PatchLintError(f"git check-ignore could not classify candidate `{path}`")
    return hard


def check_screen(files: list[str], desc: str, repo: Path) -> list[str]:
    hard = check_paths(files)
    # Do not pass unsafe paths to git/path scanners. E1 already makes the candidate
    # ineligible, and probing an escaping path would turn a policy refusal into an
    # unrelated tool error. Safe over-cap candidates continue so all refusal reasons
    # can be reported in one pass.
    if any(not _safe_repo_path(path) for path in files):
        return hard
    hard.extend(check_ignored(repo, files))
    hard.extend(check_collisions(repo, files))

    for path in files:
        if REVIEWER_TRIGGER_PATH.search(path):
            hard.append(f"E3: `{path}` is a reviewer-trigger surface")
        if DEP_MANIFEST.search(path):
            hard.append(f"E4: `{path}` is a dependency manifest or lock file")
        if DURABLE_FILE.search(path):
            hard.append(f"E5: `{path}` looks like a schema, migration, or durable artifact")
        if PUBLIC_CONTRACT_PATH.search(path):
            hard.append(f"E5: `{path}` looks like a public contract surface")

    if REVIEWER_TRIGGER_CONTENT.search(desc):
        hard.append("E3: the change request names a reviewer-trigger surface")
    if DURABLE_INTENT_CONTENT.search(desc) or DURABLE_LINE.search(desc):
        hard.append("E5: the change request names durable-state or schema work")
    if DESTRUCTIVE_LINE.search(desc):
        hard.append("E5: the change request names a destructive operation")
    if PUBLIC_CONTRACT_CONTENT.search(desc):
        hard.append("E5: the change request names a public contract change")
    return hard


def gather_diff(
    repo: Path, base: str, excluded_file: str | None
) -> tuple[set[str], list[tuple[str, str]], set[str]]:
    """Return changed paths, added lines, and deleted paths since ``base``."""
    try:
        _git(repo, "rev-parse", "--verify", "--quiet", base + "^{commit}")
    except PatchLintError as exc:
        raise PatchLintError(f"base ref `{base}` does not resolve in this repository") from exc

    def keep(path: str) -> bool:
        return not excluded_file or path != excluded_file

    changed = {
        _norm(path)
        for path in _git(repo, "diff", "--name-only", base).splitlines()
        if path.strip() and keep(_norm(path))
    }
    deleted = {
        _norm(path)
        for path in _git(repo, "diff", "--diff-filter=D", "--name-only", base).splitlines()
        if path.strip() and keep(_norm(path))
    }
    untracked = [
        _norm(path)
        for path in _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        if path.strip() and keep(_norm(path))
    ]
    changed.update(untracked)

    added_lines: list[tuple[str, str]] = []
    current = "?"
    for line in _git(repo, "diff", "--unified=0", base).splitlines():
        if line.startswith("+++ b/"):
            current = _norm(line[6:])
        elif line.startswith("+") and not line.startswith("+++") and keep(current):
            added_lines.append((current, line[1:]))
    for path in untracked:
        try:
            text = (repo / path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise PatchLintError(f"untracked candidate `{path}` could not be read: {exc}") from exc
        added_lines.extend((path, line) for line in text.splitlines())
    return changed, added_lines, deleted


def check_post_diff(
    changed: set[str], added_lines: list[tuple[str, str]], deleted: set[str], files: list[str]
) -> list[str]:
    hard: list[str] = []
    frozen = set(files)
    if not changed:
        hard.append("H9: no working-tree diff exists for the requested patch")
    for path in sorted(changed - frozen):
        hard.append(f"H9: diff touches `{path}` outside the frozen candidate set")
    for path in sorted(path for path in changed if DURABLE_FILE.search(path)):
        hard.append(f"H8: `{path}` looks like a schema, migration, or durable artifact")
    for path in sorted(deleted):
        hard.append(f"H10: diff deletes `{path}`")

    seen: set[tuple[str, str, str]] = set()
    for path, line in added_lines:
        excerpt = line.strip()[:120]
        for code, pattern, label in (
            ("H8", DURABLE_LINE, "durable-state write"),
            ("H10", DESTRUCTIVE_LINE, "destructive operation"),
            ("H11", NEW_SURFACE_LINE, "new public contract surface"),
        ):
            if pattern.search(line) and (code, path, excerpt) not in seen:
                seen.add((code, path, excerpt))
                hard.append(f"{code}: {label} in {path}: `{excerpt}`")
    return hard


def run_admission(arg: Path) -> tuple[list[str], list[str]]:
    files, desc, stub = load_candidate(arg)
    repo = resolve_repo(stub)
    return check_screen(files, desc, repo), []


def run_post(arg: Path, base: str | None) -> tuple[list[str], list[str]]:
    files, desc, stub = load_candidate(arg)
    repo = resolve_repo(stub)
    if not base:
        raise PatchLintError("--post requires --base <commit>")
    hard = check_screen(files, desc, repo)
    excluded = None
    try:
        excluded = _norm(str(stub.relative_to(repo)))
    except ValueError:
        pass
    changed, added_lines, deleted = gather_diff(repo, base, excluded)
    hard.extend(check_post_diff(changed, added_lines, deleted, files))
    return hard, []


def emit(mode: str, candidate: Path, hard: list[str], advisory: list[str], as_json: bool) -> int:
    status = "fail" if hard else "pass"
    if as_json:
        print(
            json.dumps(
                {
                    "status": status,
                    "mode": mode,
                    "candidate": str(candidate),
                    "hard_failures": hard,
                    "advisory": advisory,
                    "route": "/ce-plan" if hard else None,
                },
                indent=2,
            )
        )
        return 1 if hard else 0

    print(f"patch-lint [{mode}]: {candidate}")
    if hard:
        print(f"\n  FAIL — {len(hard)} refusal(s):")
        for finding in hard:
            print(f"    x {finding}")
        print("\n  -> route directly to /ce-plan; do not edit or widen /ce-patch.")
    else:
        print("\n  PASS — express-only patch checks hold.")
    print()
    return 1 if hard else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Admission and post-diff gate for the express-only /ce-patch lane."
    )
    parser.add_argument(
        "candidate",
        help="express.json candidate stub, or a directory containing express.json",
    )
    parser.add_argument(
        "--express",
        action="store_true",
        help="backward-compatible alias; /ce-patch is always express-only",
    )
    parser.add_argument("--post", action="store_true", help="check the actual diff")
    parser.add_argument("--base", help="git commit captured before patch-owned edits")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    mode = "post" if args.post else "admission"
    candidate = Path(args.candidate)
    try:
        if args.post:
            hard, advisory = run_post(candidate, args.base)
        else:
            if args.base:
                parser.error("--base is only valid with --post")
            hard, advisory = run_admission(candidate)
    except PatchLintError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "mode": mode,
                        "candidate": str(candidate),
                        "message": str(exc),
                        "route": "/ce-plan",
                    }
                )
            )
        else:
            print(f"patch-lint [{mode}]: ERROR — {exc}", file=sys.stderr)
            print("  -> route directly to /ce-plan; admission is inconclusive.", file=sys.stderr)
        return 2
    return emit(mode, candidate, hard, advisory, args.json)


if __name__ == "__main__":
    sys.exit(main())
