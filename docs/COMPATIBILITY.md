# Compatibility And Upgrades

This is the supported runtime and upgrade contract, not a claim about every host
combination.

## Supported runtime

| Surface | Baseline | Limit |
|---|---|---|
| Claude Code | 2.1.195+ | CI validates the floor on Ubuntu; validate newer versions in a pilot |
| Local hooks and gates | Python 3.10+ and Git | Shipped Python is stdlib-only; Git-dependent checks stop or degrade explicitly |
| Plugin host OS | An OS supported by Claude Code | CI exercises Ubuntu; shell/tool behavior remains repository-specific |
| Merge bar | GitHub action or documented GitHub/GitLab/Azure copy-in | Requires Python and Git, not Claude Code |
| External systems | Repository-owned integration | No built-in tracker write or deployment authority |

Only the latest published release is supported. Security fixes are not
backported; see the root security policy.

## Breaking lean-core release

This redesign intentionally changes the public workflow:

- one canonical plan-directory shape replaces special feature-count modes;
- a brief is optional;
- architecture work runs only when load-bearing and uses an iterative
  evidence/question/adjust/selection loop;
- plan records `Specification route: compact|explicit`;
- compact implementation composes and lints the canonical spec artifacts;
- review and verification remain independent but can be orchestrated;
- verified documentation and any risk-triggered documentation audit precede
  the final release decision;
- only actual human decisions are gates.

Do not preserve old artifact modes by weakening validators or fabricating
receipts. Re-run the owning workflow on a representative branch and review the
new canonical artifacts.

## Before updating

1. Read `CHANGELOG.md`.
2. Record plugin and Claude Code versions.
3. Commit or otherwise preserve policy, plan, and evidence artifacts.
4. Run `/core-engineering:ce-init --readiness`.
5. Choose a representative compact feature and an explicit/load-bearing
   feature for the pilot.

## Update and verify

```bash
claude plugin update core-engineering@vg-coding
# If installed:
claude plugin update product-discovery@vg-coding
```

Restart Claude Code, then:

1. rerun readiness;
2. run one read-only ask or impact workflow;
3. plan and build one compact and one explicit feature on a disposable branch;
4. verify architecture selection and adjustment on genuinely load-bearing work;
5. run independent review and verification;
6. when documentation is impacted, generate and conditionally audit it, then
   prepare the release package;
7. rerun normal build/test/security CI and the merge bar.

Promote only after outputs, hooks, receipts, and Git-host controls behave as
expected.

## Rollback and support

On failure, stop write-capable runs, preserve the diff and receipts, and restore
a previously reviewed plugin bundle through the normal plugin-management
process. Do not delete plan/evidence artifacts or bypass a live write lease.

Include plugin version, Claude Code version, OS, command, expected/observed
behavior, and a secret-free fixture in a bug report.
