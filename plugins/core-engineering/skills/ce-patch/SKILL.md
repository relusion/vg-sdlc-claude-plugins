---
name: ce-patch
description: |
  Make a genuinely-small change on a lightweight lane — the plan→spec→implement spine folded for n=1, admitted only via the on-disk Patch Charter and gated by a diff lint; graduates to /ce-plan when it proves big; never auto-commits.
  Triggers: a small/minor change, one-file edit, or quick fix without full ceremony. Multi-feature/contract/schema work → /ce-plan.
argument-hint: "[change description] [--express]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion, Skill, Task
disable-model-invocation: true
---

# Patch

**Invocation input:** Change requested: $ARGUMENTS


Make a small change to an existing project — **the spine folded for one bounded
change**, not a hole cut in it. A patch drops the repo-wide codebase profile, the
multi-feature plan directory, and five of the seven interactive gates; it keeps
**every discipline** — test-first, EARS criteria, a lint-checked artifact, human
consent, evidence-bound verification, and the locks — running in miniature.

The one idea that makes the fold honest: **the decision to go light is itself one of
the framework's four primitives — a consented gate, a recorded artifact, an on-disk
check, and an escalation path.** Lightness here means *fewer context boundaries and
fewer round-trips, never fewer artifacts or fewer disciplines.* A "small" change that
turns out to be big does not slip through — the **Scope Lock** graduates it into
`/ce-plan`, exactly the way every other lock in the toolset escalates
up rather than expands.

**The express fold** is the featherweight version of this same fold: when a change is
so small that the mechanical `patch-lint --express` screen (E1–E4) auto-passes — ≤ 2
files, no cross-feature collision, no reviewer-trigger surface, no dependency manifest —
the lane runs a test-first edit behind **one combined gate** and records a single
ledger line, with **no spec artifacts**. It is a *mode of `/ce-patch`*, not a separate
skill: it inherits the Charter, the Lock, and the lint for free. Any screen FAIL falls
the change back to the full lane below — express is **refused, never shrunk**.

## Runtime Inputs

