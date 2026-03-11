"""DOAJ (Directory of Open Access Journals) API adapter.

No API key required for search. Completely open.
Coverage: 12.4M+ open access articles, 21,400+ journals, all disciplines.
Response: JSON.
"""

from __future__ import annotations

import logging
import urllib.parse

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)

_BASE_URL = "https://doaj.org/api"


class DOAJAdapter(BaseAdapter):
    name = "doaj"

    def __init__(self, config: APIConfig) -> None:
        super().__init__(config)

    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
    ) -> list[Paper]:
        # Build query with year filter
        q = query
        if year_from and year_to:
            q += f" AND bibjson.year:[{year_from} TO {year_to}]"
        elif year_from:
            q += f" AND bibjson.year:[{year_from} TO *]"
        elif year_to:
            q += f" AND bibjson.year:[* TO {year_to}]"

        try:
            resp = self._request_with_retry(
                "GET",
                f"{_BASE_URL}/search/articles/{urllib.parse.quote(q, safe='')}",
                params={"pageSize": min(max_results, 100), "page": 1},
                rate_limit_interval=0.5,
            )
            data = resp.json()
        except Exception as e:
            logger.error("DOAJ search failed: %s", e)
            return []

        return [self._parse_result(item) for item in data.get("results", [])]

    def get_paper(self, identifier: str) -> Paper | None:
        """Get paper by DOI."""
        if not identifier.startswith("10."):
            return None

        try:
            resp = self._request_with_retry(
                "GET",
                f"{_BASE_URL}/search/articles/doi:{identifier}",
                params={"pageSize": 1},
                rate_limit_interval=0.5,
            )
            results = resp.json().get("results", [])
            if results:
                return self._parse_result(results[0])
        except Exception as e:
            logger.error("DOAJ lookup failed for %s: %s", identifier, e)
        return None

    def _parse_result(self, item: dict) -> Paper:
        bib = item.get("bibjson", {})

        # Authors
        authors = []
        for a in bib.get("author", []):
            name = a.get("name", "Unknown")
            orcid = a.get("orcid_id")
            aff = a.get("affiliation")
            authors.append(Author(name=name, orcid=orcid, affiliation=aff))

        # DOI
        doi = None
        for ident in bib.get("identifier", []):
            if ident.get("type") == "doi":
                doi = ident.get("id")
                break

        # Year
        year = None
        year_str = bib.get("year")
        if year_str and str(year_str).isdigit():
            year = int(year_str)

        # Journal
        journal_obj = bib.get("journal", {})
        journal = journal_obj.get("title")

        # Keywords
        keywords = bib.get("keywords", [])

        # Abstract
        abstract = bib.get("abstract")

        # Link
        links = bib.get("link", [])
        pdf_url = None
        for link in links:
            if link.get("type") == "fulltext":
                pdf_url = link.get("url")
                break

        # Language
        lang = bib.get("journal", {}).get("language", [])
        language = lang[0] if lang else None

        return Paper(
            title=bib.get("title", "Untitled"),
            year=year,
            doi=doi,
            abstract=abstract,
            authors=authors,
            source_journal=journal,
            is_open_access=True,  # DOAJ is all OA
            pdf_url=pdf_url,
            language=language,
            keywords=keywords,
            paper_type="journal-article",
            source_db="doaj",
            source_id=item.get("id", ""),
            source_url=f"https://doaj.org/article/{item.get('id', '')}",
            raw=item,
        )
