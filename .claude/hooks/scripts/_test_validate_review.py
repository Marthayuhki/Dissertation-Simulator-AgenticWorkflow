#!/usr/bin/env python3
"""Tests for validate_review.py — Adversarial Review validation (R1-R5).

Run: python3 -m pytest _test_validate_review.py -v
  or: python3 _test_validate_review.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import validate_review as vr


class TestReviewValidation(unittest.TestCase):
    """Test Adversarial Review validation rules R1-R5."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.review_dir = self.tmpdir / "review-logs"
        self.review_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write_review_log(self, step, content):
        path = self.review_dir / f"step-{step}-review.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _make_valid_review(self, step=1, verdict="PASS"):
        return (
            f"# Review Report — Step {step}\n\n"
            f"## Issues Found\n\n"
            f"1. Minor: Citation format inconsistency (p.3)\n"
            f"2. Suggestion: Add methodology justification\n\n"
            f"## pACS Assessment\n\n"
            f"- F: 80\n- C: 75\n- L: 85\n\n"
            f"## Verdict: {verdict}\n"
        )

    def test_valid_review_log(self):
        self._write_review_log(1, self._make_valid_review())
        result = vr.validate_review_log(
            str(self.review_dir / "step-1-review.md"))
        self.assertTrue(result.get("valid", False) or result.get("r1", False),
                        f"Valid review log should pass: {result}")

    def test_missing_file(self):
        result = vr.validate_review_log(
            str(self.review_dir / "nonexistent.md"))
        self.assertFalse(result.get("valid", True))

    def test_empty_file(self):
        self._write_review_log(1, "")
        result = vr.validate_review_log(
            str(self.review_dir / "step-1-review.md"))
        self.assertFalse(result.get("valid", True))


class TestNoSystemSOTReference(unittest.TestCase):
    def test_no_state_yaml_reference(self):
        src = Path(__file__).parent / "validate_review.py"
        content = src.read_text(encoding="utf-8")
        self.assertNotIn("state.yaml", content,
                         "validate_review.py must not reference system SOT")


if __name__ == "__main__":
    unittest.main()
