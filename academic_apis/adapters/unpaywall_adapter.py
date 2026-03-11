"""Unpaywall API adapter.

No API key required — just an email parameter.
Coverage: 20M+ open access scholarly articles.
Response: JSON.

Note: Unpaywall is DOI-based only (no keyword search).
Used to find open access versions of papers found via other adapters.
"""

from __future__ import annotations

import logging

import requests

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.unpaywall.org/v2"


class UnpaywallAdapter(BaseAdapter):
    """Unpaywall adapter for finding open access PDF links.

    This adapter does NOT support keyword search. It enriches
    existing papers (found via other adapters) with OA links.
    """

    name = "unpaywall"

    def __init__(self, config: APIConfig) -> None:
        super().__init__(config)
        if config.crossref_email:
            self._email = config.crossref_email
        else:
            self._email = "user@dissertation-simulator.org"
            logger.warning("Unpaywall: no CROSSREF_EMAIL set, using fallback. Set CROSSREF_EMAIL for reliable access.")

    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
    ) -> list[Paper]:
        """Unpaywall doesn't support keyword search — returns empty."""
        return []

    def get_paper(self, identifier: str) -> Paper | None:
        """Get OA information for a DOI."""
        if not identifier.startswith("10."):
            return None

        try:
            resp = self._request_with_retry(
                "GET",
                f"{_BASE_URL}/{identifier}",
                params={"email": self._email},
                timeout=15,
                rate_limit_interval=0.01,
            )
            data = resp.json()
            return self._parse_result(data)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            logger.error("Unpaywall lookup failed for %s: %s", identifier, e)
        except Exception as e:
            logger.error("Unpaywall lookup failed for %s: %s", identifier, e)
        return None

    def find_oa_url(self, doi: str) -> str | None:
        """Quick lookup: return the best OA URL for a DOI, or None."""
        paper = self.get_paper(doi)
        if paper:
            return paper.oa_url or paper.pdf_url
        return None

    def _parse_result(self, data: dict) -> Paper:
        # Best OA location
        best_loc = data.get("best_oa_location") or {}
        oa_url = best_loc.get("url") or best_loc.get("url_for_landing_page")
        pdf_url = best_loc.get("url_for_pdf")

        # Authors
        authors = []
        for a in data.get("z_authors", []) or []:
            name_parts = []
            if a.get("given"):
                name_parts.append(a["given"])
            if a.get("family"):
                name_parts.append(a["family"])
            name = " ".join(name_parts) or "Unknown"
            authors.append(Author(name=name, orcid=a.get("ORCID")))

        return Paper(
            title=data.get("title", "Untitled"),
            year=data.get("year"),
            doi=data.get("doi"),
            authors=authors,
            source_journal=data.get("journal_name"),
            publication_date=data.get("published_date"),
            is_open_access=data.get("is_oa"),
            oa_url=oa_url,
            pdf_url=pdf_url,
            paper_type=data.get("genre"),
            source_db="unpaywall",
            source_id=data.get("doi", ""),
            source_url=data.get("doi_url", ""),
        )
