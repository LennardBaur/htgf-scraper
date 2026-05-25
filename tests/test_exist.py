"""EXIST collector — fetch + LLM mocked."""

from __future__ import annotations

import asyncio
from datetime import datetime

from htgf_sourcer.fetch import FetchResult
from htgf_sourcer.models import Source
from htgf_sourcer.sources.exist import KEYWORDS, ExistCollector


async def _make_fake_fetch(content_per_url: dict[str, str]):
    async def fake(url, **kwargs):
        if url in content_per_url:
            return FetchResult(
                url=url, content=content_per_url[url], fetcher="jina", fetched_at=datetime.utcnow()
            )
        return None

    return fake


def test_exist_keeps_entries_matching_keyword_and_year():
    urls = ["https://www.exist.de/index.html"]
    fetch_fn = asyncio.run(_make_fake_fetch({urls[0]: "# EXIST index\ntext"}))

    extracted = [
        {"name": "Foo SaaS", "one_liner": "Cloud platform", "year": 2025, "location": "TU München"},
        {"name": "Old Tech", "one_liner": "Software", "year": 2010, "location": "TUB"},
        {"name": "Hardware", "one_liner": "Lab gear", "year": 2025, "location": "KIT"},
    ]

    def fake_llm(prompt, tool, **kwargs):
        return {"startups": extracted}

    collector = ExistCollector(fetch_fn=fetch_fn, llm_call=fake_llm, index_urls=urls)
    leads = asyncio.run(collector.collect())

    names = [lead.name for lead in leads]
    assert names == ["Foo SaaS"]
    assert leads[0].source is Source.EXIST
    assert leads[0].location_hint == "TU München"


def test_exist_returns_empty_when_fetch_fails():
    urls = ["https://www.exist.de/index.html"]

    async def fail_fetch(url, **kwargs):
        return None

    def boom_llm(*a, **k):
        raise AssertionError("LLM should not be called when fetch fails")

    collector = ExistCollector(fetch_fn=fail_fetch, llm_call=boom_llm, index_urls=urls)
    leads = asyncio.run(collector.collect())
    assert leads == []


def test_exist_respects_limit():
    urls = ["https://www.exist.de/index.html"]
    fetch_fn = asyncio.run(_make_fake_fetch({urls[0]: "x"}))
    extracted = [
        {"name": f"Cloud {i}", "one_liner": "saas thing", "year": 2025, "location": "TUM"}
        for i in range(5)
    ]

    def fake_llm(prompt, tool, **kwargs):
        return {"startups": extracted}

    collector = ExistCollector(fetch_fn=fetch_fn, llm_call=fake_llm, index_urls=urls)
    leads = asyncio.run(collector.collect(limit=2))
    assert len(leads) == 2


def test_keyword_whitelist_covers_german_and_english():
    assert "saas" in KEYWORDS
    assert "ki" in KEYWORDS
    assert "entwickler" in KEYWORDS
