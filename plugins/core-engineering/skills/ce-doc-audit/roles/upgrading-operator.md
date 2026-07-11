# Role: upgrading-operator

## Goal
Upgrade a running version-N install to N+1 from the release notes and upgrade
guide alone — without losing data, and knowing how to roll back at every stage.
(Upgrade sibling of `selfhost-operator`, who installs fresh with nothing at
stake yet.)

## Knows
- The product at operator level on version N: its config vocabulary, its
  normal startup logs, how their own deployment is laid out.
- Linux administration and their own environment: where config, data, and
  backups live.
- How to take and restore a backup of their own environment.

## Has access to
- The running version-N environment, its config and data, and current backups.
  (In the audit sandbox: a disposable version-N fixture install — or recorded
  state — stands in for the live environment.)
- The released N+1 artifacts, and the upgrade guide / release notes under
  audit.

## Does NOT know   ← the crux
- What changed between N and N+1: renamed or removed config keys, flag
  changes, new required settings — unless the notes state them.
- Whether the data schema migrates automatically, is one-way, or needs a
  manual step.
- The rollback procedure, and whether rollback is even possible after the data
  migration has run.
- How long the upgrade takes and whether it needs downtime — silence on either
  leaves them unable to plan a maintenance window.

## Cannot see / access
- The source diff between versions, or the maintainers' intent — the release
  notes are the interface.
- Anyone to ask before their maintenance window closes.
- A spare production-grade environment — a rehearsal happens only if the doc
  tells them how.

## Environment
- The same substrate as `selfhost-operator`: an Ubuntu LTS-class server,
  services under Docker or systemd. In the sandbox, steps that would touch the
  live data run against the disposable fixture copy or are recorded
  needs-execution — never against real state.

## Success looks like   ← caps severity
- Version N+1 is running, the doc's own post-upgrade check passes, existing
  data survived, and at every stage they knew the documented rollback point.
  Performance tuning, new-feature adoption, and changelog color are
  after-success.
