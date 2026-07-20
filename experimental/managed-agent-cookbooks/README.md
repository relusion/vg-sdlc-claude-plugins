# Unsupported Managed Agent archive

These cookbooks are retained as design references only. They are not part of
the supported `vg-coding` product, are excluded from the repository's required
validation and documentation paths, and receive no compatibility guarantee.

The supported automation surface is the Claude Code plugin under
[`plugins/core-engineering`](../../plugins/core-engineering). Use its skills,
hooks, custom agents, and CI merge bar for production workflows.

## Why this is archived

The Managed Agent beta path duplicated deployment, orchestration, permission,
and validation concerns without proving enough additional user value. Keeping
it in the supported path made the product harder to understand and maintain.

The snapshot remains useful for teams evaluating a hosted-agent substrate. It
contains four sample manifests, steering-event examples, an illustrative host
loop, and local dry-run tooling. The examples do not inherit plugin hooks; any
experiment must provide its own sandbox, tool allowlist, budget, approval, and
audit controls.

## Running the snapshot

From this directory:

```bash
tools/deploy-managed-agent.sh spec-author --dry-run
tools/test-cookbooks.sh
```

Live deployment requires beta API access, `jq`, Python with `pyyaml`, and an
`ANTHROPIC_API_KEY`. Treat all commands as experimental and inspect the
resolved payload before sending it.

See [ORCHESTRATION.md](./ORCHESTRATION.md) for the archived host-flow example.

## Re-entry criteria

Move this capability back into the supported product only after an owner can
show a stable API contract, hook-equivalent host controls, end-to-end tests,
measured adoption, and a workflow outcome that the Claude Code surface cannot
meet as simply.
