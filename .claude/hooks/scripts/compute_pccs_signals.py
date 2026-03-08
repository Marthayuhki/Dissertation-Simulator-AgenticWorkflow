#!/usr/bin/env python3
"""compute_pccs_signals.py — Phase A: P1 Ground Truth Signal Extraction.

Reads thesis output files and extracts deterministic P1 signals per claim.
Produces claim-map.json for downstream LLM evaluation and P1 synthesis.

This is the first phase of the pCCS P1 Sandwich pipeline:
  Phase A (this) → Phase B-1 (LLM) → Phase C-1 (P1) → Phase B-2 (LLM) →
  Phase C-2 (P1) → Phase D (P1 synthesis)

P1 Signals extracted per claim:
  A1 — Citation presence: does the claim have a source citation with year?
  A2 — Trace marker presence: does the claim reference prior steps?
  A3 — Blocked pattern detection: does the claim contain absolute language?
  A4 — Source-requiring pattern: does the claim have stats without citation?
  A5 — Confidence field existence: was a confidence value explicitly stated?
  A6 — Claim type validity: is the claim_type recognized?

Output: claim-map.json
  {
    "step": N,
    "file": "path/to/file.md",
    "total_claims": N,
    "claims": [
      {
        "claim_id": "EMP-001",
        "claim_type": "EMPIRICAL",
        "canonical_type": "EMPIRICAL",
        "confidence_raw": "95",
        "confidence_numeric": 95,
        "p1_signals": {
          "a1_has_citation": true,
          "a2_has_trace": false,
          "a3_blocked": false,
          "a4_stats_no_source": false,
          "a5_confidence_explicit": true,
          "a6_type_recognized": true
        },
        "p1_score": 85.0
      }, ...
    ]
  }

Usage:
  python3 compute_pccs_signals.py --file <output.md> --step <N>
  python3 compute_pccs_signals.py --file <output.md> --step <N> --output claim-map.json

Exit codes:
  0 — always (P1 compliant, non-blocking)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

# Add script directory to path for shared library import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _claim_patterns import (  # noqa: E402
    BLOCKED_CLAIM_PATTERNS,
    CITATION_YEAR_RE,
    CONFIDENCE_DEFAULT,
    REQUIRE_SOURCE_PATTERNS,
    TRACE_MARKER_RE,
    canonicalize_claim_type,
    extract_claim_metadata,
)


# =============================================================================
# P1 Signal Weights for p1_score computation
# =============================================================================

# Each signal contributes to the P1 ground truth score (0-100).
# These are additive bonuses/penalties.
_P1_WEIGHTS = {
    "a1_has_citation": 30,       # +30 if claim has citation
    "a2_has_trace": 10,          # +10 if claim references prior steps
    "a3_blocked": -40,           # -40 if claim uses absolute language
    "a4_stats_no_source": -20,   # -20 if claim has stats without source
    "a5_confidence_explicit": 10,  # +10 if confidence was explicitly stated
    "a6_type_recognized": 10,    # +10 if claim_type maps to known canonical
}

# Base P1 score (before signals)
_P1_BASE = 50


def _extract_claim_context(content: str, claim_id: str) -> str:
    """Extract context for a claim using natural claim block boundaries.

    Uses adjacent claim IDs as boundaries instead of a fixed character window.
    The previous claim_id occurrence (or start of file) marks the block start,
    and the next claim_id occurrence (or end of file) marks the block end.
    The block is capped at 800 chars max to keep signal analysis bounded.
    """
    # Find the claim ID in content
    pattern = re.compile(re.escape(claim_id))
    match = pattern.search(content)
    if not match:
        return ""

    # Find natural boundaries using any claim_id pattern (e.g., "EMP-001", "THEO-NEURO-003")
    # Matches standard claim ID format: 2-4 uppercase letters, optional sub-prefix, dash, digits
    claim_id_boundary = re.compile(r'[A-Z]{2,4}(?:-[A-Z]{2,})*-\d{3,}')

    # Find previous claim_id (block start)
    block_start = 0
    for prev_match in claim_id_boundary.finditer(content, 0, match.start()):
        if prev_match.group() != claim_id:
            block_start = prev_match.start()

    # Find next claim_id (block end)
    block_end = len(content)
    for next_match in claim_id_boundary.finditer(content, match.end()):
        if next_match.group() != claim_id:
            block_end = next_match.start()
            break

    # Cap at 800 chars max, centered on the claim_id
    block_len = block_end - block_start
    if block_len > 800:
        center = match.start()
        half = 400
        block_start = max(block_start, center - half)
        block_end = min(block_end, block_start + 800)

    return content[block_start:block_end]


def compute_p1_signals(
    claim: dict[str, Any],
    content: str,
) -> dict[str, Any]:
    """Compute P1 ground truth signals for a single claim.

    Args:
        claim: Claim metadata dict from extract_claim_metadata().
        content: Full file content for context extraction.

    Returns:
        Dict with p1_signals and computed p1_score.
    """
    claim_id = claim["claim_id"]
    context = _extract_claim_context(content, claim_id)

    # A1: Citation presence
    a1 = claim.get("has_citation", False)

    # A2: Trace marker presence in context
    a2 = bool(TRACE_MARKER_RE.search(context))

    # A3: Blocked absolute-claim pattern in context
    a3 = any(p.search(context) for p in BLOCKED_CLAIM_PATTERNS)

    # A4: Statistical claim without source citation
    a4 = False
    for p in REQUIRE_SOURCE_PATTERNS:
        if p.search(context):
            # Check if there's a citation nearby
            if not CITATION_YEAR_RE.search(context):
                a4 = True
                break

    # A5: Confidence field explicitly present (not defaulted)
    a5 = claim.get("confidence_raw") is not None

    # A6: Claim type recognized (not UNKNOWN)
    a6 = claim.get("canonical_type", "UNKNOWN") != "UNKNOWN"

    signals = {
        "a1_has_citation": a1,
        "a2_has_trace": a2,
        "a3_blocked": a3,
        "a4_stats_no_source": a4,
        "a5_confidence_explicit": a5,
        "a6_type_recognized": a6,
    }

    # Compute P1 score
    score = _P1_BASE
    for key, weight in _P1_WEIGHTS.items():
        if signals[key]:
            score += weight
    score = max(0, min(100, score))

    return {
        "p1_signals": signals,
        "p1_score": float(score),
    }


def compute_claim_map(
    file_path: str,
    step: int,
) -> dict[str, Any]:
    """Compute the full claim-map for a file.

    Args:
        file_path: Path to thesis output .md file.
        step: Thesis workflow step number.

    Returns:
        claim-map dict ready for JSON serialization.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError) as e:
        return {
            "step": step,
            "file": file_path,
            "total_claims": 0,
            "claims": [],
            "error": str(e),
        }

    claims_meta = extract_claim_metadata(content)

    claims_out: list[dict[str, Any]] = []
    for cm in claims_meta:
        p1 = compute_p1_signals(cm, content)
        claims_out.append({
            "claim_id": cm["claim_id"],
            "claim_type": cm["claim_type"],
            "canonical_type": cm["canonical_type"],
            "confidence_raw": cm["confidence_raw"],
            "confidence_numeric": cm["confidence_numeric"],
            "has_source": cm["has_source"],
            "source_text": cm["source_text"],
            **p1,
        })

    return {
        "step": step,
        "file": os.path.basename(file_path),
        "total_claims": len(claims_out),
        "claims": claims_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="pCCS Phase A: P1 Ground Truth Signal Extraction"
    )
    parser.add_argument(
        "--file", required=True,
        help="Thesis output file (.md) to analyze"
    )
    parser.add_argument(
        "--step", type=int, required=True,
        help="Thesis workflow step number"
    )
    parser.add_argument(
        "--output",
        help="Output JSON file path (default: stdout)"
    )
    args = parser.parse_args()

    result = compute_claim_map(args.file, args.step)

    json_str = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        out_dir = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(out_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(
            f"[compute_pccs_signals] Phase A complete: "
            f"{result['total_claims']} claims → {args.output}"
        )
    else:
        print(json_str)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[compute_pccs_signals] FATAL: {e}", file=sys.stderr)
        sys.exit(0)  # P1: never block
