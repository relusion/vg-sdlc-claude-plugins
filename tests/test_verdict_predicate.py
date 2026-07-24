"""Offline tests for scripts/verdict_predicate.py — the signed-verdict predicate
transform.

Proves the whole contract without a network or Claude: the predicate round-trips
from a REAL gate_runner verdict (built by git-init-ing the shipped fixture and
running the runner as a subprocess, so a verdict-field rename would break this
test, not slip through), carries EXACTLY the whitelisted fields (nothing
model-derived and no local filesystem path leaks), projects gates[] to the three
key subset in order, and honors the 0/2 exit contract (a malformed verdict —
non-JSON, non-object, a missing whitelisted field, or an un-projectable gates
entry — exits 2, never a fake gate FAIL).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "verdict_predicate.py"
RUNNER = REPO / "scripts" / "gate_runner.py"
PLUGIN = REPO / "plugins" / "core-engineering"
FIXTURE = REPO / "evals" / "fixtures" / "implementation-ready-feature"

TEST_BODY = (
    "from src.invitations import create_invitation\n\n\n"
    "def test_create_invitation_returns_token():\n"
    "    inv = create_invitation('a@example.com', 'admin')\n"
    "    assert inv['token']\n"
    "    assert inv['email'] == 'a@example.com'\n"
)

WHITELIST = {
    "base_sha", "head_sha", "policy_sha256", "status", "change_class",
    "change_class_source", "validity_required", "gates",
}
GATE_KEYS = {"id", "disposition", "status"}

sys.path.insert(0, str(REPO / "scripts"))
import verdict_predicate  # noqa: E402


def run(args, stdin_text=None):
    """Run the script as a subprocess -> (returncode, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin_text, capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def build_real_verdict(tmp: Path) -> dict:
    """Git-init a copy of the shipped fixture with an honest test and run the
    real gate_runner to produce a genuine verdict object."""
    demo = tmp / "adopter-repo"
    subprocess.run(["cp", "-R", str(FIXTURE), str(demo)], check=True)
    (demo / "tests").mkdir(exist_ok=True)
    (demo / "tests" / "test_invitations.py").write_text(TEST_BODY, encoding="utf-8")
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null",
               GIT_CONFIG_SYSTEM="/dev/null")

    def g(*a):
        subprocess.run(
            ["git", "-C", str(demo), "-c", "user.name=t",
             "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *a],
            check=True, capture_output=True, env=env)

    subprocess.run(["git", "-C", str(demo), "init", "-q", "-b", "main"],
                   check=True, capture_output=True, env=env)
    g("add", "-A")
    g("commit", "-qm", "base: honest feature with a real test")
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "--repo", str(demo), "--base", "HEAD",
         "--change-class", "standard", "--declared", "",
         "--plugin-root", str(PLUGIN), "--json"],
        capture_output=True, text=True, timeout=180, env=env)
    return json.loads(proc.stdout)


class RealVerdictRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.verdict = build_real_verdict(Path(cls._tmp.name))
        if cls.verdict["status"] != "pass":
            raise AssertionError(
                f"implementation-ready fixture produced a non-green verdict: "
                f"{cls.verdict['hard_failures']}"
            )

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_predicate_has_exactly_the_whitelist(self):
        pred = verdict_predicate.build_predicate(self.verdict)
        self.assertEqual(set(pred), WHITELIST)
        # The single source PREDICATE_KEYS agrees with the observed keys.
        self.assertEqual(set(verdict_predicate.PREDICATE_KEYS), WHITELIST)

    def test_values_match_the_source_verdict(self):
        pred = verdict_predicate.build_predicate(self.verdict)
        self.assertEqual(pred["base_sha"], self.verdict["base_sha"])
        self.assertEqual(pred["head_sha"], self.verdict["head_sha"])
        # The ONE nested projection: policy_sha256 <- verdict['policy']['sha256'].
        self.assertEqual(pred["policy_sha256"], self.verdict["policy"]["sha256"])
        for f in ("status", "change_class", "change_class_source",
                  "validity_required"):
            self.assertEqual(pred[f], self.verdict[f])

    def test_gates_projected_to_three_keys_in_order(self):
        pred = verdict_predicate.build_predicate(self.verdict)
        self.assertEqual(len(pred["gates"]), len(self.verdict["gates"]))
        for got, src in zip(pred["gates"], self.verdict["gates"]):
            self.assertEqual(set(got), GATE_KEYS)
            self.assertEqual(got["id"], src["id"])
            self.assertEqual(got["disposition"], src["disposition"])
            self.assertEqual(got["status"], src["status"])

    def test_nothing_model_derived_or_path_bearing_leaks(self):
        """The verdict carries local paths (policy.path, repo) and free prose
        (summary, advisory, hard_failures, proves, run argv) — none may enter
        the signed predicate."""
        pred = verdict_predicate.build_predicate(self.verdict)
        for leaked in ("policy", "repo", "summary", "advisory", "hard_failures",
                       "base", "head", "change_class_matched_paths",
                       "schema_version"):
            self.assertNotIn(leaked, pred, f"{leaked!r} leaked into predicate")
        for gate in pred["gates"]:
            self.assertNotIn("proves", gate)
            self.assertNotIn("runs", gate)
        # Belt and suspenders: no absolute filesystem path anywhere in the JSON.
        self.assertNotIn(str(REPO), json.dumps(pred))

    def test_subprocess_in_flag_exit_0(self):
        with tempfile.TemporaryDirectory() as d:
            vpath = Path(d) / "merge-verdict.json"
            vpath.write_text(json.dumps(self.verdict), encoding="utf-8")
            rc, out, _ = run(["--in", str(vpath)])
            self.assertEqual(rc, 0)
            self.assertEqual(set(json.loads(out)), WHITELIST)

    def test_subprocess_stdin_and_out_flag(self):
        with tempfile.TemporaryDirectory() as d:
            outp = Path(d) / "predicate.json"
            rc, out, _ = run(["--out", str(outp)],
                             stdin_text=json.dumps(self.verdict))
            self.assertEqual(rc, 0)
            self.assertEqual(out, "")  # nothing on stdout when --out is given
            self.assertEqual(set(json.loads(outp.read_text())), WHITELIST)


