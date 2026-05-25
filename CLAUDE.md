# HTGF Sourcer — Working Memory

Source of truth: `PLAN.md` (sections referenced below as §N). This file is the compressed map; consult `PLAN.md` for full specs, prompts, and rationale.

**Status:** all 7 build steps shipped. 77 mocked tests pass in < 2s. README is the reviewer-facing doc — keep this file as the AI-co-author orientation.

## Purpose

AI-native pipeline that surfaces pre-seed / seed Digital Tech startups in **DACH** before they hit Crunchbase / Dealroom. Discovers leads from 5+ early-signal sources, enriches via LLM, scores against HTGF's thesis, and outputs: ranked CSV/XLSX + per-startup one-pager (**German**) + live Google Sheet.

Edge = **time, not volume**. Fuse signals (EXIST grants, university TTOs, GitHub orgs, Show HN, Product Hunt, Beta List) that no single VC systematically combines.

## Locked Decisions (do not revisit without explicit user sign-off)

- **Sector:** Digital Tech (B2B SaaS, AI-native, dev tools). Pluggable via `config/htgf_thesis.yaml`.
- **Geography:** DACH primary; framework extensible.
- **Stage:** Pre-seed / seed, company ≤ 3 years old.
- **Budget cap:** $15–20 per full run. Enforced by `--max-spend`.
- **LLM:** Anthropic SDK direct, no LangChain. Sonnet 4.6 for extraction/scoring, Haiku 4.5 for dedup/filter.
- **Fetch chain:** Jina Reader (`r.jina.ai/<url>`, free) → Firecrawl → Playwright. In that order, no exceptions.
- **AI-native scraping:** No per-site CSS selectors. Markdown → LLM with Pydantic tool-use for extraction.
- **Outputs:** CSV + XLSX + Markdown one-pagers (German) + Google Sheets tab per run.
- **Idempotency:** Every stage resumable. `discover` dedups by domain; `enrich` skips records < 14 days fresh; `score` is cheap, always re-runs.
- **Cache contract:** All LLM calls go through `llm.cached_call` keyed by `sha256(model + prompt + schema)`. Reviewer re-run must be ~free.
- **Commit policy:** `cache/state.db`, `cache/pages/`, `cache/llm/`, and `outputs/` ARE committed. `.env` and private outputs are gitignored.
- **Privacy:** No LinkedIn profile scraping (ToS + GDPR). Founder emails only if explicitly on imprint/contact page — prompt forbids guessing.
- **Handelsregister:** Defer to stub in v1. If poor signal-to-noise, document as limitation.

## Tech Stack (§4)

- **Env:** `uv` + Python 3.11+
- **HTTP:** `httpx` (async) · **HTML:** `selectolax` · **JS fetch:** `playwright` (chromium, headless, fallback only)
- **LLM:** `anthropic` SDK · **Schemas:** `pydantic` v2 + tool-use
- **State:** stdlib `sqlite3` + `sqlmodel` ORM
- **CLI:** `typer` · **Logging:** `loguru` · **Console:** `rich`
- **Data:** `pandas` + `openpyxl` · **Sheets:** `gspread` + `google-auth`
- **Config:** `pyyaml` + `pydantic-settings` · **Retry:** `tenacity`
- **Test:** `pytest` + `pytest-recording` (VCR fixtures)
- **Lint:** `ruff` (only)

## File Structure (§3)

```
htgf-sourcer/
├── pyproject.toml                    # uv-managed (deps list in §4)
├── .env.example                      # API key placeholders
├── config/
│   ├── htgf_thesis.yaml              # anchors, score weights, hard filters
│   ├── universities.yaml             # TTO URLs (TUM, RWTH, KIT, TUB, Fraunhofer)
│   └── sources.yaml                  # enabled sources + rate limits
├── src/htgf_sourcer/
│   ├── cli.py                        # Typer entry point (§11)
│   ├── models.py                     # Pydantic (§5)
│   ├── db.py                         # SQLite schema (§10)
│   ├── fetch.py                      # Jina → Firecrawl → Playwright chain
│   ├── llm.py                        # Anthropic wrapper + cached_call
│   ├── sources/                      # Collector ABC + per-source modules
│   ├── enrich.py                     # §7
│   ├── score.py                      # §8
│   ├── dedup.py                      # §9: domain canon + Haiku pairwise
│   └── exporters/                    # csv_writer, markdown_onepager, google_sheets
├── prompts/                          # extract_startup, score_startup, dedup_check
├── cache/                            # pages/, llm/, state.db — all committed
├── tests/                            # pytest + fixtures/
├── outputs/                          # leads.csv/.xlsx, onepagers/, run_summary.md — committed
└── scripts/scrape_htgf_portfolio.py  # one-off anchor list builder
```

## Core Data Models (§5)

`RawLead` (collector output) → `EnrichedStartup` (LLM-extracted, canonical) → `Score` (LLM-scored, weighted overall).

- `canonical_id` = stable hash of normalized domain (lower, no `www.`, no trailing `/`, no `utm_*`).
- Score dims (1–5 each): `thesis_fit` · `team_quality` · `earliness` · `traction` · `contactability`. Weights in `config/htgf_thesis.yaml` (default: 0.35 / 0.20 / 0.25 / 0.15 / 0.05).
- Score `rationale` is **German**. Score weights are config-driven, NOT hardcoded.

