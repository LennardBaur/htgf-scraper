"""University collector — config-driven AI-native extraction."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from htgf_sourcer.fetch import FetchResult
from htgf_sourcer.models import Source
from htgf_sourcer.sources.universities import UniversityCollector


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    p = tmp_path / "universities.yaml"
    p.write_text(
        "universities:\n"
        '  - name: "TU München"\n'
        '    spinoff_url: "https://tum.example/spinoffs"\n'
        '  - name: "RWTH Aachen"\n'
        '    spinoff_url: "https://rwth.example/spinoffs"\n'
    )
    return p


def test_university_collector_emits_lead_per_university(config_path: Path):
    async def fake_fetch(url, **kwargs):
        return FetchResult(
            url=url,
            content=f"Listings for {url}",
            fetcher="jina",
            fetched_at=datetime.utcnow(),
        )

    extractions = iter(
        [
            {"startups": [{"name": "Alpha", "one_liner": "AI ops"}]},
            {"startups": [{"name": "Beta", "one_liner": "DevTool"}]},
        ]
    )

    def fake_llm(prompt, tool, **kwargs):
        return next(extractions)

    collector = UniversityCollector(
        fetch_fn=fake_fetch, llm_call=fake_llm, config_path=config_path
    )
    leads = asyncio.run(collector.collect())

    assert [lead.name for lead in leads] == ["Alpha", "Beta"]
    assert leads[0].location_hint == "TU München"
    assert leads[1].location_hint == "RWTH Aachen"
    assert all(lead.source is Source.UNIVERSITY for lead in leads)


def test_university_collector_returns_empty_when_config_missing(tmp_path: Path):
    missing = tmp_path / "does-not-exist.yaml"

    def boom_llm(*a, **k):
        raise AssertionError("LLM should not be called")

    async def boom_fetch(url, **kwargs):
        raise AssertionError("fetch should not be called")

    collector = UniversityCollector(
        fetch_fn=boom_fetch, llm_call=boom_llm, config_path=missing
    )
    leads = asyncio.run(collector.collect())
    assert leads == []


def test_university_collector_respects_limit(config_path: Path):
    async def fake_fetch(url, **kwargs):
        return FetchResult(url=url, content="x", fetcher="jina", fetched_at=datetime.utcnow())

    def fake_llm(prompt, tool, **kwargs):
        return {"startups": [{"name": f"S{i}"} for i in range(10)]}

    collector = UniversityCollector(
        fetch_fn=fake_fetch, llm_call=fake_llm, config_path=config_path
    )
    leads = asyncio.run(collector.collect(limit=3))
    assert len(leads) == 3
