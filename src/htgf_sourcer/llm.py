"""Anthropic wrapper with request-hashed caching and cost tracking (§10).

Every call goes through `cached_call`. If the same (model, prompt, tool) tuple
has been seen before, the cached tool input is returned without a network hit
or any cost. Otherwise the SDK is invoked, the tool's input dict is extracted
from the response, the result is persisted to `llm_cache`, and the dollar cost
is computed from token usage.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from . import db

# Model IDs per the Anthropic API at the time of writing.
SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"

# USD per million tokens (input, output).
PRICING: dict[str, tuple[float, float]] = {
    SONNET: (3.0, 15.0),
    HAIKU: (1.0, 5.0),
}


class BudgetExceeded(RuntimeError):
    """Raised by `cached_call` when cumulative LLM spend exceeds the cap."""


# Module-level cap (USD). `None` disables. Set by the CLI from `--max-spend`.
_MAX_SPEND_USD: float | None = None


def set_max_spend(usd: float | None) -> None:
    """Set / clear the cumulative-spend cap honored by `cached_call`."""
    global _MAX_SPEND_USD
    _MAX_SPEND_USD = usd


def cached_call(
    prompt: str,
    tool: dict,
    model: str = SONNET,
    *,
    max_tokens: int = 4096,
    client: Any | None = None,
    db_path: Path = db.DEFAULT_DB_PATH,
) -> dict:
    """Run an Anthropic tool-use call and return the tool input dict.

    Cached by sha256(model + prompt + tool-schema). The cache is hit on
    repeat runs, which is what makes reviewer re-runs free (§10).
    """
    if "name" not in tool or "input_schema" not in tool:
        raise ValueError("tool must be an Anthropic tool dict with name + input_schema")

    request_hash = _request_hash(model, prompt, tool)

    cached = _get_cached(request_hash, db_path)
    if cached is not None:
        return cached

    if client is None:
        client = _make_client()

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": prompt}],
    )

    tool_input = _extract_tool_input(response, tool["name"])
    cost = estimate_cost(model, response.usage)
    _store(request_hash, response_payload=tool_input, model=model, cost=cost, db_path=db_path)

    # Budget enforcement: after every paid call, check cumulative spend. We
    # let the in-flight call complete so the result is cached (and not paid
    # for again on retry), but refuse to start the next one.
    if _MAX_SPEND_USD is not None:
        with db.connect(db_path) as conn:
            total = db.total_llm_cost(conn)
        if total > _MAX_SPEND_USD:
            raise BudgetExceeded(
                f"LLM spend ${total:.4f} exceeds cap ${_MAX_SPEND_USD:.4f} "
                f"(--max-spend). Run with a higher cap or inspect cost via `sourcer status`."
            )
    return tool_input


def pydantic_tool(model_cls, name: str, description: str = "") -> dict:
    """Build an Anthropic tool dict from a Pydantic model class."""
    schema = model_cls.model_json_schema()
    return {
        "name": name,
        "description": description or f"Record a {model_cls.__name__}.",
        "input_schema": schema,
    }


def estimate_cost(model: str, usage) -> float:
    """USD cost from token usage. 0.0 if pricing unknown."""
    pricing = PRICING.get(model)
    if pricing is None:
        return 0.0
    input_per_m, output_per_m = pricing
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    return (input_tokens / 1_000_000) * input_per_m + (output_tokens / 1_000_000) * output_per_m


# ---- internals ------------------------------------------------------------


def _request_hash(model: str, prompt: str, tool: dict) -> str:
    payload = json.dumps({"model": model, "prompt": prompt, "tool": tool}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_cached(request_hash: str, db_path: Path) -> dict | None:
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT response FROM llm_cache WHERE request_hash=?",
            (request_hash,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["response"])


def _store(
    request_hash: str,
    *,
    response_payload: dict,
    model: str,
    cost: float,
    db_path: Path,
) -> None:
    with db.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO llm_cache (request_hash, response, model, cost_usd, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(request_hash) DO UPDATE SET
                response=excluded.response,
                model=excluded.model,
                cost_usd=excluded.cost_usd,
                created_at=excluded.created_at
            """,
            (
                request_hash,
                json.dumps(response_payload),
                model,
                cost,
                datetime.utcnow(),
            ),
        )


def _extract_tool_input(response, tool_name: str) -> dict:
    for block in response.content:
        block_type = getattr(block, "type", None)
        if block_type == "tool_use" and getattr(block, "name", None) == tool_name:
            return dict(getattr(block, "input", {}))
    raise RuntimeError(f"Anthropic response did not include a tool_use block for {tool_name!r}")


def _make_client():
    """Lazy import so tests / cache-only runs don't require the SDK."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set; run `sourcer doctor`")
    from anthropic import Anthropic

    return Anthropic()
