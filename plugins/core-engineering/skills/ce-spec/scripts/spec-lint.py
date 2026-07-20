#!/usr/bin/env python3
"""spec-lint.py — referential-integrity lint for an assembled feature spec.

Checks a `ce-spec.md` + `tasks.json` pair (produced by the `spec` workflow;
legacy `spec.md` accepted in dir mode)
for the *mechanical* traceability invariants the pre-write Validation Checklist
otherwise asserts by hand. It SUPPLEMENTS that checklist — it does not replace it:

  * An un-runnable lint (missing/garbled inputs) exits 2 so the owning workflow
    can apply its documented degraded mode; it must never look like a pass.
  * Only the on-disk-checkable subset is covered; genuine-judgment items
    (e.g. "is this `manual:judgment` really un-automatable?") stay with the human.

HARD checks (a FAIL -> exit 1; these gate auto-build's spec-artifact step):
  H1  Every `verifies` id in tasks.json is a TC id that exists in ce-spec.md.
  H2  Every TC in ce-spec.md carries both a `modality:` and a `verification:` tag,
      and a `manual` modality pairs with `manual:judgment`.
  H3  No orphan task — every task has a non-empty `verifies`.
  H4  No orphan TC — every TC is referenced by at least one task's `verifies`.
  H5  Security-criteria coverage (only when the feature has assigned threat-ids):
      every `TZ-NNN` the plan's threat-model.md assigns to this feature is covered
      by >= 1 acceptance criterion carrying a `[SECURITY: TZ-NNN]` marker. Security
      is a stated, traceable requirement — not left to the generator (the Veracode
      finding that AI-code security pass rates are flat). N/A-safe: a feature with
      no supplied threat-ids (legacy specs, threat-model absent, `--threat-*` not
      passed) skips H5 entirely — never a false FAIL.
      H5's disposition is always REPORTED as `h5_status` (in `--json` and the human
      PASS line): `ran` (threat-ids resolved, the check executed), `na` (no
      threat-model file and no `--threat-ids`/`--threat-model` flag — genuinely out
      of scope), or `disarmed` (a threat-model / flag was supplied but yielded no
      ids: the feature matched no `security_obligations` entry, the block parse
      failed, or the flag value was empty/unresolvable). `disarmed` never changes
      the exit code, but it is LOUD — an advisory names the unmatched feature id —
      so a formatting slip in threat-model.md can no longer silently switch the
      security gate off.
  H6  `tasks[].files` file-set consistency (only when `enforce_files=True`, which
      main() sets — so `/core-engineering:ce-spec` and the auto-build spec gate enforce it, but
      patch-lint's `run_checks(parsed, tasks)` import stays unaffected). Once a spec
      ADOPTS the file-boundary convention — any task carrying a non-empty `files`
      list — EVERY task must carry one, so the implement-scope guard can enforce the
      Scope Lock's file boundary with no silent gaps. A spec where NO task lists files
      is a legacy spec authored before enforcement: H6 is N/A (silent — the guard
      itself advisory-warns on it, never a false FAIL here).

ADVISORY checks (warnings only; never change the exit code — markdown-derived,
best-effort):
  A0  a TC's `modality:` / `verification:` value is outside the known vocabulary.
  A1  ce-spec.md section 6 task ids and tasks.json task ids agree.
  A2  Every AC is proven by >= 1 TC ("(proves AC-x)").
  A3  Every TC- / T- / AC- token in the section 7 Traceability Matrix resolves.
  A4  Surface-quality coverage: when the spec declares a user-facing rendered
      surface (>= 1 `modality: browser` TC) but NO acceptance criterion carries a
      `[SURFACE]` marker, warn that no Surface-Quality criteria were authored for
      the Surface Critique pass to check against. Asserts DECLARATION only — never
      readability (un-lintable from markdown; the model-judgment pass renders the
      findings). N/A-safe: no browser surface, or a `[SURFACE]` AC already present,
      skips A4 entirely — never a false warning that something is broken.

Usage:
    spec-lint.py <spec-dir>                     # dir holding ce-spec.md (legacy spec.md accepted) + tasks.json
    spec-lint.py --spec ce-spec.md --tasks t.json  # explicit files
    spec-lint.py <spec-dir> --json              # machine-readable result
    spec-lint.py <spec-dir>                     # H5 auto-runs if <spec-dir>/../../threat-model.md exists
    spec-lint.py <spec-dir> --threat-ids TZ-001,TZ-002       # H5: explicit ids
    spec-lint.py --spec s.md --tasks t.json --threat-model path/threat-model.md  # H5: explicit file

Exit codes:
    0  PASS  — no hard failures (advisory warnings may still be printed)
    1  FAIL  — at least one hard referential-integrity failure
    2  ERROR — inputs missing or unparseable; caller must apply its owning
               workflow's documented exit-2 disposition (never a pass)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Known vocabularies (spec SKILL.md section 2.2). Out-of-enum values are
# an advisory warning, not a hard failure — a spec may legitimately extend these.
MODALITIES = {"browser", "http", "cli", "sdk", "event", "iac", "db", "manual"}
VERIFICATIONS = {"auto", "manual:harness-gap", "manual:judgment"}

TC_HEADER = re.compile(r"^#{2,4}\s+(TC-[A-Za-z0-9]+)\b(.*)$")
AC_HEADER = re.compile(r"^#{2,4}\s+(AC-[A-Za-z0-9]+)\b(.*)$")
TASK_HEADER = re.compile(r"^#{2,4}\s+(T-[A-Za-z0-9]+)\b(.*)$")
MODALITY_TAG = re.compile(r"modality:\s*([A-Za-z][A-Za-z0-9:-]*)")
VERIFICATION_TAG = re.compile(r"verification:\s*(manual:[A-Za-z-]+|[A-Za-z]+)")
PROVES = re.compile(r"proves\s+(AC-[A-Za-z0-9]+)")
ID_TOKEN = re.compile(r"\b((?:TC|T|AC)-[A-Za-z0-9]+)\b")
# H5: a security AC carries a `[SECURITY: TZ-NNN]` marker on its header line (the
# `.*` AC_HEADER tail already captures it). The marker may list >1 id, e.g.
# `[SECURITY: TZ-001, TZ-002]`, and an AC header may carry >1 marker — all are unioned.
SECURITY_MARKER = re.compile(r"\[SECURITY\b([^\]]*)\]", re.I)
THREAT_ID = re.compile(r"\bTZ-\d+\b", re.I)
# A4: a Surface-Quality AC carries a `[SURFACE]` marker on its header line (same
# placement + tail-capture as [SECURITY], and disjoint from it — `\bSURFACE` never
# matches SECURITY). Its PRESENCE means surface-quality criteria were authored; its
# ABSENCE alongside a rendered-surface signal (a `modality: browser` TC) is what A4
# warns on. An optional tail names the surface, e.g. `[SURFACE: room-canvas]`.
SURFACE_MARKER = re.compile(r"\[SURFACE\b([^\]]*)\]", re.I)


def _canon_tz(tz: str) -> str:
    """Canonicalize a threat-id for H5 comparison so a format slip never causes a
    false miss: uppercase + strip leading zeros (TZ-001, tz-1, TZ-1 all -> TZ-1)."""
    m = re.match(r"TZ-0*(\d+)$", tz.strip(), re.I)
    return f"TZ-{m.group(1)}" if m else tz.strip().upper()


class SpecLintError(Exception):
    """Inputs cannot be loaded/parsed -> exit 2, never a pass."""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def resolve_inputs(args) -> tuple[Path, Path]:
    if args.spec or args.tasks:
        if not (args.spec and args.tasks):
            raise SpecLintError("--spec and --tasks must be given together")
        return Path(args.spec), Path(args.tasks)
    if not args.spec_dir:
        raise SpecLintError("provide a spec directory, or --spec and --tasks")
    d = Path(args.spec_dir)
    # Canonical artifact name is ce-spec.md; legacy spec.md is accepted as a
    # fallback so pre-rename spec dirs still lint. When neither exists, return
    # the canonical path so load()'s not-found error names the expected file.
    spec = d / "ce-spec.md"
    if not spec.is_file() and (d / "spec.md").is_file():
        spec = d / "spec.md"
    return spec, d / "tasks.json"


def load(spec_path: Path, tasks_path: Path) -> tuple[str, dict]:
    if not spec_path.is_file():
        raise SpecLintError(f"spec file not found: {spec_path} "
                            f"(canonical ce-spec.md; legacy spec.md accepted)")
    if not tasks_path.is_file():
        raise SpecLintError(f"tasks.json not found: {tasks_path}")
    spec_text = spec_path.read_text(encoding="utf-8")
    try:
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SpecLintError(f"tasks.json is not valid JSON: {e}") from e
    if not isinstance(tasks, dict) or not isinstance(tasks.get("tasks"), list):
        raise SpecLintError("tasks.json must be an object with a `tasks` array")
    return spec_text, tasks


# ---------------------------------------------------------------------------
# Parsing the spec markdown (ce-spec.md; legacy spec.md accepted)
# ---------------------------------------------------------------------------

def _blocks(lines, header_regex):
    """Yield (id, header_tail, body_text) for each header match — body is the
    lines up to the next header of any level."""
    any_header = re.compile(r"^#{2,4}\s+\S")
    i = 0
    n = len(lines)
    while i < n:
        m = header_regex.match(lines[i])
        if m:
            start = i + 1
            j = start
            while j < n and not any_header.match(lines[j]):
                j += 1
            yield m.group(1), m.group(2), "\n".join(lines[start:j])
            i = j
        else:
            i += 1


def parse_spec(spec_text: str) -> dict:
    lines = spec_text.splitlines()

    test_cases = {}
    for tc_id, tail, body in _blocks(lines, TC_HEADER):
        scope = tail + "\n" + body
        mod = MODALITY_TAG.search(scope)
        ver = VERIFICATION_TAG.search(scope)
        proves = PROVES.findall(scope)
        test_cases[tc_id] = {
            "modality": mod.group(1) if mod else None,
            "verification": ver.group(1) if ver else None,
            "proves": proves,
        }

    # AC ids (a set, unchanged for A2/A3) and, in the same pass, the security ACs:
    # {ac_id: [TZ-NNN, ...]} for any AC whose header tail carries a [SECURITY: ...] marker.
    acceptance = set()
    security_acs = {}
    surface_acs = {}
    for ac_id, tail, _body in _blocks(lines, AC_HEADER):
        acceptance.add(ac_id)
        markers = list(SECURITY_MARKER.finditer(tail))  # header line only — not the body
        if markers:
            ids = []
            for mk in markers:
                ids.extend(THREAT_ID.findall(mk.group(1)))
            security_acs[ac_id] = ids  # may be [] for a bare [SECURITY] — covers nothing specific
        smarkers = list(SURFACE_MARKER.finditer(tail))  # header line only — not the body
        if smarkers:
            names = []
            for mk in smarkers:
                names.append(mk.group(1).lstrip(":").strip())
            surface_acs[ac_id] = [n for n in names if n]  # named surfaces; [] for a bare [SURFACE]

    md_tasks = {t_id for t_id, _tail, _body in _blocks(lines, TASK_HEADER)}

    # Section 7 traceability matrix: collect ID tokens from table rows that sit
    # under a "Traceability" heading.
    matrix_ids = set()
    in_matrix = False
    for ln in lines:
        if re.match(r"^#{2,3}\s", ln):
            in_matrix = "traceability" in ln.lower()
            continue
        if in_matrix and ln.lstrip().startswith("|"):
            matrix_ids.update(ID_TOKEN.findall(ln))

    return {
        "test_cases": test_cases,
        "acceptance": acceptance,
        "security_acs": security_acs,
        "surface_acs": surface_acs,
        "md_tasks": md_tasks,
        "matrix_ids": matrix_ids,
    }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def run_checks(spec: dict, tasks: dict, threat_ids: set | None = None,
               enforce_files: bool = False) -> tuple[list, list]:
    """`threat_ids` (a set of TZ-NNN the threat-model assigns to this feature) drives
    H5. It is keyword/optional so existing callers — incl. patch-lint's
    `sl.run_checks(parsed, tasks)` — keep working unchanged, and a feature with no
    assigned threats (or no threat-model) simply skips H5.

    `enforce_files` (default False) drives H6, the `tasks[].files` consistency check.
    main() sets it True so `/core-engineering:ce-spec` and the auto-build spec gate enforce the file
    boundary; patch-lint imports `run_checks` and calls it WITHOUT the flag (the patch
    lane has its own frozen_files discipline), so its behavior is unchanged."""
    hard, advisory = [], []
    tcs = spec["test_cases"]
    tc_ids = set(tcs)

    json_tasks = tasks["tasks"]
    json_task_ids = []
    verified_tcs = set()

    # H3 orphan tasks + H1 verifies resolve
    for idx, t in enumerate(json_tasks):
        if not isinstance(t, dict):
            hard.append(f"H3 <task #{idx + 1}>: task entry is not an object")
            continue
        tid = t.get("id") or f"<task #{idx + 1}>"
        json_task_ids.append(t.get("id"))
        verifies = t.get("verifies") or []
        if not isinstance(verifies, list):
            hard.append(f"H1 {tid}: `verifies` must be a list")
            continue
        if not verifies:
            hard.append(f"H3 {tid}: orphan task — empty `verifies` (every task must prove >= 1 TC)")
        for v in verifies:
            verified_tcs.add(v)
            if v not in tc_ids:
                hard.append(f"H1 {tid}: `verifies` -> {v}, which is not a TC in the spec")

    # H2 TC tags
    for tc_id, tc in sorted(tcs.items()):
        if not tc["modality"]:
            hard.append(f"H2 {tc_id}: missing `modality:` tag")
        if not tc["verification"]:
            hard.append(f"H2 {tc_id}: missing `verification:` tag")
        if tc["modality"] == "manual" and tc["verification"] != "manual:judgment":
            hard.append(
                f"H2 {tc_id}: `modality: manual` must pair with `verification: manual:judgment` "
                f"(found `{tc['verification']}`)"
            )
        if tc["modality"] and tc["modality"] not in MODALITIES:
            advisory.append(f"A0 {tc_id}: unknown modality `{tc['modality']}` (not in {sorted(MODALITIES)})")
        if tc["verification"] and tc["verification"] not in VERIFICATIONS:
            advisory.append(f"A0 {tc_id}: unknown verification `{tc['verification']}`")

    # H4 orphan TCs
    for tc_id in sorted(tc_ids):
        if tc_id not in verified_tcs:
            hard.append(f"H4 {tc_id}: orphan TC — no task `verifies` it")

    # H5 security-criteria coverage — only when the feature has assigned threat-ids
    # (a falsy threat_ids — None or empty — is N/A, never a FAIL). Each assigned
    # TZ-NNN must be covered by >= 1 AC carrying `[SECURITY: TZ-NNN]`.
    if threat_ids:
        covered = set()
        for tzids in spec.get("security_acs", {}).values():
            covered.update(_canon_tz(t) for t in tzids)
        for tz in sorted(threat_ids):
            if _canon_tz(tz) not in covered:
                hard.append(
                    f"H5 {tz}: threat-model.md assigns this threat to the feature, but no "
                    f"acceptance criterion carries `[SECURITY: {tz}]`. Security is a stated, "
                    f"traceable requirement — add a [SECURITY] AC (auto / manual:harness-gap), "
                    f"or consent-exclude the obligation in the plan."
                )

    # H6 tasks[].files consistency — only under enforce_files (main() sets it; the
    # patch-lint import does not). Once ANY task declares a non-empty `files` list the
    # spec has adopted the file-boundary convention, so EVERY task must declare one —
    # otherwise the implement-scope guard would have a silent hole (a task whose files
    # it cannot check). A spec where NO task lists files is a legacy spec authored
    # before enforcement: H6 is N/A (the implement-scope guard advisory-warns on it),
    # never a false FAIL.
    if enforce_files:
        def _has_files(t: dict) -> bool:
            fs = t.get("files")
            return isinstance(fs, list) and any(
                isinstance(f, str) and f.strip() for f in fs)
        any_files = any(isinstance(t, dict) and _has_files(t) for t in json_tasks)
        if any_files:
            for idx, t in enumerate(json_tasks):
                if not isinstance(t, dict):
                    continue
                tid = t.get("id") or f"<task #{idx + 1}>"
                if not _has_files(t):
                    hard.append(
                        f"H6 {tid}: this spec declares `tasks[].files` on other tasks "
                        f"but this task lists none — every task must name its files so "
                        f"the implement-scope guard can enforce the Scope Lock's file "
                        f"boundary. Add a non-empty `files` list (>= 1 path string).")

    # A1 task-id agreement
    json_set = {t for t in json_task_ids if t}
    md_set = spec["md_tasks"]
    if md_set:
        for missing in sorted(md_set - json_set):
            advisory.append(f"A1 {missing}: task in spec section 6 but not in tasks.json")
        for missing in sorted(json_set - md_set):
            advisory.append(f"A1 {missing}: task in tasks.json but not in spec section 6")

    # A2 every AC proven by >= 1 TC
    proven = set()
    for tc in tcs.values():
        proven.update(tc["proves"])
    for ac in sorted(spec["acceptance"]):
        if ac not in proven:
            advisory.append(f"A2 {ac}: no TC declares `(proves {ac})`")

    # A3 matrix tokens resolve
    known = tc_ids | spec["acceptance"] | json_set | md_set
    for tok in sorted(spec["matrix_ids"]):
        if tok not in known:
            advisory.append(f"A3 {tok}: referenced in the Traceability Matrix but defined nowhere")

    # A4 surface-quality coverage — advisory only, never a hard FAIL. A rendered
    # surface is signalled by >= 1 `modality: browser` TC; surface-quality criteria
    # are signalled by a `[SURFACE]` AC marker. A surface with no such criterion has
    # nothing for the Surface Critique pass to check against. Asserts DECLARATION,
    # never readability (which is un-lintable from markdown).
    browser_tc = sorted(t for t, tc in tcs.items() if tc.get("modality") == "browser")
    if browser_tc and not spec.get("surface_acs"):
        advisory.append(
            f"A4: spec declares a rendered surface ({len(browser_tc)} browser TC: "
            f"{', '.join(browser_tc)}) but no acceptance criterion carries a `[SURFACE]` "
            f"marker — author a Surface-Quality criterion (the Surface Critique pass checks "
            f"against it), or record why none applies."
        )

    return hard, advisory


# ---------------------------------------------------------------------------
# H5 threat-id resolution
# ---------------------------------------------------------------------------

def read_feature_threat_ids(threat_model_path: Path, feature: str) -> set | None:
    """Best-effort extraction of ONE feature's `threat_ids` from threat-model.md's
    `security_obligations` block. Stdlib-only (no YAML dep, deliberately — spec-lint
    must stay importable by patch-lint without new deps). MISS-SAFE: an unreadable
    file, an absent feature, or an empty list all return a falsy result so H5 becomes
    N/A — a parse failure must never manufacture a hard FAIL. The miss is not silent,
    though: resolve_threat_ids reports it as `h5_status: disarmed` and main() renders
    a loud advisory. For reliability the caller may instead pass --threat-ids
    explicitly (it takes precedence)."""
    if not threat_model_path.is_file():
        return None
    try:
        text = threat_model_path.read_text(encoding="utf-8")
    except OSError:
        return None
    # Match `- feature: <feature>` and capture up to the next `- feature:` / EOF,
    # then pull the `threat_ids: [ ... ]` list out of that slice.
    block = re.search(
        r"-\s*feature:\s*['\"]?" + re.escape(feature) + r"['\"]?\s*\n(.*?)(?=\n\s*-\s*feature:|\Z)",
        text, re.S,
    )
    if not block:
        return None
    seg = block.group(1)
    # YAML flow form: `threat_ids: [TZ-001, TZ-002]`
    flow = re.search(r"threat_ids:\s*\[([^\]]*)\]", seg)
    if flow:
        return set(THREAT_ID.findall(flow.group(1)))
    # YAML block form: `threat_ids:\n  - TZ-001\n  - TZ-002` (up to the next sibling key / EOF)
    blk = re.search(r"threat_ids:\s*\n(.*?)(?=\n\s*\w[\w-]*:|\Z)", seg, re.S)
    if blk:
        return set(THREAT_ID.findall(blk.group(1)))
    return None


def _feature_id(args, spec_path: Path, tasks: dict) -> str:
    """Feature id = --feature, else tasks.json `feature_id`, else the spec dir name.
    .resolve() so the spec-dir-name fallback is invocation-form-independent — a
    relative `.` arg would otherwise yield an empty name and silently bypass H5."""
    return args.feature or tasks.get("feature_id") or spec_path.resolve().parent.name


def resolve_threat_ids(args, spec_path: Path, tasks: dict) -> tuple[set | None, str]:
    """--threat-ids (explicit, comma-separated) wins; else --threat-model; else the
    CANONICAL location `<spec_dir>/../../threat-model.md` is auto-discovered — so H5
    runs on any `spec-lint.py specs/<id>` over a plan that has a threat-model, with no
    flag, CWD-independent. Returns `(ids, h5_status)`:
      ("ran")      non-empty ids resolved — H5 executes;
      ("na")       no threat-model file exists AND neither `--threat-ids` nor
                   `--threat-model` was passed — H5 genuinely out of scope;
      ("disarmed") H5 was armed but could not run: a threat-model file resolved but
                   this feature matched no `security_obligations` entry (or the block
                   parse failed), an explicit `--threat-model` path is not a file, or
                   `--threat-ids` parsed to no ids. Never a FAIL — but main() renders
                   a loud advisory so the fail-open is visible."""
    if args.threat_ids:
        ids = {t.strip() for t in args.threat_ids.split(",") if t.strip()}
        return ids, ("ran" if ids else "disarmed")
    if args.threat_model:
        tm = Path(args.threat_model)
    else:
        tm = spec_path.parent / ".." / ".." / "threat-model.md"  # docs/plans/<slug>/specs/<id> -> plans/<slug>
    if not tm.is_file():
        # `na` only when H5 was never armed; an explicit --threat-model that does
        # not resolve to a file is a disarm, never a silent skip.
        return None, ("disarmed" if args.threat_model else "na")
    ids = read_feature_threat_ids(tm, _feature_id(args, spec_path, tasks))
    return ids, ("ran" if ids else "disarmed")


def h5_disarm_advisory(args, spec_path: Path, tasks: dict) -> str:
    """The loud half of the fail-open contract: name WHY H5 could not arm, so a
    formatting slip in threat-model.md (the silent-disarm class) is always visible.
    Advisory only — a disarm must never manufacture a hard FAIL."""
    if args.threat_ids:
        return ("H5 N/A though --threat-ids was passed — it parsed to no TZ-NNN ids; "
                "fix the flag value (e.g. --threat-ids TZ-001,TZ-002)")
    if args.threat_model and not Path(args.threat_model).is_file():
        return (f"H5 N/A though --threat-model was passed — {args.threat_model} is not "
                f"a file; fix the path, or pass --threat-ids")
    return (f"H5 N/A though threat-model.md is present — feature id "
            f"{_feature_id(args, spec_path, tasks)} matched no security_obligations "
            f"entry; pass --threat-ids or --feature to force, or fix the "
            f"threat-model block")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Referential-integrity lint for a feature spec.")
    p.add_argument("spec_dir", nargs="?",
                   help="directory containing ce-spec.md (legacy spec.md accepted) + tasks.json")
    p.add_argument("--spec", help="path to the spec markdown file (use with --tasks)")
    p.add_argument("--tasks", help="path to tasks.json (use with --spec)")
    p.add_argument("--threat-ids", help="comma-separated TZ-NNN this feature must cover (H5); takes precedence over --threat-model")
    p.add_argument("--threat-model", help="path to the plan's threat-model.md; H5 reads this feature's threat_ids from it")
    p.add_argument("--feature", help="feature id for --threat-model lookup (default: tasks.json feature_id, else spec-dir name)")
    p.add_argument("--json", action="store_true", help="emit a machine-readable JSON result")
    args = p.parse_args(argv)

    try:
        spec_path, tasks_path = resolve_inputs(args)
        spec_text, tasks = load(spec_path, tasks_path)
        spec = parse_spec(spec_text)
        threat_ids, h5_status = resolve_threat_ids(args, spec_path, tasks)
        hard, advisory = run_checks(spec, tasks, threat_ids=threat_ids,
                                    enforce_files=True)
        if h5_status == "disarmed":
            advisory.append(h5_disarm_advisory(args, spec_path, tasks))
    except SpecLintError as e:
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            print(f"spec-lint: ERROR — could not run: {e}", file=sys.stderr)
            print("  -> follow the owning workflow's exit-2 disposition; never treat this as a pass.", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        # Any UNEXPECTED failure (e.g. a shape the checks never anticipated) must
        # honor the exit-2 "could not run" contract, never
        # leak as an uncaught traceback that exits 1 and impersonates a hard FAIL
        # to a caller (auto-build) that gates on the exit code. SystemExit is not
        # an Exception subclass, so argparse's own --help/usage exits are unaffected.
        if args.json:
            print(json.dumps({"status": "error", "message": f"unexpected: {type(e).__name__}: {e}"}))
        else:
            print(f"spec-lint: ERROR — unexpected failure ({type(e).__name__}): {e}", file=sys.stderr)
            print("  -> follow the owning workflow's exit-2 disposition; never treat this as a pass.", file=sys.stderr)
        return 2

    status = "fail" if hard else "pass"
    if args.json:
        print(json.dumps({
            "status": status,
            "spec": str(spec_path),
            "test_cases": len(spec["test_cases"]),
            "acceptance_criteria": len(spec["acceptance"]),
            "security_acs": len(spec.get("security_acs", {})),
            "surface_acs": len(spec.get("surface_acs", {})),
            "threat_ids": sorted(threat_ids) if threat_ids else [],
            "h5_status": h5_status,
            "tasks": len(tasks["tasks"]),
            "hard_failures": hard,
            "advisory": advisory,
        }, indent=2))
        return 1 if hard else 0

    tc_n = len(spec["test_cases"])
    ac_n = len(spec["acceptance"])
    t_n = len(tasks["tasks"])
    sec_n = len(spec.get("security_acs", {}))
    surf_n = len(spec.get("surface_acs", {}))
    sec_note = f" · {sec_n} security AC" if sec_n else ""
    surf_note = f" · {surf_n} surface AC" if surf_n else ""
    threat_note = f" · H5 over {len(threat_ids)} threat-id(s)" if threat_ids else ""
    print(f"spec-lint: {spec_path}")
    print(f"  parsed: {ac_n} AC · {tc_n} TC · {t_n} tasks{sec_note}{surf_note}{threat_note}")
    if hard:
        print(f"\n  FAIL — {len(hard)} hard referential-integrity failure(s):")
        for f in hard:
            print(f"    x {f}")
    else:
        passed = "H1-H5" if h5_status == "ran" else "H1-H4"
        h5_note = {"ran": "H5 ran", "na": "H5 n/a", "disarmed": "H5 DISARMED"}[h5_status]
        print(f"\n  PASS — hard referential-integrity checks ({passed}) hold ({h5_note}).")
    if advisory:
        print(f"\n  advisory ({len(advisory)} — review, non-blocking):")
        for a in advisory:
            print(f"    ! {a}")
    print()
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
