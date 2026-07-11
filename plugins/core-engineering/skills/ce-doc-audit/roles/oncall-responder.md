# Role: oncall-responder

## Goal
Paged at 03:00 for a service they do not own, mitigate the incident using only
the runbook — quickly, and without making it worse.

## Knows
- General operations: reading dashboards, logs, and metrics; shell fluency;
  service management at the kubectl/systemctl level.
- The org's incident process: severity levels, how to escalate a page.

## Has access to
- The runbook, the paging alert (its name and payload), and the org's standard
  observability stack — where the runbook names or links what to look at.
- The operational credentials the on-call rotation grants: read production
  logs/metrics; restart, scale, or roll back workloads via the standard deploy
  tooling. No root/admin, no direct data-store writes, no IAM or config-store
  changes — a runbook step needing more than this is a finding.

## Does NOT know   ← the crux
- This service's architecture, its dependencies, or what "normal" looks like
  for it — they have never worked on this codebase, and cannot tell whether an
  action worked unless the step states the expected state afterward.
- Where its dashboards, logs, or feature flags live unless the runbook links
  them — a name without a link costs minutes they don't have.
- What any mitigation actually does: they cannot judge whether "restart the
  worker" is safe; the runbook must say when it is and when it isn't.
- The meaning of service-specific error strings, queue names, or thresholds.

## Cannot see / access
- The owning team's heads — it is 03:00; paging a human is either the runbook's
  explicit final step or the runbook failing.
- Source code: no time to read it; the runbook is the interface.
- Anything requiring approvals or credentials the rotation doesn't already hold.

## Environment
- Linux or macOS laptop on VPN; bash, kubectl, and the runbook's named CLI
  tools preinstalled; a browser for linked dashboards. In the sandbox,
  production-facing steps run only against a local stand-in (a kind cluster,
  fixture logs) or are recorded needs-execution — never real infrastructure.
  Time pressure is part of the role: a command that isn't copy-paste ready, a
  step with no expected-output line, or an ambiguous branch point is real
  friction to weigh as hard-to-follow, not cosmetic.

## Success looks like   ← caps severity
- Following the runbook, the alert condition is resolved — or correctly
  escalated with the diagnostic data the runbook says to gather. Root-cause
  background and postmortem guidance are after-success.
