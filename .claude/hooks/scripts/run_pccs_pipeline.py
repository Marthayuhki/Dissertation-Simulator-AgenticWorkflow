#!/usr/bin/env python3
"""run_pccs_pipeline.py — P1 Pipeline Runner for pCCS Scoring.

Eliminates hallucination risk in pCCS pipeline execution by replacing
8-10 individual CLI commands with deterministic orchestration.

The Orchestrator previously had to remember and execute the correct sequence
of Phase A → Calibration → B-1 → C-1 → B-2 → C-2 → D → PC1-6 → SOT
commands in the right order — ~500 hallucination-prone CLI calls across a
full 88-step Tier A thesis run. This script reduces that to 1 call (DEGRADED)
or 3 calls (FULL).

Modes:
  DEGRADED: Single invocation — Phase A → Calibration → Phase D → PC1-PC6 → SOT
            For routine Tier A steps. P1-only scoring, no LLM semantic evaluation.

  FULL:     3 invocations bracketing 2 LLM sub-agent calls:
            1. prepare   — Phase A + Calibration → claim-map.json
               [Orchestrator calls @claim-quality-evaluator, saves response]
            2. after-b1  — Extract + Validate evaluator output (CA1-CA8)
               [Orchestrator calls @claim-quality-critic, saves response]
            3. finalize  — Extract + Validate critic (CA1-CA5) → Phase D → PC1-PC6 → SOT

Usage:
  # DEGRADED (single call — replaces 4 bash commands):
  python3 run_pccs_pipeline.py --mode degraded \\
    --file output.md --step 42 --project-dir thesis-output/my-thesis

  # FULL mode (3 calls bracketing 2 LLM calls):
  python3 run_pccs_pipeline.py --mode full --phase prepare \\
    --file output.md --step 42 --project-dir thesis-output/my-thesis \\
    --work-dir /tmp/pccs-42

  python3 run_pccs_pipeline.py --mode full --phase after-b1 \\
    --work-dir /tmp/pccs-42 --b1-response /tmp/b1-response.txt

  python3 run_pccs_pipeline.py --mode full --phase finalize \\
    --work-dir /tmp/pccs-42 --b2-response /tmp/b2-response.txt \\
    --project-dir thesis-output/my-thesis

Exit codes:
  0 — always (P1 compliant, non-blocking)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from typing import Any

# Add script directory to path for shared library import
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from compute_pccs_signals import compute_claim_map  # noqa: E402
from extract_json_block import extract_json_block  # noqa: E402
from generate_pccs_report import generate_report  # noqa: E402
from pccs_calibration import compute_calibration  # noqa: E402
from validate_pccs_assessment import validate_assessment  # noqa: E402
from validate_pccs_output import validate_pccs_report  # noqa: E402


# =============================================================================
# File I/O Helpers
# =============================================================================

def _write_json(path: str, data: dict[str, Any]) -> None:
    """Write JSON to file, creating parent dirs as needed."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _read_json(path: str) -> dict[str, Any] | None:
    """Read JSON file, returning None on failure."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _read_text(path: str) -> str | None:
    """Read text file, returning None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (IOError, OSError):
        return None


# =============================================================================
# SOT Update (subprocess — isolated write to thesis SOT)
# =============================================================================

def _update_sot(
    project_dir: str,
    report_path: str | None = None,
    cal_path: str | None = None,
) -> bool:
    """Update thesis SOT via checklist_manager.py subprocess.

    Uses subprocess to maintain write isolation — checklist_manager.py
    handles the read-modify-write cycle with proper SOT locking.
    """
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "checklist_manager.py"),
        "--update-pccs-cal",
        "--project-dir", project_dir,
    ]
    if report_path:
        cmd.extend(["--pccs-report", report_path])
    if cal_path:
        cmd.extend(["--pccs-cal", cal_path])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(
                f"[run_pccs_pipeline] SOT update warning: {result.stderr.strip()}",
                file=sys.stderr,
            )
            return False
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        print(f"[run_pccs_pipeline] SOT update error: {e}", file=sys.stderr)
        return False


# =============================================================================
# DEGRADED Pipeline — Single Invocation
# =============================================================================

