#!/usr/bin/env python3
"""dep-guard.py — the on-disk gate against hallucinated / slopsquatted dependencies.

LLMs hallucinate package names at scale (USENIX Security 2025: ~19.7% of suggested
packages across 576k samples did not exist), and attackers pre-register those
hallucinated names as malware ("slopsquatting"), so an agent's `npm install <pkg>` /
`pip install <pkg>` of a confabulated name pulls a payload. The defense is to verify a
NEW dependency *before* it is installed — that it really exists, is not suspiciously
brand-new, and is not a typo of a popular package.

This script does the **deterministic, offline half** of that defense, exactly as
test-guard.py / spec-lint.py / patch-lint.py do their checks offline and stdlib-only:
it DETECTS new direct dependencies added to a manifest since a baseline, checks each
against a caller-supplied **declared/verified** allowlist (the slopsquatting smoking
gun is a dep that entered the manifest the agent never verified), and flags any new
name that is edit-distance-close to a popular package (an offline typosquat backstop).

What it does NOT do — by design, because it would break the stdlib-only + offline +
deterministic invariant every gate in this corpus holds: it never touches the network.
EXISTENCE (does the registry return the package), AGE (is it suspiciously new), and
live typo confirmation are the registry half — performed by the **agent** (`npm view`,
`pip index versions`, or an install proxy like Aikido Safe Chain) as a skill-prose
discipline *before* install, never here. A typosquat flag from this script is a
*material finding to adjudicate* (then the agent's registry check confirms or clears
it), never an automatic verdict on its own.

Mode (git, mirroring test-guard's --base mode):
  --base <ref> [--head <ref>]   Diff the dependency manifests that changed between
                                `base` and `head` (default: the working tree); report
                                the NEW direct dependencies each added.
  --declared name1,name2,...    The deps the agent verified this run (existence-checked,
                                recorded). A new dep NOT in this set is UNDECLARED — a
                                hard failure (the smoking gun). The undeclared check is
                                **ON by default**: an empty / omitted set fails *every*
                                new dep (fail-safe — a forgotten flag never silent-passes).
  --detect-only                 Turn the undeclared check OFF — report new deps + typo
                                flags only. For ad-hoc exploration, never as a gate.

HARD checks (a FAIL -> exit 1):
  D1  an added direct dependency is not in --declared (an undeclared / unverified dep
      entered the manifest). Only evaluated when --declared is supplied.

ADVISORY (warnings only; never change the exit code):
  A1  an added dependency's name is edit-distance-close (>= 0.85 similarity, not exact)
      to a popular package in the bundled list — a possible typosquat; the agent's
      registry existence-check is the authority.

Ecosystems (parsed): npm (package.json), Python (pyproject.toml / requirements*.txt),
NuGet (*.csproj / Directory.Packages.props), Go (go.mod), and Cargo (Cargo.toml). A
manifest of a still-unparsed ecosystem (Maven pom.xml / Gradle) that changed in the diff
exits 2 (LOUD — manual check required), never a silent skip.

Exit codes (identical contract to spec-lint / test-guard / patch-lint):
    0  PASS  — no undeclared deps (advisory typo flags may still print)
    1  FAIL  — at least one undeclared dependency (D1)
    2  ERROR — base unresolvable / not a git repo / a changed manifest's ecosystem has
               no parser / a manifest is unparseable; the caller falls back to the
               manual dependency check (loudly)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import tomllib  # Python 3.11+ stdlib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


class DepGuardError(Exception):
    """Inputs cannot be loaded / no parser / git unavailable -> exit 2, caller falls back."""


# --- which manifest files map to which ecosystem ------------------------------------
# Supported (Phase 1) have a parser; "stub" ecosystems are recognized but unparsed ->
# a changed one exits 2 LOUDLY rather than silently missing a dependency add.
SUPPORTED = {
    "package.json": "npm",
    "pyproject.toml": "pypi-pyproject",
    "Cargo.toml": "cargo",
    "go.mod": "go",
    # NuGet Central Package Management: versions/global refs live in a props file
    # (per-project .csproj carry versionless PackageReference); parsed as the same kind.
    "Directory.Packages.props": "nuget",
}
STUB_MANIFESTS = {  # recognized manifests still without a parser -> exit 2 (LOUD)
    "pom.xml": "maven",
    "build.gradle": "gradle", "build.gradle.kts": "gradle",
}
# Match the many pip layouts: requirements.txt, dev-requirements.txt, requirements.in
# (pip-tools direct-dep source), and the split `requirements/<name>.{txt,in}` directory
# — the last is common and was a silent blind spot if only `requirements*.txt` matched.
REQUIREMENTS_RE = re.compile(
    r"(^|/)(?:[\w.-]*requirements[\w.-]*\.(?:txt|in)"
    r"|requirements/[\w./-]+\.(?:txt|in))$",
    re.I,
)
CSPROJ_RE = re.compile(r"\.csproj$")


def classify(path: str) -> str | None:
    """Return a parser key for a manifest path, 'STUB:<eco>' for a known-unparsed one,
    or None if the path is not a dependency manifest at all."""
    name = path.rsplit("/", 1)[-1]
    if name in SUPPORTED:
        return SUPPORTED[name]
    if REQUIREMENTS_RE.search(path):
        return "pypi-requirements"
    if CSPROJ_RE.search(path):
        return "nuget"
    if name in STUB_MANIFESTS:
        return f"STUB:{STUB_MANIFESTS[name]}"
    return None


# --- direct-dependency parsers (offline, stdlib) ------------------------------------
# Parse the MANIFEST (direct deps), never the lockfile — a lockfile carries transitive
# resolution and would over-report a transitive package as a new direct dependency.

def _norm(n: str) -> str:
    """Normalize a package name for comparison: lowercase, collapse - _ . runs (so
    Flask == flask, flask_x == flask-x). Leaves an npm @scope/name's @ and / intact."""
    return re.sub(r"[-_.]+", "-", n.strip().lower())


