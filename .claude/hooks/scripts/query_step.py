#!/usr/bin/env python3
"""Step Execution Registry — deterministic step→execution parameters mapping.

Eliminates Orchestrator hallucination at 4 critical decision points:
  H-1: Step→Agent mapping (which agent executes this step?)
  H-2: pCCS mode selection (FULL or DEGRADED?)
  H-3: Critic agent routing (which critic reviews this step?)
  H-4: Tier selection (Tier 1/2/3?)

The Orchestrator calls this script INSTEAD of interpreting prose rules.
All outputs are deterministic — no LLM interpretation needed.

Usage:
  python3 query_step.py --step 47 [--project-dir <dir>]
  python3 query_step.py --step 47 --json
  python3 query_step.py --step 47 --field agent
  python3 query_step.py --list-agents
  python3 query_step.py --list-steps --agent literature-searcher

P1 Compliance: Pure stdlib, no LLM, deterministic, exit 0 always.
"""

import argparse
import json
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Step Registry — THE single source of truth for step execution parameters
# ---------------------------------------------------------------------------

# Agent assignment by step range.
# Format: (start, end, agent_name, description_prefix)
# Within a range, each step maps to the same agent.
# For mixed-agent sections, individual step overrides are in _STEP_OVERRIDES.

_RANGE_AGENTS: list[tuple[int, int, str, str]] = [
    # Phase 0: Initialization (steps 1-8) — Orchestrator direct
    (1, 8, "_orchestrator", "Phase 0 setup"),
    # Phase 0-A: Topic Exploration (steps 9-14)
    (9, 11, "topic-explorer", "Topic exploration"),
    (12, 14, "literature-analyzer", "Literature feasibility"),
    # Phase 0-D: Learning Mode (steps 15-34)
    (15, 16, "methodology-tutor", "Learning setup"),
    (17, 22, "methodology-tutor", "Learning module"),
    (23, 28, "methodology-tutor", "Learning module"),
    (29, 32, "methodology-tutor", "Learning module"),
    (33, 34, "assessment-agent", "Assessment"),
    # HITL-1 (steps 35-38) — Orchestrator direct (human interaction)
    (35, 38, "_orchestrator", "HITL-1 interaction"),
    # Wave 1 (steps 39-54)
    (39, 42, "literature-searcher", "Wave 1 literature search"),
    (43, 46, "seminal-works-analyst", "Wave 1 seminal works"),
    (47, 50, "trend-analyst", "Wave 1 trend analysis"),
    (51, 54, "methodology-scanner", "Wave 1 methodology scan"),
    # Gate 1 (steps 55-58)
    (55, 55, "_orchestrator", "Gate 1 cross-validation"),
    (56, 56, "translator", "Gate 1 translation"),
    (57, 57, "_orchestrator", "Gate 1 translation validation"),
    (58, 58, "_orchestrator", "Gate 1 SOT record"),
    # Wave 2 (steps 59-74)
    (59, 62, "theoretical-framework-analyst", "Wave 2 theory analysis"),
    (63, 66, "empirical-evidence-analyst", "Wave 2 empirical analysis"),
    (67, 70, "gap-identifier", "Wave 2 gap identification"),
    (71, 74, "variable-relationship-analyst", "Wave 2 variable analysis"),
    # Gate 2 (steps 75-78)
    (75, 75, "_orchestrator", "Gate 2 cross-validation"),
    (76, 76, "translator", "Gate 2 translation"),
    (77, 77, "_orchestrator", "Gate 2 translation validation"),
    (78, 78, "_orchestrator", "Gate 2 SOT record"),
    # Wave 3 (steps 79-94)
    (79, 82, "critical-reviewer", "Wave 3 critical review"),
    (83, 86, "methodology-critic", "Wave 3 methodology critique"),
    (87, 90, "limitation-analyst", "Wave 3 limitation analysis"),
    (91, 94, "future-direction-analyst", "Wave 3 future directions"),
    # Gate 3 (steps 95-98)
    (95, 95, "_orchestrator", "Gate 3 cross-validation"),
    (96, 96, "translator", "Gate 3 translation"),
    (97, 97, "_orchestrator", "Gate 3 translation validation"),
    (98, 98, "_orchestrator", "Gate 3 SOT record"),
    # Wave 4 (steps 99-106)
    (99, 102, "synthesis-agent", "Wave 4 synthesis"),
    (103, 106, "conceptual-model-builder", "Wave 4 conceptual model"),
    # SRCS Full (steps 107-110)
    (107, 107, "unified-srcs-evaluator", "SRCS full evaluation"),
    (108, 108, "translator", "SRCS translation"),
    (109, 109, "_orchestrator", "SRCS translation validation"),
    (110, 110, "_orchestrator", "SRCS SOT record"),
    # Wave 5 (steps 111-114)
    (111, 112, "plagiarism-checker", "Wave 5 plagiarism check"),
    (113, 113, "translator", "Wave 5 translation"),
    (114, 114, "_orchestrator", "Wave 5 SOT record"),
    # HITL-2 (steps 115-120) — Orchestrator direct
    (115, 120, "_orchestrator", "HITL-2 literature review approval"),
    # Phase 2 (steps 121-140)
    (121, 121, "_orchestrator", "Phase 2 design approach"),
    (122, 122, "_orchestrator", "Phase 2 agent configuration"),
]

