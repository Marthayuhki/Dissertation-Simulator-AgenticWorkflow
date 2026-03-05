#!/usr/bin/env python3
"""Tests for checklist_manager.py — thesis workflow SOT management.

Run: python3 -m pytest _test_checklist_manager.py -v
  or: python3 _test_checklist_manager.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add script directory to path
sys.path.insert(0, str(Path(__file__).parent))

import checklist_manager as cm


class TestSchemaValidation(unittest.TestCase):
    """Test validate_thesis_sot() — TS1 through TS10."""

    def _make_valid_sot(self, **overrides):
        sot = cm.create_initial_sot("test-project")
        sot.update(overrides)
        return sot

    def test_ts1_root_must_be_dict(self):
        errors = cm.validate_thesis_sot([1, 2, 3])
        self.assertEqual(len(errors), 1)
        self.assertIn("TS1", errors[0])

    def test_ts2_missing_required_keys(self):
        errors = cm.validate_thesis_sot({"project_name": "x"})
        self.assertTrue(any("TS2" in e for e in errors))

    def test_ts3_invalid_status(self):
        sot = self._make_valid_sot(status="active")
        errors = cm.validate_thesis_sot(sot)
        self.assertTrue(any("TS3" in e for e in errors))

    def test_ts3_valid_statuses(self):
        for status in cm.VALID_STATUSES:
            sot = self._make_valid_sot(status=status)
            errors = cm.validate_thesis_sot(sot)
            status_errors = [e for e in errors if "TS3" in e]
            self.assertEqual(len(status_errors), 0, f"Status '{status}' should be valid")

    def test_ts4_negative_current_step(self):
        sot = self._make_valid_sot(current_step=-1)
        errors = cm.validate_thesis_sot(sot)
        self.assertTrue(any("TS4" in e for e in errors))

    def test_ts5_current_exceeds_total(self):
        sot = self._make_valid_sot(current_step=300, total_steps=210)
        errors = cm.validate_thesis_sot(sot)
        self.assertTrue(any("TS5" in e for e in errors))

    def test_ts6_invalid_research_type(self):
        sot = self._make_valid_sot(research_type="invalid")
        errors = cm.validate_thesis_sot(sot)
        self.assertTrue(any("TS6" in e for e in errors))

    def test_ts7_invalid_input_mode(self):
        sot = self._make_valid_sot(input_mode="Z")
        errors = cm.validate_thesis_sot(sot)
        self.assertTrue(any("TS7" in e for e in errors))

    def test_ts8_outputs_not_dict(self):
        sot = self._make_valid_sot(outputs="bad")
        errors = cm.validate_thesis_sot(sot)
        self.assertTrue(any("TS8" in e for e in errors))

    def test_ts8_output_value_not_string(self):
        sot = self._make_valid_sot(outputs={"step-1": 123})
        errors = cm.validate_thesis_sot(sot)
        self.assertTrue(any("TS8" in e for e in errors))

    def test_ts9_invalid_gate_status(self):
        sot = self._make_valid_sot()
        sot["gates"]["gate-1"]["status"] = "invalid"
        errors = cm.validate_thesis_sot(sot)
        self.assertTrue(any("TS9" in e for e in errors))

    def test_ts10_invalid_timestamp(self):
        sot = self._make_valid_sot(created_at="not-a-date")
        errors = cm.validate_thesis_sot(sot)
        self.assertTrue(any("TS10" in e for e in errors))

    def test_ts11_invalid_execution_mode(self):
        sot = self._make_valid_sot(execution_mode="turbo")
        errors = cm.validate_thesis_sot(sot)
        self.assertTrue(any("TS11" in e for e in errors))

    def test_ts11_valid_execution_modes(self):
        for mode in cm.VALID_EXECUTION_MODES:
            sot = self._make_valid_sot(execution_mode=mode)
            errors = cm.validate_thesis_sot(sot)
            mode_errors = [e for e in errors if "TS11" in e]
            self.assertEqual(len(mode_errors), 0, f"Mode '{mode}' should be valid")

    def test_valid_sot_no_errors(self):
        sot = self._make_valid_sot()
        errors = cm.validate_thesis_sot(sot)
        self.assertEqual(errors, [])


class TestAtomicWrite(unittest.TestCase):
    """Test atomic_write_json() — crash-safe file writes."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_creates_file(self):
        filepath = self.tmpdir / "test.json"
        cm.atomic_write_json(filepath, {"key": "value"})
        self.assertTrue(filepath.exists())
        data = json.loads(filepath.read_text())
        self.assertEqual(data["key"], "value")

    def test_overwrites_existing(self):
        filepath = self.tmpdir / "test.json"
        cm.atomic_write_json(filepath, {"v": 1})
        cm.atomic_write_json(filepath, {"v": 2})
        data = json.loads(filepath.read_text())
        self.assertEqual(data["v"], 2)

    def test_creates_parent_dirs(self):
        filepath = self.tmpdir / "a" / "b" / "test.json"
        cm.atomic_write_json(filepath, {"nested": True})
        self.assertTrue(filepath.exists())

    def test_no_temp_files_left(self):
        filepath = self.tmpdir / "test.json"
        cm.atomic_write_json(filepath, {"clean": True})
        # Only the target file should exist
        files = list(self.tmpdir.iterdir())
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "test.json")


