# Academic Database API Integration Guide

> **Purpose**: Transform the Dissertation Simulator from simulation-based to real-data-driven literature search.
> **Last Updated**: 2026-03-11
> **Status**: Research Complete — Ready for Implementation

---

## Executive Summary

### Current State
The simulator declares 18 academic databases but accesses **none** of them. All literature search results are simulated estimates (±30%).

### Target State
Integrate **9 free APIs** (5 international + 4 Korean) to provide real scholarly data covering 270M+ international papers and Korean academic literature.

### API Key Requirements at a Glance

| API | Key Required? | Cost | Registration | Daily Limit (Free) |
|-----|:---:|------|-------------|------|
| **OpenAlex** | Yes | Free | openalex.org account | ~10,000 list / ~1,000 search |
| **Semantic Scholar** | Optional | Free | Email request | 1,000 req/sec shared (no key) |
| **CrossRef** | No | Free | None (email in header) | 3 req/sec polite pool |
| **arXiv** | No | Free | None | 1 req / 3 sec |
| **CORE** | Yes | Free | core.ac.uk registration | 1,000 tokens/day |
| **KCI** | Yes | Free | kci.go.kr or data.go.kr | 5,000 req (dev) |
| **DBpia** | Yes | Free | api.dbpia.co.kr | Per agreement |
| **RISS** | Yes | Free | data.go.kr | Per agreement |
| **ScienceON** | Yes | Free | ScienceON portal | Per agreement |

**Automation potential**: Claude Code can automatically configure 4 of 9 APIs (OpenAlex, Semantic Scholar, CrossRef, arXiv) without any user action. The remaining 5 require web registration (1-2 min each).

---

## Part 1: International APIs (Tier 1 — Highest Priority)

---

### 1.1 OpenAlex

**Coverage**: ~270M+ works, ~90M authors, ~100K sources
**Comparison**: Indexes 34,217 OA journals vs Scopus 7,351 and WoS 6,157
**License**: CC0 (completely open)

#### Authentication

As of February 2026, API keys are **required**.

1. Create free account at `https://openalex.org`
2. Get API key at `https://openalex.org/settings/api`
3. Add `?api_key=YOUR_KEY` to every request

#### Pricing (Usage-Based, Free Tier Generous)

| Operation | Cost | Free Daily Allowance ($1/day) |
|-----------|------|------|
| Get by ID | $0.00 | Unlimited |
| List/Filter | $0.0001 | ~10,000 requests |
| Search | $0.001 | ~1,000 requests |
| PDF download | $0.01 | ~100 PDFs |
| Max rate | 100 req/sec | — |

#### Base URL
```
https://api.openalex.org
```

#### Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /works` | Search/filter scholarly documents |
| `GET /works/{id}` | Single work by OpenAlex ID, DOI, PMID |
| `GET /authors/{id}` | Author by ID or ORCID |
| `GET /sources/{id}` | Journal/repository info |
| `GET /topics` | Topic classifications |
| `GET /works?filter=cites:{id}` | Papers citing a given work |
| `GET /works?filter=cited_by:{id}` | References of a given work |

#### ID Formats
```
/works/W2741809807                              # OpenAlex ID
/works/https://doi.org/10.1038/nature12373     # DOI
/works/pmid:29456894                           # PubMed ID
/authors/https://orcid.org/0000-0001-6187-6610 # ORCID
```

#### Search Syntax
```
# Boolean (operators MUST be uppercase)
?search=(machine learning AND "drug discovery") NOT review

# Phrase search
?search="climate change"

# Proximity (words within 5 positions)
?search="climate change"~5

# Wildcard
?search=machin*

# No stemming
?search.exact=surgery
```

#### Filter Syntax
```
# AND (comma-separated)
?filter=publication_year:2024,is_oa:true,type:article

# OR (pipe-separated)
?filter=type:article|book|dataset

# NOT
?filter=type:!paratext

# Range
?filter=publication_year:2020-2024
?filter=cited_by_count:>100

# Date range
?filter=from_publication_date:2023-01-01,to_publication_date:2024-12-31
```

#### Sorting & Pagination
```
?sort=cited_by_count:desc
?sort=publication_year:desc,relevance_score:desc
?per_page=50&page=2
# Deep pagination: use cursor=* then next_cursor from response
```

