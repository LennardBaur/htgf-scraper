"""GitHub collector (§6.4).

Strategy (v2):
1. Use `/search/users?q=location:<DACH>` to find developers explicitly located
   in Germany / Austria / Switzerland (or major DACH cities).
2. For each user, list their recent non-fork, non-archived original repos via
   `/users/{login}/repos`.
3. Filter by `created_at >= since` and `stars >= min_stars`.
4. Attribute `location_hint` from the search query so downstream scoring sees
   the DACH signal.

v1 used a `/search/repositories` query with a `.de`/`.at`/`.ch` TLD filter on
the homepage. That missed 90% of real DACH startups, which use `.com`/`.ai`/
`.io`/`.dev` for international markets. The user-based approach above gives
real DACH yield.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx
from loguru import logger
from pydantic import ValidationError

from ..models import RawLead, Source
from .base import Collector

USER_SEARCH_ENDPOINT = "https://api.github.com/search/users"
USER_REPOS_TEMPLATE = "https://api.github.com/users/{login}/repos"

# Major DACH location qualifiers. Order matters — Germany first, then larger
# cities, then AT/CH. Each gets its own search call.
DACH_LOCATIONS = ["Germany", "Berlin", "Munich", "Austria", "Vienna", "Switzerland", "Zurich"]

DEFAULT_MIN_STARS = 10
DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_USERS_PER_LOCATION = 20
DEFAULT_REPOS_PER_USER = 10
MIN_FOLLOWERS = 5


class GithubCollector(Collector):
    source = Source.GITHUB

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        token: str | None = None,
        locations: list[str] | None = None,
        min_stars: int = DEFAULT_MIN_STARS,
        users_per_location: int = DEFAULT_USERS_PER_LOCATION,
        repos_per_user: int = DEFAULT_REPOS_PER_USER,
    ) -> None:
        self._transport = transport
        self._token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        self._locations = locations or list(DACH_LOCATIONS)
        self._min_stars = min_stars
        self._users_per_location = users_per_location
        self._repos_per_user = repos_per_user

    async def collect(
        self,
        since: datetime | None = None,
        *,
        limit: int | None = None,
    ) -> list[RawLead]:
        if not self._token:
            logger.warning("github: GITHUB_TOKEN unset — skipping collector")
            return []

        if since is None:
            since = datetime.utcnow() - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        since_date = since.strftime("%Y-%m-%d")

        leads: list[RawLead] = []
        seen_full_names: set[str] = set()

        async with self._make_client() as client:
            for location in self._locations:
                if limit is not None and len(leads) >= limit:
                    break
                users = await self._search_users(client, location)
                for user in users:
                    if limit is not None and len(leads) >= limit:
                        break
                    repos = await self._user_repos(client, user["login"], since_date)
                    for repo in repos:
                        if limit is not None and len(leads) >= limit:
                            break
                        full_name = repo.get("full_name") or ""
                        if not full_name or full_name in seen_full_names:
                            continue
                        seen_full_names.add(full_name)
                        lead = _to_lead(repo, location_hint=location)
                        if lead is None:
                            continue
                        leads.append(lead)
        return leads

    def _make_client(self) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "htgf-sourcer/0.1",
            "Authorization": f"Bearer {self._token}",
        }
        kwargs: dict = {"timeout": httpx.Timeout(30.0, connect=10.0), "headers": headers}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def _search_users(self, client: httpx.AsyncClient, location: str) -> list[dict]:
        q = f"location:{location} followers:>={MIN_FOLLOWERS} type:user"
        params = {
            "q": q,
            "sort": "followers",
            "order": "desc",
            "per_page": self._users_per_location,
        }
        r = await client.get(USER_SEARCH_ENDPOINT, params=params)
        if r.status_code != 200:
            logger.warning(f"github: user search failed ({r.status_code}) for {location}")
            return []
        return (r.json().get("items") or [])

    async def _user_repos(
        self, client: httpx.AsyncClient, login: str, since_date: str
    ) -> list[dict]:
        url = USER_REPOS_TEMPLATE.format(login=login)
        params = {"type": "owner", "sort": "updated", "per_page": self._repos_per_user}
        r = await client.get(url, params=params)
        if r.status_code != 200:
            return []
        return [
            repo
            for repo in (r.json() or [])
            if not repo.get("fork")
            and not repo.get("archived")
            and (repo.get("stargazers_count") or 0) >= self._min_stars
            and (repo.get("created_at") or "") >= since_date + "T00:00:00Z"
        ]


def _to_lead(item: dict, *, location_hint: str) -> RawLead | None:
    full_name = item.get("full_name") or ""
    if not full_name:
        return None
    homepage = (item.get("homepage") or "").strip() or None
    # Fall back to the repo HTML URL as a website so downstream enrichment has
    # something to fetch (the README / repo description) even if no homepage.
    website = homepage or item.get("html_url")
    name = item.get("name") or full_name.split("/", 1)[-1]
    try:
        return RawLead(
            source=Source.GITHUB,
            source_id=full_name,
            name=name,
            website=website,
            one_liner=item.get("description") or None,
            location_hint=location_hint,
            discovered_at=datetime.utcnow(),
            raw_payload={
                "full_name": full_name,
                "stars": item.get("stargazers_count"),
                "language": item.get("language"),
                "created_at": item.get("created_at"),
                "owner_login": (item.get("owner") or {}).get("login"),
                "html_url": item.get("html_url"),
                "topics": item.get("topics") or [],
            },
        )
    except ValidationError:
        return None
