#!/usr/bin/env python3
"""run_academic_search.py — P1 Academic Search Pre-fetch for Literature Agents.

Bridges the gap between the academic_apis package (which requires Bash/requests)
and literature-searcher agents (which only have Read/Write/Glob/Grep/WebSearch).

The Orchestrator calls this script via Bash BEFORE invoking @literature-searcher.
Results are cached to {project-dir}/search-cache/step-{N}-results.json so the
agent can Read the file directly.

This is the "Orchestrator Pre-fetch Pattern":
  1. Orchestrator runs this P1 script (Bash)
  2. Script calls academic_apis.client.AcademicSearchClient
  3. Results written to search-cache/
  4. @literature-searcher reads cached JSON (Read tool)

Hallucination Containment:
  --auto-from-sot mode reads research_question from session.json (SOT),
  eliminating LLM-constructed query strings. The Orchestrator SHOULD use
  this mode via the pre_execution_command from query_step.py.

Usage:
  # P1 deterministic (recommended — query from SOT):
  python3 run_academic_search.py --auto-from-sot \
    --project-dir thesis-output/my-thesis --step 39

  # Manual query (fallback — LLM constructs query):
  python3 run_academic_search.py --query "AI safety alignment" \
    --project-dir thesis-output/my-thesis --step 39

  python3 run_academic_search.py --auto-from-sot \
    --project-dir thesis-output/my-thesis --step 39 \
    --max-results 100 --year-from 2020

Exit codes:
  0 — always (P1 compliant, non-blocking)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# Thesis SOT filename (aligned with checklist_manager.py — no import to avoid
# circular dependency / path issues when called standalone).
_THESIS_SOT_FILENAME = "session.json"


def _extract_query_from_sot(project_dir: str) -> str | None:
    """P1 deterministic: extract search query from SOT's research_question.

    Reads session.json and returns a cleaned query string derived from:
      1. research_question (primary — set by user at HITL-1)
      2. academic_field (supplementary context)

    Returns None if SOT is unreadable or research_question is empty.
    This eliminates LLM-constructed query strings (Hallucination Vector 1).
    """
    sot_path = os.path.join(project_dir, _THESIS_SOT_FILENAME)
    try:
        with open(sot_path, "r", encoding="utf-8") as f:
            sot = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"[run_academic_search] WARNING: Cannot read SOT at {sot_path}: {e}",
            file=sys.stderr,
        )
        return None

    rq = sot.get("research_question", "")
    if not isinstance(rq, str) or not rq.strip():
        print(
            "[run_academic_search] WARNING: research_question is empty in SOT",
            file=sys.stderr,
        )
        return None

    # Build query: research_question is the primary search term.
    # academic_field narrows scope if available.
    query = rq.strip()
    field = sot.get("academic_field", "")
    if isinstance(field, str) and field.strip():
        query = f"{field.strip()} {query}"

    return query


def _search(
    query: str,
    max_results: int = 50,
    year_from: int | None = None,
    year_to: int | None = None,
    databases: list[str] | None = None,
) -> dict[str, Any]:
    """Execute academic search and return serializable results."""
    try:
        from academic_apis.client import AcademicSearchClient
    except ImportError as e:
        return {
            "error": f"academic_apis not importable: {e}",
            "papers": [],
            "databases_searched": [],
            "total_results": 0,
        }

    try:
        client = AcademicSearchClient()
        result = client.search(
            query,
            max_results=max_results,
            year_from=year_from,
            year_to=year_to,
            databases=databases,
        )
        client.close()
        return result.to_dict()
    except Exception as e:
        return {
            "error": str(e),
            "papers": [],
            "databases_searched": [],
            "total_results": 0,
        }


def _validate_cache(
    cache_path: str,
    total: int,
    dbs: list[str],
    papers: list[dict[str, Any]],
) -> dict[str, Any]:
    """P1 deterministic validation of cached search results.

    Checks:
      V-1: Cache file exists and is valid JSON (read-back)
      V-2: At least 1 database returned results
      V-3: Papers have required fields (title, source_db)
      V-4: Total results count matches papers array length
    """
    checks: dict[str, str] = {}
    warnings: list[str] = []

    # V-1: Read-back validation
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            readback = json.load(f)
        checks["V1_valid_json"] = "PASS"
    except (json.JSONDecodeError, OSError) as e:
        checks["V1_valid_json"] = "FAIL"
        warnings.append(f"V-1: Cache read-back failed: {e}")
        return {"checks": checks, "warnings": warnings, "valid": False}

    # V-2: At least 1 database searched
    if len(dbs) >= 1:
        checks["V2_databases"] = "PASS"
    else:
        checks["V2_databases"] = "WARN"
        warnings.append("V-2: No databases returned results")

    # V-3: Papers have required fields
    malformed = 0
    for p in papers[:20]:  # Sample first 20
        if not isinstance(p, dict) or not p.get("title"):
            malformed += 1
    if malformed == 0:
        checks["V3_paper_schema"] = "PASS"
    else:
        checks["V3_paper_schema"] = "WARN"
        warnings.append(f"V-3: {malformed} papers missing 'title' field")

    # V-4: Count consistency
    if total == len(papers):
        checks["V4_count_match"] = "PASS"
    else:
        checks["V4_count_match"] = "WARN"
        warnings.append(f"V-4: total_results={total} but papers array has {len(papers)}")

    is_valid = all(v != "FAIL" for v in checks.values())

    if warnings:
        for w in warnings:
            print(f"[run_academic_search] {w}", file=sys.stderr)

    return {"checks": checks, "warnings": warnings, "valid": is_valid}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Academic search pre-fetch for literature agents (P1)"
    )
    # Query source: either --auto-from-sot (P1 deterministic) or --query (LLM-constructed)
    query_group = parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument(
        "--auto-from-sot", action="store_true",
        help="P1 deterministic: extract query from session.json research_question",
    )
    query_group.add_argument("--query", help="Search query string (LLM-constructed fallback)")
    parser.add_argument("--project-dir", required=True, help="Thesis project directory")
    parser.add_argument("--step", type=int, required=True, help="Step number")
    parser.add_argument("--max-results", type=int, default=50, help="Max results per DB")
    parser.add_argument("--year-from", type=int, default=None, help="Filter: year from")
    parser.add_argument("--year-to", type=int, default=None, help="Filter: year to")
    parser.add_argument(
        "--databases", nargs="*", default=None,
        help="Specific databases to search (default: all keyless)",
    )
    args = parser.parse_args()

    # Resolve query: P1 deterministic (SOT) or LLM-constructed fallback
    if args.auto_from_sot:
        query = _extract_query_from_sot(args.project_dir)
        if query is None:
            # SOT unreadable or research_question empty — report and exit
            report = {
                "error": "auto-from-sot failed: research_question is empty or SOT unreadable",
                "cache_path": None,
                "total_results": 0,
                "databases_searched": [],
                "query_source": "sot_failed",
            }
            print(json.dumps(report, indent=2))
            return
        query_source = "sot"
    else:
        query = args.query
        query_source = "manual"

    # Execute search
    print(f"[run_academic_search] Searching: {query!r} (step {args.step}, source={query_source})")
    result = _search(
        query,
        max_results=args.max_results,
        year_from=args.year_from,
        year_to=args.year_to,
        databases=args.databases,
    )

    # Inject query metadata into result for traceability (Hallucination Containment)
    result["query"] = query
    result["query_source"] = query_source

    # Write to search-cache
    cache_dir = os.path.join(args.project_dir, "search-cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"step-{args.step}-results.json")

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total = result.get("total_results", 0)
    dbs = result.get("databases_searched", [])
    errors = result.get("errors", {})
    papers = result.get("papers", [])
    error_str = f", errors={errors}" if errors else ""

    print(
        f"[run_academic_search] Done: {total} papers from {len(dbs)} databases "
        f"({', '.join(dbs)}){error_str}"
    )
    print(f"[run_academic_search] Cached → {cache_path}")

    # P1 validation of cached results
    validation = _validate_cache(cache_path, total, dbs, papers)

    # Build P1 deterministic SOT registration command (Hallucination Vector 2 fix).
    # Orchestrator runs this verbatim — no JSON field extraction needed.
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    cm_path = os.path.join(scripts_dir, "checklist_manager.py")
    dbs_arg = " ".join(dbs) if dbs else ""
    # Shell-safe quoting for query (replace single quotes)
    safe_query = query.replace("'", "'\\''")
    sot_reg_cmd = (
        f"{sys.executable} {cm_path} --register-search-cache"
        f" --project-dir {{project_dir}} --step {args.step}"
        f" --cache-path {cache_path}"
        f" --total-results {total}"
    )
    if dbs_arg:
        sot_reg_cmd += f" --databases {dbs_arg}"
    sot_reg_cmd += f" --search-query '{safe_query}' --query-source {query_source}"

    # Print JSON to stdout for Orchestrator consumption
    print(json.dumps({
        "cache_path": cache_path,
        "total_results": total,
        "databases_searched": dbs,
        "errors": errors,
        "validation": validation,
        "query": query,
        "query_source": query_source,
        "sot_registration_command": sot_reg_cmd,
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[run_academic_search] FATAL: {e}", file=sys.stderr)
        sys.exit(0)  # P1: never block
