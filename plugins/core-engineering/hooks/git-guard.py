#!/usr/bin/env python3
"""git-guard.py — PreToolUse backstop for core-engineering's version-control rules.

The toolset's prose says, everywhere: the human owns what enters shared history —
the agent never pushes, opens/merges PRs, tags, or writes commits to the
protected branch (commit/merge/revert/cherry-pick/am) on its own. This hook makes
that a *structural* checkpoint instead of prose that a compacted or autonomous
context can talk itself out of.

It is a BACKSTOP, not the source of truth: the prose disciplines stay verbatim,
and this hook only adds a confirmation/block on the few clearly-shared-history
git operations. By default every guarded op is `ask` (a confirmation prompt) —
safe to leave always-on, because it never hard-blocks a push the human explicitly
wants; it just forces a conscious, in-the-loop approval.

Decision tiers are env-configurable per operation (no file edit needed):
  CE_GIT_GUARD_PUSH=deny      # hard-block `git push`
  CE_GIT_GUARD_PR=deny        # hard-block `gh pr create|merge` and `gh api`
                              # calls that write to /pulls or /merge endpoints
  CE_GIT_GUARD_TAG=deny       # hard-block `git tag <name>` (create/move/delete;
                              # listing stays silent)
  CE_GIT_GUARD_COMMIT=deny    # hard-block history writes on the protected
                              # branch (commit/merge/revert/cherry-pick/am)
Values: "ask" (default) or "deny"; anything else falls back to "ask".

Error posture (deliberate, tested):
* payload parses, tool is Bash, but the command cannot be extracted →
  **deny** (recognized-but-malformed: after a host schema change the command
  could hide in a shape this guard cannot see — failing open here would
  silently retire the backstop);
* stdin is not JSON, or the payload has no tool_name at all → **ask** (an
  unrecognized shape gets a human, not a hard block and not a silent pass);
* tool_name present but not Bash → allow (correctly recognized non-target).

Kill switch (documented, local): CE_GIT_GUARD=off disables the guard entirely
for this environment — the escape hatch if a host payload change ever strands
a session. Decisions are appended best-effort to .claude/ce-guard-log.jsonl
through the shared guard_log.py writer, which sha256-chains each line to the
prior one so the ledger is tamper-evident (guard_log.py --verify <file>).
"""
import json
import os
import re
import shlex
import subprocess
import sys


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


_GUARD_LOG = _load_guard_log()

# Actor context captured once in main() from the hook payload, so decide() — called
# from ~a dozen sites without the payload in scope — can log session/tool/payload.
_LOG_CTX = {"session_id": "", "tool": "", "tool_input": None, "hook_event": "PreToolUse"}

# Splitting the command on shell operators, then TOKENIZING each segment and
# reading its subcommand — instead of substring-matching `git push` across the
# whole string — fixes two failure modes of the old `\bgit\s+push\b` regex:
#   * FAIL-OPEN: `git -C dir push`, `git -c k=v push`, `git --no-pager push`,
#     `gh --repo o/r pr create` — a global option sits between `git` and the
#     subcommand, so the prefix regex never matched and the push sailed through.
#   * FALSE-POSITIVE: `git commit -m "how to git push"` or `echo "git push"` —
#     the substring `git push` appears inside a quoted argument, so the regex
#     fired a spurious confirmation on a command that pushes nothing.
# Split on shell operators AND on command-substitution / subshell / brace-group
# openers, so a push nested in `x=$(git push)`, `` `git push` ``, or `(git push)`
# becomes its own segment and is still read at command position.
_SEGMENT_SPLIT = re.compile(r"&&|\|\||\$\(|[;\n|&()`{}]")
# git global options that consume the FOLLOWING token as their value; the
# subcommand is whatever non-option token appears after them.
_GIT_OPTS_WITH_ARG = frozenset({
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--super-prefix", "--config-env",
})
# gh options that consume the following token (so we skip past their value when
# scanning for the `pr create` / `pr merge` command path).
_GH_OPTS_WITH_ARG = frozenset({"-R", "--repo", "--hostname"})
# Command wrappers that take ANOTHER command as their tail (`sudo git push`,
# `nohup git push`, `env FOO=bar git push`). A leading bare wrapper is stripped
# so the real program underneath is read. Honest limit: a wrapper carrying its
# own value-taking option (e.g. `sudo -u deploy git push`) is not unwrapped —
# documented alongside the alias/indirection caveats in hooks/README.md.
# `xargs` is deliberately NOT here: its real subcommand arrives on stdin
# (`echo push | xargs git`), so unwrapping it would read a bare `git` and fail
# open — it gets its own opaque-tail rule in guarded_ops() instead.
_CMD_WRAPPERS = frozenset({
    "sudo", "doas", "env", "nohup", "nice", "time", "command", "exec",
    "stdbuf", "setsid", "ionice", "chrt",
})
# Wrappers that take a leading positional value before the command (`timeout
# 30 git push`), plus the options that consume the following token.
_ARG_WRAPPERS = frozenset({"timeout"})
_ARG_WRAPPER_OPTS_WITH_VALUE = frozenset({"-s", "--signal", "-k", "--kill-after"})
# Shell keywords that sit at command position inside a compound command, after
# segment-splitting (`if x; then git push; fi` -> a `then git push` segment).
_SHELL_KEYWORDS = frozenset({"then", "do", "else", "elif", "!", "time"})
# Interpreters whose `-c <string>` / `-lc <string>` argument is another command
# line — re-scanned recursively (`bash -c 'git push'`).
_SHELL_INTERPRETERS = frozenset({"bash", "sh", "dash", "zsh", "ksh"})


