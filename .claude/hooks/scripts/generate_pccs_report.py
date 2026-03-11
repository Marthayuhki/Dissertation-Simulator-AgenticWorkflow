#!/usr/bin/env python3
"""generate_pccs_report.py — Phase D: P1 Synthesis (pCCS Score Computation).

Fuses P1 ground truth (Phase A), LLM evaluation (Phase B-1/B-2), and
calibration data into final per-claim pCCS scores. ALL computation is P1
(deterministic Python) — zero LLM involvement in the score calculation.

This is the final phase of the pCCS P1 Sandwich pipeline:
  Phase A (P1) → Phase B-1 (LLM) → Phase C-1 (P1) → Phase B-2 (LLM) →
  Phase C-2 (P1) → Phase D (this — P1 synthesis)

Inputs:
  --claim-map      claim-map.json from Phase A
  --assessment     pccs-assessment.json from Phase B-1 (LLM) → C-1 (P1 validated)
  --critic         pccs-critic.json from Phase B-2 (LLM) → C-2 (P1 validated)
  --calibration    pccs-calibration.json (optional, from pccs_calibration.py)

Output: pccs-report.json
  {
    "step": N,
    "file": "output.md",
    "summary": {
      "total_claims": N,
      "green": N,     // pCCS >= 70
      "yellow": N,    // 50 <= pCCS < 70
      "red": N,       // pCCS < 50
      "mean_pccs": 78.5
    },
    "decision": {
      "action": "proceed" | "rewrite_claims" | "rewrite_step",
      "red_claim_ids": []
    },
    "claims": [
      {
        "claim_id": "EMP-001",
        "canonical_type": "EMPIRICAL",
        "p1_score": 85.0,
        "raw_agent": 90,
        "llm_assessment": 80,
        "cal_delta": 5.0,
        "blocked": false,
        "pccs": 82.3,
        "color": "GREEN"
      }, ...
    ],
    "pcae": {  // predicted Claim Alignment Error
      "e1_numeric_contradictions": [],
      "e2_duplicate_claims": [],
      "e3_source_conflicts": []
    }
  }

Exit codes:
  0 — always (P1 compliant, non-blocking)

Usage:
  python3 generate_pccs_report.py \\
    --claim-map claim-map.json \\
    --output pccs-report.json

  python3 generate_pccs_report.py \\
    --claim-map claim-map.json \\
    --assessment pccs-assessment.json \\
    --critic pccs-critic.json \\
    --calibration pccs-calibration.json \\
    --output pccs-report.json
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


# =============================================================================
# pCCS Weight Tables — claim-type adaptive
# =============================================================================

# P1 vs agent weighting by canonical claim type.
# FACTUAL: P1 signals are very reliable → high P1 weight.
# SPECULATIVE: P1 signals are weak (no citations expected) → low P1 weight.
WEIGHTS: dict[str, dict[str, float]] = {
    "FACTUAL":       {"p1": 0.50, "agent": 0.50},
    "EMPIRICAL":     {"p1": 0.45, "agent": 0.55},
    "THEORETICAL":   {"p1": 0.25, "agent": 0.75},
    "METHODOLOGICAL": {"p1": 0.35, "agent": 0.65},
    "INTERPRETIVE":  {"p1": 0.20, "agent": 0.80},
    "SPECULATIVE":   {"p1": 0.15, "agent": 0.85},
    "UNKNOWN":       {"p1": 0.35, "agent": 0.65},
}

# Maximum confidence by claim type (ceiling clamp).
# Prevents over-confident scores for inherently uncertain claim types.
CONFIDENCE_CEILING: dict[str, int] = {
    "FACTUAL": 95,
    "EMPIRICAL": 85,
    "THEORETICAL": 75,
    "METHODOLOGICAL": 80,
    "INTERPRETIVE": 70,
    "SPECULATIVE": 60,
    "UNKNOWN": 80,
}

# Color thresholds
_GREEN_THRESHOLD = 70
_YELLOW_THRESHOLD = 50  # 50 <= pCCS < 70

# Blocked pattern hard ceiling
_BLOCKED_CEILING = 40.0


# =============================================================================
# pCCS Fusion Formula
# =============================================================================

def compute_pccs(
    claim_type: str,
    p1_score: float,
    raw_agent: int,
    cal_delta: float,
    blocked: bool,
) -> float:
    """Compute the final pCCS score for a single claim.

    Formula:
      calibrated = min(raw_agent - cal_delta, CEILING[type])
      pccs_raw = p1_score * w_p1 + calibrated * w_agent
      if blocked: pccs_raw = min(pccs_raw, 40.0)
      pccs = clamp(pccs_raw, 0, 100)

    All inputs are P1-produced or pre-validated constants.
    """
    w = WEIGHTS.get(claim_type, WEIGHTS["UNKNOWN"])
    ceiling = CONFIDENCE_CEILING.get(claim_type, CONFIDENCE_CEILING["UNKNOWN"])

    calibrated = min(raw_agent - cal_delta, ceiling)
    pccs_raw = p1_score * w["p1"] + calibrated * w["agent"]

    if blocked:
        pccs_raw = min(pccs_raw, _BLOCKED_CEILING)

    return round(max(0.0, min(100.0, pccs_raw)), 1)


def classify_color(pccs: float) -> str:
    """Classify pCCS into GREEN/YELLOW/RED."""
    if pccs >= _GREEN_THRESHOLD:
        return "GREEN"
    elif pccs >= _YELLOW_THRESHOLD:
        return "YELLOW"
    else:
        return "RED"


# =============================================================================
# Decision Matrix
# =============================================================================

def compute_decision(claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the Orchestrator decision based on pCCS scores.

    Rules:
      - RED = pCCS < 50 (non-SPECULATIVE) OR pCCS < 40 (SPECULATIVE)
      - 0 actionable RED → proceed
      - 1-2 actionable RED → rewrite_claims (specific claims only)
      - 3+ actionable RED → rewrite_step (entire step)

    Returns:
        {"action": str, "red_claim_ids": list[str]}
    """
    red_claims: list[dict[str, Any]] = []
    for c in claims:
        pccs = c.get("pccs", 0)
        ct = c.get("canonical_type", "UNKNOWN")
        if ct == "SPECULATIVE":
            if pccs < 40:
                red_claims.append(c)
        else:
            if pccs < _YELLOW_THRESHOLD:
                red_claims.append(c)

    red_ids = [c["claim_id"] for c in red_claims]

    if len(red_claims) == 0:
        return {"action": "proceed", "red_claim_ids": []}
    elif len(red_claims) <= 2:
        return {"action": "rewrite_claims", "red_claim_ids": red_ids}
    else:
        return {"action": "rewrite_step", "red_claim_ids": red_ids}


