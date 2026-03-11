"""Academic Database API Integration Module.

Provides unified access to 9 academic databases:
- International: OpenAlex, Semantic Scholar, CrossRef, arXiv, CORE
- Korean: KCI, DBpia, RISS, ScienceON
"""

from academic_apis.models import Paper, Author, SearchResult
from academic_apis.client import AcademicSearchClient

__all__ = ["Paper", "Author", "SearchResult", "AcademicSearchClient"]
__version__ = "0.1.0"
