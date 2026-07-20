#!/usr/bin/env python3
"""net-guard.py — PreToolUse egress checkpoint (the send-side guard hook).

env-guard.py closes the credential-*read* half of the exfiltration bug that
motivated it (the May-2026 Claude Code GitHub Action leak) — but reading a secret
is only half of an exfil, and the adversarial review of this layer noted the guards
watched reads and not the *send*. This hook is the send half: on `Bash`, `WebFetch`,
and `WebSearch` it screens OUTBOUND network calls against a data-driven per-repo
allowlist and confirms (or denies) the ones that leave it.

INERT WITHOUT A POLICY. Like write-scope-guard, this guard does nothing until a
policy file exists — so it is safe to leave always-on and a no-policy session sees
ZERO friction. The policy lives at `.claude/ce-net-policy.json` (override the path
with `CE_NET_POLICY`, for tests/operators) and is seeded by `/core-engineering:ce-init`:

  {
    "schema_version": 1,
    "enabled": true,
    "allow_hosts": ["api.github.com", "*.githubusercontent.com"],
    "tiers": {"non_allowlisted": "ask", "upload": "ask"}
  }

`allow_hosts` is a list of fnmatch host globs. `tiers` values are `ask` (default)
or `deny`. Loopback hosts (`localhost`, `127.0.0.1`, `0.0.0.0`, `::1`) are never
egress and always pass regardless of the allowlist.

Decisions (strongest wins: deny > ask > silent allow):

  * a network command whose UPLOAD PAYLOAD is a guarded secret — `curl -d @.env`,
    `curl -T id_rsa`, `curl -F x=@.env.prod` — or whose line references a
    home-anchored credential STORE (`~/.aws/credentials`, `~/.ssh/id_*`, …)
    alongside a network verb → **deny**. This is the exfil headline; the guarded
    corpus is env-guard's `guarded-secrets.json` (reused via its WS4-T7 loader).
  * an upload flag (`curl -d/--data*/-F/--form/-T/--upload-file`,
    `wget --post-data/--post-file/--body-data/--body-file`) to a NON-allowlisted
    host → the `upload` tier (default `ask`; escalate to deny with
    `CE_NET_GUARD_UPLOAD=deny`).
  * any network verb (`curl`, `wget`, `nc`, `ssh`, `scp`, `sftp`, `rsync`, …)
    to a NON-allowlisted host, and a `WebFetch` to a non-allowlisted URL host →
    the `non_allowlisted` tier (default `ask`).
  * everything else → silent allow. A non-network Bash command (`ls`, `git
    status`) is never touched even with a policy active.

The `Bash` scan reuses git-guard.py's tokenizer BY PATH (segment splitter /
`_tokenize` / `_unwrap` / `_program`) — one tokenizer, no fork (the write-scope
precedent) — so `sudo curl …`, `timeout 10 curl …`, and shell-operator chains are
read at command position.

Kill switch (documented, local): `CE_NET_GUARD=off` disables the guard entirely
for this environment. Decisions are appended best-effort to
`.claude/ce-guard-log.jsonl` through the shared `guard_log.py` writer (NEVER raw
appends), which sha256-chains each line to the prior one so the ledger stays
tamper-evident (`guard_log.py --verify <file>`).

Error posture (per-vector, deliberate):
  * `CE_NET_GUARD=off` → allow everything (guard disabled).
  * unparseable hook input, or a payload with no `tool_name` → loud non-blocking
    warning (stderr + exit 1): a guarded call always arrives as a JSON object, so
    an unparseable shape cannot carry one. Never a silent allow, never a hard
    block that would brick every Bash/WebFetch on harness drift (env-guard's
    precedent).
  * no policy file, or a disabled policy → inert (allow, exit 0).
  * a policy PRESENT but unreadable/invalid → `ask` on the network call (confirm
    instead of guessing — git-guard's posture; fixing the policy JSON stops it).
  * an unexpected internal error while screening → `ask` (fail toward confirm,
    never a silent unscreened egress and never a bricking hard deny).

Honest limitations — a CHECKPOINT, not a network sandbox. Out of scope and
DOCUMENTED, never implied away: DNS-tunnel exfil (data smuggled in subdomain
lookups); interpreter/shell sockets (`python -c 'import socket…'`, bash
`/dev/tcp/host/port`, `<(…)`); MCP-mediated egress (MCP tools load no plugin
hook); shell-variable / `$VAR` / command-substitution host indirection and
base64-obfuscated commands; and execution surfaces that load no `hooks.json`.
Host extraction is heuristic: an option value may occasionally
be mis-read as a host (an extra harmless `ask`, never a wrong deny), a bare
internal hostname with no dot is not extracted, and a `$VAR` URL is not resolved
(not screened). `ssh`/`scp`/`rsync`/`nc` host parsing is best-effort; the reliably
screened, tested vectors are `curl`/`wget` URLs, their upload flags, and
`WebFetch`. The secrets deny is a co-occurrence signal: a `.pem`/`.key` may be a
public cert (a false deny — use the kill switch or move the file). `WebSearch` is
matched for completeness but carries no target host in its payload, so it is
acknowledged and passed unscreened.
"""

