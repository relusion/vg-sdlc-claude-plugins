# Executable-Doc Mode — execute the doc as the role

Loaded by `SKILL.md` Stage 0 when the document has runnable steps. The spine has
already resolved the role, established the sandbox, and set the execution tier
(Gates 1–3). This file owns the execute-and-audit loop. All spine cross-cutting
rules still bind — especially **Stay in Role**, **Run-as-Written**, and
**Consent-gated execution**.

## Setup

1. **Establish the sandbox** confirmed at Gate 2: a fresh temp working dir, or a
   git worktree (`git worktree add`) when the doc's steps operate on this repo.
   Scrub the env of real secrets; block egress to production. If isolation cannot
   be established, **stop and report** — never fall back to the live tree.
2. **Segment the doc into ordered steps.** A step is one runnable unit (a command,
   a block to paste, a config to apply, one API call). Record each step's span
   (`§heading` / `L<line>`) for anchoring.
3. **Snapshot the role's starting state and success criterion** — what the role
   has *before* step 1, and the done-state the role is trying to reach (both from
   the role manifest). The success criterion sets each finding's `position`.

## The step loop — for each step, in order

Hold two stances (never let one contaminate the other):

**A. Executor (in role, verbatim).**

1. **Reachability check first.** Before running anything, ask: *could the role get
   to this step using only the doc so far + what the role knows/has?* If a
   required input (a value, a path, an env var, an access grant, a prior tool) was
   never provided and the role could not know it → emit an **incomplete** finding
   anchored at this span, note what was missing, and **use the minimum inference
   needed to continue** (recorded as an assumption in the report) — do not pretend
   the gap didn't exist.
2. **Classify the step's side-effect class:**
   - *read-only / idempotent* (build, list, `--dry-run`, GET, local read) → run
     for real under the `observe` tier.
   - *side-effecting* (writes external state, deploys, deletes, POST/PUT that
     mutates, sends mail) → run **only** if its class was pre-authorized at Gate 3
     or the human opts in at the per-step gate; otherwise **simulate-and-annotate**
     (record the exact command, mark evidence-tier `needs-execution`, and flag it
     unverified — do **not** assert what it "would" do as fact).
3. **Run it exactly as written** — copy-paste the documented command with no silent
   correction. Capture stdout/stderr/exit code to `evidence/<date>-<slug>/F-*` (or
   `step-N.log`).

**B. Auditor (judge against reality + the role).**

4. **Compare to the doc's promise.** The doc's stated expected output / effect vs
   what actually happened:
   - command errored, flag/option rejected, path wrong, output differs, link dead,
     version mismatch → **inaccurate** finding, evidence-tier `execution-proven`,
     transcript attached.
   - it worked but required a step the doc never stated (a `cd`, an install, a
     login) → **incomplete** finding.
5. **Judge friction (role-anchored):**
   - two plausible readings, undefined jargon relative to the role, an unresolved
     pronoun/reference → **unclear**.
   - bad ordering, no checkpoint to confirm success before the next step, a big
     unexplained leap, needing a second terminal the doc never frees up →
     **hard-to-follow**.
   Each cites the span and the role's knowledge boundary, else suppress it.
6. **Reach for a mechanical anchor.** Where a claim *can* be reduced to a
   mechanical check the sandbox can run (a command exit code, a `grep`/count over
   the doc or repo, a link that resolves, a version compare), do so and attach it —
   those become `execution-proven` or `internal-consistency` findings the report
   can *confirm*. A pure judgment call can only be *rated*, never confirmed;
   prefer the anchor when one exists.
7. **Checkpoint.** If the doc claims a verifiable state ("you should see X"),
   verify it and record proven / diverged. Set each finding's `position`
   (before/after the role's success criterion) — it caps severity per the spine's
   rubric.

## Discipline

- **One pass, in order.** Walk each step once; do not brute-force variations. If a
  step blocks the whole doc, record downstream steps as **blocked (not reached)** —
  do not skip ahead and silently assume they'd pass.
- **Never fix the doc mid-run**, even when the correct command is obvious — the
  fix is a *suggested-fix* field on the finding, addressed later by another skill.
- **Stuck rule.** If a step fails and it is genuinely unclear whether the cause is
  a doc defect or a real environment problem (missing license, network policy),
  **stop and ask one short question**; record it in *Open Questions / Stops*.
- **Secret hygiene.** Any credential the doc requires is a scrubbed test value;
  never a real secret. Redact any secret that surfaces in output before writing
  evidence.

## Produce the artifacts

1. **Cluster by root cause first** (spine's Findings rule): fold same-cause
   findings into one structural finding with sub-instances before numbering.
2. **Findings report** `docs/doc-audits/<date>-<slug>.md` per the spine template —
   lead with the role's ignorance boundary + success criterion, then findings
   ordered by severity then doc span.
3. **Annotated copy** `docs/doc-audits/<date>-<slug>.annotated.md` — the source doc
   verbatim, with `> ⟦DOC-AUDIT F-N · <category> · <severity>⟧ <comment>` inserted
   at each finding's span. This is the human's inline-review surface.
4. **Evidence** under `docs/doc-audits/evidence/<date>-<slug>/` — one transcript
   per execution-proven finding.

## Triage (final, tiered)

Batch findings by severity × evidence-tier. Execution-proven high-severity or
ambiguous findings → **material** decisions (each read back with its transcript);
clear-cut low-severity → **batch approve-with-veto**. A `needs-execution` finding
is presented as unverified and is **never** downgraded by assuming unobservable
state (spine Contract §8). Record every triage (Escalate / Defer / Dismiss) in the
report — dismissals kept with their reason, never dropped. Then print the spine's
Closing block.