def _tokenize(segment):
    """Best-effort argv for one command segment. shlex is POSIX-accurate;
    unbalanced quotes (rare, and never in a real push) fall back to a plain
    split so the scan still sees the program and subcommand tokens."""
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _strip_env_assignments(tokens):
    """Drop leading `NAME=value` env-var assignments so `FOO=bar git push` still
    resolves to a git invocation."""
    i = 0
    while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]):
        i += 1
    return tokens[i:]


def _unwrap(tokens):
    """Strip leading env assignments, shell keywords, and command-wrapper tokens
    so the real program is read: `sudo git push`, `then git push`, `timeout 30
    git push` all resolve to `git push`. Stops at the first ordinary wrapper
    carrying a dashed option (its value parsing is ambiguous) — that residual
    case is documented, not silently mis-handled."""
    tokens = _strip_env_assignments(tokens)
    progressing = True
    while progressing and tokens:
        progressing = False
        head = os.path.basename(tokens[0]).lower()
        if head in _SHELL_KEYWORDS:
            tokens = _strip_env_assignments(tokens[1:])
            progressing = True
        elif (head in _CMD_WRAPPERS and len(tokens) > 1
              and not tokens[1].startswith("-")):
            tokens = _strip_env_assignments(tokens[1:])
            progressing = True
        elif head in _ARG_WRAPPERS and len(tokens) > 1:
            i = 1
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 2 if tokens[i] in _ARG_WRAPPER_OPTS_WITH_VALUE else 1
            if i < len(tokens):
                i += 1  # the positional value (e.g. timeout's duration)
            tokens = _strip_env_assignments(tokens[i:])
            progressing = True
    return tokens


def _dash_c_argument(tokens):
    """The command string an interpreter's -c/-lc/-ic option carries, if any."""
    for i in range(1, len(tokens) - 1):
        t = tokens[i]
        if t.startswith("-") and "c" in t.lstrip("-"):
            return tokens[i + 1]
    return None


def _program(tokens):
    return os.path.basename(tokens[0]).lower() if tokens else ""


def _git_subcommand_index(tokens):
    """Index of the first non-option token after `git`, skipping global options
    (and the values of those that take one). None if the segment is bare `git`."""
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t in _GIT_OPTS_WITH_ARG:
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        return i
    return None


def _git_subcommand(tokens):
    """First non-option token after `git` (the subcommand), or None."""
    i = _git_subcommand_index(tokens)
    return tokens[i] if i is not None else None


# `git tag` options that consume the FOLLOWING token — their value is not a
# tag name, so it must not count as the positional that marks a mutation.
_GIT_TAG_OPTS_WITH_ARG = frozenset({
    "-m", "-F", "-u", "--contains", "--no-contains", "--merged",
    "--no-merged", "--points-at", "--sort", "--format", "--color",
})


def _git_tag_mutates(tokens):
    """True when a `git tag` invocation names a tag (create / move / delete —
    any positional argument), False for pure listing: bare `git tag`,
    `git tag -l`, `git tag --list 'v*'`."""
    i = _git_subcommand_index(tokens)  # the `tag` token itself
    if i is None:
        return False
    i += 1
    positional = False
    while i < len(tokens):
        t = tokens[i]
        if t in ("-l", "--list"):
            return False
        if t in _GIT_TAG_OPTS_WITH_ARG:
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        positional = True
        i += 1
    return positional