from __future__ import annotations

import json
import os
import sys
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urlparse


def _load_sibling(name: str, mod_name: str):
    """Load a sibling hook module BY PATH (importlib) so the portability AST scan
    sees only stdlib imports and there is ONE implementation, not a fork; wrapped
    so a missing/broken sibling degrades gracefully rather than crashing the guard.
    git-guard/env-guard/guard_log module bodies have no import-time side effects
    (their `main()` runs only under `__name__ == '__main__'`)."""
    try:
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
        spec = importlib.util.spec_from_file_location(mod_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


_GUARD_LOG = _load_sibling("guard_log.py", "ce_guard_log")
_GIT_GUARD = _load_sibling("git-guard.py", "ce_git_guard")
_ENV_GUARD = _load_sibling("env-guard.py", "ce_env_guard")

# Actor context captured once in main() from the hook payload, so decide() can
# hash-chain session/tool/payload into the shared guard log.
_LOG_CTX = {"root": "", "session_id": "", "tool": "", "tool_input": None,
            "hook_event": "PreToolUse"}

TARGET_TOOLS = ("Bash", "WebFetch", "WebSearch")
DEFAULT_POLICY = ".claude/ce-net-policy.json"
POLICY_ENV = "CE_NET_POLICY"
MAX_TOK = 4096  # longer "paths"/URLs are adversarial padding — don't realpath them

# Loopback is never egress — always allowed regardless of the allowlist.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"})

# Network programs, by host-extraction family.
HTTP_PROGRAMS = frozenset({"curl", "wget"})
SSH_PROGRAMS = frozenset({"ssh", "scp", "sftp", "rsync"})
SOCKET_PROGRAMS = frozenset({"nc", "ncat", "netcat", "telnet", "ftp", "socat"})
NET_PROGRAMS = HTTP_PROGRAMS | SSH_PROGRAMS | SOCKET_PROGRAMS

# --- curl/wget option tables --------------------------------------------------
# curl/wget options whose FOLLOWING space-separated token is a value (not a URL);
# skipped so an option value (`-o out.html`, `-H 'Host: x'`) is never read as a
# host. Attached (`-oout.html`) and `=`-joined (`--output=out.html`) forms start
# with `-`, so they are skipped as flags without needing to appear here.
_HTTP_OPTS_WITH_ARG = frozenset({
    "-o", "--output", "-H", "--header", "-u", "--user", "-A", "--user-agent",
    "-e", "--referer", "-b", "--cookie", "-c", "--cookie-jar", "-x", "--proxy",
    "-w", "--write-out", "-K", "--config", "-m", "--max-time", "--retry",
    "--connect-to", "--resolve", "--cacert", "--cert", "--key", "-E",
    "-d", "--data", "--data-ascii", "--data-binary", "--data-urlencode",
    "--data-raw", "-F", "--form", "-T", "--upload-file", "-X", "--request",
    # wget
    "-O", "--output-document", "-P", "--directory-prefix", "--user-agent",
    "--password", "--referer", "-U", "--limit-rate", "-o", "--output-file",
    "-a", "--append-output", "--header", "--post-data", "--post-file",
    "--body-data", "--body-file",
})
# curl `--url URL` names the URL explicitly (the value IS the URL, not skipped).
_URL_NAMING = frozenset({"--url"})

# Upload flags whose value is FILE-BACKED (a local file read into the request body
# → the exfil payload). curl `@file`/`name=@file`, or a direct filename.
_CURL_AT_DATA = frozenset({"-d", "--data", "--data-ascii", "--data-binary",
                           "--data-urlencode"})  # file only when value starts `@`
_CURL_FORM = frozenset({"-F", "--form"})          # name=@file / name=<file
_CURL_FILE = frozenset({"-T", "--upload-file"})   # value is directly a file
_WGET_FILE = frozenset({"--post-file", "--body-file"})  # value is directly a file
# Any upload flag at all (file-backed or literal) — marks the call as an upload,
# so a NON-allowlisted destination gets the `upload` tier even for literal bodies.
_UPLOAD_FLAGS = (_CURL_AT_DATA | _CURL_FORM | _CURL_FILE | _WGET_FILE
                 | frozenset({"--data-raw", "--post-data", "--body-data"}))

# ssh/scp/rsync/nc options whose following token is a value (skipped so it is not
# mistaken for a destination host).
_SSH_OPTS_WITH_ARG = frozenset({
    "-p", "-P", "-i", "-o", "-l", "-L", "-R", "-D", "-b", "-c", "-e", "-F",
    "-J", "-m", "-O", "-Q", "-S", "-W", "-w", "--rsh", "--port", "--temp-dir",
    "--exclude", "--include", "--files-from", "--out-format", "-x", "-X",
    "-q", "-I", "-N", "-s", "-T",
})

RANK = {"deny": 2, "ask": 1}

KILL_SWITCH_HINT = (
    "Scoped opt-out: confirm the prompt, or set CE_NET_GUARD=off to disable this "
    "egress checkpoint for the environment (say why)."
)

BUILTIN_CORPUS = {
    "home_path": [
        {"id": "aws-credentials", "pattern": "~/.aws/credentials"},
        {"id": "ssh-private-key", "pattern": "~/.ssh/id_*"},
        {"id": "netrc", "pattern": "~/.netrc"},
    ],
    "basename": [
        {"id": "dotenv", "pattern": ".env"},
        {"id": "dotenv-suffixed", "pattern": ".env.*"},
        {"id": "pem", "pattern": "*.pem"},
        {"id": "key", "pattern": "*.key"},
    ],
}


# --- logging / decision --------------------------------------------------------
def log_decision(decision: str, reason: str) -> None:
    """Best-effort, hash-chained record of this guard's decision (via the shared
    guard_log.py writer). Never raises — a logging failure must not change a
    permission decision."""
    if _GUARD_LOG is None:
        return
    try:
        root = (_LOG_CTX.get("root") or os.environ.get("CLAUDE_PROJECT_DIR")
                or os.getcwd())
        _GUARD_LOG.append_entry(
            root, "net-guard", decision, reason, _LOG_CTX.get("tool_input"),
            session_id=_LOG_CTX.get("session_id", ""),
            tool=_LOG_CTX.get("tool", ""),
            hook_event=_LOG_CTX.get("hook_event", "PreToolUse"),
        )
    except Exception:
        pass


def decide(decision: str, reason: str) -> None:
    log_decision(decision, reason)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


# --- policy --------------------------------------------------------------------
def workspace_root(cwd: str | None = None) -> Path:
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd()
    try:
        return Path(raw).expanduser().resolve()
    except OSError:
        return Path(raw)


def policy_path(root: Path) -> Path:
    raw = os.environ.get(POLICY_ENV)
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_absolute() else (root / p)
    return root / DEFAULT_POLICY


def load_policy(path: Path):
    """Return (status, policy). status ∈ {absent, disabled, malformed, ok}.
    `policy` is the normalized dict only when status == 'ok'."""
    if not path.is_file():
        return ("absent", None)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ("malformed", None)
    if not isinstance(data, dict):
        return ("malformed", None)
    if not data.get("enabled", False):
        return ("disabled", None)
    if data.get("schema_version") != 1:
        return ("malformed", None)
    allow = data.get("allow_hosts", [])
    if not isinstance(allow, list) or not all(isinstance(x, str) for x in allow):
        return ("malformed", None)
    tiers = data.get("tiers")
    return ("ok", {
        "allow_hosts": [x.strip().lower() for x in allow if x.strip()],
        "tiers": tiers if isinstance(tiers, dict) else {},
    })


def policy_tier(policy: dict, name: str, default: str = "ask") -> str:
    v = (policy.get("tiers") or {}).get(name, default)
    if isinstance(v, str) and v.strip().lower() in ("ask", "deny"):
        return v.strip().lower()
    return default


def upload_decision(policy: dict) -> str:
    """The effective upload-tier decision: an explicit CE_NET_GUARD_UPLOAD env
    overrides the policy tier (the documented deny escalation)."""
    env = os.environ.get("CE_NET_GUARD_UPLOAD", "").strip().lower()
    if env in ("ask", "deny"):
        return env
    return policy_tier(policy, "upload", "ask")


# --- host handling -------------------------------------------------------------
def _looks_like_host(s: str) -> bool:
    """A scheme-less token is treated as a host only when it looks like one — a
    dotted name / IP. This keeps bare command words (`file`, `data`) and
    dotless internal names out of the extractor (a documented miss), so the
    scheme-URL path stays the reliable signal and false `ask`s stay rare."""
    if not s or len(s) > 255 or "." not in s:
        return False
    body = s.strip("[]")
    return all(ch.isalnum() or ch in ".-:" for ch in body)


def _host_from_urlish(token: str):
    """Best-effort host from a URL-ish token: a scheme URL via urlparse, else a
    scheme-less `user@host:port/path` head when it looks like a host."""
    tok = token.strip().strip('"').strip("'")
    if not tok or len(tok) > MAX_TOK:
        return None
    if "://" in tok:
        try:
            h = urlparse(tok).hostname
        except ValueError:
            h = None
        return h.lower() if h else None
    head = tok.split("/", 1)[0]
    if "@" in head:
        head = head.rsplit("@", 1)[1]
    hostpart = head.split(":", 1)[0]
    return hostpart.lower() if _looks_like_host(hostpart) else None


def host_allowed(host: str, allow_hosts) -> bool:
    if not host:
        return True  # nothing extracted → nothing to screen
    h = host.strip().lower().strip("[]")
    if h in LOOPBACK_HOSTS or h.strip("[]") in LOOPBACK_HOSTS:
        return True
    return any(fnmatch(h, glob) for glob in allow_hosts)


def _http_hosts(tokens):
    """Hosts a curl/wget invocation targets: scheme URLs, `--url` values, and
    scheme-less positional hosts. Value-taking options are skipped so their
    values are never mistaken for a host."""
    hosts = []
    i = 1
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t in _URL_NAMING:
            if i + 1 < n:
                h = _host_from_urlish(tokens[i + 1])
                if h:
                    hosts.append(h)
            i += 2
            continue
        if t.startswith("--url="):
            h = _host_from_urlish(t.split("=", 1)[1])
            if h:
                hosts.append(h)
            i += 1
            continue
        if t in _HTTP_OPTS_WITH_ARG:
            i += 2  # skip the option AND its value
            continue
        if t.startswith("-"):
            i += 1  # attached / `=`-joined flag (value glued in) — not a host
            continue
        h = _host_from_urlish(t)  # positional URL or bare host
        if h:
            hosts.append(h)
        i += 1
    return hosts


def _ssh_hosts(tokens):
    """Best-effort destination hosts for ssh/scp/sftp/rsync: `user@host`,
    `host:path`, and `scheme://host` forms; value-taking options skipped."""
    hosts = []
    i = 1
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t in _SSH_OPTS_WITH_ARG:
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        tok = t.strip().strip('"').strip("'")
        if "://" in tok:
            h = _host_from_urlish(tok)
            if h:
                hosts.append(h)
        elif "@" in tok:  # user@host[:path] — the @ makes it unambiguously remote
            rest = tok.rsplit("@", 1)[1]
            hostpart = rest.split(":", 1)[0].split("/", 1)[0]
            if hostpart:
                hosts.append(hostpart.lower())
        elif ":" in tok and "/" not in tok.split(":", 1)[0]:  # host:path
            hostpart = tok.split(":", 1)[0]
            if _looks_like_host(hostpart):
                hosts.append(hostpart.lower())
        elif _looks_like_host(tok):  # bare dotted host (`ssh a.example.com`)
            hosts.append(tok.lower())
        i += 1
    return hosts


def _socket_hosts(prog, tokens):
    """Best-effort host for nc/ncat/netcat/telnet/ftp/socat: the first non-option
    positional. A listener (`nc -l`) is not egress → no host."""
    if prog in ("nc", "ncat", "netcat", "socat"):
        if any(t in ("-l", "--listen") or t.startswith("-l") for t in tokens[1:]):
            return []
    i = 1
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t in _SSH_OPTS_WITH_ARG:
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        tok = t.strip().strip('"').strip("'")
        if "://" in tok:
            h = _host_from_urlish(tok)
            return [h] if h else []
        hostpart = tok.split(":", 1)[0]
        return [hostpart.lower()] if _looks_like_host(hostpart) else []
    return []


def segment_hosts(prog, tokens):
    if prog in HTTP_PROGRAMS:
        return _http_hosts(tokens)
    if prog in SSH_PROGRAMS:
        return _ssh_hosts(tokens)
    if prog in SOCKET_PROGRAMS:
        return _socket_hosts(prog, tokens)
    return []


# --- upload / secret detection -------------------------------------------------
def _opt_value(tokens, i):
    """The value of an option token at index i: an attached (`-dVAL`), a
    `--flag=VAL`, or a following-token value. Returns (value_or_None, consumed)."""
    t = tokens[i]
    if "=" in t and t.startswith("--"):
        return t.split("=", 1)[1], 1
    # attached short form: -dVAL (len>2, not a long option)
    if len(t) > 2 and t[1] != "-" and t.startswith("-"):
        return t[2:], 1
    if i + 1 < len(tokens):
        return tokens[i + 1], 2
    return None, 1


def _short_flag(t: str) -> str:
    """The canonical flag for an attached short option (`-dVAL` -> `-d`); the
    token unchanged otherwise."""
    if len(t) > 2 and t.startswith("-") and t[1] != "-":
        return t[:2]
    if t.startswith("--") and "=" in t:
        return t.split("=", 1)[0]
    return t


def upload_info(prog, tokens):
    """(has_upload, payload_files) for a curl/wget segment. has_upload is True for
    ANY upload flag (file-backed or literal). payload_files lists only the
    FILE-BACKED payloads (the exfil candidates)."""
    if prog not in HTTP_PROGRAMS:
        return (False, [])
    has_upload = False
    files = []
    i = 1
    n = len(tokens)
    while i < n:
        t = tokens[i]
        flag = _short_flag(t)
        if flag in _UPLOAD_FLAGS:
            has_upload = True
            val, consumed = _opt_value(tokens, i)
            if val is not None:
                if flag in _CURL_AT_DATA:
                    if val.startswith("@"):
                        files.append(val[1:])
                elif flag in _CURL_FORM:
                    for sep in ("=@", "=<"):
                        if sep in val:
                            files.append(val.split(sep, 1)[1])
                            break
                elif flag in _CURL_FILE or flag in _WGET_FILE:
                    files.append(val)
            i += consumed
            continue
        i += 1
    return (has_upload, files)


def _clean_file_token(token: str) -> str:
    tok = token.strip().strip('"').strip("'")
    if tok.startswith("@"):
        tok = tok[1:]
    return tok


def _home_match(pattern, resolved, raw_abs) -> bool:
    if _ENV_GUARD is not None and hasattr(_ENV_GUARD, "home_match"):
        try:
            return _ENV_GUARD.home_match(pattern, resolved, raw_abs)
        except Exception:
            pass
    exp = os.path.expanduser(pattern)
    for cand in (resolved, raw_abs):
        if cand and fnmatch(cand, exp):
            return True
    return False


def corpus_hit(token, corpus, include_basename: bool):
    """The guarded-secrets entry a local-file token matches, or None. A URL token
    (`://`) is never a local file. `home_path` stores match via env-guard's
    home_match; `basename` classes match the filename glob (workspace-relative
    location is irrelevant here — sending a project's own `.env` out IS the leak)."""
    f = _clean_file_token(token)
    if not f or "://" in f or len(f) > MAX_TOK:
        return None
    exp = os.path.expanduser(f)
    raw_abs = os.path.normpath(exp) if os.path.isabs(exp) else ""
    try:
        resolved = os.path.realpath(exp)
    except OSError:
        resolved = ""
    for entry in corpus.get("home_path", []):
        if _home_match(entry["pattern"], resolved, raw_abs):
            return entry
    if include_basename:
        bn = os.path.basename(f)
        for entry in corpus.get("basename", []):
            if fnmatch(bn, entry["pattern"]):
                return entry
    return None


def load_corpus():
    if _ENV_GUARD is not None and hasattr(_ENV_GUARD, "load_corpus"):
        try:
            return _ENV_GUARD.load_corpus()
        except Exception:
            pass
    return {k: [dict(e) for e in v] for k, v in BUILTIN_CORPUS.items()}


# --- screening -----------------------------------------------------------------
def _tokens_for(segment):
    if _GIT_GUARD is not None:
        return _GIT_GUARD._unwrap(_GIT_GUARD._tokenize(segment))
    return segment.split()


def _program(tokens):
    if not tokens:
        return ""
    if _GIT_GUARD is not None:
        return _GIT_GUARD._program(tokens)
    return os.path.basename(tokens[0]).lower()


def _segments(cmd):
    if _GIT_GUARD is not None:
        return _GIT_GUARD._SEGMENT_SPLIT.split(cmd)
    return [cmd]


def screen_bash(cmd: str, policy: dict, corpus: dict) -> None:
    """Screen a Bash command's outbound network vectors; decide() the strongest
    finding (deny > ask), or return to allow silently."""
    allow_hosts = policy["allow_hosts"]
    parsed = []          # (prog, tokens) for each segment
    all_tokens = []
    network_present = False
    findings = []        # (rank, decision, reason)

    for segment in _segments(cmd):
        tokens = _tokens_for(segment)
        if not tokens:
            continue
        prog = _program(tokens)
        parsed.append((prog, tokens))
        all_tokens.extend(tokens)
        if prog not in NET_PROGRAMS:
            continue
        network_present = True
        hosts = list(dict.fromkeys(segment_hosts(prog, tokens)))
        has_upload, payload_files = upload_info(prog, tokens)

        # Rule S1: an upload payload that is a guarded secret → deny (any host).
        for pf in payload_files:
            hit = corpus_hit(pf, corpus, include_basename=True)
            if hit:
                findings.append((RANK["deny"], "deny",
                    f"core-engineering net-guard: this `{prog}` command uploads "
                    f"`{pf}` — a guarded secret ({hit['id']}, matching "
                    f"`{hit['pattern']}`) — to the network. That is credential "
                    f"exfiltration; denied. " + KILL_SWITCH_HINT))

        non_allow = [h for h in hosts if not host_allowed(h, allow_hosts)]
        if non_allow:
            for h in non_allow:
                if has_upload:
                    d = upload_decision(policy)
                    findings.append((RANK[d], d,
                        f"core-engineering net-guard: `{prog}` UPLOADS to `{h}`, "
                        f"a host outside this repo's egress allowlist. Confirm the "
                        f"data leaving the workspace (or add the host to "
                        f"`{DEFAULT_POLICY}`). " + KILL_SWITCH_HINT))
                else:
                    d = policy_tier(policy, "non_allowlisted", "ask")
                    findings.append((RANK[d], d,
                        f"core-engineering net-guard: `{prog}` reaches `{h}`, a "
                        f"host outside this repo's egress allowlist. Confirm this "
                        f"outbound call (or add the host to `{DEFAULT_POLICY}`). "
                        + KILL_SWITCH_HINT))
        elif has_upload and not hosts:
            # An upload whose destination this guard could not read — confirm it.
            d = upload_decision(policy)
            findings.append((RANK[d], d,
                f"core-engineering net-guard: `{prog}` performs an upload to a "
                f"destination this guard could not read from the command. Confirm "
                f"what data is leaving the workspace. " + KILL_SWITCH_HINT))

    # Rule S2: a home-anchored credential STORE referenced alongside any network
    # verb (`cat ~/.aws/credentials | curl …`) → deny. Home stores are never
    # legit workspace content, so co-occurrence with egress is the exfil pattern.
    if network_present:
        for tok in all_tokens:
            hit = corpus_hit(tok, corpus, include_basename=False)
            if hit:
                findings.append((RANK["deny"], "deny",
                    f"core-engineering net-guard: this command references the "
                    f"home-anchored credential store `{tok}` ({hit['id']}) "
                    f"alongside a network verb — the exfiltration pattern. Denied. "
                    + KILL_SWITCH_HINT))
                break

    if not findings:
        return  # allow silently
    findings.sort(key=lambda f: f[0], reverse=True)
    _, decision, reason = findings[0]
    decide(decision, reason)


def screen_webfetch(url, policy: dict) -> None:
    host = _host_from_urlish(url) if isinstance(url, str) else None
    if host and not host_allowed(host, policy["allow_hosts"]):
        d = policy_tier(policy, "non_allowlisted", "ask")
        decide(d,
               f"core-engineering net-guard: WebFetch targets `{host}`, a host "
               f"outside this repo's egress allowlist. Confirm this fetch (or add "
               f"the host to `{DEFAULT_POLICY}`). " + KILL_SWITCH_HINT)
    # allowlisted / loopback / unresolvable → allow silently


def main() -> None:
    if os.environ.get("CE_NET_GUARD", "").strip().lower() == "off":
        return  # kill switch: guard disabled for this environment
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("net-guard: unparseable hook input — the egress screen was NOT "
              "applied to this tool call (check plugins/core-engineering/hooks/"
              "net-guard.py against the harness hook schema).", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict) or "tool_name" not in data:
        print("net-guard: hook payload has no tool_name — the egress screen was "
              "NOT applied to this tool call.", file=sys.stderr)
        sys.exit(1)

    tool = data.get("tool_name")
    if tool not in TARGET_TOOLS:
        return  # correctly recognized non-target event

    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    root = workspace_root(cwd)
    status, policy = load_policy(policy_path(root))
    if status in ("absent", "disabled"):
        return  # inert — zero friction without an enabled policy

    _LOG_CTX["root"] = (os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd())
    _LOG_CTX["session_id"] = data.get("session_id") or ""
    _LOG_CTX["tool"] = tool or ""
    _LOG_CTX["tool_input"] = data.get("tool_input")
    _LOG_CTX["hook_event"] = data.get("hook_event_name") or "PreToolUse"

    try:
        if tool == "WebSearch":
            return  # no target host in the payload — nothing to screen
        tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        if tool == "Bash":
            cmd = tool_input.get("command")
            if not isinstance(cmd, str) or not cmd.strip():
                return  # no readable command — nothing to screen
            if status == "malformed":
                decide("ask",
                       "core-engineering net-guard: an egress policy is present at "
                       f"`{DEFAULT_POLICY}` but could not be read as a valid "
                       "schema_version:1 object — confirming this network call "
                       "instead of guessing the allowlist. Fix the policy JSON. "
                       + KILL_SWITCH_HINT)
            corpus = load_corpus()
            screen_bash(cmd, policy, corpus)
        else:  # WebFetch
            url = tool_input.get("url")
            if not isinstance(url, str) or not url.strip():
                return
            if status == "malformed":
                decide("ask",
                       "core-engineering net-guard: an egress policy is present at "
                       f"`{DEFAULT_POLICY}` but could not be read as a valid "
                       "schema_version:1 object — confirming this fetch instead of "
                       "guessing the allowlist. Fix the policy JSON. "
                       + KILL_SWITCH_HINT)
            screen_webfetch(url, policy)
    except SystemExit:
        raise
    except Exception as exc:
        decide("ask",
               f"core-engineering net-guard: internal error while screening this "
               f"call ({exc.__class__.__name__}) — confirming fail-safe rather "
               f"than passing an unscreened egress. " + KILL_SWITCH_HINT)


if __name__ == "__main__":
    main()
