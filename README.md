# Dissertation Simulator

**AI 에이전트 48개가 협업하는 210-step 박사 논문 연구 시뮬레이션 시스템.**

주제 탐색에서 학술지 투고까지, 박사 논문 연구의 전 과정을 AI 에이전트가 지원합니다.
문헌 검토(5 Wave) → 연구 설계(양적/질적/혼합) → 논문 집필 → 출판 전략의 4단계로 구성되며,
5개 Cross-Validation Gate와 9개 HITL(Human-In-The-Loop) 체크포인트가 학술적 엄밀성을 보장합니다.

> 이 시스템은 [AgenticWorkflow](AGENTICWORKFLOW-ARCHITECTURE-AND-PHILOSOPHY.md) — 만능줄기세포 프레임워크에서 태어난 자식 시스템입니다.
> 부모의 전체 DNA(절대 기준, 품질 보장, 안전장치, 기억 체계)를 상속하면서, 박사 논문 도메인에 특화된 아키텍처를 갖습니다.

## Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (v1.0+)
- Claude Pro/Max/Team/Enterprise 구독 (API 호출에 필요)

## 빠른 시작

```bash
# 1. 프로젝트 클론
git clone https://github.com/cysinsight/Dissertation-Simulator-AgenticWorkflow.git
cd Dissertation-Simulator-AgenticWorkflow

# 2. Claude Code 실행
claude

# 3. 시작 (스마트 라우터가 자동으로 적절한 진입점을 선택합니다)
/start
```

## 워크플로우 구조

```
Phase 0: 초기화 + 주제 탐색         (Step 1-38)    ── HITL-0/1 ──▶
Phase 1: 문헌 검토                  (Step 39-104)
  ├── Wave 1: 기초 검색 (4 agents)  ── Gate-1 ──▶
  ├── Wave 2: 심층 분석 (4 agents)  ── Gate-2 ──▶
  ├── Wave 3: 비판적 분석 (4 agents) ── Gate-3 ──▶
  ├── Wave 4: 통합 합성 (2 agents)  ── Gate-4 ──▶
  └── Wave 5: 품질 보증             ── HITL-2 ──▶ (Context Reset 1)
Phase 2: 연구 설계                  (Step 105-132)  ── HITL-3/4 ──▶ (Context Reset 2)
  ├── Quantitative Path (5 agents)
  ├── Qualitative Path (4 agents)
  └── Mixed Methods Path (2 agents)
Phase 3: 논문 집필                  (Step 133-168)  ── HITL-5/6/7 ──▶ (Context Reset 3)
Phase 4: 출판 전략                  (Step 169-180)  ── HITL-8 ──▶ (Context Reset 4)
Translation: 한국어 번역             (Step 181-210)
```

## 핵심 특징

| 특징 | 설명 |
|------|------|
| **48개 전문 에이전트** | 문헌 검색·분석·연구 설계·작성·출판 각 과정에 전문화된 AI 에이전트 |
| **GRA 3계층 품질 보장** | Agent Self-Verification → Cross-Validation Gate → SRCS 통합 평가 |
| **9개 HITL 체크포인트** | 연구 방향·방법론·최종 산출물에 대한 인간 연구자의 승인 |
| **7가지 Input Mode** | 주제(A), 연구질문(B), 기존문헌(C), 학습(D), 선행논문(E), 제안서(F), 커스텀(G) |
| **GroundedClaim 스키마** | 43개 고유 prefix, 6가지 claim 유형, Hallucination Firewall |
| **3-tier Fallback** | Team → Sub-agent → Direct 실행으로 복원력 보장 |
| **Context Reset Model** | 4개 HITL 지점에서 안전한 컨텍스트 리셋 + 3-File Memory로 복원 |
| **25개 Slash Commands** | `/thesis-init`, `/thesis-start`, `/thesis-status` 등 전체 워크플로우 제어 |

## 프로젝트 구조

```
Dissertation-Simulator-AgenticWorkflow/
│
│  ── 자식 시스템 (Dissertation Simulator) 문서 ──
├── README.md                                        ← 이 파일
├── DISSERTATION-SIMULATOR-ARCHITECTURE-AND-PHILOSOPHY.md  ← 도메인 고유 아키텍처
├── DISSERTATION-SIMULATOR-USER-MANUAL.md             ← 사용자 매뉴얼
│
│  ── 부모 프레임워크 (AgenticWorkflow) 문서 ──
├── AGENTICWORKFLOW-ARCHITECTURE-AND-PHILOSOPHY.md    ← 프레임워크 설계 철학
├── AGENTICWORKFLOW-USER-MANUAL.md                    ← 프레임워크 사용법
├── DECISION-LOG.md                                   ← 설계 결정 로그 (ADR-001~055)
├── soul.md                                           ← DNA 유전 철학
│
│  ── AI 에이전트 지시서 ──
├── CLAUDE.md                 # Claude Code 전용 지시서
├── AGENTS.md                 # 모든 AI 에이전트 공통 지시서 (Hub)
├── GEMINI.md                 # Gemini CLI 전용 (Spoke)
│
│  ── 논문 워크플로우 인프라 ──
├── .claude/
│   ├── settings.json         # Hook 설정
│   ├── agents/               # 51개 에이전트 (기반 3 + 논문 48)
│   │   ├── thesis-orchestrator.md    (총괄 조율)
│   │   ├── literature-searcher.md    (문헌 검색)
│   │   ├── synthesis-agent.md        (통합 합성)
│   │   └── ... (48개 논문 전문 에이전트)
│   ├── commands/              # 27개 Slash Commands (시스템 2 + 논문 25)
│   ├── hooks/scripts/         # 49개 스크립트 (프로덕션 35 + 테스트 14)
│   │   ├── checklist_manager.py      (논문 SOT 관리)
│   │   ├── query_workflow.py         (워크플로우 관측성)
│   │   ├── validate_grounded_claim.py (claim 검증)
│   │   ├── fallback_controller.py    (3-tier Fallback)
│   │   ├── compute_srcs_scores.py    (SRCS 점수 계산)
│   │   └── ... (검증·안전·컨텍스트 보존 스크립트)
│   └── skills/
│       ├── workflow-generator/  # 워크플로우 설계·생성
│       ├── doctoral-writing/    # 박사급 학술 글쓰기
│       ├── skill-creator/       # 스킬 메타 생성기
│       └── subagent-creator/    # 에이전트 메타 생성기
├── tests/e2e/                 # E2E 통합 테스트 (5 Track, 108+ 테스트)
├── prompt/
│   └── workflow.md            # 210-step 워크플로우 정의
└── thesis-output/             # 논문 산출물 (런타임 생성)
    └── [project-name]/
        ├── session.json       # 논문 SOT
        ├── todo-checklist.md  # 150-step 체크리스트
        ├── research-synthesis.md  # 연구 합성
        ├── wave-results/      # Wave별 산출물
        └── checkpoints/       # 체크포인트
```

