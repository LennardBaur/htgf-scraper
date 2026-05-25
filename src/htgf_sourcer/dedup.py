"""Deduplication — two stages per PLAN.md §9.

Stage 1: deterministic canonical-id collision merge. Called from `enrich.py`
before persisting a freshly extracted startup: if a row already exists for the
same canonical_id, merge `sources` + `source_urls` and keep the latest payload.

Stage 2: Haiku pairwise check for websiteless leads (EXIST entries, early
university spin-outs) against existing enriched startups. Candidate pairs are
shortlisted with `difflib.SequenceMatcher.ratio()` to keep LLM volume low.
Idempotent across runs because every Haiku call is cached.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from loguru import logger
from pydantic import ValidationError

from . import db
from .llm import HAIKU
from .llm import cached_call as default_llm_call
from .models import EnrichedStartup, RawLead, Source

DEDUP_PROMPT_PATH = Path("prompts/dedup_check.txt")
DEDUP_TOOL = {
    "name": "judge_match",
    "description": "Decide whether two records describe the same startup.",
    "input_schema": {
        "type": "object",
        "properties": {
            "match": {
                "type": "boolean",
                "description": "True if A and B are the same startup.",
            },
            "reasoning": {
                "type": "string",
                "description": "One short sentence justifying the verdict.",
            },
        },
        "required": ["match", "reasoning"],
    },
}

DEFAULT_FUZZY_THRESHOLD = 0.6


# ---- Stage 1: canonical-id merge -----------------------------------------


def merge_with_existing(
    new: EnrichedStartup, *, db_path: Path = db.DEFAULT_DB_PATH
) -> EnrichedStartup:
    """Return a startup whose sources/source_urls include both the new and
    any previously persisted record for the same canonical_id.
    """
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT payload FROM enriched_startups WHERE canonical_id=?",
            (new.canonical_id,),
        ).fetchone()
    if row is None:
        return new
    try:
        existing = EnrichedStartup.model_validate_json(row["payload"])
    except (ValidationError, json.JSONDecodeError):
        return new

    sources = _dedup_keep_order([*existing.sources, *new.sources])
    source_urls = _dedup_keep_order([str(u) for u in (*existing.source_urls, *new.source_urls)])
    payload = new.model_dump()
    payload["sources"] = sources
    payload["source_urls"] = source_urls
    return EnrichedStartup.model_validate(payload)


# ---- Stage 2: pairwise LLM check -----------------------------------------


def pairwise_match_leads(
    *,
    db_path: Path = db.DEFAULT_DB_PATH,
    llm_call: Callable | None = None,
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
    limit: int | None = None,
) -> tuple[int, int]:
    """Iterate websiteless leads and merge them into matching enriched rows.

    Returns (n_checked, n_merged). `n_checked` counts (lead, candidate) pairs
    that went to Haiku; `n_merged` counts leads that ended up appended to an
    enriched record.
    """
    llm_call = llm_call or default_llm_call

    leads = _websiteless_leads(db_path=db_path, limit=limit)
    if not leads:
        return 0, 0
    enriched = _all_enriched(db_path=db_path)
    if not enriched:
        return 0, 0

    n_checked = 0
    n_merged = 0
    prompt_template = _load_prompt()

    for lead in leads:
        candidates = _shortlist(lead, enriched, threshold=fuzzy_threshold)
        for candidate in candidates:
            n_checked += 1
            if _is_match(lead, candidate, llm_call=llm_call, template=prompt_template):
                merged = _attach_lead_source(candidate, lead)
                with db.connect(db_path) as conn:
                    db.upsert_enriched(conn, merged)
                # Replace candidate in `enriched` so subsequent iterations see
                # the merged source list.
                for idx, e in enumerate(enriched):
                    if e.canonical_id == candidate.canonical_id:
                        enriched[idx] = merged
                        break
                n_merged += 1
                break  # one match per lead is enough
    return n_checked, n_merged


# ---- helpers --------------------------------------------------------------


def _shortlist(
    lead: RawLead, enriched: list[EnrichedStartup], *, threshold: float
) -> list[EnrichedStartup]:
    name = (lead.name or "").lower().strip()
    if not name:
        return []
    out: list[tuple[float, EnrichedStartup]] = []
    for e in enriched:
        candidate_name = (e.name or "").lower().strip()
        if not candidate_name:
            continue
        ratio = SequenceMatcher(None, name, candidate_name).ratio()
        if ratio >= threshold:
            out.append((ratio, e))
    out.sort(key=lambda pair: pair[0], reverse=True)
    return [e for _, e in out]


def _is_match(
    lead: RawLead,
    candidate: EnrichedStartup,
    *,
    llm_call: Callable,
    template: str,
) -> bool:
    a = lead.model_dump_json(indent=2)
    b = candidate.model_dump_json(indent=2)
    prompt = template.replace("{{record_a}}", a).replace("{{record_b}}", b)
    try:
        out = llm_call(prompt, DEDUP_TOOL, model=HAIKU)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"dedup: pairwise check failed — {e}")
        return False
    return bool(out.get("match"))


def _attach_lead_source(candidate: EnrichedStartup, lead: RawLead) -> EnrichedStartup:
    sources = _dedup_keep_order([*candidate.sources, lead.source])
    source_urls = [str(u) for u in candidate.source_urls]
    payload = candidate.model_dump()
    payload["sources"] = sources
    payload["source_urls"] = source_urls
    payload["last_enriched"] = datetime.utcnow()
    return EnrichedStartup.model_validate(payload)


def _websiteless_leads(*, db_path: Path, limit: int | None) -> list[RawLead]:
    out: list[RawLead] = []
    with db.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT source, source_id, name, website, one_liner,
                   discovered_at, raw_payload
            FROM leads
            WHERE website IS NULL OR website = ''
            ORDER BY discovered_at DESC
            """
        ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["raw_payload"]) if row["raw_payload"] else {}
        except json.JSONDecodeError:
            payload = {}
        try:
            lead = RawLead(
                source=Source(row["source"]),
                source_id=row["source_id"],
                name=row["name"],
                website=None,
                one_liner=row["one_liner"],
                discovered_at=_parse_ts(row["discovered_at"]) or datetime.utcnow(),
                raw_payload=payload,
            )
        except ValidationError:
            continue
        out.append(lead)
        if limit is not None and len(out) >= limit:
            break
    return out


def _all_enriched(*, db_path: Path) -> list[EnrichedStartup]:
    out: list[EnrichedStartup] = []
    with db.connect(db_path) as conn:
        rows = conn.execute("SELECT payload FROM enriched_startups").fetchall()
    for row in rows:
        try:
            out.append(EnrichedStartup.model_validate_json(row["payload"]))
        except (ValidationError, json.JSONDecodeError):
            continue
    return out


def _parse_ts(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _dedup_keep_order(seq: list) -> list:
    """Stable dedup. Works for hashables; falls back to `str()` for the rest."""
    seen: set = set()
    out: list = []
    for item in seq:
        try:
            key = item if isinstance(item, (str, int, bytes)) else str(item)
        except Exception:  # noqa: BLE001
            key = repr(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _load_prompt() -> str:
    return DEDUP_PROMPT_PATH.read_text()