# =============================================================================
# pCAE — predicted Claim Alignment Error (inter-claim consistency)
# =============================================================================

def compute_pcae(
    claims: list[dict[str, Any]],
    critic_additions: list[dict[str, Any]] | None = None,
) -> dict[str, list[Any]]:
    """Detect inter-claim inconsistencies (P1 deterministic).

    E1: Numeric contradictions — claims citing conflicting statistics.
    E2: Duplicate detection — claims with same source and similar text.
    E3: Source conflicts — same source cited with different conclusions.
    E4: Critic additions — issues flagged by @claim-quality-critic that
        the evaluator missed. Previously dead data, now surfaced.
    """
    e1: list[dict[str, str]] = []
    e2: list[dict[str, str]] = []
    e3: list[dict[str, str]] = []
    e4: list[dict[str, Any]] = critic_additions or []

    # Build source index for E2/E3
    source_index: dict[str, list[str]] = {}
    for c in claims:
        src = c.get("source_text", "").strip()
        if src:
            # Normalize: lowercase, strip punctuation
            key = re.sub(r'[^\w\s]', '', src.lower())[:100]
            source_index.setdefault(key, []).append(c["claim_id"])

    # E2: Duplicate detection — same source cited by multiple claims
    for key, ids in source_index.items():
        if len(ids) > 1:
            e2.append({
                "claim_ids": ids,
                "source_key": key[:60],
                "note": "Multiple claims reference the same source — verify distinct contributions.",
            })

    return {
        "e1_numeric_contradictions": e1,
        "e1_status": "not_implemented",
        "e2_duplicate_claims": e2,
        "e3_source_conflicts": e3,
        "e3_status": "not_implemented",
        "e4_critic_additions": e4,
    }


