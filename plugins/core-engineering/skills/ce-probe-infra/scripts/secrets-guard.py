#!/usr/bin/env python3
"""secrets-guard.py — stop a PR that ADDS a live credential from going green.

The deterministic secret floor the merge bar lacked. It scans the lines a change ADDS
between two commits (base..head) for credential signatures + high-entropy assignments —
the git-history-aware, gitleaks-class territory ce-probe-infra's thin floor explicitly
routes OUT (SKILL.md) — and renders the same evidence-logged verdict every other gate
emits. Diff-scoped by design: it flags only secrets the change introduces, so a
pre-existing committed secret never reds every PR (the anti-"cries wolf" choice); a
whole-tree/historical sweep is the separate gitleaks adapter (docs/WORKFLOW-RECIPES.md).

Determinism: a pure function of the committed base..head diff — never the working tree,
never the network. Redaction: a matched credential is reported by type + file:line + a
REDACTED excerpt; the raw value is never written to stdout, JSON, or anywhere — the same
in-code discipline as infra-lint.py. Consulting the disposition ledger
(.merge-bar/dispositions.json, read AS COMMITTED at head): a consciously-accepted finding
moves to `accepted` (shown, counted, with its disposition id), never silently dropped —
so an accepted test fixture stops failing without hiding it. Editing that ledger escalates
the change to two-human review (merge-policy class_rules), so a PR cannot silently waive
its own new secret.

Advisory merge-bar gate (registered in merge-policy.json advisory_gates); an adopter
promotes it to required in a local policy override once its finding stream is dispositioned.

Exit codes: 0 = scanned clean (or every finding is actively dispositioned) · 1 = at least
one un-dispositioned secret in added lines · 2 = could not run (not a git repo, git failure)
— loud, never a silent pass.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import merge_disposition  # noqa: E402  (dir-local forked reader)

# Skip only genuinely vendored / tool-generated trees. Deliberately NOT env/build/dist:
# those are prime hand-authored-secret locations (env/prod.env), and the gate is
# diff-scoped so scanning them adds little noise (adversarial review finding).
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__"}

# Detection — the proven signature+entropy set from infra-lint.py (kept self-contained so
# the gate has no cross-skill import). See ce-probe-infra/scripts/infra-lint.py. NOTE: the
# value class here omits infra-lint's '#' exclusion on purpose — a '#' inside a credential
# (`aB#Str0ng…`, a connection string) must not truncate the captured value below the {6,}
# floor; `\s` still terminates an unquoted trailing `# comment` (adversarial review finding).
_AWS_AK_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_PEM_RE = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
_ASSIGN_SECRET_RE = re.compile(
    r"""(?ix)
    \b(password|passwd|pwd|secret|secret[_-]?key|token|auth[_-]?token|
       api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|
       connection[_-]?string|conn[_-]?str)\b
    \s*[:=]\s*
    ['"]?(?P<val>[^\s'"]{6,})['"]?
    """,
)
_PLACEHOLDER_RE = re.compile(
    r"""(?ix)^(
        \$\{.*\} | \{\{.*\}\} | <.*> |
        change[_-]?me | your[_-].* | example.* | sample.* | dummy.* | placeholder |
        x{3,} | todo | none | null | true | false |
        \d+(\.\d+)? |
        var\..* | local\..* | data\..* | module\..*
    )$""",
)


def eprint(*a):
    print(*a, file=sys.stderr)


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values())


def _looks_secret(val: str) -> bool:
    """A generic value is a credential candidate only if long, high-entropy, and not an
    obvious placeholder/reference — keeps `password: changeme` from flagging."""
    if _PLACEHOLDER_RE.match(val):
        return False
    if "${" in val or "{{" in val or val.startswith("$"):
        return False
    return len(val) >= 8 and _entropy(val) >= 3.0


def _scrub(line: str) -> str:
    """Blank EVERY credential shape in a line so an excerpt can never carry a raw value —
    including a second secret sharing the line. Over-redaction is safe: excerpts are made
    only for already-flagged lines."""
    text = _AWS_AK_RE.sub("[REDACTED]", line)
    text = _PEM_RE.sub("-----BEGIN [REDACTED] PRIVATE KEY-----", text)
    text = _ASSIGN_SECRET_RE.sub(lambda m: m.group(0).replace(m.group("val"), "[REDACTED]"), text)
    # {16,} matches detect()'s base64-inline floor exactly: every blob the scan can FLAG is
    # also scrubbed, so a 16–19 char detected token can never leak (adversarial review finding).
    text = re.sub(r"[A-Za-z0-9+/]{16,}={0,2}", "[REDACTED]", text)  # long blobs (base64 etc.)
    return text.strip()[:200]


def detect(line: str) -> str | None:
    """Return the credential TYPE found in a line (redaction-safe label), or None. The raw
    value is used only to locate + redact; it never leaves this function."""
    if _AWS_AK_RE.search(line):
        return "AWS access key id"
    if _PEM_RE.search(line):
        return "PEM private key header"
    m = _ASSIGN_SECRET_RE.search(line)
    if m and _looks_secret(m.group("val")):
        return f"assignment to `{m.group(1).lower()}`"
    bm = re.match(r"\s*[\w.\-]+\s*:\s*([A-Za-z0-9+/]{16,}={0,2})\s*$", line)
    if bm:
        try:
            decoded = base64.b64decode(bm.group(1), validate=True).decode("utf-8", "replace")
        except (ValueError, UnicodeError):
            decoded = ""
        if _AWS_AK_RE.search(decoded) or _PEM_RE.search(decoded) or _looks_secret(decoded):
            return "base64-encoded inline value"
    return None


def _skipped(path: str) -> bool:
    return any(part in SKIP_DIRS for part in path.split("/"))


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    # errors="replace": a non-UTF-8 byte in an added line or in the committed ledger blob
    # must not crash the decode (subprocess raises UnicodeDecodeError inside text=True). The
    # scan still runs on the lossy text — a secret in a latin-1 file is still caught, and the
    # ledger flows to parse_ledger's graceful degradation (adversarial review finding).
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True, errors="replace", timeout=60)


def added_lines(repo: str, base: str, head: str):
    """Yield (path, new_line_number, content) for every line the diff ADDS between base and
    head. Raises RuntimeError on any git failure (caller degrades to exit 2)."""
    proc = _git(repo, "diff", "--unified=0", "--no-color", "--no-ext-diff", base, head)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git diff exited {proc.returncode}")
    # Track hunk state: `+++ `/`--- ` are file headers ONLY before a file's first `@@`; once
    # inside a hunk every `+`-prefixed line is added CONTENT. Without this an added content
    # line that literally reads `++ /dev/null` is misparsed as a `+++` header and silently
    # disables the scan for the rest of the file — a live-secret bypass (adversarial review
    # finding). `diff --git` resets the boundary for each file.
    path = None
    new_lineno = 0
    in_hunk = False
    for raw in proc.stdout.splitlines():
        if raw.startswith("diff --git"):
            in_hunk = False
            path = None
            continue
        if not in_hunk and raw.startswith("+++ "):
            target = raw[4:].strip()
            path = None if target == "/dev/null" else re.sub(r"^b/", "", target)
            continue
        if raw.startswith("@@"):
            in_hunk = True
            m = re.search(r"\+(\d+)", raw)
            new_lineno = int(m.group(1)) if m else 0
            continue
        if in_hunk and raw.startswith("+"):
            if path and not _skipped(path):
                yield path, new_lineno, raw[1:]
            new_lineno += 1
    return


def read_committed_ledger(repo: str, head: str):
    """Load .merge-bar/dispositions.json AS COMMITTED at head (never the working tree)."""
    proc = _git(repo, "show", f"{head}:{merge_disposition.LEDGER_RELPATH}")
    if proc.returncode != 0:
        return [], None  # ledger absent at head — no dispositions
    return merge_disposition.parse_ledger(proc.stdout)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan lines a change adds (base..head) for secret credentials.")
    parser.add_argument("--repo", default=".", help="repository root (a git repo)")
    parser.add_argument("--base", help="base ref/sha to diff FROM (required to scan)")
    parser.add_argument("--head", default="HEAD", help="head ref/sha to diff TO")
    parser.add_argument("--today", help="override today for disposition expiry (YYYY-MM-DD; tests)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    repo = os.path.abspath(args.repo)
    if not os.path.isdir(os.path.join(repo, ".git")) and not os.path.isdir(repo):
        eprint(f"secrets-guard: ERROR — repo not found: {repo}")
        return 2
    if not args.base:
        eprint("secrets-guard: ERROR — --base is required to scan a change. This is not a pass.")
        return 2

    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        eprint(f"secrets-guard: ERROR — bad --today {args.today!r}")
        return 2

    try:
        rows = list(added_lines(repo, args.base, args.head))
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        eprint(f"secrets-guard: DEGRADED — git diff failed ({exc.__class__.__name__}: {exc}). "
               "The change was NOT scanned. This is not a pass.")
        return 2

    raw_findings = []
    files = set()
    for path, lineno, content in rows:
        files.add(path)
        f_type = detect(content)
        if f_type:
            raw_findings.append({"file": path, "line": lineno, "type": f_type,
                                 "excerpt": _scrub(content)})

    entries, ledger_err = read_committed_ledger(repo, args.head)
    findings, accepted = merge_disposition.partition(raw_findings, entries, "secrets-guard", today)

    hard_failures = [
        f"{f['type']} in an added line at {f['file']}:{f['line']} — value redacted: {f['excerpt']}"
        for f in findings
    ]
    result = {
        "schema_version": 1,
        "status": "fail" if findings else "pass",
        "files_scanned": len(files),
        "added_lines_scanned": len(rows),
        "findings": findings,
        "accepted": accepted,
        "hard_failures": hard_failures,
    }
    if ledger_err:
        # A malformed ledger cannot suppress (we scanned with no dispositions); surface it,
        # never swallow it — disposition-lint fails on it as a required detail.
        result["ledger_warning"] = ledger_err

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"secrets-guard: scanned {len(rows)} added line(s) across {len(files)} file(s); "
              f"{len(findings)} secret(s), {len(accepted)} accepted via ledger.")
        for f in findings:
            print(f"  ✗ {f['type']} at {f['file']}:{f['line']} — {f['excerpt']}")
        for a in accepted:
            print(f"  ○ accepted [{a['disposition_id']}] {a['type']} at {a['file']}:{a['line']}")
        if ledger_err:
            eprint(f"secrets-guard: ledger warning — {ledger_err}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