def _gh_command_path(tokens, limit=2):
    """The leading non-option command tokens after `gh` (e.g. ['pr','create']),
    skipping global options and their values."""
    out = []
    i = 1
    while i < len(tokens) and len(out) < limit:
        t = tokens[i]
        if t in _GH_OPTS_WITH_ARG:
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        out.append(t)
        i += 1
    return out


# gh api flags that consume the FOLLOWING token — skipped so a flag value
# (`-f title="merge fix"`) never masquerades as the endpoint path.
_GH_API_OPTS_WITH_ARG = frozenset({
    "-X", "--method", "-f", "--raw-field", "-F", "--field", "-H", "--header",
    "-q", "--jq", "-t", "--template", "--input", "--cache", "--hostname",
    "-p", "--preview",
})
# Body flags that flip `gh api`'s default method from GET to POST even
# without an explicit -X/--method.
_GH_API_BODY_FLAGS = frozenset({"-f", "--raw-field", "-F", "--field", "--input"})
_GH_API_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _gh_api_pr_mutation(tokens):
    """True when a `gh api` invocation writes to a PR endpoint: a positional
    path containing `/pulls` or `/merge` AND write semantics — an explicit
    mutating -X/--method, or a body flag that flips gh's default GET to POST.
    A plain GET of the same endpoint (listing PRs) stays silent."""
    method = None
    has_body = False
    pr_path = False
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t in ("-X", "--method"):
            if i + 1 < len(tokens):
                method = tokens[i + 1].upper()
            i += 2
            continue
        if t.startswith("--method="):
            method = t.split("=", 1)[1].upper()
            i += 1
            continue
        if t in _GH_API_BODY_FLAGS:
            has_body = True
            i += 2
            continue
        if t in _GH_API_OPTS_WITH_ARG or t in _GH_OPTS_WITH_ARG:
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        # positional: the leading `api` token, then the endpoint path
        if t != "api" and ("/pulls" in t or "/merge" in t):
            pr_path = True
        i += 1
    return pr_path and (method in _GH_API_MUTATING_METHODS
                        or (method is None and has_body))


# git subcommands that write commits — on the protected branch they are the
# same violation as `git commit`, so they share the CE_GIT_GUARD_COMMIT tier.
_GIT_COMMIT_WRITERS = frozenset({"commit", "merge", "revert", "cherry-pick", "am"})


def guarded_ops(cmd, _depth=0):
    """The guarded shared-history operations present in a Bash command:
    a subset of {'push', 'pr', 'tag', 'commit', 'opaque'}, order-independent
    ('opaque' = an xargs tail feeding git/gh a piped subcommand)."""
    ops = set()
    if _depth > 4:  # bounded recursion into nested `bash -c '...'` strings
        return ops
    # `{}` is the xargs/find placeholder; the segment splitter would otherwise
    # split on its braces and hide `xargs -I{} git {}` from the opaque-tail
    # rule. A literal EMPTY brace pair opens no brace group, so neutralizing
    # it before splitting can only merge what was over-split, never hide one.
    cmd = cmd.replace("{}", " __ce_brace_pair__ ")
    for segment in _SEGMENT_SPLIT.split(cmd):
        tokens = _unwrap(_tokenize(segment))
        if not tokens:
            continue
        prog = _program(tokens)
        if prog == "xargs":
            # xargs's real subcommand arrives on stdin; if git/gh sits in its
            # tail the invocation is unreadable here — flag, don't guess.
            if any(os.path.basename(t).lower() in ("git", "gh")
                   for t in tokens[1:]):
                ops.add("opaque")
            continue
        if prog in _SHELL_INTERPRETERS:
            nested = _dash_c_argument(tokens)
            if nested:
                ops |= guarded_ops(nested, _depth + 1)
            continue
        if prog == "git":
            sub = _git_subcommand(tokens)
            if sub == "push":
                ops.add("push")
            elif sub == "tag" and _git_tag_mutates(tokens):
                ops.add("tag")
            elif sub in _GIT_COMMIT_WRITERS:
                ops.add("commit")
        elif prog == "gh":
            path = _gh_command_path(tokens)
            if path in (["pr", "create"], ["pr", "merge"]):
                ops.add("pr")
            elif path[:1] == ["api"] and _gh_api_pr_mutation(tokens):
                ops.add("pr")
    return ops
KILL_SWITCH_HINT = (
    "Scoped opt-out: confirm the prompt, or set CE_GIT_GUARD=off to disable "
    "this backstop for the environment (say why)."
)


