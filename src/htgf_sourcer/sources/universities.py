"""University TTO collector (§6.2).

Config-driven. For each entry in `config/universities.yaml`, fetch the
`spinoff_url` through the fetch chain and AI-extract startup entries via
`_ai_listing`. Each extracted entry becomes a `RawLead` with the university
name as the location hint.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import yaml
from loguru import logger
from pydantic import ValidationError

from ..fetch import fetch as default_fetch
from ..models import RawLead, Source
from ._ai_listing import extract_listing
from .base import Collector

CONFIG_PATH = Path("config/universities.yaml")


class UniversityCollector(Collector):
    source = Source.UNIVERSITY

    def __init__(
        self,
        *,
        fetch_fn: Callable | None = None,
        llm_call: Callable | None = None,
        config_path: Path | None = None,
    ) -> None:
        self._fetch_fn = fetch_fn or default_fetch
        self._llm_call = llm_call
        self._config_path = config_path or CONFIG_PATH

    async def collect(
        self,
        since: datetime | None = None,
        *,
        limit: int | None = None,
    ) -> list[RawLead]:
        entries = self._load_config()
        if not entries:
            logger.warning(f"universities: no entries in {self._config_path}")
            return []

        leads: list[RawLead] = []
        for entry in entries:
            university = entry.get("name") or "(unknown)"
            for key in ("spinoff_url", "news_url"):
                url = entry.get(key)
                if not url:
                    continue

                page = await self._fetch_fn(url)
                if page is None:
                    logger.warning(f"universities: fetch failed for {url}")
                    continue

                items = extract_listing(
                    page.content,
                    source_hint=f"university spin-off listing for {university}",
                    llm_call=self._llm_call,
                )
                for item in items:
                    lead = _to_lead(item, university=university, source_url=url)
                    if lead is None:
                        continue
                    leads.append(lead)
                    if limit is not None and len(leads) >= limit:
                        return leads
        return leads

    def _load_config(self) -> list[dict]:
        if not self._config_path.exists():
            return []
        data = yaml.safe_load(self._config_path.read_text()) or {}
        return data.get("universities") or []


def _to_lead(item: dict, *, university: str, source_url: str) -> RawLead | None:
    name = (item.get("name") or "").strip()
    if not name:
        return None
    source_id = hashlib.sha256(f"{university}:{name}".encode()).hexdigest()[:16]
    website = (item.get("website") or "").strip() or None
    try:
        return RawLead(
            source=Source.UNIVERSITY,
            source_id=source_id,
            name=name,
            website=website,
            one_liner=item.get("one_liner") or None,
            location_hint=university,
            discovered_at=datetime.utcnow(),
            raw_payload={
                "source_url": source_url,
                "year": item.get("year"),
                "founders": item.get("founders") or [],
                "university": university,
            },
        )
    except ValidationError:
        return None