def run_degraded(
    file_path: str,
    step: int,
    project_dir: str,
    output_path: str | None = None,
    work_dir: str | None = None,
) -> dict[str, Any]:
    """Run complete DEGRADED pipeline: A → Calibration → D → PC1-PC6 → SOT.

    Single invocation replaces 4 separate CLI commands. Zero LLM involvement.
    Calibration is always computed — fixing the disconnected calibration loop bug.

    Args:
        file_path: Thesis output .md file to analyze.
        step: Thesis workflow step number.
        project_dir: Thesis project directory (for calibration data + SOT).
        output_path: Final report path (default: work_dir/pccs-report.json).
        work_dir: Work directory for intermediate files (default: tempdir).

    Returns:
        The final pCCS report dict.
    """
    if not work_dir:
        work_dir = tempfile.mkdtemp(prefix=f"pccs-{step}-")
    else:
        os.makedirs(work_dir, exist_ok=True)

    # Phase A: P1 signal extraction
    claim_map = compute_claim_map(file_path, step)
    claim_map_path = os.path.join(work_dir, "claim-map.json")
    _write_json(claim_map_path, claim_map)
    n_claims = claim_map.get("total_claims", 0)
    print(f"[run_pccs_pipeline] Phase A: {n_claims} claims extracted")

    # Calibration: compute cal_delta from ground truth (CRITICAL FIX)
    cal_result = compute_calibration(project_dir, step)
    cal_path = os.path.join(work_dir, "pccs-calibration.json")
    _write_json(cal_path, cal_result)
    print(
        f"[run_pccs_pipeline] Calibration: delta={cal_result['cal_delta']}, "
        f"samples={cal_result['total_samples']}"
    )

    # Phase D: P1 synthesis (with calibration data)
    report = generate_report(
        claim_map_path=claim_map_path,
        calibration_path=cal_path,
    )
    report["mode"] = "DEGRADED"
    report_path = output_path or os.path.join(work_dir, "pccs-report.json")
    _write_json(report_path, report)

    # PC1-PC6 structural validation
    validation = validate_pccs_report(report)
    val_path = os.path.join(work_dir, "pccs-validation.json")
    _write_json(val_path, validation)
    checks_str = ", ".join(
        f"{c['id']}:{'OK' if c['passed'] else 'FAIL'}" for c in validation["checks"]
    )
    print(
        f"[run_pccs_pipeline] PC1-PC7: "
        f"{'PASS' if validation['passed'] else 'FAIL'} — {checks_str}"
    )

    # SOT update (with both calibration and report)
    sot_updated = _update_sot(project_dir, report_path, cal_path)

    s = report.get("summary", {})
    d = report.get("decision", {})
    print(
        f"[run_pccs_pipeline] DEGRADED complete: "
        f"{s.get('total_claims', 0)} claims, mean={s.get('mean_pccs', 0)}, "
        f"G={s.get('green', 0)}/Y={s.get('yellow', 0)}/R={s.get('red', 0)}, "
        f"action={d.get('action', '?')}, sot_updated={sot_updated}"
    )

    report["sot_updated"] = sot_updated

    # A-2: Flag empty claim_map for Orchestrator retry
    if n_claims == 0:
        report["retry_required"] = True
        report["retry_reason"] = "Phase A extracted 0 claims — file may be empty or malformed"
        print(
            "[run_pccs_pipeline] WARNING: 0 claims extracted — retry_required=True",
            file=sys.stderr,
        )

    return report


# =============================================================================
# FULL Pipeline — 3 Phases
# =============================================================================

def run_full_prepare(
    file_path: str,
    step: int,
    project_dir: str,
    work_dir: str,
) -> dict[str, Any]:
    """FULL mode Phase 1: Prepare — Phase A + Calibration.

    Creates work directory with claim-map.json and calibration data.
    Orchestrator then calls @claim-quality-evaluator with claim-map.json path.

    Returns:
        {"claim_map_path": str, "claims": int}
    """
    os.makedirs(work_dir, exist_ok=True)

    # Phase A: P1 signal extraction
    claim_map = compute_claim_map(file_path, step)
    claim_map_path = os.path.join(work_dir, "claim-map.json")
    _write_json(claim_map_path, claim_map)
    n_claims = claim_map.get("total_claims", 0)

    # Calibration
    cal_result = compute_calibration(project_dir, step)
    cal_path = os.path.join(work_dir, "pccs-calibration.json")
    _write_json(cal_path, cal_result)

    # Save pipeline metadata for later phases
    meta = {
        "step": step,
        "file": file_path,
        "project_dir": project_dir,
        "total_claims": n_claims,
        "cal_delta": cal_result["cal_delta"],
    }
    _write_json(os.path.join(work_dir, "_pipeline-meta.json"), meta)

    print(
        f"[run_pccs_pipeline] FULL prepare: {n_claims} claims, "
        f"cal_delta={cal_result['cal_delta']} → {work_dir}"
    )

    return {"claim_map_path": claim_map_path, "claims": n_claims}


