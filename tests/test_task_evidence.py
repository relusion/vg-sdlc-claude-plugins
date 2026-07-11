"""Tests for ce-implement's task-evidence.py — the evidence stamp on tasks.json.

Covers the `stamp --task` done-recording (all three fields written; test_run_digest
projected verbatim from WS4-T4's passes.json marker; --test-log fallback; null when
neither exists), unknown-task refusal (exit 1), commit resolution to a full sha,
the `stamp --all-done` Stage-3 finalizer (fills null commit_sha, leaves already-
stamped untouched), atomic-write JSON integrity, the exit-2 error contract, and the
invariant that a stamped tasks.json still passes spec-lint H1-H4 (fields are additive).

Also covers the WS3-T4 `check` subcommand — the consumer-side freshness verdict:
fresh (commit_sha in HEAD's ancestry), stale (rewound past the stamped commit → exit
1), unstamped (legacy / uncommitted / no-git → warn, exit 0), and the test_run_digest
mismatch → stale path.
"""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-implement/scripts/task-evidence.py"
SPEC_LINT = REPO / "plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py"

FEATURE_ID = "03-widget"

SPEC_MD = """\
# ce-spec: widget

## Acceptance Criteria

### AC-1
The widget renders.

## Test Cases

### TC-1
modality: cli
verification: auto
(proves AC-1)

### TC-2
modality: manual
verification: manual:judgment
(proves AC-1)
"""


def base_tasks():
    return {
        "feature_id": FEATURE_ID,
        "spec_revision": 1,
        "tasks": [
            {"id": "T-1", "description": "impl", "files": ["a.py"],
             "verifies": ["TC-1"], "order": 1, "status": "todo"},
            {"id": "T-2", "description": "manual", "files": ["b.py"],
             "verifies": ["TC-2"], "order": 2, "status": "todo"},
        ],
    }


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=30,
    )


def spec_lint(spec_dir: Path):
    return subprocess.run(
        [sys.executable, str(SPEC_LINT), str(spec_dir), "--json"],
        capture_output=True, text=True, timeout=30,
    )


def write_tasks(path: Path, data=None):
    path.write_text(json.dumps(data or base_tasks(), indent=2) + "\n")


def write_passes(root: Path, feature_id: str, entries: list) -> Path:
    d = root / ".test-guard" / feature_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / "passes.json"
    p.write_text(json.dumps(
        {"schema": "test-guard/passes@1", "feature_id": feature_id, "passes": entries},
        indent=2) + "\n")
    return p


def git_repo(root: Path):
    """Init a repo with one commit; return (repo_root, head_sha)."""
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / "seed").write_text("x")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "seed"], check=True)
    sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()
    return root, sha