# Phase 2 has research-type-dependent agents — handled by _STEP_OVERRIDES_BY_RESEARCH_TYPE
_PHASE2_QUANT_AGENTS: list[tuple[int, int, str, str]] = [
    (123, 123, "quantitative-designer", "Research methodology"),
    (124, 124, "hypothesis-developer", "Variable definition"),
    (125, 125, "sampling-designer", "Sampling strategy"),
    (126, 126, "instrument-developer", "Research instruments"),
    (127, 127, "statistical-planner", "Statistical analysis plan"),
    (128, 128, "data-collection-planner", "Data collection procedure"),
    (129, 129, "ethics-reviewer", "Ethical considerations"),
]

_PHASE2_QUAL_AGENTS: list[tuple[int, int, str, str]] = [
    (123, 123, "paradigm-consultant", "Research methodology"),
    (124, 124, "qualitative-data-designer", "Variable definition"),
    (125, 125, "participant-selector", "Sampling strategy"),
    (126, 126, "instrument-developer", "Research instruments"),
    (127, 127, "qualitative-analysis-planner", "Analysis plan"),
    (128, 128, "data-collection-planner", "Data collection procedure"),
    (129, 129, "ethics-reviewer", "Ethical considerations"),
]

_PHASE2_MIXED_AGENTS: list[tuple[int, int, str, str]] = [
    (123, 123, "mixed-methods-designer", "Research methodology"),
    (124, 124, "integration-strategist", "Variable definition"),
    (125, 125, "sampling-designer", "Sampling strategy"),
    (126, 126, "instrument-developer", "Research instruments"),
    (127, 127, "statistical-planner", "Analysis plan"),
    (128, 128, "data-collection-planner", "Data collection procedure"),
    (129, 129, "ethics-reviewer", "Ethical considerations"),
]

# Phase 2 common tail (steps 130-140)
_PHASE2_COMMON_TAIL: list[tuple[int, int, str, str]] = [
    (130, 130, "research-model-developer", "Research timeline"),
    (131, 131, "thesis-writer", "Draft research design"),
    (132, 132, "_orchestrator", "Internal review"),
    (133, 133, "translator", "Phase 2 translation"),
    (134, 134, "_orchestrator", "Phase 2 translation validation"),
    (135, 135, "_orchestrator", "Phase 2 SOT record"),
    (136, 136, "_orchestrator", "HITL-3 research type"),
    (137, 137, "_orchestrator", "HITL-4 design approval"),
    (138, 138, "_orchestrator", "HITL-3/4 checkpoint"),
    (139, 139, "_orchestrator", "Finalize design package"),
    (140, 140, "_orchestrator", "Archive design artifacts"),
]

