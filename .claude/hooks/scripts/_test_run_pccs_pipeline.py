#!/usr/bin/env python3
"""Tests for run_pccs_pipeline.py — P1 Pipeline Runner.

Tests DEGRADED mode (single call), FULL mode (3-phase), and edge cases.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_pccs_pipeline import (
    run_degraded,
    run_full_after_b1,
    run_full_finalize,
    run_full_prepare,
)


def _write_json(tmpdir: str, name: str, data: dict) -> str:
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def _write_text(tmpdir: str, name: str, text: str) -> str:
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _make_claim_file(tmpdir: str) -> str:
    """Create a minimal thesis output .md file with one GroundedClaim."""
    content = (
        "# Wave 1 Output\n\n"
        "```yaml\n"
        "- id: EMP-001\n"
        "  claim_type: EMPIRICAL\n"
        "  confidence: 85\n"
        "  text: \"Studies show that X leads to Y (Smith, 2020).\"\n"
        "  sources:\n"
        "    - \"Smith (2020) Journal of Research\"\n"
        "```\n"
    )
    return _write_text(tmpdir, "wave1-output.md", content)


# =============================================================================
# DEGRADED Mode Tests
# =============================================================================

class TestRunDegraded(unittest.TestCase):
    """Test the single-invocation DEGRADED pipeline."""

    def test_basic_degraded(self):
        """DEGRADED mode produces a report with mode=DEGRADED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claim_file = _make_claim_file(tmpdir)
            work_dir = os.path.join(tmpdir, "work")
            report = run_degraded(claim_file, 42, tmpdir, work_dir=work_dir)

            self.assertEqual(report["mode"], "DEGRADED")
            self.assertEqual(report["step"], 42)
            self.assertIn("summary", report)
            self.assertIn("decision", report)
            self.assertIn("claims", report)
            self.assertIn("calibration", report)

    def test_degraded_creates_intermediates(self):
        """Work directory should contain intermediate files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claim_file = _make_claim_file(tmpdir)
            work_dir = os.path.join(tmpdir, "work")
            run_degraded(claim_file, 10, tmpdir, work_dir=work_dir)

            self.assertTrue(os.path.exists(os.path.join(work_dir, "claim-map.json")))
            self.assertTrue(os.path.exists(os.path.join(work_dir, "pccs-calibration.json")))
            self.assertTrue(os.path.exists(os.path.join(work_dir, "pccs-report.json")))
            self.assertTrue(os.path.exists(os.path.join(work_dir, "pccs-validation.json")))

    def test_degraded_custom_output(self):
        """Output path override should work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claim_file = _make_claim_file(tmpdir)
            out_path = os.path.join(tmpdir, "custom-report.json")
            run_degraded(claim_file, 10, tmpdir, output_path=out_path)

            self.assertTrue(os.path.exists(out_path))
            with open(out_path) as f:
                report = json.load(f)
            self.assertEqual(report["mode"], "DEGRADED")

    def test_degraded_calibration_computed(self):
        """Calibration should be computed (fixing the disconnected loop bug)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claim_file = _make_claim_file(tmpdir)
            work_dir = os.path.join(tmpdir, "work")
            report = run_degraded(claim_file, 42, tmpdir, work_dir=work_dir)

            # Calibration block should exist in report
            self.assertIn("calibration", report)
            self.assertIn("cal_delta", report["calibration"])
            # With no ground truth logs, cal_delta should be 0.0
            self.assertEqual(report["calibration"]["cal_delta"], 0.0)

    def test_degraded_empty_file(self):
        """Empty file → 0 claims, proceed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claim_file = _write_text(tmpdir, "empty.md", "# Nothing here\n")
            report = run_degraded(claim_file, 1, tmpdir)
            self.assertEqual(report["summary"]["total_claims"], 0)
            self.assertEqual(report["decision"]["action"], "proceed")

    def test_degraded_auto_tempdir(self):
        """Without explicit work_dir, tempdir should be auto-created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claim_file = _make_claim_file(tmpdir)
            report = run_degraded(claim_file, 10, tmpdir)
            self.assertIsNotNone(report)
            self.assertEqual(report["mode"], "DEGRADED")


# =============================================================================
# FULL Mode Tests — prepare phase
# =============================================================================

class TestRunFullPrepare(unittest.TestCase):
    """Test FULL mode Phase 1: prepare."""

    def test_prepare_creates_claim_map(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            claim_file = _make_claim_file(tmpdir)
            work_dir = os.path.join(tmpdir, "work")
            result = run_full_prepare(claim_file, 42, tmpdir, work_dir)

            self.assertIn("claim_map_path", result)
            self.assertTrue(os.path.exists(result["claim_map_path"]))

    def test_prepare_creates_calibration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            claim_file = _make_claim_file(tmpdir)
            work_dir = os.path.join(tmpdir, "work")
            run_full_prepare(claim_file, 42, tmpdir, work_dir)

            cal_path = os.path.join(work_dir, "pccs-calibration.json")
            self.assertTrue(os.path.exists(cal_path))

    def test_prepare_creates_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            claim_file = _make_claim_file(tmpdir)
            work_dir = os.path.join(tmpdir, "work")
            run_full_prepare(claim_file, 42, tmpdir, work_dir)

            meta_path = os.path.join(work_dir, "_pipeline-meta.json")
            self.assertTrue(os.path.exists(meta_path))
            with open(meta_path) as f:
                meta = json.load(f)
            self.assertEqual(meta["step"], 42)


# =============================================================================
# FULL Mode Tests — after-b1 phase
# =============================================================================

class TestRunFullAfterB1(unittest.TestCase):
    """Test FULL mode Phase 2: after-b1."""

    def _setup_work_dir(self, tmpdir: str) -> str:
        """Create work_dir with claim-map.json from prepare phase."""
        work_dir = os.path.join(tmpdir, "work")
        os.makedirs(work_dir, exist_ok=True)
        claim_map = {
            "step": 42,
            "file": "output.md",
            "claims": [
                {"claim_id": "EMP-001", "canonical_type": "EMPIRICAL",
                 "p1_score": 70.0, "confidence_numeric": 80}
            ],
        }
        _write_json(work_dir, "claim-map.json", claim_map)
        return work_dir

    def test_extracts_valid_json(self):
        """Valid ```json block → pccs-assessment.json created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = self._setup_work_dir(tmpdir)
            b1_response = _write_text(tmpdir, "b1.txt", (
                "Here is my evaluation:\n"
                "```json\n"
                '{"assessments": [{"claim_id": "EMP-001", "quality_score": 75, '
                '"specificity": 20, "evidence_alignment": 20, '
                '"logical_soundness": 18, "contribution": 17}]}\n'
                "```\n"
            ))
            result = run_full_after_b1(work_dir, b1_response)
            self.assertTrue(os.path.exists(result["assessment_path"]))
            with open(result["assessment_path"]) as f:
                data = json.load(f)
            self.assertEqual(len(data["assessments"]), 1)

    def test_invalid_json_fallback(self):
        """No valid JSON → empty assessment fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = self._setup_work_dir(tmpdir)
            b1_response = _write_text(tmpdir, "b1.txt", "No JSON here at all")
            result = run_full_after_b1(work_dir, b1_response)
            with open(result["assessment_path"]) as f:
                data = json.load(f)
            self.assertEqual(data["assessments"], [])

    def test_unreadable_file_fallback(self):
        """Non-existent file → empty assessment fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = self._setup_work_dir(tmpdir)
            result = run_full_after_b1(work_dir, "/nonexistent/b1.txt")
            with open(result["assessment_path"]) as f:
                data = json.load(f)
            self.assertEqual(data["assessments"], [])

    def test_validation_result_returned(self):
        """Validation passed/failed status should be in result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = self._setup_work_dir(tmpdir)
            b1_response = _write_text(tmpdir, "b1.txt", (
                "```json\n"
                '{"assessments": [{"claim_id": "EMP-001", "quality_score": 75}]}\n'
                "```\n"
            ))
            result = run_full_after_b1(work_dir, b1_response)
            self.assertIn("validation_passed", result)


# =============================================================================
# FULL Mode Tests — finalize phase
# =============================================================================

class TestRunFullFinalize(unittest.TestCase):
    """Test FULL mode Phase 3: finalize."""

    def _setup_work_dir(self, tmpdir: str) -> str:
        """Create work_dir with claim-map + assessment from prior phases."""
        work_dir = os.path.join(tmpdir, "work")
        os.makedirs(work_dir, exist_ok=True)
        claim_map = {
            "step": 42,
            "file": "output.md",
            "claims": [
                {"claim_id": "EMP-001", "canonical_type": "EMPIRICAL",
                 "p1_score": 70.0, "confidence_numeric": 80,
                 "p1_signals": {"a3_blocked": False}}
            ],
        }
        assessment = {
            "assessments": [{"claim_id": "EMP-001", "quality_score": 75}]
        }
        calibration = {"cal_delta": 3.0, "total_samples": 10}
        _write_json(work_dir, "claim-map.json", claim_map)
        _write_json(work_dir, "pccs-assessment.json", assessment)
        _write_json(work_dir, "pccs-calibration.json", calibration)
        return work_dir

    def test_finalize_produces_full_report(self):
        """Finalize with valid critic → FULL mode report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = self._setup_work_dir(tmpdir)
            b2_response = _write_text(tmpdir, "b2.txt", (
                "```json\n"
                '{"judgments": [{"claim_id": "EMP-001", "adjusted_score": 70}], '
                '"additions": []}\n'
                "```\n"
            ))
            report = run_full_finalize(work_dir, b2_response, tmpdir)
            self.assertEqual(report["mode"], "FULL")
            self.assertEqual(report["step"], 42)
            self.assertEqual(len(report["claims"]), 1)

    def test_finalize_creates_report_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = self._setup_work_dir(tmpdir)
            b2_response = _write_text(tmpdir, "b2.txt", (
                '```json\n{"judgments": [], "additions": []}\n```\n'
            ))
            run_full_finalize(work_dir, b2_response, tmpdir)
            self.assertTrue(os.path.exists(os.path.join(work_dir, "pccs-report.json")))

    def test_finalize_custom_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = self._setup_work_dir(tmpdir)
            out_path = os.path.join(tmpdir, "final.json")
            b2_response = _write_text(tmpdir, "b2.txt", (
                '```json\n{"judgments": [], "additions": []}\n```\n'
            ))
            run_full_finalize(work_dir, b2_response, tmpdir, output_path=out_path)
            self.assertTrue(os.path.exists(out_path))

    def test_finalize_critic_additions_in_pcae(self):
        """Critic additions should flow into pcae.e4_critic_additions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = self._setup_work_dir(tmpdir)
            b2_response = _write_text(tmpdir, "b2.txt", (
                '```json\n'
                '{"judgments": [{"claim_id": "EMP-001", "adjusted_score": 65}], '
                '"additions": [{"claim_id": "EMP-001", "issue": "Weak evidence", "severity": "high"}]}\n'
                '```\n'
            ))
            report = run_full_finalize(work_dir, b2_response, tmpdir)
            self.assertEqual(len(report["pcae"]["e4_critic_additions"]), 1)

    def test_finalize_invalid_critic_fallback(self):
        """Invalid critic response → empty fallback, report still generated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = self._setup_work_dir(tmpdir)
            b2_response = _write_text(tmpdir, "b2.txt", "No JSON")
            report = run_full_finalize(work_dir, b2_response, tmpdir)
            # Should still produce a report (FULL mode since assessment exists)
            self.assertEqual(report["mode"], "FULL")

    def test_finalize_calibration_applied(self):
        """Calibration delta should be applied to scores."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = self._setup_work_dir(tmpdir)
            b2_response = _write_text(tmpdir, "b2.txt", (
                '```json\n{"judgments": [], "additions": []}\n```\n'
            ))
            report = run_full_finalize(work_dir, b2_response, tmpdir)
            # cal_delta=3.0 should be reflected in claim output
            self.assertEqual(report["claims"][0]["cal_delta"], 3.0)


# =============================================================================
# Full Pipeline Integration Test
# =============================================================================

class TestFullPipelineIntegration(unittest.TestCase):
    """Test the complete 3-phase FULL pipeline end-to-end."""

    def test_full_pipeline_end_to_end(self):
        """prepare → after-b1 → finalize produces consistent report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claim_file = _make_claim_file(tmpdir)
            work_dir = os.path.join(tmpdir, "work")

            # Phase 1: Prepare
            prep = run_full_prepare(claim_file, 50, tmpdir, work_dir)
            self.assertTrue(os.path.exists(prep["claim_map_path"]))

            # Phase 2: After B-1 (simulated evaluator response)
            b1_response = _write_text(tmpdir, "b1.txt", (
                "```json\n"
                '{"assessments": [{"claim_id": "EMP-001", "quality_score": 72}]}\n'
                "```\n"
            ))
            b1_result = run_full_after_b1(work_dir, b1_response)
            self.assertTrue(os.path.exists(b1_result["assessment_path"]))

            # Phase 3: Finalize (simulated critic response)
            b2_response = _write_text(tmpdir, "b2.txt", (
                "```json\n"
                '{"judgments": [{"claim_id": "EMP-001", "adjusted_score": 68}], '
                '"additions": []}\n'
                "```\n"
            ))
            report = run_full_finalize(work_dir, b2_response, tmpdir)

            # Verify end-to-end consistency
            self.assertEqual(report["mode"], "FULL")
            self.assertEqual(report["step"], 50)
            self.assertEqual(len(report["claims"]), 1)
            claim = report["claims"][0]
            self.assertEqual(claim["claim_id"], "EMP-001")
            # LLM score: (72+68)/2 = 70
            self.assertEqual(claim["llm_assessment"], 70)
            self.assertGreater(claim["pccs"], 0)


if __name__ == "__main__":
    unittest.main()
