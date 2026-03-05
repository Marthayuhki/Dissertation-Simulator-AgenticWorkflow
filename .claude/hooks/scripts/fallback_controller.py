#!/usr/bin/env python3
"""Fallback Controller — P1 deterministic 3-tier fallback switching.

Manages the Team → Sub-agent → Direct execution fallback tiers.
Decisions are based on timeout, health status, and retry counts.

Storage: Uses thesis SOT's `fallback_history` array (single source of truth).
Imports read/write functions from checklist_manager.py.

Usage:
  python3 fallback_controller.py --project-dir <dir> --step <N> --check
  python3 fallback_controller.py --project-dir <dir> --step <N> --escalate
  python3 fallback_controller.py --project-dir <dir> --log
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Import SOT functions from checklist_manager — single source of truth.
# NOTE: This is a thesis-internal import, NOT a system SOT reference (R6 safe).
from checklist_manager import read_thesis_sot, write_thesis_sot

# Fallback tiers (highest quality → lowest)
TIER_TEAM = "team"
TIER_SUBAGENT = "subagent"
TIER_DIRECT = "direct"
TIER_ORDER = [TIER_TEAM, TIER_SUBAGENT, TIER_DIRECT]

# Thresholds
DEFAULT_TIMEOUT_SECONDS = 600  # 10 minutes per tier attempt
MAX_RETRIES_PER_TIER = 2
HEALTH_CHECK_INTERVAL = 60  # seconds


def load_fallback_log(project_dir: str) -> list[dict]:
    """Load fallback history from thesis SOT's fallback_history field."""
    try:
        sot = read_thesis_sot(Path(project_dir))
        return list(sot.get("fallback_history", []))
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return []


def save_fallback_log(project_dir: str, log: list[dict]) -> None:
    """Save fallback history to thesis SOT's fallback_history field."""
    project_path = Path(project_dir)
    sot = read_thesis_sot(project_path)
    sot["fallback_history"] = log
    write_thesis_sot(project_path, sot)


def get_current_tier(project_dir: str, step: int) -> str:
    """Get current fallback tier for a step."""
    log = load_fallback_log(project_dir)
    # Find most recent entry for this step
    for entry in reversed(log):
        if entry.get("step") == step:
            return entry.get("tier", TIER_TEAM)
    return TIER_TEAM  # Default: start with team


def get_retry_count(project_dir: str, step: int, tier: str) -> int:
    """Count retries for a specific step and tier."""
    log = load_fallback_log(project_dir)
    return sum(
        1 for entry in log
        if entry.get("step") == step
        and entry.get("tier") == tier
        and entry.get("action") == "retry"
    )


def next_tier(current: str) -> str | None:
    """Get next fallback tier, or None if at lowest."""
    try:
        idx = TIER_ORDER.index(current)
        if idx + 1 < len(TIER_ORDER):
            return TIER_ORDER[idx + 1]
    except ValueError:
        pass
    return None


