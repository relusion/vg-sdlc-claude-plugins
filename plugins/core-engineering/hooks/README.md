# core-engineering hooks

## `git-guard.py` — version-control backstop (PreToolUse, on `Bash`)

Every skill in this toolset promises, in prose, that **the human owns what
enters shared history** — the agent never pushes, opens/merges PRs, tags, or
writes commits to the protected branch on its own. `git-guard.py` makes that a
*structural* checkpoint, so a compacted or autonomous context can't silently
violate it.

It inspects each `Bash` command and, for the few clearly-shared-history git
operations, returns a permission decision:

| Operation | Default decision |
|---|---|
| `git push` — including forms with global options (`git -C DIR push`, `git -c k=v push`, `git --no-pager push`, a `NAME=val` env prefix) | `ask` — confirm before it runs |
| `gh pr create` / `gh pr merge` — including a leading `--repo`/`-R` flag — and `gh api` calls that **write** to a PR endpoint: a path containing `/pulls` or `/merge` with a mutating `-X`/`--method` (POST/PUT/PATCH/DELETE) or a body flag (`-f`/`-F`/`--field`/`--raw-field`/`--input`, which flips gh's default GET to POST). A plain `gh api repos/o/r/pulls` GET, or any `/issues` call, passes silently | `ask` |
| `git tag <name>` — any positional argument, i.e. tag creation, move (`-f`), or deletion (`-d`). Pure listing (bare `git tag`, `git tag -l`, `git tag --list 'v*'`) passes silently | `ask` |
| A history-writing subcommand — `git commit` / `merge` / `revert` / `cherry-pick` / `am` — while HEAD is the protected branch (`origin/HEAD`, else `main`/`master`) | `ask` |
| `xargs` with `git`/`gh` in its tail (`echo push \| xargs git`) — the piped subcommand arrives on stdin, so the guard cannot read it; it confirms instead of guessing | `ask` (always — no env tier) |

The guard splits the command on shell operators and reads each segment's actual
`git`/`gh` subcommand (skipping global options) rather than substring-matching
`git push` — so a global option before the subcommand is still caught, and the
string `git push` inside a commit message or an `echo`/`grep` argument does
**not** trigger a false confirmation. A leading command wrapper (`sudo`, `env FOO=bar`, `nohup`, `timeout 30`), a
shell keyword prefix (`if …; then git push; fi`, a loop body), a nested
interpreter string (`bash -c 'git push'`), a push inside a command
substitution (`x=$(git push)`) or subshell, and an xargs placeholder form
(`xargs -I{} git {}`) are all still caught. Honest limits
(a backstop, not a sandbox): it does not see a push hidden behind shell-variable
indirection, a base64-decoded command, a shell alias, or a wrapper carrying its
own value-taking option (`sudo -u deploy git push`).

Everything else is allowed silently. The default is **`ask`** (a confirmation
prompt), not `deny`, so the guard is safe to leave always-on — it never
hard-blocks a push you explicitly want; it just forces a conscious, in-the-loop
approval. To hard-enforce instead, set the per-operation env tiers —
`CE_GIT_GUARD_PUSH=deny`, `CE_GIT_GUARD_PR=deny`, `CE_GIT_GUARD_TAG=deny`,
`CE_GIT_GUARD_COMMIT=deny` (values `ask`/`deny`; anything else falls back to
`ask`).

**Error posture (fail-closed where it counts).** A payload that parses as a
`Bash` event but carries no readable command is **denied** — after a host
schema change, the command could hide where the guard can't see it, and
failing open would silently retire the backstop. An unparseable payload or
one with no `tool_name` at all gets **`ask`** (an unrecognized shape gets a
human, never a silent pass and never a hard block). A recognized non-`Bash`
event is allowed. Every deny names the escape hatch: the documented kill
switch `CE_GIT_GUARD=off` disables the guard for the environment (use it if
host payload drift ever strands a session, and say why). Decisions are appended
best-effort to `.claude/ce-guard-log.jsonl` through the shared `guard_log.py`
writer — an **unkeyed** sha256 hash chain over each prior raw line, so false-deny
rates stay measurable. `--verify` (`python3
"${CLAUDE_PLUGIN_ROOT}/hooks/guard_log.py" --verify .claude/ce-guard-log.jsonl`,
exit 0 valid / 1 broken / 2 could-not-run) proves **only that the file on disk is
internally self-consistent** — it is corruption-evidence, not adversary-evidence.
It catches accidental damage and a *naive* edit, deletion, or reorder (one that
leaves a later line's `prev` pointing at the pre-change hash). It does **not**
catch an actor with write access to the ledger who edits a line and then
recomputes every downstream `prev` — the chain is unkeyed and its algorithm is
public, so re-chaining is trivial for the very agent the log audits, and the
re-chained file passes `--verify`. It likewise does **not** catch a wholesale
re-genesis (replacing the whole file with one fresh forged genesis line, of any
length) or a tail-truncation; and an empty file or a single genesis line both
report as a "valid chain". **Real tamper-evidence lives out of band:** the chain
head (the last line's sha256 plus the entry count) must be retained by an
**independent party** — git-committed, archived by CI, or delivered to the
auditor — and a later log compared against it; a chain head written back onto the
same agent-writable tree anchors nothing. Two guards deciding on the very same
tool call in parallel could interleave; `--verify` then flags the interleave as a
break rather than lose it silently.

**This is a backstop, not the source of truth.** The prose VC disciplines in the
skills remain verbatim and are the only enforcement on the Claude Managed Agent
deployment, which does not load plugin `hooks.json`.

## `env-guard.py` — secret-file read confinement (PreToolUse, on `Read|Grep|Bash`)

`git-guard.py`'s capability sibling (Rule-of-Two hardening). Where
git-guard backstops *who owns shared history*, env-guard backstops *what an agent
may read*: it **denies** the deterministic file-read vectors behind agent
credential exfiltration — the exact shape of the May-2026 Claude Code GitHub
Action bug:

The guarded set is **data-driven** — `plugins/core-engineering/hooks/guarded-secrets.json`,
loaded beside the hook (the `popular-packages.json` precedent; `CE_GUARDED_SECRETS`
overrides the path). A missing or malformed corpus is never fatal: the hook
degrades **loudly** (stderr) to a built-in `environ`+`.env` floor, so a bad data
edit can neither silently retire the guard nor brick a session.

| Vector | Rule | Default decision |
|---|---|---|
| Process-environment file | any path or `Bash` command text matching `/proc/<pid \| self \| thread-self>[/task/<tid>]/environ` (raw **or** symlink-resolved) | `deny` |
| Home-anchored credential store | a `Read`/`Grep` path or `Bash` token whose realpath matches a `home_path` glob in the corpus (`~/.aws/credentials`, `~/.aws/config`, `~/.ssh/id_*`, `~/.netrc`, `~/.kube/config`, `~/.docker/config.json`, gcloud ADC) — **OR** a directory-targeted read (`grep -r`/`cp -r`/`tar`, or the `Grep` tool pointed at a directory) whose token **is the store's directory or an ancestor of it** (`~/.ssh`, `~/.aws`, `~`/`$HOME`), so a recursive read cannot exfiltrate the same bytes — **denied regardless of cwd**, because a credential store is never workspace content | `deny` |
| Out-of-workspace secret file | a `Read`/`Grep` path, or a `Bash` path token — absolute **or relative** (the branch `cwd`-joins relative tokens **and bare names**, closing the old Read/Grep-vs-Bash asymmetry so a bare-named workspace symlink into a guarded class is caught too), bare or the value half of a `flag=PATH` form like `dd if=PATH` — whose basename matches a `basename` glob in the corpus (`.env`/`.env.*`, `.npmrc`, `.pypirc`, `.envrc`, `*.pem`, `*.key`) and whose realpath falls **outside** the workspace root (`$CLAUDE_PROJECT_DIR`, else the hook's `cwd`); a directory token resolving outside the workspace that **directly holds** such a secret is denied likewise | `deny` |

**The workspace's own `.env`/`.npmrc`/`*.pem` stay readable** — `basename`-class
files are guarded only *outside* the workspace root, while `home_path`-class
credential stores are guarded everywhere; the trust boundary this hook draws is
unchanged. Paths are realpath-resolved on both sides, so a workspace symlink
pointing *out* at a secrets file and an innocent-looking name resolving *into* a
guarded file are both caught — including a **bare-named** symlink read via `Bash`
(`cat server` where `server -> ~/.aws/credentials`), which the Bash branch now
screens symmetrically with `Read`/`Grep`. A guarded basename whose containment
cannot be determined (no resolvable root) is denied **fail-safe**.

Defaults are `deny` (unlike git-guard's `ask`): these reads have no routine
legitimate agent form, and the exfil bug bit in headless contexts where an `ask`
has nobody to answer. Each deny names the human escape hatch: read the file
yourself, copy the needed values into the workspace, or flip the `ENVIRON` /
`ENV_FILE` constants at the top of `env-guard.py` to `"ask"`. To turn the guard
off, remove its `PreToolUse` entry from `hooks.json`.

**Error posture — deliberately stricter than git-guard's fail-open**, because
here a silent allow is the vulnerability itself: an internal error while
screening → **deny** (fail-safe); unparseable hook input → a **loud,
non-blocking** stderr warning (exit 1) — the hook analogue of the lint gates'
"exit 2: could-not-run → fall back loudly", never a silent pass and never a
session-bricking deny-all on harness drift. Every env-guard deny/ask now joins
the shared tamper-evident `.claude/ce-guard-log.jsonl` chain (env-guard carried
no ledger before) — same `guard_log.py` writer, same `--verify` contract and the
same tail-truncation caveat described under git-guard above.

**Honest limitations.** This hook denies the *file-read* vectors only, and its
guarded set is now the data-driven `guarded-secrets.json` corpus (home-anchored
credential stores denied everywhere; `basename` secrets denied outside the
workspace). Both `Read`/`Grep` paths **and** `Bash` tokens are screened — `cat ../../.env`,
a bare-named symlink (`cat server` → `~/.aws/credentials`), and split-quoted
`$HOME` (`cat "$HOME"/.aws/credentials`) are all caught, closing the old Bash
asymmetries; and a directory-targeted read of a home store (`grep -r ~/.ssh`,
`cp -r ~/.aws`, `grep -r ~`) is denied at the directory token, not only the file
token. What remains out of scope, deliberately: environment-variable *expansion*
(`printenv`, `echo $API_KEY` — Bash inherits the process environment with no file
read at all; run agents with no credentials exported, per the Rule-of-Two note in
auto-build); interpreter one-liners (`python3 -c 'open(...)'`, `node -e`);
shell-variable indirection and obfuscation (`F=$HOME; cat $F/.env`, base64-decoded
paths); a `basename`-class secret nested **deeper** under a recursively-read
out-of-workspace directory (the directory screen checks immediate children only —
the home-anchored stores are covered at any depth by the ancestor test, but a
deep out-of-workspace tree is a residual gap); additional working directories
beyond the project root (a legitimate cross-root `.env` read is denied fail-safe —
use the escape hatch); MCP-tool reads; and the Managed-Agent surface, which loads
no plugin hooks (see each cookbook README's isolation tier).

## `write-scope-guard.py` — optional write lease (PreToolUse, on `Write|Edit|MultiEdit|NotebookEdit|Bash`)

The write-scope guard makes a **repo/session write lease** structural when a
policy is present. It is inert by default: if no policy exists, normal Write/Edit
calls proceed silently. Two modes:

- **`lease`** (default): every Write/Edit/MultiEdit/NotebookEdit target must
  match the policy allowlist and miss the denylist. Read-only-on-code skills
  set a lease at their Stage 0 and clear it (restoring the baseline) at exit —
  a *cooperative* convention that makes accidental tool-mediated drift
  structural, not an adversarial sandbox.
- **`deny-only`**: a standing baseline — denylist matches are denied,
  everything else is allowed, no allowlist needed. `/ce-init` seeds this with
  always-true denials (`.git/**` and the lease file itself), so the baseline
  never fights a writing skill like `/ce-implement`.

Every deny names the lease holder and its allowed globs once, then a single
audience-split lift path (the agent reconciles with the holder's write
contract and never edits or deletes the lease; a human deletes a stale lease
and says why), and is logged best-effort to the shared tamper-evident
`.claude/ce-guard-log.jsonl` chain (`guard_log.py`, same `--verify` contract as
the sibling guards). Both runtime files are gitignored.

### Shell write vectors (the `Bash` matcher)

The lease is not only enforced on the Write/Edit-family tools — the same policy
now screens the shell write vectors a `Bash` command can reach. The Bash branch
**reuses git-guard.py's tokenizer by path** (one tokenizer, no fork: the same
segment splitter, quote-aware tokenize, and wrapper/keyword unwrap), then extracts
a write target per vector and screens it through the identical `target_allowed()`
the Write/Edit path uses:

| Vector | What is screened |
|---|---|
| Redirections `>` / `>>` (including `2>`, `&>`, `>\|`) | the file target, scanned **per command segment** (the segment splitter deliberately does not split on `>`); fd-duplications like `2>&1` name no file and are skipped |
| `tee [-a] FILE…` | each non-flag file operand (`-` = stdout, skipped) |
| `sed -i[SUFFIX] … FILE…` | the in-place file operands — **without** `-i`/`--in-place`, sed writes to stdout and nothing is screened; with no `-e`/`-f` the first operand is the sed *script*, not a file |
| `cp` / `mv … DEST` | the destination (last operand, or the `-t DIR` target); a **`mv`'s source** operand is additionally screened against the lease-file hard-deny only (rule 2), because `mv` deletes its source |
| `rm FILE…` | every non-flag operand |
| `dd … of=FILE` | the `of=` value |
| `install [-m…] SRC DEST` / `install -t DIR …` / `install -d DIR…` | the installed destination (last operand, the `-t` dir, or each `-d` created dir) — `install` overwrites its destination |
| `ln [-sf] TARGET LINK` / `ln -t DIR …` | the link name created (last operand, the `-t` dir, or `basename(TARGET)` for a one-operand `ln`) |
| `xargs [opts] <writer> [LITERAL…]` | a literal-operand tail writer (`xargs rm src/x.py`, `xargs dd of=…`) is dispatched through that writer's extractor; a **stdin-fed** operand (`… \| xargs rm`) carries no readable literal target and is a residual |

The screen is **cwd-aware**: it walks the command's segments left-to-right, tracks
the effective working directory across a literal `cd`/`pushd`, and resolves each
**relative** target against that cwd rather than a fixed root — so a relative write
to a denied path or the lease *after* `cd <subdir>` (`cd sub && rm ../<denied>`) is
caught, not mis-resolved to an out-of-workspace pass. When a `cd` destination is
unknowable (`cd "$DIR"`, `cd -`), a subsequent **relative** write target cannot be
resolved and is denied fail-safe.

Two Bash-only posture rules:

1. **Out-of-workspace targets stay permissive.** `/tmp` scratch and any write
   resolving outside the workspace root are not a workspace lease's concern, so
   the Bash branch allows them (unlike the Write/Edit path, which denies
   out-of-workspace targets). Under the `/ce-init` deny-only baseline this means a
   `Bash` write is denied **only** when it lands on a denylisted in-workspace path
   (`.git/**`) or the lease file — everything else, including temp files, passes.
2. **The lease file is guarded across the recognized shell write vectors.** A
   mutation, deletion, or move of the policy file itself
   (`.claude/ce-write-scope.json`, or the `CE_WRITE_SCOPE_POLICY` target) through any
   vector in the table above — a redirect, `rm`, a `mv` **source or destination**,
   `cp`, `tee`, `sed -i`, `dd of=`, `install`, `ln`, or a literal-operand
   `xargs <writer>` — is **hard-denied whenever a policy is enabled**, regardless of
   what the allow/deny lists say; retiring the lease was previously a zero-friction
   bypass of the entire pattern. This screens the **enumerated** write vectors — a
   closed set, not an absolute "never writable" guarantee: interpreter one-liners,
   `$VAR`/backtick indirection, a stdin-fed `xargs`, and an untracked `cd $VAR`
   (below) remain residuals. Wherever the tokenizer sibling can't be loaded, the Bash
   branch degrades to redirect-only screening (rule 2 still applies to redirect
   targets).

Example:

```json
{
  "schema_version": 1,
  "enabled": true,
  "reason": "ce-review may write reports only",
  "allow": [
    "docs/plans/**/specs/**/code-review.md",
    "docs/plans/**/specs/**/review-summary.json",
    "docs/infra-reviews/**"
  ],
  "deny": [
    "src/**",
    "app/**",
    "**/*.py"
  ]
}
```

Set `CE_WRITE_SCOPE_POLICY` to point at a different policy file. This supports
skill-scoped enforcement when an orchestrator or team wrapper can create the
appropriate lease before invoking a read-only/report-writing skill.

**Honest limitations.** Claude Code's current hook payload does not provide a
stable "active skill" field to this repository, so this guard is
**policy-activated, not automatically skill-activated** — an orchestrator or team
wrapper sets the lease before invoking a read-only/report-writing skill. The Bash
screen closes the old "shell writes are ungoverned" gap for the common vectors in
the table above, but it is a best-effort backstop, not a shell sandbox. Still out
of scope, deliberately:

- **Interpreter one-liners** that write through a language API rather than a shell
  vector — `python3 -c 'open("src/x.py","w")'`, `node -e 'fs.writeFileSync(...)'`,
  a `perl -i`. These write no file the tokenizer can see.
- **Shell-variable / command-substitution targets** — `> "$OUT"`, `rm "$LEASE"`,
  `` tee `mkpath` ``. A `$`- or backtick-bearing target is left unscreened (rather
  than deny its literal text and false-fire), so a *variable-indirected* lease
  deletion is a residual — the same indirection class git-guard documents. The
  literal `rm .claude/ce-write-scope.json` is caught; `rm "$LEASE"` is not.
- **`mv`'s source-side deletion of an ordinary file** — a `mv`'s source is screened
  against the lease-file hard-deny (rule 2) only, so `mv <lease> /tmp/` **is** caught,
  but moving an *ordinary* workspace file *out* of the tree (`mv src/x.py /tmp/`) is
  not screened against the allow/deny lists by this vector (a `rm` of the same file
  would be).
- **Stdin-fed / placeholder `xargs`** — a literal-operand `xargs rm src/x.py` is
  dispatched to the writer's extractor, but an operand arriving on stdin
  (`git ls-files … | xargs rm`) carries no readable target, and nested or
  `-I{}`-placeholder xargs forms are best-effort only.
- **Untracked `cd` destinations** — the screen follows a *literal* `cd`/`pushd`, but a
  `cd "$DIR"` / `cd -` / subshell-scoped `cd` leaves the effective cwd unknowable; a
  subsequent *relative* write is then denied fail-safe rather than silently
  mis-resolved, and `popd` / subshell-exit cwd restoration is not modeled.
- **Exotic redirect / option forms** — noclobber games, a redirect operator inside
  a quoted argument (screened as a literal, harmless under the permissive baseline),
  a wrapper carrying its own value-taking option (`sudo -u deploy tee …`).
- **`cp -t DIR` / `sed` multi-file edge forms** resolve to the directory or a
  best-effort operand set, not each written leaf path.

A **malformed policy** fail-safe-denies *both* the Write/Edit-family calls **and**
`Bash` (loud, deliberate — a corrupt lease should halt loudly, not silently pass
writes); delete or fix `.claude/ce-write-scope.json` to clear it. A lease left
behind by a **dead session** is **self-healing**: leases carry a `lease_id` bound
to the owning session in `.claude/ce-write-scope.session.json`, so an in-scope
write from a different session (or a lease orphaned past `CE_WRITE_LEASE_TTL_S`,
default 8h) degrades the lease to the deny-only baseline with a single logged
`ask` naming the holder and its age — no hidden JSON file to hand-delete. A
**live** owner is never degraded.
The Managed-Agent surface loads no plugin hooks (see each cookbook README's
isolation tier), so none of this applies there — the prose write disciplines are
the only enforcement.

## `model-attest.py` — runtime model-tier attestation (PreToolUse, on `Bash`)

`model-policy.json` *declares* which model tier each skill's stages must run on
("judgment / gate / escalation / evidence stages always use the strongest
model"), and `scripts/check.py` §7 lints that promise at commit time. This hook
adds the missing **runtime** leg, so the promise is auditable after the fact and
not only lintable: on every `Bash` PreToolUse event it reads the payload's
`transcript_path`, **tail-scans** that JSONL (a bounded read of the file's tail —
O(1) in transcript length, never a full parse) for the most recent assistant
turn's `model` id, and refreshes `.claude/ce-session-model.json`
`{session_id, model, ts}` under the workspace root. Skills then stamp that
`model` id onto their gate-stage / `attestation` metric lines, and `/ce-retro`
maps it through `model-policy.json`'s `tier_patterns` to surface any gate stage
that ran below its policy tier as an **accepted degradation**.

**Posture — a passive recorder, deliberately the opposite of the guard hooks.**
It emits **no permission decision** (no `permissionDecision` field at all), so it
can neither block a call nor allow one — an emitted `"allow"` would bypass the
sibling git/env/write-scope guards' `ask`/`deny`, so it stays silent and the tool
proceeds exactly as if the hook were absent. It **never raises**: an unparseable
payload, a missing/short/garbled transcript, or an unwritable sidecar is
swallowed and the hook exits 0 — a failed attestation must never cost a tool
call. And it writes the sidecar **only when it actually reads a model**, so a
transcript it cannot parse leaves any previously-recorded value standing rather
than nulling it.

**Honest limitations.** The sidecar is only as current as the last `Bash` event —
a session that never runs a shell command leaves it stale or absent, and a skill
reading it records `model: null` (never a guessed tier). It captures the model of
the *session's* most recent assistant turn, not a per-subagent identity, so a
spawned agent running on a different tier is not separately attributed. And the
**Managed-Agent surface loads no plugin hooks**, so there every `model` field is
`null` — `/ce-retro` reports those as `unattested`, an honest finding rather than
an assumed-fine pass. This is an audit aid, not an enforcement gate: it records
what ran; it never changes what runs.

## `net-guard.py` — egress checkpoint (PreToolUse, on `Bash|WebFetch|WebSearch`)

`env-guard.py` closes the credential-*read* half of the exfiltration bug that
motivated it — but reading a secret is only half of an exfil, and the adversarial
review of this layer noted the guards watched reads and not the **send**.
`net-guard.py` is the send half: it screens OUTBOUND network calls against a
data-driven per-repo allowlist and confirms (or denies) the ones that leave it.

**Inert without a policy.** Like `write-scope-guard.py`, this guard does nothing
until `.claude/ce-net-policy.json` exists — so it is safe to leave always-on and a
no-policy session sees **zero friction** (a non-network `Bash` command like `ls`
or `git status` is never touched even with a policy active). `/ce-init` seeds a
conservative starter; `CE_NET_POLICY` overrides the path (tests/operators). The
policy:

```json
{
  "schema_version": 1,
  "enabled": true,
  "allow_hosts": ["api.github.com", "*.githubusercontent.com"],
  "tiers": {"non_allowlisted": "ask", "upload": "ask"}
}
```

`allow_hosts` is a list of fnmatch host globs; `tiers` values are `ask` (default)
or `deny`. Loopback hosts (`localhost`, `127.0.0.1`, `0.0.0.0`, `::1`) are never
egress and always pass regardless of the allowlist.

| Vector | Default decision |
|---|---|
| An upload PAYLOAD that is a guarded secret — `curl -d @.env`, `curl -T id_rsa`, `curl -F x=@.env.prod`, `wget --post-file=.env` — or a home-anchored credential STORE (`~/.aws/credentials`, `~/.ssh/id_*`) referenced alongside a network verb (`cat ~/.aws/credentials \| curl …`) | `deny` (always — the exfil headline; host-independent) |
| An upload flag (`curl -d/--data*/-F/--form/-T/--upload-file`, `wget --post-data/--post-file/--body-*`) to a **non-allowlisted** host | `upload` tier — `ask`, escalatable to `deny` with `CE_NET_GUARD_UPLOAD=deny` |
| Any network verb (`curl`, `wget`, `nc`, `ssh`, `scp`, `sftp`, `rsync`, …) to a **non-allowlisted** host, and a `WebFetch` to a non-allowlisted URL host | `non_allowlisted` tier — `ask` |
| An allowlisted / loopback host, an upload to an allowlisted host, a non-network command, or `WebSearch` (no target host in its payload) | allow (silent) |

The guarded-secrets corpus is **reused** from `env-guard.py`'s `guarded-secrets.json`
via its WS4-T7 loader (no fork), and the `Bash` scan **reuses git-guard.py's
tokenizer by path** (one tokenizer, no fork), so `sudo curl …`, `timeout 10 curl
…`, and shell-operator chains are read at command position. The strongest finding
wins (deny > ask > silent allow). Decisions route through the shared `guard_log.py`
writer (never raw appends), so every ask/deny joins the sha256 hash chain
alongside its git/env/write-scope siblings.

**Error posture (per-vector).** `CE_NET_GUARD=off` disables the guard entirely
(documented kill switch). Unparseable hook input, or a payload with no
`tool_name`, is a **loud non-blocking** warning (stderr + exit 1) — a guarded call
always arrives as a JSON object, so an unparseable shape cannot carry one; never a
silent allow and never a hard block that would brick every `Bash`/`WebFetch` on
harness drift. No policy file, or a disabled policy → inert. A policy **present but
unreadable/invalid** → `ask` on the call (confirm instead of guessing; fixing the
JSON stops it). An unexpected internal screening error → `ask` (fail toward
confirm, never a silent unscreened egress).

**Honest limitations — a checkpoint, not a network sandbox.** Out of scope and
never implied away: **DNS-tunnel exfil** (data smuggled in subdomain lookups —
`nslookup`/`dig` are not network verbs here), **interpreter / shell sockets**
(`python -c 'import socket…'`, bash `/dev/tcp/host/port`, process substitution),
**MCP-mediated egress** (MCP tools load no plugin hook), **`$VAR` / command-
substitution host indirection** and base64-obfuscated commands, **git's own
transport** (`git clone`/`fetch`/`pull` — git-guard governs push/PR/tag, not
transport), and the **Claude Managed-Agent surface**, which loads no `hooks.json`.
Host extraction is heuristic: an option value may occasionally be mis-read as a
host (an extra harmless `ask`, never a wrong deny), a bare internal hostname with
no dot is not extracted, and a `$VAR` URL is not resolved. The reliably screened,
tested vectors are `curl`/`wget` URLs, their upload flags, and `WebFetch`;
`ssh`/`scp`/`rsync`/`nc` parsing is best-effort. The secrets deny is a
co-occurrence signal, so a `.pem`/`.key` that is actually a **public** cert denies
too (a false deny — use the kill switch or move the file). Like its siblings this
is a cooperative backstop on the Claude Code surface, not an adversarial sandbox.

## `hook-integrity.py` — hook self-integrity (SessionStart)

The four PreToolUse guards above police *tool calls* but cannot detect their
**own** subversion — an in-session `sed -i` on `env-guard.py` silently disarms the
credential-read confinement and no guard notices (the adversarial review's "the
guards cannot detect their own subversion"). `hook-integrity.py` closes that
blind spot from the other side: on **every session start** it recomputes the
sha256 of each `hooks/*.py` + `hooks.json` and compares them to the shipped
`integrity-manifest.json`, printing a loud, named warning on any drift.

**Warn, never block.** SessionStart cannot block a tool call, and a deliberate
local edit or an in-flight plugin upgrade must not brick a session — so the hook
always exits 0. A drift emits a warning to stderr **and** injects it into the
session as SessionStart `additionalContext` (naming each drifted file). A
**missing or unreadable manifest degrades loudly** ("hook tampering cannot be
detected this session") rather than passing silently. Any internal error is
swallowed — a failed self-check must never cost a session. It reads no policy and
no env, and locates its manifest from `__file__` (never `${CLAUDE_PLUGIN_ROOT}`),
so `portability_check` runs it under a scrubbed, harness-free env.

**Two halves, one manifest.** The runtime hook is paired with the commit-time
generator `scripts/hook_manifest.py`:

```bash
python3 scripts/hook_manifest.py --write   # regenerate after an intentional hook edit
python3 scripts/hook_manifest.py --check   # exit 0 fresh · 1 stale · 2 could-not-run
```

`scripts/check.py` §5d runs `--check` on every invocation, so a hook edited
without refreshing the manifest goes **CI-red** (the version-bump-hook pattern:
mechanical freshness). The manifest records `*.py` + `hooks.json` only and
**excludes itself**; both the runtime hook and the generator share one file-set
rule so their views can never diverge.

**Honest bound — tamper-EVIDENCE, not tamper-proofing.** An agent with Bash can
rewrite `integrity-manifest.json` too, so the guarantee is only that the
*committed* manifest is CI-verified and any drift therefore shows up in the
reviewable diff — the same claim class as the merge bar's `sha256sum -c` step,
never a claim that a guard cannot be edited. Data corpora the guards read
(`guarded-secrets.json`) are out of the manifest's tracked set; the scope is the
executable hook code plus its registration (`hooks.json`).
