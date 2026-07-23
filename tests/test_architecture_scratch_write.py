"""Tests for ce-architecture's non-interpolating scratch writer."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-architecture/scripts/scratch-write.py"
SPEC = importlib.util.spec_from_file_location("architecture_scratch_write", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ScratchWriteTests(unittest.TestCase):
    def test_writes_untrusted_shell_text_as_literal_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            scratch = Path(td) / "owned"
            scratch.mkdir()
            payload = b"# View\n`touch /tmp/nope` $(printf nope) $HOME\n"
            target = MODULE.write_scratch(scratch, "views.md", payload)
            self.assertEqual(target.read_bytes(), payload)

    def test_rejects_noncanonical_filename(self):
        with tempfile.TemporaryDirectory() as td:
            scratch = Path(td) / "owned"
            scratch.mkdir()
            with self.assertRaisesRegex(ValueError, "not a canonical"):
                MODULE.write_scratch(scratch, "../escape.md", b"unsafe")

    def test_rejects_directory_outside_temp_root(self):
        with self.assertRaisesRegex(ValueError, "OS temporary"):
            MODULE.write_scratch(REPO, "views.md", b"# view\n")

    def test_validates_json_before_replacing_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            scratch = Path(td) / "owned"
            scratch.mkdir()
            target = scratch / "architecture.json"
            target.write_text(json.dumps({"old": True}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid"):
                MODULE.write_scratch(scratch, "architecture.json", b"{")
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"old": True})

    def test_architecture_json_requires_strict_schema_v2(self):
        with tempfile.TemporaryDirectory() as td:
            scratch = Path(td) / "owned"
            scratch.mkdir()
            with self.assertRaisesRegex(ValueError, "schema v2"):
                MODULE.write_scratch(
                    scratch,
                    "architecture.json",
                    json.dumps({"schema_version": 1}).encode("utf-8"),
                )
            payload = json.dumps(
                {
                    "$schema": MODULE.ARCHITECTURE_SCHEMA_URN,
                    "schema_version": MODULE.ARCHITECTURE_SCHEMA_VERSION,
                }
            ).encode("utf-8")
            self.assertEqual(
                MODULE.write_scratch(
                    scratch, "architecture.json", payload
                ).read_bytes(),
                payload,
            )

    def test_architecture_json_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as td:
            scratch = Path(td) / "owned"
            scratch.mkdir()
            payload = (
                b'{"$schema":"urn:vg-sdlc:ce-architecture:architecture:v2",'
                b'"schema_version":2,"schema_version":2}'
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                MODULE.write_scratch(scratch, "architecture.json", payload)


if __name__ == "__main__":
    unittest.main()
