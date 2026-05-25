# HTGF Sourcer — Working Memory

`PLAN.md` is the **original design intent** (handed over before any code was
written). This file is the **current ship state** — what actually got built,
what got disabled, and what diverged from the plan. When generating new docs
(e.g. a README), prefer this file for "what exists today" and PLAN.md for
"why the design looks this way."

**Status (2026-05-25):** 80 mocked tests pass in ~1.2s, ruff clean, end-to-end
pipeline produced 46 enriched + scored startups across 3 enabled sources at a
total cost of $2.86. Reviewer cache-replay path verified.

## Ship state vs PLAN.md

PLAN.md proposed 7 sources. **3 ship enabled, 4 are disabled-by-default**
(wired and tested, but live endpoints either drifted or block cheap geography
filtering). See `config/sources.yaml` for the per-source toggle and inline
reason.

| Source | Plan | Ship |
|---|---|---|
| Hacker News | DACH B2B/devtool Haiku filter | ✅ as planned |
| GitHub | Repo-search + `.de/.at/.ch` homepage filter | **Rewritten:** user-search by `location:Germany/Berlin/Munich/Austria/Vienna/Switzerland/Zurich`, then list their non-fork repos. The plan's TLD filter rejected ~100% of real DACH startups (they use `.com/.ai/.io/.dev` for international markets). |
| Product Hunt | GraphQL + DACH maker/website filter | **Pivoted:** global, no DACH filter (PH v2 API hides external URLs behind a JS redirect; maker locations are null). Lead `website` points at `/products/SLUG` (fetchable) instead of `/r/HASHCODE` (JS redirect). |
| EXIST grants | AI-native extraction from index page | **Disabled.** Live page drifted into a marketing landing page; project rows moved to per-program sub-pages. |
| University TTOs | AI-native extraction from spinoff pages | **Disabled.** TUM/RWTH URLs return 404; surviving pages describe programs, not specific spin-outs. |
| Beta List | AI-native extraction from markets/germany | **Disabled.** `/markets/germany` is a category index ("AI", "Commerce"), not a list of startups. |
| Handelsregister | OffeneRegister bulk import | Stub (deferred per PLAN.md §6.3 / §15 Step 8 — sparse `purpose` field). |

Other notable differences from the plan:
- `dedup` is a separate CLI command (not auto-run inside `score` or `enrich`).
- `--max-spend` is enforced inside `llm.cached_call` via a module-level cap
  (`set_max_spend(usd)`); it raises `BudgetExceeded` after the offending call
  is cached so the cap-hit response isn't lost. CLI catches it cleanly (exit 3).
- `ExtractedScore` and `ExtractedStartup` are LLM-extraction-only subset models
  so the orchestrator owns `canonical_id`, `sources`, `source_urls`,
  `last_enriched`, and the weighted `overall`.

## Locked Decisions

- **Sector:** Digital Tech (B2B SaaS, AI-native, dev tools). Pluggable via `config/htgf_thesis.yaml`.
- **Geography:** HTGF thesis = DACH only (hard constraint per PLAN.md §1). But **PH discovery is global** by design — we rely on the scoring prompt to penalize non-DACH startups via `thesis_fit` rather than filter at discover.
- **Stage:** Pre-seed / seed, company ≤ 3 years old.
- **Budget cap:** Default $20 via `--max-spend`. Enforced live.
- **LLM:** Anthropic SDK direct, no LangChain. Sonnet 4.6 (`claude-sonnet-4-6`) for extraction + scoring; Haiku 4.5 (`claude-haiku-4-5-20251001`) for HN classifier + pairwise dedup.
- **Fetch chain:** Jina Reader (free) → Firecrawl (paid fallback) → Playwright (last resort). In that order.
- **AI-native scraping:** Zero per-site CSS selectors. Markdown → LLM with Pydantic-driven tool-use for extraction.
- **Outputs:** CSV + XLSX (frozen header, bold row 1, frozen rank column) + Markdown one-pagers in **German** + per-run dated Google Sheets tab.
- **Idempotency:** `discover` upserts by `(source, source_id)`; `enrich` skips records enriched < 14 days ago; `score` is free against cache (prompt-hashed).
- **Cache contract:** Every fetch + every LLM call is hashed and cached. `cache/state.db`, `cache/pages/`, `cache/llm/`, and `outputs/` ARE committed so reviewers can replay at $0.
- **Privacy:** No LinkedIn profile scraping. Founder emails only if explicitly on imprint/contact page — prompt forbids guessing; tests assert.

