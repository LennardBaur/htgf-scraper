"""Collector abstract base. Every source implements this interface (§6)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..models import RawLead, Source


class Collector(ABC):
    """Async collector that pulls leads from a single source."""

    source: Source

    @abstractmethod
    async def collect(self, since: datetime | None = None) -> list[RawLead]:
        """Return RawLead rows discovered since `since` (defaults to source's lookback)."""
        ...
