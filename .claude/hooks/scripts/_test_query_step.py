#!/usr/bin/env python3
"""Unit tests for query_step.py — Step Execution Registry."""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from query_step import (
    _compact_ranges,
    _get_critic_config,
    _get_gate_context,
    _get_pccs_config,
    _get_phase,
    _get_wave,
    list_agents,
    list_steps_for_agent,
    query_step,
)


class TestQueryStepBasic(unittest.TestCase):
    """Test basic query_step functionality."""

    def test_valid_step_returns_dict(self):
        result = query_step(1)
        self.assertIsInstance(result, dict)
        self.assertNotIn("error", result)

    def test_invalid_step_zero(self):
        result = query_step(0)
        self.assertIn("error", result)

    def test_invalid_step_211(self):
        result = query_step(211)
        self.assertIn("error", result)

    def test_all_steps_have_agent(self):
        """Every step 1-210 must return a non-empty agent."""
        for step in range(1, 211):
            result = query_step(step)
            self.assertNotIn("error", result, f"Step {step} returned error")
            self.assertIn("agent", result, f"Step {step} missing 'agent' key")
            self.assertTrue(result["agent"], f"Step {step} has empty agent")

    def test_all_steps_have_required_fields(self):
        """Every step must have all required output fields."""
        required = {
            "step", "agent", "description", "tier", "phase",
            "wave", "critic", "dialogue_domain", "dialogue",
            "l2_enhanced", "pccs_required", "pccs_mode",
            "has_grounded_claims", "output_path",
            "gate_before", "gate_after", "hitl",
            "hitl_required", "translation_required",
        }
        for step in range(1, 211):
            result = query_step(step)
            missing = required - set(result.keys())
            self.assertEqual(missing, set(), f"Step {step} missing fields: {missing}")


class TestAgentMapping(unittest.TestCase):
    """Test H-1: Step→Agent mapping correctness."""

    def test_wave1_literature_searcher(self):
        for step in range(39, 43):
            result = query_step(step)
            self.assertEqual(result["agent"], "literature-searcher", f"Step {step}")

    def test_wave1_seminal_works(self):
        for step in range(43, 47):
            result = query_step(step)
            self.assertEqual(result["agent"], "seminal-works-analyst", f"Step {step}")

    def test_wave1_trend_analyst(self):
        for step in range(47, 51):
            result = query_step(step)
            self.assertEqual(result["agent"], "trend-analyst", f"Step {step}")

    def test_wave1_methodology_scanner(self):
        for step in range(51, 55):
            result = query_step(step)
            self.assertEqual(result["agent"], "methodology-scanner", f"Step {step}")

    def test_wave2_agents(self):
        expected = [
            (59, 62, "theoretical-framework-analyst"),
            (63, 66, "empirical-evidence-analyst"),
            (67, 70, "gap-identifier"),
            (71, 74, "variable-relationship-analyst"),
        ]
        for start, end, agent in expected:
            for step in range(start, end + 1):
                result = query_step(step)
                self.assertEqual(result["agent"], agent, f"Step {step}")

    def test_wave3_agents(self):
        expected = [
            (79, 82, "critical-reviewer"),
            (83, 86, "methodology-critic"),
            (87, 90, "limitation-analyst"),
            (91, 94, "future-direction-analyst"),
        ]
        for start, end, agent in expected:
            for step in range(start, end + 1):
                result = query_step(step)
                self.assertEqual(result["agent"], agent, f"Step {step}")

    def test_wave4_agents(self):
        for step in range(99, 103):
            self.assertEqual(query_step(step)["agent"], "synthesis-agent")
        for step in range(103, 107):
            self.assertEqual(query_step(step)["agent"], "conceptual-model-builder")

    def test_gate_steps_orchestrator(self):
        for step in [55, 57, 58, 75, 77, 78, 95, 97, 98]:
            result = query_step(step)
            self.assertEqual(result["agent"], "_orchestrator", f"Gate step {step}")

    def test_translation_gate_steps(self):
        for step in [56, 76, 96, 108, 113]:
            result = query_step(step)
            self.assertEqual(result["agent"], "translator", f"Translation step {step}")

    def test_phase3_thesis_writer(self):
        for step in [143, 144, 145, 146, 147, 148, 151, 153, 155, 158]:
            result = query_step(step)
            self.assertEqual(result["agent"], "thesis-writer", f"Step {step}")

    def test_phase4_agents(self):
        self.assertEqual(query_step(165)["agent"], "publication-strategist")
        self.assertEqual(query_step(166)["agent"], "journal-matcher")
        self.assertEqual(query_step(167)["agent"], "submission-preparer")
        self.assertEqual(query_step(168)["agent"], "cover-letter-writer")

    def test_phase6_all_translator(self):
        for step in range(181, 211):
            result = query_step(step)
            self.assertEqual(result["agent"], "translator", f"Step {step}")


