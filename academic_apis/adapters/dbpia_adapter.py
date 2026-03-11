"""DBpia Open API adapter.

API key required (free registration at api.dbpia.co.kr).
Coverage: Korean journal articles, conference proceedings, magazines.
Response: XML.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)


class DBpiaAdapter(BaseAdapter):
    name = "dbpia"

    def __init__(self, config: APIConfig) -> None:
        super().__init__(config)

    def is_available(self) -> bool:
        return bool(self.config.dbpia_api_key)

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
            "key": self.config.dbpia_api_key,
            "target": "se",
            "searchall": query,
            "pagecount": str(min(max_results, 50)),
            "pagenumber": "1",
        }

        sort_map = {"relevance": "1", "date": "2", "citations": "3"}
        params["sorttype"] = sort_map.get(sort_by, "1")
        params["sortorder"] = "desc"

        if year_from and year_to:
            params["pyear"] = "3"  # custom range
            params["pyear_start"] = str(year_from)
            params["pyear_end"] = str(year_to)
        elif year_from:
            params["pyear"] = "3"
            params["pyear_start"] = str(year_from)
            params["pyear_end"] = "2030"

        try:
            resp = self._request_with_retry(
                "GET",
                self.config.dbpia_base_url,
                params=params,
                rate_limit_interval=0.5,
            )
            return self._parse_xml_results(resp.content)
        except Exception as e:
            logger.error("DBpia search failed: %s", e)
            return []

    def get_paper(self, identifier: str) -> Paper | None:
        """DBpia doesn't have a direct lookup by DOI — search by title."""
        return None

    def _parse_xml_results(self, content: bytes) -> list[Paper]:
        papers = []
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.error("DBpia XML parse error: %s", e)
            return []

        for item in root.iter("item"):
            try:
                papers.append(self._parse_item(item))
            except Exception as e:
                logger.warning("Failed to parse DBpia item: %s", e)

        return papers

    def _parse_item(self, item: ET.Element) -> Paper:
        def _text(tag: str) -> str | None:
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else None

        title = _text("title") or "Untitled"

        # Authors from sub-elements
        authors = []
        for author_el in item.iter("author"):
            name_el = author_el.find("name")
            if name_el is not None and name_el.text:
                authors.append(Author(name=name_el.text.strip()))

        # If no structured authors, try author text
        if not authors:
            author_text = _text("authors")
            if author_text:
                for name in author_text.split(","):
                    name = name.strip()
                    if name:
                        authors.append(Author(name=name))

        # Publication info
        publication = _text("publication") or _text("book")
        link_url = _text("link_url") or _text("linkUrl")

        # Year extraction from publication date or volume info
        year = None
        pub_year = _text("pub_year") or _text("pubYear")
        if pub_year and pub_year.isdigit():
            year = int(pub_year)

        return Paper(
            title=title,
            year=year,
            authors=authors,
            source_journal=publication,
            language="ko",
            source_db="dbpia",
            source_id=_text("node_id") or "",
            source_url=link_url or "",
        )
