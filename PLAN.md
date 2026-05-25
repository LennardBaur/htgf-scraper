# HTGF Early-Stage Sourcing Tool — Build Plan

**Goal:** An AI-native pipeline that surfaces pre-seed / seed Digital Tech startups in DACH **before** they appear on Crunchbase or Dealroom, enriches them, scores them against HTGF's thesis, and outputs a ranked CSV + per-startup one-pager (German) + live Google Sheet.

**Scope (locked):**
- Sector: Digital Tech (B2B SaaS, AI-native, dev tools) — pipeline is sector-pluggable via config
- Geography: DACH primary, framework supports extension
- Stage: Pre-seed and seed (companies ≤ 3 years old)
- Repeatedly runnable, incremental, cache-deterministic
- Budget cap: ~$15–20 per full run

---

## 0. Strategic Premise

HTGF's edge in this task is **time**, not data volume. Crunchbase, Dealroom, PitchBook are reactive — they list a startup *after* a round is announced. By then 20 other VCs already saw it. The interesting signals are the ones that surface **intent to build** or **early traction** before any round closes:

1. **EXIST grant recipients** — German federal grant for academic founders, publicly announced, lightly tracked.
2. **University TTO spin-out announcements** — TUM, RWTH, KIT, TU Berlin, Fraunhofer.
3. **GitHub orgs with ≥2 contributors, recent activity, a German website** — building-in-public signal.
4. **Hacker News "Show HN" with EU/DACH founders** — same.
5. **Product Hunt + Beta List "upcoming"** — pre-launch product, not yet funded.

These five sources rarely get fused systematically by a single VC. That's the wedge.

---

## 1. HTGF Digital Tech Thesis (Reference)

Anchor portfolio companies (use these as positive examples in the scoring prompt):

| Company | HQ | Founded | Round | One-liner |
|---|---|---|---|---|
| Zeeg | Berlin | 2023 | €1.1M Pre-Seed (Oct 2025) | AI-powered booking CRM, EU data sovereignty |
| Stackgini | DACH | 2023 | Pre-Seed (Apr 2024, revealed Jul 2025) | AI for IT demand management, enterprise customers (DAX40, Mittelstand) |
| Pactos | Munich | 2024 | €2.7M Pre-Seed (Sep 2025) | AI platform for managing external workforces |
| syte | Münster | 2022 | €5M Seed (Sep 2024) | AI data platform for real estate (digitalization + decarbonization) |
| Data Virtuality | Leipzig | (legacy) | Seed → Exit | Data integration platform (acquired by CData) |

**Hard constraints HTGF applies:**
- Company ≤ 3 years since incorporation
- HQ in Germany OR has German base of operations
- Active in Digital Tech, Industrial Tech, Life Sciences, or Chemistry
- For seed cap: up to €8M from HTGF in one company

**Pattern across the anchors:**
- B2B SaaS (always)
- AI-powered (≥90% of recent Digital Tech bets)
- Enterprise / Mittelstand customer base
- Often vertical-specific (proptech, IT ops, real estate, HR/workforce)
- Sometimes "EU sovereignty" angle (privacy, on-prem option, GDPR-native)

The scoring prompt (Section 9) bakes these in as few-shot anchors.

---

## 2. Architecture Overview

Three loosely coupled stages, each producing inspectable artifacts:

```
                    ┌─────────────────────────────────────────────┐
                    │            STATE (SQLite + cache/)           │
                    │   leads, enrichments, scores, raw_pages      │
                    └─────────────▲───────────────────────────────┘
                                  │
   ┌──────────────┐        ┌──────┴──────┐        ┌─────────────────┐
   │   DISCOVER   │ ─────▶ │   ENRICH    │ ─────▶ │  SCORE & EXPORT │
   │ (collectors) │        │ (fetch+LLM) │        │  (rank, write)  │
   └──────────────┘        └─────────────┘        └─────────────────┘
        │                        │                       │
   sources/*.py            enrichers/*.py           exporters/*.py
   each → RawLead          → EnrichedStartup        → CSV + MD + Sheet
```

**Key principle:** each stage is idempotent and resumable. Re-running `discover` only adds new leads (dedup by domain). Re-running `enrich` skips startups enriched within the last 14 days. Re-running `score` is always cheap and always runs.

---

## 3. Project Structure

