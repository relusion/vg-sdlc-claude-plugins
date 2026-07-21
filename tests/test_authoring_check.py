import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = "plugins/core-engineering/skills"


class AuthoringCheck(unittest.TestCase):
    def _copy_repo(self, tmp: Path) -> Path:
        dst = tmp / "repo"
        for sub in ("scripts", "plugins", "docs"):
            shutil.copytree(
                REPO / sub, dst / sub, ignore=shutil.ignore_patterns("__pycache__")
            )
        return dst

    def _lint(self, repo: Path):
        return subprocess.run(
            [sys.executable, str(repo / "scripts" / "authoring_check.py"), "--root", str(repo)],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _mutate(self, repo: Path, rel: str, old: str, new: str) -> None:
        path = repo / rel
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"fixture drift: {old!r} not found in {rel}")
        path.write_text(text.replace(old, new), encoding="utf-8")

    def test_clean_copy_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            res = self._lint(repo)
            self.assertEqual(res.returncode, 0, res.stderr)

    def test_glossary_gloss_changed_in_one_copy_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            # Change the runtime Legend's gloss for `excluded` without touching
            # the contributor mirror — the exact one-copy drift A9 exists for.
            self._mutate(
                repo, f"{SKILLS}/ce-plan/stage-4-7-gates.md",
                "intentionally never built",
                "intentionally skipped for now",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("never built", res.stderr)
            self.assertIn("excluded", res.stderr)

    def test_glossary_term_removed_from_mirror_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            self._mutate(
                repo, "docs/contributing/HITL-GATE-STANDARD.md",
                "select-to-continue exclusion",
                "wizard-screen exclusion",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("select-to-continue", res.stderr)

    def test_material_gate_without_locator_discipline_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            # A10 globs every *.md in the skill dir, and ce-verify now carries
            # the `Gate N of M` locator literal in more than one file (SKILL.md
            # plus the batched per-journey gate in stage-2-2.6-walks.md). Strip
            # it from both so the skill retains its [material] markers but no
            # locator discipline — the condition A10 must fire on.
            for rel in (
                f"{SKILLS}/ce-verify/SKILL.md",
                f"{SKILLS}/ce-verify/stage-2-2.6-walks.md",
            ):
                self._mutate(repo, rel, "Gate N of M", "a gate label")
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("ce-verify", res.stderr)
            self.assertIn("gate-locator", res.stderr)

    def test_freeform_hitl_suffix_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            self._mutate(
                repo, f"{SKILLS}/ce-debug/SKILL.md",
                "## Human-in-the-Loop — tiered",
                "## Human-in-the-Loop — tiered, mostly",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("suffix must be one of", res.stderr)

    def test_date_drift_spelling_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            skill = repo / SKILLS / "ce-ask/SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8")
                + "\nWrite the report to docs/asks/<YYYY-MM-DD>-ask.md.\n",
                encoding="utf-8",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("<date>", res.stderr)

    def test_never_overwritten_date_without_same_day_suffix_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            self._mutate(
                repo, f"{SKILLS}/ce-decide/SKILL.md",
                "**Same-day collision rule:**",
                "**Second-run collision rule:**",
            )
            self._mutate(
                repo, f"{SKILLS}/ce-decide/SKILL.md",
                "`<date>-2`",
                "`<date>-next`",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("same-day `-2` collision suffix", res.stderr)

    def test_retired_concept_name_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            skill = repo / SKILLS / "ce-spec/SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8") + "\nSee the Backward-Edge Summary.\n",
                encoding="utf-8",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("Back-Edge", res.stderr)

    def test_impossible_gate_label_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            skill = repo / SKILLS / "ce-probe-infra/SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8") + "\nThen Gate 3 of 2 runs.\n",
                encoding="utf-8",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("Gate 3 of 2", res.stderr)

    def test_invariant_core_loss_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            self._mutate(
                repo, f"{SKILLS}/ce-probe-perf/SKILL.md",
                "Open Questions / Stops",
                "Open Qs",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("invariant core", res.stderr)

    def test_noncanonical_rule_heading_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            self._mutate(
                repo, f"{SKILLS}/ce-probe-perf/SKILL.md",
                "## Cross-cutting rule — Findings, Not Verdicts",
                "## Findings, Not Verdicts",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("must read exactly", res.stderr)

    def test_cluster_description_regression_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            self._mutate(
                repo, f"{SKILLS}/ce-review/SKILL.md",
                "/core-engineering:ce-verify",
                "the behavior sibling",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("does not mention /core-engineering:ce-verify", res.stderr)

    def test_skill_line_cap_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            skill = repo / SKILLS / "ce-ask/SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8") + "filler\n" * 400,
                encoding="utf-8",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("externalize stage bodies", res.stderr)

    def test_description_char_cap_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            self._mutate(
                repo, f"{SKILLS}/ce-debug/SKILL.md",
                "description: |\n",
                "description: |\n  " + "x" * 1600 + "\n",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("platform cap", res.stderr)

    def test_evidence_mapping_clause_missing_fails(self):
        # A11 — a skill that keeps its `Three-State Evidence` rule but drops the
        # meta-scale mapping clause must red (the anti-pattern is falling back to
        # N×N cross-skill name-checks instead of the one shared scale).
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            self._mutate(
                repo, f"{SKILLS}/ce-probe-perf/SKILL.md",
                "shared evidence scale",
                "this skill's own scale",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("ce-probe-perf", res.stderr)
            self.assertIn("shared evidence scale", res.stderr)

    def test_evidence_meta_scale_removed_from_glossary_fails(self):
        # A11 — the meta-scale's canonical definition must stay in the shared
        # consequence-glossary so every mapping clause resolves to one home.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            self._mutate(
                repo, "docs/contributing/HITL-GATE-STANDARD.md",
                "Evidence-strength meta-scale",
                "Evidence tiers",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("evidence-strength meta-scale", res.stderr)

    def test_retired_lock_brand_fails(self):
        # A4 (WS7-T10) — the five lock brands collapsed into one "Scope Lock";
        # reintroducing an old brand in any skill markdown must red.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            skill = repo / SKILLS / "ce-implement/SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8") + "\nHonor the Spec Lock here.\n",
                encoding="utf-8",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("Scope Lock", res.stderr)

    def test_scope_lock_glossary_term_removed_fails(self):
        # A9 — the "scope lock" gloss must live in both homes; dropping it from
        # the contributor mirror breaks term-set parity.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            self._mutate(
                repo, "docs/contributing/HITL-GATE-STANDARD.md",
                "| Scope Lock | The boundary a stage may not widen",
                "| Widen Guard | The boundary a stage may not widen",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("scope lock", res.stderr)

    def test_scope_lock_anchor_changed_in_one_copy_fails(self):
        # A9 — changing the "scope lock" anchor in the runtime Legend only is the
        # exact one-copy drift the check exists for.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            self._mutate(
                repo, f"{SKILLS}/ce-plan/stage-4-7-gates.md",
                "widening goes up a layer, never through it",
                "widening escalates, never through it",
            )
            res = self._lint(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("widening goes up a layer", res.stderr)
            self.assertIn("scope lock", res.stderr)


if __name__ == "__main__":
    unittest.main()
