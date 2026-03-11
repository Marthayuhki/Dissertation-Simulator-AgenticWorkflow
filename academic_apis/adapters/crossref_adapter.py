"""CrossRef REST API adapter.

No API key required. Polite pool via email.
Coverage: 176M+ DOI metadata records.
"""

from __future__ import annotations

import logging

from habanero import Crossref

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)


class CrossRefAdapter(BaseAdapter):
    name = "crossref"

    def __init__(self, config: APIConfig) -> None:
        super().__init__(config)
        self._client = Crossref(
            mailto=config.crossref_email or None,
        )

    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
    ) -> list[Paper]:
        self._rate_limit(0.35)  # ~3 req/sec polite pool

        filters: dict[str, str] = {}
        if year_from:
            filters["from_pub_date"] = f"{year_from}-01-01"
        if year_to:
            filters["until_pub_date"] = f"{year_to}-12-31"

        sort_map = {
            "relevance": "relevance",
            "citations": "is-referenced-by-count",
            "date": "published",
        }

        try:
            result = self._client.works(
                query=query,
                filter=filters if filters else None,
                sort=sort_map.get(sort_by, "relevance"),
                order="desc",
                limit=min(max_results, 100),
            )
        except Exception as e:
            logger.error("CrossRef search failed: %s", e)
            return []

        return [self._parse_work(item) for item in (result.get("message", {}).get("items", []))]

    def get_paper(self, identifier: str) -> Paper | None:
        self._rate_limit(0.1)
        try:
            result = self._client.works(ids=identifier)
            msg = result.get("message", {})
            if msg:
                return self._parse_work(msg)
        except Exception as e:
            logger.error("CrossRef lookup failed for %s: %s", identifier, e)
        return None

    def get_references(self, identifier: str, max_results: int = 50) -> list[Paper]:
        """Get references listed in a CrossRef work (if deposited)."""
        self._rate_limit(0.1)
        try:
            result = self._client.works(ids=identifier)
            refs = result.get("message", {}).get("reference", [])
            papers = []
            for ref in refs[:max_results]:
                doi = ref.get("DOI")
                title = ref.get("article-title") or ref.get("unstructured", "")
                year_str = ref.get("year")
                papers.append(Paper(
                    title=title,
                    year=int(year_str) if year_str else None,
                    doi=doi,
                    authors=[Author(name=ref["author"])] if ref.get("author") else [],
                    source_journal=ref.get("journal-title"),
                    source_db="crossref",
                    source_id=doi or "",
                ))
            return papers
        except Exception as e:
            logger.error("CrossRef references failed for %s: %s", identifier, e)
            return []

    def _parse_work(self, item: dict) -> Paper:
        # Authors
        authors = []
        for a in item.get("author", []):
            name_parts = []
            if a.get("given"):
                name_parts.append(a["given"])
            if a.get("family"):
                name_parts.append(a["family"])
            name = " ".join(name_parts) or a.get("name", "Unknown")
            affiliation_list = a.get("affiliation", [])
            aff = affiliation_list[0].get("name") if affiliation_list else None
            authors.append(Author(
                name=name,
                orcid=a.get("ORCID"),
                affiliation=aff,
            ))

        # Date — guard against None / missing elements in date-parts
        date_parts = None
        for date_field in ("published-print", "published-online", "issued", "published"):
            raw_dp = item.get(date_field)
            if not isinstance(raw_dp, dict):
                continue
            dp = raw_dp.get("date-parts", [])
            if dp and isinstance(dp, list) and dp[0] and isinstance(dp[0], list) and dp[0][0] is not None:
                date_parts = dp[0]
                break

        year = int(date_parts[0]) if date_parts and date_parts[0] is not None else None
        pub_date = None
        if date_parts and date_parts[0] is not None:
            parts = [str(date_parts[0])]
            if len(date_parts) > 1 and date_parts[1] is not None:
                parts.append(f"{int(date_parts[1]):02d}")
            if len(date_parts) > 2 and date_parts[2] is not None:
                parts.append(f"{int(date_parts[2]):02d}")
            pub_date = "-".join(parts)

        # Title
        titles = item.get("title", [])
        title = titles[0] if titles else "Untitled"

        # Journal
        containers = item.get("container-title", [])
        journal = containers[0] if containers else None

        doi = item.get("DOI")

        return Paper(
            title=title,
            year=year,
            doi=doi,
            abstract=item.get("abstract"),
            authors=authors,
            citation_count=item.get("is-referenced-by-count"),
            reference_count=item.get("references-count") or item.get("reference-count"),
            source_journal=journal,
            publication_date=pub_date,
            paper_type=item.get("type"),
            language=item.get("language"),
            source_db="crossref",
            source_id=doi or "",
            source_url=item.get("URL", ""),
            raw=item,
        )