def run_full_after_b1(
    work_dir: str,
    b1_response_path: str,
) -> dict[str, Any]:
    """FULL mode Phase 2: After B-1 — Extract + Validate evaluator output.

    Extracts JSON from @claim-quality-evaluator response text,
    validates with CA1-CA8, saves pccs-assessment.json.
    Orchestrator then calls @claim-quality-critic.

    Returns:
        {"assessment_path": str, "validation_passed": bool}
    """
    claim_map_path = os.path.join(work_dir, "claim-map.json")
    claim_map = _read_json(claim_map_path)
    assessment_path = os.path.join(work_dir, "pccs-assessment.json")

    # Extract JSON from B-1 response
    b1_extraction_failed = False
    b1_text = _read_text(b1_response_path)
    if b1_text:
        extracted = extract_json_block(b1_text)
        if extracted:
            _write_json(assessment_path, extracted)
            print(f"[run_pccs_pipeline] B-1 JSON extracted → pccs-assessment.json")
        else:
            b1_extraction_failed = True
            _write_json(assessment_path, {
                "assessments": [],
                "_extraction_failed": True,
                "_reason": "JSON extraction from evaluator response failed",
            })
            print(
                "[run_pccs_pipeline] B-1 extraction FAILED — "
                "Orchestrator MUST retry @claim-quality-evaluator",
                file=sys.stderr,
            )
    else:
        b1_extraction_failed = True
        _write_json(assessment_path, {
            "assessments": [],
            "_extraction_failed": True,
            "_reason": f"B-1 response not readable: {b1_response_path}",
        })
        print(
            f"[run_pccs_pipeline] B-1 response not readable: {b1_response_path}",
            file=sys.stderr,
        )

    # Validate evaluator output (CA1-CA8)
    validation_passed = True
    assessment = _read_json(assessment_path) or {"assessments": []}
    if claim_map:
        val_result = validate_assessment(assessment, claim_map, "evaluator")
        val_path = os.path.join(work_dir, "pccs-assessment-validation.json")
        _write_json(val_path, val_result)
        validation_passed = val_result["passed"]
        checks_str = ", ".join(
            f"{c['id']}:{'OK' if c['passed'] else 'FAIL'}"
            for c in val_result["checks"]
        )
        print(
            f"[run_pccs_pipeline] CA1-CA8 (evaluator): "
            f"{'PASS' if validation_passed else 'FAIL'} — {checks_str}"
        )
    else:
        print(
            "[run_pccs_pipeline] WARNING: claim-map not found for CA validation",
            file=sys.stderr,
        )

    result: dict[str, Any] = {
        "assessment_path": assessment_path,
        "validation_passed": validation_passed,
        "extraction_failed": b1_extraction_failed,
    }

    # A-2: Flag extraction failure for Orchestrator retry
    if b1_extraction_failed:
        result["retry_required"] = True
        result["retry_reason"] = "B-1 JSON extraction failed — Orchestrator MUST retry @claim-quality-evaluator"

    return result