# Phase 3: Thesis Writing (steps 141-164)
_PHASE3_AGENTS: list[tuple[int, int, str, str]] = [
    (141, 141, "thesis-architect", "Create thesis outline"),
    (142, 142, "_orchestrator", "HITL-5 outline approval"),
    (143, 143, "thesis-writer", "Chapter 1 Introduction"),
    (144, 144, "thesis-writer", "Chapter 2 Literature Review"),
    (145, 145, "thesis-writer", "Chapter 3 Research Methodology"),
    (146, 146, "thesis-writer", "Chapter 4 Results"),
    (147, 147, "thesis-writer", "Chapter 5 Discussion"),
    (148, 148, "thesis-writer", "Chapter 6 Conclusion"),
    (149, 149, "abstract-writer", "Abstract"),
    (150, 150, "citation-manager", "References"),
    (151, 151, "thesis-writer", "Appendices"),
    (152, 152, "thesis-reviewer", "Internal review cycle 1"),
    (153, 153, "thesis-writer", "Revision 1"),
    (154, 154, "thesis-reviewer", "Internal review cycle 2"),
    (155, 155, "thesis-writer", "Revision 2"),
    (156, 156, "thesis-plagiarism-checker", "Full thesis plagiarism"),
    (157, 157, "_orchestrator", "HITL-6 draft review"),
    (158, 158, "thesis-writer", "Final revision"),
    (159, 159, "manuscript-formatter", "Format check"),
    (160, 160, "_orchestrator", "HITL-7 final approval"),
    (161, 161, "translator", "Translate chapters"),
    (162, 162, "_orchestrator", "Validate translations"),
    (163, 163, "_orchestrator", "Bilingual package"),
    (164, 164, "_orchestrator", "Archive writing artifacts"),
]

# Phase 4: Publication (steps 165-172)
_PHASE4_AGENTS: list[tuple[int, int, str, str]] = [
    (165, 165, "publication-strategist", "Identify journals"),
    (166, 166, "journal-matcher", "Journal requirements"),
    (167, 167, "submission-preparer", "Submission package"),
    (168, 168, "cover-letter-writer", "Cover letter"),
    (169, 169, "manuscript-formatter", "Journal formatting"),
    (170, 170, "_orchestrator", "Final quality check"),
    (171, 171, "_orchestrator", "HITL-8 submission approval"),
    (172, 172, "_orchestrator", "Final submission package"),
]

# Phase 5: Finalization (steps 173-180)
_PHASE5_AGENTS: list[tuple[int, int, str, str]] = [
    (173, 173, "_orchestrator", "Consolidate artifacts"),
    (174, 174, "_orchestrator", "Cross-reference validation"),
    (175, 175, "citation-manager", "Citation report"),
    (176, 176, "_orchestrator", "Supplementary materials"),
    (177, 177, "_orchestrator", "Data availability"),
    (178, 178, "thesis-plagiarism-checker", "Final plagiarism check"),
    (179, 179, "_orchestrator", "Author contribution"),
    (180, 180, "_orchestrator", "Archive project"),
]

# Phase 6: Translation (steps 181-210)
_PHASE6_AGENTS: list[tuple[int, int, str, str]] = [
    (181, 210, "translator", "Translation step"),
]


# ---------------------------------------------------------------------------
# Critic routing — which critic reviews which step
# ---------------------------------------------------------------------------

# Steps that use Adversarial Dialogue with research domain
# (parallel @fact-checker + @reviewer)
_DIALOGUE_RESEARCH_STEPS: set[int] = set()
# Wave 1-3 content steps (agent work, not gate/translation/SOT steps)
for _s, _e in [(39, 54), (59, 74), (79, 94)]:
    _DIALOGUE_RESEARCH_STEPS.update(range(_s, _e + 1))
# Wave 4 synthesis steps
_DIALOGUE_RESEARCH_STEPS.update(range(99, 106 + 1))