class TestInitProject(unittest.TestCase):
    """Test init_project() — full project initialization."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "test-thesis"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_creates_directory_structure(self):
        cm.init_project(self.project_dir, "Test Thesis")

        expected_dirs = [
            "wave-results/wave-1", "wave-results/wave-2", "wave-results/wave-3",
            "wave-results/wave-4", "wave-results/wave-5",
            "gate-reports", "research-design", "thesis-drafts",
            "submission-package", "verification-logs", "pacs-logs",
            "review-logs", "fallback-logs", "checkpoints", "user-resource",
        ]
        for d in expected_dirs:
            self.assertTrue((self.project_dir / d).is_dir(), f"Missing directory: {d}")

    def test_creates_sot(self):
        cm.init_project(self.project_dir, "Test Thesis")
        sot_path = self.project_dir / cm.THESIS_SOT_FILENAME
        self.assertTrue(sot_path.exists())

        sot = json.loads(sot_path.read_text())
        self.assertEqual(sot["project_name"], "Test Thesis")
        self.assertEqual(sot["status"], "running")
        self.assertEqual(sot["current_step"], 0)

    def test_creates_checklist(self):
        cm.init_project(self.project_dir, "Test Thesis")
        cl_path = self.project_dir / cm.THESIS_CHECKLIST_FILENAME
        self.assertTrue(cl_path.exists())
        content = cl_path.read_text()
        self.assertIn("Step 1:", content)
        self.assertIn("- [ ]", content)

    def test_creates_insights_file(self):
        cm.init_project(self.project_dir, "Test Thesis")
        ins_path = self.project_dir / cm.THESIS_INSIGHTS_FILENAME
        self.assertTrue(ins_path.exists())

    def test_respects_research_type(self):
        sot = cm.init_project(self.project_dir, "Test", research_type="qualitative")
        self.assertEqual(sot["research_type"], "qualitative")

    def test_respects_input_mode(self):
        sot = cm.init_project(self.project_dir, "Test", input_mode="D")
        self.assertEqual(sot["input_mode"], "D")

    def test_respects_execution_mode(self):
        sot = cm.init_project(self.project_dir, "Test", execution_mode="autopilot+ulw")
        self.assertEqual(sot["execution_mode"], "autopilot+ulw")

    def test_default_execution_mode_is_interactive(self):
        sot = cm.init_project(self.project_dir, "Test")
        self.assertEqual(sot["execution_mode"], "interactive")

    def test_returns_valid_sot(self):
        sot = cm.init_project(self.project_dir, "Test")
        errors = cm.validate_thesis_sot(sot)
        self.assertEqual(errors, [])


class TestStepAdvancement(unittest.TestCase):
    """Test advance_step() and dependency checking."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        cm.init_project(self.project_dir, "Test")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_advance_forward(self):
        sot = cm.advance_step(self.project_dir, 1)
        self.assertEqual(sot["current_step"], 1)

    def test_advance_multiple_steps(self):
        cm.advance_step(self.project_dir, 5)
        sot = cm.advance_step(self.project_dir, 10)
        self.assertEqual(sot["current_step"], 10)

    def test_cannot_go_backward(self):
        cm.advance_step(self.project_dir, 10)
        with self.assertRaises(ValueError):
            cm.advance_step(self.project_dir, 5)

    def test_force_backward(self):
        cm.advance_step(self.project_dir, 10)
        sot = cm.advance_step(self.project_dir, 5, force=True)
        self.assertEqual(sot["current_step"], 5)

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            cm.advance_step(self.project_dir, 999)

    def test_dependency_wave2_needs_gate1(self):
        """Wave 2 requires gate-1 to pass."""
        # Advance to wave-2 range without passing gate-1
        cm.advance_step(self.project_dir, 54)  # end of wave-1
        unmet = cm.check_step_dependencies(
            cm.read_thesis_sot(self.project_dir), 55  # start of wave-2
        )
        self.assertTrue(len(unmet) > 0)
        self.assertTrue(any("gate-1" in u for u in unmet))

    def test_dependency_met_after_gate_pass(self):
        """After gate passes, dependency is met."""
        cm.advance_step(self.project_dir, 54)
        cm.record_gate_result(self.project_dir, "gate-1", "pass")
        unmet = cm.check_step_dependencies(
            cm.read_thesis_sot(self.project_dir), 55
        )
        # Only phase dependency might remain
        gate_unmet = [u for u in unmet if "gate-1" in u]
        self.assertEqual(len(gate_unmet), 0)

    def test_checklist_syncs_on_advance(self):
        cm.advance_step(self.project_dir, 3)
        cl = (self.project_dir / cm.THESIS_CHECKLIST_FILENAME).read_text()
        # Steps 1-3 should be checked
        self.assertIn("- [x] Step 1:", cl)
        self.assertIn("- [x] Step 3:", cl)
        # Step 4 should remain unchecked
        self.assertIn("- [ ] Step 4:", cl)


