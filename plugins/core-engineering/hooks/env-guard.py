#!/usr/bin/env python3
"""env-guard.py — PreToolUse capability hook denying the secret-file read vectors.

git-guard.py's sibling. Where git-guard backstops *who owns shared history*, this
hook backstops *what an agent may read*: it denies the deterministic file-read
vectors behind agent credential exfiltration (the May-2026 Claude Code GitHub
Action bug) —

  1. the process-environment file family — `/proc/<pid>/environ` (any pid, `self`,
     `thread-self`, task threads): no agent workflow legitimately reads it;
  2. a data-driven corpus of credential files (`guarded-secrets.json`, loaded from
     beside this hook — the popular-packages.json precedent). Two entry kinds:
       - `home_path` — a home-anchored credential store (`~/.aws/credentials`,
         `~/.ssh/id_*`, `~/.kube/config`, gcloud ADC, …): denied REGARDLESS of
         cwd, because a credential store is never workspace content;
       - `basename` — a filename glob (`.env`/`.env.*`, `.npmrc`, `.pypirc`,
         `.envrc`, `*.pem`, `*.key`): denied only when it resolves OUTSIDE the
         workspace root, so a project's own `.env`/`.npmrc` stays readable (its
         tooling needs it). The trust boundary is unchanged from the old
         dotenv-only rule; the corpus only widens the set of guarded basenames.

It screens the `Read` and `Grep` tools' path arguments and `Bash` command text.
Paths are realpath-resolved, so a symlink into any guarded class is caught from
both directions (a workspace symlink pointing out, or an innocent-looking name
resolving into a guarded file). Bash yields EVERY relative token — bare names
(`server`) included — so `cat ../../.env` and a bare-named workspace symlink
into a guarded class (`cat server`, `server -> ~/.aws/credentials`) are both
caught, closing the old asymmetry with the Read/Grep branch. A home-anchored
store is denied in BOTH directions: the file itself, AND a directory-targeted
read that would descend into it — `grep -r` / `cp -r` / `tar` on `~/.ssh` or
`~/.aws` (or on `~`/`$HOME`, an ancestor of every store) is denied at the
directory token, not only at the file token. The false-positive surface stays
bounded because only a token whose realpath lands in a guarded class ever
triggers. This is *capability confinement*, not a content gate — it composes
with dep-guard.py (the dep-existence discipline) and shares no code with it.

Corpus resilience: a missing or malformed `guarded-secrets.json` is NEVER fatal —
the hook degrades LOUDLY (stderr warning) to a built-in environ+dotenv floor, so
a bad data edit can never silently retire the guard nor brick a session.
`CE_GUARDED_SECRETS` overrides the corpus path (tests / operator use).

Posture — deliberately stricter than git-guard's documented fail-open, because
here a silent allow IS the vulnerability:
  - guarded-class match, or a guarded basename whose workspace containment
    cannot be determined → DENY (fail-safe);
  - unexpected internal error while screening → DENY (fail-safe);
  - unparseable hook input → loud non-blocking warning (stderr + exit 1), the
    hook analogue of the lint gates' "exit 2: could-not-run → fall back loudly".
    A hard deny here would brick every Read/Grep/Bash on harness drift; a
    silent allow would be the fail-open hole.

Honest limitations — env-var *expansion* like `printenv`/`echo $API_KEY` is not
a file read; nor are interpreter one-liners, shell variable indirection /
obfuscation (`F=$HOME; cat $F/.env`), MCP-tool reads, or execution surfaces
that load no plugin hooks. Directory-read denial is exact for the
home-anchored stores (a structural ancestor test, no enumeration, any depth);
for the `basename` class an out-of-workspace directory is screened by its
*immediate* children only, so a `basename` secret nested deeper under a
recursively-read out-of-workspace directory is a residual gap — the home stores
(the headline exfil target) are covered regardless of depth.
"""
import json
import os
import re
import sys
from fnmatch import fnmatch


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

# Actor context captured in main() from the hook payload, so decide() — reached
# from several screening sites — can hash-chain session/tool/payload into the log.
_LOG_CTX = {"root": "", "session_id": "", "tool": "", "tool_input": None,
            "hook_event": "PreToolUse"}