# Steps that use Adversarial Dialogue with development domain (@code-reviewer)
_DIALOGUE_DEVELOPMENT_STEPS: set[int] = set()
# Phase 2 design steps (123-131) — methodology design is development-type review
_DIALOGUE_DEVELOPMENT_STEPS.update(range(123, 131 + 1))

# Steps that use single-review (@reviewer only, no dialogue)
_SINGLE_REVIEW_STEPS: set[int] = set()
# Phase 3 review cycles
_SINGLE_REVIEW_STEPS.update({152, 154})
# Phase 4 quality check
_SINGLE_REVIEW_STEPS.add(170)

# Gate steps that need L2 Enhanced review
_GATE_STEPS: set[int] = {55, 75, 95, 107}


def _get_critic_config(step: int) -> dict[str, Any]:
    """Return critic configuration for a step.

    Returns:
        dict with keys:
        - critic: primary critic agent name (or None)
        - dialogue_domain: "research" | "development" | None
        - dialogue: bool — whether Adversarial Dialogue is used
        - l2_enhanced: bool — whether L2 Enhanced review applies
    """
    if step in _DIALOGUE_RESEARCH_STEPS:
        return {
            "critic": "fact-checker",
            "critic_secondary": "reviewer",
            "dialogue_domain": "research",
            "dialogue": True,
            "l2_enhanced": True,
        }
    if step in _DIALOGUE_DEVELOPMENT_STEPS:
        return {
            "critic": "code-reviewer",
            "critic_secondary": None,
            "dialogue_domain": "development",
            "dialogue": True,
            "l2_enhanced": True,
        }
    if step in _SINGLE_REVIEW_STEPS or step in _GATE_STEPS:
        return {
            "critic": "reviewer",
            "critic_secondary": None,
            "dialogue_domain": None,
            "dialogue": False,
            "l2_enhanced": True,
        }
    return {
        "critic": None,
        "critic_secondary": None,
        "dialogue_domain": None,
        "dialogue": False,
        "l2_enhanced": False,
    }


# ---------------------------------------------------------------------------
# pCCS mode selection — deterministic FULL vs DEGRADED
# ---------------------------------------------------------------------------

# Steps where pCCS FULL mode is required (high-importance Tier A content steps)
_PCCS_FULL_STEPS: set[int] = set()
# NOTE: Gate steps (55, 75, 95, 107) are cross-validation, not content — no pCCS
# Wave 4 synthesis (high importance — final synthesis before HITL-2)
_PCCS_FULL_STEPS.update(range(99, 106 + 1))
# Phase 3 thesis chapters (high importance — final thesis content)
_PCCS_FULL_STEPS.update(range(143, 151 + 1))

# Steps that produce GroundedClaim output (Tier A) — pCCS applicable
_GROUNDED_CLAIM_STEPS: set[int] = set()
# Wave 1-3 content steps
for _s, _e in [(39, 54), (59, 74), (79, 94)]:
    _GROUNDED_CLAIM_STEPS.update(range(_s, _e + 1))
# Wave 4 synthesis
_GROUNDED_CLAIM_STEPS.update(range(99, 106 + 1))
# Phase 2 design content (123-131)
_GROUNDED_CLAIM_STEPS.update(range(123, 131 + 1))
# Phase 3 thesis chapters (143-151)
_GROUNDED_CLAIM_STEPS.update(range(143, 151 + 1))


def _get_pccs_config(step: int) -> dict[str, Any]:
    """Return pCCS configuration for a step.

    Returns:
        dict with keys:
        - pccs_required: bool — whether pCCS scoring applies
        - pccs_mode: "FULL" | "DEGRADED" | None
        - has_grounded_claims: bool — whether step produces GroundedClaim output
    """
    if step not in _GROUNDED_CLAIM_STEPS:
        return {
            "pccs_required": False,
            "pccs_mode": None,
            "has_grounded_claims": False,
        }
    mode = "FULL" if step in _PCCS_FULL_STEPS else "DEGRADED"
    return {
        "pccs_required": True,
        "pccs_mode": mode,
        "has_grounded_claims": True,
    }


