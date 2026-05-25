"""Tests for the shared AI-native listing helper (`sources/_ai_listing.py`)."""

from __future__ import annotations

from htgf_sourcer.sources._ai_listing import LISTING_TOOL, extract_listing


def test_extract_listing_returns_named_startups():
    captured: dict = {}

    def fake_llm(prompt, tool, **kwargs):
        captured["prompt"] = prompt
        captured["tool"] = tool
        return {
            "startups": [
                {"name": "Alpha", "one_liner": "AI ops"},
                {"name": "Beta GmbH", "website": "https://beta.de"},
                {"name": "", "one_liner": "empty"},  # filtered: no name
                "not a dict",  # filtered: not a dict
            ]
        }

    out = extract_listing(
        "# Some markdown\nAlpha and Beta GmbH...", source_hint="test page", llm_call=fake_llm
    )
    assert [s["name"] for s in out] == ["Alpha", "Beta GmbH"]
    assert captured["tool"]["name"] == "record_startups"
    assert "test page" in captured["prompt"]
    assert "# Some markdown" in captured["prompt"]


def test_extract_listing_returns_empty_on_llm_error():
    def angry_llm(prompt, tool, **kwargs):
        raise RuntimeError("boom")

    assert extract_listing("anything", source_hint="x", llm_call=angry_llm) == []


def test_listing_tool_schema_shape():
    assert LISTING_TOOL["name"] == "record_startups"
    props = LISTING_TOOL["input_schema"]["properties"]
    assert "startups" in props
    item_props = props["startups"]["items"]["properties"]
    for required_field in ("name", "one_liner", "website", "founders", "year", "location"):
        assert required_field in item_props
    assert LISTING_TOOL["input_schema"]["properties"]["startups"]["items"]["required"] == ["name"]
