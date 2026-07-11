#!/usr/bin/env python3
"""Optional PreToolUse write-scope guard for Write/Edit tools and Bash writes.

The Claude Code hook surface does not provide a stable "currently running skill"
signal to this repository. This guard therefore stays inert unless a policy file
exists. When active, it makes a session/repo-scoped write lease structural:
Write/Edit/MultiEdit/NotebookEdit targets — and the shell write vectors a Bash
command can reach (`>`/`>>` redirections, `tee`, `sed -i`, `cp`/`mv` plus a `mv`'s
deleted source, `rm`, `dd of=`, `install`, `ln`, and a literal-operand `xargs
<writer>` tail) — must stay inside the allowlist and outside the denylist. The Bash
half reuses git-guard.py's tokenizer by path (one tokenizer, no fork), walks the
command's segments cwd-aware (tracking `cd`/`pushd` so a relative target after
`cd <subdir>` resolves against the real cwd, not the root), and adds per-vector
target extraction on top. Two Bash-only posture rules: out-of-workspace targets
(`/tmp` scratch and the like) are not a workspace lease's concern and stay
permissive; and mutation, deletion, or move of the lease file itself is HARD-DENIED
through those recognized shell write vectors whenever a policy is enabled, so a
literal `rm`/`mv`/`install`/`ln`/redirect onto `.claude/ce-write-scope.json` can no
longer silently retire the lease (interpreter one-liners, `$VAR`/backtick
indirection, a stdin-fed `xargs`, and an untracked `cd $VAR` stay documented
residuals — see hooks/README.md; this is a cooperative backstop, not a sandbox).

Session-bound leases (self-healing stale leases). A lease-mode policy carries a
`lease_id` + `created_at` (stamped by write-lease.py). On the first lease-mode
evaluation this guard binds the lease to the host-owned `session_id` from the
hook payload, recording ``{lease_id, session_id, bound_at}`` in a sidecar beside
the lease (``.claude/ce-write-scope.session.json``). When a later event carries a
DIFFERENT session_id for that same lease — or the lease predates the lease TTL and
no live session ever owned it — the lease belongs to a dead session, so the guard
DEGRADES TO WARN-AND-REPLACE instead of a hard deny: it rewrites the lease to the
deny-only baseline, logs the replacement, and returns a single ``ask`` naming the
stale holder, its age, and what happened — so a week-one user never hunts down a
hidden JSON file to hand-delete. Any ambiguity — no session_id, a legacy lease
with no `lease_id`, or an unreadable sidecar — fail-safes to the ordinary deny
path (same-session out-of-scope writes still hard-deny, unchanged). The TTL is a
generous backstop for an orphan left with no sidecar; override it with
``CE_WRITE_LEASE_TTL_S`` (a live owner recorded in the sidecar is never degraded
by the TTL).

Two policy modes:

* ``lease`` (the default) — the current session holds a write lease: targets
  must match the allowlist and miss the denylist. Read-only skills set this at
  their Stage 0 and clear it at exit (cooperative — see hooks/README.md).
* ``deny-only`` — a standing baseline: targets matching the denylist are
  denied, everything else is allowed. No allowlist required. `/ce-init` seeds
  this with always-true denials (`.git/**` internals and the lease file
  itself) so the baseline never fights a writing skill.

Every deny states the verdict once — which skill holds the lease and what it
may write — then a single audience-split lift path: the agent reconciles with
the holder's write contract and never edits or deletes the lease; a human
deletes a stale lease and says why. Denies are also appended, best-effort,
to ``.claude/ce-guard-log.jsonl`` through the shared ``guard_log.py`` writer —
a sha256 hash chain over the prior line, so false-deny rates stay measurable and
after-the-fact edits/deletions/reorders of the ledger are detectable
(``python3 guard_log.py --verify <file>``).

Default policy path:
  .claude/ce-write-scope.json

Override:
  CE_WRITE_SCOPE_POLICY=/absolute/or/relative/path.json

Example (lease mode):
{
  "schema_version": 1,
  "enabled": true,
  "skill": "ce-review",
  "reason": "ce-review may write reports only",
  "allow": ["docs/plans/**/specs/**/code-review.md", "docs/infra-reviews/**"],
  "deny": ["src/**", "app/**", "**/*.py"]
}

Example (baseline):
{
  "schema_version": 1,
  "enabled": true,
  "mode": "deny-only",
  "reason": "core-engineering baseline: git internals and the lease file are not agent-writable",
  "deny": [".git/**", ".claude/ce-write-scope.json"]
}
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path


def _load_guard_log():
    """Load the shared hash-chained log writer sitting beside this hook. By-path
    (importlib) so the portability AST scan sees only stdlib imports; wrapped so a
    missing/broken sibling degrades to no logging rather than crashing the guard."""
    try:
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard_log.py")
        spec = importlib.util.spec_from_file_location("ce_guard_log", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _load_git_guard():
    """Load git-guard.py's Bash tokenizer (segment splitter / _tokenize / _unwrap
    / _program) sitting beside this hook. By-path (importlib) so the portability
    AST scan sees only stdlib imports and there is ONE tokenizer, not a fork;
    wrapped so a missing/broken sibling degrades to redirect-only Bash screening
    rather than crashing the guard. git-guard's module body has no import-time side
    effects (its `main()` runs only under `__name__ == '__main__'`)."""
    try:
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "git-guard.py")
        spec = importlib.util.spec_from_file_location("ce_git_guard", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


_GUARD_LOG = _load_guard_log()
_GIT_GUARD = _load_git_guard()

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
DEFAULT_POLICY = ".claude/ce-write-scope.json"
SESSION_SIDECAR = ".claude/ce-write-scope.session.json"
LEASE_TTL_ENV = "CE_WRITE_LEASE_TTL_S"
# Generous backstop for a lease orphaned with NO session sidecar (the primary
# staleness signal is a session-id mismatch); a live owner in the sidecar is
# never degraded by the TTL. Env-overridable via LEASE_TTL_ENV; <= 0 disables it.
DEFAULT_LEASE_TTL_SECONDS = 8 * 60 * 60
MODES = {"lease", "deny-only"}

# The deny-only baseline this guard restores when it degrades a dead session's
# lease. Mirrors write-lease.py's BASELINE and ce-init's seeded floor: git
# internals and the lease file itself are never agent-writable.
BASELINE_POLICY = {
    "schema_version": 1,
    "enabled": True,
    "mode": "deny-only",
    "reason": (
        "core-engineering baseline restored by write-scope-guard: the prior "
        "session write lease was orphaned by a dead session and auto-replaced"
    ),
    "deny": [".git/**", DEFAULT_POLICY],
}


def deny_message(verdict: str, policy: dict) -> str:
    """Compose a deny: the verdict, which skill holds the lease and what it may
    write, then ONE audience-split lift path. The lease path appears exactly
    once (in the Human half) — the agent is never invited to touch the lease.
    """
    verdict = verdict.rstrip(". ")
    lift_target = f"{DEFAULT_POLICY} (or the CE_WRITE_SCOPE_POLICY target)"
    if policy.get("mode", "lease") == "lease":
        skill = policy.get("skill")
        holder = (
            f"/{skill.strip()}" if isinstance(skill, str) and skill.strip()
            else "the lease-holding skill"
        )
        allow = policy.get("allow") if isinstance(policy.get("allow"), list) else []
        globs = (
            ", ".join(str(pat) for pat in allow) if allow
            else "nothing (this session writes no files)"
        )
        return (
            f"core-engineering write-scope-guard: {verdict}. "
            f"A write lease is held by {holder}; allowed writes: {globs}. "
            f"Agent: reconcile with {holder}'s write contract; do not edit or "
            f"delete the lease. Human: if this session is not {holder}, the "
            f"lease is stale — delete {lift_target} and say why."
        )
    reason = str(policy.get("reason", "no reason recorded")).rstrip(". ")
    return (
        f"core-engineering write-scope-guard: {verdict}. "
        f"Policy reason: {reason}. "
        f"Agent: do not edit or delete the write-scope policy. "
        f"Human: if this policy is wrong for this session, delete "
        f"{lift_target} and say why."
    )


def log_decision(root: Path, decision: str, tool: str, target: str, reason: str,
                 payload: dict | None = None, session_id: str = "",
                 hook_event: str = "PreToolUse") -> None:
    """Best-effort, hash-chained record of guard decisions, false-deny
    measurement (via the shared guard_log.py writer). Never raises: a logging
    failure must not change a permission decision. The blocked `target` is
    carried by the deny `reason` and bound by `payload_sha256` (the tool_input),
    so the shared entry schema keeps no separate target field.
    """
    if _GUARD_LOG is None:
        return
    try:
        _GUARD_LOG.append_entry(
            str(root), "write-scope-guard", decision, reason, payload,
            session_id=session_id, tool=tool or "", hook_event=hook_event,
        )
    except Exception:
        pass


def hook_decide(decision: str, reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))
    raise SystemExit(0)


def workspace_root(cwd: str | None = None) -> Path:
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd()
    return Path(raw).expanduser().resolve()


def policy_path(root: Path) -> Path:
    raw = os.environ.get("CE_WRITE_SCOPE_POLICY")
    if raw:
        path = Path(raw).expanduser()
        return path.resolve() if path.is_absolute() else (root / path).resolve()
    return (root / DEFAULT_POLICY).resolve()


def load_policy(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        hook_decide(
            "deny",
            f"core-engineering write-scope-guard: policy {path} could not be read "
            f"({exc.__class__.__name__}). Denying fail-safe.",
        )
    if not isinstance(data, dict):
        hook_decide("deny", f"core-engineering write-scope-guard: policy {path} is not a JSON object.")
    if data.get("schema_version") != 1:
        hook_decide("deny", f"core-engineering write-scope-guard: policy {path} must set schema_version: 1.")
    return data


def inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def rel_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def as_patterns(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        hook_decide("deny", "core-engineering write-scope-guard: policy allow/deny entries must be arrays.")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            hook_decide("deny", "core-engineering write-scope-guard: policy patterns must be non-empty strings.")
        out.append(item.strip())
    return out


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def target_allowed(root: Path, policy: dict, target: Path) -> tuple[bool, str]:
    target = target.expanduser()
    if not target.is_absolute():
        target = (root / target).resolve()
    else:
        target = target.resolve()
    if not inside(target, root):
        return False, f"target `{target}` is outside workspace `{root}`"

    rel = rel_posix(target, root)
    mode = policy.get("mode", "lease")
    if mode not in MODES:
        return False, f"write-scope policy mode {mode!r} is unknown (use 'lease' or 'deny-only')"
    allow = as_patterns(policy.get("allow"))
    deny = as_patterns(policy.get("deny"))
    if matches(rel, deny):
        return False, f"`{rel}` matches write-scope denylist"
    if mode == "deny-only":
        return True, f"`{rel}` allowed (deny-only baseline, no denylist match)"
    if not allow:
        return False, "write-scope policy has no allow patterns"
    if not matches(rel, allow):
        return False, f"`{rel}` is outside write-scope allowlist"
    return True, f"`{rel}` allowed by write-scope policy"


def extract_target(tool_input: dict) -> str | None:
    for key in ("file_path", "path", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


# --- Bash write-vector screening ---------------------------------------------
#
# git-guard.py already owns a battle-tested Bash tokenizer (segment splitter,
# quote-aware _tokenize, wrapper/keyword _unwrap, _program). We REUSE it by path
# — one tokenizer, no fork — and add write-target extraction per shell vector on
# top. Redirect targets are scanned on the RAW command because git-guard's
# segment splitter deliberately does not split on `>`.

# A redirect operator + its file target (`>`/`>>`/`2>`/`&>`/`>|`). `(?!&)` skips
# fd-duplications (`2>&1`, `>&2`) — those name no file to screen.
_REDIRECT_TARGET = re.compile(
    r"(?:[0-9]*|&)>>?(?!&)\|?\s*"
    r"('[^']*'|\"(?:[^\"\\]|\\.)*\"|[^\s;|&<>()`]+)"
)


def _strip_quotes(tok: str) -> str:
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ("'", '"'):
        return tok[1:-1]
    return tok


def _strip_redirect_tokens(tokens: list) -> list:
    """Drop redirect operators and their target tokens from a tokenized segment,
    so the program-specific extractors never mistake `> out` for a file operand
    (the redirect target is caught separately by _REDIRECT_TARGET on the raw
    command)."""
    out: list = []
    skip_next = False
    for t in tokens:
        if skip_next:
            skip_next = False
            continue
        if re.fullmatch(r"(?:[0-9]*|&)?(?:>>?|<)", t):
            skip_next = True  # bare operator: the FOLLOWING token is its target
            continue
        if re.match(r"^(?:[0-9]*|&)?(?:>>?|<)", t):
            continue  # attached form: `>out`, `2>out`, `<in`
        out.append(t)
    return out


def _tee_targets(tokens: list) -> list:
    out, seen_ddash = [], False
    for t in tokens[1:]:
        if not seen_ddash and t == "--":
            seen_ddash = True
            continue
        if t == "-":
            continue  # `-` is stdout, not a file
        if not seen_ddash and t.startswith("-"):
            continue
        out.append(t)
    return out


_SED_ARG_OPTS_SHORT = frozenset({"e", "f", "l"})  # short sed opts that take a value


def _sed_targets(tokens: list) -> list:
    """File operands of a `sed -i` (in-place) invocation. Without `-i`/`--in-place`
    sed writes to stdout — no target. When no `-e`/`-f` script flag is present the
    FIRST operand is the sed script, not a file."""
    in_place = script_via_flag = False
    operands, i, n = [], 1, len(tokens)
    while i < n:
        t = tokens[i]
        if t == "--":
            operands.extend(tokens[i + 1:])
            break
        if t.startswith("--"):
            name = t.split("=", 1)[0]
            if name == "--in-place":
                in_place = True
            elif name in ("--expression", "--file"):
                script_via_flag = True
                if "=" not in t:
                    i += 1
            elif name == "--line-length" and "=" not in t:
                i += 1
            i += 1
            continue
        if t.startswith("-") and t != "-":
            body, j, consume_next = t[1:], 0, False
            while j < len(body):
                c = body[j]
                if c == "i":
                    in_place = True
                    break  # remainder of this token is the backup suffix
                if c in _SED_ARG_OPTS_SHORT:
                    if c in ("e", "f"):
                        script_via_flag = True
                    if j + 1 < len(body):
                        j = len(body)  # value attached in the same token
                    else:
                        consume_next = True
                        j += 1
                else:
                    j += 1
            if consume_next:
                i += 1
            i += 1
            continue
        operands.append(t)
        i += 1
    if not in_place:
        return []
    return operands if script_via_flag else operands[1:]


def _cp_mv_targets(tokens: list) -> list:
    """Destination operand of a `cp`/`mv`. `-t DIR`/`--target-directory` names the
    destination directory; otherwise the LAST operand is the destination. Only the
    write side is screened — a `mv`'s source-side deletion is a documented residual."""
    operands, target_dir, i, n = [], None, 1, len(tokens)
    while i < n:
        t = tokens[i]
        if t == "--":
            operands.extend(tokens[i + 1:])
            break
        if t in ("-t", "--target-directory"):
            if i + 1 < n:
                target_dir = tokens[i + 1]
            i += 2
            continue
        if t.startswith("--target-directory="):
            target_dir = t.split("=", 1)[1]
            i += 1
            continue
        if t in ("-S", "--suffix"):
            i += 2
            continue
        if t.startswith("--suffix="):
            i += 1
            continue
        if t.startswith("-") and t != "-":
            i += 1
            continue
        operands.append(t)
        i += 1
    if target_dir is not None:
        return [target_dir]
    return [operands[-1]] if len(operands) >= 2 else []