def parse_npm(text: str) -> set:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise DepGuardError(f"package.json is not valid JSON: {e}") from e
    names = set()
    for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        d = data.get(key)
        if isinstance(d, dict):
            names.update(d.keys())
    return {_norm(n) for n in names}


def _pep508_name(spec: str) -> str | None:
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec)
    return m.group(1) if m else None


def parse_pyproject(text: str) -> set:
    if tomllib is None:
        raise DepGuardError("pyproject.toml needs tomllib (Python 3.11+) — manual check required")
    try:
        data = tomllib.loads(text)
    except Exception as e:  # noqa: BLE001 — any TOML failure is exit-2 fallback
        raise DepGuardError(f"pyproject.toml is not valid TOML: {e}") from e
    names = set()
    proj = data.get("project", {}) if isinstance(data.get("project"), dict) else {}
    for dep in proj.get("dependencies", []) or []:
        n = _pep508_name(dep) if isinstance(dep, str) else None
        if n:
            names.add(n)
    for grp in (proj.get("optional-dependencies", {}) or {}).values():
        for dep in grp or []:
            n = _pep508_name(dep) if isinstance(dep, str) else None
            if n:
                names.add(n)
    poetry = data.get("tool", {}).get("poetry", {}) if isinstance(data.get("tool"), dict) else {}
    for key in ("dependencies", "dev-dependencies"):
        d = poetry.get(key)
        if isinstance(d, dict):
            names.update(k for k in d if k.lower() != "python")
    return {_norm(n) for n in names}


def parse_requirements(text: str) -> set:
    names = set()
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#") or ln.startswith("-"):
            continue  # blank, comment, or option line (-e, -r, --hash, …)
        head = ln.split("#", 1)[0].strip()
        # PEP 508 direct reference `name @ url` carries a real registry name on the LHS
        # (a pinned-URL install of a confabulated name is itself a slopsquat vector) — keep it.
        if " @ " in head:
            head = head.split(" @ ", 1)[0].strip()
        elif "://" in head:
            continue  # a bare URL / VCS install (no LHS name) — nothing to verify here
        n = _pep508_name(head)
        if n:
            names.add(_norm(n))
    return names


