"""Beta List collector tests — AI-native, no network."""

from __future__ import annotations

import asyncio
from datetime import datetime

from htgf_sourcer.fetch import FetchResult
from htgf_sourcer.models import Source
from htgf_sourcer.sources.betalist import BetaListCollector


def test_betalist_emits_leads_and_dedupes_by_name():
    market_urls = ["https://betalist.com/markets/germany", "https://betalist.com/markets/berlin"]

    async def fake_fetch(url, **kwargs):
        return FetchResult(
            url=url, content=f"market: {url}", fetcher="jina", fetched_at=datetime.utcnow()
        )

    pages = iter(
        [
            {"startups": [{"name": "FooApp", "one_liner": "saas"}]},
            {
                "startups": [
                    {"name": "fooapp", "one_liner": "dup"},  # dedup target (case-insensitive)
                    {"name": "BarApp", "one_liner": "dev tool"},
                ]
            },
        ]
    )

    def fake_llm(prompt, tool, **kwargs):
        return next(pages)

    collector = BetaListCollector(
        fetch_fn=fake_fetch, llm_call=fake_llm, market_urls=market_urls
    )
    leads = asyncio.run(collector.collect())

    assert [lead.name for lead in leads] == ["FooApp", "BarApp"]
    assert leads[0].source is Source.BETALIST
    # location_hint defaults to the market slug when item.location is missing
    assert leads[0].location_hint == "germany"
    assert leads[1].location_hint == "berlin"


def test_betalist_returns_empty_when_all_pages_fail():
    market_urls = ["https://betalist.com/markets/germany"]

    async def fail_fetch(url, **kwargs):
        return None

    def boom_llm(*a, **k):
        raise AssertionError("LLM should not be called when fetch fails")

    collector = BetaListCollector(
        fetch_fn=fail_fetch, llm_call=boom_llm, market_urls=market_urls
    )
    leads = asyncio.run(collector.collect())
    assert leads == []


def test_betalist_respects_limit():
    market_urls = ["https://betalist.com/markets/germany"]

    async def fake_fetch(url, **kwargs):
        return FetchResult(url=url, content="x", fetcher="jina", fetched_at=datetime.utcnow())

    def fake_llm(prompt, tool, **kwargs):
        return {"startups": [{"name": f"App {i}"} for i in range(5)]}

    collector = BetaListCollector(
        fetch_fn=fake_fetch, llm_call=fake_llm, market_urls=market_urls
    )
    leads = asyncio.run(collector.collect(limit=2))
    assert len(leads) == 2
