"""Handelsregister collector — deferred to v2 (§6.3).

OffeneRegister bulk data is messy and the `purpose` field is sparse, so the
signal-to-noise ratio is poor without further normalization. Step 8 may
revisit if there's time; for now this collector always returns an empty list
and is disabled in config/sources.yaml.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from ..models import RawLead, Source
from .base import Collector


class HandelsregisterCollector(Collector):
    source = Source.HANDELSREGISTER

    async def collect(
        self,
        since: datetime | None = None,
        *,
        limit: int | None = None,
    ) -> list[RawLead]:
        logger.info("handelsregister collector is a stub (deferred to v2)")
        return []