#### Work Object Key Fields
```json
{
  "id": "W2741809807",
  "doi": "https://doi.org/10.7717/peerj.4375",
  "display_name": "Paper Title",
  "publication_year": 2024,
  "publication_date": "2024-03-15",
  "type": "article",
  "language": "en",
  "is_oa": true,
  "oa_status": "gold",
  "cited_by_count": 42,
  "fwci": 2.5,
  "citation_normalized_percentile": {
    "value": 0.95,
    "is_in_top_1_percent": false,
    "is_in_top_10_percent": true
  },
  "referenced_works": ["W123...", "W456..."],
  "referenced_works_count": 35,
  "authorships": [{
    "author": {"id": "A123", "display_name": "Name", "orcid": "0000-..."},
    "institutions": [{"id": "I123", "display_name": "MIT", "country_code": "US"}],
    "is_corresponding": true
  }],
  "primary_location": {
    "source": {"id": "S137773608", "display_name": "Nature"},
    "is_oa": true,
    "landing_page_url": "https://...",
    "license": "cc-by"
  },
  "primary_topic": {
    "id": "T12345",
    "display_name": "Machine Learning",
    "domain": {"id": "D1", "display_name": "Physical Sciences"},
    "field": {"id": "F123", "display_name": "Computer Science"},
    "subfield": {"id": "SF456", "display_name": "Artificial Intelligence"}
  },
  "keywords": [{"keyword": "deep learning", "score": 0.95}],
  "abstract_inverted_index": {"The": [0], "study": [1], ...},
  "has_fulltext": true,
  "is_retracted": false,
  "biblio": {"volume": "42", "issue": "3", "first_page": "123", "last_page": "145"}
}
```

#### Python Client: pyalex
```bash
pip install pyalex
```

```python
import pyalex
from pyalex import Works, Authors

pyalex.config.api_key = "YOUR_KEY"

# Search
results = Works().search("machine learning drug discovery").get()

# Filter + sort
results = (Works()
    .filter(publication_year=2024, is_oa=True)
    .sort(cited_by_count="desc")
    .get())

# Get by DOI
work = Works()["https://doi.org/10.1038/s41586-021-03819-2"]

# Paginate
for page in Works().search("CRISPR").paginate(per_page=200):
    for work in page:
        print(work["display_name"], work["cited_by_count"])

# Citations of a specific work
citing = Works().filter(cites="W2741809807").sort(cited_by_count="desc").get()

# Author by ORCID
author = Authors()["https://orcid.org/0000-0001-6187-6610"]
print(author["summary_stats"]["h_index"])
```

#### Bulk Download (for comprehensive analysis)
```bash
aws s3 sync 's3://openalex' 'openalex-snapshot' --no-sign-request
# ~330 GB compressed, ~1.6 TB decompressed, JSON Lines format
```

---

### 1.2 Semantic Scholar

**Coverage**: 214M papers, 2.49B citation edges, 79M authors
**Unique**: TLDR summaries, SPECTER2 embeddings, citation intent classification

#### Authentication

Most endpoints work **without a key**. Key recommended for production.

- **Without key**: 1,000 req/sec shared across all anonymous users
- **With key**: 1 req/sec dedicated (higher on request)

**Getting a key** (free):
1. Visit `https://www.semanticscholar.org/product/api`
2. Scroll to API key request form
3. Submit name, email, use case
4. Key sent via email

**Header**: `x-api-key: YOUR_KEY`

#### Base URL
```
https://api.semanticscholar.org/graph/v1
```

#### Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/paper/search` | GET | Relevance-ranked search (max 1,000 results) |
| `/paper/search/bulk` | GET | Boolean bulk search (up to 10M results) |
| `/paper/{id}` | GET | Single paper lookup |
| `/paper/batch` | POST | Batch lookup (max 500 IDs) |
| `/paper/{id}/citations` | GET | Papers citing this paper |
| `/paper/{id}/references` | GET | Papers cited by this paper |
| `/paper/search/match` | GET | Best title match (single result) |
| `/author/search` | GET | Author search |
| `/author/{id}/papers` | GET | Author's publications |
| `/snippet/search` | GET | Full-text snippet search |

#### Supported Paper ID Formats
```
649def34f8be52c8b66281af98ae884c09aef38b   # S2 Paper ID
CorpusId:215416146                          # Corpus ID
DOI:10.18653/v1/N18-3011                    # DOI
ARXIV:2106.15928                            # arXiv
PMID:19872477                               # PubMed
PMCID:2323736                               # PubMed Central
ACL:W12-3903                                # ACL Anthology
URL:https://arxiv.org/abs/2106.15928        # URL
```

#### Search Filters

| Parameter | Example |
|-----------|---------|
| `year` | `2020-2024`, `2023-` |
| `publicationDateOrYear` | `2023-01-01:2024-06-30` |
| `venue` | `Nature,Science,ICML` |
| `fieldsOfStudy` | `Computer Science,Philosophy` |
| `minCitationCount` | `100` |
| `publicationTypes` | `JournalArticle,Conference,Review` |
| `openAccessPdf` | (flag, no value) |

#### Boolean Syntax (bulk search)
```
+"required term"
-"excluded term"
"exact phrase"
term1 | term2
(group1) | (group2)
fish*               # prefix wildcard
bugs~3              # fuzzy match
```

#### Sorting (bulk search)
```
sort=citationCount:desc
sort=publicationDate:desc
sort=paperId:asc
```

