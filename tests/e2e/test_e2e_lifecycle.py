"""Track 1: Full Workflow Lifecycle E2E Tests.

Tests the complete init → advance → gate → HITL → checkpoint → restore cycle.
"""

import json
from pathlib import Path

import pytest

from conftest import run_cm, read_sot, write_sot


class TestInit:
    """E2E: Project initialization."""

    def test_init_creates_sot(self, tmp_path):
        proj = tmp_path / "thesis-output" / "fresh"
        run_cm("--init", "--project-dir", str(proj))
        sot = read_sot(proj)
        assert sot["status"] == "running"
        assert sot["current_step"] == 0
        assert sot["total_steps"] == 211

    def test_init_creates_checklist(self, tmp_path):
        proj = tmp_path / "thesis-output" / "fresh"
        run_cm("--init", "--project-dir", str(proj))
        cl = proj / "todo-checklist.md"
        assert cl.exists()
        content = cl.read_text()
        assert "Step 1:" in content

    def test_init_creates_insights(self, tmp_path):
        proj = tmp_path / "thesis-output" / "fresh"
        run_cm("--init", "--project-dir", str(proj))
        ins = proj / "research-synthesis.md"
        assert ins.exists()

    def test_init_creates_subdirs(self, tmp_path):
        proj = tmp_path / "thesis-output" / "fresh"
        run_cm("--init", "--project-dir", str(proj))
        assert (proj / "wave-results").is_dir()
        assert (proj / "checkpoints").is_dir()

    def test_init_with_research_type(self, tmp_path):
        proj = tmp_path / "thesis-output" / "qual"
        run_cm("--init", "--project-dir", str(proj), "--research-type", "qualitative")
        sot = read_sot(proj)
        assert sot["research_type"] == "qualitative"

    def test_init_with_input_mode(self, tmp_path):
        proj = tmp_path / "thesis-output" / "modeB"
        run_cm("--init", "--project-dir", str(proj), "--input-mode", "B")
        sot = read_sot(proj)
        assert sot["input_mode"] == "B"

    def test_init_default_gates(self, thesis_project):
        proj, sot = thesis_project
        assert len(sot["gates"]) == 5
        for g in sot["gates"].values():
            assert g["status"] == "pending"

    def test_init_default_hitls(self, thesis_project):
        proj, sot = thesis_project
        assert len(sot["hitl_checkpoints"]) == 9
        for h in sot["hitl_checkpoints"].values():
            assert h["status"] == "pending"


class TestAdvance:
    """E2E: Step advancement."""

    def test_advance_forward(self, thesis_project):
        proj, _ = thesis_project
        run_cm("--advance", "--step", "1", "--project-dir", str(proj))
        sot = read_sot(proj)
        assert sot["current_step"] == 1

    def test_advance_multiple_steps(self, thesis_project):
        proj, _ = thesis_project
        run_cm("--advance", "--step", "1", "--project-dir", str(proj))
        run_cm("--advance", "--step", "5", "--project-dir", str(proj))
        sot = read_sot(proj)
        assert sot["current_step"] == 5

    def test_advance_backward_fails(self, thesis_project):
        proj, _ = thesis_project
        run_cm("--advance", "--step", "5", "--project-dir", str(proj))
        result = run_cm("--advance", "--step", "3", "--project-dir", str(proj), expect_ok=False)
        assert result.returncode != 0

    def test_advance_backward_with_force(self, thesis_project):
        proj, _ = thesis_project
        run_cm("--advance", "--step", "5", "--project-dir", str(proj))
        run_cm("--advance", "--step", "3", "--project-dir", str(proj), "--force")
        sot = read_sot(proj)
        assert sot["current_step"] == 3

    def test_advance_out_of_range(self, thesis_project):
        proj, _ = thesis_project
        result = run_cm("--advance", "--step", "999", "--project-dir", str(proj), expect_ok=False)
        assert result.returncode != 0

    def test_advance_updates_checklist(self, thesis_project):
        proj, _ = thesis_project
        run_cm("--advance", "--step", "3", "--project-dir", str(proj))
        cl = (proj / "todo-checklist.md").read_text()
        # Steps 1-3 should be checked
        assert "[x]" in cl


class TestGates:
    """E2E: Gate pass/fail recording."""

    def test_record_gate_pass(self, thesis_project):
        proj, _ = thesis_project
        import checklist_manager as cm
        cm.record_gate_result(proj, "gate-1", "pass")
        sot = read_sot(proj)
        assert sot["gates"]["gate-1"]["status"] == "pass"
        assert sot["gates"]["gate-1"]["timestamp"] is not None

    def test_record_gate_fail(self, thesis_project):
        proj, _ = thesis_project
        import checklist_manager as cm
        cm.record_gate_result(proj, "gate-2", "fail")
        sot = read_sot(proj)
        assert sot["gates"]["gate-2"]["status"] == "fail"

    def test_gate_with_report(self, thesis_project):
        proj, _ = thesis_project
        import checklist_manager as cm
        cm.record_gate_result(proj, "gate-1", "pass", report_path="gate-1-report.md")
        sot = read_sot(proj)
        assert sot["gates"]["gate-1"]["report"] == "gate-1-report.md"

    def test_unknown_gate_raises(self, thesis_project):
        proj, _ = thesis_project
        import checklist_manager as cm
        with pytest.raises(ValueError, match="Unknown gate"):
            cm.record_gate_result(proj, "gate-999", "pass")

    def test_invalid_gate_status_raises(self, thesis_project):
        proj, _ = thesis_project
        import checklist_manager as cm
        with pytest.raises(ValueError, match="must be 'pass' or 'fail'"):
            cm.record_gate_result(proj, "gate-1", "maybe")


