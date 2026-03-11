"""Unified data models for academic papers across all databases."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Author:
    """Normalized author representation."""

    name: str
    orcid: str | None = None
    affiliation: str | None = None
    h_index: int | None = None
    source_id: str | None = None  # DB-specific ID


@dataclass
class Paper:
    """Normalized paper representation across all databases.

    The canonical dedup key is DOI (lowercased). If DOI is absent,
    a fingerprint from (title_lower, year) is used instead.
    """

    title: str
    year: int | None = None
    doi: str | None = None
    abstract: str | None = None
    authors: list[Author] = field(default_factory=list)
    citation_count: int | None = None
    reference_count: int | None = None
    source_journal: str | None = None
    publication_date: str | None = None
    is_open_access: bool | None = None
    oa_url: str | None = None
    pdf_url: str | None = None
    full_text: str | None = None
    language: str | None = None
    paper_type: str | None = None  # article, book, thesis, preprint, etc.
    keywords: list[str] = field(default_factory=list)
    fields_of_study: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)  # DOIs or IDs
    source_db: str = ""  # which database this came from
    source_id: str = ""  # DB-specific identifier
    source_url: str = ""  # link to the record
    raw: dict[str, Any] = field(default_factory=dict, repr=False)  # original response

    # Semantic Scholar extras
    tldr: str | None = None
    influential_citation_count: int | None = None

    # OpenAlex extras
    fwci: float | None = None
    citation_percentile: float | None = None

    @property
    def dedup_key(self) -> str:
        """Canonical deduplication key."""
        if self.doi:
            return f"doi:{self.doi.lower().strip()}"
        # Fallback: fingerprint from title + year + first author
        title_norm = (self.title or "").lower().strip()
        first_author = self.authors[0].name.lower().strip() if self.authors else ""
        fp = hashlib.sha256(f"{title_norm}|{self.year}|{first_author}".encode()).hexdigest()[:16]
        return f"fp:{fp}"

    def merge_from(self, other: Paper) -> None:
        """Merge missing fields from another Paper (same dedup_key)."""
        for attr in (
            "year", "abstract", "citation_count", "reference_count", "source_journal",
            "publication_date", "is_open_access", "oa_url", "pdf_url",
            "full_text", "language", "paper_type", "tldr",
            "influential_citation_count", "fwci", "citation_percentile",
        ):
            if getattr(self, attr) is None and getattr(other, attr) is not None:
                setattr(self, attr, getattr(other, attr))
        if not self.doi and other.doi:
            self.doi = other.doi
        if not self.authors and other.authors:
            self.authors = other.authors
        if not self.keywords and other.keywords:
            self.keywords = other.keywords
        if not self.fields_of_study and other.fields_of_study:
            self.fields_of_study = other.fields_of_study
        if not self.references and other.references:
            self.references = other.references

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary (excludes raw)."""
        return {
            "title": self.title,
            "year": self.year,
            "doi": self.doi,
            "abstract": self.abstract,
            "authors": [
                {"name": a.name, "orcid": a.orcid, "affiliation": a.affiliation}
                for a in self.authors
            ],
            "citation_count": self.citation_count,
            "reference_count": self.reference_count,
            "source_journal": self.source_journal,
            "publication_date": self.publication_date,
            "is_open_access": self.is_open_access,
            "oa_url": self.oa_url,
            "pdf_url": self.pdf_url,
            "language": self.language,
            "paper_type": self.paper_type,
            "keywords": self.keywords,
            "fields_of_study": self.fields_of_study,
            "full_text": self.full_text,
            "references": self.references,
            "source_db": self.source_db,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "tldr": self.tldr,
            "influential_citation_count": self.influential_citation_count,
            "fwci": self.fwci,
            "citation_percentile": self.citation_percentile,
        }


@dataclass
class SearchResult:
    """Result of a search across one or more databases."""

    query: str
    total_results: int
    papers: list[Paper]
    databases_searched: list[str]
    errors: dict[str, str] = field(default_factory=dict)  # db_name -> error msg

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "total_results": self.total_results,
            "databases_searched": self.databases_searched,
            "errors": self.errors,
            "papers": [p.to_dict() for p in self.papers],
        }
