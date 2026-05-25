"""Product Hunt collector (§6.6).

Pulls top posts in the last 90 days via the v2 GraphQL API. Geography is NOT
filtered at this stage — the PH v2 API only exposes a JS-redirect tracking URL
for each post's external website, so cheap DACH detection is impossible. The
HTGF thesis prompt (`prompts/score_startup.txt`) already penalizes non-DACH
startups via the `thesis_fit` dimension; relying on that downstream filter is
the right tradeoff for a global funnel.

For each post we use the Product Hunt **product page URL** (`/products/SLUG`)
as the lead's `website`. That page is fetchable by Jina and contains the
product description + "Visit Website" link, which the LLM extracts into a
proper `EnrichedStartup` downstream.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import httpx
from loguru import logger
from pydantic import ValidationError

from ..models import RawLead, Source
from .base import Collector

GRAPHQL_ENDPOINT = "https://api.producthunt.com/v2/api/graphql"
DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_PAGE_SIZE = 50
DEFAULT_MAX_PAGES = 4
DEFAULT_MIN_VOTES = 10

GRAPHQL_QUERY = """
query Posts($postedAfter: DateTime, $cursor: String) {
  posts(first: 50, order: VOTES, postedAfter: $postedAfter, after: $cursor) {
    edges {
      cursor
      node {
        id
        slug
        name
        tagline
        url
        website
        votesCount
        createdAt
        makers {
          name
          headline
          websiteUrl
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
""".strip()


class ProductHuntCollector(Collector):
    source = Source.PRODUCTHUNT

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        token: str | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        min_votes: int = DEFAULT_MIN_VOTES,
    ) -> None:
        self._transport = transport
        self._token = token if token is not None else os.environ.get("PRODUCT_HUNT_TOKEN")
        self._max_pages = max_pages
        self._min_votes = min_votes

    async def collect(
        self,
        since: datetime | None = None,
        *,
        limit: int | None = None,
    ) -> list[RawLead]:
        if not self._token:
            logger.warning("producthunt: PRODUCT_HUNT_TOKEN unset — skipping collector")
            return []

        if since is None:
            since = datetime.now(UTC) - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        posted_after = since.astimezone(UTC).isoformat()

        leads: list[RawLead] = []
        cursor: str | None = None

        async with self._make_client() as client:
            for _ in range(self._max_pages):
                payload = {
                    "query": GRAPHQL_QUERY,
                    "variables": {"postedAfter": posted_after, "cursor": cursor},
                }
                r = await client.post(GRAPHQL_ENDPOINT, json=payload)
                if r.status_code != 200:
                    logger.warning(f"producthunt: graphql failed ({r.status_code})")
                    break
                data = r.json()
                posts = (data.get("data") or {}).get("posts") or {}
                edges = posts.get("edges") or []
                page_info = posts.get("pageInfo") or {}

                for edge in edges:
                    node = edge.get("node") or {}
                    if (node.get("votesCount") or 0) < self._min_votes:
                        continue
                    lead = _to_lead(node)
                    if lead is None:
                        continue
                    leads.append(lead)
                    if limit is not None and len(leads) >= limit:
                        return leads

                if not page_info.get("hasNextPage"):
                    break
                cursor = page_info.get("endCursor")
                if not cursor:
                    break
        return leads

    def _make_client(self) -> httpx.AsyncClient:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "User-Agent": "htgf-sourcer/0.1",
        }
        kwargs: dict = {"timeout": httpx.Timeout(30.0, connect=10.0), "headers": headers}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)


def _to_lead(node: dict) -> RawLead | None:
    name = (node.get("name") or "").strip()
    if not name:
        return None
    # Use the PH product page (`/products/SLUG`) — fetchable, has real content.
    # `node.website` is a JS-redirect tracker, useless to Jina.
    product_url = (node.get("url") or "").strip() or None
    try:
        return RawLead(
            source=Source.PRODUCTHUNT,
            source_id=str(node.get("id") or node.get("slug") or name),
            name=name,
            website=product_url,
            one_liner=node.get("tagline") or None,
            discovered_at=datetime.now(UTC),
            raw_payload={
                "slug": node.get("slug"),
                "votes": node.get("votesCount"),
                "created_at": node.get("createdAt"),
                "external_website_redirect": node.get("website"),
                "makers": node.get("makers") or [],
            },
        )
    except ValidationError:
        return None


__all__ = ["ProductHuntCollector", "GRAPHQL_ENDPOINT"]