def parse_csproj(text: str) -> set:
    """NuGet direct deps from an MSBuild project (.csproj) or a central-package file
    (Directory.Packages.props). The dependency name is always the `Include` attribute of
    a `PackageReference` (per-project), `PackageVersion`, or `GlobalPackageReference`
    (central). Tags are matched by LOCAL name so both SDK-style (no namespace) and legacy
    `xmlns=...msbuild/2003` projects parse. XML parse failure -> exit-2 fallback."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise DepGuardError(f"NuGet manifest is not valid XML: {e}") from e
    names = set()
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]  # strip the {namespace} prefix if present
        if tag in ("PackageReference", "PackageVersion", "GlobalPackageReference"):
            inc = el.get("Include") or el.get("include")
            if inc and inc.strip():
                names.add(inc.strip())
    return {_norm(n) for n in names}


def _gomod_module(line: str) -> str | None:
    """The module path from one require-line, or None for an `// indirect` dep (transitive)
    or an empty line. A non-indirect trailing comment is kept."""
    if "//" in line:
        code, comment = line.split("//", 1)
        if "indirect" in comment:
            return None  # transitive dependency — not a direct add
        line = code.strip()
    tok = line.split()
    return tok[0] if tok else None


def parse_gomod(text: str) -> set:
    """Go direct deps from go.mod: single-line `require <module> <version>` and the
    block `require ( ... )` form. `// indirect` lines (transitive) are dropped; the dep
    name is the module path (first token)."""
    names = set()
    in_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if in_block:
            if line.startswith(")"):
                in_block = False
                continue
            m = _gomod_module(line)
            if m:
                names.add(m)
            continue
        parts = line.split(None, 1)
        if parts[0] != "require":
            continue
        rest = parts[1].strip() if len(parts) > 1 else ""
        if rest.startswith("("):
            in_block = True
            rest = rest[1:].strip()
            if rest and not rest.startswith(")"):
                m = _gomod_module(rest)
                if m:
                    names.add(m)
        elif rest:
            m = _gomod_module(rest)
            if m:
                names.add(m)
    return {_norm(n) for n in names}


def parse_cargo(text: str) -> set:
    """Cargo direct deps from Cargo.toml: [dependencies], [dev-dependencies],
    [build-dependencies], [workspace.dependencies], and any target.*.dependencies (incl.
    its dev/build tables). A rename table (`local = { package = "real-name", ... }`) is
    resolved to the real registry crate — the typosquat target is the real name."""
    if tomllib is None:
        raise DepGuardError("Cargo.toml needs tomllib (Python 3.11+) — manual check required")
    try:
        data = tomllib.loads(text)
    except Exception as e:  # noqa: BLE001 — any TOML failure is exit-2 fallback
        raise DepGuardError(f"Cargo.toml is not valid TOML: {e}") from e
    names: set[str] = set()

    def _collect(tbl) -> None:
        if not isinstance(tbl, dict):
            return
        for key, spec in tbl.items():
            if isinstance(spec, dict):
                real = spec.get("package")
                names.add(real if isinstance(real, str) and real.strip() else key)
            else:
                names.add(key)

    for sect in ("dependencies", "dev-dependencies", "build-dependencies"):
        _collect(data.get(sect))
    ws = data.get("workspace")
    if isinstance(ws, dict):
        _collect(ws.get("dependencies"))
    target = data.get("target")
    if isinstance(target, dict):
        for tbl in target.values():
            if isinstance(tbl, dict):
                for sect in ("dependencies", "dev-dependencies", "build-dependencies"):
                    _collect(tbl.get(sect))
    return {_norm(n) for n in names}


def parse_manifest(kind: str, text: str) -> set:
    if kind == "npm":
        return parse_npm(text)
    if kind == "pypi-pyproject":
        return parse_pyproject(text)
    if kind == "pypi-requirements":
        return parse_requirements(text)
    if kind == "nuget":
        return parse_csproj(text)
    if kind == "go":
        return parse_gomod(text)
    if kind == "cargo":
        return parse_cargo(text)
    raise DepGuardError(f"no parser for manifest kind {kind!r}")


_ECOSYSTEM = {
    "npm": "npm",
    "pypi-pyproject": "pypi",
    "pypi-requirements": "pypi",
    "nuget": "nuget",
    "go": "go",
    "cargo": "cargo",
}


def ecosystem_of(kind: str) -> str:
    return _ECOSYSTEM.get(kind, "pypi")


# --- offline typosquat backstop -----------------------------------------------------

def _osa(a: str, b: str) -> int:
    """Optimal string alignment distance — Levenshtein plus *adjacent transposition*,
    so a classic typosquat (loadsh↔lodash, reqeusts↔requests: a single swap) counts as
    distance 1, not 2. Plain Levenshtein scored those 2 and missed them at the ratio cut."""
    la, lb = len(a), len(b)
    if a == b:
        return 0
    if not a:
        return lb
    if not b:
        return la
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)  # transposition
    return d[la][lb]


def load_popular(override: str | None) -> dict:
    """Load the bundled popular-package list (a script-relative sibling, so each forked
    copy reads its own). Missing list is non-fatal — the typo backstop just goes quiet."""
    ecos = ("npm", "pypi", "nuget", "go", "cargo")
    path = Path(override) if override else (Path(__file__).resolve().parent / "popular-packages.json")
    if not path.is_file():
        return {eco: set() for eco in ecos}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {eco: set() for eco in ecos}
    return {eco: {_norm(n) for n in data.get(eco, [])} for eco in ecos}


def typo_match(name: str, eco: str, popular: dict, threshold: float = 0.85) -> str | None:
    """Closest popular name that looks like a typosquat of `name` — flagged when the
    edit distance is small (<= 2 absolute, for names >= 5 chars, so short transposition
    typos like loadsh/reqeusts fire) OR the normalized similarity is >= threshold.
    An exact match means the dep IS the popular package, not a typo — never flagged."""
    best, best_score = None, -1.0
    for pop in popular.get(eco, ()):
        if pop == name:
            return None  # exact — this is the real package
        dist = _osa(name, pop)
        sim = 1.0 - dist / max(len(name), len(pop))
        close = sim >= threshold or (dist <= 2 and max(len(name), len(pop)) >= 5)
        if close and sim > best_score:
            best, best_score = pop, sim
    return best


# --- git plumbing (subprocess only, mirroring test-guard / patch-lint) --------------

def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise DepGuardError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def _git_toplevel(start: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        if out.returncode == 0:
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _show(repo: Path, ref: str, path: str) -> str | None:
    out = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{path}"],
        capture_output=True, text=True,
    )
    return out.stdout if out.returncode == 0 else None


def _read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None


# --- the run ------------------------------------------------------------------------

def run(repo: Path, base: str, head: str | None, declared: set | None, popular: dict) -> tuple[list, list, list]:
    """Returns (hard, advisory, added) where added is [{name, ecosystem, manifest}]."""
    try:
        _git(repo, "rev-parse", "--verify", "--quiet", base + "^{commit}")
    except DepGuardError:
        raise DepGuardError(
            f"base ref `{base}` does not resolve — re-derive it from disk, or fall back "
            f"to the manual dependency check."
        )
    hard: list[str] = []
    advisory: list[str] = []
    added: list[dict] = []
    declared_norm = {_norm(d) for d in declared} if declared is not None else None

    # Tracked manifests that changed between base and head/worktree, PLUS — in
    # working-tree mode — untracked NEW manifests (a brand-new package.json a feature
    # added; `git diff` omits untracked files, so gather them like patch-lint does).
    changed = [p.strip() for p in _git(repo, "diff", "--name-only", base, *([head] if head else [])).splitlines() if p.strip()]
    if not head:
        changed += [p.strip() for p in _git(repo, "ls-files", "--others", "--exclude-standard").splitlines() if p.strip()]

    seen = set()
    for path in changed:
        if path in seen:
            continue
        seen.add(path)
        kind = classify(path)
        if kind is None:
            continue  # not a dependency manifest
        if kind.startswith("STUB:"):
            raise DepGuardError(
                f"no parser for {kind[5:]} manifest `{path}` — dependency detection "
                f"unavailable for this ecosystem (parsed: npm, Python, NuGet, Go, Cargo; "
                f"still-manual: Maven, Gradle); manual check required."
            )
        old_text = _show(repo, base, path)  # None for an untracked / newly-added manifest
        new_text = _show(repo, head, path) if head else (_read(repo / path) if (repo / path).is_file() else None)
        if new_text is None:
            continue  # manifest deleted at head — no additions from it
        old = parse_manifest(kind, old_text) if old_text else set()
        new = parse_manifest(kind, new_text)
        eco = ecosystem_of(kind)
        for name in sorted(new - old):
            added.append({"name": name, "ecosystem": eco, "manifest": path})
            if declared_norm is not None and name not in declared_norm:
                hard.append(
                    f"D1 {name} ({eco}, {path}): a new dependency entered the manifest that "
                    f"the agent did not declare/verify this run — the slopsquatting smoking gun. "
                    f"Verify it exists on the registry (and is not a typosquat) and record it, or remove it."
                )
            hit = typo_match(name, eco, popular)
            if hit:
                advisory.append(
                    f"A1 {name} ({eco}, {path}): name is close to the popular package `{hit}` "
                    f"— possible typosquat. Confirm against the live registry before trusting it."
                )
    return hard, advisory, added


def emit(label: str, hard: list, advisory: list, added: list, declared: set | None, as_json: bool) -> int:
    status = "fail" if hard else "pass"
    if as_json:
        print(json.dumps({
            "status": status,
            "label": label,
            "declared_supplied": declared is not None,
            "added": added,
            "hard_failures": hard,
            "advisory": advisory,
        }, indent=2))
        return 1 if hard else 0
    print(f"dep-guard: {label}")
    print(f"  {len(added)} new direct dependency(ies)" + (" · undeclared-check OFF (--detect-only)" if declared is None else ""))
    if hard:
        print(f"\n  FAIL — {len(hard)} undeclared dependency(ies):")
        for f in hard:
            print(f"    x {f}")
    elif declared is None:
        print("\n  PASS (detect-only) — undeclared check not run; new deps reported above for review.")
    else:
        print("\n  PASS — every new dependency is declared/verified.")
    if advisory:
        print(f"\n  advisory ({len(advisory)} — review, non-blocking):")
        for a in advisory:
            print(f"    ! {a}")
    print()
    return 1 if hard else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="On-disk gate against hallucinated / slopsquatted dependencies.")
    p.add_argument("--base", required=True, metavar="REF", help="committed baseline ref to diff manifests against")
    p.add_argument("--head", metavar="REF", help="head ref (default: the working tree)")
    p.add_argument("--declared", metavar="N1,N2", default="", help="comma-separated deps the agent verified this run; any NEW dep not listed is undeclared (D1). The check is ON by default — an empty/omitted set means *every* new dep is undeclared (fail-safe). Use --detect-only to turn it off.")
    p.add_argument("--detect-only", action="store_true", help="report new deps + typo flags only; do NOT enforce the D1 undeclared check (for ad-hoc exploration, never as a gate)")
    p.add_argument("--feature", help="feature id, for the report label")
    p.add_argument("--repo", metavar="PATH", help="repo root (default: git toplevel of cwd)")
    p.add_argument("--popular", metavar="PATH", help="override the bundled popular-packages.json")
    p.add_argument("--json", action="store_true", help="machine-readable result")
    args = p.parse_args(argv)

    label = args.feature or "dep-guard"
    # Fail-safe default: the undeclared check is ON unless --detect-only. A forgotten or
    # empty --declared therefore FAILS any new dep (safe), never silently passes (the
    # fail-open footgun the gate exists to prevent).
    declared = None if args.detect_only else {d.strip() for d in args.declared.split(",") if d.strip()}
    try:
        repo = Path(args.repo) if args.repo else (_git_toplevel(Path.cwd()) or Path.cwd())
        if _git_toplevel(repo) is None:
            raise DepGuardError("not inside a git repository — cannot diff manifests")
        popular = load_popular(args.popular)
        hard, advisory, added = run(repo, args.base, args.head, declared, popular)
    except DepGuardError as e:
        if args.json:
            print(json.dumps({"status": "error", "label": label, "message": str(e)}))
        else:
            print(f"dep-guard: ERROR — could not run: {e}", file=sys.stderr)
            print("  -> fall back to the manual dependency-existence check (loudly).", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — any unexpected failure honors the exit-2 contract,
        # never leaks a traceback that exits 1 and impersonates a hard FAIL to a gating caller.
        if args.json:
            print(json.dumps({"status": "error", "label": label, "message": f"unexpected: {type(e).__name__}: {e}"}))
        else:
            print(f"dep-guard: ERROR — unexpected failure ({type(e).__name__}): {e}", file=sys.stderr)
            print("  -> fall back to the manual dependency-existence check (loudly).", file=sys.stderr)
        return 2

    return emit(label, hard, advisory, added, declared, args.json)


if __name__ == "__main__":
    sys.exit(main())
