---
description: "Predictive Failure Analysis — scan codebase and predict production failures using P1-sandwich architecture"
---

# /predict-failures — Predictive Failure Analysis

Performs a full codebase scan and predicts production failure areas using cross-domain
patterns from other systems. Uses a P1-sandwich architecture to prevent hallucinations:

```
P1 Scan (grounding) → @failure-predictor (LLM) → P1 Validation → @failure-critic (LLM) → P1 Synthesis
```

Results persist in `failure-predictions/` and are surfaced at every session start via RLM.

---

## Orchestration (main context executes — do NOT delegate to sub-agent)

Announce to user: "Starting Predictive Failure Analysis — full scan. This involves two LLM agents and P1 validation steps."

### Phase A: Code Structure Scan (P1 — establishes ground truth)

Run:
```bash
python .claude/hooks/scripts/scan_code_structure.py \
  --project-dir <ACTUAL_PROJECT_DIR> \
  --output .claude/context-snapshots/fp-code-map.json
```

Report to user:
- How many files were scanned
- Which F-categories have matches
- Any files with Critical-severity signals

**If Phase A fails**: Report the error to the user and STOP. Do not proceed without ground truth.

### Phase B-1: Failure Prediction (@failure-predictor)

Invoke `@failure-predictor` via Agent tool:
```
subagent_type: failure-predictor
prompt: |
  Read the code structure map at:
  <ACTUAL_PROJECT_DIR>/.claude/context-snapshots/fp-code-map.json

  Analyze the ENTIRE codebase for production failure risks using the F1-F7 taxonomy.
  Apply cross-domain patterns from other production systems.

  IMPORTANT:
  - Only cite files and line numbers from the code map
  - Output a JSON block with your predictions
  - Minimum 3 predictions required
```

**Save the agent's full text response** to `.claude/context-snapshots/fp-predictor-response.txt` using the Write tool (preserves raw response for debugging).

**Extract JSON deterministically** (P1 — prevents hallucination at LLM→P1 handoff):
```bash
python .claude/hooks/scripts/extract_json_block.py \
  --input .claude/context-snapshots/fp-predictor-response.txt \
  --output .claude/context-snapshots/fp-draft.json
```

**If extraction reports FAIL** (no valid JSON block found): Re-invoke @failure-predictor (same prompt), save new response, re-run extractor. If second attempt also fails: report to user and STOP.

### Phase C-1: Validate Predictor Output (P1 — FP1-FP7)

Run:
```bash
python .claude/hooks/scripts/validate_failure_predictions.py \
  --input .claude/context-snapshots/fp-draft.json \
  --code-map .claude/context-snapshots/fp-code-map.json \
  --output .claude/context-snapshots/fp-validated.json
```

Report to user:
- How many predictions passed validation
- How many were removed and why (FP1-FP6 violations)

**If fewer than 3 valid predictions remain** (FP7 threshold): Report the violation list to user and STOP. Do not proceed with insufficient predictions — re-run Phase B-1 or investigate predictor prompt.

### Phase B-2: Adversarial Critic (@failure-critic)

Invoke `@failure-critic` via Agent tool:
```
subagent_type: failure-critic
prompt: |
  Read the validated predictions at:
  <ACTUAL_PROJECT_DIR>/.claude/context-snapshots/fp-validated.json

  For each prediction:
  1. Read the referenced file at the referenced line
  2. Verdict: CONFIRM (verified), DISMISS (existing safeguard found), or ESCALATE (more severe than rated)
  3. Add any risks the predictor missed (additions)

  Output a JSON block with your judgments.
```

**Save the agent's full text response** to `.claude/context-snapshots/fp-critic-response.txt` using the Write tool.

**Extract JSON deterministically** (P1 — with critic fallback for robustness):
```bash
python .claude/hooks/scripts/extract_json_block.py \
  --input .claude/context-snapshots/fp-critic-response.txt \
  --output .claude/context-snapshots/fp-critic.json \
  --fallback-critic
```

The `--fallback-critic` flag ensures that if no valid JSON block is found, an empty critic response `{"judgments": [], "additions": []}` is generated deterministically by Python (never LLM-typed — prevents spelling errors like "judgements"). Report that critic review was skipped if fallback was used.

### Phase C-2: Validate Critic Output (P1 — format check)

Run:
```bash
python .claude/hooks/scripts/validate_failure_predictions.py \
  --critic \
  --input .claude/context-snapshots/fp-critic.json \
  --output .claude/context-snapshots/fp-critic-validated.json
```

### Phase D: Generate Report (P1 — synthesis + SOT update)

Run:
```bash
python .claude/hooks/scripts/generate_failure_report.py \
  --validated .claude/context-snapshots/fp-validated.json \
  --critic .claude/context-snapshots/fp-critic-validated.json \
  --project-dir <ACTUAL_PROJECT_DIR>
```

### Phase E: Report to User

Read `failure-predictions/active-risks.md`.

Present final summary:
- Total predictions confirmed, breakdown by severity (Critical / Warning / Info)
- How many were dismissed by @failure-critic
- Top 3 Critical risks: id, file, one-line summary
- Path to full archived report: `failure-predictions/YYYY-MM-DD.md`

---

## Error Recovery

| Failure point | Action |
|--------------|--------|
| Phase A fails | STOP — report scan error to user |
| Phase B-1 no JSON | Retry once; if still no JSON → STOP |
| Phase C-1 → <3 valid | STOP — report FP violations to user (FP7 threshold) |
| Phase B-2 fails | Skip critic; CONFIRM all validated predictions |
| Phase D fails | Report error; preserve temp files for debugging |

---

## Notes

- Intermediate files (fp-code-map.json, fp-draft.json, etc.) are preserved in `.claude/context-snapshots/` for debugging. They are overwritten on the next `/predict-failures` run and are gitignored via `.claude/context-snapshots/`.
- Full analysis takes several minutes (two LLM agents + P1 scripts).
- Speed and token cost are irrelevant — quality is the only criterion.
- Results in `failure-predictions/` persist across sessions.
- `active-risks.md` is replaced on every run — always reflects the latest scan.
- Run `/predict-failures` again after fixing identified risks to verify improvement.
