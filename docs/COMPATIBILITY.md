# Compatibility And Upgrades

This page defines the supported runtime floor and the safe upgrade path for
`vg-coding`. It is a product-support contract, not a claim that every possible
Claude Code, operating-system, shell, or Git-host combination has been tested.

## Supported Runtime

| Surface | Supported baseline | Evidence and limit |
|---|---|---|
| Claude Code plugin runtime | Claude Code 2.1.195 or newer | CI installs 2.1.195 and runs strict marketplace/plugin validation. Older versions are outside the supported floor; newer versions should still be validated before a broad team rollout. |
| Local gate and hook scripts | Python 3.10+ and Git | Shipped scripts are stdlib-only and the portability suite runs them with no Claude Code installed. Git-dependent checks degrade or stop explicitly when repository evidence is unavailable. |
| Plugin host OS | Any OS supported by the installed Claude Code version | Repository CI exercises Ubuntu. Shell commands, local tools, and path behavior still depend on the adopter environment; report the exact OS and `claude --version` with a bug. |
| Merge bar | GitHub composite action, or the documented GitHub/GitLab/Azure copy-in path | The gate runner itself needs Python and Git, not Claude Code. Host branch protection, required checks, and human review remain external configuration. |
| External systems | No built-in MCP or tracker write integration | Repository-specific MCP servers are optional and must be permissioned, tested, and owned separately. |

Only the latest published repository release is supported; security fixes are
not backported. See the repository-root `SECURITY.md`.

## Before Updating

1. Read the repository-root `CHANGELOG.md`, especially command moves and artifact
   contract changes under `Unreleased` or the target version.
2. Record the installed plugin and Claude Code versions with `claude plugin
   list` and `claude --version`.
3. Commit or otherwise preserve repository policy and `docs/plans/` artifacts.
   An update must not be used to erase evidence or silently regenerate human
   policy.
4. On a representative repository, run `/core-engineering:ce-init --readiness`.
   Treat `external-unverified` host controls as an administrator check, not a
   local pass.

## Update And Verify

Update through Claude Code's plugin flow, then restart Claude Code so the new
plugin bundle is loaded:

```bash
claude plugin update core-engineering@vg-coding
# Only when installed:
claude plugin update product-discovery@vg-coding
```

In the representative repository:

1. Run `/core-engineering:ce-init --readiness` again and review new local gaps.
2. Run one read-only core workflow such as `/core-engineering:ce-ask`.
3. Run one bounded write workflow in a disposable branch or fixture, then
   inspect its diff and verification evidence.
4. Re-run the repository's normal build/test CI and merge bar. A green merge
   bar does not substitute for the build/test job.
5. Promote the update team-wide only after the plugin output, hooks, and
   required host checks behave as expected.

## Current Migration Notes

| Previous behavior | Current path | Operator action |
|---|---|---|
| Retired `ce-probe-ux` identifier | `/core-engineering:ce-ux-audit` adversarial-discovery mode | Change direct invocations; the old skill has no tombstone wrapper. |
| Retired `ce-troubleshoot` identifier | `/core-engineering:ce-debug` plan-free mode | Change direct invocations; existing investigation artifacts remain ordinary repository files. |
| Core-owned `ce-idea-*` / `ce-market-scan` calls | `/product-discovery:...` namespace | Install the companion plugin only for product-discovery work and update qualified commands. |
| Advanced `ce-patch` modes | Conservative two-file `/core-engineering:ce-patch` lane | Route structural, dependency, or uncertain work to `/core-engineering:ce-plan`. |
| Multi-mode auto-build orchestration | One bounded sequential auto-build profile | Review and re-approve bounds; do not assume removed worktree/checkpoint modes still exist. |
| Unstamped done tasks could pass the legacy freshness check with a warning | Release uses strict freshness | Re-open through `/core-engineering:ce-implement` to bind or re-derive evidence, then rerun `/core-engineering:ce-verify`; do not convert the release NO-GO into tool approval. |
| Unversioned or schema-v1 metrics | Schema-v2 producers and coverage-aware reporting | Existing lines remain readable. Missing streams and runtime metadata now appear as gaps instead of zero activity. |
| Schema-v1 `architecture-selection.json` | Schema-v2 selections bind the immutable human-readable `architecture-options.md` review snapshot | Existing v1 selections remain valid but have no options-report guarantee. To obtain one, reopen architecture direction selection through plan revision and review fresh options; never fabricate a report or imply retrospective approval. |
| Schema-v1 `architecture/` package | Strict schema-v2 architecture consumer contract | Run `/core-engineering:ce-architecture <slug>` to regenerate and review the complete baseline. `--allow-legacy-v1` is diagnostic only; specification, implementation, review, and publication reject a v1 package as authority. |
| Spec without `architecture_context`, or context schema v1 | Schema-v2 feature binding seals project/feature identity plus the current plan, selected direction, accepted ADRs, package receipt, feature mapping, and gaps | Re-run `/core-engineering:ce-spec <slug>/<id>`. The shipped merge bar now requires H7, and deleting the tasks context cannot downgrade a previously bound spec to legacy. Preserve the old spec for review; do not hand-copy or invent digests. |
| Schema-v1 `review-summary.json`, or tasks with no concrete `tasks[].files` scope | Schema-v2 review evidence binds the current specification, architecture context, declared files, non-ignored repository state, and exact evaluated commit | Re-run `/core-engineering:ce-review <slug>/<id>` after re-specifying any unbound legacy spec. Repositories that promoted `review-gate` to required will fail closed until current evidence exists; do not weaken the local policy as a migration shortcut. |
| One date-only snapshot name per day | Collision-safe run keys | The first path keeps `<date>`; later same-day runs use `-2`, `-3`, and the same key across report and evidence companions. |

## Rollback And Support

If an update breaks a repository workflow, stop write-capable runs, preserve the
working-tree diff and guard/eval receipts, and disable the plugin until the
team restores a previously reviewed bundle through its normal plugin-management
process. Do not delete `docs/plans/`, rewrite metrics, or bypass a live write
lease to make the older behavior appear green.

When reporting a compatibility problem, include the plugin version, Claude Code
version, OS, failing command or skill, expected/observed result, and a minimal
repository fixture with secrets removed.
