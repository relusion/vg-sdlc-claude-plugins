#!/usr/bin/env python3
"""Lint the skill corpus against the authoring standard.

The normative guide is ``docs/contributing/SKILL-AUTHORING.md``.

corpus_lint.py catches referential drift (stale names, broken companion refs,
missing skeleton headings). This lint locks the *vocabulary and structural
conventions* that keep 32 independently authored skills reading as one
product — the drift class that previously accumulated silently because only
reviewer diligence guarded it:

  * A1  `## Human-in-the-Loop` heading suffixes come from a closed enum —
        a suffix names a real HITL *shape*, not a stylistic flourish;
  * A2  `Gate N of M` labels are internally sane per file (1 <= N <= M);
  * A3  artifact-path templates use the `<date>` placeholder — never
        `<YYYY-MM-DD>` or a literal `YYYY-MM-DD-` prefix (one date vocabulary;
        `<date>` resolves to the run date in YYYY-MM-DD form);
  * A4  one name per concept (e.g. `Back-Edge`, never the reversed long form);
  * A5  the shared cross-cutting rules keep their invariant cores verbatim
        ("Findings, Not Verdicts" -> the human triages via
        Escalate / Defer / Dismiss; "Ask, Don't Guess" -> record in
        *Open Questions / Stops*) while the per-skill examples stay local;
  * A6  router-overlap clusters stay mutually disambiguated — every member's
        frontmatter description names each sibling skill;
  * A7  SKILL.md stays under the hard line cap — stage bodies belong in
        lazily loaded stage files (the ce-plan / ce-spec pattern);
  * A8  frontmatter descriptions stay under the platform character cap;
  * A9  the shared consequence-glossary's two copies (the contributor mirror
        in docs/contributing/HITL-GATE-STANDARD.md and the runtime Legend in ce-plan's
        stage-4-7-gates.md) keep term-set parity and each term's invariant
        anchor phrase in BOTH copies — the copies are deliberately
        format-divergent, so this is the A5 pattern (anchors), not byte
        identity;
  * A10 a skill whose docs mark any `[material` gate states the R5 gate-locator
        discipline (a literal `Gate N of M` instruction somewhere in the
        skill's files) — located & labeled is not optional for material gates.
  * A11 the evidence-strength meta-scale (`demonstrated`/`read`/`inferred`)
        stays in the shared consequence-glossary, and every SKILL.md that
        declares a `Three-State Evidence` rule maps its own domain tags onto it
        with the literal `shared evidence scale` clause — one mental model, each
        genre's tag strings a labeled specialization (not N×N cross-references).
  * A12 a dated, never-overwritten artifact contract states a same-day collision
        rule and the `-2` suffix convention somewhere in that skill's shipped
        docs, so a second run cannot silently clobber the first.
  * A13 decision-option tables contain at most four choices, and prose never
        instructs a single `AskUserQuestion` round to carry more than four
        questions. Larger gates must use an explicit same-locator split.
  * A14 always-loaded entrypoints and individually loaded companion Markdown
        files stay below deterministic token-proxy ceilings. The proxy is a
        stable byte estimate, not a claim about any model's tokenizer.

Stdlib-only, exit 0 clean / 1 findings, same contract as corpus_lint.py.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
# The skeleton/HITL/canon/cluster/material checks iterate every plugin's skills/
# dir (see skills_roots). SKILLS_REL stays core-scoped only for GLOSSARY_RUNTIME
# below — the shared consequence-glossary's runtime home is core-owned by design.
SKILLS_REL = Path("plugins") / "core-engineering" / "skills"

# A1 — closed enum of HITL heading suffixes. A bare heading is the default
# interactive shape; each token names a distinct, documented gate topology.
HITL_TOKENS = (
    "tiered",       # material gates ask, mechanical steps proceed
    "inverted",     # autonomous by default, human pulled in at boundaries
    "adaptive",     # gate density follows the learner/user signal
    "light",        # a consent gate + a read-back, little in between
    "minimal",      # a single confirmation around a mechanical transform
    "opinionated",  # renders a verdict; every call human-overridable
    "batched",      # judgment batched to a few named gates
)
HITL_HEADING_RE = re.compile(r"^##\s+Human-in-the-Loop(?P<rest>.*)$", re.MULTILINE)

# A2
GATE_LABEL_RE = re.compile(r"\bGate\s+(\d+)\s+of\s+(\d+)\b")

# A3 — the two historical drift spellings for the date slot in artifact paths.
DATE_DRIFT = ("<YYYY-MM-DD>", "YYYY-MM-DD-<")

# A4 — canonical concept names. Key: forbidden regex; value: canonical form.
# The four retired lock brands collapse into one "Scope Lock" (WS7-T10) — one
# brand, five per-skill scopes; reintroducing an old brand in any skill/doc
# markdown fails lint. The old->new mapping lives in CHANGELOG.md, which A4 never
# scans (repo-root, not a skill doc or under docs/), so the migration note is safe.
CONCEPT_CANON = (
    (re.compile(r"[Bb]ackward[- ][Ee]dge"), "Back-Edge"),
    (re.compile(r"[Bb]oundary[- ][Ll]ock"), "Scope Lock"),
    (re.compile(r"[Ss]pec[- ][Ll]ock"), "Scope Lock"),
    (re.compile(r"[Pp]atch[- ][Ll]ock"), "Scope Lock"),
    (re.compile(r"[Ff]rame[- ][Ll]ock"), "Scope Lock"),
)

# A5 — shared cross-cutting rules: exact heading + invariant substrings that
# must survive in the section body (per-skill examples around them stay free).
FINDINGS_HEADING = "## Cross-cutting rule — Findings, Not Verdicts"
ASK_HEADING = "## Cross-cutting rule — Stuck or Ambiguous → Ask, Don't Guess"
# The universal core is "the human triages"; the Escalate/Defer/Dismiss triple
# is probe-genre disposition vocabulary and lives in each skill's triage table
# or artifact template, so it is deliberately NOT required here (ce-plan-audit
# and ce-review route dispositions in their own vocabulary).
INVARIANTS = {
    FINDINGS_HEADING: ("human triages",),
    ASK_HEADING: ("Open Questions / Stops",),
}
# Any heading that *mentions* the rule must be the canonical spelling.
INVARIANT_MENTIONS = {
    "findings, not verdicts": FINDINGS_HEADING,
    "ask, don't guess": ASK_HEADING,
}

# A6 — description-overlap clusters: these skills triage adjacent intents, and
# only their contrastive description clauses keep a router from misfiring.
# Every member's frontmatter must name every sibling as /<name>.
CLUSTERS = (
    ("ce-architecture", "ce-plan", "ce-spec"),
    ("ce-architecture", "ce-decide"),
    ("ce-review", "ce-verify"),
    ("ce-probe-infra", "ce-probe-deps"),
    ("ce-idea-score", "ce-idea-scout", "ce-market-scan"),
    ("ce-doc-audit", "ce-ship-document"),
    ("ce-onboard", "ce-domain"),
)

SKILL_LINE_CAP = 400       # A7 — externalize stages past this (see ce-plan)
DESCRIPTION_CHAR_CAP = 1536  # A8 — live-verified platform truncation limit

# A14 — line counts miss dense prose and minified tables. ``ceil(utf8_bytes/4)``
# is intentionally simple, deterministic, tokenizer-independent, and cheap to
# reproduce in CI. These are migration ceilings, not authoring targets: they
# leave every untouched file in the current corpus green while preventing
# unlimited growth. The authoring guide sets lower design targets.
TOKEN_PROXY_BYTES_PER_UNIT = 4
SKILL_TOKEN_PROXY_CAP = 10_000
COMPANION_TOKEN_PROXY_CAP = 20_000

# A9 — the shared consequence-glossary's two homes and, per term, the anchor
# phrase that must survive (normalized) in BOTH copies. Changing a gloss's
# meaning breaks its anchor in that copy; renaming a term breaks term parity.
GLOSSARY_MIRROR = Path("docs") / "contributing" / "HITL-GATE-STANDARD.md"
GLOSSARY_MIRROR_HEADING = "## The shared consequence-glossary"
GLOSSARY_RUNTIME = SKILLS_REL / "ce-plan" / "stage-4-7-gates.md"
GLOSSARY_RUNTIME_START = "**Legend**"
GLOSSARY_RUNTIME_END = "5. **Full Journey Map"
GLOSSARY_ANCHORS = {
    "durable noun": ("expects to return",),
    "reciprocal": ("find / change / delete",),
    "revisit": ("find it again",),
    "retain": ("how long it's kept",),
    "access-mode": ("user-owned-mutable", "system-or-append-only"),
    "data-class": ("material move",),
    "owned-by": ("no action",),
    "bridge": ("stand-in",),
    "excluded": ("never built",),
    "deprecate": ("window",),
    "shim": ("adapter",),
    "hard-break": ("breaks immediately",),
    "break-class": ("outside caller",),
    "select-to-continue": ("pick one and move forward",),
    "scope lock": ("frozen for this run", "widening goes up a layer"),
}

# A10 — material-gate marker and the locator instruction it requires.
MATERIAL_MARKER = "[material"
LOCATOR_LITERAL = "Gate N of M"

# A11 — the evidence-strength meta-scale. Its canonical definition lives in the
# shared consequence-glossary (GLOSSARY_MIRROR); every skill that declares a
# Three-State Evidence rule maps its own domain tags onto the meta-scale with the
# EVIDENCE_MAPPING_CLAUSE literal (replacing the old N×N cross-skill name-checks).
# The scale is glossed at those runtime print-sites, not in the ce-plan Legend, so
# it is intentionally NOT in GLOSSARY_ANCHORS — A11, not A9, keeps it in sync.
EVIDENCE_TRIGGER_RE = re.compile(r"three[- ]state evidence", re.IGNORECASE)
EVIDENCE_MAPPING_CLAUSE = "shared evidence scale"
EVIDENCE_GLOSSARY_ANCHOR = "evidence-strength meta-scale"
EVIDENCE_META_TIERS = ("demonstrated", "read", "inferred")

# A12 — date-only snapshot names collide on a second run that day. A skill that
# promises never-overwritten dated output must ship the collision behavior in
# its own runtime docs (not only in the contributor guide).
NEVER_OVERWRITE_RE = re.compile(r"never[- ]overwrit", re.IGNORECASE)
SAME_DAY_LITERAL = "same-day"
COLLISION_SUFFIX_LITERAL = "-2"

# A13 — the Claude Code decision harness accepts no more than four questions in
# one AskUserQuestion call and no more than four options per question. Decision
# tables are identified narrowly by their first two header cells so ordinary
# comparison/data tables are not mistaken for dialogs. Question-range prose is
# checked only when the same paragraph explicitly says the questions are in one
# round/call; a larger total spread across several rounds remains valid.
DECISION_TABLE_FIRST_CELLS = {"option", "user choice"}
DECISION_TABLE_SECOND_CELLS = {"consequence", "result", "what happens next"}
QUESTION_CALL_RANGE_RE = re.compile(
    r"(?P<low>\d+)\s*[\-\u2013]\s*(?P<high>\d+)\s+"
    r"(?:[a-z-]+\s+){0,3}questions\b"
    r"(?:(?!\n\s*\n).){0,180}?"
    r"\b(?:in\s+(?:a|one|the)\s+(?:single\s+)?round|"
    r"single\s+(?:interactive\s+)?round|AskUserQuestion\s+call)\b",
    re.IGNORECASE | re.DOTALL,
)


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def skills_roots(root: Path) -> list[Path]:
    """Every marketplace plugin's skills/ dir — validators iterate all plugins,
    not just core-engineering (GLOSSARY_RUNTIME below stays core-owned)."""
    return sorted(p for p in (root / "plugins").glob("*/skills") if p.is_dir())


def skill_md_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for skills_root in skills_roots(root):
        files.extend(skills_root.glob("*/SKILL.md"))
    return sorted(files)


def all_skill_docs(root: Path) -> list[Path]:
    files: list[Path] = []
    for skills_root in skills_roots(root):
        files.extend(skills_root.glob("**/*.md"))
    return sorted(files)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def frontmatter_block(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for i in range(1, min(len(lines), 80)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])
    return ""


def description_text(fm: str) -> str:
    out: list[str] = []
    capturing = False
    for line in fm.splitlines():
        if capturing:
            if not line.strip() or line.startswith((" ", "\t")):
                out.append(line.strip())
                continue
            break
        m = re.match(r"description:\s*(.*)$", line)
        if m is not None:
            rest = m.group(1).strip()
            if rest and rest not in ("|", ">", "|-", ">-"):
                return rest
            capturing = True
    return " ".join(piece for piece in out if piece)


def h2_sections(text: str) -> list[tuple[int, str, str]]:
    """Return (line_number, heading_line, body) for every `## ` section."""
    lines = text.splitlines()
    sections: list[tuple[int, str, str]] = []
    current: tuple[int, str, list[str]] | None = None
    for idx, line in enumerate(lines, start=1):
        if line.startswith("## "):
            if current is not None:
                sections.append((current[0], current[1], "\n".join(current[2])))
            current = (idx, line.rstrip(), [])
        elif current is not None:
            current[2].append(line)
    if current is not None:
        sections.append((current[0], current[1], "\n".join(current[2])))
    return sections


def markdown_table_cells(line: str) -> list[str] | None:
    """Return normalized cells for a simple pipe table row, or ``None``.

    Skill decision tables intentionally use simple text cells. This parser is
    correspondingly conservative: it does not try to interpret escaped pipes
    or arbitrary inline HTML, avoiding false positives in non-dialog content.
    """
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip().lower() for cell in stripped[1:-1].split("|")]


def is_markdown_separator(cells: list[str] | None) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def check_hitl_headings(root: Path, errors: list[str]) -> int:
    checked = 0
    allowed = {f"## Human-in-the-Loop — {token}" for token in HITL_TOKENS}
    allowed.add("## Human-in-the-Loop")
    for path in skill_md_files(root):
        text = path.read_text(encoding="utf-8")
        for match in HITL_HEADING_RE.finditer(text):
            checked += 1
            heading = f"## Human-in-the-Loop{match.group('rest')}".rstrip()
            if heading not in allowed:
                errors.append(
                    f"{rel(root, path)}:{line_of(text, match.start())}: "
                    f"HITL heading {heading!r} — suffix must be one of "
                    f"{', '.join(HITL_TOKENS)} (or none); see "
                    "docs/contributing/SKILL-AUTHORING.md"
                )
    return checked


def check_gate_labels(root: Path, errors: list[str]) -> int:
    checked = 0
    for path in all_skill_docs(root):
        text = path.read_text(encoding="utf-8")
        for match in GATE_LABEL_RE.finditer(text):
            checked += 1
            n, m = int(match.group(1)), int(match.group(2))
            if n < 1 or m < 1 or n > m:
                errors.append(
                    f"{rel(root, path)}:{line_of(text, match.start())}: "
                    f"inconsistent gate label 'Gate {n} of {m}' (need 1 <= N <= M)"
                )
    return checked


def check_date_placeholders(root: Path, errors: list[str]) -> int:
    checked = 0
    for path in all_skill_docs(root):
        text = path.read_text(encoding="utf-8")
        checked += 1
        for needle in DATE_DRIFT:
            start = 0
            while (pos := text.find(needle, start)) != -1:
                errors.append(
                    f"{rel(root, path)}:{line_of(text, pos)}: date spelled "
                    f"{needle!r} — use the `<date>` placeholder "
                    f"(it resolves to the run date, YYYY-MM-DD)"
                )
                start = pos + len(needle)
    return checked


def check_concept_canon(root: Path, errors: list[str]) -> int:
    checked = 0
    paths = all_skill_docs(root) + sorted((root / "docs").glob("**/*.md"))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        checked += 1
        for pattern, canonical in CONCEPT_CANON:
            for match in pattern.finditer(text):
                errors.append(
                    f"{rel(root, path)}:{line_of(text, match.start())}: "
                    f"{match.group(0)!r} — the canonical concept name is "
                    f"{canonical!r} (one name per concept)"
                )
    return checked


def check_invariant_blocks(root: Path, errors: list[str]) -> int:
    checked = 0
    for path in all_skill_docs(root):
        text = path.read_text(encoding="utf-8")
        for line_no, heading, body in h2_sections(text):
            lowered = heading.lower()
            for mention, canonical in INVARIANT_MENTIONS.items():
                if mention in lowered and heading != canonical:
                    errors.append(
                        f"{rel(root, path)}:{line_no}: heading {heading!r} — "
                        f"the shared rule heading must read exactly {canonical!r}"
                    )
            if heading in INVARIANTS:
                checked += 1
                for needle in INVARIANTS[heading]:
                    if needle not in body:
                        errors.append(
                            f"{rel(root, path)}:{line_no}: section {heading!r} "
                            f"lost its invariant core — must contain {needle!r}"
                        )
    return checked


def check_router_clusters(root: Path, errors: list[str]) -> int:
    checked = 0
    # A router cluster may span plugins (e.g. the idea trio in product-discovery),
    # so resolve each member's SKILL.md across every plugin's skills/ dir.
    by_name = {p.parent.name: p for p in skill_md_files(root)}
    for cluster in CLUSTERS:
        for member in cluster:
            path = by_name.get(member)
            if path is None or not path.is_file():
                errors.append(f"cluster: {member} has no SKILL.md but is in a router cluster")
                continue
            checked += 1
            fm = frontmatter_block(path.read_text(encoding="utf-8"))
            for sibling in cluster:
                if sibling == member:
                    continue
                sibling_path = by_name.get(sibling)
                sibling_command = (
                    f"/{sibling_path.parents[2].name}:{sibling}"
                    if sibling_path is not None
                    else f"/<plugin>:{sibling}"
                )
                if sibling_command not in fm:
                    errors.append(
                        f"{rel(root, path)}: description does not mention "
                        f"{sibling_command} — "
                        f"router cluster {cluster} relies on mutual contrastive clauses"
                    )
    return checked


def check_skill_size(root: Path, errors: list[str]) -> int:
    checked = 0
    for path in skill_md_files(root):
        checked += 1
        count = len(path.read_text(encoding="utf-8").splitlines())
        if count > SKILL_LINE_CAP:
            errors.append(
                f"{rel(root, path)}: {count} lines > {SKILL_LINE_CAP} cap — "
                f"externalize stage bodies into stage-*.md files "
                "(the ce-plan / ce-spec pattern; see "
                "docs/contributing/SKILL-AUTHORING.md)"
            )
    return checked


def check_description_length(root: Path, errors: list[str]) -> int:
    checked = 0
    for path in skill_md_files(root):
        checked += 1
        desc = description_text(frontmatter_block(path.read_text(encoding="utf-8")))
        if len(desc) > DESCRIPTION_CHAR_CAP:
            errors.append(
                f"{rel(root, path)}: description is {len(desc)} chars > "
                f"{DESCRIPTION_CHAR_CAP} platform cap — it will truncate at runtime"
            )
    return checked


def token_proxy(text: str) -> int:
    """Return a deterministic upper-level context-size proxy.

    This is deliberately not named ``tokens``: tokenization depends on the
    selected model. UTF-8 bytes divided by four is a stable review and CI budget
    that catches dense one-line prose the line cap cannot see.
    """
    byte_count = len(text.encode("utf-8"))
    return (byte_count + TOKEN_PROXY_BYTES_PER_UNIT - 1) // TOKEN_PROXY_BYTES_PER_UNIT


def check_token_proxy_budgets(root: Path, errors: list[str]) -> int:
    """A14 — bound always-loaded and single-load Markdown context."""
    checked = 0
    for entrypoint in skill_md_files(root):
        text = entrypoint.read_text(encoding="utf-8")
        estimate = token_proxy(text)
        checked += 1
        if estimate > SKILL_TOKEN_PROXY_CAP:
            errors.append(
                f"{rel(root, entrypoint)}: token proxy {estimate} > "
                f"{SKILL_TOKEN_PROXY_CAP} entrypoint ceiling — keep only the "
                "routing and execution contract in SKILL.md; deduplicate or "
                "load stage detail on demand (A14; "
                "docs/contributing/SKILL-AUTHORING.md §2)"
            )

        for companion in sorted(entrypoint.parent.glob("**/*.md")):
            if companion == entrypoint:
                continue
            companion_text = companion.read_text(encoding="utf-8")
            companion_estimate = token_proxy(companion_text)
            checked += 1
            if companion_estimate > COMPANION_TOKEN_PROXY_CAP:
                errors.append(
                    f"{rel(root, companion)}: token proxy {companion_estimate} > "
                    f"{COMPANION_TOKEN_PROXY_CAP} companion-file ceiling — split "
                    "by the stage that consumes the content or remove duplicated "
                    "contracts (A14; docs/contributing/SKILL-AUTHORING.md §2)"
                )
    return checked


def normalize_gloss(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("*", "").replace("`", "")).lower()


def glossary_copy_texts(root: Path, errors: list[str]) -> tuple[str, str] | None:
    mirror_path = root / GLOSSARY_MIRROR
    runtime_path = root / GLOSSARY_RUNTIME
    try:
        mirror_all = mirror_path.read_text(encoding="utf-8")
        runtime_all = runtime_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"glossary: cannot read a glossary home: {exc}")
        return None
    if GLOSSARY_MIRROR_HEADING not in mirror_all:
        errors.append(
            f"{rel(root, mirror_path)}: contributor-mirror heading "
            f"{GLOSSARY_MIRROR_HEADING!r} not found — the glossary sync check lost its anchor"
        )
        return None
    mirror = mirror_all.split(GLOSSARY_MIRROR_HEADING, 1)[1]
    next_h2 = re.search(r"^## ", mirror, re.MULTILINE)
    if next_h2:
        mirror = mirror[: next_h2.start()]
    start = runtime_all.find(GLOSSARY_RUNTIME_START)
    end = runtime_all.find(GLOSSARY_RUNTIME_END)
    if start == -1 or end == -1 or end <= start:
        errors.append(
            f"{rel(root, runtime_path)}: runtime Legend block not found between "
            f"{GLOSSARY_RUNTIME_START!r} and {GLOSSARY_RUNTIME_END!r} — "
            "the glossary sync check lost its anchor"
        )
        return None
    return normalize_gloss(mirror), normalize_gloss(runtime_all[start:end])


def check_glossary_sync(root: Path, errors: list[str]) -> int:
    """A9 — a consequence-glossary term must read the same at every gate."""
    texts = glossary_copy_texts(root, errors)
    if texts is None:
        return 1
    mirror, runtime = texts
    checked = 0
    for term, anchors in GLOSSARY_ANCHORS.items():
        checked += 1
        for name, text in (("contributor mirror", mirror), ("runtime Legend", runtime)):
            if term not in text:
                errors.append(
                    f"glossary: term {term!r} missing from the {name} — "
                    "term-set parity broken (rename/remove must land in both copies)"
                )
                continue
            for anchor in anchors:
                if normalize_gloss(anchor) not in text:
                    errors.append(
                        f"glossary: {name} lost the anchor {anchor!r} for term {term!r} — "
                        "a gloss changed in one copy only (sync both, per HITL-GATE-STANDARD)"
                    )
    return checked


def check_material_gate_locators(root: Path, errors: list[str]) -> int:
    """A10 — material gates require the R5 gate-locator discipline stated."""
    checked = 0
    skill_dirs = [
        d
        for skills_root in skills_roots(root)
        for d in sorted(skills_root.iterdir())
    ]
    for skill_dir in skill_dirs:
        if not (skill_dir / "SKILL.md").is_file():
            continue
        docs = sorted(skill_dir.glob("**/*.md"))
        texts = [p.read_text(encoding="utf-8") for p in docs]
        if not any(MATERIAL_MARKER in t for t in texts):
            continue
        checked += 1
        if not any(LOCATOR_LITERAL in t for t in texts):
            errors.append(
                f"{rel(root, skill_dir)}: marks `[material` gates but never states the "
                f"R5 gate-locator discipline (a literal {LOCATOR_LITERAL!r} instruction) — "
                "located & labeled is mandatory for material gates "
                "(docs/contributing/HITL-GATE-STANDARD.md)"
            )
    return checked


def check_evidence_meta_scale(root: Path, errors: list[str]) -> int:
    """A11 — one evidence meta-scale; each three-state genre maps its tags onto it."""
    checked = 0
    # (a) the meta-scale's canonical definition lives in the shared glossary mirror.
    checked += 1
    mirror_path = root / GLOSSARY_MIRROR
    try:
        mirror_all = mirror_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"evidence-scale: cannot read the glossary home: {exc}")
        mirror_all = ""
    if mirror_all:
        region = mirror_all
        if GLOSSARY_MIRROR_HEADING in mirror_all:
            region = mirror_all.split(GLOSSARY_MIRROR_HEADING, 1)[1]
            next_h2 = re.search(r"^## ", region, re.MULTILINE)
            if next_h2:
                region = region[: next_h2.start()]
        if EVIDENCE_GLOSSARY_ANCHOR not in region.lower():
            errors.append(
                f"{rel(root, mirror_path)}: the shared consequence-glossary lost the "
                f"{EVIDENCE_GLOSSARY_ANCHOR!r} block — the evidence meta-scale is the one "
                "shape every genre's three-state axis specializes (A11; "
                "docs/contributing/SKILL-AUTHORING.md §5)"
            )
        else:
            for tier in EVIDENCE_META_TIERS:
                if f"`{tier}`" not in region:
                    errors.append(
                        f"{rel(root, mirror_path)}: evidence meta-scale missing tier "
                        f"`{tier}` — the scale is `demonstrated`/`read`/`inferred` (A11)"
                    )
    # (b) every SKILL.md declaring a Three-State Evidence rule maps it onto the scale.
    for path in skill_md_files(root):
        text = path.read_text(encoding="utf-8")
        if not EVIDENCE_TRIGGER_RE.search(text):
            continue
        checked += 1
        if EVIDENCE_MAPPING_CLAUSE not in text.lower():
            errors.append(
                f"{rel(root, path)}: declares a Three-State Evidence rule but never maps its "
                f"tags onto the {EVIDENCE_MAPPING_CLAUSE!r} — add the one-line mapping clause "
                "(e.g. `measured→demonstrated, observed→read, inferred→inferred`) instead of "
                "name-checking other skills' vocabularies (A11; "
                "docs/contributing/SKILL-AUTHORING.md §5)"
            )
    return checked


def check_dated_snapshot_collisions(root: Path, errors: list[str]) -> int:
    """A12 — never-overwritten dated snapshots need a second-run key."""
    checked = 0
    skill_dirs = [
        directory
        for skills_root in skills_roots(root)
        for directory in sorted(skills_root.iterdir())
        if (directory / "SKILL.md").is_file()
    ]
    for skill_dir in skill_dirs:
        texts = [
            path.read_text(encoding="utf-8")
            for path in sorted(skill_dir.glob("**/*.md"))
        ]
        if not any("<date>" in text and NEVER_OVERWRITE_RE.search(text) for text in texts):
            continue
        checked += 1
        combined = "\n".join(texts).lower()
        if SAME_DAY_LITERAL not in combined or COLLISION_SUFFIX_LITERAL not in combined:
            errors.append(
                f"{rel(root, skill_dir)}: promises never-overwritten `<date>` "
                "artifacts but does not define a same-day `-2` collision suffix "
                "in its shipped docs (A12; docs/contributing/SKILL-AUTHORING.md §5)"
            )
    return checked


def check_hitl_harness_limits(root: Path, errors: list[str]) -> int:
    """A13 — decision dialogs must fit the platform's four-by-four limit."""
    checked = 0
    for path in all_skill_docs(root):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()

        for index, line in enumerate(lines):
            header = markdown_table_cells(line)
            if (
                header is None
                or len(header) < 2
                or header[0] not in DECISION_TABLE_FIRST_CELLS
                or header[1] not in DECISION_TABLE_SECOND_CELLS
                or index + 1 >= len(lines)
                or not is_markdown_separator(markdown_table_cells(lines[index + 1]))
            ):
                continue
            checked += 1
            option_count = 0
            cursor = index + 2
            while cursor < len(lines):
                row = markdown_table_cells(lines[cursor])
                if row is None:
                    break
                if not is_markdown_separator(row):
                    option_count += 1
                cursor += 1
            if option_count > 4:
                errors.append(
                    f"{rel(root, path)}:{index + 1}: decision table has "
                    f"{option_count} options — AskUserQuestion allows at most 4; "
                    "split the dialog under the same gate locator and state why"
                )

        for match in QUESTION_CALL_RANGE_RE.finditer(text):
            checked += 1
            high = int(match.group("high"))
            if high > 4:
                excerpt = re.sub(r"\s+", " ", match.group(0)).strip()
                errors.append(
                    f"{rel(root, path)}:{line_of(text, match.start())}: "
                    f"single decision round permits up to {high} questions "
                    f"({excerpt!r}) — AskUserQuestion allows at most 4; "
                    "split the round under the same gate locator and state why"
                )
    return checked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint skill-corpus authoring conformance")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    errors: list[str] = []
    checked = 0
    if not skill_md_files(root):
        errors.append("structure: no SKILL.md files found under any plugins/*/skills")
    checked += check_hitl_headings(root, errors)
    checked += check_gate_labels(root, errors)
    checked += check_date_placeholders(root, errors)
    checked += check_concept_canon(root, errors)
    checked += check_invariant_blocks(root, errors)
    checked += check_router_clusters(root, errors)
    checked += check_skill_size(root, errors)
    checked += check_description_length(root, errors)
    checked += check_token_proxy_budgets(root, errors)
    checked += check_glossary_sync(root, errors)
    checked += check_material_gate_locators(root, errors)
    checked += check_evidence_meta_scale(root, errors)
    checked += check_dated_snapshot_collisions(root, errors)
    checked += check_hitl_harness_limits(root, errors)

    if errors:
        print(
            f"authoring-check: FAIL — {len(errors)} issue(s) across {checked} check(s):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  ✗ {error}", file=sys.stderr)
        return 1
    print(f"authoring-check: OK — {checked} check(s), 0 issues.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