```
htgf-sourcer/
├── README.md                       # how to install, run, what it does
├── pyproject.toml                  # uv-managed
├── .env.example                    # API keys placeholders
├── .gitignore                      # excludes .env, cache/raw/, outputs/private/
├── config/
│   ├── htgf_thesis.yaml            # anchors, weights, hard filters
│   ├── universities.yaml           # TTO URLs
│   └── sources.yaml                # which sources enabled, rate limits
├── src/htgf_sourcer/
│   ├── __init__.py
│   ├── cli.py                      # Typer entry point
│   ├── models.py                   # Pydantic: RawLead, Founder, EnrichedStartup, Score
│   ├── db.py                       # SQLite schema + helpers
│   ├── fetch.py                    # Jina → Firecrawl → Playwright chain
│   ├── llm.py                      # Anthropic client wrapper (extract, score, dedup)
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py                 # Collector ABC
│   │   ├── exist.py
│   │   ├── universities.py         # TUM, RWTH, KIT, TUB, Fraunhofer
│   │   ├── handelsregister.py      # via OffeneRegister
│   │   ├── github.py               # trending + new orgs
│   │   ├── hackernews.py           # Algolia HN
│   │   ├── producthunt.py
│   │   └── betalist.py
│   ├── enrich.py                   # orchestrates enrichment per lead
│   ├── score.py                    # scoring orchestration
│   ├── dedup.py                    # domain + LLM pairwise
│   └── exporters/
│       ├── csv_writer.py
│       ├── markdown_onepager.py
│       └── google_sheets.py
├── prompts/
│   ├── extract_startup.txt         # extraction prompt with Pydantic schema
│   ├── score_startup.txt           # scoring prompt with HTGF anchors
│   └── dedup_check.txt             # pairwise dedup prompt (Haiku)
├── cache/
│   ├── pages/                      # raw markdown of every URL fetched
│   ├── llm/                        # SHA256-keyed LLM responses
│   └── state.db                    # SQLite
├── tests/
│   ├── test_models.py
│   ├── test_dedup.py
│   ├── test_sources_exist.py
│   └── fixtures/                   # captured HTML/JSON for offline tests
├── outputs/
│   ├── leads.csv
│   ├── leads.xlsx                  # same data, pretty formatted
│   ├── onepagers/                  # one .md per top-N startup
│   └── run_summary.md              # per-run report
└── scripts/
    └── scrape_htgf_portfolio.py    # one-off: build anchor list from htgf.de
```

---

## 4. Tech Stack (Exact)

| Layer | Choice | Reason |
|---|---|---|
| Env / packaging | `uv` | Fast, modern, used by AI-native projects |
| Python | 3.11+ | `StrEnum`, better error messages |
| HTTP | `httpx` (async) | Modern, supports HTTP/2 |
| HTML parsing | `selectolax` | 10× faster than BeautifulSoup, good enough |
| JS-heavy fetch | `playwright` (chromium, headless) | Fallback only |
| AI-native fetch | `r.jina.ai/<url>` (free) + Firecrawl (paid fallback) | Returns clean markdown, saves 80% of parsing work |
| LLM | `anthropic` SDK | Direct, no LangChain bloat |
| Models | Claude Sonnet 4.6 (extraction + scoring), Claude Haiku 4.5 (dedup pairwise) | Cost/quality balance |
| Structured output | `pydantic` v2 + Anthropic tool-use | Validated outputs |
| State | `sqlite3` (stdlib) + `sqlmodel` for ORM | No setup, file-based, transparent |
| CLI | `typer` | Click with type hints |
| Logging | `loguru` | Pretty by default |
| Console output | `rich` | Progress bars, tables |
| Data wrangling | `pandas` + `openpyxl` | CSV + XLSX export |
| Google Sheets | `gspread` + `google-auth` | Service-account OAuth |
| Config | `pyyaml` + `pydantic-settings` | Typed config |
| Test | `pytest` + `pytest-recording` (VCR) | Replayable HTTP fixtures |
| Lint | `ruff` | Fast, all-in-one |

`pyproject.toml` dependencies (copy-paste-ready):

```toml
[project]
name = "htgf-sourcer"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40",
    "httpx>=0.27",
    "selectolax>=0.3",
    "playwright>=1.45",
    "pydantic>=2.7",
    "pydantic-settings>=2.4",
    "sqlmodel>=0.0.21",
    "typer>=0.12",
    "loguru>=0.7",
    "rich>=13",
    "pandas>=2.2",
    "openpyxl>=3.1",
    "gspread>=6.1",
    "google-auth>=2.32",
    "pyyaml>=6.0",
    "tenacity>=9.0",  # retry decorators
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-recording>=0.13", "ruff>=0.6"]

[project.scripts]
sourcer = "htgf_sourcer.cli:app"
```

---

## 5. Data Models (Pydantic)