# ---------------------------------------------------------------------------
# Wave/Phase/Gate mapping
# ---------------------------------------------------------------------------

def _get_wave(step: int) -> int | None:
    """Return wave number (1-5) for a step, or None if not in a wave."""
    if 39 <= step <= 54:
        return 1
    if 59 <= step <= 74:
        return 2
    if 79 <= step <= 94:
        return 3
    if 99 <= step <= 106:
        return 4
    if 111 <= step <= 114:
        return 5
    return None


def _get_phase(step: int) -> str:
    """Return phase name for a step."""
    if step <= 8:
        return "phase_0_init"
    if step <= 14:
        return "phase_0a_topic"
    if step <= 34:
        return "phase_0d_learning"
    if step <= 38:
        return "hitl_1"
    if step <= 54:
        return "wave_1"
    if step <= 58:
        return "gate_1"
    if step <= 74:
        return "wave_2"
    if step <= 78:
        return "gate_2"
    if step <= 94:
        return "wave_3"
    if step <= 98:
        return "gate_3"
    if step <= 106:
        return "wave_4"
    if step <= 110:
        return "srcs_full"
    if step <= 114:
        return "wave_5"
    if step <= 120:
        return "hitl_2"
    if step <= 140:
        return "phase_2_design"
    if step <= 164:
        return "phase_3_writing"
    if step <= 172:
        return "phase_4_publication"
    if step <= 180:
        return "phase_5_finalization"
    if step <= 210:
        return "phase_6_translation"
    return "unknown"


def _get_gate_context(step: int) -> dict[str, Any]:
    """Return gate context — which gate comes before/after this step."""
    gate_before = None
    gate_after = None

    if 55 <= step <= 58:
        gate_before = None
        gate_after = "gate-1"
    elif 59 <= step <= 78:
        gate_before = "gate-1"
        gate_after = "gate-2"
    elif 79 <= step <= 98:
        gate_before = "gate-2"
        gate_after = "gate-3"
    elif 99 <= step <= 110:
        gate_before = "gate-3"
        gate_after = "srcs-full"
    elif 111 <= step <= 114:
        gate_before = "srcs-full"
        gate_after = "final-quality"

    return {"gate_before": gate_before, "gate_after": gate_after}


# ---------------------------------------------------------------------------
# HITL mapping
# ---------------------------------------------------------------------------

_HITL_STEPS: dict[int, str] = {
    35: "hitl-1", 36: "hitl-1", 37: "hitl-1", 38: "hitl-1",
    115: "hitl-2", 116: "hitl-2", 117: "hitl-2", 118: "hitl-2",
    119: "hitl-2", 120: "hitl-2",
    136: "hitl-3", 137: "hitl-4",
    142: "hitl-5",
    157: "hitl-6",
    160: "hitl-7",
    171: "hitl-8",
}


# ---------------------------------------------------------------------------
# Translation step detection
# ---------------------------------------------------------------------------

_TRANSLATION_STEPS: set[int] = set()
# Gate translation steps
_TRANSLATION_STEPS.update({56, 76, 96, 108, 113})
# Phase 2 translation
_TRANSLATION_STEPS.add(133)
# Phase 3 translation
_TRANSLATION_STEPS.add(161)
# Phase 6 all translation
_TRANSLATION_STEPS.update(range(181, 210 + 1))


# ---------------------------------------------------------------------------
# Output path pattern
# ---------------------------------------------------------------------------

def _get_output_pattern(step: int, phase: str) -> str:
    """Return expected output file path pattern for a step."""
    wave = _get_wave(step)
    if wave is not None:
        return f"wave-results/wave-{wave}/step-{step:03d}-*.md"
    if phase.startswith("phase_2"):
        return f"phase-2/step-{step:03d}-*.md"
    if phase.startswith("phase_3"):
        return f"phase-3/step-{step:03d}-*.md"
    if phase.startswith("phase_4"):
        return f"submission-package/step-{step:03d}-*.md"
    if phase.startswith("phase_6"):
        return f"translations/step-{step:03d}-*.ko.md"
    return f"step-{step:03d}-*.md"


