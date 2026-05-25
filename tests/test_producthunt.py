"""Product Hunt collector — GraphQL mocked via httpx.MockTransport.

After the v2 of this collector dropped the DACH-only filter (HTGF can score
non-DACH startups via the thesis prompt — see prompts/score_startup.txt), the
filter logic here is just: votes >= min_votes and a non-empty name.
"""

from __future__ import annotations

import asyncio

import httpx

from htgf_sourcer.models import Source
from htgf_sourcer.sources.producthunt import GRAPHQL_ENDPOINT, ProductHuntCollector


def _post(name: str, *, votes: int = 100, post_id: str | None = None,
          website: str | None = None) -> dict:
    slug = name.lower().replace(" ", "-")
    return {
        "id": post_id or slug,
        "slug": slug,
        "name": name,
        "tagline": f"{name} tagline",
        "url": f"https://www.producthunt.com/products/{slug}",
        "website": website or f"https://www.producthunt.com/r/{slug.upper()}",
        "votesCount": votes,
        "createdAt": "2026-04-01T00:00:00Z",
        "makers": [],
    }


def _gql_handler(edges: list[dict], *, has_next: bool = False, end_cursor: str | None = None):
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.producthunt.com"
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(
            200,
            json={
                "data": {
                    "posts": {
                        "edges": edges,
                        "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
                    }
                }
            },
        )

    return handle


def test_producthunt_keeps_all_posts_globally():
    """No DACH filter — every post above the vote threshold is kept."""
    edges = [
        {"node": _post("DACHTool")},
        {"node": _post("USThing")},
        {"node": _post("AsianStartup")},
    ]
    transport = httpx.MockTransport(_gql_handler(edges))
    collector = ProductHuntCollector(transport=transport, token="fake", min_votes=10)
    leads = asyncio.run(collector.collect())

    names = sorted(lead.name for lead in leads)
    assert names == ["AsianStartup", "DACHTool", "USThing"]
    assert all(lead.source is Source.PRODUCTHUNT for lead in leads)


def test_producthunt_website_uses_product_page_not_redirect():
    """Lead website must be the PH /products/SLUG URL, not /r/HASHCODE."""
    edges = [{"node": _post("Demo Co")}]
    transport = httpx.MockTransport(_gql_handler(edges))
    collector = ProductHuntCollector(transport=transport, token="fake", min_votes=10)
    leads = asyncio.run(collector.collect())

    assert len(leads) == 1
    website = str(leads[0].website)
    assert "/products/demo-co" in website
    assert "/r/" not in website
    # The original redirect is preserved in raw_payload for reference.
    assert "/r/" in leads[0].raw_payload["external_website_redirect"]


def test_producthunt_filters_below_min_votes():
    edges = [
        {"node": _post("Popular", votes=200)},
        {"node": _post("Niche", votes=5)},  # below default min_votes=10
    ]
    transport = httpx.MockTransport(_gql_handler(edges))
    collector = ProductHuntCollector(transport=transport, token="fake", min_votes=10)
    leads = asyncio.run(collector.collect())

    assert [lead.name for lead in leads] == ["Popular"]


def test_producthunt_skips_when_no_token():
    collector = ProductHuntCollector(token="")
    leads = asyncio.run(collector.collect())
    assert leads == []


def test_producthunt_handles_graphql_error_gracefully():
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"errors": ["boom"]})

    transport = httpx.MockTransport(handle)
    collector = ProductHuntCollector(transport=transport, token="fake")
    leads = asyncio.run(collector.collect())
    assert leads == []


def test_producthunt_endpoint_is_https():
    assert GRAPHQL_ENDPOINT.startswith("https://")


def test_producthunt_respects_limit():
    edges = [{"node": _post(f"P{i}")} for i in range(5)]
    transport = httpx.MockTransport(_gql_handler(edges))
    collector = ProductHuntCollector(transport=transport, token="fake", min_votes=10)
    leads = asyncio.run(collector.collect(limit=2))
    assert len(leads) == 2
