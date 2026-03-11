"""OpenCitations API adapter (Index v2 + Meta v1).

No API key required. Completely open.
Coverage: 2.2B+ citation records, all disciplines.
Response: JSON.
"""

from __future__ import annotations

import logging

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)

_INDEX_URL = "https://api.opencitations.net/index/v2"
_META_URL = "https://api.opencitations.net/meta/v1"


class OpenCitationsAdapter(BaseAdapter):
    """OpenCitations adapter for citation graph traversal.

    Unlike other adapters, OpenCitations excels at citation relationships
    rather than keyword search. Use get_citations/get_references.
    For keyword search, use other adapters and then enrich with citation data.
    """

    name = "opencitations"

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
        """OpenCitations doesn't support keyword search.

        This is a no-op — use other adapters for search, then
        use get_citations/get_references for citation enrichment.
        """
        return []

    def get_paper(self, identifier: str) -> Paper | None:
        """Get paper metadata from OpenCitations Meta."""
        doi = identifier if identifier.startswith("10.") else None
        if not doi:
            return None

        try:
            resp = self._request_with_retry(
                "GET",
                f"{_META_URL}/metadata/doi:{doi}",
                timeout=30,
                rate_limit_interval=0.35,
            )
            data = resp.json()
            if data:
                return self._parse_meta(data[0])
        except Exception as e:
            logger.error("OpenCitations meta lookup failed for %s: %s", identifier, e)
        return None

    def get_citations(self, identifier: str, max_results: int = 50) -> list[Paper]:
        """Get papers that cite the given DOI. Uses OpenCitations Index."""
        doi = identifier if identifier.startswith("10.") else None
        if not doi:
            return []

        try:
            resp = self._request_with_retry(
                "GET",
                f"{_INDEX_URL}/citations/doi:{doi}",
                timeout=30,
                rate_limit_interval=0.35,
            )
            data = resp.json()

            # Extract citing DOIs
            citing_dois = []
            for record in data[:max_results]:
                citing = record.get("citing", "")
                # Format: "doi:10.xxx/yyy"
                if citing.startswith("doi:"):
                    citing_dois.append(citing[4:])
                elif citing.startswith("10."):
                    citing_dois.append(citing)

            # Batch lookup metadata
            return self._batch_meta(citing_dois[:max_results])
        except Exception as e:
            logger.error("OpenCitations citations failed for %s: %s", identifier, e)
            return []

    def get_references(self, identifier: str, max_results: int = 50) -> list[Paper]:
        """Get papers referenced by the given DOI."""
        doi = identifier if identifier.startswith("10.") else None
        if not doi:
            return []

        try:
            resp = self._request_with_retry(
                "GET",
                f"{_INDEX_URL}/references/doi:{doi}",
                timeout=30,
                rate_limit_interval=0.35,
            )
            data = resp.json()

            cited_dois = []
            for record in data[:max_results]:
                cited = record.get("cited", "")
                if cited.startswith("doi:"):
                    cited_dois.append(cited[4:])
                elif cited.startswith("10."):
                    cited_dois.append(cited)

            return self._batch_meta(cited_dois[:max_results])
        except Exception as e:
            logger.error("OpenCitations references failed for %s: %s", identifier, e)
            return []

    def get_citation_count(self, doi: str) -> int | None:
        """Get citation count for a DOI (efficient, single call)."""
        try:
            resp = self._request_with_retry(
                "GET",
                f"{_INDEX_URL}/citation-count/doi:{doi}",
                timeout=15,
                rate_limit_interval=0.35,
            )
            data = resp.json()
            if data:
                return int(data[0].get("count", 0))
        except Exception:
            pass
        return None

    def _batch_meta(self, dois: list[str]) -> list[Paper]:
        """Lookup metadata for multiple DOIs via Meta API."""
        if not dois:
            return []
        # OpenCitations Meta supports batch via space-separated DOIs
        # But we do sequential calls to respect rate limits
        papers = []
        for doi in dois:
            try:
                resp = self._request_with_retry(
                    "GET",
                    f"{_META_URL}/metadata/doi:{doi}",
                    timeout=15,
                    rate_limit_interval=0.35,
                )
                data = resp.json()
                if data:
                    papers.append(self._parse_meta(data[0]))
            except Exception:
                # Skip failures in batch
                papers.append(Paper(
                    title="[Metadata unavailable]",
                    doi=doi,
                    source_db="opencitations",
                    source_id=doi,
                ))
        return papers

    def _parse_meta(self, item: dict) -> Paper:
        # Authors: "family, given; family2, given2"
        authors = []
        author_str = item.get("author", "")
        if author_str:
            for a in author_str.split("; "):
                parts = a.split(", ")
                if len(parts) >= 2:
                    name = f"{parts[1].strip()} {parts[0].strip()}"
                else:
                    name = a.strip()

                # Check for ORCID in brackets
                orcid = None
                if "[" in name and "]" in name:
                    orcid_part = name[name.index("[") + 1:name.index("]")]
                    name = name[:name.index("[")].strip()
                    if "orcid" in orcid_part.lower():
                        orcid = orcid_part.replace("orcid:", "").strip()

                if name:
                    authors.append(Author(name=name, orcid=orcid))

        # Year from pub_date
        pub_date = item.get("pub_date", "")
        year = None
        if pub_date:
            year_str = pub_date[:4]
            if year_str.isdigit():
                year = int(year_str)

        # IDs
        ids = item.get("id", "")
        doi = None
        for id_part in ids.split(" "):
            if id_part.startswith("doi:"):
                doi = id_part[4:]
                break

        return Paper(
            title=item.get("title", "Untitled"),
            year=year,
            doi=doi,
            authors=authors,
            source_journal=item.get("venue"),
            publication_date=pub_date,
            paper_type=item.get("type"),
            source_db="opencitations",
            source_id=doi or ids,
            source_url=f"https://opencitations.net/meta/br/{ids.split(' ')[0]}" if ids else "",
        )
