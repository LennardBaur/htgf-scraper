"""LLM cache tests. No real Anthropic calls."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from htgf_sourcer import db, llm

# ---- fakes ---------------------------------------------------------------


@dataclass
class FakeUsage:
    input_tokens: int = 1000
    output_tokens: int = 500


@dataclass
class FakeToolUseBlock:
    type: str
    name: str
    input: dict


@dataclass
class FakeResponse:
    content: list
    usage: FakeUsage


class FakeMessages:
    def __init__(self, payload: dict, name: str):
        self.payload = payload
        self.name = name
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return FakeResponse(
            content=[FakeToolUseBlock(type="tool_use", name=self.name, input=self.payload)],
            usage=FakeUsage(),
        )


class FakeClient:
    def __init__(self, payload: dict, name: str):
        self.messages = FakeMessages(payload, name)


# ---- fixtures ------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "state.db"
    db.init_db(p)
    return p


@pytest.fixture
def tool() -> dict:
    return {
        "name": "record_demo",
        "description": "demo",
        "input_schema": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    }


# ---- tests ---------------------------------------------------------------


def test_cached_call_returns_tool_input_and_stores_row(db_path: Path, tool: dict):
    fake = FakeClient(payload={"value": "ok"}, name="record_demo")

    out = llm.cached_call(
        prompt="hello",
        tool=tool,
        model=llm.SONNET,
        client=fake,
        db_path=db_path,
    )

    assert out == {"value": "ok"}
    assert fake.messages.calls == 1

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT response, model, cost_usd FROM llm_cache").fetchall()
    assert len(rows) == 1
    response, model, cost = rows[0]
    assert model == llm.SONNET
    # 1000 input * $3/M + 500 output * $15/M = 0.003 + 0.0075 = 0.0105
    assert cost == pytest.approx(0.0105)


def test_cache_hit_skips_second_api_call(db_path: Path, tool: dict):
    fake = FakeClient(payload={"value": "first"}, name="record_demo")

    llm.cached_call(prompt="hello", tool=tool, model=llm.SONNET, client=fake, db_path=db_path)

    # If the cache is honoured, the client should NOT be invoked a second
    # time. Pass a client whose .create raises if hit.
    class ExplodingClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise AssertionError("cache miss: should not have called the API")

    out2 = llm.cached_call(
        prompt="hello", tool=tool, model=llm.SONNET, client=ExplodingClient, db_path=db_path
    )
    assert out2 == {"value": "first"}


def test_different_prompt_misses_cache(db_path: Path, tool: dict):
    fake = FakeClient(payload={"value": "a"}, name="record_demo")
    llm.cached_call(prompt="prompt-A", tool=tool, client=fake, db_path=db_path)

    fake2 = FakeClient(payload={"value": "b"}, name="record_demo")
    out = llm.cached_call(prompt="prompt-B", tool=tool, client=fake2, db_path=db_path)
    assert out == {"value": "b"}
    assert fake2.messages.calls == 1


def test_pydantic_tool_helper_builds_valid_schema():
    from htgf_sourcer.models import Founder

    tool = llm.pydantic_tool(Founder, "record_founder", "Capture a single founder.")
    assert tool["name"] == "record_founder"
    assert tool["description"] == "Capture a single founder."
    assert tool["input_schema"]["type"] == "object"
    assert "name" in tool["input_schema"]["properties"]


def test_estimate_cost_unknown_model_returns_zero():
    assert llm.estimate_cost("unknown-model", FakeUsage()) == 0.0


def test_cached_call_rejects_invalid_tool(db_path: Path):
    with pytest.raises(ValueError):
        llm.cached_call(prompt="x", tool={"name": "no-schema"}, db_path=db_path)


def test_max_spend_aborts_second_call(db_path: Path, tool: dict):
    """First call exceeds the cap → caches its result, but the *next* call raises."""
    llm.set_max_spend(0.005)  # below 1 single Sonnet call cost (≈ $0.0105)
    try:
        fake = FakeClient(payload={"value": "first"}, name="record_demo")
        # First call: succeeds (returns), then sees total > cap and raises.
        with pytest.raises(llm.BudgetExceeded):
            llm.cached_call(
                prompt="hello", tool=tool, client=fake, db_path=db_path
            )
        # The first response WAS cached so a re-run is free and does not re-trip.
        out = llm.cached_call(
            prompt="hello", tool=tool, client=fake, db_path=db_path
        )
        assert out == {"value": "first"}
    finally:
        llm.set_max_spend(None)


def test_max_spend_disabled_when_none(db_path: Path, tool: dict):
    llm.set_max_spend(None)
    fake = FakeClient(payload={"value": "ok"}, name="record_demo")
    out = llm.cached_call(prompt="x", tool=tool, client=fake, db_path=db_path)
    assert out == {"value": "ok"}