## Sources (§6)

| # | Source | Key signal | Notes |
|---|---|---|---|
| 1 | EXIST grants | German federal grants, lightly tracked | Whitelist DACH digital-tech keywords (§6.1) |
| 2 | University TTOs | Spin-out announcements | AI-native: Jina → Sonnet structured extract |
| 3 | Handelsregister (OffeneRegister) | Newly-registered GmbHs | v1 stub; defer if noisy |
| 4 | GitHub | Trending repos + new orgs w/ DACH location | Needs `GITHUB_TOKEN`; 5k req/hr |
| 5 | Hacker News (Algolia) | Show HN last 90d | Haiku filter for DACH B2B/devtool |
| 6 | Product Hunt (GraphQL) | Recent launches with DACH makers | Needs `PRODUCT_HUNT_TOKEN` |
| 7 | Beta List | Pre-launch products | Jina → Sonnet extract |

Each implements `Collector` ABC: `async def collect(since) -> list[RawLead]`. Wrap each in try/except — one source failing must not abort the run.

## CLI Surface (§11)

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

Global flags: `--config` · `--dry-run` · `--no-sheets` · `--max-spend USD` · `--verbose`.

`--max-spend` is enforced inside `llm.cached_call` via module-level `set_max_spend()` and raises `BudgetExceeded` after the offending call's response is cached. CLI commands catch it and exit cleanly (code 3).

## Build Order (§15) — all shipped

1. ✅ Skeleton + models + `db.py` + CLI stubs + working `doctor` + pytest placeholder
2. ✅ `fetch.py` (Jina/Firecrawl/Playwright) + `llm.py` (`cached_call` + cost tracking) + mocked HTTP tests
3. ✅ HN end-to-end: `sources/hackernews.py` + `enrich.py`
4. ✅ Remaining collectors (exist / universities / github / producthunt / betalist) + handelsregister stub
5. ✅ `score.py` + `dedup.py` (Stage 1 auto-merge in enrich, Stage 2 Haiku pairwise as a CLI command)
6. ✅ Exporters (CSV / XLSX / German MD one-pagers / Sheets) + run_summary
7. ✅ `--max-spend` wired end-to-end · README per §14 · CLAUDE.md updated
8. ⏸ Handelsregister — deferred per §15 Step 8 / §6.3 (poor signal-to-noise without Northdata)

## Conventions

- **Determinism:** Same inputs + same cache = same outputs. Never introduce non-determinism into extraction/scoring without surfacing it.
- **Cache before compute:** Always check `fetch_cache` / `llm_cache` first. New code that calls Anthropic must go through `llm.cached_call`.
- **Pydantic everywhere at boundaries:** Collectors emit `RawLead`. Enrichers emit `EnrichedStartup`. Scorers emit `Score`. Use `model_json_schema()` to feed Anthropic tool-use — do not hand-write JSON schemas.
- **LLM prompts live in `prompts/`**, not inlined in `.py` files. Edit prompts there; load at call site.
- **German for user-facing copy** in one-pagers and score rationales. Code, logs, comments stay English.
- **Conservative extraction:** Prompts must instruct "leave null if unsure" and "never guess emails." Tests should assert.
- **Cost logging per call** in `llm_cache.cost_usd`. `sourcer status` surfaces cost-to-date.
- **No new dependencies** beyond the §4 list without user sign-off.
- **Tests are 100% mocked** — `httpx.MockTransport` for HTTP, fake LLM callables for Anthropic. `pytest-recording` is in deps for any future cassette-based tests. Never hit live APIs in CI.

## Definition of Done (§18 — checklist)

- `sourcer doctor` passes on fresh checkout post `uv sync` + `.env`
- `sourcer run-all --max-spend 20` completes clean
- `outputs/leads.csv` ≥ 30 rows · `outputs/onepagers/` ≥ 10 German one-pagers
- ≥ 1 entry from each enabled source in output
- `outputs/run_summary.md` generated
- README covers what / why / install / re-run / GDPR / limitations
- Reviewer can `git clone && uv sync && sourcer export` and get same CSV without API key (cache-replay)
- No secrets in repo · `.env.example` present
- Shipped as ZIP **and** GitHub repo

## Risks worth remembering (§16)

- LLM email hallucination → prompt forbids + test asserts presence in source markdown
- Cloudflare blocks Jina → auto-fallback to Firecrawl → Playwright
- Reviewer has no Anthropic key → cache replay must be complete
- Cross-source duplicates are a **feature**: merge `sources[]` and `source_urls[]`, keep the enriched record

## Gotchas learned the hard way

- **Never pass `detect_types=PARSE_DECLTYPES` to `sqlite3.connect`.** Python's legacy `convert_timestamp` adapter can't parse tz-aware ISO strings — explodes on `+00:00` with `ValueError: invalid literal for int(): '18+00'`. We store ISO strings and parse in Python via `datetime.fromisoformat()`, which handles both naive and tz-aware.
- **`model_copy(update=...)` bypasses validation** — `HttpUrl`-typed fields stay as `str`, then Pydantic warns on serialization. Use `model_validate(model_dump() | {...})` instead.

---
*Update this file when locked decisions change. PLAN.md is the spec; this is the working map.*
