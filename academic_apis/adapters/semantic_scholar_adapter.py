"""Semantic Scholar Academic Graph API adapter.

No key required for basic use (shared 1000 req/sec pool).
With key: 1 req/sec dedicated.
Coverage: 214M papers, 2.49B citations, 79M authors.

Uses direct HTTP calls (requests) instead of the semanticscholar library
to avoid async context issues in thread pool execution.
"""

from __future__ import annotations

import logging

import requests

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.semanticscholar.org/graph/v1"

_PAPER_FIELDS = (
    "paperId,corpusId,externalIds,url,title,abstract,venue,year,"
    "referenceCount,citationCount,influentialCitationCount,"
    "isOpenAccess,openAccessPdf,fieldsOfStudy,publicationTypes,"
    "publicationDate,journal,tldr,authors"
)

# Bulk endpoint does not support tldr, openAccessPdf, etc.
_BULK_FIELDS = (
    "paperId,externalIds,url,title,venue,year,"
    "citationCount,influentialCitationCount,"
    "isOpenAccess,fieldsOfStudy,publicationTypes,"
    "publicationDate,authors"
)


class SemanticScholarAdapter(BaseAdapter):
    name = "semantic_scholar"

    def __init__(self, config: APIConfig) -> None:
        super().__init__(config)
        if config.s2_api_key:
            self._session.headers["x-api-key"] = config.s2_api_key
        self._min_interval = 1.1 if config.s2_api_key else 3.5  # shared pool: be polite

    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
    ) -> list[Paper]:
        self._rate_limit(self._min_interval)

        params: dict[str, str] = {
            "query": query,
            "fields": _PAPER_FIELDS,
            "limit": str(min(max_results, 100)),
        }

        if year_from or year_to:
            y_from = str(year_from) if year_from else ""
            y_to = str(year_to) if year_to else ""
            params["year"] = f"{y_from}-{y_to}"

        # Use bulk endpoint for citation sorting (limited fields)
        if sort_by == "citations":
            endpoint = f"{_BASE_URL}/paper/search/bulk"
            params["fields"] = _BULK_FIELDS
            params["sort"] = "citationCount:desc"
        else:
            endpoint = f"{_BASE_URL}/paper/search"

        try:
            resp = self._request_with_retry(
                "GET", endpoint, params=params,
                rate_limit_interval=self._min_interval,
            )
            data = resp.json()
        except Exception:
            # Fall back to bulk endpoint on any failure from regular search
            if endpoint.endswith("/paper/search"):
                try:
                    endpoint = f"{_BASE_URL}/paper/search/bulk"
                    params["fields"] = _BULK_FIELDS
                    params.pop("limit", None)
                    resp = self._request_with_retry(
                        "GET", endpoint, params=params,
                        rate_limit_interval=self._min_interval,
                    )
                    data = resp.json()
                except Exception as e:
                    logger.error("Semantic Scholar search failed: %s", e)
                    return []
            else:
                return []

        papers = []
        for item in data.get("data", []):
            try:
                papers.append(self._parse_paper(item))
            except Exception as e:
                logger.warning("Failed to parse S2 result: %s", e)
        return papers[:max_results]

    def get_paper(self, identifier: str) -> Paper | None:
        # Normalize DOI format for S2
        if identifier.startswith("10."):
            identifier = f"DOI:{identifier}"
        try:
            resp = self._request_with_retry(
                "GET", f"{_BASE_URL}/paper/{identifier}",
                params={"fields": _PAPER_FIELDS},
                rate_limit_interval=self._min_interval,
            )
            return self._parse_paper(resp.json())
        except Exception as e:
            logger.error("S2 paper lookup failed for %s: %s", identifier, e)
        return None

    def get_citations(self, identifier: str, max_results: int = 50) -> list[Paper]:
        if identifier.startswith("10."):
            identifier = f"DOI:{identifier}"
        try:
            resp = self._request_with_retry(
                "GET", f"{_BASE_URL}/paper/{identifier}/citations",
                params={
                    "fields": "contexts,intents,isInfluential,"
                              "citingPaper.paperId,citingPaper.title,"
                              "citingPaper.year,citingPaper.citationCount,"
                              "citingPaper.authors,citingPaper.externalIds,"
                              "citingPaper.venue",
                    "limit": str(min(max_results, 100)),
                },
                rate_limit_interval=self._min_interval,
            )
            data = resp.json()
            papers = []
            for cit in data.get("data", []):
                citing = cit.get("citingPaper", {})
                if citing and citing.get("title"):
                    papers.append(self._parse_paper(citing))
            return papers
        except Exception as e:
            logger.error("S2 citations failed for %s: %s", identifier, e)
            return []

    def get_references(self, identifier: str, max_results: int = 50) -> list[Paper]:
        if identifier.startswith("10."):
            identifier = f"DOI:{identifier}"
        try:
            resp = self._request_with_retry(
                "GET", f"{_BASE_URL}/paper/{identifier}/references",
                params={
                    "fields": "citedPaper.paperId,citedPaper.title,"
                              "citedPaper.year,citedPaper.citationCount,"
                              "citedPaper.authors,citedPaper.externalIds,"
                              "citedPaper.venue",
                    "limit": str(min(max_results, 100)),
                },
                rate_limit_interval=self._min_interval,
            )
            data = resp.json()
            papers = []
            for ref in data.get("data", []):
                cited = ref.get("citedPaper", {})
                if cited and cited.get("title"):
                    papers.append(self._parse_paper(cited))
            return papers
        except Exception as e:
            logger.error("S2 references failed for %s: %s", identifier, e)
            return []

    def _parse_paper(self, item: dict) -> Paper:
        # Authors
        authors = []
        for a in (item.get("authors") or []):
            authors.append(Author(
                name=a.get("name", "Unknown"),
                source_id=str(a.get("authorId", "")),
            ))

        # External IDs
        ext_ids = item.get("externalIds") or {}
        doi = ext_ids.get("DOI")

        # Open access PDF
        oa_pdf = item.get("openAccessPdf") or {}
        pdf_url = oa_pdf.get("url")

        # TLDR
        tldr_obj = item.get("tldr")
        tldr_text = tldr_obj.get("text") if isinstance(tldr_obj, dict) else None

        # Journal
        journal_obj = item.get("journal") or {}
        journal_name = journal_obj.get("name") if isinstance(journal_obj, dict) else None
        venue = item.get("venue")

        pub_types = item.get("publicationTypes") or []

        return Paper(
            title=item.get("title") or "Untitled",
            year=item.get("year"),
            doi=doi,
            abstract=item.get("abstract"),
            authors=authors,
            citation_count=item.get("citationCount"),
            reference_count=item.get("referenceCount"),
            influential_citation_count=item.get("influentialCitationCount"),
            source_journal=journal_name or venue,
            publication_date=item.get("publicationDate"),
            is_open_access=item.get("isOpenAccess"),
            pdf_url=pdf_url,
            fields_of_study=item.get("fieldsOfStudy") or [],
            paper_type=pub_types[0] if pub_types else None,
            tldr=tldr_text,
            source_db="semantic_scholar",
            source_id=str(item.get("paperId") or ""),
            source_url=item.get("url") or "",
            raw=item,
        )
