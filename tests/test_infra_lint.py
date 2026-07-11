"""Fixture tests for probe-infra's infra-lint.py — the offline IaC/k8s/Dockerfile floor.

Asserts the 0/1/2 exit-code contract, the --json shape, the no-files require() path,
format detection, the X-COPY hard fact, the parser-free pattern hits, the bounded
unsupported-format recording, the overlay-context demotion signal, and — the safety
invariant — that NO raw secret value ever appears in any output for a known-secret
fixture.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-probe-infra/scripts/infra-lint.py"


def run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=30, cwd=cwd,
    )


def write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def run_json(root: Path, *extra):
    proc = run("--root", str(root), "--scope", str(root), "--json", *extra)
    return proc, json.loads(proc.stdout)


class ExitContract(unittest.TestCase):
    def test_bare_invocation_no_files_is_zero(self):
        # The portability-style invocation: bare, empty dir -> no-files, exit 0, no crash.
        with tempfile.TemporaryDirectory() as tmp:
            proc = run(cwd=tmp)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_no_files_status_is_not_a_clean_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "src/app.py", "print('hi')\n")  # not infra
            proc, data = run_json(root)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(data["status"], "no-files")
            self.assertEqual(data["supported_files"], 0)

    def test_missing_scope_is_error_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run("--root", tmp, "--scope", "does/not/exist", "--json")
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stdout)["status"], "error")

    def test_scope_escaping_root_is_error_not_traversal(self):
        # Regression: a `..`-laden --scope must not read outside --root.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "realroot"
            root.mkdir()
            write(Path(tmp), "outside.tf", 'storage_encrypted = false\n')
            proc = run("--root", str(root), "--scope", "../outside.tf", "--json")
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stdout)["status"], "error")


class HardChecks(unittest.TestCase):
    def test_xcopy_broken_source_is_hard_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "Dockerfile", "FROM python:3.12\nCOPY app/ /app\nUSER nobody\n")
            proc, data = run_json(root)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(data["status"], "fail")
            self.assertTrue(any(h["check"] == "X-COPY" for h in data["hard_failures"]))

    def test_xcopy_present_source_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "app/main.py", "x=1\n")
            write(root, "Dockerfile", "FROM python:3.12\nCOPY app/ /app\nUSER nobody\n")
            proc, data = run_json(root)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(data["hard_failures"], [])

    def test_xcopy_exempts_url_glob_and_buildstage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "Dockerfile",
                  "FROM build AS b\n"
                  "ADD https://example.com/x.tar /x\n"
                  "COPY *.txt /etc/\n"
                  "COPY --from=b /out /out\n"
                  "USER nobody\n")
            proc, data = run_json(root)
            self.assertEqual(data["hard_failures"], [])

    def test_xcopy_exempts_heredoc_and_shell_var(self):
        # Regression: BuildKit here-doc and bare $VAR sources must NOT be false HARD fails.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "Dockerfile",
                  "FROM alpine\n"
                  "ARG SRC=src\n"
                  "COPY <<FILE /app/config\ninline content\nFILE\n"
                  "COPY ${SRC}/app.bin /app/\n"
                  "COPY $APPDIR/x.txt /y/\n"
                  "USER nobody\n")
            proc, data = run_json(root)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(data["hard_failures"], [])


class PatternChecks(unittest.TestCase):
    def test_dockerfile_latest_and_no_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "Dockerfile", "FROM ubuntu:latest\nRUN echo hi\n")
            _, data = run_json(root)
            checks = {f["check"] for f in data["findings"]}
            self.assertIn("P-LATEST", checks)
            self.assertIn("P-NO-USER", checks)
            self.assertEqual(data["status"], "pass")  # advisory only, no hard fail

    def test_k8s_privileged_open_cidr_wildcard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "deploy.yaml",
                  "apiVersion: apps/v1\n"
                  "kind: Deployment\n"
                  "spec:\n"
                  "  template:\n"
                  "    spec:\n"
                  "      containers:\n"
                  "        - image: nginx\n"          # untagged -> P-LATEST
                  "          securityContext:\n"
                  "            privileged: true\n")   # -> P-PRIVILEGED
            write(root, "rbac.yaml",
                  "apiVersion: rbac.authorization.k8s.io/v1\n"
                  "kind: ClusterRole\n"
                  "rules:\n"
                  "  - verbs: [\"*\"]\n"
                  "    resources: [\"*\"]\n")
            write(root, "net.tf", 'cidr_blocks = ["0.0.0.0/0"]\n')
            _, data = run_json(root)
            checks = {f["check"] for f in data["findings"]}
            self.assertIn("P-PRIVILEGED", checks)
            self.assertIn("P-LATEST", checks)
            self.assertIn("P-WILDCARD-IAM", checks)
            self.assertIn("P-OPEN-INGRESS", checks)
            self.assertEqual(data["formats_detected"].get("k8s"), 2)
            self.assertEqual(data["formats_detected"].get("terraform"), 1)

    def test_terraform_unencrypted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "db.tf", 'resource "aws_db" "x" {\n  storage_encrypted = false\n}\n')
            _, data = run_json(root)
            self.assertTrue(any(f["check"] == "P-UNENCRYPTED" for f in data["findings"]))


class SecretRedaction(unittest.TestCase):
    SECRET = "AKIAIOSFODNN7EXAMPLE"          # canonical AWS example access key id
    HIGH_ENTROPY = "S3cr3tV4lue9xQ2zPmK7wL"  # generic high-entropy credential

    def test_known_secret_never_appears_in_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "Dockerfile",
                  f"FROM alpine:3.19\n"
                  f"ENV AWS_ACCESS_KEY_ID={self.SECRET}\n"
                  f"ENV DB_PASSWORD={self.HIGH_ENTROPY}\n"
                  f"USER nobody\n")
            proc, data = run_json(root)
            blob = proc.stdout + proc.stderr
            self.assertNotIn(self.SECRET, blob)
            self.assertNotIn(self.HIGH_ENTROPY, blob)
            self.assertGreaterEqual(data["secrets_redacted_count"], 1)
            self.assertTrue(any(f["check"] == "P-PLAINTEXT-SECRET" for f in data["findings"]))

    def test_two_secrets_on_one_line_both_redacted(self):
        # Regression: a SECOND secret sharing a line must not ride along in the excerpt.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "x.tf",
                  f'config = "password={self.HIGH_ENTROPY} token={self.SECRET}"\n')
            proc, data = run_json(root)
            blob = proc.stdout + proc.stderr
            self.assertNotIn(self.SECRET, blob)
            self.assertNotIn(self.HIGH_ENTROPY, blob)

    def test_aws_then_trailing_assignment_both_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "env.tf", f'key = "{self.SECRET}" ; pw = "{self.HIGH_ENTROPY}"\n')
            proc, _ = run_json(root)
            blob = proc.stdout + proc.stderr
            self.assertNotIn(self.SECRET, blob)
            self.assertNotIn(self.HIGH_ENTROPY, blob)

    def test_placeholder_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "vars.tf", 'password = "changeme"\ntoken = "${var.token}"\n')
            _, data = run_json(root)
            self.assertEqual(data["secrets_redacted_count"], 0)

    def test_k8s_secret_base64_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # base64 of the AWS example key -> must be detected and never emitted raw
            import base64
            blob = base64.b64encode(self.SECRET.encode()).decode()
            write(root, "secret.yaml",
                  "apiVersion: v1\n"
                  "kind: Secret\n"
                  "data:\n"
                  f"  awskey: {blob}\n")
            proc, data = run_json(root)
            self.assertNotIn(self.SECRET, proc.stdout + proc.stderr)
            self.assertGreaterEqual(data["secrets_redacted_count"], 1)


class UnsupportedAndOverlays(unittest.TestCase):
    def test_compose_and_helm_recorded_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "docker-compose.yml", "services:\n  web:\n    image: nginx:1.27\n")
            write(root, "chart/Chart.yaml", "apiVersion: v2\nname: x\nversion: 0.1.0\n")
            write(root, "chart/templates/deploy.yaml",
                  "apiVersion: apps/v1\nkind: Deployment\nspec: {{ .Values.x }}\n")
            _, data = run_json(root)
            fams = {u["format"] for u in data["unsupported_formats"]}
            self.assertIn("compose", fams)
            self.assertIn("helm", fams)
            # a Chart.yaml present -> overlay context recorded so the skill demotes X-REF
            self.assertTrue(data["overlay_context"])

    def test_supported_alongside_unsupported_still_audits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "compose.yaml", "services:\n  a:\n    image: r:1\n")
            write(root, "k.yaml", "apiVersion: v1\nkind: Pod\nspec:\n  hostNetwork: true\n")
            proc, data = run_json(root)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(data["formats_detected"].get("k8s"), 1)
            self.assertTrue(any(f["check"] == "P-PRIVILEGED" for f in data["findings"]))


if __name__ == "__main__":
    unittest.main()
