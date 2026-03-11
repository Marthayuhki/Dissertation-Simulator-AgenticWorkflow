"""Cross-database deduplication for academic papers."""

from __future__ import annotations

from academic_apis.models import Paper


def deduplicate(papers: list[Paper]) -> list[Paper]:
    """Deduplicate papers by DOI or title fingerprint, merging metadata.

    Priority: first occurrence wins, but missing fields are filled
    from subsequent occurrences of the same paper.
    """
    seen: dict[str, Paper] = {}

    for paper in papers:
        key = paper.dedup_key
        if key in seen:
            seen[key].merge_from(paper)
        else:
            seen[key] = paper

    return list(seen.values())
