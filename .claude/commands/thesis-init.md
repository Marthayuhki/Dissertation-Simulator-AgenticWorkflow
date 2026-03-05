---
description: Initialize a new doctoral thesis research project. Sets up the project directory, SOT (session.json), checklist, and external memory files.
---

# Thesis Initialization

You are starting a new doctoral thesis research project.

## Protocol

### Step 1: Gather User Input

Ask the user (in Korean) for:

1. **Research topic or question**: What is the research about?
2. **Research type** (select one):
   - Quantitative Research (양적연구)
   - Qualitative Research (질적연구)
   - Mixed Methods Research (혼합연구)
   - Undecided (아직 미정)
3. **Academic field** (select one):
   - Business/Economics (경영학/경제학)
   - Social Sciences (사회과학)
   - Humanities (인문학)
   - Natural Sciences/Engineering (자연과학/공학)
   - Medical/Health Sciences (의학/보건학)
   - Education (교육학)
   - Other (기타)
4. **Input mode**:
   - Mode A: Start with research topic (Default)
   - Mode B: Start with research question
   - Mode C: Have existing literature review
   - Mode D: Learning mode
   - Mode E: Upload prior papers
   - Mode F: Upload research proposal
   - Mode G: Custom input

### Step 2: Initialize Project

The `--execution-mode` value comes from the user's mode selection in `/start` Step 3.5.

```bash
python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/scripts/checklist_manager.py \
  --init \
  --project-dir "$CLAUDE_PROJECT_DIR/thesis-output/{sanitized-topic-name}" \
  --project-name "{topic}" \
  --research-type {type} \
  --input-mode {mode} \
  --execution-mode {execution_mode}
```

Where `{execution_mode}` maps from the user's selection:
- Mode 1 (Interactive) → `interactive`
- Mode 2 (Autopilot) → `autopilot`
- Mode 3 (ULW) → `ulw`
- Mode 2+3 → `autopilot+ulw`

### Step 3: Set Orchestrator Environment

```bash
export THESIS_ORCHESTRATOR=1
```

### Step 4: Confirm to User (Korean)

Display:
- Created project directory and structure
- Selected settings (research type, input mode, academic field, **execution mode**)
- Total workflow steps (210)
- Next step preview

### Step 5: Auto-Continue to Workflow

After displaying the confirmation, **automatically** execute the `/thesis-start` protocol without requiring the user to manually invoke it. This ensures a seamless transition from initialization to workflow execution.

Do NOT stop and wait for user input here — proceed directly to `/thesis-start`.
