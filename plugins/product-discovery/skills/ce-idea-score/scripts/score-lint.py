#!/usr/bin/env python3
"""score-lint.py — the Verdict-Honesty gate for /product-discovery:ce-idea-score.

`ce-idea-score` is a VERDICT-RENDERING tool (unlike /product-discovery:ce-market-scan, whose scan-lint.py
forbids verdicts via the Scope Lock). A verdict is permitted here; an *unaccountable*
verdict is not. This external checker over the composed scorecard enforces the
**Verdict-Honesty Contract**: the verdict may be rendered, but it may never rest on
un-evidenced guesses dressed as measurement, let a fatal weakness hide behind a strong
average, or bury the per-axis shape behind one composite number.

The contract rests on five devices this lint checks the shape of:
  1. evidence-tagged scores — every axis carries confirmed/suspected/unknown;
  2. non-compensatory knockouts — Feasibility/Distribution <= 3 must DISQUALIFY, and a
     disqualified idea may not be recommended Pursue / Pursue-with-changes;
  3. the composite never travels alone — weights + per-axis vector + disclaimer present;
  4. a falsifiable kill-condition — a `DEAD IF <observable>` line, not a failure story;
  5. an on-list recommendation — Pursue / Pursue-with-changes / Park / Drop.

HONEST FRAMING (per the framework's scan-lint.py / patch-lint.py precedent): the lint
checks SHAPE, not TRUTH. It cannot verify that a score is correct, that a cited source is
relevant, that a named moat is real, or that a DEAD-IF is genuinely falsifiable. Those are
human judgments. A clean PASS means the verdict is *accountable*, not *right*.

HARD checks (a FAIL -> exit 1; a Verdict-Honesty violation to fix before the verdict stands):
  H1  the Scorecard + Gates + Weighted Verdict + Recommendation sections are present,
      and the Scorecard names all seven axes.
  H2  every axis carries an integer score in 1..10.
  H3  every axis carries an evidence tag (confirmed | suspected | unknown).
  H4  the Gates section states the knockout-floor result; AND if Feasibility <= 3 or
      Distribution <= 3 in the Scorecard, the Gates section says DISQUALIFIED (the
      knockout was actually applied, not averaged away).
  H5  a falsifiable `DEAD IF <observable>` kill-condition line is present.
  H6  the Weighted Verdict shows a Weights line, a Vector line, a Composite line, and the
      standing disclaimer (the composite never travels without its shape).
  H7  the Recommendation is exactly one of Pursue / Pursue-with-changes / Park / Drop.
  H8  a disqualified idea is NOT recommended Pursue or Pursue-with-changes — disqualified
      meaning either a breached knockout floor (Gates says DISQUALIFIED) OR a fired binary
      kill-condition (an affirmative `DEAD` in the Gates section). A fired gate cannot be
      bought back by the composite (the contract's "regardless of the composite" promise).

ADVISORY (warnings only; never change the exit code):
  A1  an axis tagged `unknown` — the score rests on no evidence; down-weight it.
  A2  a Pursue recommendation while >= 2 axes are `unknown` — thin evidence for a Pursue.
  A3  `judgment-only` evidence mode with any `confirmed` tag — confirmed needs a source.

Exit codes (identical contract to scan-lint / spec-lint / patch-lint):
    0  PASS  — no Verdict-Honesty violations (advisory warnings may still print)
    1  FAIL  — at least one violation; the verdict must be fixed before it stands
    2  ERROR — the artifact is missing/unreadable; the caller falls back to the manual
               Verdict-Honesty checklist (loudly)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Canonical axes — matched case-insensitively on the Scorecard row's first cell.
AXES = [
    ("Market demand", re.compile(r"market\s+demand", re.I)),
    ("Distribution", re.compile(r"distribution", re.I)),
    ("Feasibility", re.compile(r"feasibility", re.I)),
    ("Differentiation", re.compile(r"differentiation", re.I)),
    ("Defensibility", re.compile(r"defensibility", re.I)),
    ("Revenue potential", re.compile(r"revenue", re.I)),
    ("Timing", re.compile(r"timing", re.I)),
]
KNOCKOUT_AXES = {"Feasibility", "Distribution"}

EVIDENCE_STATES = ("confirmed", "suspected", "unknown")
EVIDENCE_RE = re.compile(r"\b(confirmed|suspected|unknown)\b", re.I)

# The fixed recommendation set. Order matters: match the hyphenated form before the bare
# "Pursue" so "Pursue-with-changes" is not mis-read as "Pursue".
RECOMMENDATIONS = ["Pursue-with-changes", "Pursue", "Park", "Drop"]
REC_RES = [(r, re.compile(r"\b" + re.escape(r) + r"\b", re.I)) for r in RECOMMENDATIONS]

DEAD_IF = re.compile(r"\bdead\s+if\b", re.I)
DISQUALIFIED = re.compile(r"\bdisqualified\b", re.I)
# A FIRED binary kill-condition appears in the Gates section as an affirmative `DEAD`
# result (e.g. "requires a regulated license — DEAD"). The Verdict-Honesty contract says a
# fired binary kill forces Drop/Park "regardless of the composite", so it must disqualify
# just like a breached knockout floor (mirrors decide-lint's gate_status() DEAD scan). Two
# things are NOT a fire and must be excluded: the rubric phrasing "(DEAD if any true)" — a
# `DEAD if` conditional — and a negated status like "not DEAD" / "no kill fired". Negation
# is checked only IMMEDIATELY before the token, not anywhere on the line, so a kill
# *description* that itself contains "cannot"/"not" (e.g. "...the team cannot get — DEAD")
# still fires — the dangerous direction for a verdict-honesty gate is a missed fire.
DEAD_RESULT = re.compile(r"\bdead\b", re.I)
NEG_BEFORE = re.compile(r"\b(no|not|never|none|isn'?t|aren'?t|n'?t|un-?fired|non-?fired)\W*$", re.I)


def gates_disqualified(gates: str | None) -> bool:
    """Whether the Gates section bars the verdict from Pursue — a fired knockout floor
    (DISQUALIFIED) OR a fired binary kill-condition (an affirmative DEAD result). The
    `DEAD if any true` rubric and a negated `not DEAD` status do not count as a fire."""
    if not gates:
        return False
    if DISQUALIFIED.search(gates):
        return True
    for m in DEAD_RESULT.finditer(gates):
        if re.match(r"\s+if\b", gates[m.end():m.end() + 4], re.I):
            continue  # "DEAD if any true" — the rubric, not a result
        before = gates[gates.rfind("\n", 0, m.start()) + 1 : m.start()]
        if NEG_BEFORE.search(before):
            continue  # "not DEAD" / "no ... DEAD"
        return True
    return False

# Weighted-Verdict shape lines.
WEIGHTS_LINE = re.compile(r"^\s*weights?\s*:", re.I)
VECTOR_LINE = re.compile(r"^\s*vector\s*:", re.I)
COMPOSITE_LINE = re.compile(r"^\s*composite\s*:", re.I)
# Stable fragment of the standing disclaimer ("...not a fact; read the vector...").
DISCLAIMER = re.compile(r"not\s+a\s+fact", re.I)

EVIDENCE_MODE = re.compile(r"evidence-mode\s*:\s*(researched|judgment-only)", re.I)

SECTIONS = ["Scorecard", "Gates", "Kill-Condition", "Weighted Verdict", "Recommendation"]


class ScoreLintError(Exception):
    """The artifact cannot be loaded -> exit 2, caller falls back to the manual checklist."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
