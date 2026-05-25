# HTGF Early-Stage Sourcing Tool

An AI-native pipeline that surfaces **pre-seed / seed Digital Tech startups in DACH** before they appear on Crunchbase or Dealroom. It pulls leads from five early-signal sources, enriches each with website + LLM extraction, scores them against HTGF's published thesis, and produces a ranked CSV, a German one-pager per startup, and a live Google Sheet.

**Why this works:** Crunchbase, Dealroom and PitchBook are reactive — they list a startup after a round is announced. The signals that surface *intent to build* or *early traction* before any round closes (EXIST grants, university TTOs, GitHub orgs with DACH footprint, Show HN, Beta List) are public but rarely fused systematically by a single VC. This tool fuses them.

---

## TL;DR for the reviewer

1. Open **`outputs/leads.xlsx`** — ranked list, frozen header, one row per startup.
2. Read **`outputs/run_summary.md`** — counts, cost, top-5 with links.
3. Open 2–3 files in **`outputs/onepagers/`** — German one-pagers with rationale, founders, sources.
4. (Optional) Open the linked Google Sheet — same data, dated tab per run.

To regenerate the outputs from the committed cache without any API key:

```bash
uv sync
uv run sourcer export
```

That is the cache-replay path. No network. No spend.

---

## How it works

