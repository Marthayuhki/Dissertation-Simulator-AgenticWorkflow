# Quality Gates & P1 Validation

> 이 문서는 5계층 품질 보장 아키텍처와 P1 할루시네이션 봉쇄의 상세 명세이다.
> CLAUDE.md에서 분리됨 — 품질 게이트 설계·디버깅·확장 시 참조.

## 5계층 품질 보장 아키텍처 (L0 → L1 → L1.5 → L1.7 → L2)

Orchestrator는 `current_step`을 순차적으로만 증가. 각 단계 완료 시 최대 5계층 검증을 통과해야 진행한다:

1. **L0 Anti-Skip Guard** (결정론적) — 산출물 파일 존재 + 최소 크기(100 bytes). Hook 계층의 `validate_step_output()` 함수가 수행.
2. **L1 Verification Gate** (의미론적) — 산출물이 `Verification` 기준을 100% 달성했는지 에이전트 자기 검증. 실패 시 해당 부분만 재실행(최대 10회). `verification-logs/step-N-verify.md`에 기록.
3. **L1.5 pACS Self-Rating** (신뢰도) — Pre-mortem Protocol 수행 후 F/C/L 3차원 채점. `pacs-logs/step-N-pacs.md`에 기록. RED(< 50) 시 재작업.
4. **L1.7 pCCS per-claim confidence** (Tier A steps only) — P1 Sandwich 아키텍처로 개별 claim의 신뢰도를 정량화. AlphaFold pLDDT에서 영감. 상세: §(19).
5. **[L2 Adversarial Review]** (선택적) — `Review:` 필드 지정 단계에서 `@reviewer`/`@fact-checker`/`@code-reviewer`가 산출물을 독립적으로 적대적 검토. Review FAIL 시 Adversarial Dialogue(반복 루프) 시작. 고위험 단계만. 상세: `AGENTS.md §5.5`, `docs/protocols/adversarial-dialogue.md`

> `Verification` 필드가 없는 단계는 Anti-Skip Guard만으로 진행 (하위 호환). 상세: `AGENTS.md §5.3`, `§5.4`

---

## P1 할루시네이션 봉쇄 (Hallucination Prevention)

반복적으로 100% 정확해야 하는 작업을 Python 코드로 강제한다.

### (1) KI 스키마 검증
`_validate_session_facts()`가 knowledge-index 쓰기 직전 RLM 필수 키(session_id, tags, final_status, diagnosis_patterns 등 11개) 존재를 보장 — 누락 시 안전 기본값 채움.

### (2) 부분 실패 격리
`archive_and_index_session()`에서 archive 파일 쓰기 실패가 knowledge-index 갱신을 차단하지 않음 — RLM 핵심 자산 보호.

### (3) SOT 쓰기 패턴 검증
`setup_init.py`의 `_check_sot_write_safety()`가 Hook 스크립트에서 SOT 파일명 + 쓰기 패턴 공존을 AST 함수 경계 기반으로 탐지 (Tier 1: 비-SOT 스크립트의 SOT 참조 차단, Tier 2: SOT-aware 스크립트의 함수별 쓰기 패턴 검사).

### (4) SOT 스키마 검증
`validate_sot_schema()`가 워크플로우 state.yaml의 구조적 무결성을 8항목으로 검증:
- **S1-S6**: current_step 타입·범위, outputs 타입·키 형식, 미래 단계 산출물 탐지, workflow_status 유효값, auto_approved_steps 정합성
- **S7**: pacs 5개 필드 검증 (S7a dimensions F/C/L 0-100, S7b current_step_score 0-100, S7c weak_dimension F/C/L, S7d history dict→{score, weak}, S7e pre_mortem_flag string)
- **S8**: active_team 5개 필드 검증 (S8a name string, S8b status partial|all_completed, S8c tasks_completed list, S8d tasks_pending list, S8e completed_summaries dict→dict)

SessionStart와 Stop hook 양쪽에서 실행.

