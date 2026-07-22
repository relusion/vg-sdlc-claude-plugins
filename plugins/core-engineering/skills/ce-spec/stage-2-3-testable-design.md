# Feature-Spec Workflow — Stages 2–3: Make Scope Testable and Design Against the Codebase

Stage file for the `spec` skill (orchestrator: `SKILL.md`). Load this file after Stage 1 is complete.

**Next:** when Stage 3 is complete, load `${CLAUDE_SKILL_DIR}/stage-4-5-tasks-write.md`.

---

## Stage 2 — Make Scope Testable  *(Gap 2)*

### 2.1 Acceptance Criteria — EARS

Convert each Scope item, plus the Validation Target, into acceptance criteria
written in **EARS** (Easy Approach to Requirements Syntax). One grammar covers
every feature type — pick the pattern that fits each requirement:

| Pattern | Template | Use for |
|---|---|---|
| Ubiquitous | The `<system>` shall `<response>`. | An always-true property |
| Event-driven | When `<trigger>`, the `<system>` shall `<response>`. | A response to an event |
| State-driven | While `<state>`, the `<system>` shall `<response>`. | Behaviour during a state |
| Unwanted behaviour | If `<condition>`, then the `<system>` shall `<response>`. | Errors and failure modes |
| Optional | Where `<feature>`, the `<system>` shall `<response>`. | A conditional capability |

Walk the patterns as a completeness check: every event has its trigger named,
every relevant state is covered, and **every failure mode has an
unwanted-behaviour criterion** — error handling is a stated requirement, not an
afterthought.

#### Governance Reciprocal Criteria

When this feature owns a durable noun whose plan **Stage 6.3** closure row
dispositions a governance reciprocal `owned-by:` this feature — `retain`,
`export`, or `erase` — that obligation is a stated requirement, not background
intent. Read the closure row's **data-class** and emit a criterion that *drives*
the owning surface, so the reciprocal gets a real consumer the build is held to:

- **`retain`** — *State-driven:* "While a `<noun>` is older than `<N days>`, the
  system shall `<expire / purge / archive>` it." The policy names a real number, not
  "eventually"; an enforcing job/criterion makes it `auto`-checkable.
- **`export`** — *Event-driven:* "When a subject requests their data, the system
  shall return every `<noun>` attributable to them in `<format>`." Tag `auto` —
  shape and completeness are checkable.
- **`erase`** — *Event-driven:* "When a subject erases their account, the system
  shall remove (not soft-hide) every `<noun>` attributable to them." Plus an
  *Unwanted-behaviour* criterion: "If a `<noun>` survives an erase, the conformance
  check shall fail." A `sensitive` data-class also carries the reviewer's
  security-criterion obligation from §2.1.

These are checkable obligations, so tag them `auto` or `manual:harness-gap` — never
`manual:judgment`. A governance reciprocal the plan marked `owned-by:` this feature
with **no** criterion driving it is a coverage gap §2.3 must surface, exactly as a
missing journey-step test case is.

EARS structures a requirement; it does not make it testable on its own. Each
criterion must still be **concrete, observable, and testable** — name real
values, never "gracefully" or "quickly". Reviewer-triggers must each be covered
by a criterion (e.g. a security criterion when the feature handles
security-sensitive data — formalized below), and measurable non-functional
targets — latency, throughput, limits — belong here as ubiquitous or
state-driven criteria with real numbers.

#### Security Criteria

For `plan_mode: single-feature-minimal`, `IC-NNN`, governance-reciprocal, and
cross-feature Journey obligations are `N/A by construction`; do not manufacture
their absent full-plan files or ids. `TZ-NNN` is different: read it from the
minimal plan's inline Security Projection and apply the same security-criterion
rules below. If the real scope crosses a trust boundary not represented there,
introduces shared durable state, or otherwise needs a new plan-owned obligation,
route to `/core-engineering:ce-plan` and stop before drafting criteria.

