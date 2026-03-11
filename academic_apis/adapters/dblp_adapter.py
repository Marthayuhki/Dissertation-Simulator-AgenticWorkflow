"""DBLP API adapter.

No API key required. Completely open.
Coverage: 8M+ computer science publications.
Response: JSON/XML.
"""

from __future__ import annotations

import logging

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)

_BASE_URL = "https://dblp.org/search/publ/api"


class DBLPAdapter(BaseAdapter):
    name = "dblp"

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
        # DBLP search supports year filtering via query syntax
        q = query
        if year_from and year_to:
            q += f" year:{year_from}-{year_to}:"
        elif year_from:
            q += f" year:{year_from}-2099:"
        elif year_to:
            q += f" year:1900-{year_to}:"

        try:
            resp = self._request_with_retry(
                "GET",
                _BASE_URL,
                params={
                    "q": q,
                    "format": "json",
                    "h": min(max_results, 100),  # hits per page
                    "f": 0,  # first result offset
                },
                rate_limit_interval=0.5,
            )
            data = resp.json()
        except Exception as e:
            logger.error("DBLP search failed: %s", e)
            return []

        result = data.get("result", {})
        hits = result.get("hits", {}).get("hit", [])

        return [self._parse_hit(h) for h in hits]

    def get_paper(self, identifier: str) -> Paper | None:
        """Get paper by DOI (search DBLP for the DOI)."""
        if not identifier.startswith("10."):
            return None

        try:
            resp = self._request_with_retry(
                "GET",
                _BASE_URL,
                params={"q": f"doi:{identifier}", "format": "json", "h": 1},
                rate_limit_interval=0.5,
            )
            hits = resp.json().get("result", {}).get("hits", {}).get("hit", [])
            if hits:
                return self._parse_hit(hits[0])
        except Exception as e:
            logger.error("DBLP lookup failed for %s: %s", identifier, e)
        return None

    def _parse_hit(self, hit: dict) -> Paper:
        info = hit.get("info", {})

        # Authors — can be string or list
        authors_raw = info.get("authors", {}).get("author", [])
        authors = []
        if isinstance(authors_raw, str):
            authors = [Author(name=authors_raw)]
        elif isinstance(authors_raw, list):
            for a in authors_raw:
                if isinstance(a, dict):
                    authors.append(Author(
                        name=a.get("text", a.get("@text", "Unknown")),
                        source_id=a.get("@pid"),
                    ))
                elif isinstance(a, str):
                    authors.append(Author(name=a))
        elif isinstance(authors_raw, dict):
            authors = [Author(
                name=authors_raw.get("text", authors_raw.get("@text", "Unknown")),
                source_id=authors_raw.get("@pid"),
            )]

        # Year
        year = None
        year_str = info.get("year")
        if year_str and str(year_str).isdigit():
            year = int(year_str)

        # DOI
        doi = info.get("doi")

        # Venue
        venue = info.get("venue")

        # Type
        paper_type = info.get("type")

        # Access
        access = info.get("access")
        is_oa = access == "open" if access else None

        return Paper(
            title=info.get("title", "Untitled").rstrip("."),
            year=year,
            doi=doi,
            authors=authors,
            source_journal=venue,
            is_open_access=is_oa,
            paper_type=paper_type,
            fields_of_study=["Computer Science"],
            source_db="dblp",
            source_id=info.get("key", ""),
            source_url=info.get("url", info.get("ee", "")),
        )
