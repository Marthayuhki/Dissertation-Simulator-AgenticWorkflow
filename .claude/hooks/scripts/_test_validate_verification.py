#!/usr/bin/env python3
"""Tests for validate_verification.py — Verification Gate validation (V1a-V1c).

Run: python3 -m pytest _test_validate_verification.py -v
  or: python3 _test_validate_verification.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import validate_verification as vv


class TestVerificationValidation(unittest.TestCase):
    """Test Verification Gate validation rules V1a-V1c."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.verify_dir = self.tmpdir / "verification-logs"
        self.verify_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write_verify_log(self, step, content):
        path = self.verify_dir / f"step-{step}-verify.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _make_valid_verification(self, step=1):
        return (
            f"# Verification Log — Step {step}\n\n"
            f"## Criteria Check\n\n"
            f"| Criterion | Result | Evidence |\n"
            f"|-----------|--------|----------|\n"
            f"| Output exists | PASS | File size: 2048 bytes |\n"
            f"| Min quality | PASS | Contains 5 GroundedClaims |\n"
            f"| Format valid | PASS | YAML schema validated |\n\n"
            f"## Verdict: PASS\n"
        )

    def test_valid_verification_log(self):
        self._write_verify_log(1, self._make_valid_verification())
        result = vv.validate_verification_log(
            str(self.verify_dir / "step-1-verify.md"))
        self.assertTrue(result.get("valid", False) or result.get("v1a", False),
                        f"Valid verification log should pass: {result}")

    def test_missing_file(self):
        result = vv.validate_verification_log(
            str(self.verify_dir / "nonexistent.md"))
        self.assertFalse(result.get("valid", True))

    def test_empty_file(self):
        self._write_verify_log(1, "")
        result = vv.validate_verification_log(
            str(self.verify_dir / "step-1-verify.md"))
        self.assertFalse(result.get("valid", True))


class TestNoSystemSOTReference(unittest.TestCase):
    def test_no_state_yaml_reference(self):
        src = Path(__file__).parent / "validate_verification.py"
        content = src.read_text(encoding="utf-8")
        self.assertNotIn("state.yaml", content,
                         "validate_verification.py must not reference system SOT")


if __name__ == "__main__":
    unittest.main()
