"""KCI (Korea Citation Index) API adapter.

API key required (free, via kci.go.kr or data.go.kr).
Coverage: Korean academic journals with citation data and impact factors.
Response: XML.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)


class KCIAdapter(BaseAdapter):
    name = "kci"

    def __init__(self, config: APIConfig) -> None:
        super().__init__(config)

    def is_available(self) -> bool:
        return bool(self.config.kci_api_key)

    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
    ) -> list[Paper]:
        params: dict[str, str] = {
            "key": self.config.kci_api_key,
            "apiCode": "articleSearch",
            "title": query,
            "displayCount": str(min(max_results, 100)),
        }

        sort_map = {"relevance": "accuracy", "date": "pubYear", "citations": "accuracy"}
        params["sortNm"] = sort_map.get(sort_by, "accuracy")
        params["sortDir"] = "desc"

        if year_from:
            params["dateFrom"] = f"{year_from}01"
        if year_to:
            params["dateTo"] = f"{year_to}12"

        try:
            resp = self._request_with_retry(
                "GET",
                self.config.kci_base_url,
                params=params,
                rate_limit_interval=0.5,
            )
            return self._parse_xml_results(resp.content)
        except Exception as e:
            logger.error("KCI search failed: %s", e)
            return []

    def search_by_keyword(self, keyword: str, **kwargs) -> list[Paper]:
        """Search using keyword field instead of title."""
        params: dict[str, str] = {
            "key": self.config.kci_api_key,
            "apiCode": "articleSearch",
            "keyword": keyword,
            "displayCount": str(kwargs.get("max_results", 50)),
            "sortNm": "accuracy",
            "sortDir": "desc",
        }
        try:
            resp = self._request_with_retry(
                "GET", self.config.kci_base_url, params=params, rate_limit_interval=0.5,
            )
            return self._parse_xml_results(resp.content)
        except Exception as e:
            logger.error("KCI keyword search failed: %s", e)
            return []

    def get_paper(self, identifier: str) -> Paper | None:
        """Get paper by DOI via KCI."""
        params = {
            "key": self.config.kci_api_key,
            "apiCode": "articleDetail",
            "doi": identifier,
        }
        try:
            resp = self._request_with_retry(
                "GET", self.config.kci_base_url, params=params, rate_limit_interval=0.5,
            )
            papers = self._parse_xml_results(resp.content)
            return papers[0] if papers else None
        except Exception as e:
            logger.error("KCI lookup failed for %s: %s", identifier, e)
        return None

    def get_citations(self, identifier: str, max_results: int = 50) -> list[Paper]:
        """Get citations via KCI citation API."""
        params = {
            "key": self.config.kci_api_key,
            "apiCode": "citation",
            "doi": identifier,
            "displayCount": str(min(max_results, 100)),
        }
        try:
            resp = self._request_with_retry(
                "GET", self.config.kci_base_url, params=params, rate_limit_interval=0.5,
            )
            return self._parse_xml_results(resp.content)
        except Exception as e:
            logger.error("KCI citations failed for %s: %s", identifier, e)
            return []

    def _parse_xml_results(self, content: bytes) -> list[Paper]:
        """Parse KCI XML response into Paper objects."""
        papers = []
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.error("KCI XML parse error: %s", e)
            return []

        # Try multiple possible element paths
        for record in root.iter("record"):
            try:
                papers.append(self._parse_record(record))
            except Exception as e:
                logger.warning("Failed to parse KCI record: %s", e)

        # Also try 'item' elements
        if not papers:
            for record in root.iter("item"):
                try:
                    papers.append(self._parse_record(record))
                except Exception:
                    pass

        return papers

    def _parse_record(self, record: ET.Element) -> Paper:
        def _text(tag: str) -> str | None:
            el = record.find(tag)
            return el.text.strip() if el is not None and el.text else None

        title = _text("title") or _text("articleTitle") or "Untitled"
        doi = _text("doi")
        year_str = _text("pubYear") or _text("year")
        year = int(year_str) if year_str and year_str.isdigit() else None

        # Authors - may be comma-separated or in sub-elements
        author_text = _text("author") or _text("authors") or ""
        authors = []
        if author_text:
            for name in author_text.split(";"):
                name = name.strip()
                if name:
                    authors.append(Author(name=name))

        journal = _text("journalTitle") or _text("journal")

        return Paper(
            title=title,
            year=year,
            doi=doi,
            abstract=_text("abstract"),
            authors=authors,
            source_journal=journal,
            language="ko",
            source_db="kci",
            source_id=_text("articleId") or doi or "",
            source_url=_text("url") or "",
        )