```python
# src/htgf_sourcer/models.py
from datetime import date, datetime
from enum import StrEnum
from pydantic import BaseModel, Field, HttpUrl

class Source(StrEnum):
    EXIST = "exist"
    UNIVERSITY = "university"
    HANDELSREGISTER = "handelsregister"
    GITHUB = "github"
    HACKERNEWS = "hackernews"
    PRODUCTHUNT = "producthunt"
    BETALIST = "betalist"

class Stage(StrEnum):
    PRE_INCORPORATION = "pre_incorporation"
    STEALTH = "stealth"
    PRE_LAUNCH = "pre_launch"
    PRE_SEED = "pre_seed"
    SEED = "seed"
    UNKNOWN = "unknown"

class RawLead(BaseModel):
    """Output of a Source collector. Lightweight, may be incomplete."""
    source: Source
    source_id: str                          # the source's native id (HN story id, GH repo, etc.)
    name: str | None = None
    website: HttpUrl | None = None
    one_liner: str | None = None
    location_hint: str | None = None        # e.g. "Berlin" or "TUM"
    discovered_at: datetime
    raw_payload: dict = Field(default_factory=dict)  # everything the source returned

class Founder(BaseModel):
    name: str
    role: str | None = None
    linkedin_url: HttpUrl | None = None
    email: str | None = None
    background: str | None = None           # 1-sentence summary from LLM extraction

class EnrichedStartup(BaseModel):
    """After fetch + LLM extraction."""
    canonical_id: str                        # stable hash of normalized domain
    name: str
    website: HttpUrl | None = None
    one_liner: str
    long_description: str
    sector: str                              # e.g. "B2B SaaS", "DevTools", "PropTech AI"
    sub_sector: str | None = None
    hq_city: str | None = None
    hq_country: str | None = None
    founded_year: int | None = None
    incorporation_status: str | None = None  # "GmbH eingetragen", "in Gründung", ...
    stage_signal: Stage = Stage.UNKNOWN
    team_size_estimate: int | None = None
    founders: list[Founder] = Field(default_factory=list)
    traction_signals: list[str] = Field(default_factory=list)   # "10k GitHub stars", "Paying customer: Grünenthal"
    funding_signals: list[str] = Field(default_factory=list)    # "EXIST 2025", "Pre-seed Oct 2025"
    sources: list[Source] = Field(default_factory=list)          # which collectors found this
    source_urls: list[HttpUrl] = Field(default_factory=list)
    last_enriched: datetime

class Score(BaseModel):
    """LLM-generated, per startup."""
    canonical_id: str
    thesis_fit: int = Field(ge=1, le=5)        # B2B SaaS, AI, DACH, dev/enterprise?
    team_quality: int = Field(ge=1, le=5)      # Technical founders, prior exits, academic credentials
    earliness: int = Field(ge=1, le=5)         # 5 = pre-incorporation, 1 = already funded by major VC
    traction: int = Field(ge=1, le=5)          # Customers, paying users, GitHub momentum
    contactability: int = Field(ge=1, le=5)    # Email/LinkedIn available, founder responsive online
    overall: float                              # weighted (see config/htgf_thesis.yaml)
    rationale: str                              # 2-3 sentences, German
    red_flags: list[str] = Field(default_factory=list)
    scored_at: datetime
```

The Anthropic tool-use schema is auto-generated from these Pydantic models via `model.model_json_schema()`.

---

## 6. Source Collectors

Each module implements:

```python
class Collector(ABC):
    source: Source
    @abstractmethod
    async def collect(self, since: datetime | None) -> list[RawLead]: ...
```

### 6.1 EXIST Grants (`sources/exist.py`)

**What:** EXIST-Gründerstipendium and EXIST-Forschungstransfer are German federal grants. Recipients are publicly listed.

**Where:**
- Primary list: `https://www.exist.de/EXIST/Navigation/DE/Gefoerderte-Projekte/EXIST-Gruenderstipendium/exist-gruenderstipendium.html`
- Forschungstransfer: `https://www.exist.de/EXIST/Navigation/DE/Gefoerderte-Projekte/EXIST-Forschungstransfer/exist-forschungstransfer.html`
- Many universities publish their own list too

**Strategy:**
1. Fetch index page via Jina Reader (`r.jina.ai/https://www.exist.de/...`)
2. Parse for project entries (title, university, abstract, year)
3. Filter: year ≥ current_year - 2, abstract contains digital tech keywords (`software`, `KI`, `SaaS`, `Plattform`, `Daten`, `Cloud`, `Entwickler`, `API`, ...)
4. Each entry → `RawLead` with `name = project_title`, `location_hint = university`

