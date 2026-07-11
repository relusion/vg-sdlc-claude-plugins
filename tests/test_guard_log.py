"""Tests for hooks/guard_log.py — the shared tamper-evident guard-log writer.

Covers the append_entry contract (all fields, genesis prev, forward chaining,
payload binding, never-raises) and the --verify CLI (valid chain exits 0; edit /
deletion / reorder each exit 1; missing file exits 2; empty file exits 0;
no-args exits 2 — the portability 0/1/2 contract).

The `VerifyKnownLimitations` class ENCODES what --verify cannot do, so nobody
later mistakes it for adversary-proof: because the chain is an unkeyed public
sha256, a write-capable actor who re-chains downstream `prev` values after an
edit, or who re-genesises the whole file, still passes --verify (exit 0); an
empty or single-genesis-line file passes too. Those tests pin the bypasses as
KNOWN and route the real detection through the out-of-band chain-head + entry-
count comparison a retained prior pack performs (demonstrated for tail-
truncation and re-genesis).
"""

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/hooks/guard_log.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("guard_log_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard_log = _load_module()

LOG_REL = Path(".claude") / "ce-guard-log.jsonl"
FIELDS = ("ts", "guard", "decision", "reason", "session_id", "tool",
          "hook_event", "payload_sha256", "prev")


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=60,
    )


def _chain_head(path):
    """Mirror evidence-pack.guard_section's out-of-band anchor: (sha256-hex of
    the last non-empty raw line, count of non-empty lines) — the {chain_head,
    entry_count} an independent party retains and later compares. This is what
    catches the tampers --verify alone cannot."""
    raw = [ln for ln in Path(path).read_text(encoding="utf-8").splitlines()
           if ln.strip()]
    if not raw:
        return (None, 0)
    return (hashlib.sha256(raw[-1].encode("utf-8")).hexdigest(), len(raw))


def _rechain_from(lines, start):
    """Recompute each line's `prev` from index `start` forward so the chain
    stays internally consistent after an in-place edit — the trivial forward
    re-chaining a write-capable adversary performs (the chain is unkeyed and
    its algorithm is public)."""
    for j in range(start, len(lines)):
        obj = json.loads(lines[j])
        obj["prev"] = "" if j == 0 else hashlib.sha256(
            lines[j - 1].encode("utf-8")).hexdigest()
        lines[j] = json.dumps(obj, sort_keys=True)
    return lines


class AppendEntry(unittest.TestCase):
    def test_first_entry_has_genesis_prev_and_all_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guard_log.append_entry(
                root, "git-guard", "ask", "reason one",
                {"command": "git push"}, session_id="s1", tool="Bash")
            entry = json.loads((root / LOG_REL).read_text().splitlines()[0])
            for key in FIELDS:
                self.assertIn(key, entry, key)
            self.assertEqual(entry["prev"], "")  # genesis
            self.assertEqual(entry["guard"], "git-guard")
            self.assertEqual(entry["decision"], "ask")
            self.assertEqual(entry["session_id"], "s1")
            self.assertEqual(entry["tool"], "Bash")
            self.assertEqual(entry["hook_event"], "PreToolUse")
            self.assertEqual(len(entry["payload_sha256"]), 64)

    def test_payload_hash_is_canonical_and_order_independent(self):
        expect = hashlib.sha256(
            json.dumps({"a": 1, "b": 2}, sort_keys=True).encode()).hexdigest()
        self.assertEqual(guard_log.payload_hash({"b": 2, "a": 1}), expect)
        self.assertEqual(guard_log.payload_hash({"a": 1, "b": 2}), expect)

    def test_second_entry_chains_to_the_first_raw_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guard_log.append_entry(root, "git-guard", "ask", "r1", {"x": 1})
            guard_log.append_entry(root, "env-guard", "deny", "r2", {"x": 2})
            lines = (root / LOG_REL).read_text().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(
                json.loads(lines[1])["prev"],
                hashlib.sha256(lines[0].encode()).hexdigest())

    def test_append_entry_never_raises_when_root_is_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "not-a-dir"
            blocker.write_text("x", encoding="utf-8")
            try:
                guard_log.append_entry(blocker, "git-guard", "ask", "r", {})
            except Exception as exc:  # noqa: BLE001
                self.fail(f"append_entry raised instead of swallowing: {exc!r}")


class Verify(unittest.TestCase):
    def _make_log(self, root, n=3):
        for i in range(n):
            guard_log.append_entry(root, "git-guard", "ask", f"r{i}", {"i": i})
        return root / LOG_REL

    def test_valid_chain_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._make_log(Path(tmp))
            res = run_cli("--verify", str(log))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("chain valid", res.stdout)

    def test_edited_middle_line_breaks_chain_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._make_log(Path(tmp))
            lines = log.read_text().splitlines()
            obj = json.loads(lines[1])
            obj["reason"] = "TAMPERED"
            lines[1] = json.dumps(obj, sort_keys=True)
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
            res = run_cli("--verify", str(log))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("chain broken", res.stderr)

    def test_deleted_line_breaks_chain_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._make_log(Path(tmp))
            lines = log.read_text().splitlines()
            del lines[1]
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
            res = run_cli("--verify", str(log))
            self.assertEqual(res.returncode, 1, res.stdout)

    def test_reordered_lines_break_chain_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._make_log(Path(tmp))
            lines = log.read_text().splitlines()
            lines[1], lines[2] = lines[2], lines[1]
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
            res = run_cli("--verify", str(log))
            self.assertEqual(res.returncode, 1, res.stdout)

    def test_non_json_line_is_unverifiable_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._make_log(Path(tmp), n=1)
            with log.open("a", encoding="utf-8") as fh:
                fh.write("this is not json\n")
            res = run_cli("--verify", str(log))
            self.assertEqual(res.returncode, 1, res.stdout)

    def test_missing_file_is_could_not_run_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_cli("--verify", str(Path(tmp) / "nope.jsonl"))
            self.assertEqual(res.returncode, 2, res.stdout)

    def test_empty_file_is_vacuously_valid_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "empty.jsonl"
            log.write_text("", encoding="utf-8")
            res = run_cli("--verify", str(log))
            self.assertEqual(res.returncode, 0, res.stderr)

    def test_no_args_prints_usage_and_exits_2(self):
        res = run_cli()
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn("--verify", res.stderr)