class StampTask(unittest.TestCase):
    def test_all_three_fields_from_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tj = root / "tasks.json"
            write_tasks(tj)
            digest = "sha256:" + "a" * 64
            passes = write_passes(root, FEATURE_ID, [
                {"task_id": "T-1", "verdict": "pass", "ts": "2026-07-04T00:00:00Z",
                 "snapshot_sha256": digest},
            ])
            r = run("stamp", str(tj), "--task", "T-1",
                    "--commit", "deadbeefdeadbeef", "--passes", str(passes),
                    "--now", "2026-07-04T12:00:00Z")
            self.assertEqual(r.returncode, 0, r.stderr)
            t1 = next(t for t in json.loads(tj.read_text())["tasks"] if t["id"] == "T-1")
            self.assertEqual(t1["status"], "done")
            self.assertEqual(t1["completed_at"], "2026-07-04T12:00:00Z")
            self.assertEqual(t1["commit_sha"], "deadbeefdeadbeef")
            # test_run_digest is the marker's snapshot_sha256, projected VERBATIM.
            self.assertEqual(t1["test_run_digest"], digest)

    def test_digest_falls_back_to_test_log_when_no_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tj = root / "tasks.json"
            write_tasks(tj)
            log = root / "run.log"
            log.write_bytes(b"3 passed in 0.4s\n")
            expect = "sha256:" + hashlib.sha256(b"3 passed in 0.4s\n").hexdigest()
            r = run("stamp", str(tj), "--task", "T-1", "--test-log", str(log))
            self.assertEqual(r.returncode, 0, r.stderr)
            t1 = next(t for t in json.loads(tj.read_text())["tasks"] if t["id"] == "T-1")
            self.assertEqual(t1["test_run_digest"], expect)
            self.assertIsNone(t1["commit_sha"])  # no --commit -> null

    def test_marker_wins_over_test_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tj = root / "tasks.json"
            write_tasks(tj)
            digest = "sha256:" + "b" * 64
            passes = write_passes(root, FEATURE_ID, [
                {"task_id": "T-1", "verdict": "pass", "ts": "t", "snapshot_sha256": digest},
            ])
            log = root / "run.log"
            log.write_bytes(b"unused")
            r = run("stamp", str(tj), "--task", "T-1",
                    "--passes", str(passes), "--test-log", str(log))
            self.assertEqual(r.returncode, 0, r.stderr)
            t1 = next(t for t in json.loads(tj.read_text())["tasks"] if t["id"] == "T-1")
            self.assertEqual(t1["test_run_digest"], digest)  # marker, not the log

    def test_latest_marker_entry_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tj = root / "tasks.json"
            write_tasks(tj)
            old, new = "sha256:" + "1" * 64, "sha256:" + "2" * 64
            passes = write_passes(root, FEATURE_ID, [
                {"task_id": "T-1", "verdict": "pass", "ts": "t1", "snapshot_sha256": old},
                {"task_id": "T-1", "verdict": "pass", "ts": "t2", "snapshot_sha256": new},
            ])
            r = run("stamp", str(tj), "--task", "T-1", "--passes", str(passes))
            self.assertEqual(r.returncode, 0, r.stderr)
            t1 = next(t for t in json.loads(tj.read_text())["tasks"] if t["id"] == "T-1")
            self.assertEqual(t1["test_run_digest"], new)

    def test_digest_null_when_no_marker_and_no_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tj = root / "tasks.json"
            write_tasks(tj)
            r = run("stamp", str(tj), "--task", "T-2")
            self.assertEqual(r.returncode, 0, r.stderr)
            t2 = next(t for t in json.loads(tj.read_text())["tasks"] if t["id"] == "T-2")
            self.assertIsNone(t2["test_run_digest"])  # never fabricated
            self.assertEqual(t2["status"], "done")

    def test_marker_auto_derived_from_repo_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            specs = root / "specs" / FEATURE_ID
            specs.mkdir(parents=True)
            tj = specs / "tasks.json"
            write_tasks(tj)
            digest = "sha256:" + "c" * 64
            write_passes(root, FEATURE_ID, [
                {"task_id": "T-1", "verdict": "pass", "ts": "t", "snapshot_sha256": digest},
            ])
            # No --passes: derive .test-guard/<feature_id>/passes.json from --repo.
            r = run("stamp", str(tj), "--task", "T-1", "--repo", str(root))
            self.assertEqual(r.returncode, 0, r.stderr)
            t1 = next(t for t in json.loads(tj.read_text())["tasks"] if t["id"] == "T-1")
            self.assertEqual(t1["test_run_digest"], digest)


class UnknownTask(unittest.TestCase):
    def test_unknown_task_id_exits_1_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tj = Path(tmp) / "tasks.json"
            write_tasks(tj)
            before = tj.read_text()
            r = run("stamp", str(tj), "--task", "T-99")
            self.assertEqual(r.returncode, 1)
            self.assertEqual(tj.read_text(), before)  # untouched

    def test_unknown_task_json_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            tj = Path(tmp) / "tasks.json"
            write_tasks(tj)
            r = run("stamp", str(tj), "--task", "T-99", "--json")
            self.assertEqual(r.returncode, 1)
            self.assertEqual(json.loads(r.stdout)["exit"], 1)


class CommitResolution(unittest.TestCase):
    def test_head_resolves_to_full_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = git_repo(Path(tmp))
            tj = root / "tasks.json"
            write_tasks(tj)
            r = run("stamp", str(tj), "--task", "T-1", "--commit", "HEAD", "--repo", str(root))
            self.assertEqual(r.returncode, 0, r.stderr)
            t1 = next(t for t in json.loads(tj.read_text())["tasks"] if t["id"] == "T-1")
            self.assertEqual(t1["commit_sha"], sha)  # full 40-char sha, not "HEAD"

    def test_unresolvable_ref_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tj = Path(tmp) / "tasks.json"
            write_tasks(tj)
            r = run("stamp", str(tj), "--task", "T-1", "--commit", "not-a-sha")
            self.assertEqual(r.returncode, 2)