### (5) Adversarial Review P1 검증
`validate_review_output()`이 리뷰 보고서의 구조적 무결성을 검증:
- R1: 파일 존재
- R2: 최소 크기
- R3: 필수 섹션 4개
- R4: PASS/FAIL 명시적 추출
- R5: 이슈 테이블 ≥ 1행

`parse_review_verdict()` — regex로 이슈 심각도 카운트 추출.
`calculate_pacs_delta()` — Generator-Reviewer pACS 차이(Delta ≥ 15 → 재조정).
`validate_review_sequence()` — Review PASS → Translation 순서를 파일 타임스탬프로 강제.
독립 실행 스크립트: `validate_review.py`.

### (6) Translation P1 검증

**Layer 1a — 구조 검증 (T1-T9)**: `validate_translation_output()`이 번역 산출물을 7항목으로 검증:
- T1: 파일 존재, T2: 최소 크기, T3: 영어 원본 존재, T4: .ko.md 확장자, T5: 비-공백, T6: 헤딩 수 ±20%, T7: 코드 블록 수 일치

`check_glossary_freshness()` — glossary 타임스탬프 신선도 (T8).
`verify_pacs_arithmetic()` — 모든 pACS 로그의 min() 산술 정확성 (T9 — 범용).
`validate_verification_log()` — 검증 로그 V1a-V1e:
- V1a: 파일 존재, V1b: 기준별 PASS/FAIL 명시, V1c: 논리 일관성(FAIL 있으면 전체 PASS 불가)
- V1d: Evidence 품질 ≥ 20자 (피상적 증거 "ok", "checked" 방지)
- V1e: 복합 기준 탐지 (WARNING only — `and`, `+`, `및` 접속사)
`validate_translation.py`는 Review verdict=PASS를 필수 체크.
독립 실행 스크립트: `validate_translation.py`.

**Layer 1b — 콘텐츠 보존 검증 (T10-T12)**: `verify_translation_terms.py`가 영-한 번역의 콘텐츠 보존을 3항목으로 검증:
- T10: 용어집 준수 — glossary.yaml의 영어 용어가 한국어에서 올바르게 매핑되었는지 (regex 매칭)
- T11: 숫자/통계 보존 — 영어 원본의 모든 숫자(%, p-value, n=, 4자리 연도, 큰 수)가 한국어에 존재하는지
- T12: 인용 보존 — (Author, Year) 및 [N] 형식 인용이 한국어에 보존되었는지

P1 준수: 순수 Python regex/문자열 매칭 — LLM 추론 0%. 동일 입력 → 동일 결과.
Non-blocking: exit 0 (P1 compliant).
독립 실행 스크립트: `verify_translation_terms.py`.

**Layer 2 — 의미론적 검증 (선택)**: `@translation-verifier` 서브에이전트가 고중요도 단계에서 독립 pACS 평가.
- Fidelity (Ft), Naturalness (Nt), Completeness (Ct) 3축 평가
- Layer 1 결과와 교차 검증 (Agreement / Layer 1 only / Semantic only)
- pACS >= 0.85: PASS, 0.70-0.84: CONDITIONAL, < 0.70: FAIL

### (7) pACS P1 검증
`validate_pacs_output()`이 pACS 로그를 6항목으로 검증:
- PA1: 파일 존재, PA2: 최소 크기 50 bytes, PA3: 차원 점수 ≥ 3개(0-100 범위), PA4: Pre-mortem 섹션 존재, PA5: min() 산술 정확성, PA7: RED 차단(pACS < 50 → FAIL)
- PA6(선택): 점수-색상 영역 정합성

독립 실행 스크립트: `validate_pacs.py`.

### (8) L0 Anti-Skip Guard 코드 구현
`validate_step_output()` — L0 검증 3항목:
- L0a: SOT outputs.step-N 경로의 파일 존재
- L0b: 파일 크기 ≥ MIN_OUTPUT_SIZE(100 bytes)
- L0c: 비-공백 확인

`validate_pacs.py --check-l0`으로 pACS + L0 동시 검증 가능.

### (9) Predictive Debugging P1 검증

