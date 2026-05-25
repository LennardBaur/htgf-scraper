"""EXIST grants collector (§6.1).

EXIST-Gründerstipendium and EXIST-Forschungstransfer are German federal
grants whose recipients are listed publicly. The names are usually working
titles, not company names — the enrichment stage handles canonicalization.

Strategy:
1. Fetch each index page via the standard fetch chain (Jina first).
2. AI-extract entries with `_ai_listing.extract_listing`.
3. Post-filter: keep entries with year ≥ now - 2 *and* whose one_liner / name
   contains at least one digital-tech keyword.
4. Emit RawLead — website is usually missing, so leads from this source rely
   on dedup to merge with website-bearing sources later.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import datetime, timedelta

from loguru import logger
from pydantic import ValidationError

from ..fetch import fetch as default_fetch
from ..models import RawLead, Source
from ._ai_listing import extract_listing
from .base import Collector

INDEX_URLS = [
    "https://www.exist.de/EXIST/Navigation/DE/Gefoerderte-Projekte/EXIST-Gruenderstipendium/exist-gruenderstipendium.html",
    "https://www.exist.de/EXIST/Navigation/DE/Gefoerderte-Projekte/EXIST-Forschungstransfer/exist-forschungstransfer.html",
]

# Digital-tech keyword whitelist from §6.1. Matched on word boundaries (case-
# insensitive) so short tokens like "ki" don't false-match "kit", "skipper", etc.
KEYWORDS = {
    "software", "saas", "plattform", "cloud", "ki", "ai", "ml",
    "data", "daten", "api", "developer", "entwickler", "b2b",
    "automation", "enterprise", "cyber", "devops", "analytics",
}
_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(KEYWORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

DEFAULT_LOOKBACK_YEARS = 2


class ExistCollector(Collector):
    source = Source.EXIST

    def __init__(
        self,
        *,
        fetch_fn: Callable | None = None,
        llm_call: Callable | None = None,
        index_urls: list[str] | None = None,
    ) -> None:
        self._fetch_fn = fetch_fn or default_fetch
        self._llm_call = llm_call
        self._index_urls = index_urls or list(INDEX_URLS)

    async def collect(
        self,
        since: datetime | None = None,
        *,
        limit: int | None = None,
    ) -> list[RawLead]:
        floor = since or datetime.utcnow() - timedelta(days=365 * DEFAULT_LOOKBACK_YEARS)
        cutoff_year = floor.year

        leads: list[RawLead] = []
        for url in self._index_urls:
            page = await self._fetch_fn(url)
            if page is None:
                logger.warning(f"exist: fetch failed for {url}")
                continue

            items = extract_listing(
                page.content, source_hint="EXIST grant listing", llm_call=self._llm_call
            )

            for item in items:
                if not _matches_filters(item, cutoff_year=cutoff_year):
                    continue
                lead = _to_lead(item, source_url=url)
                if lead is None:
                    continue
                leads.append(lead)
                if limit is not None and len(leads) >= limit:
                    return leads
        return leads


def _matches_filters(item: dict, *, cutoff_year: int) -> bool:
    year = item.get("year")
    if isinstance(year, int) and year < cutoff_year:
        return False
    haystack = " ".join(
        str(v) for v in (item.get("name"), item.get("one_liner"), item.get("location")) if v
    )
    return _KEYWORD_RE.search(haystack) is not None


def _to_lead(item: dict, *, source_url: str) -> RawLead | None:
    name = (item.get("name") or "").strip()
    if not name:
        return None
    source_id = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    website = (item.get("website") or "").strip() or None
    try:
        return RawLead(
            source=Source.EXIST,
            source_id=source_id,
            name=name,
            website=website,
            one_liner=item.get("one_liner") or None,
            location_hint=item.get("location") or None,
            discovered_at=datetime.utcnow(),
            raw_payload={
                "source_url": source_url,
                "year": item.get("year"),
                "founders": item.get("founders") or [],
            },
        )
    except ValidationError:
        return None


# Re-export for tests that want to lock the keyword set.
__all__ = ["ExistCollector", "INDEX_URLS", "KEYWORDS"]
