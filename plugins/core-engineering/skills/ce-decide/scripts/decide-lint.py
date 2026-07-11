#!/usr/bin/env python3
"""decide-lint.py — the Decision-Honesty gate for /ce-decide.

`decide` is a VERDICT-RENDERING tool, on the ENGINEERING side of the line (unlike
/ce-idea-score, which renders a PRODUCT verdict; unlike /ce-market-scan, whose scan-lint.py
forbids verdicts via the Scope Lock — both ship in the companion `product-discovery` plugin). A recommendation among technical options is
permitted here; an *unaccountable* one is not. This external checker over the composed
scorecard enforces the **Decision-Honesty Contract**: the recommendation may be rendered,
but it may never rest on un-evidenced guesses dressed as measurement, let a fatal weakness
(an option that doesn't solve the problem, or breaks a hard constraint) hide behind a
strong average, weight the axes silently, or bury the per-option shape behind one composite.

The contract rests on six devices this lint checks the SHAPE of:
  1. evidence-tagged scores — every axis of every option carries measured/inferred/unknown;
  2. non-compensatory knockouts — Efficacy/Constraint-fit <= 3 must DISQUALIFY that option,
     and a disqualified option may not be the Adopt / Adopt-with-mitigations pick;
  3. each composite never travels alone — weights + per-option vector + disclaimer present;
  4. the weights are derived from the situation, in the open — a `## Situation` section
     that names the weighting, and exactly seven axis weights that sum to ~1;
  5. a falsifiable kill-condition — a `DEAD IF <observable>` line, not a failure story;
  6. an on-list recommendation — Adopt / Adopt-with-mitigations / Spike-first / Reject.

It parses the Gates section and the Weights line PER ITEM (per option / per axis) rather
than scanning the whole section for a stray keyword, and it reads negation-aware (a Gates
line that says "not disqualified" does NOT satisfy the knockout-application check), so a
buried or denied knockout cannot slip through and a paraphrased Adopt pick cannot skip the
buy-back guard.

HONEST FRAMING (per the framework's score-lint.py / scan-lint.py / patch-lint.py
precedent): the lint checks SHAPE, not TRUTH. It cannot verify that a score is correct,
that the option set is complete, that the weighting matches the situation, or that a
DEAD-IF is genuinely falsifiable. Those are human judgments. A clean PASS means the
recommendation is *accountable*, not *right*.

HARD checks (a FAIL -> exit 1; a Decision-Honesty violation to fix before the call stands):
  D1  the required sections are present, and every option's Scorecard names all seven axes.
  D1b at least two option blocks (### ...) under the Scorecard, or an affirmatively
      declared single-option case.
  D2  every axis of every option carries an integer score in 1..10.
  D3  every axis of every option carries an evidence tag (measured | inferred | unknown).
  D4  the Gates section states a knockout result for each option; AND every option with
      Efficacy <= 3 or Constraint-fit <= 3 is affirmatively DISQUALIFIED there (the
      knockout was actually applied, not averaged away or denied).
  D5  a falsifiable `DEAD IF <observable>` kill-condition line is present.
  D6  the Weighted Verdict shows a Weights line, a Vector line, a Composite line, and the
      standing disclaimer; AND the Weights line carries all seven axis weights summing
      to ~1.0 (no silent / non-normalized weighting).
  D7  the Recommendation is exactly one of Adopt / Adopt-with-mitigations / Spike-first / Reject.
  D8  an Adopt / Adopt-with-mitigations recommendation names exactly one scorecard option,
      and that option is NOT disqualified (a knockout that fired cannot be bought back).
  D9  a `## Situation` section is present and names the weighting derivation (no silent weighting).

ADVISORY (warnings only; never change the exit code):
  A1  an axis tagged `unknown` — the score rests on no evidence; down-weight it.
  A2  an Adopt recommendation whose chosen option has >= 2 `unknown` axes — thin evidence.
  A3  `reasoned` evidence mode with any `measured` score tag — a measured score needs a number/source.

Exit codes (identical contract to score-lint / scan-lint / spec-lint / patch-lint):
    0  PASS  — no Decision-Honesty violations (advisory warnings may still print)
    1  FAIL  — at least one violation; the recommendation must be fixed before it stands
    2  ERROR — the artifact is missing/unreadable; the caller falls back to the manual
               Decision-Honesty checklist (loudly)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Canonical axes — matched case-insensitively on each option's Scorecard row first cell
# and on the Weights line. Patterns are chosen unique: "constraint" (not "fit", which
# "Constraint-fit" also contains) anchors Constraint-fit, and "reuse" anchors Fit & reuse.
AXES = [
    ("Efficacy", re.compile(r"efficacy", re.I)),
    ("Constraint-fit", re.compile(r"constraint", re.I)),
    ("Reversibility", re.compile(r"reversibilit", re.I)),
    ("Time-to-relief", re.compile(r"time.to.relief", re.I)),
    ("Build cost", re.compile(r"build\s*cost", re.I)),
    ("Operability", re.compile(r"operabilit", re.I)),
    ("Fit & reuse", re.compile(r"reuse", re.I)),
]
KNOCKOUT_AXES = {"Efficacy", "Constraint-fit"}

EVIDENCE_STATES = ("measured", "inferred", "unknown")
# Anchored: the tag must LEAD the Evidence cell, so "not measured anywhere" is rejected.
EVIDENCE_LEAD = re.compile(r"^\s*(measured|inferred|unknown)\b", re.I)

# The fixed recommendation set. Order matters: match the hyphenated form before bare
# "Adopt" so "Adopt-with-mitigations" is not mis-read as "Adopt".
RECOMMENDATIONS = ["Adopt-with-mitigations", "Adopt", "Spike-first", "Reject"]
REC_RES = [(r, re.compile(r"\b" + re.escape(r) + r"\b", re.I)) for r in RECOMMENDATIONS]
PURSUE_CLASS = {"Adopt", "Adopt-with-mitigations"}

DEAD_IF = re.compile(r"\bdead\s+if\b", re.I)
DISQUALIFIED = re.compile(r"\bdisqualif\w*\b", re.I)
DEAD_RESULT = re.compile(r"\bdead\b", re.I)
PASS_RESULT = re.compile(r"\bpass\w*\b", re.I)
# A negator anywhere earlier on the same line flips a result/declaration token to non-affirmative.
NEGATOR = re.compile(r"\b(no|not|none|never|without|cannot|can't|n't|isn't|aren't|neither|nor)\b", re.I)
# A declared single-option case (the lint accepts < 2 options only when this is affirmed).
SINGLE_OPTION = re.compile(r"single[\s-]option|only one (?:viable |genuine )?option|one viable option", re.I)

# Weighted-Verdict shape lines.
WEIGHTS_LINE = re.compile(r"^\s*weights?\s*:", re.I)
VECTOR_LINE = re.compile(r"^\s*vector\b", re.I)
COMPOSITE_LINE = re.compile(r"^\s*composite\b", re.I)
# Stable fragment of the standing disclaimer ("...not a fact; read the vector...").
DISCLAIMER = re.compile(r"not\s+a\s+fact", re.I)

EVIDENCE_MODE = re.compile(r"evidence-mode\s*:\s*(measured|reasoned)", re.I)
WEIGHT_WORD = re.compile(r"\bweight", re.I)
OPTION_KEY = re.compile(r"option\s+([A-Za-z0-9]+)", re.I)

SECTIONS = [
    "Decision", "Situation", "Options", "Scorecard", "Gates",
    "Kill-Condition", "Weighted Verdict", "Recommendation",
]


class DecideLintError(Exception):
    """The artifact cannot be loaded -> exit 2, caller falls back to the manual checklist."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
