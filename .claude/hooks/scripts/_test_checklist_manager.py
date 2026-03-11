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
            "gate-reports", "phase-2", "thesis-drafts",
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
        """Wave 2 (step 59+) requires gate-1 to pass."""
        # Advance through wave-1, then through gate-1 range
        cm.advance_step(self.project_dir, 54)  # end of wave-1
        cm.advance_step(self.project_dir, 58)  # end of gate-1 (wave-1 dep met)
        # Check step 59 (wave-2 start) without gate-1 pass recorded
        unmet = cm.check_step_dependencies(
            cm.read_thesis_sot(self.project_dir), 59  # start of wave-2
        )
        self.assertTrue(len(unmet) > 0)
        self.assertTrue(any("gate-1" in u for u in unmet))

    def test_dependency_met_after_gate_pass(self):
        """After gate passes, dependency is met."""
        cm.advance_step(self.project_dir, 54)  # end of wave-1
        cm.advance_step(self.project_dir, 58)  # end of gate-1
        cm.record_gate_result(self.project_dir, "gate-1", "pass")
        unmet = cm.check_step_dependencies(
            cm.read_thesis_sot(self.project_dir), 59
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

        cm.advance_step(self.project_dir, 100, force=True)
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

    def test_gate_3(self):
        self.assertEqual(cm.get_phase_for_step(95), "gate-3")

    def test_wave_5(self):
        self.assertEqual(cm.get_phase_for_step(111), "wave-5")

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
        """Phase ranges should cover steps 1 through 211."""
        all_steps = set()
        for _, (start, end) in cm.PHASE_RANGES.items():
            all_steps.update(range(start, end + 1))
        self.assertEqual(min(all_steps), 1)
        self.assertEqual(max(all_steps), 211)


class TestCLIRecordGate(unittest.TestCase):
    """Test --record-gate CLI flag."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        cm.init_project(self.project_dir, "Test")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_cli_record_gate_pass(self):
        args = type("Args", (), {
            "project_dir": str(self.project_dir),
            "gate_name": "gate-1", "gate_status": "pass", "report_path": None,
        })()
        ret = cm._cli_record_gate(args)
        self.assertEqual(ret, 0)
        sot = cm.read_thesis_sot(self.project_dir)
        self.assertEqual(sot["gates"]["gate-1"]["status"], "pass")

    def test_cli_record_gate_with_report(self):
        args = type("Args", (), {
            "project_dir": str(self.project_dir),
            "gate_name": "gate-1", "gate_status": "pass",
            "report_path": "gate-reports/gate-1-report.json",
        })()
        ret = cm._cli_record_gate(args)
        self.assertEqual(ret, 0)
        sot = cm.read_thesis_sot(self.project_dir)
        self.assertEqual(sot["gates"]["gate-1"]["report"], "gate-reports/gate-1-report.json")

    def test_cli_record_gate_missing_name(self):
        args = type("Args", (), {
            "project_dir": str(self.project_dir),
            "gate_name": None, "gate_status": "pass", "report_path": None,
        })()
        ret = cm._cli_record_gate(args)
        self.assertEqual(ret, 1)

    def test_cli_record_gate_missing_status(self):
        args = type("Args", (), {
            "project_dir": str(self.project_dir),
            "gate_name": "gate-1", "gate_status": None, "report_path": None,
        })()
        ret = cm._cli_record_gate(args)
        self.assertEqual(ret, 1)


class TestCLIRecordOutput(unittest.TestCase):
    """Test --record-output CLI flag."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        cm.init_project(self.project_dir, "Test")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_cli_record_output(self):
        args = type("Args", (), {
            "project_dir": str(self.project_dir),
            "step": 5, "output_path": "wave-results/wave-1/05-output.md",
        })()
        ret = cm._cli_record_output(args)
        self.assertEqual(ret, 0)
        sot = cm.read_thesis_sot(self.project_dir)
        self.assertEqual(sot["outputs"]["step-5"], "wave-results/wave-1/05-output.md")

    def test_cli_record_output_missing_step(self):
        args = type("Args", (), {
            "project_dir": str(self.project_dir),
            "step": None, "output_path": "file.md",
        })()
        ret = cm._cli_record_output(args)
        self.assertEqual(ret, 1)

    def test_cli_record_output_missing_path(self):
        args = type("Args", (), {
            "project_dir": str(self.project_dir),
            "step": 1, "output_path": None,
        })()
        ret = cm._cli_record_output(args)
        self.assertEqual(ret, 1)


class TestCLIRecordTranslation(unittest.TestCase):
    """Test --record-translation CLI flag."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        cm.init_project(self.project_dir, "Test")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_cli_record_translation(self):
        args = type("Args", (), {
            "project_dir": str(self.project_dir),
            "step": 3, "ko_path": "wave-results/wave-1/03-output.ko.md",
        })()
        ret = cm._cli_record_translation(args)
        self.assertEqual(ret, 0)
        sot = cm.read_thesis_sot(self.project_dir)
        self.assertEqual(sot["outputs"]["step-3-ko"], "wave-results/wave-1/03-output.ko.md")

    def test_cli_record_translation_missing_step(self):
        args = type("Args", (), {
            "project_dir": str(self.project_dir),
            "step": None, "ko_path": "file.ko.md",
        })()
        ret = cm._cli_record_translation(args)
        self.assertEqual(ret, 1)

    def test_cli_record_translation_missing_path(self):
        args = type("Args", (), {
            "project_dir": str(self.project_dir),
            "step": 1, "ko_path": None,
        })()
        ret = cm._cli_record_translation(args)
        self.assertEqual(ret, 1)


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


class TestTranslationProgress(unittest.TestCase):
    """Test get_translation_progress() — translation coverage tracking."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "test-thesis"
        cm.init_project(self.project_dir, "Test")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_no_outputs_returns_zero(self):
        progress = cm.get_translation_progress(self.project_dir)
        self.assertEqual(progress["total_en"], 0)
        self.assertEqual(progress["translated"], 0)
        self.assertEqual(progress["coverage_pct"], 0.0)
        self.assertEqual(progress["missing_steps"], [])

    def test_en_only_shows_missing(self):
        cm.record_output(self.project_dir, 1, "/path/step-1.md")
        cm.record_output(self.project_dir, 2, "/path/step-2.md")
        progress = cm.get_translation_progress(self.project_dir)
        self.assertEqual(progress["total_en"], 2)
        self.assertEqual(progress["translated"], 0)
        self.assertEqual(progress["coverage_pct"], 0.0)
        self.assertEqual(progress["missing_steps"], [1, 2])

    def test_partial_coverage(self):
        cm.record_output(self.project_dir, 1, "/path/step-1.md")
        cm.record_output(self.project_dir, 2, "/path/step-2.md")
        cm.record_translation(self.project_dir, 1, "/path/step-1.ko.md")
        progress = cm.get_translation_progress(self.project_dir)
        self.assertEqual(progress["total_en"], 2)
        self.assertEqual(progress["translated"], 1)
        self.assertEqual(progress["coverage_pct"], 50.0)
        self.assertEqual(progress["missing_steps"], [2])

    def test_full_coverage(self):
        cm.record_output(self.project_dir, 1, "/path/step-1.md")
        cm.record_translation(self.project_dir, 1, "/path/step-1.ko.md")
        progress = cm.get_translation_progress(self.project_dir)
        self.assertEqual(progress["coverage_pct"], 100.0)
        self.assertEqual(progress["missing_steps"], [])


class TestDialogueCommands(unittest.TestCase):
    """Test adversarial dialogue SOT management (start/round/end)."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis-output" / "test-project"
        self.project_dir.mkdir(parents=True, exist_ok=True)
        cm.init_project(self.project_dir, "Test Project")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_start_dialogue_creates_sot_field(self):
        """start_dialogue writes dialogue_state to SOT."""
        cm.start_dialogue(self.project_dir, step=5, domain="research", max_rounds=3)
        sot = cm.read_thesis_sot(self.project_dir)
        ds = sot.get("dialogue_state")
        self.assertIsNotNone(ds, "dialogue_state must be present in SOT after start")
        self.assertEqual(ds["step"], 5)
        self.assertEqual(ds["domain"], "research")
        self.assertEqual(ds["max_rounds"], 3)
        self.assertEqual(ds["rounds_used"], 0)
        self.assertEqual(ds["status"], "in_progress")

    def test_start_dialogue_creates_directory(self):
        """start_dialogue creates dialogue-logs/ directory."""
        cm.start_dialogue(self.project_dir, step=5, domain="research", max_rounds=3)
        self.assertTrue((self.project_dir / "dialogue-logs").exists())

    def test_start_dialogue_invalid_domain_raises(self):
        """start_dialogue with invalid domain raises ValueError."""
        with self.assertRaises(ValueError):
            cm.start_dialogue(self.project_dir, step=5, domain="invalid", max_rounds=3)

    def test_advance_dialogue_round_increments_counter(self):
        """advance_dialogue_round increments rounds_used in SOT."""
        cm.start_dialogue(self.project_dir, step=5, domain="research", max_rounds=3)
        cm.advance_dialogue_round(self.project_dir, step=5, round_num=1, verdict="FAIL")
        sot = cm.read_thesis_sot(self.project_dir)
        ds = sot["dialogue_state"]
        self.assertEqual(ds["rounds_used"], 1)
        # verdict is stored in round_history, not a top-level last_verdict field
        history = ds.get("round_history", [])
        self.assertTrue(len(history) > 0, "round_history must have an entry")
        self.assertEqual(history[-1]["verdict"], "FAIL")

    def test_advance_dialogue_round_multiple_rounds(self):
        """Multiple advance_dialogue_round calls accumulate correctly."""
        cm.start_dialogue(self.project_dir, step=5, domain="research", max_rounds=3)
        cm.advance_dialogue_round(self.project_dir, step=5, round_num=1, verdict="FAIL")
        cm.advance_dialogue_round(self.project_dir, step=5, round_num=2, verdict="FAIL")
        sot = cm.read_thesis_sot(self.project_dir)
        self.assertEqual(sot["dialogue_state"]["rounds_used"], 2)

    def test_end_dialogue_consensus_updates_outcome(self):
        """end_dialogue with consensus sets outcome and status."""
        cm.start_dialogue(self.project_dir, step=5, domain="research", max_rounds=3)
        cm.advance_dialogue_round(self.project_dir, step=5, round_num=1, verdict="PASS")
        cm.end_dialogue(self.project_dir, step=5, outcome="consensus")
        sot = cm.read_thesis_sot(self.project_dir)
        ds = sot["dialogue_state"]
        self.assertEqual(ds["outcome"], "consensus")
        # end_dialogue sets status = outcome ("consensus" or "escalated")
        self.assertEqual(ds["status"], "consensus")

    def test_end_dialogue_escalated_updates_outcome(self):
        """end_dialogue with escalated sets correct outcome."""
        cm.start_dialogue(self.project_dir, step=5, domain="research", max_rounds=3)
        cm.end_dialogue(self.project_dir, step=5, outcome="escalated")
        sot = cm.read_thesis_sot(self.project_dir)
        ds = sot["dialogue_state"]
        self.assertEqual(ds["outcome"], "escalated")

    def test_end_dialogue_invalid_outcome_raises(self):
        """end_dialogue with invalid outcome raises ValueError."""
        cm.start_dialogue(self.project_dir, step=5, domain="research", max_rounds=3)
        with self.assertRaises(ValueError):
            cm.end_dialogue(self.project_dir, step=5, outcome="unknown-outcome")

    def test_development_domain_accepted(self):
        """Development domain is valid for start_dialogue."""
        cm.start_dialogue(self.project_dir, step=3, domain="development", max_rounds=2)
        sot = cm.read_thesis_sot(self.project_dir)
        self.assertEqual(sot["dialogue_state"]["domain"], "development")

    def test_init_project_creates_dialogue_logs_dir(self):
        """init_project must create dialogue-logs/ directory."""
        new_project = self.tmpdir / "new-project"
        cm.init_project(new_project, "New Project")
        self.assertTrue((new_project / "dialogue-logs").exists(),
                        "dialogue-logs/ must be created by init_project")


class TestAdvanceGroup(unittest.TestCase):
    """Test advance_group() — atomic consolidated step advancement."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        cm.init_project(self.project_dir, "Test")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_normal_group_advance(self):
        """advance_group(first=1, last=3) with current=0 should set current=3."""
        sot = cm.advance_group(
            self.project_dir, first_step=1, last_step=3,
            output_path="wave-results/step-001-to-003-test.md",
        )
        self.assertEqual(sot["current_step"], 3)

    def test_output_recorded_for_all_steps(self):
        """Each step in the group should have the shared output path recorded."""
        cm.advance_group(
            self.project_dir, first_step=1, last_step=3,
            output_path="output.md",
        )
        sot = cm.read_thesis_sot(self.project_dir)
        for step in (1, 2, 3):
            self.assertEqual(sot["outputs"][f"step-{step}"], "output.md")

    def test_checklist_synced(self):
        """Steps 1-3 should be [x] and step 4 should be [ ] after group advance."""
        cm.advance_group(
            self.project_dir, first_step=1, last_step=3,
            output_path="output.md",
        )
        cl = (self.project_dir / cm.THESIS_CHECKLIST_FILENAME).read_text()
        self.assertIn("- [x] Step 1:", cl)
        self.assertIn("- [x] Step 3:", cl)
        self.assertIn("- [ ] Step 4:", cl)

    def test_precondition_current_must_be_first_minus_one(self):
        """advance_group requires current_step == first_step - 1."""
        cm.advance_step(self.project_dir, 5)  # current = 5
        with self.assertRaises(ValueError) as ctx:
            cm.advance_group(
                self.project_dir, first_step=3, last_step=5,
                output_path="output.md",
            )
        self.assertIn("expected 2", str(ctx.exception))

    def test_precondition_matches_advance_step(self):
        """After advance_step(5), advance_group(6, 8) should work."""
        cm.advance_step(self.project_dir, 5)  # current = 5
        sot = cm.advance_group(
            self.project_dir, first_step=6, last_step=8,
            output_path="output.md",
        )
        self.assertEqual(sot["current_step"], 8)

    def test_first_greater_than_last_raises(self):
        """first_step > last_step should raise ValueError."""
        with self.assertRaises(ValueError):
            cm.advance_group(
                self.project_dir, first_step=5, last_step=3,
                output_path="output.md",
            )

    def test_group_exceeds_safety_cap(self):
        """Group size > 6 should raise ValueError (aligned with _MAX_CONSOLIDATION_SIZE)."""
        with self.assertRaises(ValueError):
            cm.advance_group(
                self.project_dir, first_step=1, last_step=12,
                output_path="output.md",
            )

    def test_last_step_exceeds_total(self):
        """last_step > total_steps should raise ValueError."""
        with self.assertRaises(ValueError):
            cm.advance_group(
                self.project_dir, first_step=1, last_step=999,
                output_path="output.md",
            )

    def test_substep_cleared(self):
        """execution_substep should be None after advance_group."""
        sot = cm.read_thesis_sot(self.project_dir)
        sot["execution_substep"] = "L1_verification"
        cm.write_thesis_sot(self.project_dir, sot)
        sot = cm.advance_group(
            self.project_dir, first_step=1, last_step=3,
            output_path="output.md",
        )
        self.assertIsNone(sot["execution_substep"])

    def test_sequential_group_then_step(self):
        """advance_group(1,3) then advance_step(4) should work."""
        cm.advance_group(
            self.project_dir, first_step=1, last_step=3,
            output_path="output.md",
        )
        sot = cm.advance_step(self.project_dir, 4)
        self.assertEqual(sot["current_step"], 4)

    def test_sequential_groups(self):
        """Two consecutive groups should work."""
        cm.advance_group(
            self.project_dir, first_step=1, last_step=3,
            output_path="out1.md",
        )
        sot = cm.advance_group(
            self.project_dir, first_step=4, last_step=6,
            output_path="out2.md",
        )
        self.assertEqual(sot["current_step"], 6)


class TestAdvanceGroupCLI(unittest.TestCase):
    """Test --advance-group CLI handler."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        cm.init_project(self.project_dir, "Test")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_cli_advance_group_success(self):
        """CLI --advance-group with valid args should return 0."""
        import subprocess
        script = str(Path(__file__).parent / "checklist_manager.py")
        result = subprocess.run(
            [sys.executable, script,
             "--advance-group",
             "--project-dir", str(self.project_dir),
             "--first-step", "1",
             "--last-step", "3",
             "--output-path", "output.md"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Advanced group [1-3]", result.stdout)

    def test_cli_advance_group_missing_args(self):
        """CLI --advance-group without required args should return 1."""
        import subprocess
        script = str(Path(__file__).parent / "checklist_manager.py")
        result = subprocess.run(
            [sys.executable, script,
             "--advance-group",
             "--project-dir", str(self.project_dir)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires", result.stderr)

    def test_cli_advance_group_bad_precondition(self):
        """CLI --advance-group with wrong current_step should return 1."""
        import subprocess
        script = str(Path(__file__).parent / "checklist_manager.py")
        # First advance to step 5
        subprocess.run(
            [sys.executable, script,
             "--advance", "--project-dir", str(self.project_dir),
             "--step", "5"],
            capture_output=True, text=True, timeout=10,
        )
        # Try group starting at 3 (expects current=2 but current=5)
        result = subprocess.run(
            [sys.executable, script,
             "--advance-group",
             "--project-dir", str(self.project_dir),
             "--first-step", "3",
             "--last-step", "5",
             "--output-path", "output.md"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
