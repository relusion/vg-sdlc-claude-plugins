---
name: ce-ship-document
description: |
  Generate user-facing documentation — README, getting-started/usage guide, API/interface reference, configuration — grounded in the plan's VERIFIED behavior, every example run not narrated. Never writes the versioned CHANGELOG.md (that is /ce-ship-release's).
  Triggers: write or regenerate user-facing docs, a README, or API/usage reference. To VALIDATE that a reader can follow an existing doc (not write one), use /ce-doc-audit.
argument-hint: "[plan-slug] [--audience user|api|contributor] [--target <path>]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Ship Document

**Invocation input:** Plan to document (and optional --audience / --target): $ARGUMENTS


Write the documentation a *user* of this software reads — grounded in what the plan
actually built and verified.

`/ce-ship-document` turns the pipeline's proven output into durable, user-facing product
documentation: a README, a getting-started / usage guide, an API or interface
reference, and configuration docs. It writes these into the project's **real** doc
locations (`README.md`, `docs/`, …) — not the planning tree — and it documents
**only verified behavior**, with **runnable** examples.

It runs after the work is verified:

```
plan → spec → implement → verify → document
```

Distinct from what already produces text:

- **vs the planning tree (`docs/plans/**`)** — those are *process* artifacts (plans,
  specs, decisions) for the team. `/ce-ship-document` writes *product* docs for the user,
  into the repo's own doc paths.
- **vs `/ce-implement`'s Try-It runbook** — the runbook is per-feature, local
  exploration-for-confidence, *not* verification; `/ce-ship-document` is the durable,
  audience-shaped product manual whose examples are freshly run and verification-backed.
- **vs `/ce-ship-release`** — release owns the versioned `CHANGELOG.md`; `/ce-ship-document` never
  writes it (it may render or link it read-only, or write a distinctly-named usage
  doc such as `docs/whats-new.md`).
- **It describes, it does not define.** A behavior the code doesn't have is never
  documented; a behavior that can't be documented truthfully escalates up.

## Runtime Inputs

- **Plan slug (required):** resolve via `docs/plans/plans.json`; if missing, ask. Do not guess.
- **`--audience` (optional):** `user` · `api` · `contributor` (one or more). Default: inferred from the plan's primary journeys + interface modalities.
- **`--target` (optional):** the doc root to write into. Default: the repo's detected doc location (`README.md`, `docs/`).
- **`--voice` (optional):** the narrative tone for the optional **Stage-3.5** naturalize pass — `technical` (default) · `professional` · `conversational` · `executive` · `skip` (publish the scaffolding as-is, no humanize). Passed through to `/ce-humanize`; asked at Stage 0 if unset. Orthogonal to `--audience` (audience is *who* reads; voice is *how it reads*).
- **Loaded (read-only):** `docs/plans/<slug>/verification-report.md` (what's proven), each `specs/<id>/verification.md` (criteria + passing evidence — and the Try-It runbook as a *non-authoritative* hint), the specs (the contract), `feature-plan.md` (journeys), the real code / interfaces, `shared-context.md`, and the repo's existing docs to match house style.

Writes user-facing doc files into the project's doc locations (consented), plus a
local provenance manifest `docs/plans/<slug>/docs/<date>-docs-manifest.md`.

## Execution Contract

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive gate; compute M from the gates that actually fire this run, never a hardcoded constant.

1. **Document reality, not intent.** Every documented capability traces to a verified feature; nothing is described that the implementation does not do.
2. **Runnable examples only — by modality.** Every code sample / command is executed and its real output captured, never narrated. Execute by the example's modality: an **app** — start + exercise; a **CLI** — invoke; an **HTTP API** — call a running instance; a **library / SDK** — write the snippet as a scratch program or example-test, compile and run it against the built library, capture the output. An example that cannot be run is a defect: fix the doc or escalate, never ship it narrated.
3. **Verified subset only.** Document `verified` features as working; an unverified or `manual:judgment`-pending capability is marked clearly (e.g. "experimental / unverified") or omitted — never presented as proven.
4. **Write product docs; read-only on everything else.** Writes the repo's doc files + the local manifest; never edits code, specs, or the planning tree, and **never writes `CHANGELOG.md`** (owned by `/ce-ship-release`) — render / link it read-only, or write `docs/whats-new.md`.
5. **The human owns what publishes.** The doc plan and the final docs are material — public-facing text is the human's to approve.
6. **Honest coverage.** Report what is documented and what is not (undocumented surfaces, deferred areas) — never imply completeness.
7. **Escalate, don't paper over.** A spec ambiguity or undefined behavior surfaced while documenting escalates to `/ce-spec`; a needed-but-unverified capability escalates to `/ce-verify`.

## Document Reality, Don't Invent It  [the lock]

Docs describe **verified behavior**. When the code and the intended documentation
disagree, the **code wins** and the gap escalates — to `/ce-spec` if the contract is
ambiguous, to `/ce-verify` if the behavior is unproven — it is **never** resolved by
documenting a fiction or an aspiration. Every example is run; a sample that does not
reproduce is a defect in the doc (fix it to match reality) or a signal reality is
wrong (escalate). `/ce-ship-document` raises the floor on accuracy, not the ceiling on prose.

## The Doc Set — scaled to the project

Pick the audiences the project needs; scale, don't manufacture:

| Audience | Docs | For |
|---|---|---|
| **user** | README overview · getting-started · usage guide · what's-new (links `/ce-ship-release`'s `CHANGELOG.md`) | apps, CLIs, services |
| **api** | API / interface reference · auth · errors · examples | REST APIs, libraries / SDKs |
| **contributor** | architecture overview · setup · how-to-extend (links into ADRs / specs, does not duplicate them) | any repo with outside contributors |

