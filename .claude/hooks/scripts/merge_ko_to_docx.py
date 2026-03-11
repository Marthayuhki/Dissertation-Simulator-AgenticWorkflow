#!/usr/bin/env python3
"""Merge Korean translation files into a consolidated Word document.

Discovers .ko.md chapter files in translations/, orders them by academic
convention, merges into a single markdown, then converts to .docx via pandoc.

Chapter ordering strategy (2-tier):
  Tier 1: Read deliverables/chapter-order.json if it exists (explicit list)
  Tier 2: Keyword-based heuristic (abstract→0, chapterN→N, appendix→90, reference→91)

P1 Compliance: Pure stdlib + pandoc subprocess. No LLM, deterministic, exit 0 always.

Usage:
  python3 merge_ko_to_docx.py --project-dir <dir>
  python3 merge_ko_to_docx.py --project-dir <dir> --json
  python3 merge_ko_to_docx.py --project-dir <dir> --dry-run
  python3 merge_ko_to_docx.py --project-dir <dir> --reference-doc style.docx
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Chapter ordering — keyword → sort priority (Tier 2 heuristic)
# ---------------------------------------------------------------------------

# Priority values: lower = earlier in document.
# 0 = abstract (front matter), 1-89 = body chapters, 90+ = back matter.
_CHAPTER_PRIORITY: dict[str, int] = {
    "abstract": 0,
    "chapter1": 1, "chapter-1": 1, "introduction": 1,
    "chapter2": 2, "chapter-2": 2, "literature": 2,
    "chapter3": 3, "chapter-3": 3, "methodology": 3,
    "chapter4": 4, "chapter-4": 4,
    "chapter5": 5, "chapter-5": 5,
    "chapter6": 6, "chapter-6": 6,
    "chapter7": 7, "chapter-7": 7,
    "chapter8": 8, "chapter-8": 8,
    "chapter9": 9, "chapter-9": 9,
    "chapter10": 10, "chapter-10": 10,
    "appendix": 90, "appendices": 90,
    "reference": 91, "references": 91, "bibliography": 91,
}

# Files to exclude from thesis content merge.
# These are .ko.md files that are NOT part of the thesis body.
_EXCLUDE_KEYWORDS: set[str] = {
    "cover-letter",
    "cover_letter",
    "korean-thesis-summary",
    "thesis-summary",
}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def get_chapter_priority(filename: str) -> int:
    """Compute sort priority for a translation file using keyword heuristics.

    Returns:
        int priority: 0 = abstract, 1-N = chapter number, 50 = unknown,
        90 = appendix, 91 = references.
    """
    name_lower = filename.lower()

    # Pattern 1: explicit chapter number — "chapterN" or "chapters7-8"
    m = re.search(r"chapters?[-_]?(\d+)", name_lower)
    if m:
        return int(m.group(1))

    # Pattern 2: keyword match from priority table
    for keyword, priority in _CHAPTER_PRIORITY.items():
        if keyword in name_lower:
            return priority

    # Unknown content — place after chapters, before appendices
    return 50


def should_exclude(filename: str) -> bool:
    """Check if a file should be excluded from the thesis merge."""
    name_lower = filename.lower()
    for keyword in _EXCLUDE_KEYWORDS:
        if keyword in name_lower:
            return True
    return False


def discover_chapter_files(
    translations_dir: Path,
    project_dir: Path,
) -> list[Path]:
    """Discover and order Korean translation files for merging.

    Tier 1: Read deliverables/chapter-order.json if it exists.
            Format: JSON array of filenames (relative to translations/).
    Tier 2: Keyword-based heuristic ordering.

    Returns:
        Ordered list of Path objects to chapter files.
    """
    # Tier 1: Explicit chapter order file
    order_file = project_dir / "deliverables" / "chapter-order.json"
    if order_file.exists():
        try:
            with open(order_file, "r", encoding="utf-8") as f:
                order = json.load(f)
            if isinstance(order, list) and len(order) > 0:
                files: list[Path] = []
                for name in order:
                    path = translations_dir / str(name)
                    if path.exists():
                        files.append(path)
                if files:
                    return files
        except (json.JSONDecodeError, IOError):
            pass  # Fall through to heuristic

    # Tier 2: Keyword-based heuristic
    ko_files = sorted(translations_dir.glob("step-*-*.ko.md"))

    # Filter: exclude non-thesis-content files
    content_files = [f for f in ko_files if not should_exclude(f.name)]

    # Sort by chapter priority, then by filename for stable ordering
    content_files.sort(key=lambda f: (get_chapter_priority(f.name), f.name))

    return content_files


def merge_files_to_markdown(files: list[Path]) -> str:
    """Concatenate chapter files into a single markdown string.

    Inserts a horizontal rule between chapters as a visual separator.
    """
    parts: list[str] = []
    for i, filepath in enumerate(files):
        content = filepath.read_text(encoding="utf-8").strip()
        if i > 0:
            parts.append("\n\n---\n\n")
        parts.append(content)
    return "\n".join(parts)


def convert_to_docx(
    markdown_path: Path,
    docx_path: Path,
    reference_doc: str | None = None,
) -> tuple[bool, str]:
    """Convert markdown to docx using pandoc.

    Returns:
        (success: bool, message: str)
    """
    if not shutil.which("pandoc"):
        return False, "pandoc not found in PATH"

    cmd: list[str] = [
        "pandoc",
        str(markdown_path),
        "-o", str(docx_path),
        "-f", "markdown",
        "-t", "docx",
        "--toc",
        "--toc-depth=3",
    ]
    if reference_doc and os.path.exists(reference_doc):
        cmd.extend(["--reference-doc", reference_doc])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return True, "OK"
        return False, f"pandoc exit {result.returncode}: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, "pandoc timed out (120s)"
    except OSError as e:
        return False, f"pandoc OSError: {e}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge Korean translation files into consolidated Word document"
    )
    parser.add_argument(
        "--project-dir", required=True,
        help="Thesis project directory",
    )
    parser.add_argument(
        "--reference-doc",
        help="Optional pandoc reference.docx for custom styling",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show files that would be merged without executing",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()
    project_dir = Path(args.project_dir)
    translations_dir = project_dir / "translations"
    deliverables_dir = project_dir / "deliverables"

    # Validate inputs
    if not project_dir.exists():
        _output({"error": f"Project directory not found: {project_dir}"}, args.json)
        return 1
    if not translations_dir.exists():
        _output(
            {"error": f"Translations directory not found: {translations_dir}"},
            args.json,
        )
        return 1

    # Discover and order chapter files
    chapter_files = discover_chapter_files(translations_dir, project_dir)

    if not chapter_files:
        _output({"error": "No Korean translation chapter files found"}, args.json)
        return 1

    # Dry run: show what would be merged
    if args.dry_run:
        result: dict[str, Any] = {
            "mode": "dry_run",
            "files_count": len(chapter_files),
            "files": [f.name for f in chapter_files],
            "order": [
                {
                    "index": i,
                    "file": f.name,
                    "priority": get_chapter_priority(f.name),
                }
                for i, f in enumerate(chapter_files)
            ],
        }
        _output(result, args.json)
        return 0

    # Ensure deliverables directory exists
    deliverables_dir.mkdir(parents=True, exist_ok=True)

    # Merge files into single markdown
    merged_content = merge_files_to_markdown(chapter_files)
    merged_md_path = deliverables_dir / "consolidated-thesis-ko.md"
    merged_md_path.write_text(merged_content, encoding="utf-8")

    # Convert to docx
    docx_path = deliverables_dir / "consolidated-thesis-ko.docx"
    docx_success, docx_msg = convert_to_docx(
        merged_md_path, docx_path, args.reference_doc,
    )

    # Build result
    result = {
        "status": "success",
        "files_merged": len(chapter_files),
        "files": [f.name for f in chapter_files],
        "markdown_output": str(merged_md_path),
        "docx_output": str(docx_path) if docx_success else None,
        "docx_generated": docx_success,
    }

    if not docx_success:
        result["warning"] = (
            f"DOCX conversion unavailable ({docx_msg}). "
            f"Consolidated markdown saved as fallback. "
            f"Install pandoc to generate .docx: brew install pandoc"
        )

    _output(result, args.json)
    return 0


def _output(data: dict[str, Any], as_json: bool) -> None:
    """Print result in JSON or human-readable format."""
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    if "error" in data:
        print(f"ERROR: {data['error']}", file=sys.stderr)
        return

    if data.get("mode") == "dry_run":
        print(f"Dry run: {data['files_count']} files would be merged:")
        for entry in data.get("order", []):
            print(f"  {entry['index']:2d}. {entry['file']} (priority {entry['priority']})")
        return

    n = data.get("files_merged", 0)
    print(f"Merged {n} files into consolidated thesis")
    if data.get("docx_generated"):
        print(f"  DOCX: {data['docx_output']}")
    print(f"  Markdown: {data['markdown_output']}")
    if "warning" in data:
        print(f"  WARNING: {data['warning']}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # P1: exit 0 always (non-blocking)
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(0)