class MalformedInputs(unittest.TestCase):
    def test_not_json_exit_2(self):
        rc, _, err = run([], stdin_text="not json at all")
        self.assertEqual(rc, 2)
        self.assertIn("not valid JSON", err)

    def test_top_level_not_object_exit_2(self):
        rc, _, _ = run([], stdin_text="[]")
        self.assertEqual(rc, 2)
        rc, _, _ = run([], stdin_text='"a string"')
        self.assertEqual(rc, 2)

    def test_missing_scalar_field_exit_2(self):
        # A gate_runner runner-error verdict has this exact shape and must NOT
        # be signable — it lacks base_sha and the rest.
        rc, _, err = run([], stdin_text='{"status": "error", "message": "boom"}')
        self.assertEqual(rc, 2)
        self.assertIn("base_sha", err)

    def test_missing_policy_sha256_exit_2(self):
        v = {"base_sha": "a", "head_sha": "b", "status": "pass",
             "change_class": "standard", "change_class_source": "explicit",
             "validity_required": "human", "gates": []}
        rc, _, err = run([], stdin_text=json.dumps(v))
        self.assertEqual(rc, 2)
        self.assertIn("policy", err)

    def test_gates_not_a_list_exit_2(self):
        v = {"base_sha": "a", "head_sha": "b", "policy": {"sha256": "z"},
             "status": "pass", "change_class": "standard",
             "change_class_source": "explicit", "validity_required": "human",
             "gates": {"not": "a list"}}
        rc, _, err = run([], stdin_text=json.dumps(v))
        self.assertEqual(rc, 2)
        self.assertIn("gates", err)

    def test_gate_entry_missing_keys_exit_2(self):
        v = {"base_sha": "a", "head_sha": "b", "policy": {"sha256": "z"},
             "status": "pass", "change_class": "standard",
             "change_class_source": "explicit", "validity_required": "human",
             "gates": [{"id": "spec-lint", "status": "pass"}]}  # no disposition
        rc, _, err = run([], stdin_text=json.dumps(v))
        self.assertEqual(rc, 2)
        self.assertIn("disposition", err)

    def test_unreadable_in_path_exit_2(self):
        rc, _, err = run(["--in", "/no/such/verdict.json"])
        self.assertEqual(rc, 2)
        self.assertIn("cannot read", err)


class MinimalWellFormedVerdict(unittest.TestCase):
    """A hand-built minimal verdict (no git needed) exercises the happy path and
    the gate projection independently of the runner."""

    VERDICT = {
        "status": "pass",
        "schema_version": 1,
        "change_class": "standard",
        "change_class_source": "rule:0",
        "change_class_matched_paths": ["auth/login.py"],
        "validity_required": "two-human",
        "base": "origin/main",
        "head": "HEAD",
        "base_sha": "1111111111111111111111111111111111111111",
        "head_sha": "2222222222222222222222222222222222222222",
        "repo": "/home/someone/secret-repo",
        "policy": {"path": "/tmp/merge-policy.json",
                   "sha256": "deadbeef", "shipped_default": False},
        "gates": [
            {"id": "spec-lint", "disposition": "required", "status": "pass",
             "proves": "traceability", "runs": [{"args": ["/abs/path"]}]},
            {"id": "test-guard", "disposition": "required", "status": "fail",
             "proves": "no weakened tests", "runs": []},
        ],
        "hard_failures": ["test-guard: gutted"],
        "advisory": [],
        "summary": "1/2 required gates pass",
    }

    def test_projection_and_no_leak(self):
        pred = verdict_predicate.build_predicate(self.VERDICT)
        self.assertEqual(set(pred), WHITELIST)
        self.assertEqual(pred["policy_sha256"], "deadbeef")
        self.assertEqual(pred["change_class_source"], "rule:0")
        self.assertEqual(pred["validity_required"], "two-human")
        # matched paths (auth/login.py) and the local repo path must NOT leak.
        self.assertNotIn("auth/login.py", json.dumps(pred))
        self.assertNotIn("secret-repo", json.dumps(pred))
        self.assertEqual(
            pred["gates"],
            [{"id": "spec-lint", "disposition": "required", "status": "pass"},
             {"id": "test-guard", "disposition": "required", "status": "fail"}])

    def test_fail_status_still_projects(self):
        """A red verdict is a faithful projection too — signing policy (only sign
        green) lives in the workflow's `if:` guard, not in this transform."""
        v = dict(self.VERDICT, status="fail")
        pred = verdict_predicate.build_predicate(v)
        self.assertEqual(pred["status"], "fail")


if __name__ == "__main__":
    unittest.main()
