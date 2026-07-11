"""Tests for hooks/env-guard.py — the secret-file-read backstop.

env-guard was the one shipped deny-hook with no unit tests. This suite locks in
its documented posture: deny the process-environment file and out-of-workspace
dotenv reads; leave the project's own .env and unrelated reads alone; and, on an
UNPARSEABLE payload, emit a loud non-blocking warning (exit 1) rather than a
hard deny — the deliberate hot-path choice (asking/denying on every Read/Grep/
Bash would brick the session on harness drift, and a malformed payload cannot
carry a real guarded read the harness would dispatch).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/hooks/env-guard.py"


def run_hook(payload, root, extra_env=None):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(root)
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin, capture_output=True, text=True, env=env, timeout=60,
    )


def decision(res):
    return json.loads(res.stdout)["hookSpecificOutput"]["permissionDecision"]


class EnvGuard(unittest.TestCase):
    def test_reading_proc_environ_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook({"tool_name": "Read", "cwd": tmp,
                            "tool_input": {"file_path": "/proc/self/environ"}}, Path(tmp))
            self.assertEqual(decision(res), "deny")

    def test_bash_catting_proc_environ_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook({"tool_name": "Bash", "cwd": tmp,
                            "tool_input": {"command": "cat /proc/self/environ"}}, Path(tmp))
            self.assertEqual(decision(res), "deny")

    def test_deny_is_logged_to_the_hash_chained_ledger(self):
        # env-guard had no ledger before WS3-T2; a deny now joins the shared
        # tamper-evident chain with its actor fields, and the chain verifies.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res = run_hook({"tool_name": "Read", "cwd": tmp,
                            "session_id": "sess-env",
                            "hook_event_name": "PreToolUse",
                            "tool_input": {"file_path": "/proc/self/environ"}}, root)
            self.assertEqual(decision(res), "deny")
            log = root / ".claude" / "ce-guard-log.jsonl"
            self.assertTrue(log.is_file())
            entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(entry["guard"], "env-guard")
            self.assertEqual(entry["decision"], "deny")
            self.assertEqual(entry["session_id"], "sess-env")
            self.assertEqual(entry["tool"], "Read")
            self.assertEqual(entry["prev"], "")  # genesis
            self.assertEqual(len(entry["payload_sha256"]), 64)
            verify = subprocess.run(
                [sys.executable,
                 str(REPO / "plugins/core-engineering/hooks/guard_log.py"),
                 "--verify", str(log)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(verify.returncode, 0, verify.stderr)

    def test_out_of_workspace_dotenv_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / ".env").write_text("SECRET=x", encoding="utf-8")
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            res = run_hook({"tool_name": "Read", "cwd": str(workspace),
                            "tool_input": {"file_path": str(outside / ".env")}}, workspace)
            self.assertEqual(decision(res), "deny")

    def test_in_workspace_dotenv_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("LOCAL=ok", encoding="utf-8")
            res = run_hook({"tool_name": "Read", "cwd": tmp,
                            "tool_input": {"file_path": str(root / ".env")}}, root)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")  # allowed silently

    def test_unrelated_read_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("hi", encoding="utf-8")
            res = run_hook({"tool_name": "Read", "cwd": tmp,
                            "tool_input": {"file_path": str(root / "README.md")}}, root)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")

    def test_non_guarded_tool_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook({"tool_name": "Write", "cwd": tmp,
                            "tool_input": {"file_path": "/proc/self/environ"}}, Path(tmp))
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")

    def test_unparseable_payload_is_loud_nonblocking(self):
        # Documented posture: exit 1 (non-blocking) + a loud stderr warning, NOT
        # a hard deny — a malformed payload cannot carry a guarded read, and
        # bricking every Read/Grep/Bash on harness drift is worse than a warn.
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook("not json at all", Path(tmp))
            self.assertEqual(res.returncode, 1)
            self.assertEqual(res.stdout.strip(), "")  # no permission decision emitted
            self.assertIn("secrets screen was NOT applied", res.stderr)

    def test_non_object_json_is_loud_nonblocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run_hook("[1, 2, 3]", Path(tmp))
            self.assertEqual(res.returncode, 1)
            self.assertIn("secrets screen was NOT applied", res.stderr)


class CorpusHomePaths(unittest.TestCase):
    """home_path corpus entries deny a credential store regardless of cwd — the
    workspace/outside distinction basename entries make does NOT apply here."""

    def test_reading_aws_credentials_is_denied_regardless_of_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            (home / ".aws").mkdir(parents=True)
            (home / ".aws" / "credentials").write_text("[default]\n", encoding="utf-8")
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            res = run_hook(
                {"tool_name": "Read", "cwd": str(workspace),
                 "tool_input": {"file_path": str(home / ".aws" / "credentials")}},
                workspace, extra_env={"HOME": str(home)})
            self.assertEqual(decision(res), "deny")

    def test_reading_aws_credentials_via_tilde_bash_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            (home / ".aws").mkdir(parents=True)
            (home / ".aws" / "credentials").write_text("[default]\n", encoding="utf-8")
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            res = run_hook(
                {"tool_name": "Bash", "cwd": str(workspace),
                 "tool_input": {"command": "cat ~/.aws/credentials"}},
                workspace, extra_env={"HOME": str(home)})
            self.assertEqual(decision(res), "deny")

    def test_workspace_symlink_to_ssh_private_key_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            (home / ".ssh").mkdir(parents=True)
            (home / ".ssh" / "id_rsa").write_text("-----BEGIN-----\n", encoding="utf-8")
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            link = workspace / "innocent"
            link.symlink_to(home / ".ssh" / "id_rsa")
            res = run_hook(
                {"tool_name": "Read", "cwd": str(workspace),
                 "tool_input": {"file_path": str(link)}},
                workspace, extra_env={"HOME": str(home)})
            self.assertEqual(decision(res), "deny")

    def test_home_credential_store_is_denied_even_if_workspace_is_under_home(self):
        # A project living under $HOME must not disable the home_path rule.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            (home / ".kube").mkdir(parents=True)
            (home / ".kube" / "config").write_text("apiVersion: v1\n", encoding="utf-8")
            workspace = home / "projects" / "app"
            workspace.mkdir(parents=True)
            res = run_hook(
                {"tool_name": "Read", "cwd": str(workspace),
                 "tool_input": {"file_path": str(home / ".kube" / "config")}},
                workspace, extra_env={"HOME": str(home)})
            self.assertEqual(decision(res), "deny")


class CorpusBasenames(unittest.TestCase):
    """basename corpus entries keep the outside-the-workspace containment test —
    the project's own file stays readable; the same basename outside is denied."""

    def test_out_of_workspace_npmrc_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / ".npmrc").write_text("//r/:_authToken=x", encoding="utf-8")
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            res = run_hook(
                {"tool_name": "Read", "cwd": str(workspace),
                 "tool_input": {"file_path": str(outside / ".npmrc")}}, workspace)
            self.assertEqual(decision(res), "deny")

    def test_in_workspace_npmrc_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".npmrc").write_text("registry=https://r/", encoding="utf-8")
            res = run_hook(
                {"tool_name": "Read", "cwd": tmp,
                 "tool_input": {"file_path": str(root / ".npmrc")}}, root)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")

    def test_out_of_workspace_pem_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / "server.pem").write_text("-----BEGIN-----\n", encoding="utf-8")
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            res = run_hook(
                {"tool_name": "Read", "cwd": str(workspace),
                 "tool_input": {"file_path": str(outside / "server.pem")}}, workspace)
            self.assertEqual(decision(res), "deny")

    def test_in_workspace_pem_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cert.pem").write_text("-----BEGIN-----\n", encoding="utf-8")
            res = run_hook(
                {"tool_name": "Read", "cwd": tmp,
                 "tool_input": {"file_path": str(root / "cert.pem")}}, root)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")