#### Requestable Fields (via `?fields=`)
Core: `paperId`, `corpusId`, `title`, `abstract`, `year`, `citationCount`, `influentialCitationCount`, `referenceCount`, `isOpenAccess`, `openAccessPdf`, `fieldsOfStudy`, `publicationTypes`, `publicationDate`, `journal`, `venue`, `externalIds`
Special: `tldr`, `embedding`, `citationStyles`
Citation edge: `contexts`, `intents`, `isInfluential`, `contextsWithIntent`
Author: `authorId`, `name`, `url`, `affiliations`, `homepage`, `paperCount`, `citationCount`, `hIndex`

#### Python Client
```bash
pip install semanticscholar
```

```python
from semanticscholar import SemanticScholar

sch = SemanticScholar()  # or SemanticScholar(api_key="YOUR_KEY")

# Keyword search
results = sch.search_paper(
    "transformers attention mechanism",
    year="2020-2024",
    fields_of_study=["Computer Science"],
    min_citation_count=50,
    limit=100
)

# Bulk boolean search
results = sch.search_paper(
    '"large language models"',
    bulk=True,
    sort="citationCount:desc"
)

# Single paper by DOI
paper = sch.get_paper("DOI:10.1038/nature12373")
print(paper.title, paper.citationCount, paper.tldr)

# Citations with context
citations = sch.get_paper_citations("CorpusId:49313245")

# Batch lookup
papers = sch.get_papers(["DOI:10.1038/nature12373", "ARXIV:2005.14165"])

# Author + h-index
author = sch.get_author(1741101)
print(author.name, author.hIndex)

# Recommendations
recs = sch.get_recommended_papers("CorpusId:49313245", limit=20)
```

---

### 1.3 CrossRef

**Coverage**: 176M+ metadata records with DOIs, 24,000+ member organizations
**Unique**: Authoritative DOI metadata, reference lists, citation counts

#### Authentication

**No key required.** Polite pool via email:

```
# Option 1: Query parameter
?mailto=you@example.com

# Option 2: User-Agent header
User-Agent: MyApp/1.0 (mailto:you@example.com)
```

Must use HTTPS.

#### Rate Limits (since Dec 2025)

| Pool | Single Record | List/Search | Concurrency |
|------|:---:|:---:|:---:|
| Public | 5 req/sec | 1 req/sec | 1 |
| Polite | 10 req/sec | 3 req/sec | 3 |
| Metadata Plus (paid) | 150 req/sec | — | Unrestricted |

#### Base URL
```
https://api.crossref.org
```

#### Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /works?query=...` | Search works |
| `GET /works/{doi}` | Lookup by DOI |
| `GET /works?filter=...` | Filtered retrieval |
| `GET /journals/{issn}/works` | Works in a journal |
| `GET /funders/{id}/works` | Works by funder |
| `GET /members/{id}/works` | Works by publisher |

#### Query Parameters
```
?query=deep+learning+transformers           # Free text
?query.author=Geoffrey+Hinton               # Author
?query.container-title=Nature               # Journal
?query.bibliographic=neural+networks+2024   # Citation-style
?query.affiliation=MIT                      # Affiliation
```

#### Filter Syntax
```
# AND (different filters): comma-separated
?filter=type:journal-article,from-pub-date:2024-01-01,has-references:true

# OR (same filter): repeated
?filter=type:journal-article,type:book-chapter

# Common filters
has-references:true         # Has deposited references
has-orcid:true              # Has ORCID
has-abstract:true           # Has abstract
has-full-text:true          # Has full-text link
type:journal-article        # Work type
from-pub-date:2024-01-01    # Date range
until-pub-date:2024-12-31
funder:10.13039/100000001   # By funder DOI
member:311                  # By publisher member ID
```

#### Sorting
```
?sort=is-referenced-by-count&order=desc   # By citation count
?sort=published&order=desc                 # By date
?sort=relevance                            # By relevance (default with query)
```

#### Pagination
```
?rows=100&offset=0                  # Simple (max offset: 10,000)
?rows=100&cursor=*                  # Deep pagination (use next-cursor)
?sample=50                          # Random sample
```

#### Work Object Key Fields
```
DOI, title, author[{given, family, ORCID, affiliation}],
container-title, type, issued, published-print, published-online,
is-referenced-by-count (citation count),
reference-count,
reference[{key, doi, article-title, author, year, journal-title}],
abstract (JATS XML, ~20-30% of works),
ISSN, ISBN, volume, issue, page,
license[{URL, delay-in-days}],
funder[{DOI, name, award}],
subject[]
```

**Note**: `reference` array available for ~50% of works. Use `has-references:true` filter.
**Note**: Actual citing DOI list requires Crossref membership (not via public API). Only `is-referenced-by-count` (the count) is public.

#### Python Client: habanero
```bash
pip install habanero
```

