#!/usr/bin/env python3
"""Tests for validate_step_sequence.py — Step dependency enforcement.

Imports PHASE_RANGES, STEP_DEPENDENCIES from checklist_manager (single source).
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_step_sequence import (
    validate_step,
    validate_all_steps,
    get_completed_steps,
    get_gate_results,
    get_hitl_results,
    PHASE_ENTRY_STEPS,
)
from checklist_manager import (
    PHASE_RANGES,
    STEP_DEPENDENCIES,
    THESIS_SOT_FILENAME,
)


def create_sot(tmpdir, outputs=None, gates=None, hitl_checkpoints=None):
    """Helper to create a thesis SOT file."""
    sot = {
        "outputs": outputs or {},
        "gates": gates or {},
        "hitl_checkpoints": hitl_checkpoints or {},
    }
    Path(tmpdir, THESIS_SOT_FILENAME).write_text(json.dumps(sot))


class TestPhaseRanges(unittest.TestCase):
    """Test phase range constants (imported from checklist_manager)."""

    def test_19_phases_defined(self):
        self.assertEqual(len(PHASE_RANGES), 19)

    def test_phases_start_at_1(self):
        min_start = min(start for start, _ in PHASE_RANGES.values())
        self.assertEqual(min_start, 1)

    def test_phases_end_at_211(self):
        max_end = max(end for _, end in PHASE_RANGES.values())
        self.assertEqual(max_end, 211)

    def test_no_gaps_in_coverage(self):
        all_steps = set()
        for start, end in PHASE_RANGES.values():
            for s in range(start, end + 1):
                all_steps.add(s)
        for s in range(1, 212):
            self.assertIn(s, all_steps, f"Step {s} not in any phase")

    def test_phase_entry_steps_derived(self):
        for step, phase_name in PHASE_ENTRY_STEPS.items():
            start, _ = PHASE_RANGES[phase_name]
            self.assertEqual(step, start)


class TestGetCompletedSteps(unittest.TestCase):
    """Test step extraction from SOT."""

    def test_empty_outputs(self):
        self.assertEqual(get_completed_steps({"outputs": {}}), set())

    def test_step_extraction(self):
        sot = {"outputs": {"step-1": "done", "step-5": "done", "step-5-ko": "done"}}
        result = get_completed_steps(sot)
        self.assertEqual(result, {1, 5})

    def test_ko_excluded(self):
        sot = {"outputs": {"step-1-ko": "done"}}
        result = get_completed_steps(sot)
        self.assertEqual(result, set())


class TestGetGateResults(unittest.TestCase):
    def test_gate_dict(self):
        sot = {"gates": {"gate-1": {"status": "pass"}}}
        result = get_gate_results(sot)
        self.assertEqual(result["gate-1"], "pass")

    def test_gate_string(self):
        sot = {"gates": {"gate-1": "pass"}}
        result = get_gate_results(sot)
        self.assertEqual(result["gate-1"], "pass")


class TestGetHITLResults(unittest.TestCase):
    def test_hitl_dict(self):
        sot = {"hitl_checkpoints": {"hitl-2": {"status": "completed"}}}
        result = get_hitl_results(sot)
        self.assertEqual(result["hitl-2"], "completed")

    def test_empty_hitl(self):
        sot = {"hitl_checkpoints": {}}
        result = get_hitl_results(sot)
        self.assertEqual(result, {})

    def test_missing_hitl_key(self):
        """SOT without hitl_checkpoints key returns empty dict."""
        sot = {}
        result = get_hitl_results(sot)
        self.assertEqual(result, {})


class TestValidateStep(unittest.TestCase):
    """Test step validation."""

    def test_no_sot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_step(tmpdir, 1)
            self.assertFalse(result["can_proceed"])

    def test_step_1_always_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_sot(tmpdir)
            result = validate_step(tmpdir, 1)
            self.assertTrue(result["can_proceed"])

    def test_step_2_requires_step_1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_sot(tmpdir)
            result = validate_step(tmpdir, 2)
            self.assertFalse(result["can_proceed"])
            self.assertTrue(any("step 1" in e.lower() for e in result["errors"]))

    def test_step_2_with_step_1_completed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_sot(tmpdir, outputs={"step-1": "done"})
            result = validate_step(tmpdir, 2)
            self.assertTrue(result["can_proceed"])

    def test_gate_prerequisite_block(self):
        """Wave-2 (step 59) requires gate-1. Without it, should block."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = {f"step-{i}": "done" for i in range(1, 59)}
            create_sot(tmpdir, outputs=outputs)
            result = validate_step(tmpdir, 59)
            self.assertFalse(result["can_proceed"])
            self.assertTrue(any("gate" in e.lower() for e in result["errors"]))

    def test_gate_prerequisite_pass(self):
        """Wave-2 (step 59) with gate-1 passed should proceed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = {f"step-{i}": "done" for i in range(1, 59)}
            gates = {"gate-1": {"status": "pass"}}
            create_sot(tmpdir, outputs=outputs, gates=gates)
            result = validate_step(tmpdir, 59)
            self.assertTrue(result["can_proceed"])

    def test_hitl_prerequisite_block(self):
        """Phase-2 (step 121) requires hitl-2. Without it, should block."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = {f"step-{i}": "done" for i in range(1, 121)}
            create_sot(tmpdir, outputs=outputs)
            result = validate_step(tmpdir, 121)
            self.assertFalse(result["can_proceed"])
            self.assertTrue(any("hitl" in e.lower() for e in result["errors"]))

    def test_hitl_prerequisite_pass(self):
        """Phase-2 (step 121) with hitl-2 completed should proceed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = {f"step-{i}": "done" for i in range(1, 121)}
            hitl = {"hitl-2": {"status": "completed"}}
            create_sot(tmpdir, outputs=outputs, hitl_checkpoints=hitl)
            result = validate_step(tmpdir, 121)
            self.assertTrue(result["can_proceed"])

    def test_already_completed_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_sot(tmpdir, outputs={"step-1": "done"})
            result = validate_step(tmpdir, 1)
            self.assertTrue(result["can_proceed"])
            self.assertTrue(any("already completed" in w.lower() for w in result["warnings"]))

    def test_phase_entry_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_sot(tmpdir)
            result = validate_step(tmpdir, 1)
            self.assertTrue(any("entering" in w.lower() for w in result["warnings"]))


class TestValidateAllSteps(unittest.TestCase):
    """Test full sequence validation."""

    def test_no_sot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = validate_all_steps(tmpdir)
            self.assertTrue(any("error" in r for r in results))

    def test_no_completed_steps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_sot(tmpdir)
            results = validate_all_steps(tmpdir)
            self.assertTrue(any("info" in r for r in results))

    def test_gap_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_sot(tmpdir, outputs={"step-1": "done", "step-3": "done"})
            results = validate_all_steps(tmpdir)
            self.assertTrue(any(r.get("issue") == "gap" for r in results))

    def test_sequential_no_issues(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = {f"step-{i}": "done" for i in range(1, 6)}
            create_sot(tmpdir, outputs=outputs)
            results = validate_all_steps(tmpdir)
            self.assertFalse(any("issue" in r for r in results))


class TestNoSystemSOTReference(unittest.TestCase):
    def test_no_state_yaml_reference(self):
        content = (SCRIPT_DIR / "validate_step_sequence.py").read_text(encoding="utf-8")
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            self.assertNotIn("state.yaml", line, f"Line {i}")
            self.assertNotIn("state.yml", line, f"Line {i}")


if __name__ == "__main__":
    unittest.main()
