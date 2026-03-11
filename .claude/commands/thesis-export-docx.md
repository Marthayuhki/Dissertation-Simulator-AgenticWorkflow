# Thesis Export DOCX

Generate a consolidated Korean thesis Word document from translation files.

## Protocol

### Step 1: Identify Project

```bash
ls thesis-output/ 2>/dev/null
```

If multiple projects exist, ask the user which project to export.

### Step 2: Verify Translations Exist

```bash
ls thesis-output/{project}/translations/step-*-*.ko.md 2>/dev/null | head -20
```

If no Korean translation files found, inform the user that translations must be completed first (Phase 6).

### Step 3: Preview Chapter Order (Dry Run)

```bash
python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/scripts/merge_ko_to_docx.py \
  --project-dir "$CLAUDE_PROJECT_DIR/thesis-output/{project}" \
  --dry-run --json
```

Display the chapter ordering to the user for confirmation. If the order is wrong, the user can create `deliverables/chapter-order.json` with the correct file list.

### Step 4: Execute Merge

```bash
python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/scripts/merge_ko_to_docx.py \
  --project-dir "$CLAUDE_PROJECT_DIR/thesis-output/{project}" \
  --json
```

### Step 5: Report Results (Korean)

Display:
- Number of chapter files merged
- Chapter ordering used
- Output file locations (DOCX and/or Markdown fallback)
- If pandoc was not available, provide installation instructions

### Notes

- This command does NOT modify the SOT (session.json). It is safe to run on any project at any stage.
- For automated workflow execution (Step 211), the thesis-orchestrator handles SOT advancement separately.
- To customize chapter ordering, create `deliverables/chapter-order.json` as a JSON array of filenames.