**Layer 1 — Historical (자동)**: `validate_risk_scores()` — risk-scores.json 6항목:
- RS1: 필수 키, RS2: data_sessions 정수, RS3: risk_score 범위, RS4: error_count 산술 정합, RS5: resolution_rate 범위, RS6: top_risk_files 정렬+존재

**Layer 2 — Proactive (on-demand `/predict-failures`)**:
P1 Sandwich 아키텍처로 할루시네이션 봉쇄:
1. `scan_code_structure.py` — Phase A: F1-F7 패턴 스캔 → fp-code-map.json (ground truth)
2. `@failure-predictor` — Phase B-1: 교차 도메인 패턴 기반 LLM 예측
3. `validate_failure_predictions.py` — Phase C-1: FP1-FP7 구조 검증 (할루시네이션 제거)
   - FP1: 인용 파일이 fp-code-map.json에 존재, FP2: 라인 번호 범위 내, FP3: 날조 참조 제거
   - FP4: severity ∈ {Critical, Warning, Info}, FP5: 필수 필드 존재, FP6: category ∈ F1-F7
   - FP7: 유효 예측 ≥ 1개
4. `@failure-critic` — Phase B-2: 적대적 비평 (CONFIRM/DISMISS/ESCALATE)
5. `validate_failure_predictions.py --critic` — Phase C-2: 비평 형식 검증
6. `generate_failure_report.py` — Phase D: 결정론적 합성 → active-risks.md + index.jsonl (SOT)

독립 실행 스크립트: `scan_code_structure.py`, `extract_json_block.py`, `validate_failure_predictions.py`, `generate_failure_report.py`.
슬래시 커맨드: `/predict-failures`.

H-1/H-2 할루시네이션 봉쇄: `extract_json_block.py`가 LLM→P1 핸드오프 구간에서 JSON 추출을 결정론적으로 수행. LLM이 JSON을 추출·복사·타이핑하지 않음.
H-3 파일 존재 검증: `generate_failure_report.py`가 critic additions의 파일 존재를 `os.path.exists()`로 검증. 날조 파일 경로 제거.
H-4 FP7 임계값: `MIN_VALID_PREDICTIONS = 3` — @failure-predictor Absolute Rule 5와 P1 검증 기준 통일.

### (10) Retry Budget P1 검증
`validate_retry_budget.py` — 재시도 예산 결정론적 판정:
- RB1: 카운터 파일 읽기, RB2: ULW 활성 감지, RB3: 예산 비교 (`retries_used < max_retries`)
- `max_retries`: ULW 활성 시 15, 비활성 시 10 (`ULW_MAX_RETRIES=15`, `DEFAULT_MAX_RETRIES=10`)
- `--check-and-increment` 모드로 확인+카운터 atomic write 증가 일괄 처리
- `--gate dialogue` 지원 (dialogue-logs/ 디렉터리 기반 카운터)

### (11) Abductive Diagnosis P1 검증
`validate_diagnosis_log()` — 진단 로그 10항목:
- AD1: 파일 존재, AD2: 최소 크기 100 bytes, AD3: Gate 필드 일치, AD4: 선택 가설 존재, AD5: 증거 ≥ 1개, AD6: Action Plan 존재, AD7: 순방향 참조 금지, AD8: 가설 ≥ 2개, AD9: 선택 가설 일관성, AD10: 이전 진단 참조(재시도 > 0)

`diagnose_failure_context()` — 사전 증거 수집 (retry_history, upstream_evidence, hypothesis_priority, fast_path, raw_evidence). Fast-Path(FP1-FP3)로 결정론적 단축.
독립 실행 스크립트: `diagnose_context.py`(사전 분석), `validate_diagnosis.py`(사후 검증).

### (12) Cross-Step Traceability P1 검증
`validate_cross_step_traceability()` — 교차 단계 추적성 5항목:
- CT1: trace 마커 존재, CT2: 참조 단계 산출물 존재, CT3: 섹션 ID 해결(Warning), CT4: 최소 밀도 ≥ 3, CT5: 순방향 참조 금지

독립 실행 스크립트: `validate_traceability.py`.

