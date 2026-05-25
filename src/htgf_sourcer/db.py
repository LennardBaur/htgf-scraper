"""SQLite state for the sourcing pipeline. Schema per PLAN.md §10."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .models import EnrichedStartup, RawLead, Score

DEFAULT_DB_PATH = Path("cache/state.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    name          TEXT,
    website       TEXT,
    one_liner     TEXT,
    discovered_at TIMESTAMP NOT NULL,
    raw_payload   TEXT,
    UNIQUE(source, source_id)
);

CREATE TABLE IF NOT EXISTS enriched_startups (
    canonical_id  TEXT PRIMARY KEY,
    payload       TEXT NOT NULL,
    last_enriched TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
    canonical_id TEXT PRIMARY KEY,
    payload      TEXT NOT NULL,
    scored_at    TIMESTAMP NOT NULL,
    FOREIGN KEY (canonical_id) REFERENCES enriched_startups(canonical_id)
);

CREATE TABLE IF NOT EXISTS fetch_cache (
    url_hash     TEXT PRIMARY KEY,
    url          TEXT NOT NULL,
    content_path TEXT NOT NULL,
    fetched_at   TIMESTAMP NOT NULL,
    fetcher      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_cache (
    request_hash TEXT PRIMARY KEY,
    response     TEXT NOT NULL,
    model        TEXT NOT NULL,
    cost_usd     REAL,
    created_at   TIMESTAMP NOT NULL
);
"""


def init_db(path: Path = DEFAULT_DB_PATH) -> Path:
    """Create the database file and schema if missing. Idempotent."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
    return path


@contextmanager
def connect(path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    """Context-managed connection. Initializes schema lazily.

    Timestamps are stored as ISO-8601 strings and parsed by the callers via
    `datetime.fromisoformat()`. We intentionally do NOT pass
    `detect_types=PARSE_DECLTYPES` because Python's legacy `convert_timestamp`
    adapter can't handle timezone offsets (e.g. `+00:00`) and crashes with
    `ValueError: invalid literal for int(): '18+00'`.
    """
    init_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---- thin helpers ---------------------------------------------------------
# Bare minimum for Step 1; richer query helpers land in Step 3 alongside the
# first real collector.


def upsert_lead(conn: sqlite3.Connection, lead_id: str, lead: RawLead) -> None:
    conn.execute(
        """
        INSERT INTO leads (id, source, source_id, name, website, one_liner,
                           discovered_at, raw_payload)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, source_id) DO UPDATE SET
            name=excluded.name,
            website=excluded.website,
            one_liner=excluded.one_liner,
            raw_payload=excluded.raw_payload
        """,
        (
            lead_id,
            lead.source.value,
            lead.source_id,
            lead.name,
            str(lead.website) if lead.website else None,
            lead.one_liner,
            lead.discovered_at,
            json.dumps(lead.raw_payload, default=str),
        ),
    )


def upsert_enriched(conn: sqlite3.Connection, enriched: EnrichedStartup) -> None:
    conn.execute(
        """
        INSERT INTO enriched_startups (canonical_id, payload, last_enriched)
        VALUES (?, ?, ?)
        ON CONFLICT(canonical_id) DO UPDATE SET
            payload=excluded.payload,
            last_enriched=excluded.last_enriched
        """,
        (
            enriched.canonical_id,
            enriched.model_dump_json(),
            enriched.last_enriched,
        ),
    )


def upsert_score(conn: sqlite3.Connection, score: Score) -> None:
    conn.execute(
        """
        INSERT INTO scores (canonical_id, payload, scored_at)
        VALUES (?, ?, ?)
        ON CONFLICT(canonical_id) DO UPDATE SET
            payload=excluded.payload,
            scored_at=excluded.scored_at
        """,
        (score.canonical_id, score.model_dump_json(), score.scored_at),
    )


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Row counts per table — used by `sourcer status`."""
    out: dict[str, int] = {}
    for table in ("leads", "enriched_startups", "scores", "fetch_cache", "llm_cache"):
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        out[table] = row["n"]
    return out


def total_llm_cost(conn: sqlite3.Connection) -> float:
    row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM llm_cache").fetchone()
    return float(row["total"])