# Default decision for the guarded FILE classes: "deny" (hard block) or "ask"
# (confirm in-the-loop). These stay the single flip-to-ask lever every deny
# message documents: a corpus entry MAY override with its own "decision", but the
# shipped guarded-secrets.json omits it, so flipping ENV_FILE here flips the whole
# file-read corpus (both kinds) at once. ENVIRON governs the /proc/.../environ
# regex vector, which is not part of the data-driven corpus.
ENVIRON = "deny"
ENV_FILE = "deny"

GUARDED_TOOLS = ("Read", "Grep", "Bash")

ENVIRON_RE = re.compile(r"/proc/(?:self|thread-self|\d+|\*)(?:/task/(?:\d+|\*))?/environ(?![\w-])")

MAX_PATH = 4096  # PATH_MAX; longer "paths" are adversarial padding — don't realpath them

# Built-in floor used when the corpus can't be loaded — the guarantee that a bad
# guarded-secrets.json never silently drops the dotenv coverage. (The environ
# vector is a separate hardcoded regex, always active regardless of the corpus.)
BUILTIN_FLOOR = {
    "home_path": [],
    "basename": [
        {"id": "dotenv", "pattern": ".env", "decision": ENV_FILE},
        {"id": "dotenv-suffixed", "pattern": ".env.*", "decision": ENV_FILE},
    ],
}

ESCAPE = ('If the human wants this read: do it yourself outside the agent, copy the needed '
          'values into the workspace, or flip the decision constants in '
          'plugins/core-engineering/hooks/env-guard.py to "ask".')


def log_decision(decision, reason):
    """Best-effort, hash-chained record of this guard's decision (via the shared
    guard_log.py writer). Never raises — a logging failure must not change a
    permission decision. env-guard had no ledger before this; every deny/ask now
    joins the tamper-evident chain alongside its git-guard/write-scope siblings."""
    if _GUARD_LOG is None:
        return
    try:
        root = (_LOG_CTX.get("root") or os.environ.get("CLAUDE_PROJECT_DIR")
                or os.getcwd())
        _GUARD_LOG.append_entry(
            root, "env-guard", decision, reason, _LOG_CTX.get("tool_input"),
            session_id=_LOG_CTX.get("session_id", ""),
            tool=_LOG_CTX.get("tool", ""),
            hook_event=_LOG_CTX.get("hook_event", "PreToolUse"),
        )
    except Exception:
        pass


def decide(decision, reason):
    log_decision(decision, reason)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def load_corpus():
    """Load the guarded-secrets corpus from beside the hook (CE_GUARDED_SECRETS
    overrides the path). ANY load/shape failure degrades LOUDLY to BUILTIN_FLOOR —
    never fatal, never a silent loss of the floor: a bad data edit cannot retire
    the guard, and a JSON typo cannot brick every Read/Grep/Bash."""
    path = os.environ.get("CE_GUARDED_SECRETS") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "guarded-secrets.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        entries = data["entries"]
        if not isinstance(entries, list):
            raise ValueError("`entries` is not a list")
        out = {"home_path": [], "basename": []}
        for entry in entries:
            kind = entry["kind"]
            if kind not in out:
                raise ValueError(f"unknown kind {kind!r}")
            pattern = entry["pattern"]
            if not isinstance(pattern, str) or not pattern:
                raise ValueError("empty or non-string pattern")
            decision = entry.get("decision", ENV_FILE)
            if decision not in ("deny", "ask"):
                decision = ENV_FILE
            out[kind].append({
                "id": str(entry.get("id", pattern)),
                "pattern": pattern,
                "decision": decision,
            })
        if not out["home_path"] and not out["basename"]:
            raise ValueError("corpus has no entries")
        return out
    except Exception as exc:
        print("env-guard: could not load the guarded-secrets corpus "
              f"({exc.__class__.__name__}) — falling back to the built-in environ+dotenv "
              "floor so the guard never silently loses coverage. Check "
              "plugins/core-engineering/hooks/guarded-secrets.json.", file=sys.stderr)
        return {kind: [dict(e) for e in entries] for kind, entries in BUILTIN_FLOOR.items()}


