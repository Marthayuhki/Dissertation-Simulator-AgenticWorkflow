---
description: Display current thesis workflow status including progress, gates, checkpoints, and outputs.
---

# Thesis Status

Display comprehensive workflow status in Korean.

## Protocol

### Step 1: Read SOT

```bash
python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/scripts/checklist_manager.py \
  --status \
  --project-dir "$CLAUDE_PROJECT_DIR/thesis-output/{project}"
```

### Step 2: Display Status (Korean)

```
## 논문 연구 워크플로우 상태

- 프로젝트: {project_name}
- 상태: {status}
- 진행률: {current_step}/{total_steps} ({progress_pct}%)
- 현재 단계: {current_phase}
- 연구 유형: {research_type}
- 입력 모드: Mode {input_mode}
- 실행 모드: {execution_mode}
- 게이트 통과: {gates_passed}
- HITL 체크포인트: {hitls_completed}
- 영어 산출물: {outputs_en}개
- 한국어 번역: {outputs_ko}개
- 활성 팀: {active_team or "없음"}
- Fallback 이력: {fallback_count}건
- 체크포인트: {checkpoint_count}개
```

### Step 3: Show Next Steps

Based on current position, display the next 3 pending steps from the checklist.
