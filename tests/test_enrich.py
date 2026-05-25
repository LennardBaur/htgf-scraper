"""Enrichment pipeline tests — fetch + LLM mocked, no network calls."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest

from htgf_sourcer import db
from htgf_sourcer.enrich import (
    canonical_id_for,
    enrich_lead,
    enrich_pending,
)
from htgf_sourcer.fetch import FetchResult, normalize_url
from htgf_sourcer.models import RawLead, Source


@pytest.fixture
def isolated_db(tmp_path: Path) -> Path:
    p = tmp_path / "state.db"
    db.init_db(p)
    return p


def _make_lead(source_id: str = "hn-1", website: str = "https://Example.de/") -> RawLead:
    return RawLead(
        source=Source.HACKERNEWS,
        source_id=source_id,
        name="Example",
        website=website,
        one_liner="A demo German B2B SaaS",
        discovered_at=datetime.utcnow(),
        raw_payload={"hn_filter_decision": "yes"},
    )


def _seed_lead(db_path: Path, lead: RawLead, lead_id: str = "lead-1") -> None:
    with db.connect(db_path) as conn:
        db.upsert_lead(conn, lead_id, lead)


async def _fake_fetch_factory(content_map: dict[str, str]):
    """Return a fake fetch() that maps URL → content. Unknown URLs → None."""

    async def fake_fetch(url: str, **kwargs):
        norm = normalize_url(url)
        if norm in content_map:
            return FetchResult(
                url=norm, content=content_map[norm], fetcher="jina", fetched_at=datetime.utcnow()
            )
        return None

    return fake_fetch


def test_canonical_id_is_stable_for_equivalent_urls():
    a = canonical_id_for(normalize_url("https://WWW.Example.de/"))
    b = canonical_id_for(normalize_url("https://example.de"))
    assert a == b


def test_enrich_lead_persists_enriched_row(isolated_db: Path):
    lead = _make_lead()
    landing_url = normalize_url(str(lead.website))

    content_map = {
        landing_url: "# Example GmbH\n\nWe build AI for the Mittelstand.",
        landing_url + "/about": "About: founded 2024 by Ada Lovelace in Berlin.",
    }
    fake_fetch = asyncio.run(_fake_fetch_factory(content_map))

    extracted_payload = {
        "name": "Example GmbH",
        "one_liner": "AI for the Mittelstand.",
        "long_description": "B2B SaaS that brings AI to German Mittelstand companies.",
        "sector": "B2B SaaS",
        "hq_city": "Berlin",
        "hq_country": "DE",
        "founded_year": 2024,
        "stage_signal": "pre_seed",
        "founders": [{"name": "Ada Lovelace", "role": "CEO"}],
        "traction_signals": ["Pilot with mid-sized manufacturer"],
        "funding_signals": ["EXIST 2025"],
    }

    def fake_llm(prompt, tool, **kwargs):
        assert tool["name"] == "record_startup"
        assert "CONTENT:" in prompt
        return extracted_payload

    startup = asyncio.run(
        enrich_lead(
            lead, db_path=isolated_db, fetch_fn=fake_fetch, llm_call=fake_llm
        )
    )

    assert startup is not None
    assert startup.canonical_id == canonical_id_for(landing_url)
    assert startup.name == "Example GmbH"
    assert startup.sector == "B2B SaaS"
    assert startup.sources == [Source.HACKERNEWS]
    assert any(str(u).startswith(landing_url) for u in startup.source_urls)

    with db.connect(isolated_db) as conn:
        row = conn.execute(
            "SELECT canonical_id, payload FROM enriched_startups"
        ).fetchone()
    assert row["canonical_id"] == startup.canonical_id
    persisted = json.loads(row["payload"])
    assert persisted["sector"] == "B2B SaaS"


def test_enrich_lead_returns_none_when_landing_fetch_fails(isolated_db: Path):
    lead = _make_lead()

    async def empty_fetch(url, **kwargs):
        return None

    def boom_llm(*a, **kw):
        raise AssertionError("LLM should not be called when fetch fails")

    out = asyncio.run(
        enrich_lead(lead, db_path=isolated_db, fetch_fn=empty_fetch, llm_call=boom_llm)
    )
    assert out is None


def test_enrich_lead_returns_none_when_lead_has_no_website(isolated_db: Path):
    lead = RawLead(
        source=Source.HACKERNEWS,
        source_id="x",
        name="No-site",
        website=None,
        discovered_at=datetime.utcnow(),
    )

    async def boom_fetch(url, **kwargs):
        raise AssertionError("fetch should not be called")

    out = asyncio.run(
        enrich_lead(lead, db_path=isolated_db, fetch_fn=boom_fetch, llm_call=lambda *a, **k: {})
    )
    assert out is None


def test_enrich_pending_skips_fresh_enrichments(isolated_db: Path):
    lead = _make_lead()
    _seed_lead(isolated_db, lead)

    landing_url = normalize_url(str(lead.website))
    fake_fetch = asyncio.run(
        _fake_fetch_factory({landing_url: "# Example\nLanding content."})
    )
    call_count = {"n": 0}

    def fake_llm(prompt, tool, **kwargs):
        call_count["n"] += 1
        return {
            "name": "Example",
            "one_liner": "x",
            "long_description": "y",
            "sector": "B2B SaaS",
        }

    s1, f1 = asyncio.run(
        enrich_pending(db_path=isolated_db, fetch_fn=fake_fetch, llm_call=fake_llm)
    )
    assert (s1, f1) == (1, 0)
    assert call_count["n"] == 1

    # Second pass — the existing enriched row is fresh, so the lead is skipped.
    s2, f2 = asyncio.run(
        enrich_pending(db_path=isolated_db, fetch_fn=fake_fetch, llm_call=fake_llm)
    )
    assert (s2, f2) == (0, 0)
    assert call_count["n"] == 1  # LLM was NOT invoked again


def test_enrich_pending_respects_limit(isolated_db: Path):
    _seed_lead(isolated_db, _make_lead("hn-1", "https://a.de"), lead_id="lead-1")
    _seed_lead(isolated_db, _make_lead("hn-2", "https://b.de"), lead_id="lead-2")
    _seed_lead(isolated_db, _make_lead("hn-3", "https://c.de"), lead_id="lead-3")

    async def fake_fetch(url, **kwargs):
        return FetchResult(
            url=url, content="# x\n y", fetcher="jina", fetched_at=datetime.utcnow()
        )

    def fake_llm(prompt, tool, **kwargs):
        return {
            "name": "X",
            "one_liner": "x",
            "long_description": "y",
            "sector": "B2B SaaS",
        }

    s, f = asyncio.run(
        enrich_pending(
            limit=2, db_path=isolated_db, fetch_fn=fake_fetch, llm_call=fake_llm
        )
    )
    assert (s, f) == (2, 0)

    with db.connect(isolated_db) as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM enriched_startups").fetchone()["n"]
    assert n == 2
