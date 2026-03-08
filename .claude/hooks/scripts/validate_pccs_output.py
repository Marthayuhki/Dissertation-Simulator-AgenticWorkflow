#!/usr/bin/env python3
"""validate_pccs_output.py — PC1-PC7 Structural Validation for pCCS Reports.

P1 deterministic validation of pCCS report structure and score integrity.
Run after generate_pccs_report.py (Phase D) to verify output correctness.

Checks:
  PC1: Required fields present (step, file, summary, decision, claims, pcae)
  PC2: Score ranges valid (0 <= pccs <= 100, 0 <= p1_score <= 100)
  PC3: Color classification correct (GREEN >= 70, YELLOW >= 50, RED < 50)
  PC4: Decision matrix consistent with RED count
  PC5: Summary counts match actual claim colors
  PC6: Claim IDs unique (no duplicates)
  PC7: Mode field valid (FULL or DEGRADED) if present

Usage:
  python3 validate_pccs_output.py --report pccs-report.json
  python3 validate_pccs_output.py --report pccs-report.json --output validation.json

Exit codes:
  0 — always (P1 compliant, non-blocking)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def validate_pccs_report(report: dict[str, Any]) -> dict[str, Any]:
    """Validate pCCS report structure and score integrity.

    Returns:
        {"passed": bool, "checks": [...], "errors": [...], "warnings": [...]}
    """
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    # PC1: Required fields
    required_top = {"step", "file", "summary", "decision", "claims", "pcae"}
    missing = required_top - set(report.keys())
    pc1_pass = len(missing) == 0
    checks.append({"id": "PC1", "name": "Required fields", "passed": pc1_pass})
    if not pc1_pass:
        errors.append(f"PC1: Missing top-level fields: {sorted(missing)}")

    claims = report.get("claims", [])
    summary = report.get("summary", {})
    decision = report.get("decision", {})

    # PC2: Score ranges
    pc2_pass = True
    for c in claims:
        pccs = c.get("pccs", -1)
        p1 = c.get("p1_score", -1)
        cid = c.get("claim_id", "?")
        if not (0 <= pccs <= 100):
            errors.append(f"PC2: {cid} pccs={pccs} out of [0,100]")
            pc2_pass = False
        if not (0 <= p1 <= 100):
            errors.append(f"PC2: {cid} p1_score={p1} out of [0,100]")
            pc2_pass = False
    checks.append({"id": "PC2", "name": "Score ranges", "passed": pc2_pass})

    # PC3: Color classification
    pc3_pass = True
    for c in claims:
        pccs = c.get("pccs", 0)
        color = c.get("color", "")
        cid = c.get("claim_id", "?")
        expected = "GREEN" if pccs >= 70 else ("YELLOW" if pccs >= 50 else "RED")
        if color != expected:
            errors.append(f"PC3: {cid} pccs={pccs} color={color}, expected={expected}")
            pc3_pass = False
    checks.append({"id": "PC3", "name": "Color classification", "passed": pc3_pass})

    # PC4: Decision matrix consistency
    pc4_pass = True
    action = decision.get("action", "")
    red_ids = decision.get("red_claim_ids", [])
    # Count actionable reds
    actual_reds = []
    for c in claims:
        pccs = c.get("pccs", 0)
        ct = c.get("canonical_type", "UNKNOWN")
        if ct == "SPECULATIVE" and pccs < 40:
            actual_reds.append(c.get("claim_id"))
        elif ct != "SPECULATIVE" and pccs < 50:
            actual_reds.append(c.get("claim_id"))
    if len(actual_reds) == 0 and action != "proceed":
        errors.append(f"PC4: 0 actionable reds but action={action}, expected=proceed")
        pc4_pass = False
    elif 1 <= len(actual_reds) <= 2 and action != "rewrite_claims":
        errors.append(f"PC4: {len(actual_reds)} reds but action={action}, expected=rewrite_claims")
        pc4_pass = False
    elif len(actual_reds) >= 3 and action != "rewrite_step":
        errors.append(f"PC4: {len(actual_reds)} reds but action={action}, expected=rewrite_step")
        pc4_pass = False
    checks.append({"id": "PC4", "name": "Decision consistency", "passed": pc4_pass})

    # PC5: Summary counts
    pc5_pass = True
    actual_green = sum(1 for c in claims if c.get("color") == "GREEN")
    actual_yellow = sum(1 for c in claims if c.get("color") == "YELLOW")
    actual_red = sum(1 for c in claims if c.get("color") == "RED")
    if summary.get("green") != actual_green:
        errors.append(f"PC5: summary.green={summary.get('green')} != actual={actual_green}")
        pc5_pass = False
    if summary.get("yellow") != actual_yellow:
        errors.append(f"PC5: summary.yellow={summary.get('yellow')} != actual={actual_yellow}")
        pc5_pass = False
    if summary.get("red") != actual_red:
        errors.append(f"PC5: summary.red={summary.get('red')} != actual={actual_red}")
        pc5_pass = False
    if summary.get("total_claims") != len(claims):
        errors.append(f"PC5: summary.total={summary.get('total_claims')} != actual={len(claims)}")
        pc5_pass = False
    checks.append({"id": "PC5", "name": "Summary counts", "passed": pc5_pass})

    # PC6: Unique claim IDs
    pc6_pass = True
    seen_ids: set[str] = set()
    for c in claims:
        cid = c.get("claim_id", "")
        if cid in seen_ids:
            errors.append(f"PC6: Duplicate claim_id: {cid}")
            pc6_pass = False
        seen_ids.add(cid)
    checks.append({"id": "PC6", "name": "Unique claim IDs", "passed": pc6_pass})

    # PC7: Mode field valid (if present)
    pc7_pass = True
    mode = report.get("mode")
    if mode is not None and mode not in ("FULL", "DEGRADED"):
        errors.append(f"PC7: mode='{mode}' invalid (expected FULL or DEGRADED)")
        pc7_pass = False
    checks.append({"id": "PC7", "name": "Mode valid", "passed": pc7_pass})

    return {
        "passed": len(errors) == 0,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="pCCS PC1-PC6 Structural Validation"
    )
    parser.add_argument(
        "--report", required=True,
        help="pCCS report JSON to validate"
    )
    parser.add_argument(
        "--output",
        help="Output validation JSON (default: stdout)"
    )
    args = parser.parse_args()

    if not os.path.exists(args.report):
        result = {
            "passed": False,
            "checks": [],
            "errors": [f"Report file not found: {args.report}"],
            "warnings": [],
        }
    else:
        try:
            with open(args.report, "r", encoding="utf-8") as f:
                report = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            result = {
                "passed": False,
                "checks": [],
                "errors": [f"Failed to load report: {e}"],
                "warnings": [],
            }
        else:
            result = validate_pccs_report(report)

    json_str = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        out_dir = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(out_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)

    status = "PASS" if result["passed"] else "FAIL"
    checks_str = ", ".join(
        f"{c['id']}:{'OK' if c['passed'] else 'FAIL'}" for c in result["checks"]
    )
    print(f"[validate_pccs_output] {status} — {checks_str}")

    if result["errors"]:
        for e in result["errors"]:
            print(f"  ERROR: {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[validate_pccs_output] FATAL: {e}", file=sys.stderr)
    sys.exit(0)  # P1: never block
