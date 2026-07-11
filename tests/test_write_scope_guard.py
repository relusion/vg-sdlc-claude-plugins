import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/hooks/write-scope-guard.py"


def run_hook(root: Path, payload: dict, policy: Path | None = None):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(root)
    if policy:
        env["CE_WRITE_SCOPE_POLICY"] = str(policy)
    else:
        env.pop("CE_WRITE_SCOPE_POLICY", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


class WriteScopeGuard(unittest.TestCase):
    def test_no_policy_is_inert(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {
                "tool_name": "Write",
                "cwd": str(root),
                "tool_input": {"file_path": "src/app.py"},
            }
            res = run_hook(root, payload)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(res.stdout.strip(), "")

    def test_policy_allows_and_denies_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            policy.write_text(json.dumps({
                "schema_version": 1,
                "enabled": True,
                "reason": "report-only test",
                "allow": ["docs/**"],
                "deny": ["src/**"],
            }), encoding="utf-8")

            allowed = run_hook(root, {
                "tool_name": "Write",
                "cwd": str(root),
                "tool_input": {"file_path": "docs/report.md"},
            }, policy)
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            self.assertEqual(allowed.stdout.strip(), "")

            denied = run_hook(root, {
                "tool_name": "Edit",
                "cwd": str(root),
                "tool_input": {"file_path": "src/app.py"},
            }, policy)
            self.assertEqual(denied.returncode, 0)
            data = json.loads(denied.stdout)
            output = data["hookSpecificOutput"]
            self.assertEqual(output["permissionDecision"], "deny")
            self.assertIn("denylist", output["permissionDecisionReason"])

    def test_deny_only_baseline_allows_unmatched_and_denies_matched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = root / "baseline.json"
            policy.write_text(json.dumps({
                "schema_version": 1,
                "enabled": True,
                "mode": "deny-only",
                "reason": "baseline test",
                "deny": [".git/**", ".claude/ce-write-scope.json"],
            }), encoding="utf-8")

            allowed = run_hook(root, {
                "tool_name": "Write",
                "cwd": str(root),
                "tool_input": {"file_path": "src/app.py"},
            }, policy)
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            self.assertEqual(allowed.stdout.strip(), "")

            denied = run_hook(root, {
                "tool_name": "Edit",
                "cwd": str(root),
                "tool_input": {"file_path": ".claude/ce-write-scope.json"},
            }, policy)
            out = json.loads(denied.stdout)["hookSpecificOutput"]
            self.assertEqual(out["permissionDecision"], "deny")

    def test_unknown_mode_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            policy.write_text(json.dumps({
                "schema_version": 1,
                "enabled": True,
                "mode": "wide-open",
                "deny": [],
            }), encoding="utf-8")
            res = run_hook(root, {
                "tool_name": "Write",
                "cwd": str(root),
                "tool_input": {"file_path": "docs/x.md"},
            }, policy)
            out = json.loads(res.stdout)["hookSpecificOutput"]
            self.assertEqual(out["permissionDecision"], "deny")
            self.assertIn("unknown", out["permissionDecisionReason"])

    def test_deny_reason_carries_scoped_opt_out_and_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            policy.write_text(json.dumps({
                "schema_version": 1,
                "enabled": True,
                "reason": "lease test",
                "allow": ["docs/**"],
            }), encoding="utf-8")
            res = run_hook(root, {
                "tool_name": "Write",
                "cwd": str(root),
                "tool_input": {"file_path": "src/app.py"},
            }, policy)
            out = json.loads(res.stdout)["hookSpecificOutput"]
            self.assertEqual(out["permissionDecision"], "deny")
            self.assertIn(".claude/ce-write-scope.json", out["permissionDecisionReason"])
            log = root / ".claude" / "ce-guard-log.jsonl"
            self.assertTrue(log.is_file())
            entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(entry["guard"], "write-scope-guard")
            self.assertEqual(entry["decision"], "deny")

    def test_log_carries_actor_fields_and_hash_chain_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            policy.write_text(json.dumps({
                "schema_version": 1,
                "enabled": True,
                "reason": "lease test",
                "allow": ["docs/**"],
            }), encoding="utf-8")
            run_hook(root, {
                "tool_name": "Write",
                "cwd": str(root),
                "session_id": "sess-ws",
                "hook_event_name": "PreToolUse",
                "tool_input": {"file_path": "src/app.py"},
            }, policy)
            log = root / ".claude" / "ce-guard-log.jsonl"
            entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(entry["guard"], "write-scope-guard")
            self.assertEqual(entry["session_id"], "sess-ws")
            self.assertEqual(entry["tool"], "Write")
            self.assertEqual(entry["hook_event"], "PreToolUse")
            self.assertEqual(entry["prev"], "")  # genesis
            self.assertEqual(len(entry["payload_sha256"]), 64)
            verify = subprocess.run(
                [sys.executable,
                 str(REPO / "plugins/core-engineering/hooks/guard_log.py"),
                 "--verify", str(log)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(verify.returncode, 0, verify.stderr)

    def test_lease_deny_names_holder_scope_and_single_lift_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lease = root / ".claude" / "ce-write-scope.json"
            lease.parent.mkdir(parents=True)
            lease.write_text(json.dumps({
                "schema_version": 1,
                "enabled": True,
                "mode": "lease",
                "skill": "ce-review",
                "reason": ("session write lease set by /ce-review Stage 0 — "
                           "this session writes only: docs/plans/**/code-review.md"),
                "allow": ["docs/plans/**/code-review.md"],
                "deny": [".git/**", ".claude/ce-write-scope.json"],
            }), encoding="utf-8")
            res = run_hook(root, {
                "tool_name": "Edit",
                "cwd": str(root),
                "tool_input": {"file_path": "src/app.py"},
            })
            out = json.loads(res.stdout)["hookSpecificOutput"]
            self.assertEqual(out["permissionDecision"], "deny")
            msg = out["permissionDecisionReason"]
            # The lease path appears exactly once (in the Human lift), the two
            # audience lines are both present, and no doubled punctuation.
            self.assertEqual(msg.count(".claude/ce-write-scope.json"), 1, msg)
            self.assertIn("Agent:", msg)
            self.assertIn("Human:", msg)
            self.assertNotIn("..", msg)
            self.assertIn("/ce-review", msg)
            self.assertIn("docs/plans/**/code-review.md", msg)

    def test_policy_denies_out_of_workspace_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            policy = root / "policy.json"
            policy.write_text(json.dumps({
                "schema_version": 1,
                "enabled": True,
                "allow": ["docs/**"],
            }), encoding="utf-8")
            outside = Path(tmp) / "outside.md"
            res = run_hook(root, {
                "tool_name": "Write",
                "cwd": str(root),
                "tool_input": {"file_path": str(outside)},
            }, policy)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(json.loads(res.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


def _bash(root: Path, command: str, policy: Path | None = None):
    return run_hook(root, {
        "tool_name": "Bash",
        "cwd": str(root),
        "session_id": "sess-bash",
        "tool_input": {"command": command},
    }, policy)


def _write_lease(root: Path):
    """Seed a ce-review-style lease at the default policy path (lease mode)."""
    lease = root / ".claude" / "ce-write-scope.json"
    lease.parent.mkdir(parents=True, exist_ok=True)
    lease.write_text(json.dumps({
        "schema_version": 1,
        "enabled": True,
        "mode": "lease",
        "skill": "ce-review",
        "reason": ("session write lease set by /ce-review Stage 0 — "
                   "this session writes only: docs/plans/**/code-review.md"),
        "allow": ["docs/plans/**/code-review.md"],
        "deny": [".git/**", ".claude/ce-write-scope.json"],
    }), encoding="utf-8")
    return lease


class WriteScopeGuardBash(unittest.TestCase):
    def test_bash_inert_without_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res = _bash(root, "rm src/app.py")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(res.stdout.strip(), "")

    def test_bash_lease_denies_shell_write_vectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_lease(root)
            vectors = [
                "sed -i 's/a/b/' src/x.py",
                "echo hello > src/x.py",
                "printf '%s' hi >> src/x.py",
                "tee src/x.py < /dev/null",
                "cat foo | tee -a src/x.py",
                "dd if=/dev/zero of=src/x.py",
                "cp templates/base.py src/x.py",
                "mv scratch.py src/x.py",
                "sudo rm -rf src/x.py",
            ]
            for cmd in vectors:
                res = _bash(root, cmd)
                self.assertEqual(res.returncode, 0, cmd)
                out = json.loads(res.stdout)["hookSpecificOutput"]
                self.assertEqual(out["permissionDecision"], "deny", cmd)
                # the deny carries the lease-holder message
                self.assertIn("/ce-review", out["permissionDecisionReason"], cmd)

    def test_bash_lease_allows_allowlisted_report_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_lease(root)
            allowed = [
                "echo '# report' > docs/plans/f1/code-review.md",
                "sed -i 's/x/y/' docs/plans/f1/code-review.md",
                "cat body.md | tee docs/plans/f1/code-review.md",
                "cp draft.md docs/plans/f1/code-review.md",
            ]
            for cmd in allowed:
                res = _bash(root, cmd)
                self.assertEqual(res.returncode, 0, cmd)
                self.assertEqual(res.stdout.strip(), "", cmd)

    def test_bash_hard_denies_lease_mutation(self):
        # Rule 2: mutating/deleting the lease file itself is denied even when the
        # allowlist would otherwise permit it.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lease = root / ".claude" / "ce-write-scope.json"
            lease.parent.mkdir(parents=True, exist_ok=True)
            lease.write_text(json.dumps({
                "schema_version": 1,
                "enabled": True,
                "mode": "lease",
                "skill": "ce-review",
                "reason": "lease",
                "allow": [".claude/**", "docs/**"],   # would allow it but for rule 2
                "deny": [],
            }), encoding="utf-8")
            for cmd in ("rm .claude/ce-write-scope.json",
                        "rm -f ./.claude/ce-write-scope.json",
                        "echo '{}' > .claude/ce-write-scope.json",
                        "mv evil.json .claude/ce-write-scope.json"):
                res = _bash(root, cmd)
                out = json.loads(res.stdout)["hookSpecificOutput"]
                self.assertEqual(out["permissionDecision"], "deny", cmd)
                self.assertIn("lease", out["permissionDecisionReason"].lower(), cmd)

    def test_bash_cd_subdir_relative_write_is_cwd_resolved(self):
        # Finding 6 (cd-desync): a relative write/redirect/rm after `cd <subdir>`
        # must resolve against the effective cwd, not a fixed root — so `../src/x.py`
        # (denied) and `../<lease>` reached from a subdir are CAUGHT, not
        # mis-resolved to an out-of-workspace permissive pass.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_lease(root)
            denied = [
                "cd plugins && echo x > ../src/x.py",             # redirect, out-of-scope
                "cd plugins && rm ../.claude/ce-write-scope.json",  # rm of the lease
                "cd plugins && echo x > ../.claude/ce-write-scope.json",  # redirect at lease
                "cd a/b && rm ../../src/x.py",                    # multi-segment climb
            ]
            for cmd in denied:
                res = _bash(root, cmd)
                out = json.loads(res.stdout)["hookSpecificOutput"]
                self.assertEqual(out["permissionDecision"], "deny", cmd)
            # a LEGIT in-scope write reached via cd stays ALLOWED (no false positive)
            ok = _bash(root, "cd docs && echo x > plans/f1/code-review.md")
            self.assertEqual(ok.stdout.strip(), "", ok.stdout)

    def test_bash_cd_baseline_relative_write_not_over_denied(self):
        # cwd tracking must not start denying normal in-workspace writes under the
        # permissive baseline: `cd src && echo x > app.py` lands on src/app.py, which
        # the baseline (deny only .git/** + lease) permits.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = root / ".claude" / "ce-write-scope.json"
            policy.parent.mkdir(parents=True, exist_ok=True)
            policy.write_text(json.dumps({
                "schema_version": 1, "enabled": True, "mode": "deny-only",
                "deny": [".git/**", ".claude/ce-write-scope.json"],
            }), encoding="utf-8")
            self.assertEqual(_bash(root, "cd src && echo x > app.py").stdout.strip(), "")
            # but a climb back onto git internals from the subdir is still caught
            git_deny = json.loads(_bash(root, "cd src && rm -rf ../.git/config").stdout)
            self.assertEqual(git_deny["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_bash_untracked_cd_relative_write_fails_safe(self):
        # When the cd destination is unknowable ($VAR / `cd -`), a subsequent relative
        # target cannot be resolved — deny fail-safe rather than pass it as
        # out-of-workspace (the desync could otherwise hide a denied/lease write).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_lease(root)
            res = _bash(root, 'cd "$SUBDIR" && rm ../src/x.py')
            out = json.loads(res.stdout)["hookSpecificOutput"]
            self.assertEqual(out["permissionDecision"], "deny", res.stdout)

    def test_bash_mv_lease_source_is_denied(self):
        # Finding 5 (mv source): `mv <lease> /tmp/parked.json` retires the lease by
        # DELETING its source (the out-of-tree dest sails past rule 1). The mv SOURCE
        # must hit the rule-2 lease-file hard-deny.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_lease(root)
            for cmd in ("mv .claude/ce-write-scope.json /tmp/parked.json",
                        "mv -f ./.claude/ce-write-scope.json /tmp/x.json"):
                res = _bash(root, cmd)
                out = json.loads(res.stdout)["hookSpecificOutput"]
                self.assertEqual(out["permissionDecision"], "deny", cmd)
                self.assertIn("lease", out["permissionDecisionReason"].lower(), cmd)
            # a mv of an ORDINARY file out of the tree stays a documented residual
            # (source-side deletion not screened) — no false positive introduced
            self.assertEqual(_bash(root, "mv notes.md /tmp/notes.md").stdout.strip(), "")

    def test_bash_xargs_wrapped_writer_is_screened(self):
        # Finding 7 (xargs): a writer wrapped in `xargs` with a literal operand must be
        # dispatched through the same target extractors — `xargs rm/tee/dd of=` of a
        # denied path is caught, and `xargs rm <lease>` hits the lease hard-deny.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_lease(root)
            for cmd in ("xargs rm src/x.py",
                        "xargs tee src/x.py",
                        "xargs dd of=src/x.py",
                        "xargs -n1 rm src/x.py",
                        "xargs rm .claude/ce-write-scope.json"):
                res = _bash(root, cmd)
                out = json.loads(res.stdout)["hookSpecificOutput"]
                self.assertEqual(out["permissionDecision"], "deny", cmd)

    def test_bash_install_and_ln_onto_lease_are_denied(self):
        # Finding 4 (install/ln): coreutils file-writers not in the original 8 vectors
        # could replace the lease. `install DEST` and `ln [-sf] LINK` onto the lease
        # path must hit the rule-2 hard-deny.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_lease(root)
            for cmd in ("install /tmp/permissive.json .claude/ce-write-scope.json",
                        "install -m 644 /tmp/p.json .claude/ce-write-scope.json",
                        "ln -sf /tmp/permissive.json .claude/ce-write-scope.json",
                        "ln -f /tmp/permissive.json .claude/ce-write-scope.json"):
                res = _bash(root, cmd)
                out = json.loads(res.stdout)["hookSpecificOutput"]
                self.assertEqual(out["permissionDecision"], "deny", cmd)
                self.assertIn("lease", out["permissionDecisionReason"].lower(), cmd)
            # install/ln to an allowlisted report path stays ALLOWED (no false positive)
            self.assertEqual(
                _bash(root, "install draft.md docs/plans/f1/code-review.md").stdout.strip(),
                "")

    def test_bash_baseline_permissive_but_protects_git_and_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = root / ".claude" / "ce-write-scope.json"
            policy.parent.mkdir(parents=True, exist_ok=True)
            policy.write_text(json.dumps({
                "schema_version": 1,
                "enabled": True,
                "mode": "deny-only",
                "reason": "baseline",
                "deny": [".git/**", ".claude/ce-write-scope.json"],
            }), encoding="utf-8")

            # in-workspace, non-denylisted write → allowed under the baseline
            self.assertEqual(_bash(root, "echo x > src/app.py").stdout.strip(), "")
            # out-of-workspace scratch → not a workspace lease's concern → allowed
            outside = Path(tempfile.gettempdir()) / "ce-ws-outside-scratch.txt"
            self.assertEqual(_bash(root, f"echo x > {outside}").stdout.strip(), "")
            # denylisted git internals → denied
            git_deny = json.loads(_bash(root, "rm -rf .git/config").stdout)
            self.assertEqual(git_deny["hookSpecificOutput"]["permissionDecision"], "deny")
            # lease mutation → denied (rule 2)
            lease_deny = json.loads(_bash(root, "rm .claude/ce-write-scope.json").stdout)
            self.assertEqual(lease_deny["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_bash_quoted_redirect_operator_not_a_false_target_in_baseline(self):
        # `echo "a > b"` names no real redirect target under the permissive baseline.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = root / ".claude" / "ce-write-scope.json"
            policy.parent.mkdir(parents=True, exist_ok=True)
            policy.write_text(json.dumps({
                "schema_version": 1,
                "enabled": True,
                "mode": "deny-only",
                "deny": [".git/**", ".claude/ce-write-scope.json"],
            }), encoding="utf-8")
            res = _bash(root, 'echo "1 > 0 is false"')
            self.assertEqual(res.stdout.strip(), "", res.stdout)

    def test_bash_variable_indirection_is_documented_residual(self):
        # A `$VAR` redirect target is unresolvable here — not screened (residual),
        # so it is neither a false-deny nor a claimed catch.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_lease(root)
            res = _bash(root, "echo x > $LOGFILE")
            self.assertEqual(res.stdout.strip(), "", res.stdout)

    def test_bash_denial_is_logged_and_chain_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_lease(root)
            _bash(root, "sed -i 's/a/b/' src/x.py")
            log = root / ".claude" / "ce-guard-log.jsonl"
            self.assertTrue(log.is_file())
            entry = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(entry["guard"], "write-scope-guard")
            self.assertEqual(entry["decision"], "deny")
            self.assertEqual(entry["tool"], "Bash")
            self.assertEqual(entry["session_id"], "sess-bash")
            verify = subprocess.run(
                [sys.executable,
                 str(REPO / "plugins/core-engineering/hooks/guard_log.py"),
                 "--verify", str(log)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(verify.returncode, 0, verify.stderr)

    def test_bash_unparseable_payload_is_loud_non_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = os.environ.copy()
            env["CLAUDE_PROJECT_DIR"] = str(root)
            env.pop("CE_WRITE_SCOPE_POLICY", None)
            res = subprocess.run(
                [sys.executable, str(SCRIPT)],
                input="this is not json{",
                capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(res.returncode, 1)
            self.assertEqual(res.stdout.strip(), "")
            self.assertIn("unparseable", res.stderr.lower())


DEFAULT_LEASE = ".claude/ce-write-scope.json"
SIDECAR = ".claude/ce-write-scope.session.json"


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def _seed_session_lease(root: Path, *, lease_id="L1", created_at=None,
                        allow=("docs/plans/**/code-review.md",)):
    """Seed a lease-mode policy carrying the session-binding identity fields at
    the DEFAULT lease path (so a degrade rewrites this same file)."""
    if created_at is None:
        created_at = _iso(datetime.now(timezone.utc))
    lease = root / DEFAULT_LEASE
    lease.parent.mkdir(parents=True, exist_ok=True)
    lease.write_text(json.dumps({
        "schema_version": 1,
        "enabled": True,
        "mode": "lease",
        "skill": "ce-review",
        "lease_id": lease_id,
        "created_at": created_at,
        "reason": "session write lease set by /ce-review Stage 0",
        "allow": list(allow),
        "deny": [".git/**", DEFAULT_LEASE],
    }), encoding="utf-8")
    return lease


def _seed_sidecar(root: Path, *, lease_id, session_id, bound_at=None):
    sc = root / SIDECAR
    sc.parent.mkdir(parents=True, exist_ok=True)
    sc.write_text(json.dumps({
        "lease_id": lease_id,
        "session_id": session_id,
        "bound_at": bound_at or _iso(datetime.now(timezone.utc)),
    }), encoding="utf-8")
    return sc


def _edit(root: Path, target: str, session_id=None, ttl=None):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(root)
    env.pop("CE_WRITE_SCOPE_POLICY", None)
    if ttl is not None:
        env["CE_WRITE_LEASE_TTL_S"] = str(ttl)
    payload = {"tool_name": "Edit", "cwd": str(root),
               "tool_input": {"file_path": target}}
    if session_id is not None:
        payload["session_id"] = session_id
    return subprocess.run(
        [sys.executable, str(SCRIPT)], input=json.dumps(payload),
        capture_output=True, text=True, env=env, timeout=60)


def _decision(res):
    out = res.stdout.strip()
    return None if out == "" else json.loads(out)["hookSpecificOutput"]["permissionDecision"]


class WriteScopeGuardSessionLease(unittest.TestCase):
    def test_first_use_binds_the_lease_to_the_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_session_lease(root)
            # first lease-mode evaluation (an allowed in-scope write) binds the sidecar
            res = _edit(root, "docs/plans/team/specs/f1/code-review.md", "sess-A")
            self.assertEqual(_decision(res), None, res.stdout)
            sc = json.loads((root / SIDECAR).read_text())
            self.assertEqual(sc["lease_id"], "L1")
            self.assertEqual(sc["session_id"], "sess-A")
            self.assertIn("bound_at", sc)

    def test_same_session_out_of_scope_still_hard_denies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_session_lease(root)
            _seed_sidecar(root, lease_id="L1", session_id="sess-A")
            res = _edit(root, "src/app.py", "sess-A")
            self.assertEqual(_decision(res), "deny")
            # the live owner's lease is untouched (still lease mode)
            self.assertEqual(json.loads((root / DEFAULT_LEASE).read_text())["mode"], "lease")

    def test_dead_session_lease_degrades_to_single_ask_then_writes_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            created = _iso(datetime.now(timezone.utc) - timedelta(minutes=30))
            _seed_session_lease(root, created_at=created)
            _seed_sidecar(root, lease_id="L1", session_id="sess-A")

            first = _edit(root, "src/app.py", "sess-B")
            out = json.loads(first.stdout)["hookSpecificOutput"]
            self.assertEqual(out["permissionDecision"], "ask")
            reason = out["permissionDecisionReason"]
            self.assertIn("dead session", reason)
            self.assertIn("/ce-review", reason)     # names the stale holder
            self.assertIn("set 30m ago", reason)    # its age from created_at
            self.assertIn("auto-replac", reason)     # what just happened

            # the lease is now the deny-only baseline; the orphaned sidecar is gone
            self.assertEqual(json.loads((root / DEFAULT_LEASE).read_text())["mode"], "deny-only")
            self.assertFalse((root / SIDECAR).is_file())

            # the next write in session B flows under the restored baseline
            second = _edit(root, "src/app.py", "sess-B")
            self.assertEqual(_decision(second), None, second.stdout)

    def test_ttl_orphan_without_sidecar_degrades(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = _iso(datetime.now(timezone.utc) - timedelta(hours=20))
            _seed_session_lease(root, created_at=old)  # no sidecar; default TTL 8h
            res = _edit(root, "src/app.py", "sess-Z")
            self.assertEqual(_decision(res), "ask")
            self.assertEqual(json.loads((root / DEFAULT_LEASE).read_text())["mode"], "deny-only")

    def test_fresh_lease_without_sidecar_binds_and_still_enforces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_session_lease(root)  # recent created_at, no sidecar
            res = _edit(root, "src/app.py", "sess-Z")
            self.assertEqual(_decision(res), "deny")  # bound, not degraded
            self.assertTrue((root / SIDECAR).is_file())
            self.assertEqual(json.loads((root / DEFAULT_LEASE).read_text())["mode"], "lease")

    def test_ttl_zero_disables_the_age_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = _iso(datetime.now(timezone.utc) - timedelta(hours=50))
            _seed_session_lease(root, created_at=old)
            res = _edit(root, "src/app.py", "sess-Z", ttl=0)
            self.assertEqual(_decision(res), "deny")  # TTL off → bind, enforce

    def test_missing_session_id_fail_safes_to_deny(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_session_lease(root)
            _seed_sidecar(root, lease_id="L1", session_id="sess-A")
            res = _edit(root, "src/app.py", session_id=None)  # ambiguous
            self.assertEqual(_decision(res), "deny")
            self.assertEqual(json.loads((root / DEFAULT_LEASE).read_text())["mode"], "lease")

    def test_legacy_lease_without_id_fail_safes_to_deny(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lease = root / DEFAULT_LEASE
            lease.parent.mkdir(parents=True)
            lease.write_text(json.dumps({
                "schema_version": 1, "enabled": True, "mode": "lease",
                "skill": "ce-review", "reason": "legacy",
                "allow": ["docs/**"], "deny": [".git/**", DEFAULT_LEASE],
            }), encoding="utf-8")
            res = _edit(root, "src/app.py", "sess-B")
            self.assertEqual(_decision(res), "deny")

    def test_unreadable_sidecar_fail_safes_to_deny(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_session_lease(root)
            (root / SIDECAR).write_text("{ not json", encoding="utf-8")
            res = _edit(root, "src/app.py", "sess-B")
            self.assertEqual(_decision(res), "deny")

    def test_new_lease_rebinds_a_sidecar_naming_an_older_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_session_lease(root, lease_id="L2")
            _seed_sidecar(root, lease_id="L1", session_id="sess-A")  # stale, other lease
            res = _edit(root, "docs/plans/team/specs/f1/code-review.md", "sess-B")
            self.assertEqual(_decision(res), None, res.stdout)  # in-scope, allowed
            sc = json.loads((root / SIDECAR).read_text())
            self.assertEqual(sc["lease_id"], "L2")
            self.assertEqual(sc["session_id"], "sess-B")

    def test_degrade_ask_is_logged_and_chain_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_session_lease(root)
            _seed_sidecar(root, lease_id="L1", session_id="sess-A")
            _edit(root, "src/app.py", "sess-B")
            log = root / ".claude" / "ce-guard-log.jsonl"
            entry = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(entry["guard"], "write-scope-guard")
            self.assertEqual(entry["decision"], "ask")
            verify = subprocess.run(
                [sys.executable,
                 str(REPO / "plugins/core-engineering/hooks/guard_log.py"),
                 "--verify", str(log)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(verify.returncode, 0, verify.stderr)

    def test_bash_vector_under_a_dead_session_lease_degrades(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_session_lease(root)
            _seed_sidecar(root, lease_id="L1", session_id="sess-A")
            res = run_hook(root, {
                "tool_name": "Bash", "cwd": str(root), "session_id": "sess-B",
                "tool_input": {"command": "sed -i 's/a/b/' src/x.py"},
            })
            out = json.loads(res.stdout)["hookSpecificOutput"]
            self.assertEqual(out["permissionDecision"], "ask")
            self.assertIn("dead session", out["permissionDecisionReason"])


if __name__ == "__main__":
    unittest.main()
