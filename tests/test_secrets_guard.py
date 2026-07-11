"""Tests for secrets-guard.py — the diff-scoped merge-bar secret floor.

Exercised exactly as a gating caller runs it (subprocess, --json), against throwaway
git repos so base..head diffs are real, never mocked. The redaction discipline is a
first-class assertion: a raw secret value must never appear in stdout or the JSON.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-probe-infra/scripts/secrets-guard.py"

# A real, well-known AWS example key + a high-entropy token whose raw values the tests
# assert never leak. `password: changeme` is a placeholder that must NOT flag.
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
HIGH_ENTROPY = "s3cr3tR3allyH1ghEntropyV4lue99"

GIT_ENV = dict(
    os.environ,
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
    GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
    GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
)


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True, text=True, env=GIT_ENV, timeout=60)


def _sha(repo, ref="HEAD"):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", ref],
                          check=True, capture_output=True, text=True, env=GIT_ENV,
                          timeout=60).stdout.strip()


class _Repo:
    """Throwaway git repo with an empty base commit; add head commits via commit()."""
    def __init__(self):
        self.dir = tempfile.mkdtemp()
        _git(self.dir, "init", "-q", "-b", "main")
        _git(self.dir, "commit", "-q", "--allow-empty", "-m", "base")
        self.base = _sha(self.dir)

    def commit(self, files, msg="c"):
        for rel, content in files.items():
            fp = Path(self.dir) / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content)
        _git(self.dir, "add", "-A")
        _git(self.dir, "commit", "-q", "-m", msg)
        return _sha(self.dir)

    def cleanup(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)


def run_guard(repo, base, head="HEAD", *extra):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--base", base,
         "--head", head, "--json", *extra],
        capture_output=True, text=True, env=GIT_ENV, timeout=60)


LEDGER = ".merge-bar/dispositions.json"


def _ledger(*entries):
    return json.dumps({"schema_version": 1, "dispositions": list(entries)})


class SecretsGuard(unittest.TestCase):
    def setUp(self):
        self.repo = _Repo()

    def tearDown(self):
        self.repo.cleanup()

    def test_added_secret_is_found_and_redacted(self):
        head = self.repo.commit({"config.py": f'aws = "{AWS_KEY}"\napi_key = "{HIGH_ENTROPY}"\n'})
        r = run_guard(self.repo.dir, self.repo.base, head)
        self.assertEqual(r.returncode, 1, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["status"], "fail")
        types = sorted(f["type"] for f in data["findings"])
        self.assertEqual(types, ["AWS access key id", "assignment to `api_key`"])
        # Redaction: the raw values must appear NOWHERE in stdout.
        self.assertNotIn(AWS_KEY, r.stdout)
        self.assertNotIn(HIGH_ENTROPY, r.stdout)
        self.assertTrue(all("[REDACTED]" in f["excerpt"] for f in data["findings"]))
        # hard_failures carries a human-evidence line the runner renders.
        self.assertTrue(data["hard_failures"])
        self.assertTrue(any("config.py:1" in h for h in data["hard_failures"]))

    def test_placeholder_value_does_not_flag(self):
        head = self.repo.commit({"app.yml": "password: changeme\ntoken: ${VAULT_TOKEN}\n"})
        r = run_guard(self.repo.dir, self.repo.base, head)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["findings"], [])

    def test_diff_scoped_pre_existing_secret_is_not_flagged(self):
        # A secret committed in the BASE, unchanged by the change, must not red the PR.
        base_with_secret = self.repo.commit({"config.py": f'aws = "{AWS_KEY}"\n'}, "seed")
        head = self.repo.commit({"README.md": "# docs\n"}, "unrelated")
        r = run_guard(self.repo.dir, base_with_secret, head)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["findings"], [])

    def test_removed_secret_line_is_not_flagged(self):
        base = self.repo.commit({"config.py": f'aws = "{AWS_KEY}"\nkeep = 1\n'}, "seed")
        head = self.repo.commit({"config.py": "keep = 1\n"}, "remove secret")
        r = run_guard(self.repo.dir, base, head)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_active_disposition_accepts_finding(self):
        head = self.repo.commit({
            "config.py": f'api_key = "{HIGH_ENTROPY}"\n',
            LEDGER: _ledger({
                "id": "SEC-1", "gate": "secrets-guard",
                "match": {"file": "config.py", "type": "assignment to `api_key`"},
                "reason": "test fixture", "accepted_by": "t",
                "date": "2026-07-09", "expires": "2999-01-01"}),
        })
        r = run_guard(self.repo.dir, self.repo.base, head, "--today", "2026-07-10")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["findings"], [])
        self.assertEqual(len(data["accepted"]), 1)
        self.assertEqual(data["accepted"][0]["disposition_id"], "SEC-1")

    def test_expired_disposition_re_alarms(self):
        head = self.repo.commit({
            "config.py": f'api_key = "{HIGH_ENTROPY}"\n',
            LEDGER: _ledger({
                "id": "SEC-1", "gate": "secrets-guard",
                "match": {"file": "config.py", "type": "assignment to `api_key`"},
                "reason": "test fixture", "accepted_by": "t",
                "date": "2026-07-09", "expires": "2026-07-09"}),
        })
        r = run_guard(self.repo.dir, self.repo.base, head, "--today", "2026-08-01")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(len(json.loads(r.stdout)["findings"]), 1)

    def test_partial_disposition_leaves_other_finding(self):
        head = self.repo.commit({
            "config.py": f'aws = "{AWS_KEY}"\napi_key = "{HIGH_ENTROPY}"\n',
            LEDGER: _ledger({
                "id": "SEC-1", "gate": "secrets-guard",
                "match": {"path_glob": "config.py", "type": "assignment to `api_key`"},
                "reason": "test fixture", "accepted_by": "t",
                "date": "2026-07-09", "expires": "2999-01-01"}),
        })
        r = run_guard(self.repo.dir, self.repo.base, head, "--today", "2026-07-10")
        self.assertEqual(r.returncode, 1, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual([f["type"] for f in data["findings"]], ["AWS access key id"])
        self.assertEqual(len(data["accepted"]), 1)

    def test_diff_header_spoof_does_not_disable_scan(self):
        # An added CONTENT line that literally reads '++ /dev/null' must not be misparsed
        # as a '+++' file header and silently disable the scan (a live-secret bypass).
        head = self.repo.commit({"evil.txt": f'++ /dev/null\naws = "{AWS_KEY}"\n'})
        r = run_guard(self.repo.dir, self.repo.base, head)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(any(f["type"] == "AWS access key id"
                            for f in json.loads(r.stdout)["findings"]))

    def test_hash_in_value_is_detected(self):
        # A '#' inside a credential must not truncate the captured value below the {6,} floor.
        head = self.repo.commit({"cfg.txt": 'password = "aB#Str0ngLiveP4ssw0rdWithEntropy99"\n'})
        r = run_guard(self.repo.dir, self.repo.base, head)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual([f["type"] for f in data["findings"]], ["assignment to `password`"])
        self.assertNotIn("Str0ngLiveP4ssw0rd", r.stdout)  # still redacted

    def test_short_base64_blob_is_flagged_and_redacted(self):
        # detect() flags base64 blobs at {16,}; _scrub must redact at the same floor so a
        # 16-19 char flagged token can never leak verbatim (the redaction contract).
        blob = "YUIzeEs5bVAycUx6"  # exactly 16 chars
        head = self.repo.commit({"blob.yaml": f"foo: {blob}\n"})
        r = run_guard(self.repo.dir, self.repo.base, head)
        self.assertEqual(len(json.loads(r.stdout)["findings"]), 1)
        self.assertNotIn(blob, r.stdout)

    def test_secret_under_env_dir_is_scanned(self):
        # env/ is a prime secret location and must NOT be in SKIP_DIRS.
        head = self.repo.commit({"env/prod.txt": f'aws = "{AWS_KEY}"\n'})
        r = run_guard(self.repo.dir, self.repo.base, head)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_non_utf8_added_file_does_not_crash(self):
        # A non-UTF-8 added file must degrade (errors="replace"), never crash the decode.
        (Path(self.repo.dir) / "bin.txt").write_bytes(b"name: value\xff\xfe more\n")
        _git(self.repo.dir, "add", "-A")
        _git(self.repo.dir, "commit", "-q", "-m", "bin")
        r = run_guard(self.repo.dir, self.repo.base, _sha(self.repo.dir))
        self.assertIn(r.returncode, (0, 1), r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_missing_base_is_loud_error(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo.dir), "--json"],
            capture_output=True, text=True, env=GIT_ENV, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a pass", r.stderr)

    def test_bad_repo_is_exit_2(self):
        r = run_guard("/nonexistent/path/xyz", "HEAD~1")
        self.assertEqual(r.returncode, 2)

    def test_bad_ref_degrades_loudly(self):
        r = run_guard(self.repo.dir, "no-such-ref", "HEAD")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a pass", r.stderr)


if __name__ == "__main__":
    unittest.main()