### (13) Domain Knowledge Structure P1 검증
`validate_domain_knowledge()` — domain-knowledge.yaml 7항목:
- DK1: 파일 존재+YAML 유효, DK2: metadata 필수 키, DK3: entities 구조, DK4: relations 참조 무결성, DK5: constraints 구조, DK6: 산출물 DKS 참조 해결, DK7: 제약 조건 비위반

독립 실행 스크립트: `validate_domain_knowledge.py`. 선택적 — 모든 워크플로우가 필요로 하지 않음.

### (14) Gate Report Persistence (MANDATORY)

Each Cross-Validation Gate MUST persist its validation result to disk:

```bash
python3 .claude/hooks/scripts/validate_wave_gate.py \
  --project-dir {dir} --gate {gate-name} \
  --output-json {dir}/gate-reports/{gate-name}-report.json
```

The `--output-json` flag writes the full validation result (status, gate, files_checked, total_claims, errors, warnings, file_results) to the specified path. The report path MUST be recorded in session.json via `record_gate_result(report_path=...)`.

Gate retry reports use the naming convention: `gate-reports/{gate-name}-retry-{K}-report.json`.

### (15) Workflow.md DNA Inheritance P1 검증
`validate_workflow_md()` — 9항목:
- W1: 파일 존재, W2: 최소 크기 500 bytes, W3: `## Inherited DNA` 헤더, W4: Inherited Patterns 테이블 ≥ 3행, W5: Constitutional Principles 섹션, W6: CAP 참조, W7: CT Verification-Validator 정합성, W8: DKS Verification-Validator 정합성, W9: English-First Execution 패턴 존재 (ADR-027a)

독립 실행 스크립트: `validate_workflow.py`. workflow-generator 완료 후 수동 호출.

### (16) Criteria-Evidence Cross-Check P1 검증 (할루시네이션 탐지)

에이전트의 Verification PASS 선언을 **실제 산출물 파일에 대해 결정론적으로 재검증**. Agent PASS + P1 FAIL → `HALLUCINATION_DETECTED`.

`validate_criteria_evidence.py` — 5항목:
- VE1: Section/heading count — `re.findall(r"^#{1,6}\s+.+$")` heading 수와 기준 명시 숫자 비교
- VE2: Placeholder absence — `example.com`, `TODO`, `TBD`, `FIXME`, `Lorem ipsum` 탐지
- VE3: Item/row/element count — 리스트 항목(`^[-*+]`) + 테이블 행(`^\|`) 카운트
- VE4: `[trace:step-N]` marker count — 추적성 마커 수량 검증
- VE5: Field/keyword presence — 기준 명시 필드(name, price 등) 존재 여부

P1 준수: 순수 Python regex/문자열 매칭 — LLM 추론 0%. 동일 입력 → 동일 결과.
Non-blocking: exit 0 (P1 compliant). SOT Read-only.
독립 실행 스크립트: `validate_criteria_evidence.py`. Orchestrator가 Verification Gate 후 호출.

### (17) Fork Safety P1 검증 (FS-1~FS-5)

`context: fork` 선언 파일의 **포크 안전성을 결정론적으로 검증**. SOT 손상·HITL 우회·도구 미지원 포크를 사전 차단.

`validate_fork_safety.py` — 5항목:
- FS-1: `context: fork` frontmatter 탐지 (YAML 파싱)
- FS-2: SOT 쓰기 패턴 부재 검증 — `session.json`, `state.yaml`, `checklist_manager --advance/--gate/--init` 등
- FS-3: Bash 의존성 호환 에이전트 검증 — `allowed_tools` 중 Bash 포함 여부
- FS-4: HITL 패턴 부재 검증 — `AskUserQuestion`, `human approval` 등
- FS-5: `agent:` 지정 시 에이전트 존재 및 필수 도구 보유 검증

P1 준수: 순수 Python regex/YAML 파싱 — LLM 추론 0%. 동일 입력 → 동일 결과.
CLI 도구 (Hook 아님): exit 0 (PASS), exit 1 (FAIL). SOT Read-only.
독립 실행 스크립트: `validate_fork_safety.py`. skill-creator/subagent-creator 완료 후 호출, `--all`로 전체 감사.

