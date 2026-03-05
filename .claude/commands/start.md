---
description: Smart router for thesis workflow. Detects project state and routes to the correct entry point (init/start/resume).
---

# Workflow Start Router

You are the smart entry point for the thesis workflow. Detect the current state and route to the appropriate action.

## Natural Language Triggers

This command is invoked when the user says any of these (in Korean or English):
- "시작하자", "시작", "시작해", "시작해줘", "시작합시다"
- "start", "let's start", "begin"
- "워크플로우를 시작하자", "워크플로우 시작"
- "논문 작업을 하자", "논문 작업 시작", "논문을 시작하자"
- "논문 시뮬레이터를 시작하자", "시뮬레이터 시작"
- "시뮬레이션을 시작하자", "시뮬레이션 시작"
- "연구를 시작하자", "연구 시작"
- Or any variation that signals "I want to begin/continue the thesis workflow"

## Routing Protocol

### Step 1: Check for Existing Projects

```bash
ls thesis-output/ 2>/dev/null
```

### Step 2: Route Based on State

```
[No thesis-output/ directory OR empty]
  → Route A: First-time initialization
  → Execute /thesis-init protocol

[Single project exists]
  → Read SOT: checklist_manager.py --status --project-dir thesis-output/{project}
  → If SOT readable and workflow in-progress:
    → Route B: Continue workflow
    → Execute /thesis-start protocol
  → If SOT unreadable or corrupted:
    → Route C: Recovery mode
    → Execute /thesis-resume protocol

[Multiple projects exist]
  → List all projects with their status
  → Ask user which project to continue (Korean)
  → Then route to B or C based on selected project's state
```

### Step 3: Display Entry Banner (Korean)

Before routing, always display:

```
====================================
  Dissertation Simulator v1.0
  박사 논문 연구 시뮬레이터
====================================
```

### Step 3.5: User Mode Guide (Korean)

After the banner, present the user mode guide. The behavior depends on the route:

**Route A (New project):** Always display the full mode guide and ask for selection.

**Route B/C (Existing project):** Read the existing `execution_mode` from SOT first. Display the current mode and ask: "현재 모드: {mode}. 변경하시겠습니까? (Enter로 유지)" — only re-select if user requests a change.

#### Mode Guide Display (for Route A, or Route B/C when user wants to change):

```
┌─────────────────────────────────────────────────┐
│              실행 모드를 선택하세요              │
├──────────┬──────────────────────────────────────┤
│ 모드     │ 설명                                 │
├──────────┼──────────────────────────────────────┤
│ 1. 대화형 │ (기본) 각 단계마다 확인을 받으며     │
│ Interactive│ 진행합니다. 초보자에게 권장.         │
├──────────┼──────────────────────────────────────┤
│ 2. 자동   │ 사람 개입 지점(HITL)을 자동 승인     │
│ Autopilot │ 하여 무중단으로 실행합니다.           │
│           │ 품질 검증 Hook은 그대로 작동합니다.   │
├──────────┼──────────────────────────────────────┤
│ 3. 정밀   │ 최대 철저함으로 실행합니다.           │
│ ULW       │ 에러 해결까지 완벽 수행, 생략 없음.   │
│           │ Autopilot과 독립적으로 조합 가능.     │
└──────────┴──────────────────────────────────────┘
```

**Mode Selection Rules:**
1. Ask the user to choose a mode (1, 2, or 3) or combination (e.g., "2+3" for Autopilot + ULW)
2. If the user does not choose, default to **Interactive** (mode 1)
3. Pass the selected mode to `/thesis-init` (Route A) or update SOT directly (Route B/C)
4. The mode can be changed mid-workflow by the user at any time

**Activation Mapping:**

| Selection | Autopilot | ULW | Behavior |
|-----------|-----------|-----|----------|
| 1 (Interactive) | OFF | OFF | Every HITL requires manual approval |
| 2 (Autopilot) | ON | OFF | HITL auto-approved, standard thoroughness |
| 3 (ULW) | OFF | ON | HITL requires manual approval, maximum thoroughness |
| 2+3 (Autopilot + ULW) | ON | ON | Full automation with maximum thoroughness |

Then display the routing decision:

| Route | Display Message |
|-------|----------------|
| A (Init) | "새로운 논문 프로젝트를 시작합니다. 연구 주제와 설정을 입력해 주세요." |
| B (Continue) | "기존 프로젝트 '{name}'를 이어서 진행합니다. [Step {N}/{total} - {pct}%]" |
| C (Resume) | "프로젝트 '{name}'의 상태를 복원합니다..." |
| Multiple | "여러 프로젝트가 발견되었습니다. 어떤 프로젝트를 진행하시겠습니까?" |

### Step 4: Execute Routed Command

After routing decision, immediately execute the appropriate protocol:
- Route A → Follow `/thesis-init` protocol (gather user input, initialize)
- Route B → Follow `/thesis-start` protocol (read SOT, execute next step)
- Route C → Follow `/thesis-resume` protocol (recover state, then continue)
