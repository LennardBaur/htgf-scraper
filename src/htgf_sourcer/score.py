"""Scoring — Sonnet rates each enriched startup against HTGF's thesis (§8).

The LLM returns the 5 dimension scores (1–5), a German rationale, and a list
of red flags via the `record_score` tool. The orchestrator computes the
weighted `overall` from `config/htgf_thesis.yaml`, then persists a `Score` row.

The LLM call goes through `llm.cached_call`, so re-runs against unchanged
enriched payloads are free.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import yaml
from loguru import logger
from pydantic import ValidationError

from . import db
from .llm import SONNET, pydantic_tool
from .llm import cached_call as default_llm_call
from .models import EnrichedStartup, ExtractedScore, Score

SCORE_PROMPT_PATH = Path("prompts/score_startup.txt")
THESIS_CONFIG_PATH = Path("config/htgf_thesis.yaml")
SCORE_TOOL_NAME = "record_score"

DEFAULT_WEIGHTS: dict[str, float] = {
    "thesis_fit":     0.35,
    "team_quality":   0.20,
    "earliness":      0.25,
    "traction":       0.15,
    "contactability": 0.05,
}


# ---- public api -----------------------------------------------------------


def score_all(
    *,
    limit: int | None = None,
    db_path: Path = db.DEFAULT_DB_PATH,
    llm_call: Callable | None = None,
    weights: dict[str, float] | None = None,
    thesis_config_path: Path = THESIS_CONFIG_PATH,
) -> tuple[int, int]:
    """Score every enriched startup. Returns (succeeded, failed)."""
    llm_call = llm_call or default_llm_call
    weights = weights if weights is not None else load_weights(thesis_config_path)

    startups = _load_enriched(db_path=db_path)
    if limit is not None:
        startups = startups[:limit]

    succeeded, failed = 0, 0
    for startup in startups:
        try:
            score = score_one(startup, llm_call=llm_call, weights=weights, db_path=db_path)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"score: {startup.canonical_id[:12]} — {e}")
            score = None
        if score is None:
            failed += 1
        else:
            succeeded += 1
    return succeeded, failed


def score_one(
    startup: EnrichedStartup,
    *,
    llm_call: Callable | None = None,
    weights: dict[str, float] | None = None,
    db_path: Path = db.DEFAULT_DB_PATH,
) -> Score | None:
    llm_call = llm_call or default_llm_call
    weights = weights if weights is not None else DEFAULT_WEIGHTS

    template = _load_prompt()
    startup_json = startup.model_dump_json(indent=2)
    prompt = template.replace("{{startup_json}}", startup_json)
    tool = pydantic_tool(
        ExtractedScore,
        SCORE_TOOL_NAME,
        "Score the startup against HTGF's Digital Tech thesis.",
    )

    try:
        raw = llm_call(prompt, tool, model=SONNET, db_path=db_path)
    except Exception:
        return None

    try:
        extracted = ExtractedScore.model_validate(raw)
    except ValidationError:
        return None

    overall = compute_overall(extracted, weights)
    score = Score(
        canonical_id=startup.canonical_id,
        thesis_fit=extracted.thesis_fit,
        team_quality=extracted.team_quality,
        earliness=extracted.earliness,
        traction=extracted.traction,
        contactability=extracted.contactability,
        overall=overall,
        rationale=extracted.rationale,
        red_flags=list(extracted.red_flags),
        scored_at=datetime.utcnow(),
    )
    with db.connect(db_path) as conn:
        db.upsert_score(conn, score)
    return score


# ---- helpers --------------------------------------------------------------


def compute_overall(extracted: ExtractedScore, weights: dict[str, float]) -> float:
    """Weighted sum of dimension scores. Result is clamped to [0, 5]."""
    dims = {
        "thesis_fit": extracted.thesis_fit,
        "team_quality": extracted.team_quality,
        "earliness": extracted.earliness,
        "traction": extracted.traction,
        "contactability": extracted.contactability,
    }
    total = sum(weights.get(k, 0.0) * v for k, v in dims.items())
    return round(max(0.0, min(5.0, total)), 4)


def load_weights(path: Path = THESIS_CONFIG_PATH) -> dict[str, float]:
    if not path.exists():
        return dict(DEFAULT_WEIGHTS)
    data = yaml.safe_load(path.read_text()) or {}
    weights = data.get("score_weights") or {}
    out: dict[str, float] = {}
    for key in DEFAULT_WEIGHTS:
        out[key] = float(weights.get(key, DEFAULT_WEIGHTS[key]))
    return out


def _load_enriched(*, db_path: Path) -> list[EnrichedStartup]:
    out: list[EnrichedStartup] = []
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT payload FROM enriched_startups ORDER BY last_enriched DESC"
        ).fetchall()
    for row in rows:
        try:
            out.append(EnrichedStartup.model_validate_json(row["payload"]))
        except (ValidationError, json.JSONDecodeError):
            continue
    return out


def _load_prompt() -> str:
    return SCORE_PROMPT_PATH.read_text()


__all__ = ["score_all", "score_one", "compute_overall", "load_weights", "DEFAULT_WEIGHTS"]