class BashRelativePathAsymmetry(unittest.TestCase):
    """The fixed Bash asymmetry: a relative token that cwd-joins to an
    out-of-workspace guarded file is now caught, matching the Read/Grep branch."""

    def test_bash_relative_out_of_workspace_dotenv_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside_env = Path(tmp) / ".env"  # parent of the workspace
            outside_env.write_text("SECRET=x", encoding="utf-8")
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            res = run_hook(
                {"tool_name": "Bash", "cwd": str(workspace),
                 "tool_input": {"command": "cat ../.env"}}, workspace)
            self.assertEqual(decision(res), "deny")

    def test_bash_relative_in_workspace_dotenv_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("LOCAL=ok", encoding="utf-8")
            res = run_hook(
                {"tool_name": "Bash", "cwd": tmp,
                 "tool_input": {"command": "cat ./.env"}}, root)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")


class CorpusResilience(unittest.TestCase):
    """A missing/corrupt guarded-secrets.json degrades LOUDLY to the built-in
    environ+dotenv floor — never fatal, never a silent loss of coverage."""

    def test_corrupt_corpus_keeps_dotenv_floor_and_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            corrupt = Path(tmp) / "bad.json"
            corrupt.write_text("{ this is not valid json", encoding="utf-8")
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / ".env").write_text("SECRET=x", encoding="utf-8")
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            res = run_hook(
                {"tool_name": "Read", "cwd": str(workspace),
                 "tool_input": {"file_path": str(outside / ".env")}},
                workspace, extra_env={"CE_GUARDED_SECRETS": str(corrupt)})
            self.assertEqual(decision(res), "deny")  # dotenv floor still enforced
            self.assertIn("falling back to the built-in", res.stderr)

    def test_corrupt_corpus_drops_home_path_coverage(self):
        # Proof the fallback is the FLOOR (no home_path), not the full corpus:
        # an ~/.aws/credentials read that the real corpus denies now passes.
        with tempfile.TemporaryDirectory() as tmp:
            corrupt = Path(tmp) / "bad.json"
            corrupt.write_text("not json", encoding="utf-8")
            home = Path(tmp) / "home"
            (home / ".aws").mkdir(parents=True)
            (home / ".aws" / "credentials").write_text("[default]\n", encoding="utf-8")
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            res = run_hook(
                {"tool_name": "Read", "cwd": str(workspace),
                 "tool_input": {"file_path": str(home / ".aws" / "credentials")}},
                workspace, extra_env={"HOME": str(home),
                                      "CE_GUARDED_SECRETS": str(corrupt)})
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")  # floor has no home_path entry
            self.assertIn("falling back to the built-in", res.stderr)


