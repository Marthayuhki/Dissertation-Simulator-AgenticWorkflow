"""OpenAlex API adapter.

API key required (free, $1/day credit).
Coverage: ~270M+ works, broadest free scholarly database.
"""

from __future__ import annotations

import logging

import pyalex
from pyalex import Works, Authors

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)


class OpenAlexAdapter(BaseAdapter):
    name = "openalex"

    def __init__(self, config: APIConfig) -> None:
        super().__init__(config)
        if config.openalex_api_key:
            pyalex.config.api_key = config.openalex_api_key

    def is_available(self) -> bool:
        return bool(self.config.openalex_api_key)

    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
    ) -> list[Paper]:
        self._rate_limit(0.01)  # 100 req/sec

        try:
            w = Works().search(query)

            if year_from and year_to:
                w = w.filter(publication_year=f"{year_from}-{year_to}")
            elif year_from:
                w = w.filter(publication_year=f">{year_from - 1}")
            elif year_to:
                w = w.filter(publication_year=f"<{year_to + 1}")

            sort_map = {
                "relevance": "relevance_score",
                "citations": "cited_by_count",
                "date": "publication_year",
            }
            sort_field = sort_map.get(sort_by, "relevance_score")
            w = w.sort(**{sort_field: "desc"})

            results = w.get(per_page=min(max_results, 200))
            return [self._parse_work(item) for item in results]
        except Exception as e:
            logger.error("OpenAlex search failed: %s", e)
            return []

    def get_paper(self, identifier: str) -> Paper | None:
        self._rate_limit(0.01)
        try:
            # Accept DOI URL or OpenAlex ID
            if identifier.startswith("10."):
                identifier = f"https://doi.org/{identifier}"
            work = Works()[identifier]
            if work:
                return self._parse_work(work)
        except Exception as e:
            logger.error("OpenAlex lookup failed for %s: %s", identifier, e)
        return None

    def get_citations(self, identifier: str, max_results: int = 50) -> list[Paper]:
        self._rate_limit(0.01)
        try:
            # identifier should be an OpenAlex work ID like W2741809807
            results = Works().filter(cites=identifier).sort(cited_by_count="desc").get(
                per_page=min(max_results, 200)
            )
            return [self._parse_work(item) for item in results]
        except Exception as e:
            logger.error("OpenAlex citations failed for %s: %s", identifier, e)
            return []

    def get_references(self, identifier: str, max_results: int = 50) -> list[Paper]:
        """Get referenced works from a paper's referenced_works field."""
        self._rate_limit(0.01)
        try:
            work = Works()[identifier]
            ref_ids = work.get("referenced_works", [])
            if not ref_ids:
                return []
            # Batch lookup (OpenAlex supports pipe-separated IDs in filter)
            batch = ref_ids[:max_results]
            results = Works().filter(openalex="|".join(batch)).get(per_page=len(batch))
            return [self._parse_work(item) for item in results]
        except Exception as e:
            logger.error("OpenAlex references failed for %s: %s", identifier, e)
            return []

    def _parse_work(self, item: dict) -> Paper:
        # Authors — guard against None author_info or institutions
        authors = []
        for authorship in (item.get("authorships") or []):
            author_info = authorship.get("author") or {}
            institutions = authorship.get("institutions") or []
            aff = institutions[0].get("display_name") if institutions and isinstance(institutions[0], dict) else None
            authors.append(Author(
                name=author_info.get("display_name", "Unknown"),
                orcid=author_info.get("orcid"),
                affiliation=aff,
                source_id=author_info.get("id"),
            ))

        # Source/journal
        primary_loc = item.get("primary_location", {}) or {}
        source = primary_loc.get("source", {}) or {}
        journal = source.get("display_name")

        # Open access
        oa = item.get("open_access", {}) or {}
        oa_url = oa.get("oa_url")

        # Topic / fields of study
        topics = item.get("topics", [])
        fields = [t.get("display_name", "") for t in topics if t.get("display_name")]

        # Keywords
        kw_list = item.get("keywords", [])
        keywords = [k.get("keyword", "") for k in kw_list if k.get("keyword")]

        # Abstract reconstruction from inverted index
        abstract = None
        inv_idx = item.get("abstract_inverted_index")
        if inv_idx and isinstance(inv_idx, dict):
            try:
                word_positions: list[tuple[int, str]] = []
                for word, positions in inv_idx.items():
                    for pos in positions:
                        word_positions.append((pos, word))
                word_positions.sort(key=lambda x: x[0])
                abstract = " ".join(w for _, w in word_positions)
            except Exception:
                pass

        # Citation percentile
        cit_pct = item.get("citation_normalized_percentile", {}) or {}
        percentile = cit_pct.get("value")

        # References
        refs = item.get("referenced_works", [])

        doi_raw = item.get("doi")
        doi = doi_raw.replace("https://doi.org/", "") if doi_raw else None

        return Paper(
            title=item.get("display_name", "Untitled"),
            year=item.get("publication_year"),
            doi=doi,
            abstract=abstract,
            authors=authors,
            citation_count=item.get("cited_by_count"),
            reference_count=item.get("referenced_works_count"),
            source_journal=journal,
            publication_date=item.get("publication_date"),
            is_open_access=oa.get("is_oa"),
            oa_url=oa_url,
            language=item.get("language"),
            paper_type=item.get("type"),
            keywords=keywords,
            fields_of_study=fields,
            references=refs,
            fwci=item.get("fwci"),
            citation_percentile=percentile,
            source_db="openalex",
            source_id=item.get("id", ""),
            source_url=item.get("id", ""),
            raw=item,
        )