## Tech Stack

`uv` + Python 3.11+ · `httpx` async · `selectolax` (HTML→text) · `playwright` chromium (fallback) · `anthropic` SDK · `pydantic` v2 + tool-use · stdlib `sqlite3` + `sqlmodel` · `typer` · `loguru` · `rich` · `pandas` + `openpyxl` · `gspread` + `google-auth` · `pyyaml` + `pydantic-settings` · `tenacity` · `pytest` + `pytest-recording` · `ruff`.

## File Structure

```
htgf-sourcer/
├── PLAN.md / CLAUDE.md / README.md
├── pyproject.toml · .python-version · .env.example · .gitignore
├── config/
│   ├── htgf_thesis.yaml      # score weights + anchors (kept in sync with prompt)
│   ├── universities.yaml     # TTO URLs (collector currently disabled)
│   └── sources.yaml          # enabled/disabled per source + inline reasons
├── prompts/
│   ├── extract_startup.txt   # Sonnet: per-startup landing-page extraction
│   ├── extract_listing.txt   # Sonnet: listing-page extraction (used by exist/uni/betalist when enabled)
│   ├── score_startup.txt     # Sonnet: HTGF scoring with anchors
│   ├── hn_filter.txt         # Haiku: Show HN DACH B2B/devtool classifier
│   └── dedup_check.txt       # Haiku: pairwise A/B match
├── src/htgf_sourcer/
│   ├── cli.py                # Typer entry; collector registry; --max-spend
│   ├── models.py             # RawLead, Founder, EnrichedStartup, ExtractedStartup, Score, ExtractedScore
│   ├── db.py                 # SQLite schema + helpers
│   ├── fetch.py              # Jina → Firecrawl → Playwright + cache writeback
│   ├── llm.py                # cached_call + BudgetExceeded + cost ledger
│   ├── enrich.py             # pipeline + Stage-1 dedup transparent merge
│   ├── dedup.py              # Stage-1 + Stage-2 (Haiku pairwise)
│   ├── score.py              # iterates enriched, computes weighted overall
│   ├── export.py             # row assembly + run_summary
│   ├── sources/              # base.py + 7 source modules (hackernews, github, producthunt, exist, universities, betalist, handelsregister) + _ai_listing.py helper
│   └── exporters/            # csv_writer, markdown_onepager, google_sheets
├── cache/                    # state.db + pages/ + llm/ — COMMITTED
├── outputs/                  # leads.csv/.xlsx + onepagers/ + run_summary.md — COMMITTED
└── tests/                    # 80 mocked tests; ~1.2s; no network
```

## Core Data Models

`RawLead` → `EnrichedStartup` → `Score`. Plus extraction-only subsets:
- `ExtractedStartup` — LLM returns this from `record_startup` tool. Orchestrator adds `canonical_id`, `sources`, `source_urls`, `last_enriched`.
- `ExtractedScore` — LLM returns 5 dim scores (1–5) + German `rationale` + `red_flags`. Orchestrator computes `overall` from weights and stamps `canonical_id` + `scored_at`.

`canonical_id` = sha256 of normalized domain (lower-case host, no `www.`, no trailing `/`, drop `utm_*` params). The whole-URL-equivalence-class hash.

Score weights live in `config/htgf_thesis.yaml`. Default: thesis_fit 0.35 · team_quality 0.20 · earliness 0.25 · traction 0.15 · contactability 0.05.

## CLI Surface

