"""Track 5: Error Recovery E2E Tests.

Tests corrupted SOT handling, missing files, invalid steps,
dependency enforcement, and checkpoint-based recovery.
"""

import json
import os
from pathlib import Path

import pytest

from conftest import run_cm, read_sot, write_sot


class TestCorruptedSOT:
    """E2E: System behavior when SOT is corrupted."""

    def test_invalid_json(self, thesis_project):
        proj, _ = thesis_project
        sot_path = proj / "session.json"
        sot_path.write_text("{invalid json!!!", encoding="utf-8")
        result = run_cm("--status", "--project-dir", str(proj), expect_ok=False)
        assert result.returncode != 0

    def test_missing_sot(self, tmp_path):
        proj = tmp_path / "thesis-output" / "broken"
        proj.mkdir(parents=True)
        result = run_cm("--status", "--project-dir", str(proj), expect_ok=False)
        assert result.returncode != 0

    def test_invalid_status_field(self, thesis_project):
        proj, _ = thesis_project
        sot = read_sot(proj)
        sot["status"] = "BOGUS"
        write_sot(proj, sot)
        result = run_cm("--validate", "--project-dir", str(proj), expect_ok=False)
        assert result.returncode != 0

    def test_negative_current_step(self, thesis_project):
        proj, _ = thesis_project
        sot = read_sot(proj)
        sot["current_step"] = -5
        write_sot(proj, sot)
        import checklist_manager as cm
        errors = cm.validate_thesis_sot(sot)
        assert any("TS4" in e for e in errors)

    def test_current_exceeds_total(self, thesis_project):
        proj, _ = thesis_project
        sot = read_sot(proj)
        sot["current_step"] = 999
        write_sot(proj, sot)
        import checklist_manager as cm
        errors = cm.validate_thesis_sot(sot)
        assert any("TS5" in e for e in errors)

    def test_missing_required_keys(self, thesis_project):
        proj, _ = thesis_project
        sot = read_sot(proj)
        del sot["outputs"]
        del sot["gates"]
        write_sot(proj, sot)
        import checklist_manager as cm
        errors = cm.validate_thesis_sot(sot)
        assert any("TS2" in e for e in errors)


class TestMissingFiles:
    """E2E: Recovery when auxiliary files are missing."""

    def test_missing_checklist_advance_still_works(self, thesis_project):
        """Advance should update SOT even if checklist.md is missing."""
        proj, _ = thesis_project
        cl_path = proj / "todo-checklist.md"
        if cl_path.exists():
            cl_path.unlink()
        run_cm("--advance", "--step", "1", "--project-dir", str(proj))
        assert read_sot(proj)["current_step"] == 1

    def test_missing_insights_init_creates_it(self, tmp_path):
        proj = tmp_path / "thesis-output" / "fresh"
        run_cm("--init", "--project-dir", str(proj))
        assert (proj / "research-synthesis.md").exists()

    def test_checkpoint_missing_checklist(self, thesis_project):
        """Checkpoint should work even if checklist is missing."""
        proj, _ = thesis_project
        (proj / "todo-checklist.md").unlink()
        # Should not crash — just skip copying checklist
        run_cm("--save-checkpoint", "--checkpoint", "no-cl", "--project-dir", str(proj))
        assert (proj / "checkpoints" / "no-cl" / "session.json").exists()


class TestDependencyEnforcement:
    """E2E: Wave/gate dependencies block unauthorized advancement."""

    def test_wave2_blocked_without_gate1(self, thesis_project):
        import checklist_manager as cm
        proj, _ = thesis_project
        # Jump to end of gate-1 (step 58) with force
        cm.advance_step(proj, 58, force=True)
        # Try to enter wave-2 (step 59) WITHOUT gate-1 pass
        with pytest.raises(ValueError, match="(?i)gate.*gate-1"):
            cm.advance_step(proj, 59)

    def test_wave2_allowed_with_gate1(self, gated_project):
        import checklist_manager as cm
        proj, _ = gated_project
        # gate-1 already passed — wave-2 (step 59) should be accessible
        cm.advance_step(proj, 59)
        assert read_sot(proj)["current_step"] == 59

    def test_wave3_blocked_without_gate2(self, gated_project):
        import checklist_manager as cm
        proj, _ = gated_project
        # Jump to end of wave-2 (step 74) + gate-2 (step 78) with force
        cm.advance_step(proj, 78, force=True)
        # Try to enter wave-3 (step 79) WITHOUT gate-2 pass
        with pytest.raises(ValueError, match="(?i)gate.*gate-2"):
            cm.advance_step(proj, 79)

    def test_phase2_blocked_without_hitl2(self, thesis_project):
        import checklist_manager as cm
        proj, _ = thesis_project
        # Jump to end of hitl-2 range (step 120) with force
        cm.advance_step(proj, 120, force=True)
        # Try to enter phase-2 (step 121) WITHOUT hitl-2
        with pytest.raises(ValueError, match="(?i)hitl.*hitl-2"):
            cm.advance_step(proj, 121)

    def test_phase2_allowed_with_hitl2(self, thesis_project):
        import checklist_manager as cm
        proj, _ = thesis_project
        # Force to step 120, record HITL-2
        cm.advance_step(proj, 120, force=True)
        cm.record_hitl(proj, "hitl-2")
        # Should now work
        cm.advance_step(proj, 121)
        assert read_sot(proj)["current_step"] == 121

    def test_force_bypasses_all_deps(self, thesis_project):
        import checklist_manager as cm
        proj, _ = thesis_project
        # Force should bypass gate and HITL deps
        cm.advance_step(proj, 105, force=True)
        assert read_sot(proj)["current_step"] == 105


class TestCheckpointRecovery:
    """E2E: Checkpoint-based recovery from various failure states."""

    def test_restore_after_gate_fail(self, thesis_project):
        import checklist_manager as cm
        proj, _ = thesis_project
        # Advance and save checkpoint
        cm.advance_step(proj, 54, force=True)
        run_cm("--save-checkpoint", "--checkpoint", "pre-gate", "--project-dir", str(proj))
        # Record gate failure
        cm.record_gate_result(proj, "gate-1", "fail")
        assert read_sot(proj)["gates"]["gate-1"]["status"] == "fail"
        # Restore
        run_cm("--restore-checkpoint", "--checkpoint", "pre-gate", "--project-dir", str(proj))
        sot = read_sot(proj)
        assert sot["gates"]["gate-1"]["status"] == "pending"

    def test_restore_preserves_earlier_data(self, thesis_project):
        import checklist_manager as cm
        proj, _ = thesis_project
        # Record some outputs
        cm.record_output(proj, 1, "wave-results/step-1.md")
        run_cm("--save-checkpoint", "--checkpoint", "with-output", "--project-dir", str(proj))
        # Modify further
        cm.advance_step(proj, 10, force=True)
        cm.record_output(proj, 10, "wave-results/step-10.md")
        # Restore
        run_cm("--restore-checkpoint", "--checkpoint", "with-output", "--project-dir", str(proj))
        sot = read_sot(proj)
        assert "step-1" in sot["outputs"]
        assert "step-10" not in sot["outputs"]

    def test_multiple_checkpoints_coexist(self, thesis_project):
        proj, _ = thesis_project
        for i in range(3):
            run_cm("--save-checkpoint", "--checkpoint", f"cp-{i}", "--project-dir", str(proj))
        for i in range(3):
            assert (proj / "checkpoints" / f"cp-{i}" / "session.json").exists()
