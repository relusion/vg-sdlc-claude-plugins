#!/usr/bin/env python3
"""model-attest.py — PreToolUse attestation recorder (on `Bash`).

`model-policy.json` *declares*, per skill, which model tier a stage is supposed
to run on ("judgment/gate/escalation/evidence stages always use the strongest
model"), and `scripts/check.py` §7 lints that promise at commit time. This hook
adds the missing *runtime* leg: it records which model **actually** executed, so
the tier promise is auditable after the fact, not only lintable at commit time.

On every `Bash` PreToolUse event it:
  1. reads the hook payload's `transcript_path`;
  2. tail-scans that JSONL (a bounded read of the file's tail — O(1) in the
     transcript length, never a full parse) for the most recent assistant turn's
     `model` id;
  3. refreshes `.claude/ce-session-model.json` `{session_id, model, ts}` under the
     workspace root.

Skills then stamp that `model` id onto their gate-stage / attestation metric
lines (reading `null` when the sidecar is absent, so it records the *absence*,
never a guess), and
`/ce-retro` maps the recorded id through `model-policy.json`'s `tier_patterns` to
surface any gate stage that ran below its policy tier as an accepted degradation.

Posture — a **passive recorder**, deliberately the opposite of the guard hooks:
  - it **never blocks** — it emits no `permissionDecision`, so it can neither
    allow (which would bypass a sibling guard's `ask`/`deny`) nor block a call;
    the tool proceeds exactly as if this hook were absent;
  - it **never raises** — any error (unparseable payload, missing/short/garbled
    transcript, unwritable sidecar) is swallowed and the hook exits 0. A failure
    to attest must never cost a tool call.
It writes the sidecar **only when it actually finds a model**, so a transcript it
cannot read leaves any previously-recorded value standing rather than nulling it.

Stdlib-only (portability_check runs it under a scrubbed, harness-free env).
"""
import json
import os
import sys
from datetime import datetime, timezone

# Bounded tail read — the transcript grows without limit, but the most recent
# assistant turn is always within the last few KB, so we never read or parse the
# whole file. 256 KiB is generous headroom for a long final assistant turn.
TAIL_BYTES = 256 * 1024

# Placeholder model ids the harness injects for synthetic / system turns — never
# a real executed model, so they are skipped when scanning for the latest model.
_SKIP_MODELS = {"<synthetic>", "synthetic", ""}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tail_lines(path: str) -> list:
    """Last decoded lines of `path`, reading at most TAIL_BYTES from the end.

    If the read started mid-file, the first (possibly partial) line is dropped so
    a truncated JSON object is never mis-parsed. Returns [] on any I/O problem."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            start = max(0, size - TAIL_BYTES)
            fh.seek(start)
            chunk = fh.read()
    except OSError:
        return []
    lines = chunk.decode("utf-8", "replace").splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # drop the partial leading line
    return lines


def _model_of(obj) -> str:
    """The model id of a transcript entry, if it is an assistant turn carrying a
    real one; '' otherwise. Tolerates both the `{message:{model}}` shape and a
    top-level `model` field."""
    if not isinstance(obj, dict) or obj.get("type") != "assistant":
        return ""
    for candidate in (
        (obj.get("message") or {}).get("model") if isinstance(obj.get("message"), dict) else None,
        obj.get("model"),
    ):
        if isinstance(candidate, str) and candidate not in _SKIP_MODELS:
            return candidate
    return ""


def latest_model(transcript_path: str) -> str:
    """Most recent assistant `model` id in the transcript tail; '' if none."""
    for line in reversed(_tail_lines(transcript_path)):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        model = _model_of(obj)
        if model:
            return model
    return ""


def write_sidecar(root: str, session_id: str, model: str) -> None:
    """Atomically refresh `.claude/ce-session-model.json`. Best-effort — any I/O
    failure is the caller's to swallow (this must never cost a tool call)."""
    claude_dir = os.path.join(root, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    path = os.path.join(claude_dir, "ce-session-model.json")
    payload = {"session_id": session_id or "", "model": model, "ts": _utc_now()}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(tmp, path)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return  # no payload → nothing to attest; proceed silently (allow-through)
    if not isinstance(data, dict):
        return
    transcript_path = data.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return
    model = latest_model(transcript_path)
    if not model:
        return  # could not read a model → leave any prior sidecar standing
    root_raw = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    if not isinstance(root_raw, str) or not root_raw:
        return
    session_id = data.get("session_id") or ""
    write_sidecar(root_raw, session_id, model)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never raises: a failed attestation must never block or crash a tool call.
        pass
    sys.exit(0)