class AllDone(unittest.TestCase):
    def test_fills_null_commit_sha_leaves_stamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, sha = git_repo(Path(tmp))
            tj = root / "tasks.json"
            data = base_tasks()
            # T-1 done + already per-task stamped; T-2 done + null; T-nope todo.
            data["tasks"][0]["status"] = "done"
            data["tasks"][0]["commit_sha"] = "pretaskcommit1234"
            data["tasks"][1]["status"] = "done"
            data["tasks"][1]["commit_sha"] = None
            write_tasks(tj, data)
            r = run("stamp", str(tj), "--all-done", "--commit", "HEAD", "--repo", str(root))
            self.assertEqual(r.returncode, 0, r.stderr)
            out = {t["id"]: t for t in json.loads(tj.read_text())["tasks"]}
            self.assertEqual(out["T-1"]["commit_sha"], "pretaskcommit1234")  # untouched
            self.assertEqual(out["T-2"]["commit_sha"], sha)                  # filled

    def test_all_done_requires_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            tj = Path(tmp) / "tasks.json"
            write_tasks(tj)
            r = run("stamp", str(tj), "--all-done")
            self.assertEqual(r.returncode, 2)  # argparse error -> exit 2


class ErrorContract(unittest.TestCase):
    def test_missing_tasks_json_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run("stamp", str(Path(tmp) / "nope.json"), "--task", "T-1")
            self.assertEqual(r.returncode, 2)

    def test_unparseable_tasks_json_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tj = Path(tmp) / "tasks.json"
            tj.write_text("{not json")
            r = run("stamp", str(tj), "--task", "T-1")
            self.assertEqual(r.returncode, 2)

    def test_no_subcommand_exits_2(self):
        r = run()
        self.assertEqual(r.returncode, 2)  # required subparser


def _git(root, *args, **kw):
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, **kw)


def _commit(root, fname, msg):
    (root / fname).write_text("x")
    _git(root, "add", fname, check=True)
    _git(root, "commit", "-qm", msg, check=True)
    return _git(root, "rev-parse", "HEAD", check=True).stdout.strip()