```python
from habanero import Crossref

cr = Crossref(mailto="you@example.com")

# Search
results = cr.works(query="deep learning transformers", limit=5)

# DOI lookup
work = cr.works(ids="10.1038/nature12373")

# Filter + sort
results = cr.works(
    filter={"type": "journal-article", "from_pub_date": "2024-01-01", "has_orcid": True},
    sort="is-referenced-by-count",
    order="desc",
    limit=20
)

# Deep pagination
results = cr.works(query="CRISPR", cursor="*", cursor_max=10000, limit=1000)

# Field selection
results = cr.works(query="climate", select=["DOI", "title", "is-referenced-by-count"])
```

---

### 1.4 arXiv

**Coverage**: ~3M papers, ~28,000 new/month, STEM only (16 subject groups, 155+ categories)
**Unique**: Preprint-first, fast indexing, PDF/source download

#### Authentication
**None required.** Completely open.

#### Rate Limit
1 request per 3 seconds. Max 2,000 results per request. Overall cap ~50,000 per query.

#### Base URL
```
http://export.arxiv.org/api/query
```

#### Query Syntax

| Prefix | Field |
|--------|-------|
| `ti:` | Title |
| `au:` | Author |
| `abs:` | Abstract |
| `cat:` | Category |
| `all:` | All fields |

Boolean: `AND`, `OR`, `ANDNOT`

```
# Search by title + category
?search_query=ti:transformer+AND+cat:cs.CL&max_results=10

# Author + title
?search_query=au:vaswani+AND+ti:attention&sortBy=submittedDate&sortOrder=descending

# Date range
?search_query=cat:cs.AI+AND+submittedDate:[202501010000+TO+202512312359]

# By ID
?id_list=2301.07041,1605.08386v1
```

#### Parameters
```
search_query    # Search terms with field prefixes
id_list         # Specific arXiv IDs (comma-delimited)
start           # Pagination offset (0-based)
max_results     # Per page (max 2,000)
sortBy          # relevance, lastUpdatedDate, submittedDate
sortOrder       # ascending, descending
```

#### Response Format: Atom XML
```xml
<entry>
  <id>http://arxiv.org/abs/2301.07041v2</id>
  <title>Paper Title</title>
  <published>2023-01-17T18:58:29Z</published>
  <updated>2023-03-01T12:00:00Z</updated>
  <summary>Abstract text...</summary>
  <author><name>Author Name</name></author>
  <category term="cs.AI"/>
  <arxiv:doi>10.1234/example</arxiv:doi>
  <link href="http://arxiv.org/pdf/2301.07041v2" type="application/pdf"/>
</entry>
```

#### Limitations
- No citation data (no citation counts, no reference graphs)
- No full-text search (title/abstract/metadata only)
- STEM only (no humanities, social sciences)
- XML only (no JSON)
- Result cap ~50,000

#### Python Client
```bash
pip install arxiv
```

```python
import arxiv

client = arxiv.Client(page_size=100, delay_seconds=3.0, num_retries=3)

search = arxiv.Search(
    query='ti:"transformer" AND cat:cs.CL',
    max_results=50,
    sort_by=arxiv.SortCriterion.SubmittedDate
)

for result in client.results(search):
    print(result.title, result.published, result.entry_id)
    # result.download_pdf()     # download PDF
    # result.download_source()  # download LaTeX source

# Lookup by ID
search = arxiv.Search(id_list=["2301.07041v2", "1605.08386"])
```

---

### 1.5 CORE

**Coverage**: 313M metadata records, 37M full-text papers, 14,000+ data providers, 150+ countries
**Unique**: Full-text search and access, open access focus, all academic disciplines

#### Authentication

API key required. Free registration.

1. Visit `https://core.ac.uk/services/api`
2. Fill registration form (email, name, use case)
3. Receive API key via email

**Header**: `Authorization: Bearer YOUR_API_KEY`

#### Rate Limits

| Tier | Tokens/Day | Per Minute |
|------|:---:|:---:|
| Unauthenticated | 100 | 10 |
| Registered Personal | 1,000 | 25 |
| Academic | 5,000 | 10 |
| Supporting Institution | ~200,000 | Negotiated |

Simple query = 1 token. Complex query = 3-5 tokens.

#### Base URL
```
https://api.core.ac.uk/v3
```

#### Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /search/works?q=...` | Search deduplicated works |
| `GET /search/outputs?q=...` | Search raw harvested outputs |
| `GET /works/{id}` | Work by CORE ID |
| `GET /works/doi:{doi}` | Work by DOI |
| `GET /outputs/{id}/download` | Download PDF |
| `GET /search/journals?q=...` | Search journals |
| `GET /labs/expert-finder` | Find domain experts |

#### Query Syntax (Elasticsearch-based)
```
title:"deep learning"
title:transformer AND yearPublished:2024
title:BERT OR title:GPT
(title:AI OR title:ML) AND yearPublished>=2023
_exists_:fullText                              # only papers with full text
```

#### Searchable Fields
`abstract`, `arxivId`, `authors`, `citationCount`, `doi`, `downloadUrl`, `fieldOfStudy`, `fullText`, `title`, `yearPublished`, `language`, `license`, `publisher`, `pubmedId`, `references`