def tier(env_name, default="ask"):
    value = os.environ.get(env_name, default).strip().lower()
    return value if value in ("ask", "deny") else default


def log_decision(decision, reason, cwd=None):
    """Best-effort, hash-chained local record of guard decisions (via the shared
    guard_log.py writer). Never raises — a logging failure must not change a
    permission decision."""
    if _GUARD_LOG is None:
        return
    try:
        root = os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd()
        _GUARD_LOG.append_entry(
            root, "git-guard", decision, reason, _LOG_CTX.get("tool_input"),
            session_id=_LOG_CTX.get("session_id", ""),
            tool=_LOG_CTX.get("tool", ""),
            hook_event=_LOG_CTX.get("hook_event", "PreToolUse"),
        )
    except Exception:
        pass


def decide(decision, reason, cwd=None):
    log_decision(decision, reason, cwd)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def git(args):
    try:
        r = subprocess.run(["git"] + args, capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return ""


def protected_branch():
    ref = git(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"])
    if ref:
        return ref.rsplit("/", 1)[-1]
    cfg = git(["config", "--get", "init.defaultBranch"])
    if cfg:
        return cfg
    for b in ("main", "master"):
        if git(["rev-parse", "--verify", "--quiet", b]):
            return b
    return ""


def main():
    if os.environ.get("CE_GIT_GUARD", "").strip().lower() == "off":
        return  # kill switch: allow everything, guard disabled for this env
    try:
        data = json.load(sys.stdin)
    except Exception:
        decide("ask", "core-engineering git-guard: hook input was not parseable JSON "
                      "(unrecognized payload shape) — confirming instead of guessing. "
                      + KILL_SWITCH_HINT)
    if not isinstance(data, dict) or "tool_name" not in data:
        decide("ask", "core-engineering git-guard: hook payload has no tool_name "
                      "(unrecognized payload shape) — confirming instead of guessing. "
                      + KILL_SWITCH_HINT)
    _LOG_CTX["session_id"] = data.get("session_id") or ""
    _LOG_CTX["tool"] = data.get("tool_name") or ""
    _LOG_CTX["tool_input"] = data.get("tool_input")
    _LOG_CTX["hook_event"] = data.get("hook_event_name") or "PreToolUse"
    if data.get("tool_name") != "Bash":
        return  # correctly recognized non-target event
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    tool_input = data.get("tool_input")
    cmd = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(cmd, str) or not cmd.strip():
        # Recognized Bash event, but the command is not where this guard can
        # see it. Fail closed: a schema drift must not silently retire the
        # backstop on exactly the operations it exists to catch.
        decide("deny", "core-engineering git-guard: Bash payload carries no readable "
                       "command (recognized event, malformed content) — denying "
                       "fail-safe. " + KILL_SWITCH_HINT, cwd)

    ops = guarded_ops(cmd)
    # push > pr > tag > commit > opaque priority preserves the old short-circuit
    # order (the push confirmation wins if a command both pushes and commits).
    if "push" in ops:
        decide(tier("CE_GIT_GUARD_PUSH"),
               "core-engineering: the human owns what enters shared history — "
               "confirm this `git push` (or push it yourself). " + KILL_SWITCH_HINT, cwd)
    if "pr" in ops:
        decide(tier("CE_GIT_GUARD_PR"),
               "core-engineering: opening or merging a PR is the human's call — "
               "confirm, or do it yourself. " + KILL_SWITCH_HINT, cwd)
    if "tag" in ops:
        decide(tier("CE_GIT_GUARD_TAG"),
               "core-engineering: creating, moving, or deleting a tag is the "
               "human's call (release's go/no-go gate owns tagging) — confirm, "
               "or tag it yourself. " + KILL_SWITCH_HINT, cwd)
    if "commit" in ops:
        prot = protected_branch()
        cur = git(["rev-parse", "--abbrev-ref", "HEAD"])
        if prot and cur and cur == prot:
            decide(tier("CE_GIT_GUARD_COMMIT"),
                   f"core-engineering: writing commits directly to `{prot}` "
                   "(commit / merge / revert / cherry-pick / am) is the human's "
                   "call — work on a feature branch, or confirm. " + KILL_SWITCH_HINT, cwd)
    if "opaque" in ops:
        decide("ask",
               "core-engineering git-guard: `xargs` feeds `git`/`gh` a piped "
               "subcommand this guard cannot read — confirm what it will run. "
               + KILL_SWITCH_HINT, cwd)
    # everything else → allow (silent)


if __name__ == "__main__":
    main()
