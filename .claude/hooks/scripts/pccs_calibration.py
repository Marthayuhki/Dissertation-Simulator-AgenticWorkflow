#!/usr/bin/env python3
"""pccs_calibration.py — pCCS Calibration Delta Computation.

Computes the calibration delta (cal_delta) by comparing agent confidence
against ground truth from @fact-checker (Tier 1) and L1 Verification (Tier 2).

Calibration reduces systematic over-confidence by computing:
  cal_delta = mean(agent_confidence - ground_truth_score)

If agents consistently rate claims at 90 but @fact-checker verdicts average
80, cal_delta = 10 and all future scores are adjusted downward by 10.

Tier 1 (@fact-checker verdicts — primary):
  Verified → 90, Partially Verified → 60, Unable to Verify → 40,
  Outdated → 30, False → 10

Tier 2 (L1 Verification PASS/FAIL — secondary):
  PASS → 85, FAIL → 30

Output: pccs-calibration.json
  {
    "cal_delta": 5.0,
    "tier1_samples": 12,
    "tier2_samples": 24,
    "total_samples": 36,
    "tier1_delta": 8.0,
    "tier2_delta": 3.0,
    "computed_at_step": 63
  }

Usage:
  python3 pccs_calibration.py --project-dir . --step 63
  python3 pccs_calibration.py --project-dir . --step 63 --output pccs-calibration.json

Exit codes:
  0 — always (P1 compliant, non-blocking)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


# =============================================================================
# Ground Truth Mapping
# =============================================================================

# Tier 1: @fact-checker verdict → numeric ground truth
VERDICT_TO_SCORE: dict[str, int] = {
    "verified": 90,
    "partially verified": 60,
    "unable to verify": 40,
    "outdated": 30,
    "false": 10,
}

# Tier 2: L1 Verification result → numeric ground truth
L1_RESULT_TO_SCORE: dict[str, int] = {
    "pass": 85,
    "fail": 30,
}


def _scan_fact_checker_logs(project_dir: str) -> list[dict[str, Any]]:
    """Scan fact-checker logs for verdict data (Tier 1).

    Returns list of {"claim_id": str, "verdict": str, "score": int}
    """
    logs_dir = Path(project_dir) / "dialogue-logs"
    if not logs_dir.is_dir():
        return []

    samples: list[dict[str, Any]] = []

    # Scan for fact-checker verdict patterns in dialogue logs
    verdict_re = re.compile(
        r'(?:verdict|result):\s*["\']?(Verified|Partially Verified|'
        r'Unable to Verify|Outdated|False)["\']?',
        re.IGNORECASE,
    )
    claim_re = re.compile(
        r'(?:id|claim_id):\s*["\']?([A-Z]{1,6}(?:-[A-Z]{1,6})*-?\d{2,4})["\']?'
    )

    for log_file in sorted(logs_dir.glob("*.md")):
        # Match fact-checker output files: step-{N}-r{K}-fc.md or *fact-check*.md
        name_lower = log_file.name.lower()
        if not (name_lower.endswith("-fc.md") or "fact-check" in name_lower):
            continue
        try:
            content = log_file.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            continue

        # Find claim-verdict pairs
        for vm in verdict_re.finditer(content):
            verdict = vm.group(1).lower()
            score = VERDICT_TO_SCORE.get(verdict)
            if score is None:
                continue
            # Find nearest claim ID (look backward up to 500 chars)
            start = max(0, vm.start() - 500)
            context = content[start:vm.start()]
            cm = claim_re.search(context)
            if cm:
                samples.append({
                    "claim_id": cm.group(1),
                    "verdict": verdict,
                    "score": score,
                })

    return samples


def _scan_verification_logs(project_dir: str) -> list[dict[str, Any]]:
    """Scan L1 verification logs for PASS/FAIL data (Tier 2).

    Returns list of {"step": int, "result": str, "score": int}
    """
    logs_dir = Path(project_dir) / "verification-logs"
    if not logs_dir.is_dir():
        return []

    samples: list[dict[str, Any]] = []
    result_re = re.compile(r'\|\s*.*?\s*\|\s*(PASS|FAIL)\s*\|', re.IGNORECASE)

    for log_file in sorted(logs_dir.glob("step-*-verify.md")):
        try:
            content = log_file.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            continue

        # Extract step number
        step_match = re.search(r'step-(\d+)', log_file.name)
        step = int(step_match.group(1)) if step_match else -1

        for rm in result_re.finditer(content):
            result = rm.group(1).lower()
            score = L1_RESULT_TO_SCORE.get(result)
            if score is not None:
                samples.append({
                    "step": step,
                    "result": result,
                    "score": score,
                })

    return samples


def compute_calibration(
    project_dir: str,
    current_step: int,
    agent_mean_confidence: float = 85.0,
) -> dict[str, Any]:
    """Compute calibration delta from available ground truth.

    Uses a weighted combination:
      - Tier 1 (fact-checker): weight 2.0 (more reliable)
      - Tier 2 (verification): weight 1.0

    Args:
        project_dir: Project root directory.
        current_step: Current thesis step (for metadata).
        agent_mean_confidence: Mean agent confidence (from claim-map).

    Returns:
        Calibration result dict.
    """
    tier1 = _scan_fact_checker_logs(project_dir)
    tier2 = _scan_verification_logs(project_dir)

    tier1_scores = [s["score"] for s in tier1]
    tier2_scores = [s["score"] for s in tier2]

    # Compute per-tier means
    tier1_mean = sum(tier1_scores) / len(tier1_scores) if tier1_scores else None
    tier2_mean = sum(tier2_scores) / len(tier2_scores) if tier2_scores else None

    # Compute per-tier deltas (agent_mean - ground_truth)
    tier1_delta = agent_mean_confidence - tier1_mean if tier1_mean is not None else None
    tier2_delta = agent_mean_confidence - tier2_mean if tier2_mean is not None else None

    # Weighted combination
    if tier1_delta is not None and tier2_delta is not None:
        cal_delta = (tier1_delta * 2.0 + tier2_delta * 1.0) / 3.0
    elif tier1_delta is not None:
        cal_delta = tier1_delta
    elif tier2_delta is not None:
        cal_delta = tier2_delta
    else:
        cal_delta = 0.0  # No calibration data → no adjustment

    # B-1: Clamp cal_delta to [-20, +20] — extreme values indicate data issues
    if cal_delta > 20.0:
        print(
            f"[pccs_calibration] WARNING: cal_delta={cal_delta:.1f} clamped to 20.0 "
            f"(extreme overconfidence — check ground truth data)",
            file=sys.stderr,
        )
        cal_delta = 20.0
    elif cal_delta < -20.0:
        print(
            f"[pccs_calibration] WARNING: cal_delta={cal_delta:.1f} clamped to -20.0 "
            f"(extreme underconfidence — check ground truth data)",
            file=sys.stderr,
        )
        cal_delta = -20.0

    return {
        "cal_delta": round(cal_delta, 1),
        "tier1_samples": len(tier1),
        "tier2_samples": len(tier2),
        "total_samples": len(tier1) + len(tier2),
        "tier1_delta": round(tier1_delta, 1) if tier1_delta is not None else None,
        "tier2_delta": round(tier2_delta, 1) if tier2_delta is not None else None,
        "agent_mean_confidence": agent_mean_confidence,
        "computed_at_step": current_step,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="pCCS Calibration Delta Computation"
    )
    parser.add_argument(
        "--project-dir", required=True,
        help="Project root directory"
    )
    parser.add_argument(
        "--step", type=int, required=True,
        help="Current thesis step"
    )
    parser.add_argument(
        "--agent-mean", type=float, default=85.0,
        help="Mean agent confidence from claim-map (default: 85.0)"
    )
    parser.add_argument(
        "--output",
        help="Output JSON file path (default: stdout)"
    )
    args = parser.parse_args()

    result = compute_calibration(args.project_dir, args.step, args.agent_mean)

    json_str = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        out_dir = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(out_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(
            f"[pccs_calibration] delta={result['cal_delta']}, "
            f"tier1={result['tier1_samples']}, tier2={result['tier2_samples']} → {args.output}"
        )
    else:
        print(json_str)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[pccs_calibration] FATAL: {e}", file=sys.stderr)
        sys.exit(0)  # P1: never block
