# Skill Authoring Standard

Skills written by many hands (and many Claudes) must read as **one
product**: same skeleton, same vocabulary, same gate language, same artifact
conventions. This document is the normative standard; `scripts/authoring_check.py`
enforces its mechanical half (run by `check.py`, so a violation cannot merge),
and the rest is contributor discipline flagged here honestly.

Related standards: [HITL-GATE-STANDARD.md](HITL-GATE-STANDARD.md) (the five
rules for interactive gates), `CLAUDE.md` (naming, model-tier policy, doc
currency).

## 1. The skeleton

Every `SKILL.md` carries, in this order:

1. Frontmatter — `name:` (must equal the directory, `ce-` prefixed),
   `description:` (see §6), `argument-hint:`, `allowed-tools:` (leaf toolset).
2. Title + one-paragraph purpose (what it produces, what it never does).
3. `## Runtime Inputs` — what the invocation needs, required vs optional.
4. `## Execution Contract` — the numbered non-negotiables.
5. `## Human-in-the-Loop` — the gate topology (see §3).
6. Cross-cutting rule sections (see §5), where the genre uses them.
7. The stages — inline when small, externalized past the threshold (see §2).
8. `## Escalation` — where findings/failures route.
9. `## Honest Limitations` — what the skill cannot guarantee.

`corpus_lint.py` enforces presence of the four load-bearing headings (Runtime
Inputs, Execution Contract, Escalation, Honest Limitations) in `SKILL.md`
itself — they must not move into stage files. Order is discipline, not lint.

## 2. Progressive disclosure — the externalization rule

`SKILL.md` is loaded on every invocation; stage bodies are not needed until
their stage runs. **Hard cap: 400 lines per SKILL.md** (`authoring_check.py`
A7). Reach for externalization earlier — around 300 lines or more than four
stages:

- **Staged form** (exemplars: `ce-plan`, `ce-spec`): stage bodies live in
  `stage-<range>-<slug>.md`, `SKILL.md` keeps a stage-map table
  (`| stages | file | one-line summary |`) plus load pointers
  (`To begin: load ${CLAUDE_SKILL_DIR}/stage-....md and start Stage N`).
- **Compact form** (exemplar: `ce-patch`): all stage bodies in one
  `stages.md` when they are small.
- Artifact templates always live in their own file
  (`artifact-template.md` / `*-template.md`) — never reconstructed from memory.

Companion files are referenced as `${CLAUDE_SKILL_DIR}/<file>`;
`corpus_lint.py` verifies every such reference resolves.

## 3. Human-in-the-Loop heading vocabulary

The HITL heading names the skill's **gate topology** from a closed enum —
a suffix is a shape, not a flourish (`authoring_check.py` A1):

| Heading | Shape |
|---|---|
| `## Human-in-the-Loop` | default interactive — gates as they arise |
| `— tiered` | material gates ask; mechanical steps proceed |
| `— inverted` | autonomous by default; human pulled in at named boundaries |
| `— adaptive` | gate density follows the user's signal |
| `— light` | a consent gate + a read-back, little in between |
| `— minimal` | a single confirmation around a mechanical transform |
| `— opinionated` | renders a verdict; every call human-overridable |
| `— batched` | judgment batched to a few named gates |

Anything the suffix can't say goes in the section body. New topologies extend
the enum in `authoring_check.py` **and** this table in the same change.

## 4. Gate labeling

Per [HITL-GATE-STANDARD.md](HITL-GATE-STANDARD.md) rule 5, interactive gates
are located and labeled. When a skill numbers a gate **sequence**, the label is
`Gate N of M` (with `1 ≤ N ≤ M` — `authoring_check.py` A2 rejects impossible
labels; `ce-probe-infra` computes M after its sweep and is the exemplar).
**Alternative** gates — where a module selects one of several, as in
`ce-probe-sec`'s remote-target vs local-sandbox attestations — are lettered
(`Gate A`, `Gate B`), never numbered, so a letter signals "one of these
applies" and a number signals "you will pass them all."

## 5. One vocabulary

- **Dates in artifact paths** are the `<date>` placeholder, which resolves to
  the run date in `YYYY-MM-DD` form. Never spell the pattern into the path
  template (A3 rejects the two historical drift spellings).
- **One name per concept.** The loop-back summary between spine stages is the
  `Back-Edge Summary` — the reversed long form is retired (A4; the canon table
  lives in `authoring_check.py`, extend it on the next rename).
- **Shared cross-cutting rules keep their exact headings and invariant cores**
  (A5); the examples around the core stay skill-specific:
  - `## Cross-cutting rule — Findings, Not Verdicts` — core: **the human
    triages**. Disposition vocabulary (Escalate / Defer / Dismiss for the
    probe genre) lives in each skill's triage table or artifact template.
  - `## Cross-cutting rule — Stuck or Ambiguous → Ask, Don't Guess` — core:
    stop, ask one short direct question, record in **Open Questions / Stops**.
