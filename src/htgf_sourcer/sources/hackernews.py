"""Hacker News collector — Algolia HN Search for Show HN posts (§6.5).

Pipeline:
1. Page through Algolia for tags=show_hn from `since` to now.
2. For each hit with a URL, fetch a short excerpt via the fetch chain.
3. Run a Haiku yes/no/unsure classifier (DACH B2B SaaS / dev tool?).
4. Keep "yes" + "unsure" → RawLead. Drop "no".

The HTTP client and the LLM call are injectable so tests can run offline.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from pydantic import ValidationError

from ..fetch import fetch as default_fetch
from ..llm import HAIKU
from ..llm import cached_call as default_llm_call
from ..models import RawLead, Source
from .base import Collector

ALGOLIA_ENDPOINT = "https://hn.algolia.com/api/v1/search_by_date"
DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 5  # 500 posts cap
EXCERPT_CHARS = 1000

FILTER_PROMPT_PATH = Path("prompts/hn_filter.txt")
FILTER_TOOL = {
    "name": "classify_post",
    "description": "Classify a HN post for DACH B2B SaaS / dev tool relevance.",
    "input_schema": {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["yes", "no", "unsure"],
                "description": "Relevance verdict.",
            },
            "reason": {
                "type": "string",
                "description": "One short sentence justifying the decision.",
            },
        },
        "required": ["decision", "reason"],
    },
}


class HackerNewsCollector(Collector):
    source = Source.HACKERNEWS

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        llm_call: Callable | None = None,
        fetch_fn: Callable | None = None,
        fetch_excerpts: bool = True,
    ) -> None:
        self._transport = transport
        self._llm_call = llm_call or default_llm_call
        self._fetch_fn = fetch_fn or default_fetch
        self._fetch_excerpts = fetch_excerpts

    async def collect(
        self,
        since: datetime | None = None,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
        page_size: int = DEFAULT_PAGE_SIZE,
        limit: int | None = None,
    ) -> list[RawLead]:
        if since is None:
            since = datetime.now(UTC) - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        since_ts = int(since.timestamp())

        hits = await self._fetch_algolia(since_ts, max_pages=max_pages, page_size=page_size)

        leads: list[RawLead] = []
        for hit in hits:
            if limit is not None and len(leads) >= limit:
                break
            url = (hit.get("url") or "").strip()
            if not url:
                continue  # text-only Show HN, no external link
            try:
                excerpt = await self._gather_excerpt(url)
            except Exception:
                excerpt = ""
            decision = self._classify(hit, url, excerpt)
            if decision == "no":
                continue
            lead = self._to_lead(hit, url, decision)
            if lead is not None:
                leads.append(lead)
        return leads

    # ---- internals --------------------------------------------------------

    def _make_client(self) -> httpx.AsyncClient:
        kwargs: dict = {"timeout": httpx.Timeout(30.0, connect=10.0)}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def _fetch_algolia(
        self, since_ts: int, *, max_pages: int, page_size: int
    ) -> list[dict]:
        all_hits: list[dict] = []
        async with self._make_client() as client:
            for page in range(max_pages):
                params = {
                    "tags": "show_hn",
                    "numericFilters": f"created_at_i>{since_ts}",
                    "hitsPerPage": page_size,
                    "page": page,
                }
                r = await client.get(ALGOLIA_ENDPOINT, params=params)
                if r.status_code != 200:
                    break
                data = r.json()
                page_hits = data.get("hits", []) or []
                all_hits.extend(page_hits)
                # stop when we've exhausted the search
                n_pages = data.get("nbPages", 0)
                if not page_hits or (n_pages and page >= n_pages - 1):
                    break
        return all_hits

    async def _gather_excerpt(self, url: str) -> str:
        if not self._fetch_excerpts:
            return ""
        result = await self._fetch_fn(url)
        if result is None:
            return ""
        return result.content[:EXCERPT_CHARS]

    def _classify(self, hit: dict, url: str, excerpt: str) -> str:
        title = (hit.get("title") or "").strip()
        prompt = _load_filter_prompt().format(
            title=title or "(no title)",
            url=url,
            excerpt=excerpt or "(no excerpt available)",
        )
        try:
            out = self._llm_call(prompt, FILTER_TOOL, model=HAIKU)
        except Exception:
            return "unsure"  # fail open — better to keep than to drop silently
        decision = (out.get("decision") or "unsure").lower()
        return decision if decision in {"yes", "no", "unsure"} else "unsure"

    def _to_lead(self, hit: dict, url: str, decision: str) -> RawLead | None:
        title_raw = (hit.get("title") or "").strip()
        # Strip leading "Show HN:" prefix (and dashes).
        name = title_raw
        for prefix in ("Show HN:", "Show HN —", "Show HN -"):
            if name.startswith(prefix):
                name = name[len(prefix) :].strip(" -—:")
                break
        ts = hit.get("created_at_i") or 0
        discovered = (
            datetime.fromtimestamp(ts, tz=UTC)
            if ts
            else datetime.now(UTC)
        )
        try:
            return RawLead(
                source=Source.HACKERNEWS,
                source_id=str(hit.get("objectID") or hit.get("story_id") or ""),
                name=name or None,
                website=url,
                one_liner=(hit.get("story_text") or None),
                discovered_at=discovered,
                raw_payload={
                    "author": hit.get("author"),
                    "points": hit.get("points"),
                    "hn_filter_decision": decision,
                    "title_raw": title_raw,
                },
            )
        except ValidationError:
            # Non-http URLs (PDFs hosted weirdly, etc.) — skip silently.
            return None


def _load_filter_prompt() -> str:
    return FILTER_PROMPT_PATH.read_text()
