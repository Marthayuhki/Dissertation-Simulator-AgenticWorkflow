"""KCI adapter (keyless) — portal search + OAI-PMH enrichment.

No API key required. Uses two complementary access methods:
1. KCI Portal search (keyword search, structured HTML scraping)
2. KCI OAI-PMH 2.0 (date-range harvest, single record retrieval)

Coverage: 2.36M+ articles from 2,500+ Korean academic journals.
Operated by NRF (National Research Foundation of Korea).
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)

_OAI_ENDPOINT = "https://open.kci.go.kr/oai/request"
_PORTAL_SEARCH_URL = "https://www.kci.go.kr/kciportal/po/search/poArtiSearList.kci"
_ARTICLE_BASE_URL = (
    "https://www.kci.go.kr/kciportal/ci/sereArticleSearch/"
    "ciSereArtiView.kci?sereArticleSearchBean.artiId="
)

# OAI-PMH namespaces
_NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "kci": "http://www.kci.go.kr/kciportal/OAI/",
}

# Regex patterns for parsing KCI portal search HTML
_RE_ARTICLE = re.compile(
    r'fnArtiDetail\([\'"]+(ART\d+)[\'"].*?class="subject">\s*(.*?)\s*</a>'
    r'(.*?)</ul>\s*<ul class="nopm floats subject-info2">(.*?)</ul>',
    re.DOTALL,
)
_RE_AUTHOR = re.compile(
    r'poCretDetail\.kci\?[^"]*">\s*([^<]+?)\s*</a>', re.DOTALL
)
_RE_ORCID = re.compile(r'orcid\.org/([0-9X-]+)')
_RE_JOURNAL = re.compile(
    r'ciSereInfoView\.kci\?[^"]*">\s*([^<]+?)\s*</a>', re.DOTALL
)
_RE_VOLUME = re.compile(
    r'poSereArtiList\.kci\?[^"]*">\s*([^<]+?)\s*</a>', re.DOTALL
)
_RE_PAGES = re.compile(r'pp\.(\d+~\d+)')
_RE_DATE = re.compile(r'<li>(\d{4}\.\d{2})</li>')
_RE_FIELD = re.compile(r'<li>([^<]{2,50})</li>')
_RE_CITATION = re.compile(r'#listCita[^>]*>\s*(\d+)\s*</a>')
_RE_KCI_TYPE = re.compile(r'type-ico\d[^"]*"[^>]*>([^<]+)')


class KCIOaiAdapter(BaseAdapter):
    """KCI adapter for Korean academic articles (keyless).

    Uses KCI portal for keyword search (fast, accurate),
    and OAI-PMH for date-range harvest and single record retrieval.
    """

    name = "kci_oai"

    # ── Portal-based keyword search ──────────────────────────────

    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
    ) -> list[Paper]:
        """Search KCI via portal (keyword search, keyless)."""
        if not query:
            return []

        papers: list[Paper] = []
        page = 1
        page_size = min(max_results, 50)

        while len(papers) < max_results:
            try:
                params: dict[str, str] = {
                    "poSearchBean.queryText": query,
                    "poSearchBean.searType": "article",
                    "poSearchBean.docsCount": str(page_size),
                    "poSearchBean.startPg": str(page),
                }
                if year_from:
                    params["poSearchBean.pubiStYr"] = str(year_from)
                if year_to:
                    params["poSearchBean.pubiEndYr"] = str(year_to)

                resp = self._request_with_retry(
                    "GET", _PORTAL_SEARCH_URL,
                    params=params, rate_limit_interval=1.0,
                )

                new_papers = self._parse_portal_html(resp.text)
                if not new_papers:
                    break

                papers.extend(new_papers)
                page += 1

                # Portal returns max 50 per page
                if len(new_papers) < page_size:
                    break

            except Exception as e:
                logger.error("KCI portal search failed: %s", e)
                break

        return papers[:max_results]

    def _parse_portal_html(self, html: str) -> list[Paper]:
        """Parse KCI portal search result HTML into Paper objects."""
        papers: list[Paper] = []

        # Split by article entries
        articles = _RE_ARTICLE.findall(html)

        for art_id, raw_title, info_block, info2_block in articles:
            # Title: strip HTML tags (including <em> highlights)
            title = re.sub(r"<[^>]+>", "", raw_title).strip() or "Untitled"

            # Authors
            authors: list[Author] = []
            author_names = _RE_AUTHOR.findall(info_block)
            orcids = _RE_ORCID.findall(info_block)
            for i, name in enumerate(author_names):
                orcid = orcids[i] if i < len(orcids) else None
                authors.append(Author(name=name.strip(), orcid=orcid))

            # Journal
            journal_match = _RE_JOURNAL.search(info_block)
            journal = journal_match.group(1).strip() if journal_match else None

            # Volume/issue
            vol_match = _RE_VOLUME.search(info_block)

            # Pages
            pages_match = _RE_PAGES.search(info_block)

            # Date (YYYY.MM format)
            date_match = _RE_DATE.search(info_block)
            year = None
            pub_date = None
            if date_match:
                pub_date = date_match.group(1)
                year_str = pub_date.split(".")[0]
                if year_str.isdigit():
                    year = int(year_str)

            # Field/category — last <li> items that aren't dates/pages/volumes
            field_matches = _RE_FIELD.findall(info_block)
            keywords = []
            for fm in field_matches:
                fm = fm.strip()
                # Exclude dates, pages, and volume patterns
                if (fm and not re.match(r"\d{4}\.\d{2}", fm)
                        and not fm.startswith("pp.") and not fm.startswith("KCI")):
                    keywords.append(fm)

            # Citation count
            cite_match = _RE_CITATION.search(info2_block)
            citation_count = int(cite_match.group(1)) if cite_match else None

            # KCI registration type (등재, 등재후보, etc.)
            kci_type = _RE_KCI_TYPE.search(html[html.find(art_id) - 200:html.find(art_id)])

            papers.append(Paper(
                title=title,
                year=year,
                doi=None,
                abstract=None,  # Portal search doesn't include abstracts
                authors=authors,
                source_journal=journal,
                citation_count=citation_count,
                publication_date=pub_date,
                language="ko",
                keywords=keywords,
                source_db="kci_oai",
                source_id=art_id,
                source_url=f"{_ARTICLE_BASE_URL}{art_id}",
            ))

        return papers

    # ── OAI-PMH methods ──────────────────────────────────────────

    def get_paper(self, identifier: str) -> Paper | None:
        """Get a single record by KCI article ID or OAI identifier.

        identifier formats: 'ART003258148', 'oai:kci.go.kr:ARTI/12578', or '12578'
        """
        # Convert article ID to OAI format
        if identifier.startswith("ART"):
            # Can't use OAI-PMH with ART IDs — they differ from OAI IDs
            # Fall back to portal detail page scraping (future enhancement)
            logger.info("ART-style IDs not supported for OAI-PMH get_paper: %s", identifier)
            return None

        if not identifier.startswith("oai:"):
            identifier = f"oai:kci.go.kr:ARTI/{identifier}"

        try:
            resp = self._request_with_retry(
                "GET", _OAI_ENDPOINT,
                params={
                    "verb": "GetRecord",
                    "identifier": identifier,
                    "metadataPrefix": "oai_kci",
                },
                rate_limit_interval=1.0,
            )
            root = ET.fromstring(resp.content)

            record = root.find(".//oai:record", _NS)
            if record is not None:
                return self._parse_oai_record(record)
        except Exception as e:
            logger.error("KCI OAI GetRecord failed for %s: %s", identifier, e)
        return None

    def harvest(
        self,
        from_date: str | None = None,
        until_date: str | None = None,
        max_records: int = 100,
    ) -> list[Paper]:
        """Harvest records from KCI OAI-PMH by date range.

        Args:
            from_date: Start date (YYYY-MM-DD)
            until_date: End date (YYYY-MM-DD)
            max_records: Maximum records to harvest

        Returns:
            List of Paper objects from KCI.
        """
        return self._list_records(
            from_date=from_date,
            until_date=until_date,
            max_records=max_records,
        )

    def _list_records(
        self,
        from_date: str | None = None,
        until_date: str | None = None,
        max_records: int = 200,
    ) -> list[Paper]:
        """Fetch records via OAI-PMH ListRecords with resumptionToken support."""
        papers: list[Paper] = []

        params: dict[str, str] = {
            "verb": "ListRecords",
            "set": "ARTI",
            "metadataPrefix": "oai_kci",
        }
        if from_date:
            params["from"] = from_date
        if until_date:
            params["until"] = until_date

        while len(papers) < max_records:
            try:
                resp = self._request_with_retry(
                    "GET", _OAI_ENDPOINT,
                    params=params, timeout=60, rate_limit_interval=1.0,
                )
                root = ET.fromstring(resp.content)
            except Exception as e:
                logger.error("KCI OAI ListRecords failed: %s", e)
                break

            # Check for OAI-PMH errors
            error = root.find(".//oai:error", _NS)
            if error is not None:
                code = error.get("code", "")
                logger.warning("KCI OAI error: %s — %s", code, error.text)
                break

            # Parse records
            records = root.findall(".//oai:record", _NS)
            for record in records:
                if len(papers) >= max_records:
                    break
                try:
                    paper = self._parse_oai_record(record)
                    if paper:
                        papers.append(paper)
                except Exception as e:
                    logger.warning("Failed to parse KCI record: %s", e)

            # Check for resumptionToken (pagination)
            token_el = root.find(".//oai:resumptionToken", _NS)
            if token_el is not None and token_el.text:
                params = {"verb": "ListRecords", "resumptionToken": token_el.text}
            else:
                break

        return papers

    # ── OAI-PMH record parsing ───────────────────────────────────

    def _parse_oai_record(self, record: ET.Element) -> Paper | None:
        """Parse a single OAI-PMH record into a Paper object."""
        header = record.find("oai:header", _NS)
        if header is not None and header.get("status") == "deleted":
            return None

        oai_id = ""
        id_el = header.find("oai:identifier", _NS) if header is not None else None
        if id_el is not None and id_el.text:
            oai_id = id_el.text

        metadata = record.find("oai:metadata", _NS)
        if metadata is None:
            return None

        return self._parse_kci_metadata(metadata, oai_id)

    def _parse_kci_metadata(self, metadata: ET.Element, oai_id: str) -> Paper:
        """Parse oai_kci extended metadata."""
        kci_root = metadata.find("kci:oai_kci", _NS)
        if kci_root is None:
            kci_root = metadata[0] if len(metadata) > 0 else metadata

        journal_info = kci_root.find("kci:journalInfo", _NS)
        article_info = kci_root.find("kci:articleInfo", _NS)

        def _find_text(parent: ET.Element | None, tag: str) -> str | None:
            if parent is None:
                return None
            el = parent.find(f"kci:{tag}", _NS)
            return el.text.strip() if el is not None and el.text else None

        # Title
        title = "Untitled"
        if article_info is not None:
            title_group = article_info.find("kci:title-group", _NS)
            if title_group is not None:
                for t in title_group.findall("kci:article-title", _NS):
                    lang = t.get("lang", "")
                    if lang == "original" and t.text:
                        title = t.text.strip()
                        break
                    if lang == "english" and t.text and title == "Untitled":
                        title = t.text.strip()

        # Authors
        authors: list[Author] = []
        if article_info is not None:
            author_name_block = article_info.find("kci:author-name", _NS)
            if author_name_block is not None:
                for a in author_name_block.findall("kci:author", _NS):
                    name = _find_text(a, "name") or ""
                    aff = _find_text(a, "affiliation")
                    if name:
                        authors.append(Author(name=name, affiliation=aff))

        # Fallback: author-group
        if not authors and article_info is not None:
            author_group = article_info.find("kci:author-group", _NS)
            if author_group is not None:
                for a in author_group.findall("kci:author", _NS):
                    raw = a.text.strip() if a.text else ""
                    if raw:
                        if "(" in raw and raw.endswith(")"):
                            name = raw[:raw.index("(")].strip()
                            aff = raw[raw.index("(") + 1:-1].strip()
                            authors.append(Author(name=name, affiliation=aff))
                        else:
                            authors.append(Author(name=raw))

        # Abstract
        abstract = None
        if article_info is not None:
            abstract_group = article_info.find("kci:abstract-group", _NS)
            if abstract_group is not None:
                for ab in abstract_group.findall("kci:abstract", _NS):
                    lang = ab.get("lang", "")
                    if lang == "original" and ab.text:
                        abstract = ab.text.strip()
                        break
                    if lang == "english" and ab.text and abstract is None:
                        abstract = ab.text.strip()

        # Year
        year = None
        year_str = _find_text(journal_info, "pub-year")
        if year_str and year_str.isdigit():
            year = int(year_str)

        # Other fields
        uci = _find_text(article_info, "uci")
        citation_count_str = _find_text(article_info, "citation-count")
        citation_count = (
            int(citation_count_str)
            if citation_count_str and citation_count_str.isdigit()
            else None
        )
        article_id = article_info.get("article-id", "") if article_info is not None else ""
        url = _find_text(article_info, "url") or ""
        is_oa = _find_text(article_info, "orte-open-yn") == "Y"
        language = _find_text(article_info, "language") or "ko"
        journal_name = _find_text(journal_info, "journal-name")
        categories = _find_text(article_info, "article-categories")

        return Paper(
            title=title,
            year=year,
            doi=None,
            abstract=abstract,
            authors=authors,
            source_journal=journal_name,
            citation_count=citation_count,
            is_open_access=is_oa,
            language=language,
            keywords=[categories] if categories else [],
            source_db="kci_oai",
            source_id=uci or article_id or oai_id,
            source_url=url or (
                f"{_ARTICLE_BASE_URL}{article_id}" if article_id else ""
            ),
        )
