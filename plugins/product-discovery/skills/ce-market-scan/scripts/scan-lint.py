#!/usr/bin/env python3
"""scan-lint.py — the Scope Lock gate for /product-discovery:ce-market-scan's Stage 3.5.

Stage 3.5 ("Frame the Decision Space") assembles the scan's scattered findings into
three sections — **Strategic Tensions**, **Positioning Options**, **Load-Bearing
Unknowns** — that map the decision a reader faces *without ever collapsing it into a
verdict*. The thing that keeps that honest — that stops the tier becoming "a context
that talks itself into a recommendation" — is this external checker over the composed
artifact. It enforces the **Scope Lock**: the tier may map the decision space but may
never collapse it.

The verdict-impossibility is structural, resting on four composing devices this lint
checks the shape of:
  1. plurality + independence — >= 2 Positioning Options (no singular "do X" slot);
  2. symmetric kill-condition — every option carries its own evidenced death-condition
     (no option can be the unmarked "safe" one);
  3. no order / no valence — no rank/recommend/superlative lexicon, and the standing
     valence-disclaimer line is present (so "better-evidenced" can't read as "better bet");
  4. evidence-trace — every tension/option cites a Finding ID that resolves in the
     Findings Index (the tier cites the document's own evidence spine, coins no new claim).

HONEST FRAMING (per the framework's own patch-lint.py precedent): the no-verdict
lexicon check (H5/H6) is a **HIGH-RECALL, LOW-PRECISION backstop, NOT a proof** — a
verdict phrased in an idiom this grep does not list WILL slip past. The real guarantee
is the COMPOSITION of the structural checks (H2/H3/H4/H7/H8) plus the human, not the
verb list. A lexicon hit is a material finding the human adjudicates.

HARD checks (a FAIL -> exit 1; a Scope Lock violation the tier must fix before close):
  H1  the three tier sections + a Findings Index are present.
  H2  Positioning Options has >= 2 `### Option` blocks (the plurality floor).
  H3  every Option block has all three fields: an "Escapes the squeeze of", a
      "Load-bearing belief", and a "Kill-condition" line (symmetric kill-condition).
  H4  every Strategic Tension bullet cites >= 1 Finding ID (F<n>).
  H5  no verdict / recommendation lexicon in the tier's content lines.
  H6  no Load-Bearing Unknown is phrased as an imperative ("read…", "build…",
      "pick…") or carries a ranking superlative ("cheapest", "first", "most important") —
      unknowns are gaps to close, not steps to take, and are un-ordered.
  H7  every Finding ID referenced anywhere in the tier resolves in the Findings Index
      (no dangling evidence reference).
  H8  the standing valence-disclaimer line is present under Positioning Options.
  H9  the disposition record, if present, is human-stamped (`by human`) — the Stage-5
      close routes the human's choice; the tool may not record a disposition alone.

ADVISORY (warnings only; never change the exit code):
  A1  a Load-Bearing Unknown that cites no Finding ID (weaker evidence trace).
  A2  an unusually large option set (>5) — possible dilution of the framing.
  A3  fewer than two grounded options, but declared as a coverage limit — a
      Scope-Lock-honest thin-set exception (H2 fires only when undeclared).

Exit codes (identical contract to spec-lint / patch-lint):
    0  PASS  — no Scope Lock violations (advisory warnings may still print)
    1  FAIL  — at least one Scope Lock violation; the tier must fix before close
    2  ERROR — the artifact is missing/unreadable; the caller falls back to the manual
               Scope Lock checklist (loudly)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TIER_SECTIONS = ["Strategic Tensions", "Positioning Options", "Load-Bearing Unknowns"]
INDEX_SECTION = "Findings Index"

FINDING_REF = re.compile(r"\bF\d+\b")
# A Findings-Index line DEFINES the id that is its first token, tolerant of list
# markers / **bold** / table pipes / blockquote: "- **F1** = …", "| F1 | … |",
# "F1. …", "- F1 — …" all define F1 (captured in group 1).
INDEX_DEF = re.compile(r"^[\s>*_|()-]*(?:\*\*)?\s*(F\d+)\b")
OPTION_HEADER = re.compile(r"^#{3,4}\s+Option\b", re.I)
# Shared prefix of BOTH standing disclaimer lines (under Strategic Tensions and under
# Positioning Options) — intentional double duty. H8 enforces its presence only under
# Positioning Options; content_lines() skips any line carrying it.
VALENCE_LINE = "Evidence state describes grounding of the FRAMING"

# The Stage-5 disposition record. The close routes the HUMAN's pick; this stamp is the
# on-disk proof the tool did not decide. The Scope Lock binds the tool, not the human,
# so the choice text itself is NOT held to the no-verdict lexicon — only the stamp is.
DISPOSITION_SECTION = "Disposition"
BY_HUMAN = re.compile(r"\bby\s+human\b", re.I)

# Option field markers (case-insensitive, tolerate **bold**, punctuation, hyphen/space).
FIELD_ESCAPES = re.compile(r"escapes?\s+the\s+squeeze", re.I)
FIELD_BELIEF = re.compile(r"load[- ]?bearing belief", re.I)
FIELD_KILL = re.compile(r"kill[- ]?condition", re.I)

# The Scope-Lock-honest thin-set escape: when the findings ground fewer than two
# independent options, the tier must SAY SO on a STANDALONE declaration line (not as
# prose embedded inside an option), never present one as "the" option. Anchored to the
# line start so an ordinary "coverage limit" phrase inside a kill-condition can't smuggle
# the escape (M2). The skill's Stage 3.5.c emits one of these verbatim.
THIN_SET_DECL = re.compile(r"^\s*[-*>]?\s*(fewer than two grounded options|thin option set)\b", re.I)

# H5 — verdict / recommendation lexicon. Targets ASSERTIVE usage so it does NOT collide
# with the tier's own disclaimers ("NOT RANKED", "framing, not recommendation").
VERDICT_LEXICON = [
    re.compile(r"\b(we|i)\s+recommend\b", re.I),
    re.compile(r"\byou\s+should\b", re.I),
    re.compile(r"\bgo/?\s*no-?go\b", re.I),
    re.compile(r"\bthe\s+best\s+(option|bet|choice|position|positioning|path)\b", re.I),
    re.compile(r"\bbest\s+bet\b", re.I),
    re.compile(r"\bthe\s+answer\s+is\b", re.I),
    re.compile(r"\bpick\s+(this|that|option|the)\b", re.I),
    re.compile(r"\b(the\s+)?(clear\s+)?winner\b", re.I),
    re.compile(r"\bmost\s+promising\b", re.I),
    re.compile(r"\bstrongest\s+(option|position|bet)\b", re.I),
    re.compile(r"\bin\s+order\s+of\s+(merit|preference|strength|promise)\b", re.I),
    re.compile(r"\branked\s+by\b", re.I),
    re.compile(r"\b(our|my)\s+recommendation\b", re.I),
    # tightened so "clears the most common objection" (legitimate prose) does not fire (m1):
    re.compile(r"\bclears?\s+the\s+most\s+(kill-?conditions?|options?|tensions?|squeezes?|forces?|pressures?)\b", re.I),
    re.compile(r"\bthe\s+(safest|obvious)\s+(bet|choice|option)\b", re.I),
    # soft-recommendation idioms (m3 — recall improvement, consistent with high-recall posture):
    re.compile(r"\blean(?:ing)?\s+(toward|towards|into)\b", re.I),
    re.compile(r"\bthe\s+(obvious|natural|smart)\s+(play|choice|move|path|bet)\b", re.I),
    re.compile(r"\bgo\s+with\b", re.I),
    re.compile(r"\bthe\s+path\s+forward\b", re.I),
    re.compile(r"\bthe\s+safer?\s+(play|bet|choice)\b", re.I),
    # collapse-phrase: a covert "only one survives" / conditional verdict (M6 hardening):
    re.compile(r"\bonly\s+(survivor|surviving\s+option)\b", re.I),
    re.compile(r"\bthe\s+(only|sole)\s+(option|position)\s+(left|remaining|that\s+survives)\b", re.I),
    re.compile(r"\bif\s+(confirmed|true)\b.{0,40}\b(only|sole)\b", re.I),
]

# H6 — imperative-initial probes + ranking superlatives in Load-Bearing Unknowns.
# The verb must be followed by WHITESPACE then an object (a real imperative), so
# hyphenated noun openers idiomatic to this section — "Run-rate economics…",
# "Go-to-market motion…", "Start-up cost…", "Build-vs-buy…" — do NOT false-FAIL (M3).
IMPERATIVE_START = re.compile(
    r"^\s*([-*]|\d+\.)\s*(read|build|pick|choose|use|go|run|test|pivot|do|adopt|ship|"
    r"start|validate|prioriti[sz]e|focus)(?=\s+\S)",
    re.I,
)
RANK_SUPERLATIVE = re.compile(
    r"\b(cheapest|the\s+first\b|most\s+important|highest-?value|top\s+priority|"
    r"biggest|number\s+one|#1)\b",
    re.I,
)


class ScanLintError(Exception):
    """The artifact cannot be loaded -> exit 2, caller falls back to the manual checklist."""


# ---------------------------------------------------------------------------
# Parsing — load/section_body and the emit/main scaffolding are MIRRORED in
# score-lint.py (idea-score); each gate stays stdlib-only and self-contained
# (the portability guarantee), so a fix to this shared shape must be applied
# to both copies by hand.
# ---------------------------------------------------------------------------

def load(path: Path) -> str:
    if not path.is_file():
        raise ScanLintError(f"market-scan artifact not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise ScanLintError(f"could not read {path}: {e}") from e


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


def content_lines(body: str) -> list[str]:
    """Bullets / field lines, excluding headers, the standing disclaimer, and HTML
    comment blocks — single- AND multi-line (m2: a `we recommend …` buried inside a
    multi-line `<!-- … -->` must not reach the H5 lexicon scan)."""
    out = []
    in_comment = False
    for ln in body.splitlines():
        s = ln.strip()
        if in_comment:
            if "-->" in s:
                in_comment = False
            continue
        if s.startswith("<!--"):
            if "-->" not in s:
                in_comment = True
            continue
        if not s or s.startswith("#") or VALENCE_LINE in s:
            continue
        out.append(ln)
    return out


def option_blocks(body: str) -> list[list[str]]:
    """Split the Positioning Options body into per-option blocks at `### Option` headers."""
    blocks, cur = [], None
    for ln in body.splitlines():
        if OPTION_HEADER.match(ln):
            cur = []
            blocks.append(cur)
        elif cur is not None:
            cur.append(ln)
    return blocks


RULE = re.compile(r"^\s*([-*_])\1{2,}\s*$")          # --- / *** / ___ horizontal rules
BULLET = re.compile(r"^\s*([-*]|\d+\.)\s+\S")          # "- x", "* x", "1. x" (not a rule)


def bullets(body: str) -> list[str]:
    """List items (`-`, `*`, or `1.`-numbered), excluding horizontal-rule separators so
    a `---` between sections is not miscounted as a finding-less bullet (M4/V1)."""
    return [ln for ln in body.splitlines() if BULLET.match(ln) and not RULE.match(ln)]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def run_checks(md: str) -> tuple[list, list]:
    hard, advisory = [], []

    sections = {t: section_body(md, t) for t in TIER_SECTIONS}
    index_body = section_body(md, INDEX_SECTION)

    # H1 — presence
    for t in TIER_SECTIONS:
        if sections[t] is None:
            hard.append(f"H1: missing tier section `## {t}` (Stage 3.5 did not run, or was dropped)")
    if index_body is None:
        hard.append(f"H1: missing `## {INDEX_SECTION}` — Finding IDs cannot be resolved (Stage 3.5.a)")

    defined: set[str] = set()
    if index_body is not None:
        defined = {m for ln in index_body.splitlines() for m in [_first_def(ln)] if m}

    tensions = sections.get("Strategic Tensions")
    options = sections.get("Positioning Options")
    unknowns = sections.get("Load-Bearing Unknowns")

    # H4 — every tension bullet cites >= 1 Finding ID
    if tensions is not None:
        tb = bullets(tensions)
        if not tb:
            hard.append("H4: `Strategic Tensions` has no tension bullets")
        for b in tb:
            if not FINDING_REF.search(b):
                hard.append(f"H4: tension cites no Finding ID: `{b.strip()[:90]}`")

    # H2 + H3 — plurality + symmetric kill-condition
    if options is not None:
        blocks = option_blocks(options)
        thin_declared = any(THIN_SET_DECL.match(ln) for ln in options.splitlines())
        if len(blocks) < 2 and not thin_declared:
            hard.append(
                f"H2: Positioning Options has {len(blocks)} `### Option` block(s) and no "
                f"thin-option-set declaration; the plurality floor is 2 — a single un-caveated "
                f"option is a verdict in disguise. Either add an independent second option, or "
                f"state 'fewer than two grounded options' as a coverage limit (Scope Lock)."
            )
        elif len(blocks) < 2 and thin_declared:
            advisory.append(
                "A3: fewer than two grounded options, declared as a coverage limit — a "
                "Scope-Lock-honest thin-set exception (the decision space is under-determined)."
            )
        for idx, blk in enumerate(blocks, 1):
            text = "\n".join(blk)
            if not FIELD_ESCAPES.search(text):
                hard.append(f"H3: Option #{idx} missing an `Escapes the squeeze of:` line")
            if not FIELD_BELIEF.search(text):
                hard.append(f"H3: Option #{idx} missing a `Load-bearing belief:` line")
            if not FIELD_KILL.search(text):
                hard.append(
                    f"H3: Option #{idx} missing a `Kill-condition:` line — every option must "
                    f"carry its own evidenced death-condition (symmetric kill-condition)."
                )
        if len(blocks) > 5:
            advisory.append(f"A2: {len(blocks)} options — a large set may dilute the framing; consider whether all are independent.")

        # H8 — standing valence disclaimer present under Positioning Options
        if VALENCE_LINE not in (options or ""):
            hard.append(
                "H8: the standing valence-disclaimer line "
                f"(\"{VALENCE_LINE}…\") is missing under `Positioning Options` "
                "— it is what blocks `better-evidenced` from reading as `better bet`."
            )

    # H6 — unknowns: gaps, not imperatives; un-ordered (no ranking superlative)
    if unknowns is not None:
        ub = bullets(unknowns)
        if not ub:
            hard.append("H6: `Load-Bearing Unknowns` has no entries")
        for b in ub:
            if IMPERATIVE_START.match(b):
                hard.append(f"H6: unknown is phrased as an imperative (a next step, not a gap): `{b.strip()[:90]}`")
            if RANK_SUPERLATIVE.search(b):
                hard.append(f"H6: unknown carries a ranking superlative (unknowns are un-ordered): `{b.strip()[:90]}`")
            if not FINDING_REF.search(b):
                advisory.append(f"A1: unknown cites no Finding ID (weaker evidence trace): `{b.strip()[:80]}`")

    # H5 — verdict / recommendation lexicon across the tier's content lines
    for t in TIER_SECTIONS:
        body = sections.get(t)
        if not body:
            continue
        for ln in content_lines(body):
            for pat in VERDICT_LEXICON:
                m = pat.search(ln)
                if m:
                    hard.append(
                        f"H5 [{t}]: verdict/recommendation lexicon `{m.group(0)}` — the tier "
                        f"frames, it never recommends: `{ln.strip()[:90]}`"
                    )
                    break

    # H7 — every Finding ID referenced in the tier resolves in the Findings Index
    referenced = set()
    for t in TIER_SECTIONS:
        if sections.get(t):
            referenced.update(FINDING_REF.findall(sections[t]))
    if index_body is not None:
        for ref in sorted(referenced, key=lambda s: (len(s), s)):
            if ref not in defined:
                hard.append(f"H7: tier references `{ref}` but it is not defined in the Findings Index (dangling evidence trace)")

    # H9 — the Stage-5 disposition record, if present, must be human-stamped. The close
    # routes the human's pick; the tool may never record a disposition the human did not
    # choose. The choice text itself is not held to the no-verdict lexicon (the human is
    # free to decide "drop") — only the `by human` stamp is required, as proof.
    disposition = section_body(md, DISPOSITION_SECTION)
    if disposition is not None and not BY_HUMAN.search(disposition):
        hard.append(
            "H9: `## Disposition` is present but carries no `by human` stamp — the Stage-5 "
            "close routes the human's choice; the tool may not record a disposition alone."
        )

    return hard, advisory


def _first_def(line: str) -> str | None:
    """A Findings-Index line defines the id that is its FIRST token (after markup).
    Returns that id, else None. (Index lines have the form `F# = <desc> [state]`.)"""
    m = INDEX_DEF.match(line)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def emit(path: Path, hard: list, advisory: list, as_json: bool) -> int:
    status = "fail" if hard else "pass"
    if as_json:
        print(json.dumps({"status": status, "artifact": str(path),
                          "hard_failures": hard, "advisory": advisory}, indent=2))
        return 1 if hard else 0
    print(f"scan-lint: {path}")
    if hard:
        print(f"\n  FAIL — {len(hard)} Scope Lock violation(s):")
        for f in hard:
            print(f"    x {f}")
    else:
        print("\n  PASS — Scope Lock checks hold (the tier maps the decision space, never collapses it).")
    if advisory:
        print(f"\n  advisory ({len(advisory)} — review, non-blocking):")
        for a in advisory:
            print(f"    ! {a}")
    print()
    return 1 if hard else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Scope Lock gate for a /product-discovery:ce-market-scan Stage-3.5 artifact.")
    p.add_argument("artifact", help="the composed market-scan markdown file (docs/market-scans/<slug>/<date>.md)")
    p.add_argument("--json", action="store_true", help="machine-readable result")
    args = p.parse_args(argv)

    try:
        md = load(Path(args.artifact))
    except ScanLintError as e:
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            print(f"scan-lint: ERROR — could not run: {e}", file=sys.stderr)
            print("  -> fall back to the manual Scope Lock checklist (loudly).", file=sys.stderr)
        return 2

    hard, advisory = run_checks(md)
    return emit(Path(args.artifact), hard, advisory, args.json)


if __name__ == "__main__":
    sys.exit(main())