When the plan's `threat-model.md` assigns this feature one or more `TZ-NNN`
threat-ids (its **Per-Feature Security Obligations** block — a feature that crosses
a trust boundary or owns the security / secrets surface), each is a **stated
requirement**, not background diligence — exactly as a governance reciprocal is.
Read the threat-id's `surface_kinds` and emit an EARS criterion that *drives* the
defense, marked **`[SECURITY: TZ-NNN]`** on the AC's heading line itself (e.g.
`### AC-3 — Reject unauthenticated reads  [SECURITY: TZ-002]`) — spec-lint H5 reads
the marker from the heading, not the criterion body — so it traces:

- **injection** — *Unwanted-behaviour:* "If a request carries `<SQL / command /
  template metacharacters>`, then the system shall `<reject / parameterize / escape>`
  it."
- **authz** — *Unwanted-behaviour:* "If an unauthenticated or unauthorized principal
  requests `<resource>`, then the system shall deny with `<status>`." (the §6.3
  access-mode says *who may*; this says the system *enforces* it.)
- **secrets** — *Ubiquitous:* "The system shall never log or return `<secret>`," plus
  an *Unwanted-behaviour* criterion a conformance check can assert.
- **validation** — *Event-driven:* "When input crosses `<the documented boundary>`,
  the system shall validate it against `<schema / allowlist>` before use."

Tag each security criterion's test cases `auto` or `manual:harness-gap`, **never
`manual:judgment`** — "is it secure?" *is* checkable (a rejected payload, a 401, a
secret absent from logs); deferring it to judgment is the same dodge §2.1 forbids for
governance reciprocals and conformance. A `sensitive` data-class with **no** threat-id
of its own (no boundary it owns) is an **advisory** the threat-model already flagged —
surface it, but it is not a hard obligation here (*surface, don't force*).

The `[SECURITY: TZ-NNN]` marker is what the spec-lint **H5** gate reads (§2.3): a
feature the threat-model assigns a `TZ-NNN` must carry an AC marked for it, or the
obligation is **consent-excluded in the plan** — never silently dropped. This turns
the security-criterion obligation §2.1 has always named into a *mechanically enforced*
one, the Veracode-flatline fix: security injected at the spec, not hoped from the
generator.

#### Interaction-Contract Criteria

When the plan's `interaction-contract.md` assigns this feature one or more `IC-NNN`
obligations (its **Per-Feature Interaction Obligations** block — a behavioural-protocol
invariant on a cross-feature edge / shared noun, or an architecture-determining NFR),
each is a **stated requirement**, not background diligence — exactly as a `TZ-NNN` is.
Read the obligation's `kinds` and emit an EARS criterion that *pins* the guarantee,
marked **`[CONTRACT: IC-NNN]`** on the AC's heading line itself (e.g.
`### AC-4 — Dedupe replayed order events  [CONTRACT: IC-003]`) so it traces:

- **idempotency** — *Unwanted-behaviour:* "If a message / retry is redelivered, then the
  system shall apply its effect at most once (dedupe on `<key>`)."
- **delivery / ordering** — *Event-driven:* "When the consumer receives events for one
  `<entity>`, the system shall process them in `<key>` order / tolerate at-least-once
  redelivery."
- **retry / timeout** — *Unwanted-behaviour:* "If the producer call times out, then the
  system shall retry with backoff / surface a failure without double-applying."
- **concurrency** — *Unwanted-behaviour:* "If two features write `<shared noun>`
  concurrently, then the system shall reject the stale write / serialize on `<version>`."
  (the §6.3 access-mode says *who may*; this says the system *enforces* the concurrent-write
  posture.)
