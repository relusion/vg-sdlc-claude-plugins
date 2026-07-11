# Feature-Patch Workflow — Stages 0–4, Promotion, and Closing

Stage file for the `patch` skill. The orchestrator is `SKILL.md` — read it first for the Execution Contract, the Patch Charter, the Scope Lock, Graduation, Tiered HITL, and the Architecture diagram (including Substrate Fallback). Load this file when you begin Stage 0.

**Next:** this file runs Stages 0–4 to completion (Promotion Procedure and Closing included). At the write / close steps, also load `${CLAUDE_SKILL_DIR}/artifact-reference.md` for the artifact layout, the `eligibility.json` template, the `express-log.jsonl` schema, and the metrics format.

**Two lanes.** If the invocation carried `--express` (or the human accepts the express offer at the Stage-0 pre-screen), run **The Express Fold** below instead of Stages 0–4. Otherwise run Stages 0–4. The Express Fold is a *mode of the same skill* — it inherits the Charter, the Lock, and the lint; it only trades the spec artifacts for a single ledger line, behind a stricter mechanical screen.

---

## The Express Fold — the featherweight one-gate lane  *(interactive)*

Entered when the invocation carried `--express`, or when you offer it at the Stage-0 pre-screen (Step 1 came back clean and the change is featherweight) and the human accepts. The fold runs a test-first edit behind **one combined gate** and records a single ledger line — **no `eligibility.json`, no `ce-spec.md`, no `tasks.json`, no `plans.json` entry.** Any screen FAIL falls the change back to Stage 0 of the full lane; express is **refused, never shrunk**.

