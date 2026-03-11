#!/usr/bin/env python3
"""Compute SRCS scores — deterministic axes (CS, VS) computed by Python.

This script handles the P1 (deterministic) portion of SRCS scoring:
  - CS (Citation Score): count and validate citations
  - VS (Verifiability Score): check for DOIs, URLs, verifiable references

GS (Grounding Score) and US (Uncertainty Score) require LLM evaluation
and are handled by the unified-srcs-evaluator agent.

Usage:
  python3 compute_srcs_scores.py --file <claim-file.md>
  python3 compute_srcs_scores.py --project-dir <dir> --wave <N>
"""

import argparse
import json
import re
import sys
from pathlib import Path

from _claim_patterns import (  # noqa: E402
    CITATION_DOI_RE,
    CITATION_INLINE_RE,
    CITATION_PAREN_RE,
    count_claims as _count_claims,
)

# Scoring parameters
MAX_CS_SCORE = 100
MAX_VS_SCORE = 100


def compute_citation_score(content: str, claim_count: int) -> int:
    """Compute Citation Score (CS) — deterministic.

    Criteria:
    - Citations per claim ratio
    - DOI presence
    - Publication year recency
    - Source diversity (PRIMARY vs SECONDARY)
    """
    if claim_count == 0:
        return 0

    # Count citations using centralized patterns from _claim_patterns
    citations = CITATION_PAREN_RE.findall(content)
    citations2 = CITATION_INLINE_RE.findall(content)
    total_citations = len(citations) + len(citations2)

    # Citations per claim ratio (target: 2+ per claim = full score)
    ratio = min(total_citations / max(claim_count, 1), 2.0)
    ratio_score = ratio / 2.0 * 40  # 40 points max

    # DOI presence (centralized pattern from _claim_patterns)
    dois = CITATION_DOI_RE.findall(content)
    doi_count = len(dois)
    doi_score = min(doi_count / max(claim_count, 1), 1.0) * 30  # 30 points max

    # Source type diversity
    primary = len(re.findall(r'type:\s*PRIMARY', content))
    secondary = len(re.findall(r'type:\s*SECONDARY', content))
    diversity = 1.0 if (primary > 0 and secondary > 0) else 0.5
    diversity_score = diversity * 30  # 30 points max

    return min(round(ratio_score + doi_score + diversity_score), MAX_CS_SCORE)


def compute_verifiability_score(content: str, claim_count: int) -> int:
    """Compute Verifiability Score (VS) — deterministic.

    Criteria:
    - DOI/URL availability for claims
    - Specific page/section references
    - Reproducibility indicators
    """
    if claim_count == 0:
        return 0

    # DOI count (centralized pattern from _claim_patterns)
    dois = len(CITATION_DOI_RE.findall(content))
    doi_ratio = min(dois / max(claim_count, 1), 1.0)
    doi_score = doi_ratio * 40  # 40 points

    # URL/link count
    urls = len(re.findall(r'https?://\S+', content))
    url_score = min(urls / max(claim_count, 1), 1.0) * 20  # 20 points

    # verified: true markers
    verified = len(re.findall(r'verified:\s*true', content, re.IGNORECASE))
    verified_ratio = min(verified / max(claim_count, 1), 1.0)
    verified_score = verified_ratio * 20  # 20 points

    # Specific references (page numbers, sections, volumes, tables, figures)
    specifics = len(re.findall(
        r'(?:p\.\s*\d+|pp\.\s*\d+[-–]\d+|p\s+\d+|'
        r'chapter\s+\d+|section\s+\d+|'
        r'vol\.\s*\d+|volume\s+\d+|'
        r'table\s+\d+|figure\s+\d+|fig\.\s*\d+)',
        content, re.IGNORECASE,
    ))
    specific_score = min(specifics / max(claim_count, 1), 1.0) * 20  # 20 points

    return min(round(doi_score + url_score + verified_score + specific_score), MAX_VS_SCORE)


def compute_file_scores(file_path: str) -> dict:
    """Compute CS and VS scores for a single file."""
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    content = path.read_text(encoding="utf-8")

    # Count claims (centralized pattern from _claim_patterns)
    claim_count = _count_claims(content)

    cs = compute_citation_score(content, claim_count)
    vs = compute_verifiability_score(content, claim_count)

    return {
        "file": str(path.name),
        "claim_count": claim_count,
        "CS": cs,
        "VS": vs,
        "GS": None,  # Requires LLM evaluation
        "US": None,  # Requires LLM evaluation
        "mode": "P1_ONLY",  # GS/US null → P1 only; "WITH_EVALUATOR" when LLM fills GS/US
        "note": "GS and US require LLM evaluation via unified-srcs-evaluator",
    }


def compute_wave_scores(project_dir: str, wave: int) -> list[dict]:
    """Compute CS and VS for all files in a wave."""
    wave_dir = Path(project_dir) / "wave-results" / f"wave-{wave}"
    if not wave_dir.is_dir():
        return [{"error": f"Wave directory not found: {wave_dir}"}]

    results = []
    for md_file in sorted(wave_dir.glob("*.md")):
        if md_file.name.endswith(".ko.md"):
            continue
        results.append(compute_file_scores(str(md_file)))

    return results


def main():
    parser = argparse.ArgumentParser(description="SRCS Score Computer (CS, VS)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Single file to score")
    group.add_argument("--project-dir", help="Project directory (use with --wave)")
    parser.add_argument("--wave", type=int, help="Wave number (1-5)")
    parser.add_argument("--output-json", help="Write results to JSON")
    args = parser.parse_args()

    if args.file:
        results = [compute_file_scores(args.file)]
    elif args.project_dir:
        if not args.wave:
            parser.error("--project-dir requires --wave")
        results = compute_wave_scores(args.project_dir, args.wave)
    else:
        parser.error("Specify --file or --project-dir + --wave")
        return 1

    for r in results:
        if "error" in r:
            print(f"ERROR: {r['error']}")
        else:
            print(f"{r['file']}: CS={r['CS']}, VS={r['VS']}, claims={r['claim_count']}")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults written to: {args.output_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
