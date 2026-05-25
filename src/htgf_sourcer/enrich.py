"""Enrichment pipeline: RawLead → fetch → LLM extract → EnrichedStartup (§7).

For each pending lead with a website:
1. Canonicalize the URL (normalize_url) and derive `canonical_id`.
2. Fetch landing + a small set of about / team / careers paths in parallel.
3. Concatenate the markdown, cap to MAX_CHARS, send to Sonnet 4.6 via the
   tool-use schema of `ExtractedStartup`.
4. Persist as `EnrichedStartup`, attaching the lead's source + URL.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from pydantic import ValidationError

from . import db
from .fetch import fetch as default_fetch
from .fetch import normalize_url
from .llm import SONNET, pydantic_tool
from .llm import cached_call as default_llm_call
from .models import EnrichedStartup, ExtractedStartup, RawLead, Source

ABOUT_PATHS = ["/about", "/about-us", "/team", "/ueber-uns", "/uber-uns", "/jobs", "/careers"]
STALE_DAYS = 14
MAX_CHARS = 80_000  # ≈ 20k tokens at 4 chars/token
PER_PAGE_CHAR_CAP = 8000

EXTRACT_PROMPT_PATH = Path("prompts/extract_startup.txt")
EXTRACT_TOOL_NAME = "record_startup"


# ---- public api -----------------------------------------------------------


async def enrich_pending(
    *,
    limit: int | None = None,
    db_path: Path = db.DEFAULT_DB_PATH,
    fetch_fn: Callable | None = None,
    llm_call: Callable | None = None,
    stale_days: int = STALE_DAYS,
) -> tuple[int, int]:
    """Enrich pending leads. Returns (succeeded, failed)."""
    fetch_fn = fetch_fn or default_fetch
    llm_call = llm_call or default_llm_call

    pending = _list_pending_leads(db_path=db_path, stale_days=stale_days, limit=limit)
    succeeded, failed = 0, 0
    for lead in pending:
        try:
            startup = await enrich_lead(
                lead, db_path=db_path, fetch_fn=fetch_fn, llm_call=llm_call
            )
        except Exception:
            startup = None
        if startup is None:
            failed += 1
        else:
            succeeded += 1
    return succeeded, failed


async def enrich_lead(
    lead: RawLead,
    *,
    db_path: Path = db.DEFAULT_DB_PATH,
    fetch_fn: Callable | None = None,
    llm_call: Callable | None = None,
) -> EnrichedStartup | None:
    fetch_fn = fetch_fn or default_fetch
    llm_call = llm_call or default_llm_call

    if not lead.website:
        return None

    canonical_url = normalize_url(str(lead.website))
    canonical_id = canonical_id_for(canonical_url)

    parsed = urlparse(canonical_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    landing_task = fetch_fn(canonical_url, db_path=db_path)
    about_tasks = [fetch_fn(f"{base}{p}", db_path=db_path) for p in ABOUT_PATHS]
    landing, *about_results = await asyncio.gather(
        landing_task, *about_tasks, return_exceptions=True
    )

    if isinstance(landing, Exception) or landing is None:
        return None

    sections = [_format_section("LANDING", canonical_url, landing.content)]
    fetched_urls: list[str] = [canonical_url]
    for path, result in zip(ABOUT_PATHS, about_results, strict=True):
        if isinstance(result, Exception) or result is None:
            continue
        url = f"{base}{path}"
        sections.append(_format_section(path.upper().lstrip("/"), url, result.content))
        fetched_urls.append(url)

    body = "\n\n---\n\n".join(sections)[:MAX_CHARS]
    prompt = _load_extract_prompt() + "\n\nCONTENT:\n\n" + body
    tool = pydantic_tool(
        ExtractedStartup,
        EXTRACT_TOOL_NAME,
        "Extract structured startup data from concatenated website content.",
    )

    try:
        raw = llm_call(prompt, tool, model=SONNET, db_path=db_path)
    except Exception:
        return None

    try:
        extracted = ExtractedStartup.model_validate(raw)
    except ValidationError:
        return None

    startup = EnrichedStartup(
        canonical_id=canonical_id,
        sources=[lead.source],
        source_urls=fetched_urls,  # Pydantic coerces strings to HttpUrl
        last_enriched=datetime.utcnow(),
        **extracted.model_dump(),
    )

    # Stage 1 dedup: if this canonical_id was already enriched by another
    # lead/source, merge the sources + source_urls instead of overwriting.
    from . import dedup as _dedup
    startup = _dedup.merge_with_existing(startup, db_path=db_path)

    with db.connect(db_path) as conn:
        db.upsert_enriched(conn, startup)

    return startup


def canonical_id_for(canonical_url: str) -> str:
    """Stable 64-hex id derived from the normalized URL."""
    return hashlib.sha256(canonical_url.encode()).hexdigest()


# ---- pending-lead query --------------------------------------------------


def _list_pending_leads(
    *, db_path: Path, stale_days: int, limit: int | None
) -> list[RawLead]:
    """Leads with a website, not yet enriched (or enriched > stale_days ago)."""
    cutoff = datetime.utcnow() - timedelta(days=stale_days)
    pending: list[RawLead] = []
    with db.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT source, source_id, name, website, one_liner,
                   discovered_at, raw_payload
            FROM leads
            WHERE website IS NOT NULL AND website != ''
            ORDER BY discovered_at DESC
            """
        ).fetchall()
        for row in rows:
            canonical_url = normalize_url(row["website"])
            cid = canonical_id_for(canonical_url)
            existing = conn.execute(
                "SELECT last_enriched FROM enriched_startups WHERE canonical_id=?",
                (cid,),
            ).fetchone()
            if existing is not None:
                last = _parse_ts(existing["last_enriched"])
                if last is not None and last > cutoff:
                    continue
            try:
                lead = _row_to_lead(row)
            except ValidationError:
                continue
            pending.append(lead)
            if limit is not None and len(pending) >= limit:
                break
    return pending


def _row_to_lead(row: sqlite3.Row) -> RawLead:
    payload = {}
    raw = row["raw_payload"]
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
    return RawLead(
        source=Source(row["source"]),
        source_id=row["source_id"],
        name=row["name"],
        website=row["website"],
        one_liner=row["one_liner"],
        discovered_at=_parse_ts(row["discovered_at"]) or datetime.utcnow(),
        raw_payload=payload,
    )


def _parse_ts(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


# ---- helpers -------------------------------------------------------------


def _format_section(label: str, url: str, content: str) -> str:
    body = content.strip()
    if len(body) > PER_PAGE_CHAR_CAP:
        body = body[:PER_PAGE_CHAR_CAP] + "\n…[truncated]"
    return f"# {label}\nURL: {url}\n\n{body}"


def _load_extract_prompt() -> str:
    return EXTRACT_PROMPT_PATH.read_text()
