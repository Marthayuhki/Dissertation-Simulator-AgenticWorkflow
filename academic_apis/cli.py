#!/usr/bin/env python3
"""CLI entry point for academic database searches.

Usage:
    # Check which databases are configured
    python -m academic_apis status

    # Search across all available databases
    python -m academic_apis search "free will artificial intelligence" --max-results 20

    # Search with filters
    python -m academic_apis search "transformer attention" --year-from 2020 --sort citations

    # Search only international databases
    python -m academic_apis search "deep learning" --databases openalex,semantic_scholar,crossref

    # Search only Korean databases
    python -m academic_apis search-korean "인공지능 자유의지"

    # Get paper by DOI
    python -m academic_apis get "10.1038/nature12373"

    # Get citations of a paper
    python -m academic_apis citations "10.1038/nature12373"

    # Get references from a paper
    python -m academic_apis references "10.1038/nature12373"

    # JSON output for programmatic use
    python -m academic_apis search "query" --json
"""

from __future__ import annotations

import argparse
import json
import sys

from academic_apis.client import AcademicSearchClient
from academic_apis.config import APIConfig


def cmd_status(args: argparse.Namespace) -> None:
    """Show API configuration status."""
    config = APIConfig.from_env()
    client = AcademicSearchClient(config)

    print("=" * 60)
    print("  Academic Database API Status")
    print("=" * 60)

    status = client.status()
    available = client.available_databases

    for db, state in status.items():
        indicator = "[OK]" if db in available else "[--]"
        print(f"  {indicator} {db:<20s} {state}")

    print("-" * 60)
    print(f"  Available: {len(available)}/{len(status)} databases")
    print(f"  Ready to search: {', '.join(available) if available else 'none'}")
    print("=" * 60)


def cmd_search(args: argparse.Namespace) -> None:
    """Search across databases."""
    client = AcademicSearchClient()

    databases = args.databases.split(",") if args.databases else None

    result = client.search(
        args.query,
        databases=databases,
        max_results=args.max_results,
        year_from=args.year_from,
        year_to=args.year_to,
        sort_by=args.sort,
    )

    if args.json:
        json.dump(result.to_dict(), sys.stdout, indent=2, ensure_ascii=False)
        print()
        return

    _print_results(result)


def cmd_search_korean(args: argparse.Namespace) -> None:
    """Search Korean databases only."""
    client = AcademicSearchClient()
    result = client.search_korean(
        args.query,
        max_results=args.max_results,
        year_from=args.year_from,
        year_to=args.year_to,
    )

    if args.json:
        json.dump(result.to_dict(), sys.stdout, indent=2, ensure_ascii=False)
        print()
        return

    _print_results(result)