## 품질 보장 체계 (GRA)

Grounded Research Architecture — 3계층 품질 보장:

```
Layer 1: Agent Self-Verification
  └── GroundedClaim 스키마 (id, text, sources[], confidence, verification)
  └── Hallucination Firewall ("all studies agree" 등 차단)
  └── Claim 유형별 최소 confidence (FACTUAL:95, EMPIRICAL:85, THEORETICAL:75)

Layer 2: Cross-Validation Gates (5개)
  └── Gate 1-4: Wave 간 claim 품질 교차 검증
  └── Gate 5: 연구 설계 최종 검증

Layer 3: SRCS Unified Evaluation
  └── 4축: Source · Rigor · Confidence · Specificity
  └── Claim 유형별 차등 가중치 (EMPIRICAL vs THEORETICAL vs FACTUAL)
  └── 75점 임계값 — 미달 claim 플래그
```

## 부모-자식 문서 분리 패턴

이 프로젝트는 "만능줄기세포" (AgenticWorkflow)와 그로부터 태어난 "자식 시스템" (Dissertation Simulator)을 구분합니다.
부모 문서(`AGENTICWORKFLOW-*.md`)는 방법론/프레임워크를, 자식 문서(`DISSERTATION-SIMULATOR-*.md`)는 도메인 고유 아키텍처를 기술합니다.
이 분리는 자식 시스템이 독립적으로 이해·운영될 수 있게 합니다.

## 문서 읽기 순서

| 순서 | 문서 | 목적 |
|------|------|------|
| 1 | **README.md** (이 파일) | 프로젝트 개요와 빠른 시작 |
| 2 | [`DISSERTATION-SIMULATOR-USER-MANUAL.md`](DISSERTATION-SIMULATOR-USER-MANUAL.md) | 논문 워크플로우 사용법 |
| 3 | [`DISSERTATION-SIMULATOR-ARCHITECTURE-AND-PHILOSOPHY.md`](DISSERTATION-SIMULATOR-ARCHITECTURE-AND-PHILOSOPHY.md) | 도메인 고유 아키텍처와 설계 철학 |
| 4 | [`DECISION-LOG.md`](DECISION-LOG.md) | 설계 결정의 맥락과 근거 |
| - | [`AGENTICWORKFLOW-ARCHITECTURE-AND-PHILOSOPHY.md`](AGENTICWORKFLOW-ARCHITECTURE-AND-PHILOSOPHY.md) | (참고) 부모 프레임워크 설계 철학 |
| - | [`AGENTICWORKFLOW-USER-MANUAL.md`](AGENTICWORKFLOW-USER-MANUAL.md) | (참고) 부모 프레임워크 사용법 |
| - | [`soul.md`](soul.md) | (참고) DNA 유전 철학 |

## 절대 기준

AgenticWorkflow에서 상속한 최상위 규칙:

1. **품질 최우선** — 토큰 비용, 속도보다 학술적 엄밀성이 유일한 기준
2. **단일 파일 SOT** — `session.json`에 모든 논문 상태 집중. 동시 수정 금지
3. **코드 변경 프로토콜 (CCP)** — 의도 파악 → 영향 범위 분석 → 변경 설계
4. **English-First 강제 (MANDATORY)** — 모든 에이전트 작업·산출물은 영어로 수행. 영어 완성 → `@translator`로 한국어 번역 (순서 역전 불가). 절대 기준 1(품질)의 직접적 구현 (ADR-027a)
5. **품질 > SOT, CCP** — 충돌 시 품질이 우선

## AI 도구 호환성

| AI CLI 도구 | 지시서 파일 | 자동 적용 |
|------------|-----------|----------|
| Claude Code | `CLAUDE.md` | Yes |
| Gemini CLI | `GEMINI.md` | Yes |
| Codex CLI | `AGENTS.md` | Yes |
| Copilot CLI | `.github/copilot-instructions.md` | Yes |

상세: `AGENTS.md` (Hub — 방법론 SOT)

## License

[MIT License](LICENSE) — Copyright (c) 2026 최윤식 (Yoonsik, Choi)
