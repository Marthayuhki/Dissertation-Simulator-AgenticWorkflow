"""CORE API v3 adapter.

API key required (free registration).
Coverage: 313M metadata, 37M full-text papers.
Unique: full-text access inline in API response.
"""

from __future__ import annotations

import logging

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)


class CoreAdapter(BaseAdapter):
    name = "core"

    def __init__(self, config: APIConfig) -> None:
        super().__init__(config)
        if config.core_api_key:
            self._session.headers["Authorization"] = f"Bearer {config.core_api_key}"

    def is_available(self) -> bool:
        return bool(self.config.core_api_key)

    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
    ) -> list[Paper]:
        q_parts = [query]
        if year_from:
            q_parts.append(f"yearPublished>={year_from}")
        if year_to:
            q_parts.append(f"yearPublished<={year_to}")

        q = " AND ".join(q_parts)

        try:
            resp = self._request_with_retry(
                "GET",
                f"{self.config.core_base_url}/search/works",
                params={"q": q, "limit": min(max_results, 100)},
                rate_limit_interval=2.5,
            )
            data = resp.json()
        except Exception as e:
            logger.error("CORE search failed: %s", e)
            return []

        return [self._parse_work(item) for item in data.get("results", [])]

    def get_paper(self, identifier: str) -> Paper | None:
        try:
            # Support DOI or CORE ID
            if identifier.startswith("10."):
                url = f"{self.config.core_base_url}/works/doi:{identifier}"
            else:
                url = f"{self.config.core_base_url}/works/{identifier}"

            resp = self._request_with_retry(
                "GET", url, rate_limit_interval=2.5,
            )
            return self._parse_work(resp.json())
        except Exception as e:
            logger.error("CORE lookup failed for %s: %s", identifier, e)
        return None

    def search_fulltext(self, query: str, max_results: int = 20) -> list[Paper]:
        """Search within full paper text (CORE's unique feature)."""
        try:
            q = f'{query} AND _exists_:fullText'
            resp = self._request_with_retry(
                "GET",
                f"{self.config.core_base_url}/search/works",
                params={"q": q, "limit": min(max_results, 50)},
                rate_limit_interval=2.5,
            )
            data = resp.json()
            return [self._parse_work(item) for item in data.get("results", [])]
        except Exception as e:
            logger.error("CORE fulltext search failed: %s", e)
            return []

    def _parse_work(self, item: dict) -> Paper:
        authors = [
            Author(name=a.get("name", "Unknown"))
            for a in (item.get("authors") or [])
        ]

        doi = item.get("doi")
        identifiers = item.get("identifiers", {}) or {}
        if not doi and isinstance(identifiers, dict):
            doi = identifiers.get("doi")

        lang = item.get("language", {})
        lang_code = lang.get("code") if isinstance(lang, dict) else lang

        refs = item.get("references", [])
        ref_dois = [r.get("doi") for r in refs if r.get("doi")] if isinstance(refs, list) else []

        return Paper(
            title=item.get("title", "Untitled"),
            year=item.get("yearPublished"),
            doi=doi,
            abstract=item.get("abstract"),
            authors=authors,
            citation_count=item.get("citationCount"),
            source_journal=(item.get("journals") or [{}])[0].get("title") if item.get("journals") else None,
            publication_date=item.get("publishedDate"),
            is_open_access=True,  # CORE focuses on OA
            pdf_url=item.get("downloadUrl"),
            full_text=item.get("fullText"),
            language=lang_code,
            paper_type=item.get("documentType"),
            fields_of_study=[item["fieldOfStudy"]] if item.get("fieldOfStudy") else [],
            references=ref_dois,
            source_db="core",
            source_id=str(item.get("id", "")),
            source_url=f"https://core.ac.uk/works/{item.get('id', '')}",
            raw=item,
        )
