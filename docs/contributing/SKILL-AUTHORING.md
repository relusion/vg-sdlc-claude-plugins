# Skill Authoring Standard

Skills are product code. Keep their contracts small, repository-aware, and
testable. `scripts/authoring_check.py` enforces the mechanical rules; the
[HITL Gate Standard](HITL-GATE-STANDARD.md) governs real human decisions.

## 1. Entrypoint contract

Every `SKILL.md` keeps only what is needed to route and start the workflow:

1. frontmatter (`name`, concise routing `description`, `argument-hint`, and
   least-privilege `allowed-tools`);
2. purpose and explicit non-responsibilities;
3. `## Runtime Inputs`;
4. `## Execution Contract`;
5. `## Human-in-the-Loop` when decisions can occur;
6. a short stage map or compact workflow;
7. `## Escalation`;
8. `## Honest Limitations`.

Do not repeat schemas, command help, artifact templates, or deterministic
algorithm details in the entrypoint. Point to the canonical companion or run
the helper that owns the rule.

## 2. Context budgets and progressive disclosure

`SKILL.md` is always loaded. A companion should be loaded only by the stage
that consumes it.

`authoring_check.py` enforces two independent ceilings:

- entrypoint: 400 lines and a 10,000 token proxy;
- each companion Markdown file: a 20,000 token proxy.

The proxy is `ceil(UTF-8 bytes / 4)`. It is deterministic and
tokenizer-independent; it is a context-growth guard, not measured model usage.
The ceilings keep untouched skills valid during migration. New or substantially
edited workflows should target no more than 2,500 proxy units for `SKILL.md`
and 5,000 for a companion.

Prefer:

- one stage file per independently loaded concern;
- a compact `stages.md` only when the whole body is genuinely small;
- one canonical artifact template;
- executable validators for exact schemas and calculations;
- links instead of copied contracts.

Splitting a large file without reducing what one run loads is not progressive
disclosure. Review the actual load path.

Companions use `${CLAUDE_SKILL_DIR}/<file>`. `corpus_lint.py` verifies that
references resolve.

## 3. Human-in-the-loop vocabulary

The suffix describes gate topology:

| Heading | Meaning |
|---|---|
| `## Human-in-the-Loop` | decisions appear when required |
| `— tiered` | material decisions ask; mechanical work proceeds |
| `— inverted` | autonomous until a named boundary |
| `— adaptive` | decision density follows the evidence and user signal |
| `— light` | initial consent plus a final read-back |
| `— minimal` | one decision around a bounded transform |
| `— opinionated` | recommendation is explicit and human-overridable |
| `— batched` | compatible decisions share a small number of gates |

A gate exists only for an actual choice, consent, exception, or authority-owned
judgment. Deterministic PASS, read-only work, generated projections, and clean
negative findings proceed without re-attestation. A deterministic failure
stops or routes; a human may not relabel it PASS inside the workflow.

Material architecture selection remains human-owned. The workflow must render
the evidence, alternatives, criteria, trade-offs, unknowns, recommendation,
confidence, and sensitivity, then support question/inspect, adjust, select, or
park at the same locator.

## 4. Gate mechanics

Interactive gates print `Gate N of M — <name>`, where M is the gates that
actually fire. Each option says what happens next. A call supports at most four
questions and four options per question; split a larger interaction under the
same locator and say why.

Material product, scope, architecture, security, destructive, contract,
accepted-risk, and release choices name their decision owner. If evidence or
authority is missing, offer gather evidence, route to owner, or park. Silence
is not approval.

## 5. Shared vocabulary

- Artifact dates use `<date>`. Never-overwritten workflows use one shared
  same-day `-2`, then `-3`, key across report and companions.
- The loop-back summary is `Back-Edge Summary`.
- A stage boundary is the `Scope Lock`; widening routes upward.
- `## Cross-cutting rule — Findings, Not Verdicts` retains “the human
  triages.”
- `## Cross-cutting rule — Stuck or Ambiguous → Ask, Don't Guess` records the
  issue in `Open Questions / Stops`.
- Evidence genres retain their domain tags but map them to the shared evidence
  scale: `demonstrated`, `read`, or `inferred`.

The shared consequence glossary lives in
[HITL-GATE-STANDARD.md](HITL-GATE-STANDARD.md) and the ce-plan runtime legend.
`authoring_check.py` checks their invariant anchors.

## 6. Routing descriptions

The frontmatter description is a router input, not documentation. State the
output, the distinctive trigger, and the nearest “use X instead” boundary.
Keep it under the 1,536-character platform ceiling.

Mutual contrast is required for registered overlap clusters:

- architecture / plan / spec;
- architecture / decide;
- review / verify;
- infra probe / dependency probe;
- doc audit / doc generation;
- onboarding / domain learning;
- idea scoring / scouting / market scan.

Update the `CLUSTERS` registry in `scripts/authoring_check.py` when an adjacent
intent is added.

## 7. Shared scripts

Portable skill scripts are addressed through `${CLAUDE_SKILL_DIR}`. When the
same gate is required beside multiple skills, register one canonical file and
its copies in `plugins/core-engineering/fork-manifest.json`, edit the canonical,
and run:

```bash
python3 scripts/fork_sync.py --write
```

Do not hand-edit a registered copy.

## 8. Review standard

A green lint proves structural consistency, not workflow quality. Reviewers
still verify:

- the workflow solves one clear developer job;
- its input, output, failure, and degraded modes are predictable;
- loaded context is proportional to the task;
- deterministic work is not restated as model prose;
- only real human decisions block progress;
- permissions and write scope are minimal;
- an eval or fixture exercises the changed behavior.
