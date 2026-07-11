# ce-debug — Planned mode (a plan/spec owns the failing target)

Stage file for the `ce-debug` skill (orchestrator: `SKILL.md`). The Stage-0 mode
probe routed here because `docs/plans/plans.json` resolves the failing target to a
feature with a `specs/<id>/ce-spec.md` — the **contract** to diagnose against.
Load this file once the probe announces planned mode.

**Next:** this is the last file for a planned-mode run — the run ends with the
Closing block below.

---

## What planned mode is — and is not

Like its read-only siblings `/ce-verify` and `/ce-review`, debug **escalates, never
mutates**. What makes planned-mode diagnosis distinct:

- **vs `/ce-verify`** — verify *detects* that behavior regressed; debug *explains
  why*. Verify says "checkout step 3 fails"; debug says "because `applyDiscount()`
  at `cart.ts:88` mutates the shared cart."
- **vs `/ce-review`** — review proactively surveys healthy code for *unknown* latent
  issues across six lenses; debug reactively roots one *known, active* failure to
  a reproduced, confirmed cause — which neither verify nor review produces.
- **vs `/ce-implement`** — implement *fixes* (mutates code), and its `~3` per-task
  attempts are already aimed at that task's failing `auto` test. What it has no
  mechanism for is **reproducing and root-causing a failure that arrives from
  outside the task loop** — a `/ce-verify` regression, a `/ce-review` finding, a pasted
  stack trace — or one whose cause lies outside the current task's diff. Debug
  supplies that; it never touches code.
- **vs `/ce-spec`** — spec changes the contract; debug may *conclude* the contract is
  the culprit (correct code, wrong spec) and route there, but never edits it.

## Diagnose, Do Not Fix

The failing code and the spec are both **read-only** to this workflow. If the fix
looks trivial while you are in there — resist. Applying it here bypasses the
test-first, gated, traceable path `/ce-implement` enforces and the human-owned review
`/ce-spec` enforces. Debug's product is a *diagnosis that routes*, not a change.

The **recommendation** it emits stays inside debug's authority, scoped to the
cause's class: for a `bug` it may name the fix locus, the minimal approach, and the
**existing** test/AC that confirms it; for a `spec-gap` or `structural` cause it
names **the gap and its evidence only** — defining the new or revised contract (and
any new acceptance criterion) is the routed `/ce-spec` or `/ce-plan`'s call, never
debug's. That boundary is what keeps "escalate-up, by construction" true at the
recommendation layer, not only at the apply layer.

`plan ◄── spec ◄── implement ◄── { verify · review · debug }` — each escalates up
on conflict; none mutates a layer it does not own.

---

## Stage 0 — Load and Scope the Failure

The mode probe already resolved the plan + feature via `docs/plans/plans.json`.
Confirm feature state the same way the rest of the toolset does — `implemented` iff
`tasks.json` exists, every task `done`, and `verification.md` exists; else `specced`
if `ce-spec.md` exists; else `planned`. **Planned mode needs a spec** (the contract
to diagnose against): a `planned`-only feature has nothing to diagnose — say so and
point to `/ce-spec`.

Ingest and **restate the failure concretely**: which test / AC / verdict / finding
/ error, and the expected observable from the spec. Load the read-only inputs;
check `docs/plans/patterns.md` for a known pitfall matching the symptom.

**Scope checkpoint [material]:** *Proceed / Wrong feature / Abort.*

## Stage 1 — Reproduce

Reproduce the failure deterministically, driving it with the recorded command or
modality — the failing `auto` test's command, the `manual` case's
preconditions / action, or the journey step's modality from the verify report.
Capture exact evidence (test output, stack, response body, screenshot) to
`docs/plans/<slug>/evidence/DX-N.*`.

Record reproduction status:

| Status | Meaning | Effect |
|---|---|---|
| `reproduced` | fails deterministically here | proceed to localize |
| `intermittent` | fails sometimes | promote nondeterminism (race / ordering / time / external state) to a lead hypothesis, then localize |
| `unreproduced` | cannot trigger here | **stop** — record what was tried; route to the human as environmental / flaky / insufficient-info. Do **not** invent a cause. |

The reproduction is the evidence anchor: a root cause asserted without one is at
most `suspected`, and must say so.

## Stage 2 — Localize

Form 2–4 ranked hypotheses from the symptom, the diff since the feature's last
green (`git log` / `diff` / `blame`), the spec's expected behavior, and known
pitfalls. Narrow by **read-only probing**: read the suspect code plus one hop to
its call sites; compare actual behavior against the spec's expected observable;
vary inputs to the *existing* tests; optionally bisect history (consent-gated;
snapshot-and-restore per the Execution Contract — skipped under auto-build).

