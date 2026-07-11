#!/usr/bin/env python3
"""hook-integrity.py — SessionStart hook self-integrity check.

The PreToolUse guards (git-guard, env-guard, write-scope-guard, net-guard) can
police tool calls but cannot detect their OWN subversion: an in-session
`sed -i` on env-guard.py silently disarms the credential-read confinement and no
guard notices (the trust finding's "guards cannot detect their own
subversion"). This SessionStart hook closes that blind spot: at every session
start it recomputes the sha256 of each `hooks/*.py` + `hooks.json` and compares
them to the shipped, CI-verified `integrity-manifest.json`. On any drift it
prints a loud, named warning.

Posture — a passive reporter, like model-attest.py:
  - it **never blocks** — SessionStart cannot block a tool call, and a
    deliberate local edit or an in-flight plugin upgrade must not brick a
    session; the goal is that tampering becomes *detectable*, not impossible. It
    exits 0 on every path.
  - it **never raises** — any error is swallowed. A failed self-check must not
    cost a session.
  - a **missing/unreadable manifest degrades loudly** (own warning) rather than
    passing silently — an absent oracle is itself worth surfacing.

Honest bound — tamper-EVIDENCE, not tamper-proofing: an agent with Bash can
rewrite `integrity-manifest.json` too, so the guarantee is only that the
committed manifest is CI-verified (scripts/check.py runs
`scripts/hook_manifest.py --check`) and any drift is therefore auditable in the
reviewable diff — the same claim class as the merge bar's checksum step, never a
guarantee that a guard cannot be edited.

Stdlib-only (portability_check runs it under a scrubbed, harness-free env, so
this locates its manifest from `__file__`, never from `${CLAUDE_PLUGIN_ROOT}`).
"""
import hashlib
import json
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = HOOKS_DIR / "integrity-manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tracked(hooks_dir: Path) -> list:
    """Every `*.py` plus `hooks.json` in *hooks_dir* (sorted by basename) — the
    exact set scripts/hook_manifest.py records. Keep the two selection rules
    identical so the runtime and commit-time checks agree on the file set."""
    files = [p for p in hooks_dir.glob("*.py")
             if p.is_file() and "__pycache__" not in p.parts]
    hooks_json = hooks_dir / "hooks.json"
    if hooks_json.is_file():
        files.append(hooks_json)
    return sorted(files, key=lambda p: p.name)


def _compute(hooks_dir: Path) -> dict:
    out = {}
    for p in _tracked(hooks_dir):
        try:
            out[p.name] = _sha256(p)
        except OSError:
            continue
    return out


def drift(hooks_dir: Path, manifest_path: Path):
    """(status, messages).

    status is 'clean' | 'drift' | 'no-manifest'. Any read/parse failure of the
    manifest yields 'no-manifest' (degrade loudly, never crash)."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        recorded = manifest["hooks"]
        if not isinstance(recorded, dict):
            raise ValueError("no 'hooks' object")
    except (OSError, ValueError, KeyError, TypeError):
        return "no-manifest", []
    actual = _compute(hooks_dir)
    messages = []
    for name in sorted(set(recorded) | set(actual)):
        if name not in actual:
            messages.append(f"{name} (recorded in manifest, missing on disk)")
        elif name not in recorded:
            messages.append(f"{name} (present on disk, absent from manifest)")
        elif recorded[name] != actual[name]:
            messages.append(f"{name} (sha256 differs from manifest)")
    return ("drift" if messages else "clean"), messages


def _emit(warning: str) -> None:
    """Surface *warning* both to the user (stderr) and into the session context
    (SessionStart additionalContext). Never blocks — the caller exits 0."""
    sys.stderr.write(warning + "\n")
    try:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": warning,
            }
        }))
    except (OSError, ValueError):
        pass


def main() -> None:
    # SessionStart passes JSON on stdin; we don't need it, but drain it so a
    # closed/empty pipe never errors. Best-effort.
    try:
        sys.stdin.read()
    except (OSError, ValueError):
        pass
    status, messages = drift(HOOKS_DIR, MANIFEST_PATH)
    if status == "clean":
        return  # silent — the common path
    if status == "no-manifest":
        _emit("[hook-integrity] WARNING: the hook self-integrity manifest "
              f"({MANIFEST_PATH.name}) is missing or unreadable — hook tampering "
              "cannot be detected this session. Restore it with "
              "`python3 scripts/hook_manifest.py --write`.")
        return
    _emit("[hook-integrity] WARNING: one or more core-engineering hooks differ "
          "from the shipped manifest — a guard may have been modified in this "
          "session. Drifted: " + "; ".join(messages) + ". If this edit is "
          "intentional, refresh the manifest with "
          "`python3 scripts/hook_manifest.py --write`.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never raises: a failed self-check must not cost a session.
        pass
    sys.exit(0)
