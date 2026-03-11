"""RISS (Research Information Sharing Service) API adapter.

API key required (free via data.go.kr).
Coverage: Korean dissertations, domestic/overseas academic papers.
Response: XML.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)


class RISSAdapter(BaseAdapter):
    name = "riss"

    def __init__(self, config: APIConfig) -> None:
        super().__init__(config)

    def is_available(self) -> bool:
        return bool(self.config.riss_api_key)

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
            "serviceKey": self.config.riss_api_key,
            "query": query,
            "displayCount": str(min(max_results, 100)),
            "startCount": "0",
        }

        if year_from:
            params["pubYearFrom"] = str(year_from)
        if year_to:
            params["pubYearTo"] = str(year_to)

        try:
            resp = self._request_with_retry(
                "GET",
                self.config.riss_base_url,
                params=params,
                rate_limit_interval=1.0,
            )
            return self._parse_xml_results(resp.content)
        except Exception as e:
            logger.error("RISS search failed: %s", e)
            return []

    def get_paper(self, identifier: str) -> Paper | None:
        """RISS doesn't provide direct DOI lookup via public API."""
        return None

    def _parse_xml_results(self, content: bytes) -> list[Paper]:
        papers = []
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.error("RISS XML parse error: %s", e)
            return []

        # Try multiple possible structures
        for record in root.iter("record"):
            try:
                papers.append(self._parse_record(record))
            except Exception as e:
                logger.warning("Failed to parse RISS record: %s", e)

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

        authors = []
        author_text = _text("creator") or _text("author") or ""
        for name in author_text.split(";"):
            name = name.strip()
            if name:
                authors.append(Author(name=name))

        year_str = _text("pubYear") or _text("year") or _text("date")
        year = None
        if year_str:
            # Extract 4-digit year
            for part in year_str.split():
                if part.isdigit() and len(part) == 4:
                    year = int(part)
                    break

        return Paper(
            title=title,
            year=year,
            doi=_text("doi"),
            abstract=_text("abstract") or _text("description"),
            authors=authors,
            source_journal=_text("publisher") or _text("source"),
            paper_type=_text("type") or "dissertation",
            language="ko",
            source_db="riss",
            source_id=_text("controlNo") or "",
            source_url=_text("url") or _text("link") or "",
        )