Converge on **one root cause** at `file:line` with a confidence:

- **`confirmed`** — the diff that introduced it is identified and explains the
  symptom, or the repro flips with the cause isolated.
- **`suspected`** — best-supported hypothesis, not proven; state what evidence
  would confirm it.

If genuinely indeterminate after **~3 narrowing loops**, stop and record the
narrowed candidates + the evidence that would decide — escalate to the human
rather than guess. (Debug adds no instrumentation — that would mutate code; a
cause needing live tracing stays `suspected`. See Honest Limitations.)

## Stage 3 — Classify and Route

Classify the cause into exactly one bucket and route it. The classification is
**material** — present it as a decision with the evidence.

| Root cause | Means | Route |
|---|---|---|
| Code violates a correct spec | **bug** | `/ce-implement <id>` — with the fix locus + approach |
| Code correctly implements a wrong / missing / ambiguous spec | **spec-gap** | `/ce-spec <id>` — name the gap; the new contract is spec's to define |
| Cause spans features, wrong boundary, or bad ship order | **structural** | `/ce-plan` |
| Not reproducible / environmental / flaky / external | **not-a-code-defect** | record; hand to the human — no code path |
| Recurring, novel pitfall worth remembering | — | suggest seeding `docs/plans/patterns.md` (out of band), alongside the primary route |

*The `bug` route's `<id>` is the feature that **owns** the fix. Usually that is the
diagnosed feature; for a bridge that outlived its built replacer it is the
**replacer's id** (mirroring `/ce-verify`'s escalation), not the
feature that surfaced the symptom.*

The diagnosis carries a **class-scoped recommendation** (per *Diagnose, Do Not
Fix*): for a `bug`, the fix locus + minimal approach + the existing confirming
test/AC, so the routed `/ce-implement` aims its attempts; for a `spec-gap` /
`structural` cause, the gap and its evidence only. Debug never applies it.

## Stage 4 — Write and Hand Off

Write `docs/plans/<slug>/diagnosis.md` per the template in `${CLAUDE_SKILL_DIR}/artifact-template.md`
(do not reconstruct it from memory) — cumulative across the plan's features: each
run appends a `DX-N` entry; prior ones stay. (Under auto-build, write the
per-feature `specs/<id>/diagnosis.md` instead.) Confirm, then point to the routed
skill.

**The artifact template named above is bundled in this skill's own directory.** Read it at `${CLAUDE_SKILL_DIR}/artifact-template.md` — `${CLAUDE_SKILL_DIR}` is the environment variable that resolves to this skill's directory regardless of the current working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`) and read the file by its resulting absolute path; **never load a companion file by bare name** — in an installed plugin the working directory is the user's project, so a bare name finds nothing and triggers a filesystem search. (`diagnosis.md`, `evidence/`, and everything under `docs/plans/` live in the user's project, not this skill — those paths stay as-is.)

**Metrics (best-effort, optional).** After writing, append a `stage-complete` line
(`stage: "debug"`) — plus, for a route that has one, an `escalation` line
(`escalation_type` one of `/ce-implement` · `/ce-spec` · `/ce-plan`; omit it for a
`not-a-code-defect` or `unreproduced` outcome) — to `docs/plans/<slug>/.metrics.jsonl`
per the `retro` skill's schema. Derive every field from data already
produced, label any token figure an estimate, and **never** let this block or fail
the diagnosis. It powers `/ce-retro`.

---

## Closing (planned mode)

```text
Diagnosed: <id> — <N> root cause(s) (<C> confirmed, <S> suspected, <U> unreproduced)
Cause:     <file:line> — <class>
Route:     <skill>
Diagnosis: docs/plans/<slug>/diagnosis.md
```

Debug never patches — the routed skill applies the fix. Point to it
(`/ce-implement <id>`, `/ce-spec <id>`, or
`/ce-plan`). Never commit, push, or deploy.

**For a `bug` route, print the exact resuming invocation** so the fix continues without hand-carried context — `/ce-implement <plan-slug>/<id>` (the qualified form) — and name the diagnosis path (`docs/plans/<slug>/diagnosis.md`). `/ce-implement` now **auto-detects** that diagnosis in its Stage 0: when the routed feature matches and the class is `bug`, it loads the `file:line` fix locus + confirming test/AC as the **lead** for the task's restate, so the human no longer re-pastes the cause across the seam (the lead never widens scope — the Scope Lock still holds).
