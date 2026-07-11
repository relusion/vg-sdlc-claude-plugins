#!/usr/bin/env python3
"""patch-lint.py — on-disk gate for the lightweight `/ce-patch` lane.

A patch is the spine *folded* for a single, genuinely-small change. The thing that
keeps the fold honest — that stops it becoming "a context that talks itself out of
the gates" — is this external checker. It is run by a process that did **not** write
the spec or the code, exactly as auto-build gates a spawned subagent, so the
load-bearing safety checks (durable-noun, scope-creep, surface-novelty) are verified
against ground truth on disk, never self-reported.

It SUPPLEMENTS `spec`'s `spec-lint.py` — it does not replace it. The H1–H4
referential-integrity checks and the `modality` / `verification` vocabularies are
**imported** from `spec-lint.py` (single source — those cannot drift), and patch-lint
adds the patch-specific clauses of the **Patch Charter** (C1–C7). *(spec-lint's
plan-scoped security `H5` is deliberately NOT run here — the n=1 patch lane has no
plan and no `threat-model.md`; a security-sensitive surface trips Patch-Charter C6 and
graduates to `/ce-plan`. patch-lint's own H5 below is the unrelated lease-eligibility
check.)* The one local
vocabulary literal — `PERSISTED_MODALITIES` (H6) — is a *subset* of spec-lint's
`MODALITIES`, asserted against it at run time so it cannot silently drift either.

Four modes, four moments in the folded flow:

  --eligibility <spec-dir>   Stage 0. Validate the lightness *lease* before any spec
                             is written: the recorded human-consented eligibility
                             block exists and is well-formed, no clause is a NO, and
                             the *mechanical* clauses (C1 file cap, C4 cross-feature
                             collision) actually hold against the repo — recomputed,
                             not trusted.
  --pre <spec-dir>           Stage 2. Gate the spec artifact before implement:
                             spec-lint H1–H4 + a valid lease + no persisted-store
                             modality (C2 pre) + planned task files within the lease.
  --post <spec-dir> [--base R]  Stage 4. Gate the *actual diff* after implement:
                             spec-lint H1–H4 + no durable-noun write (C2 post) +
                             diff files within the lease (C1 post) + no destructive
                             op (C5 post). The second, build-evidence end of the
                             charter — the one that catches what slipped the pre-scan.
  --express <stub-or-dir>    The featherweight *express* lane's mechanical screen —
                             no eligibility.json, no ce-spec.md, no tasks.json. Takes a
                             minimal JSON stub ({"files": [...], "desc": "..."}, or a
                             directory holding express.json) and decides admission
                             ENTIRELY mechanically: E1 file count ≤ 2 (stricter than
                             C1's cap), E2 the C4 cross-feature collision scan (reused),
                             E3 a reviewer-trigger heuristic (C6 mechanical floor —
                             auth/secret/payment/migration/i18n/a11y path + durable/
                             destructive walls), E4 no dependency-manifest file in the
                             set. Any hit → exit 1 with the clause named; the caller
                             falls back to the full lane (express is refused, never
                             shrunk). --express --post --base R re-runs H8/H9/H10 over
                             the ACTUAL diff against the candidate set, so the one-gate
                             express lane still has an external on-disk end check.

HARD checks (a FAIL -> exit 1):
  H1–H4  spec-lint referential integrity (imported).               [--pre, --post]
  H5     eligibility lease present, well-formed, human-decided,     [all three modes]
         no clause == "no"; C1 (len frozen_files <= file_cap) and
         C4 (no frozen file owned by another plan's tasks.json)
         recomputed against the repo. Re-asserted at --pre AND
         --post, so a clause flipped to NO or a stripped
         attestation between stages is still caught.
  H6     no test case carries a persisted-store modality            [--pre]
         (db / event / iac) — C2, pre-implementation end.
  H7     every planned task `files` entry is within frozen_files    [--pre]
         — the spec does not plan to touch outside the lease.
  H8     no durable-noun write in the diff (new migration/schema/   [--post]
         persisted file, DDL/DML, ORM persist call) — C2, the
         build-evidence end. Heuristic + conservative: a match
         FAILS and routes to promotion, because a false negative
         (a durable noun shipped via the light lane) is the one
         outcome the lane exists to prevent.
  H9     the diff touches only frozen_files — C1, post end.         [--post]
  H10    no destructive / irreversible op in the diff — C5, post.   [--post, --express --post]

  E1     express candidate holds ≤ 2 files (stricter than C1).       [--express]
  E2     no express candidate file collides with another plan's      [--express]
         tasks.json (C4, via recompute_c4 with a synthetic anchor).
  E3     no reviewer-trigger surface in the candidate paths or the   [--express]
         change description — C6's mechanical floor: auth / secret /
         payment / migration / i18n / a11y path segments + the H8
         durable-file wall + the H8/H10 content walls over the desc.
  E4     no dependency-manifest file (package.json, requirements.txt, [--express]
         go.mod, *.csproj, …) in the candidate set.
  (--express --post re-runs H8 / H9 / H10 over the actual diff.)

ADVISORY checks (warnings only; never change the exit code):
  A4     C4 could not be checked — the spec dir is not under        [all three modes]
         docs/plans/<slug>/specs/<id>, so sibling plans can't be
         scanned; confirm the collision clause by hand.
  A5     a frozen file is imported by many modules (heuristic       [all three modes]
         blast-radius signal for C4 — grep-based, language-naive).
  (plus spec-lint's own A0–A3 on --pre / --post)

Exit codes (identical contract to spec-lint, so callers treat both the same):
    0  PASS  — no hard failures (advisory warnings may still print)
    1  FAIL  — at least one hard failure; the caller disposes per the skill's Stage 4
    2  ERROR — inputs missing / unparseable, or git unavailable for --post; the
               caller falls back to the manual checklist (loudly)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

# --- import spec-lint (single source for H1–H4 + the tag vocabularies) ------
# patch-lint lives at skills/ce-patch/scripts/patch-lint.py; spec-lint at
# skills/ce-spec/scripts/spec-lint.py — siblings under skills/.
SPEC_LINT_PATH = (
    Path(__file__).resolve().parents[2] / "ce-spec" / "scripts" / "spec-lint.py"
)


class PatchLintError(Exception):
    """Inputs cannot be loaded / a dependency is missing -> exit 2, caller falls back."""


def load_spec_lint():
    if not SPEC_LINT_PATH.is_file():
        raise PatchLintError(
            f"spec-lint.py not found at {SPEC_LINT_PATH} — cannot run the shared "
            f"referential-integrity checks; fall back to the manual checklist."
        )
    try:
        spec = importlib.util.spec_from_file_location("spec_lint", SPEC_LINT_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001 — any import failure is a fallback condition
        raise PatchLintError(f"could not import spec-lint.py: {e}") from e
    return mod


# --- the eligibility lease ---------------------------------------------------

REQUIRED_CLAUSES = [
    "C1_bounded_surface",
    "C2_no_durable_noun",
    "C3_no_new_interface",
    "C4_no_blast_radius",
    "C5_reversible",
    "C6_no_reviewer_trigger",
    "C7_no_open_unknown",
]
HUMAN_ATTESTED_CLAUSES = {"C6_no_reviewer_trigger", "C7_no_open_unknown"}


def load_eligibility(spec_dir: Path) -> dict:
    path = spec_dir / "eligibility.json"
    if not path.is_file():
        raise PatchLintError(f"eligibility.json not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PatchLintError(f"eligibility.json is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise PatchLintError("eligibility.json must be a JSON object")
    return data


def check_eligibility(spec_dir: Path, draft: bool = False) -> tuple[list, list]:
    """H5 + the mechanical recomputes (C1 cap, C4 collision) + the A5 advisory.

    `draft=True` runs the **mechanical pre-screen** the skill uses *before* the human
    consents at the Eligibility Gate: the human-consent invariants (decided_by,
    accepted_at, attested_by) are not yet stamped, so they are demoted to advisory —
    but the mechanical clauses (C1 cap, C4 collision), the structural shape, and any
    explicit NO verdict stay HARD, so a doomed change is refused before the human is
    asked. The full (non-draft) check then runs after stamping as the recorded gate.

    Returns (hard, advisory). Raises PatchLintError only when the lease itself
    cannot be loaded (-> exit 2)."""
    elig = load_eligibility(spec_dir)
    hard: list[str] = []
    advisory: list[str] = []
    # In draft mode the consent fields aren't stamped yet — collect them as advisory.
    consent = advisory if draft else hard

    # --- structural / consent well-formedness -------------------------------
    if elig.get("decided_by") != "human":
        consent.append('H5: eligibility.decided_by must be "human" (lightness is a human-consented lease)')
    if not elig.get("accepted_at"):
        consent.append("H5: eligibility.accepted_at is missing (the lease must be timestamped)")
    base_ref = elig.get("base_ref")
    if not base_ref:
        hard.append("H5: eligibility.base_ref is missing (the diff base the post-gate compares against)")

    file_cap = elig.get("file_cap")
    if not isinstance(file_cap, int) or file_cap < 1:
        hard.append("H5: eligibility.file_cap must be a positive integer")
        file_cap = None

    frozen = elig.get("frozen_files")
    if not isinstance(frozen, list) or not frozen or not all(isinstance(f, str) for f in frozen):
        hard.append("H5: eligibility.frozen_files must be a non-empty list of path strings")
        frozen = []

    clauses = elig.get("clauses")
    if not isinstance(clauses, dict):
        hard.append("H5: eligibility.clauses must be an object with the seven C1–C7 verdicts")
        clauses = {}

    # --- every clause present, a yes/no verdict, no NO ----------------------
    for key in REQUIRED_CLAUSES:
        c = clauses.get(key)
        if not isinstance(c, dict) or c.get("verdict") not in ("yes", "no"):
            # Not yet answered is fine during the draft pre-screen; a NO is caught below.
            consent.append(f"H5 {key}: missing or non-yes/no verdict")
            continue
        if c["verdict"] == "no":
            hard.append(
                f"H5 {key}: verdict is NO — this change is not patch-eligible. "
                f"Route to /ce-plan."
            )
        if key in HUMAN_ATTESTED_CLAUSES and c.get("attested_by") != "human":
            consent.append(
                f"H5 {key}: human-attested clause must record `attested_by: human` "
                f"(an agent may not self-certify a reviewer-trigger / open-unknown call)"
            )

    # --- C1 recompute: file cap (mechanical, not trusted) -------------------
    if file_cap is not None and frozen and len(frozen) > file_cap:
        hard.append(
            f"H5 C1: frozen_files holds {len(frozen)} files but file_cap is {file_cap} "
            f"— bounded-surface clause violated. Route to /ce-plan or raise the "
            f"cap in vc-policy.md (a consented, recorded choice)."
        )

    # --- C4 recompute: cross-feature collision against other plans ----------
    if frozen:
        hard_c4, adv_c4 = recompute_c4(spec_dir, frozen)
        hard.extend(hard_c4)
        advisory.extend(adv_c4)

    return hard, advisory


def recompute_c4(spec_dir: Path, frozen: list[str]) -> tuple[list, list]:
    """C4 (hard): none of frozen_files is owned by another plan's tasks.json `files`.
    A5 (advisory): a frozen file imported by many modules (heuristic blast radius)."""
    hard: list[str] = []
    advisory: list[str] = []

    # docs/plans is spec_dir.parents[2]:  .../plans/<patch-slug>/specs/<id>
    resolved = spec_dir.resolve()
    if len(resolved.parents) < 3 or resolved.parents[2].name != "plans":
        # Not the expected docs/plans/<slug>/specs/<id> layout — C4 cannot scan sibling
        # plans. Don't silently assume "clean": say so, so the human checks it.
        advisory.append(
            "A4: C4 cross-feature collision NOT checked — the spec dir is not under "
            "docs/plans/<slug>/specs/<id>, so sibling plans can't be scanned. Confirm by hand."
        )
        return hard, advisory
    plans_dir = resolved.parents[2]
    this_plan = resolved.parents[1]

    frozen_set = {_norm(f) for f in frozen}
    for tasks_path in plans_dir.glob("*/specs/*/tasks.json"):
        if this_plan in tasks_path.resolve().parents:
            continue  # the patch's own plan — not a collision
        try:
            data = json.loads(tasks_path.read_text(encoding="utf-8"))
            tasks = data.get("tasks") if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError):
            continue  # a sibling plan we can't read isn't this lint's problem
        if not isinstance(tasks, list):
            continue
        #  .../plans/<plan-slug>/specs/<feature-id>/tasks.json
        owner_plan = tasks_path.resolve().parents[2].name
        owner_feature = tasks_path.resolve().parents[0].name
        for t in tasks:
            for f in (t.get("files") or []) if isinstance(t, dict) else []:
                if _norm(f) in frozen_set:
                    hard.append(
                        f"H5 C4: frozen file `{f}` is owned by feature "
                        f"{owner_plan}/{owner_feature} (task {t.get('id', '?')} in its "
                        f"tasks.json `files`) — cross-feature blast radius. "
                        f"Route to /ce-plan."
                    )

    # A5 advisory importer count — cheap, language-naive, never blocks.
    repo = _git_toplevel(spec_dir)
    if repo:
        for f in frozen:
            n = _importer_count(repo, f)
            if n is not None and n > 8:
                advisory.append(
                    f"A5: `{f}` appears in ~{n} files' import/require lines — possible shared "
                    f"infrastructure (blast-radius signal). Confirm C4 before proceeding."
                )
    return hard, advisory


def _norm(p: str) -> str:
    # Strip only a literal leading "./" (NOT lstrip("./"), which deletes a *character
    # set* and would corrupt dotfile paths like .github/… or .env -> env).
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


# --- ce-spec.md / tasks.json shared loaders (via spec-lint) -----------------

def load_spec_and_tasks(spec_dir: Path, sl) -> tuple[dict, dict]:
    """Parse ce-spec.md (legacy spec.md accepted) + tasks.json using spec-lint's
    own loaders -> (parsed_spec, tasks)."""
    # ce-spec.md is the canonical spec artifact name; legacy spec.md accepted.
    spec_path = spec_dir / "ce-spec.md"
    if not spec_path.is_file() and (spec_dir / "spec.md").is_file():
        spec_path = spec_dir / "spec.md"
    tasks_path = spec_dir / "tasks.json"
    spec_text, tasks = sl.load(spec_path, tasks_path)  # raises SpecLintError on bad input
    return sl.parse_spec(spec_text), tasks


# --- H6: no persisted-store modality (C2, pre end) --------------------------

# A subset of spec-lint's modality vocabulary — the modalities that imply persisted
# state / infrastructure. Asserted against spec-lint's enum at run time (see
# load_spec_lint callers) so this local literal cannot silently drift out of it.
PERSISTED_MODALITIES = {"db", "event", "iac"}


def assert_modalities_subset(sl) -> None:
    """Guard the n2 drift: PERSISTED_MODALITIES must stay a subset of spec-lint's
    MODALITIES. A mismatch is a maintenance error -> exit 2 (loud), not a silent pass."""
    if not PERSISTED_MODALITIES <= set(getattr(sl, "MODALITIES", set())):
        raise PatchLintError(
            "PERSISTED_MODALITIES has drifted from spec-lint.MODALITIES "
            f"({sorted(PERSISTED_MODALITIES)} ⊄ {sorted(getattr(sl, 'MODALITIES', set()))}) "
            "— reconcile the two before relying on H6."
        )


def check_pre_modality(parsed_spec: dict) -> list:
    hard = []
    for tc_id, tc in sorted(parsed_spec["test_cases"].items()):
        mod = tc.get("modality")
        if mod in PERSISTED_MODALITIES:
            hard.append(
                f"H6 {tc_id}: modality `{mod}` is persisted-store / infrastructure work — "
                f"a durable noun the patch lane may not mint (C2). Route to /ce-plan."
            )
    return hard


# --- H7: planned task files within the lease --------------------------------

def check_pre_task_files(tasks: dict, frozen: list[str]) -> list:
    hard = []
    frozen_set = {_norm(f) for f in frozen}
    for t in tasks.get("tasks", []):
        if not isinstance(t, dict):
            continue
        for f in t.get("files") or []:
            if _norm(f) not in frozen_set:
                hard.append(
                    f"H7 {t.get('id', '?')}: planned to touch `{f}`, outside the frozen lease "
                    f"({len(frozen)} files). The spec already exceeds the patch boundary — "
                    f"route to /ce-plan."
                )
    return hard


# --- the diff (for --post) ---------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise PatchLintError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
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


def _importer_count(repo: Path, target: str) -> int | None:
    """Rough count of files whose source names the target module (import/require/from).
    Heuristic and language-naive — advisory only."""
    stem = Path(target).stem
    if not stem:
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "grep", "-l", "-E",
             rf"(import|require|from).*{re.escape(stem)}"],
            capture_output=True, text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode not in (0, 1):  # 1 == no matches, which is fine
        return None
    files = {ln for ln in out.stdout.splitlines() if ln and _norm(ln) != _norm(target)}
    return len(files)


def gather_diff(repo: Path, base: str, exclude_prefix: str | None) -> tuple[set, list]:
    """Return (changed_file_set, added_lines) covering tracked diff vs base PLUS
    untracked new files (read whole, treated as added).

    `exclude_prefix` (repo-relative, e.g. `docs/plans/patch-<slug>`) drops the
    patch lane's OWN bookkeeping subtree — eligibility.json, ce-spec.md, tasks.json,
    verification.md, .metrics.jsonl — so the diff gate scopes to production code,
    not the artifacts the lane itself writes (the same reason /ce-ship-deliver excludes
    docs/plans/).

    LIMITATION (m4): untracked files are gathered with `--exclude-standard`, so an
    artifact written into a .gitignore'd path is invisible to H8/H9/H10 — a narrow
    false negative in the dangerous direction. The skill's manual checklist must cover
    ignored-path writes; this gate cannot."""
    try:
        _git(repo, "rev-parse", "--verify", "--quiet", base + "^{commit}")
    except PatchLintError:
        raise PatchLintError(f"base ref `{base}` does not resolve in this repo")

    def keep(path: str) -> bool:
        return not (exclude_prefix and (path == exclude_prefix or path.startswith(exclude_prefix + "/")))

    changed = {
        _norm(p) for p in _git(repo, "diff", "--name-only", base).splitlines()
        if p.strip() and keep(_norm(p))
    }
    untracked = [
        p for p in _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        if p.strip() and keep(_norm(p))
    ]
    changed.update(_norm(p) for p in untracked)

    added_lines: list[tuple[str, str]] = []  # (path, line) — path best-effort
    diff_text = _git(repo, "diff", "--unified=0", base)
    cur = "?"
    for ln in diff_text.splitlines():
        if ln.startswith("+++ b/"):
            cur = _norm(ln[6:])
        elif ln.startswith("+") and not ln.startswith("+++") and keep(cur):
            added_lines.append((cur, ln[1:]))
    for p in untracked:
        full = repo / p
        try:
            for line in full.read_text(encoding="utf-8", errors="replace").splitlines():
                added_lines.append((_norm(p), line))
        except OSError:
            pass
    return changed, added_lines


# --- H8 / H10 / C3: diff content heuristics ---------------------------------
#
# These are HIGH-RECALL, LOW-PRECISION backstops, NOT a proof. They recognize a
# finite pattern set covering the dominant idioms; an op expressed in an idiom not
# listed here WILL slip past, so C2-post / C5-post are best-effort, never a guarantee
# (see the skill's Honest Limitations). They bias toward firing — an H8/H10 hit is a
# *material finding* the human adjudicates (real → promote; false positive → recorded
# acknowledgement citing the line), not an automatic verdict.

# C2 (durable-noun) — new migration/schema/persisted files.
DURABLE_FILE = re.compile(
    r"(^|/)(migrations?|migrate)/|\.(sql|ddl)$|schema\.(prisma|sql|rb)$|\b\d{10,}[-_].*\.(js|ts|py|rb)$",
    re.I,
)
# C2 (durable-noun) — DDL/DML + ORM / file / KV-store persistence calls across the
# common stacks (EF Core, SQLAlchemy, Prisma, TypeORM, Mongoose, Sequelize, fs, redis).
DURABLE_LINE = re.compile(
    r"\bCREATE\s+TABLE\b|\bALTER\s+TABLE\b|\bCREATE\s+INDEX\b|\bINSERT\s+INTO\b|\bUPDATE\s+\w+\s+SET\b"
    r"|\bcreate_table\b|\badd_column\b|\bSchema\s*\("
    r"|\.(save|saveChanges|saveChangesAsync|persist|insert|insertOne|insertMany|create|createMany|upsert|bulkCreate)\s*\("
    r"|\b(session|db|ctx|context|em|entityManager|repo|repository)\.(add|addAsync|merge|commit)\b"
    r"|\.Add(Async|Range)?\s*\("
    r"|\b(write_file|writeFile|writeFileSync|appendFile|appendFileSync)\b|\bfs\.(write|append)"
    r"|\b(localStorage|sessionStorage|redis|cache|kv|store)\.(set|setItem|put)\s*\("
    r"|\bmigrations?\.(create|add)\b",
    re.I,
)
# C5 (destructive / irreversible) — DDL drops/truncates/deletes, ORM deletes, fs removes.
DESTRUCTIVE_LINE = re.compile(
    r"\bDROP\s+TABLE\b|\bDROP\s+DATABASE\b|\bDROP\s+COLLECTION\b|\bTRUNCATE\b|\bDELETE\s+FROM\b"
    r"|\bdrop_table\b|\bdropCollection\b"
    r"|\.(delete|deleteOne|deleteMany|destroy|drop|remove)\s*\("
    r"|\b(os\.(remove|unlink|rmdir)|shutil\.rmtree|File\.Delete|Directory\.Delete)\b"
    r"|\b(unlink|unlinkSync|rm|rmSync|rmdir|rmdirSync)\s*\("
    r"|\brm\s+-rf\b|\brmtree\b",
    re.I,
)
# C3 (new interface/contract) — ADVISORY ONLY. New public surface another feature
# could consume. Far too fuzzy to gate on, so it surfaces for the human's Stage-4
# reconsideration; the primary C3 enforcement is the Stage-0 human attestation.
NEW_SURFACE_LINE = re.compile(
    r"^\s*export\s+(?!type\b|interface\b|//)"
    r"|^\s*public\s+(?!class\b|abstract\b)"
    r"|@(app|router|route|api|blueprint|bp)\.(get|post|put|patch|delete|route)\b"
    r"|\.(add_argument|addArgument|add_option|option|addOption|addCommand)\s*\(",
    re.I,
)


def check_post_diff(changed: set, added_lines: list, frozen: list[str]) -> tuple[list, list]:
    hard, advisory = [], []
    frozen_set = {_norm(f) for f in frozen}

    # H9 — scope creep (mechanical, exact). Mandatory promotion: the lease is void.
    for f in sorted(changed - frozen_set):
        hard.append(
            f"H9: the diff touches `{f}`, outside the frozen lease — the patch boundary "
            f"is exceeded (C1). This is a mandatory promotion to /ce-plan."
        )

    # H8 — durable noun in the diff (high-recall backstop; human adjudicates a hit).
    for f in sorted({p for p in changed if DURABLE_FILE.search(p)}):
        hard.append(f"H8: `{f}` looks like a migration / schema / persisted artifact — a durable noun (C2).")
    seen_h8 = set()
    for path, line in added_lines:
        if DURABLE_LINE.search(line):
            key = (path, line.strip()[:80])
            if key not in seen_h8:
                seen_h8.add(key)
                hard.append(f"H8: durable-store write in {path}: `{line.strip()[:100]}` (C2).")

    # H10 — destructive op in the diff (high-recall backstop; human adjudicates a hit).
    seen_h10 = set()
    for path, line in added_lines:
        if DESTRUCTIVE_LINE.search(line):
            key = (path, line.strip()[:80])
            if key not in seen_h10:
                seen_h10.add(key)
                hard.append(f"H10: destructive / irreversible op in {path}: `{line.strip()[:100]}` (C5).")

    # C3 — new public surface (ADVISORY: surfaces for the human, never gates).
    seen_c3 = set()
    for path, line in added_lines:
        if NEW_SURFACE_LINE.search(line):
            key = (path, line.strip()[:80])
            if key not in seen_c3:
                seen_c3.add(key)
                advisory.append(
                    f"C3: possible new public surface in {path}: `{line.strip()[:100]}` — "
                    f"reconsider whether this is a contract another feature would consume (C3 is "
                    f"human-attested; this is only a signal)."
                )

    return hard, advisory


# --- the express lane: mechanical featherweight screen (E1–E4) --------------
#
# The express fold (WS5-T2) admits a change with ONE gate — so the mechanical
# precondition has to be strong enough to justify bundling C6/C7 into that single
# gate. This screen is that precondition. It has no spec dir, no eligibility.json,
# no tasks.json: it takes a minimal stub ({"files": [...], "desc": "..."}) and
# refuses (exit 1, clause named) on anything a reviewer would need to see. It is
# high-recall by design — a false positive only routes to the full lane (safe);
# a false negative would let a sensitive surface through the one-gate lane (the
# outcome the screen exists to prevent).

EXPRESS_FILE_CAP = 2  # E1 — stricter than C1's file_cap; the featherweight ceiling.

# E3 — reviewer-trigger PATH segments (C6 mechanical floor). A candidate whose path
# has a SEGMENT beginning with one of these tokens cannot self-certify "no reviewer
# trigger" in the express lane. Left-bounded prefix match (so `authorization/`,
# `paymentService.ts`, `secrets/` all trip) — high-recall by design: over-matching
# only routes to the full /ce-patch lane, which is the safe direction.
REVIEWER_TRIGGER_PATH = re.compile(
    r"(^|/)("
    r"auth|login|logout|signin|signup|session|oauth|oidc|saml|jwt|sso"
    r"|secret|credential|token|password|passwd|crypto|keystore|vault"
    r"|payment|billing|checkout|invoice|charge|stripe|paypal|wallet"
    r"|migration|schema"
    r"|i18n|l10n|locale|translation"
    r"|a11y|accessibility|aria"
    r")",
    re.I,
)

# E3 — reviewer-trigger CONTENT patterns applied to the change *description* (the
# only content the pre-edit screen has). Word-anchored so prose about, say, an
# authentication bug is flagged, but incidental substrings are not.
REVIEWER_TRIGGER_CONTENT = re.compile(
    r"\b("
    r"auth\w*|login|logout|sign[- ]?in|sign[- ]?up|oauth|oidc|saml|jwt|sso|session"
    r"|secret\w*|credential\w*|password\w*|token|crypto\w*|encrypt\w*|decrypt\w*"
    r"|payment\w*|billing|checkout|invoice|charge|stripe|paypal"
    r"|migration\w*|schema"
    r"|i18n|l10n|locale\w*|translat\w*"
    r"|a11y|accessibilit\w*|aria"
    r")\b",
    re.I,
)

# E4 — dependency-manifest files. A candidate that edits one changes the supply
# chain; that is /ce-plan (dep-guard) territory, never the featherweight lane.
DEP_MANIFEST = re.compile(
    r"(^|/)("
    r"package(-lock)?\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml"
    r"|requirements[^/]*\.txt|Pipfile(\.lock)?|poetry\.lock|pyproject\.toml"
    r"|setup\.py|setup\.cfg|constraints[^/]*\.txt"
    r"|Gemfile(\.lock)?|go\.mod|go\.sum|Cargo\.(toml|lock)"
    r"|pom\.xml|build\.gradle(\.kts)?|ivy\.xml"
    r"|composer\.(json|lock)|packages\.config|paket\.dependencies"
    r")$"
    r"|\.(csproj|fsproj|vbproj)$",
    re.I,
)


def load_express_stub(arg: Path) -> tuple[list, str]:
    """Load the express stub: either a JSON file, or a directory holding express.json.
    Returns (normalized_files, description). Raises PatchLintError (-> exit 2) on any
    unreadable / malformed input, so garbled input reads as 'could-not-run, fall back
    loudly', never as a substantive FAIL."""
    stub_path = (arg / "express.json") if arg.is_dir() else arg
    if not stub_path.is_file():
        raise PatchLintError(f"express stub not found: {stub_path}")
    try:
        data = json.loads(stub_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PatchLintError(f"express stub is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise PatchLintError("express stub must be a JSON object with `files` and `desc`")
    files = data.get("files")
    if (not isinstance(files, list) or not files
            or not all(isinstance(f, str) and f.strip() for f in files)):
        raise PatchLintError("express stub `files` must be a non-empty list of path strings")
    desc = data.get("desc", "")
    if not isinstance(desc, str):
        raise PatchLintError("express stub `desc` must be a string")
    return [_norm(f) for f in files], desc


def _retag(msgs: list, old: str, new: str) -> list:
    return [new + m[len(old):] if m.startswith(old) else m for m in msgs]


def check_express_collision(files: list[str], repo: Path | None) -> tuple[list, list]:
    """E2 — reuse recompute_c4's cross-feature scan. The express lane has no spec dir
    of its own and no 'own plan' to exclude, so anchor a synthetic dir under the repo's
    docs/plans (parents[2].name == 'plans') and let recompute_c4 scan every real plan's
    tasks.json. Its `H5 C4:` findings are re-tagged to the E2 clause vocabulary."""
    anchor = (repo or Path.cwd()) / "docs" / "plans" / "__express__" / "specs" / "__candidate__"
    hard, advisory = recompute_c4(anchor, files)
    return _retag(hard, "H5 C4:", "E2:"), advisory


def check_express_screen(files: list[str], desc: str, repo: Path | None) -> tuple[list, list]:
    """E1–E4, the whole mechanical admission screen. Returns (hard, advisory)."""
    hard: list[str] = []
    advisory: list[str] = []

    # E1 — file cap (stricter than C1).
    if len(files) > EXPRESS_FILE_CAP:
        hard.append(
            f"E1: express admits at most {EXPRESS_FILE_CAP} files; candidate lists "
            f"{len(files)} — route to the full /ce-patch lane."
        )

    # E2 — C4 cross-feature collision (reused recompute_c4).
    c4_hard, c4_adv = check_express_collision(files, repo)
    hard += c4_hard
    advisory += c4_adv

    # E3 — reviewer-trigger surfaces (C6 mechanical floor): paths + durable-file wall.
    for f in files:
        if REVIEWER_TRIGGER_PATH.search(f):
            hard.append(
                f"E3: candidate file `{f}` is a reviewer-trigger surface "
                f"(auth / secret / payment / migration / i18n / a11y) — the express lane "
                f"may not self-certify C6. Route to the full /ce-patch lane."
            )
        if DURABLE_FILE.search(f):
            hard.append(
                f"E3: candidate file `{f}` looks like a migration / schema / persisted "
                f"artifact — a durable noun (C2). Route to the full /ce-patch lane."
            )
    # E3 — reviewer-trigger / durable / destructive content named in the description.
    if (REVIEWER_TRIGGER_CONTENT.search(desc)
            or DURABLE_LINE.search(desc) or DESTRUCTIVE_LINE.search(desc)):
        hard.append(
            "E3: the change description names a reviewer-trigger / durable / destructive "
            "surface — the express lane may not self-certify C6. Route to the full "
            "/ce-patch lane."
        )

    # E4 — no dependency-manifest file in the candidate set.
    for f in files:
        if DEP_MANIFEST.search(f):
            hard.append(
                f"E4: candidate file `{f}` is a dependency manifest — supply-chain surface "
                f"the express lane may not touch (C6/dep-guard). Route to the full "
                f"/ce-patch lane."
            )

    return hard, advisory


def run_express(arg: Path) -> tuple[list, list]:
    """--express (screen): the mechanical E1–E4 admission decision."""
    files, desc = load_express_stub(arg)
    stub_dir = arg if arg.is_dir() else arg.resolve().parent
    repo = _git_toplevel(stub_dir) or _git_toplevel(Path.cwd())
    return check_express_screen(files, desc, repo)


def run_express_post(arg: Path, base_override: str | None) -> tuple[list, list]:
    """--express --post: re-run H8/H9/H10 over the actual diff against the candidate
    file set — the one-gate express lane's external on-disk end check."""
    files, _desc = load_express_stub(arg)
    stub_file = (arg / "express.json") if arg.is_dir() else arg
    stub_dir = arg if arg.is_dir() else arg.resolve().parent
    repo = _git_toplevel(stub_dir) or _git_toplevel(Path.cwd())
    if repo is None:
        raise PatchLintError("not inside a git repository — cannot run the --express --post diff gate")
    if not base_override:
        raise PatchLintError("--express --post requires --base <ref> (the diff base to compare against)")
    # The express lane has no plan bookkeeping subtree, but its OWN stub file must not
    # count as a scope violation if it happens to live in the tree — exclude just it
    # (same reason --post excludes the patch's bookkeeping).
    exclude_prefix = None
    try:
        exclude_prefix = _norm(str(stub_file.resolve().relative_to(repo.resolve())))
    except (ValueError, OSError):
        pass  # stub is outside the repo — nothing to exclude
    changed, added_lines = gather_diff(repo, base_override, exclude_prefix)  # raises -> exit 2
    return check_post_diff(changed, added_lines, files)  # H8 / H9 / H10 + C3 advisory


# --- mode orchestration ------------------------------------------------------

def safe_spec_checks(spec_dir: Path, sl) -> tuple[dict, dict, list, list]:
    """Load + parse ce-spec.md (legacy spec.md accepted)/tasks.json and run
    spec-lint's H1–H4, mapping ANY failure
    from the spec-lint path (including a SpecLintError or a malformed-tasks crash) to a
    PatchLintError -> exit 2. Garbled input must read as 'could-not-run, fall back
    loudly', never masquerade as a substantive gate FAIL (exit 1)."""
    try:
        parsed, tasks = load_spec_and_tasks(spec_dir, sl)
        sl_hard, sl_adv = sl.run_checks(parsed, tasks)
    except PatchLintError:
        raise
    except Exception as e:  # noqa: BLE001 — any spec-lint-path failure is a fallback
        raise PatchLintError(f"spec-lint could not run on {spec_dir}: {e}") from e
    return parsed, tasks, sl_hard, sl_adv


def run_eligibility(spec_dir: Path, draft: bool = False) -> tuple[list, list]:
    return check_eligibility(spec_dir, draft=draft)


def run_pre(spec_dir: Path, sl) -> tuple[list, list]:
    assert_modalities_subset(sl)                       # n2 drift guard -> exit 2 if drifted
    hard, advisory = [], []
    e_hard, e_adv = check_eligibility(spec_dir)        # H5 (lease must be valid first)
    hard += e_hard
    advisory += e_adv

    parsed, tasks, sl_hard, sl_adv = safe_spec_checks(spec_dir, sl)  # H1–H4 (+ A0–A3)
    hard += sl_hard
    advisory += sl_adv

    hard += check_pre_modality(parsed)                 # H6
    frozen = load_eligibility(spec_dir).get("frozen_files") or []
    hard += check_pre_task_files(tasks, frozen)        # H7
    return hard, advisory


def run_post(spec_dir: Path, sl, base_override: str | None) -> tuple[list, list]:
    hard, advisory = [], []
    # m1 — re-assert the lease's consent invariants at the build-evidence end too, so a
    # clause flipped to NO / a stripped attestation between pre and post is still caught.
    e_hard, e_adv = check_eligibility(spec_dir)        # H5
    hard += e_hard
    advisory += e_adv

    _parsed, _tasks, sl_hard, sl_adv = safe_spec_checks(spec_dir, sl)  # H1–H4 (final spec)
    hard += sl_hard
    advisory += sl_adv

    elig = load_eligibility(spec_dir)
    frozen = elig.get("frozen_files") or []
    base = base_override or elig.get("base_ref")
    if not base:
        raise PatchLintError("no diff base — pass --base or record base_ref in eligibility.json")

    repo = _git_toplevel(spec_dir)
    if repo is None:
        raise PatchLintError("not inside a git repository — cannot run the --post diff gate")

    # The patch's own plan dir (.../plans/<patch-slug>) holds the lane's bookkeeping;
    # exclude it so the diff gate scopes to production code only.
    exclude_prefix = None
    try:
        plan_dir = spec_dir.resolve().parents[1]
        exclude_prefix = _norm(str(plan_dir.relative_to(repo.resolve())))
    except (IndexError, ValueError):
        pass  # spec dir not under the repo in the expected layout — exclude nothing

    changed, added_lines = gather_diff(repo, base, exclude_prefix)  # raises -> exit 2
    d_hard, d_adv = check_post_diff(changed, added_lines, frozen)   # H8 / H9 / H10 + C3 advisory
    hard += d_hard
    advisory += d_adv
    return hard, advisory


# --- reporting ---------------------------------------------------------------

def emit(mode: str, spec_dir: Path, hard: list, advisory: list, as_json: bool) -> int:
    status = "fail" if hard else "pass"
    if as_json:
        print(json.dumps({
            "status": status,
            "mode": mode,
            "spec_dir": str(spec_dir),
            "hard_failures": hard,
            "advisory": advisory,
        }, indent=2))
        return 1 if hard else 0

    print(f"patch-lint [{mode}]: {spec_dir}")
    if hard:
        print(f"\n  FAIL — {len(hard)} hard failure(s):")
        for f in hard:
            print(f"    x {f}")
    else:
        print(f"\n  PASS — patch-charter checks for [{mode}] hold.")
    if advisory:
        print(f"\n  advisory ({len(advisory)} — review, non-blocking):")
        for a in advisory:
            print(f"    ! {a}")
    print()
    return 1 if hard else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="On-disk gate for the /ce-patch lane.")
    p.add_argument("spec_dir", help="the patch spec directory (holds eligibility.json, and after Stage 1 "
                                     "ce-spec.md + tasks.json); with --express, the express stub JSON "
                                     "(or a directory holding express.json)")
    # Four modes; --express is the only one that pairs with another flag (--post).
    # Manual validation (not a mutually_exclusive_group) so --express --post can co-occur.
    p.add_argument("--eligibility", action="store_true", help="Stage 0 — validate the lightness lease")
    p.add_argument("--pre", action="store_true", help="Stage 2 — gate the spec artifact before implement")
    p.add_argument("--post", action="store_true", help="Stage 4 — gate the actual diff after implement "
                                                        "(or, with --express, the express diff end check)")
    p.add_argument("--express", action="store_true",
                   help="featherweight express screen — mechanical E1–E4 admission over a JSON stub; "
                        "combine with --post --base R for the diff end check")
    p.add_argument("--draft", action="store_true",
                   help="with --eligibility: mechanical pre-screen before the human stamps the lease "
                        "(consent fields demoted to advisory; C1/C4 + explicit-NO stay hard)")
    p.add_argument("--base", help="diff base ref for --post / --express --post (overrides eligibility.base_ref)")
    p.add_argument("--json", action="store_true", help="machine-readable result")
    args = p.parse_args(argv)

    # --- mode resolution: exactly one primary mode; --express pairs only with --post ---
    if args.express:
        if args.eligibility or args.pre:
            p.error("--express combines only with --post (or runs alone); not with --eligibility/--pre")
        mode_name = "express-post" if args.post else "express"
    else:
        if (args.eligibility + args.pre + args.post) != 1:
            p.error("exactly one of --eligibility / --pre / --post is required (or --express)")
        mode_name = "eligibility" if args.eligibility else "pre" if args.pre else "post"

    spec_dir = Path(args.spec_dir)

    # All spec-lint-path failures are converted to PatchLintError inside run_pre/run_post
    # (safe_spec_checks), so a single PatchLintError handler covers every exit-2 case.
    try:
        if args.express:
            if args.post:
                hard, advisory = run_express_post(spec_dir, args.base)
            else:
                hard, advisory = run_express(spec_dir)
        elif args.eligibility:
            hard, advisory = run_eligibility(spec_dir, draft=args.draft)
        else:
            sl = load_spec_lint()
            if args.pre:
                hard, advisory = run_pre(spec_dir, sl)
            else:
                hard, advisory = run_post(spec_dir, sl, args.base)
    except PatchLintError as e:
        if args.json:
            print(json.dumps({"status": "error", "mode": mode_name, "message": str(e)}))
        else:
            print(f"patch-lint [{mode_name}]: ERROR — could not run: {e}", file=sys.stderr)
            print("  -> fall back to the manual Patch-Charter checklist (loudly).", file=sys.stderr)
        return 2

    return emit(mode_name, spec_dir, hard, advisory, args.json)


if __name__ == "__main__":
    sys.exit(main())