class TestOutputRecording(unittest.TestCase):
    """Test record_output() and record_translation()."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        cm.init_project(self.project_dir, "Test")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_record_output(self):
        sot = cm.record_output(self.project_dir, 1, "wave-results/wave-1/01-search.md")
        self.assertEqual(sot["outputs"]["step-1"], "wave-results/wave-1/01-search.md")

    def test_record_translation(self):
        sot = cm.record_translation(self.project_dir, 1, "wave-results/wave-1/01-search.ko.md")
        self.assertEqual(sot["outputs"]["step-1-ko"], "wave-results/wave-1/01-search.ko.md")

    def test_multiple_outputs(self):
        cm.record_output(self.project_dir, 1, "file1.md")
        cm.record_output(self.project_dir, 2, "file2.md")
        sot = cm.record_translation(self.project_dir, 1, "file1.ko.md")
        self.assertEqual(len(sot["outputs"]), 3)


class TestGateRecording(unittest.TestCase):
    """Test record_gate_result()."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        cm.init_project(self.project_dir, "Test")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_record_pass(self):
        sot = cm.record_gate_result(self.project_dir, "gate-1", "pass")
        self.assertEqual(sot["gates"]["gate-1"]["status"], "pass")
        self.assertIsNotNone(sot["gates"]["gate-1"]["timestamp"])

    def test_record_fail(self):
        sot = cm.record_gate_result(self.project_dir, "gate-2", "fail")
        self.assertEqual(sot["gates"]["gate-2"]["status"], "fail")

    def test_invalid_status(self):
        with self.assertRaises(ValueError):
            cm.record_gate_result(self.project_dir, "gate-1", "maybe")

    def test_unknown_gate(self):
        with self.assertRaises(ValueError):
            cm.record_gate_result(self.project_dir, "gate-99", "pass")

    def test_with_report_path(self):
        sot = cm.record_gate_result(
            self.project_dir, "gate-1", "pass",
            report_path="gate-reports/gate-1-report.json",
        )
        self.assertEqual(sot["gates"]["gate-1"]["report"], "gate-reports/gate-1-report.json")


class TestHITLRecording(unittest.TestCase):
    """Test record_hitl()."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        cm.init_project(self.project_dir, "Test")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_record_hitl_completed(self):
        sot = cm.record_hitl(self.project_dir, "hitl-1")
        self.assertEqual(sot["hitl_checkpoints"]["hitl-1"]["status"], "completed")

    def test_unknown_hitl(self):
        with self.assertRaises(ValueError):
            cm.record_hitl(self.project_dir, "hitl-99")


class TestCheckpointManagement(unittest.TestCase):
    """Test save_checkpoint() and restore_checkpoint()."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        cm.init_project(self.project_dir, "Test")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_save_creates_checkpoint_dir(self):
        cp_path = cm.save_checkpoint(self.project_dir, "hitl-2")
        self.assertTrue(Path(cp_path).is_dir())
        self.assertTrue((Path(cp_path) / cm.THESIS_SOT_FILENAME).exists())

    def test_save_records_in_sot(self):
        cm.save_checkpoint(self.project_dir, "hitl-2")
        sot = cm.read_thesis_sot(self.project_dir)
        snapshots = sot.get("context_snapshots", [])
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["name"], "hitl-2")

    def test_restore_recovers_state(self):
        # Advance, save, advance further, restore
        cm.advance_step(self.project_dir, 50)
        cm.save_checkpoint(self.project_dir, "mid-point")

        cm.advance_step(self.project_dir, 100)
        sot = cm.read_thesis_sot(self.project_dir)
        self.assertEqual(sot["current_step"], 100)

        restored = cm.restore_checkpoint(self.project_dir, "mid-point")
        self.assertEqual(restored["current_step"], 50)

    def test_restore_nonexistent(self):
        with self.assertRaises(FileNotFoundError):
            cm.restore_checkpoint(self.project_dir, "nonexistent")


