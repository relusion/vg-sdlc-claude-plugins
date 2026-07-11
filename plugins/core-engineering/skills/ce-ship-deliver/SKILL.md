---
name: ce-ship-deliver
description: |
  Construct a clean, house-style delivery branch of a plan's CODE — squashed into human-authored commits, AI tool-exhaust and planning artifacts stripped, built fresh off the org base; never rewrites your branch.
  Triggers: prepare/export a clean delivery or hand-off branch, strip tool metadata. Builds the branch; /ce-ship-release decides the version + go/no-go.
argument-hint: "[plan-slug] [--base <branch>] [--profile <name>]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion, Skill
disable-model-invocation: true
---

# Ship Deliver

**Invocation input:** Plan to deliver (and optional --base / --profile): $ARGUMENTS


Produce a **delivery branch** an organization repo will accept: only the
production code from a plan, in clean human-authored commits, with this toolset's
exhaust removed — built without ever rewriting your working branch.

## The model — construct, don't launder

The safe way to get a clean branch is to **build one**, not to rewrite the messy
one. This workflow takes the net code state of the work, branches fresh off the
org base, and lays down curated commits. It **never** rebases, `filter-repo`s, or
force-pushes the working branch: the source is read-only; the delivery branch is
constructed. History rewriting is the most destructive operation in git — this
workflow does not do it.

## Runtime Inputs

- **Plan slug (required):** e.g. `customer-portal`. Resolve via
  `docs/plans/plans.json`; if missing, ask. Do not guess.
- **`--base` (optional):** the org base branch to build the delivery off.
  Default: the delivery profile's `base_branch`, else the repo's default branch.
- **`--profile` (optional):** a named delivery profile in `vc-policy.md`.
  Default: the repo's single profile, or build one interactively in Stage 0.
- **Loaded:** `docs/plans/<slug>/plan.json` (feature set, ship order, the
  implemented file paths), `docs/plans/vc-policy.md` (the delivery profile),
  any profile-declared supply-chain evidence files, and the working branch's git
  state.

## Execution Contract

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive gate; compute M from the gates that actually fire this run, never a hardcoded constant.

1. **Construct, never launder.** The source branch is read-only. Never rebase,
   `filter-repo`, amend, or force-push it or `main`.
2. **Disclosure is the human's.** Surface it, never conceal it (Disclosure Gate).
   This tool does not decide whether your org must be told AI was used.
3. **Code only.** `docs/plans/**`, `docs/adr/**` (configurable), `**/.metrics.jsonl`,
   and run reports never enter the delivery branch.
4. **Strip only the defined AI markers.** An explicit allowlist (profile
   `strip_markers`) — never anything else, never the Never-Touch set.
5. **Preserve attribution.** `LICENSE`, `NOTICE`, SPDX headers, and **real
   (non-AI) co-authors** are Never-Touch — carried through, never removed.
6. **Author-normalize.** Delivery commits carry the configured human identity,
   a house-style message, and **no** AI trailers.
7. **Supply-chain evidence inventory.** Inventory profile-declared SBOM,
   provenance, signatures, checksums, and other evidence files in the local
   manifest. Include them in the delivery branch only when the profile explicitly
   allows it; otherwise record them as local evidence for `/ce-ship-release`.
8. **Transparency before finalize.** Write the Stripped-Manifest and take a
   material human approval before the branch is final. Never push.
9. **Honor git-guard.** The existing PreToolUse hook still blocks push / PR /
   protected-branch commits — this workflow relies on it, never bypasses it.

## Disclosure Gate  [material — twice-attested]

