# merge-bar — the merge bar as a composite GitHub Action

Runs the vg-sdlc-claude-plugins merge bar — [`scripts/gate_runner.py`](../../scripts/gate_runner.py)
executing [`plugins/core-engineering/merge-policy.json`](../../plugins/core-engineering/merge-policy.json) —
against every pull request and fails the check when any required integrity
gate fails. It is agent-agnostic: a PR authored by any coding agent — or a
human — gets the identical red/green verdict. Stdlib-only Python, offline,
zero Claude Code installed. The runner enforces the INTEGRITY conjunct only;
the VALIDITY conjunct (human / two-human attestation) maps to required
approving reviews in branch protection (see
[docs/TEAM-ROLLOUT.md](../../docs/TEAM-ROLLOUT.md), "Wire it to branch
protection").

## Adopt it — three workflow lines

Create `.github/workflows/merge-bar.yml` in your repo:

```yaml
name: merge-bar
on: pull_request
permissions:
  contents: read
jobs:
  merge-bar:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with: { fetch-depth: 0 } # the diff gates need the base ref, not a shallow tip
      - uses: relusion/vg-sdlc-claude-plugins/action/merge-bar@<PIN-ME-40-HEX-COMMIT-SHA>
```

The three load-bearing lines are the two `uses:` lines plus `fetch-depth: 0`;
the rest is a standard workflow skeleton.

**Fill the pin before you run it.** Replace `<PIN-ME-40-HEX-COMMIT-SHA>` with
the **full 40-hex commit SHA** of a vg-sdlc-claude-plugins release commit you
have reviewed. When release notes publish a recommended pin, verify the
referenced commit and use that SHA. If you start from a tag, independently
verify the provenance or signature your policy requires, resolve it with
`git rev-parse '<tag>^{commit}'`, and pin the resulting commit. Do not assume
a tag is signed, and never put a tag or branch name in `uses:`: those refs are
movable, commit SHAs are not, and the action refuses a movable ref at run time.

> **Pin source:** the trust decision is the reviewed release commit. A tag may
> help discover or authenticate that commit, but the action consumes the
> immutable 40-hex SHA and works at any reviewed commit.

Then wire branch protection (details in
[docs/TEAM-ROLLOUT.md](../../docs/TEAM-ROLLOUT.md)):

1. Require the `merge-bar` status check **alongside your own build/test
   required check** (see the scope statement below).
2. Require **2 approving reviews globally** in branch protection. GitHub's
   review-count rule is static and cannot vary per PR from the verdict's runtime
   class. This safely enforces both `human` and `two-human`; `human` is a
   reported minimum, not a dynamically lowered host rule. The verdict does not
   count reviews or authorize merge.
3. Protect `.github/**` with CODEOWNERS or a repository ruleset — on
   `pull_request` your calling workflow file runs from the PR merge ref, so
   without this a PR can rewrite the workflow that invokes the action.

## What this proves / what it does not — integrity, not function

A green verdict proves artifact INTEGRITY: traceability held, tests were
not weakened, no undeclared dependency entered a manifest. It never
proves test SUFFICIENCY (a weak-but-unweakened suite passes) and never
proves a dependency EXISTS on a registry (dep-guard's offline half only).
The bar NEVER builds the project and NEVER runs its test suite — a repo
whose only required check is `merge-bar` can merge code that does not
compile behind a green bar. Keep your own build/test job as a second
required status check alongside `merge-bar`.

## Why one SHA pin is the whole verification story

A `uses:` pin fetches this **entire repository** at that immutable commit,
so the action, `scripts/gate_runner.py`, the shipped merge policy, and every
gate script the policy registers arrive **atomically under one SHA** — there
is nothing left to checksum. The checksum-pinned copy-in fallback (below) verifies five
files by hand precisely because it fetches them at a ref it must then prove;
the action collapses that whole step into the pin itself.

## The PR must not grade itself

Same threat model as the copy-in template:

* the `merge-policy.json` override is read from the **base ref**
  (`git show <base>:...`), never from the PR head — a PR cannot swap in a
  weaker policy in the same commit; the new policy applies only after that edit
  merges under review.
* `declared-deps.txt` is read from **both** the base ref and the PR head, and
  the union is passed to dep-guard — so a PR **may** declare a new dependency
  in the same commit. It does not grade itself for free: declaring a dep edits
  `.github/merge-bar/**`, which the shipped policy's `class_rules` escalate to
  the two-human `sensitive` bar, so a same-PR declaration is admissible **only
  under review** — encoded in the base policy (which the PR cannot weaken
  same-commit). Prefer declaring deps in a prior, separate PR for a one-human
  path; declare in-PR when you accept the two-human bar.
* the action ref is rejected at run time unless it is a full 40-hex commit
  SHA, so a movable tag/branch pin fails loudly instead of silently drifting.
* **NOT covered here:** the calling workflow file runs from the PR merge
  ref, so a PR can still edit the workflow that invokes this action. Protect
  `.github/**` with CODEOWNERS or a repository ruleset (required companion
  control — [docs/TEAM-ROLLOUT.md](../../docs/TEAM-ROLLOUT.md) and
  [docs/ENTERPRISE-HARDENING.md](../../docs/ENTERPRISE-HARDENING.md)).

## Signed verdicts — authenticating stored verdict bytes

The threat above ("NOT covered here") has a residue no base-ref read can close:
on `pull_request` the calling workflow runs from the PR merge ref, so a green
`merge-bar` status is only as trustworthy as the workflow file — and a PR can
edit that file. CODEOWNERS or a protected ruleset on `.github/**` is therefore
required. Signing authenticates the exact verdict bytes and signer workflow
identity; it does **not** prove that an untrusted workflow ran the merge bar
honestly or used the expected policy.

With `attest: 'true'`, after a **green** verdict the action projects
`merge-verdict.json` down to a minimal whitelisted predicate
([`scripts/verdict_predicate.py`](../../scripts/verdict_predicate.py) —
`base_sha`, `head_sha`, `policy_sha256`, `status`, `change_class`,
`change_class_source`, `validity_required`, and the `gates[]` id/disposition/status,
**nothing model-derived and no filesystem path**) and calls GitHub's built-in
keyless OIDC attestation ([`actions/attest`](https://github.com/actions/attest),
SHA-pinned) to sigstore-sign it under the workflow's OIDC identity. **No stored
secret, no user-supplied signing key** — the certificate binds the repository,
the workflow path, and the trigger commit. A separate required check then
*verifies* the signature and asserts that the stored predicate names the PR's
real commits. This makes later byte tampering detectable. Trust still depends
on verifying the expected signer workflow/ref and protecting that workflow;
the custom predicate is not SLSA build provenance.

> **Availability:** GitHub Artifact Attestations require a **public repository** (all plans), or a **private/internal repository on GitHub Enterprise Cloud** (not GitHub Enterprise Server). On a user-owned *private* repo `actions/attest` refuses with *"Feature not available for user-owned private repositories."* — and an org-owned private repo on Free/Team plans is likewise unsupported. Leave `attest: 'false'` there (the integrity verdict is unaffected; only the independent signature is), or make the repo public / move it under Enterprise Cloud. The predicate transform and wiring are validated regardless; only the E2E signature depends on the plan tier.

### Turn it on (caller workflow)

Grant the two OIDC permissions and flip the input:

```yaml
name: merge-bar
on: pull_request
permissions:
  contents: read
jobs:
  merge-bar:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write        # actions/attest mints the OIDC token
      attestations: write    # actions/attest stores the attestation
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with: { fetch-depth: 0 }
      - uses: relusion/vg-sdlc-claude-plugins/action/merge-bar@<PIN-ME-40-HEX-COMMIT-SHA>
        with:
          attest: 'true'
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2
        with:
          name: merge-bar-verdict
          path: merge-verdict.json
```

Default (`attest: 'false'`) needs neither permission — leave the two `write`
lines out and the action runs with `contents: read` only.

### Verify it (a second required check / merge-queue job)

Signing proves nothing unless something verifies. Add a **second required
status check** (or a merge-queue job) that verifies the attestation and asserts
the signed predicate judged *this* PR's real commits. This is the half that
turns a signature into a merge gate:

```yaml
name: verify-signed-verdict
on: pull_request
permissions:
  contents: read
jobs:
  verify:
    needs: merge-bar
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with: { fetch-depth: 0 }
      - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093 # v4.3.0
        with:
          name: merge-bar-verdict
          path: .
      - name: Verify the signed verdict
        env:
          GH_TOKEN: ${{ github.token }}
          PTYPE: https://github.com/relusion/vg-sdlc-claude-plugins/attestations/merge-verdict/v1
          SIGNER: ${{ github.repository }}/.github/workflows/merge-bar.yml
        run: |
          set -euo pipefail
          gh attestation verify merge-verdict.json \
            --repo ${{ github.repository }} \
            --signer-workflow "$SIGNER" \
            --predicate-type "$PTYPE"
          # A valid signature over the WRONG commits is worthless: assert the
          # signed predicate judged THIS PR's real merge-base and head. Pull the
          # predicate back out of the verified attestation and diff it against
          # git's own answer for the PR.
          base_sha="$(git merge-base "origin/${{ github.base_ref }}" HEAD)"
          head_sha="$(git rev-parse HEAD)"
          gh attestation verify merge-verdict.json \
            --repo ${{ github.repository }} \
            --signer-workflow "$SIGNER" \
            --predicate-type "$PTYPE" --format json \
            | jq -e --arg b "$base_sha" --arg h "$head_sha" '
                .[0].verificationResult.statement.predicate as $p
                | ($p.base_sha == $b) and ($p.head_sha == $h)
                and ($p.status == "pass")
              ' > /dev/null \
            || { echo "::error::signed verdict does not match this PR's commits"; exit 1; }
```

Require **both** checks (`merge-bar` and `verify-signed-verdict`) in branch
protection. The verify job needs no secret and no OIDC permission. Public-repo
attestations use the public Sigstore transparency log; private-repo attestations
on GitHub Enterprise Cloud use GitHub's private Sigstore service without a
public transparency log.

For protection against a PR-controlled execution context, put signing in a
trusted reusable workflow whose ref and inputs the PR cannot modify, then verify
that workflow with `--signer-workflow` (and an organization-approved signer
policy). Predicate fields are workflow-supplied claims, not trusted facts by
themselves.

> The exact command an adopter runs to check a verdict by hand:
> ```bash
> gh attestation verify merge-verdict.json \
>   --repo <org>/<repo> \
>   --signer-workflow <org>/<repo>/.github/workflows/merge-bar.yml \
>   --predicate-type https://github.com/relusion/vg-sdlc-claude-plugins/attestations/merge-verdict/v1
> ```

### Honest bound — the copy-in fallback does not sign

The copy-in [`templates/adopter-ci/gates.yml`](../../templates/adopter-ci/gates.yml)
has **no attestation path** — the template produces the identical
verdict but cannot sigstore-sign it. What that forfeits: an unsigned verdict is
only as trustworthy as the workflow that produced it, so those orgs must lean
entirely on the prevention control (CODEOWNERS / protected-path rules on the
pipeline file and inputs) without an authenticated stored verdict. Signed verdicts are a
GitHub-hosted-runner capability, not a parity feature — this README states that
rather than implying the fallback signs.

## Cold start — before your first plan exists

The bar's `spec-lint` fans out over `docs/plans/*/specs/*` and fails closed
when none exist, so out of the box it is unusable on a repo with no plans yet.
Until your first plan lands, commit a local policy override at
`.github/merge-bar/merge-policy.json` with `"spec_lint_scope": "changed-plans"`:
`spec-lint` then only gates spec dirs a PR actually touches and **vacuously
passes** a PR that touches none — so a single legacy/broken spec (or an empty
repo) no longer fails every PR. Remove the override once you adopt the
plan/spec layout to restore the fail-closed `"all"` posture. `changed-plans`
trades cold-start usability for scope: it proves nothing about spec dirs a PR
does not touch, by choice.

## Inputs

| Input | Default | Notes |
|---|---|---|
| `base-ref` | `${{ github.base_ref }}` | resolved as `origin/<base-ref>`; set explicitly for non-`pull_request` events |
| `change-class` | `''` | empty (recommended) omits the flag, so the policy's `class_rules` auto-classify each PR from its committed diff (auth/, migrations/, `.github/**` → the two-human `sensitive` bar; else the fallback); set a class (e.g. `standard`, `sensitive`) to FORCE one bar for every PR |
| `declared-deps-path` | `.github/merge-bar/declared-deps.txt` | declared-dependency list, read from **both** the base ref and the PR head (union); a same-PR addition is admissible only under the two-human escalation `.github/merge-bar/**` triggers |
| `policy-path` | `.github/merge-bar/merge-policy.json` | local policy override, read from the **base ref**; absent → the shipped policy |
| `gate-timeout` | `120` | per-gate-run subprocess timeout, seconds |
| `repo-path` | `${{ github.workspace }}` | repository under judgment; override when your checkout used `path:` (also how the self-test drives a fixture repo) |
| `attest` | `'false'` | opt-in [signed verdicts](#signed-verdicts--verifiable-independently-of-the-workflow); `'true'` sigstore-signs a **green** verdict via GitHub's keyless OIDC attestation. Requires the caller to grant `permissions: {id-token: write, attestations: write}`. Default off keeps the 3-line adoption and GHES/no-OIDC compatibility (`contents: read` only) |

## Outputs

| Output | Value |
|---|---|
| `status` | `pass` / `fail` / `error`, from the verdict JSON |
| `verdict-path` | absolute path of the `merge-verdict.json` produced — upload it with `actions/upload-artifact` as merge evidence |
| `predicate-path` | absolute path of the signed-verdict predicate JSON — non-empty only when `attest: 'true'` and the bar came back green |

## Checksum-pinned copy-in fallback

Orgs that forbid third-party GitHub Actions copy
[`templates/adopter-ci/gates.yml`](../../templates/adopter-ci/gates.yml)
instead: the same runner, policy, and gate scripts, fetched at a pinned
commit SHA and verified by five SHA-256 checksums before anything runs.
Same verdict, more pin maintenance — six values change per upgrade instead
of one. Because it fetches the toolkit at run time, disconnected environments
must point the checkout step at an approved internal mirror; this template is
not itself an offline distribution.

## Self-test and Marketplace note

`.github/workflows/action-selftest.yml` in this repository runs the action
(as `uses: ./action/merge-bar`) against a fixture adopter repo on every PR:
an honest change must come back green, and a committed test-gutting cheat
must come back red — so the action's plumbing is proven continuously at
every commit an adopter might pin.

GitHub Marketplace listing requires a root-level `action.yml`; this action
deliberately lives at `action/merge-bar/` inside the toolkit repository so
the runner, policy, and gate scripts ship atomically under one SHA. A thin
root-level forwarder action is a possible future addition if a Marketplace
listing becomes worth it.
