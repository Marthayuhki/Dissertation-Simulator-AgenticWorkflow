#!/usr/bin/env python3
"""Tests for validate_traceability.py — Cross-Step Traceability validation (CT1-CT5).

Run: python3 -m pytest _test_validate_traceability.py -v
  or: python3 _test_validate_traceability.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import validate_traceability as vt


class TestTraceabilityValidation(unittest.TestCase):
    """Test Cross-Step Traceability validation rules CT1-CT5."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write_output(self, filename, content):
        path = self.tmpdir / filename
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_valid_traceability_markers(self):
        content = (
            "# Analysis Output\n\n"
            "Based on previous findings [trace:step-1:methodology], "
            "we extend the framework [trace:step-2:framework]. "
            "The data supports [trace:step-3:results].\n"
        )
        path = self._write_output("step-5.md", content)
        result = vt.validate_traceability(path, step=5, project_dir=str(self.tmpdir))
        self.assertTrue(result.get("valid", False) or result.get("ct1", False),
                        f"Valid traceability should pass: {result}")

    def test_missing_file(self):
        result = vt.validate_traceability(
            str(self.tmpdir / "nonexistent.md"), step=5,
            project_dir=str(self.tmpdir))
        self.assertFalse(result.get("valid", True))

    def test_no_markers(self):
        content = "# Analysis Output\n\nNo cross-references here.\n"
        path = self._write_output("step-5.md", content)
        result = vt.validate_traceability(path, step=5, project_dir=str(self.tmpdir))
        # Should fail CT1 — minimum 3 markers required
        self.assertFalse(result.get("valid", True) and result.get("ct1", True))


class TestNoSystemSOTReference(unittest.TestCase):
    def test_no_state_yaml_reference(self):
        src = Path(__file__).parent / "validate_traceability.py"
        content = src.read_text(encoding="utf-8")
        self.assertNotIn("state.yaml", content,
                         "validate_traceability.py must not reference system SOT")


if __name__ == "__main__":
    unittest.main()