# ---------------------------------------------------------------------------
# Core query function
# ---------------------------------------------------------------------------

def query_step(step: int, research_type: str = "undecided") -> dict[str, Any]:
    """Query execution parameters for a given step.

    Args:
        step: Step number (1-210)
        research_type: "quantitative", "qualitative", "mixed", or "undecided"

    Returns:
        dict with all deterministic execution parameters.
    """
    if step < 1 or step > 210:
        return {"error": f"Step {step} out of range [1, 210]"}

    # Build the full agent list based on research type
    all_ranges: list[tuple[int, int, str, str]] = list(_RANGE_AGENTS)

    # Add Phase 2 type-specific agents
    if research_type == "quantitative":
        all_ranges.extend(_PHASE2_QUANT_AGENTS)
    elif research_type == "qualitative":
        all_ranges.extend(_PHASE2_QUAL_AGENTS)
    elif research_type == "mixed":
        all_ranges.extend(_PHASE2_MIXED_AGENTS)
    else:
        # Default to quantitative for "undecided" (most common fallback)
        all_ranges.extend(_PHASE2_QUANT_AGENTS)

    all_ranges.extend(_PHASE2_COMMON_TAIL)
    all_ranges.extend(_PHASE3_AGENTS)
    all_ranges.extend(_PHASE4_AGENTS)
    all_ranges.extend(_PHASE5_AGENTS)
    all_ranges.extend(_PHASE6_AGENTS)

    # Find agent for this step
    agent = "_orchestrator"
    description = "Unknown step"
    for start, end, agent_name, desc in all_ranges:
        if start <= step <= end:
            agent = agent_name
            description = desc
            break

    # Tier determination — deterministic (from thesis-orchestrator.md Step-to-Tier Mapping)
    # Default: Tier 2. Orchestrator direct = Tier 3. Translator = Tier 2.
    if agent == "_orchestrator":
        tier = 3  # Orchestrator performs directly
    else:
        tier = 2  # Default: sub-agent (quality-first)

    phase = _get_phase(step)
    gate_ctx = _get_gate_context(step)
    critic_cfg = _get_critic_config(step)
    pccs_cfg = _get_pccs_config(step)
    hitl = _HITL_STEPS.get(step)
    is_translation = step in _TRANSLATION_STEPS
    output_pattern = _get_output_pattern(step, phase)

    return {
        "step": step,
        "agent": agent,
        "description": description,
        "tier": tier,
        "phase": phase,
        "wave": _get_wave(step),
        "research_type_used": research_type,
        # Critic routing (H-3)
        "critic": critic_cfg["critic"],
        "critic_secondary": critic_cfg.get("critic_secondary"),
        "dialogue_domain": critic_cfg["dialogue_domain"],
        "dialogue": critic_cfg["dialogue"],
        "l2_enhanced": critic_cfg["l2_enhanced"],
        # pCCS (H-2)
        "pccs_required": pccs_cfg["pccs_required"],
        "pccs_mode": pccs_cfg["pccs_mode"],
        "has_grounded_claims": pccs_cfg["has_grounded_claims"],
        # Context
        "output_path": output_pattern,
        "gate_before": gate_ctx["gate_before"],
        "gate_after": gate_ctx["gate_after"],
        "hitl": hitl,
        "hitl_required": hitl is not None,
        "translation_required": is_translation,
    }


def list_agents() -> dict[str, list[int]]:
    """Return a mapping of agent_name → list of steps they handle.

    Uses 'undecided' research type for the base mapping.
    """
    result: dict[str, list[int]] = {}
    for step in range(1, 211):
        info = query_step(step)
        agent = info["agent"]
        if agent not in result:
            result[agent] = []
        result[agent].append(step)
    return result


