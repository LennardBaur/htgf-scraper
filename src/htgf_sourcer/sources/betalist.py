"""Beta List collector (§6.7).

Beta List has no API. We hit the static "markets" slugs that filter products
by country/city, then AI-extract via `_ai_listing`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime

from loguru import logger
from pydantic import ValidationError

from ..fetch import fetch as default_fetch
from ..models import RawLead, Source
from ._ai_listing import extract_listing
from .base import Collector

MARKET_URLS = [
    "https://betalist.com/markets/germany",
    "https://betalist.com/markets/berlin",
    "https://betalist.com/markets/austria",
    "https://betalist.com/markets/switzerland",
]


class BetaListCollector(Collector):
    source = Source.BETALIST

    def __init__(
        self,
        *,
        fetch_fn: Callable | None = None,
        llm_call: Callable | None = None,
        market_urls: list[str] | None = None,
    ) -> None:
        self._fetch_fn = fetch_fn or default_fetch
        self._llm_call = llm_call
        self._market_urls = market_urls or list(MARKET_URLS)

    async def collect(
        self,
        since: datetime | None = None,
        *,
        limit: int | None = None,
    ) -> list[RawLead]:
        leads: list[RawLead] = []
        seen_names: set[str] = set()

        for url in self._market_urls:
            page = await self._fetch_fn(url)
            if page is None:
                logger.warning(f"betalist: fetch failed for {url}")
                continue

            market = url.rsplit("/", 1)[-1]
            items = extract_listing(
                page.content,
                source_hint=f"Beta List market page ({market})",
                llm_call=self._llm_call,
            )
            for item in items:
                name = (item.get("name") or "").strip()
                if not name or name.lower() in seen_names:
                    continue
                lead = _to_lead(item, market=market, source_url=url)
                if lead is None:
                    continue
                seen_names.add(name.lower())
                leads.append(lead)
                if limit is not None and len(leads) >= limit:
                    return leads
        return leads


def _to_lead(item: dict, *, market: str, source_url: str) -> RawLead | None:
    name = (item.get("name") or "").strip()
    if not name:
        return None
    source_id = hashlib.sha256(f"betalist:{name}".encode()).hexdigest()[:16]
    website = (item.get("website") or "").strip() or None
    try:
        return RawLead(
            source=Source.BETALIST,
            source_id=source_id,
            name=name,
            website=website,
            one_liner=item.get("one_liner") or None,
            location_hint=item.get("location") or market,
            discovered_at=datetime.utcnow(),
            raw_payload={
                "source_url": source_url,
                "market": market,
                "year": item.get("year"),
            },
        )
    except ValidationError:
        return None
