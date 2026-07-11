---
name: ce-doc-audit
description: |
  Audit an existing document for accuracy and usability by impersonating a named reader role, executing its steps in a local sandbox, and reporting inline, evidence-bound findings — never editing the doc. Executable-doc mode (the doc has runnable steps): run each step exactly as written as the role, observe reality, and flag where it is inaccurate / incomplete / unclear / hard-to-follow. Conceptual-doc mode (no runnable steps): a role-comprehension walk instead of execution. Findings, not verdicts; the human triages; a separate skill addresses approved feedback.
  Triggers: validate/QA/test-drive whether a role can actually follow a doc, runbook, quickstart, README, or setup guide. To WRITE docs use /ce-ship-document; to teach a maintainer the code use /ce-onboard; to walk a running app's UI use /ce-ux-audit.
argument-hint: "[doc-path] [--role <name|inline text>] [--sandbox <dir>]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
disable-model-invocation: true
---

# Doc Audit

**Invocation input:** Document to audit (path), optional `--role`, optional `--sandbox`: $ARGUMENTS


Validate whether **a human in a specific role** can successfully follow a
document. The skill **impersonates that role**, reads the doc top-to-bottom with
only what the role would know, **executes the documented steps in a local
sandbox**, and reports **inline, evidence-bound findings** where the doc is
**inaccurate, incomplete, unclear, or hard to follow**.

The workflow is **read-only on the source document and on code** — it finds
issues and **escalates**; it never edits the doc it is auditing and never
commits. Same finding-and-escalate discipline as `/ce-ux-audit` and
`/ce-probe-sec`. Approved findings are addressed later by a *different* skill
(`/ce-ship-document` to regenerate, `/ce-patch` for a small edit, or by hand).

It runs in one of **two auto-detected modes**, chosen by a Stage-0 probe of the
document — you never have to know which:

- **Executable-doc mode** — the doc contains runnable steps (commands, setup,
  config to apply, an API call sequence). *Executes* each step exactly as
  written, as the role, in the sandbox, and reports where reality diverges from
  the doc.
- **Conceptual-doc mode** — the doc is explanatory (architecture, rationale,
  policy) with nothing to run. *Reads* it as the role and reports comprehension
  gaps. **No execution is faked** — if there is nothing to run, the skill says so.

## Sister tools

|  | `/ce-doc-audit` | `/ce-ship-document` | `/ce-ux-audit` | `/ce-onboard` |
|---|---|---|---|---|
| Subject | an **existing doc** | user-facing docs | a **running app's UI** | as-built **code** |
| Direction | **validates** it | **writes** it | walks journeys | **teaches** a human |
| Output | inline findings | the doc | findings | a walkthrough |
| Edits source? | **never** | authors it | never | never |

`/ce-ship-document` and `/ce-doc-audit` are inverse operations on the same
artifact: one generates a doc from verified behavior, the other checks an
existing doc against executed reality. When a doc-audit finding is *approved*,
the fix routes back to `/ce-ship-document` or `/ce-patch`.

## Runtime Inputs

- **Document (required):** a path to the doc to audit. If absent, ask.
- **`--role` (required, resolved at Stage 0):** the reader role to impersonate,
  resolved in precedence order **inline text > `docs/roles/<name>.md` >
  `${CLAUDE_SKILL_DIR}/roles/<name>.md`**. The role's *ignorance boundary* and its
  *success criterion* are the engine of the audit (see `role-manifest.md`). If
  none resolves, the skill offers the shipped roles and asks — never invents one.
- **`--sandbox` (optional):** the local isolation dir. Default is a fresh temp
  working dir the skill creates; a git worktree is used when the doc's steps run
  against the repo. Never the user's live working tree, never production.
- **Execution tier (Stage 0 gate):** `observe` (default — run read-only /
  idempotent steps for real) with **per-step opt-in** for any step that has side
  effects. Never a blanket "run everything."

Writes only its own dated artifacts (never the source doc):
`docs/doc-audits/<date>-<slug>.md` (the findings report) +
`docs/doc-audits/<date>-<slug>.annotated.md` (a copy of the doc with inline
comment markers) + `docs/doc-audits/evidence/<date>-<slug>/` (command
transcripts). Dated snapshots — a run never overwrites a prior one.

## Preconditions

