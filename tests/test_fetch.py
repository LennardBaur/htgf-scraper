"""Fetch chain tests with no network access."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from htgf_sourcer import db, fetch


@pytest.fixture
def tmp_paths(tmp_path: Path) -> tuple[Path, Path]:
    db_path = tmp_path / "state.db"
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    db.init_db(db_path)
    return db_path, pages_dir


def _run(coro):
    return asyncio.run(coro)


def test_normalize_url_strips_www_utm_and_trailing_slash():
    assert (
        fetch.normalize_url("https://WWW.Example.com/About/?utm_source=x&q=1")
        == "https://example.com/About?q=1"
    )


def test_jina_path_used_when_jina_returns_content(monkeypatch, tmp_paths):
    db_path, pages_dir = tmp_paths
    calls = []

    async def fake_jina(url):
        calls.append(("jina", url))
        return "# Hello\nMarkdown body."

    async def fake_firecrawl(url):
        calls.append(("firecrawl", url))
        return "should not be reached"

    async def fake_playwright(url):
        calls.append(("playwright", url))
        return "should not be reached"

    monkeypatch.setattr(fetch, "_fetch_jina", fake_jina)
    monkeypatch.setattr(fetch, "_fetch_firecrawl", fake_firecrawl)
    monkeypatch.setattr(fetch, "_fetch_playwright", fake_playwright)

    result = _run(fetch.fetch("https://example.com/", db_path=db_path, pages_dir=pages_dir))

    assert result is not None
    assert result.fetcher == "jina"
    assert result.content.startswith("# Hello")
    assert [c[0] for c in calls] == ["jina"]


def test_falls_back_to_firecrawl_when_jina_empty(monkeypatch, tmp_paths):
    db_path, pages_dir = tmp_paths
    calls = []

    async def fake_jina(url):
        calls.append("jina")
        return None  # blocked / empty

    async def fake_firecrawl(url):
        calls.append("firecrawl")
        return "from firecrawl"

    async def fake_playwright(url):
        calls.append("playwright")
        return "from playwright"

    monkeypatch.setattr(fetch, "_fetch_jina", fake_jina)
    monkeypatch.setattr(fetch, "_fetch_firecrawl", fake_firecrawl)
    monkeypatch.setattr(fetch, "_fetch_playwright", fake_playwright)

    result = _run(fetch.fetch("https://example.com/", db_path=db_path, pages_dir=pages_dir))

    assert result is not None
    assert result.fetcher == "firecrawl"
    assert calls == ["jina", "firecrawl"]


def test_falls_back_to_playwright_when_jina_and_firecrawl_empty(monkeypatch, tmp_paths):
    db_path, pages_dir = tmp_paths

    async def empty(url):
        return None

    async def fake_playwright(url):
        return "rendered html text"

    monkeypatch.setattr(fetch, "_fetch_jina", empty)
    monkeypatch.setattr(fetch, "_fetch_firecrawl", empty)
    monkeypatch.setattr(fetch, "_fetch_playwright", fake_playwright)

    result = _run(fetch.fetch("https://example.com/", db_path=db_path, pages_dir=pages_dir))

    assert result is not None
    assert result.fetcher == "playwright"


def test_returns_none_when_all_fetchers_fail(monkeypatch, tmp_paths):
    db_path, pages_dir = tmp_paths

    async def empty(url):
        return None

    monkeypatch.setattr(fetch, "_fetch_jina", empty)
    monkeypatch.setattr(fetch, "_fetch_firecrawl", empty)
    monkeypatch.setattr(fetch, "_fetch_playwright", empty)

    result = _run(fetch.fetch("https://example.com/", db_path=db_path, pages_dir=pages_dir))
    assert result is None


def test_second_call_hits_disk_cache(monkeypatch, tmp_paths):
    db_path, pages_dir = tmp_paths
    call_count = {"n": 0}

    async def fake_jina(url):
        call_count["n"] += 1
        return "cached content"

    async def empty(url):
        return None

    monkeypatch.setattr(fetch, "_fetch_jina", fake_jina)
    monkeypatch.setattr(fetch, "_fetch_firecrawl", empty)
    monkeypatch.setattr(fetch, "_fetch_playwright", empty)

    first = _run(fetch.fetch("https://example.com/x", db_path=db_path, pages_dir=pages_dir))
    second = _run(fetch.fetch("https://example.com/x", db_path=db_path, pages_dir=pages_dir))

    assert first is not None and second is not None
    assert call_count["n"] == 1
    assert second.fetcher == "cache"
    assert second.content == first.content

    # Sidecar + content files on disk
    files = sorted(p.name for p in pages_dir.iterdir())
    assert any(f.endswith(".md") for f in files)
    assert any(f.endswith(".meta.json") for f in files)