### (18) Adversarial Dialogue P1 검증 (DA1-DA5, CI1-CI4)

**L2 반복 루프 — Adversarial Dialogue**의 무결성을 결정론적으로 검증. Orchestrator가 Dialogue 각 라운드 후 호출.

**Dialogue State 검증 (DA1-DA5)**: `validate_dialogue_state.py` — 5항목:
- DA1: `dialogue-logs/step-N-rK-{fc|rv|cr}.md` 파일 존재 (domain에 따른 파일 세트)
- DA2: 현재 라운드 draft 타임스탬프가 이전 라운드 critic 보고서보다 최신 (Generator가 피드백 반영했는지)
- DA3: 최종 summary.md consensus verdict와 마지막 Critic 보고서 일관성
- DA4: `session.json.dialogue_state` SOT 필드 정합 (rounds_used, status, outcome)
- DA5: rounds_used ≤ max_rounds (예산 초과 방지)

**Claim Inheritance 검증 (CI1-CI4)**: `validate_claim_inheritance.py` — 4항목 (Round 2+, Research 도메인):
- CI1: 상속 claim이 이전 라운드 @fact-checker 보고서에 실제 존재
- CI2: 상속 claim의 이전 판정이 상속 가능 (Verified/Partially Verified만 — False/Unable-to-Verify/Outdated 금지)
- CI3: 현재 라운드 총 claim 수 ≥ 이전 라운드 (claim 소실 방지)
- CI4: 상속 claim이 수정된 단락에서 온 경우 상속 금지 (재검증 강제)

P1 준수: 순수 Python regex/파일시스템 — LLM 추론 0%. 동일 입력 → 동일 결과.
Non-blocking: exit 0 (P1 compliant). SOT Read-only.
독립 실행 스크립트: `validate_dialogue_state.py`, `validate_claim_inheritance.py`. 상세: `docs/protocols/adversarial-dialogue.md`

### (19) pCCS — predicted Claim Confidence Score (L1.7)

AlphaFold의 pLDDT (per-residue confidence)에서 영감을 받은 **per-claim 신뢰도 정량화** 시스템. GroundedClaim이 있는 Tier A 단계(88개)에서만 실행.

**P1 Sandwich 아키텍처** (Predictive Debugging과 동일 패턴):

1. `compute_pccs_signals.py` — **Phase A**: P1 signal 추출 → claim-map.json
   - A1: Citation 존재 (+30), A2: Trace marker (+10), A3: Blocked 절대 표현 (-40)
   - A4: 통계 무출처 (-20), A5: Confidence 명시 (+10), A6: Type 인식 (+10)
   - P1 score = 50(base) + signal weights, clamp [0, 100]

2. `@claim-quality-evaluator` — **Phase B-1**: LLM 시맨틱 평가 (Specificity/Evidence/Logic/Contribution, 0-25 각)
3. `validate_pccs_assessment.py` — **Phase C-1**: CA1-CA5 구조 검증 (claim ID 존재, 점수 범위, 필수 필드, 비어있지 않음, 중복 없음)
4. `@claim-quality-critic` — **Phase B-2**: 적대적 교차 검증 (과신 도전, 누락 이슈 탐지)
5. `validate_pccs_assessment.py --mode critic` — **Phase C-2**: CA1-CA5 비평 검증
6. `generate_pccs_report.py` — **Phase D**: P1 합성 — 최종 pCCS 점수 계산

**pCCS Fusion Formula** (Phase D, ALL arithmetic is Python):
```
calibrated = min(raw_agent - cal_delta, CEILING[type])
pccs = p1_score × w_p1 + calibrated × w_agent
if blocked: pccs = min(pccs, 40.0)
```

**Claim-type Adaptive Weights**:

| Type | w_p1 | w_agent | Ceiling |
|------|------|---------|---------|
| FACTUAL | 0.50 | 0.50 | 95 |
| EMPIRICAL | 0.45 | 0.55 | 85 |
| THEORETICAL | 0.25 | 0.75 | 75 |
| METHODOLOGICAL | 0.35 | 0.65 | 80 |
| INTERPRETIVE | 0.20 | 0.80 | 70 |
| SPECULATIVE | 0.15 | 0.85 | 60 |
| UNKNOWN | 0.35 | 0.65 | 80 |