#### Response Format: JSON
```json
{
  "totalHits": 15432,
  "limit": 10,
  "offset": 0,
  "results": [{
    "id": 123456789,
    "doi": "10.1234/example",
    "title": "Paper Title",
    "authors": [{"name": "Author Name"}],
    "abstract": "Abstract text...",
    "fullText": "Complete paper text...",
    "yearPublished": 2024,
    "citationCount": 42,
    "downloadUrl": "https://core.ac.uk/download/pdf/123456789.pdf",
    "fieldOfStudy": "Computer Science",
    "references": [{"doi": "10.5678/ref1", "title": "..."}],
    "language": {"code": "en", "name": "English"}
  }]
}
```

#### Python (requests)
```python
import requests

API_KEY = "your_api_key"
BASE = "https://api.core.ac.uk/v3"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# Search with full-text filter
resp = requests.get(f"{BASE}/search/works", headers=HEADERS, params={
    "q": 'title:"deep learning" AND _exists_:fullText AND yearPublished>=2023',
    "limit": 10
})

for work in resp.json()["results"]:
    print(work["title"], work.get("citationCount"))
    # work["fullText"] contains the complete paper text
```

---

## Part 2: Korean APIs (Tier 2)

---

### 2.1 KCI (Korea Citation Index) — Best Documented

**Operator**: NRF (National Research Foundation of Korea)
**Coverage**: Korean academic journals with citation data and impact factors

#### Authentication

**Option A**: KCI Open API Portal
1. Visit `https://www.kci.go.kr/kciportal/po/openapi/openApiKeyRequest.kci`
2. Register and request API key
3. Contact: kciadmin@nrf.re.kr, 042-869-6674

**Option B**: data.go.kr (Public Data Portal)
1. Register at `https://www.data.go.kr`
2. Apply for KCI Paper Info Service (Dataset 15085348)
3. Auto-approval for development key (5,000 requests)

#### Endpoints (KCI Open API)

**Base**: `https://open.kci.go.kr/po/openapi/openApiSearch.kci`

| apiCode | Service |
|---------|---------|
| `articleSearch` | Paper search |
| `referenceSearch` | Reference search |
| `citation` | Citation data |
| `articleDetail` | Full paper info |
| `citationDetail` | Citation metrics |

#### Parameters
```
key=YOUR_API_KEY          # Required
apiCode=articleSearch     # Required
title=machine+learning    # UTF-8 encoded
author=홍길동              # Author name
journal=한국정보과학회     # Journal name
keyword=인공지능          # Keywords
dateFrom=202301           # YYYYMM
dateTo=202412             # YYYYMM
doi=10.1234/example       # DOI
displayCount=50           # 10, 20, 50, 100, All
sortNm=accuracy           # accuracy, title, author, pub date, impact factor
sortDir=desc              # asc/desc
```

#### Response: XML

#### data.go.kr Endpoints
```
# Paper Info
http://apis.data.go.kr/B552540/KCIOpenApi/artiInfo/openApiD217List

# Journal Info
http://apis.data.go.kr/B552540/KCIOpenApi/sereInfo/openApiD154List

# DOI Info
http://apis.data.go.kr/B552540/KCIOpenApi/doiInfo/openApiD211List
```

#### Python Example
```python
import requests
import xml.etree.ElementTree as ET

url = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"
params = {
    "key": "YOUR_API_KEY",
    "apiCode": "articleSearch",
    "title": "machine learning",
    "displayCount": 10,
    "sortNm": "accuracy"
}
resp = requests.get(url, params=params)
root = ET.fromstring(resp.content)
for article in root.findall(".//record"):
    print(article.findtext("title"), article.findtext("author"))
```

---

### 2.2 DBpia — Best for Journal Articles

**Operator**: Nurimedia Inc.
**Coverage**: Korean journal articles, conference proceedings, magazines

#### Authentication
1. Register at `https://api.dbpia.co.kr/openApi/index.do`
2. Obtain Search API key

#### Endpoint
```
http://api.dbpia.co.kr/v2/search/search.xml
```

#### Parameters
```
key=YOUR_API_KEY
target=se               # se=basic, se_adv=advanced, rated_art=popular
searchall=deep+learning  # Basic search keywords
searchauthor=홍길동      # Author
searchbook=학회논문집    # Publication name
itype=1                 # 1=Journals, 2=Conference, 3=Magazines, 4=Reports
category=4              # 1-9 (Humanities through General Education)
pyear=3                 # 1=Last year, 2=Last 3 years, 3=Custom
pyear_start=2020
pyear_end=2024
pagecount=20
pagenumber=1
sorttype=2              # 1=Relevance, 2=Date, 3=Popularity
sortorder=desc
```

#### Response: XML (title, authors, publisher, publication, issue, pages, price, links)

