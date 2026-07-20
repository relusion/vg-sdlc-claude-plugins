# Spec Author — managed-agent template

## Overview

Raw idea → an ordered feature plan and per-feature `ce-spec.md` + `tasks.json` (EARS acceptance criteria, test cases, executable task list). Built on the [`core-engineering`](../../../plugins/core-engineering) plugin's `ce-plan` + `ce-spec` skills — this directory is an unsupported Managed Agent cookbook snapshot for `POST /v1/agents`.

## Deploy

```bash
export ANTHROPIC_API_KEY=sk-ant-...
../tools/deploy-managed-agent.sh spec-author --dry-run
```

## Steering events

See [`steering-examples.json`](./steering-examples.json).

## Security & handoffs

**Isolation tier: read/author.** No shell (`bash` is disabled in
[`agent.yaml`](./agent.yaml)), no MCP servers; it reads the repo and writes only
plan/spec artifacts under `docs/plans/` (plus ADRs under `docs/adr/`) in its
sandboxed checkout. By the **Rule of Two** ({untrusted input, secret
access, external write} — hold at most two) it holds untrusted input + workspace
write; keep the remaining leg cut by deploying with **no credentials in the
environment**. Plugin hooks (`git-guard.py`, `env-guard.py`) do **not** load on
this surface — `agent.yaml` tool config, the system prompt, and your sandbox are
the only enforcement here.

Spec author is a single-process agent in the skeleton — no leaf workers (`callable_agents: []`). Its only side effect is writing plan/spec artifacts under `docs/plans/` and ADRs under `docs/adr/`. A recommended fanout if you add subagents:

| Leaf | Tools | Connectors |
|---|---|---|
| `clarifier` | `Read`, `Grep` | none — reads ambient repo state and user input |
| `decomposer` | `Read` | none — turns the cleared scope into ordered features |
| **`writer`** (Write-holder) | `Read`, `Write`, `Edit` | none |

Artifacts land where the skills always write them: the plan directory at
`docs/plans/<slug>/` (feature plan, shared context + decisions ledger, plan.json)
and each feature's `docs/plans/<slug>/specs/<id>/ce-spec.md` + `tasks.json`.
