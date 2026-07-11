# Spec Impl — managed-agent template

## Overview

Approved spec → working code + tests, a ticked `tasks.json`, and the spec's `verification.md`. Built on the [`core-engineering`](../../plugins/core-engineering) plugin's `ce-implement` skill — this directory is the Managed Agent cookbook for `POST /v1/agents`.

## Deploy

```bash
export ANTHROPIC_API_KEY=sk-ant-...
../../scripts/deploy-managed-agent.sh spec-impl
```

## Steering events

See [`steering-examples.json`](./steering-examples.json).

## Security & handoffs

**Isolation tier: privileged worker.** Shell + working-tree write (`agent.yaml`
grants `bash` and `write`). By the **Rule of Two** ({untrusted input, secret
access, external write} — hold at most two) it already holds untrusted input +
write-with-shell, so the deployment **must cut the secrets leg**: ephemeral
checkout, **no credentials in the environment**, egress limited to package
mirrors (detailed below). Plugin hooks (`git-guard.py`, `env-guard.py`) do
**not** load on this surface — `agent.yaml` tool config, the system prompt, and
your sandbox are the only enforcement here.

Spec Impl runs against a working tree and executes shell commands — treat it as a privileged worker on a sandboxed checkout, never against your real repo. It is single-process in the skeleton (`callable_agents: []`); a recommended fanout if you add subagents:

| Leaf | Tools | Connectors |
|---|---|---|
| `reader` | `Read`, `Grep`, `Glob` | none — surveys the existing code |
| `runner` | `Read`, `Bash` (sandboxed) | none — runs the test suite, captures output |
| **`writer`** (Write-holder) | `Read`, `Write`, `Edit` | none |

Sandbox the working tree: an ephemeral checkout, no credentials in env, no network egress beyond package mirrors.