def _rm_targets(tokens: list) -> list:
    out, seen_ddash = [], False
    for t in tokens[1:]:
        if not seen_ddash and t == "--":
            seen_ddash = True
            continue
        if not seen_ddash and t.startswith("-") and t != "-":
            continue
        out.append(t)
    return out


def _dd_targets(tokens: list) -> list:
    return [t[3:] for t in tokens[1:] if t.startswith("of=") and len(t) > 3]


# install options that consume the FOLLOWING token — their value is not a path.
_INSTALL_OPTS_WITH_ARG = frozenset({
    "-m", "--mode", "-o", "--owner", "-g", "--group", "-S", "--suffix",
})


def _install_targets(tokens: list) -> list:
    """Destination(s) of a coreutils `install`. `-t DIR`/`--target-directory` names
    the destination dir; `-d`/`--directory` makes every operand a created directory;
    otherwise the LAST operand is the installed destination file (`install SRC DEST`).
    install overwrites its destination, so it can replace the lease with a permissive
    policy — screen it like the other file-writers."""
    operands, target_dir, make_dirs, i, n = [], None, False, 1, len(tokens)
    while i < n:
        t = tokens[i]
        if t == "--":
            operands.extend(tokens[i + 1:])
            break
        if t in ("-t", "--target-directory"):
            if i + 1 < n:
                target_dir = tokens[i + 1]
            i += 2
            continue
        if t.startswith("--target-directory="):
            target_dir = t.split("=", 1)[1]
            i += 1
            continue
        if t in ("-d", "--directory"):
            make_dirs = True
            i += 1
            continue
        if t in _INSTALL_OPTS_WITH_ARG:
            i += 2
            continue
        if t.startswith("-") and t != "-":
            i += 1
            continue
        operands.append(t)
        i += 1
    if target_dir is not None:
        return [target_dir]
    if make_dirs:
        return operands  # `install -d DIR...`: every operand is a created directory
    return [operands[-1]] if len(operands) >= 2 else []


