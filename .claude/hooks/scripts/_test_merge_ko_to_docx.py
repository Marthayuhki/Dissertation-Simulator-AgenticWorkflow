#!/usr/bin/env python3
"""Tests for merge_ko_to_docx.py — Korean thesis DOCX merge script."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Import from sibling module
sys.path.insert(0, str(Path(__file__).parent))
from merge_ko_to_docx import (
    discover_chapter_files,
    get_chapter_priority,
    merge_files_to_markdown,
    should_exclude,
)


class TestGetChapterPriority(unittest.TestCase):
    """Test keyword-based chapter priority heuristic."""

    def test_abstract(self):
        self.assertEqual(get_chapter_priority("step-193-abstract.ko.md"), 0)

    def test_chapter_1_by_number(self):
        self.assertEqual(
            get_chapter_priority("step-181-chapter1-introduction.ko.md"), 1,
        )

    def test_chapter_2_by_number(self):
        self.assertEqual(
            get_chapter_priority("step-183-chapter2-literature-review.ko.md"), 2,
        )

    def test_chapters_7_8_combined(self):
        self.assertEqual(
            get_chapter_priority("step-191-chapters7-8-discussion-conclusion.ko.md"), 7,
        )

    def test_appendices(self):
        self.assertEqual(get_chapter_priority("step-195-appendices.ko.md"), 90)

    def test_references(self):
        self.assertEqual(get_chapter_priority("step-195-references.ko.md"), 91)

    def test_unknown_gets_50(self):
        self.assertEqual(get_chapter_priority("step-999-something-else.ko.md"), 50)

    def test_introduction_keyword(self):
        # "introduction" keyword maps to priority 1
        self.assertEqual(get_chapter_priority("step-001-introduction.ko.md"), 1)

    def test_methodology_keyword(self):
        self.assertEqual(get_chapter_priority("step-003-methodology.ko.md"), 3)

    def test_bibliography_keyword(self):
        self.assertEqual(get_chapter_priority("step-999-bibliography.ko.md"), 91)


class TestShouldExclude(unittest.TestCase):
    """Test non-content file exclusion."""

    def test_cover_letter_excluded(self):
        self.assertTrue(should_exclude("step-197-cover-letter.ko.md"))

    def test_korean_thesis_summary_excluded(self):
        self.assertTrue(should_exclude("step-202-korean-thesis-summary.ko.md"))

    def test_thesis_summary_excluded(self):
        self.assertTrue(should_exclude("step-999-thesis-summary.ko.md"))

    def test_chapter_not_excluded(self):
        self.assertFalse(should_exclude("step-181-chapter1-introduction.ko.md"))

    def test_abstract_not_excluded(self):
        self.assertFalse(should_exclude("step-193-abstract.ko.md"))

    def test_appendices_not_excluded(self):
        self.assertFalse(should_exclude("step-195-appendices.ko.md"))


class TestDiscoverChapterFiles(unittest.TestCase):
    """Test file discovery and ordering."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        self.translations_dir = self.project_dir / "translations"
        self.translations_dir.mkdir(parents=True)
        self.deliverables_dir = self.project_dir / "deliverables"
        self.deliverables_dir.mkdir(parents=True)

    def _create_file(self, name: str, content: str = "test content") -> Path:
        path = self.translations_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_heuristic_ordering_standard(self):
        """Files should be ordered: abstract, ch1, ch2, ..., appendix, references."""
        self._create_file("step-195-references.ko.md")
        self._create_file("step-181-chapter1-introduction.ko.md")
        self._create_file("step-193-abstract.ko.md")
        self._create_file("step-183-chapter2-literature-review.ko.md")
        self._create_file("step-195-appendices.ko.md")

        files = discover_chapter_files(self.translations_dir, self.project_dir)
        names = [f.name for f in files]

        self.assertEqual(names, [
            "step-193-abstract.ko.md",
            "step-181-chapter1-introduction.ko.md",
            "step-183-chapter2-literature-review.ko.md",
            "step-195-appendices.ko.md",
            "step-195-references.ko.md",
        ])

    def test_excludes_cover_letter(self):
        self._create_file("step-181-chapter1-introduction.ko.md")
        self._create_file("step-197-cover-letter.ko.md")

        files = discover_chapter_files(self.translations_dir, self.project_dir)
        names = [f.name for f in files]

        self.assertNotIn("step-197-cover-letter.ko.md", names)
        self.assertIn("step-181-chapter1-introduction.ko.md", names)

    def test_excludes_korean_thesis_summary(self):
        self._create_file("step-181-chapter1-introduction.ko.md")
        self._create_file("step-202-korean-thesis-summary.ko.md")

        files = discover_chapter_files(self.translations_dir, self.project_dir)
        names = [f.name for f in files]

        self.assertNotIn("step-202-korean-thesis-summary.ko.md", names)

    def test_ignores_non_ko_md_files(self):
        """Only step-*-*.ko.md files should be discovered."""
        self._create_file("step-181-chapter1-introduction.ko.md")
        (self.translations_dir / "step-199-cross-validation.md").write_text("x")
        (self.translations_dir / "glossary.yaml").write_text("x")

        files = discover_chapter_files(self.translations_dir, self.project_dir)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "step-181-chapter1-introduction.ko.md")

    def test_chapter_order_json_tier1(self):
        """Tier 1: chapter-order.json overrides heuristic."""
        self._create_file("step-193-abstract.ko.md")
        self._create_file("step-181-chapter1-introduction.ko.md")

        # Create chapter-order.json with reversed order
        order = [
            "step-181-chapter1-introduction.ko.md",
            "step-193-abstract.ko.md",
        ]
        order_file = self.deliverables_dir / "chapter-order.json"
        order_file.write_text(json.dumps(order), encoding="utf-8")

        files = discover_chapter_files(self.translations_dir, self.project_dir)
        names = [f.name for f in files]

        # Should follow chapter-order.json, not heuristic
        self.assertEqual(names, [
            "step-181-chapter1-introduction.ko.md",
            "step-193-abstract.ko.md",
        ])

    def test_chapter_order_json_missing_file_skipped(self):
        """Tier 1: missing files in chapter-order.json are skipped."""
        self._create_file("step-181-chapter1-introduction.ko.md")

        order = [
            "step-181-chapter1-introduction.ko.md",
            "step-999-nonexistent.ko.md",
        ]
        order_file = self.deliverables_dir / "chapter-order.json"
        order_file.write_text(json.dumps(order), encoding="utf-8")

        files = discover_chapter_files(self.translations_dir, self.project_dir)
        self.assertEqual(len(files), 1)

    def test_empty_translations_returns_empty(self):
        files = discover_chapter_files(self.translations_dir, self.project_dir)
        self.assertEqual(files, [])

    def test_duplicate_step_numbers_handled(self):
        """Two files with same step number should both be included and properly ordered."""
        self._create_file("step-191-chapter6-application.ko.md")
        self._create_file("step-191-chapters7-8-discussion-conclusion.ko.md")

        files = discover_chapter_files(self.translations_dir, self.project_dir)
        names = [f.name for f in files]

        # chapter6 (priority 6) before chapters7 (priority 7)
        self.assertEqual(names, [
            "step-191-chapter6-application.ko.md",
            "step-191-chapters7-8-discussion-conclusion.ko.md",
        ])