- **a numeric NFR** (latency / throughput / concurrency / tick-rate) — *Ubiquitous /
  state-driven:* "The system shall meet `<the cited target — e.g. p99 < 200ms at 10k
  msg/s>`," with the real number from the contract's `Target`.

Tag each interaction criterion's test cases `auto` or `manual:harness-gap`, **never
`manual:judgment`** — a behavioural guarantee *is* checkable (a duplicate suppressed, an
out-of-order event rejected, a stale write 409'd) and a numeric target *is* measurable. A
numeric-NFR criterion's realistic harness is a load/perf run; `/core-engineering:ce-probe-perf`
is the tool that *proves* a numeric breach (it records, doesn't block), so the criterion
degrades to `manual:harness-gap` when no load harness is available — never `manual:judgment`.

**Deliberately attestation, not lint (unlike `[SECURITY]`'s H5).** No machine signal can
prove an AC actually captures `exactly-once` or `p99 < 200ms`, so there is **no H5-style
hard gate** for `IC-NNN` — coverage is **human/agent-attested** (the §2.3 coverage bullet
and the §5.3 checklist line), exactly like the §3.5 SHARED reconciliation and the §3.6
cross-feature-flow call. An assigned `IC-NNN` with no `[CONTRACT: IC-NNN]` AC is a gap to
surface or **consent-exclude in the plan** — never silently dropped; whether the criterion
is *substantively adequate* (does it really pin the invariant) stays the human's.

#### Interface Conformance Criteria

When this feature exposes a surface that has an **Interface Foundation** — the
plan records a matching Boundary-Owner (`design-system` — or another foundationed
surface's owner), an existing foundation, or provided conventions (plan
Stage 7.8) — it must **conform**
to that foundation's contract. Most of "looks good / well-formed" is *conformance*,
and conformance is **checkable** — so write it as criteria that *drive* the build,
not as judgment deferred to a reviewer.

Read the foundation's ADR (Stage 3.1) and emit conformance criteria for what the
contract makes objective:

- **`browser` / design-system** — *Ubiquitous:* "The UI shall render interactive
  elements using the shared token primitives (ADR-NNNN) — no color or spacing
  value outside the token scale." *Unwanted-behaviour:* "If a component hardcodes
  a color outside the palette, the conformance check shall fail." Plus WCAG-AA
  contrast and responsive breakpoints — `manual:harness-gap` (browser-checkable).

*(Another foundationed surface conforms the same way — e.g. an `http` api-contract
foundation adds `auto` criteria for the error envelope, status-code map, and
pagination contract.)*

Tag these `auto` or `manual:harness-gap` — they are checkable. Reserve
`manual:judgment` (§2.2) for the genuinely subjective residue only: does the UI
*feel* polished, is the API *ergonomic*. This split is what makes "good-looking /
well-formed" a built-against contract instead of an after-the-fact verdict.

**If this feature *is* the interface-foundation owner**, its Scope and task list
must include the **conformance checker** — the lint rule / contrast or contract
test, wired into the project's lint or test command — not just the tokens or
contract. A foundation that ships the contract but no checker leaves every
downstream `auto` conformance criterion unrunnable; the checker is what makes the
contract enforceable, so it is in-scope for the foundation feature by definition.

#### Surface-Quality Criteria

When a Scope item renders a **user-facing surface that composes more than one
element** onto a shared region — a screen, list, board, dashboard, map, or a
`canvas`/WebGL scene — its *assembled* readability and playability is a **stated
requirement**, not deferred taste. This is the inter-element sibling of Interface
Conformance: conformance checks each element against the token/contract scale; this
checks the **composition** a first-time user actually sees. It is **not** gated on an
Interface Foundation — a surface with no foundation owes these criteria too, and a
foundation's "spacing" is the token gap-scale, not non-overlap.

Author the surface's **Surface Quality Contract** — the user-standpoint properties
that matter for *this* surface — then emit the functional ones as EARS criteria:

```text
serves:             <the goal a first-time user comes to this surface to accomplish>
must-be-legible:    <content that MUST be readable>
primary-affordance: <the primary action that MUST be discoverable>
density:            <expected element count / crowding tolerance>
must-not:           <surface-specific broken states: overlap, clip, off-screen>
taste-line:         <what is explicitly aesthetic preference here>
```

Emit at minimum, each marked **`[SURFACE]`** on the AC's heading line (e.g.
`### AC-5 — Objects stay individually distinguishable  [SURFACE]` — spec-lint **A4**
reads the marker from the heading, as H5 reads `[SECURITY]`):

