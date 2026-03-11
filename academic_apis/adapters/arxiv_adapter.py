"""arXiv API adapter.

No authentication required. Rate limit: 1 req / 3 sec.
Coverage: ~3M STEM preprints.
"""

from __future__ import annotations

import logging

import arxiv

from academic_apis.adapters.base import BaseAdapter
from academic_apis.config import APIConfig
from academic_apis.models import Author, Paper

logger = logging.getLogger(__name__)


class ArxivAdapter(BaseAdapter):
    name = "arxiv"

    def __init__(self, config: APIConfig) -> None:
        super().__init__(config)
        self._client = arxiv.Client(
            page_size=100,
            delay_seconds=3.0,
            num_retries=3,
        )

    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
    ) -> list[Paper]:
        # Note: arxiv.Client already enforces delay_seconds=3.0 between requests
        sort_map = {
            "relevance": arxiv.SortCriterion.Relevance,
            "date": arxiv.SortCriterion.SubmittedDate,
            "citations": arxiv.SortCriterion.Relevance,  # arXiv has no citation sort
        }

        search = arxiv.Search(
            query=query,
            max_results=min(max_results, 300),
            sort_by=sort_map.get(sort_by, arxiv.SortCriterion.Relevance),
            sort_order=arxiv.SortOrder.Descending,
        )

        papers = []
        try:
            for result in self._client.results(search):
                paper = self._parse_result(result)
                # Year filtering (arXiv API date filtering is limited)
                if year_from and paper.year and paper.year < year_from:
                    continue
                if year_to and paper.year and paper.year > year_to:
                    continue
                papers.append(paper)
                if len(papers) >= max_results:
                    break
        except Exception as e:
            logger.error("arXiv search failed: %s", e)

        return papers

    def get_paper(self, identifier: str) -> Paper | None:
        """Get paper by arXiv ID (e.g., '2301.07041' or '2301.07041v2')."""
        # arxiv.Client handles its own rate limiting
        try:
            search = arxiv.Search(id_list=[identifier])
            for result in self._client.results(search):
                return self._parse_result(result)
        except Exception as e:
            logger.error("arXiv lookup failed for %s: %s", identifier, e)
        return None

    def _parse_result(self, result: arxiv.Result) -> Paper:
        authors = [
            Author(name=a.name)
            for a in result.authors
        ]

        # Extract arXiv ID from entry_id URL
        arxiv_id = result.entry_id.split("/abs/")[-1] if result.entry_id else ""

        # Extract DOI if available
        doi = result.doi

        # Categories as fields of study
        categories = list(result.categories) if result.categories else []

        year = result.published.year if result.published else None
        pub_date = result.published.strftime("%Y-%m-%d") if result.published else None

        return Paper(
            title=result.title,
            year=year,
            doi=doi,
            abstract=result.summary,
            authors=authors,
            source_journal=result.journal_ref,
            publication_date=pub_date,
            is_open_access=True,  # arXiv is always OA
            pdf_url=result.pdf_url,
            fields_of_study=categories,
            paper_type="preprint",
            source_db="arxiv",
            source_id=arxiv_id,
            source_url=result.entry_id or "",
        )
