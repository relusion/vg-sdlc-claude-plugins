"""Behavioral tests for plugins/core-engineering/mcp/gate_server.py.

The server is driven exactly as an MCP host drives it: as a subprocess over
real stdio, fed newline-delimited JSON-RPC 2.0 messages, its stdout parsed back
line by line. Nothing is imported — the server is proven to run standalone
(`python3 gate_server.py`), the portability contract every shipped script owns.

Offline: the git-mode tools reuse the implementation-ready-feature eval fixture
as a stand-in adopter repo (git-init + one commit), the same pattern
test_gate_runner.py uses.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "core-engineering"
SERVER = PLUGIN / "mcp" / "gate_server.py"
RUNNER = REPO / "scripts" / "gate_runner.py"
POLICY = PLUGIN / "merge-policy.json"
FIXTURE = REPO / "evals" / "fixtures" / "implementation-ready-feature"
FIXTURE_SPEC = (FIXTURE / "docs" / "plans" / "team-invitations"
                / "specs" / "01-invite-user")

EXPECTED_TOOLS = {"merge_bar", "spec_lint", "test_guard", "dep_guard"}

GIT_ENV = dict(
    os.environ,
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)

# test-guard's default test-file heuristic wants a conventionally-named test file
# (the fixture's checks/*_check.py layout does not match) — mirrors
# test_gate_runner.py so the adopter copy is a realistic merge-bar target.
TEST_FILE_REL = "tests/test_invitations.py"
TEST_FILE_BODY = (
    "from src.invitations import create_invitation\n\n\n"
    "def test_create_invitation_returns_token():\n"
    "    inv = create_invitation('a@example.com', 'admin')\n"
    "    assert inv['token']\n"
    "    assert inv['email'] == 'a@example.com'\n"
)


def _make_adopter_repo(tmpdir):
    """Fixture copy + conventional test file + git init/commit -> (repo, base)."""
    repo = Path(tmpdir) / "repo"
    shutil.copytree(FIXTURE, repo,
                    ignore=shutil.ignore_patterns("__pycache__"))
    test_file = repo / TEST_FILE_REL
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(TEST_FILE_BODY, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"],
                   check=True, capture_output=True, env=GIT_ENV, timeout=60)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                    "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                    "add", "-A"],
                   check=True, capture_output=True, env=GIT_ENV, timeout=60)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                    "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                    "commit", "-q", "-m", "base"],
                   check=True, capture_output=True, env=GIT_ENV, timeout=60)
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, env=GIT_ENV, timeout=60,
    ).stdout.strip()
    return repo, base


def _drive(messages):
    """Feed a list of JSON-RPC message dicts to the server over stdio; return
    (responses_by_id, exit_code). Notifications (no `id`) draw no response."""
    payload = "".join(json.dumps(m) + "\n" for m in messages)
    proc = subprocess.run(
        [sys.executable, str(SERVER)],
        input=payload, capture_output=True, text=True, timeout=180,
    )
    responses = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        responses[obj.get("id")] = obj
    return responses, proc.returncode, proc.stderr


def _init():
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}


def _call(msg_id, name, arguments):
    return {"jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}


def _tool_payload(response):
    """Unwrap a tools/call result -> the parsed text content object."""
    result = response["result"]
    return json.loads(result["content"][0]["text"]), result.get("isError", False)


_TMP_RE = re.compile(r"/tmp/gate-runner-specs-[^/\"]+")


def _normalize_verdict(verdict):
    """Project out the two fields that legitimately differ between the server's
    fork-copy invocation and a canonical-CLI invocation, leaving the substantive
    verdict for equality:

      * the runner materializes the head tree into a FRESH TemporaryDirectory
        each run, so `gate-runner-specs-XXXX` paths differ between ANY two
        invocations (CLI vs CLI too) — nondeterminism of the runner, not the MCP
        wrapper;
      * `policy.shipped_default` is True only when the runner recognizes the
        --policy as its OWN DEFAULT_POLICY; the fork copy's DEFAULT_POLICY
        mis-resolves from mcp/, so it honestly reports False — the documented
        reason the server passes explicit --policy/--plugin-root.
    """
    text = _TMP_RE.sub("<tmp>", json.dumps(verdict))
    out = json.loads(text)
    if isinstance(out.get("policy"), dict):
        out["policy"].pop("shipped_default", None)
    return out


class InitializeAndList(unittest.TestCase):
    def test_initialize_pins_protocol_and_serverinfo(self):
        responses, code, err = _drive([_init()])
        self.assertEqual(code, 0, err)
        result = responses[1]["result"]
        self.assertIn("protocolVersion", result)
        self.assertEqual(result["serverInfo"]["name"], "gate-runner")
        self.assertIn("tools", result["capabilities"])

    def test_tools_list_returns_the_four_tools(self):
        msgs = [
            _init(),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        responses, code, err = _drive(msgs)
        self.assertEqual(code, 0, err)
        # The notification (no id) must NOT have drawn a response.
        self.assertNotIn(None, responses)
        tools = responses[2]["result"]["tools"]
        self.assertEqual({t["name"] for t in tools}, EXPECTED_TOOLS)
        for t in tools:
            self.assertIn("inputSchema", t)
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertIn("required", t["inputSchema"])

    def test_bare_session_lists_tools(self):
        """The done-when: a bare `python3 gate_server.py` session lists tools."""
        responses, code, _ = _drive(
            [{"jsonrpc": "2.0", "id": 7, "method": "tools/list"}])
        self.assertEqual(code, 0)
        self.assertEqual(
            {t["name"] for t in responses[7]["result"]["tools"]}, EXPECTED_TOOLS)

    def test_empty_stdin_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, str(SERVER)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class Errors(unittest.TestCase):
    def test_unknown_method_is_jsonrpc_error(self):
        responses, _, _ = _drive(
            [{"jsonrpc": "2.0", "id": 3, "method": "no/such/method"}])
        self.assertEqual(responses[3]["error"]["code"], -32601)

    def test_unknown_tool_is_tool_error(self):
        responses, _, _ = _drive([_call(4, "not_a_tool", {})])
        payload, is_error = _tool_payload(responses[4])
        self.assertTrue(is_error)
        self.assertIn("unknown tool", payload["error"])

    def test_missing_required_arg_is_tool_error(self):
        responses, _, _ = _drive([_call(5, "merge_bar", {"repo": "/tmp"})])
        payload, is_error = _tool_payload(responses[5])
        self.assertTrue(is_error)
        self.assertIn("base", payload["error"])

    def test_nonexistent_repo_is_tool_error(self):
        responses, _, _ = _drive(
            [_call(6, "merge_bar",
                   {"repo": "/no/such/dir/xyzzy", "base": "HEAD"})])
        payload, is_error = _tool_payload(responses[6])
        self.assertTrue(is_error)
        self.assertIn("existing directory", payload["error"])

    def test_parse_error_on_garbage_line(self):
        # Not driven through _drive (which json.dumps): feed raw garbage.
        proc = subprocess.run(
            [sys.executable, str(SERVER)],
            input="this is not json\n", capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        obj = json.loads(proc.stdout.strip())
        self.assertEqual(obj["error"]["code"], -32700)


class SpecLintDispatch(unittest.TestCase):
    def test_spec_lint_on_fixture_spec_passes(self):
        self.assertTrue(FIXTURE_SPEC.is_dir(), FIXTURE_SPEC)
        responses, code, err = _drive(
            [_call(10, "spec_lint", {"spec_dir": str(FIXTURE_SPEC)})])
        self.assertEqual(code, 0, err)
        payload, is_error = _tool_payload(responses[10])
        self.assertFalse(is_error)
        self.assertEqual(payload["exit_code"], 0)
        self.assertIsInstance(payload["verdict"], dict)


@unittest.skipUnless(shutil.which("git"), "git-mode server tools need git")
class GitModeDispatch(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_merge_bar_matches_cli_verdict(self):
        """The done-when: merge_bar returns the same verdict JSON as the CLI."""
        repo, base = _make_adopter_repo(self._tmp.name)
        # CLI invocation exactly as the server builds it (explicit policy/root).
        cli = subprocess.run(
            [sys.executable, str(RUNNER), "--repo", str(repo), "--base", base,
             "--change-class", "standard", "--declared", "",
             "--policy", str(POLICY), "--plugin-root", str(PLUGIN), "--json"],
            capture_output=True, text=True, timeout=180,
        )
        cli_verdict = json.loads(cli.stdout)

        responses, code, err = _drive(
            [_call(11, "merge_bar",
                   {"repo": str(repo), "base": base,
                    "change_class": "standard", "declared": ""})])
        self.assertEqual(code, 0, err)
        payload, is_error = _tool_payload(responses[11])
        self.assertFalse(is_error)
        self.assertEqual(payload["exit_code"], cli.returncode)
        self.maxDiff = None
        self.assertEqual(_normalize_verdict(payload["verdict"]),
                         _normalize_verdict(cli_verdict))
        self.assertEqual(payload["verdict"]["status"], "pass")

    def test_dep_guard_dispatches_to_real_script(self):
        repo, base = _make_adopter_repo(self._tmp.name)
        responses, code, err = _drive(
            [_call(12, "dep_guard",
                   {"repo": str(repo), "base": base, "declared": ""})])
        self.assertEqual(code, 0, err)
        payload, is_error = _tool_payload(responses[12])
        self.assertFalse(is_error)
        self.assertIn(payload["exit_code"], (0, 1, 2))
        self.assertIsInstance(payload["verdict"], dict)

    def test_test_guard_dispatches_to_real_script(self):
        repo, base = _make_adopter_repo(self._tmp.name)
        responses, code, err = _drive(
            [_call(13, "test_guard", {"repo": str(repo), "base": base})])
        self.assertEqual(code, 0, err)
        payload, is_error = _tool_payload(responses[13])
        self.assertFalse(is_error)
        self.assertIn(payload["exit_code"], (0, 1, 2))
        self.assertIsInstance(payload["verdict"], dict)


if __name__ == "__main__":
    unittest.main()
