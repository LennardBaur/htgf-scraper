"""GitHub collector — MockTransport for /search/users + /users/{login}/repos."""

from __future__ import annotations

import asyncio

import httpx

from htgf_sourcer.models import Source
from htgf_sourcer.sources.github import GithubCollector


def _repo(name: str, *, homepage: str | None = None, stars: int = 25) -> dict:
    return {
        "id": hash(name) & 0xFFFF,
        "name": name.split("/")[-1],
        "full_name": name,
        "html_url": f"https://github.com/{name}",
        "description": f"Project {name}",
        "homepage": homepage,
        "stargazers_count": stars,
        "language": "TypeScript",
        "created_at": "2026-03-15T00:00:00Z",
        "fork": False,
        "archived": False,
        "owner": {"login": name.split("/")[0]},
        "topics": [],
    }


def _user(login: str) -> dict:
    return {"login": login, "id": hash(login) & 0xFFFF, "type": "User"}


def _make_handler(
    *,
    users_by_location: dict[str, list[dict]],
    repos_by_user: dict[str, list[dict]],
):
    """Route /search/users and /users/{login}/repos to canned responses."""

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/search/users":
            q = request.url.params.get("q", "")
            for location, items in users_by_location.items():
                if f"location:{location}" in q:
                    return httpx.Response(200, json={"items": items, "total_count": len(items)})
            return httpx.Response(200, json={"items": [], "total_count": 0})
        if path.startswith("/users/") and path.endswith("/repos"):
            login = path[len("/users/"):-len("/repos")]
            return httpx.Response(200, json=repos_by_user.get(login, []))
        return httpx.Response(404, json={"message": "not found"})

    return handle


def test_github_collects_repos_for_dach_users():
    users_by_location = {
        "Germany": [_user("berlin_dev"), _user("munich_dev")],
        "Austria": [_user("vienna_dev")],
    }
    repos_by_user = {
        "berlin_dev": [_repo("berlin_dev/devtool", homepage="https://devtool.io")],
        "munich_dev": [_repo("munich_dev/saaskit", homepage="https://saaskit.com")],
        "vienna_dev": [_repo("vienna_dev/dataops")],  # no homepage; should fall back to repo URL
    }

    transport = httpx.MockTransport(
        _make_handler(users_by_location=users_by_location, repos_by_user=repos_by_user)
    )
    collector = GithubCollector(
        transport=transport,
        token="fake",
        locations=["Germany", "Austria"],
        min_stars=10,
    )
    leads = asyncio.run(collector.collect())

    kept = sorted(lead.source_id for lead in leads)
    assert kept == ["berlin_dev/devtool", "munich_dev/saaskit", "vienna_dev/dataops"]
    assert all(lead.source is Source.GITHUB for lead in leads)
    # location_hint comes from the search-by-location step.
    by_id = {lead.source_id: lead for lead in leads}
    assert by_id["berlin_dev/devtool"].location_hint == "Germany"
    assert by_id["vienna_dev/dataops"].location_hint == "Austria"
    # No-homepage repo fell back to its github.com URL so enrichment has something to fetch.
    assert "github.com/vienna_dev/dataops" in str(by_id["vienna_dev/dataops"].website)


def test_github_skips_forks_archived_and_low_stars():
    forked = _repo("user1/forked")
    forked["fork"] = True
    archived = _repo("user1/archived")
    archived["archived"] = True
    low_star = _repo("user1/tiny", stars=2)
    fresh_good = _repo("user1/winner", homepage="https://winner.de")

    users = {"Germany": [_user("user1")]}
    repos = {"user1": [forked, archived, low_star, fresh_good]}
    transport = httpx.MockTransport(
        _make_handler(users_by_location=users, repos_by_user=repos)
    )

    collector = GithubCollector(
        transport=transport, token="fake", locations=["Germany"], min_stars=10
    )
    leads = asyncio.run(collector.collect())
    assert [lead.source_id for lead in leads] == ["user1/winner"]


def test_github_skips_when_no_token():
    collector = GithubCollector(token="")
    leads = asyncio.run(collector.collect())
    assert leads == []


def test_github_respects_limit():
    users = {"Germany": [_user(f"dev{i}") for i in range(5)]}
    repos = {f"dev{i}": [_repo(f"dev{i}/proj")] for i in range(5)}
    transport = httpx.MockTransport(
        _make_handler(users_by_location=users, repos_by_user=repos)
    )

    collector = GithubCollector(
        transport=transport, token="fake", locations=["Germany"], min_stars=10
    )
    leads = asyncio.run(collector.collect(limit=3))
    assert len(leads) == 3


def test_github_handles_search_failure_gracefully():
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "rate limit"})

    transport = httpx.MockTransport(handle)
    collector = GithubCollector(transport=transport, token="fake", locations=["Germany"])
    leads = asyncio.run(collector.collect())
    assert leads == []
