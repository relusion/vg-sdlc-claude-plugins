# Surface Critique — the framework's vision-based rendered-surface pass

Canonical definition of the **Surface Critique** discipline. It lives here, in
`spec/` (the stage that *authors* a surface's quality criteria owns the
discipline that *checks* them), and is **applied in-context by every consumer** —
`spec` (authors the criteria), `implement`, `verify`,
`ce-auto-build`, `ce-ux-audit` (both journey-walk and adversarial-discovery
modes). It is **not** a runtime file
the other skills load (`${CLAUDE_SKILL_DIR}` resolves to each skill's *own*
directory, so a cross-skill read is not possible) — it is the contributor
reference each consumer's compact invocation must stay faithful to, exactly as
*findings-not-verdicts* and the layer locks are defined once and applied per skill.

The discipline exists because the framework was authored on a now-false premise —
"no tool can assert visual layout/polish, so defer it to a human verdict." A
**multimodal model is that tool**: it can read a screenshot and critique it. So a
rendered surface is no longer merely *confirmed* against per-element criteria — it
is **critiqued** from a first-time user's standpoint, emitting evidence-bound
**findings**. The model's sight is fallible, so a finding is evidence the human
adjudicates, never a verdict the agent renders. **It raises the floor, not the
ceiling.**

---

## What it produces — a finding set, never a score or a verdict

Given (1) a captured **screenshot** of a rendered surface at a named viewport/state,
(2) the surface's **declared contract + goal** (where one exists; §"Inputs" below),
and (3) the fixed **dimension rubric**, the pass emits a list of findings, each:

```text
{ dimension      — one of the six below
  class          — functional | taste            (the line; see classifier)
  severity        — high | medium | low
  evidence-tier  — geometric | vision | human     (precedence: geometric > vision)
  surface-kind   — dom | canvas                   (the evidence substrate)
  contract-clause — the bound clause id, or `unbound`
  observation    — "<what is wrong> because <what in the pixels grounds it>"
  evidence-ref   — the screenshot region / file (evidence/ convention)
  suggested-route — /core-engineering:ce-spec (contract gap) · /core-engineering:ce-implement (defect) · Dismiss (noise) }
```

No composite score. No "the design is good/bad" verdict. The consumer's existing
verdict (the human's, or an agent's per-case verdict) is unchanged; this *adds
findings to it*.

## The six dimensions (fixed rubric)

1. **Readability / legible density** — is required text/content legible at the
   captured size; is the surface so dense that elements blur together.
2. **Visual hierarchy** — does emphasis track importance; is the primary thing the
   visually dominant thing.
3. **Affordance discoverability** — can a first-time user find the primary action;
   is it present *and* visible, not occluded or off-screen.
4. **Alignment / spacing / crowding** — are elements aligned and spaced, or
   colliding/cramped.
5. **Clipping / overlap / off-screen** — is content cut off, overlapping so it
   can't be read or clicked, or rendered outside the viewport.
6. **Goal-service** — *the "critique the idea" dimension.* Against the surface's
   stated goal: does this surface as rendered let a first-time user accomplish that
   goal — is the goal-relevant information where attention lands, or buried by
   chrome. A surface can pass every conformance check (tokens correct, contrast
   fine, nothing overlapping) and still **fail to serve its goal**.

## The functional-vs-taste classifier — the line the framework will not cross

The framework deliberately **defers taste** (palette, brand feel, delight) to a
human and lets **functional** defects gate. This pass preserves that line with a
**two-mechanism rule** — it never lets the model's bare opinion gate:

- **Primary (human-drawn, from the contract).** The line is set *per surface by the
  human at spec time*. A finding binding to a `must-be-legible` / `primary-affordance`
  / `must-not` clause is **functional**; one binding to the contract's `taste-line`
  is **taste**. The pass **looks up** the clause's side — it does **not** re-decide
  the line at critique time and **cannot promote a taste clause to functional**.
- **Fallback (evidence-gated, for an unbound/contractless finding).** A finding that
  binds to no clause is **functional only if it cites a specific blocked use** in
  evidence — primary affordance occluded/off-screen, content clipped/overlapping so
  it can't be read or clicked, density/contrast making required text illegible,
  hierarchy so broken the user can't tell what to do next, a required goal step
  impossible. **Absent that citation it degrades to `taste`-advisory.**

Per-dimension default residue (anchors the fallback): clipping/overlap/off-screen is
**functional by definition** when it blocks reading or clicking; alignment/spacing is
**taste** unless it clips or hides; the *weak* form of goal-service ("would be better
if X were higher") is **always taste**, the *strong* form (a required step
dead-ended on the surface) is functional.

**A `taste` finding has no gating path in any consumer.** It is surfaced, advisory,
and re-classable by the human at the end-review — never blocks, never parks, never
fails a step. This is what makes the line structurally uncollapsible.

## Three-tier evidence model

Every finding declares its tier so a guess is never dressed as a measurement:

- **`geometric`** — deterministic bounds: DOM element bounding rects, or a
  canvas/WebGL scene's object bounds **where the app exposes them** (e.g. a Phaser
  scene via an `evaluate_script` hook). AABB-overlap, off-viewport, and clipping are
  *measured* here. **Outranks `vision`.**