def run_full_finalize(
    work_dir: str,
    b2_response_path: str,
    project_dir: str,
    output_path: str | None = None,
) -> dict[str, Any]:
    """FULL mode Phase 3: Finalize — Critic + Phase D + PC1-PC6 + SOT.

    Extracts JSON from @claim-quality-critic response, validates (CA1-CA5),
    runs Phase D synthesis with all inputs, validates report (PC1-PC6),
    and updates thesis SOT.

    Returns:
        The final pCCS report dict.
    """
    claim_map_path = os.path.join(work_dir, "claim-map.json")
    assessment_path = os.path.join(work_dir, "pccs-assessment.json")
    cal_path = os.path.join(work_dir, "pccs-calibration.json")
    claim_map = _read_json(claim_map_path)

    # Extract JSON from B-2 response
    b2_text = _read_text(b2_response_path)
    critic_path = os.path.join(work_dir, "pccs-critic.json")
    b2_extraction_failed = False
    if b2_text:
        extracted = extract_json_block(b2_text)
        if extracted:
            _write_json(critic_path, extracted)
            print(f"[run_pccs_pipeline] B-2 JSON extracted → pccs-critic.json")
        else:
            b2_extraction_failed = True
            _write_json(critic_path, {
                "judgments": [], "additions": [],
                "_extraction_failed": True,
                "_reason": "JSON extraction from critic response failed",
            })
            print(
                "[run_pccs_pipeline] B-2 extraction FAILED — "
                "proceeding with P1-only scoring (DEGRADED fallback)",
                file=sys.stderr,
            )
    else:
        b2_extraction_failed = True
        _write_json(critic_path, {
            "judgments": [], "additions": [],
            "_extraction_failed": True,
            "_reason": f"B-2 response not readable: {b2_response_path}",
        })
        print(
            f"[run_pccs_pipeline] B-2 response not readable: {b2_response_path}",
            file=sys.stderr,
        )

    # Validate critic output (CA1-CA5)
    critic = _read_json(critic_path) or {"judgments": [], "additions": []}
    if claim_map:
        val_result = validate_assessment(critic, claim_map, "critic")
        val_path = os.path.join(work_dir, "pccs-critic-validation.json")
        _write_json(val_path, val_result)
        checks_str = ", ".join(
            f"{c['id']}:{'OK' if c['passed'] else 'FAIL'}"
            for c in val_result["checks"]
        )
        print(
            f"[run_pccs_pipeline] CA1-CA5 (critic): "
            f"{'PASS' if val_result['passed'] else 'FAIL'} — {checks_str}"
        )

    # Phase D: P1 synthesis with ALL available inputs
    report = generate_report(
        claim_map_path=claim_map_path,
        assessment_path=assessment_path if os.path.exists(assessment_path) else None,
        critic_path=critic_path if os.path.exists(critic_path) else None,
        calibration_path=cal_path if os.path.exists(cal_path) else None,
    )
    report["mode"] = "FULL"
    report_path = output_path or os.path.join(work_dir, "pccs-report.json")
    _write_json(report_path, report)

    # PC1-PC7 structural validation
    validation = validate_pccs_report(report)
    val_path = os.path.join(work_dir, "pccs-validation.json")
    _write_json(val_path, validation)
    checks_str = ", ".join(
        f"{c['id']}:{'OK' if c['passed'] else 'FAIL'}" for c in validation["checks"]
    )
    print(
        f"[run_pccs_pipeline] PC1-PC7: "
        f"{'PASS' if validation['passed'] else 'FAIL'} — {checks_str}"
    )

    # SOT update (with both calibration and report)
    sot_updated = _update_sot(project_dir, report_path, cal_path)

    s = report.get("summary", {})
    d = report.get("decision", {})
    print(
        f"[run_pccs_pipeline] FULL finalize: "
        f"{s.get('total_claims', 0)} claims, mean={s.get('mean_pccs', 0)}, "
        f"G={s.get('green', 0)}/Y={s.get('yellow', 0)}/R={s.get('red', 0)}, "
        f"action={d.get('action', '?')}, sot_updated={sot_updated}"
    )

    report["sot_updated"] = sot_updated
    return report


# =============================================================================
# CLI
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="pCCS P1 Pipeline Runner — eliminates hallucination risk in pipeline execution"
    )
    parser.add_argument(
        "--mode", required=True, choices=["degraded", "full"],
        help="Pipeline mode: degraded (A→D) or full (A→B1→C1→B2→C2→D)",
    )
    parser.add_argument(
        "--phase", choices=["prepare", "after-b1", "finalize"],
        help="FULL mode phase (required when --mode full)",
    )
    parser.add_argument("--file", help="Thesis output file (.md) to analyze")
    parser.add_argument("--step", type=int, help="Thesis workflow step number")
    parser.add_argument(
        "--project-dir",
        help="Thesis project directory (for calibration + SOT update)",
    )
    parser.add_argument(
        "--work-dir",
        help="Work directory for intermediate files",
    )
    parser.add_argument(
        "--b1-response",
        help="B-1 evaluator response text file (FULL after-b1 phase)",
    )
    parser.add_argument(
        "--b2-response",
        help="B-2 critic response text file (FULL finalize phase)",
    )
    parser.add_argument(
        "--output",
        help="Output report JSON path (default: work-dir/pccs-report.json)",
    )
    args = parser.parse_args()

    if args.mode == "degraded":
        if not args.file or args.step is None or not args.project_dir:
            parser.error("DEGRADED mode requires --file, --step, --project-dir")
        run_degraded(
            args.file, args.step, args.project_dir,
            output_path=args.output, work_dir=args.work_dir,
        )

    elif args.mode == "full":
        if not args.phase:
            parser.error("FULL mode requires --phase")

        if args.phase == "prepare":
            if not args.file or args.step is None or not args.project_dir or not args.work_dir:
                parser.error("prepare requires --file, --step, --project-dir, --work-dir")
            run_full_prepare(args.file, args.step, args.project_dir, args.work_dir)

        elif args.phase == "after-b1":
            if not args.work_dir or not args.b1_response:
                parser.error("after-b1 requires --work-dir, --b1-response")
            run_full_after_b1(args.work_dir, args.b1_response)

        elif args.phase == "finalize":
            if not args.work_dir or not args.b2_response or not args.project_dir:
                parser.error("finalize requires --work-dir, --b2-response, --project-dir")
            run_full_finalize(
                args.work_dir, args.b2_response, args.project_dir,
                output_path=args.output,
            )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[run_pccs_pipeline] FATAL: {e}", file=sys.stderr)
        sys.exit(0)  # P1: never block
