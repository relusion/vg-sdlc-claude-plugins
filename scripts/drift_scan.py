#!/usr/bin/env python3
"""drift_scan.py — re-project HEAD against every plan directory and report drift.

The merge bar (scripts/gate_runner.py) judges a PR *before* it lands; nothing
re-judges `main` *after* merge, so a retired surface, a broken traceability
link, or a silently-disarmed security gate can rot for weeks. drift_scan closes
that gap: it walks `docs/plans/plans.json` -> every registered plan directory in
a repo's committed HEAD and reports where the on-disk artifacts have drifted
away from the specs they claim.

It speaks the SAME Scope Lock vocabulary the interactive skills use, so every
finding routes to the owning layer:

  * plan-layer Scope Lock drift -> route to /core-engineering:ce-plan   (plan artifact / registry
    integrity broken; a spec dir that resolves to no plan feature)
  * spec-layer Scope Lock drift -> route to /core-engineering:ce-spec   (spec referential integrity
    broken; a phantom [SECURITY: TZ-NNN]; a disarmed security-coverage gate)

(One brand — "Scope Lock" — spelled out in full in every finding string; the
plan-vs-spec layer is carried by the route, not a second brand name.)

The scan judges COMMITTED state, like gate_runner.py: `--head` (default HEAD) is
resolved to a commit SHA and its full tree is MATERIALIZED into a scratch
checkout via `git read-tree` + `git checkout-index` (never the mutable working
tree), so an uncommitted edit cannot change the verdict. `--worktree` is the
operator override: scan the repo on disk as-is, no git required (used for legacy
adoption and for driving the scan over an un-committed fixture).

It re-uses the shipped lints as its integrity oracle — plan-lint.py (from
ce-plan-audit) over each plan dir and spec-lint.py (from ce-spec) over each
`specs/<id>` — invoked as subprocesses with `--json`, exactly as gate_runner
runs its gates. The lints come from THIS toolkit checkout (resolved relative to
this file), not from the scanned repo, so the scan works against an adopter repo
that ships no toolkit scripts.

FINDING CLASSES
  HARD (exit 1 unless --advisory-only):
    * plan_lint_fail   — plan-lint exits 1 on a plan dir.
    * spec_lint_fail   — spec-lint exits 1 (or could-not-run) on a specs/<id>.
    * h5_disarmed      — the plan's threat-model declares threat_ids for a
                         feature, but spec-lint's security-coverage gate (H5)
                         reports `disarmed` for that feature's spec: the gate
                         no longer runs (a formatting slip / a tasks.json
                         feature_id that drifted from the plan).
    * orphan_spec      — a specs/<id> dir whose id is in no plan.json feature.
    * phantom_threat_id— a spec cites [SECURITY: TZ-NNN] for an id the plan's
                         threat-model never defines (the inverse of H5).
    * registry_break   — plans.json entry with no directory, or a plan
                         directory with no plans.json entry.
  ADVISORY (never change the exit code — best-effort, markdown/heuristic):
    * surface_residue  — a Surface-Removal Closure row dispositioned
                         `deprecate:...,removed_by:<id>` or `hard-break:` whose
                         removing feature is done, yet whose surface string
                         still appears elsewhere in the repo.
    * claimed_file_missing — a file a spec claims (tasks[].files, the hard
                         source; else file paths named in ce-spec.md) is absent
                         from the committed tree.

Exit codes (the house gate contract):
    0  PASS   — no hard drift (advisory findings may exist), or --advisory-only.
    1  DRIFT  — at least one hard drift finding.
    2  ERROR  — the scan could not run: --repo missing, git absent in commit
                mode, plans.json unparseable, unexpected failure. Fall back to a
                manual re-projection, loudly.

Stdlib-only, offline, read-only (materializes into a temp dir it owns; never
writes the scanned repo), Claude-free.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PLUGIN_ROOT = SCRIPT_DIR.parent / "plugins" / "core-engineering"
DEFAULT_PLAN_LINT = DEFAULT_PLUGIN_ROOT / "skills" / "ce-plan-audit" / "scripts" / "plan-lint.py"
DEFAULT_SPEC_LINT = DEFAULT_PLUGIN_ROOT / "skills" / "ce-spec" / "scripts" / "spec-lint.py"

# The CURRENT lock vocabulary. Spelled in full in every finding string so a
# future rename sweep (skills + scripts) catches these literals here too.
PLAN_SCOPE_LOCK = "Scope Lock"
SPEC_SCOPE_LOCK = "Scope Lock"

# A security AC carries a `[SECURITY: TZ-NNN]` marker (mirrors spec-lint's
# grammar); the marker may list >1 id.
SECURITY_MARKER = re.compile(r"\[SECURITY\b([^\]]*)\]", re.I)
TZ_TOKEN = re.compile(r"\bTZ-\d+\b", re.I)

# A heuristic file path named in a spec's prose: a backtick-quoted token that
# contains a path separator and a file extension (advisory input only, used when
# a spec's tasks carry no enforced `files` list).
BACKTICK = re.compile(r"`([^`]+)`")
PATHY = re.compile(r"^[\w./-]+/[\w.-]+\.[A-Za-z0-9]+$")

# Directories a residue/existence grep never descends into.
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
             ".pytest_cache", "dist", "build", ".idea", ".tox"}
# Files bigger than this (bytes) are skipped by the residue grep (best-effort).
MAX_GREP_BYTES = 2_000_000


class DriftScanError(Exception):
    """The scan itself cannot run -> exit 2 (never impersonates a drift FAIL)."""


def _canon_tz(tz: str) -> str:
    """Canonicalize a threat-id so a zero-padding slip never causes a false
    miss (TZ-001 / tz-1 / TZ-1 all collapse to TZ-1). Mirrors spec-lint."""
    m = re.match(r"TZ-0*(\d+)$", tz.strip(), re.I)
    return f"TZ-{m.group(1)}" if m else tz.strip().upper()


# ---------------------------------------------------------------------------
# git — resolve + materialize the committed HEAD tree (gate_runner discipline)
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, timeout=60)
    except FileNotFoundError as e:
        raise DriftScanError(
            "git is not on PATH — drift_scan judges committed state and needs "
            "git (pass --worktree to scan the working tree on disk instead)"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise DriftScanError(f"git {' '.join(args[:2])} timed out in {repo}") from e


def resolve_head(repo: Path, ref: str) -> str:
    proc = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if proc.returncode != 0:
        raise DriftScanError(
            f"--head {ref!r} does not resolve to a commit in {repo}: "
            f"{proc.stderr.decode(errors='replace').strip() or 'unknown ref'} "
            f"(is it a git repo with at least one commit? use --worktree to "
            f"scan on disk)")
    return proc.stdout.decode().strip()


def materialize_head(repo: Path, tree_ish: str, dest: Path) -> Path:
    """Check out the tree at `tree_ish` into `dest` via a SCRATCH index and
    return `dest`. Deliberately `checkout-index` (not `git archive`, which would
    apply `.gitattributes export-ignore` and could silently drop a committed
    plan file); the scratch index leaves the repo's real index untouched."""
    dest.mkdir(parents=True, exist_ok=True)
    scratch_index = str(dest) + ".scratch-index"
    env = dict(os.environ, GIT_INDEX_FILE=scratch_index)
    try:
        read = subprocess.run(
            ["git", "-C", str(repo), "read-tree", tree_ish],
            capture_output=True, env=env, timeout=60)
        if read.returncode != 0:
            raise DriftScanError(
                f"git read-tree {tree_ish} failed: "
                f"{read.stderr.decode(errors='replace').strip()}")
        checkout = subprocess.run(
            ["git", "-C", str(repo), "checkout-index", "--all", "--force",
             f"--prefix={dest}{os.sep}"],
            capture_output=True, env=env, timeout=180)
        if checkout.returncode != 0:
            raise DriftScanError(
                f"git checkout-index at {tree_ish} failed: "
                f"{checkout.stderr.decode(errors='replace').strip()}")
    finally:
        try:
            Path(scratch_index).unlink()
        except OSError:
            pass
    return dest