def _ln_targets(tokens: list) -> list:
    """Link name a `ln` creates (the write side). `-t DIR`/`--target-directory` puts
    links in DIR; `ln TARGET LINK_NAME` names the link explicitly (last operand);
    `ln TARGET` defaults the link to TARGET's basename in the current directory.
    Screened so `ln -sf SRC .claude/ce-write-scope.json` can't re-point the lease."""
    operands, target_dir, i, n = [], None, 1, len(tokens)
    while i < n:
        t = tokens[i]
        if t == "--":
            operands.extend(tokens[i + 1:])
            break
        if t in ("-t", "--target-directory"):
            if i + 1 < n:
                target_dir = tokens[i + 1]
            i += 2
            continue
        if t.startswith("--target-directory="):
            target_dir = t.split("=", 1)[1]
            i += 1
            continue
        if t in ("-S", "--suffix"):
            i += 2
            continue
        if t.startswith("--suffix="):
            i += 1
            continue
        if t.startswith("-") and t != "-":
            i += 1
            continue
        operands.append(t)
        i += 1
    if target_dir is not None:
        return [target_dir]
    if len(operands) >= 2:
        return [operands[-1]]
    if len(operands) == 1:
        # `ln TARGET` links to basename(TARGET) in the current directory.
        return [os.path.basename(operands[0])]
    return []


