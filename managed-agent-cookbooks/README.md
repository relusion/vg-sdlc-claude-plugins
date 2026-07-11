# Managed-agent templates for vg-coding

All four entries below are Claude Managed Agent templates that reference the
canonical `core-engineering` skills. `spec-author` and `spec-impl` also ship as
Claude Code custom agents in the
[`core-engineering`](../plugins/core-engineering) plugin; `quality-gate` and
`release-coordinator` are managed-agent templates only. The underlying skills
remain the single source of truth on every surface.

Run `../scripts/deploy-managed-agent.sh <slug>` to upload skills, create any declared subagents, and `POST /v1/agents` with the resolved config. Each template ships with `steering-examples.json` and a per-agent README covering its security tier and handoffs. The reference orchestration path is documented in [ORCHESTRATION.md](./ORCHESTRATION.md):

```text
spec-author -> spec-impl -> quality-gate -> release-coordinator
```

| Agent | Plugin | What it produces | CMA steering event | Suggested leaf fanout *(not yet wired)* |
|---|---|---|---|---|
| [`spec-author`](./spec-author/) | core-engineering | Raw idea → `docs/plans/<slug>/` plan + per-feature `ce-spec.md` + `tasks.json` | `Draft spec: <one-line idea>` | clarifier · decomposer · writer |
| [`spec-impl`](./spec-impl/) | core-engineering | Approved spec → working code + ticked `tasks.json` + `verification.md` | `Implement spec at <path>` | reader · runner · writer |
| [`quality-gate`](./quality-gate/) | core-engineering | Implemented work → review findings + verification report + diagnosis/routing | `Review and verify <path>` | reviewer · runner · reporter |
| [`release-coordinator`](./release-coordinator/) | core-engineering | Verified plan → delivery manifest + release decision + docs handoff | `Prepare release handoff for <plan>` | evidence-reader · release-drafter · branch-preparer |

All shipped manifests are single-process (`callable_agents: []`); the fanout column is the recommended subagent split each per-agent README sketches for when you add them (one Write-holding leaf per agent).

> **Model:** all cookbooks pin `claude-opus-4-8`. They run judgment-bearing stages (decomposition, EARS authoring, implementation, review, verification, release readiness) that the toolset's model-tier policy keeps on the strongest available model — track the current strongest model when you upgrade, or treat the pin as a deliberate reproducibility choice.

## Manifest vs API

The `agent.yaml` files use the real `POST /v1/agents` field names with a few conveniences the deploy script resolves:

| Manifest convention | Resolves to |
|---|---|
| `system: {file: ./system.md, append: "..."}` | `system: "<inlined contents + append>"` |
| `system: {text: "..."}` | `system: "<text>"` |
| `skills: [{from_plugin: ../../plugins/core-engineering}]` | uploads every `skills/*` under that dir → `[{type: custom, skill_id: ...}, ...]` |
| `skills: [{path: ../../plugins/core-engineering/skills/<skill>}]` | uploads that one skill → `{type: custom, skill_id: ...}` |
| `skills: [{path: ./skills/foo}]` | uploads that directory → `{type: custom, skill_id: ...}` |
| `callable_agents: [{manifest: ./subagents/foo.yaml}]` | creates the subagent first, references it by id |

`scripts/managed_agent_check.py` verifies cookbook inventory, steering examples,
orchestration docs, and `scripts/orchestrate.py` allowlist coverage.
`scripts/check.py` verifies every cross-file reference resolves before you push.
`scripts/test-cookbooks.sh` dry-runs every cookbook and asserts the resolved API
bodies are well-formed.