A library leans `api`+`user`; a web app leans `user`; a service leans `api`+`user`.
Match the plan's primary journeys and interface modalities.

## Human-in-the-Loop — tiered

- **Stage 0 (material)** — audience(s), target, scope, and narrative voice.
- **Stage 3 (material)** — the accuracy-gate result (what can and cannot be claimed).
- **Stage 3.5 (routine)** — the optional `/ce-humanize` naturalize pass; no separate gate — its result flows into Stage 4's approval.
- **Stage 4 (material)** — approve what publishes.
- Routine — phrasing and ordering.

---

## Stage 0 — Load, Detect, Scope

Resolve the plan via `docs/plans/plans.json`. Read each feature's verified state from
the verification report's **Per-Feature Status** section — `verify` owns that
rule and records the derived `Verified` cell per feature; document only features whose
cell reads `Verified` (treat `partial` as not-yet-verified), and do not re-derive it
here. Detect the existing doc locations + house style (README, `docs/`, a framework
like mkdocs / Docusaurus). Determine audience(s) + target, and the narrative
`--voice` for the optional Stage-3.5 naturalize pass (default `technical`; `skip`
to publish the scaffolding as-is). Confirm scope with the human  [material].

## Stage 1 — Map Verified Features → User Docs

Map each `verified` feature / journey to the user-facing capability it provides, and
assemble a doc outline grounded in real behavior. Flag, separately: **unverified**
features (do not document them as working) and any capability you **cannot describe
truthfully** (carry it to the accuracy gate / escalation).

## Stage 2 — Draft with Runnable Examples

Draft each section grounded in the specs, journeys, code, and the feature's
`verification.md` **passing evidence**. The Try-It runbook (implement Stage 3)
is a **non-authoritative hint** — it is exploration-not-verification, and may be
absent or partial; **never copy an unrun runbook command** as a documented example.
The authority for a documentable example is the feature's `verification.md` passing
evidence **plus this stage's own fresh run** (Contract #2, by modality). An example
with no passing-verification backing must be re-derived-and-run or escalated, never
shipped narrated. **Example byproducts** (raw captured output, working screenshots
not meant as published assets) go under `docs/plans/<slug>/docs/` (deliver-excluded);
only deliberately-authored doc assets are written to the shipped doc paths.

## Stage 3 — Accuracy Gate  [material]

A real check, not prose. For the drafted doc set assert: every documented capability
→ a `verified` feature; no claim exceeds verified behavior; every example was run and
its output matched. Disposition:

- **Pass** → proceed to write.
- **A claim with no verified backing** → cut it, or escalate (`/ce-spec` / `/ce-verify`) —
  never ship it.
- Report the gate result **loudly**, including every capability left undocumented.