# =============================================================================
# Report Generation
# =============================================================================

def _load_json(path: str | None) -> dict[str, Any] | None:
    """Load a JSON file, returning None on failure."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _get_llm_score(
    claim_id: str,
    assessment: dict[str, Any] | None,
    critic: dict[str, Any] | None,
) -> int | None:
    """Extract LLM assessment score for a claim.

    Merges evaluator (B-1) and critic (B-2) scores:
    - If both available: average
    - If only evaluator: use evaluator
    - If neither: None (fallback to raw_agent)
    """
    eval_score: int | None = None
    critic_score: int | None = None

    if assessment:
        for a in assessment.get("assessments", []):
            if a.get("claim_id") == claim_id:
                eval_score = a.get("quality_score")
                break

    if critic:
        for j in critic.get("judgments", []):
            if j.get("claim_id") == claim_id:
                critic_score = j.get("adjusted_score")
                break

    if eval_score is not None and critic_score is not None:
        return round((eval_score + critic_score) / 2)
    elif eval_score is not None:
        return eval_score
    elif critic_score is not None:
        return critic_score
    return None


def _check_disagreement(
    claim_id: str,
    assessment: dict[str, Any] | None,
    critic: dict[str, Any] | None,
) -> bool:
    """Check if evaluator and critic scores disagree significantly (|diff| >= 20)."""
    eval_score: int | None = None
    critic_score: int | None = None

    if assessment:
        for a in assessment.get("assessments", []):
            if a.get("claim_id") == claim_id:
                eval_score = a.get("quality_score")
                break

    if critic:
        for j in critic.get("judgments", []):
            if j.get("claim_id") == claim_id:
                critic_score = j.get("adjusted_score")
                break

    if eval_score is not None and critic_score is not None:
        return abs(eval_score - critic_score) >= 20
    return False


def generate_report(
    claim_map_path: str,
    assessment_path: str | None = None,
    critic_path: str | None = None,
    calibration_path: str | None = None,
) -> dict[str, Any]:
    """Generate the full pCCS report.

    Fuses Phase A (P1), Phase B-1/B-2 (LLM), and calibration data.
    All arithmetic is P1 (this function) — LLM outputs are pre-validated inputs.
    """
    claim_map = _load_json(claim_map_path)
    if not claim_map:
        return {
            "step": -1,
            "file": "",
            "mode": "ERROR",
            "summary": {"total_claims": 0, "green": 0, "yellow": 0, "red": 0, "mean_pccs": 0, "disagreement_count": 0},
            "calibration": {"cal_delta": 0.0, "total_samples": 0},
            "decision": {"action": "rewrite_step", "red_claim_ids": [], "reason": "claim_map_load_failed"},
            "claims": [],
            "pcae": {"e1_numeric_contradictions": [], "e2_duplicate_claims": [], "e3_source_conflicts": [], "e4_critic_additions": []},
            "error": f"Failed to load claim-map: {claim_map_path}",
        }

    # Guard: empty claim-map → force rewrite_step (prevents silent bypass)
    if not claim_map.get("claims"):
        return {
            "step": claim_map.get("step", -1),
            "file": claim_map.get("file", ""),
            "mode": "ERROR",
            "summary": {"total_claims": 0, "green": 0, "yellow": 0, "red": 0, "mean_pccs": 0, "disagreement_count": 0},
            "calibration": {"cal_delta": 0.0, "total_samples": 0},
            "decision": {"action": "rewrite_step", "red_claim_ids": [], "reason": "empty_claim_map"},
            "claims": [],
            "pcae": {"e1_numeric_contradictions": [], "e2_duplicate_claims": [], "e3_source_conflicts": [], "e4_critic_additions": []},
            "error": "Claim-map contains 0 claims — step output has no GroundedClaims",
        }

    assessment = _load_json(assessment_path)
    critic = _load_json(critic_path)
    calibration = _load_json(calibration_path)

    # ④ Auto-detect mode: FULL if LLM data provided, DEGRADED otherwise
    has_llm_data = bool(
        (assessment and assessment.get("assessments"))
        or (critic and critic.get("judgments"))
    )
    mode = "FULL" if has_llm_data else "DEGRADED"

    # Get calibration delta (default 0 if no calibration data)
    cal_delta = 0.0
    cal_total_samples = 0
    if calibration:
        cal_delta = calibration.get("cal_delta", 0.0)
        cal_total_samples = calibration.get("total_samples", 0)  # ⑦

    claims_out: list[dict[str, Any]] = []

    for cm in claim_map.get("claims", []):
        claim_id = cm["claim_id"]
        canonical_type = cm.get("canonical_type", "UNKNOWN")
        p1_score = cm.get("p1_score", 50.0)
        raw_agent = cm.get("confidence_numeric", 50)
        blocked = cm.get("p1_signals", {}).get("a3_blocked", False)

        # Get LLM assessment score (may be None if B-1/B-2 not available)
        llm_score = _get_llm_score(claim_id, assessment, critic)

        # ⑥ High disagreement flag (|eval - critic| >= 20)
        high_disagreement = _check_disagreement(claim_id, assessment, critic)

        # Use LLM score if available, otherwise raw_agent confidence
        effective_agent = llm_score if llm_score is not None else raw_agent

        pccs = compute_pccs(canonical_type, p1_score, effective_agent, cal_delta, blocked)
        color = classify_color(pccs)

        claims_out.append({
            "claim_id": claim_id,
            "canonical_type": canonical_type,
            "p1_score": p1_score,
            "raw_agent": raw_agent,
            "llm_assessment": llm_score,
            "cal_delta": cal_delta,
            "blocked": blocked,
            "pccs": pccs,
            "color": color,
            "high_disagreement": high_disagreement,  # ⑥
        })

    # Summary statistics
    total = len(claims_out)
    green = sum(1 for c in claims_out if c["color"] == "GREEN")
    yellow = sum(1 for c in claims_out if c["color"] == "YELLOW")
    red = sum(1 for c in claims_out if c["color"] == "RED")
    mean_pccs = round(sum(c["pccs"] for c in claims_out) / max(total, 1), 1)
    disagreement_count = sum(1 for c in claims_out if c["high_disagreement"])

    # Decision matrix
    decision = compute_decision(claims_out)

    # ⑤ Extract critic additions (previously dead data)
    critic_additions: list[dict[str, Any]] = []
    if critic:
        critic_additions = critic.get("additions", [])

    # pCAE (with critic additions connected)
    pcae = compute_pcae(claim_map.get("claims", []), critic_additions)

    return {
        "step": claim_map.get("step", -1),
        "file": claim_map.get("file", ""),
        "mode": mode,  # ④
        "summary": {
            "total_claims": total,
            "green": green,
            "yellow": yellow,
            "red": red,
            "mean_pccs": mean_pccs,
            "disagreement_count": disagreement_count,  # ⑥
        },
        "calibration": {  # ⑦
            "cal_delta": cal_delta,
            "total_samples": cal_total_samples,
        },
        "decision": decision,
        "claims": claims_out,
        "pcae": pcae,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="pCCS Phase D: P1 Synthesis — Final Score Computation"
    )
    parser.add_argument(
        "--claim-map", required=True,
        help="claim-map.json from Phase A"
    )
    parser.add_argument(
        "--assessment",
        help="pccs-assessment.json from Phase B-1 → C-1 (optional)"
    )
    parser.add_argument(
        "--critic",
        help="pccs-critic.json from Phase B-2 → C-2 (optional)"
    )
    parser.add_argument(
        "--calibration",
        help="pccs-calibration.json (optional)"
    )
    parser.add_argument(
        "--output",
        help="Output JSON file path (default: stdout)"
    )
    args = parser.parse_args()

    report = generate_report(
        claim_map_path=args.claim_map,
        assessment_path=args.assessment,
        critic_path=args.critic,
        calibration_path=args.calibration,
    )

    json_str = json.dumps(report, indent=2, ensure_ascii=False)

    if args.output:
        out_dir = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(out_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        s = report["summary"]
        d = report["decision"]
        print(
            f"[generate_pccs_report] Phase D complete: "
            f"{s['total_claims']} claims, mean={s['mean_pccs']}, "
            f"G={s['green']}/Y={s['yellow']}/R={s['red']}, "
            f"action={d['action']} → {args.output}"
        )
    else:
        print(json_str)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[generate_pccs_report] FATAL: {e}", file=sys.stderr)
        sys.exit(0)  # P1: never block
