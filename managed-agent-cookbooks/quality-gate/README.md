# Quality Gate — managed-agent template

## Overview

Implemented plan/spec → review findings, verification report, and routed
diagnosis when something fails. Built on the
[`core-engineering`](../../plugins/core-engineering) plugin's `ce-review`,
`ce-verify`, and `ce-debug` skills — this directory is the Managed Agent cookbook
for `POST /v1/agents`.

## Deploy

```bash
export ANTHROPIC_API_KEY=sk-ant-...
../../scripts/deploy-managed-agent.sh quality-gate
```

## Steering events

See [`steering-examples.json`](./steering-examples.json).

## Security & handoffs

**Isolation tier: quality worker.** Shell + artifact write
([`agent.yaml`](./agent.yaml) grants `bash` and `write`) so it can run tests and
write reports, but it must not mutate production code or specs. By the **Rule of
Two** ({untrusted input, secret access, external write} — hold at most two), it
already holds untrusted input + shell/write in a sandboxed checkout; deploy with
no credentials in the environment and no production network reachability.

Plugin hooks (`git-guard.py`, `env-guard.py`) do **not** load on this surface —
`agent.yaml` tool config, the system prompt, and your sandbox are the enforcement
boundary.

Quality Gate is single-process (`callable_agents: []`). A recommended fanout if
you add subagents:

| Leaf | Tools | Connectors |
|---|---|---|
| `reviewer` | `Read`, `Grep`, `Glob` | none — inspects code and specs |
| `runner` | `Read`, `Bash` | none — runs tests and captures output |
| **`reporter`** (Write-holder) | `Read`, `Write` | none — writes quality artifacts |

Handoff policy:

- Code defects route to `spec-impl`.
- Spec/plan defects route to `spec-author`.
- Clean quality gates may route to `release-coordinator`.
- This agent never patches, commits, pushes, opens PRs, tags, or deploys.
