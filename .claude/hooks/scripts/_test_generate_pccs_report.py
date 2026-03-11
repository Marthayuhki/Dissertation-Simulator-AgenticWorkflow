#!/usr/bin/env python3
"""Tests for generate_pccs_report.py — Phase D: pCCS Score Computation.

Covers all 6 public functions:
  1. compute_pccs()     — fusion formula
  2. classify_color()   — color classification
  3. compute_decision() — decision matrix
  4. compute_pcae()     — inter-claim alignment errors
  5. _get_llm_score()   — LLM score extraction
  6. generate_report()  — full report generation
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_pccs_report import (
    CONFIDENCE_CEILING,
    WEIGHTS,
    _check_disagreement,
    _get_llm_score,
    classify_color,
    compute_decision,
    compute_pcae,
    compute_pccs,
    generate_report,
)


# =============================================================================
# 1. compute_pccs() — Fusion Formula
# =============================================================================

class TestComputePccs(unittest.TestCase):
    """Test the pCCS fusion formula."""

    def test_factual_no_calibration_no_block(self):
        """FACTUAL: p1=80, agent=90, cal=0 → 0.50*80 + 0.50*min(90,95) = 85.0"""
        result = compute_pccs("FACTUAL", 80.0, 90, 0.0, False)
        self.assertEqual(result, 85.0)

    def test_empirical_basic(self):
        """EMPIRICAL: p1=70, agent=80, cal=0 → 0.45*70 + 0.55*min(80,85) = 75.5"""
        result = compute_pccs("EMPIRICAL", 70.0, 80, 0.0, False)
        self.assertEqual(result, 75.5)

    def test_speculative_basic(self):
        """SPECULATIVE: p1=50, agent=70, cal=0 → 0.15*50 + 0.85*min(70,60) = 58.5"""
        # ceiling clamp: min(70, 60) = 60
        result = compute_pccs("SPECULATIVE", 50.0, 70, 0.0, False)
        self.assertEqual(result, 58.5)

    def test_ceiling_clamp_factual(self):
        """Agent score above FACTUAL ceiling (95) should be clamped."""
        # p1=90, agent=100, cal=0 → calibrated = min(100, 95) = 95
        # pccs = 0.50*90 + 0.50*95 = 92.5
        result = compute_pccs("FACTUAL", 90.0, 100, 0.0, False)
        self.assertEqual(result, 92.5)

    def test_ceiling_clamp_theoretical(self):
        """THEORETICAL ceiling is 75."""
        # p1=80, agent=90, cal=0 → calibrated = min(90, 75) = 75
        # pccs = 0.25*80 + 0.75*75 = 20+56.25 = 76.25 → 76.2 (rounded)
        result = compute_pccs("THEORETICAL", 80.0, 90, 0.0, False)
        self.assertEqual(result, 76.2)

    def test_calibration_delta_positive(self):
        """Positive cal_delta reduces agent score (over-confidence correction)."""
        # FACTUAL: p1=80, agent=90, cal=10 → calibrated = min(90-10, 95) = 80
        # pccs = 0.50*80 + 0.50*80 = 80.0
        result = compute_pccs("FACTUAL", 80.0, 90, 10.0, False)
        self.assertEqual(result, 80.0)

    def test_calibration_delta_negative(self):
        """Negative cal_delta increases agent score (under-confidence correction)."""
        # FACTUAL: p1=80, agent=80, cal=-5 → calibrated = min(80-(-5), 95) = min(85, 95) = 85
        # pccs = 0.50*80 + 0.50*85 = 82.5
        result = compute_pccs("FACTUAL", 80.0, 80, -5.0, False)
        self.assertEqual(result, 82.5)

    def test_calibration_exceeds_ceiling(self):
        """Even with negative cal_delta, ceiling still applies."""
        # SPECULATIVE: p1=50, agent=50, cal=-20 → calibrated = min(50+20, 60) = 60
        # pccs = 0.15*50 + 0.85*60 = 7.5+51.0 = 58.5
        result = compute_pccs("SPECULATIVE", 50.0, 50, -20.0, False)
        self.assertEqual(result, 58.5)

    def test_blocked_ceiling(self):
        """Blocked claims are capped at 40.0."""
        # FACTUAL: p1=80, agent=90, cal=0 → normally 85.0, blocked → min(85.0, 40.0) = 40.0
        result = compute_pccs("FACTUAL", 80.0, 90, 0.0, True)
        self.assertEqual(result, 40.0)

    def test_blocked_below_ceiling(self):
        """Blocked claim already below 40 stays unchanged."""
        # SPECULATIVE: p1=20, agent=20, cal=0 → 0.15*20+0.85*20 = 20.0, blocked → min(20, 40) = 20.0
        result = compute_pccs("SPECULATIVE", 20.0, 20, 0.0, True)
        self.assertEqual(result, 20.0)

    def test_unknown_type_uses_default(self):
        """Unknown claim type falls back to UNKNOWN weights/ceiling."""
        # UNKNOWN: p1=60, agent=70, cal=0 → 0.35*60 + 0.65*min(70,80) = 21+45.5 = 66.5
        result = compute_pccs("UNKNOWN", 60.0, 70, 0.0, False)
        self.assertEqual(result, 66.5)

    def test_unrecognized_type_uses_unknown(self):
        """Completely unknown type also falls back to UNKNOWN."""
        result_unknown = compute_pccs("UNKNOWN", 60.0, 70, 0.0, False)
        result_garbage = compute_pccs("NONEXISTENT_TYPE", 60.0, 70, 0.0, False)
        self.assertEqual(result_unknown, result_garbage)

    def test_clamp_floor_zero(self):
        """Negative raw score should be clamped to 0."""
        # FACTUAL: p1=0, agent=0, cal=50 → calibrated = min(0-50, 95) = -50
        # pccs_raw = 0.50*0 + 0.50*(-50) = -25.0 → clamped to 0.0
        result = compute_pccs("FACTUAL", 0.0, 0, 50.0, False)
        self.assertEqual(result, 0.0)

    def test_clamp_ceiling_100(self):
        """Score cannot exceed 100."""
        # Even with extreme inputs, clamped at 100
        result = compute_pccs("FACTUAL", 100.0, 100, -50.0, False)
        self.assertLessEqual(result, 100.0)

    def test_all_types_have_weights(self):
        """All 7 canonical types exist in WEIGHTS."""
        expected = {"FACTUAL", "EMPIRICAL", "THEORETICAL", "METHODOLOGICAL",
                    "INTERPRETIVE", "SPECULATIVE", "UNKNOWN"}
        self.assertEqual(set(WEIGHTS.keys()), expected)

    def test_all_types_have_ceiling(self):
        """All 7 canonical types exist in CONFIDENCE_CEILING."""
        expected = {"FACTUAL", "EMPIRICAL", "THEORETICAL", "METHODOLOGICAL",
                    "INTERPRETIVE", "SPECULATIVE", "UNKNOWN"}
        self.assertEqual(set(CONFIDENCE_CEILING.keys()), expected)

    def test_weights_sum_to_one(self):
        """p1 + agent weights must sum to 1.0 for each type."""
        for ct, w in WEIGHTS.items():
            with self.subTest(ct=ct):
                self.assertAlmostEqual(w["p1"] + w["agent"], 1.0, places=5)

    def test_result_is_rounded_one_decimal(self):
        """Output should be rounded to 1 decimal place."""
        # METHODOLOGICAL: p1=63, agent=77, cal=3
        # calibrated = min(77-3, 80) = 74
        # pccs = 0.35*63 + 0.65*74 = 22.05 + 48.1 = 70.15 → 70.2 (round to 1 decimal)
        result = compute_pccs("METHODOLOGICAL", 63.0, 77, 3.0, False)
        self.assertEqual(result, 70.2)


# =============================================================================
# 2. classify_color() — Color Classification
# =============================================================================

class TestClassifyColor(unittest.TestCase):
    """Test color classification."""

    def test_green_at_threshold(self):
        self.assertEqual(classify_color(70.0), "GREEN")

    def test_green_above_threshold(self):
        self.assertEqual(classify_color(95.0), "GREEN")

    def test_yellow_at_threshold(self):
        self.assertEqual(classify_color(50.0), "YELLOW")

    def test_yellow_between(self):
        self.assertEqual(classify_color(69.9), "YELLOW")

    def test_red_below_threshold(self):
        self.assertEqual(classify_color(49.9), "RED")

    def test_red_zero(self):
        self.assertEqual(classify_color(0.0), "RED")

    def test_green_100(self):
        self.assertEqual(classify_color(100.0), "GREEN")


# =============================================================================
# 3. compute_decision() — Decision Matrix
# =============================================================================

class TestComputeDecision(unittest.TestCase):
    """Test the Orchestrator decision matrix."""

    def test_all_green_proceed(self):
        claims = [
            {"claim_id": "A", "pccs": 80, "canonical_type": "FACTUAL"},
            {"claim_id": "B", "pccs": 75, "canonical_type": "EMPIRICAL"},
        ]
        d = compute_decision(claims)
        self.assertEqual(d["action"], "proceed")
        self.assertEqual(d["red_claim_ids"], [])

    def test_one_red_rewrite_claims(self):
        claims = [
            {"claim_id": "A", "pccs": 80, "canonical_type": "FACTUAL"},
            {"claim_id": "B", "pccs": 30, "canonical_type": "EMPIRICAL"},
        ]
        d = compute_decision(claims)
        self.assertEqual(d["action"], "rewrite_claims")
        self.assertEqual(d["red_claim_ids"], ["B"])

    def test_two_red_rewrite_claims(self):
        claims = [
            {"claim_id": "A", "pccs": 40, "canonical_type": "FACTUAL"},
            {"claim_id": "B", "pccs": 30, "canonical_type": "EMPIRICAL"},
            {"claim_id": "C", "pccs": 80, "canonical_type": "THEORETICAL"},
        ]
        d = compute_decision(claims)
        self.assertEqual(d["action"], "rewrite_claims")
        self.assertIn("A", d["red_claim_ids"])
        self.assertIn("B", d["red_claim_ids"])
        self.assertEqual(len(d["red_claim_ids"]), 2)

    def test_three_red_rewrite_step(self):
        claims = [
            {"claim_id": "A", "pccs": 30, "canonical_type": "FACTUAL"},
            {"claim_id": "B", "pccs": 20, "canonical_type": "EMPIRICAL"},
            {"claim_id": "C", "pccs": 10, "canonical_type": "THEORETICAL"},
        ]
        d = compute_decision(claims)
        self.assertEqual(d["action"], "rewrite_step")
        self.assertEqual(len(d["red_claim_ids"]), 3)

    def test_speculative_threshold_40(self):
        """SPECULATIVE uses pCCS<40 threshold (not <50)."""
        claims = [
            {"claim_id": "A", "pccs": 45, "canonical_type": "SPECULATIVE"},
        ]
        d = compute_decision(claims)
        self.assertEqual(d["action"], "proceed",
                         "SPECULATIVE at 45 should not be RED (threshold is <40)")

    def test_speculative_below_40_is_red(self):
        claims = [
            {"claim_id": "A", "pccs": 39, "canonical_type": "SPECULATIVE"},
        ]
        d = compute_decision(claims)
        self.assertEqual(d["action"], "rewrite_claims")
        self.assertIn("A", d["red_claim_ids"])

    def test_speculative_at_40_not_red(self):
        claims = [
            {"claim_id": "A", "pccs": 40, "canonical_type": "SPECULATIVE"},
        ]
        d = compute_decision(claims)
        self.assertEqual(d["action"], "proceed")

    def test_non_speculative_at_50_not_red(self):
        """Non-SPECULATIVE at exactly 50 is YELLOW, not RED."""
        claims = [
            {"claim_id": "A", "pccs": 50, "canonical_type": "FACTUAL"},
        ]
        d = compute_decision(claims)
        self.assertEqual(d["action"], "proceed")

    def test_non_speculative_at_49_is_red(self):
        claims = [
            {"claim_id": "A", "pccs": 49, "canonical_type": "FACTUAL"},
        ]
        d = compute_decision(claims)
        self.assertEqual(d["action"], "rewrite_claims")

    def test_empty_claims(self):
        d = compute_decision([])
        self.assertEqual(d["action"], "proceed")
        self.assertEqual(d["red_claim_ids"], [])

    def test_missing_canonical_type_defaults_unknown(self):
        """Missing canonical_type → UNKNOWN → uses <50 threshold."""
        claims = [
            {"claim_id": "A", "pccs": 30},
        ]
        d = compute_decision(claims)
        self.assertEqual(d["action"], "rewrite_claims")


# =============================================================================
# 4. compute_pcae() — predicted Claim Alignment Error
# =============================================================================

class TestComputePcae(unittest.TestCase):
    """Test inter-claim consistency checks."""

    def test_e2_duplicate_detection(self):
        """Claims sharing normalized source text should be flagged."""
        claims = [
            {"claim_id": "A", "source_text": "Smith et al. (2020) found X"},
            {"claim_id": "B", "source_text": "Smith et al. (2020) found X"},
        ]
        result = compute_pcae(claims)
        self.assertEqual(len(result["e2_duplicate_claims"]), 1)
        dup = result["e2_duplicate_claims"][0]
        self.assertIn("A", dup["claim_ids"])
        self.assertIn("B", dup["claim_ids"])

    def test_e2_no_duplicates(self):
        claims = [
            {"claim_id": "A", "source_text": "Smith (2020) study alpha"},
            {"claim_id": "B", "source_text": "Jones (2021) study beta"},
        ]
        result = compute_pcae(claims)
        self.assertEqual(len(result["e2_duplicate_claims"]), 0)

    def test_e2_normalization(self):
        """Punctuation differences should be normalized away."""
        claims = [
            {"claim_id": "A", "source_text": "Smith, et al. (2020)"},
            {"claim_id": "B", "source_text": "Smith et al (2020)"},
        ]
        result = compute_pcae(claims)
        self.assertEqual(len(result["e2_duplicate_claims"]), 1)

    def test_e1_not_implemented(self):
        result = compute_pcae([])
        self.assertEqual(result["e1_status"], "not_implemented")
        self.assertEqual(result["e1_numeric_contradictions"], [])

    def test_e3_not_implemented(self):
        result = compute_pcae([])
        self.assertEqual(result["e3_status"], "not_implemented")
        self.assertEqual(result["e3_source_conflicts"], [])

    def test_empty_source_text_ignored(self):
        claims = [
            {"claim_id": "A", "source_text": ""},
            {"claim_id": "B", "source_text": ""},
        ]
        result = compute_pcae(claims)
        self.assertEqual(len(result["e2_duplicate_claims"]), 0)

    def test_missing_source_text_ignored(self):
        claims = [
            {"claim_id": "A"},
            {"claim_id": "B"},
        ]
        result = compute_pcae(claims)
        self.assertEqual(len(result["e2_duplicate_claims"]), 0)

    def test_three_claims_same_source(self):
        """Three claims referencing the same source → one E2 entry with 3 IDs."""
        claims = [
            {"claim_id": "A", "source_text": "Study X found Y"},
            {"claim_id": "B", "source_text": "Study X found Y"},
            {"claim_id": "C", "source_text": "Study X found Y"},
        ]
        result = compute_pcae(claims)
        self.assertEqual(len(result["e2_duplicate_claims"]), 1)
        self.assertEqual(len(result["e2_duplicate_claims"][0]["claim_ids"]), 3)

    def test_e4_critic_additions_passed_through(self):
        """⑤ Critic additions should appear in e4_critic_additions."""
        additions = [
            {"claim_id": "A", "issue": "Missing citation", "severity": "high"},
        ]
        result = compute_pcae([], critic_additions=additions)
        self.assertEqual(len(result["e4_critic_additions"]), 1)
        self.assertEqual(result["e4_critic_additions"][0]["claim_id"], "A")

    def test_e4_empty_when_no_additions(self):
        result = compute_pcae([])
        self.assertEqual(result["e4_critic_additions"], [])

    def test_e4_none_additions_gives_empty(self):
        result = compute_pcae([], critic_additions=None)
        self.assertEqual(result["e4_critic_additions"], [])


# =============================================================================
# 4b. _check_disagreement() — Evaluator-Critic Disagreement
# =============================================================================

class TestCheckDisagreement(unittest.TestCase):
    """Test high_disagreement flag (⑥)."""

    def test_high_disagreement_true(self):
        """Difference of exactly 20 → True."""
        assessment = {"assessments": [{"claim_id": "A", "quality_score": 80}]}
        critic = {"judgments": [{"claim_id": "A", "adjusted_score": 60}]}
        self.assertTrue(_check_disagreement("A", assessment, critic))

    def test_no_disagreement(self):
        """Difference of 10 → False."""
        assessment = {"assessments": [{"claim_id": "A", "quality_score": 80}]}
        critic = {"judgments": [{"claim_id": "A", "adjusted_score": 70}]}
        self.assertFalse(_check_disagreement("A", assessment, critic))

    def test_disagreement_at_19(self):
        """Difference of 19 → False (threshold is >= 20)."""
        assessment = {"assessments": [{"claim_id": "A", "quality_score": 80}]}
        critic = {"judgments": [{"claim_id": "A", "adjusted_score": 61}]}
        self.assertFalse(_check_disagreement("A", assessment, critic))

    def test_only_evaluator_no_disagreement(self):
        """Only evaluator → no disagreement possible."""
        assessment = {"assessments": [{"claim_id": "A", "quality_score": 80}]}
        self.assertFalse(_check_disagreement("A", assessment, None))

    def test_neither_no_disagreement(self):
        self.assertFalse(_check_disagreement("A", None, None))

    def test_claim_not_found(self):
        assessment = {"assessments": [{"claim_id": "B", "quality_score": 80}]}
        critic = {"judgments": [{"claim_id": "B", "adjusted_score": 60}]}
        self.assertFalse(_check_disagreement("A", assessment, critic))


# =============================================================================
# 5. _get_llm_score() — LLM Score Extraction
# =============================================================================

class TestGetLlmScore(unittest.TestCase):
    """Test LLM assessment score extraction and merging."""

    def test_both_available_averaged(self):
        assessment = {"assessments": [{"claim_id": "A", "quality_score": 80}]}
        critic = {"judgments": [{"claim_id": "A", "adjusted_score": 70}]}
        result = _get_llm_score("A", assessment, critic)
        self.assertEqual(result, 75)  # (80+70)/2

    def test_only_evaluator(self):
        assessment = {"assessments": [{"claim_id": "A", "quality_score": 80}]}
        result = _get_llm_score("A", assessment, None)
        self.assertEqual(result, 80)

    def test_only_critic(self):
        critic = {"judgments": [{"claim_id": "A", "adjusted_score": 70}]}
        result = _get_llm_score("A", None, critic)
        self.assertEqual(result, 70)

    def test_neither_available(self):
        result = _get_llm_score("A", None, None)
        self.assertIsNone(result)

    def test_claim_not_in_assessment(self):
        assessment = {"assessments": [{"claim_id": "B", "quality_score": 80}]}
        result = _get_llm_score("A", assessment, None)
        self.assertIsNone(result)

    def test_claim_not_in_critic(self):
        critic = {"judgments": [{"claim_id": "B", "adjusted_score": 70}]}
        result = _get_llm_score("A", None, critic)
        self.assertIsNone(result)

    def test_average_rounds(self):
        """(81+70)/2 = 75.5 → rounds to 76."""
        assessment = {"assessments": [{"claim_id": "A", "quality_score": 81}]}
        critic = {"judgments": [{"claim_id": "A", "adjusted_score": 70}]}
        result = _get_llm_score("A", assessment, critic)
        self.assertEqual(result, 76)

    def test_empty_assessment_list(self):
        assessment = {"assessments": []}
        result = _get_llm_score("A", assessment, None)
        self.assertIsNone(result)

    def test_evaluator_present_critic_missing_claim(self):
        """Evaluator has claim, critic exists but doesn't have it → use evaluator only."""
        assessment = {"assessments": [{"claim_id": "A", "quality_score": 80}]}
        critic = {"judgments": [{"claim_id": "B", "adjusted_score": 70}]}
        result = _get_llm_score("A", assessment, critic)
        self.assertEqual(result, 80)

    def test_only_critic_has_claim(self):
        """Only critic has the claim → use critic only."""
        assessment = {"assessments": [{"claim_id": "B", "quality_score": 90}]}
        critic = {"judgments": [{"claim_id": "A", "adjusted_score": 65}]}
        result = _get_llm_score("A", assessment, critic)
        self.assertEqual(result, 65)


