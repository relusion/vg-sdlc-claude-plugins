#!/usr/bin/env python3
"""gate_server.py — a stdlib-only stdio MCP server exposing the deterministic
merge bar and its integrity gates as MCP tools to ANY MCP-capable runtime
(Cursor, custom agents, other harnesses) without porting a single prompt.

It is a hand-rolled JSON-RPC 2.0 loop over stdin/stdout — NO MCP SDK, no
third-party dependency — so it honors the same portability guarantee every
shipped gate/hook script does (scripts/portability_check.py runs it standalone;
run with an empty stdin it reads EOF and exits 0). It implements exactly three
methods:

    initialize   -> pins a protocol version, advertises the `tools` capability
    tools/list   -> the four tools below, each with a JSON input schema
    tools/call   -> dispatches to one tool, subprocessing the REAL gate script

The four tools each wrap an existing, already-shipped gate script — the server
adds NO judgment of its own:

    merge_bar   -> scripts/gate_runner.py (the fork copy that ships INSIDE the
                   plugin at ./gate_runner.py — the repo-root canonical is never
                   installed; CLAUDE_PLUGIN_ROOT never reaches repo-root scripts)
    spec_lint   -> ../skills/ce-spec/scripts/spec-lint.py
    test_guard  -> ../skills/ce-implement/scripts/test-guard.py
    dep_guard   -> ../skills/ce-implement/scripts/dep-guard.py

Each tool returns the gate's OWN `--json` verdict VERBATIM plus the gate's exit
code, wrapped as `{"exit_code": <int>, "verdict": <the gate JSON>}` — the server
never reinterprets a verdict (a gate FAIL, exit 1, is a legitimate result, not a
tool error). A tool result is only marked `isError` when the SERVER itself could
not run the gate (bad input, unresolvable repo, spawn failure, timeout).

Hardening: every gate is invoked as an argv list — never shell=True — with the
same interpreter that runs this server; `repo`/`spec_dir` inputs must resolve to
existing directories before any subprocess is spawned; the gate scripts are
resolved by fixed relative path from this file, never from caller input.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# --- protocol identity -------------------------------------------------------
# A pinned MCP protocol version string (the stable revision this server speaks).
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "gate-runner"
SERVER_VERSION = "0.1.0"

# Generous outer bound; the runner enforces its own per-gate --gate-timeout.
GATE_SUBPROCESS_TIMEOUT = 600

# --- gate script locations (fixed relative to THIS file, never caller input) -
MCP_DIR = Path(__file__).resolve().parent          # plugins/core-engineering/mcp
PLUGIN_ROOT = MCP_DIR.parent                        # plugins/core-engineering
GATE_RUNNER = MCP_DIR / "gate_runner.py"            # the fork copy shipped in-plugin
MERGE_POLICY = PLUGIN_ROOT / "merge-policy.json"
SPEC_LINT = PLUGIN_ROOT / "skills" / "ce-spec" / "scripts" / "spec-lint.py"
TEST_GUARD = PLUGIN_ROOT / "skills" / "ce-implement" / "scripts" / "test-guard.py"
DEP_GUARD = PLUGIN_ROOT / "skills" / "ce-implement" / "scripts" / "dep-guard.py"


# --- error taxonomy ----------------------------------------------------------
class ToolError(Exception):
    """A tool could not run on this input -> an isError tool result (not a
    JSON-RPC protocol error): the model should see it and can correct."""


class MethodNotFound(Exception):
    """An unknown JSON-RPC method -> a -32601 error response."""


# --- input hardening ---------------------------------------------------------
def _require_str(arguments: dict, key: str) -> str:
    val = arguments.get(key)
    if not isinstance(val, str) or not val:
        raise ToolError(f"{key!r} is required and must be a non-empty string")
    return val


def _require_dir(arguments: dict, key: str) -> Path:
    raw = _require_str(arguments, key)
    p = Path(raw).expanduser()
    if not p.is_dir():
        raise ToolError(f"{key!r} must resolve to an existing directory: {raw}")
    return p.resolve()


def _opt_str(arguments: dict, key: str):
    val = arguments.get(key)
    if val is None:
        return None
    if not isinstance(val, str):
        raise ToolError(f"{key!r} must be a string")
    return val


# --- gate invocation ---------------------------------------------------------
def _run_gate(argv: list) -> dict:
    """Run a gate as an argv list (no shell) and wrap its verbatim verdict.

    Returns `{"exit_code": <int>, "verdict": <parsed gate JSON>}`. If the gate's
    stdout is not JSON (a crash before it could emit its verdict), the raw text
    is preserved under `raw_stdout` and `verdict` is null — the server still
    reports the exit code rather than inventing a verdict.
    """
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=GATE_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise ToolError(f"gate timed out after {GATE_SUBPROCESS_TIMEOUT}s")
    except OSError as exc:
        raise ToolError(f"could not execute gate: {exc}")

    payload: dict = {"exit_code": proc.returncode}
    out = proc.stdout or ""
    if out.strip():
        try:
            payload["verdict"] = json.loads(out)
        except json.JSONDecodeError:
            payload["verdict"] = None
            payload["raw_stdout"] = out
    else:
        payload["verdict"] = None
    if (proc.stderr or "").strip():
        payload["stderr"] = proc.stderr
    return payload


# --- the four tools ----------------------------------------------------------
def _tool_merge_bar(arguments: dict) -> dict:
    repo = _require_dir(arguments, "repo")
    base = _require_str(arguments, "base")
    argv = [
        sys.executable, str(GATE_RUNNER),
        "--repo", str(repo),
        "--base", base,
        "--policy", str(MERGE_POLICY),
        "--plugin-root", str(PLUGIN_ROOT),
        "--json",
    ]
    head = _opt_str(arguments, "head")
    if head:
        argv += ["--head", head]
    change_class = _opt_str(arguments, "change_class")
    if change_class:
        argv += ["--change-class", change_class]
    declared = _opt_str(arguments, "declared")
    if declared is not None:
        argv += ["--declared", declared]
    return _run_gate(argv)


def _tool_spec_lint(arguments: dict) -> dict:
    spec_dir = _require_dir(arguments, "spec_dir")
    argv = [sys.executable, str(SPEC_LINT), str(spec_dir), "--json"]
    threat_ids = _opt_str(arguments, "threat_ids")
    if threat_ids:
        argv += ["--threat-ids", threat_ids]
    return _run_gate(argv)


def _tool_test_guard(arguments: dict) -> dict:
    repo = _require_dir(arguments, "repo")
    base = _require_str(arguments, "base")
    argv = [
        sys.executable, str(TEST_GUARD),
        "--base", base,
        "--repo", str(repo),
        "--json",
    ]
    head = _opt_str(arguments, "head")
    if head:
        argv += ["--head", head]
    spec_dir = _opt_str(arguments, "spec_dir")
    if spec_dir:
        argv += ["--spec-dir", spec_dir]
    return _run_gate(argv)


def _tool_dep_guard(arguments: dict) -> dict:
    repo = _require_dir(arguments, "repo")
    base = _require_str(arguments, "base")
    argv = [
        sys.executable, str(DEP_GUARD),
        "--base", base,
        "--repo", str(repo),
        "--json",
    ]
    head = _opt_str(arguments, "head")
    if head:
        argv += ["--head", head]
    declared = _opt_str(arguments, "declared")
    if declared is not None:
        argv += ["--declared", declared]
    return _run_gate(argv)


HANDLERS = {
    "merge_bar": _tool_merge_bar,
    "spec_lint": _tool_spec_lint,
    "test_guard": _tool_test_guard,
    "dep_guard": _tool_dep_guard,
}

TOOLS = [
    {
        "name": "merge_bar",
        "description": (
            "Run the deterministic merge bar (gate_runner) over a committed "
            "diff: the selected change class's required integrity gates "
            "(spec-lint, test-guard, dep-guard). Returns the runner's JSON "
            "verdict verbatim plus its exit code (0 pass / 1 fail-closed / "
            "2 runner error). Judges COMMITTED state only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "path to the target repository root",
                },
                "base": {
                    "type": "string",
                    "description": "committed baseline ref the diff gates compare against",
                },
                "head": {
                    "type": "string",
                    "description": "head ref (default: HEAD)",
                },
                "change_class": {
                    "type": "string",
                    "description": "policy change class; omitted -> auto-classify "
                                   "from the diff, else the fail-safe defaults bar",
                },
                "declared": {
                    "type": "string",
                    "description": "comma-separated deps declared/verified this "
                                   "change; '' (default) means every new dep is undeclared",
                },
            },
            "required": ["repo", "base"],
        },
    },
    {
        "name": "spec_lint",
        "description": (
            "Referential-integrity hard lint (H1-H4) for ONE feature spec "
            "directory (spec.md + tasks.json). Returns the gate's JSON verdict "
            "verbatim plus its exit code (0 pass / 1 violation / 2 could-not-run)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec_dir": {
                    "type": "string",
                    "description": "path to the feature spec directory to lint",
                },
                "threat_ids": {
                    "type": "string",
                    "description": "comma-separated TZ-NNN this feature must cover (H5)",
                },
            },
            "required": ["spec_dir"],
        },
    },
    {
        "name": "test_guard",
        "description": (
            "On-disk gate against agent-weakened tests, git-diff mode: compares "
            "test files between base and head. Returns the gate's JSON verdict "
            "verbatim plus its exit code."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "path to the target repository root",
                },
                "base": {
                    "type": "string",
                    "description": "committed baseline ref to diff test files against",
                },
                "head": {
                    "type": "string",
                    "description": "head ref (default: the working tree)",
                },
                "spec_dir": {
                    "type": "string",
                    "description": "optional spec dir for acceptance-criteria labeling",
                },
            },
            "required": ["repo", "base"],
        },
    },
    {
        "name": "dep_guard",
        "description": (
            "On-disk gate against hallucinated / slopsquatted dependencies: "
            "diffs manifests between base and head. Returns the gate's JSON "
            "verdict verbatim plus its exit code."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "path to the target repository root",
                },
                "base": {
                    "type": "string",
                    "description": "committed baseline ref to diff manifests against",
                },
                "head": {
                    "type": "string",
                    "description": "head ref (default: the working tree)",
                },
                "declared": {
                    "type": "string",
                    "description": "comma-separated deps verified this change; '' "
                                   "(default) means every new dep is undeclared",
                },
            },
            "required": ["repo", "base"],
        },
    },
]


# --- tools/call --------------------------------------------------------------
def _text_result(obj: dict, *, is_error: bool) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(obj, indent=2)}],
        "isError": is_error,
    }


def handle_tools_call(params: dict) -> dict:
    if not isinstance(params, dict):
        return _text_result({"error": "params must be an object"}, is_error=True)
    name = params.get("name")
    arguments = params.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return _text_result({"error": "'arguments' must be an object"}, is_error=True)
    handler = HANDLERS.get(name)
    if handler is None:
        return _text_result({"error": f"unknown tool: {name!r}"}, is_error=True)
    try:
        payload = handler(arguments)
    except ToolError as exc:
        return _text_result({"error": str(exc)}, is_error=True)
    return _text_result(payload, is_error=False)


# --- JSON-RPC dispatch -------------------------------------------------------
def dispatch(method: str, params):
    if method == "initialize":
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        return handle_tools_call(params or {})
    if method == "ping":
        return {}
    raise MethodNotFound(method)


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _send_result(msg_id, result) -> None:
    _send({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _send_error(msg_id, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


def main() -> int:
    """Read newline-delimited JSON-RPC messages until EOF. Notifications (no
    `id`) never draw a response — including EOF/empty stdin, which just ends the
    loop with exit 0 (the standalone contract portability_check depends on)."""
    for raw in iter(sys.stdin.readline, ""):
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _send_error(None, -32700, "parse error")
            continue
        if not isinstance(msg, dict):
            _send_error(None, -32600, "invalid request: not a JSON object")
            continue
        is_notification = "id" not in msg
        msg_id = msg.get("id")
        method = msg.get("method")
        if not isinstance(method, str):
            if not is_notification:
                _send_error(msg_id, -32600, "invalid request: missing 'method'")
            continue
        try:
            result = dispatch(method, msg.get("params"))
        except MethodNotFound:
            if not is_notification:
                _send_error(msg_id, -32601, f"method not found: {method}")
            continue
        except Exception as exc:  # noqa: BLE001 — never crash the loop on one msg
            if not is_notification:
                _send_error(msg_id, -32603, f"internal error: {type(exc).__name__}: {exc}")
            continue
        if not is_notification:
            _send_result(msg_id, result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 — could-not-run is 2, never a fake crash
        print(f"gate_server: unexpected error: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        sys.exit(2)
