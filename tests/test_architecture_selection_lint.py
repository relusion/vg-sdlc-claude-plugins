"""Unit and CLI coverage for architecture-selection-lint.py."""

import copy
import hashlib
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
    / "plugins/core-engineering/skills/ce-plan-audit/scripts/architecture-selection-lint.py"
)

_spec = importlib.util.spec_from_file_location("architecture_selection_lint_mod", SCRIPT)
sl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sl)


WEIGHTS = (0.25, 0.20, 0.15, 0.15, 0.15, 0.10)


def _option(option_id: str, constraints: list[dict], score: int) -> dict:
    option = {
        "option_id": option_id,
        "title": f"Direction {option_id}",
        "summary": f"Complete solution direction {option_id}.",
        "responsibilities_and_boundaries": ["Application and data responsibilities are explicit."],
        "runtime_and_deployment": ["One regional application runtime and managed database."],
        "data_ownership": ["Application owns invitations; identity service owns membership."],
        "integrations_and_failure": ["HTTPS integration fails closed with explicit retries."],
        "trust_residency_and_security": ["Personal data remains in the required region."],
        "quality_tactics": ["Idempotency and queue-depth observability."],
        "migration_and_evolution": ["Additive migration with a reversible cutover."],
        "capability_implications": ["Supports invitation creation and acceptance."],
        "assumptions": ["Existing identity API remains available."],
        "irreversible_commitments": ["No irreversible commitment before cutover."],
        "constraint_verdicts": [
            {
                "constraint_id": row["id"],
                "verdict": "pass",
                "basis": f"{option_id} satisfies {row['id']}.",
            }
            for row in constraints
        ],
        "scores": [
            {
                "criterion_id": criterion,
                "score": score,
                "evidence_state": "recorded",
                "evidence": ["docs/briefs/smoke.md"],
            }
            for criterion in sl.CRITERIA
        ],
        "weighted_score": score,
        "confidence": "high",
        "option_sha256": "",
    }
    option["option_sha256"] = sl.option_hash(option)
    return option


def build_artifact(root: Path, *, option_count: int = 2) -> tuple[Path, dict]:
    source = root / "docs/briefs/smoke.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Approved brief\n\nKeep invitation data in-region.\n", encoding="utf-8")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    sources = [{"path": "docs/briefs/smoke.md", "sha256": source_hash, "kind": "brief"}]
    criteria = [
        {"id": criterion, "weight": weight, "basis": f"Priority for {criterion}."}
        for criterion, weight in zip(sl.CRITERIA, WEIGHTS)
    ]
    constraints = [
        {
            "id": "HC01",
            "statement": "Personal data remains in-region.",
            "basis": "Approved brief.",
            "authority": "Product and compliance owner.",
        }
    ]
    options = [
        _option(f"A0{index}", constraints, 5 if index == 1 else 4)
        for index in range(1, option_count + 1)
    ]
    selected = options[0] if options else None
    option_set_sha256 = sl.option_set_hash(options, [])
    evaluation_frame = {
        "project_intent": "Add team invitations without widening product scope.",
        "non_goals": ["Replace the identity provider."],
        "architecture_applicability": "required",
        "driver_screen": [
            {
                "id": driver_id,
                "verdict": "positive" if index == 0 else "negative",
                "basis": f"Recorded applicability basis for {driver_id}.",
                "evidence": ["docs/briefs/smoke.md"],
            }
            for index, driver_id in enumerate(sl.DRIVER_IDS)
        ],
        "accepted_decisions": [],
        "material_gaps": [],
        "capabilities": [
            {
                "id": "C01",
                "outcome": "An administrator can invite a teammate.",
                "actors": ["administrator"],
                "data": ["invitation"],
                "integrations": ["identity provider"],
                "observable": "The invitation is visible and deliverable.",
            }
        ],
        "journeys": [
            {
                "id": "J01",
                "outcome": "A teammate joins the workspace.",
                "actors": ["administrator", "invitee"],
                "capability_refs": ["C01"],
                "steps": ["Create, deliver, and accept an invitation."],
                "observable": "The invitee becomes an active teammate.",
            }
        ],
        "quality_attribute_scenarios": [
            {
                "id": "QA01",
                "attribute": "security",
                "stimulus": "An invalid invitation token is submitted.",
                "environment": "normal operation",
                "response": "Reject the request without membership mutation.",
                "target": "no unauthorized membership write",
                "priority": "must",
                "evidence": ["docs/briefs/smoke.md"],
            }
        ],
    }
    data = {
        "schema_version": 1,
        "project_slug": "smoke",
        "exploration_id": f"AEX-{option_set_sha256[:12]}",
        "source_capability_revision": 1,
        "source_exploration_attempt": 1,
        "source_input_sha256": "0" * 64,
        "evaluation_frame": evaluation_frame,
        "blocking_decision": None,
        "sources": sources,
        "evidence_fingerprint": sl.canonical_sha256(sources),
        "criteria": criteria,
        "hard_constraints": constraints,
        "options": options,
        "eliminated_options": [],
        "option_set_sha256": option_set_sha256,
        "recommendation": {
            "option_id": selected["option_id"] if selected else None,
            "confidence": "high",
            "sensitivity": "stable" if len(options) > 1 else "not-applicable",
            "sensitivity_witness": None,
            "basis": "Best evidence-backed fit across the confirmed frame.",
        },
        "selection": {
            "status": "direction-selected",
            "option_id": selected["option_id"] if selected else None,
            "option_sha256": selected["option_sha256"] if selected else None,
            "decided_by": "human",
            "rationale": "Select the strongest eligible direction.",
        },
        "next_owner": "ce-plan",
    }
    data["source_input_sha256"] = sl.source_input_hash(data)
    artifact = root / "docs/plans/smoke/architecture-selection.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return artifact, data


