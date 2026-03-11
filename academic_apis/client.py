"""Unified Academic Search Client.

Single entry point for searching across 16 academic databases.
10 keyless (zero setup) + 6 optional (API key needed).
Handles adapter initialization, parallel search, deduplication, and error isolation.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from academic_apis.adapters.base import BaseAdapter
# Keyless adapters (always available)
from academic_apis.adapters.crossref_adapter import CrossRefAdapter
from academic_apis.adapters.arxiv_adapter import ArxivAdapter
from academic_apis.adapters.semantic_scholar_adapter import SemanticScholarAdapter
from academic_apis.adapters.europepmc_adapter import EuropePMCAdapter
from academic_apis.adapters.pubmed_adapter import PubMedAdapter
from academic_apis.adapters.opencitations_adapter import OpenCitationsAdapter
from academic_apis.adapters.dblp_adapter import DBLPAdapter
from academic_apis.adapters.doaj_adapter import DOAJAdapter
from academic_apis.adapters.unpaywall_adapter import UnpaywallAdapter
from academic_apis.adapters.kci_oai_adapter import KCIOaiAdapter
# Key-required adapters (optional)
from academic_apis.adapters.openalex_adapter import OpenAlexAdapter
from academic_apis.adapters.core_adapter import CoreAdapter
from academic_apis.adapters.kci_adapter import KCIAdapter
from academic_apis.adapters.dbpia_adapter import DBpiaAdapter
from academic_apis.adapters.riss_adapter import RISSAdapter
from academic_apis.adapters.scienceon_adapter import ScienceONAdapter
from academic_apis.config import APIConfig
from academic_apis.dedup import deduplicate
from academic_apis.models import Paper, SearchResult

logger = logging.getLogger(__name__)

# Database groupings
KEYLESS_DBS = [
    "crossref", "semantic_scholar", "arxiv",
    "europepmc", "pubmed", "dblp", "doaj",
    "kci_oai",
]
# opencitations and unpaywall are DOI-based only (no keyword search)
ENRICHMENT_DBS = ["opencitations", "unpaywall"]

KEY_REQUIRED_INTERNATIONAL = ["openalex", "core"]
KEYLESS_KOREAN = ["kci_oai"]
KEY_REQUIRED_KOREAN = ["kci", "dbpia", "riss", "scienceon"]

ALL_SEARCH_DBS = KEYLESS_DBS + KEY_REQUIRED_INTERNATIONAL + KEY_REQUIRED_KOREAN


class AcademicSearchClient:
    """Unified interface to 16 academic databases (10 keyless + 6 optional)."""

    def __init__(self, config: APIConfig | None = None) -> None:
        self.config = config or APIConfig.from_env()
        self._adapters: dict[str, BaseAdapter] = {}
        self._init_adapters()

    def _init_adapters(self) -> None:
        """Initialize all configured adapters."""
        adapter_classes: list[type[BaseAdapter]] = [
            # Keyless — always initialized
            CrossRefAdapter, ArxivAdapter, SemanticScholarAdapter,
            EuropePMCAdapter, PubMedAdapter, OpenCitationsAdapter,
            DBLPAdapter, DOAJAdapter, UnpaywallAdapter,
            KCIOaiAdapter,
            # Key-required — only if credentials present
            OpenAlexAdapter, CoreAdapter,
            KCIAdapter, DBpiaAdapter, RISSAdapter, ScienceONAdapter,
        ]
        for cls in adapter_classes:
            try:
                adapter = cls(self.config)
                if adapter.is_available():
                    self._adapters[adapter.name] = adapter
                else:
                    logger.info("Adapter %s not available (missing credentials)", adapter.name)
            except Exception as e:
                logger.warning("Failed to initialize %s adapter: %s", cls.name, e)

    @property
    def available_databases(self) -> list[str]:
        """List of databases that are configured and ready."""
        return list(self._adapters.keys())

    def status(self) -> dict[str, str]:
        """Get configuration status for all databases."""
        return self.config.get_status_report()

    def search(
        self,
        query: str,
        *,
        databases: list[str] | None = None,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
        deduplicate_results: bool = True,
    ) -> SearchResult:
        """Search across multiple databases and return unified results.

        Args:
            query: Search query string.
            databases: List of database names to search. None = all available
                       (excluding enrichment-only DBs like opencitations/unpaywall).
            max_results: Maximum results per database.
            year_from: Filter papers published from this year.
            year_to: Filter papers published until this year.
            sort_by: Sort order — "relevance", "citations", or "date".
            deduplicate_results: Whether to deduplicate across databases.

        Returns:
            SearchResult with unified, optionally deduplicated papers.
        """
        if databases is None:
            # Default: all searchable DBs (exclude enrichment-only ones)
            target_dbs = [
                db for db in self._adapters
                if db not in ENRICHMENT_DBS
            ]
        else:
            target_dbs = [db for db in databases if db in self._adapters]

        if not target_dbs:
            return SearchResult(
                query=query,
                total_results=0,
                papers=[],
                databases_searched=[],
                errors={"all": "No databases available."},
            )

        all_papers: list[Paper] = []
        errors: dict[str, str] = {}
        searched: list[str] = []

        # Parallel search across databases
        with ThreadPoolExecutor(max_workers=min(len(target_dbs), 6)) as executor:
            futures = {}
            for db_name in target_dbs:
                adapter = self._adapters[db_name]
                future = executor.submit(
                    adapter.search,
                    query,
                    max_results=max_results,
                    year_from=year_from,
                    year_to=year_to,
                    sort_by=sort_by,
                )
                futures[future] = db_name

            for future in as_completed(futures):
                db_name = futures[future]
                try:
                    papers = future.result(timeout=60)
                    all_papers.extend(papers)
                    searched.append(db_name)
                    logger.info("Got %d results from %s", len(papers), db_name)
                except Exception as e:
                    errors[db_name] = str(e)
                    logger.error("Search failed for %s: %s", db_name, e)

        # Deduplicate
        if deduplicate_results:
            all_papers = deduplicate(all_papers)

        # Sort merged results
        if sort_by == "citations":
            all_papers.sort(key=lambda p: p.citation_count or 0, reverse=True)
        elif sort_by == "date":
            all_papers.sort(key=lambda p: p.year or 0, reverse=True)

        return SearchResult(
            query=query,
            total_results=len(all_papers),
            papers=all_papers,
            databases_searched=searched,
            errors=errors,
        )

    def search_keyless(self, query: str, **kwargs) -> SearchResult:
        """Search only keyless databases (zero setup required)."""
        return self.search(query, databases=KEYLESS_DBS, **kwargs)

    def search_korean(self, query: str, **kwargs) -> SearchResult:
        """Search Korean databases (keyless + key-required if configured)."""
        return self.search(query, databases=KEYLESS_KOREAN + KEY_REQUIRED_KOREAN, **kwargs)

    def get_paper(self, doi: str) -> Paper | None:
        """Get paper metadata from the best available source.

        Tries CrossRef first (authoritative for DOI), then enriches
        with Semantic Scholar, Europe PMC, and Unpaywall data.
        """
        paper = None
        priority = [
            "crossref", "semantic_scholar", "europepmc", "pubmed",
            "openalex", "core", "unpaywall",
        ]

        for db_name in priority:
            adapter = self._adapters.get(db_name)
            if not adapter:
                continue
            try:
                result = adapter.get_paper(doi)
                if result:
                    if paper is None:
                        paper = result
                    else:
                        paper.merge_from(result)
            except Exception as e:
                logger.warning("get_paper failed for %s via %s: %s", doi, db_name, e)

        return paper

    def get_citations(self, doi: str, max_results: int = 50) -> list[Paper]:
        """Get papers citing the given work.

        Tries Semantic Scholar (best citation data), then OpenCitations,
        then Europe PMC, then OpenAlex.
        """
        for db_name in ["semantic_scholar", "opencitations", "europepmc", "openalex"]:
            adapter = self._adapters.get(db_name)
            if not adapter:
                continue
            try:
                results = adapter.get_citations(doi, max_results=max_results)
                if results:
                    return results
            except Exception as e:
                logger.warning("get_citations failed via %s: %s", db_name, e)
        return []

    def get_references(self, doi: str, max_results: int = 50) -> list[Paper]:
        """Get papers referenced by the given work.

        Tries CrossRef first (reference lists), then OpenCitations,
        then Semantic Scholar.
        """
        for db_name in ["crossref", "opencitations", "semantic_scholar", "openalex"]:
            adapter = self._adapters.get(db_name)
            if not adapter:
                continue
            try:
                results = adapter.get_references(doi, max_results=max_results)
                if results:
                    return results
            except Exception as e:
                logger.warning("get_references failed via %s: %s", db_name, e)
        return []

    def get_full_text(self, doi: str) -> str | None:
        """Try to get full paper text. CORE is the primary source."""
        core = self._adapters.get("core")
        if core and isinstance(core, CoreAdapter):
            try:
                paper = core.get_paper(doi)
                if paper and paper.full_text:
                    return paper.full_text
            except Exception as e:
                logger.warning("Full text retrieval failed via CORE: %s", e)
        return None

    def find_oa_pdf(self, doi: str) -> str | None:
        """Find open access PDF URL for a DOI via Unpaywall."""
        upa = self._adapters.get("unpaywall")
        if upa and isinstance(upa, UnpaywallAdapter):
            return upa.find_oa_url(doi)
        return None

    def close(self) -> None:
        """Close all adapter HTTP sessions."""
        for adapter in self._adapters.values():
            adapter.close()