class TestResearchTypeVariants(unittest.TestCase):
    """Test Phase 2 agent variation by research type."""

    def test_quantitative_step123(self):
        result = query_step(123, "quantitative")
        self.assertEqual(result["agent"], "quantitative-designer")

    def test_qualitative_step123(self):
        result = query_step(123, "qualitative")
        self.assertEqual(result["agent"], "paradigm-consultant")

    def test_mixed_step123(self):
        result = query_step(123, "mixed")
        self.assertEqual(result["agent"], "mixed-methods-designer")

    def test_undecided_defaults_to_quantitative(self):
        result = query_step(123, "undecided")
        self.assertEqual(result["agent"], "quantitative-designer")

    def test_quant_sampling(self):
        result = query_step(125, "quantitative")
        self.assertEqual(result["agent"], "sampling-designer")

    def test_qual_sampling(self):
        result = query_step(125, "qualitative")
        self.assertEqual(result["agent"], "participant-selector")


class TestTierSelection(unittest.TestCase):
    """Test H-4: Tier selection correctness."""

    def test_orchestrator_steps_tier3(self):
        """Orchestrator-direct steps should be Tier 3."""
        for step in [1, 5, 35, 55, 58, 115]:
            result = query_step(step)
            if result["agent"] == "_orchestrator":
                self.assertEqual(result["tier"], 3, f"Step {step}")

    def test_agent_steps_tier2(self):
        """Agent-delegated steps should be Tier 2 (quality-first default)."""
        for step in [39, 47, 59, 79, 99, 143, 165]:
            result = query_step(step)
            self.assertEqual(result["tier"], 2, f"Step {step}")


class TestCriticRouting(unittest.TestCase):
    """Test H-3: Critic agent routing correctness."""

    def test_wave1_research_dialogue(self):
        for step in range(39, 55):
            cfg = _get_critic_config(step)
            self.assertEqual(cfg["critic"], "fact-checker", f"Step {step}")
            self.assertEqual(cfg["critic_secondary"], "reviewer", f"Step {step}")
            self.assertEqual(cfg["dialogue_domain"], "research", f"Step {step}")
            self.assertTrue(cfg["dialogue"], f"Step {step}")

    def test_wave2_research_dialogue(self):
        for step in range(59, 75):
            cfg = _get_critic_config(step)
            self.assertTrue(cfg["dialogue"], f"Step {step}")
            self.assertEqual(cfg["dialogue_domain"], "research", f"Step {step}")

    def test_phase2_development_dialogue(self):
        for step in range(123, 132):
            cfg = _get_critic_config(step)
            self.assertEqual(cfg["critic"], "code-reviewer", f"Step {step}")
            self.assertEqual(cfg["dialogue_domain"], "development", f"Step {step}")

    def test_phase3_review_cycles_single_review(self):
        for step in [152, 154]:
            cfg = _get_critic_config(step)
            self.assertEqual(cfg["critic"], "reviewer", f"Step {step}")
            self.assertFalse(cfg["dialogue"], f"Step {step}")
            self.assertTrue(cfg["l2_enhanced"], f"Step {step}")

    def test_gate_steps_l2_enhanced(self):
        for step in [55, 75, 95, 107]:
            cfg = _get_critic_config(step)
            self.assertTrue(cfg["l2_enhanced"], f"Gate step {step}")

    def test_orchestrator_steps_no_critic(self):
        for step in [1, 5, 58, 115]:
            cfg = _get_critic_config(step)
            self.assertIsNone(cfg["critic"], f"Step {step}")
            self.assertFalse(cfg["l2_enhanced"], f"Step {step}")


