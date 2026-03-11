#!/usr/bin/env python3
"""Tests for verify_step_output.py — P1 Step Output Verification.

Tests the 5 verification checks:
    VO-1: File exists + min size
    VO-2: UTF-8 validity
    VO-3: Placeholder detection
    VO-4: GroundedClaim presence (Tier A)
    VO-5: Claim prefix match
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from verify_step_output import (
    _detect_placeholders,
    _extract_prefix,
    _resolve_output_file,
    verify_step_output,
)


class TestExtractPrefix(unittest.TestCase):
    """Test claim ID prefix extraction."""

    def test_simple_prefix(self):
        self.assertEqual(_extract_prefix("LS-001"), "LS")

    def test_multi_hyphen(self):
        self.assertEqual(_extract_prefix("EMP-NEURO-001"), "EMP-NEURO")

    def test_sub_prefix(self):
        self.assertEqual(_extract_prefix("VRA-H-003"), "VRA-H")

    def test_long_digits(self):
        self.assertEqual(_extract_prefix("SA-TA-0001"), "SA-TA")

    def test_no_digits(self):
        self.assertEqual(_extract_prefix("LS"), "LS")


class TestDetectPlaceholders(unittest.TestCase):
    """Test placeholder pattern detection."""

    def test_lorem_ipsum(self):
        result = _detect_placeholders("Some text lorem ipsum dolor sit amet")
        self.assertTrue(len(result) > 0)

    def test_todo(self):
        result = _detect_placeholders("# Section\nTODO: write this section")
        self.assertTrue(len(result) > 0)

    def test_fixme(self):
        result = _detect_placeholders("FIXME: broken reference")
        self.assertTrue(len(result) > 0)

    def test_insert_bracket(self):
        result = _detect_placeholders("The results show [insert data here]")
        self.assertTrue(len(result) > 0)

    def test_tbd(self):
        result = _detect_placeholders("The methodology is [TBD]")
        self.assertTrue(len(result) > 0)

    def test_clean_content(self):
        result = _detect_placeholders(
            "# Literature Review\n\n"
            "This section examines the theoretical foundations of AI safety.\n"
            "Smith (2020) argues that alignment is critical."
        )
        self.assertEqual(len(result), 0)


class TestResolveOutputFile(unittest.TestCase):
    """Test output file resolution from glob patterns."""

    def test_single_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wave_dir = os.path.join(tmpdir, "wave-results", "wave-1")
            os.makedirs(wave_dir)
            fpath = os.path.join(wave_dir, "step-042-literature-search.md")
            Path(fpath).write_text("content", encoding="utf-8")

            result = _resolve_output_file(tmpdir, "wave-results/wave-1/step-042-*.md")
            self.assertEqual(result, fpath)

    def test_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _resolve_output_file(tmpdir, "wave-results/wave-1/step-042-*.md")
            self.assertIsNone(result)

    def test_multiple_matches_selects_newest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wave_dir = os.path.join(tmpdir, "wave-results", "wave-1")
            os.makedirs(wave_dir)
            f1 = os.path.join(wave_dir, "step-042-old.md")
            f2 = os.path.join(wave_dir, "step-042-new.md")
            Path(f1).write_text("old", encoding="utf-8")
            import time
            time.sleep(0.05)  # ensure different mtime
            Path(f2).write_text("new", encoding="utf-8")

            result = _resolve_output_file(tmpdir, "wave-results/wave-1/step-042-*.md")
            self.assertEqual(result, f2)


class TestVerifyStepOutput(unittest.TestCase):
    """Integration tests for verify_step_output with mocked query_step."""

    def _mock_step_info(self, step, research_type="undecided"):
        """Return a mock step info dict."""
        return {
            "step": step,
            "agent": "literature-searcher",
            "output_path": f"wave-results/wave-1/step-{step:03d}-*.md",
            "min_output_bytes": 100,
            "has_grounded_claims": True,
            "pccs_required": True,
        }

    def _create_valid_output(self, project_dir, step):
        """Create a valid output file with GroundedClaims."""
        wave_dir = os.path.join(project_dir, "wave-results", "wave-1")
        os.makedirs(wave_dir, exist_ok=True)
        fpath = os.path.join(wave_dir, f"step-{step:03d}-literature-search.md")
        content = (
            "# Literature Search Results\n\n"
            "## Findings\n\n"
            "```yaml\n"
            "- id: LS-001\n"
            "  claim_type: FACTUAL\n"
            "  confidence: 90\n"
            "  claim: >-\n"
            "    AI safety research has grown exponentially.\n"
            "  source: \"Smith (2020)\"\n"
            "```\n\n"
            "The literature reveals significant growth in the field.\n"
            "Multiple sources confirm the trend identified by LS-001.\n"
        )
        Path(fpath).write_text(content, encoding="utf-8")
        return fpath

    @patch("verify_step_output._get_query_step")
    def test_valid_output_passes_all_checks(self, mock_qs):
        mock_module = type("MockQS", (), {
            "query_step": staticmethod(lambda step, rt: {
                "step": step, "agent": "literature-searcher",
                "output_path": f"wave-results/wave-1/step-{step:03d}-*.md",
                "min_output_bytes": 100, "has_grounded_claims": True,
            })
        })()
        mock_qs.return_value = mock_module

        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_valid_output(tmpdir, 42)
            result = verify_step_output(42, tmpdir)
            self.assertTrue(result["valid"])
            self.assertEqual(result["checks"]["VO1_exists"], "PASS")
            self.assertEqual(result["checks"]["VO2_utf8"], "PASS")
            self.assertEqual(result["checks"]["VO3_no_placeholder"], "PASS")
            self.assertEqual(result["checks"]["VO4_has_claims"], "PASS")
            self.assertEqual(result["checks"]["VO5_prefix_match"], "PASS")

    @patch("verify_step_output._get_query_step")
    def test_missing_file_fails_vo1(self, mock_qs):
        mock_module = type("MockQS", (), {
            "query_step": staticmethod(lambda step, rt: {
                "step": step, "agent": "literature-searcher",
                "output_path": f"wave-results/wave-1/step-{step:03d}-*.md",
                "min_output_bytes": 100, "has_grounded_claims": True,
            })
        })()
        mock_qs.return_value = mock_module

        with tempfile.TemporaryDirectory() as tmpdir:
            result = verify_step_output(42, tmpdir)
            self.assertFalse(result["valid"])
            self.assertEqual(result["checks"]["VO1_exists"], "FAIL")

    @patch("verify_step_output._get_query_step")
    def test_placeholder_fails_vo3(self, mock_qs):
        mock_module = type("MockQS", (), {
            "query_step": staticmethod(lambda step, rt: {
                "step": step, "agent": "literature-searcher",
                "output_path": f"wave-results/wave-1/step-{step:03d}-*.md",
                "min_output_bytes": 50, "has_grounded_claims": False,
            })
        })()
        mock_qs.return_value = mock_module

        with tempfile.TemporaryDirectory() as tmpdir:
            wave_dir = os.path.join(tmpdir, "wave-results", "wave-1")
            os.makedirs(wave_dir)
            fpath = os.path.join(wave_dir, "step-042-output.md")
            Path(fpath).write_text(
                "# Output\n\nTODO: write this section\n\nLorem ipsum dolor sit amet.\n",
                encoding="utf-8"
            )
            result = verify_step_output(42, tmpdir)
            self.assertFalse(result["valid"])
            self.assertEqual(result["checks"]["VO3_no_placeholder"], "FAIL")

    @patch("verify_step_output._get_query_step")
    def test_no_claims_fails_vo4(self, mock_qs):
        mock_module = type("MockQS", (), {
            "query_step": staticmethod(lambda step, rt: {
                "step": step, "agent": "literature-searcher",
                "output_path": f"wave-results/wave-1/step-{step:03d}-*.md",
                "min_output_bytes": 50, "has_grounded_claims": True,
            })
        })()
        mock_qs.return_value = mock_module

        with tempfile.TemporaryDirectory() as tmpdir:
            wave_dir = os.path.join(tmpdir, "wave-results", "wave-1")
            os.makedirs(wave_dir)
            fpath = os.path.join(wave_dir, "step-042-output.md")
            Path(fpath).write_text(
                "# Output\n\nSome analysis without any GroundedClaim blocks.\n"
                "This is just narrative text with no structured claims.\n",
                encoding="utf-8"
            )
            result = verify_step_output(42, tmpdir)
            self.assertFalse(result["valid"])
            self.assertEqual(result["checks"]["VO4_has_claims"], "FAIL")

    @patch("verify_step_output._get_query_step")
    def test_wrong_prefix_fails_vo5(self, mock_qs):
        mock_module = type("MockQS", (), {
            "query_step": staticmethod(lambda step, rt: {
                "step": step, "agent": "literature-searcher",
                "output_path": f"wave-results/wave-1/step-{step:03d}-*.md",
                "min_output_bytes": 50, "has_grounded_claims": True,
            })
        })()
        mock_qs.return_value = mock_module

        with tempfile.TemporaryDirectory() as tmpdir:
            wave_dir = os.path.join(tmpdir, "wave-results", "wave-1")
            os.makedirs(wave_dir)
            fpath = os.path.join(wave_dir, "step-042-output.md")
            # Write claims with WRONG prefix (TRA instead of LS)
            Path(fpath).write_text(
                "# Output\n\n```yaml\n- id: TRA-001\n  claim_type: FACTUAL\n"
                "  confidence: 90\n  claim: \"Wrong prefix\"\n```\n",
                encoding="utf-8"
            )
            result = verify_step_output(42, tmpdir)
            self.assertFalse(result["valid"])
            self.assertEqual(result["checks"]["VO5_prefix_match"], "FAIL")

    @patch("verify_step_output._get_query_step")
    def test_tier_b_skips_claim_checks(self, mock_qs):
        """Tier B steps (no claims expected) should skip VO-4 and VO-5."""
        mock_module = type("MockQS", (), {
            "query_step": staticmethod(lambda step, rt: {
                "step": step, "agent": "_orchestrator",
                "output_path": f"step-{step:03d}-*.md",
                "min_output_bytes": 50, "has_grounded_claims": False,
            })
        })()
        mock_qs.return_value = mock_module

        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "step-035-hitl.md")
            Path(fpath).write_text(
                "# HITL-1 Result\n\nResearch question reviewed and approved by user.\n"
                "Topic: AI Safety in Large Language Models\n",
                encoding="utf-8"
            )
            result = verify_step_output(35, tmpdir)
            self.assertTrue(result["valid"])
            self.assertTrue(result["checks"]["VO4_has_claims"].startswith("SKIP"))
            self.assertTrue(result["checks"]["VO5_prefix_match"].startswith("SKIP"))


class TestRealModuleIntegration(unittest.TestCase):
    """Integration test using REAL query_step module (no mock).

    This catches C-1: function name mismatches between verify_step_output
    and query_step that mocks would silently hide.
    """

    def test_real_query_step_call_no_crash(self):
        """verify_step_output must call query_step.query_step() without AttributeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 42 is a wave-1 literature-searcher step — always valid
            result = verify_step_output(42, tmpdir)
            # File won't exist, so VO1 should FAIL — but no AttributeError
            self.assertFalse(result["valid"])
            self.assertEqual(result["checks"]["VO1_exists"], "FAIL")
            # Verify we got a real agent prefix (proves query_step was called)
            self.assertEqual(result["expected_prefix"], "LS")

    def test_real_query_step_phase2_undecided_error(self):
        """Phase 2 step with undecided research_type should return error (GAP-6)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = verify_step_output(125, tmpdir, "undecided")
            self.assertFalse(result["valid"])
            self.assertTrue(any("HITL-3" in e for e in result["errors"]))


class TestFallbackSplitGroup(unittest.TestCase):
    """Test split_consolidated_group in fallback_controller."""

    def test_split_6_steps(self):
        from fallback_controller import split_consolidated_group
        result = split_consolidated_group([39, 40, 41, 42, 43, 44])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], [39, 40, 41])
        self.assertEqual(result[1], [42, 43, 44])

    def test_split_4_steps(self):
        from fallback_controller import split_consolidated_group
        result = split_consolidated_group([39, 40, 41, 42])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], [39, 40])
        self.assertEqual(result[1], [41, 42])

    def test_split_2_steps(self):
        from fallback_controller import split_consolidated_group
        result = split_consolidated_group([39, 40])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], [39])
        self.assertEqual(result[1], [40])

    def test_split_1_step(self):
        from fallback_controller import split_consolidated_group
        result = split_consolidated_group([39])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], [39])

    def test_split_empty(self):
        from fallback_controller import split_consolidated_group
        result = split_consolidated_group([])
        self.assertEqual(len(result), 0)

    def test_split_3_steps(self):
        from fallback_controller import split_consolidated_group
        result = split_consolidated_group([39, 40, 41])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], [39])
        self.assertEqual(result[1], [40, 41])


if __name__ == "__main__":
    unittest.main()
