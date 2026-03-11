#!/usr/bin/env python3
"""Tests for determine_dialogue_outcome.py — P1 Dialogue Decision.

Tests the deterministic dialogue outcome rules:
    - All PASS → consensus
    - Any FAIL + round < max → continue_round
    - Any FAIL + round >= max → escalate
    - Missing files → continue_round
    - Null verdicts → continue_round (or escalate at max)
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from determine_dialogue_outcome import determine_outcome


def _create_project(tmpdir: str, step: int, domain: str = "research",
                    max_rounds: int = 3) -> str:
    """Create a project directory with SOT and dialogue state."""
    project_dir = os.path.join(tmpdir, "thesis-project")
    os.makedirs(project_dir, exist_ok=True)
    dlg_dir = os.path.join(project_dir, "dialogue-logs")
    os.makedirs(dlg_dir, exist_ok=True)

    sot = {
        "current_step": step,
        "dialogue_state": {
            "domain": domain,
            "rounds_used": 1,
            "max_rounds": max_rounds,
        }
    }
    with open(os.path.join(project_dir, "session.json"), "w") as f:
        json.dump(sot, f)

    return project_dir


def _write_critic_file(project_dir: str, step: int, round_num: int,
                       critic_type: str, verdict: str) -> None:
    """Write a critic file with a given verdict."""
    dlg_dir = os.path.join(project_dir, "dialogue-logs")
    filename = f"step-{step}-r{round_num}-{critic_type}.md"
    filepath = os.path.join(dlg_dir, filename)
    content = f"# Critic Report\n\n## Analysis\nSome analysis.\n\n## Verdict: {verdict}\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


class TestConsensus(unittest.TestCase):
    """Rule 2: All verdicts PASS → consensus."""

    def test_research_both_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            _write_critic_file(proj, 5, 1, "fc", "PASS")
            _write_critic_file(proj, 5, 1, "rv", "PASS")
            result = determine_outcome(proj, 5, 1)
            self.assertEqual(result["outcome"], "consensus")

    def test_development_single_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5, domain="development")
            _write_critic_file(proj, 5, 1, "cr", "PASS")
            result = determine_outcome(proj, 5, 1)
            self.assertEqual(result["outcome"], "consensus")


class TestContinueRound(unittest.TestCase):
    """Rule 3: Any FAIL + round < max → continue_round."""

    def test_one_fail_round1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            _write_critic_file(proj, 5, 1, "fc", "PASS")
            _write_critic_file(proj, 5, 1, "rv", "FAIL")
            result = determine_outcome(proj, 5, 1, max_rounds=3)
            self.assertEqual(result["outcome"], "continue_round")

    def test_both_fail_round1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            _write_critic_file(proj, 5, 1, "fc", "FAIL")
            _write_critic_file(proj, 5, 1, "rv", "FAIL")
            result = determine_outcome(proj, 5, 1, max_rounds=3)
            self.assertEqual(result["outcome"], "continue_round")

    def test_development_fail_round1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5, domain="development")
            _write_critic_file(proj, 5, 1, "cr", "FAIL")
            result = determine_outcome(proj, 5, 1, max_rounds=3)
            self.assertEqual(result["outcome"], "continue_round")


class TestEscalate(unittest.TestCase):
    """Rule 4: Any FAIL + round >= max → escalate."""

    def test_fail_at_max_round(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            _write_critic_file(proj, 5, 3, "fc", "PASS")
            _write_critic_file(proj, 5, 3, "rv", "FAIL")
            result = determine_outcome(proj, 5, 3, max_rounds=3)
            self.assertEqual(result["outcome"], "escalate")

    def test_all_fail_at_max_round(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            _write_critic_file(proj, 5, 3, "fc", "FAIL")
            _write_critic_file(proj, 5, 3, "rv", "FAIL")
            result = determine_outcome(proj, 5, 3, max_rounds=3)
            self.assertEqual(result["outcome"], "escalate")

    def test_pass_at_max_round_is_consensus(self):
        """Even at max round, all PASS → consensus (not escalate)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            _write_critic_file(proj, 5, 3, "fc", "PASS")
            _write_critic_file(proj, 5, 3, "rv", "PASS")
            result = determine_outcome(proj, 5, 3, max_rounds=3)
            self.assertEqual(result["outcome"], "consensus")


