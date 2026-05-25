"""dedup.py tests — both stages, mocked Haiku."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from htgf_sourcer import db
from htgf_sourcer.dedup import (
    merge_with_existing,
    pairwise_match_leads,
)
from htgf_sourcer.fetch import FetchResult
from htgf_sourcer.models import EnrichedStartup, RawLead, Source


@pytest.fixture
def isolated_db(tmp_path: Path) -> Path:
    p = tmp_path / "state.db"
    db.init_db(p)
    return p


def _make_startup(canonical_id: str, name: str, sources: list[Source]) -> EnrichedStartup:
    return EnrichedStartup(
        canonical_id=canonical_id,
        name=name,
        one_liner="x",
        long_description="y",
        sector="B2B SaaS",
        sources=sources,
        source_urls=[],
        last_enriched=datetime.utcnow(),
    )


def _seed(db_path: Path, startup: EnrichedStartup) -> None:
    with db.connect(db_path) as conn:
        db.upsert_enriched(conn, startup)


def _seed_lead(db_path: Path, lead: RawLead, lead_id: str | None = None) -> None:
    lead_id = lead_id or hashlib.sha256(
        f"{lead.source.value}:{lead.source_id}".encode()
    ).hexdigest()
    with db.connect(db_path) as conn:
        db.upsert_lead(conn, lead_id, lead)


# ---- Stage 1 -------------------------------------------------------------


def test_merge_with_existing_unions_sources_and_urls(isolated_db: Path):
    seeded = EnrichedStartup(
        canonical_id="abc",
        name="Demo",
        one_liner="x",
        long_description="y",
        sector="B2B SaaS",
        sources=[Source.HACKERNEWS],
        source_urls=["https://demo.de"],
        last_enriched=datetime.utcnow(),
    )
    _seed(isolated_db, seeded)

    new = EnrichedStartup(
        canonical_id="abc",
        name="Demo",
        one_liner="x",
        long_description="y",
        sector="B2B SaaS",
        sources=[Source.GITHUB],
        source_urls=["https://demo.de/about"],
        last_enriched=datetime.utcnow(),
    )

    merged = merge_with_existing(new, db_path=isolated_db)
    source_values = {s.value for s in merged.sources}
    assert source_values == {"hackernews", "github"}
    assert sorted(str(u) for u in merged.source_urls) == sorted(
        ["https://demo.de/", "https://demo.de/about"]
    )


def test_merge_with_existing_returns_new_when_no_prior_row(isolated_db: Path):
    new = _make_startup("xyz", "Other", [Source.BETALIST])
    out = merge_with_existing(new, db_path=isolated_db)
    assert out is new or out.canonical_id == "xyz"
    assert [s.value for s in out.sources] == ["betalist"]


# ---- Stage 2 -------------------------------------------------------------


def test_pairwise_no_op_when_no_websiteless_leads(isolated_db: Path):
    _seed(isolated_db, _make_startup("abc", "Demo", [Source.HACKERNEWS]))
    n_checked, n_merged = pairwise_match_leads(
        db_path=isolated_db, llm_call=lambda *a, **k: {"match": True, "reasoning": "x"}
    )
    assert (n_checked, n_merged) == (0, 0)


def test_pairwise_matches_websiteless_lead_to_enriched(isolated_db: Path):
    _seed(
        isolated_db,
        _make_startup("abc", "Acme Robotics GmbH", [Source.HACKERNEWS]),
    )
    lead = RawLead(
        source=Source.EXIST,
        source_id="exist-1",
        name="Acme Robotics",  # close match to "Acme Robotics GmbH"
        website=None,
        one_liner="EXIST grant project",
        discovered_at=datetime.utcnow(),
    )
    _seed_lead(isolated_db, lead)

    calls = {"n": 0}

    def fake_llm(prompt, tool, **kwargs):
        calls["n"] += 1
        assert tool["name"] == "judge_match"
        assert "Acme Robotics" in prompt
        return {"match": True, "reasoning": "Same team."}

    n_checked, n_merged = pairwise_match_leads(db_path=isolated_db, llm_call=fake_llm)

    assert n_merged == 1
    assert calls["n"] == 1

    with db.connect(isolated_db) as conn:
        row = conn.execute(
            "SELECT payload FROM enriched_startups WHERE canonical_id='abc'"
        ).fetchone()
    merged = json.loads(row["payload"])
    assert sorted(merged["sources"]) == ["exist", "hackernews"]


def test_pairwise_skips_non_matching_pairs(isolated_db: Path):
    _seed(isolated_db, _make_startup("abc", "Acme Robotics", [Source.HACKERNEWS]))
    lead = RawLead(
        source=Source.EXIST,
        source_id="exist-2",
        name="Acme Robots",  # close fuzzy ratio
        website=None,
        discovered_at=datetime.utcnow(),
    )
    _seed_lead(isolated_db, lead)

    def fake_llm(prompt, tool, **kwargs):
        return {"match": False, "reasoning": "Different teams."}

    n_checked, n_merged = pairwise_match_leads(db_path=isolated_db, llm_call=fake_llm)
    assert n_checked >= 1
    assert n_merged == 0


def test_pairwise_ignores_dissimilar_names(isolated_db: Path):
    _seed(isolated_db, _make_startup("abc", "Acme Robotics", [Source.HACKERNEWS]))
    lead = RawLead(
        source=Source.EXIST,
        source_id="exist-3",
        name="Zenith Quantum Holographic Toolchain",  # nothing in common
        website=None,
        discovered_at=datetime.utcnow(),
    )
    _seed_lead(isolated_db, lead)

    def boom_llm(*a, **k):
        raise AssertionError("LLM should not be consulted for dissimilar names")

    n_checked, n_merged = pairwise_match_leads(db_path=isolated_db, llm_call=boom_llm)
    assert (n_checked, n_merged) == (0, 0)


# ---- Combined: enrich.py auto-merges via Stage 1 -------------------------


def test_enrich_calls_stage_1_merge(isolated_db: Path):
    """Re-enriching the same domain via a different lead source merges sources."""
    from htgf_sourcer.enrich import enrich_lead

    lead_a = RawLead(
        source=Source.HACKERNEWS,
        source_id="hn-A",
        name="Same Co",
        website="https://same.de/",
        discovered_at=datetime.utcnow(),
    )
    lead_b = RawLead(
        source=Source.PRODUCTHUNT,
        source_id="ph-B",
        name="Same Co",
        website="https://same.de/",
        discovered_at=datetime.utcnow(),
    )

    async def fake_fetch(url, **kwargs):
        return FetchResult(
            url=url, content="# x\ndata", fetcher="jina", fetched_at=datetime.utcnow()
        )

    def fake_llm(prompt, tool, **kwargs):
        return {
            "name": "Same Co",
            "one_liner": "x",
            "long_description": "y",
            "sector": "B2B SaaS",
        }

    asyncio.run(
        enrich_lead(lead_a, db_path=isolated_db, fetch_fn=fake_fetch, llm_call=fake_llm)
    )
    asyncio.run(
        enrich_lead(lead_b, db_path=isolated_db, fetch_fn=fake_fetch, llm_call=fake_llm)
    )

    with db.connect(isolated_db) as conn:
        row = conn.execute("SELECT payload FROM enriched_startups").fetchone()
    payload = json.loads(row["payload"])
    assert sorted(payload["sources"]) == ["hackernews", "producthunt"]