class TestMergeFilesToMarkdown(unittest.TestCase):
    """Test markdown merging."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def _create_file(self, name: str, content: str) -> Path:
        path = self.tmpdir / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_single_file(self):
        f = self._create_file("ch1.md", "# Chapter 1\nContent")
        result = merge_files_to_markdown([f])
        self.assertEqual(result, "# Chapter 1\nContent")

    def test_multiple_files_separated_by_hr(self):
        f1 = self._create_file("ch1.md", "# Chapter 1")
        f2 = self._create_file("ch2.md", "# Chapter 2")
        result = merge_files_to_markdown([f1, f2])
        self.assertIn("---", result)
        self.assertIn("# Chapter 1", result)
        self.assertIn("# Chapter 2", result)

    def test_strips_whitespace(self):
        f = self._create_file("ch1.md", "\n\n# Chapter 1\n\n\n")
        result = merge_files_to_markdown([f])
        self.assertEqual(result, "# Chapter 1")


class TestCLIDryRun(unittest.TestCase):
    """Test CLI --dry-run mode."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.project_dir = self.tmpdir / "thesis"
        translations_dir = self.project_dir / "translations"
        translations_dir.mkdir(parents=True)
        (translations_dir / "step-181-chapter1-introduction.ko.md").write_text("ch1")
        (translations_dir / "step-193-abstract.ko.md").write_text("abstract")

    def test_dry_run_json_output(self):
        script = str(Path(__file__).parent / "merge_ko_to_docx.py")
        result = subprocess.run(
            [sys.executable, script,
             "--project-dir", str(self.project_dir),
             "--dry-run", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data["mode"], "dry_run")
        self.assertEqual(data["files_count"], 2)
        # Abstract should come first (priority 0 < 1)
        self.assertEqual(data["files"][0], "step-193-abstract.ko.md")

    def test_dry_run_no_translations_returns_error(self):
        empty_project = self.tmpdir / "empty"
        (empty_project / "translations").mkdir(parents=True)

        script = str(Path(__file__).parent / "merge_ko_to_docx.py")
        result = subprocess.run(
            [sys.executable, script,
             "--project-dir", str(empty_project),
             "--dry-run", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertIn("error", data)


class TestStep211Integration(unittest.TestCase):
    """Integration test: verify step 211 query_step output."""

    def test_step_211_returns_orchestrator(self):
        from query_step import query_step
        result = query_step(211)
        self.assertEqual(result["agent"], "_orchestrator")
        self.assertEqual(result["tier"], 3)
        self.assertEqual(result["phase"], "phase_6_translation")
        self.assertFalse(result["pccs_required"])
        self.assertFalse(result["translation_required"])
        self.assertEqual(result["output_path"], "deliverables/consolidated-thesis-ko.docx")
        self.assertIsNotNone(result["execution_command"])
        self.assertIn("merge_ko_to_docx.py", result["execution_command"])
        self.assertIn("{project_dir}", result["execution_command"])

    def test_step_211_not_in_translation_steps(self):
        from query_step import _TRANSLATION_STEPS
        self.assertNotIn(211, _TRANSLATION_STEPS)

    def test_step_211_not_consolidated(self):
        from query_step import query_step
        result = query_step(211)
        self.assertEqual(result["consolidate_with"], [211])
        self.assertIsNone(result["consolidated_output_filename"])


if __name__ == "__main__":
    unittest.main()
