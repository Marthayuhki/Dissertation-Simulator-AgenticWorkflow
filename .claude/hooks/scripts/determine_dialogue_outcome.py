#!/usr/bin/env python3
"""determine_dialogue_outcome.py — P1 Deterministic Dialogue Loop Decision.

Replaces the Orchestrator's LLM-based interpretation of dialogue state
with a deterministic decision algorithm. The Orchestrator calls this
script after each dialogue round and blindly follows the outcome.

This eliminates Vulnerability V-2: "Dialogue Loop Exit Decision is
non-deterministic — Orchestrator interprets DA1-DA5 results differently
across invocations."

Usage:
    python3 determine_dialogue_outcome.py \
        --step 5 --round 2 --max-rounds 3 --project-dir .

Output: JSON to stdout
    {
        "outcome": "consensus" | "continue_round" | "escalate",
        "round": 2,
        "max_rounds": 3,
        "verdicts": {"fc": "PASS", "rv": "PASS"},
        "reason": "All critic verdicts PASS in round 2",
        "da_valid": true
    }

Decision Rules (deterministic):
    1. Extract verdicts from ALL critic files for current round
    2. If ALL verdicts == PASS → "consensus"
    3. If ANY verdict != PASS AND round < max_rounds → "continue_round"
    4. If ANY verdict != PASS AND round >= max_rounds → "escalate"
    5. If critic files missing → "continue_round" (allow retry)
    6. If DA validation fails fatally → "escalate" with reason

Exit codes:
    0 — always (P1 compliant, non-blocking)

P1 Compliance: All decisions are regex + filesystem + integer comparison.
SOT Compliance: Read-only access to dialogue-logs/ and session.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

# Add script directory to path for shared library import
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from validate_dialogue_state import (  # noqa: E402
    _critic_files_for_round,
    _extract_verdict,
    _read_sot,
    validate_dialogue_state,
)

# Default max dialogue rounds before escalation
DEFAULT_MAX_ROUNDS = 3


def determine_outcome(
    project_dir: str,
    step: int,
    current_round: int,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> dict[str, object]:
    """Deterministic dialogue outcome decision.

    This function replaces ALL LLM-based dialogue state interpretation.
    The Orchestrator MUST follow the returned outcome without modification.

    Args:
        project_dir: Project root directory
        step: Step number
        current_round: Round that just completed (1-indexed)
        max_rounds: Maximum allowed rounds before escalation

    Returns:
        dict with outcome, verdicts, reason, and validation state
    """
    # Step 1: Detect domain from SOT
    sot = _read_sot(project_dir)
    domain = "research"  # safe default
    if sot:
        ds = sot.get("dialogue_state", {})
        if isinstance(ds, dict):
            domain = ds.get("domain", "research")
            # Use SOT max_rounds if available and caller didn't override
            sot_max = ds.get("max_rounds")
            if sot_max is not None and max_rounds == DEFAULT_MAX_ROUNDS:
                max_rounds = int(sot_max)

    # Step 2: Extract verdicts from ALL critic files for current round
    critic_files = _critic_files_for_round(project_dir, step, current_round, domain)
    verdicts: dict[str, str | None] = {}
    missing_files: list[str] = []

    for fpath in critic_files:
        basename = os.path.basename(fpath)
        # Extract critic type from filename: step-N-rK-{type}.md
        match = re.search(r"-r\d+-(\w+)\.md$", basename)
        critic_type = match.group(1) if match else basename
        if os.path.exists(fpath):
            verdicts[critic_type] = _extract_verdict(fpath)
        else:
            verdicts[critic_type] = None
            missing_files.append(basename)

    # Step 3: Run DA1-DA5 validation for state integrity check
    da_result = validate_dialogue_state(
        project_dir, step, current_round, check_consensus=False
    )
    da_valid = da_result.get("valid", False)

    # Step 4: Apply deterministic decision rules

    # Rule 5: Missing critic files → retry OR escalate (prevent infinite loop)
    if missing_files:
        if current_round >= max_rounds:
            # At max rounds, missing files = cannot retry → must escalate
            return {
                "outcome": "escalate",
                "round": current_round,
                "max_rounds": max_rounds,
                "verdicts": verdicts,
                "reason": f"Critic files missing at max round {current_round}/{max_rounds}: "
                          f"{', '.join(missing_files)} — escalating to prevent infinite loop",
                "da_valid": da_valid,
                "missing_files": missing_files,
            }
        return {
            "outcome": "continue_round",
            "round": current_round,
            "max_rounds": max_rounds,
            "verdicts": verdicts,
            "reason": f"Critic files missing for round {current_round}: "
                      f"{', '.join(missing_files)} — retry round",
            "da_valid": da_valid,
            "missing_files": missing_files,
        }

    # Rule: Handle None verdicts (file exists but no PASS/FAIL extracted)
    null_verdicts = [k for k, v in verdicts.items() if v is None]
    if null_verdicts:
        if current_round >= max_rounds:
            return {
                "outcome": "escalate",
                "round": current_round,
                "max_rounds": max_rounds,
                "verdicts": verdicts,
                "reason": f"Cannot extract verdict from {', '.join(null_verdicts)} "
                          f"at round {current_round}/{max_rounds} — escalating",
                "da_valid": da_valid,
            }
        return {
            "outcome": "continue_round",
            "round": current_round,
            "max_rounds": max_rounds,
            "verdicts": verdicts,
            "reason": f"Cannot extract verdict from {', '.join(null_verdicts)} "
                      f"— retry round {current_round + 1}",
            "da_valid": da_valid,
        }

    # Rule 2: All verdicts PASS → consensus
    all_pass = all(v == "PASS" for v in verdicts.values())
    if all_pass:
        return {
            "outcome": "consensus",
            "round": current_round,
            "max_rounds": max_rounds,
            "verdicts": verdicts,
            "reason": f"All critic verdicts PASS in round {current_round}",
            "da_valid": da_valid,
        }

    # Rule 3/4: Some verdict FAIL → check round budget
    failed_critics = [k for k, v in verdicts.items() if v == "FAIL"]

    if current_round >= max_rounds:
        # Rule 4: Budget exhausted → escalate
        return {
            "outcome": "escalate",
            "round": current_round,
            "max_rounds": max_rounds,
            "verdicts": verdicts,
            "reason": f"Critics {', '.join(failed_critics)} still FAIL "
                      f"at round {current_round}/{max_rounds} — escalating to user",
            "da_valid": da_valid,
        }

    # Rule 3: Budget remaining → continue
    return {
        "outcome": "continue_round",
        "round": current_round,
        "max_rounds": max_rounds,
        "verdicts": verdicts,
        "reason": f"Critics {', '.join(failed_critics)} FAIL "
                  f"— advancing to round {current_round + 1}/{max_rounds}",
        "da_valid": da_valid,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P1 Deterministic Dialogue Outcome Decision"
    )
    parser.add_argument("--step", type=int, required=True, help="Step number")
    parser.add_argument("--round", type=int, required=True,
                        help="Current round number (just completed)")
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS,
                        help=f"Maximum rounds before escalation (default: {DEFAULT_MAX_ROUNDS})")
    parser.add_argument("--project-dir", type=str, default=".",
                        help="Project root directory")
    args = parser.parse_args()

    result = determine_outcome(
        os.path.abspath(args.project_dir),
        args.step,
        args.round,
        args.max_rounds,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception as e:
        error_output = {
            "outcome": "escalate",
            "error": str(e),
            "reason": f"Fatal error in determine_dialogue_outcome: {e}",
        }
        print(json.dumps(error_output, indent=2, ensure_ascii=False))
        sys.exit(0)  # P1: never block