# ---------------------------------------------------------------------------
# lint invocation — the integrity oracle (subprocess + --json, like gate_runner)
# ---------------------------------------------------------------------------

def run_lint(script: Path, target: Path, extra: list[str], cwd: Path,
             timeout: float = 120) -> tuple[int | None, dict | None]:
    """Run a lint over `target` and return (exit_code, parsed_json_or_None).
    exit_code is None on timeout. A non-dict / unparseable stdout yields None."""
    try:
        proc = subprocess.run(
            [sys.executable, str(script), str(target), *extra, "--json"],
            capture_output=True, text=True, timeout=timeout, cwd=str(cwd))
    except subprocess.TimeoutExpired:
        return None, None
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        data = None
    return proc.returncode, data


# ---------------------------------------------------------------------------
# threat-model parsing (stdlib-only; mirrors spec-lint's obligation reader)
# ---------------------------------------------------------------------------

def threat_ids_for_feature(tm_text: str, feature: str) -> set[str]:
    """The threat_ids the threat-model's `security_obligations` block assigns to
    ONE feature (canonicalized), or an empty set. Best-effort, miss-safe."""
    block = re.search(
        r"-\s*feature:\s*['\"]?" + re.escape(feature) + r"['\"]?\s*\n(.*?)"
        r"(?=\n\s*-\s*feature:|\Z)", tm_text, re.S)
    if not block:
        return set()
    seg = block.group(1)
    flow = re.search(r"threat_ids:\s*\[([^\]]*)\]", seg)
    if flow:
        return {_canon_tz(t) for t in TZ_TOKEN.findall(flow.group(1))}
    blk = re.search(r"threat_ids:\s*\n(.*?)(?=\n\s*\w[\w-]*:|\Z)", seg, re.S)
    if blk:
        return {_canon_tz(t) for t in TZ_TOKEN.findall(blk.group(1))}
    return set()