def _mv_sources(tokens: list) -> list:
    """Source operand(s) a `mv` DELETES. Mirrors _cp_mv_targets' operand parsing but
    returns the complementary (non-destination) operands. `mv` removes its source, so
    `mv <lease> /tmp/parked.json` retires the lease — these are screened against the
    lease-file hard-deny ONLY (an ordinary mv-source deletion stays a documented
    residual; only the lease-file equality is newly enforced)."""
    operands, target_dir, i, n = [], None, 1, len(tokens)
    while i < n:
        t = tokens[i]
        if t == "--":
            operands.extend(tokens[i + 1:])
            break
        if t in ("-t", "--target-directory"):
            if i + 1 < n:
                target_dir = tokens[i + 1]
            i += 2
            continue
        if t.startswith("--target-directory="):
            target_dir = t.split("=", 1)[1]
            i += 1
            continue
        if t in ("-S", "--suffix"):
            i += 2
            continue
        if t.startswith("--suffix="):
            i += 1
            continue
        if t.startswith("-") and t != "-":
            i += 1
            continue
        operands.append(t)
        i += 1
    if target_dir is not None:
        return operands  # `-t DIR`: every operand is a source
    return operands[:-1] if len(operands) >= 2 else []


# xargs options that consume the FOLLOWING token when given as a separate arg; GNU
# short forms may also attach their value (`-n1`, `-I{}`), handled in the scan.
_XARGS_OPTS_WITH_ARG = frozenset({
    "-I", "-i", "-n", "-L", "-P", "-s", "-E", "-d", "-a",
    "--replace", "--max-args", "--max-procs", "--max-lines", "--max-chars",
    "--eof", "--delimiter", "--arg-file", "--process-slot-var",
})


