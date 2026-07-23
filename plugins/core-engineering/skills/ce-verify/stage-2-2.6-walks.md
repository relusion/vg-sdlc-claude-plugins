# ce-verify — Stage 2–2.6: Journey, Revisit, and Surface-Removal Walks

Stage file for the `ce-verify` skill (orchestrator: `SKILL.md` — read it first for the Execution Contract, Human-in-the-Loop moments, and the Escalation table). Load this file after Stage 1 is complete.

**Next:** when Stages 2–2.6 are complete, load `${CLAUDE_SKILL_DIR}/stage-3-acceptance-report.md`.

---

## Stage 2 — Journey Verification

For each in-scope journey, walk it end-to-end, grounded in the plan's
Reachability / Consumability Trace. The plan's journey table maps journey
steps → owning features. Drive the whole journey and capture evidence before
any prompt.

Read each step's **verification modality** from the plan's Journey Map — the journey's primary modality, or a step's own modality where it differs (`browser · http · cli · sdk · event · iac · db · manual`). The spec's test cases carry the same modality on each case (the `modality:` tag), so a journey step and its proving test case agree on the tool. It tells you which tool to drive with; don't guess it. If a step's modality can't be driven here (its harness is unavailable), fall back to the documented observable as a human-run check and record the degradation — never silently skip it.

### 2.a Drive every step (evidence capture — no prompt yet)

For each step, in order:

1. Restate the step, the owning feature, and its **expected observable** (from the plan's journey table — the concrete signal that proves the step passed).
2. Drive the step with its modality — browser (dev server + click-through), http, cli, sdk, event observe, iac plan/apply, or a db/state assertion (`manual` modality = walk it by hand) — and check the result against the expected observable. Capture evidence (screenshots, response bodies, logs).
3. **For a `browser` / live rendered surface, critique the assembled view — not
   just the step's observable.** A pile of overlapping objects satisfies every
   per-step observable while being visibly unplayable. Present the **rendered
   surface itself** (the screenshot, not a textual summary) and run the **Surface
   Critique** pass from a first-time user's standpoint: overlap/occlusion,
   clipping/off-screen, illegible density, visual hierarchy, affordance
   discoverability, and whether the surface serves its goal. Draw the line
   explicitly — **functional readability** (occlusion, illegible density, an
   unreachable affordance, clipping, a dead-ended goal step) is a **Fail** that
   escalates like any step Fail; **aesthetic taste** (on-theme, beautiful, palette)
   stays the human's `manual:judgment` verdict, never a Fail. *(The framework's
   Surface Critique discipline — rubric, classifier, and canvas-vs-DOM evidence
   model in `spec/surface-critique.md`; on a `<canvas>` surface the critique
   reads the screenshot pixels, since the DOM exposes no per-object children.)*
4. Derive an **evidence result** for the step: `Pass` (evidence matched the
   expected observable), `Fail` (it did not — including a functional-readability
   Fail from the Surface Critique), or `uncertain` (evidence ambiguous, a degraded
   modality, or a `manual:judgment`/taste call only the human can make). This is
   a demonstrated result for objective checks; only uncertainty and
   `manual:judgment` need a human verdict.

