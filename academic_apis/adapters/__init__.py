"""Database-specific API adapters."""

# --- Keyless (no registration needed) ---
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

# --- Key required (optional, for users who register) ---
from academic_apis.adapters.openalex_adapter import OpenAlexAdapter
from academic_apis.adapters.core_adapter import CoreAdapter
from academic_apis.adapters.kci_adapter import KCIAdapter
from academic_apis.adapters.dbpia_adapter import DBpiaAdapter
from academic_apis.adapters.riss_adapter import RISSAdapter
from academic_apis.adapters.scienceon_adapter import ScienceONAdapter

__all__ = [
    # Keyless
    "CrossRefAdapter", "ArxivAdapter", "SemanticScholarAdapter",
    "EuropePMCAdapter", "PubMedAdapter", "OpenCitationsAdapter",
    "DBLPAdapter", "DOAJAdapter", "UnpaywallAdapter",
    "KCIOaiAdapter",
    # Key required
    "OpenAlexAdapter", "CoreAdapter",
    "KCIAdapter", "DBpiaAdapter", "RISSAdapter", "ScienceONAdapter",
]
