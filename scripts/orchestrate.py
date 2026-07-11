#!/usr/bin/env python3
"""Reference event loop for cross-agent handoffs between managed agents.

REFERENCE ONLY — replace with your firm's workflow engine (Temporal, Airflow,
Guidewire event bus). This script shows the shape of the loop, not a
production implementation.

Security note: handoff requests are surfaced in the orchestrator's text output,
which is downstream of untrusted-document readers. An attacker who controls a
processed document could embed a literal handoff_request blob that, if echoed,
would be parsed here. This script mitigates by (a) hard-allowlisting
target_agent against the deployed slugs and (b) schema-validating the payload
before steering. In production, prefer emitting handoffs via a dedicated tool
call or a typed SSE event the model cannot produce by quoting document text.
"""
import json
import os
import re
import sys

ALLOWED_TARGETS = {
    "spec-author",
    "spec-impl",
    "quality-gate",
    "release-coordinator",
}

HANDOFF_PAYLOAD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["event"],
    "properties": {
        "event": {"type": "string", "maxLength": 2000},
        "context_ref": {"type": "string", "maxLength": 256,
                        "pattern": r"^[A-Za-z0-9 ._/:#-]+$"},
    },
}

HANDOFF_ANCHOR = re.compile(r'\{"type":\s*"handoff_request"')
CONTEXT_REF_RE = re.compile(HANDOFF_PAYLOAD_SCHEMA["properties"]["context_ref"]["pattern"])


def _balanced_object(text: str, start: int) -> str | None:
    """Return the complete JSON object opening at text[start], or None if its
    braces never balance. A lazy-regex match would stop at the FIRST `}`, which
    truncates any handoff whose payload is itself an object — so braces are
    counted, skipping over string literals (and their escapes)."""
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_handoff(text: str) -> dict | None:
    m = HANDOFF_ANCHOR.search(text)
    if not m:
        return None
    blob = _balanced_object(text, m.start())
    if blob is None:
        return None
    try:
        obj = json.loads(blob)
    except json.JSONDecodeError:
        return None
    target = obj.get("target_agent")
    payload = obj.get("payload")
    if target not in ALLOWED_TARGETS:
        return None
    if not _valid_handoff_payload(payload):
        return None
    return {"target_agent": target, "payload": payload}


def _valid_handoff_payload(payload) -> bool:
    """Validate the deliberately tiny handoff payload schema locally.

    The standalone `scripts/validate.py` keeps the general JSON Schema
    dependency. This reference loop needs only the fixed handoff schema above,
    so a local validator keeps extraction tests runnable on bare Python.
    """
    if not isinstance(payload, dict):
        return False
    if set(payload) - {"event", "context_ref"}:
        return False
    event = payload.get("event")
    if not isinstance(event, str) or len(event) > 2000:
        return False
    if "context_ref" in payload:
        context_ref = payload["context_ref"]
        if not isinstance(context_ref, str) or len(context_ref) > 256:
            return False
        if not CONTEXT_REF_RE.fullmatch(context_ref):
            return False
    return True


def run(source_session_id: str, agent_ids: dict[str, str]) -> None:
    """agent_ids maps slug -> deployed CMA agent_id."""
    try:
        import anthropic  # SDK needed only to drive sessions, not to parse handoffs
    except ImportError:
        print(
            "ERROR: orchestrate.py run() requires 'anthropic' (pip install anthropic)",
            file=sys.stderr,
        )
        sys.exit(2)
    client = anthropic.Anthropic()
    # /v1/agents is a preview endpoint; SDK type stubs don't cover it yet.
    with client.beta.agents.sessions.stream(session_id=source_session_id) as stream:  # type: ignore[attr-defined]
        for event in stream:
            if event.type != "message_delta" or not getattr(event, "text", None):
                continue
            handoff = extract_handoff(event.text)
            if not handoff:
                continue
            target_slug = handoff["target_agent"]
            target_id = agent_ids.get(target_slug)
            if not target_id:
                continue
            client.beta.agents.sessions.steer(  # type: ignore[attr-defined]
                agent_id=target_id,
                input=handoff["payload"]["event"],
            )


if __name__ == "__main__":
    run(
        source_session_id=os.environ["SOURCE_SESSION_ID"],
        agent_ids=json.loads(os.environ.get("AGENT_IDS", "{}")),
    )