class DirectoryTargetedHomeStoreReads(unittest.TestCase):
    """Regression — HIGH directory/recursive-read bypass. Before the fix, the
    home_path check was file-glob-only, so a directory token (`~/.ssh`, `~/.aws`,
    `~`) matched no glob and screen_path fell through to a silent ALLOW: `grep -r`
    / `cp -r` / `tar` / the Grep tool read the exact bytes `cat ~/.ssh/id_rsa` is
    denied for. The store directory and its ancestors are now guarded."""

    def _home_ws(self, tmp):
        home = Path(tmp) / "home"
        (home / ".ssh").mkdir(parents=True)
        (home / ".ssh" / "id_rsa").write_text("-----BEGIN-----\n", encoding="utf-8")
        (home / ".aws").mkdir(parents=True)
        (home / ".aws" / "credentials").write_text("[default]\n", encoding="utf-8")
        ws = Path(tmp) / "ws"
        ws.mkdir()
        return home, ws

    def _bash(self, cmd, home, ws):
        return run_hook({"tool_name": "Bash", "cwd": str(ws),
                         "tool_input": {"command": cmd}},
                        ws, extra_env={"HOME": str(home)})

    def test_grep_recursive_ssh_dir_is_denied(self):
        # `grep -r x ~/.ssh` dumps id_rsa lines — was ALLOW, must be DENY.
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._home_ws(tmp)
            self.assertEqual(decision(self._bash("grep -r x ~/.ssh", home, ws)), "deny")

    def test_cp_recursive_ssh_dir_into_workspace_is_denied(self):
        # `cp -r ~/.ssh ./stolen` copies id_rsa INTO the workspace — DENY at source.
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._home_ws(tmp)
            self.assertEqual(decision(self._bash("cp -r ~/.ssh ./stolen", home, ws)), "deny")

    def test_tar_of_ssh_dir_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._home_ws(tmp)
            self.assertEqual(decision(self._bash("tar cf out.tar ~/.ssh", home, ws)), "deny")

    def test_grep_recursive_aws_dir_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._home_ws(tmp)
            self.assertEqual(decision(self._bash("grep -r x ~/.aws", home, ws)), "deny")

    def test_grep_recursive_home_itself_is_denied(self):
        # `grep -r x ~` — HOME is an ancestor of every store, so the token is denied.
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._home_ws(tmp)
            self.assertEqual(decision(self._bash("grep -r x ~", home, ws)), "deny")

    def test_grep_tool_pointed_at_ssh_dir_is_denied(self):
        # The Grep TOOL with path=~/.ssh (a directory) — the same bytes as grep -r.
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._home_ws(tmp)
            res = run_hook({"tool_name": "Grep", "cwd": str(ws),
                            "tool_input": {"path": str(home / ".ssh"), "pattern": "PRIV"}},
                           ws, extra_env={"HOME": str(home)})
            self.assertEqual(decision(res), "deny")

    def test_specific_noncredential_file_in_store_dir_stays_allowed(self):
        # The ancestor test is bounded: it guards the store DIRECTORY and its
        # ancestors, not every descendant — a specific non-guarded file inside
        # ~/.aws (no corpus entry, no basename glob) is not the agent's target and
        # stays readable, so the fix does not become an over-broad ~/.aws blackout.
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._home_ws(tmp)
            (home / ".aws" / "cli-history.txt").write_text("aws s3 ls\n", encoding="utf-8")
            res = run_hook({"tool_name": "Read", "cwd": str(ws),
                            "tool_input": {"file_path": str(home / ".aws" / "cli-history.txt")}},
                           ws, extra_env={"HOME": str(home)})
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")

    def test_in_workspace_recursive_grep_stays_allowed_under_home(self):
        # A project living UNDER $HOME must keep normal recursive in-workspace
        # reads: the workspace is a sibling of the stores, never an ancestor.
        with tempfile.TemporaryDirectory() as tmp:
            home, _ = self._home_ws(tmp)
            ws = home / "projects" / "app"
            (ws / "src").mkdir(parents=True)
            (ws / "src" / "main.py").write_text("print(1)\n", encoding="utf-8")
            res = run_hook({"tool_name": "Bash", "cwd": str(ws),
                            "tool_input": {"command": "grep -r x ."}},
                           ws, extra_env={"HOME": str(home)})
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")