class TestPCCSMode(unittest.TestCase):
    """Test H-2: pCCS mode selection correctness."""

    def test_wave1_degraded(self):
        for step in range(39, 55):
            cfg = _get_pccs_config(step)
            self.assertTrue(cfg["pccs_required"], f"Step {step}")
            self.assertEqual(cfg["pccs_mode"], "DEGRADED", f"Step {step}")

    def test_wave4_full(self):
        for step in range(99, 107):
            cfg = _get_pccs_config(step)
            self.assertTrue(cfg["pccs_required"], f"Step {step}")
            self.assertEqual(cfg["pccs_mode"], "FULL", f"Step {step}")

    def test_gate_steps_no_pccs(self):
        """Gate steps are cross-validation, not content — no pCCS needed."""
        for step in [55, 75, 95]:
            cfg = _get_pccs_config(step)
            self.assertFalse(cfg["pccs_required"], f"Gate step {step}")

    def test_srcs_eval_step_full(self):
        """SRCS evaluation step (107) produces evaluation, not claims."""
        cfg = _get_pccs_config(107)
        self.assertFalse(cfg["pccs_required"])

    def test_phase3_chapters_full(self):
        for step in range(143, 152):
            cfg = _get_pccs_config(step)
            self.assertTrue(cfg["pccs_required"], f"Step {step}")
            self.assertEqual(cfg["pccs_mode"], "FULL", f"Step {step}")

    def test_orchestrator_steps_no_pccs(self):
        for step in [1, 5, 35, 115]:
            cfg = _get_pccs_config(step)
            self.assertFalse(cfg["pccs_required"], f"Step {step}")
            self.assertIsNone(cfg["pccs_mode"], f"Step {step}")

    def test_translation_steps_no_pccs(self):
        for step in range(181, 211):
            cfg = _get_pccs_config(step)
            self.assertFalse(cfg["pccs_required"], f"Step {step}")


class TestWavePhaseMapping(unittest.TestCase):
    """Test wave and phase mapping."""

    def test_wave_numbers(self):
        self.assertEqual(_get_wave(39), 1)
        self.assertEqual(_get_wave(54), 1)
        self.assertEqual(_get_wave(59), 2)
        self.assertEqual(_get_wave(74), 2)
        self.assertEqual(_get_wave(79), 3)
        self.assertEqual(_get_wave(94), 3)
        self.assertEqual(_get_wave(99), 4)
        self.assertEqual(_get_wave(106), 4)
        self.assertEqual(_get_wave(111), 5)
        self.assertEqual(_get_wave(114), 5)

    def test_non_wave_steps(self):
        self.assertIsNone(_get_wave(1))
        self.assertIsNone(_get_wave(55))
        self.assertIsNone(_get_wave(115))
        self.assertIsNone(_get_wave(143))

    def test_phase_names(self):
        self.assertEqual(_get_phase(1), "phase_0_init")
        self.assertEqual(_get_phase(9), "phase_0a_topic")
        self.assertEqual(_get_phase(15), "phase_0d_learning")
        self.assertEqual(_get_phase(39), "wave_1")
        self.assertEqual(_get_phase(55), "gate_1")
        self.assertEqual(_get_phase(107), "srcs_full")
        self.assertEqual(_get_phase(121), "phase_2_design")
        self.assertEqual(_get_phase(141), "phase_3_writing")
        self.assertEqual(_get_phase(165), "phase_4_publication")
        self.assertEqual(_get_phase(181), "phase_6_translation")


class TestGateContext(unittest.TestCase):
    """Test gate before/after context."""

    def test_pre_gate1(self):
        ctx = _get_gate_context(39)
        self.assertIsNone(ctx["gate_before"])
        self.assertIsNone(ctx["gate_after"])

    def test_gate1_steps(self):
        ctx = _get_gate_context(55)
        self.assertIsNone(ctx["gate_before"])
        self.assertEqual(ctx["gate_after"], "gate-1")

    def test_wave2_gate_context(self):
        ctx = _get_gate_context(59)
        self.assertEqual(ctx["gate_before"], "gate-1")
        self.assertEqual(ctx["gate_after"], "gate-2")

    def test_wave3_gate_context(self):
        ctx = _get_gate_context(79)
        self.assertEqual(ctx["gate_before"], "gate-2")
        self.assertEqual(ctx["gate_after"], "gate-3")


