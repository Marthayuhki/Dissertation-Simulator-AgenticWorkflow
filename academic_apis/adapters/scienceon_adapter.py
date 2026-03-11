"""ScienceON (formerly NDSL) API adapter.

Credentials required (free via ScienceON portal).
Coverage: Korean science and technology papers, patents, reports.
Response: XML.
"""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)


class ScienceONAdapter(BaseAdapter):
    name = "scienceon"

    def __init__(self, config: APIConfig) -> None:
        super().__init__(config)

    def is_available(self) -> bool:
        return bool(self.config.scienceon_client_id and self.config.scienceon_token)

    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
    ) -> list[Paper]:
        # Build search query in ScienceON JSON format
        search_conditions = [{"field": "BI", "value": query}]
        if year_from:
            search_conditions.append({"field": "PY", "value": f">={year_from}"})
        if year_to:
            search_conditions.append({"field": "PY", "value": f"<={year_to}"})

        search_query = json.dumps(search_conditions, ensure_ascii=False)

        sort_map = {"relevance": "relevance", "date": "pubyear", "citations": "relevance"}

        params: dict[str, str] = {
            "client_id": self.config.scienceon_client_id,
            "token": self.config.scienceon_token,
            "version": "1.0",
            "action": "search",
            "target": "ARTI",
            "searchQuery": search_query,  # requests handles URL encoding
            "sortField": sort_map.get(sort_by, "relevance"),
            "curPage": "1",
            "rowCount": str(min(max_results, 100)),
        }

        try:
            resp = self._request_with_retry(
                "GET",
                self.config.scienceon_base_url,
                params=params,
                rate_limit_interval=1.0,
            )
            return self._parse_xml_results(resp.content)
        except Exception as e:
            logger.error("ScienceON search failed: %s", e)
            return []

    def get_paper(self, identifier: str) -> Paper | None:
        """ScienceON lookup by DOI via search."""
        search_query = json.dumps([{"field": "DI", "value": identifier}])
        params = {
            "client_id": self.config.scienceon_client_id,
            "token": self.config.scienceon_token,
            "version": "1.0",
            "action": "search",
            "target": "ARTI",
            "searchQuery": search_query,  # requests handles URL encoding
            "rowCount": "1",
        }
        try:
            resp = self._request_with_retry(
                "GET", self.config.scienceon_base_url, params=params, rate_limit_interval=1.0,
            )
            papers = self._parse_xml_results(resp.content)
            return papers[0] if papers else None
        except Exception as e:
            logger.error("ScienceON lookup failed: %s", e)
        return None

    def _parse_xml_results(self, content: bytes) -> list[Paper]:
        papers = []
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.error("ScienceON XML parse error: %s", e)
            return []

        for record in root.iter("record"):
            try:
                papers.append(self._parse_record(record))
            except Exception as e:
                logger.warning("Failed to parse ScienceON record: %s", e)

        return papers

    def _parse_record(self, record: ET.Element) -> Paper:
        def _text(tag: str) -> str | None:
            el = record.find(tag)
            return el.text.strip() if el is not None and el.text else None

        title = _text("title") or _text("TI") or "Untitled"

        authors = []
        author_text = _text("author") or _text("AU") or ""
        for name in author_text.split(";"):
            name = name.strip()
            if name:
                authors.append(Author(name=name))

        year_str = _text("pubYear") or _text("PY")
        year = int(year_str) if year_str and year_str.isdigit() else None

        return Paper(
            title=title,
            year=year,
            doi=_text("doi") or _text("DI"),
            abstract=_text("abstract") or _text("AB"),
            authors=authors,
            source_journal=_text("journalTitle") or _text("JT"),
            language="ko",
            source_db="scienceon",
            source_id=_text("cn") or _text("CN") or "",
            source_url=_text("url") or "",
        )