def defined_threat_ids(tm_text: str) -> set[str]:
    """Every TZ-NNN the threat-model DEFINES anywhere (canonicalized). A spec
    that cites a [SECURITY: TZ-NNN] outside this set is a phantom reference."""
    return {_canon_tz(t) for t in TZ_TOKEN.findall(tm_text)}


def spec_cited_threat_ids(spec_text: str) -> set[str]:
    """Canonical TZ ids a spec cites through its `[SECURITY: ...]` markers."""
    cited: set[str] = set()
    for mk in SECURITY_MARKER.finditer(spec_text):
        cited.update(_canon_tz(t) for t in TZ_TOKEN.findall(mk.group(1)))
    return cited


# ---------------------------------------------------------------------------
# markdown table helper (Surface-Removal Closure) — best-effort
# ---------------------------------------------------------------------------

_SEP_CELL = re.compile(r"^:?-{2,}:?$")


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_sep(cells: list[str]) -> bool:
    non_empty = [c for c in cells if c]
    return bool(non_empty) and all(_SEP_CELL.match(c) for c in non_empty)


def find_table(text: str, anchors: list[str]):
    """First markdown table whose header row contains ALL `anchors`; returns
    (header_cells, [row_cells,...]) or (None, [])."""
    lines = text.splitlines()
    want = [a.lower() for a in anchors]
    for i, ln in enumerate(lines):
        if "|" not in ln:
            continue
        header = _split_row(ln)
        low = [c.lower() for c in header]
        if not all(a in low for a in want):
            continue
        rows: list[list[str]] = []
        j = i + 1
        if j < len(lines) and "|" in lines[j] and _is_sep(_split_row(lines[j])):
            j += 1
        while j < len(lines):
            lj = lines[j]
            if "|" not in lj or not lj.strip().startswith("|"):
                break
            rc = _split_row(lj)
            if not _is_sep(rc):
                rows.append(rc)
            j += 1
        return header, rows
    return None, []


# ---------------------------------------------------------------------------
# repo grep — residue / existence over the committed tree (best-effort)
# ---------------------------------------------------------------------------