def _xargs_tail_tokens(tokens: list) -> list:
    """The tail command tokens after `xargs` and its own options — `xargs rm src/x.py`
    -> `['rm', 'src/x.py']`. Best-effort: skips xargs option words (and the values of
    those that take one) to the first non-option token. A stdin-fed operand
    (`echo f | xargs rm`) leaves the writer with no readable literal target — that
    residual is documented, not a claimed catch."""
    i, n = 1, len(tokens)
    while i < n:
        t = tokens[i]
        if t == "--":
            i += 1
            break
        if t.startswith("--"):
            name = t.split("=", 1)[0]
            i += 2 if (name in _XARGS_OPTS_WITH_ARG and "=" not in t) else 1
            continue
        if t.startswith("-") and t != "-":
            # a value-taking short opt with a SEPARATE value skips it; an
            # attached-value form (`-n1`, `-I{}`) or a bare flag consumes no token.
            i += 2 if t in _XARGS_OPTS_WITH_ARG else 1
            continue
        break
    return tokens[i:]


def _program_write_targets(prog: str, tokens: list) -> tuple:
    """(write_targets, source_targets) for one command's known write vectors.
    write_targets are screened in full; source_targets (a `mv`'s deleted source) are
    screened against the lease-file hard-deny only. Unknown programs yield ([], [])."""
    if prog == "tee":
        return _tee_targets(tokens), []
    if prog == "sed":
        return _sed_targets(tokens), []
    if prog in ("cp", "mv"):
        return _cp_mv_targets(tokens), (_mv_sources(tokens) if prog == "mv" else [])
    if prog == "rm":
        return _rm_targets(tokens), []
    if prog == "dd":
        return _dd_targets(tokens), []
    if prog == "install":
        return _install_targets(tokens), []
    if prog == "ln":
        return _ln_targets(tokens), []
    return [], []


def _unresolvable(tok: str) -> bool:
    """A target carrying a shell variable or command substitution can't be resolved
    to a literal path here — screening its raw text would false-deny (`> $LOG`) or
    give false confidence. Treat it as the documented indirection residual instead."""
    return "$" in tok or "`" in tok


# A single write/delete a Bash command names.
#   raw          — the target string, as tokenized (quotes stripped).
#   base         — the directory a RELATIVE `raw` resolves against: the segment's
#                  effective cwd (cd/pushd-aware). None means the cwd is unknowable
#                  AND `raw` is relative, so the target is unresolvable and fail-safe
#                  denies (never an out-of-workspace pass).
#   source_only  — True for a `mv` source operand: only the lease-file hard-deny
#                  (rule 2) applies (an ordinary mv-source deletion stays a residual).
_WriteIntent = namedtuple("_WriteIntent", ("raw", "base", "source_only"))


def _is_abs_target(raw: str) -> bool:
    """True when `raw` resolves cwd-independently (absolute, or `~`-expandable)."""
    try:
        return Path(raw).expanduser().is_absolute()
    except Exception:
        return False


def _cd_operand(prog: str, tokens: list) -> tuple:
    """(is_cd, operand) for a `cd`/`pushd` segment: (True, dir) with one literal
    directory operand, (True, None) when the destination is unknowable (bare `cd`
    -> $HOME, `cd -` -> previous dir, a $/backtick operand, or multiple operands),
    else (False, None)."""
    if prog not in ("cd", "pushd"):
        return (False, None)
    operands = []
    for t in tokens[1:]:
        if t == "--":
            continue
        if t.startswith("-") and t != "-":
            continue  # cd -P / -L flags
        operands.append(t)
    if len(operands) != 1:
        return (True, None)
    op = operands[0]
    if op == "-" or _unresolvable(op):
        return (True, None)
    return (True, op)