- **non-overlap / in-bounds** — *Ubiquitous:* "The system shall lay out `<elements>`
  so no two non-stacked elements' rendered bounds overlap beyond `<tolerance>`, and
  none renders outside the surface bounds."
- **readability under load** — *Unwanted-behaviour:* "If `<N>` elements share a
  `<surface>`, then the system shall space/reflow them so each stays individually
  distinguishable."
- **primary-affordance / goal-service** — where the surface has a primary action:
  *Ubiquitous:* "The system shall render `<the primary affordance>` visible and
  unoccluded on first paint."

Tag these `auto` where a geometric assertion can drive them — an AABB/bounding-box
or off-viewport check **is deterministically headless** (geometry, not pixels) — and
`manual:harness-gap` otherwise (the **Surface Critique** pass renders the finding
from the screenshot). **Never `manual:judgment`** — an unreadable assembled surface
is a *functional* defect, not "art fidelity / taste"; do not mis-file it as judgment
to dodge the check, the same dodge §2.1 forbids for conformance and security. Reserve
`manual:judgment` for the contract's `taste-line` residue only (palette, brand feel).

The full discipline — the six-dimension rubric, the functional-vs-taste classifier,
the three-tier evidence model, and the canvas-vs-DOM honesty — is defined in
**`${CLAUDE_SKILL_DIR}/surface-critique.md`**; downstream stages (`/core-engineering:ce-implement`,
`/core-engineering:ce-verify`, `/core-engineering:ce-auto-build`, the UX skills) critique the running surface against the
contract authored here.

### 2.2 Test Cases

For each acceptance criterion, enumerate the test cases that prove it — happy
path, edge cases, and failure modes. Each test case states:

```text
TC-n  (proves AC-x) — modality: <tool class> · verification: auto | manual:harness-gap | manual:judgment
  Realizes:        Journey <name> step <n>   (when the test case comes from a journey observable)
  Preconditions:   …
  Action / input:  …
  Expected result: <observable>
```

Every test case carries **two independent tags**:

- **`modality`** — the **tool class** that drives it: `browser · http · cli · sdk · event · iac · db · manual` (the plan's journey vocabulary). When a test case realizes a journey step, **inherit that step's modality** from the plan's Journey Map (Stage 6 / section 8); otherwise pick the modality that fits the criterion's surface. `manual` means no tool can drive it.
- **`verification`** — **who renders the verdict** (below).

Tag each test case's **verification mode**:

- **`auto`** — the default. The expected result is deterministically checkable by
  the project's test harness (logic, data, API responses, errors, element
  presence, e2e flows).
- **`manual`** — the expected result can't be checked by the project's unit harness. Tag the **kind**:
  - **`manual:harness-gap`** — objectively checkable, just not by the unit harness (needs a browser, e2e, a real external system, or a device). A tool *can* render the verdict — e.g. a browser MCP driving the UI. These are browser-verifiable, so an unattended run can confirm them with evidence.
  - **`manual:judgment`** — needs human judgment no tool can render (genuine aesthetic taste / ergonomic feel, copy tone). Note: most "looks good / well-formed" is *conformance* — uses the shared tokens or contract, contrast, spacing, status codes — which **is** checkable; capture that as `auto` / `manual:harness-gap` **conformance criteria** (§2.1), and reserve `manual:judgment` for the subjective residue only. Likewise an *assembled-surface* defect — overlap, clipping, off-screen content, illegible density, an occluded primary affordance — is **Surface-Quality** (§2.1), checkable `auto` (geometry) or `manual:harness-gap` (the Surface Critique pass reads the screenshot), **not** judgment. Do not label conformance *or* surface-quality as judgment to dodge writing the check.
  Every `manual` case carries its kind and a one-line reason.