```
sourcer discover [--source X] [--limit N]
sourcer enrich [--limit N]
sourcer dedup [--limit N]
sourcer score [--limit N]
sourcer export [--top-n N]
sourcer run-all [--discover-limit N] [--enrich-limit N] [--score-limit N] [--skip-dedup]
sourcer status
sourcer doctor
```

Global flags (go **before** the subcommand — Typer convention): `--config` · `--dry-run` · `--no-sheets` · `--max-spend USD` · `--verbose`.

## Conventions

- **Determinism:** Same inputs + same cache = same outputs.
- **Cache before compute:** Always check `fetch_cache` / `llm_cache` first. Every Anthropic call goes through `llm.cached_call`.
- **Pydantic at boundaries:** `model_json_schema()` feeds Anthropic tool-use; do not hand-write JSON schemas.
- **Prompts live in `prompts/`** — not inlined in `.py`. One-pager template is a Python f-string (output format, not LLM input).
- **German for user-facing copy** (one-pagers, score rationales). Code/logs/comments stay English.
- **Conservative extraction:** Prompts instruct "leave null if unsure" and "never guess emails."
- **Cost logging per call** in `llm_cache.cost_usd`. `sourcer status` aggregates.
- **No new dependencies** beyond the original §4 list without explicit sign-off.
- **Tests are 100% mocked** — `httpx.MockTransport` for HTTP, fake LLM callables for Anthropic. `pytest-recording` is in deps but unused so far.

## Definition of Done — verified

- ✅ `sourcer doctor` passes (all checks green when `.env` is set)
- ✅ `sourcer run-all` completes; `--max-spend` enforced
- ✅ `outputs/leads.csv` = 46 rows; `outputs/onepagers/` = 46 German files
- ✅ ≥ 1 entry per enabled source (HN: 26, PH: 15, GitHub: 5)
- ✅ `outputs/run_summary.md` generated
- ✅ README covers what / why / install / re-run / GDPR / limitations
- ✅ Cache replay path tested
- ✅ No secrets in repo · `.env.example` present
- ⏸ ZIP + GitHub repo — user to handle

## Gotchas learned the hard way

- **Never pass `detect_types=PARSE_DECLTYPES` to `sqlite3.connect`.** Python's legacy `convert_timestamp` adapter can't parse tz-aware ISO strings — explodes on `+00:00` with `ValueError: invalid literal for int(): '18+00'`. We store ISO strings and parse via `datetime.fromisoformat()` in `_parse_ts()` helpers.
- **`model_copy(update=...)` bypasses validation** — `HttpUrl`-typed fields stay as `str`, then Pydantic warns on serialization. Use `EnrichedStartup.model_validate(payload | {...})` instead.
- **GitHub TLD filter is a trap.** Real DACH startups use `.com/.ai/.io/.dev` for international markets, not `.de`. The plan's "search repos, filter by homepage TLD" approach yielded zero. Pivot: search USERS by `location:Germany|Berlin|Munich|...`, then list their recent repos. That gives real DACH developer projects.
- **Product Hunt v2 API hides external URLs.** `node.website` is `producthunt.com/r/HASHCODE`, which redirects via JavaScript — httpx can't follow it. Use `node.url` (`/products/SLUG`) as the lead website; that page is fetchable and contains a "Visit Website" link plus product info.
- **Listing-page sources drift fast.** EXIST's index page is now a marketing landing page; TUM/RWTH/Beta List similar. Disabling beats burning LLM budget on empty extractions. The `_ai_listing.py` helper still works — just point it at pages that actually contain entries.

## Cost ledger (2026-05-25)

Real numbers from the shipped run:
- HN discover (with Haiku filter): ~$0.05 per 10 posts
- Enrich (Sonnet, includes parallel landing + about fetch): ~$0.05–0.10 per startup
- Score (Sonnet against HTGF anchors): ~$0.02 per startup
- Dedup Stage 2 (Haiku pairwise): ~$0.001 per pair, only invoked on fuzzy-name shortlist
- Full pipeline at 46 leads: **$2.86 total**

---
*Single source of truth for current state. PLAN.md = original intent; this = ship.*
