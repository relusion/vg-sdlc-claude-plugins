"""Tests for hooks/model-attest.py — the runtime model-tier attestation recorder.

model-attest is a PreToolUse *recorder*, deliberately the opposite of the guard
hooks: it emits no permission decision (so it can never bypass a sibling guard's
ask/deny), it never raises, and it writes the `.claude/ce-session-model.json`
sidecar ONLY when it actually reads a model from the session transcript tail —
so a transcript it cannot parse leaves any prior value standing rather than
nulling it. This suite locks that posture in.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/hooks/model-attest.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("model_attest", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MA = _load_module()


def write_transcript(path: Path, entries) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


def assistant(model, extra=None):
    entry = {"type": "assistant", "message": {"role": "assistant", "model": model}}
    if extra:
        entry.update(extra)
    return entry


def run_hook(payload, project_dir=None, scrub_project_dir=False):
    env = os.environ.copy()
    env.pop("CLAUDE_PROJECT_DIR", None)
    if project_dir is not None and not scrub_project_dir:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin, capture_output=True, text=True, env=env, timeout=60,
    )


def sidecar_of(root: Path):
    path = root / ".claude" / "ce-session-model.json"
    return json.loads(path.read_text()) if path.exists() else None


class LatestModelUnit(unittest.TestCase):
    """Direct unit tests of the transcript tail-scan (no subprocess)."""

    def test_most_recent_assistant_model_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp) / "transcript.jsonl"
            write_transcript(t, [
                assistant("claude-opus-4-8"),
                {"type": "user", "message": {"role": "user"}},
                assistant("claude-sonnet-4-5"),
            ])
            self.assertEqual(MA.latest_model(str(t)), "claude-sonnet-4-5")

    def test_synthetic_model_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp) / "transcript.jsonl"
            write_transcript(t, [
                assistant("claude-opus-4-8"),
                assistant("<synthetic>"),
            ])
            self.assertEqual(MA.latest_model(str(t)), "claude-opus-4-8")

    def test_top_level_model_field_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp) / "transcript.jsonl"
            write_transcript(t, [{"type": "assistant", "model": "claude-haiku-4"}])
            self.assertEqual(MA.latest_model(str(t)), "claude-haiku-4")

    def test_non_assistant_entries_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp) / "transcript.jsonl"
            write_transcript(t, [
                assistant("claude-opus-4-8"),
                {"type": "user", "message": {"role": "user", "model": "claude-haiku-4"}},
            ])
            # the user turn's stray model field must not win
            self.assertEqual(MA.latest_model(str(t)), "claude-opus-4-8")

    def test_missing_file_returns_empty(self):
        self.assertEqual(MA.latest_model("/no/such/transcript.jsonl"), "")

    def test_garbled_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp) / "transcript.jsonl"
            t.write_text('not json\n{"type":"assistant","message":{"model":"claude-opus-4-8"}}\n{oops\n',
                         encoding="utf-8")
            self.assertEqual(MA.latest_model(str(t)), "claude-opus-4-8")

    def test_partial_leading_line_from_tail_read_is_dropped(self):
        # A transcript larger than TAIL_BYTES: the tail read starts mid-file and
        # the first (partial) line must be discarded, never mis-parsed.
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp) / "transcript.jsonl"
            filler = json.dumps(assistant("claude-filler-model",
                                          {"pad": "x" * 4096}))
            lines = [filler] * 200 + [json.dumps(assistant("claude-opus-4-8"))]
            t.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.assertGreater(t.stat().st_size, MA.TAIL_BYTES)
            self.assertEqual(MA.latest_model(str(t)), "claude-opus-4-8")


class SidecarRefresh(unittest.TestCase):
    def test_records_model_session_and_ts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            t = root / "transcript.jsonl"
            write_transcript(t, [assistant("claude-opus-4-8")])
            res = run_hook({"tool_name": "Bash", "cwd": str(root),
                            "session_id": "sess-1",
                            "transcript_path": str(t),
                            "tool_input": {"command": "ls"}}, project_dir=root)
            self.assertEqual(res.returncode, 0)
            side = sidecar_of(root)
            self.assertIsNotNone(side)
            self.assertEqual(side["model"], "claude-opus-4-8")
            self.assertEqual(side["session_id"], "sess-1")
            self.assertTrue(side["ts"].endswith("Z"))

    def test_uses_payload_cwd_when_no_project_dir_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            t = root / "transcript.jsonl"
            write_transcript(t, [assistant("claude-opus-4-8")])
            res = run_hook({"tool_name": "Bash", "cwd": str(root),
                            "transcript_path": str(t),
                            "tool_input": {"command": "ls"}},
                           project_dir=root, scrub_project_dir=True)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(sidecar_of(root)["model"], "claude-opus-4-8")

    def test_never_emits_a_permission_decision(self):
        # The recorder must never print permissionDecision — an emitted "allow"
        # would bypass the sibling git/env/write-scope guards' ask/deny.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            t = root / "transcript.jsonl"
            write_transcript(t, [assistant("claude-opus-4-8")])
            res = run_hook({"tool_name": "Bash", "cwd": str(root),
                            "transcript_path": str(t),
                            "tool_input": {"command": "ls"}}, project_dir=root)
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("permissionDecision", res.stdout)
            self.assertEqual(res.stdout.strip(), "")

    def test_no_transcript_field_writes_no_sidecar_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res = run_hook({"tool_name": "Bash", "cwd": str(root),
                            "tool_input": {"command": "ls"}}, project_dir=root)
            self.assertEqual(res.returncode, 0)
            self.assertIsNone(sidecar_of(root))

    def test_missing_transcript_file_leaves_no_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res = run_hook({"tool_name": "Bash", "cwd": str(root),
                            "transcript_path": str(root / "nope.jsonl"),
                            "tool_input": {"command": "ls"}}, project_dir=root)
            self.assertEqual(res.returncode, 0)
            self.assertIsNone(sidecar_of(root))

    def test_unreadable_model_does_not_null_a_prior_sidecar(self):
        # If the transcript yields no model this call, an existing good value
        # must survive (record the absence, never overwrite with null).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude").mkdir()
            prior = {"session_id": "old", "model": "claude-opus-4-8", "ts": "2026-01-01T00:00:00Z"}
            (root / ".claude" / "ce-session-model.json").write_text(json.dumps(prior))
            empty = root / "empty.jsonl"
            empty.write_text("", encoding="utf-8")
            res = run_hook({"tool_name": "Bash", "cwd": str(root),
                            "transcript_path": str(empty),
                            "tool_input": {"command": "ls"}}, project_dir=root)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(sidecar_of(root), prior)

    def test_unparseable_stdin_exits_zero_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook("not json at all", project_dir=Path(tmp))
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Traceback", res.stderr)

    def test_empty_stdin_exits_zero(self):
        # The portability contract: empty stdin, no crash, exit in {0,1,2}.
        res = subprocess.run([sys.executable, str(SCRIPT)],
                             input="", capture_output=True, text=True, timeout=60)
        self.assertEqual(res.returncode, 0)
        self.assertNotIn("Traceback", res.stderr)


if __name__ == "__main__":
    unittest.main()