class VerifyKnownLimitations(unittest.TestCase):
    """--verify proves INTERNAL consistency only. These tests pin the bypasses
    an unkeyed public chain cannot close, so a future reader does not mistake a
    passing --verify for adversary-proof history. Real detection is the
    out-of-band {chain_head, entry_count} comparison (also exercised here)."""

    def _build(self, root, decisions):
        for i, dec in enumerate(decisions):
            guard_log.append_entry(root, "git-guard", dec, f"r{i}", {"i": i})
        return root / LOG_REL

    def test_rechained_middle_edit_passes_verify(self):
        # KNOWN LIMITATION (finding 8): an actor with write access forges a
        # DENY -> ALLOW on a middle line, then recomputes every downstream
        # `prev`. The re-chained file is internally consistent, so --verify
        # returns 0 with the forged 'allow' in place. This is NOT desired
        # behavior — it documents why --verify alone is corruption-evidence,
        # not adversary-evidence; the external chain-head comparison is the
        # real anti-tamper mechanism.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = self._build(root, ["allow", "deny", "allow"])
            lines = log.read_text().splitlines()
            forged = json.loads(lines[1])
            self.assertEqual(forged["decision"], "deny")  # the real record
            forged["decision"] = "allow"                  # after-the-fact forge
            lines[1] = json.dumps(forged, sort_keys=True)
            _rechain_from(lines, 2)                        # re-chain downstream
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")

            res = run_cli("--verify", str(log))
            self.assertEqual(res.returncode, 0, res.stderr)  # bypass: passes
            self.assertIn("chain valid", res.stdout)
            self.assertEqual(
                json.loads(log.read_text().splitlines()[1])["decision"],
                "allow", "forged decision is on disk yet --verify passed")

    def test_wholesale_re_genesis_passes_verify_but_chain_head_collapses(self):
        # KNOWN LIMITATION (finding 9): replacing the whole file with one fresh
        # forged genesis line (prev == "") erases all history yet --verify
        # reports "chain valid — 1 entry". The retained out-of-band anchor is
        # what catches it: entry_count collapses N -> 1 and chain_head differs.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = self._build(root, ["allow", "deny", "deny"])
            prior_head, prior_count = _chain_head(log)
            self.assertEqual(prior_count, 3)

            forged = {"ts": "2026-01-01T00:00:00+00:00", "guard": "git-guard",
                      "decision": "allow", "reason": "fabricated genesis",
                      "session_id": "", "tool": "", "hook_event": "PreToolUse",
                      "payload_sha256": "0" * 64, "prev": ""}
            log.write_text(json.dumps(forged, sort_keys=True) + "\n",
                           encoding="utf-8")

            res = run_cli("--verify", str(log))
            self.assertEqual(res.returncode, 0, res.stderr)  # bypass: passes
            new_head, new_count = _chain_head(log)
            self.assertEqual(new_count, 1)                   # history erased
            self.assertNotEqual(new_count, prior_count)      # anchor catches it
            self.assertNotEqual(new_head, prior_head)

    def test_single_genesis_line_verifies_exit_0(self):
        # No genesis binding / no chain-length floor: a lone genesis line is a
        # "valid chain" (finding 9). Pins that --verify does not floor length.
        with tempfile.TemporaryDirectory() as tmp:
            log = self._build(Path(tmp), ["allow"])
            self.assertEqual(len(log.read_text().splitlines()), 1)
            res = run_cli("--verify", str(log))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("1 entry", res.stdout)

    def test_tail_truncation_passes_verify_but_chain_head_detects_it(self):
        # Tail-truncation leaves a shorter but internally consistent chain, so
        # --verify returns 0 (limitation). The genuine detection is the retained
        # {chain_head, entry_count}: both change, so an independent comparator
        # catches the dropped decisions.
        with tempfile.TemporaryDirectory() as tmp:
            log = self._build(Path(tmp), ["allow", "deny", "allow"])
            prior_head, prior_count = _chain_head(log)
            lines = log.read_text().splitlines()[:2]        # drop the last line
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")

            res = run_cli("--verify", str(log))
            self.assertEqual(res.returncode, 0, res.stderr)  # truncation passes
            new_head, new_count = _chain_head(log)
            self.assertEqual(new_count, 2)
            self.assertNotEqual(new_count, prior_count)      # anchor catches it
            self.assertNotEqual(new_head, prior_head)

    def test_naive_edit_without_rechain_is_still_caught(self):
        # The genuine detection --verify DOES keep: an edit that forgets to
        # recompute the downstream `prev` breaks the chain (exit 1). Distinct
        # from test_rechained_middle_edit_passes_verify, which re-chains.
        with tempfile.TemporaryDirectory() as tmp:
            log = self._build(Path(tmp), ["allow", "deny", "allow"])
            lines = log.read_text().splitlines()
            obj = json.loads(lines[1])
            obj["decision"] = "allow"                        # forge, no re-chain
            lines[1] = json.dumps(obj, sort_keys=True)
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")

            res = run_cli("--verify", str(log))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("chain broken", res.stderr)


if __name__ == "__main__":
    unittest.main()