Before constructing anything, two attestations (the same twice-attested shape as
`/ce-probe-sec`'s consent):

- **Gate A — Policy.** Confirm: *"My organization permits AI-assisted code in
  this repo provided commits follow house conventions, and does **not** require
  AI-use disclosure for this delivery."* If disclosure is **required**, or AI is
  **prohibited** → **STOP.** This is the wrong tool: the honest, lower-risk path
  is to follow that policy, not to automate around it. Say so and exit.
- **Gate B — Scope.** Show, literally, the resolved `base` branch, the delivery
  branch name, the author identity, and the `exclude` / `strip` sets. Capture
  *Run / Edit / Abort* against that concrete plan.

Both attestations are recorded verbatim in the Stripped-Manifest. The workflow
recommends; the human attests.

## Safety Invariants

- **Fresh branch only.** Build off `<base>` in a new worktree. Abort if the
  working tree is dirty or the delivery branch already exists.
- **No push, ever.** No `git push`, no force-push, no PR — the human delivers.
- **Never-Touch list.** Licenses, `NOTICE`, SPDX headers, and non-AI co-authors
  are detected, **preserved**, and listed in the manifest — never stripped.
- **Strip is an allowlist.** Only markers named in the profile are removed;
  every other byte of every included file is left untouched.
- **Marker-match semantics (line-oriented glob).** Each `strip_marker` is matched
  against whole lines — both file content and commit-message trailers — with `*` as
  a wildcard for any run of characters and leading/trailing whitespace ignored. A
  line that matches the pattern is removed **in its entirety**; matching is never a
  substring deletion inside a line that is otherwise kept.
- **Source is read-only.** The working branch and `main` are never modified.

---

## Stage 0 — Load, Profile, and Disclosure Gate

Resolve the plan and the delivery profile. If no profile exists, build one
interactively (schema below) and record it under a `## Delivery Profiles` section
in `docs/plans/vc-policy.md`. Confirm the working tree is clean. Run the
**Disclosure Gate** (A then B). Do not proceed past a failed Gate A.

## Stage 1 — Compute the Delivery Set

1. **Net code diff:** `git diff <base>...<work>` limited to the implemented file
   paths from `plan.json`, **minus** the profile's `exclude_globs`.
2. **Scan included files** for `strip_markers` → record every `file:line` hit.
3. **Detect Never-Touch items** in the set (licenses, `NOTICE`, SPDX, headers) →
   record and protect.
4. **Detect real co-authors** across the work's commits (any `Co-Authored-By`
   that is **not** the AI) → carry them onto the delivery commit(s).
5. **Supply-chain evidence inventory:** scan the profile's
   `supply_chain_evidence.evidence_globs` for SBOM, provenance, checksums,
   signatures, and related artifacts. Record present/missing evidence, format if
   obvious (CycloneDX, SPDX, SLSA provenance), and whether each path enters the
   delivery branch.
6. Present the set as Markdown: files in, paths excluded, markers found,
   attributions preserved.

## Stage 2 — Construct the Delivery Branch

1. Create `<delivery_branch_pattern>` off `<base>` in a worktree.
2. Bring the code (`git checkout <work> -- <paths>`); apply the marker strips to
   included files — **Never-Touch items untouched**.
3. Commit per `commit_granularity` (default `squashed`): author = configured
   identity, message from `commit_message_template`, real co-authors retained,
   AI trailers absent.

## Stage 3 — Manifest and Approval  [material]

1. Write the **Stripped-Manifest** to
   `docs/plans/<slug>/delivery/<date>-manifest.md` — it stays local; it is **not**
   in the delivery branch.
2. Present: the branch + commits, the **full delivery diff vs base**, every
   excluded path, every stripped marker (before → after), every Never-Touch item
   preserved, the Supply-chain evidence inventory, and both attestations.
3. Ask *Finalize / Adjust / Abort*. **Never push.**

## Closing

Report the branch is ready and hand off:

```text
Delivery branch ready: <delivery-branch>  (off <base>)
Commits:   <N> (author: <identity>, no AI trailers)
Excluded:  <count> paths (docs/plans, metrics, …)
Stripped:  <count> markers across <files>
Preserved: <count> attributions (licenses / co-authors)
Manifest:  docs/plans/<slug>/delivery/<date>-manifest.md
```

The human reviews and pushes / opens the PR. This workflow never pushes,
force-pushes, or rewrites.

