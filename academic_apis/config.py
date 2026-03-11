"""Configuration management for academic API keys and settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Default .env location: project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


def _load_dotenv() -> None:
    """Load .env file into os.environ (stdlib only, no dependency)."""
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:  # don't override existing env
            os.environ[key] = value


# Auto-load on import
_load_dotenv()


@dataclass
class APIConfig:
    """Configuration for all academic APIs."""

    # OpenAlex
    openalex_api_key: str = ""
    openalex_base_url: str = "https://api.openalex.org"

    # Semantic Scholar
    s2_api_key: str = ""
    s2_base_url: str = "https://api.semanticscholar.org/graph/v1"

    # CrossRef
    crossref_email: str = ""
    crossref_base_url: str = "https://api.crossref.org"

    # arXiv
    arxiv_base_url: str = "http://export.arxiv.org/api"

    # CORE
    core_api_key: str = ""
    core_base_url: str = "https://api.core.ac.uk/v3"

    # Korean APIs
    kci_api_key: str = ""
    kci_base_url: str = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"

    dbpia_api_key: str = ""
    dbpia_base_url: str = "http://api.dbpia.co.kr/v2/search/search.xml"

    riss_api_key: str = ""
    riss_base_url: str = "http://www.riss.kr/apicenter/apiSearchJournal.do"

    scienceon_client_id: str = ""
    scienceon_token: str = ""
    scienceon_base_url: str = "https://apigateway.kisti.re.kr/openapicall.do"

    # Enabled databases (user can disable specific ones)
    enabled_databases: list[str] = field(default_factory=lambda: [
        # Keyless (always available)
        "crossref", "arxiv", "semantic_scholar",
        "europepmc", "pubmed", "opencitations",
        "dblp", "doaj", "unpaywall", "kci_oai",
        # Key-required (optional)
        "openalex", "core",
        "kci", "dbpia", "riss", "scienceon",
    ])

    @classmethod
    def from_env(cls) -> APIConfig:
        """Load configuration from environment variables."""
        return cls(
            openalex_api_key=os.environ.get("OPENALEX_API_KEY", ""),
            s2_api_key=os.environ.get("S2_API_KEY", ""),
            crossref_email=os.environ.get("CROSSREF_EMAIL", ""),
            core_api_key=os.environ.get("CORE_API_KEY", ""),
            kci_api_key=os.environ.get("KCI_API_KEY", ""),
            dbpia_api_key=os.environ.get("DBPIA_API_KEY", ""),
            riss_api_key=os.environ.get("RISS_API_KEY", ""),
            scienceon_client_id=os.environ.get("SCIENCEON_CLIENT_ID", ""),
            scienceon_token=os.environ.get("SCIENCEON_TOKEN", ""),
        )

    def get_available_databases(self) -> list[str]:
        """Return list of databases that have valid credentials (or don't need them)."""
        available = []
        # Keyless APIs: always available (10)
        for db in [
            "crossref", "arxiv", "semantic_scholar",
            "europepmc", "pubmed", "opencitations",
            "dblp", "doaj", "unpaywall", "kci_oai",
        ]:
            if db in self.enabled_databases:
                available.append(db)

        # Key-required APIs (6)
        if "openalex" in self.enabled_databases and self.openalex_api_key:
            available.append("openalex")
        if "core" in self.enabled_databases and self.core_api_key:
            available.append("core")
        if "kci" in self.enabled_databases and self.kci_api_key:
            available.append("kci")
        if "dbpia" in self.enabled_databases and self.dbpia_api_key:
            available.append("dbpia")
        if "riss" in self.enabled_databases and self.riss_api_key:
            available.append("riss")
        if "scienceon" in self.enabled_databases and self.scienceon_client_id:
            available.append("scienceon")

        return available

    def get_status_report(self) -> dict[str, str]:
        """Return status of each database configuration."""
        return {
            # Keyless (always ready)
            "crossref": "ready" if self.crossref_email else "ready (no email, public pool)",
            "arxiv": "ready",
            "semantic_scholar": "ready (no key)" if not self.s2_api_key else "ready (with key)",
            "europepmc": "ready",
            "pubmed": "ready",
            "opencitations": "ready (citation graph only)",
            "dblp": "ready (CS only)",
            "doaj": "ready (OA only)",
            "unpaywall": "ready (DOI lookup only)",
            "kci_oai": "ready (OAI-PMH, 2.36M Korean articles)",
            # Key-required (optional)
            "openalex": "ready" if self.openalex_api_key else "optional — needs API key",
            "core": "ready" if self.core_api_key else "optional — needs API key",
            "kci": "ready" if self.kci_api_key else "optional — needs API key",
            "dbpia": "ready" if self.dbpia_api_key else "optional — needs API key",
            "riss": "ready" if self.riss_api_key else "optional — needs API key",
            "scienceon": "ready" if self.scienceon_client_id else "optional — needs credentials",
        }