def _resolve_target(base: Path, raw: str) -> Path | None:
    try:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = base / p
        return p.resolve()
    except Exception:
        return None


def bash_write_intents(cmd: str, root: Path) -> list:
    """Best-effort (raw, base-dir, source?) write intents a Bash command names, per
    known vector: `>`/`>>` redirects, `tee`, `sed -i`, `cp`/`mv` (+ a `mv` source),
    `rm`, `dd of=`, `install`, `ln`, and a literal-operand `xargs <writer>` tail.

    The screen is CWD-AWARE: it walks the command's segments left-to-right, tracks the
    effective cwd across literal `cd`/`pushd`, and pins each RELATIVE target to that
    cwd — so `cd sub && rm ../<denied>` is caught, not mis-resolved to an
    out-of-workspace pass. Interpreter one-liners, `$VAR`/backtick indirection, a
    stdin-fed `xargs`, and an untracked `cd $VAR` are documented residuals."""
    intents: list = []
    if _GIT_GUARD is None:
        # Degraded (no tokenizer sibling): redirect-only screening against root, no
        # segment/cwd model. Rule 2 still applies to the redirect targets.
        for m in _REDIRECT_TARGET.finditer(cmd):
            raw = _strip_quotes(m.group(1))
            if raw and not _unresolvable(raw):
                intents.append(_WriteIntent(raw, root, False))
        return intents

    eff_cwd, cwd_known = root, True
    for segment in _GIT_GUARD._SEGMENT_SPLIT.split(cmd):
        seg_targets: list = []  # (raw, source_only) for THIS segment
        for m in _REDIRECT_TARGET.finditer(segment):
            raw = _strip_quotes(m.group(1))
            if raw and not _unresolvable(raw):
                seg_targets.append((raw, False))
        tokens = _GIT_GUARD._unwrap(
            _strip_redirect_tokens(_GIT_GUARD._tokenize(segment)))
        prog = _GIT_GUARD._program(tokens) if tokens else ""
        if prog:
            writes, sources = _program_write_targets(prog, tokens)
            if prog == "xargs":  # dispatch the literal-operand tail writer
                tail = _xargs_tail_tokens(tokens)
                if tail:
                    w, s = _program_write_targets(_GIT_GUARD._program(tail), tail)
                    writes += w
                    sources += s
            for t in writes:
                if t and not _unresolvable(t):
                    seg_targets.append((t, False))
            for t in sources:
                if t and not _unresolvable(t):
                    seg_targets.append((t, True))
        # Pin this segment's targets to the CURRENT effective cwd, before a trailing
        # cd/pushd retargets the cwd for the NEXT segment.
        for raw, source_only in seg_targets:
            base = eff_cwd if (cwd_known or _is_abs_target(raw)) else None
            intents.append(_WriteIntent(raw, base, source_only))
        is_cd, op = _cd_operand(prog, tokens)
        if is_cd:
            if op is None:
                cwd_known = False  # bare cd / cd - / $-operand → cwd unknowable
            elif _is_abs_target(op):
                resolved_cd = _resolve_target(eff_cwd, op)  # absolute → base ignored
                if resolved_cd is not None:
                    eff_cwd, cwd_known = resolved_cd, True  # re-establishes a known cwd
                else:
                    cwd_known = False
            elif cwd_known:
                resolved_cd = _resolve_target(eff_cwd, op)
                if resolved_cd is not None:
                    eff_cwd = resolved_cd
                else:
                    cwd_known = False
            # a relative cd while the cwd is already unknown stays unknown
    return intents


def screen_bash(tool_input: dict, root: Path, policy: dict,
                session_id: str, hook_event: str) -> int:
    """Screen a Bash command's write vectors against the same write-scope policy
    the Write/Edit path uses. Two Bash-only posture rules: (1) out-of-workspace
    targets — `/tmp` scratch and the like — are not a workspace lease's concern, so
    the Bash branch stays permissive there (unlike the Write/Edit path); (2) any
    mutation, deletion, or move of the lease file itself is HARD-DENIED through the
    recognized shell write vectors whenever a policy is enabled, regardless of the
    allow/deny lists — retiring the lease was the pattern's zero-friction bypass. The
    screen is cwd-aware (see bash_write_intents): a relative target after an untracked
    `cd`/`pushd` (whose destination this guard can't follow) is denied fail-safe
    rather than passed as out-of-workspace."""
    cmd = tool_input.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return 0  # no readable command — the Write/Edit path stays the enforcement surface
    lease_file = policy_path(root)
    for intent in bash_write_intents(cmd, root):
        if intent.base is None:
            # cwd unknowable after an untracked cd AND a relative target → can't
            # resolve it. A write is denied fail-safe; an unresolved mv-SOURCE is a
            # documented residual (only the lease-file hard-deny would apply, and we
            # can't prove equality without the cwd), so it is skipped.
            if intent.source_only:
                continue
            reason = (f"Bash write target `{intent.raw}` is relative to an untracked "
                      f"`cd`/`pushd` destination and cannot be resolved — denying "
                      f"fail-safe")
            log_decision(root, "deny", "Bash", intent.raw, reason, tool_input,
                         session_id, hook_event)
            hook_decide("deny", deny_message(reason, policy))
        resolved = _resolve_target(intent.base, intent.raw)
        if resolved is None:
            continue
        if resolved == lease_file:  # rule 2: the lease file is never Bash-writable
            reason = ("Bash command would mutate, delete, or move the write-scope "
                      f"lease file `{DEFAULT_POLICY}`")
            log_decision(root, "deny", "Bash", intent.raw, reason, tool_input,
                         session_id, hook_event)
            hook_decide("deny", deny_message(reason, policy))
        if intent.source_only:  # mv source: only the lease-file hard-deny applies
            continue
        if not inside(resolved, root):  # rule 1: out-of-workspace Bash writes pass
            continue
        ok, reason = target_allowed(root, policy, resolved)
        if ok:
            continue
        log_decision(root, "deny", "Bash", intent.raw, reason, tool_input,
                     session_id, hook_event)
        hook_decide("deny", deny_message(reason, policy))
    return 0