**Filter keywords (whitelist, OR):** `software`, `saas`, `plattform`, `cloud`, `ki`, `ai`, `ml`, `data`, `daten`, `api`, `developer`, `entwickler`, `b2b`, `automation`, `enterprise`, `cyber`, `devops`, `analytics`

**Rate limit:** None imposed, but cache aggressively (one fetch per day max).

**Edge case:** Names are often working titles, not company names. The enrichment stage handles canonicalization.

### 6.2 University TTOs (`sources/universities.py`)

**Targets (config-driven):**

```yaml
# config/universities.yaml
universities:
  - name: "TU München"
    spinoff_url: "https://www.unternehmertum.de/themen/startups"
    news_url: "https://www.tum.de/aktuelles/alle-meldungen"
  - name: "RWTH Aachen"
    spinoff_url: "https://www.rwth-innovation.de/de/gruendung/spinoffs"
  - name: "KIT"
    spinoff_url: "https://www.kit.edu/kit/innovation.php"
  - name: "TU Berlin"
    spinoff_url: "https://www.tu.berlin/forschung/anwendungen-und-transfer/ausgruendungen"
  - name: "Fraunhofer"
    spinoff_url: "https://www.fraunhofer-venture.de/de/start-ups/portfolio.html"
```

**Strategy:**
1. For each URL: Jina Reader → markdown
2. Pass markdown to Claude Sonnet with a structured-output tool: "Extract every spin-off or startup mentioned on this page. For each: name, one-liner, founders if listed, website if listed, year if listed."
3. Each extracted item → `RawLead`

This is **AI-native scraping**: we don't write fragile CSS selectors per university; we let the LLM do structured extraction. ~1k tokens per page, ~$0.01 per university.

### 6.3 Handelsregister via OffeneRegister (`sources/handelsregister.py`)

**What:** Newly registered GmbHs in tech sectors.

**Where:** `https://offeneregister.de/` — open data German trade register. Bulk dataset is downloadable.

**Strategy (lean version for v1):**
1. Download the JSON dump (one-time, ~500MB).
2. Filter rows: `registration_date >= today - 180 days` AND `purpose` field contains digital tech keywords.
3. Each row → `RawLead` with `name = company_name`, `location_hint = city`.

**Note:** OffeneRegister doesn't always have purposes. If too noisy, drop this source for v1 and add as a "next steps" item in the README. Decision rule: if first run yields < 30% useful leads from this source, document it as a known limitation.

### 6.4 GitHub (`sources/github.py`)

**Two signals:**

**A. Trending repos with DACH context**
- Endpoint: `https://api.github.com/search/repositories?q=created:>{date}+language:typescript+location:Germany&sort=stars&order=desc`
- Search variations: language ∈ {TypeScript, Python, Rust, Go}, location ∈ {Germany, Berlin, Munich, Hamburg, Cologne, Vienna, Zurich, ...}
- Filter: stars ≥ 50, created in last 12 months, has a website in repo metadata

**B. New organizations with multiple contributors**
- Endpoint: `https://api.github.com/orgs/{org}` (we need a seed list — derived from A)
- Filter orgs: ≥ 2 members, members have DACH location in profile, public website looks like a startup site (not personal blog)

**Auth:** Personal Access Token in `GITHUB_TOKEN` env. 5000 requests/hour with token. Plenty.

**Each repo/org → `RawLead`** with `website = repo.homepage`, `one_liner = repo.description`.

### 6.5 Hacker News (`sources/hackernews.py`)

**API:** Algolia HN Search — `https://hn.algolia.com/api/v1/search?tags=show_hn&numericFilters=created_at_i>{ts}`

**Strategy:**
1. Pull all Show HN from last 90 days
2. For each: fetch the linked URL via Jina Reader, capture title + first 1000 chars
3. Use Claude Haiku to filter: "Is this a DACH-based B2B SaaS or dev tool? Yes/no/unsure." Keep yes + unsure.
4. Each kept → `RawLead`

**Cost note:** Filtering ~300 Show HN posts via Haiku ≈ $0.20.

### 6.6 Product Hunt (`sources/producthunt.py`)

**API:** Product Hunt GraphQL API, free with API key (`PRODUCT_HUNT_TOKEN`).

**Query:** posts created in last 90 days, sorted by votes.

**Filter:**
- Makers list includes someone with `headline` containing DACH cities or `website` ending `.de`/`.at`/`.ch`, OR
- The product website is DACH

**Each post → `RawLead`** with `website = post.website`, `one_liner = post.tagline`.