- The document exists and is readable.
- A role manifest resolves (library or inline) — else stop and ask.
- For **executable-doc mode**: the sandbox can be established (temp dir or
  worktree). If isolation cannot be guaranteed, **stop and report** — the skill
  never executes documented steps against unsandboxed or production state.

## Execution Contract

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive gate; compute M from the gates that actually fire this run, never a hardcoded constant.

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-doc-audit --allow 'docs/doc-audits/**'` — only the dated report, annotated copy, and evidence are writable; the source doc is **not** in the lease. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Never edit the source doc, patch code, or commit.** Find, do not fix. Write only the dated report + annotated copy + `evidence/`. The doc under audit is read-only.
2. **Stay in role — the ignorance boundary.** Read and act with **only** what the role declares it knows and can access. A gap you could fill from repo context or your own knowledge, but the role could not, is a **finding**, not a detour to resolve silently. (Cross-cutting rule below.)
3. **Run-as-written, report reality.** Execute the documented command **exactly as written** (copy-paste fidelity) and report **what actually happened** — never what you know it *should* do. A command that fails as written is an accuracy finding even when you know the correct form. Prefer a **mechanically-checkable anchor** (a command exit code, a `grep`/count, a link that resolves) over an assertion — a mechanical anchor is the only thing the audit can *confirm* rather than merely rate. (Cross-cutting rule below.)
4. **Consent-gated execution.** `observe` tier is default (read-only / idempotent steps only). Any step with side effects runs only on a **per-step opt-in**; otherwise it is simulated-and-annotated, and recorded as *not executed* (evidence-tier `needs-execution`). Refuses production; sandbox only.
5. **Evidence-bound, three tiers.** Every finding carries its tier + receipt (see the Findings rule). No evidence → no finding.
6. **Findings, not verdicts.** The agent reports observations; the human triages. It never declares the doc "good" or "broken."
7. **Stuck or ambiguous → ask, don't guess.** When a step is genuinely blocked and it is unclear whether the cause is a doc defect or a real environment problem → stop and ask one short question; record it.
8. **Honest degradation — never resolve a `needs-execution` gap by assumption.** Conceptual mode runs no steps and says so; a step that could not be sandboxed or opted-into is reported `needs-execution`, **unverified**. Such a finding may **not** be downgraded or dismissed by assuming unobservable state (what a template ships, how a script behaves) — only a real run settles it.

## Cross-cutting rule — Stay in Role (the ignorance boundary)

The audit is only as good as the fidelity of the role's *not-knowing*. At every
step ask: **could this role get from here to the next step using only the doc so
far plus what the role declared it knows and can access?**

- **Yes** → proceed in role.
- **No** → an **incomplete** finding, anchored to the exact span where the role
  stalls, with what the role would have needed. Do **not** fill the gap from your
  own knowledge and move on — filling it silently is the single most common way
  this audit goes wrong.

## Cross-cutting rule — Run-as-Written, Report Reality

Two internal stances, kept separate so one never contaminates the other:

- **Executor** — types the documented command verbatim, in role, and records the
  literal result. Never "corrects" a command in its head.
- **Auditor** — judges friction (clarity, ordering, missing checkpoints) against
  the role's knowledge.

Execution is ground truth for the *accuracy* and *completeness* halves; the
Auditor supplies the *clarity* and *difficulty* halves. Keep them distinct in the
report so a judgment call is never dressed up as a proven defect.

## Cross-cutting rule — Findings, Not Verdicts

A finding is `{id, category, severity, doc-span, role-anchor, evidence-tier,
position, observation, evidence, suggested-fix, suggested-escalation}`.

- **category** ∈ `inaccurate | incomplete | unclear | hard-to-follow`
- **evidence-tier** — how the finding is backed, strongest first:
  - `execution-proven` — a sandbox run produced a transcript (an accuracy /
    completeness defect, demonstrated).
  - `internal-consistency` — a **doc-vs-doc** defect verifiable by reading alone
    (a contradiction between two spans, orphaned jargon, a broken cross-ref, a
    dead internal link). **No run needed** — do not label these `needs-execution`.
  - `role-judgment` — a clarity / difficulty call anchored to the role's boundary.
  - `needs-execution` — an accuracy claim a run *would* settle but that could not
    be run here (conceptual mode, or a side-effecting step not opted-in). Reported
    unverified; never downgraded by assumption (Contract §8).
  A `role-judgment` finding with no role-anchor is noise — suppress it.
- **position** ∈ `before-success | after-success`, relative to the role's declared
  success criterion (from the role manifest). **Severity rubric:** a finding
  `after-success` (in an optional "confirm it's healthy" tail, or an end-of-doc
  reference table) caps at **low** unless it would actively prevent the role from
  *reaching* success. Only `before-success` findings on the critical path earn
  medium/high.

The agent never declares pass / fail. The human triages each finding:

| Triage | Result |
|---|---|
| **Escalate** | `/ce-ship-document` (regenerate) · `/ce-patch` (small doc edit) · `/ce-debug` or `/ce-implement` (the doc is right, the *code* is wrong) |
| **Defer** | Record as a known limitation in the report |
| **Dismiss** | False positive — record the dismissal and its reason (kept, never silently dropped) |

A doc-audit finding sometimes reveals a **product** bug, not a doc bug: the doc
says X, the code does Y, and the doc is the correct spec. Those route to
`/ce-debug` / `/ce-implement`, not to a doc rewrite — the triage column carries
the distinction.

**Cluster by root cause.** Before reporting, fold findings that share one root
cause into a single **structural** finding with sub-instances (e.g. "optional /
Azure-only components leak into the required happy path" spanning four spans),
rather than emitting N independent nits — a structural finding is more actionable
and less noisy than its scattered instances.

## Stage 0 — Mode Probe *(auto-detect, announced, never a question)*

Resolve the mode yourself from the document:

1. **Scan the doc for runnable steps** — fenced shell/command blocks, imperative
   "run / execute / apply" steps, config to install, an API call sequence.
2. **Has runnable steps → executable-doc mode.** **None → conceptual-doc mode.**
   A doc with a few runnable steps embedded in mostly prose is executable-doc
   mode scoped to those steps.
3. **Announce in one line, then proceed** — offer the override, do not gate:
   - Executable: *"Executable-doc mode — this doc has N runnable steps; I'll run
     them as `<role>` in a sandbox. (To force a read-only comprehension pass
     instead, say so.)"*
   - Conceptual: *"Conceptual-doc mode — nothing here is runnable; I'll audit it
     for comprehension as `<role>`, no execution. (If steps are meant to run,
     point me at them.)"*
4. **Load the mode's stage file and continue:**
   - **executable-doc** → `${CLAUDE_SKILL_DIR}/mode-executable.md`
   - **conceptual-doc** → `${CLAUDE_SKILL_DIR}/mode-conceptual.md`

The announcement is not one of the interactive gates counted in `Gate N of M`.

## Stage 0 — Role, Sandbox, Consent  *(material)*

Run before any execution. Asked via `AskUserQuestion`; stops on refusal or "not sure."

**Gate 1 of M — Role.** Resolve `--role` (precedence above). Read it back: the
role's goal, what it knows, what it **does not know / cannot access**, and its
**success criterion**. Confirm this is the reader whose experience you simulate.
*Proceed / Pick another role / Abort.*

**Gate 2 of M — Sandbox & environment** *(executable-doc mode only)*. Confirm:
this is **not** production; steps run in a throwaway local dir (or a git worktree
for repo-targeting docs); env is scrubbed of real secrets; no calls to
production systems; not run as root; resource/time-limited. *Proceed / Abort.*

**Gate 3 of M — Execution tier** *(executable-doc mode only)*. `observe` is on
(read-only / idempotent steps run for real). For side-effecting steps, choose:
pre-authorize a named class (e.g. "local file writes are fine") **or** ask me
per step. Anything not authorized is simulated-and-annotated, not run. *Confirm.*

## Human-in-the-Loop — tiered

- **Stage 0 (announced auto-detect)** — the mode read-back; override, never a question.
- **Stage 0 (material)** — Role · Sandbox · Execution-tier gates above.
- **Mid-run (Stuck rule)** — a genuinely blocked / ambiguous step, or a per-step
  side-effect opt-in.
- **Final (tiered)** — triage of findings (execution-proven high-severity or
  ambiguous → material decisions; clear-cut → batch approve-with-veto).

No per-step verdicts during the walk — the agent executes/reads autonomously,
captures evidence, and reports.

## Modes — how to run

This skill is a thin **orchestrator**: the Stage-0 mode probe chooses the mode,
then the mode's stages live in a companion file loaded only when reached.

| Mode | Load this file | Then |
|---|---|---|
| Executable-doc | `${CLAUDE_SKILL_DIR}/mode-executable.md` | Role/sandbox/tier gates → execute each step as the role → compare to doc → annotate → triage → write report |
| Conceptual-doc | `${CLAUDE_SKILL_DIR}/mode-conceptual.md` | Role gate → read as the role → mark comprehension gaps → annotate → triage → write report |

The role-contract format and resolution rules live in
`${CLAUDE_SKILL_DIR}/role-manifest.md`; shipped starter roles live in
`${CLAUDE_SKILL_DIR}/roles/`.

**The companion files named above are bundled in this skill's own directory.**
`${CLAUDE_SKILL_DIR}` resolves to this skill's directory regardless of the current
working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`) and read
each file by its resulting absolute path; **never load a companion file by bare
name** — in an installed plugin the working directory is the user's project, so a
bare name finds nothing and triggers a filesystem search. (`docs/doc-audits/` and
`docs/roles/` live in the user's project, not this skill — those stay as-is.)

---

## Report Template — `docs/doc-audits/<date>-<slug>.md`

````markdown
# Doc Audit — <date> · <slug>

> Document: <path>   ·   Mode: executable | conceptual
> Role: <name> (source: inline | docs/roles | shipped) · success = <role's done-state>
> Sandbox: <dir | worktree | n/a>   ·   Execution tier: observe [+ opted-in: <classes>]
> Steps: <run> run · <sim> simulated · <blocked> blocked
> Findings: <T>  (<H> high · <M> medium · <L> low)
> Evidence: <X> execution-proven · <C> internal-consistency · <J> role-judgment · <N> needs-execution

## Role & Ignorance Boundary (as impersonated)

(the resolved role's knows / does-not-know / access + success criterion — the lens for every finding)

## Findings

### F-N — <short title>  [severity]

- **Category / Evidence-tier / Position:** incomplete · internal-consistency · before-success
- **Doc span:** `<path>` §<heading> / L<line>  — "<verbatim quote>"
- **Role anchor:** <what the role could not do or know here>
- **Observation:** <what happened / what's missing>
- **Evidence:** `evidence/<date>-<slug>/F-N.{txt,log}` (command + real output) *or* the cited spans
- **Suggested fix:** <concrete doc change>
- **Suggested escalation / Triage:** /ce-ship-document | /ce-patch | /ce-debug — Escalate / Defer / Dismiss — <date>
````

The **annotated copy** `docs/doc-audits/<date>-<slug>.annotated.md` is the source
doc verbatim with a marker inserted at each finding's span:
`> ⟦DOC-AUDIT F-N · <category> · <severity>⟧ <one-line comment>`. This is the
human's inline-review surface; the report is the structured, triage-able list.

## Closing

```text
Doc Audit complete: <slug> — <date>  (<mode>)
Role:      <name>  (does-not-know boundary + success criterion applied)
Sandbox:   <dir | worktree | n/a>   Tier: observe [+ <classes>]
Steps:     <run> run · <sim> simulated · <blocked> blocked
Findings:  <total> (<high> high, <med> medium, <low> low)
Evidence:  <X> proven · <C> internal-consistency · <J> judgment · <N> needs-execution
Report:    docs/doc-audits/<date>-<slug>.md
Annotated: docs/doc-audits/<date>-<slug>.annotated.md
```

**Never edit the audited doc; never commit.** Approved findings are addressed by
`/ce-ship-document`, `/ce-patch`, or by hand — after your review.

## Escalation

Doc rewrites / regeneration route to `/ce-ship-document`; small bounded doc edits
route to `/ce-patch`; a finding where the doc is correct but the *code* misbehaves
routes to `/ce-debug` (diagnose) or `/ce-implement` (owned feature). This skill
records findings and evidence, not fixes.

## Honest Limitations

- **Role fidelity is fallible.** The impersonation shares the model's blind spots;
  it can still "know too much." Every finding is the human's to triage.
- **Bounded execution.** `observe` tier by design misses defects that only surface
  from side-effecting steps you did not opt into; those steps are reported
  `needs-execution`, never assumed correct.
- **Sandbox ≠ the reader's real machine.** Environment-specific breakage (a
  corporate proxy, a licensed tool the role has) may not reproduce locally;
  flagged as environment-dependent, not proven.
- **Conceptual mode is comprehension-only.** No execution, so no accuracy proof —
  only role-anchored gap findings and internal-consistency findings.
- **Snapshots, not history.** Dated reports; runs never overwrite prior runs.