# --- Session-bound lease: bind on first use, self-heal a dead session's lease --
#
# A lease-mode policy carries a `lease_id` + `created_at` (write-lease.py). This
# guard binds the lease to the host-owned session_id on first use, and degrades a
# lease orphaned by a dead session to the deny-only baseline — rather than
# hard-denying every write in the next session until a human hand-deletes the
# lease file. Ambiguity (no session_id, a legacy lease with no id, an unreadable
# sidecar) fail-safes to the ordinary deny path.

def session_sidecar_path(root: Path) -> Path:
    return (root / SESSION_SIDECAR).resolve()


def lease_ttl_seconds() -> int:
    """Lease TTL backstop in seconds; env-overridable via LEASE_TTL_ENV. A
    non-positive or unparseable value disables the TTL signal, leaving a
    session-id mismatch as the sole staleness signal."""
    raw = os.environ.get(LEASE_TTL_ENV)
    if raw is None:
        return DEFAULT_LEASE_TTL_SECONDS
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEFAULT_LEASE_TTL_SECONDS


def _parse_iso(stamp) -> datetime | None:
    if not isinstance(stamp, str) or not stamp.strip():
        return None
    try:
        parsed = datetime.fromisoformat(stamp.strip())
    except (ValueError, TypeError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def lease_age_phrase(created_at) -> str:
    """Human phrase for how long ago a stale lease was created, from its ISO
    `created_at`. 'age unknown' on a missing or unparseable stamp."""
    stamped = _parse_iso(created_at)
    if stamped is None:
        return "age unknown"
    secs = int((datetime.now(timezone.utc) - stamped).total_seconds())
    if secs < 0:
        return "set moments ago"
    if secs < 90:
        return f"set {secs}s ago"
    if secs < 90 * 60:
        return f"set {secs // 60}m ago"
    if secs < 48 * 3600:
        return f"set {secs // 3600}h ago"
    return f"set {secs // 86400}d ago"


def _older_than_ttl(created_at, ttl: int) -> bool:
    if ttl <= 0:
        return False
    stamped = _parse_iso(created_at)
    if stamped is None:
        return False
    return (datetime.now(timezone.utc) - stamped).total_seconds() > ttl


def load_sidecar(path: Path) -> tuple[str, dict | None]:
    """('absent' | 'ok' | 'unreadable', data). 'unreadable' (present but corrupt
    or non-object) is ambiguous to the caller and fail-safes to the deny path."""
    if not path.is_file():
        return "absent", None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "unreadable", None
    return ("ok", data) if isinstance(data, dict) else ("unreadable", None)


def write_sidecar(path: Path, lease_id: str, session_id: str) -> None:
    """Best-effort bind lease->session. Never raises: a failed bind must not
    change a permission decision — the guard falls through to normal enforcement
    and simply retries the bind on the next event."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "lease_id": lease_id,
            "session_id": session_id,
            "bound_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def restore_baseline_lease(path: Path) -> None:
    """Rewrite the lease file to the deny-only baseline (direct I/O — the guard's
    own write, not a screened tool call). Best-effort: on failure the caller still
    returns `ask`, and the next event re-evaluates the unchanged lease."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(BASELINE_POLICY, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def _degrade_stale_lease(root: Path, policy: dict, session_id: str, tool: str,
                         tool_input: dict, hook_event: str, sidecar: Path) -> None:
    """Warn-and-replace a dead session's lease: rewrite it to the baseline, drop
    the orphaned binding, log the replacement, and emit a single `ask` naming the
    stale holder and its age. `hook_decide` raises SystemExit, ending the hook."""
    holder = policy.get("skill")
    holder = (f"/{holder.strip()}" if isinstance(holder, str) and holder.strip()
              else "an earlier session's read-only skill")
    age = lease_age_phrase(policy.get("created_at"))
    reason = (
        f"core-engineering write-scope-guard: the write lease held by {holder} "
        f"belongs to a dead session ({age}) — auto-replacing it with the "
        f"deny-only baseline so writes flow again. This one write is paused for "
        f"your OK; after it there is no hidden lease file to hand-delete."
    )
    restore_baseline_lease(policy_path(root))
    try:
        sidecar.unlink()  # drop the now-orphaned binding; best-effort
    except OSError:
        pass
    log_decision(root, "ask", tool or "", "", reason, tool_input,
                 session_id, hook_event)
    hook_decide("ask", reason)