---

## Delivery Profile — recorded in `docs/plans/vc-policy.md`

```yaml
delivery_profile:
  name: acme-org
  base_branch: main
  delivery_branch_pattern: delivery/<plan-slug>
  author: "Jane Dev <jane@acme.com>"        # default: repo git identity
  commit_granularity: squashed              # squashed | per-feature
  commit_message_template: "<type>(<scope>): <summary>"
  exclude_globs:                            # never enter the delivery branch
    - docs/plans/**
    - docs/adr/**                           # configurable — some orgs want ADRs
    - "**/.metrics.jsonl"
  strip_markers:                            # removed from included files + messages
    - "Co-Authored-By: Claude*"
    - "🤖 Generated with*"
    - "> Generated by /ce-*"
  supply_chain_evidence:
    include_in_delivery_branch: false       # true only if your org wants evidence committed
    evidence_globs:
      - "sbom*.json"
      - "sbom*.xml"
      - "dist/**/*.intoto.jsonl"
      - "dist/**/*.sig"
      - "dist/**/*.sha256"
  never_touch:                              # preserved even if marker-like
    - LICENSE
    - NOTICE
    - "SPDX-License-Identifier"
    - non-AI Co-Authored-By trailers
  disclosure_required: false                # if true → Disclosure Gate A STOPS
```

## Stripped-Manifest Template — `docs/plans/<slug>/delivery/<date>-manifest.md`

````markdown
# Delivery Manifest: <slug>  (<date>)

> Local audit artifact — NOT committed to the delivery branch.

## Attestations
- Gate A (policy permits clean-commit delivery, no disclosure required): <yes>
- Gate B (scope): base <base> · branch <delivery> · author <identity>

## Delivery
- Branch: <delivery-branch>  off  <base>
- Commits: <N>  ·  granularity: <squashed|per-feature>

## Excluded (not in delivery)
| Path / glob | Reason |
|---|---|

## Stripped markers
| File:line | Marker | Before → After |
|---|---|---|

## Preserved (Never-Touch)
| Item | Type |
|---|---|
| LICENSE | license |
| Co-Authored-By: <real person> | human attribution |

## Supply-chain evidence inventory
| Evidence | Path | State | Included in delivery branch? | Note |
|---|---|---|---|---|
| SBOM | <path> | present | no | CycloneDX/SPDX if knowable |
| SLSA provenance | <path> | missing | no | profile glob matched nothing |
| checksums | <path> | present | no | sha256 |
| signatures | <path> | present | no | signer unknown unless artifact says |

## Delivery diff vs base
<git diff --stat output>
````

## Escalation

If delivery policy is unclear or disclosure is required, stop for the human owner.
If release readiness or versioning is the question, route to `/ce-ship-release`.
If the delivery diff exposes missing verification or review, route back to
`/ce-verify` or `/ce-review`. This workflow constructs a local branch and manifest;
it never pushes or opens a PR.

## Honest Limitations

- **Removes deterministic markers; does not make code "non-AI".** Stylometric
  tells — comment density, structure, phrasing — are not touched and **cannot**
  be reliably removed without rewriting the code (and risking bugs). This is not
  an undetectability tool; a real audit can still infer AI use.
- **Hygiene, not a compliance shield.** Your organization's policy governs;
  disclosure is the human's responsibility. The Disclosure Gate makes that
  boundary explicit rather than hiding it.
- **Squashing discards granular history by design.** The per-task / per-feature
  commit trail stays on the working branch; the delivery branch is curated.
- **Marker stripping edits text in included files.** Review the manifest — a
  stripped line could, rarely, carry meaning.
- **It knows only what the profile encodes.** It cannot read your org's full
  policy; an unlisted marker or excluded path is on you to add.
- **Supply-chain inventory is evidence discovery, not attestation.** It records
  profile-declared SBOM, provenance, checksums, and signatures when present; it
  does not generate them, verify signatures, or make the release SLSA-compliant.