#### Python Example
```python
import requests
import xml.etree.ElementTree as ET

url = "http://api.dbpia.co.kr/v2/search/search.xml"
params = {
    "key": "YOUR_DBPIA_KEY",
    "target": "se",
    "searchall": "인공지능 자유의지",
    "pagecount": 20,
    "sorttype": 2
}
resp = requests.get(url, params=params)
root = ET.fromstring(resp.content)
for item in root.findall(".//item"):
    print(item.findtext("title"), item.findtext("link_url"))
```

---

### 2.3 RISS — Best for Dissertations

**Operator**: KERIS (Korean Education & Research Information Service)
**Coverage**: Korean dissertations, domestic/overseas academic papers, books

#### Authentication
1. Register at `https://www.data.go.kr`
2. Apply for RISS API (Dataset 3046254 for domestic, 3046274 for overseas)

#### Endpoints
```
# Domestic academic papers
http://www.riss.kr/apicenter/apiSearchJournal.do

# Overseas academic journal papers
http://www.riss.kr/apicenter/apiSearchDissEtc.do
```

#### Response: XML

**Note**: RISS API documentation is less publicly accessible. Full parameter specs require login to the RISS API Center portal. SAM (Scholarly Analysis & Metrics) API requires Korean university affiliation.

---

### 2.4 ScienceON — Science & Technology Focus

**Operator**: KISTI
**Coverage**: Korean science and technology papers, patents, reports

#### Authentication
1. Register at ScienceON API Gateway portal
2. Receive `client_id` (64-char) and `ACCESS_TOKEN`

#### Endpoint
```
https://apigateway.kisti.re.kr/openapicall.do
```

#### Parameters
```
client_id=YOUR_CLIENT_ID
token=YOUR_ACCESS_TOKEN
version=1.0
action=search
target=ARTI                    # Papers
searchQuery=<JSON, URI-encoded>
sortField=relevance            # pubyear, title, jtitle, relevance
curPage=1
rowCount=100                   # max 100
```

#### Search Fields
`BI` (full text), `TI` (title), `AU` (author), `AB` (abstract), `KW` (keywords), `PB` (publisher), `SN` (ISSN), `BN` (ISBN), `PY` (year), `DI` (DOI)

#### Response: XML

---

## Part 3: API Capability Matrix

### Coverage Comparison

| API | Total Records | Citations | References | Full Text | Abstracts | OA Focus |
|-----|:---:|:---:|:---:|:---:|:---:|:---:|
| **OpenAlex** | 270M+ | Yes (count + list) | Yes (list) | Index only | Inverted index | Yes |
| **Semantic Scholar** | 214M | Yes (count + list + context) | Yes (list) | Snippet search | Yes | Partial |
| **CrossRef** | 176M+ | Count only | ~50% of works | No | ~20-30% | No |
| **arXiv** | 3M | No | No | PDF download | Yes | All OA |
| **CORE** | 313M/37M FT | Yes (count) | Yes | **Yes (inline)** | Yes | All OA |
| **KCI** | Korean journals | **Yes (citation + IF)** | Yes | No | Varies | No |
| **DBpia** | Korean journals | No | No | No | Varies | No |
| **RISS** | Korean all | No | No | No | Varies | No |

### Unique Strengths per API

| API | Unique Value |
|-----|-------------|
| **OpenAlex** | Broadest free coverage, topic hierarchy, FWCI, institutional data |
| **Semantic Scholar** | TLDR summaries, SPECTER2 embeddings, citation intent, full-text snippets |
| **CrossRef** | Authoritative DOI metadata, funder data, reference lists |
| **arXiv** | Fastest preprint access, LaTeX source, version history |
| **CORE** | Full paper text inline in API response, global OA coverage |
| **KCI** | Korean citation index, impact factors, NRF quality metrics |
| **DBpia** | Korean journal articles with popularity rankings |
| **RISS** | Korean dissertations (most comprehensive source) |

### Recommended Search Strategy by Use Case

| Use Case | Primary API | Supplementary |
|----------|-------------|---------------|
| **Systematic literature review** | OpenAlex (broadest) | Semantic Scholar (citations), CrossRef (DOI verify) |
| **Citation network analysis** | Semantic Scholar (contexts) | OpenAlex (FWCI) |
| **Find seminal works** | Semantic Scholar (influential citations) | OpenAlex (citation percentile) |
| **Verify DOI metadata** | CrossRef (authoritative) | — |
| **Get full paper text** | CORE (37M full-text) | arXiv (STEM PDFs) |
| **STEM preprints** | arXiv (fastest) | Semantic Scholar |
| **Korean literature** | KCI (citations) + DBpia (articles) | RISS (dissertations) |
| **Trend analysis** | OpenAlex (group_by year) | Semantic Scholar (bulk search) |

---

## Part 4: Implementation Architecture

### Recommended Integration Order

```
Phase 1 (Immediate — No/Minimal Registration)
├── CrossRef     ← No registration, just add email
├── arXiv        ← No registration at all
└── Semantic Scholar ← Works without key

Phase 2 (Quick Registration — 1-2 minutes each)
├── OpenAlex     ← Create account, get key from settings
└── CORE         ← Submit form, key via email

Phase 3 (Korean — data.go.kr registration)
├── KCI          ← data.go.kr registration + API apply
├── DBpia        ← api.dbpia.co.kr registration
├── RISS         ← data.go.kr registration + API apply
└── ScienceON    ← Portal registration
```

