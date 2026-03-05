---
description: Start or continue the doctoral thesis research workflow. Reads SOT to determine current position and executes the next steps.
---

# Thesis Start / Continue

Resume or start the thesis workflow execution.

## Protocol

### Step 1: Read Current State

```bash
python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/scripts/checklist_manager.py \
  --status \
  --project-dir "$CLAUDE_PROJECT_DIR/thesis-output/{project}"
```

If no project exists, redirect to `/thesis:init`.

### Step 2: Determine Next Action

Based on current_step and input_mode in SOT:

| Current Position | Action |
|-----------------|--------|
| Step 0 (fresh) | Begin Phase 0 initialization |
| Phase 0-A steps | Topic exploration with @topic-explorer |
| Phase 0-D steps | Learning mode with Agent Team |
| HITL-1 | Present research question candidates for user approval |
| Wave 1-5 steps | Literature review with Agent Teams |
| Gate steps | Run cross-validation gate |
| HITL-2+ | Present results for user review |
| Phase 2 steps | Research design with Agent Team |
| Phase 3 steps | Thesis writing with Agent Team |
| Phase 4 steps | Publication strategy |

### Step 3: Execute via Orchestrator

Invoke the thesis-orchestrator as a sub-agent. Pass the full execution context:

```
Agent: subagent_type="thesis-orchestrator", prompt="
  Project directory: thesis-output/{project}
  Current step: {current_step} (from SOT)
  Current phase: {phase}
  Execution mode: {execution_mode}
  Research topic: {research_question}

  Execute the next step(s) following your Execution Protocol.
  For team-based steps, use Tier 1 (Agent Team) first.
  Report back: completed steps, outputs created, any gate results.
"
```

The orchestrator will:
1. Determine execution tier (Team / Sub-agent / Direct) based on phase
2. Create Agent Team for wave/phase steps, or call sub-agents for sequential steps
3. Execute in English, validate output (L0 Anti-Skip + pACS)
4. Call @translator for Korean pair
5. Update SOT (outputs, current_step, active_team)
6. Return execution summary

**Do NOT perform orchestrator duties directly.** Always delegate to the thesis-orchestrator agent, which has the full tool set (TeamCreate, TaskCreate, SendMessage, TaskList, TaskUpdate) and execution protocol.

### Step 4: Report Progress (Korean)

After each step completion, show:
- Completed step description
- Current progress (step/total, percentage)
- Next step preview
- Any quality gate results
