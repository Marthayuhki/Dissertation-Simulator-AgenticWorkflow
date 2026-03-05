#!/usr/bin/env python3
"""Tests for validate_thesis_output.py — Thesis output structural validation (TO1-TO3).

Run: python3 -m pytest _test_validate_thesis_output.py -v
  or: python3 _test_validate_thesis_output.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import validate_thesis_output as vto


class TestThesisOutputValidation(unittest.TestCase):
    """Test thesis output structural validation rules TO1-TO3."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.wave_dir = self.tmpdir / "wave-results" / "wave-1"
        self.wave_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write_output(self, step, content):
        path = self.wave_dir / f"step-{step}.md"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_valid_output(self):
        content = (
            "# Literature Search Results\n\n"
            "## Findings\n\n"
            "```yaml\n"
            "- claim_id: LS-001\n"
            "  type: EMPIRICAL\n"
            "  statement: AI improves research efficiency\n"
            "  source: Smith et al. 2024\n"
            "```\n"
        )
        path = self._write_output(39, content)
        result = vto.validate_output(path, project_dir=str(self.tmpdir))
        self.assertTrue(result.get("valid", False) or result.get("to1", False),
                        f"Valid output should pass: {result}")

    def test_missing_file(self):
        result = vto.validate_output(
            str(self.wave_dir / "nonexistent.md"),
            project_dir=str(self.tmpdir))
        self.assertFalse(result.get("valid", True))

    def test_empty_file(self):
        self._write_output(39, "")
        result = vto.validate_output(
            str(self.wave_dir / "step-39.md"),
            project_dir=str(self.tmpdir))
        self.assertFalse(result.get("valid", True))


class TestNoSystemSOTReference(unittest.TestCase):
    def test_no_state_yaml_reference(self):
        src = Path(__file__).parent / "validate_thesis_output.py"
        content = src.read_text(encoding="utf-8")
        self.assertNotIn("state.yaml", content,
                         "validate_thesis_output.py must not reference system SOT")


if __name__ == "__main__":
    unittest.main()
