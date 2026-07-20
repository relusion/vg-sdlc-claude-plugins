# Archived Managed Agent orchestration

> **Unsupported reference.** This document and its companion tools are outside
> the supported product and mandatory validation path. The API and examples may
> drift. Use them only in an isolated experiment with explicit human ownership.

The managed-agent cookbooks are an **experimental**, secondary surface —
deployable workers, not a workflow engine, and not co-equal with the Claude Code
plugin. Your host system owns routing, state, retries, budgets, and human
approvals. This document shows the reference product path:

```text
spec-author -> spec-impl -> quality-gate -> release-coordinator
```

Each worker wraps canonical `core-engineering` skills from
`plugins/core-engineering/skills/`. The skills remain the source of truth.

> **Status & prerequisites.** This path targets the **Managed Agents beta**
> (`anthropic-beta: managed-agents-2026-04-01`) — you need the entitlement on
> your API key. `tools/deploy-managed-agent.sh` requires `jq` and Python
> `pyyaml`. All four cookbooks deploy as **single-process agents**
> (`callable_agents: []` — subagent fanout is not yet wired), and the
> `orchestrate.py` loop referenced below is a **reference implementation you
> run and own**, not a hosted engine. Unlike the Claude Code plugin surface,
> managed agents load **no plugin hooks** — host-side controls are the safety
> boundary here (see each cookbook's README).

## Agents

| Agent | Owns | Skills | Writes |
|---|---|---|---|
| `spec-author` | Plan and implementation-ready specs | `ce-plan`, `ce-spec` | `docs/plans/<slug>/`, `ce-spec.md`, `tasks.json` |
| `spec-impl` | Test-first implementation | `ce-implement` | code/tests, ticked `tasks.json`, `verification.md` |
| `quality-gate` | Review, verification, diagnosis | `ce-review`, `ce-verify`, `ce-debug` | `code-review.md`, `review-summary.json`, `verification-report.md`, `diagnosis.md` |
| `release-coordinator` | Release/docs preparation | `ce-ship-release`, `ce-ship-document` | release decision, docs manifest, user docs on consent |

## Reference Flow

1. Host receives a product/engineering request.
2. Host steers `spec-author`:

   ```json
   {
     "agent": "spec-author",
     "event": "Draft spec: add team invitations with role-based access"
   }
   ```

3. `spec-author` writes `docs/plans/<slug>/` and one or more
   `docs/plans/<slug>/specs/<feature-id>/` directories.
4. Host validates the expected plan/spec artifacts exist, then steers
   `spec-impl` for each approved feature:

   ```json
   {
     "agent": "spec-impl",
     "event": "Implement spec at docs/plans/team-invitations/specs/01-invite-user/"
   }
   ```

5. Host verifies `tasks.json` and `verification.md` exist, then steers
   `quality-gate`:

   ```json
   {
     "agent": "quality-gate",
     "event": "Review and verify docs/plans/team-invitations/specs/01-invite-user after implementation"
   }
   ```

6. If `quality-gate` reports a code defect, host routes to `spec-impl`. If it
   reports a spec or plan defect, host routes to `spec-author`. If the plan is
   clean enough for handoff, host steers `release-coordinator`:

   ```json
   {
     "agent": "release-coordinator",
     "event": "Prepare release handoff for docs/plans/team-invitations after quality gate passed"
   }
   ```

7. Human release owner reviews the release decision, docs, and pending
   approvals. The human pushes, tags, deploys, or publishes outside
   the managed-agent loop.

## Handoff JSON

When a worker needs host routing, it may emit a handoff request in text. The
reference parser in `tools/orchestrate.py` accepts only this narrow shape:

```json
{
  "type": "handoff_request",
  "target_agent": "spec-impl",
  "payload": {
    "event": "Fix CR-1 in docs/plans/team-invitations/specs/01-invite-user/",
    "context_ref": "docs/plans/team-invitations/specs/01-invite-user"
  }
}
```

Allowed targets:

- `spec-author`
- `spec-impl`
- `quality-gate`
- `release-coordinator`

The parser hard-allowlists targets and validates the payload schema. Treat it as
a reference loop only; production systems should prefer typed tool calls,
workflow-engine events, or an out-of-band message bus the model cannot spoof by
quoting repository text.

## Host Gates

Run host-side checks between workers. Minimum gates:

| Transition | Required host evidence |
|---|---|
| request -> `spec-author` | sandbox checkout exists; no production credentials |
| `spec-author` -> `spec-impl` | `plan.json`, feature file, `ce-spec.md`, and `tasks.json` exist; human has approved implementation |
| `spec-impl` -> `quality-gate` | code/tests changed only in sandbox; `tasks.json` completed or partial state recorded; `verification.md` exists |
| `quality-gate` -> `spec-impl` | confirmed code defect or failed verification route |
| `quality-gate` -> `spec-author` | confirmed spec/plan/scope defect route |
| `quality-gate` -> `release-coordinator` | no unresolved high-severity review finding; verification gaps accepted or closed |
| `release-coordinator` -> human release owner | release/docs artifacts exist; no publish action performed by agent |

## Security Defaults

- Use ephemeral checkouts.
- Provide no production credentials to any worker.
- Keep release signing keys and package registry write tokens outside the agent
  environment.
- Restrict network egress for `spec-impl`, `quality-gate`, and
  `release-coordinator` to the minimum needed package/test endpoints.
- Remember plugin hooks do not load on the Managed Agent surface. Tool grants,
  sandboxing, host policy, and post-run inspection are the enforcement layer.

## Local Validation

Before changing cookbooks or orchestration docs, run:

```bash
bash tools/test-cookbooks.sh
```

This dry run checks payload shape only. The repository's supported validation
battery deliberately does not validate this archive.
