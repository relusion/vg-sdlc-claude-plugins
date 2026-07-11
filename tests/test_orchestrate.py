"""Unit tests for scripts/orchestrate.py's handoff extraction.

The reference loop's whole value is the extract -> allowlist -> schema-validate
shape, so the extraction must actually work on a schema-valid handoff — whose
`payload` is a nested JSON object. A lazy-regex implementation truncated at the
first `}` and could never steer; these tests pin the balanced-brace fix. The
handoff schema is intentionally small and validated in `orchestrate.py` itself,
so these tests run on bare Python; `anthropic` remains lazy and run()-only.
"""
import unittest
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "orchestrate.py"

def _load():
    spec = importlib.util.spec_from_file_location("orchestrate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VALID = (
    '{"type": "handoff_request", "target_agent": "spec-impl", '
    '"payload": {"event": "spec ready for 03-export", '
    '"context_ref": "docs/plans/demo/specs/03-export"}}'
)


class ExtractHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def test_schema_valid_nested_payload_extracts(self):
        # The regression case: payload is an object, so the blob nests braces.
        got = self.mod.extract_handoff(f"some narration\n{VALID}\nmore text")
        self.assertIsNotNone(got)
        self.assertEqual(got["target_agent"], "spec-impl")
        self.assertEqual(got["payload"]["event"], "spec ready for 03-export")

    def test_braces_inside_string_values_do_not_truncate(self):
        blob = (
            '{"type": "handoff_request", "target_agent": "spec-author", '
            '"payload": {"event": "review {scope} block done"}}'
        )
        got = self.mod.extract_handoff(blob)
        self.assertIsNotNone(got)
        self.assertEqual(got["payload"]["event"], "review {scope} block done")

    def test_quality_and_release_targets_extract(self):
        for target in ("quality-gate", "release-coordinator"):
            blob = (
                '{"type": "handoff_request", "target_agent": "' + target + '", '
                '"payload": {"event": "route docs/plans/demo", '
                '"context_ref": "docs/plans/demo"}}'
            )
            got = self.mod.extract_handoff(blob)
            self.assertIsNotNone(got)
            self.assertEqual(got["target_agent"], target)

    def test_trailing_close_braces_are_not_swallowed(self):
        got = self.mod.extract_handoff(VALID + "}}}")
        self.assertIsNotNone(got)
        self.assertEqual(got["target_agent"], "spec-impl")

    def test_no_handoff_returns_none(self):
        self.assertIsNone(self.mod.extract_handoff("plain narration, no blob"))

    def test_truncated_blob_returns_none(self):
        self.assertIsNone(self.mod.extract_handoff(VALID[:-2]))

    def test_disallowed_target_returns_none(self):
        blob = VALID.replace("spec-impl", "evil-agent")
        self.assertIsNone(self.mod.extract_handoff(blob))

    def test_missing_payload_fails_schema(self):
        blob = '{"type": "handoff_request", "target_agent": "spec-impl"}'
        self.assertIsNone(self.mod.extract_handoff(blob))

    def test_extra_payload_property_fails_schema(self):
        blob = (
            '{"type": "handoff_request", "target_agent": "spec-impl", '
            '"payload": {"event": "x", "shell": "rm -rf /"}}'
        )
        self.assertIsNone(self.mod.extract_handoff(blob))
