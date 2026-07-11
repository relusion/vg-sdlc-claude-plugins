# Release Coordinator — managed-agent template

## Overview

Verified plan → delivery manifest, release decision package, supply-chain
evidence inventory, and user-facing documentation grounded in verified behavior.
Built on the [`core-engineering`](../../plugins/core-engineering) plugin's
`ce-ship-deliver`, `ce-ship-release`, and `ce-ship-document` skills — this
directory is the Managed Agent cookbook for `POST /v1/agents`.

## Deploy

```bash
export ANTHROPIC_API_KEY=sk-ant-...
../../scripts/deploy-managed-agent.sh release-coordinator
```

## Steering events

See [`steering-examples.json`](./steering-examples.json).

## Security & handoffs

**Isolation tier: release-prep worker.** Shell + workspace write
([`agent.yaml`](./agent.yaml) grants `bash` and `write`) so it can prepare local
delivery/release/doc artifacts. It has no authority to publish: no push, PR,
tag, deploy, package publish, credential rotation, or external tracker write.

By the **Rule of Two** ({untrusted input, secret access, external write} — hold
at most two), it already holds untrusted input + local write/shell. Deploy it
with no production credentials, no release signing keys, and no package registry
write tokens. Plugin hooks (`git-guard.py`, `env-guard.py`) do **not** load on
this surface — `agent.yaml` tool config, the system prompt, and your sandbox are
the enforcement boundary.

Release Coordinator is single-process (`callable_agents: []`). A recommended
fanout if you add subagents:

| Leaf | Tools | Connectors |
|---|---|---|
| `evidence-reader` | `Read`, `Grep`, `Glob` | none — inventories verification/review/supply-chain evidence |
| `release-drafter` | `Read`, `Write` | none — writes release decision and docs manifests |
| **`branch-preparer`** (Shell-holder) | `Read`, `Bash`, `Write` | none — constructs local delivery branch only |

Handoff policy:

- Missing verification or unresolved review findings route to `quality-gate`.
- Spec/plan defects route to `spec-author`.
- Implementation defects route to `spec-impl`.
- Publishing remains the human release owner's job.
