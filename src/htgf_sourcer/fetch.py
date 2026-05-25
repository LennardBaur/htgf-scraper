"""URL fetching with the Jina → Firecrawl → Playwright fallback chain (§7).

Every successful fetch writes:
- `cache/pages/<sha256(url)>.md`           (content as markdown / text)
- `cache/pages/<sha256(url)>.meta.json`    (url, fetcher, fetched_at, status)
- a row in the `fetch_cache` SQLite table

Subsequent calls with the same URL return the cached content without hitting
the network.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx

from . import db

PAGES_DIR = Path("cache/pages")
JINA_PREFIX = "https://r.jina.ai/"
FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
USER_AGENT = "htgf-sourcer/0.1 (+https://github.com/htgf)"


# ---- result type ----------------------------------------------------------


@dataclass(frozen=True)
class FetchResult:
    url: str
    content: str
    fetcher: str  # "jina" | "firecrawl" | "playwright" | "cache"
    fetched_at: datetime


# ---- public api -----------------------------------------------------------


async def fetch(
    url: str,
    *,
    force_refresh: bool = False,
    db_path: Path = db.DEFAULT_DB_PATH,
    pages_dir: Path = PAGES_DIR,
) -> FetchResult | None:
    """Fetch `url` through the chain. Returns None if all fetchers fail."""
    canonical = normalize_url(url)
    url_hash = hashlib.sha256(canonical.encode()).hexdigest()

    if not force_refresh:
        hit = _read_cache(url_hash, db_path, pages_dir)
        if hit is not None:
            return hit

    content: str | None = None
    fetcher: str | None = None

    for name, runner in (
        ("jina", _fetch_jina),
        ("firecrawl", _fetch_firecrawl),
        ("playwright", _fetch_playwright),
    ):
        try:
            result = await runner(canonical)
        except Exception:
            result = None
        if result:
            content, fetcher = result, name
            break

    if not content or not fetcher:
        return None

    fetched_at = datetime.utcnow()
    _write_cache(
        url_hash=url_hash,
        url=canonical,
        content=content,
        fetcher=fetcher,
        fetched_at=fetched_at,
        db_path=db_path,
        pages_dir=pages_dir,
    )
    return FetchResult(url=canonical, content=content, fetcher=fetcher, fetched_at=fetched_at)


def normalize_url(url: str) -> str:
    """Lower-case scheme/host, strip `www.`, drop `utm_*` params, strip trailing slash."""
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    # drop utm_* params
    params = [p for p in parsed.query.split("&") if p and not p.startswith("utm_")]
    query = "&".join(params)
    path = (parsed.path or "").rstrip("/")
    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


# ---- individual fetchers --------------------------------------------------


async def _fetch_jina(url: str) -> str | None:
    """Jina Reader. Free, returns clean markdown. Best path."""
    target = JINA_PREFIX + url
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT}) as c:
        r = await c.get(target)
    if r.status_code != 200:
        return None
    text = r.text.strip()
    return text or None


async def _fetch_firecrawl(url: str) -> str | None:
    """Firecrawl scrape endpoint. Requires FIRECRAWL_API_KEY; skipped otherwise."""
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return None
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"url": url, "formats": ["markdown"]}
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers) as c:
        r = await c.post(FIRECRAWL_ENDPOINT, json=payload)
    if r.status_code != 200:
        return None
    data = r.json()
    md = (data.get("data") or {}).get("markdown") or ""
    return md.strip() or None


async def _fetch_playwright(url: str) -> str | None:
    """Headless chromium fallback. Returns plain text extracted from <body>."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent=USER_AGENT)
                await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                html = await page.content()
            finally:
                await browser.close()
    except Exception:
        return None

    return _html_to_text(html) or None


# ---- helpers --------------------------------------------------------------


def _html_to_text(html: str) -> str:
    """Strip scripts/styles, return body text. Fallback path; quality is OK."""
    try:
        from selectolax.parser import HTMLParser
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html)

    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript"):
        tag.decompose()
    body = tree.body
    if body is None:
        return ""
    return body.text(separator="\n", strip=True)


def _read_cache(url_hash: str, db_path: Path, pages_dir: Path) -> FetchResult | None:
    """Return a FetchResult from disk if both the DB row and file exist."""
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT url, content_path, fetched_at, fetcher FROM fetch_cache WHERE url_hash=?",
            (url_hash,),
        ).fetchone()
    if row is None:
        return None
    content_file = pages_dir / row["content_path"]
    if not content_file.exists():
        return None
    return FetchResult(
        url=row["url"],
        content=content_file.read_text(),
        fetcher="cache",
        fetched_at=_parse_ts(row["fetched_at"]),
    )


def _write_cache(
    *,
    url_hash: str,
    url: str,
    content: str,
    fetcher: str,
    fetched_at: datetime,
    db_path: Path,
    pages_dir: Path,
) -> None:
    pages_dir.mkdir(parents=True, exist_ok=True)
    md_path = pages_dir / f"{url_hash}.md"
    meta_path = pages_dir / f"{url_hash}.meta.json"
    md_path.write_text(content)
    meta_path.write_text(
        json.dumps(
            {"url": url, "fetcher": fetcher, "fetched_at": fetched_at.isoformat()},
            indent=2,
        )
    )
    with db.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fetch_cache (url_hash, url, content_path, fetched_at, fetcher)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(url_hash) DO UPDATE SET
                fetched_at=excluded.fetched_at,
                fetcher=excluded.fetcher,
                content_path=excluded.content_path
            """,
            (url_hash, url, md_path.name, fetched_at, fetcher),
        )


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.utcnow()


# ---- convenience sync wrapper --------------------------------------------


def fetch_sync(url: str, **kwargs) -> FetchResult | None:
    """Synchronous wrapper for use from non-async contexts (CLI, tests)."""
    return asyncio.run(fetch(url, **kwargs))
