"""Contract tests for deterministic schema-v2 architecture projections."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO
    / "plugins/core-engineering/skills/ce-architecture/scripts/architecture-render.py"
)
FIXTURE = REPO / "tests/architecture_v2_fixture.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


renderer = _load(SCRIPT, "architecture_renderer_tests")
v2 = _load(FIXTURE, "architecture_renderer_fixture")


class ArchitectureRender(unittest.TestCase):
    def test_four_projection_contracts_have_exact_headings_and_headers(self):
        with tempfile.TemporaryDirectory() as td:
            _, manifest = v2.make_v2_repo(Path(td))
            documents = {
                path: payload.decode("utf-8")
                for path, payload in renderer.render_documents(manifest).items()
            }
            solution = documents["solution-architecture.md"]
            for heading in (
                "## Executive Summary",
                "## Scope and Non-Goals",
                "## Architecture Drivers",
                "## Selected Direction Realizations",
                "## Assumptions and Coverage Gaps",
                "## Open Questions",
                "## Validation Strategy",
            ):
                self.assertIn(heading, solution)
            self.assertNotIn("> Lifecycle:", solution)
            self.assertIn("Required dimensions:", solution)
            self.assertIn(
                "| Dimension | Required | Status | Gap IDs | Evidence |",
                solution,
            )
            self.assertIn(
                "| Question ID | Question | Status | Material | Owner |",
                solution,
            )

            views = documents["views.md"]
            self.assertIn(
                "| Boundary | Name | Responsibility | In scope | Out of scope |",
                views,
            )
            self.assertIn(
                "| Actor | Name | Kind | Roles | Features | Evidence state | Evidence |",
                views,
            )
            self.assertIn("## Transition Architecture", views)
            self.assertIn(
                "| Journey ref | Features | Evidence state | Evidence |",
                views,
            )
            self.assertIn("```mermaid", views)

            data = documents["data-and-integrations.md"]
            self.assertIn("## Trust Boundaries", data)
            self.assertIn("## Security and Privacy Re-Projection", data)
            self.assertIn("## Interaction Contract Realizations", data)

            quality = documents["quality-attributes.md"]
            self.assertIn("## Operations", quality)
            self.assertIn("## Quality and Operations Gaps", quality)
            self.assertIn(
                "| Operation | Name | Category | Responsibility | Owner |",
                quality,
            )

    def test_render_is_byte_deterministic_and_check_accepts_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            arch_dir, manifest = v2.make_v2_repo(Path(td))
            first = renderer.render_documents(manifest)
            second = renderer.render_documents(copy.deepcopy(manifest))
            self.assertEqual(first, second)
            result, code = renderer.check_package(arch_dir)
            self.assertEqual(code, 0, result)
            self.assertEqual(result["status"], "pass")

    def test_review_digest_survives_publish_only_mutations(self):
        with tempfile.TemporaryDirectory() as td:
            _, proposed = v2.make_v2_repo(Path(td))
            proposed_documents = renderer.render_documents(proposed)
            review = renderer.review_payload_sha256(proposed, proposed_documents)
            published = copy.deepcopy(proposed)
            published["lifecycle_status"] = "published"
            published["approval"] = {
                "decision": published["baseline_status"],
                "recorded_by": "architect@example.test",
                "recorded_at": "2026-07-23T10:30:00Z",
                "authority": "Solution Architecture Council",
                "reference": "REVIEW-123",
                "gate": renderer.FINAL_APPROVAL_GATE,
                "review_payload_sha256": review,
                "receipt_sha256": None,
            }
            published_documents = renderer.render_documents(published)
            self.assertEqual(published_documents, proposed_documents)
            self.assertEqual(
                renderer.review_payload_sha256(published, published_documents),
                review,
            )
            receipt = renderer.receipt_sha256(published, published_documents)
            published["approval"]["receipt_sha256"] = receipt
            self.assertEqual(
                renderer.receipt_sha256(published, published_documents),
                receipt,
            )

    def test_any_projection_byte_mutation_fails_check(self):
        with tempfile.TemporaryDirectory() as td:
            arch_dir, _ = v2.make_v2_repo(Path(td))
            path = arch_dir / "quality-attributes.md"
            path.write_bytes(path.read_bytes() + b"\nmanual edit\n")
            result, code = renderer.check_package(arch_dir)
            self.assertEqual(code, 1)
            self.assertTrue(
                any("deterministic projection differs" in item for item in result["mismatches"])
            )

    def test_finalize_review_replaces_stale_projection_and_review_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            _, manifest = v2.make_v2_repo(Path(td))
            manifest["projections"][0]["sha256"] = "0" * 64
            manifest["approval"] = copy.deepcopy(renderer.PENDING_APPROVAL)
            finalized, documents = renderer.finalize_review_manifest(manifest)
            self.assertEqual(
                finalized["projections"][0]["sha256"],
                renderer.projection_hashes(documents)["solution-architecture.md"],
            )
            self.assertRegex(
                finalized["approval"]["review_payload_sha256"],
                r"^[0-9a-f]{64}$",
            )

    def test_check_rejects_duplicate_manifest_keys(self):
        with tempfile.TemporaryDirectory() as td:
            arch_dir, _ = v2.make_v2_repo(Path(td))
            path = arch_dir / "architecture.json"
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace(
                    '"schema_version": 2,',
                    '"schema_version": 2,\n  "schema_version": 2,',
                    1,
                ),
                encoding="utf-8",
            )
            result, code = renderer.check_package(arch_dir)
            self.assertEqual(code, 2)
            self.assertIn("duplicate JSON object key", result["message"])

    def test_check_command_and_legacy_flag_emit_json(self):
        with tempfile.TemporaryDirectory() as td:
            arch_dir, _ = v2.make_v2_repo(Path(td))
            for command in (
                [sys.executable, str(SCRIPT), "check", str(arch_dir), "--json"],
                [sys.executable, str(SCRIPT), "--check", str(arch_dir), "--json"],
            ):
                with self.subTest(command=command[2]):
                    proc = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    self.assertEqual(
                        proc.returncode, 0, proc.stdout + proc.stderr
                    )
                    self.assertEqual(json.loads(proc.stdout)["status"], "pass")


if __name__ == "__main__":
    unittest.main()