def list_steps_for_agent(agent_name: str) -> list[int]:
    """Return all steps handled by a specific agent."""
    agents = list_agents()
    return agents.get(agent_name, [])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step Execution Registry — deterministic step→execution mapping"
    )
    parser.add_argument("--step", type=int, help="Step number to query (1-210)")
    parser.add_argument("--project-dir", help="Project directory (reads research_type from SOT)")
    parser.add_argument("--research-type",
                        choices=["quantitative", "qualitative", "mixed", "undecided"],
                        help="Research type override (default: read from SOT or 'undecided')")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--field", help="Output only a specific field value")
    parser.add_argument("--list-agents", action="store_true", help="List all agents and their step ranges")
    parser.add_argument("--list-steps", action="store_true", help="List steps for a specific agent (use with --agent)")
    parser.add_argument("--agent", help="Agent name (for --list-steps)")

    args = parser.parse_args()

    # Determine research type
    research_type = "undecided"
    if args.research_type:
        research_type = args.research_type
    elif args.project_dir:
        try:
            import os
            sot_path = os.path.join(args.project_dir, "session.json")
            if os.path.exists(sot_path):
                with open(sot_path, "r", encoding="utf-8") as f:
                    sot = json.load(f)
                research_type = sot.get("research_type", "undecided")
        except (json.JSONDecodeError, IOError):
            pass  # Fall back to undecided

    if args.list_agents:
        agents = list_agents()
        if args.json:
            print(json.dumps(agents, indent=2))
        else:
            for agent_name in sorted(agents.keys()):
                steps = agents[agent_name]
                ranges = _compact_ranges(steps)
                print(f"{agent_name}: {ranges} ({len(steps)} steps)")
        return 0

    if args.list_steps:
        if not args.agent:
            print("ERROR: --list-steps requires --agent NAME", file=sys.stderr)
            return 1
        steps = list_steps_for_agent(args.agent)
        if args.json:
            print(json.dumps(steps))
        else:
            if steps:
                print(f"{args.agent}: steps {_compact_ranges(steps)}")
            else:
                print(f"{args.agent}: no steps assigned")
        return 0

    if args.step is None:
        parser.error("--step is required (or use --list-agents)")
        return 1

    result = query_step(args.step, research_type)

    if "error" in result:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        return 1

    if args.field:
        val = result.get(args.field)
        if val is None and args.field not in result:
            print(f"ERROR: Unknown field '{args.field}'", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(val))
        else:
            print(val if val is not None else "null")
        return 0

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Step {result['step']}: {result['description']}")
        print(f"  Agent: {result['agent']}")
        print(f"  Tier: {result['tier']}")
        print(f"  Phase: {result['phase']}")
        if result['wave']:
            print(f"  Wave: {result['wave']}")
        if result['critic']:
            critic_str = result['critic']
            if result.get('critic_secondary'):
                critic_str += f" + {result['critic_secondary']}"
            print(f"  Critic: {critic_str}")
            if result['dialogue']:
                print(f"  Dialogue: {result['dialogue_domain']}")
        if result['pccs_required']:
            print(f"  pCCS: {result['pccs_mode']}")
        if result['hitl']:
            print(f"  HITL: {result['hitl']}")
        if result['gate_before']:
            print(f"  Gate before: {result['gate_before']}")
        if result['gate_after']:
            print(f"  Gate after: {result['gate_after']}")
        print(f"  Output: {result['output_path']}")

    return 0


def _compact_ranges(steps: list[int]) -> str:
    """Convert [1,2,3,5,6,8] to '1-3, 5-6, 8'."""
    if not steps:
        return "none"
    sorted_steps = sorted(steps)
    ranges: list[str] = []
    start = sorted_steps[0]
    end = start
    for s in sorted_steps[1:]:
        if s == end + 1:
            end = s
        else:
            ranges.append(f"{start}-{end}" if start != end else str(start))
            start = end = s
    ranges.append(f"{start}-{end}" if start != end else str(start))
    return ", ".join(ranges)


if __name__ == "__main__":
    sys.exit(main())
