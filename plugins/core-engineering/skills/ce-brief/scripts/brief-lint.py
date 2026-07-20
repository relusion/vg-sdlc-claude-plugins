#!/usr/bin/env python3
"""brief-lint.py — well-formedness lint for a /core-engineering:ce-brief artifact pair.

Validates a `docs/briefs/<slug>.md` brief and its `docs/briefs/<slug>.json`
sidecar so the **Brief -> Plan skip contract** (ce-plan Stage 1.4) is COMPUTED
from data instead of model-attested prose. The sidecar is the machine-readable
skip map; if it is malformed, ce-plan's Brief-Aware Skip Contract would be
skipping questions on the strength of an unchecked artifact — this closes the
spine's least-verified entry stage.

Sidecar schema (schema_version 1):
    {
      "schema_version": 1,
      "sections": {"<section-slug>": "answered"|"open"|"disputed", ...},
      "lenses": ["solutions-architect", ...],   # applied persona lenses
      "open_questions": <int >= 0>
    }

HARD checks (a FAIL -> exit 1; these gate Stage 3's "Approve & write"):
  H1  Every required Brief-Template heading is present in the markdown brief.
  H2  The Project Description section is non-empty and clears a self-sufficiency
      length floor (it is /core-engineering:ce-plan's required free-text input — a stub cannot
      arm the skip).
  H3  Every lens named in the sidecar's `lenses` resolves to a persona file in
      the skill's `personas/` dir (catches the dangling "UX/design lens" class
      of reference — a lens the library never shipped).
  H4  Sidecar shape: schema_version == 1; `sections` is a non-empty object whose
      every value is one of {answered, open, disputed}; `lenses` is a list of
      strings; `open_questions` is an int >= 0.

ADVISORY checks (warnings only; never change the exit code — best-effort,
markdown-derived):
  A1  A named range exception (fewer than 2 lenses) carries a reason in the
      brief's "Lenses Applied" section.
  A2  Each durable noun in "Primary Journeys" has a management loop (find /
      return / edit / switch / manage) or is deferred to an Open Question.
  A3  The sidecar's `open_questions` count matches the "Open Questions" section.
  A4  Every required section slug appears in the sidecar's `sections` map.

Usage:
    brief-lint.py <brief.md>                 # sidecar defaults to <brief>.json
    brief-lint.py <brief.md> --sidecar p.json
    brief-lint.py <brief.md> --personas-dir <dir>   # default: ../personas
    brief-lint.py <brief.md> --json          # machine-readable result

Exit codes:
    0  PASS  — no hard failures (advisory warnings may still print)
    1  FAIL  — at least one hard well-formedness failure
    2  ERROR — inputs missing/unparseable; caller falls back to the manual
               approval self-attestation (loudly).

Stdlib-only (portability guarantee): runs with zero Claude Code present.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = 1
SECTION_STATES = {"answered", "open", "disputed"}
# The Project Description must stand alone as /core-engineering:ce-plan's input — a real one-to-two
# paragraph statement clears this; a stub or bare `<placeholder>` does not.
DESC_FLOOR = 120

# Canonical Brief-Template headings (ce-brief SKILL.md "Brief Template").
REQUIRED_HEADINGS = [
    "Raw Idea", "Lenses Applied", "Project Description", "Problem & Goals",
    "Users & Roles", "Primary Journeys", "Scope", "Success Criteria",
    "Technical Context", "Constraints & Ordering", "Known Risks & Pitfalls",
    "Assumptions", "Open Questions", "Decision Log",
]
LOOP_VERBS = ("find", "return", "edit", "switch", "manage", "list", "browse")
CREATE_VERBS = ("create", "save", "add", "new ", "accumulat")

HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PLACEHOLDER_RE = re.compile(r"^<[^>]*>$")


class BriefLintError(Exception):
    """Inputs cannot be loaded/parsed -> exit 2, caller falls back."""


def slugify(heading: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", heading.lower())).strip("-")


def parse_sections(md_text: str) -> dict:
    """Map heading text -> body (lines up to the next heading of any level)."""
    lines = md_text.splitlines()
    sections: dict = {}
    cur = None
    buf: list = []
    for ln in lines:
        m = HEADER_RE.match(ln)
        if m:
            if cur is not None:
                sections[cur] = "\n".join(buf).strip()
            cur = m.group(2).strip()
            buf = []
        elif cur is not None:
            buf.append(ln)
    if cur is not None:
        sections[cur] = "\n".join(buf).strip()
    return sections


def _content_len(body: str) -> int:
    """Length of real prose — drop blank lines and bare `<placeholder>` lines."""
    kept = [ln for ln in body.splitlines()
            if ln.strip() and not PLACEHOLDER_RE.match(ln.strip())]
    return len("\n".join(kept).strip())


def load_brief(path: Path) -> dict:
    if not path.is_file():
        raise BriefLintError(f"brief markdown not found: {path}")
    try:
        return parse_sections(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise BriefLintError(f"cannot read brief: {e}") from e


def load_sidecar(path: Path) -> dict:
    if not path.is_file():
        raise BriefLintError(
            f"brief.json sidecar not found: {path} "
            f"(ce-brief Stage 3 writes it alongside the markdown)")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise BriefLintError(f"sidecar is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise BriefLintError("sidecar must be a JSON object")
    return data


def check_sidecar(sidecar: dict, personas_dir: Path) -> tuple[list, list]:
    hard, advisory = [], []

    # H4 shape
    if sidecar.get("schema_version") != SCHEMA_VERSION:
        hard.append(f"H4 schema_version: expected {SCHEMA_VERSION}, "
                    f"found {sidecar.get('schema_version')!r}")
    sections = sidecar.get("sections")
    if not isinstance(sections, dict) or not sections:
        hard.append("H4 sections: must be a non-empty object {section-slug: state}")
        sections = {}
    for slug, state in sections.items():
        if state not in SECTION_STATES:
            hard.append(f"H4 sections[{slug}]: state {state!r} not in "
                        f"{sorted(SECTION_STATES)}")
    lenses = sidecar.get("lenses")
    if not isinstance(lenses, list) or not all(isinstance(x, str) for x in lenses):
        hard.append("H4 lenses: must be a list of strings")
        lenses = []
    oq = sidecar.get("open_questions")
    if not isinstance(oq, int) or isinstance(oq, bool) or oq < 0:
        hard.append("H4 open_questions: must be an integer >= 0")

    # H3 every applied lens resolves to a persona file
    for lens in lenses:
        name = lens.strip()
        if name.endswith(".md"):
            name = name[:-3]
        if not (personas_dir / f"{name}.md").is_file():
            hard.append(f"H3 lens {lens!r}: no personas/{name}.md in the library "
                        f"({personas_dir}) — a lens the library never shipped")

    # A1 named under-selection exception carries a reason (checked in check_brief,
    # which has the markdown; nothing to add here).
    return hard, advisory


def check_brief(md: dict, sidecar: dict) -> tuple[list, list]:
    hard, advisory = [], []
    present = {h.lower() for h in md}

    # H1 required headings
    for h in REQUIRED_HEADINGS:
        if h.lower() not in present:
            hard.append(f"H1 heading: required section '## {h}' is missing")

    # H2 Project Description self-sufficiency
    desc = next((b for h, b in md.items()
                 if h.lower() == "project description"), None)
    if desc is not None:
        n = _content_len(desc)
        if n < DESC_FLOOR:
            hard.append(f"H2 Project Description: only {n} chars of content "
                        f"(floor {DESC_FLOOR}) — it must stand alone as /core-engineering:ce-plan's "
                        f"required input, not a stub or bare placeholder")

    # A1 range exception carries a reason
    lenses = sidecar.get("lenses") if isinstance(sidecar.get("lenses"), list) else []
    if len(lenses) < 2:
        applied = md.get("Lenses Applied", "").lower()
        if not any(k in applied for k in
                   ("exception", "under-selection", "zero-lens", "fallback", "reason")):
            advisory.append("A1 Lenses Applied: fewer than 2 lenses but no named "
                            "range exception / reason stated (Stage 0.5 step 3)")

    # A2 durable-noun management loop
    journeys = md.get("Primary Journeys", "").lower()
    oq_text = md.get("Open Questions", "").lower()
    if any(v in journeys for v in CREATE_VERBS) \
            and not any(v in journeys for v in LOOP_VERBS) \
            and "loop" not in journeys and "loop" not in oq_text:
        advisory.append("A2 Primary Journeys: a durable noun is created/saved but "
                        "no management loop (find/return/edit/switch) or Open "
                        "Question about it is stated")

    # A3 open_questions count vs the section
    oq_section = md.get("Open Questions", "")
    listed = len([ln for ln in oq_section.splitlines()
                  if re.match(r"^\s*[-*]\s+\S", ln)])
    declared = sidecar.get("open_questions")
    if isinstance(declared, int) and not isinstance(declared, bool) and listed != declared:
        advisory.append(f"A3 open_questions: sidecar says {declared} but the "
                        f"Open Questions section lists {listed} bullet(s)")

    # A4 sidecar covers the required section slugs
    sec = sidecar.get("sections") if isinstance(sidecar.get("sections"), dict) else {}
    for h in REQUIRED_HEADINGS:
        if slugify(h) not in sec:
            advisory.append(f"A4 sidecar sections: missing slug '{slugify(h)}' "
                            f"(for '## {h}')")

    return hard, advisory


def resolve_personas_dir(args, brief_path: Path) -> Path:
    if args.personas_dir:
        return Path(args.personas_dir)
    # Default: the skill's own personas dir, next to this script's parent.
    return Path(__file__).resolve().parent.parent / "personas"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Well-formedness lint for a /core-engineering:ce-brief pair.")
    p.add_argument("brief", help="path to docs/briefs/<slug>.md")
    p.add_argument("--sidecar", help="path to the brief.json sidecar (default: <brief>.json)")
    p.add_argument("--personas-dir", help="persona library dir (default: ../personas)")
    p.add_argument("--json", action="store_true", help="emit a machine-readable JSON result")
    args = p.parse_args(argv)

    try:
        brief_path = Path(args.brief)
        sidecar_path = Path(args.sidecar) if args.sidecar else brief_path.with_suffix(".json")
        md = load_brief(brief_path)
        sidecar = load_sidecar(sidecar_path)
        personas_dir = resolve_personas_dir(args, brief_path)
        h1, a1 = check_sidecar(sidecar, personas_dir)
        h2, a2 = check_brief(md, sidecar)
        hard, advisory = h1 + h2, a1 + a2
    except BriefLintError as e:
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            print(f"brief-lint: ERROR — could not run: {e}", file=sys.stderr)
            print("  -> fall back to the manual approval self-attestation (loudly).",
                  file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — never leak a traceback as a hard FAIL
        if args.json:
            print(json.dumps({"status": "error",
                              "message": f"unexpected: {type(e).__name__}: {e}"}))
        else:
            print(f"brief-lint: ERROR — unexpected failure "
                  f"({type(e).__name__}): {e}", file=sys.stderr)
        return 2

    status = "fail" if hard else "pass"
    if args.json:
        print(json.dumps({
            "status": status,
            "brief": str(brief_path),
            "sidecar": str(sidecar_path),
            "sections": len(sidecar.get("sections") or {}),
            "lenses": sidecar.get("lenses") if isinstance(sidecar.get("lenses"), list) else [],
            "open_questions": sidecar.get("open_questions"),
            "hard_failures": hard,
            "advisory": advisory,
        }, indent=2))
        return 1 if hard else 0

    print(f"brief-lint: {brief_path}")
    print(f"  sidecar: {sidecar_path} · {len(sidecar.get('sections') or {})} section(s)")
    if hard:
        print(f"\n  FAIL — {len(hard)} hard well-formedness failure(s):")
        for f in hard:
            print(f"    x {f}")
    else:
        print("\n  PASS — sidecar is well-formed; the Brief -> Plan skip map is computable.")
    if advisory:
        print(f"\n  advisory ({len(advisory)} — review, non-blocking):")
        for a in advisory:
            print(f"    ! {a}")
    print()
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