def cmd_get(args: argparse.Namespace) -> None:
    """Get paper by DOI."""
    client = AcademicSearchClient()
    paper = client.get_paper(args.doi)

    if not paper:
        print(f"Paper not found: {args.doi}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        json.dump(paper.to_dict(), sys.stdout, indent=2, ensure_ascii=False)
        print()
        return

    _print_paper_detail(paper)


def cmd_citations(args: argparse.Namespace) -> None:
    """Get citations of a paper."""
    client = AcademicSearchClient()
    papers = client.get_citations(args.doi, max_results=args.max_results)

    if args.json:
        json.dump([p.to_dict() for p in papers], sys.stdout, indent=2, ensure_ascii=False)
        print()
        return

    print(f"Citations of {args.doi}: {len(papers)} found")
    print("-" * 60)
    for i, p in enumerate(papers, 1):
        _print_paper_brief(i, p)


def cmd_references(args: argparse.Namespace) -> None:
    """Get references from a paper."""
    client = AcademicSearchClient()
    papers = client.get_references(args.doi, max_results=args.max_results)

    if args.json:
        json.dump([p.to_dict() for p in papers], sys.stdout, indent=2, ensure_ascii=False)
        print()
        return

    print(f"References of {args.doi}: {len(papers)} found")
    print("-" * 60)
    for i, p in enumerate(papers, 1):
        _print_paper_brief(i, p)


def _print_results(result) -> None:
    """Pretty-print search results."""
    print(f"\nQuery: \"{result.query}\"")
    print(f"Databases searched: {', '.join(result.databases_searched)}")
    if result.errors:
        for db, err in result.errors.items():
            print(f"  [ERROR] {db}: {err}")
    print(f"Total results (deduplicated): {result.total_results}")
    print("=" * 70)

    for i, paper in enumerate(result.papers, 1):
        _print_paper_brief(i, paper)


def _print_paper_brief(i: int, paper) -> None:
    """Print a single paper in brief format."""
    authors_str = ", ".join(a.name for a in paper.authors[:3])
    if len(paper.authors) > 3:
        authors_str += f" et al. ({len(paper.authors)} authors)"

    cite_str = f"  Citations: {paper.citation_count}" if paper.citation_count is not None else ""
    doi_str = f"  DOI: {paper.doi}" if paper.doi else ""

    print(f"\n[{i}] {paper.title}")
    print(f"    {authors_str} ({paper.year or '?'})")
    print(f"    {paper.source_journal or '?'} | {paper.source_db}{cite_str}{doi_str}")
    if paper.tldr:
        print(f"    TLDR: {paper.tldr[:150]}...")


def _print_paper_detail(paper) -> None:
    """Print detailed paper info."""
    print(f"\nTitle: {paper.title}")
    print(f"Year: {paper.year}")
    print(f"DOI: {paper.doi}")
    print(f"Journal: {paper.source_journal}")
    print(f"Type: {paper.paper_type}")
    print(f"Language: {paper.language}")
    print(f"Open Access: {paper.is_open_access}")
    print(f"Citations: {paper.citation_count}")
    print(f"References: {paper.reference_count}")
    if paper.fwci:
        print(f"FWCI: {paper.fwci}")
    if paper.citation_percentile:
        print(f"Citation Percentile: {paper.citation_percentile}")
    print(f"\nAuthors:")
    for a in paper.authors:
        aff = f" ({a.affiliation})" if a.affiliation else ""
        orcid = f" [ORCID: {a.orcid}]" if a.orcid else ""
        print(f"  - {a.name}{aff}{orcid}")
    if paper.abstract:
        print(f"\nAbstract:\n{paper.abstract[:500]}{'...' if len(paper.abstract or '') > 500 else ''}")
    if paper.keywords:
        print(f"\nKeywords: {', '.join(paper.keywords)}")
    if paper.fields_of_study:
        print(f"Fields: {', '.join(paper.fields_of_study)}")
    print(f"\nSource: {paper.source_db} | {paper.source_url}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="academic_apis",
        description="Search academic databases from the command line.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Show API configuration status")

    # search
    p_search = sub.add_parser("search", help="Search across databases")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--databases", "-d", help="Comma-separated database names")
    p_search.add_argument("--max-results", "-n", type=int, default=20)
    p_search.add_argument("--year-from", type=int)
    p_search.add_argument("--year-to", type=int)
    p_search.add_argument("--sort", choices=["relevance", "citations", "date"], default="relevance")
    p_search.add_argument("--json", action="store_true", help="JSON output")

    # search-korean
    p_kr = sub.add_parser("search-korean", help="Search Korean databases")
    p_kr.add_argument("query", help="Search query (Korean)")
    p_kr.add_argument("--max-results", "-n", type=int, default=20)
    p_kr.add_argument("--year-from", type=int)
    p_kr.add_argument("--year-to", type=int)
    p_kr.add_argument("--json", action="store_true")

    # get
    p_get = sub.add_parser("get", help="Get paper by DOI")
    p_get.add_argument("doi", help="Paper DOI")
    p_get.add_argument("--json", action="store_true")

    # citations
    p_cite = sub.add_parser("citations", help="Get citations of a paper")
    p_cite.add_argument("doi", help="Paper DOI or ID")
    p_cite.add_argument("--max-results", "-n", type=int, default=20)
    p_cite.add_argument("--json", action="store_true")

    # references
    p_ref = sub.add_parser("references", help="Get references from a paper")
    p_ref.add_argument("doi", help="Paper DOI or ID")
    p_ref.add_argument("--max-results", "-n", type=int, default=20)
    p_ref.add_argument("--json", action="store_true")

    args = parser.parse_args()

    handlers = {
        "status": cmd_status,
        "search": cmd_search,
        "search-korean": cmd_search_korean,
        "get": cmd_get,
        "citations": cmd_citations,
        "references": cmd_references,
    }

    handlers[args.command](args)


if __name__ == "__main__":
    main()
