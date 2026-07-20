# Team Rollout

How an engineering lead takes `core-engineering` from "installed on my
machine" to "how the team ships" — as a bounded pilot with explicit norms,
measurements, and a rollback path. Individual setup lives in
[GETTING-STARTED.md](./GETTING-STARTED.md); this page is about the team.

## The shape: pilot → norms → measure → scale

Don't mandate the whole framework on day one. The skills are independently
useful; adoption sticks when the team meets them in increasing-stakes order:
read-only skills first (zero risk), then one real feature through the spine,
then the gates as merge norms.

## Week 0 — setup (lead + one senior, ~2 hours)

1. **Install** per [GETTING-STARTED.md](./GETTING-STARTED.md) and run
   `/ce-init --write` in the pilot repo — it profiles the repo and writes the
   starter policy artifacts.
2. **Calibrate the policies as a team decision, not a default:**
   - `review-policy.md` — what severity blocks a merge, what's advisory.
     `/ce-review` runs uncalibrated without it *and says so*.
   - `vc-policy.md` — branch/commit conventions the skills must respect.
3. **Set the budget expectation** — share
   [BENCHMARKS.md](./BENCHMARKS.md)'s measured floors (~US$1 for a grounded
   question, ≈US$12 for a tiny feature through the spine, more on real repos)
   so nobody is surprised by model spend, and agree who approves
   `/ce-auto-build` runs (they're budget-capped at Stage 0 by design).

## Weeks 1–2 — the pilot (about 5 engineers)

**Days 1–3, read-only skills** (no write authority — nothing to review, no
risk): `/ce-ask` for codebase questions, `/ce-impact` on real tickets before
estimating them, `/ce-probe-infra` on the manifests. This builds the habit of
*cited* answers and gives everyone a feel for output quality on your code.

**Days 4–10, one real feature through the spine:** pick something
medium-sized and non-critical; run `/ce-brief` → `/ce-plan` → `/ce-spec` →
`/ce-implement`, then `/ce-review` + `/ce-verify` before the PR.

**The one norm that makes the pilot honest:** the generated artifacts
(`docs/plans/<slug>/…`, `ce-spec.md`, `tasks.json`, `verification.md`,
`code-review.md`) go **into the PR and get reviewed like code**. They're
plain markdown/JSON in your repo for exactly this reason. A plan nobody read
is a plan nobody owns.

## Norms that make it stick

- **Artifacts in PRs** — reviewers read the spec before the diff.
- **Honor the locks** — when a skill escalates (the Scope Lock, the
  patch lane graduating to `/ce-plan`), that's the framework working; don't
  pressure it to "just do it here."
- **Humans triage findings** — review/probe findings get an explicit
  Escalate / Defer / Dismiss from a person, recorded in the artifact.
- **Gates are merge conditions, not suggestions** — once the pilot ends,
  `/ce-review` + `/ce-verify` before merge is the team bar for
  framework-built features. The mechanical floor under that norm is the
  **merge bar**: the same `spec-lint` / `test-guard` / `dep-guard` scripts
  run as a required CI status on every PR (see
  [Wire it to branch protection](#wire-it-to-branch-protection)) — and
  because the runner is a plain CI-side script, it gates PRs from any coding
  agent identically, not just framework-built ones.

## What to mandate vs. leave optional

| Tier | Skills | Norm |
|---|---|---|
| Free use, anytime | `/ce-ask`, `/ce-impact`, `/ce-onboard`, `/ce-debug`, probes | encouraged; read-only by contract |
| Per feature | `/ce-brief` → `/ce-plan` → `/ce-spec` → `/ce-implement` | the default path for planned work |
| Before merge | `/ce-review`, `/ce-verify` | required for framework-built features; the `merge-bar` required status (below) is the mechanical floor for every PR |
| Gated | `/ce-auto-build`, `/ce-patch` | auto-build needs a named budget owner; patch ends at one human acceptance gate |
| As needed | ship genre, `/ce-decide`, `/ce-plan-audit`, `/ce-retro` | when the situation calls |

## Wire it to branch protection

The merge bar makes the integrity gates a required PR status — deterministic,
offline, and agnostic to what authored the code. Your engineers can use any
coding agent (or none); the bar gates every PR identically.

**The bar proves integrity, not function.** A green `merge-bar` verdict proves
artifact integrity: traceability held, tests were not weakened, no undeclared
dependency entered a manifest. It never proves test sufficiency (a
weak-but-unweakened suite passes) and never proves a dependency exists on a
registry (dep-guard's offline half only) — and it never builds the project or
runs its test suite. A repo whose only required check is `merge-bar` can merge
code that does not compile behind a green bar: keep your own build/test job as
a second required status check alongside it.

### Preferred path: the composite action (three lines)

Create `.github/workflows/merge-bar.yml` in your repo:

```yaml
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
  with: { fetch-depth: 0 } # the diff gates need the base ref, not a shallow tip
- uses: relusion/vg-sdlc-claude-plugins/action/merge-bar@<PIN-ME-40-HEX-COMMIT-SHA>
```

(Those are the job's steps — wrap them in the standard `on: pull_request`
workflow skeleton shown in
[`action/merge-bar/README.md`](../action/merge-bar/README.md).)

1. **Pin by commit SHA** — replace the placeholder with the **full 40-hex
   commit SHA** of a toolkit release commit you have reviewed. Use the commit
   recorded in the release notes, or independently verify the provenance or
   signature your policy requires before resolving a tag with
   `git rev-parse '<tag>^{commit}'`; do not assume a tag is signed. The action
   refuses a movable tag/branch ref at run time, and that one pin fetches the
   runner, the policy, and every gate script atomically — there are no checksum
   placeholders to fill.
2. **Wire branch protection** — steps 4–6 of the fallback path below apply
   identically: require the status check alongside your own build/test check,
   map the policy's validity to required approving reviews, and protect
   `.github/**` with CODEOWNERS.
3. **Optional local inputs** — step 3 below also applies identically: the
   action reads the `merge-policy.json` override from the **base ref** only,
   and `.github/merge-bar/declared-deps.txt` from **both** base and head (so a
   same-PR declaration is admissible, but only under the two-human escalation
   `.github/merge-bar/**` triggers). The same **cold-start** override applies.

Inputs, outputs, and the full threat model:
[`action/merge-bar/README.md`](../action/merge-bar/README.md).

### Optional: signed verdicts (make the green check verifiable independently)

On `pull_request` your calling workflow runs from the PR merge ref, so a green
`merge-bar` status is only as trustworthy as the workflow file — which a PR can
edit. CODEOWNERS on `.github/**` (step 6 below) is the *prevention* control;
**signed verdicts add the *detection* control** so post-hoc tampering is
evident even when prevention fails. It uses GitHub's built-in keyless OIDC
attestation — **no stored secret, no signing key** — and is opt-in
(GHES/air-gapped runners have no OIDC, so it stays off by default).

1. **Turn signing on** — set the action's `attest: 'true'` input and grant the
   caller workflow `permissions: {contents: read, id-token: write,
   attestations: write}`. After a green verdict the action projects
   `merge-verdict.json` to a whitelisted predicate and sigstore-signs it under
   the workflow's OIDC identity (binding repo + workflow path + trigger SHA).
2. **Verify at branch protection** — add a **second required status check** (or
   merge-queue job) that runs, with `contents: read` + `id-token: write` and no
   secret:

   ```bash
   gh attestation verify merge-verdict.json \
     --repo <org>/<repo> \
     --predicate-type https://github.com/relusion/vg-sdlc-claude-plugins/attestations/merge-verdict/v1
   ```

   then a `jq` assert that the signed predicate's `base_sha`/`head_sha` equal
   the PR's real `git merge-base`/`HEAD` — a valid signature over the wrong
   commits is worthless. Require **both** the `merge-bar` check and this verify
   check. Copy-paste workflow: [`action/merge-bar/README.md`](../action/merge-bar/README.md),
   "Signed verdicts". A green bar is then provable to have judged *these*
   commits under *this* policy hash, regardless of what the workflow file says.
3. **Air-gapped orgs cannot sign** — the copy-in `gates.yml` fallback has no
   attestation path (no OIDC). Those orgs lean entirely on the CODEOWNERS
   prevention control; this is a hosted-runner capability, not a parity feature.

### Air-gapped fallback: the copy-in template

For orgs that forbid third-party GitHub Actions,
`templates/adopter-ci/gates.yml` is the documented fallback — the same
runner, policy, and verdict, pinned by hand-verified checksums instead of an
actions fetch. Under 30 minutes:

1. **Copy the template** — `templates/adopter-ci/gates.yml` from the toolkit
   repo to `.github/workflows/gates.yml` in your repo.
2. **Pin the toolkit** — set `TOOLKIT_REF` to the **full 40-hex commit SHA**
   of a toolkit release commit you have reviewed (never a tag name — the
   workflow refuses anything that isn't 40 hex chars), and fill the five
   `<PIN-ME-*-SHA256>` placeholders. In the toolkit repo at that commit, run:

   ```bash
   python3 scripts/print_pin_block.py --required-only <sha>
   ```

   It prints the `TOOLKIT_REF` line plus these five checksum lines from
   committed state, ready to paste into the "Verify toolkit integrity" step —
   the file set is **derived from `merge-policy.json`'s gate registry**, so a
   future gate addition can never leave the pin block stale (the earlier
   hand-maintained list could). These five decide pass/fail (the runner, the
   policy, and the three **required** gate scripts the policy registers). The policy also
   registers *advisory* gate scripts (`sca-guard`, `implement-scope`,
   `review-gate`, `plan-lint`) whose findings never change the verdict; they are
   not pinned in this minimal block — run `print_pin_block.py <sha>` (no
   `--required-only`) for the **complete** block and add their checksum lines too
   if you want tamper-evidence on advisory findings. On upgrade, the same six
   values change — nothing else. (Every published GitHub Release regenerates and
   prints the complete block for you; see `.github/workflows/release-pin-block.yml`.)
3. **Optional local inputs** — commit `.github/merge-bar/declared-deps.txt`
   (one verified dependency name per line; without it, *every* new dependency
   goes red — that's the fail-safe working, not a bug: a dep nobody declared
   is exactly what the bar exists to catch) and/or a local policy override at
   `.github/merge-bar/merge-policy.json` (e.g. a change class without
   `spec-lint` for repos that don't use the `docs/plans/*/specs/*` layout).
   The **policy override is read from the base ref only** — a PR cannot weaken
   its own policy in the same commit. The **declared-deps list is read from
   both base and head** (the union goes to dep-guard), so a PR *may* declare a
   new dependency in the same commit — but that edit touches
   `.github/merge-bar/**`, which the shipped policy's `class_rules` escalate to
   the two-human `sensitive` bar, so a same-PR declaration is admissible only
   under review (the base policy governs; the PR cannot weaken it same-commit).
   Two documented paths: **prior-PR standard** (declare the dep in a separate,
   earlier PR → the next PR that adds it passes under the normal one-human bar)
   and **same-PR escalated** (declare + add in one PR → two-human). *Cold
   start:* before your first plan exists, `spec-lint` fans out over
   `docs/plans/*/specs/*` and fails closed when none exist — commit an override
   with `"spec_lint_scope": "changed-plans"` so `spec-lint` only gates spec
   dirs a PR touches (and vacuously passes a PR that touches none), and remove
   it once the plan/spec layout is in place to restore the fail-closed `"all"`
   posture.
4. **Require the status** — GitHub Settings → Branches → branch protection
   rule → require the status check **`merge-bar`** *alongside* your own
   build/test required check (integrity, not function — the bar never builds
   the project or runs its test suite; see above).
5. **Map the validity conjunct** — the policy's `validity` is reported in the
   verdict but only branch protection can enforce it: set required approving
   reviews to **1 for `human`**, **2 for `two-human`**, with the reviewer not
   the person who ran the pipeline (segregation of duties). Skipping this
   step silently degrades the bar to integrity-only.
6. **Protect the bar's own inputs** — add `.github/**` to CODEOWNERS (or a
   repository ruleset requiring review from the platform/security owners).
   On `pull_request` the workflow file itself runs from the PR merge ref, so
   without this a PR can rewrite `gates.yml` — the one merge-bar input the
   base-ref reads in step 3 cannot defend. Skipping this step leaves the bar
   editable by the PRs it gates.

### Other CI platforms: GitLab CI and Azure Pipelines

The same bar ships as copy-in ports for the two other common CI surfaces —
identical runner, policy, and verdict, only the platform glue differs. Neither
GitLab nor Azure has a composite-action equivalent, so the **checksum discipline
is the whole product there**, which is exactly why the pin block is generated,
never hand-kept.

- **GitLab CI** — [`templates/adopter-ci/gates.gitlab-ci.yml`](../templates/adopter-ci/gates.gitlab-ci.yml).
  Copy to `.gitlab-ci.yml`; it runs on `merge_request_event`. The diff gates
  compare against `CI_MERGE_REQUEST_TARGET_BRANCH_NAME` (fetched explicitly), the
  toolkit is `git clone`d and `git checkout`ed at the 40-hex `TOOLKIT_REF`, and
  the base-ref reads use `.gitlab/merge-bar/**`. Map the **validity** conjunct to
  a Merge Request **approval rule** (human → 1, two-human → 2), mark the job
  required via "Pipelines must succeed", and protect `.gitlab-ci.yml` +
  `.gitlab/merge-bar/**` with **CODEOWNERS + a protected-branch push rule**.
- **Azure Pipelines** — [`templates/adopter-ci/azure-pipelines-gates.yml`](../templates/adopter-ci/azure-pipelines-gates.yml).
  `trigger: none` + `pr: *`, `pool: ubuntu-latest` (the bash body needs
  bash/coreutils/git/python3), base ref from `System.PullRequest.TargetBranch`,
  base-ref reads under `.azure/merge-bar/**`. Enforce it with an Azure Repos
  **branch policy**: a required **Build validation** running this pipeline plus a
  **Minimum-reviewers** policy (human → 1, two-human → 2, "requestors can't
  approve their own changes"), and a required-reviewers path policy protecting the
  pipeline file + `.azure/merge-bar/**`.

Both fill their five `<PIN-ME-*-SHA256>` placeholders from the same
`python3 scripts/print_pin_block.py --required-only <sha>` generator as the
GitHub template, and carry the full THREAT MODEL / integrity-not-function header.

## Keep it live after merge — the drift monitor

The merge bar judges a PR *before* it lands; nothing re-judges `main` *after*
merge, so a retired surface, a broken traceability link, or a silently-disarmed
security gate can rot for weeks behind a long-green history.
`templates/adopter-ci/drift.yml` closes that gap — it runs the toolkit's
`scripts/drift_scan.py`, which re-projects the repo's committed `HEAD` against
every `docs/plans/plans.json`-registered plan directory and reports drift in the
**same lock vocabulary** the skills use, so a red run routes straight to the
owning skill (**Scope Lock drift → `/ce-plan`**, **Scope Lock drift →
`/ce-spec`**). It is the post-merge complement to the pre-merge bar; adopting
both is what closes "live-and-verified". Under 30 minutes, mirroring the fallback
template above:

1. **Copy the template** — `templates/adopter-ci/drift.yml` from the toolkit
   repo to `.github/workflows/drift.yml` in your repo. It triggers weekly on a
   `schedule` and on every `push` to `main`, with `permissions: contents: read`.
2. **Pin the toolkit** — set `TOOLKIT_REF` to the **same** full 40-hex commit
   SHA you pinned in `gates.yml` (the workflow refuses anything that isn't 40
   hex chars), and fill the three `<PIN-ME-*-SHA256>` placeholders. At that
   commit, run:

   ```bash
   sha256sum scripts/drift_scan.py \
     plugins/core-engineering/skills/ce-plan-audit/scripts/plan-lint.py \
     plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py
   ```

   and paste the three hashes into the "Verify toolkit integrity" step — these
   three decide drift (the scanner and the two lints it runs as its integrity
   oracle). On upgrade, the same three values change — nothing else. Batch
   toolkit script changes into one release so the checksums bind at one ref.
3. **Roll it out advisory-first** — for the first week set
   `DRIFT_ADVISORY_ONLY: '1'`. Legacy or hand-authored plan artifacts often
   carry pre-existing drift; advisory mode **reports** every hard finding but
   never fails the run (`drift_scan --advisory-only`). Read the findings, fix or
   waive them at their owning skill, then clear `DRIFT_ADVISORY_ONLY` to `''` to
   arm the gate — after that, drift on `main` turns the run red.
4. **Optional — escalate to a tracked issue** — set `DRIFT_ESCALATE: '1'` *and*
   add `issues: write` to the job's `permissions:`. On a red run the workflow
   then files a GitHub issue carrying the lock-vocabulary findings, so drift on
   `main` pings a human rather than rotting in a workflow log. It stays off by
   default so the shipped posture is least-privilege `contents: read`.

Unlike `merge-bar`, this workflow is **not** a required PR status — it runs after
merge, so wire notifications (the optional issue, or your CI's failed-run alert),
not branch protection.

## Measuring whether it's working

- **Per plan:** `/ce-retro` aggregates the pipeline's own `.metrics.jsonl`
  stream into descriptive signals — escalation rate, park/retry rate, review
  disposition, testability.
- **Across plans:** `python3 scripts/metrics_report.py --json` gives a
  machine-readable roll-up you can put on a dashboard.
- **Watch for:** rising escalation/park rates (specs too thin → invest in
  briefs), review findings recurring after dismissal (calibrate
  `review-policy.md`), and whether artifacts are actually read in PRs (the
  leading indicator of the whole thing).
- Ask pilot engineers one question at the end: *"which skill would you keep
  if you could only keep three?"* — that's your mandate map for the next team.

## Cost control

Floors and the failure log are published in [BENCHMARKS.md](./BENCHMARKS.md).
Practical rules: budget-cap every `/ce-auto-build` run; prefer `/ce-patch`
for genuinely small changes (it's cheaper and self-gating); treat a
budget-exceeded eval or run as calibration data, not something to retry
blindly.

## Rolling back

There is no lock-in to unwind: uninstall the plugin
(`claude plugin uninstall core-engineering@vg-coding`) and you keep every
artifact — they're plain markdown/JSON in your repo, and the gate scripts
that check them are stdlib-only Python that runs with no Claude Code present
(the portability guarantee, proven in CI). Keep the artifacts as
documentation, or delete the directories; nothing else changes.