class TestHITL:
    """E2E: HITL checkpoint recording."""

    def test_record_hitl_completed(self, thesis_project):
        proj, _ = thesis_project
        run_cm("--record-hitl", "hitl-1", "--project-dir", str(proj))
        sot = read_sot(proj)
        assert sot["hitl_checkpoints"]["hitl-1"]["status"] == "completed"
        assert sot["hitl_checkpoints"]["hitl-1"]["timestamp"] is not None

    def test_record_hitl_custom_status(self, thesis_project):
        proj, _ = thesis_project
        run_cm("--record-hitl", "hitl-2", "--hitl-status", "blocked", "--project-dir", str(proj))
        sot = read_sot(proj)
        assert sot["hitl_checkpoints"]["hitl-2"]["status"] == "blocked"

    def test_record_unknown_hitl_fails(self, thesis_project):
        proj, _ = thesis_project
        result = run_cm("--record-hitl", "hitl-99", "--project-dir", str(proj), expect_ok=False)
        assert result.returncode != 0

    def test_record_all_hitls(self, thesis_project):
        proj, _ = thesis_project
        for i in range(9):
            run_cm("--record-hitl", f"hitl-{i}", "--project-dir", str(proj))
        sot = read_sot(proj)
        for i in range(9):
            assert sot["hitl_checkpoints"][f"hitl-{i}"]["status"] == "completed"


class TestCheckpoints:
    """E2E: Checkpoint save and restore."""

    def test_save_creates_dir(self, thesis_project):
        proj, _ = thesis_project
        run_cm("--save-checkpoint", "--checkpoint", "cp-1", "--project-dir", str(proj))
        assert (proj / "checkpoints" / "cp-1").is_dir()

    def test_save_copies_sot(self, thesis_project):
        proj, _ = thesis_project
        run_cm("--save-checkpoint", "--checkpoint", "cp-1", "--project-dir", str(proj))
        cp_sot = proj / "checkpoints" / "cp-1" / "session.json"
        assert cp_sot.exists()
        data = json.loads(cp_sot.read_text())
        assert data["current_step"] == 0

    def test_save_copies_checklist(self, thesis_project):
        proj, _ = thesis_project
        run_cm("--save-checkpoint", "--checkpoint", "cp-1", "--project-dir", str(proj))
        assert (proj / "checkpoints" / "cp-1" / "todo-checklist.md").exists()

    def test_save_records_in_sot(self, thesis_project):
        proj, _ = thesis_project
        run_cm("--save-checkpoint", "--checkpoint", "cp-1", "--project-dir", str(proj))
        sot = read_sot(proj)
        assert len(sot["context_snapshots"]) == 1
        assert sot["context_snapshots"][0]["name"] == "cp-1"

    def test_restore_recovers_state(self, thesis_project):
        proj, _ = thesis_project
        # Save at step 0
        run_cm("--save-checkpoint", "--checkpoint", "cp-origin", "--project-dir", str(proj))
        # Advance to step 10
        run_cm("--advance", "--step", "10", "--project-dir", str(proj))
        assert read_sot(proj)["current_step"] == 10
        # Restore
        run_cm("--restore-checkpoint", "--checkpoint", "cp-origin", "--project-dir", str(proj))
        sot = read_sot(proj)
        assert sot["current_step"] == 0

    def test_restore_nonexistent_fails(self, thesis_project):
        proj, _ = thesis_project
        result = run_cm(
            "--restore-checkpoint", "--checkpoint", "no-such-cp",
            "--project-dir", str(proj), expect_ok=False,
        )
        assert result.returncode != 0


class TestFullLifecycle:
    """E2E: Complete lifecycle from init through checkpoint restore."""

    def test_init_advance_gate_hitl_checkpoint_restore(self, tmp_path):
        import checklist_manager as cm

        proj = tmp_path / "thesis-output" / "lifecycle"
        # 1. Init
        run_cm("--init", "--project-dir", str(proj), "--research-type", "mixed")
        sot = read_sot(proj)
        assert sot["status"] == "running"
        assert sot["research_type"] == "mixed"

        # 2. Advance through phase-0
        for step in [1, 3, 8]:
            run_cm("--advance", "--step", str(step), "--project-dir", str(proj))
        assert read_sot(proj)["current_step"] == 8

        # 3. Record outputs
        cm.record_output(proj, 1, "wave-results/step-1.md")
        cm.record_output(proj, 3, "wave-results/step-3.md")
        cm.record_translation(proj, 1, "wave-results/step-1.ko.md")
        sot = read_sot(proj)
        assert "step-1" in sot["outputs"]
        assert "step-1-ko" in sot["outputs"]
        assert "step-3" in sot["outputs"]

        # 4. Record HITL-0
        run_cm("--record-hitl", "hitl-0", "--project-dir", str(proj))

        # 5. Save checkpoint
        run_cm("--save-checkpoint", "--checkpoint", "post-hitl-0", "--project-dir", str(proj))

        # 6. Advance further, pass gate-1
        cm.advance_step(proj, 54, force=True)
        cm.record_gate_result(proj, "gate-1", "pass")
        assert read_sot(proj)["gates"]["gate-1"]["status"] == "pass"

        # 7. Restore to post-hitl-0
        run_cm("--restore-checkpoint", "--checkpoint", "post-hitl-0", "--project-dir", str(proj))
        sot = read_sot(proj)
        assert sot["current_step"] == 8
        assert sot["gates"]["gate-1"]["status"] == "pending"  # restored to pre-gate state

        # 8. Status check
        status = cm.get_status(proj)
        assert status["current_step"] == 8
        assert status["gates_passed"] == "0/5"
        assert status["hitls_completed"] == "1/9"
        assert status["outputs_en"] == 2
        assert status["outputs_ko"] == 1