### Python Package Dependencies
```
# requirements-academic.txt
pyalex>=0.14          # OpenAlex client
semanticscholar>=0.8  # Semantic Scholar client
habanero>=1.2         # CrossRef client
arxiv>=2.1            # arXiv client
requests>=2.31        # CORE + Korean APIs (direct HTTP)
```

### Configuration File Structure
```yaml
# config/academic-apis.yaml
apis:
  openalex:
    base_url: https://api.openalex.org
    api_key: ${OPENALEX_API_KEY}  # from env
    rate_limit: 100  # req/sec
    daily_budget: 1.0  # USD

  semantic_scholar:
    base_url: https://api.semanticscholar.org/graph/v1
    api_key: ${S2_API_KEY}  # optional
    rate_limit: 1  # req/sec with key

  crossref:
    base_url: https://api.crossref.org
    mailto: ${CROSSREF_EMAIL}
    rate_limit: 3  # req/sec polite

  arxiv:
    base_url: http://export.arxiv.org/api
    rate_limit: 0.33  # 1 req / 3 sec

  core:
    base_url: https://api.core.ac.uk/v3
    api_key: ${CORE_API_KEY}
    daily_tokens: 1000

  kci:
    base_url: https://open.kci.go.kr/po/openapi/openApiSearch.kci
    api_key: ${KCI_API_KEY}

  dbpia:
    base_url: http://api.dbpia.co.kr/v2/search/search.xml
    api_key: ${DBPIA_API_KEY}

  riss:
    base_url: http://www.riss.kr/apicenter/apiSearchJournal.do
    api_key: ${RISS_API_KEY}

  scienceon:
    base_url: https://apigateway.kisti.re.kr/openapicall.do
    client_id: ${SCIENCEON_CLIENT_ID}
    token: ${SCIENCEON_TOKEN}
```

### Environment Variables
```bash
# .env (gitignored)
OPENALEX_API_KEY=your_openalex_key
S2_API_KEY=your_semantic_scholar_key       # optional
CROSSREF_EMAIL=your@email.com
CORE_API_KEY=your_core_key
KCI_API_KEY=your_kci_key
DBPIA_API_KEY=your_dbpia_key
RISS_API_KEY=your_riss_key
SCIENCEON_CLIENT_ID=your_scienceon_id
SCIENCEON_TOKEN=your_scienceon_token
```

### Unified Search Interface (Conceptual)

```python
class AcademicSearchClient:
    """Unified interface to 9 academic databases."""

    def search(self, query: str, *, databases: list[str] | None = None,
               year_range: tuple[int, int] | None = None,
               min_citations: int = 0,
               max_results: int = 100) -> list[Paper]:
        """Search across multiple databases and deduplicate by DOI."""

    def get_paper(self, doi: str) -> Paper:
        """Get paper metadata from the best available source."""

    def get_citations(self, doi: str) -> list[Paper]:
        """Get papers citing the given work."""

    def get_references(self, doi: str) -> list[Paper]:
        """Get papers referenced by the given work."""

    def get_full_text(self, doi: str) -> str | None:
        """Try to get full text (CORE > arXiv PDF > OA link)."""

    def search_korean(self, query: str, **kwargs) -> list[Paper]:
        """Search Korean databases (KCI + DBpia + RISS)."""
```

---

## Part 5: API Key Setup Guide (Step-by-Step)

### Phase 1: Zero-Registration APIs

#### CrossRef
No setup needed. Just use email in requests:
```python
from habanero import Crossref
cr = Crossref(mailto="your@email.com")  # That's it
```

#### arXiv
No setup needed. Just use the API:
```python
import arxiv
client = arxiv.Client()  # That's it
```

#### Semantic Scholar (without key)
No setup needed for basic use:
```python
from semanticscholar import SemanticScholar
sch = SemanticScholar()  # That's it (shared pool)
```

### Phase 2: Quick Web Registration

#### OpenAlex (2 minutes)
1. Go to `https://openalex.org`
2. Click "Sign Up" / Create account (email + password)
3. Go to `https://openalex.org/settings/api`
4. Copy your API key
5. Set environment variable:
   ```bash
   export OPENALEX_API_KEY="your_key_here"
   ```

#### Semantic Scholar (with key, 3-5 minutes)
1. Go to `https://www.semanticscholar.org/product/api`
2. Scroll to "Request API Key" form
3. Fill: name, email, use case description
4. Check email for API key (may take a few minutes)
5. Set environment variable:
   ```bash
   export S2_API_KEY="your_key_here"
   ```

