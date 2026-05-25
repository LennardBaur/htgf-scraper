"""HN collector tests — Algolia mocked via httpx.MockTransport, LLM mocked inline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

import httpx

from htgf_sourcer.fetch import FetchResult
from htgf_sourcer.models import Source
from htgf_sourcer.sources.hackernews import (
    ALGOLIA_ENDPOINT,
    HackerNewsCollector,
)


@dataclass
class _FakeFetcher:
    """Returns synthetic excerpts for excerpt-gathering."""

    excerpt: str = "Some excerpt about a German SaaS product."
    calls: int = 0

    async def __call__(self, url: str, **kwargs):
        self.calls += 1
        return FetchResult(
            url=url, content=self.excerpt, fetcher="jina", fetched_at=datetime.utcnow()
        )


def _algolia_handler(hits: list[dict]):
    """MockTransport handler that returns one page then signals end-of-results."""
    state = {"page": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "hn.algolia.com"
        if state["page"] == 0:
            state["page"] += 1
            return httpx.Response(
                200, json={"hits": hits, "nbPages": 1, "page": 0}
            )
        return httpx.Response(200, json={"hits": [], "nbPages": 1, "page": 1})

    return handle


def _hit(object_id: str, title: str, url: str | None, ts: int = 1735689600) -> dict:
    return {
        "objectID": object_id,
        "title": title,
        "url": url,
        "created_at_i": ts,
        "author": "tester",
        "points": 42,
    }


def test_collector_returns_leads_for_yes_and_unsure():
    hits = [
        _hit("1", "Show HN: Berlin DevTool", "https://devtool.de"),
        _hit("2", "Show HN: Stealth thing", "https://example.com/x"),
        _hit("3", "Show HN: Consumer toy", "https://toy.example.com"),
    ]
    transport = httpx.MockTransport(_algolia_handler(hits))
    fetcher = _FakeFetcher()

    decisions = iter(
        [
            {"decision": "yes", "reason": "DE domain"},
            {"decision": "unsure", "reason": "unclear"},
            {"decision": "no", "reason": "consumer"},
        ]
    )

    def fake_llm(prompt, tool, **kwargs):
        return next(decisions)

    collector = HackerNewsCollector(
        transport=transport, llm_call=fake_llm, fetch_fn=fetcher
    )
    leads = asyncio.run(collector.collect())

    assert [lead.source_id for lead in leads] == ["1", "2"]
    assert all(lead.source is Source.HACKERNEWS for lead in leads)
    assert leads[0].name == "Berlin DevTool"  # "Show HN: " stripped
    assert str(leads[0].website).startswith("https://devtool.de")
    assert leads[0].raw_payload["hn_filter_decision"] == "yes"
    assert leads[1].raw_payload["hn_filter_decision"] == "unsure"
    assert fetcher.calls == 3


def test_collector_skips_hits_without_url():
    hits = [
        _hit("100", "Show HN: text-only post", None),
        _hit("101", "Show HN: with link", "https://startup.de"),
    ]
    transport = httpx.MockTransport(_algolia_handler(hits))

    def fake_llm(prompt, tool, **kwargs):
        return {"decision": "yes", "reason": "DE"}

    collector = HackerNewsCollector(
        transport=transport, llm_call=fake_llm, fetch_fn=_FakeFetcher()
    )
    leads = asyncio.run(collector.collect())
    assert [lead.source_id for lead in leads] == ["101"]


def test_collector_fail_open_when_llm_errors():
    hits = [_hit("200", "Show HN: thing", "https://thing.de")]
    transport = httpx.MockTransport(_algolia_handler(hits))

    def angry_llm(prompt, tool, **kwargs):
        raise RuntimeError("API down")

    collector = HackerNewsCollector(
        transport=transport, llm_call=angry_llm, fetch_fn=_FakeFetcher()
    )
    leads = asyncio.run(collector.collect())
    # Fail-open: post is kept as 'unsure' rather than dropped silently.
    assert len(leads) == 1
    assert leads[0].raw_payload["hn_filter_decision"] == "unsure"


def test_collector_respects_limit():
    hits = [_hit(str(i), f"Show HN: Thing {i}", f"https://t{i}.de") for i in range(5)]
    transport = httpx.MockTransport(_algolia_handler(hits))

    def fake_llm(prompt, tool, **kwargs):
        return {"decision": "yes", "reason": "ok"}

    collector = HackerNewsCollector(
        transport=transport, llm_call=fake_llm, fetch_fn=_FakeFetcher()
    )
    leads = asyncio.run(collector.collect(limit=2))
    assert len(leads) == 2


def test_collector_skips_excerpt_fetch_when_disabled():
    hits = [_hit("300", "Show HN: thing", "https://thing.de")]
    transport = httpx.MockTransport(_algolia_handler(hits))
    fetcher = _FakeFetcher()

    def fake_llm(prompt, tool, **kwargs):
        return {"decision": "yes", "reason": "ok"}

    collector = HackerNewsCollector(
        transport=transport,
        llm_call=fake_llm,
        fetch_fn=fetcher,
        fetch_excerpts=False,
    )
    leads = asyncio.run(collector.collect())
    assert len(leads) == 1
    assert fetcher.calls == 0


def test_algolia_endpoint_constant_is_https():
    assert ALGOLIA_ENDPOINT.startswith("https://")