Default to `auto`. `manual` is a justified exception, not an escape from writing a
hard test. A `manual` case needs no special format — its preconditions / action /
expected double as the human's check script, so write them as runnable
instructions.

**How the two tags relate.** `modality: manual` ⇒ `verification: manual:judgment` (no tool, pure judgment). `browser` / `event` / `iac` are usually `manual:harness-gap` (a tool *can* render the verdict, just not the unit harness) — or `auto` if wired into automated e2e. `http` / `cli` / `sdk` / `db` are usually `auto`, or `manual:harness-gap` when they need a live external system.

**Tool fallback (never silent).** The modality is the tool class a verifier *should* use; if that harness is unavailable at verify time, the case degrades to `manual:harness-gap` — a human runs the documented preconditions / action / expected. Keep the modality as recorded; the degradation is loud, not a silent downgrade.

Test cases describe **what** to verify, not harness mechanics (that is Stage 3).

### 2.3 Coverage and Boundary Checks

- Every Scope item → ≥ 1 acceptance criterion.
- Every acceptance criterion → ≥ 1 test case.
- Every **journey step this feature owns** (the plan's Journey Map `Owned By` column = this feature's id) → ≥ 1 test case that asserts the step's expected observable and carries the step's modality.
- Every **governance reciprocal** the plan's Stage 6.3 closure dispositions `owned-by:` this feature (`retain` / `export` / `erase`) → ≥ 1 acceptance criterion and ≥ 1 test case (§2.1 Governance Reciprocal Criteria).
- Every **`TZ-NNN` threat-id** the applicable plan security source assigns this feature—the full plan's `threat-model.md` or the minimal plan's inline Security Projection—→ ≥ 1 acceptance criterion marked `[SECURITY: TZ-NNN]` (the **spec-lint H5** gate — H5 checks the marker's presence; auto-build auto-discovers the full threat model on the canonical spec dir, while the interactive gate passes `--threat-model` using `threat-model.md` in full mode or `feature-plan.md` in minimal mode) **and** ≥ 1 test case proving it (the per-AC test-case rule above; H5 does not itself check the test case — A2 advisorily flags an unproven AC). A genuinely-N/A obligation is consent-excluded or explicitly assessed negative in the plan (and under autonomous auto-build the spawned agent parks it instead — it cannot edit plan-owned security input), never silently dropped.
- Every **Scope item that renders a user-facing surface composing >1 element** (a screen / list / board / map / `canvas`) → ≥ 1 Surface-Quality criterion marked `[SURFACE]` (non-overlap / in-bounds / readability, §2.1 Surface-Quality Criteria) with an `auto` geometric or `manual:harness-gap` test case. This is **human/agent-attested**, like the §3.5 SHARED reconciliation — spec-lint **A4** *advisorily* flags a declared `browser` surface carrying no `[SURFACE]` AC, but cannot prove the criterion is right or complete (no "surface renders multiple elements" signal exists to hard-gate; readability is un-lintable from markdown).
- Every **`IC-NNN` obligation** the plan's `interaction-contract.md` assigns this feature → ≥ 1 acceptance criterion marked `[CONTRACT: IC-NNN]` **and** ≥ 1 test case proving it. This is **human/agent-attested** (like the §3.5 SHARED reconciliation and the `[SURFACE]`/A4 advisory) — no machine signal can prove an AC captures a behavioural invariant or a numeric NFR, so there is **no H5-style hard gate**; an assigned `IC-NNN` with no `[CONTRACT:]` AC is a gap to surface or consent-exclude in the plan, never silently dropped.
- No criterion or test case touches an Excluded item or unplanned scope.

In `single-feature-minimal` mode, record only the Journey Map, governance
reciprocal, and `IC-NNN` rows above as `N/A by construction`; the Scope chain and
all applicable reviewer-trigger/surface checks still run. For `TZ-NNN`, consume
the inline Security Projection: every assigned id must have the criterion/test
coverage above, while an explicit empty `threat_ids` list is an assessed
negative rather than N/A inferred from feature count. A newly observed boundary
or obligation contradicts that plan input and routes to `/core-engineering:ce-plan`
before the spec is approved; it is never an implicit waiver.

Report the check result.

### 2.4 Review  [tiered]

Criteria or test cases that encode a product decision are material; mechanical
ones are routine. The human reviews wording and approves — including each
`manual` classification: confirm the case genuinely cannot be automated rather
than being a skipped test.

---

## Stage 3 — Design Against the Codebase  *(Gap 3)*

### 3.1 Read the Codebase and Binding Decisions

Read the actual files: the areas this feature will touch, the hard-dependency
specs or built code (real interfaces), existing patterns and conventions, and the
test harness.

Also read the **binding architectural decisions**. For a full plan, use the
Resolved Project Decisions ledger in `shared-context.md` as the index. In
`single-feature-minimal` mode, use only ADRs explicitly cited by
`feature-plan.md` or applicable repository rules; do not scan the whole ADR
directory to compensate for the intentionally absent ledger. Open only ADRs
whose decisions bear on this feature's surfaces or cross-cutting concerns.
Consider only ADRs with `Status: accepted`; skip superseded ones.

### 3.2 Produce the Design

- **Files** to create and modify (exact paths).
- **Integration points** — which dependency interfaces are used, and how.
- **Patterns and conventions** to follow.
- **Accepted ADRs** that constrain this feature — the design must not contradict one.
- **Interface foundation** — if this feature exposes a foundationed surface (`browser`, or another live surface), the design consumes the shared tokens/primitives or contract from its ADR; no ad-hoc styling. Name the primitives/contract elements it uses. **If this feature *is* the foundation owner, the design includes the conformance checker** the contract is enforced by.
- **Data / schema** changes. For each persisted schema, event, message, or wire/API contract this feature touches, classify the shape **NEW** (introduced here) or **SHARED** (already read or written by an earlier *shipped* feature). Mark each SHARED shape this feature **modifies** — it carries forward into §3.5.
- **Test harness mapping** — where each test case's test will live; fixtures.
- **Pitfalls** from the full plan's `shared-context.md`, or the minimal plan's
  inline Codebase Profile / Notes, that apply.

### 3.3 Boundary Reconciliation

If reading the real code shows the planned boundary is wrong — the feature is
larger than planned, Scope is infeasible as bounded, an Excluded item is actually
required, a plan assumption is false, or a hard dependency is missing — raise a
**Boundary Conflict** and present it as a *material* decision.

- **Local fix** (this feature's Scope, Excluded, surfaces, unknowns, validation
  target): on human approval, edit `features/<id>.md` for a full plan. In
  `single-feature-minimal` mode edit only the `## 4. Single Feature` block and
  append the `revised_by: spec`, date, and reason stamp to its Notes. Log the
  change in the Boundary-Conflict Log, then re-enter Stage 1 (if unknowns
  changed) or Stage 2 (if criteria changed).
- **Structural fix** (dependencies, IDs, ship order, other features): the spec
  cannot make it — escalate to `/core-engineering:ce-plan` and stop.

Never expand Scope to absorb a conflict.

If the feature genuinely cannot be designed within an **accepted ADR**, that is an
**ADR conflict** — the same discipline applies. The spec never silently overrides
an ADR: present it as a *material* decision and escalate, since superseding an ADR
is a cross-feature, human-owned call.

### 3.4 Design Decisions  [tiered]

Present genuine design tradeoffs as material decisions; mechanical choices are
routine. The human approves the design. If an approved design decision is
architecturally significant and cross-feature, promote it to an ADR (see
*Architecture Decision Records* in `SKILL.md`).

### 3.5 Shared-Shape Change Reconciliation

For `plan_mode: single-feature-minimal`, record this check as `N/A by
construction`. If code inspection finds another feature, migration owner, or
planned consumer whose contract must change, the minimal shape is disproven;
raise the structural Boundary Conflict and route to planning rather than
running an in-place cross-feature reconciliation.

The write-side inverse of Interface Conformance (§2.1, §3.2): conformance makes a
feature *match* a shape it consumes; this makes a feature *reconcile* a shape it
**owns or shares** when an earlier shipped feature already depends on it. It is the
sibling of §3.3 — §3.3 reconciles a wrong **boundary** against the real code; §3.5
reconciles a **persisted shape change** against the real consumers.

For every SHARED shape this feature **modifies** (the §3.2 Data / schema marks), run
a **consumer-impact reconciliation** before the change can stand:

1. **Enumerate consumers** — read the real code and specs to list every other
   feature, migration, stored payload, or external client that reads or writes the
   shape. "None found" is only valid when the shape is genuinely NEW; a SHARED
   shape with zero enumerated consumers is a reconciliation gap, not a pass.
2. **Classify the change per consumer** — **additive** (a consumer compiled and
   correct against the old shape stays correct: new optional field, new event a
   consumer may ignore, widened accepted input) or **breaking** (a renamed/removed
   field, a narrowed or retyped value, a changed event contract, a required
   migration). Classification is a *judgment* call — when in doubt it is breaking.
3. **Disposition** — using the same vocabulary as §3.3:
   - **Additive only** → an in-boundary design change. Record it in the spec's
     **Shared-Shape Reconciliation** block (one row per consumer, `additive`), add
     a backward-compatibility acceptance criterion (an unwanted-behaviour AC over
     the old shape, §2.1), and continue.
   - **Breaking** → the change crosses into another feature's contract, so a single
     feature edit cannot make it. Raise it as a **Boundary Conflict** (the §3.3
     *structural* disposition): present it as a *material* decision, log it in the
     Boundary-Conflict Log, escalate to `/core-engineering:ce-plan`, and stop. The
     plan owns the migration, ship-order, and the consumers' adaptation — not this
     spec.

Never narrow or restate a SHARED shape's contract to make a breaking change *look*
additive, and never expand Scope to absorb the consumers' adaptation work. Like an
ADR conflict (§3.3), superseding a shipped shape is a cross-feature, human-owned
call — **escalate up, never expand**.

Record every SHARED-modify reconciliation in the spec's §5 Design under a
`shared-shape-modify` block (one per shape). The NEW-vs-SHARED split, the
additive-vs-breaking call, and the block's completeness are **human-attested** —
at the §3.4 design review and again at the Stage 5.3 Validation Checklist; the
spec stage carries no mechanical check for them.

**Under autonomous `/core-engineering:ce-auto-build`** the call cannot be human-attested in-dialog,
so any SHARED-shape modification **parks** with the affected shape, consumers,
per-consumer impact, and cost-if-wrong (spec *Autonomous Mode*). The end-review
routes it to `/core-engineering:ce-decide` or an interactive `/core-engineering:ce-spec`. The lack of a mechanical
check is exactly why the autonomous run cannot authorize the classification.

Because additive-vs-breaking is a **model-derived assertion with no mechanical gate**,
it must not ride through as a bulk §3.4 line — present each modified SHARED shape as its
**own evidence-first decision prompt** (HITL Gate Standard R2/R3):

```text
Decision [D-n] — <shape> change: additive or breaking?   [material]
Consumers (enumerated from real code/specs): <feature A reads field X; migration Y; …>
Per consumer:  <A — additive (new optional field) | breaking (renamed field)> …
If you call this additive but it is breaking: the change ships with only a back-compat
criterion and SKIPS the /core-engineering:ce-plan Boundary Conflict — a contract break to A's shipped code
with no migration owner.
Options:
  A. Additive — record the block + a back-compat AC, continue here.
  B. Breaking — escalate to /core-engineering:ce-plan as a Boundary Conflict and stop.
Recommendation: <A/B> — <reasoning>
```

A SHARED shape with zero enumerated consumers is **not** a pass — surface it as the
reconciliation gap step 1 names, never an empty Additive default.

### 3.6 Cross-Feature Flow Reconciliation

For `plan_mode: single-feature-minimal`, record `Cross-Feature Flow: N/A by
construction`. If the design actually spans another feature, do not attempt to
match an absent Journey Map: the minimal shape is disproven, so route to
planning and stop.

The **path-side** sibling of §3.5: where §3.5 reconciles a *shape* an earlier shipped
feature consumes, this reconciles a *flow* the plan never traced. §3.3 catches a wrong
**boundary** (new scope) and §3.5 a changed **shape**; neither trips when the design
wires steps that are **each already in-scope** into an **end-to-end sequence the plan's
Journey Map never traced** — a new *path*, not new *scope*. The Scope Lock is
single-feature and scope-keyed, so a new cross-feature path widens nothing and would
otherwise ship **untraced**: never reachability-checked at `/core-engineering:ce-plan`, never journey-walked
at `/core-engineering:ce-verify`.

After §3.2's design exists, run the check from its **Integration points**:

1. **Compose the realized flow** — name any **user- or consumer-traversable** end-to-end
   sequence this design now enables that spans **more than one feature** — the same unit
   the plan's Journey Map traces (a path someone walks or a consumer drives), *not* an
   internal helper call into a dependency interface.
2. **Match it against the plan's Journey Map** — a sequence is **traced** when a single
   Journey Map row (any feature's `Owned By`) already walks it end-to-end. A
   user/consumer-traversable sequence spanning **≥ 2 features** that matches **no** row
   is a **new cross-feature flow**.
3. **Disposition** — using the same vocabulary as §3.3:
   - **Traced** (or the feature realizes no cross-feature sequence) → in-boundary;
     record `Cross-Feature Flow: traced` / `N/A` in §5 Design and continue.
   - **New cross-feature flow** → journeys are **plan-owned**, so a single feature edit
     cannot mint one. Raise it as a **Boundary Conflict** (the §3.3 *structural*
     disposition): present it as a *material* decision, log it in the Boundary-Conflict
     Log, escalate to `/core-engineering:ce-plan` (which owns the Journey Map and its
     reachability trace), and **stop**. The spec **detects and hands up — it authors no
     journey.**

A purely internal call into a dependency interface that exposes no new traversable path
is an ordinary §3.2 integration point, **not** a new flow — do not escalate it. The
traced-vs-new-flow call is a model **judgment** with no on-disk gate (un-lintable from
markdown, like §3.5's additive-vs-breaking), so it must not ride through as a bulk §3.4
line — present it as its **own evidence-first decision prompt** (HITL Gate Standard
R2/R3):

```text
Decision [D-n] — cross-feature flow: traced or new?   [material]
Realized sequence (from §3.2 integration points): <feature A step → feature B step → …>
Journey Map rows matched: <none | "<journey> · steps i–k">
If you call this traced but it is a new flow: the path ships untraced — never
reachability-checked at /core-engineering:ce-plan, never journey-walked at /core-engineering:ce-verify.
Options:
  A. Traced / N/A — record in §5 Design, continue here.
  B. New flow — escalate to /core-engineering:ce-plan as a Boundary Conflict and stop.
Recommendation: <A/B> — <reasoning>
```

**Under autonomous `/core-engineering:ce-auto-build`** the traced-vs-new-flow call can't be human-attested
in-dialog, so the spec agent instead **returns** it as a *discrete material decision*
(spec *Autonomous Mode*): a `new flow` call **parks** (the §3.3 structural
escalation — the autonomous catch-all for any condition that would escalate to `/core-engineering:ce-plan`),
while a `traced` / `N/A` call **rides through as a named decision surfaced at the
end-review** (among the self-approved design calls it confirms), never a silent inline
record. As with §3.5, the no-mechanical-check property is exactly why *surfacing* the
call is the only backstop in both modes — interactive or autonomous.