class TestHITLMapping(unittest.TestCase):
    """Test HITL checkpoint mapping."""

    def test_hitl1_steps(self):
        for step in range(35, 39):
            result = query_step(step)
            self.assertEqual(result["hitl"], "hitl-1", f"Step {step}")
            self.assertTrue(result["hitl_required"], f"Step {step}")

    def test_hitl2_steps(self):
        for step in range(115, 121):
            result = query_step(step)
            self.assertEqual(result["hitl"], "hitl-2", f"Step {step}")

    def test_non_hitl_step(self):
        result = query_step(39)
        self.assertIsNone(result["hitl"])
        self.assertFalse(result["hitl_required"])


class TestTranslation(unittest.TestCase):
    """Test translation step detection."""

    def test_gate_translation_steps(self):
        for step in [56, 76, 96, 108, 113]:
            result = query_step(step)
            self.assertTrue(result["translation_required"], f"Step {step}")

    def test_phase6_all_translation(self):
        for step in range(181, 211):
            result = query_step(step)
            self.assertTrue(result["translation_required"], f"Step {step}")

    def test_non_translation_step(self):
        result = query_step(39)
        self.assertFalse(result["translation_required"])


class TestListAgents(unittest.TestCase):
    """Test agent listing functions."""

    def test_list_agents_returns_dict(self):
        agents = list_agents()
        self.assertIsInstance(agents, dict)
        self.assertGreater(len(agents), 10)

    def test_list_agents_covers_all_steps(self):
        agents = list_agents()
        all_steps = set()
        for steps in agents.values():
            all_steps.update(steps)
        for step in range(1, 211):
            self.assertIn(step, all_steps, f"Step {step} not covered by any agent")

    def test_list_steps_for_known_agent(self):
        steps = list_steps_for_agent("literature-searcher")
        self.assertGreater(len(steps), 0)
        self.assertIn(39, steps)

    def test_list_steps_for_unknown_agent(self):
        steps = list_steps_for_agent("nonexistent-agent")
        self.assertEqual(steps, [])


class TestCompactRanges(unittest.TestCase):
    """Test _compact_ranges helper."""

    def test_single(self):
        self.assertEqual(_compact_ranges([5]), "5")

    def test_consecutive(self):
        self.assertEqual(_compact_ranges([1, 2, 3]), "1-3")

    def test_mixed(self):
        self.assertEqual(_compact_ranges([1, 2, 3, 5, 6, 8]), "1-3, 5-6, 8")

    def test_empty(self):
        self.assertEqual(_compact_ranges([]), "none")


class TestCLI(unittest.TestCase):
    """Test CLI invocation."""

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "query_step.py")
        return subprocess.run(
            [sys.executable, script, *args],
            capture_output=True, text=True, timeout=10,
        )

    def test_cli_step_json(self):
        result = self._run("--step", "47", "--json")
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data["step"], 47)
        self.assertEqual(data["agent"], "trend-analyst")

    def test_cli_step_field(self):
        result = self._run("--step", "47", "--field", "agent")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "trend-analyst")

    def test_cli_invalid_step(self):
        result = self._run("--step", "0", "--json")
        self.assertNotEqual(result.returncode, 0)

    def test_cli_list_agents(self):
        result = self._run("--list-agents")
        self.assertEqual(result.returncode, 0)
        self.assertIn("literature-searcher", result.stdout)

    def test_cli_list_agents_json(self):
        result = self._run("--list-agents", "--json")
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertIn("literature-searcher", data)

    def test_cli_list_steps(self):
        result = self._run("--list-steps", "--agent", "trend-analyst")
        self.assertEqual(result.returncode, 0)
        self.assertIn("trend-analyst", result.stdout)

    def test_cli_research_type(self):
        result = self._run("--step", "123", "--research-type", "qualitative", "--json")
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data["agent"], "paradigm-consultant")

    def test_cli_human_readable(self):
        result = self._run("--step", "47")
        self.assertEqual(result.returncode, 0)
        self.assertIn("trend-analyst", result.stdout)
        self.assertIn("Tier: 2", result.stdout)


if __name__ == "__main__":
    unittest.main()