class TestMissingFiles(unittest.TestCase):
    """Rule 5: Missing critic files → continue_round (or escalate at max)."""

    def test_no_critic_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            # No critic files written
            result = determine_outcome(proj, 5, 1)
            self.assertEqual(result["outcome"], "continue_round")
            self.assertTrue(len(result.get("missing_files", [])) > 0)

    def test_partial_critic_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            _write_critic_file(proj, 5, 1, "fc", "PASS")
            # rv file missing
            result = determine_outcome(proj, 5, 1)
            self.assertEqual(result["outcome"], "continue_round")

    def test_missing_files_at_max_round_escalates(self):
        """C-2 fix: Missing files at max round must escalate, not infinite loop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            # No critic files at max round
            result = determine_outcome(proj, 5, 3, max_rounds=3)
            self.assertEqual(result["outcome"], "escalate")
            self.assertIn("infinite loop", result["reason"])

    def test_partial_files_at_max_round_escalates(self):
        """C-2 fix: Partial files at max round must also escalate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            _write_critic_file(proj, 5, 3, "fc", "PASS")
            # rv file missing at max round
            result = determine_outcome(proj, 5, 3, max_rounds=3)
            self.assertEqual(result["outcome"], "escalate")


class TestNullVerdicts(unittest.TestCase):
    """Rule: File exists but verdict not extractable → retry or escalate."""

    def test_no_verdict_in_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            # Write file without verdict section
            dlg_dir = os.path.join(proj, "dialogue-logs")
            with open(os.path.join(dlg_dir, "step-5-r1-fc.md"), "w") as f:
                f.write("# Some content without verdict")
            _write_critic_file(proj, 5, 1, "rv", "PASS")
            result = determine_outcome(proj, 5, 1, max_rounds=3)
            self.assertEqual(result["outcome"], "continue_round")

    def test_no_verdict_at_max_round(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            dlg_dir = os.path.join(proj, "dialogue-logs")
            with open(os.path.join(dlg_dir, "step-5-r3-fc.md"), "w") as f:
                f.write("# No verdict")
            _write_critic_file(proj, 5, 3, "rv", "PASS")
            result = determine_outcome(proj, 5, 3, max_rounds=3)
            self.assertEqual(result["outcome"], "escalate")


class TestOutputFields(unittest.TestCase):
    """Verify output JSON structure."""

    def test_output_has_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            _write_critic_file(proj, 5, 1, "fc", "PASS")
            _write_critic_file(proj, 5, 1, "rv", "PASS")
            result = determine_outcome(proj, 5, 1)

            self.assertIn("outcome", result)
            self.assertIn("round", result)
            self.assertIn("max_rounds", result)
            self.assertIn("verdicts", result)
            self.assertIn("reason", result)
            self.assertIn("da_valid", result)

    def test_verdicts_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5)
            _write_critic_file(proj, 5, 1, "fc", "PASS")
            _write_critic_file(proj, 5, 1, "rv", "FAIL")
            result = determine_outcome(proj, 5, 1)
            self.assertEqual(result["verdicts"]["fc"], "PASS")
            self.assertEqual(result["verdicts"]["rv"], "FAIL")


class TestMaxRoundsFromSOT(unittest.TestCase):
    """SOT max_rounds should be used when caller doesn't override."""

    def test_sot_max_rounds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = _create_project(tmpdir, step=5, max_rounds=5)
            _write_critic_file(proj, 5, 3, "fc", "FAIL")
            _write_critic_file(proj, 5, 3, "rv", "FAIL")
            # round 3 < sot max_rounds 5 → continue
            result = determine_outcome(proj, 5, 3)
            self.assertEqual(result["outcome"], "continue_round")
            self.assertEqual(result["max_rounds"], 5)


if __name__ == "__main__":
    unittest.main()