Per-feature `manual` verdicts already in each `verification.md` are **read, not
re-run** — the journey walk is the system-level manual check. **Exception under
`/core-engineering:ce-auto-build`:** the implement subagents *self-certified* their `manual:harness-gap`
verdicts in-loop (the author rendered its own verdict against an ephemeral server),
so when this skill runs as auto-build's integration agent it **independently
re-drives those `manual:harness-gap` cases** against the integration server and
records its own verdict — a fresh agent that did not write the code, the harness-gap
analog of the spec→implement spawn boundary; a disagreement is surfaced at the
end-review. Only `manual:judgment` verdicts stay *read, not re-run* (their verdict is
the human's, gathered at the end-review).

Skip steps owned by features that are not yet `implemented`; mark the journey
`partial` if any step is missing its feature.

### 2.b Journey disposition

Render the full step/evidence table. Demonstrated Pass rows are final for this
run and are not questions. If every row passes, record the journey Pass and
continue.

If any row is `Fail`, `uncertain`, or `manual:judgment`, print
`Gate N of M — Journey <name>` and lead with only those rows. Include evidence,
basis, and cost-if-wrong; give each flagged row its own `Pass` / `Fail` /
`Blocked` question. A deterministic Fail is already a failure—the question is
its disposition/route, not permission to call it Pass without contrary
evidence. Split calls over four questions with a stated reason.

The journey result is the AND of demonstrated Pass rows and human-resolved
flagged rows. Any Fail escalates; Blocked remains not verified.

---

## Stage 2.5 — Durable-Noun Revisit Walk

A forward walk (Stage 2) proves a path advances; it never proves you can come
**back**. A feature can let a user create a persisted thing yet offer no way to
list, reopen, switch between, or edit it — and every forward walk still passes.
This stage is the build-evidence end of **Lifecycle Closure** (the plan's Stage
6.3 is the discovery end): it fires off what was **built**, not what was planned,
and is the one check that can surface a durable noun the plan never named.

**Trigger (mandatory when it fires; machine-detected).** For each `implemented`
feature in scope, detect a durable-state write from the built artifacts — any of:

- a journey step with modality `db` / `event` / `iac` (a persisted target), or
- an acceptance criterion or test case whose verb writes a store (create / save / update / delete), or
- a write verb against a store in `tasks.json`.

If none fire across the in-scope features, skip this stage and record it N/A. Read
the plan's **Stage 6.3 Durable-State Closure** rows for each detected noun's
reciprocal obligations and access-mode.

**The walk (non-linear, scripted — not a planned journey).** For each detected
noun whose access-mode is `user-owned-mutable`, drive its reciprocals with the
noun's modality (browser click-through / http GET+PATCH / cli / sdk):

1. Create instance **A**, then instance **B** (two — to expose *switch* and *duplicate-on-return*).
2. Leave the creation surface (navigate away / new session / cold return).
3. **Revisit** — return and list/find: **both A and B** must be reachable.
4. **Switch/reopen** — open A, then B: each loads the correct, distinct instance (not a blank form, not a duplicate).
5. **Amend** — edit A, persist, re-list: the change is reflected and **no second instance was created**.

For access-mode `system-or-append-only`, drive only the **revisit** edge
(find/read); `amend`/`retire` are walked only where the closure marked them owned.

**Governance-reciprocal confirmation (data-class-keyed).** After the revisit walk,
for each detected durable noun whose plan Stage-6.3 **data-class** is `personal` or
`sensitive`, drive the governance reciprocals the closure marked `owned-by` with the
noun's modality — and confirm a REAL consumer, not a green endpoint:

- **`retain`** — confirm a policy/job is actually wired (an expiry job exists, a TTL
  is set), not merely planned. Where the horizon exceeds the verify session, record
  `N/A` (attested from the wired policy, never silently passed).
- **`export`** — request the subject data and confirm the returned payload actually
  contains instance **A** and **B** created in the revisit walk.
- **`erase`** — erase the subject and re-list: both **A** and **B** must be GONE,
  not soft-hidden (a row that still resolves on direct fetch is a `Fail`).

A green export/delete endpoint test does **not** satisfy this — it proves the verb,
not that the policy reaches every attributable noun. These governance findings feed
the **single per-noun gate** below (not a separate prompt): a missing or fake-consumer
reciprocal is a pre-flagged row the human rules on there, and a `Fail` routes to the
same escalation as the revisit walk.

A green list/read endpoint test does **not** satisfy this — it proves the verb,
not a consumer surface a user actually reaches the instance through.

**Threat-model consistency (data-class drift).** Where the plan wrote a
`docs/plans/<slug>/threat-model.md`, cross-check its **Secrets & Data-Classes**
table against the §6.3 closure for each noun walked above. The threat model is a
**read-only re-projection** — its data-class must equal the closure's. A mismatch
means the read-only contract was violated (a data-class was downgraded in the threat
model to dodge a governance reciprocal — the §6.3.4 risk made real): record it as a
`Fail` and escalate to `/core-engineering:ce-plan` (the closure owns the data-class;
`/core-engineering:ce-verify` never resets it). This is a mechanical equality
check: report and route a mismatch; never ask for a verdict on it.

**Interaction-contract consistency (re-projection drift).** Where the plan wrote a
`docs/plans/<slug>/interaction-contract.md`, cross-check its rows against the upstreams
they re-project — each **Behavioural-Protocol Invariant** row's shared noun against the
§6.3 closure (the data-class it touches must equal the closure's, never re-assigned here),
and each edge against a real §8 Journey-Map / §10 Dependency-Flow producer→consumer
pairing. A row that re-assigns a data-class, invents an edge the plan never traced, or
re-cuts a boundary means the read-only contract was violated: record it as a `Fail` and
escalate to `/core-engineering:ce-plan` (the plan owns the edges and the closure;
`/core-engineering:ce-verify` detects drift, never re-binds the contract). This is a mechanical consistency
check, not a judgment call — whether a built feature *honours* its `[CONTRACT: IC-NNN]`
obligation is that feature's own EARS / test-case coverage, walked above. Like
the threat-model check, report and route a mismatch without a verdict prompt.

### Noun disposition

Render the full edge/evidence table. Demonstrated clean edges are recorded
without confirmation. Mechanical re-projection mismatches are recorded as Fail
and routed directly.

If an observed edge is `Fail`, `uncertain`, or `manual:judgment`, print
`Gate N of M — Noun <name>` and ask only about those rows, each independently,
with evidence, basis, and cost-if-wrong. If no such row exists, the noun passes
without a gate.

The noun result is the AND of demonstrated edges and human-resolved flagged
rows. Any Fail escalates; Blocked remains not verified.

**Escalation.** A missing or duplicating revisit/amend surface is not a code bug
to patch here — a reciprocal obligation was never owned by any feature. Escalate
**up** to `/core-engineering:ce-plan` (see Escalation).

---

## Stage 2.6 — Surface-Removal Confirmation Walk

The build-evidence mirror of Stage 2.5 for the plan's **§6.4 Surface-Removal
Closure**: where 2.5 confirms a noun the plan *writes* got a real revisit surface,
2.6 confirms a surface the plan *breaks* shipped its continuity. Brownfield only.

**Trigger (machine-detected).** For each `implemented` feature, detect a broken
existing surface from built artifacts — a route/handler/exported-signature/event-
schema/CLI-flag/config-key the Stage 1.2 codebase profile recorded as shipped but
that no longer responds in its old shape (a deleted handler, a renamed export, a
changed event field). If none fire, record this stage `N/A`.

**Confirm the disposition shipped.** For each detected break, read the plan's §6.4
closure row and confirm the continuity disposition actually shipped:

- **`deprecate:`** — the OLD surface must still respond (drive it with its modality:
  old route returns 200 / deprecation header, old export still importable) until
  `removed_by` is implemented.
- **`shim:`** — the migration shim / redirect must carry an old-shape call onto the
  new surface.
- **`hard-break:`** — confirm the break is the consented one recorded in §13 Notes,
  not an undisclosed extra break.

Record a demonstrated Pass without a question. For `Fail`, `uncertain`, or
`manual:judgment`, print `Gate N of M — Surface removal <name>` with evidence
and ask only for disposition (`Fail` / `Blocked`, or `Pass` when contrary
evidence is supplied). A Fail—an old surface gone without its window/shim, or
an unconsented hard break—escalates to `/core-engineering:ce-plan`.
