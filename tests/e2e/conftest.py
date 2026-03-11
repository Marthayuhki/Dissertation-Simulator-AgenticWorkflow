"""Shared fixtures for E2E tests."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / ".claude" / "hooks" / "scripts"
CM_SCRIPT = SCRIPTS_DIR / "checklist_manager.py"
QW_SCRIPT = SCRIPTS_DIR / "query_workflow.py"
VGC_SCRIPT = SCRIPTS_DIR / "validate_grounded_claim.py"

# Ensure scripts dir is on the path for direct imports
sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def run_cm(*args: str, expect_ok: bool = True) -> subprocess.CompletedProcess:
    """Run checklist_manager.py with given arguments."""
    cmd = [sys.executable, str(CM_SCRIPT)] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if expect_ok:
        assert result.returncode == 0, (
            f"checklist_manager.py failed (rc={result.returncode}):\n"
            f"  args: {args}\n"
            f"  stdout: {result.stdout}\n"
            f"  stderr: {result.stderr}"
        )
    return result


def run_qw(*args: str, expect_ok: bool = True) -> subprocess.CompletedProcess:
    """Run query_workflow.py with given arguments."""
    cmd = [sys.executable, str(QW_SCRIPT)] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if expect_ok:
        assert result.returncode == 0, (
            f"query_workflow.py failed (rc={result.returncode}):\n"
            f"  args: {args}\n"
            f"  stdout: {result.stdout}\n"
            f"  stderr: {result.stderr}"
        )
    return result


def read_sot(project_dir: Path) -> dict:
    """Read session.json directly."""
    sot_path = project_dir / "session.json"
    with open(sot_path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_sot(project_dir: Path, data: dict) -> None:
    """Write session.json directly (for test setup)."""
    sot_path = project_dir / "session.json"
    with open(sot_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def thesis_project(tmp_path):
    """Create and initialize a fresh thesis project in tmp_path.

    Returns (project_dir, sot) tuple.
    """
    proj = tmp_path / "thesis-output" / "test-project"
    run_cm(
        "--init",
        "--project-dir", str(proj),
        "--research-type", "quantitative",
    )
    sot = read_sot(proj)
    return proj, sot


@pytest.fixture
def advanced_project(thesis_project):
    """A project advanced to step 10 (within phase-0-A)."""
    proj, _ = thesis_project
    run_cm("--advance", "--step", "10", "--project-dir", str(proj))
    sot = read_sot(proj)
    return proj, sot


@pytest.fixture
def gated_project(thesis_project):
    """A project with gate-1 passed and advanced to gate-1 boundary (step 58)."""
    proj, _ = thesis_project
    import checklist_manager as cm
    # Advance through wave-1 and gate-1 steps
    cm.advance_step(proj, 58, force=True)
    # Pass gate-1
    cm.record_gate_result(proj, "gate-1", "pass")
    sot = read_sot(proj)
    return proj, sot