Three idempotent stages, each producing inspectable artifacts:

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
```

- **Discover** runs every enabled collector and persists `RawLead` rows.
- **Enrich** picks pending leads (no enriched row, or stale > 14 days), fetches the landing page + a small set of about / team paths in parallel, then asks Claude Sonnet 4.6 to extract a structured `EnrichedStartup` via Anthropic tool-use. Same-domain duplicates merge their `sources` list.
- **Score** prompts Sonnet 4.6 with HTGF's thesis + five real anchor portfolio companies, gets 1–5 scores on five dimensions, computes the weighted `overall`, and writes a `Score` row.
- **Dedup** (optional) runs a Haiku pairwise check on websiteless leads (EXIST entries, early university spin-outs) against existing enriched startups using a fuzzy-name shortlist to keep LLM cost low.
- **Export** joins everything, ranks by `overall`, and writes CSV + XLSX + per-startup Markdown + run summary, then optionally pushes to Google Sheets.

Every fetch and every LLM call is **cached on disk** (`cache/state.db`, `cache/pages/`). Re-running any stage hits the cache. That's what lets the reviewer replay the pipeline for free.

---

## Sources used and why

| Source | Status | What it gives us | Why it's early-signal |
|---|---|---|---|
| **Hacker News (Show HN)** | **enabled** | Founder-posted launches in last 90 days | Strong intent signal; founders self-identify. Haiku pre-filter for DACH B2B / dev-tool. |
| **GitHub** | **enabled** | DACH-located developers' recent public repos | "Building in public" signal — code often exists before a funding round. Searches users by `location:Germany / Austria / Switzerland / Berlin / Munich / Vienna / Zurich`, then lists their non-fork repos. |
| **Product Hunt** | **enabled** | Recent launches with ≥10 upvotes in last 90 days | Pre- or just-post-launch signal. **No DACH pre-filter** — the v2 API hides external website URLs behind a JS-only redirect, so we collect globally and rely on the HTGF scoring prompt to penalize non-DACH startups via `thesis_fit`. Lead `website` points at the PH product page (`/products/SLUG`) so enrichment can extract real content. |
| EXIST grants | wired, disabled by default | Federal grants for academic founders, listed publicly | Funded *before* incorporation; lightly tracked by VCs. **Live page drifted** — actual project rows moved off the index page. Re-enable once a per-program crawler is written. |
| University TTOs (TUM, RWTH, KIT, TU Berlin, Fraunhofer) | wired, disabled by default | Spin-out announcements from tech-transfer offices | Same drift problem: TUM and RWTH URLs currently 404, and the surviving TTO pages mostly describe programs, not specific spin-outs. |
| Beta List | wired, disabled by default | Pre-launch "upcoming" products | The `/markets/germany` page is a category index ("AI", "Commerce"), not a list of startups. Needs a different ingestion path. |
| Handelsregister | stub (deferred) | Newly-registered GmbHs | OffeneRegister "purpose" field is too sparse for v1; revisit with Northdata in v2. |

Disabled sources are wired in code (`src/htgf_sourcer/sources/*.py`) and tested — toggle in `config/sources.yaml` to experiment. The decision to disable them by default is documented inline in that file.

---

## AI-native choices

- **Jina Reader → Firecrawl → Playwright** for fetching. Jina returns clean markdown for ~80% of URLs at zero cost. Firecrawl is the paid fallback. Playwright is the last-resort Cloudflare bypass. **Zero per-site CSS selectors anywhere in the codebase.**
- **Claude Sonnet 4.6 with Pydantic-driven tool-use** for extraction (`EnrichedStartup`) and scoring (`ExtractedScore`). The JSON tool schema is `model.model_json_schema()` — change a Pydantic field, the LLM contract follows.
- **Claude Haiku 4.5** for cheap pairwise dedup (`judge_match`) and the Hacker News pre-filter (`classify_post`).
- **HTGF anchors baked into the scoring prompt** — five real portfolio companies (Zeeg, Stackgini, Pactos, syte, Data Virtuality) plus four explicit negative anchors. Bias toward HTGF's actual investment style rather than generic "B2B SaaS".
- **Every LLM call is request-hashed and cached.** Re-runs are deterministic and free. Prompt-iteration changes the hash → fresh call → caches the new response. This is why the reviewer can replay the whole pipeline without an API key.

---

## Setup

Requirements: macOS or Linux, [`uv`](https://docs.astral.sh/uv/), Python 3.11+. No Conda, no virtualenv to manage by hand — `uv` does both.

```bash
# Install uv if you don't have it
brew install uv               # macOS
# or: curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project deps + dev extras (creates .venv/ for you)
uv sync --extra dev

# Copy the env template and fill in your keys
cp .env.example .env
# At minimum, set:
#   ANTHROPIC_API_KEY=sk-ant-...
# Recommended (sources degrade gracefully without them):
#   GITHUB_TOKEN=...
#   PRODUCT_HUNT_TOKEN=...
#   FIRECRAWL_API_KEY=...
# Optional (Google Sheets export; skip with --no-sheets):
#   GOOGLE_SA_PATH=~/.config/htgf-sourcer/sa.json
#   GOOGLE_SHEET_ID=...

# (Optional) install the Chromium binary if you want the Playwright fallback
uv run playwright install chromium

# Sanity-check the environment
uv run sourcer doctor
```

`doctor` prints a table of pass / warn / fail checks. If `ANTHROPIC_API_KEY` is missing it exits non-zero; the rest are recommendations.

---

## Usage

```bash
sourcer discover [--source X] [--limit N]    # run one or all enabled collectors
sourcer enrich [--limit N]                   # fetch + LLM extract pending leads
sourcer dedup [--limit N]                    # Haiku pairwise match websiteless leads
sourcer score [--limit N]                    # score enriched startups against HTGF thesis
sourcer export [--top-n N]                   # write CSV / XLSX / one-pagers / Sheets
sourcer run-all [--discover-limit N] [--enrich-limit N] [--score-limit N] [--skip-dedup]
sourcer status                                # leads / enriched / scored counts + LLM cost
sourcer doctor                                # env + tool checks
```

Global flags (these go **before** the subcommand name — Typer convention):

- `--max-spend USD` — hard cap on cumulative LLM cost (default 20). Aborts mid-run with a clean message if exceeded.
- `--no-sheets` — skip the Google Sheets push.
- `--dry-run`, `--config`, `--verbose` — reserved.

Typical first run (cold cache, ~15 leads per source, ~$3–6, ~15 min):

```bash
uv run sourcer --max-spend 8 run-all --discover-limit 15 --enrich-limit 20 --score-limit 20
```

Once the cache is warm, the same command re-executes in seconds at ~$0.

To run a single collector (useful for incremental top-ups or debugging):

```bash
uv run sourcer discover --source exist --limit 5
uv run sourcer discover --source universities --limit 5
# ... known sources: hackernews, exist, universities, github, producthunt, betalist
```

Running `discover` with no `--source` runs every collector enabled in `config/sources.yaml`.

---

## Project structure

```
htgf-sourcer/
├── PLAN.md                          # full design (the source of truth)
├── CLAUDE.md                        # working map for AI co-authors
├── README.md                        # this file
├── pyproject.toml                   # uv-managed
├── .env.example                     # API-key placeholders (real .env is gitignored)
├── config/
│   ├── htgf_thesis.yaml             # score weights + anchors
│   ├── universities.yaml            # TTO URLs
│   └── sources.yaml                 # which sources are enabled
├── prompts/
│   ├── extract_startup.txt          # Sonnet extraction prompt
│   ├── extract_listing.txt          # Sonnet listing-page extraction
│   ├── score_startup.txt            # Sonnet scoring prompt (anchors baked in)
│   ├── hn_filter.txt                # Haiku HN filter
│   └── dedup_check.txt              # Haiku pairwise dedup
├── src/htgf_sourcer/
│   ├── cli.py                       # Typer entrypoint
│   ├── models.py                    # Pydantic: RawLead, EnrichedStartup, Score, ...
│   ├── db.py                        # SQLite schema + helpers
│   ├── fetch.py                     # Jina → Firecrawl → Playwright chain
│   ├── llm.py                       # cached_call + cost tracking + --max-spend
│   ├── enrich.py                    # enrichment pipeline
│   ├── dedup.py                     # two-stage dedup
│   ├── score.py                     # LLM scoring
│   ├── export.py                    # row assembly + run summary
│   ├── sources/                     # one module per collector
│   └── exporters/                   # csv_writer, markdown_onepager, google_sheets
├── cache/                           # COMMITTED — state.db + per-URL markdown + LLM cache
├── outputs/                         # COMMITTED — leads.csv/xlsx, onepagers/, run_summary.md
└── tests/                           # pytest, mocked HTTP + LLM; 77 tests, ~1 sec
```

---

## How the reviewer can re-run

The cache is committed. No API keys needed:

```bash
git clone <repo>
cd htgf-sourcer
uv sync
uv run sourcer export       # regenerates outputs/ from the cached DB
```

To re-execute the full pipeline (still ~free because of the LLM cache):

```bash
cp .env.example .env        # set ANTHROPIC_API_KEY if you want to *extend* the dataset
uv run sourcer run-all --max-spend 20
```

The second run picks up where the first left off (incremental discover, skip-fresh enrichment) and the cache makes any work that was already done free.

---

## Limitations & GDPR notes

- **No LinkedIn profile scraping.** ToS + GDPR risk. We only surface LinkedIn URLs that are explicitly linked from a company's own site (e.g. the team page).
- **Founder emails are not guessed.** The extraction prompt forbids inference. We only include emails that are explicitly printed on the company's Impressum / contact page. Legal basis for processing those: Art. 6(1)(f) (legitimate interest of HTGF in evaluating investment opportunities).
- **Twitter/X dropped** — API cost prohibitive for this scope.
- **Handelsregister source** is a stub in v1. OffeneRegister's bulk data is messy and the `purpose` field is sparse, so signal-to-noise is poor. Re-evaluate with Northdata API for a paid v2.
- **GitHub DACH detection** uses GitHub's user-search with `location:Germany|Austria|Switzerland|Berlin|Munich|Vienna|Zurich`, then lists each user's recent original repos (no forks, no archives, stars ≥ 10). This yields real DACH developer projects. The earlier v1 strategy (search repos, filter by homepage TLD) rejected ~100% of real DACH startups because they use `.com`/`.ai`/`.io`/`.dev` for international markets — see commit history.
- **Source list is configurable.** Adding a new sector or geography is a config change (`config/htgf_thesis.yaml`, `config/sources.yaml`, `config/universities.yaml`) and a new `Collector` subclass — no schema changes.
- **Score `overall` is deterministic given the dimension scores.** Weights live in `config/htgf_thesis.yaml` and can be re-tuned without re-prompting the LLM (`sourcer score` is free against the cache).

---

## Next steps if this becomes a real tool

- Slack / email notification on new high-scoring leads above a configurable threshold.
- Daily cron via GitHub Actions, writing to the same SQLite + Sheets.
- LinkedIn enrichment via Proxycurl (paid, but high signal for the `contactability` dimension).
- Northdata API for proper Handelsregister depth.
- Embedding-based dedup at scale (Sentence Transformers + cosine, then Haiku only on the borderline cases).
- Per-analyst CRM-style "claim" workflow so two analysts don't double-track the same deal.
- Streamlit / Next.js dashboard reading from the same SQLite for non-CLI analysts.

---

*Built as a take-home assignment. Full design rationale in [`PLAN.md`](PLAN.md); architectural decisions and conventions live in [`CLAUDE.md`](CLAUDE.md). 77 tests, all mocked, run in under 2 seconds.*