def write_artifact(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def rehash(data: dict) -> None:
    if "evaluation_frame" in data:
        data["source_input_sha256"] = sl.source_input_hash(data)
    for option in data.get("options", []):
        if isinstance(option, dict):
            option["option_sha256"] = sl.option_hash(option)
    selection = data.get("selection", {})
    if selection.get("option_id") is not None:
        match = next(
            (o for o in data["options"] if o.get("option_id") == selection["option_id"]),
            None,
        )
        if match is not None:
            selection["option_sha256"] = match["option_sha256"]
    data["option_set_sha256"] = sl.option_set_hash(
        data.get("options", []), data.get("eliminated_options", [])
    )
    if data.get("selection", {}).get("status") in sl.SELECTED_STATUSES:
        data["exploration_id"] = f"AEX-{data['option_set_sha256'][:12]}"


class SelectionContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def lint(self, artifact: Path, *, allow_incomplete=False):
        return sl.validate_file(
            artifact, repo_root=self.root, allow_incomplete=allow_incomplete
        )[1]

    def test_valid_selected_artifact_passes(self):
        artifact, _ = build_artifact(self.root)
        self.assertEqual(self.lint(artifact), [])

    def test_exploration_requires_two_to_four_options(self):
        artifact, _ = build_artifact(self.root, option_count=0)
        failures = self.lint(artifact)
        self.assertTrue(any("between 1 and 4" in item for item in failures), failures)

        one_root = self.root / "one"
        artifact, data = build_artifact(one_root, option_count=1)
        failures = sl.validate_file(artifact, repo_root=one_root)[1]
        self.assertTrue(any("at least two genuine directions" in item for item in failures), failures)

        data["selection"]["status"] = "adopted-existing"
        rehash(data)
        write_artifact(artifact, data)
        self.assertEqual(sl.validate_file(artifact, repo_root=one_root)[1], [])

        other_root = self.root / "five"
        artifact, _ = build_artifact(other_root, option_count=5)
        failures = sl.validate_file(artifact, repo_root=other_root)[1]
        self.assertTrue(any("at most 4" in item for item in failures), failures)
        self.assertTrue(any("A01 through A04" in item for item in failures), failures)

    def test_option_ids_must_be_unique_sorted_and_canonical(self):
        artifact, data = build_artifact(self.root)
        data["options"][1]["option_id"] = "A01"
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("duplicate option_id" in item for item in failures), failures)

    def test_all_structural_arrays_are_required_and_nonempty(self):
        artifact, data = build_artifact(self.root)
        data["options"][0]["runtime_and_deployment"] = []
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("runtime_and_deployment must not be empty" in item for item in failures))

    def test_criteria_are_exact_weighted_and_scores_are_recomputed(self):
        artifact, data = build_artifact(self.root)
        data["criteria"][0]["weight"] = 0.30
        data["options"][0]["scores"][0]["score"] = 3
        # Deliberately leave weighted_score stale, but refresh the content hash.
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        joined = " ".join(failures)
        self.assertIn("weights must sum to 1", joined)
        self.assertIn("weighted_score must equal", joined)

    def test_zero_weight_is_valid_when_the_human_frame_still_sums_to_one(self):
        artifact, data = build_artifact(self.root)
        data["criteria"][0]["weight"] = 0
        data["criteria"][1]["weight"] = 0.45
        rehash(data)
        write_artifact(artifact, data)
        self.assertEqual(self.lint(artifact), [])

    def test_deferred_disposition_preserves_frame_but_has_no_fake_options(self):
        artifact, data = build_artifact(self.root)
        data["evaluation_frame"]["architecture_applicability"] = "recommended"
        for row in data["evaluation_frame"]["driver_screen"]:
            row["verdict"] = "negative"
        data["evaluation_frame"]["driver_screen"][
            len(sl.REQUIRED_DRIVER_IDS)
        ]["verdict"] = "positive"
        data["options"] = []
        data["eliminated_options"] = []
        data["option_set_sha256"] = sl.option_set_hash([], [])
        data["recommendation"].update(
            {"option_id": None, "sensitivity": "not-applicable"}
        )
        data["selection"] = {
            "status": "deferred",
            "option_id": None,
            "option_sha256": None,
            "decided_by": "human",
            "rationale": "Defer recommended exploration with the coverage gap visible.",
        }
        rehash(data)
        write_artifact(artifact, data)
        self.assertEqual(self.lint(artifact), [])

        data["criteria"] = []
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("six canonical ids" in item for item in failures), failures)

        _, replacement = build_artifact(self.root / "replacement")
        data["criteria"] = replacement["criteria"]
        data["options"] = replacement["options"]
        data["option_set_sha256"] = sl.option_set_hash(data["options"], [])
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("requires an empty options array" in item for item in failures), failures)

    def test_score_requires_evidence_tag_and_evidence(self):
        artifact, data = build_artifact(self.root)
        data["options"][0]["scores"][0]["evidence_state"] = "measured"
        data["options"][0]["scores"][0]["evidence"] = []
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        joined = " ".join(failures)
        self.assertIn("evidence_state", joined)
        self.assertIn("evidence must not be empty", joined)

    def test_score_evidence_is_bound_to_the_source_inventory(self):
        artifact, data = build_artifact(self.root)
        data["options"][0]["scores"][0]["evidence"] = ["missing.md"]
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(
            any("absent from top-level sources" in item for item in failures), failures
        )

    def test_source_input_hash_binds_the_canonical_decision_frame(self):
        artifact, data = build_artifact(self.root)
        data["source_input_sha256"] = "0" * 64
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("canonical decision-relevant" in item for item in failures), failures)

    def test_fail_constraint_is_eliminated_and_cannot_be_selected(self):
        artifact, data = build_artifact(self.root)
        bad = data["options"][1]
        bad["constraint_verdicts"][0]["verdict"] = "fail"
        bad["scores"] = []
        bad["weighted_score"] = None
        bad["confidence"] = "not-applicable"
        data["eliminated_options"] = [
            {
                "option_id": "A02",
                "constraint_ids": ["HC01"],
                "reason": "Violates the confirmed residency constraint.",
            }
        ]
        data["selection"]["option_id"] = "A02"
        data["recommendation"]["sensitivity"] = "not-applicable"
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("selected option has a fail/unknown" in item for item in failures))

    def test_hard_constraint_ids_use_the_stage_1a_namespace(self):
        artifact, data = build_artifact(self.root)
        data["hard_constraints"][0]["id"] = "HC-01"
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("must match HC[0-9]{2}" in item for item in failures), failures)

    def test_selected_option_can_pass_with_an_eliminated_comparator(self):
        artifact, data = build_artifact(self.root)
        bad = data["options"][1]
        bad["constraint_verdicts"][0]["verdict"] = "fail"
        bad["scores"] = []
        bad["weighted_score"] = None
        bad["confidence"] = "not-applicable"
        data["eliminated_options"] = [
            {
                "option_id": "A02",
                "constraint_ids": ["HC01"],
                "reason": "Violates the confirmed residency constraint.",
            }
        ]
        data["recommendation"]["sensitivity"] = "not-applicable"
        rehash(data)
        write_artifact(artifact, data)
        self.assertEqual(self.lint(artifact), [])

    def test_unknown_constraint_cannot_be_recommended_or_selected(self):
        artifact, data = build_artifact(self.root)
        unknown = data["options"][0]
        unknown["constraint_verdicts"][0]["verdict"] = "unknown"
        unknown["scores"] = []
        unknown["weighted_score"] = None
        unknown["confidence"] = "not-applicable"
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        joined = " ".join(failures)
        self.assertIn("recommendation.option_id cannot reference", joined)
        self.assertIn("selected option has a fail/unknown", joined)

    def test_unknown_comparator_forces_requires_evidence_before_selection(self):
        artifact, data = build_artifact(self.root)
        comparator = data["options"][1]
        comparator["constraint_verdicts"][0]["verdict"] = "unknown"
        comparator["scores"] = []
        comparator["weighted_score"] = None
        comparator["confidence"] = "not-applicable"
        data["recommendation"]["sensitivity"] = "not-applicable"
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("return requires-evidence" in item for item in failures), failures)

    def test_eliminated_ledger_exactly_covers_failed_options(self):
        artifact, data = build_artifact(self.root)
        data["options"][1]["constraint_verdicts"][0]["verdict"] = "fail"
        data["options"][1]["scores"] = []
        data["options"][1]["weighted_score"] = None
        data["options"][1]["confidence"] = "not-applicable"
        data["recommendation"]["sensitivity"] = "not-applicable"
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("exactly cover options" in item for item in failures), failures)

    def test_sensitivity_and_confidence_are_recomputed_from_evidence_ranges(self):
        artifact, data = build_artifact(self.root)
        for score in data["options"][0]["scores"]:
            score["evidence_state"] = "unknown"
            score["evidence"] = ["unknown: architecture tactic is not yet validated"]
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        joined = " ".join(failures)
        self.assertIn("confidence cannot be high", joined)
        self.assertIn("expected unstable", joined)
        self.assertIn("recommendation.confidence must be low", joined)

        data["options"][0]["confidence"] = "low"
        data["recommendation"]["confidence"] = "low"
        data["recommendation"]["sensitivity"] = "unstable"
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(
            any("requires a sensitivity_witness" in item for item in failures),
            failures,
        )

        data["recommendation"]["sensitivity_witness"] = {
            "scenario": "evidence-range",
            "criterion_id": None,
            "challenger_option_id": "A02",
            "evidence_bounds": {"recommended": "lower", "challenger": "upper"},
            "condition": (
                "At base weights with A01 at lower evidence bounds and A02 at "
                "upper evidence bounds, A02 ties or exceeds A01."
            ),
        }
        rehash(data)
        write_artifact(artifact, data)
        self.assertEqual(self.lint(artifact), [])

    def test_recommendation_must_reference_a_highest_scoring_option(self):
        artifact, data = build_artifact(self.root)
        data["recommendation"]["option_id"] = "A02"
        data["recommendation"]["sensitivity"] = "unstable"
        data["recommendation"]["confidence"] = "low"
        data["recommendation"]["sensitivity_witness"] = {
            "scenario": "base-score",
            "criterion_id": None,
            "challenger_option_id": "A01",
            "evidence_bounds": {"recommended": "exact", "challenger": "exact"},
            "condition": "At base weights with exact scores, A01 ties or exceeds A02.",
        }
        data["options"][1]["confidence"] = "low"
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("highest weighted-score" in item for item in failures), failures)

    def test_weight_perturbation_can_make_a_narrow_leader_unstable(self):
        artifact, data = build_artifact(self.root)
        a01, a02 = data["options"]
        for index, score in enumerate(a01["scores"]):
            score["score"] = 5 if index == 0 else 3
        for index, score in enumerate(a02["scores"]):
            score["score"] = 1 if index == 0 else 4
        a01["weighted_score"] = 3.5
        a02["weighted_score"] = 3.25
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("expected unstable" in item for item in failures), failures)

        a01["confidence"] = "low"
        data["recommendation"]["confidence"] = "low"
        data["recommendation"]["sensitivity"] = "unstable"
        data["recommendation"]["sensitivity_witness"] = {
            "scenario": "weight-minus-25",
            "criterion_id": "requirements-fit",
            "challenger_option_id": "A02",
            "evidence_bounds": {"recommended": "exact", "challenger": "exact"},
            "condition": (
                "With requirements-fit weight decreased by 25% and exact scores, "
                "A02 ties or exceeds A01."
            ),
        }
        rehash(data)
        write_artifact(artifact, data)
        self.assertEqual(self.lint(artifact), [])

    def test_sensitivity_witness_must_name_the_deterministic_flip(self):
        artifact, data = build_artifact(self.root)
        for score in data["options"][0]["scores"]:
            score["evidence_state"] = "unknown"
            score["evidence"] = ["unknown: architecture tactic is not yet validated"]
        data["options"][0]["confidence"] = "low"
        data["recommendation"].update(
            {
                "confidence": "low",
                "sensitivity": "unstable",
                "sensitivity_witness": {
                    "scenario": "weight-plus-25",
                    "criterion_id": "operability",
                    "challenger_option_id": "A02",
                    "evidence_bounds": {
                        "recommended": "lower",
                        "challenger": "upper",
                    },
                    "condition": "Generic prose cannot substitute for the computed flip.",
                },
            }
        )
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        joined = " ".join(failures)
        self.assertIn("sensitivity_witness.scenario", joined)
        self.assertIn("sensitivity_witness.criterion_id", joined)

    def test_weight_and_evidence_combination_is_explicit_and_recomputed(self):
        artifact, data = build_artifact(self.root)
        a01, a02 = data["options"]
        for score, value in zip(a01["scores"], (2, 2, 5, 5, 5, 5)):
            score["score"] = value
        for score, value in zip(a02["scores"], (5, 5, 2, 2, 2, 2)):
            score["score"] = value
        a01["scores"][0]["evidence_state"] = "inferred"
        a01["weighted_score"] = 3.65
        a02["weighted_score"] = 3.35
        a01["confidence"] = "low"
        data["recommendation"].update(
            {
                "confidence": "low",
                "sensitivity": "unstable",
                "sensitivity_witness": {
                    "scenario": "weight-plus-25",
                    "criterion_id": "requirements-fit",
                    "challenger_option_id": "A02",
                    "evidence_bounds": {
                        "recommended": "exact",
                        "challenger": "exact",
                    },
                    "condition": (
                        "Increasing requirements-fit weight alone makes A02 the leader."
                    ),
                },
            }
        )
        rehash(data)
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        joined = " ".join(failures)
        self.assertIn("sensitivity_witness.evidence_bounds", joined)
        self.assertIn("sensitivity_witness.condition", joined)

        data["recommendation"]["sensitivity_witness"] = {
            "scenario": "weight-plus-25",
            "criterion_id": "requirements-fit",
            "challenger_option_id": "A02",
            "evidence_bounds": {"recommended": "lower", "challenger": "upper"},
            "condition": (
                "With requirements-fit weight increased by 25%, A01 at lower "
                "evidence bounds, and A02 at upper evidence bounds, A02 ties or "
                "exceeds A01."
            ),
        }
        rehash(data)
        write_artifact(artifact, data)
        self.assertEqual(self.lint(artifact), [])

    def test_canonical_option_and_option_set_hashes_detect_tampering(self):
        artifact, data = build_artifact(self.root)
        data["options"][0]["summary"] = "Tampered without refreshing hashes."
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        joined = " ".join(failures)
        self.assertIn("option_sha256 mismatch", joined)

        artifact, data = build_artifact(self.root)
        data["option_set_sha256"] = "0" * 64
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("option_set_sha256 mismatch" in item for item in failures))

    def test_selected_exploration_id_is_content_addressed(self):
        artifact, data = build_artifact(self.root)
        data["exploration_id"] = "AEX-not-the-option-set"
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("selected exploration_id" in item for item in failures), failures)

    def test_source_order_fingerprint_and_file_freshness_are_enforced(self):
        artifact, data = build_artifact(self.root)
        second = self.root / "README.md"
        second.write_text("evidence\n", encoding="utf-8")
        data["sources"].insert(
            0,
            {
                "path": "README.md",
                "sha256": hashlib.sha256(second.read_bytes()).hexdigest(),
                "kind": "repository",
            },
        )
        # Reverse canonical order while keeping the matching fingerprint.
        data["sources"].reverse()
        data["evidence_fingerprint"] = sl.canonical_sha256(data["sources"])
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("sorted lexicographically" in item for item in failures), failures)

        artifact, _ = build_artifact(self.root)
        (self.root / "docs/briefs/smoke.md").write_text("drift\n", encoding="utf-8")
        failures = self.lint(artifact)
        self.assertTrue(any("is stale" in item for item in failures), failures)

    def test_source_kind_uses_the_versioned_evidence_vocabulary(self):
        artifact, data = build_artifact(self.root)
        data["sources"][0]["kind"] = "plan"
        data["evidence_fingerprint"] = sl.canonical_sha256(data["sources"])
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any(".kind must be one of" in item for item in failures), failures)

    def test_nonselected_final_status_uses_null_option_binding(self):
        artifact, data = build_artifact(self.root)
        data["hard_constraints"] = []
        data["options"] = []
        data["eliminated_options"] = []
        data["recommendation"] = {
            "option_id": None,
            "confidence": "high",
            "sensitivity": "not-applicable",
            "sensitivity_witness": None,
            "basis": "The admission screen found no architecture direction decision.",
        }
        data["selection"] = {
            "status": "not-applicable",
            "option_id": None,
            "option_sha256": None,
            "decided_by": "human",
            "rationale": "Architecture exploration is not applicable.",
        }
        data["evaluation_frame"]["architecture_applicability"] = "not-required"
        for row in data["evaluation_frame"]["driver_screen"]:
            row["verdict"] = "negative"
        rehash(data)
        write_artifact(artifact, data)
        self.assertEqual(self.lint(artifact), [])

    def test_transient_result_requires_allow_incomplete_and_cannot_claim_selection(self):
        artifact, data = build_artifact(self.root)
        keep = {
            "schema_version",
            "project_slug",
            "exploration_id",
            "source_capability_revision",
            "source_exploration_attempt",
            "source_input_sha256",
            "blocking_decision",
            "sources",
            "evidence_fingerprint",
            "selection",
            "next_owner",
        }
        data = {key: value for key, value in data.items() if key in keep}
        data["selection"] = {
            "status": "blocked",
            "option_id": None,
            "option_sha256": None,
            "decided_by": None,
            "rationale": "Required repository evidence is unavailable.",
        }
        write_artifact(artifact, data)
        self.assertTrue(self.lint(artifact), "default mode must reject transient status")
        self.assertEqual(self.lint(artifact, allow_incomplete=True), [])

        data["selection"]["option_id"] = "A01"
        write_artifact(artifact, data)
        failures = self.lint(artifact, allow_incomplete=True)
        self.assertTrue(any("transient selection.option_id must be null" in item for item in failures))

    def test_requires_decision_carries_a_supplied_bounded_option_frame(self):
        artifact, data = build_artifact(self.root)
        keep = set(sl.TRANSIENT_REQUIRED_TOP_KEYS)
        data = {key: value for key, value in data.items() if key in keep}
        data["selection"] = {
            "status": "requires-decision",
            "option_id": None,
            "option_sha256": None,
            "decided_by": None,
            "rationale": "One bounded transport fork changes option eligibility.",
        }
        data["blocking_decision"] = {
            "question": "Which delivery transport is authoritative?",
            "options": [
                {
                    "id": "D01",
                    "title": "Managed queue",
                    "consequence": "Adds a managed asynchronous dependency.",
                    "reversibility": "Replaceable behind the delivery boundary.",
                },
                {
                    "id": "D02",
                    "title": "Database outbox",
                    "consequence": "Keeps delivery state with application persistence.",
                    "reversibility": "Requires a migration to replace.",
                },
            ],
            "constraints": ["At-least-once delivery must be explicit."],
            "evidence": ["docs/briefs/smoke.md"],
            "cost_if_wrong": "The chosen architecture direction may be ineligible.",
        }
        write_artifact(artifact, data)
        self.assertEqual(self.lint(artifact, allow_incomplete=True), [])

        data["blocking_decision"] = None
        write_artifact(artifact, data)
        failures = self.lint(artifact, allow_incomplete=True)
        self.assertTrue(any("must supply a blocking_decision" in item for item in failures))

    def test_final_artifact_preserves_complete_evaluation_frame(self):
        artifact, data = build_artifact(self.root)
        del data["evaluation_frame"]["journeys"]
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("evaluation_frame missing key(s): journeys" in item for item in failures))

    def test_evaluation_frame_driver_screen_and_refs_are_consistent(self):
        artifact, data = build_artifact(self.root)
        data["evaluation_frame"]["architecture_applicability"] = "not-required"
        data["evaluation_frame"]["journeys"][0]["capability_refs"] = ["C99"]
        data["evaluation_frame"]["driver_screen"][0]["evidence"] = ["missing.md"]
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        joined = " ".join(failures)
        self.assertIn("contradicts driver_screen", joined)
        self.assertIn("unresolved id(s): C99", joined)
        self.assertIn("absent from top-level sources", joined)

    def test_final_status_cannot_carry_a_blocking_decision(self):
        artifact, data = build_artifact(self.root)
        data["blocking_decision"] = {
            "question": "This must not survive final selection.",
            "options": [],
            "constraints": [],
            "evidence": [],
            "cost_if_wrong": "Ambiguous ownership.",
        }
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("blocking_decision must be null" in item for item in failures))

    def test_attempt_starts_at_one(self):
        artifact, data = build_artifact(self.root)
        data["source_exploration_attempt"] = 0
        write_artifact(artifact, data)
        failures = self.lint(artifact)
        self.assertTrue(any("source_exploration_attempt" in item for item in failures))


class SelectionCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, artifact: Path, *extra: str):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(artifact),
                "--repo-root",
                str(self.root),
                "--json",
                *extra,
            ],
            capture_output=True,
            text=True,
        )

    def test_cli_pass_fail_and_error_exit_codes(self):
        artifact, data = build_artifact(self.root)
        result = self.run_cli(artifact)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pass")

        data["selection"]["decided_by"] = "agent"
        write_artifact(artifact, data)
        result = self.run_cli(artifact)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "fail")

        artifact.write_text("{not json", encoding="utf-8")
        result = self.run_cli(artifact)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "error")


if __name__ == "__main__":
    unittest.main()