**Color Classification**: GREEN ≥ 70, YELLOW ≥ 50, RED < 50.

**Decision Matrix** (P1-computed, Orchestrator executes):
- 0 actionable RED → `proceed`
- 1-2 RED → `rewrite_claims` (specific claims only)
- 3+ RED → `rewrite_step` (entire step, counts against retry budget)
- SPECULATIVE exception: only pCCS < 40 triggers RED (not < 50)

**Calibration** (`pccs_calibration.py`):
- Tier 1: @fact-checker verdicts (Verified→90, Partial→60, Unable→40, Outdated→30, False→10)
- Tier 2: L1 Verification (PASS→85, FAIL→30)
- Weighted: `cal_delta = (tier1_delta × 2.0 + tier2_delta × 1.0) / 3.0`

**P1 Structural Validation** (`validate_pccs_output.py` — PC1-PC7):
- PC1: Required fields, PC2: Score ranges [0,100], PC3: Color classification
- PC4: Decision matrix consistency, PC5: Summary counts, PC6: Unique claim IDs
- PC7: Mode field valid (FULL or DEGRADED)

**pCAE** (predicted Claim Alignment Error — inter-claim consistency):
- E2: Duplicate detection (implemented) — same source cited by multiple claims
- E4: Critic additions (implemented) — `@claim-quality-critic`의 `additions` 배열이 pCAE에 통합
- E1/E3: Numeric contradictions, source conflicts (not yet implemented)

**Mode Selection** (thesis-orchestrator.md):
- **FULL mode**: Phase A→B-1→C-1→B-2→C-2→D (Gate steps + high-importance)
- **DEGRADED mode**: Phase A→D only (routine steps — structural scoring only, no semantic evaluation)

**Pipeline Runner** (`run_pccs_pipeline.py` — 할루시네이션 방지 단일 진입점):
- Orchestrator가 8-10개 CLI 명령을 개별 실행하던 패턴을 1~3개 호출로 응축
- **DEGRADED**: `run_pccs_pipeline.py --mode degraded --file {f} --step {N} --project-dir {dir}` (단일 호출)
  - Phase A → Calibration → Phase D → PC1-PC7 → SOT 자동 갱신
- **FULL**: 3개 호출이 2개 LLM 서브에이전트 호출을 브래킷
  - `--phase prepare` → Phase A + Calibration → claim-map.json
  - `--phase after-b1` → B-1 JSON 추출 + CA1-CA8 검증
  - `--phase finalize` → B-2 JSON 추출 + CA1-CA5 + Phase D + PC1-PC7 + SOT
- Calibration이 pipeline 내부에서 항상 실행되므로 누락 불가능 (disconnected loop fix)

**Report 필드**:
- `mode`: "FULL" 또는 "DEGRADED" — 실행 모드 추적
- `calibration`: `{cal_delta, total_samples}` — 교정 메타데이터
- `summary.disagreement_count`: evaluator-critic 고분쟁 claim 수
- `claims[].high_disagreement`: |eval_score - critic_score| ≥ 20 여부 (FULL only)

**SOT Integration**: `checklist_manager.py --update-pccs-cal` writes to `session.json.pccs` block (cal_delta, last_step, history). History에 mode 기록.
**RLM Integration**: `restore_context.py._surface_pccs_state()` surfaces cal_delta + last 3 step results (with mode) as IMMORTAL section.

17→7 Canonical Type Mapping: `_claim_patterns.py.CLAIM_TYPE_TO_CANONICAL` maps actual thesis types (ANALYTICAL, THEOLOGICAL, etc.) to 7 canonical types.

독립 실행 스크립트: `compute_pccs_signals.py`, `generate_pccs_report.py`, `validate_pccs_output.py`, `validate_pccs_assessment.py`, `pccs_calibration.py`, `run_pccs_pipeline.py`.
서브에이전트: `@claim-quality-evaluator` (Phase B-1), `@claim-quality-critic` (Phase B-2).
