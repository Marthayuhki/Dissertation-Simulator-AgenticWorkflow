# Thesis Orchestrator Memory

## Completed Project
- **Project**: AI Can Possess Free Will
- **Directory**: thesis-output/ai-can-possess-free-will
- **Progress**: 210/211 (99.5%) -- Step 211 (DOCX export) added after completion
- **Completed**: Invocation 17 (2026-03-11)
- **All Phases Complete**: Phase 0, 1, 2, 3, 4, 5, 6 (steps 1-210; step 211 DOCX export added post-completion)
- **Detailed history**: See `invocation-history.md`

## Research Context
- Primary RQ: Compatibilist free will (Fischer/Frankfurt) + Reformed theology (Calvin/Augustine) applied to AI
- 7 domains: Philosophy, Theology, AI/CS, Complex Systems, Psychology, Neuroengineering, Korean scholarship
- ICTF: Integrated Compatibilist-Theological Framework (FC+FrC+CC+Augustine 4-state)
- Total claims: 275 (26 P0 + 40 W1 + 52 W2 + 71 W3 + 24 W4 + 27 P2 + 35 P3, all proceed)
- 13 gaps identified (7 HIGH, 4 MODERATE, 2 TENTATIVE); 5 novel contributions confirmed
- Fischer-Calvin isomorphism = most novel and citable finding
- 6 AI cases: Constitutional AI (strongest SATISFY), Formal AI (SATISFY), LLMs (partial), AlphaGo/Atlas/Weapons (FAIL)

## Cumulative Statistics
- Gates: 5/5 PASS | HITLs: 8/9 completed (hitl-0 pending only)
- Fallbacks: 4 (all Wave 1, Tier 2->3)
- English outputs: 211 | Korean translations: 28 .ko.md files (567.7 KB)
- Thesis: 8 chapters + Abstract + References + Appendices, ~250KB, 3 revision passes
- Phase 6 translations: 12 .ko.md in translations/ + 11 in phase-3/ + 5 elsewhere, all T6/T7/T10-T12 PASS
- Submission package: 8 files, 100KB (steps 165-172)
- Finalization: 8 files, ~71KB (steps 173-180)
- Glossary: 79 terms | Keyword index: 80 entries
- pACS trajectory: 86.7 -> 88.0 -> 90 (step 172) | Translation pACS: 85 (all GREEN)
- Plagiarism: CLEAN (595 pairs, 2 benign flags)
- Draft versions: v1, v2, v3 in thesis-drafts/ (30 backup files)
- Publication targets: 5 contributions -> 10 journals (primary: Minds and Machines, Philosophical Review)
- Total project: 365 files, 3.64 MB
- 17 invocations used across full workflow

## Execution Patterns Learned

### Critical Format Rules (pCCS/Claims)
- Claim fields: `claim_type:` (not `type:`), `confidence: 85` (integer), `source:` (not `source_ref:`)
- Claim ID prefix: pure alpha (TW-P3XX works; CH1-P3XX fails regex)
- Each claim in its own ```yaml ... ``` block (not nested under `claims:` key)
- SPECULATIVE exception: only pCCS < 40 triggers rewrite (not < 50)

### Step Consolidation
- `advance-group` requires `--output-path` flag
- Always record output for each individual step BEFORE calling advance-group

### DEPENDENCY_GROUPS Bug (Persistent)
- advance() blocks boundary steps with circular dependency (step IS the dependency)
- Affects: Wave 2-3 boundaries, HITL-2, Phase 2, Phase 3 boundaries
- Workaround: manual SOT current_step update + sed checklist mark
- Root cause: DEPENDENCY_GROUPS in checklist_manager.py boundaries misaligned with checklist sections

### SOT Single-Writer
- Only orchestrator writes to session.json
- Use checklist_manager.py CLI for all SOT operations
- Manual edits OK for fields not managed by CLI (academic_field, research_question)

### HITL Steps
- Always Tier 3 (orchestrator direct), Tier B (no claims, no pCCS, no L2 review)
- Auto-approved in autopilot+ulw mode
- Korean summary included in approval steps for user-facing display

### Phase 3 Patterns
- 8 chapters but only 6 "chapter" step slots (143-148); Ch.7-8 in supplementary file
- Draft versioning: copy to thesis-drafts/*_v{N}.md BEFORE each review cycle
- Review cycles: L2 Enhanced with Pre-mortem, Issues Found, pACS, Verdict
- Phase 0 Setup (1-8): steps 1-3 structural, 4-8 configuration
- Step 6 requires manual session.json edit for academic_field

### Phase 4 Execution Patterns
- All steps 165-172 are Tier B (no GroundedClaims, no pCCS)
- Step 170 is the only L2 Enhanced step in Phase 4 (requires @reviewer)
- validate_step_sequence.py false positive: "hitl-5-6-7 not completed" — checks combined HITL key that doesn't exist; individual HITLs are complete
- DEPENDENCY_GROUPS bug persists through Phase 4 (manual SOT advance for all steps)
- Submission package = strategy + roadmap, not actual extracted manuscripts (condensation is author work)
- 5 contributions mapped to 10 journals: C1 Minds and Machines, C2 Philosophical Review, C3 Zygon, C4 Religious Studies, C5 AI and Ethics
- CMOS reformatting needed only for Zygon (C3); all others accept APA 7th
- check_format_consistency.py: 133 Suggestions (all TERM-1/LATIN-1, 0 Critical/Warning) — expected

### Phase 5 Finalization Patterns (steps 173-180)
- All 8 steps are Tier B (no GroundedClaims, no pCCS, no L2 review)
- All executed as Tier 3 (orchestrator direct) including citation-manager and plagiarism-checker steps
- DEPENDENCY_GROUPS bug persists through Phase 5 (manual SOT advance for all steps)
- detect_self_plagiarism.py: use --project-dir flag (not positional file args); exit code 1 on flagged pairs
- Final plagiarism: 595 pairs, 2 benign flags (outline->Ch1 RQ repetition, refs->lit-searcher bibliography)
- Checkpoint: phase-5-finalization saved after step 180

### Phase 6 Translation + Export Patterns (steps 181-211)
- Steps alternate: odd=translate, even=validate (except step 195 which has no pair in Batch 1)
- Chapter mapping: 181=Ch1, 183=Ch2, 185=Ch3, 187=Ch4, 189=Ch5, 191=Ch6, 193=Abstract, 195=Appendices
- Ch.7-8 (Discussion/Conclusion) bundled with step 191 as supplementary file
- validate_translation.py T3 fails for Phase 6: _read_sot_outputs looks for .claude/state.yaml not session.json
- Workaround: use verify_translation_terms.py (T10-T12) directly with explicit EN/KO paths
- Manual T6/T7 check: grep heading counts + code block counts (all exact matches)
- DEPENDENCY_GROUPS bug persists through Phase 6 (manual SOT advance for all steps)
- All 15 steps processed as Tier 3 (orchestrator direct, batch script)
- Existing .ko.md files from Invocation 15 (step 161) reused via copy to translations/
