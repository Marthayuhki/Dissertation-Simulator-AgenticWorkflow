"""PubMed E-utilities (NCBI) API adapter.

No API key required (3 req/sec). Key optional for 10 req/sec.
Coverage: 37M+ biomedical citations and abstracts.
Response: XML/JSON.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)

_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedAdapter(BaseAdapter):
    name = "pubmed"

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
        # Build query with date filter
        q = query
        if year_from and year_to:
            q += f" AND {year_from}:{year_to}[dp]"
        elif year_from:
            q += f" AND {year_from}:3000[dp]"
        elif year_to:
            q += f" AND 1900:{year_to}[dp]"

        sort_map = {"relevance": "relevance", "date": "pub+date", "citations": "relevance"}

        # Step 1: ESearch to get PMIDs
        try:
            resp = self._request_with_retry(
                "GET",
                f"{_BASE_URL}/esearch.fcgi",
                params={
                    "db": "pubmed",
                    "term": q,
                    "retmax": min(max_results, 100),
                    "retmode": "json",
                    "sort": sort_map.get(sort_by, "relevance"),
                },
                rate_limit_interval=0.35,
            )
            data = resp.json()
        except Exception as e:
            logger.error("PubMed search failed: %s", e)
            return []

        id_list = data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        # Step 2: EFetch to get full records
        return self._fetch_records(id_list)

    def get_paper(self, identifier: str) -> Paper | None:
        """Get paper by PMID or DOI."""
        if identifier.startswith("10."):
            # Search by DOI
            try:
                resp = self._request_with_retry(
                    "GET",
                    f"{_BASE_URL}/esearch.fcgi",
                    params={"db": "pubmed", "term": f"{identifier}[doi]", "retmax": 1, "retmode": "json"},
                    rate_limit_interval=0.35,
                )
                ids = resp.json().get("esearchresult", {}).get("idlist", [])
                if not ids:
                    return None
                identifier = ids[0]
            except Exception as e:
                logger.error("PubMed DOI lookup failed: %s", e)
                return None

        papers = self._fetch_records([identifier])
        return papers[0] if papers else None

    def _fetch_records(self, pmids: list[str]) -> list[Paper]:
        """Fetch full records for a list of PMIDs."""
        try:
            resp = self._request_with_retry(
                "GET",
                f"{_BASE_URL}/efetch.fcgi",
                params={
                    "db": "pubmed",
                    "id": ",".join(pmids),
                    "rettype": "xml",
                    "retmode": "xml",
                },
                rate_limit_interval=0.35,
            )
        except Exception as e:
            logger.error("PubMed efetch failed: %s", e)
            return []

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            logger.error("PubMed XML parse error: %s", e)
            return []

        papers = []
        for article_el in root.iter("PubmedArticle"):
            try:
                papers.append(self._parse_article(article_el))
            except Exception as e:
                logger.warning("Failed to parse PubMed article: %s", e)

        return papers

    def _parse_article(self, article_el: ET.Element) -> Paper:
        medline = article_el.find("MedlineCitation")
        if medline is None:
            return Paper(title="Untitled", source_db="pubmed")

        article = medline.find("Article")
        if article is None:
            return Paper(title="Untitled", source_db="pubmed")

        # PMID
        pmid_el = medline.find("PMID")
        pmid = pmid_el.text if pmid_el is not None else ""

        # Title — use itertext() to capture inline tags (<i>, <sup>, etc.)
        title_el = article.find("ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else "Untitled"
        if not title:
            title = "Untitled"

        # Abstract — use itertext() for each AbstractText to handle inline markup
        abstract_el = article.find("Abstract")
        abstract = None
        if abstract_el is not None:
            parts = []
            for text_el in abstract_el.iter("AbstractText"):
                label = text_el.get("Label", "")
                text = "".join(text_el.itertext()).strip()
                if label and text:
                    parts.append(f"{label}: {text}")
                elif text:
                    parts.append(text)
            abstract = " ".join(parts) if parts else None

        # Authors
        authors = []
        author_list = article.find("AuthorList")
        if author_list is not None:
            for author_el in author_list.iter("Author"):
                last = author_el.findtext("LastName", "")
                first = author_el.findtext("ForeName", "") or author_el.findtext("Initials", "")
                name = f"{first} {last}".strip()
                if not name:
                    name = author_el.findtext("CollectiveName", "Unknown")

                # Affiliation
                aff_el = author_el.find("AffiliationInfo")
                aff = aff_el.findtext("Affiliation") if aff_el is not None else None

                # ORCID
                orcid = None
                for id_el in author_el.iter("Identifier"):
                    if id_el.get("Source") == "ORCID":
                        orcid = id_el.text

                authors.append(Author(name=name, orcid=orcid, affiliation=aff))

        # Journal
        journal_el = article.find("Journal")
        journal = None
        if journal_el is not None:
            journal = journal_el.findtext("Title") or journal_el.findtext("ISOAbbreviation")

        # Date
        year = None
        pub_date = article.find("Journal/JournalIssue/PubDate")
        if pub_date is not None:
            year_str = pub_date.findtext("Year")
            if year_str and year_str.isdigit():
                year = int(year_str)

        # DOI
        doi = None
        pubmed_data = article_el.find("PubmedData")
        if pubmed_data is not None:
            for id_el in pubmed_data.iter("ArticleId"):
                if id_el.get("IdType") == "doi":
                    doi = id_el.text

        # MeSH terms as keywords
        keywords = []
        mesh_list = medline.find("MeshHeadingList")
        if mesh_list is not None:
            for mesh in mesh_list.iter("MeshHeading"):
                desc = mesh.findtext("DescriptorName")
                if desc:
                    keywords.append(desc)

        # Publication type
        pub_types = []
        for pt in article.iter("PublicationType"):
            if pt.text:
                pub_types.append(pt.text)
        paper_type = pub_types[0] if pub_types else None

        # Language
        lang = article.findtext("Language")

        return Paper(
            title=title,
            year=year,
            doi=doi,
            abstract=abstract,
            authors=authors,
            source_journal=journal,
            language=lang,
            paper_type=paper_type,
            keywords=keywords,
            fields_of_study=["Medicine", "Biology"],
            source_db="pubmed",
            source_id=pmid,
            source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        )
