"""Shared AI-native extraction for listing-style pages (universities, Beta
List, EXIST). Each collector fetches a page through the standard fetch chain,
then asks Claude Sonnet to enumerate the startups mentioned on that page using
the `record_startups` tool. See §6.2 for the pattern.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..llm import SONNET
from ..llm import cached_call as default_llm_call

LISTING_PROMPT_PATH = Path("prompts/extract_listing.txt")
LISTING_TOOL = {
    "name": "record_startups",
    "description": "Capture every startup or spin-off mentioned on a listing page.",
    "input_schema": {
        "type": "object",
        "properties": {
            "startups": {
                "type": "array",
                "description": "Every startup or spin-off found on the page.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Company or project name as printed on the page.",
                        },
                        "one_liner": {
                            "type": "string",
                            "description": "One-sentence description if visible.",
                        },
                        "website": {
                            "type": "string",
                            "description": "Homepage URL if explicitly linked.",
                        },
                        "founders": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Founder names if listed.",
                        },
                        "year": {
                            "type": "integer",
                            "description": "Founding / funding / launch year if stated.",
                        },
                        "location": {
                            "type": "string",
                            "description": "City, university, or country if stated.",
                        },
                    },
                    "required": ["name"],
                },
            }
        },
        "required": ["startups"],
    },
}

MAX_CONTENT_CHARS = 60_000


def extract_listing(
    content: str,
    *,
    source_hint: str,
    llm_call: Callable | None = None,
    model: str = SONNET,
) -> list[dict]:
    """Run the AI-native extraction on `content`. Returns a list of dicts.

    Each returned dict has at least `name`; other fields may be null or absent.
    Returns [] on LLM errors so a single bad page doesn't sink a whole run.
    """
    llm_call = llm_call or default_llm_call

    body = content[:MAX_CONTENT_CHARS]
    prompt = (
        _load_prompt()
        .replace("{{source_hint}}", source_hint)
        .replace("{{content}}", body)
    )

    try:
        result = llm_call(prompt, LISTING_TOOL, model=model)
    except Exception:
        return []

    items = result.get("startups") or []
    return [item for item in items if isinstance(item, dict) and item.get("name")]


def _load_prompt() -> str:
    return LISTING_PROMPT_PATH.read_text()