## Stage 3.5 — Naturalize the prose (optional)  *(skipped when `--voice skip`)*

Runs **only after the Accuracy Gate passes** — it re-voices *certified* prose,
never an un-gated draft. Invoke `/ce-humanize` in **Inline Mode** (pass the drafted
narrative **text**, take back the rewrite — never the file path, so no File-Mode
gate fires and Stage 4 stays the single approval), with the Stage-0 `--voice` as
its tone. Two hard rules:

1. **Fences are immutable.** Every fenced code block, command, and captured
   example output is held byte-for-byte. `/ce-humanize` preserves markup by
   contract (its Contract #4); this stage **verifies** it — after the rewrite,
   assert each fenced block is byte-identical to its pre-humanize form. Any drift
   inside a fence → **discard the humanize pass, keep the certified draft**, and
   report it. The accuracy-gated examples never move.
2. **Meaning is invariant.** Humanize re-voices tone; it never re-opens the
   accuracy question. The claims certified at Stage 3 are the claims that publish.

The result — humanized, or the original if `--voice skip` or a fence drifted — is
what Stage 4 diffs and the human approves.

## Stage 4 — Approve and Write  [material]

Present the doc set — the Stage-3.5 naturalized version if it ran — + the **diff
against existing docs**; the human approves what publishes. Write to the real doc paths. Write the provenance manifest (which feature
→ which doc, the accuracy-gate result, the examples run + their captured output).

**Metrics (best-effort, optional).** Append a `stage-complete` line (`stage: "document"`
— requires `document` in `retro`'s stage enum) plus any `escalation`: a
`/ce-spec` route uses `escalation_type:"/ce-spec"`; a **lateral** `/ce-verify` route uses
`escalation_type: null` with `detail` prefixed `route:/ce-verify …` so `/ce-retro` still
counts it. Derive from data already produced; **never** let this block the run.

---

## Escalation

| Finding | Route |
|---|---|
| Spec ambiguous / behavior undefined while documenting | `/ce-spec <id>` |
| A capability that must be documented is not `verified` | `/ce-verify` |
| Cross-feature / journey gap | `/ce-plan` |

`/ce-ship-document` never closes these by writing a fiction — it routes them up.

## Artifact — what it writes

- **Product docs** into the repo's real doc paths (`README.md`, `docs/…`, an
  interface reference) — the durable output, consented at Stage 4.
- **Provenance manifest** `docs/plans/<slug>/docs/<date>-docs-manifest.md` (local,
  deliver-excluded): feature → doc map, accuracy-gate result, examples run + their
  captured output, and what was left undocumented. Example byproducts live here too,
  never in the shipped doc paths.

## Closing

```text
Documented: <slug> — <N> docs (<audiences>)
Examples:   <run>/<total> verified · <failed> failed
Coverage:   <documented>/<verified> features · <undocumented> flagged
Wrote:      <doc paths>
Manifest:   docs/plans/<slug>/docs/<date>-docs-manifest.md
```

Review the doc diff before it publishes. Never commit, push, or deploy.

**Then validate it reads for a real user.** The docs are generated and
(optionally) naturalized, but not yet *walked*. Recommend the reader-validation
follow-up — `/ce-doc-audit <primary doc> --role <the doc's primary reader>` —
which impersonates that reader and executes the steps to surface where the doc is
inaccurate, incomplete, or hard to follow. It is human-initiated, so run it
yourself; `/ce-ship-document` cannot start it.

---

## Honest Limitations

- **Docs are a snapshot.** Accurate at generation; stale after the next code change —
  re-run. There is no continuous doc-CI here.
- **Only as accurate as the verification it reads.** A wrong or missing verification
  result makes a wrong or missing doc.
- **Examples verified once, not continuously.** A sample that ran at generation can
  rot; re-running re-checks it.
- **Covers the verified subset; flags the rest.** Unverified or judgment-pending
  capabilities are marked or omitted, never presented as proven.
- **Generated structure, not authored taste.** Produces accurate reference + usage
  scaffolding; information architecture, narrative, and conceptual / marketing docs
  that need product judgment stay the human's.
- **Writes to real doc paths.** It can overwrite hand-written docs — the diff at
  Stage 4 and the manifest are your guard; review before it publishes.
