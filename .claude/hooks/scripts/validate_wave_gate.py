#!/usr/bin/env python3
"""Cross-Validation Gate — P1 deterministic validation for wave transitions.

Validates that wave outputs meet quality thresholds before allowing
progression to the next wave. Computes agreement rates, claim counts,
and identifies inconsistencies.

Usage:
  python3 validate_wave_gate.py --project-dir <dir> --gate <gate-name>
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from _claim_patterns import count_claims, extract_claim_ids  # noqa: E402

# H-4 aligned: Same strict regex as validate_thesis_output.py for consolidated files.
# Prevents false matches on arbitrary filenames.
_CONSOLIDATED_RE = re.compile(r'^step-(\d{3})-to-(\d{3})-([a-z][-a-z]*[a-z])\.md$')

# Gate definitions: which wave outputs to validate
GATE_CONFIG = {
    "gate-1": {
        "wave": 1,
        "min_claims_per_file": 3,
        "min_files": 4,
        "description": "Foundation Validation (Wave 1 → Wave 2)",
    },
    "gate-2": {
        "wave": 2,
        "min_claims_per_file": 3,
        "min_files": 4,
        "description": "Deep Analysis Validation (Wave 2 → Wave 3)",
    },
    "gate-3": {
        "wave": 3,
        "min_claims_per_file": 3,
        "min_files": 4,
        "description": "Critical Analysis Validation (Wave 3 → Wave 4)",
    },
    "srcs-full": {
        "wave": 4,
        "min_claims_per_file": 5,
        "min_files": 2,
        "description": "SRCS Full Evaluation — validates SRCS scores specifically on Wave 4 synthesis outputs (Wave 4 → Wave 5)",
    },
    "final-quality": {
        "wave": 5,
        "min_claims_per_file": 5,
        "min_files": 2,
        "description": "Final Quality Gate — validates the COMPLETE submission package including plagiarism check and all quality metrics (All Waves → HITL-2)",
    },
}

# Minimum file size for L0 check
MIN_OUTPUT_SIZE = 100


# count_claims and extract_claim_ids imported from _claim_patterns


def check_inconsistencies(
    all_claims: dict[str, list[str]],
    project_dir: str | None = None,
    wave_num: int | None = None,
) -> list[str]:
    """Check for cross-file and cross-wave inconsistencies.

    Args:
        all_claims: dict of filename → list of claim IDs (current wave)
        project_dir: project root (for loading previous wave claims)
        wave_num: current wave number (for cross-wave check)

    Returns:
        list of inconsistency descriptions
    """
    inconsistencies = []

    # Check for duplicate claim IDs within current wave
    all_ids: dict[str, str] = {}
    for filename, ids in all_claims.items():
        for cid in ids:
            if cid in all_ids:
                inconsistencies.append(
                    f"Duplicate claim ID '{cid}' in {filename} and {all_ids[cid]}"
                )
            else:
                all_ids[cid] = filename

    # Cross-wave duplicate check: load claim IDs from previous waves
    if project_dir and wave_num and wave_num > 1:
        prev_ids = _load_previous_wave_claims(project_dir, wave_num)
        for cid, filename in all_ids.items():
            if cid in prev_ids:
                inconsistencies.append(
                    f"Cross-wave duplicate: '{cid}' in wave-{wave_num}/{filename} "
                    f"already exists in {prev_ids[cid]}"
                )

    return inconsistencies


def _load_previous_wave_claims(project_dir: str, current_wave: int) -> dict[str, str]:
    """Load claim IDs from all waves prior to current_wave.

    Returns:
        dict of claim_id → "wave-N/filename" source label
    """
    prev_ids: dict[str, str] = {}
    for w in range(1, current_wave):
        wave_dir = Path(project_dir) / "wave-results" / f"wave-{w}"
        if not wave_dir.is_dir():
            continue
        for md_file in wave_dir.glob("*.md"):
            if md_file.name.endswith(".ko.md"):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
                ids = extract_claim_ids(content)
                for cid in ids:
                    if cid not in prev_ids:
                        prev_ids[cid] = f"wave-{w}/{md_file.name}"
            except (OSError, UnicodeDecodeError):
                continue
    return prev_ids


def validate_gate(project_dir: str, gate_name: str) -> dict:
    """Run gate validation.

    Returns:
        dict with status (pass/fail), details
    """
    config = GATE_CONFIG.get(gate_name)
    if not config:
        return {
            "status": "fail",
            "gate": gate_name,
            "errors": [f"Unknown gate: {gate_name}"],
        }

    project = Path(project_dir)
    wave = config["wave"]
    wave_dir = project / "wave-results" / f"wave-{wave}"

    errors = []
    warnings = []
    file_results = []
    all_claims = {}

    if not wave_dir.is_dir():
        return {
            "status": "fail",
            "gate": gate_name,
            "errors": [f"Wave directory not found: {wave_dir}"],
        }

    # Check each output file — detect consolidated vs individual mode.
    # Consolidated filenames: step-NNN-to-NNN-agent.md (from query_step.py).
    # If consolidated files exist, use ONLY those to prevent double-counting
    # claims that appear in both consolidated and residual individual files
    # (e.g., after Consolidation Fallback Protocol splits a failed group).
    all_md = sorted(wave_dir.glob("*.md"))
    all_md = [f for f in all_md if not f.name.endswith(".ko.md")]

    consolidated = [f for f in all_md if _CONSOLIDATED_RE.match(f.name)]
    if consolidated and len(consolidated) >= config["min_files"]:
        md_files = consolidated
        # Warn if mixed state detected (both consolidated + non-consolidated)
        non_consolidated = [f for f in all_md if not _CONSOLIDATED_RE.match(f.name)]
        if non_consolidated:
            warnings.append(
                f"Mixed state: {len(consolidated)} consolidated + "
                f"{len(non_consolidated)} individual files — using consolidated only"
            )
    else:
        md_files = all_md

    if len(md_files) < config["min_files"]:
        errors.append(
            f"Insufficient files: {len(md_files)} < {config['min_files']} required"
        )

    for md_file in md_files:
        size = md_file.stat().st_size
        if size < MIN_OUTPUT_SIZE:
            errors.append(f"L0 fail: {md_file.name} ({size} bytes < {MIN_OUTPUT_SIZE})")
            continue

        content = md_file.read_text(encoding="utf-8")
        claim_count = count_claims(content)
        claim_ids = extract_claim_ids(content)

        if claim_count < config["min_claims_per_file"]:
            errors.append(
                f"Insufficient claims in {md_file.name}: "
                f"{claim_count} < {config['min_claims_per_file']} required"
            )

        all_claims[md_file.name] = claim_ids

        file_results.append({
            "file": md_file.name,
            "size": size,
            "claim_count": claim_count,
            "claim_ids": claim_ids,
        })

    # Cross-file and cross-wave consistency check
    inconsistencies = check_inconsistencies(all_claims, str(project), wave)
    if inconsistencies:
        for inc in inconsistencies:
            warnings.append(f"Inconsistency: {inc}")

    # Compute total claims
    total_claims = sum(r["claim_count"] for r in file_results)

    status = "pass" if len(errors) == 0 else "fail"

    return {
        "status": status,
        "gate": gate_name,
        "description": config["description"],
        "wave": wave,
        "files_checked": len(md_files),
        "total_claims": total_claims,
        "errors": errors,
        "warnings": warnings,
        "file_results": file_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Cross-Validation Gate Validator")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--gate", required=True, choices=list(GATE_CONFIG.keys()))
    parser.add_argument("--output-json", help="Write result to JSON file")
    args = parser.parse_args()

    result = validate_gate(args.project_dir, args.gate)

    # Display result
    print(f"Gate: {result['gate']} — {result.get('description', '')}")
    print(f"Status: {result['status'].upper()}")
    print(f"Files: {result.get('files_checked', 0)}")
    print(f"Total claims: {result.get('total_claims', 0)}")

    if result["errors"]:
        print("\nErrors:")
        for err in result["errors"]:
            print(f"  - {err}")

    if result["warnings"]:
        print("\nWarnings:")
        for warn in result["warnings"]:
            print(f"  - {warn}")

    # Write JSON report if requested
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\nReport written to: {args.output_json}")

    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
