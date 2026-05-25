"""Handelsregister stub — verify it returns empty without raising."""

from __future__ import annotations

import asyncio

from htgf_sourcer.sources.handelsregister import HandelsregisterCollector


def test_handelsregister_stub_returns_empty():
    collector = HandelsregisterCollector()
    assert asyncio.run(collector.collect()) == []
    assert asyncio.run(collector.collect(limit=10)) == []