class CheckSubcommand(unittest.TestCase):
    def test_fresh_then_stale_after_rewind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = git_repo(Path(tmp))
            c1 = _commit(root, "f.txt", "feature commit")
            # tasks.json is UNTRACKED, so `git reset --hard` never reverts it —
            # the stamp survives the rewind and its commit_sha becomes unreachable.
            tj = root / "tasks.json"
            data = base_tasks()
            data["tasks"][0]["status"] = "done"
            write_tasks(tj, data)
            self.assertEqual(
                run("stamp", str(tj), "--task", "T-1", "--commit", c1,
                    "--repo", str(root)).returncode, 0)

            r = run("check", str(tj), "--repo", str(root), "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            doc = json.loads(r.stdout)
            t1 = next(t for t in doc["tasks"] if t["id"] == "T-1")
            self.assertEqual(t1["verdict"], "fresh")
            self.assertEqual(doc["counts"]["fresh"], 1)
            self.assertEqual(doc["stale"], [])

            # rewind HEAD past the feature commit; c1 is no longer an ancestor.
            self.assertEqual(_git(root, "reset", "--hard", "HEAD~1", "-q").returncode, 0)
            r2 = run("check", str(tj), "--repo", str(root), "--json")
            self.assertEqual(r2.returncode, 1)  # a stale done task -> exit 1
            doc2 = json.loads(r2.stdout)
            t1b = next(t for t in doc2["tasks"] if t["id"] == "T-1")
            self.assertEqual(t1b["verdict"], "stale")
            self.assertIn("T-1", doc2["stale"])
            self.assertEqual(doc2["counts"]["stale"], 1)

    def test_unstamped_legacy_and_uncommitted_warn_not_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = git_repo(Path(tmp))
            tj = root / "tasks.json"
            data = base_tasks()
            # T-1: legacy done, no evidence fields at all (pre-WS3-T3).
            data["tasks"][0]["status"] = "done"
            # T-2: stamped done but commit_sha still null (none-granularity).
            data["tasks"][1]["status"] = "done"
            data["tasks"][1]["completed_at"] = "2026-07-04T00:00:00Z"
            data["tasks"][1]["commit_sha"] = None
            write_tasks(tj, data)
            r = run("check", str(tj), "--repo", str(root), "--json")
            self.assertEqual(r.returncode, 0, r.stderr)  # unstamped never hard-fails
            doc = json.loads(r.stdout)
            verds = {t["id"]: t["verdict"] for t in doc["tasks"]}
            self.assertEqual(verds["T-1"], "unstamped")
            self.assertEqual(verds["T-2"], "unstamped")
            self.assertEqual(doc["counts"]["unstamped"], 2)
            self.assertEqual(doc["stamped"], 1)  # only T-2 carried a stamp

    def test_digest_mismatch_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = git_repo(Path(tmp))
            c1 = _commit(root, "f.txt", "feature commit")
            tj = root / "tasks.json"
            data = base_tasks()
            data["tasks"][0]["status"] = "done"
            data["tasks"][0]["completed_at"] = "2026-07-04T00:00:00Z"
            data["tasks"][0]["commit_sha"] = c1  # in HEAD ancestry -> ok
            data["tasks"][0]["test_run_digest"] = "sha256:" + "a" * 64
            write_tasks(tj, data)
            # the current marker projects a DIFFERENT digest -> evidence drifted.
            passes = write_passes(root, FEATURE_ID, [
                {"task_id": "T-1", "verdict": "pass", "ts": "t",
                 "snapshot_sha256": "sha256:" + "b" * 64}])
            r = run("check", str(tj), "--repo", str(root),
                    "--passes", str(passes), "--json")
            self.assertEqual(r.returncode, 1)
            doc = json.loads(r.stdout)
            t1 = next(t for t in doc["tasks"] if t["id"] == "T-1")
            self.assertEqual(t1["verdict"], "stale")
            self.assertIn("digest", t1["reason"])

    def test_matching_digest_stays_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = git_repo(Path(tmp))
            c1 = _commit(root, "f.txt", "feature commit")
            tj = root / "tasks.json"
            digest = "sha256:" + "c" * 64
            data = base_tasks()
            data["tasks"][0]["status"] = "done"
            data["tasks"][0]["completed_at"] = "2026-07-04T00:00:00Z"
            data["tasks"][0]["commit_sha"] = c1
            data["tasks"][0]["test_run_digest"] = digest
            write_tasks(tj, data)
            passes = write_passes(root, FEATURE_ID, [
                {"task_id": "T-1", "verdict": "pass", "ts": "t",
                 "snapshot_sha256": digest}])
            r = run("check", str(tj), "--repo", str(root),
                    "--passes", str(passes), "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            t1 = next(t for t in json.loads(r.stdout)["tasks"] if t["id"] == "T-1")
            self.assertEqual(t1["verdict"], "fresh")

    def test_check_missing_tasks_json_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run("check", str(Path(tmp) / "nope.json"))
            self.assertEqual(r.returncode, 2)

    def test_check_ignores_todo_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = git_repo(Path(tmp))
            tj = root / "tasks.json"
            write_tasks(tj)  # both tasks status "todo"
            r = run("check", str(tj), "--repo", str(root), "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            doc = json.loads(r.stdout)
            self.assertEqual(doc["counts"]["done"], 0)
            self.assertEqual(doc["tasks"], [])


class SpecLintUnaffected(unittest.TestCase):
    def test_stamped_tasks_still_pass_spec_lint(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = Path(tmp) / "specs" / FEATURE_ID
            spec_dir.mkdir(parents=True)
            (spec_dir / "ce-spec.md").write_text(SPEC_MD)
            tj = spec_dir / "tasks.json"
            write_tasks(tj)
            # baseline: passes H1-H4
            self.assertEqual(spec_lint(spec_dir).returncode, 0)
            # stamp both tasks done, then re-lint — additive fields must not break it.
            log = Path(tmp) / "log"
            log.write_bytes(b"ok")
            self.assertEqual(
                run("stamp", str(tj), "--task", "T-1", "--test-log", str(log)).returncode, 0)
            self.assertEqual(
                run("stamp", str(tj), "--task", "T-2", "--test-log", str(log)).returncode, 0)
            res = spec_lint(spec_dir)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertEqual(json.loads(res.stdout)["status"], "pass")


if __name__ == "__main__":
    unittest.main()
