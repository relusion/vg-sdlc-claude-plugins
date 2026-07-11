"""Tests for hooks/git-guard.py — the shared-history backstop's decision posture."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/hooks/git-guard.py"


def run_hook(stdin_text: str, root: Path, extra_env: dict | None = None,
             cwd: Path | None = None):
    env = os.environ.copy()
    env.pop("CE_GIT_GUARD", None)
    env.pop("CE_GIT_GUARD_PUSH", None)
    env.pop("CE_GIT_GUARD_PR", None)
    env.pop("CE_GIT_GUARD_TAG", None)
    env.pop("CE_GIT_GUARD_COMMIT", None)
    env["CLAUDE_PROJECT_DIR"] = str(root)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd) if cwd else None,
        timeout=60,
    )


def make_repo(root: Path, head: str, protected: str = "main") -> Path:
    """A throwaway git repo with one commit, HEAD on `head`, and a local
    `init.defaultBranch` pinning the protected branch — the fixture the
    protected-branch (commit/merge/revert/cherry-pick/am) rules need, since the
    hook resolves both branches from its own cwd."""
    repo = root / "repo"
    repo.mkdir()
    git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git + ["init", "-q"], cwd=repo, check=True)
    subprocess.run(git + ["config", "init.defaultBranch", protected],
                   cwd=repo, check=True)
    subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "init"],
                   cwd=repo, check=True)
    subprocess.run(git + ["branch", "-M", head], cwd=repo, check=True)
    return repo


def payload(command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def decision_of(res) -> dict:
    return json.loads(res.stdout)["hookSpecificOutput"]


class GitGuard(unittest.TestCase):
    def test_push_defaults_to_ask(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(payload("git push origin main"), Path(tmp))
            self.assertEqual(res.returncode, 0, res.stderr)
            out = decision_of(res)
            self.assertEqual(out["permissionDecision"], "ask")
            self.assertIn("shared history", out["permissionDecisionReason"])

    def test_push_tier_env_override_denies(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(payload("git push"), Path(tmp), {"CE_GIT_GUARD_PUSH": "deny"})
            self.assertEqual(decision_of(res)["permissionDecision"], "deny")

    def test_invalid_tier_value_falls_back_to_ask(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(payload("git push"), Path(tmp), {"CE_GIT_GUARD_PUSH": "yolo"})
            self.assertEqual(decision_of(res)["permissionDecision"], "ask")

    def test_recognized_bash_without_command_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(json.dumps({"tool_name": "Bash", "tool_input": {}}), Path(tmp))
            out = decision_of(res)
            self.assertEqual(out["permissionDecision"], "deny")
            self.assertIn("malformed", out["permissionDecisionReason"])
            self.assertIn("CE_GIT_GUARD=off", out["permissionDecisionReason"])

    def test_unparseable_input_asks_instead_of_allowing(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook("this is not json", Path(tmp))
            out = decision_of(res)
            self.assertEqual(out["permissionDecision"], "ask")
            self.assertIn("unrecognized payload shape", out["permissionDecisionReason"])

    def test_payload_without_tool_name_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(json.dumps({"something": "else"}), Path(tmp))
            self.assertEqual(decision_of(res)["permissionDecision"], "ask")

    def test_non_bash_tool_is_silently_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(json.dumps({"tool_name": "Read", "tool_input": {}}), Path(tmp))
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")

    def test_harmless_bash_command_is_silently_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(payload("git status"), Path(tmp))
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")

    def test_kill_switch_disables_the_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(payload("git push --force"), Path(tmp), {"CE_GIT_GUARD": "off"})
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")

    def test_decisions_are_logged_best_effort(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_hook(payload("git push"), root)
            log = root / ".claude" / "ce-guard-log.jsonl"
            self.assertTrue(log.is_file())
            entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(entry["guard"], "git-guard")
            self.assertEqual(entry["decision"], "ask")

    def test_log_carries_actor_fields_and_hash_chain_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for cmd in ("git push", "git tag v1"):
                run_hook(json.dumps({
                    "tool_name": "Bash", "session_id": "sess-1",
                    "hook_event_name": "PreToolUse",
                    "tool_input": {"command": cmd},
                }), root)
            log = root / ".claude" / "ce-guard-log.jsonl"
            entries = [json.loads(x) for x in
                       log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["session_id"], "sess-1")
            self.assertEqual(entries[0]["tool"], "Bash")
            self.assertEqual(entries[0]["hook_event"], "PreToolUse")
            self.assertEqual(len(entries[0]["payload_sha256"]), 64)
            self.assertEqual(entries[0]["prev"], "")  # genesis
            self.assertNotEqual(entries[1]["prev"], "")  # chained
            verify = subprocess.run(
                [sys.executable,
                 str(REPO / "plugins/core-engineering/hooks/guard_log.py"),
                 "--verify", str(log)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(verify.returncode, 0, verify.stderr)

    # --- fail-open regressions: a global option before the subcommand used to
    #     slip past the `\bgit\s+push\b` prefix regex entirely (silent allow) ---
    def _asks(self, command):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(payload(command), Path(tmp))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertNotEqual(res.stdout.strip(), "",
                                f"guard was silent (fail-open) on: {command}")
            return decision_of(res)["permissionDecision"]

    def test_push_with_dash_C_is_caught(self):
        self.assertEqual(self._asks("git -C /some/repo push origin main"), "ask")

    def test_push_with_dash_c_config_is_caught(self):
        self.assertEqual(self._asks("git -c core.pager=less push"), "ask")

    def test_push_with_no_pager_is_caught(self):
        self.assertEqual(self._asks("git --no-pager push"), "ask")

    def test_push_with_env_assignment_prefix_is_caught(self):
        self.assertEqual(self._asks("GIT_SSH_COMMAND=ssh git push"), "ask")

    def test_gh_pr_create_with_repo_flag_is_caught(self):
        self.assertEqual(self._asks("gh --repo owner/repo pr create --fill"), "ask")

    def test_gh_pr_merge_is_caught(self):
        self.assertEqual(self._asks("gh pr merge 42 --squash"), "ask")

    def test_push_in_a_later_segment_is_caught(self):
        self.assertEqual(self._asks("git add -A && git commit -m x && git push"), "ask")

    def test_sudo_git_push_is_caught(self):
        # The old substring matcher caught `sudo git push`; the tokenizer must
        # not regress it — a leading bare wrapper is stripped.
        self.assertEqual(self._asks("sudo git push"), "ask")

    def test_nohup_and_env_wrapped_push_is_caught(self):
        self.assertEqual(self._asks("nohup git push"), "ask")
        self.assertEqual(self._asks("env GIT_TRACE=1 git push"), "ask")

    def test_push_in_command_substitution_is_caught(self):
        self.assertEqual(self._asks("out=$(git push 2>&1)"), "ask")

    def test_push_in_subshell_is_caught(self):
        self.assertEqual(self._asks("(cd sub && git push)"), "ask")

    def test_timeout_wrapped_push_is_caught(self):
        self.assertEqual(self._asks("timeout 30 git push"), "ask")
        self.assertEqual(self._asks("timeout -k 5 30s git push"), "ask")

    def test_bash_dash_c_push_is_caught(self):
        self.assertEqual(self._asks("bash -c 'git push origin main'"), "ask")
        self.assertEqual(self._asks("sh -lc \"git push\""), "ask")

    def test_push_in_if_then_block_is_caught(self):
        self.assertEqual(self._asks("if true; then git push; fi"), "ask")

    def test_push_in_for_loop_body_is_caught(self):
        self.assertEqual(self._asks("for x in 1; do git push; done"), "ask")

    # --- false-positive regressions: the substring `git push` inside a quoted
    #     argument or an unrelated program must NOT trigger a confirmation ------
    def _silent(self, command):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(payload(command), Path(tmp))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(res.stdout.strip(), "",
                             f"guard cried wolf on a non-pushing command: {command}")

    def test_commit_message_mentioning_push_is_not_flagged_as_push(self):
        # A feature-branch commit whose message contains the words "git push"
        # must not raise the push confirmation (it pushes nothing).
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(payload('git commit -m "document how to git push safely"'),
                           Path(tmp))
            # On a throwaway tmp dir there is no protected branch to match, so the
            # commit path stays silent; the key assertion is it is NOT a push ask.
            out = res.stdout.strip()
            if out:
                self.assertNotIn("shared history", json.loads(out)
                                 ["hookSpecificOutput"]["permissionDecisionReason"])

    def test_echoing_git_push_is_silently_allowed(self):
        self._silent('echo "remember to git push later"')

    def test_grep_for_git_push_is_silently_allowed(self):
        self._silent('grep -r "git push" docs/')

    # --- porcelain closure: merge/revert/cherry-pick/am write commits too, so
    #     on the protected branch they share the commit rule ------------------
    def _on_branch(self, command, head, protected="main"):
        """Run the hook from inside a fixture repo; returns the raw result."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), head, protected)
            res = run_hook(payload(command), Path(tmp), cwd=repo)
            self.assertEqual(res.returncode, 0, res.stderr)
            return res

    def test_commit_writing_porcelain_on_protected_branch_asks(self):
        for command in ("git merge feature-x",
                        "git revert HEAD",
                        "git cherry-pick abc123",
                        "git am patch.mbox",
                        "git commit -m x",
                        "git -c core.pager=less merge topic"):
            with self.subTest(command=command):
                res = self._on_branch(command, head="main")
                out = decision_of(res)
                self.assertEqual(out["permissionDecision"], "ask")
                self.assertIn("main", out["permissionDecisionReason"])

    def test_commit_writing_porcelain_respects_deny_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), head="main")
            res = run_hook(payload("git cherry-pick abc123"), Path(tmp),
                           {"CE_GIT_GUARD_COMMIT": "deny"}, cwd=repo)
            self.assertEqual(decision_of(res)["permissionDecision"], "deny")

    def test_commit_writing_porcelain_off_protected_branch_is_silent(self):
        for command in ("git merge main", "git revert HEAD",
                        "git cherry-pick abc123", "git am patch.mbox"):
            with self.subTest(command=command):
                res = self._on_branch(command, head="feat/topic")
                self.assertEqual(res.stdout.strip(), "",
                                 f"guard cried wolf off-protected-branch on: {command}")

    # --- tag rule: creation/move/deletion asks; listing stays silent ----------
    def test_tag_creation_asks(self):
        for command in ("git tag v1.0.0",
                        "git tag -a v1.0.0 -m 'release'",
                        "git tag -f v1.0.0",
                        "git tag -d v1.0.0",
                        "git -C /some/repo tag v2",
                        "bash -c 'git tag v1.0.0'"):
            with self.subTest(command=command):
                out = self._asks(command)
                self.assertEqual(out, "ask")

    def test_tag_deny_tier_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(payload("git tag v1.0.0"), Path(tmp),
                           {"CE_GIT_GUARD_TAG": "deny"})
            self.assertEqual(decision_of(res)["permissionDecision"], "deny")

    def test_tag_listing_is_silently_allowed(self):
        for command in ("git tag", "git tag -l", "git tag --list",
                        "git tag -l 'v*'", "git tag --list 'v1.*'"):
            with self.subTest(command=command):
                self._silent(command)

    # --- gh api: PR-writing endpoints join the pr rule ------------------------
    def test_gh_api_pr_creation_endpoint_asks(self):
        for command in ("gh api repos/o/r/pulls -X POST -f title=x",
                        "gh api repos/o/r/pulls --method POST",
                        "gh api --method=POST repos/o/r/pulls",
                        "gh api repos/o/r/pulls/1/merge -X PUT",
                        "gh api repos/o/r/pulls -f title=x -f head=b -f base=main"):
            with self.subTest(command=command):
                self.assertEqual(self._asks(command), "ask")

    def test_gh_api_pr_rule_respects_deny_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(payload("gh api repos/o/r/pulls -X POST"), Path(tmp),
                           {"CE_GIT_GUARD_PR": "deny"})
            self.assertEqual(decision_of(res)["permissionDecision"], "deny")

    def test_gh_api_non_pr_or_read_calls_are_silently_allowed(self):
        for command in ("gh api repos/x/y/issues",
                        "gh api repos/x/y/issues -X POST -f title=bug",
                        "gh api repos/o/r/pulls",
                        "gh api repos/o/r/pulls/1"):
            with self.subTest(command=command):
                self._silent(command)

    # --- xargs hole: the piped subcommand is unreadable, so git/gh in an
    #     xargs tail asks instead of resolving to an unguarded bare git --------
    def test_xargs_git_tail_asks(self):
        for command in ("echo push | xargs git",
                        "echo 'pr create' | xargs gh",
                        "printf push | xargs -n1 git",
                        "echo push | xargs -I{} git {}"):
            with self.subTest(command=command):
                out = self._asks(command)
                self.assertEqual(out, "ask")

    def test_xargs_git_tail_reason_names_the_piped_subcommand_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(payload("echo push | xargs git"), Path(tmp))
            reason = decision_of(res)["permissionDecisionReason"]
            self.assertIn("piped subcommand this guard cannot read", reason)

    def test_xargs_without_git_or_gh_is_silently_allowed(self):
        self._silent("find . -name '*.txt' | xargs grep foo")
        self._silent("echo a b | xargs mkdir -p")

    # --- short-circuit priority: push still wins a mixed command --------------
    def test_push_reason_wins_over_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook(payload("git tag v1 && git push origin v1"), Path(tmp))
            self.assertIn("shared history",
                          decision_of(res)["permissionDecisionReason"])


if __name__ == "__main__":
    unittest.main()