- **One evidence meta-scale.** Every genre that reports findings by evidence strength
  keeps its own domain tag strings — `/ce-probe-sec`'s `confirmed`/`suspected`/`passive`,
  `/ce-probe-perf`'s `measured`/`observed`/`inferred`, `/ce-probe-infra`'s
  `scanner-confirmed`/`manifest-read`/`inferred`, `/ce-market-scan`'s
  `confirmed`/`suspected`/`unknown`, `/ce-domain`'s `recorded`/`enforced`/`inferred`
  (a deliberate two-to-one source split within `read`: human-authored artifact vs
  enforcing code) — because lint scripts (`scan-lint.py`) and the
  reports parse those exact strings and the epistemic distinctions are load-bearing.
  They all specialize **one shared shape**: the evidence meta-scale in the shared
  consequence-glossary ([HITL-GATE-STANDARD.md](HITL-GATE-STANDARD.md)) —
  `demonstrated` (a run/scan/source proved it) / `read` (taken directly from an artifact,
  manifest, or single observation) / `inferred` (model reasoning). A skill that declares a
  `Three-State Evidence` rule states its one-line mapping on first use — the literal
  `shared evidence scale` clause (e.g. `measured→demonstrated, observed→read,
  inferred→inferred`) — instead of name-checking every *other* skill's vocabulary (that
  N×N disambiguation scaled quadratically and was the tax). **A11** enforces the
  mechanical half: any `SKILL.md` matching `Three-State Evidence` must carry the mapping
  clause, and the meta-scale itself must stay in the glossary.

### Week-one terms — the bounded operating vocabulary

A reader should be able to operate the whole framework in week one on a **small, closed**
set of branded terms. Keep this list at **≤ 12**: a new skill may not mint a new *branded*
term without either mapping it to a term already here (the evidence-scale pattern above)
or adding it to the shared consequence-glossary through the **A9** mechanism (both homes,
anchored). This is contributor discipline; its two mechanical halves — A9 term-set parity
and A11's mapping clause — are lint-backed.

The current operating vocabulary (10 of 12 — two slots held open on purpose):

1. **the scope lock** — a run's frozen boundary; widen only by escalating up a layer,
   never through it (each spine genre brands its own scope; see each skill's lock section).
2. **write lease** — the per-skill declared write scope the write guard enforces.
3. **material vs routine** — a gate's weight; material gates get their own prompt.
4. **findings, not verdicts** — the agent reports, the human triages.
5. **EARS** — the acceptance-criteria grammar specs are written in.
6. **Gate N of M** — the located-and-labeled gate locator (HITL R5).
7. **the evidence scale** — `demonstrated` / `read` / `inferred` (per-genre tags map onto it).
8. **the spine artifacts** — brief → plan → spec → patch (the one thing each layer emits).
9. **escalate up** — a stuck or out-of-scope call routes up a layer, never sideways.
10. **Back-Edge Summary** — the loop-back summary between spine stages.

Mint the next term only when a real recurring concept has no home in this list or the
glossary — then document it here (or in the glossary) in the same change.

## 6. Descriptions and router clusters

The frontmatter `description:` is the routing surface: first sentence = what
it produces and its lock/discipline; then a `Triggers:` sentence with the verbs
a user would say; hard cap **1536 characters** (A8 — the live-verified platform
truncation limit).

Two further mechanical rules guard the HITL trust layer: **A9** — the shared
consequence-glossary's contributor mirror
(`docs/contributing/HITL-GATE-STANDARD.md`) and
runtime Legend (ce-plan `stage-4-7-gates.md` §6.6.1) keep term-set parity and
each term's anchor phrase in both copies (the copies are deliberately
format-divergent, so the check is anchor-based, not byte identity); **A10** —
a skill that marks any `[material` gate must state the R5 gate-locator
discipline (a literal `Gate N of M` instruction) somewhere in its files.

Skills with adjacent intents stay routable only through **mutual contrastive
clauses** ("For X use /ce-…", naming the sibling). The overlap clusters are registered in
`authoring_check.py` (A6): review↔verify,
probe-infra↔probe-deps, doc-audit↔ship-document, onboard↔domain, and
idea-score↔idea-scout↔market-scan (this last cluster lives
in the companion `product-discovery` plugin — a cluster may span plugins, and
the check resolves members across the plugin union; the `CLUSTERS` tuple in
`authoring_check.py` is the authoritative registry when this list drifts). Every member's
description must name each sibling. Adding a skill with adjacent intent means
adding it to the cluster registry in the same change.

## 7. Forked gate scripts

A gate script needed by more than one skill is **forked, never
share-referenced**: `${CLAUDE_SKILL_DIR}` is the path guarantee in skill Bash
calls, so a cross-skill path is not portable. Every fork is registered in
`plugins/core-engineering/fork-manifest.json` (canonical → copies). Edit the
**canonical**, run `python3 scripts/fork_sync.py --write`, never hand-edit a
copy; `check.py` §5 and `supply_chain_check.py` assert byte-identity from the
manifest.

## 8. What the lint does not check

Honesty about the floor: `authoring_check.py` locks vocabulary and structure,
not judgment. Still reviewer-owned: HITL-GATE-STANDARD rules R1–R4 (consequence
rendering, evidence-first attestations, isolation, triage), section order,
stage-file seam quality, and whether prose is actually good. A green lint means
"consistent," not "well-authored."