### 6.7 Beta List (`sources/betalist.py`)

**No API.** Site is static-ish. Fetch `https://betalist.com/markets/germany` and similar slugs.

**Strategy:** Jina Reader → markdown → Claude extracts startups (same AI-native pattern as universities).

---

## 7. Enrichment Pipeline (`enrich.py`)

For each `RawLead` not yet enriched (or enriched > 14 days ago):

**Step 1 — Canonicalize.** Resolve to a single canonical domain (lowercase, no www, no trailing slash). If `website` is missing, mark for manual review and skip.

**Step 2 — Fetch supporting pages.** In parallel:
- Landing page (`https://example.com/`)
- About page (try `/about`, `/team`, `/ueber-uns`, `/about-us`)
- Career page (signal of team size)
- If GitHub URL is on the site: also fetch the GitHub org page

Use the **fetch chain**:
1. Try Jina Reader (`https://r.jina.ai/<url>`) — free, returns clean markdown
2. If empty / 404 / blocked → Firecrawl API
3. If still empty → Playwright headless

Cache every successful fetch to `cache/pages/{sha256(url)}.md` with a sidecar `.meta.json` (URL, timestamp, status).

**Step 3 — LLM extraction.** Concatenate fetched markdown (capped at ~30k tokens). Send to Claude Sonnet 4.6 with the `EnrichedStartup` Pydantic schema as a tool. Prompt skeleton:

```
You extract structured startup data from website content for a German seed-stage
VC. Be conservative: only fill fields you can support from the content. Leave
fields null when unsure. Founder emails: only include if explicitly listed on
the site (imprint/contact page). Never guess emails.

CONTENT:
<concatenated markdown>

Use the `record_startup` tool to return your extraction.
```

**Step 4 — LinkedIn / founder enrichment.** If founder names are extracted but no LinkedIn URLs:
- Try a Google search via DuckDuckGo HTML (`https://duckduckgo.com/html/?q="{name}"+linkedin+{company}`)
- Parse first result; if it's `linkedin.com/in/...`, store it
- Do NOT scrape the LinkedIn profile itself — ToS risk

**Step 5 — Persist** to SQLite `enriched_startups` table.

---

## 8. Scoring (`score.py`)

After all enrichments are done, score each startup once.

**Prompt template (`prompts/score_startup.txt`):**

```
You are a senior investment analyst at HTGF (High-Tech Gründerfonds), Germany's
largest seed-stage tech investor. Score this startup for HTGF fit.

HTGF DIGITAL TECH THESIS:
- B2B SaaS, AI-powered, DACH-based
- Pre-seed or seed, company ≤ 3 years since incorporation
- HQ in Germany or German base of operations
- Verticals welcome: dev tools, infrastructure, enterprise productivity,
  vertical SaaS (proptech, IT ops, HR, real estate, etc.)
- Bonus: EU data sovereignty angle, Mittelstand/enterprise customers,
  technical founders with academic or prior-exit pedigree

POSITIVE ANCHORS (real HTGF Digital Tech investments):
- Zeeg (Berlin, 2023): AI-powered booking CRM, EU data sovereignty
- Stackgini: AI for IT demand management, DAX40 + Mittelstand customers
- Pactos (Munich, 2024): AI platform for external workforce management
- syte (Münster, 2022): AI data platform for real estate
- Data Virtuality: data integration platform

NEGATIVE ANCHORS (out of scope):
- Pure consumer apps with no enterprise angle
- Hardware-only without significant software
- Late-stage (Series A+) companies
- Non-DACH HQ with no German operations

STARTUP TO SCORE:
<EnrichedStartup JSON>

Score each dimension 1–5:
1. thesis_fit — Does it match the B2B SaaS / AI / dev-or-vertical-tools pattern?
2. team_quality — Technical founders? Academic/exit pedigree? Multi-founder?
3. earliness — How early are we vs. other investors? 5 = stealth/pre-inc, 1 = already with a Tier-1 lead.
4. traction — Paying customers? GitHub momentum? Notable partnerships?
5. contactability — Founder LinkedIn/email available, online presence active?

Then a 2–3 sentence rationale **in German** and a list of red flags.

Return via the `record_score` tool.
```

**Weighting** (in `config/htgf_thesis.yaml`):

```yaml
score_weights:
  thesis_fit: 0.35
  team_quality: 0.20
  earliness: 0.25
  traction: 0.15
  contactability: 0.05
```

`overall = sum(weight_i * score_i)` — gives a 0–5 float used for the final ranking.

---