# =============================================================================
# 6. generate_report() — Full Report Generation
# =============================================================================

class TestGenerateReport(unittest.TestCase):
    """Test full report generation with file I/O."""

    def _write_json(self, tmpdir: str, name: str, data: dict) -> str:
        path = os.path.join(tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def test_minimal_claim_map(self):
        """Single claim, no assessment/critic/calibration → DEGRADED mode behavior."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {
                "step": 42,
                "file": "wave1-output.md",
                "claims": [
                    {
                        "claim_id": "EMP-001",
                        "canonical_type": "EMPIRICAL",
                        "p1_score": 70.0,
                        "confidence_numeric": 80,
                        "p1_signals": {"a3_blocked": False},
                    }
                ],
            }
            cm_path = self._write_json(tmpdir, "claim-map.json", cm)
            report = generate_report(cm_path)

            self.assertEqual(report["step"], 42)
            self.assertEqual(report["file"], "wave1-output.md")
            self.assertEqual(report["summary"]["total_claims"], 1)
            self.assertEqual(len(report["claims"]), 1)

            claim = report["claims"][0]
            self.assertEqual(claim["claim_id"], "EMP-001")
            self.assertIsNone(claim["llm_assessment"])
            self.assertEqual(claim["cal_delta"], 0.0)
            # EMPIRICAL: 0.45*70 + 0.55*min(80,85) = 31.5+44 = 75.5
            self.assertEqual(claim["pccs"], 75.5)
            self.assertEqual(claim["color"], "GREEN")

    def test_with_assessment_and_critic(self):
        """Full mode: claim-map + assessment + critic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {
                "step": 50,
                "file": "output.md",
                "claims": [
                    {
                        "claim_id": "FACT-001",
                        "canonical_type": "FACTUAL",
                        "p1_score": 80.0,
                        "confidence_numeric": 90,
                        "p1_signals": {"a3_blocked": False},
                    }
                ],
            }
            assessment = {
                "assessments": [{"claim_id": "FACT-001", "quality_score": 70}]
            }
            critic = {
                "judgments": [{"claim_id": "FACT-001", "adjusted_score": 60}]
            }
            cm_path = self._write_json(tmpdir, "claim-map.json", cm)
            as_path = self._write_json(tmpdir, "assessment.json", assessment)
            cr_path = self._write_json(tmpdir, "critic.json", critic)

            report = generate_report(cm_path, as_path, cr_path)
            claim = report["claims"][0]

            # LLM average: (70+60)/2 = 65
            self.assertEqual(claim["llm_assessment"], 65)
            # FACTUAL: 0.50*80 + 0.50*min(65, 95) = 40+32.5 = 72.5
            self.assertEqual(claim["pccs"], 72.5)
            self.assertEqual(claim["color"], "GREEN")

    def test_with_calibration(self):
        """Calibration delta applied to agent score."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {
                "step": 60,
                "file": "output.md",
                "claims": [
                    {
                        "claim_id": "EMP-001",
                        "canonical_type": "EMPIRICAL",
                        "p1_score": 70.0,
                        "confidence_numeric": 85,
                        "p1_signals": {"a3_blocked": False},
                    }
                ],
            }
            cal = {"cal_delta": 5.0}
            cm_path = self._write_json(tmpdir, "claim-map.json", cm)
            cal_path = self._write_json(tmpdir, "calibration.json", cal)

            report = generate_report(cm_path, calibration_path=cal_path)
            claim = report["claims"][0]

            self.assertEqual(claim["cal_delta"], 5.0)
            # EMPIRICAL: calibrated = min(85-5, 85) = 80
            # pccs = 0.45*70 + 0.55*80 = 31.5+44 = 75.5
            self.assertEqual(claim["pccs"], 75.5)

    def test_blocked_claim(self):
        """Blocked claim should be capped at 40."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {
                "step": 10,
                "file": "output.md",
                "claims": [
                    {
                        "claim_id": "FACT-001",
                        "canonical_type": "FACTUAL",
                        "p1_score": 90.0,
                        "confidence_numeric": 95,
                        "p1_signals": {"a3_blocked": True},
                    }
                ],
            }
            cm_path = self._write_json(tmpdir, "claim-map.json", cm)
            report = generate_report(cm_path)
            claim = report["claims"][0]
            self.assertTrue(claim["blocked"])
            self.assertLessEqual(claim["pccs"], 40.0)

    def test_missing_claim_map(self):
        """Non-existent claim-map → error report."""
        report = generate_report("/nonexistent/path.json")
        self.assertEqual(report["step"], -1)
        self.assertEqual(report["summary"]["total_claims"], 0)
        self.assertIn("error", report)

    def test_decision_in_report(self):
        """Report includes decision from compute_decision()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {
                "step": 10,
                "file": "output.md",
                "claims": [
                    {
                        "claim_id": "A",
                        "canonical_type": "FACTUAL",
                        "p1_score": 80.0,
                        "confidence_numeric": 85,
                        "p1_signals": {"a3_blocked": False},
                    }
                ],
            }
            cm_path = self._write_json(tmpdir, "claim-map.json", cm)
            report = generate_report(cm_path)
            self.assertIn("decision", report)
            self.assertEqual(report["decision"]["action"], "proceed")

    def test_pcae_in_report(self):
        """Report includes pCAE from compute_pcae()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {
                "step": 10,
                "file": "output.md",
                "claims": [
                    {
                        "claim_id": "A",
                        "canonical_type": "FACTUAL",
                        "p1_score": 80.0,
                        "confidence_numeric": 85,
                        "source_text": "Smith 2020 study",
                        "p1_signals": {"a3_blocked": False},
                    },
                    {
                        "claim_id": "B",
                        "canonical_type": "FACTUAL",
                        "p1_score": 80.0,
                        "confidence_numeric": 85,
                        "source_text": "Smith 2020 study",
                        "p1_signals": {"a3_blocked": False},
                    },
                ],
            }
            cm_path = self._write_json(tmpdir, "claim-map.json", cm)
            report = generate_report(cm_path)
            self.assertIn("pcae", report)
            self.assertGreater(len(report["pcae"]["e2_duplicate_claims"]), 0)

    def test_summary_statistics(self):
        """Summary should count colors correctly and compute mean."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {
                "step": 10,
                "file": "output.md",
                "claims": [
                    {
                        "claim_id": "A",
                        "canonical_type": "FACTUAL",
                        "p1_score": 90.0,
                        "confidence_numeric": 90,
                        "p1_signals": {"a3_blocked": False},
                    },
                    {
                        "claim_id": "B",
                        "canonical_type": "FACTUAL",
                        "p1_score": 50.0,
                        "confidence_numeric": 50,
                        "p1_signals": {"a3_blocked": False},
                    },
                    {
                        "claim_id": "C",
                        "canonical_type": "FACTUAL",
                        "p1_score": 10.0,
                        "confidence_numeric": 10,
                        "p1_signals": {"a3_blocked": False},
                    },
                ],
            }
            cm_path = self._write_json(tmpdir, "claim-map.json", cm)
            report = generate_report(cm_path)
            s = report["summary"]

            self.assertEqual(s["total_claims"], 3)
            # Verify all 3 colors are accounted for
            self.assertEqual(s["green"] + s["yellow"] + s["red"], 3)
            # Mean should be a reasonable number
            self.assertGreater(s["mean_pccs"], 0)

    def test_empty_claims_list(self):
        """GAP-2: Claim map with empty claims list → rewrite_step (not proceed)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {"step": 10, "file": "output.md", "claims": []}
            cm_path = self._write_json(tmpdir, "claim-map.json", cm)
            report = generate_report(cm_path)
            self.assertEqual(report["decision"]["action"], "rewrite_step")
            self.assertEqual(report["decision"]["reason"], "empty_claim_map")

    def test_missing_p1_signals_defaults(self):
        """Missing p1_signals in claim → blocked=False by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {
                "step": 10,
                "file": "output.md",
                "claims": [
                    {
                        "claim_id": "A",
                        "canonical_type": "FACTUAL",
                        "p1_score": 80.0,
                        "confidence_numeric": 80,
                    }
                ],
            }
            cm_path = self._write_json(tmpdir, "claim-map.json", cm)
            report = generate_report(cm_path)
            self.assertFalse(report["claims"][0]["blocked"])

    def test_missing_optional_paths(self):
        """None paths for optional files → graceful handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {
                "step": 10,
                "file": "output.md",
                "claims": [
                    {
                        "claim_id": "A",
                        "canonical_type": "FACTUAL",
                        "p1_score": 80.0,
                        "confidence_numeric": 80,
                        "p1_signals": {},
                    }
                ],
            }
            cm_path = self._write_json(tmpdir, "claim-map.json", cm)
            report = generate_report(cm_path, None, None, None)
            self.assertEqual(len(report["claims"]), 1)

    def test_multi_claim_mixed_types(self):
        """Multiple claims of different types processed correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {
                "step": 10,
                "file": "output.md",
                "claims": [
                    {
                        "claim_id": "FACT-001",
                        "canonical_type": "FACTUAL",
                        "p1_score": 80.0,
                        "confidence_numeric": 85,
                        "p1_signals": {"a3_blocked": False},
                    },
                    {
                        "claim_id": "SPEC-001",
                        "canonical_type": "SPECULATIVE",
                        "p1_score": 40.0,
                        "confidence_numeric": 70,
                        "p1_signals": {"a3_blocked": False},
                    },
                    {
                        "claim_id": "THEO-001",
                        "canonical_type": "THEORETICAL",
                        "p1_score": 60.0,
                        "confidence_numeric": 80,
                        "p1_signals": {"a3_blocked": False},
                    },
                ],
            }
            cm_path = self._write_json(tmpdir, "claim-map.json", cm)
            report = generate_report(cm_path)

            self.assertEqual(report["summary"]["total_claims"], 3)
            types = {c["canonical_type"] for c in report["claims"]}
            self.assertEqual(types, {"FACTUAL", "SPECULATIVE", "THEORETICAL"})

    def test_corrupt_json_file(self):
        """Corrupt JSON files → graceful error handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = os.path.join(tmpdir, "bad.json")
            with open(bad_path, "w") as f:
                f.write("{invalid json")
            report = generate_report(bad_path)
            self.assertIn("error", report)
            self.assertEqual(report["summary"]["total_claims"], 0)

    # Phase 2 enhancement tests: ④⑤⑥⑦

    def test_mode_degraded_when_no_assessment(self):
        """④ No LLM data → mode=DEGRADED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {"step": 10, "file": "o.md", "claims": [
                {"claim_id": "A", "canonical_type": "FACTUAL",
                 "p1_score": 80.0, "confidence_numeric": 80, "p1_signals": {}}]}
            cm_path = self._write_json(tmpdir, "cm.json", cm)
            report = generate_report(cm_path)
            self.assertEqual(report["mode"], "DEGRADED")

    def test_mode_full_when_assessment_present(self):
        """④ Assessment data → mode=FULL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {"step": 10, "file": "o.md", "claims": [
                {"claim_id": "A", "canonical_type": "FACTUAL",
                 "p1_score": 80.0, "confidence_numeric": 80, "p1_signals": {}}]}
            assessment = {"assessments": [{"claim_id": "A", "quality_score": 75}]}
            cm_path = self._write_json(tmpdir, "cm.json", cm)
            as_path = self._write_json(tmpdir, "as.json", assessment)
            report = generate_report(cm_path, as_path)
            self.assertEqual(report["mode"], "FULL")

    def test_critic_additions_in_pcae(self):
        """⑤ Critic additions flow into pcae.e4_critic_additions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {"step": 10, "file": "o.md", "claims": [
                {"claim_id": "A", "canonical_type": "FACTUAL",
                 "p1_score": 80.0, "confidence_numeric": 80, "p1_signals": {}}]}
            critic = {
                "judgments": [{"claim_id": "A", "adjusted_score": 70}],
                "additions": [{"claim_id": "A", "issue": "Weak evidence"}],
            }
            cm_path = self._write_json(tmpdir, "cm.json", cm)
            cr_path = self._write_json(tmpdir, "cr.json", critic)
            report = generate_report(cm_path, critic_path=cr_path)
            self.assertEqual(len(report["pcae"]["e4_critic_additions"]), 1)

    def test_high_disagreement_in_claims(self):
        """⑥ high_disagreement flag appears per claim."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {"step": 10, "file": "o.md", "claims": [
                {"claim_id": "A", "canonical_type": "FACTUAL",
                 "p1_score": 80.0, "confidence_numeric": 80, "p1_signals": {}}]}
            assessment = {"assessments": [{"claim_id": "A", "quality_score": 90}]}
            critic = {"judgments": [{"claim_id": "A", "adjusted_score": 60}]}
            cm_path = self._write_json(tmpdir, "cm.json", cm)
            as_path = self._write_json(tmpdir, "as.json", assessment)
            cr_path = self._write_json(tmpdir, "cr.json", critic)
            report = generate_report(cm_path, as_path, cr_path)
            self.assertTrue(report["claims"][0]["high_disagreement"])
            self.assertEqual(report["summary"]["disagreement_count"], 1)

    def test_no_disagreement_in_claims(self):
        """⑥ No disagreement when scores are close."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {"step": 10, "file": "o.md", "claims": [
                {"claim_id": "A", "canonical_type": "FACTUAL",
                 "p1_score": 80.0, "confidence_numeric": 80, "p1_signals": {}}]}
            assessment = {"assessments": [{"claim_id": "A", "quality_score": 75}]}
            critic = {"judgments": [{"claim_id": "A", "adjusted_score": 70}]}
            cm_path = self._write_json(tmpdir, "cm.json", cm)
            as_path = self._write_json(tmpdir, "as.json", assessment)
            cr_path = self._write_json(tmpdir, "cr.json", critic)
            report = generate_report(cm_path, as_path, cr_path)
            self.assertFalse(report["claims"][0]["high_disagreement"])
            self.assertEqual(report["summary"]["disagreement_count"], 0)

    def test_calibration_metadata_in_report(self):
        """⑦ Calibration metadata (cal_delta + total_samples) in report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {"step": 10, "file": "o.md", "claims": [
                {"claim_id": "A", "canonical_type": "FACTUAL",
                 "p1_score": 80.0, "confidence_numeric": 80, "p1_signals": {}}]}
            cal = {"cal_delta": 5.0, "total_samples": 42}
            cm_path = self._write_json(tmpdir, "cm.json", cm)
            cal_path = self._write_json(tmpdir, "cal.json", cal)
            report = generate_report(cm_path, calibration_path=cal_path)
            self.assertEqual(report["calibration"]["cal_delta"], 5.0)
            self.assertEqual(report["calibration"]["total_samples"], 42)

    def test_calibration_defaults_when_no_file(self):
        """⑦ No calibration file → defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = {"step": 10, "file": "o.md", "claims": []}
            cm_path = self._write_json(tmpdir, "cm.json", cm)
            report = generate_report(cm_path)
            self.assertEqual(report["calibration"]["cal_delta"], 0.0)
            self.assertEqual(report["calibration"]["total_samples"], 0)


if __name__ == "__main__":
    unittest.main()