def resolve(path, cwd):
    """Absolute, symlink-resolved form of `path`; '' if it cannot be anchored
    (or is absurdly long — realpath is ~quadratic in segment count, so an
    adversarial 1 MB token would stall the hook; the basename branch then denies
    fail-safe on the empty result, and the environ branch still has its raw
    regex)."""
    p = os.path.expanduser(path)
    if not os.path.isabs(p):
        if not cwd:
            return ""
        p = os.path.join(cwd, p)
    if len(p) > MAX_PATH:
        return ""
    return os.path.realpath(p)


def inside(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def home_match(pattern, resolved, raw_abs):
    """True if the realpath (or the non-realpath absolute form) of a candidate
    matches a home-anchored credential-store glob. A home-dir symlink is handled
    by also testing against the realpath'd HOME prefix, so the check holds whether
    or not `$HOME` itself is a symlink."""
    home = os.environ.get("HOME") or os.path.expanduser("~")
    expanded = os.path.expanduser(pattern)  # leading ~ -> HOME
    variants = {expanded}
    if expanded.startswith(home):
        variants.add(os.path.realpath(home) + expanded[len(home):])
    for cand in (resolved, raw_abs):
        if not cand:
            continue
        for pat in variants:
            if fnmatch(cand, pat):
                return True
    return False


_FNMATCH_META = "*?["


def _literal_prefix(pattern):
    """The leading substring of an fnmatch pattern before its first metacharacter
    (`*`, `?`, `[`); the whole string when it has none. Recovers the concrete part
    of a home-store glob so its containing directory can be derived."""
    for i, ch in enumerate(pattern):
        if ch in _FNMATCH_META:
            return pattern[:i]
    return pattern


def _store_dir(expanded_pattern):
    """The concrete directory a guarded `home_path` store lives in, from the
    literal (pre-metacharacter) prefix of its already-`~`-expanded pattern:
    `~/.ssh/id_*` -> `/home/u/.ssh`, `~/.aws/credentials` -> `/home/u/.aws`,
    `~/.netrc` -> `/home/u`. A directory-targeted read of this dir (or an ancestor
    of it) descends into the store, so it is denied alongside the file itself."""
    literal = _literal_prefix(expanded_pattern)
    if not literal:
        return ""
    if literal.endswith(os.sep):
        d = literal.rstrip(os.sep) or os.sep   # pattern globs a whole directory
    else:
        d = os.path.dirname(literal)           # a concrete file (or mid-name glob)
    return os.path.normpath(d) if d else ""


def home_dir_ancestor(pattern, resolved, raw_abs):
    """True if a candidate path IS a guarded home store's directory OR an ANCESTOR
    of it — the directory-read direction that complements home_match's file-glob
    match. This is what denies `grep -r ~/.ssh`, `cp -r ~/.aws`, `tar cf x ~/.ssh`,
    a `Grep` tool pointed at the store directory, and `grep -r ~`/`$HOME` (whose
    token is an ancestor of every store). A read of a *specific* non-credential
    file inside the store directory is not an ancestor and stays allowed. The
    realpath'd-HOME variant is included so the test holds if `$HOME` is a symlink."""
    home = os.environ.get("HOME") or os.path.expanduser("~")
    expanded = os.path.expanduser(pattern)
    variants = {expanded}
    if expanded.startswith(home):
        variants.add(os.path.realpath(home) + expanded[len(home):])
    store_dirs = {d for d in (_store_dir(v) for v in variants) if d}
    for cand in (resolved, raw_abs):
        if not cand:
            continue
        for sdir in store_dirs:
            if inside(sdir, cand):   # cand == sdir, or cand is an ancestor of sdir
                return True
    return False


def dir_has_guarded_basename(directory, corpus):
    """The first `basename` corpus entry directly present in `directory` (an
    existing dir), else None. Denies a directory-targeted read (`grep -r`/`cp -r`/
    `tar`) of an OUT-OF-WORKSPACE directory that holds a guarded secret — the same
    file-level rule applied to the directory a recursive read would descend into.
    Immediate children only (bounded, non-recursive) and best-effort: an
    unreadable listing degrades to None (allow), the `home_path` ancestor test
    still covering the credential stores at any depth."""
    try:
        names = os.listdir(directory)
    except OSError:
        return None
    for name in names:
        for entry in corpus["basename"]:
            if fnmatch(name, entry["pattern"]):
                return entry
    return None


def screen_path(raw, cwd, root, corpus):
    """Deny per guarded class; falling through means this path is unguarded."""
    resolved = resolve(raw, cwd)
    if ENVIRON_RE.search(raw) or (resolved and ENVIRON_RE.search(resolved)):
        decide(ENVIRON,
               f"core-engineering env-guard: `{raw}` is the process-environment file — "
               "the credential-exfil read this hook exists to cut. Denied. " + ESCAPE)
    raw_exp = os.path.expanduser(raw)
    raw_abs = os.path.normpath(raw_exp) if os.path.isabs(raw_exp) else ""
    # 1) home-anchored credential stores — denied regardless of workspace
    #    containment, in BOTH directions: the candidate IS the guarded file
    #    (home_match), OR the candidate IS the store's directory / an ancestor of
    #    it (home_dir_ancestor) so a recursive/directory read that would descend
    #    into the store — `grep -r ~/.ssh`, `cp -r ~/.aws`, `tar cf x ~/.ssh`, a
    #    `Grep` pointed at the dir, `grep -r ~` — is denied at the directory token.
    for entry in corpus["home_path"]:
        if home_match(entry["pattern"], resolved, raw_abs):
            decide(entry["decision"],
                   f"core-engineering env-guard: `{raw}` is a home-anchored credential store "
                   f"({entry['id']}, matching `{entry['pattern']}`) — never workspace content "
                   "for an agent to read. Denied. " + ESCAPE)
        if home_dir_ancestor(entry["pattern"], resolved, raw_abs):
            decide(entry["decision"],
                   f"core-engineering env-guard: `{raw}` is (or contains) the home-anchored "
                   f"credential store `{entry['pattern']}` ({entry['id']}) — a directory-"
                   "targeted read (grep -r / cp -r / tar) would descend into it. Denied. "
                   + ESCAPE)
    # 1b) a directory OUTSIDE the workspace that directly holds a guarded-basename
    #     secret — the same out-of-workspace file rule, applied to the directory a
    #     recursive read (grep -r / cp -r / tar) would descend into. Bounded to
    #     immediate children so a normal out-of-workspace dir with no secret stays
    #     allowed; home stores are covered at any depth by the ancestor test above.
    if resolved and root and os.path.isdir(resolved) and not inside(resolved, root):
        hit = dir_has_guarded_basename(resolved, corpus)
        if hit:
            decide(hit["decision"],
                   f"core-engineering env-guard: `{raw}` resolves to `{resolved}`, an "
                   f"out-of-workspace directory holding a guarded `{hit['pattern']}` secret — "
                   "a directory-targeted read would exfiltrate it. Denied. " + ESCAPE)
    # 2) guarded basenames — denied only outside the workspace root.
    bn_raw = os.path.basename(raw)
    bn_res = os.path.basename(resolved) if resolved else ""
    for entry in corpus["basename"]:
        pat = entry["pattern"]
        if fnmatch(bn_raw, pat) or (bn_res and fnmatch(bn_res, pat)):
            if not resolved or not root:
                decide(entry["decision"],
                       f"core-engineering env-guard: cannot determine whether `{raw}` (a "
                       f"guarded `{pat}` file) is inside the workspace (no resolvable "
                       "root/cwd) — denied fail-safe. " + ESCAPE)
            if not inside(resolved, root):
                decide(entry["decision"],
                       f"core-engineering env-guard: `{raw}` resolves to `{resolved}` — a "
                       f"guarded `{pat}` secret file outside the workspace. Out-of-workspace "
                       "secrets are not the agent's to read. Denied. " + ESCAPE)
            # matched a guarded basename but it resolves INSIDE the workspace → the
            # project's own file, allowed; no later basename entry can widen that.
            break


def bash_path_tokens(cmd):
    """Path candidates in a Bash command: raw absolute tokens, the value half of a
    `flag=PATH` / `KEY=PATH` token (covers `dd if=PATH`, `--file=PATH`,
    `ENVFILE=PATH`), AND every other non-empty relative token — bare names like
    `server` included, not only `.`/`/`-bearing ones. `resolve()` cwd-joins and
    realpaths those, so an out-of-workspace guarded file reached relatively
    (`cat ../../.env`) and a bare-named workspace symlink into a guarded class
    (`cat server`, `server -> ~/.aws/credentials`) are both caught symmetrically
    with the Read/Grep branch. Quotes are fully collapsed before matching, so
    `~` / `$HOME` / `${HOME}` forms are expanded even when split-quoted
    (`"$HOME"/.aws/credentials`, `$HOME"/.aws/credentials"`). Only a token whose
    realpath lands in a guarded class ever triggers a decision, so yielding bare
    tokens is false-positive bounded. Deeper shell evaluation (variable
    indirection, command substitution, base64) stays out of scope (documented)."""
    home = os.environ.get("HOME") or os.path.expanduser("~")
    for token in re.split(r"[\s;|&<>()`]+", cmd):
        # Collapse ALL quotes in the word (not just the outer pair) the way bash
        # concatenates a quoted word, so a split-quoted variable such as
        # `"$HOME"/.aws/credentials` or `$HOME"/.aws/credentials"` normalizes to
        # `$HOME/.aws/credentials` and the $HOME expansion below fires.
        raw = token.replace('"', "").replace("'", "")
        candidates = {raw}
        if "=" in raw:
            candidates.add(raw.split("=", 1)[1])
        for cand in candidates:
            tok = cand
            for pre in ("$HOME/", "${HOME}/"):
                if tok.startswith(pre):
                    tok = home + tok[len(pre) - 1:]
                    break
            else:
                if tok.startswith("~"):
                    tok = os.path.expanduser(tok)
            if tok.startswith("/"):
                yield tok
            elif tok and "=" not in tok:
                # Any other non-empty, non-`flag=value` token, yielded as a
                # relative candidate for resolve()/realpath to screen. This covers
                # relative paths (`../.env`) AND bare names (`server`), closing the
                # bare-name symlink asymmetry with the Read/Grep branch. The `=`
                # guard drops the raw `flag=path` form (its value is already a
                # separate candidate). False-positive bounded: only a realpath that
                # lands in a guarded class denies, so command words (`cat`, `grep`,
                # `-r`) resolve to non-guarded cwd paths and fall through to allow.
                yield tok


def main():
    try:
        data = json.load(sys.stdin)
        ok = isinstance(data, dict)
    except Exception:
        ok = False
    if not ok:
        # Harness drift, not an attack signal: a guarded read always arrives as a
        # JSON OBJECT with tool_name/tool_input, so an unparseable or non-object
        # payload cannot carry one. Loud non-blocking warn (exit 1) — never a
        # silent allow, and never a hard deny that would brick every Read/Grep/Bash
        # if the harness schema drifts.
        print("env-guard: unparseable hook input — the secrets screen was NOT applied to "
              "this tool call (check plugins/core-engineering/hooks/env-guard.py against "
              "the harness hook schema).", file=sys.stderr)
        sys.exit(1)
    try:
        if data.get("tool_name") not in GUARDED_TOOLS:
            return
        args = data.get("tool_input") or {}
        cwd = data.get("cwd") or ""
        root_raw = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
        root = os.path.realpath(root_raw) if root_raw else ""
        _LOG_CTX["root"] = root_raw or cwd or os.getcwd()
        _LOG_CTX["session_id"] = data.get("session_id") or ""
        _LOG_CTX["tool"] = data.get("tool_name") or ""
        _LOG_CTX["tool_input"] = args
        _LOG_CTX["hook_event"] = data.get("hook_event_name") or "PreToolUse"
        corpus = load_corpus()

        if data["tool_name"] == "Bash":
            cmd = args.get("command") or ""
            if ENVIRON_RE.search(cmd):
                decide(ENVIRON,
                       "core-engineering env-guard: this command references the "
                       "process-environment file (`/proc/.../environ`) — the credential-exfil "
                       "read this hook exists to cut. Denied. " + ESCAPE)
            for tok in bash_path_tokens(cmd):
                screen_path(tok, cwd, root, corpus)
        else:  # Read / Grep
            path = args.get("file_path") or args.get("path") or ""
            if path:
                screen_path(path, cwd, root, corpus)
        # nothing guarded matched → allow (silent)
    except Exception as e:
        decide("deny",
               f"core-engineering env-guard: internal error while screening this call "
               f"({e.__class__.__name__}) — denying fail-safe rather than passing a possible "
               "secrets read. " + ESCAPE)


if __name__ == "__main__":
    main()