## 9. Deduplication (`dedup.py`)

Two-stage:

**Stage 1 — domain canonicalization (deterministic).** Lower-case, strip `www.`, strip trailing slash, strip `?utm_*`. Two leads with the same canonical domain merge automatically.

**Stage 2 — pairwise LLM check (Haiku).** Some startups appear without a website (EXIST entries, early-stage university spin-outs). For these, do a Haiku pairwise check against existing leads with similar normalized names (Levenshtein < 5 OR same university + similar topic):

```
Are these two records about the same startup? Answer YES or NO with one
sentence of reasoning.

A: <RawLead JSON>
B: <EnrichedStartup JSON>
```

Cost: ~$0.001 per pair, only invoked on ambiguous matches.

When merged, keep the enriched record but extend `sources` and `source_urls`. Multi-source coverage is itself a positive signal — show it in the output.

---

## 10. State & Caching

**SQLite schema** (in `db.py`):

```sql
CREATE TABLE leads (
    id TEXT PRIMARY KEY,                 -- canonical_id (sha256 of normalized domain or name+source)
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    name TEXT,
    website TEXT,
    one_liner TEXT,
    discovered_at TIMESTAMP NOT NULL,
    raw_payload TEXT,                    -- JSON
    UNIQUE(source, source_id)
);

CREATE TABLE enriched_startups (
    canonical_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,               -- full EnrichedStartup as JSON
    last_enriched TIMESTAMP NOT NULL
);

CREATE TABLE scores (
    canonical_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,               -- full Score as JSON
    scored_at TIMESTAMP NOT NULL,
    FOREIGN KEY (canonical_id) REFERENCES enriched_startups(canonical_id)
);

CREATE TABLE fetch_cache (
    url_hash TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    content_path TEXT NOT NULL,          -- relative path under cache/pages/
    fetched_at TIMESTAMP NOT NULL,
    fetcher TEXT NOT NULL                -- "jina" | "firecrawl" | "playwright"
);

CREATE TABLE llm_cache (
    request_hash TEXT PRIMARY KEY,       -- sha256 of (model + prompt + tool schema)
    response TEXT NOT NULL,              -- raw JSON
    model TEXT NOT NULL,
    cost_usd REAL,
    created_at TIMESTAMP NOT NULL
);
```

**Cache contract:** every LLM call goes through `llm.py::cached_call(prompt, schema)`. If the request hash exists, return cached. This makes the reviewer's re-run free.

**Commit policy:** `cache/state.db` and `cache/pages/` ARE committed (small, deterministic). `cache/llm/` is committed too. `.env` and any private outputs are gitignored. `outputs/` IS committed so the reviewer sees the result without running anything.

---

## 11. CLI Surface

```bash
sourcer discover                 # run all enabled collectors, write RawLead rows
sourcer discover --source exist  # one collector only
sourcer enrich                   # enrich all stale leads
sourcer enrich --limit 10        # only top-10 by discovered_at (for dev)
sourcer score                    # score all enriched startups
sourcer export                   # write CSV, XLSX, one-pagers, push to Sheets
sourcer run-all                  # discover → enrich → score → export
sourcer status                   # show counts: N leads, M enriched, K scored, cost-to-date
sourcer doctor                   # check API keys, tool availability, cache health
```

**Global flags:** `--config`, `--dry-run`, `--no-sheets`, `--max-spend USD`, `--verbose`.

`--max-spend` aborts the run mid-way if cumulative LLM spend exceeds the cap. Critical for the reviewer.

---

## 12. Output Spec

### 12.1 `outputs/leads.csv`

Columns, exact order:

```
rank, overall_score, thesis_fit, team_quality, earliness, traction, contactability,
name, website, one_liner, sector, sub_sector, hq_city, hq_country,
founded_year, stage_signal, team_size_estimate,
founder_names, founder_linkedins, founder_emails,
traction_signals, funding_signals,
sources, source_urls, rationale_de, red_flags,
discovered_at, last_enriched, scored_at, canonical_id
```

List-type fields are pipe-separated (`|`). `outputs/leads.xlsx` is the same data with column widths and a frozen header row.

### 12.2 `outputs/onepagers/{rank:02d}_{slug}.md` (German)

Template:

```markdown
# {name}

**Rang:** {rank} / {total}   **Score:** {overall_score:.2f} / 5.00

| | |
|---|---|
| Website | [{website}]({website}) |
| Sitz | {hq_city}, {hq_country} |
| Gegründet | {founded_year} |
| Stage | {stage_signal} |
| Sektor | {sector} · {sub_sector} |

## In einem Satz
{one_liner}

## Was sie machen
{long_description}

## Gründer
{for each founder:}
- **{name}** — {role}
  - LinkedIn: {linkedin_url or "—"}
  - E-Mail: {email or "—"}
  - Hintergrund: {background}

## Traction
{bullets from traction_signals}

## Finanzierung
{bullets from funding_signals}

## Bewertung (LLM)

| Dimension | Score |
|---|---|
| Thesis-Fit | {thesis_fit}/5 |
| Team-Qualität | {team_quality}/5 |
| Frühphasen-Vorteil | {earliness}/5 |
| Traction | {traction}/5 |
| Erreichbarkeit | {contactability}/5 |

**Begründung:** {rationale_de}

**Red Flags:** {red_flags or "keine"}

## Quellen
{bullets from source_urls}

---
*Generiert am {scored_at} · canonical_id: `{canonical_id}`*
```

### 12.3 `outputs/run_summary.md`

Per-run statistics:
- N leads discovered total, broken down by source
- N enriched, N skipped (already fresh), N failed
- N scored
- LLM spend in USD
- Wall-clock time per stage
- Top 5 by overall score (link to one-pager)

---

## 13. Google Sheets Export (`exporters/google_sheets.py`)

**Setup:**
1. User creates a Google Cloud project, enables Sheets API
2. Creates a service account, downloads JSON key, stores at `~/.config/htgf-sourcer/sa.json` (path configurable via env `GOOGLE_SA_PATH`)
3. User creates an empty Google Sheet, shares it with the service account email, puts its ID in `.env` as `GOOGLE_SHEET_ID`