def bind_or_degrade_lease(root: Path, policy: dict, session_id: str, tool: str,
                          tool_input: dict, hook_event: str) -> None:
    """For a lease-mode policy: bind the lease to this session on first use, and
    degrade a dead session's lease to the deny-only baseline (warn-and-replace) on
    a session-id mismatch or a TTL-expired orphan. Returns None — the caller then
    runs the ordinary target enforcement — for live/first-use/ambiguous cases; on
    a stale lease it does not return (a single `ask` ends the hook)."""
    if policy.get("mode", "lease") != "lease":
        return  # deny-only baseline: no session binding
    lease_id = policy.get("lease_id")
    if not isinstance(lease_id, str) or not lease_id.strip():
        return  # legacy lease without an id — fail-safe to the deny path
    if not session_id:
        return  # host provided no session id — ambiguous, fail-safe to deny path
    lease_id = lease_id.strip()
    sidecar = session_sidecar_path(root)
    status, data = load_sidecar(sidecar)
    if status == "unreadable":
        return  # ambiguous — fail-safe to the deny path

    if status == "ok" and data.get("lease_id") == lease_id:
        # The sidecar binds THIS lease.
        if data.get("session_id") == session_id:
            return  # the active owner — enforce as normal (never degrade a live owner)
        # A different session holds the binding for this exact lease → dead session.
        _degrade_stale_lease(root, policy, session_id, tool, tool_input,
                             hook_event, sidecar)
        return

    # No binding for THIS lease yet (fresh sidecar, or it names an older lease).
    if _older_than_ttl(policy.get("created_at"), lease_ttl_seconds()):
        # An old orphan a fresh session just met — no live owner is recorded.
        _degrade_stale_lease(root, policy, session_id, tool, tool_input,
                             hook_event, sidecar)
        return
    write_sidecar(sidecar, lease_id, session_id)  # first use: bind to this session


def hook_main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        print(
            "write-scope-guard: unparseable hook input - write scope was not applied.",
            file=sys.stderr,
        )
        return 1
    if not isinstance(data, dict):
        print("write-scope-guard: hook input was not an object.", file=sys.stderr)
        return 1

    tool = data.get("tool_name")
    if tool not in WRITE_TOOLS and tool != "Bash":
        return 0
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    root = workspace_root(cwd)
    policy = load_policy(policy_path(root))
    if not policy or not policy.get("enabled", False):
        return 0

    tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    session_id = data.get("session_id") or ""
    hook_event = data.get("hook_event_name") or "PreToolUse"

    # Session-bound lease: bind on first use; degrade a dead session's orphaned
    # lease to the baseline (one `ask`) instead of hard-denying every write until
    # a human hand-deletes the file. A stale lease ends the hook here (`ask`).
    bind_or_degrade_lease(root, policy, session_id, tool, tool_input, hook_event)

    if tool == "Bash":
        return screen_bash(tool_input, root, policy, session_id, hook_event)

    target_raw = extract_target(tool_input)
    if not target_raw:
        log_decision(root, "deny", tool, "", "no target file path", tool_input,
                     session_id, hook_event)
        hook_decide(
            "deny",
            deny_message(f"{tool} call has no target file path", policy),
        )
    ok, reason = target_allowed(root, policy, Path(target_raw))
    if ok:
        return 0
    log_decision(root, "deny", tool, target_raw, reason, tool_input,
                 session_id, hook_event)
    hook_decide("deny", deny_message(reason, policy))
    return 0


def cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a path against a write-scope policy")
    parser.add_argument("--root", default=".", help="workspace root")
    parser.add_argument("--policy", help="policy path; default .claude/ce-write-scope.json")
    parser.add_argument("--check", help="path to check")
    args = parser.parse_args(argv)

    if not args.check:
        return hook_main()

    root = Path(args.root).expanduser().resolve()
    path = Path(args.policy).expanduser().resolve() if args.policy else policy_path(root)
    policy = load_policy(path)
    if not policy or not policy.get("enabled", False):
        print("allow: no enabled policy")
        return 0
    ok, reason = target_allowed(root, policy, Path(args.check))
    print(("allow: " if ok else "deny: ") + reason)
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(cli_main())
    except SystemExit:
        raise
    except Exception as exc:  # fail-safe for hook mode
        hook_decide(
            "deny",
            f"core-engineering write-scope-guard: internal error "
            f"({exc.__class__.__name__}) - denying fail-safe.",
        )
