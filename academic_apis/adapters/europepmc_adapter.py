"""Europe PMC API adapter.

No API key required. Completely open.
Coverage: 46M+ life science records, 9M+ full text.
Response: JSON/XML.
"""

from __future__ import annotations

import logging

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"


class EuropePMCAdapter(BaseAdapter):
    name = "europepmc"

    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
    ) -> list[Paper]:
        q = query
        if year_from and year_to:
            q += f" PUB_YEAR:[{year_from} TO {year_to}]"
        elif year_from:
            q += f" PUB_YEAR:[{year_from} TO 2099]"
        elif year_to:
            q += f" PUB_YEAR:[1900 TO {year_to}]"

        # Europe PMC: default sort is relevance (no parameter needed).
        # Only "CITED desc" and "DATE desc" are valid explicit sort values.
        sort_map = {
            "citations": "CITED desc",
            "date": "DATE desc",
        }

        params: dict[str, str | int] = {
            "query": q,
            "format": "json",
            "resultType": "core",  # includes abstract
            "pageSize": min(max_results, 100),
        }
        sort_val = sort_map.get(sort_by)
        if sort_val:
            params["sort"] = sort_val

        try:
            resp = self._request_with_retry(
                "GET",
                f"{_BASE_URL}/search",
                params=params,
                rate_limit_interval=0.15,
            )
            data = resp.json()
        except Exception as e:
            logger.error("Europe PMC search failed: %s", e)
            return []

        results = data.get("resultList", {}).get("result", [])
        return [self._parse_result(item) for item in results]

    def get_paper(self, identifier: str) -> Paper | None:
        """Get paper by DOI or PMID."""
        # Try DOI first
        q = f'DOI:"{identifier}"' if identifier.startswith("10.") else f'EXT_ID:{identifier}'
        try:
            resp = self._request_with_retry(
                "GET",
                f"{_BASE_URL}/search",
                params={"query": q, "format": "json", "resultType": "core", "pageSize": 1},
                rate_limit_interval=0.15,
            )
            results = resp.json().get("resultList", {}).get("result", [])
            if results:
                return self._parse_result(results[0])
        except Exception as e:
            logger.error("Europe PMC lookup failed for %s: %s", identifier, e)
        return None

    def get_citations(self, identifier: str, max_results: int = 50) -> list[Paper]:
        """Get papers citing this work via Europe PMC citations API."""
        # Need PMID or PMC ID for citations endpoint
        paper = self.get_paper(identifier)
        if not paper or not paper.source_id:
            return []

        source = "MED"  # default to PubMed
        pmid = paper.source_id

        try:
            resp = self._request_with_retry(
                "GET",
                f"{_BASE_URL}/{source}/{pmid}/citations",
                params={"format": "json", "page": 1, "pageSize": min(max_results, 100)},
                rate_limit_interval=0.15,
            )
            data = resp.json()
            citations = data.get("citationList", {}).get("citation", [])
            papers = []
            for cit in citations:
                papers.append(Paper(
                    title=cit.get("title", "Untitled"),
                    year=int(cit["pubYear"]) if cit.get("pubYear", "").isdigit() else None,
                    doi=cit.get("doi"),
                    authors=[Author(name=cit["authorString"])] if cit.get("authorString") else [],
                    source_journal=cit.get("journalAbbreviation"),
                    source_db="europepmc",
                    source_id=cit.get("id", ""),
                ))
            return papers
        except Exception as e:
            logger.error("Europe PMC citations failed: %s", e)
            return []

    def get_references(self, identifier: str, max_results: int = 50) -> list[Paper]:
        """Get references from a paper."""
        paper = self.get_paper(identifier)
        if not paper or not paper.source_id:
            return []

        source = "MED"
        pmid = paper.source_id

        try:
            resp = self._request_with_retry(
                "GET",
                f"{_BASE_URL}/{source}/{pmid}/references",
                params={"format": "json", "page": 1, "pageSize": min(max_results, 100)},
                rate_limit_interval=0.15,
            )
            data = resp.json()
            refs = data.get("referenceList", {}).get("reference", [])
            papers = []
            for ref in refs:
                papers.append(Paper(
                    title=ref.get("title", "Untitled"),
                    year=int(ref["pubYear"]) if ref.get("pubYear", "").isdigit() else None,
                    doi=ref.get("doi"),
                    authors=[Author(name=ref["authorString"])] if ref.get("authorString") else [],
                    source_journal=ref.get("journalAbbreviation"),
                    source_db="europepmc",
                    source_id=ref.get("id", ""),
                ))
            return papers
        except Exception as e:
            logger.error("Europe PMC references failed: %s", e)
            return []

    def _parse_result(self, item: dict) -> Paper:
        # Authors
        authors = []
        author_str = item.get("authorString", "")
        if author_str:
            for name in author_str.split(", "):
                name = name.strip().rstrip(".")
                if name:
                    authors.append(Author(name=name))

        # Also check authorList for ORCID
        author_list = item.get("authorList", {}).get("author", [])
        if author_list and not authors:
            for a in author_list:
                full = a.get("fullName", "Unknown")
                authors.append(Author(
                    name=full,
                    orcid=a.get("authorId", {}).get("value") if a.get("authorId", {}).get("type") == "ORCID" else None,
                    affiliation=(a.get("affiliation") or [None])[0] if isinstance(a.get("affiliation"), list) else a.get("affiliation"),
                ))

        year = None
        pub_year = item.get("pubYear")
        if pub_year and str(pub_year).isdigit():
            year = int(pub_year)

        # Keywords / MeSH
        keywords = []
        mesh = item.get("meshHeadingList", {}).get("meshHeading", [])
        for m in mesh:
            if m.get("descriptorName"):
                keywords.append(m["descriptorName"])
        kw_list = item.get("keywordList", {}).get("keyword", [])
        keywords.extend(kw_list)

        return Paper(
            title=item.get("title", "Untitled"),
            year=year,
            doi=item.get("doi"),
            abstract=item.get("abstractText"),
            authors=authors,
            citation_count=item.get("citedByCount"),
            source_journal=item.get("journalTitle") or item.get("journalInfo", {}).get("journal", {}).get("title"),
            publication_date=item.get("firstPublicationDate"),
            is_open_access=item.get("isOpenAccess") == "Y",
            language=item.get("language"),
            paper_type=item.get("pubType"),
            keywords=keywords,
            source_db="europepmc",
            source_id=item.get("pmid") or item.get("id", ""),
            source_url=f"https://europepmc.org/article/MED/{item.get('pmid', '')}",
            raw=item,
        )