# load/section_body and the emit/main scaffolding mirror score-lint.py / scan-lint.py;
# each gate stays stdlib-only and self-contained (the portability guarantee).
# ---------------------------------------------------------------------------

def load(path: Path) -> str:
    if not path.is_file():
        raise DecideLintError(f"decide artifact not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError) as e:  # ValueError covers UnicodeDecodeError
        raise DecideLintError(f"could not read {path}: {e}") from e


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


def option_blocks(scorecard: str) -> list[tuple[str, str]]:
    """Split a Scorecard section into per-option (### <label>) blocks -> [(label, body)]."""
    blocks: list[tuple[str, str]] = []
    sub = re.compile(r"^###\s+(.*\S)\s*$")
    label: str | None = None
    cur: list[str] = []
    for ln in scorecard.splitlines():
        m = sub.match(ln)
        if m:
            if label is not None:
                blocks.append((label, "\n".join(cur)))
            label, cur = m.group(1).strip(), []
        elif label is not None:
            cur.append(ln)
    if label is not None:
        blocks.append((label, "\n".join(cur)))
    return blocks


def table_rows(body: str) -> list[list[str]]:
    """Parse markdown table rows (pipe-delimited), skipping the header and `---|---`."""
    rows = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue
        rows.append(cells)
    return rows


def axis_rows(block_body: str) -> dict[str, list[str]]:
    """Map each canonical axis -> its row cells within one option block (first match wins)."""
    found: dict[str, list[str]] = {}
    rows = table_rows(block_body)
    for canonical, pat in AXES:
        for cells in rows:
            if cells and pat.search(cells[0]):
                found[canonical] = cells
                break
    return found


def score_int(cell: str) -> int | None:
    """The score must LEAD the cell, so 'see note 9' or a trailing reference is not read."""
    m = re.match(r"\s*(\d{1,3})\b", cell)
    return int(m.group(1)) if m else None


def option_key(label: str) -> str:
    """A short matchable key for an option label, e.g. 'Option A — foo' -> 'option a'."""
    m = OPTION_KEY.search(label)
    if m:
        return f"option {m.group(1).lower()}"
    return re.split(r"[—-]", label, 1)[0].strip().lower()


def option_matchers(label: str) -> list[re.Pattern]:
    """Word-boundary patterns that identify this option in prose (key + descriptive name).
    Word boundaries stop 'option a' from matching inside 'option alpha'."""
    pats = [re.compile(r"\b" + re.escape(option_key(label)) + r"\b", re.I)]
    if "—" in label:
        name = label.split("—", 1)[1].strip().lower()
        if len(name) >= 4:
            pats.append(re.compile(r"\b" + re.escape(name), re.I))
    return pats


def names_option(text: str, label: str) -> bool:
    return any(p.search(text) for p in option_matchers(label))


def affirmative(text: str, token_re: re.Pattern) -> bool:
    """True if token_re matches somewhere NOT preceded by a negator earlier on its line.
    So 'DISQUALIFIED' counts, but 'not disqualified' / 'neither is disqualified' do not."""
    for m in token_re.finditer(text):
        ls = text.rfind("\n", 0, m.start()) + 1
        if not NEGATOR.search(text[ls:m.start()]):
            return True
    return False


def gate_status(text: str) -> str | None:
    """Read an option's Gates line(s) -> 'dead' | 'disq' | 'pass' | None (dead/disq dominate)."""
    if affirmative(text, DEAD_RESULT):
        return "dead"
    if affirmative(text, DISQUALIFIED):
        return "disq"
    if affirmative(text, PASS_RESULT):
        return "pass"
    return None


def parse_weights(weights_line: str) -> dict[str, float]:
    """Extract '<axis> <number>' weights bound to each canonical axis name (int or decimal).
    Only axis-bound numbers count, so a stray decimal elsewhere on the line is ignored."""
    weights: dict[str, float] = {}
    for canonical, pat in AXES:
        m = re.search(pat.pattern + r"[^0-9]*(\d+(?:\.\d+)?|\.\d+)", weights_line, re.I)
        if m:
            weights[canonical] = float(m.group(1))
    return weights


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
    situation = sections.get("Situation")
    options_sec = sections.get("Options")

    # D1 — required sections present
    for t in SECTIONS:
        if sections[t] is None:
            hard.append(f"D1: missing `## {t}` section")

    # D1b + per-option parse
    blocks = option_blocks(scorecard) if scorecard is not None else []
    declared_single = (
        (scorecard is not None and affirmative(scorecard, SINGLE_OPTION))
        or (options_sec is not None and affirmative(options_sec, SINGLE_OPTION))
    )
    if scorecard is not None and len(blocks) < 2 and not declared_single:
        hard.append(
            f"D1b: Scorecard has {len(blocks)} option block(s) (`### …`); need >= 2, "
            f"or an affirmative single-option declaration (do not manufacture a strawman)"
        )

    # D2 + D3 — per option, every axis scored 1..10 and evidence-tagged
    option_scores: dict[str, dict[str, int]] = {}
    option_unknowns: dict[str, int] = {}
    for label, body in blocks:
        rows = axis_rows(body)
        scores: dict[str, int] = {}
        unknowns = 0
        for canonical, _ in AXES:
            if canonical not in rows:
                hard.append(f"D1: `{label}` Scorecard is missing the `{canonical}` axis row")
                continue
            cells = rows[canonical]
            score = score_int(cells[1]) if len(cells) > 1 else None
            if score is None:
                hard.append(f"D2: `{label}` / `{canonical}` has no integer score at the start of the Score cell")
            elif not (1 <= score <= 10):
                hard.append(f"D2: `{label}` / `{canonical}` score {score} is outside 1..10")
            else:
                scores[canonical] = score
            tag_cell = cells[2] if len(cells) > 2 else ""
            m = EVIDENCE_LEAD.match(tag_cell)
            if not m:
                hard.append(
                    f"D3: `{label}` / `{canonical}` Evidence cell does not lead with a tag "
                    f"({' | '.join(EVIDENCE_STATES)}) — an untagged score is inadmissible"
                )
            elif m.group(1).lower() == "unknown":
                unknowns += 1
                advisory.append(f"A1: `{label}` / `{canonical}` is tagged `unknown` — down-weight it.")
        option_scores[label] = scores
        option_unknowns[label] = unknowns

    # D4 — knockouts evaluated AND actually applied, PER OPTION (negation-aware)
    score_disq = {
        label for label, scores in option_scores.items()
        if any(scores.get(a, 99) <= 3 for a in KNOCKOUT_AXES)
    }
    gate_disq: set[str] = set()
    if gates is not None:
        glines = gates.splitlines()
        for label in option_scores:
            owned = "\n".join(ln for ln in glines if names_option(ln, label))
            status = gate_status(owned) if owned.strip() else None
            if status in ("disq", "dead"):
                gate_disq.add(label)
            if status is None:
                hard.append(
                    f"D4: `Gates` states no knockout result (PASS / DISQUALIFIED / DEAD) for `{label}`"
                )
            elif label in score_disq and status not in ("disq", "dead"):
                hard.append(
                    f"D4: `{label}` has a knockout axis <= 3 but `Gates` does not affirmatively "
                    f"DISQUALIFY it (it cannot be averaged away or denied)."
                )

    # D5 — a falsifiable kill-condition
    kill = sections.get("Kill-Condition")
    if kill is not None and not DEAD_IF.search(kill):
        hard.append("D5: `Kill-Condition` has no `DEAD IF <observable>` line (a story is not a test)")
    elif kill is None and not DEAD_IF.search(md):
        hard.append("D5: no `DEAD IF <observable>` kill-condition anywhere in the artifact")

    # D6 — the composite never travels alone, and the seven axis weights sum to ~1
    if verdict is not None:
        vlines = verdict.splitlines()
        weights_lines = [ln for ln in vlines if WEIGHTS_LINE.match(ln)]
        if not weights_lines:
            hard.append("D6: `Weighted Verdict` has no `Weights:` line")
        if not any(VECTOR_LINE.match(ln) for ln in vlines):
            hard.append("D6: `Weighted Verdict` has no `Vector` line — the per-option shape must show")
        if not any(COMPOSITE_LINE.match(ln) for ln in vlines):
            hard.append("D6: `Weighted Verdict` has no `Composite` line")
        if not DISCLAIMER.search(verdict):
            hard.append('D6: `Weighted Verdict` is missing the standing disclaimer ("...not a fact...")')
        if weights_lines:
            w = parse_weights(weights_lines[0])
            if len(w) < len(AXES):
                missing = [a for a, _ in AXES if a not in w]
                hard.append(
                    f"D6: the `Weights` line is missing weights for {', '.join(missing)} — "
                    f"all seven axes must carry an explicit weight (no silent weighting)"
                )
            elif not (0.97 <= sum(w.values()) <= 1.03):
                hard.append(
                    f"D6: the seven axis weights sum to {sum(w.values()):.2f}, not ~1.0 — "
                    f"the weighting must be a normalized distribution"
                )

    # D7 — recommendation on-list
    chosen = None
    if rec is not None:
        for name, pat in REC_RES:
            if pat.search(rec):
                chosen = name
                break
        if chosen is None:
            hard.append(f"D7: `Recommendation` is not one of {' / '.join(RECOMMENDATIONS)}")

    # D8 — an Adopt-class recommendation names exactly one option, not a disqualified one
    buyback = score_disq | gate_disq
    chosen_option_label = None
    if rec is not None and chosen in PURSUE_CLASS:
        named = [label for label in option_scores if names_option(rec, label)]
        if not named:
            hard.append(
                f"D8: `{chosen}` recommendation names no scorecard option — "
                f"name the chosen option verbatim so the buy-back guard can run"
            )
        elif len(named) > 1:
            hard.append(
                f"D8: `{chosen}` recommendation names more than one option ({', '.join(named)}) — "
                f"an Adopt-class call must pick exactly one"
            )
        else:
            chosen_option_label = named[0]
            if chosen_option_label in buyback:
                hard.append(
                    f"D8: `{chosen_option_label}` is disqualified (a knockout fired) but recommended "
                    f"`{chosen}` — a fired knockout cannot be bought back; use Spike-first / Reject "
                    f"or pick a qualifying option."
                )
                chosen_option_label = None

    # D9 — the situation derives the weighting, in the open
    if situation is not None and not WEIGHT_WORD.search(situation):
        hard.append(
            "D9: `## Situation` does not mention the weighting — the weights must be "
            "derived from the situation in the open (no silent weighting)"
        )

    # A2 — thin evidence for an Adopt
    if chosen == "Adopt" and chosen_option_label is not None:
        if option_unknowns.get(chosen_option_label, 0) >= 2:
            advisory.append(
                f"A2: `Adopt` of `{chosen_option_label}` with "
                f"{option_unknowns[chosen_option_label]} `unknown` axes — thin evidence; "
                f"consider Spike-first."
            )

    # A3 — reasoned mode must not claim a measured score
    mode_m = EVIDENCE_MODE.search(md)
    if mode_m and mode_m.group(1).lower() == "reasoned":
        if any(
            len(cells) > 2 and EVIDENCE_LEAD.match(cells[2]) and cells[2].lower().lstrip().startswith("measured")
            for _, body in blocks for cells in axis_rows(body).values()
        ):
            advisory.append("A3: `reasoned` mode but a score is tagged `measured` — a measured score needs a number/source.")

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
    print(f"decide-lint: {path}")
    if hard:
        print(f"\n  FAIL — {len(hard)} Decision-Honesty violation(s):")
        for f in hard:
            print(f"    x {f}")
    else:
        print("\n  PASS — the recommendation is accountable (tagged, gated, weighted in the open). (Not a check that it is RIGHT.)")
    if advisory:
        print(f"\n  advisory ({len(advisory)} — review, non-blocking):")
        for a in advisory:
            print(f"    ! {a}")
    print()
    return 1 if hard else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Decision-Honesty gate for a /ce-decide artifact.")
    p.add_argument("artifact", help="the composed decide markdown file (docs/decisions/<slug>/<date>.md)")
    p.add_argument("--json", action="store_true", help="machine-readable result")
    args = p.parse_args(argv)

    try:
        md = load(Path(args.artifact))
    except DecideLintError as e:
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            print(f"decide-lint: ERROR — could not run: {e}", file=sys.stderr)
            print("  -> fall back to the manual Decision-Honesty checklist (loudly).", file=sys.stderr)
        return 2

    hard, advisory = run_checks(md)
    return emit(Path(args.artifact), hard, advisory, args.json)


if __name__ == "__main__":
    sys.exit(main())