def grep_tree(tree_root: Path, needle: str, exclude: Path | None) -> str | None:
    """Return the first repo-relative path (excluding `exclude` and SKIP_DIRS)
    whose text contains `needle`, or None. Best-effort: unreadable/binary/oversize
    files are skipped, never fatal."""
    for root, dirs, files in os.walk(tree_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rp = Path(root)
        if exclude is not None:
            try:
                rp.relative_to(exclude)
                dirs[:] = []
                continue
            except ValueError:
                pass
        for name in files:
            fp = rp / name
            try:
                if fp.stat().st_size > MAX_GREP_BYTES:
                    continue
                text = fp.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if needle in text:
                return str(fp.relative_to(tree_root))
    return None


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------

def _finding(severity: str, code: str, lock: str | None, route: str | None,
             message: str, **extra) -> dict:
    f = {"severity": severity, "code": code, "lock": lock, "route": route,
         "message": message}
    f.update(extra)
    return f


# ---------------------------------------------------------------------------
# the scan
# ---------------------------------------------------------------------------

class Scan:
    def __init__(self, tree_root: Path, plan_lint: Path, spec_lint: Path):
        self.tree_root = tree_root
        self.plan_lint = plan_lint
        self.spec_lint = spec_lint
        self.hard: list[dict] = []
        self.advisory: list[dict] = []
        self.plans_scanned = 0
        self.specs_scanned = 0
        self.notes: list[str] = []

    # -- registry -----------------------------------------------------------
    def load_registry(self, plans_json: Path) -> list[dict]:
        try:
            data = json.loads(plans_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as e:
            raise DriftScanError(f"cannot read {plans_json}: {e}") from e
        except json.JSONDecodeError as e:
            raise DriftScanError(f"{plans_json} is not valid JSON: {e}") from e
        if not isinstance(data, dict) or not isinstance(data.get("plans"), list):
            raise DriftScanError(
                f"{plans_json} must be an object with a `plans` array")
        return data["plans"]

    def check_registry(self, plans_root: Path, plans: list[dict]) -> list[str]:
        """Two-way registry reconciliation. Returns the registered slugs whose
        directory exists (the set worth scanning)."""
        registered: list[str] = []
        for i, entry in enumerate(plans):
            slug = entry.get("slug") if isinstance(entry, dict) else None
            if not (isinstance(slug, str) and slug.strip()):
                self.hard.append(_finding(
                    "hard", "registry_break", PLAN_SCOPE_LOCK, "/core-engineering:ce-plan",
                    f"{PLAN_SCOPE_LOCK} drift: plans.json entry #{i + 1} has no "
                    f"`slug` — the plan registry is broken; route to /core-engineering:ce-plan "
                    f"revision"))
                continue
            registered.append(slug)
            if not (plans_root / slug).is_dir():
                self.hard.append(_finding(
                    "hard", "registry_break", PLAN_SCOPE_LOCK, "/core-engineering:ce-plan",
                    f"{PLAN_SCOPE_LOCK} drift: plans.json registers `{slug}` but "
                    f"docs/plans/{slug}/ does not exist — plan artifact integrity "
                    f"broken; route to /core-engineering:ce-plan revision", plan=slug))
        registered_set = set(registered)
        for d in sorted(p for p in plans_root.iterdir() if p.is_dir()):
            if d.name not in registered_set:
                self.hard.append(_finding(
                    "hard", "registry_break", PLAN_SCOPE_LOCK, "/core-engineering:ce-plan",
                    f"{PLAN_SCOPE_LOCK} drift: docs/plans/{d.name}/ is present but "
                    f"unregistered in plans.json — plan artifact integrity broken; "
                    f"route to /core-engineering:ce-plan revision", plan=d.name))
        return [s for s in registered if (plans_root / s).is_dir()]

    # -- one plan dir -------------------------------------------------------
    def scan_plan(self, plans_root: Path, slug: str) -> None:
        plan_dir = plans_root / slug
        self.plans_scanned += 1

        # plan-lint over the canonical plan directory. Missing or unreadable
        # plan.json is an unevaluable authority and therefore a hard drift.
        code, data = run_lint(self.plan_lint, plan_dir, [], self.tree_root)
        if code == 1:
            detail = ""
            if isinstance(data, dict) and data.get("hard_failures"):
                detail = " · ".join(str(x) for x in data["hard_failures"][:4])
            self.hard.append(_finding(
                "hard", "plan_lint_fail", PLAN_SCOPE_LOCK, "/core-engineering:ce-plan",
                f"{PLAN_SCOPE_LOCK} drift: plan artifact integrity broken — route "
                f"to /core-engineering:ce-plan revision" + (f" [{detail}]" if detail else ""),
                plan=slug))
        elif code == 2:
            msg = data.get("message", "") if isinstance(data, dict) else ""
            self.hard.append(_finding(
                "hard", "plan_lint_fail", PLAN_SCOPE_LOCK, "/core-engineering:ce-plan",
                f"{PLAN_SCOPE_LOCK} drift: plan-lint could not evaluate "
                f"docs/plans/{slug}/ ({msg or 'unparseable inputs'}) — route "
                f"to /core-engineering:ce-plan revision", plan=slug))
        elif code is None:
            self.hard.append(_finding(
                "hard", "plan_lint_fail", PLAN_SCOPE_LOCK, "/core-engineering:ce-plan",
                f"{PLAN_SCOPE_LOCK} drift: plan-lint timed out on docs/plans/{slug}/ "
                f"— route to /core-engineering:ce-plan revision", plan=slug))

        # plan.json feature ids (for orphan-spec + surface owner-done gating).
        feature_ids = self._plan_feature_ids(plan_dir)

        # threat-model text (for phantom-TZ + h5-disarm gating).
        tm_path = plan_dir / "threat-model.md"
        tm_text = tm_path.read_text(encoding="utf-8", errors="replace") if tm_path.is_file() else None

        specs_root = plan_dir / "specs"
        if specs_root.is_dir():
            for spec_dir in sorted(d for d in specs_root.iterdir() if d.is_dir()):
                self.scan_spec(slug, spec_dir, feature_ids, tm_text)

        # advisory: retired-surface residue.
        self._scan_surface_residue(plans_root, slug, plan_dir)

    def _plan_feature_ids(self, plan_dir: Path) -> set[str] | None:
        pj = plan_dir / "plan.json"
        if not pj.is_file():
            return None
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        feats = data.get("features") if isinstance(data, dict) else None
        if not isinstance(feats, list):
            return None
        return {f.get("id") for f in feats
                if isinstance(f, dict) and isinstance(f.get("id"), str)}

    # -- one spec dir -------------------------------------------------------
    def scan_spec(self, slug: str, spec_dir: Path, feature_ids: set[str] | None,
                  tm_text: str | None) -> None:
        self.specs_scanned += 1
        spec_id = spec_dir.name
        label = f"{slug}/{spec_id}"

        # orphan spec — id resolves to no plan.json feature. A missing plan.json
        # is already a hard plan-lint failure above.
        if feature_ids is not None and spec_id not in feature_ids:
            self.hard.append(_finding(
                "hard", "orphan_spec", PLAN_SCOPE_LOCK, "/core-engineering:ce-plan",
                f"{PLAN_SCOPE_LOCK} drift: spec dir `{spec_id}` resolves to no "
                f"feature in docs/plans/{slug}/plan.json — traceability broken; "
                f"route to /core-engineering:ce-plan revision", plan=slug, feature=spec_id))

        # spec-lint over the spec dir (h5 auto-discovers threat-model.md).
        code, data = run_lint(self.spec_lint, spec_dir, [], self.tree_root)
        if code == 1:
            detail = ""
            if isinstance(data, dict) and data.get("hard_failures"):
                detail = " · ".join(str(x) for x in data["hard_failures"][:4])
            self.hard.append(_finding(
                "hard", "spec_lint_fail", SPEC_SCOPE_LOCK, "/core-engineering:ce-spec",
                f"{SPEC_SCOPE_LOCK} drift — route to /core-engineering:ce-spec"
                + (f" [{detail}]" if detail else ""),
                plan=slug, feature=spec_id))
        elif code == 2:
            msg = data.get("message", "") if isinstance(data, dict) else ""
            self.hard.append(_finding(
                "hard", "spec_lint_fail", SPEC_SCOPE_LOCK, "/core-engineering:ce-spec",
                f"{SPEC_SCOPE_LOCK} drift — spec-lint could not evaluate {label} "
                f"({msg or 'unparseable inputs'}); route to /core-engineering:ce-spec",
                plan=slug, feature=spec_id))
        elif code is None:
            self.hard.append(_finding(
                "hard", "spec_lint_fail", SPEC_SCOPE_LOCK, "/core-engineering:ce-spec",
                f"{SPEC_SCOPE_LOCK} drift — spec-lint timed out on {label}; route to "
                f"/core-engineering:ce-spec", plan=slug, feature=spec_id))

        # h5 disarmed — the threat-model DECLARES obligations for this feature,
        # yet spec-lint's coverage gate reports it disarmed (it no longer runs).
        # Gating on our own obligation parse avoids false positives on features
        # that genuinely have no security surface (spec-lint reports those
        # `disarmed` too, but there is nothing to cover).
        if tm_text is not None and isinstance(data, dict):
            h5_status = data.get("h5_status")
            if h5_status in ("disarmed", "na") and threat_ids_for_feature(tm_text, spec_id):
                self.hard.append(_finding(
                    "hard", "h5_disarmed", SPEC_SCOPE_LOCK, "/core-engineering:ce-spec",
                    f"threat-model coverage disarmed — H5 no longer runs for "
                    f"{spec_id}: the plan's threat-model assigns threat_ids to "
                    f"this feature but spec-lint reports `{h5_status}`; route to "
                    f"/core-engineering:ce-spec", plan=slug, feature=spec_id))

        # phantom TZ — a spec cites a [SECURITY: TZ-NNN] the threat-model never
        # defines (the inverse of H5, checked nowhere else).
        spec_text = self._read_spec_text(spec_dir)
        if spec_text is not None and tm_text is not None:
            defined = defined_threat_ids(tm_text)
            for tz in sorted(spec_cited_threat_ids(spec_text)):
                if tz not in defined:
                    self.hard.append(_finding(
                        "hard", "phantom_threat_id", SPEC_SCOPE_LOCK, "/core-engineering:ce-spec",
                        f"{SPEC_SCOPE_LOCK} drift — {label} cites `[SECURITY: {tz}]` "
                        f"but docs/plans/{slug}/threat-model.md never defines "
                        f"{tz} (phantom threat reference); route to /core-engineering:ce-spec",
                        plan=slug, feature=spec_id, threat_id=tz))

        # advisory: spec-claimed files that no longer exist in the committed tree.
        self._scan_claimed_files(slug, spec_dir, spec_text)

    def _read_spec_text(self, spec_dir: Path) -> str | None:
        for name in ("ce-spec.md", "spec.md"):
            p = spec_dir / name
            if p.is_file():
                try:
                    return p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return None
        return None

    def _claimed_files(self, spec_dir: Path, spec_text: str | None) -> list[str]:
        """Files a spec claims: tasks[].files (the hard source, once enforced)
        when any task carries them; else file paths named in ce-spec.md prose."""
        tasks_path = spec_dir / "tasks.json"
        if tasks_path.is_file():
            try:
                data = json.loads(tasks_path.read_text(encoding="utf-8"))
                tasks = data.get("tasks") if isinstance(data, dict) else None
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                tasks = None
            if isinstance(tasks, list):
                claimed: list[str] = []
                for t in tasks:
                    if isinstance(t, dict) and isinstance(t.get("files"), list):
                        claimed.extend(f for f in t["files"]
                                       if isinstance(f, str) and f.strip())
                if claimed:
                    return sorted(set(claimed))
        # heuristic fallback: pathy backtick tokens in the spec prose.
        if spec_text:
            return sorted({m for m in BACKTICK.findall(spec_text) if PATHY.match(m)})
        return []

    def _scan_claimed_files(self, slug: str, spec_dir: Path,
                            spec_text: str | None) -> None:
        for rel in self._claimed_files(spec_dir, spec_text):
            if not (self.tree_root / rel).exists():
                self.advisory.append(_finding(
                    "advisory", "claimed_file_missing", SPEC_SCOPE_LOCK, "/core-engineering:ce-spec",
                    f"{SPEC_SCOPE_LOCK} drift (advisory) — {slug}/{spec_dir.name} "
                    f"claims `{rel}` but it is absent from the committed tree "
                    f"(spec-vs-code traceability drift); route to /core-engineering:ce-spec",
                    plan=slug, feature=spec_dir.name, path=rel))

    # -- retired-surface residue (advisory) --------------------------------
    def _scan_surface_residue(self, plans_root: Path, slug: str,
                              plan_dir: Path) -> None:
        fp = plan_dir / "feature-plan.md"
        if not fp.is_file():
            return
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        header, rows = find_table(text, ["surface", "break-class", "continuity"])
        if not header:
            return
        low = [c.lower() for c in header]
        surf_i = low.index("surface")
        cont_i = low.index("continuity")
        for row in rows:
            surface = row[surf_i].strip() if surf_i < len(row) else ""
            cont = row[cont_i].strip() if cont_i < len(row) else ""
            if (not surface or surface.startswith("<") or len(surface) < 3
                    or not cont):
                continue
            low_cont = cont.lower()
            is_deprecate = low_cont.startswith("deprecate:") and "removed_by:" in low_cont
            is_hardbreak = low_cont.startswith("hard-break:")
            if not (is_deprecate or is_hardbreak):
                continue
            owner = None
            if is_deprecate:
                m = re.search(r"removed_by:\s*([\w./-]+)", cont, re.I)
                owner = m.group(1) if m else None
                # a deprecate window is only overdue once its removing feature is
                # done; if we cannot confirm that, skip (never a false residue).
                if owner is None or not self._feature_done(plan_dir, owner):
                    continue
            # hard-break has no window: the surface should already be gone.
            hit = grep_tree(self.tree_root, surface, exclude=plan_dir)
            if hit:
                disp = "hard-break" if is_hardbreak else f"deprecate,removed_by:{owner}"
                self.advisory.append(_finding(
                    "advisory", "surface_residue", PLAN_SCOPE_LOCK, "/core-engineering:ce-plan",
                    f"{PLAN_SCOPE_LOCK} drift (advisory) — retired surface "
                    f"`{surface}` ({disp}) still appears in `{hit}` though its "
                    f"removal is due; route to /core-engineering:ce-plan revision",
                    plan=slug, surface=surface, seen_in=hit))

    def _feature_done(self, plan_dir: Path, feature_id: str) -> bool:
        """A feature is 'done' when its spec's tasks are all status=done. A
        missing spec/tasks is treated as NOT done (we cannot confirm removal
        happened, so we do not raise a residue advisory)."""
        tasks_path = plan_dir / "specs" / feature_id / "tasks.json"
        if not tasks_path.is_file():
            return False
        try:
            data = json.loads(tasks_path.read_text(encoding="utf-8"))
            tasks = data.get("tasks") if isinstance(data, dict) else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        if not isinstance(tasks, list) or not tasks:
            return False
        return all(isinstance(t, dict) and t.get("status") == "done" for t in tasks)


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def run_scan(tree_root: Path, plan_lint: Path, spec_lint: Path) -> Scan:
    scan = Scan(tree_root, plan_lint, spec_lint)
    plans_root = tree_root / "docs" / "plans"
    plans_json = plans_root / "plans.json"
    if not plans_json.is_file():
        # No registry -> nothing to re-project. Not an error: an adopter may
        # carry no plans yet.
        scan.notes.append("no docs/plans/plans.json — no plans registered to scan")
        return scan
    plans = scan.load_registry(plans_json)
    for slug in scan.check_registry(plans_root, plans):
        scan.scan_plan(plans_root, slug)
    return scan


def emit_json(scan: Scan, repo: Path, head_sha: str | None, worktree: bool,
              advisory_only: bool) -> int:
    exit_code = 0 if (advisory_only or not scan.hard) else 1
    print(json.dumps({
        "tool": "drift_scan",
        "repo": str(repo),
        "head_sha": head_sha,
        "worktree": worktree,
        "advisory_only": advisory_only,
        "plans_scanned": scan.plans_scanned,
        "specs_scanned": scan.specs_scanned,
        "status": "drift" if scan.hard else "pass",
        "hard": scan.hard,
        "advisory": scan.advisory,
        "notes": scan.notes,
        "exit": exit_code,
    }, indent=2))
    return exit_code


def emit_human(scan: Scan, repo: Path, head_sha: str | None, worktree: bool,
               advisory_only: bool) -> int:
    where = "working tree" if worktree else f"HEAD {head_sha[:12] if head_sha else '?'}"
    print(f"drift_scan: {repo} @ {where}")
    print(f"  scanned: {scan.plans_scanned} plan(s), {scan.specs_scanned} spec(s)")
    for n in scan.notes:
        print(f"  note: {n}")
    if scan.hard:
        print(f"\n  DRIFT — {len(scan.hard)} hard finding(s):")
        for f in scan.hard:
            print(f"    x [{f['code']}] {f['message']}")
    else:
        print("\n  PASS — no hard drift on the committed plan artifacts.")
    if scan.advisory:
        print(f"\n  advisory ({len(scan.advisory)} — review, non-blocking):")
        for f in scan.advisory:
            print(f"    ! [{f['code']}] {f['message']}")
    exit_code = 0 if (advisory_only or not scan.hard) else 1
    if scan.hard and advisory_only:
        print(f"\n  --advisory-only: {len(scan.hard)} hard finding(s) reported "
              f"but exit forced to 0 (first-run adoption).")
    print()
    return exit_code


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Re-project HEAD against every plan directory and report drift.")
    p.add_argument("--repo", required=True, help="path to the repository to scan")
    p.add_argument("--head", default="HEAD",
                   help="ref to judge (default HEAD); resolved to a commit SHA")
    p.add_argument("--worktree", action="store_true",
                   help="scan the repo on disk as-is (no git) — operator override")
    p.add_argument("--advisory-only", action="store_true",
                   help="report hard findings but never exit 1 (legacy adoption)")
    p.add_argument("--plan-lint", default=str(DEFAULT_PLAN_LINT),
                   help="path to plan-lint.py (default: this toolkit's copy)")
    p.add_argument("--spec-lint", default=str(DEFAULT_SPEC_LINT),
                   help="path to spec-lint.py (default: this toolkit's copy)")
    p.add_argument("--json", action="store_true", help="emit a machine-readable result")
    args = p.parse_args(argv)

    # Resolve to absolute paths up front: the lints run as subprocesses with
    # cwd set to the (materialized) tree root, so a relative --repo / target
    # would otherwise resolve against the wrong base.
    repo = Path(args.repo).resolve()
    plan_lint = Path(args.plan_lint).resolve()
    spec_lint = Path(args.spec_lint).resolve()

    try:
        if not repo.is_dir():
            raise DriftScanError(f"--repo {repo} is not a directory")
        for name, lint in (("plan-lint", plan_lint), ("spec-lint", spec_lint)):
            if not lint.is_file():
                raise DriftScanError(
                    f"{name} script not found: {lint} (drift_scan needs this "
                    f"toolkit's lints as its integrity oracle)")

        head_sha: str | None = None
        if args.worktree:
            scan = run_scan(repo, plan_lint, spec_lint)
        else:
            head_sha = resolve_head(repo, args.head)
            with tempfile.TemporaryDirectory(prefix="drift-scan-") as tmp:
                tree_root = materialize_head(repo, head_sha, Path(tmp) / "head-tree")
                scan = run_scan(tree_root, plan_lint, spec_lint)
    except DriftScanError as e:
        if args.json:
            print(json.dumps({"tool": "drift_scan", "status": "error",
                              "message": str(e), "exit": 2}))
        else:
            print(f"drift_scan: ERROR — could not run: {e}", file=sys.stderr)
            print("  -> fall back to a manual re-projection (loudly).", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        # Any UNEXPECTED failure honors the exit-2 "could not run -> fall back"
        # contract, never leaks a traceback that exits 1 and impersonates drift.
        if args.json:
            print(json.dumps({"tool": "drift_scan", "status": "error",
                              "message": f"unexpected: {type(e).__name__}: {e}",
                              "exit": 2}))
        else:
            print(f"drift_scan: ERROR — unexpected failure "
                  f"({type(e).__name__}): {e}", file=sys.stderr)
            print("  -> fall back to a manual re-projection (loudly).", file=sys.stderr)
        return 2

    if args.json:
        return emit_json(scan, repo, head_sha, args.worktree, args.advisory_only)
    return emit_human(scan, repo, head_sha, args.worktree, args.advisory_only)


if __name__ == "__main__":
    sys.exit(main())