- **`vision`** — the model reading pixels. Real and powerful, but **fallible** —
  always labeled as inference, never presented as measurement.
- **`human`** — confirmed by a person.

Precedence: a `geometric` finding overrides a conflicting `vision` one. The
project-proven headless AABB/clipping check (a deterministic test) is the **Tier-1
floor under** this critique — reconciled as one tier of one capability, not a
competing tool.

## Canvas and DOM — honest by construction

The assertion **substrate is the screenshot pixels**, and the model reads pixels —
so the pass works **identically on a `<canvas>`/WebGL surface and a DOM surface**.
This is the precise fix for the second half of the gap: `ce-ux-audit` (in both
modes) already captures screenshots to disk, but no check reasoned over the
pixels.

- A **DOM** surface: read the screenshot; *may* cross-reference the DOM snapshot for
  the `geometric` tier (element rects).
- A **canvas/WebGL** surface: the DOM exposes a single opaque `<canvas>` with **no
  per-object children**, so a DOM snapshot is **structurally blind** to it — the
  pass **never claims otherwise**. The critique rests on the rendered-frame pixels
  (`vision`), with the `geometric` tier available **only** where the app exposes
  scene-object bounds; otherwise overlap is `vision`-inferred and labeled so.

The DOM-snapshot mechanical checks (dead-end, broken link, missing `alt`) stay
DOM-bound and are honestly **N/A for a canvas**. `surface-kind: dom | canvas` is a
required field on every finding so the evidence basis is never a silent gap.

## Inputs — the Surface Quality Contract (where one exists)

At spec time a feature exposing a user-facing rendered surface declares a per-surface
**Surface Quality Contract** (the §2.1 *Surface-Quality Criteria* subsection):

```text
serves:            <the goal a first-time user comes to this surface to accomplish>
must-be-legible:   <content that MUST be readable>                  → functional
primary-affordance:<the primary action that MUST be discoverable>   → functional
density:           <expected element count / crowding tolerance>
must-not:          <the surface-specific broken states> (overlap, clip, off-screen) → functional
taste-line:        <what is explicitly aesthetic preference here>   → taste (advisory)
```

The pass critiques **against this contract** where one exists (per-surface-tuned,
fewer false positives). Where **none** exists — a contractless surface, or
`ce-ux-audit`'s plan-free adversarial-discovery mode — it falls back to a **generic default contract**,
**explicitly labeled weaker**, and the classifier's evidence-gated fallback governs
every finding's class.

## How each consumer invokes it (the disposition matrix)

| Consumer | When | Disposition of a finding |
|---|---|---|
| **spec** | §2.1 — authors the contract + Surface-Quality criteria | template-only (re-derives the obligation so it can't propagate uncaught) |
| **implement** | Stage 2 Manual pass, on the build screenshot — the inverse "what is wrong with this view?" | returns findings; a **functional** finding is a Spec-Conflict-class gap surfaced, never a silent green; **taste** deferred |
| **verify** | Stage 2, on the assembled-surface screenshot it already captures | functional → existing escalation table; taste → recorded for the human; human owns the journey verdict |
| **ce-auto-build** | in-loop, after the first user-facing surface; via the implement subagent's `surface_findings` return | a **functional** finding bound to a clause **or citing a blocked use** PARKS the feature as `surface-defect` (so it can't propagate to dependents); taste → end-review advisory bucket; an **unbound** finding returns advisory with a suggested route, never auto-upgraded, never dropped |
| **ce-ux-audit** (journey-walk mode) | per step, on the captured screenshot — works on `<canvas>` | flows through its existing severity-scored triage table as a *functional* surface finding; a High becomes a **material human decision** (ux-audit renders no verdict and auto-escalates nothing) |
| **ce-ux-audit** (adversarial-discovery mode) | after the happy-path walk, against the generic default contract | *functional* finding into the dated report (taste is **not** emitted — no contract to bind it; deferred to the human) |

---

## Honest Limitations

- **Findings, not proof.** The pass critiques; it does not prove a surface good. It
  raises the floor (catches the obvious breakage a human would catch by looking),
  not the ceiling.
- **Shares the model's blind spots.** When the same model built the surface and
  critiques it, an error in its visual reading can be shared. Independent human
  triage is the backstop.
- **No score, no verdict.** It emits findings only; the human owns every disposition,
  and a `taste` finding can never gate.
- **A model-judgment pass, not a portable script.** Unlike `spec-lint.py` /
  `test-guard.py`, the critique runs in-harness on a multimodal model. It sits with
  skill auto-invocation **outside** the stdlib portability guarantee — honestly, the
  same as every other model-judgment stage. The *advisory* `spec-lint` A4 signal
  (declares-a-surface-but-no-criteria) is the only portable, deterministic half; it
  asserts **declaration, never readability**.
- **Cost.** A multimodal critique per surface per stage is real cost; it reuses
  screenshots the stages already capture (no extra capture), and non-rendered
  features pay nothing.
