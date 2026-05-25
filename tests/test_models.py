"""Placeholder schema tests. Locks the Pydantic models from §5."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from htgf_sourcer.models import (
    EnrichedStartup,
    Founder,
    RawLead,
    Score,
    Source,
    Stage,
)


def test_raw_lead_round_trip():
    lead = RawLead(
        source=Source.HACKERNEWS,
        source_id="42",
        name="Demo",
        website="https://example.com/",
        one_liner="A demo startup",
        location_hint="Berlin",
        discovered_at=datetime(2026, 1, 1, 12, 0, 0),
        raw_payload={"story_id": 42},
    )
    restored = RawLead.model_validate(lead.model_dump(mode="json"))
    assert restored.name == lead.name
    assert restored.source is Source.HACKERNEWS
    assert restored.raw_payload == {"story_id": 42}


def test_enriched_startup_defaults_and_stage():
    es = EnrichedStartup(
        canonical_id="abc",
        name="Demo",
        one_liner="x",
        long_description="y",
        sector="B2B SaaS",
        last_enriched=datetime(2026, 1, 1),
    )
    assert es.stage_signal is Stage.UNKNOWN
    assert es.founders == []
    assert es.sources == []

    # Founder list survives a round-trip.
    es_with_founder = es.model_copy(
        update={"founders": [Founder(name="Ada Lovelace", role="CEO")]}
    )
    restored = EnrichedStartup.model_validate(es_with_founder.model_dump(mode="json"))
    assert restored.founders[0].name == "Ada Lovelace"


def test_score_bounds_enforced():
    Score(
        canonical_id="abc",
        thesis_fit=4,
        team_quality=3,
        earliness=5,
        traction=2,
        contactability=3,
        overall=3.45,
        rationale="Solides B2B-SaaS-Team mit klarer DACH-Ausrichtung.",
        scored_at=datetime(2026, 1, 1),
    )

    with pytest.raises(ValidationError):
        Score(
            canonical_id="abc",
            thesis_fit=6,  # out of range
            team_quality=3,
            earliness=5,
            traction=2,
            contactability=3,
            overall=3.0,
            rationale="x",
            scored_at=datetime(2026, 1, 1),
        )