- **Change request (required):** a free-text description of the small change
  (e.g. *"rename the Save button to 'Save changes'"*, *"add a `--quiet` flag to the
  export CLI"*). Provided by the invocation or the user's request.
- **Target files (optional):** the file(s) the user already knows are involved —
  used to seed the scoped probe.
- **Loaded (read-only):** the named files and their direct callers (Grep), the
  project's build / test / lint commands, `docs/plans/vc-policy.md` if it exists,
  and `docs/plans/plans.json` if it exists (to register the patch and to check
  cross-feature ownership for C4). **No repo-wide codebase profile** — that is the
  ceremony this lane exists to avoid.

## Preconditions

- A git repository (the `--post` diff gate compares against a recorded base ref). If
  the target is not a git repo, say so and route to the full spine — the lane's
  build-evidence gate cannot run without a diff.
- Build / test / lint commands are discoverable, or the human supplies them.
- `patch-lint.py` (this skill's `scripts/`) is runnable, or the Patch Charter is
  checked by hand **loudly** (see *Substrate Fallback*).

## Execution Contract

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive gate; compute M from the gates that actually fire this run, never a hardcoded constant.

1. **Admission is the gate.** No code is touched until the **Patch Charter** (C1–C7)
   passes and the human consents to the eligibility lease (Stage 0). A change that
   fails any clause is **refused**, not shrunk to fit — it routes to `/ce-plan`.
2. **Human gates: two on the full lane, one on the express fold, never zero, never
   seven.** The full lane holds the **Eligibility Gate** (Stage 0) and **Final
   Acceptance** (Stage 4). The **express fold** collapses those into **one combined
   consent+acceptance gate** — its floor is **one**, and that floor is legitimate
   *only because* the mechanical `patch-lint --express` screen (E1–E4) is its
   precondition: any screen FAIL falls the change back to the full two-gate lane. A
   gateless write to code would break the framework's first invariant; the floor is
   never zero.
3. **Honor the Scope Lock** (below). The frozen file set is the boundary; the lane
   may narrow within it, never widen. A breach graduates to `/ce-plan` and stops.
4. **The gates are external, on-disk checks** — `patch-lint.py` over the eligibility
   lease and over the **actual diff**, run by a process that did not write the code.
   Substrate-independent: they run whether implement is spawned or in-context.
5. **Maintain traceability:** Scope item → Acceptance Criterion (EARS) → Test Case
   (dual-tagged) → Task. No orphans. The same `spec-lint` invariants the spine
   enforces.
6. **Version control:** **read-only on `vc-policy.md`** — the lane never establishes
   the repo's VC policy (that is the spine's, owned by `/ce-implement`). If a policy
   exists, honor it; if absent, default to **no commit** — leave the reviewed diff
   in the working tree for the human. **Never** push, open PRs, merge, or commit to
   the human's branch.
7. **Close the loop:** write `verification.md`; register the patch in `plans.json`
   with `origin: "patch"`; append the metrics line.

## The Patch Charter — what "small" means, checkably

A change is patch-eligible **only if every clause is YES with cited evidence.**
Indeterminate on any clause = NO = route to `/ce-plan`. The human consents to all seven
at the Eligibility Gate (the lease *is* the attestation); what differs is **how much
the script can independently re-check** so the human's judgment isn't the only thing
standing between a "yes" and reality:

- **Exactly re-checked** — C1, C4 (and C1 again at post): the agent writes the claim, the script verifies it against ground truth and overrides a wrong "yes".
- **Best-effort backstopped** — C2, C5: high-recall-but-not-exhaustive diff heuristics (see Honest Limitations) — they raise the floor, not prove the negative.
- **Attestation only** — C3 (advisory at post, never a gate), C6, C7: `attested_by: human` is required; the agent may not self-certify.

The honesty move is naming which is which — never dress a judgment call as an on-disk
proof.

| # | Clause | Disqualifier | Verified by |
|---|---|---|---|
| **C1** | **Bounded surface** | touches files in > 1 module, or more than the file cap, or cannot be localized to an enumerable file set | **Mechanical** — `patch-lint` counts `frozen_files` vs the cap (and the diff vs the lease at post) |
| **C2** | **No new durable noun** | adds/alters a schema, migration, persisted file/format, queue; any `db`/`event`/`iac` test-case modality | **Human-attested + two-ended backstop** — *pre*: no persisted-store modality TC (exact); *post*: a **high-recall, best-effort** heuristic over the diff (will miss unrecognized idioms — see Honest Limitations) |
| **C3** | **No new interface/contract** | new public route/export/CLI flag/response shape another feature consumes | **Human-attested at Stage 0** (primary); an **advisory** new-surface signal at post — never gates. An ADR-class surface is the spine's |
| **C4** | **No cross-feature blast radius** | a touched file is owned by another feature's `tasks.json` `files`, or is shared infra imported widely | **Mechanical** — collision scan vs every other plan's `tasks.json` (exact); importer-count advisory |
| **C5** | **Reversible** | a destructive/irreversible op in the change | **Human-attested + backstop** — a **high-recall, best-effort** diff heuristic at post (DROP/DELETE/TRUNCATE/ORM-delete/fs-remove/rm -rf …) |
| **C6** | **No reviewer-trigger surface** | touches auth, secrets, payments, data-deletion, persistence, i18n, a11y | **Human-attested** — surfaced as an explicit material question |
| **C7** | **No open unknown** | a product/architecture question the human cannot answer in one round | **Human-attested** — surfaced as an explicit material question |

The seven verdicts, the file cap, the frozen file set, and the diff base are recorded
in `specs/00-<slug>/eligibility.json` with `decided_by: human` — the audited record
of the lightness lease. `patch-lint --eligibility` **re-computes** the mechanical
clauses (C1 cap, C4 collision) against the repo rather than trusting the recorded
"yes": the agent writes the claim, the script verifies it against ground truth.

## The Scope Lock — the frozen file set

The frozen file set (recorded in the lease) is the boundary. Three invariants — the
same one-lock brand `/ce-spec` and `/ce-implement` use, scoped here to the frozen file set:

- **Frozen.** Every task, test, and edit must stay within `frozen_files`.
- **Narrow, never widen.** The lane may defer something within the set as a recorded
  limitation, but never grow the set on its own.
- **A breach escalates and stops.** Needing a file outside the set, minting a durable
  noun, or changing a contract is a **Patch Conflict** — do not improvise around it.

`plan ← spec ← implement ← patch`: a patch is the bottom of the same escalation
ladder. Because there is no layer above a patch yet, "up" means **graduation into
`/ce-plan`** — a one-way door (see *Graduation*).

## Graduation — escalate up, never expand

The lane refuses-or-promotes at three structural points; none is a judgment the
implementer makes alone:

1. **Pre-write refusal** (Stage 0). Any mechanical disqualifier (C1/C4) or
   human-attested NO (C2/C3/C5/C6/C7) → the change never enters the lane. Emit a
   `/ce-plan` seed and stop.
2. **Build-evidence revocation** (Stage 4). `patch-lint --post` scans the **real
   diff**: a durable noun written through an existing helper (H8), a touched file
   outside the lease (H9), or a destructive op (H10) the pre-scan missed → the lease
   is revoked. H9 is a **mandatory promotion**; H8/H10 are heuristic, so they are a
   *material finding* the human adjudicates (a real durable noun → promote; a
   confirmed false positive → recorded human acknowledgement, then Accept) — the same
   disposition `spec-lint` FAILs get in `spec` Stage 5.1.5.
3. **Mid-flight lock trip** (Stage 3). The implement agent needing an out-of-set file
   is a Patch Conflict → stop and promote.

**Promotion is lossless and auditable** — see *Promotion Procedure* in `${CLAUDE_SKILL_DIR}/stages.md` (flip the `plans.json` entry, carry the spec forward as the `/ce-plan` seed, quarantine any partial diff, and stop).

## Human-in-the-Loop — tiered

The lane does the legwork; the **human owns the two judgment gates.** Between them it
is autonomous.

- **Eligibility Gate (Stage 0) [material].** The human reviews the mechanical
  clause findings and **answers C6 and C7 as explicit `AskUserQuestion` prompts**
  (never bundled into one rubber-stamp accept), then consents to the lease. This is
  where lightness is granted.
- **Final Acceptance (Stage 4) [material].** *Accept / Revise / Promote.*
- **Express fold — one combined consent+acceptance gate (Stage E) [material].** When
  the mechanical `patch-lint --express` screen passes (see *The Express Fold* in
  `stages.md`), the fold collapses both full-lane gates into **one** `Gate 1 of 1`. It
  renders, in one place: the diff, the red→green test evidence, the E1–E4 mechanical
  findings, and **C6 and C7 as two explicit labeled attestation lines**, each with its
  scan evidence and its cost-if-wrong (evidence-first, R2). Options: *Accept (keep the
  diff, write one ledger line) / Revise (loop the edit) / Discard (`git restore` the
  touched files — destructive to the edit, say so) / Promote to full `/ce-patch`.*
  **Documented R3 deviation:** C6/C7 ride in this one gate rather than getting isolated
  prompts *because* the reviewer-trigger heuristic (E3) already came back clean and its
  evidence is rendered — evidence-first per R2. A heuristic hit would have forced the
  full lane, where C6/C7 get their own Stage-0 prompts. The isolation rule (R3) relaxes
  only under that mechanical precondition; R1/R2/R5 hold unchanged.

Approval is always an affirmative action — never silence or assumption. There is **no
autonomous mode**: the patch lane is interactive and is not invoked by `/ce-auto-build`
(that orchestrator owns whole plans, not single patches).

## Architecture — folded spine, externally gated

```
Stage 0 — probe + Eligibility Gate (THIS context, interactive)
  scoped read · patch-lint --eligibility --draft (H5 mechanical pre-screen: C1 cap + C4 collision)
  · C6/C7 questions · human consents + stamps the lease · patch-lint --eligibility (full, recorded)
  │   writes specs/00-<slug>/eligibility.json (frozen_files, base_ref, file_cap, 7 verdicts)
  ▼
Stage 1 — patch spec (THIS context writes the real ce-spec.md + tasks.json + features file)
  ▼
Stage 2 — [GATE] patch-lint --pre   (external: H1–H4 + H5 lease + H6 no persisted modality + H7 files ⊆ lease)
  ▼
Stage 3 — patch implement (a FRESH spawned agent; its ONLY spec input is the files on disk)
  per-task test-first (red→green) · Scope Lock · STOP & promote on a breach
  ▼
Stage 4 — [GATE] patch-lint --post  (external: H1–H4 + H5 + H8 no durable-noun + H9 diff ⊆ lease + H10 no destructive · C3 advisory)
  then: verification.md · human Accept / Revise / Promote
```

The decisive correction over a single self-policing context: the **implement agent
did not write the spec** (its only input is the files on disk) and the **gate is an
external script over the actual diff**. So the three checks that are otherwise "prose
a context talks itself out of" — durable-noun, scope-creep, surface-novelty — are run
by something that cannot rationalize them away. This mirrors auto-build's spawn
boundary at single-change scale.

**Substrate Fallback.** The implement spawn requires the **`Task`** tool. If it is
unavailable (or spawn-driving is unreliable), **fall back to implementing in this
context** — but the fallback loses **only** spec↔implement isolation. **Every other
discipline still runs:** the lease, both external `patch-lint` gates, test-first,
`verification.md`, the metrics line. Record the degradation loudly ("spec/implement
isolation relaxed — verified by the external diff gate"). Never silently fold a gate
away because spawning stopped.

---

## How to Run This Workflow

This skill is **staged**. `SKILL.md` (this file) is the orchestrator: it holds the
Execution Contract, the Patch Charter, the Scope Lock, Graduation, Tiered HITL, and
the Architecture diagram (the self-sufficient gate summary). The run flow and the
write-time artifact formats load on demand.

**The stage and reference files named below are bundled in this skill's own directory.** Read each at `${CLAUDE_SKILL_DIR}/<file>` — `${CLAUDE_SKILL_DIR}` is the environment variable that resolves to this skill's directory regardless of the current working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`) and read each file by its resulting absolute path; **never load a companion file by bare name** — in an installed plugin the working directory is the user's project, so a bare name finds nothing and triggers a filesystem search.

| Load this file | When | Holds |
|---|---|---|
| `${CLAUDE_SKILL_DIR}/stages.md` | at Stage 0, run to completion | Stages 0–4, the Promotion Procedure, and the Closing |
| `${CLAUDE_SKILL_DIR}/artifact-reference.md` | at the write / close steps | the artifact layout, the `eligibility.json` template, the `express-log.jsonl` schema, and the metrics format |

When invoked with `--express` (or when the human picks the express option offered at
the Stage-0 pre-screen because it came back clean), `stages.md` runs **The Express
Fold** instead of Stages 0–4.

To begin: load `${CLAUDE_SKILL_DIR}/stages.md` and start Stage 0 (or the Express Fold
when `--express` was passed).

---

## Escalation

Any Patch Charter failure, out-of-lease file, durable noun, contract/schema change,
or multi-step workflow graduates to `/ce-plan` as a Patch Conflict. Spec ambiguity
inside the lease routes through the folded `/ce-spec` stage; implementation failure
inside the lease stays in the folded `/ce-implement` loop until the retry/verification
rules require promotion.

## Honest Limitations

- **No decomposition, no reachability trace, no `shared-context.md`, no ADR trail.**
  A patch is one bounded leaf. Anything multi-feature, foundational, or
  boundary-bearing **must** go through `/ce-plan` — the lane physically
  refuses (C1–C7) rather than stretching.
- **No durable nouns the human or the heuristics catch.** C2 is enforced by the
  Stage-0 human attestation, an exact pre modality scan (H6), and a best-effort diff
  backstop (H8). It is **not** a proof: a durable noun written through an idiom H8
  doesn't recognize, inside a frozen file, can still slip — so this is "no durable
  nouns *as far as the attestation and the heuristics see*", not an absolute. Minting
  a schema, migration, queue, or persisted format owes revisit/amend/retire
  reciprocals, which is `/ce-plan` Stage 6.3 + `/ce-verify` Stage 2.5 territory.
- **C3 is human-attested, not mechanically gated.** C3 rests on the Stage-0
  attestation; the post scan only emits an *advisory* new-surface signal. A new
  route/export/response-shape added inside an already-frozen file is **not** blocked by
  the script — the human owns that call. ADR-worthy / Interface-Foundation surfaces are
  the spine's.
- **C2/C5 diff heuristics are HIGH-RECALL but NOT exhaustive.** H8/H10 recognize a
  finite pattern set (SQL DDL/DML, the common ORM/file/KV persistence + delete idioms);
  an op expressed in an unrecognized idiom **will** pass — a false negative in the
  dangerous direction. So C2-post / C5-post are best-effort backstops behind the human
  attestation, not guarantees. An over-fire is a *material finding* the human
  adjudicates (citing the line), never a silent pass; the manual checklist must also
  cover writes into `.gitignore`'d paths, which the diff scan cannot see.
- **Blast radius is verified to a bounded depth.** The probe greps direct callers +
  importer counts; deep transitive coupling (reflection, string-keyed lookup, DI
  registration, config consumed elsewhere) can be invisible. The post-diff H9 catches
  *file* creep, not *runtime* fan-out. `/ce-verify` on a promoted plan
  is the safety net.
- **The spawn boundary isolates code-authorship only.** The fresh implement agent
  can't collapse spec into implementation, and the external lint re-checks C1/C4 + the
  post heuristics against ground truth — but the **lane-applicability judgment** (the
  C2-pre / C3 / C5-pre / C6 / C7 verdicts, and the disposition of an H8/H10 finding) is
  owned by the single orchestrator context and is **not** independently re-verified by a
  second agent. The floor it raises is "the implementer didn't grade its own spec, and
  the diff was checked by a script", not "every judgment was double-reviewed".
- **No salami-slicing protection beyond a signal.** Three sequential patches can
  compose one un-specced feature; `/ce-retro`'s patch-promotion rate surfaces the smell,
  it does not block it.
- **The express fold trades the artifact trail for speed.** The featherweight
  `--express` mode writes **no `ce-spec.md`, no `tasks.json`, no `eligibility.json`, and
  no `plans.json` entry** — only one line in `docs/plans/express-log.jsonl`. So it has
  **no EARS traceability chain and no per-change spec**, and salami-slicing across
  several express edits is visible **only through that log's frequency + discard-rate
  signal**, never blocked. Anything that trips the E1–E4 screen is refused into the full
  lane, where the whole trail exists. C6/C7 are attested in the one combined gate (never
  auto-certified — the E3 mechanical floor is the precondition, not a replacement).
- **C4 protection is near-zero in greenfield.** With no plans yet there are no
  `tasks.json` `files` arrays to collide with; the importer-count advisory is the only
  signal. Highest value in mature, planned repos.
- **Two human gates, never zero.** A patch always costs the Eligibility consent + the
  Final Acceptance — the floor is two by design (see Execution Contract item 2).
- **Shares the model's blind spots.** Test-first catches what the tests express; an
  error shared by the implementation and its tests can still pass green — the same
  limit every implementing skill carries.