def check_tier_status(
    project_dir: str,
    step: int,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Check if current tier should be escalated.

    Returns:
        dict with current_tier, should_escalate, reason, next_tier
    """
    current = get_current_tier(project_dir, step)
    retries = get_retry_count(project_dir, step, current)

    # Check retry budget
    if retries >= MAX_RETRIES_PER_TIER:
        nxt = next_tier(current)
        return {
            "step": step,
            "current_tier": current,
            "should_escalate": nxt is not None,
            "reason": f"retry_budget_exhausted ({retries}/{MAX_RETRIES_PER_TIER})",
            "next_tier": nxt,
            "retries": retries,
        }

    # Check for stale output (timeout-based)
    project = Path(project_dir)
    wave_dir = project / "wave-results"
    if wave_dir.is_dir():
        latest_mtime = 0
        for f in wave_dir.rglob("*.md"):
            mtime = f.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime

        if latest_mtime > 0:
            age = time.time() - latest_mtime
            if age > timeout:
                nxt = next_tier(current)
                return {
                    "step": step,
                    "current_tier": current,
                    "should_escalate": nxt is not None,
                    "reason": f"timeout ({int(age)}s > {timeout}s)",
                    "next_tier": nxt,
                    "retries": retries,
                }

    return {
        "step": step,
        "current_tier": current,
        "should_escalate": False,
        "reason": "healthy",
        "next_tier": None,
        "retries": retries,
    }


def escalate_tier(
    project_dir: str,
    step: int,
    reason: str = "manual",
) -> dict:
    """Escalate to the next fallback tier.

    Returns:
        dict with old_tier, new_tier, success
    """
    current = get_current_tier(project_dir, step)
    nxt = next_tier(current)

    if nxt is None:
        return {
            "step": step,
            "old_tier": current,
            "new_tier": None,
            "success": False,
            "error": "Already at lowest tier (direct). Cannot escalate further.",
        }

    # Record escalation
    log = load_fallback_log(project_dir)
    log.append({
        "step": step,
        "tier": nxt,
        "action": "escalate",
        "from_tier": current,
        "reason": reason,
        "timestamp": time.time(),
    })
    save_fallback_log(project_dir, log)

    return {
        "step": step,
        "old_tier": current,
        "new_tier": nxt,
        "success": True,
    }


def record_retry(project_dir: str, step: int, tier: str, reason: str) -> None:
    """Record a retry attempt."""
    log = load_fallback_log(project_dir)
    log.append({
        "step": step,
        "tier": tier,
        "action": "retry",
        "reason": reason,
        "timestamp": time.time(),
    })
    save_fallback_log(project_dir, log)


def record_success(project_dir: str, step: int, tier: str) -> None:
    """Record successful completion at a tier."""
    log = load_fallback_log(project_dir)
    log.append({
        "step": step,
        "tier": tier,
        "action": "success",
        "timestamp": time.time(),
    })
    save_fallback_log(project_dir, log)


def record_fallback(
    project_dir: str,
    step: int,
    from_tier: str,
    to_tier: str,
    reason: str = "manual",
) -> dict:
    """Record a fallback tier switch (arbitrary tier transition).

    Unlike escalate_tier() which only allows sequential transitions,
    this records any tier-to-tier switch (e.g., team → direct).
    """
    if from_tier not in TIER_ORDER:
        return {"success": False, "error": f"Invalid from_tier: {from_tier}"}
    if to_tier not in TIER_ORDER:
        return {"success": False, "error": f"Invalid to_tier: {to_tier}"}

    log = load_fallback_log(project_dir)
    log.append({
        "step": step,
        "tier": to_tier,
        "action": "fallback",
        "from_tier": from_tier,
        "reason": reason,
        "timestamp": time.time(),
    })
    save_fallback_log(project_dir, log)

    return {
        "step": step,
        "old_tier": from_tier,
        "new_tier": to_tier,
        "success": True,
    }


def main():
    parser = argparse.ArgumentParser(description="Fallback Controller")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--step", type=int, help="Step number")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true",
                       help="Check if escalation is needed")
    group.add_argument("--escalate", action="store_true",
                       help="Escalate to next tier")
    group.add_argument("--record-retry", action="store_true",
                       help="Record a retry attempt")
    group.add_argument("--record-success", action="store_true",
                       help="Record successful completion")
    group.add_argument("--record-fallback", action="store_true",
                       help="Record a fallback tier switch")
    group.add_argument("--log", action="store_true",
                       help="Show fallback log")

    parser.add_argument("--reason", default="manual",
                        help="Reason for escalation/retry")
    parser.add_argument("--from-tier", choices=TIER_ORDER,
                        help="Source tier (for --record-fallback)")
    parser.add_argument("--to-tier", choices=TIER_ORDER,
                        help="Target tier (for --record-fallback)")
    args = parser.parse_args()

    if args.log:
        log = load_fallback_log(args.project_dir)
        if not log:
            print("No fallback events recorded.")
        else:
            for entry in log:
                ts = time.strftime("%H:%M:%S", time.localtime(entry.get("timestamp", 0)))
                print(f"[{ts}] Step {entry.get('step')}: "
                      f"{entry.get('action')} @ {entry.get('tier')}"
                      f" — {entry.get('reason', '')}")
        return 0

    if args.step is None:
        parser.error("--step is required for --check, --escalate, --record-retry, --record-success, --record-fallback")

    if args.check:
        result = check_tier_status(args.project_dir, args.step, args.timeout)
        print(f"Step {result['step']}: tier={result['current_tier']}, "
              f"escalate={result['should_escalate']}, reason={result['reason']}")
        if result["should_escalate"]:
            print(f"  → Recommend escalation to: {result['next_tier']}")
        return 0

    if args.escalate:
        result = escalate_tier(args.project_dir, args.step, args.reason)
        if result["success"]:
            print(f"Step {args.step}: escalated {result['old_tier']} → {result['new_tier']}")
        else:
            print(f"Step {args.step}: {result.get('error', 'escalation failed')}")
        return 0 if result["success"] else 1

    if args.record_retry:
        tier = get_current_tier(args.project_dir, args.step)
        record_retry(args.project_dir, args.step, tier, args.reason)
        print(f"Step {args.step}: retry recorded @ {tier}")
        return 0

    if args.record_success:
        tier = get_current_tier(args.project_dir, args.step)
        record_success(args.project_dir, args.step, tier)
        print(f"Step {args.step}: success recorded @ {tier}")
        return 0

    if args.record_fallback:
        if not args.from_tier or not args.to_tier:
            parser.error("--record-fallback requires --from-tier and --to-tier")
        result = record_fallback(
            args.project_dir, args.step,
            args.from_tier, args.to_tier, args.reason)
        if result["success"]:
            print(f"Step {args.step}: fallback recorded {result['old_tier']} -> {result['new_tier']}")
        else:
            print(f"Step {args.step}: {result.get('error', 'fallback recording failed')}")
        return 0 if result["success"] else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