**Behavior:**
- `sourcer export` writes to a tab named `leads_YYYY-MM-DD` (so history is preserved across runs)
- Tab is created if absent
- Header row is bold; first column (rank) is frozen
- A summary tab `runs/` is appended to with one row per run (date, counts, spend)
- `--no-sheets` flag disables this step (for when service account isn't configured)

README has a clear "Google Sheets setup is optional, skip with `--no-sheets`" note.

---

## 14. README Outline

```markdown
# HTGF Early-Stage Sourcing Tool

One-paragraph what + why.

## TL;DR for the reviewer

Quick-look: open `outputs/leads.xlsx` or the [linked Google Sheet]. Read `outputs/run_summary.md` for run stats. Read 2-3 one-pagers from `outputs/onepagers/`.

## How it works (3 paragraphs + the architecture diagram from Section 2)

## Sources used + why

Table: source · what it gives us · why it's early signal · cost.

## AI-native choices

- Jina + Firecrawl for fetching → structured markdown without per-site selectors.
- Claude Sonnet 4.6 with Pydantic-driven tool-use → typed extraction, no regex.
- Claude Haiku 4.5 for cheap pairwise dedup.
- HTGF anchors baked into scoring prompt as few-shot examples.
- Every LLM call is cached → re-runs are deterministic and free.

## Setup

uv sync, set .env from .env.example, optionally configure Google Sheets.

## Usage

CLI examples, including --max-spend.

## Project structure

(tree from Section 3)

## How the reviewer can re-run

`sourcer run-all --max-spend 20` — uses the committed cache; cost is near zero on second run.

## Limitations & GDPR notes

- LinkedIn full profile scraping is intentionally avoided (ToS + GDPR).
- Founder emails only collected when explicitly listed on company sites
  (imprint/contact); processing under legitimate-interest basis Art. 6(1)(f).
- Twitter/X dropped — API cost prohibitive.
- Handelsregister source may be noisy in v1 (purpose-field coverage gaps).
- Source list is configurable; adding new sectors = new keyword set in
  `config/htgf_thesis.yaml`.

## Next steps if this becomes a real tool

- Slack/email notification on new high-scoring leads
- Daily cron via GitHub Actions
- Add LinkedIn enrichment via Proxycurl (paid, but high-value)
- Add Northdata API for Handelsregister depth
- Embedding-based dedup at scale
- Per-analyst CRM-style "claim" workflow
```

---

## 15. Build Order for Claude Code

Hand these steps to Claude Code (or Cowork) in this order. Each step is one prompt. Verify the output before the next.

**Step 1 — Skeleton + models.**
> "Create the project structure from PLAN.md Section 3. Use uv for env. Implement `models.py` exactly as Section 5. Implement `db.py` with the schema from Section 10. Implement `cli.py` with all commands from Section 11 as stubs that print 'not implemented'. Add a `doctor` command that actually verifies env vars and tool availability. Set up pytest with a placeholder test."

**Step 2 — Fetch + LLM wrappers.**
> "Implement `fetch.py` with the Jina → Firecrawl → Playwright chain from Section 7. Implement `llm.py` with a `cached_call(prompt: str, tool_schema: dict, model: str) -> dict` function that hits the Anthropic API and caches by request hash to SQLite per Section 10. Include cost tracking. Add tests with mocked HTTP."

**Step 3 — One full source + one full enrichment, end-to-end.**
> "Implement `sources/hackernews.py` (Algolia HN, Show HN, last 90 days). Implement `enrich.py` (fetch landing + about pages via fetch chain, LLM extract into `EnrichedStartup`). Wire `sourcer discover --source hackernews` and `sourcer enrich` to actually work. Run it. We need ~10 enriched startups before moving on."

**Step 4 — Remaining sources.**
> "Implement the remaining collectors: `exist.py`, `universities.py`, `github.py`, `producthunt.py`, `betalist.py`. Use the AI-native extraction pattern from Section 6.2 (Jina → LLM with structured output) for any site without a clean API. Defer `handelsregister.py` to a stub for now."

**Step 5 — Scoring + dedup.**
> "Implement `score.py` per Section 8, using the prompt template from `prompts/score_startup.txt` with the HTGF anchors from Section 1 baked in. Implement `dedup.py` per Section 9. Run `sourcer score` on the existing enriched set."

**Step 6 — Exporters.**
> "Implement `exporters/csv_writer.py`, `exporters/markdown_onepager.py` (template from Section 12.2, **German**), `exporters/google_sheets.py` (Section 13). The xlsx export should use pandas + openpyxl with a frozen header row."

**Step 7 — End-to-end run + polish.**
> "Run `sourcer run-all --max-spend 20`. Inspect outputs. Iterate on prompts until top-10 leads look plausible. Write the README per Section 14. Make sure `cache/state.db`, `cache/pages/`, `cache/llm/`, and `outputs/` are committed so the reviewer can re-run for free."

**Step 8 — Handelsregister (only if time).**
> "Implement `sources/handelsregister.py` using OffeneRegister bulk data. If signal-to-noise is poor, document it as a known limitation in the README and disable in config by default."

---

## 16. Risk Register (things that can go wrong, and the mitigation)

| Risk | Mitigation |
|---|---|
| LLM hallucinates founder emails | Prompt explicitly forbids guessing; tests assert email format + presence in source markdown |
| Site blocks Jina (e.g. Cloudflare) | Auto-fallback to Firecrawl then Playwright |
| API spend overrun | `--max-spend` hard cap, cost logged per call |
| Reviewer can't get Anthropic key | All LLM responses are cached; re-run hits cache, no key needed |
| German legal sites are HTML soup | AI-native extraction is robust to layout changes |
| Source goes offline mid-run | Each collector wrapped in try/except, logs warning, continues |
| Same startup found 5 times across sources | Dedup at canonical_id, merge sources list (this is a feature, not a bug) |
| Top results are not actually early-stage | Scoring weight on `earliness` is 0.25; tune by inspecting top-20 manually |

---

## 17. Appendix: Estimated Cost per Full Run

| Stage | Calls | Model | Est. cost |
|---|---|---|---|
| HN filter | ~300 | Haiku | $0.20 |
| University extraction | ~5 pages | Sonnet | $0.10 |
| Enrichment (extract) | ~50 startups × 1 call | Sonnet | $5–7 |
| Scoring | ~50 × 1 call | Sonnet | $2–3 |
| Dedup pairwise | ~30 pairs | Haiku | $0.05 |
| Firecrawl fallback | ~20 pages | Firecrawl | $0.20 |
| **Total** | | | **≈ $8–11** |

Comfortably under the $15–20 cap. Second run with full cache: < $0.10 (only new sources/leads).

---

## 18. Definition of Done

- [ ] `sourcer doctor` passes on a fresh checkout (after `uv sync` + `.env`)
- [ ] `sourcer run-all --max-spend 20` completes without error
- [ ] `outputs/leads.csv` has ≥ 30 rows
- [ ] `outputs/onepagers/` has at least 10 one-pagers in **German**
- [ ] At least one entry from each enabled source appears in the output
- [ ] `outputs/run_summary.md` is generated and readable
- [ ] README covers: what / why / how to install / how to re-run / GDPR / limitations
- [ ] Reviewer can `git clone && uv sync && sourcer export` and get the same CSV without any API key (cache-replay)
- [ ] Repo committed cleanly, no secrets, `.env.example` provided
- [ ] Ship as ZIP **and** GitHub repo (URL in submission email)