#### CORE (3-5 minutes)
1. Go to `https://core.ac.uk/services/api`
2. Click "Register for API"
3. Fill: email, name, intended use
4. Check email for API key
5. Set environment variable:
   ```bash
   export CORE_API_KEY="your_key_here"
   ```

### Phase 3: Korean APIs (data.go.kr)

#### data.go.kr Registration (one-time, 5 minutes)
1. Go to `https://www.data.go.kr`
2. Click "회원가입" (Sign Up)
3. Complete registration (Korean ID or simplified process)
4. This single account gives access to KCI, RISS, and ScienceON APIs

#### KCI API Key
1. **Option A** (recommended): Go to `https://www.kci.go.kr/kciportal/po/openapi/openApiKeyRequest.kci`
   - Register and request API key
2. **Option B**: On data.go.kr, search for Dataset 15085348
   - Click "활용신청" (Apply for Use)
   - Auto-approved for development key
3. Set: `export KCI_API_KEY="your_key_here"`

#### DBpia API Key
1. Go to `https://api.dbpia.co.kr/openApi/index.do`
2. Register as member
3. Apply for Search API key
4. Set: `export DBPIA_API_KEY="your_key_here"`

#### RISS API Key
1. On data.go.kr, search for Dataset 3046254
2. Click "활용신청" (Apply for Use)
3. Set: `export RISS_API_KEY="your_key_here"`

#### ScienceON
1. Register at ScienceON API Gateway portal
2. Receive client_id and token
3. Set:
   ```bash
   export SCIENCEON_CLIENT_ID="your_id_here"
   export SCIENCEON_TOKEN="your_token_here"
   ```

---

## Part 6: Key Limitations and Mitigations

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| OpenAlex abstracts as inverted index | Harder to read | Reconstruct: `" ".join(sorted(inv_idx, key=lambda w: inv_idx[w][0]))` |
| CrossRef no citing DOI list (public) | Can't trace full citation graph | Use Semantic Scholar or OpenAlex for citation lists |
| arXiv STEM only | No humanities/social sciences | Use OpenAlex + CORE for non-STEM |
| arXiv no citation data | Can't rank by impact | Cross-reference with Semantic Scholar or OpenAlex |
| CORE rate limits (1,000/day free) | Limits full-text retrieval | Prioritize high-relevance papers for full-text |
| Korean APIs XML-only | Extra parsing needed | Use ElementTree; standardize to JSON internally |
| Korean APIs less documented | Integration uncertainty | Test with small queries first; fallback to data.go.kr |
| CrossRef 3 req/sec polite limit | Slow for bulk operations | Use cursor pagination; cache results |
| Semantic Scholar 1 req/sec with key | Slow for large searches | Use bulk search endpoint; batch lookups |

---

## Appendix A: Quick Reference — curl Examples

```bash
# OpenAlex: Search + filter + sort
curl "https://api.openalex.org/works?search=free+will+AI&filter=publication_year:>2019&sort=cited_by_count:desc&per_page=10&api_key=KEY"

# Semantic Scholar: Bulk boolean search
curl "https://api.semanticscholar.org/graph/v1/paper/search/bulk?query=%22artificial+agency%22+%2B%22free+will%22&fields=title,year,citationCount&sort=citationCount:desc"

# CrossRef: Filtered search
curl "https://api.crossref.org/works?query=free+will+artificial+intelligence&filter=type:journal-article,from-pub-date:2020-01-01&sort=is-referenced-by-count&order=desc&rows=10&mailto=you@example.com"

# arXiv: Category + keyword search
curl "http://export.arxiv.org/api/query?search_query=all:free+will+AND+cat:cs.AI&max_results=10&sortBy=submittedDate"

# CORE: Full-text filter search
curl -H "Authorization: Bearer KEY" "https://api.core.ac.uk/v3/search/works?q=title:%22free+will%22+AND+_exists_:fullText&limit=10"

# KCI: Article search
curl "https://open.kci.go.kr/po/openapi/openApiSearch.kci?key=KEY&apiCode=articleSearch&title=free+will&displayCount=10"

# DBpia: Basic search
curl "http://api.dbpia.co.kr/v2/search/search.xml?key=KEY&target=se&searchall=자유의지&pagecount=10"
```

---

## Appendix B: Data Sources Consulted

### Official Documentation
- OpenAlex: developers.openalex.org
- Semantic Scholar: api.semanticscholar.org/api-docs/
- CrossRef: crossref.org/documentation/retrieve-metadata/rest-api/
- arXiv: info.arxiv.org/help/api/
- CORE: api.core.ac.uk/docs/v3
- KCI: kci.go.kr/kciportal/po/openapi/
- DBpia: api.dbpia.co.kr/openApi/
- RISS: data.go.kr (Dataset 3046254)
- ScienceON: data.go.kr (Dataset 15117315)

### Python Libraries
- pyalex: github.com/J535D165/pyalex
- semanticscholar: github.com/danielnsilva/semanticscholar
- habanero: habanero.readthedocs.io
- arxiv: github.com/lukasschwab/arxiv.py
