# Role Manifest — the reader you impersonate

A role manifest is the lens for the entire audit. Its two load-bearing sections
are what the role **does not** know (the boundary that turns "an LLM read the
doc" into "a person in role X tried to follow it") and its **success criterion**
(the done-state that caps every finding's severity by position). A vague role
produces vague findings.

## Resolution precedence

The spine resolves `--role` in this order (first match wins), and records the
source in the report for provenance:

1. **Inline** — `--role "<free text>"` describing the reader. Fastest for a
   one-off audience; the skill normalizes it into the fields below and reads it
   back at Gate 1.
2. **Project library** — `docs/roles/<name>.md` in the audited repo. Team-owned,
   versioned, reused across audits. **Preferred for recurring audits.**
3. **Shipped library** — `${CLAUDE_SKILL_DIR}/roles/<name>.md`. Curated starters
   (see `roles/`). Copy one into `docs/roles/` to adapt it.

If none resolves, the skill lists the shipped roles and asks — it never invents a
role silently.

## Shipped starters

Each lives at `${CLAUDE_SKILL_DIR}/roles/<name>.md`; copy one into `docs/roles/`
to adapt it. Pick by the doc genre you are auditing — the role's ignorance
boundary is tuned to the gaps that genre typically hides:

| Role | Reader it simulates | Audits best |
|---|---|---|
| `external-api-consumer` | integrator with only the public docs and one issued API key | API quickstarts and getting-started guides |
| `new-hire-developer` | first-week engineer with a repo clone and zero tribal knowledge | READMEs, dev-setup, onboarding guides |
| `oncall-responder` | paged operator who has never seen the service, at 03:00 | runbooks, incident playbooks |
| `open-source-contributor` | stranger with a fork trying to land a first PR | CONTRIBUTING, build-from-source guides |
| `selfhost-operator` | sysadmin deploying software they didn't write and won't read | install / first-deploy guides |
| `upgrading-operator` | operator of a live version-N install with data at stake | migration / upgrade guides, release notes |
| `evaluating-engineering-lead` | adopt-or-reject decision-maker on a pure reading pass | conceptual docs — architecture, positioning (the conceptual-mode starter) |
| `security-reviewer` | due-diligence reviewer checking every claim has an evidence path | SECURITY.md, hardening and compliance docs |

All shipped starters are technical readers; for end-user product help, supply
an inline role (a reader with the business task, the product UI, and no
terminal) or commit one to `docs/roles/`.

## The contract format

```markdown
# Role: <name>

## Goal
Why this reader opened the doc — the outcome they need. (One sentence.)

## Knows
Prior knowledge the reader brings. Be specific: languages, tools, domain
concepts, house conventions they'd already have. Anything here, the doc may
assume.

## Has access to
Concrete tools, credentials, systems, and permissions the reader holds
(e.g. "a terminal, git, a test API key, read access to the staging DB"). Repo
access? IDE? Cloud console? Say so.

## Does NOT know   ← the crux
The knowledge this reader lacks. Every place the doc silently assumes something
here is an **incomplete** finding. Be honest and specific — "does not know our
internal service names," "has never used the deploy CLI," "doesn't know what
`$GATEWAY_URL` should be."

## Cannot see / access
Systems, files, dashboards, or secrets the reader has no path to. A step that
needs one of these without providing it is a finding.

## Environment
OS, shell, and what is (and isn't) preinstalled. Drives what "run it as written"
actually does in the sandbox.

## Success looks like   ← caps severity
How the reader knows they finished — their done-state. The audit checks the doc
actually gets them here, AND uses this line to set each finding's `position`:
anything the reader hits **after** this point (an optional "confirm it's healthy"
tail, an end-of-doc reference table) caps at **low severity** unless it would stop
the reader from *reaching* success. Draw this line precisely — it is what keeps a
cosmetic nit in an appendix from scoring like a blocker on the critical path.
```

## Writing a good role (anti-cheat guidance)

The failure mode is the impersonation quietly using knowledge the role lacks —
or scoring a trivial appendix nit like a real blocker. Guard against both:

- **Name the gaps explicitly.** "Does NOT know" and "Cannot see" are not
  optional — they are where findings come from. If they're empty, the audit will
  find almost nothing.
- **Draw the success line precisely.** It is the severity fulcrum. "Logged in and
  sees the dashboard" vs "has exercised every optional health check" produce very
  different severity distributions.
- **Prefer a narrower role.** "New hire, first week, backend team" finds more real
  doc gaps than "experienced engineer" because its boundary is wider.
- **Separate knowledge from access.** A reader may *understand* Kubernetes but have
  no cluster credentials — those are different findings.
- **Keep it stable.** For recurring audits, commit the role to `docs/roles/` so
  every run applies the *same* boundary and success line and findings stay
  comparable across doc revisions.

The skill reads the resolved role back at **Gate 1** — the does-not-know boundary
and the success criterion both — so you can catch a too-generous role or a
mis-drawn success line before it weakens the audit.