class TestStatus(unittest.TestCase):
    """Test get_status()."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        cm.init_project(self.project_dir, "Test Thesis")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_initial_status(self):
        status = cm.get_status(self.project_dir)
        self.assertEqual(status["project_name"], "Test Thesis")
        self.assertEqual(status["current_step"], 0)
        self.assertEqual(status["progress_pct"], 0.0)
        self.assertEqual(status["gates_passed"], "0/5")

    def test_status_after_progress(self):
        cm.advance_step(self.project_dir, 21)
        cm.record_output(self.project_dir, 1, "output1.md")
        cm.record_translation(self.project_dir, 1, "output1.ko.md")

        status = cm.get_status(self.project_dir)
        self.assertEqual(status["current_step"], 21)
        self.assertEqual(status["outputs_en"], 1)
        self.assertEqual(status["outputs_ko"], 1)
        self.assertGreater(status["progress_pct"], 0)


class TestPhaseMapping(unittest.TestCase):
    """Test get_phase_for_step()."""

    def test_phase_0(self):
        self.assertEqual(cm.get_phase_for_step(1), "phase-0")
        self.assertEqual(cm.get_phase_for_step(8), "phase-0")

    def test_wave_1(self):
        self.assertEqual(cm.get_phase_for_step(39), "wave-1")
        self.assertEqual(cm.get_phase_for_step(54), "wave-1")

    def test_wave_5(self):
        self.assertEqual(cm.get_phase_for_step(95), "wave-5")

    def test_out_of_range(self):
        self.assertIsNone(cm.get_phase_for_step(999))

    def test_translation_range(self):
        self.assertEqual(cm.get_phase_for_step(181), "translation")


class TestConstants(unittest.TestCase):
    """Test constant integrity."""

    def test_agent_prefixes_unique(self):
        """Each agent must have a unique claim prefix."""
        prefixes = list(cm.AGENT_CLAIM_PREFIXES.values())
        self.assertEqual(len(prefixes), len(set(prefixes)))

    def test_srcs_weights_sum_to_1(self):
        """SRCS weights for each claim type must sum to 1.0."""
        for claim_type, weights in cm.SRCS_WEIGHTS.items():
            total = sum(weights.values())
            self.assertAlmostEqual(total, 1.0, places=2,
                                   msg=f"SRCS weights for {claim_type} sum to {total}")

    def test_phase_ranges_no_overlap(self):
        """Phase ranges must not overlap."""
        all_steps = set()
        for phase, (start, end) in cm.PHASE_RANGES.items():
            for s in range(start, end + 1):
                self.assertNotIn(s, all_steps,
                                 f"Step {s} in {phase} overlaps with another phase")
                all_steps.add(s)

    def test_phase_ranges_contiguous(self):
        """Phase ranges should cover steps 1 through 180."""
        all_steps = set()
        for _, (start, end) in cm.PHASE_RANGES.items():
            all_steps.update(range(start, end + 1))
        self.assertEqual(min(all_steps), 1)
        self.assertEqual(max(all_steps), 180)


class TestNoSystemSOTReference(unittest.TestCase):
    """Verify this script does NOT reference system SOT filenames.
    This is critical for R6 compliance — _check_sot_write_safety().
    """

    def test_no_state_yaml_reference(self):
        """Script must not contain 'state.yaml' string."""
        script_path = Path(__file__).parent / "checklist_manager.py"
        content = script_path.read_text()
        # Allow the comment explaining WHY we don't reference it
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            if "state.yaml" in line.lower() or "state.yml" in line.lower():
                # Only allow in comments explaining the design decision
                stripped = line.strip()
                if not stripped.startswith("#") and not stripped.startswith("//"):
                    self.fail(
                        f"Line {i} references system SOT filename: {line.strip()}"
                    )


if __name__ == "__main__":
    unittest.main()
