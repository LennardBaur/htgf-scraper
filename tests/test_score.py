"""score.py tests — Sonnet output is mocked. No network."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from htgf_sourcer import db
from htgf_sourcer.models import EnrichedStartup, ExtractedScore, Source
from htgf_sourcer.score import (
    DEFAULT_WEIGHTS,
    compute_overall,
    load_weights,
    score_all,
    score_one,
)


@pytest.fixture
def isolated_db(tmp_path: Path) -> Path:
    p = tmp_path / "state.db"
    db.init_db(p)
    return p


def _seed_enriched(db_path: Path, canonical_id: str = "abc", name: str = "Demo") -> EnrichedStartup:
    startup = EnrichedStartup(
        canonical_id=canonical_id,
        name=name,
        one_liner="A demo",
        long_description="A longer description.",
        sector="B2B SaaS",
        sources=[Source.HACKERNEWS],
        last_enriched=datetime.utcnow(),
    )
    with db.connect(db_path) as conn:
        db.upsert_enriched(conn, startup)
    return startup


def test_compute_overall_uses_weights():
    extracted = ExtractedScore(
        thesis_fit=5,
        team_quality=4,
        earliness=5,
        traction=2,
        contactability=3,
        rationale="x",
    )
    # 5*0.35 + 4*0.20 + 5*0.25 + 2*0.15 + 3*0.05 = 1.75+0.80+1.25+0.30+0.15 = 4.25
    assert compute_overall(extracted, DEFAULT_WEIGHTS) == pytest.approx(4.25)


def test_compute_overall_clamps_to_zero_five_range():
    extracted = ExtractedScore(
        thesis_fit=5, team_quality=5, earliness=5, traction=5, contactability=5, rationale="x"
    )
    weights = {"thesis_fit": 1.0, **{k: 0.0 for k in DEFAULT_WEIGHTS if k != "thesis_fit"}}
    assert compute_overall(extracted, weights) == 5.0


def test_score_one_persists_score(isolated_db: Path):
    startup = _seed_enriched(isolated_db)

    def fake_llm(prompt, tool, **kwargs):
        assert tool["name"] == "record_score"
        assert "STARTUP JSON" in prompt
        assert startup.canonical_id in prompt
        return {
            "thesis_fit": 4,
            "team_quality": 3,
            "earliness": 5,
            "traction": 2,
            "contactability": 3,
            "rationale": "Solides B2B-SaaS-Profil mit klarer DACH-Ausrichtung.",
            "red_flags": ["Kein technischer Mitgründer sichtbar."],
        }

    score = score_one(startup, llm_call=fake_llm, db_path=isolated_db)

    assert score is not None
    assert score.canonical_id == startup.canonical_id
    # 4*0.35 + 3*0.20 + 5*0.25 + 2*0.15 + 3*0.05 = 1.40+0.60+1.25+0.30+0.15 = 3.70
    assert score.overall == pytest.approx(3.70)
    assert score.rationale.startswith("Solides")
    assert score.red_flags == ["Kein technischer Mitgründer sichtbar."]

    with db.connect(isolated_db) as conn:
        row = conn.execute("SELECT payload FROM scores").fetchone()
    persisted = json.loads(row["payload"])
    assert persisted["overall"] == pytest.approx(3.70)
    assert persisted["thesis_fit"] == 4


def test_score_all_runs_over_every_enriched(isolated_db: Path):
    _seed_enriched(isolated_db, canonical_id="aaa", name="A")
    _seed_enriched(isolated_db, canonical_id="bbb", name="B")

    seen: list[str] = []

    def fake_llm(prompt, tool, **kwargs):
        # Track which startup the prompt is for via its canonical_id presence.
        for cid in ("aaa", "bbb"):
            if cid in prompt:
                seen.append(cid)
                break
        return {
            "thesis_fit": 3,
            "team_quality": 3,
            "earliness": 3,
            "traction": 3,
            "contactability": 3,
            "rationale": "Mittel",
            "red_flags": [],
        }

    succeeded, failed = score_all(llm_call=fake_llm, db_path=isolated_db)
    assert (succeeded, failed) == (2, 0)
    assert sorted(seen) == ["aaa", "bbb"]


def test_score_all_respects_limit(isolated_db: Path):
    _seed_enriched(isolated_db, canonical_id="aaa", name="A")
    _seed_enriched(isolated_db, canonical_id="bbb", name="B")
    _seed_enriched(isolated_db, canonical_id="ccc", name="C")

    calls = {"n": 0}

    def fake_llm(prompt, tool, **kwargs):
        calls["n"] += 1
        return {
            "thesis_fit": 3, "team_quality": 3, "earliness": 3,
            "traction": 3, "contactability": 3, "rationale": "x", "red_flags": [],
        }

    succeeded, failed = score_all(limit=2, llm_call=fake_llm, db_path=isolated_db)
    assert (succeeded, failed) == (2, 0)
    assert calls["n"] == 2


def test_score_one_returns_none_on_invalid_llm_output(isolated_db: Path):
    startup = _seed_enriched(isolated_db)

    def bad_llm(prompt, tool, **kwargs):
        return {"thesis_fit": 99}  # out of range, missing required fields

    assert score_one(startup, llm_call=bad_llm, db_path=isolated_db) is None


def test_load_weights_falls_back_to_defaults(tmp_path: Path):
    missing = tmp_path / "thesis.yaml"
    weights = load_weights(missing)
    assert weights == DEFAULT_WEIGHTS


def test_load_weights_reads_yaml(tmp_path: Path):
    path = tmp_path / "thesis.yaml"
    path.write_text(
        "score_weights:\n"
        "  thesis_fit: 1.0\n"
        "  team_quality: 0.0\n"
        "  earliness: 0.0\n"
        "  traction: 0.0\n"
        "  contactability: 0.0\n"
    )
    weights = load_weights(path)
    assert weights["thesis_fit"] == 1.0
    assert weights["team_quality"] == 0.0
