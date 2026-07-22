"""Regression tests for ce-plan's decision-ready HITL gate contract."""

import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PLAN = REPO / "plugins/core-engineering/skills/ce-plan"


def read(name: str) -> str:
    return (PLAN / name).read_text(encoding="utf-8")


def between(text: str, start: str, end: str) -> str:
    start_at = text.index(start)
    return text[start_at:text.index(end, start_at)]


class CePlanHitlContract(unittest.TestCase):
    def test_material_gate_contract_names_authority_and_safe_non_decision_paths(self):
        orchestrator = read("SKILL.md")

        self.assertIn("## Material-Gate Decision Authority", orchestrator)
        for anchor in (
            "Decision owner:",
            "Decision authority:",
            "Authority/evidence gaps:",
            "Need evidence / route to owner",
            "Park — stop without a final write",
        ):
            self.assertIn(anchor, orchestrator)
        self.assertIn("Do not infer authority from participation", orchestrator)
        self.assertIn("only an explicit **Start fresh**", orchestrator)

    def test_stage_one_and_sibling_plan_choices_are_decidable_in_place(self):
        intake = read("stage-0-1-understand.md")
        sibling = between(intake, "### Sibling Plans", "## Stage 1")
        questions = between(
            intake,
            "### 1.4 Ask Decomposition Questions",
            "### 1.5 Capture Project-Wide Reference Docs",
        )

        self.assertIn("Gate N of M — Sibling Plans", sibling)
        self.assertIn("Sibling relationship evidence", sibling)
        self.assertIn("Plan-local decisions or constraints to inherit", sibling)
        self.assertIn("Repository ADRs/patterns already global", sibling)
        self.assertIn("Conflict, ambiguity, or evidence gap + owner", sibling)
        self.assertIn("Need evidence / route to owner", sibling)

        self.assertIn("Gate N of M — Project Understanding", questions)
        self.assertIn("at most four questions", questions)
        self.assertIn("split only to stay within the four-question", questions)
        self.assertIn("later same-locator calls", questions)
        self.assertNotIn("4–6 targeted questions in a single interactive round", questions)

    def test_single_feature_security_and_commit_authority_are_separate(self):
        gates = read("stage-4-7-gates.md")
        security_at = gates.index("#### 4.1.1 Single-Feature Security Attestation")
        preview_at = gates.index("#### 4.1.2 Complete minimal-artifact preview")
        approval_at = gates.index("#### 4.1.3 Single-Feature Final Plan Approval")
        self.assertLess(security_at, preview_at)
        self.assertLess(preview_at, approval_at)

        security = gates[security_at:preview_at]
        preview = gates[preview_at:approval_at]
        approval = gates[approval_at:gates.index("### 4.2", approval_at)]
        for anchor in ("basis:", "cost if wrong:", "owner / authority:"):
            self.assertIn(anchor, security)
        self.assertIn("does **not** authorize writing", security)
        self.assertIn("Supply evidence or correct", security)
        self.assertIn("render the complete", preview)
        self.assertIn("Do not summarize\nor omit fields", preview)
        self.assertIn("plans.json` registry change", preview)
        self.assertIn("Material-Gate Decision Authority", approval)
        self.assertIn("Write exactly the previewed minimal artifact", approval)
        self.assertNotIn("skips the Candidate", approval)

    def test_candidate_review_triages_and_splits_controls(self):
        gates = read("stage-4-7-gates.md")
        candidate = between(
            gates,
            "### 5.2 Present Candidate Plan",
            "### 5.5 Coarsen — scope-preserving merge",
        )

        self.assertIn("What needs your decision", candidate)
        self.assertIn("Auto-resolved (count)", candidate)
        self.assertIn("Material-Gate Decision Authority", candidate)
        self.assertIn("Open context / fork controls", candidate)
        self.assertIn("same-locator follow-up", candidate)
        self.assertIn("Need evidence / route to owner / park", candidate)
        self.assertNotRegex(candidate, r"Continue, Coarsen, Adjust, Add context")

    def test_reachability_isolates_material_rows_and_bulk_approves_only_routine(self):
        gates = read("stage-4-7-gates.md")
        decision = between(gates, "### 6.6.2 The decision", "### 6.6.4")

        phase_a = between(decision, "#### Phase A", "#### Phase B")
        phase_b = decision[decision.index("#### Phase B"):]
        self.assertIn("one `AskUserQuestion` question per material row", phase_a)
        self.assertRegex(phase_a, r"at\s+most four row-questions")
        self.assertIn("Owner / authority:", phase_a)
        self.assertIn("Cost if wrong:", phase_a)
        self.assertIn("Delegate to the named authority", phase_a)
        self.assertIn("Only after every material row is resolved", phase_b)
        self.assertIn("Approve routine rows and continue", phase_b)
        self.assertIn("Accept only the displayed routine dispositions", phase_b)
        self.assertNotIn("Approve trace", decision)

    def test_security_and_protocol_negatives_keep_separate_gates(self):
        write = read("stage-8-9-write.md")
        threat_at = write.index("### 8.2.1 Threat-model attestation")
        contract_at = write.index("### 8.2.2 Interaction-contract attestation")
        routing_at = write.index("### 8.2.3 Light-tier attestation routing")
        self.assertLess(threat_at, contract_at)
        self.assertLess(contract_at, routing_at)

        threat = write[threat_at:contract_at]
        contract = write[contract_at:routing_at]
        self.assertIn("Gate N of M — Threat-Model Attestation", threat)
        self.assertIn("one independently answerable `AskUserQuestion` question per material", threat)
        self.assertIn("Need evidence / route to owner", threat)
        self.assertIn("Gate N of M — Interaction-Contract Attestation", contract)
        self.assertIn("one independently answerable `AskUserQuestion` question per material", contract)
        self.assertIn("Need evidence / route to owner", contract)
        self.assertNotIn("Light-tier combined attestation", write)
        self.assertNotIn("Confirm both negatives", write)
        self.assertNotIn("R3 isolation rule", write)

    def test_final_review_leads_with_delta_and_has_authority_controls(self):
        write = read("stage-8-9-write.md")
        presentation = between(write, "### 8.2 Present Final Plan", "### 8.2.1")
        final = between(write, "### 8.3 Final Decision", "## Stage 9")

        self.assertLess(
            presentation.index("What needs your decision"),
            presentation.index("Supporting detail — full final plan"),
        )
        for anchor in (
            "Decision delta",
            "Unknowns and material rows",
            "Recommendation",
            "Consequence preview",
            "Auto-resolved",
        ):
            self.assertIn(anchor, presentation)
        self.assertIn("Material-Gate Decision Authority", final)
        self.assertIn("Need evidence / route to owner", final)
        self.assertIn("Park with the draft resumable", final)
        self.assertIn("same locator", final)
        self.assertNotIn("all planning work this session is lost", write.lower())

    def test_proportionality_uses_qualified_ceiling_not_a_cost_forecast(self):
        stage = read("stage-0-1-understand.md")
        proportionality = between(
            stage,
            "### Proportionality Routing",
            "### Existing-Plan Check",
        )
        normalized = re.sub(r"\s+", " ", proportionality)
        self.assertIn("Gate N of M — Proportionality Routing", proportionality)
        self.assertIn("exact facts supporting each condition", normalized)
        self.assertIn("configured", normalized)
        self.assertIn("budget caps and decision aids", normalized)
        self.assertIn("not measured costs, floors, or forecasts", normalized)
        self.assertIn("Render the authority block from `SKILL.md`", normalized)
        self.assertIn("decision owner is the requester or delivery/budget owner", normalized)
        self.assertIn("Use `/core-engineering:ce-patch`", proportionality)
        self.assertIn("Continue with full planning", proportionality)
        self.assertIn("Need evidence / route to owner / park", normalized)
        self.assertIn("**Abort**", proportionality)
        self.assertNotRegex(proportionality, re.compile(r"\$4 floor", re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