**E-Step 1 — scoped probe (same as Stage 0's).** Read only what the change needs: the named file(s), their **direct callers** (one hop), and the build / test / lint commands. Determine the candidate **file set** and record the current git HEAD as `base_ref`. The express screen refuses more than **2** files, so if the probe enumerates more, fall to the full lane.

**E-Step 2 — the mechanical screen (run it, don't narrate it).** Write a throwaway `express.json` stub — `{"files": ["path/a", "path/b"], "desc": "<the change request>"}` — to a temp path (a transient run input, **not** an artifact — delete it at the end), then:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/patch-lint.py" <tmp>/express.json --express
```

- **PASS (0)** → the mechanical charter clauses hold: **E1** (≤ 2 files), **E2** (no cross-feature collision with another plan's `tasks.json`), **E3** (no reviewer-trigger surface in the paths or the description — the C6 mechanical floor), **E4** (no dependency-manifest file). This clean screen is the **precondition** that lets C6/C7 ride the single combined gate. Proceed.
- **FAIL (1)** → present the named clause and **fall back to the full lane** (Stage 0 — the probe is already done). Do not shrink the change to fit; the lane is refused.
- **ERROR (2)** → cannot run the screen → fall back to the full lane, **loudly**, and never self-certify the screen.

**E-Step 3 — test-first edit.** In the working tree: write the change's test(s) first (**red**), implement within the candidate file set, run the tests (**green**). Capture the red→green evidence — the failing-then-passing test command and its output. There is **no spawn** (there is no spec to isolate an implementer from); the external `--express --post` diff gate is the guarantee, exactly as on the full lane.

**E-Step 4 — the external diff end check.**

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/patch-lint.py" <tmp>/express.json --express --post --base <base_ref>
```

re-runs **H8 / H9 / H10** over the **actual diff** against the candidate set — a durable-noun write (H8), a file outside the candidate set (H9), or a destructive op (H10). Any hit is a **material finding**: present the exact diff line and **fall back / promote to the full lane**, quarantining the partial diff the way the Promotion Procedure does. Could-not-run (2) → check H8–H10 against the diff by hand, **loudly**. A clean end check proceeds to the gate.

**E-Step 5 — the one combined consent+acceptance gate [material].** Print `Gate 1 of 1 — Express Accept` and render, in one place (the gate definition lives in `SKILL.md` → *Human-in-the-Loop*):

- the **diff** of the touched files;
- the **red→green** test evidence (the command + before/after);
- the **E1–E4** mechanical findings (all PASS — the screen's evidence);
- **C6** and **C7** as **two explicit labeled attestation lines**, each stating the E3 scan basis and the concrete cost-if-wrong (evidence-first, R2).

The C6/C7 bundling here is the **documented R3 deviation** (SKILL.md): it is legitimate *only because* E3 came back clean and its evidence is rendered — a heuristic hit would already have forced the full lane. Then ask:

| Option | Result |
|---|---|
| Accept | keep the diff; append **one** line to `docs/plans/express-log.jsonl` (schema in `artifact-reference.md`); delete the temp stub |
| Revise | loop back to E-Step 3 |
| Discard | `git restore` the touched files — **destructive to the edit**, the working-tree changes are gone; delete the temp stub |
| Promote to full `/ce-patch` | carry the intent into Stage 0 of the full lane (the probe is done); quarantine the diff |

On **Accept**, append the ledger line and handle version control **read-only on `vc-policy.md`** exactly as Stage 4 does — if a policy records a granularity, offer *Commit / Skip*; if absent, **do not commit**, and leave the diff for the human. The express fold **never** pushes, PRs, merges, or auto-commits. The `express-log.jsonl` line is the *only* persistent record an express change leaves — `/ce-retro` reads its frequency + discard rate as the salami-slicing smell signal.

---

## Stage 0 — Scoped Probe + Eligibility Gate  *(interactive)*

**Probe, don't profile.** Read only what the change needs: the file(s) the request
names (or that a quick Grep locates), their **direct callers** (one hop), and the
build / test / lint commands. Read `vc-policy.md` if present (for the file cap
override and VC behavior). Do **not** run the nine-dimension codebase profile.

**Compute the lease.** Determine the candidate **frozen file set** (the enumerable
files the change will touch) and the **file cap** (default **5**, or the value
recorded in `vc-policy.md` — a per-repo consented override). Record the current git
HEAD as `base_ref`. Draft the seven clause verdicts with evidence:

- **C1, C4** — compute mechanically (file count vs cap; collision with other plans'
  `tasks.json`). **C2 (pre), C5** — judged now from the request, re-checked against
  the diff at Stage 4. **C3** — attested. **C6, C7** — human-attested.

Create `docs/plans/patch-<date>-<slug>/specs/00-<slug>/` and write a
**draft** `eligibility.json` (template in `${CLAUDE_SKILL_DIR}/artifact-reference.md`) with the mechanical
verdicts filled and the human-attested clauses (C6/C7) left unanswered. Order matters
— the lease must be *complete* when the recorded gate reads it, so run the two checks
in two steps:

**Step 1 — mechanical pre-screen (before bothering the human).**

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/patch-lint.py" docs/plans/patch-<date>-<slug>/specs/00-<slug> --eligibility --draft
```

`--draft` demotes the not-yet-stamped consent fields to advisory but keeps the
mechanical clauses (C1 file cap, C4 cross-feature collision) and any explicit NO
**hard**. **FAIL (exit 1)** → a mechanical disqualifier: present it, emit a `/ce-plan`
seed, stop (Graduation #1) — without spending the human's time. **Exit 2** → check the
Charter by hand, **loudly**. Only a clean pre-screen proceeds.

**Express offer (optional).** If this pre-screen is clean and the change looks
featherweight (≤ 2 files, no reviewer-trigger surface), run the `--express` screen
(E-Step 2 above); if it PASSes, offer the human **The Express Fold** as a faster path —
*Express fold (one gate, no spec artifacts) / Full patch lane (two gates, full spec
trail).* On accept, switch to the fold; on decline (or an express-screen FAIL),
continue the full lane at Step 2.

**Step 2 — the Eligibility Gate [material].** Present the mechanical findings, then
ask the two human-attested clauses as explicit prompts:

| | Question |
|---|---|
| **C6** | Does this change touch any reviewer-trigger surface — auth, secrets, payments, data deletion, persistence, i18n, or accessibility? |
| **C7** | Is there any product or architecture question here you can't settle in one round? |

A **yes** to either is a disqualifier → emit a `/ce-plan` seed and stop. Otherwise ask
the human to **consent to the lightweight lane** (showing the frozen set + cap):
*Proceed on the patch lane / Send to /ce-plan / Abort.* On consent, **write the C6/C7
verdicts + `attested_by: human`, and stamp `decided_by: human` + `accepted_at`** into
`eligibility.json` — the lease is now complete.

**Step 3 — the recorded gate (the lease is now stamped).**

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/patch-lint.py" docs/plans/patch-<date>-<slug>/specs/00-<slug> --eligibility
```

This is the on-disk record that lightness was granted on a complete, human-consented
lease. It must PASS (**exit 0**) before Stage 1. Distinguish the two non-zero outcomes:
**exit 1 (FAIL)** means the lease was written incompletely — fix it, do not proceed;
**exit 2 (ERROR — could not run**, e.g. no `python3`) is *not* a verdict — fall back to
the manual Patch-Charter checklist (loudly), as the Preconditions allow, and record that
the gate was run by hand.

## Stage 1 — Patch Spec  *(this context writes)*

Write the **real** spec artifact (the same 10-section template `spec`
produces — content scaled to the change, *not* a new shape, so `spec-lint`'s H1–H4
apply unchanged), plus a one-file `features/00-<slug>.md` Boundary anchor and the
`plans.json` registration:

- **`features/00-<slug>.md`** — the frozen boundary: Scope, Excluded, the
  `frozen_files` list, and a pointer to `eligibility.json`.
- **`specs/00-<slug>/ce-spec.md`** — the same template `spec` emits, kept whole
  (so `spec-lint` applies unchanged): the `> Spec revision: N · Status:
  ready-for-implementation` header, then section 1 (boundary), 3 (≥ 1 EARS acceptance
  criterion per Scope item, **including ≥ 1 unwanted-behaviour criterion** for the
  failure mode), 4 (≥ 1 dual-tagged test case per criterion — `modality` +
  `verification`), 5 (design: real files + patterns), 6 (ordered tasks, each with a
  `files` list ⊆ `frozen_files`), 7 (traceability), and 10 (Handoff). Sections 2/8/9
  are typically "No open unknowns" / brief / "N/A" for a patch — keep the headings,
  don't manufacture ceremony.
- **`specs/00-<slug>/tasks.json`** — `{feature_id, spec_revision, tasks:[{id,
  description, files, verifies, order, status}]}`, every `files` entry within the
  lease.
- **`plans.json`** — add (or create) an entry for `patch-<date>-<slug>` with
  `origin: "patch"`, so `/ce-verify`, `/ce-review`, `/ce-retro`, and `/ce-ship-release` find it with
  zero special-casing.

## Stage 2 — Pre-Gate  *(external, on disk)*

Run the spec-artifact gate — an objective external check, not a self-report:

```bash
test -f docs/plans/patch-<date>-<slug>/specs/00-<slug>/ce-spec.md \
  && test -f docs/plans/patch-<date>-<slug>/specs/00-<slug>/tasks.json \
  && python3 "${CLAUDE_SKILL_DIR}/scripts/patch-lint.py" docs/plans/patch-<date>-<slug>/specs/00-<slug> --pre
```

`--pre` runs spec-lint **H1–H4** (traceability) + **H5** (the lease is still valid) +
**H6** (no `db`/`event`/`iac` modality test case — C2's pre-implementation end) +
**H7** (every planned task `files` entry is within the lease). Disposition:

- **PASS (0)** → proceed to implement.
- **FAIL (1)** → fix the spec and re-lint; an H6/H7 failure means the change outgrew
  the lane → **promote** (Graduation #1, now evidenced by the spec).
- **Could-not-run (2)** → check H1–H7 by hand, **loudly**, then proceed only if clean.

## Stage 3 — Patch Implement  *(fresh spawned agent; Scope Lock)*

**Spawn an implement agent** via the `Task` tool. Its **only** spec input is the two
files on disk — instruct it to STOP if they are absent (it cannot improvise a spec).
Its prompt carries: the spec dir path, the `frozen_files` lease, the build/test/lint
commands, and the **Scope Lock** ("touch only the frozen set; minting a durable noun
or needing an out-of-set file is a Patch Conflict — STOP and return `patch_conflict`,
do not widen"). It runs the per-task loop:

1. **Test first** — write each task's `auto` test cases as tests; red.
2. **Implement** — make the change within the frozen set; honor existing patterns.
3. **Verify** — `auto` tests green; lint/type-check; no regressions in the touched
   area.
4. **Record** — set the task `status: done` in `tasks.json`.

It returns a structured result (status `done | patch_conflict`, test summary, any
`manual:harness-gap` evidence). A `patch_conflict` → **promote** (Graduation #3).

*(Substrate Fallback: if `Task` is unavailable, run this loop in-context and record
the isolation degradation — the external Stage 4 gate is unchanged and remains the
real guarantee.)*

## Stage 4 — Post-Gate + Close  *(external, then interactive)*

Run the build-evidence gate over the **actual diff**:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/patch-lint.py" docs/plans/patch-<date>-<slug>/specs/00-<slug> --post
```

`--post` re-validates the lease (H5), re-runs **H1–H4** on the final spec + scans the
diff (base..working tree, the lane's own `docs/plans/patch-…` artifacts excluded) for
**H8** (durable-noun write — C2's build-evidence end), **H9** (any file outside the
lease — C1 post), **H10** (destructive op — C5 post), and emits an **advisory C3**
signal for any new public surface. Disposition:

- **PASS (0)** → continue to acceptance.
- **H9 FAIL** → **mandatory promotion** (Graduation #2): the lease is void.
- **H8/H10 FAIL** → a **material finding**: present the **exact diff line** it fired
  on. A real durable noun / destructive op → **promote**. A heuristic false positive →
  the human's acknowledgement must **cite that line and say why it is not durable /
  destructive** (`decided_by: human`, with the reason); a bare "dismiss" is not
  enough, because a true positive can share a signature with a common false positive —
  inspection is the point. Never reach Accept on an unacknowledged FAIL, and never
  pre-frame these as "expected noise to wave through".
- **C3 advisory** → if the scan flags a possible new public surface, present it to the
  human as a Stage-4 reconsideration of C3 (does not block; C3's gate is the Stage-0
  attestation).
- **Could-not-run (2)** → check H8–H10 against the diff by hand, **loudly**.

Then verify and close:

- Run the feature's `auto` tests (all green) and the project build/lint. For
  `manual:harness-gap` cases, drive the check where possible and capture evidence;
  defer any `manual:judgment` verdict to the human.
- Confirm every acceptance criterion traces to a passing test case.
- Present the verification summary + a short **Try-It-Yourself** runbook (the real
  commands run), then ask **Final Acceptance [material]:**

| Option | Result |
|---|---|
| Accept | Write `verification.md`; the patch is complete |
| Revise | Loop back to a task (Stage 3) |
| Promote | Graduate into `/ce-plan` (Promotion Procedure) |

On **Accept**: write `specs/00-<slug>/verification.md` (each criterion + pass
evidence, the test-run summary, the runbook). Handle version control **read-only on
policy** — if `vc-policy.md` records a granularity, offer to commit accordingly
(*Commit / Skip*); if absent, **do not commit** — report what is staged and leave the
diff for the human. Never push, PR, or merge.

## Promotion Procedure

When any Graduation point fires:

1. In `plans.json`, change the entry's `origin` from `"patch"` to a normal plan (or
   note it as the seed for a new plan).
2. Carry `features/00-<slug>.md` + the written `ce-spec.md` forward as the `/ce-plan` seed
   (the intent is already captured — `/ce-plan` decomposes from there).
3. **Revert or quarantine any partial diff** so the working tree never silently
   carries under-specced edits; the seed enumerates the half-edited files.
4. Append an `escalation` metrics line (`escalation_type: "/ce-plan"`,
   `detail: "patch-promote:<pre|post|midflight>:<reason>"`).
5. Stop and emit the exact next skill:
   `/ce-plan` (seeded from `docs/plans/patch-<date>-<slug>/`).

## Closing

```text
Patched: patch-<date>-<slug> — <N> tasks done within <F> frozen files
Verified: <M> acceptance criteria met
Artifacts: docs/plans/patch-<date>-<slug>/ · plans.json (origin: patch)
Branch: <committed per policy | not committed — diff left for you>
```

Pushing, PRs, and merging are the human's to do. For a larger follow-on, point to
`/ce-plan`; for an independent quality pass on the change,
`/ce-review patch-<date>-<slug>/00-<slug>`.