class SplitQuotedHomeExpansion(unittest.TestCase):
    """Regression — HIGH split-quoted $HOME bypass. Before the fix, `raw` stripped
    only the OUTER quote pair, so `"$HOME"/.aws/credentials` stayed `$HOME"/...`,
    failed the literal `$HOME/` prefix test, and yielded an un-expandable relative
    token → silent ALLOW. Quotes are now fully collapsed, so idiomatic quoted
    variables expand and the home store is denied."""

    def _home_ws(self, tmp):
        home = Path(tmp) / "home"
        (home / ".aws").mkdir(parents=True)
        (home / ".aws" / "credentials").write_text("[default]\n", encoding="utf-8")
        ws = Path(tmp) / "ws"
        ws.mkdir()
        return home, ws

    def _bash(self, cmd, home, ws):
        return run_hook({"tool_name": "Bash", "cwd": str(ws),
                         "tool_input": {"command": cmd}},
                        ws, extra_env={"HOME": str(home)})

    def test_double_quoted_HOME_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._home_ws(tmp)
            self.assertEqual(
                decision(self._bash('cat "$HOME"/.aws/credentials', home, ws)), "deny")

    def test_braced_quoted_HOME_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._home_ws(tmp)
            self.assertEqual(
                decision(self._bash('cat "${HOME}"/.aws/credentials', home, ws)), "deny")

    def test_mixed_quote_HOME_is_denied(self):
        # `cat $HOME"/.aws/credentials"` — quote on the path half, not the var.
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._home_ws(tmp)
            self.assertEqual(
                decision(self._bash('cat $HOME"/.aws/credentials"', home, ws)), "deny")

    def test_split_quoted_basename_out_of_workspace_is_denied(self):
        # The same outer-strip bug also slipped split-quoted basename paths:
        # `cat ../outside"/.env"` must normalize and deny out-of-workspace .env.
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / ".env").write_text("SECRET=x", encoding="utf-8")
            ws = Path(tmp) / "outside" / "ws"  # sibling under a common parent
            ws.mkdir()
            res = run_hook({"tool_name": "Bash", "cwd": str(ws),
                            "tool_input": {"command": 'cat ../".env"'}}, ws)
            self.assertEqual(decision(res), "deny")

    def test_unquoted_HOME_still_denied(self):
        # Guard against a regression in the direction that already worked.
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._home_ws(tmp)
            self.assertEqual(
                decision(self._bash("cat $HOME/.aws/credentials", home, ws)), "deny")