# load/section_body and the emit/main scaffolding are MIRRORED in scan-lint.py
# (market-scan); each gate stays stdlib-only and self-contained (the
# portability guarantee), so a fix to this shared shape must be applied to
# both copies by hand.
# ---------------------------------------------------------------------------

def load(path: Path) -> str:
    if not path.is_file():
        raise ScoreLintError(f"idea-score artifact not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise ScoreLintError(f"could not read {path}: {e}") from e


def section_body(md: str, title: str) -> str | None:
    """Return the text under `## <title>` up to the next `## ` header, or None if absent.
    Matches the title at the start of the header line, tolerating a trailing parenthetical."""
    lines = md.splitlines()
    head = re.compile(r"^##\s+" + re.escape(title) + r"\b", re.I)
    any_h2 = re.compile(r"^##\s+\S")
    i, n = 0, len(lines)
    while i < n:
        if head.match(lines[i]):
            j = i + 1
            while j < n and not any_h2.match(lines[j]):
                j += 1
            return "\n".join(lines[i + 1:j])
        i += 1
    return None


def table_rows(body: str) -> list[list[str]]:
    """Parse markdown table rows (pipe-delimited) under a section, skipping the header and
    the `---|---` separator. Each row -> list of trimmed cell strings."""
    rows = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        # skip a separator row like | --- | --- |
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue
        rows.append(cells)
    return rows


def axis_rows(scorecard: str) -> dict[str, list[str]]:
    """Map each canonical axis -> its Scorecard row cells (first match wins)."""
    found: dict[str, list[str]] = {}
    rows = table_rows(scorecard)
    for canonical, pat in AXES:
        for cells in rows:
            if cells and pat.search(cells[0]):
                found[canonical] = cells
                break
    return found


def first_int(cell: str) -> int | None:
    m = re.search(r"\b(\d{1,2})\b", cell)
    if not m:
        return None
    return int(m.group(1))


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def run_checks(md: str) -> tuple[list, list]:
    hard, advisory = [], []

    sections = {t: section_body(md, t) for t in SECTIONS}
    scorecard = sections.get("Scorecard")
    gates = sections.get("Gates")
    verdict = sections.get("Weighted Verdict")
    rec = sections.get("Recommendation")

    # H1 — required sections present
    for t in SECTIONS:
        if sections[t] is None:
            hard.append(f"H1: missing `## {t}` section")

    rows: dict[str, list[str]] = {}
    if scorecard is not None:
        rows = axis_rows(scorecard)
        for canonical, _ in AXES:
            if canonical not in rows:
                hard.append(f"H1: Scorecard is missing the `{canonical}` axis row")

    # H2 + H3 — every axis scored 1..10 and evidence-tagged
    scores: dict[str, int] = {}
    for canonical, cells in rows.items():
        score = first_int(cells[1]) if len(cells) > 1 else None
        if score is None:
            hard.append(f"H2: `{canonical}` has no numeric score")
        elif not (1 <= score <= 10):
            hard.append(f"H2: `{canonical}` score {score} is outside 1..10")
        else:
            scores[canonical] = score
        tag_cell = cells[2] if len(cells) > 2 else ""
        m = EVIDENCE_RE.search(tag_cell)
        if not m:
            hard.append(
                f"H3: `{canonical}` carries no evidence tag "
                f"({' | '.join(EVIDENCE_STATES)}) — an untagged score is inadmissible"
            )
        elif m.group(1).lower() == "unknown":
            advisory.append(f"A1: `{canonical}` is tagged `unknown` — the score rests on no evidence; down-weight it.")

    # H4 — knockouts evaluated AND actually applied
    knockout_breached = any(
        canonical in scores and scores[canonical] <= 3 for canonical in KNOCKOUT_AXES
    )
    # H4 keys strictly on the floor signal: a breached floor must say DISQUALIFIED
    # specifically (a binary-kill DEAD is a different fire, handled by H8 below).
    floor_disqualified = gates is not None and bool(DISQUALIFIED.search(gates))
    if gates is not None and not re.search(r"\b(knockout|disqualif\w*|pass\w*)\b", gates, re.I):
        hard.append("H4: `Gates` does not state the knockout-floor result (PASS / DISQUALIFIED)")
    if knockout_breached and not floor_disqualified:
        low = [a for a in KNOCKOUT_AXES if scores.get(a, 99) <= 3]
        hard.append(
            f"H4: {', '.join(sorted(low))} <= 3 but `Gates` does not say DISQUALIFIED — "
            f"a knockout floor was breached and not applied (it cannot be averaged away)."
        )

    # H5 — a falsifiable kill-condition
    kill = section_body(md, "Kill-Condition")
    if kill is not None and not DEAD_IF.search(kill):
        hard.append("H5: `Kill-Condition` has no `DEAD IF <observable>` line (a story is not a test)")
    elif kill is None and not DEAD_IF.search(md):
        hard.append("H5: no `DEAD IF <observable>` kill-condition anywhere in the artifact")

    # H6 — the composite never travels alone
    if verdict is not None:
        vlines = verdict.splitlines()
        if not any(WEIGHTS_LINE.match(ln) for ln in vlines):
            hard.append("H6: `Weighted Verdict` has no `Weights:` line")
        if not any(VECTOR_LINE.match(ln) for ln in vlines):
            hard.append("H6: `Weighted Verdict` has no `Vector:` line — the per-axis shape must show")
        if not any(COMPOSITE_LINE.match(ln) for ln in vlines):
            hard.append("H6: `Weighted Verdict` has no `Composite:` line")
        if not DISCLAIMER.search(verdict):
            hard.append('H6: `Weighted Verdict` is missing the standing disclaimer ("...not a fact...")')

    # H7 — recommendation on-list
    chosen = None
    if rec is not None:
        for name, pat in REC_RES:
            if pat.search(rec):
                chosen = name
                break
        if chosen is None:
            hard.append(
                f"H7: `Recommendation` is not one of {' / '.join(RECOMMENDATIONS)}"
            )

    # H8 — a disqualified idea may not be Pursue / Pursue-with-changes. "Disqualified" here
    # is broader than the knockout floor: a fired binary kill-condition (an affirmative DEAD
    # in the Gates section) bars Pursue just the same — the contract's "regardless of the
    # composite" promise, which keying only on the DISQUALIFIED floor token used to miss.
    disqualified = gates_disqualified(gates)
    if disqualified and chosen in ("Pursue", "Pursue-with-changes"):
        hard.append(
            f"H8: idea is disqualified (a knockout floor or binary kill-condition fired) but "
            f"recommended `{chosen}` — a fired gate cannot be bought back; use Drop or Park."
        )

    # A2 — thin evidence for a Pursue
    unknown_count = sum(
        1 for canonical, cells in rows.items()
        if len(cells) > 2 and EVIDENCE_RE.search(cells[2]) and "unknown" in cells[2].lower()
    )
    if chosen == "Pursue" and unknown_count >= 2:
        advisory.append(f"A2: `Pursue` with {unknown_count} `unknown` axes — thin evidence for a Pursue; consider Park.")

    # A3 — judgment-only must not claim confirmed
    mode_m = EVIDENCE_MODE.search(md)
    if mode_m and mode_m.group(1).lower() == "judgment-only":
        if any(len(cells) > 2 and "confirmed" in cells[2].lower() for cells in rows.values()):
            advisory.append("A3: `judgment-only` mode but a score is tagged `confirmed` — confirmed needs a cited source.")

    return hard, advisory


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def emit(path: Path, hard: list, advisory: list, as_json: bool) -> int:
    status = "fail" if hard else "pass"
    if as_json:
        print(json.dumps({"status": status, "artifact": str(path),
                          "hard_failures": hard, "advisory": advisory}, indent=2))
        return 1 if hard else 0
    print(f"score-lint: {path}")
    if hard:
        print(f"\n  FAIL — {len(hard)} Verdict-Honesty violation(s):")
        for f in hard:
            print(f"    x {f}")
    else:
        print("\n  PASS — the verdict is accountable (tagged, gated, shaped). (Not a check that it is RIGHT.)")
    if advisory:
        print(f"\n  advisory ({len(advisory)} — review, non-blocking):")
        for a in advisory:
            print(f"    ! {a}")
    print()
    return 1 if hard else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Verdict-Honesty gate for an /product-discovery:ce-idea-score artifact.")
    p.add_argument("artifact", help="the composed idea-score markdown file (docs/idea-scores/<slug>/<date>.md)")
    p.add_argument("--json", action="store_true", help="machine-readable result")
    args = p.parse_args(argv)

    try:
        md = load(Path(args.artifact))
    except ScoreLintError as e:
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            print(f"score-lint: ERROR — could not run: {e}", file=sys.stderr)
            print("  -> fall back to the manual Verdict-Honesty checklist (loudly).", file=sys.stderr)
        return 2

    hard, advisory = run_checks(md)
    return emit(Path(args.artifact), hard, advisory, args.json)


if __name__ == "__main__":
    sys.exit(main())