class BareNameSymlinkViaBash(unittest.TestCase):
    """Regression — MEDIUM bare-name Bash token bypass. Before the fix, the Bash
    tokenizer yielded a token only if it started with '/' or contained '/' or
    started with '.', so a bare filename (`server`) was never yielded and its
    symlink target never realpath-resolved — Read/Grep denied it, Bash allowed it.
    Bare relative tokens are now yielded and screened symmetrically."""

    def _ws_with_links(self, tmp):
        home = Path(tmp) / "home"
        (home / ".aws").mkdir(parents=True)
        (home / ".aws" / "credentials").write_text("[default]\n", encoding="utf-8")
        outside = Path(tmp) / "outside"
        outside.mkdir()
        (outside / ".env").write_text("SECRET=x", encoding="utf-8")
        ws = Path(tmp) / "ws"
        ws.mkdir()
        (ws / "server").symlink_to(home / ".aws" / "credentials")
        (ws / "server.pem").symlink_to(home / ".aws" / "credentials")
        (ws / "notes.txt").symlink_to(outside / ".env")
        (ws / "README.md").write_text("hi", encoding="utf-8")
        return home, ws

    def _bash(self, cmd, home, ws):
        return run_hook({"tool_name": "Bash", "cwd": str(ws),
                         "tool_input": {"command": cmd}},
                        ws, extra_env={"HOME": str(home)})

    def test_bare_name_symlink_to_home_store_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._ws_with_links(tmp)
            self.assertEqual(decision(self._bash("cat server", home, ws)), "deny")

    def test_bare_name_symlink_to_out_of_workspace_dotenv_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._ws_with_links(tmp)
            self.assertEqual(decision(self._bash("cat notes.txt", home, ws)), "deny")

    def test_bash_and_read_agree_on_the_bare_symlink(self):
        # The asymmetry the fix closes: `cat server` (Bash) and Read{server} must
        # both DENY on the same planted symlink.
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._ws_with_links(tmp)
            bash = self._bash("cat server", home, ws)
            read = run_hook({"tool_name": "Read", "cwd": str(ws),
                             "tool_input": {"file_path": "server"}},
                            ws, extra_env={"HOME": str(home)})
            self.assertEqual(decision(bash), "deny")
            self.assertEqual(decision(read), "deny")

    def test_bare_command_word_and_real_file_stay_allowed(self):
        # False-positive bound: yielding bare tokens must not deny ordinary words
        # (`cat`) or a genuine in-workspace bare-name read (`README.md`).
        with tempfile.TemporaryDirectory() as tmp:
            home, ws = self._ws_with_links(tmp)
            res = self._bash("cat README.md", home, ws)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")


class OutOfWorkspaceDirectoryWithSecret(unittest.TestCase):
    """Regression — the `basename`-class directory-read extension: a directory
    OUTSIDE the workspace that directly holds a guarded-basename secret is denied
    (immediate children only, bounded), while an out-of-workspace directory with
    no secret stays readable."""

    def test_recursive_read_of_outside_dir_holding_dotenv_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / ".env").write_text("SECRET=x", encoding="utf-8")
            ws = Path(tmp) / "ws"
            ws.mkdir()
            res = run_hook({"tool_name": "Bash", "cwd": str(ws),
                            "tool_input": {"command": f"grep -r x {outside}"}}, ws)
            self.assertEqual(decision(res), "deny")

    def test_recursive_read_of_outside_dir_without_secret_stays_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / "README.md").write_text("docs", encoding="utf-8")
            ws = Path(tmp) / "ws"
            ws.mkdir()
            res = run_hook({"tool_name": "Bash", "cwd": str(ws),
                            "tool_input": {"command": f"grep -r x {outside}"}}, ws)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
