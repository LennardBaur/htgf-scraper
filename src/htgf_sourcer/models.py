from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class Source(StrEnum):
    EXIST = "exist"
    UNIVERSITY = "university"
    HANDELSREGISTER = "handelsregister"
    GITHUB = "github"
    HACKERNEWS = "hackernews"
    PRODUCTHUNT = "producthunt"
    BETALIST = "betalist"


class Stage(StrEnum):
    PRE_INCORPORATION = "pre_incorporation"
    STEALTH = "stealth"
    PRE_LAUNCH = "pre_launch"
    PRE_SEED = "pre_seed"
    SEED = "seed"
    UNKNOWN = "unknown"


class RawLead(BaseModel):
    """Output of a Source collector. Lightweight, may be incomplete."""

    source: Source
    source_id: str
    name: str | None = None
    website: HttpUrl | None = None
    one_liner: str | None = None
    location_hint: str | None = None
    discovered_at: datetime
    raw_payload: dict = Field(default_factory=dict)


class Founder(BaseModel):
    name: str
    role: str | None = None
    linkedin_url: HttpUrl | None = None
    email: str | None = None
    background: str | None = None


class EnrichedStartup(BaseModel):
    """After fetch + LLM extraction."""

    canonical_id: str
    name: str
    website: HttpUrl | None = None
    one_liner: str
    long_description: str
    sector: str
    sub_sector: str | None = None
    hq_city: str | None = None
    hq_country: str | None = None
    founded_year: int | None = None
    incorporation_status: str | None = None
    stage_signal: Stage = Stage.UNKNOWN
    team_size_estimate: int | None = None
    founders: list[Founder] = Field(default_factory=list)
    traction_signals: list[str] = Field(default_factory=list)
    funding_signals: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    source_urls: list[HttpUrl] = Field(default_factory=list)
    last_enriched: datetime


class ExtractedStartup(BaseModel):
    """LLM extraction output. Narrower than EnrichedStartup: the orchestrator
    sets canonical_id, sources, source_urls, and last_enriched after the call,
    so we don't ask the LLM to invent them."""

    name: str
    website: HttpUrl | None = None
    one_liner: str
    long_description: str
    sector: str
    sub_sector: str | None = None
    hq_city: str | None = None
    hq_country: str | None = None
    founded_year: int | None = None
    incorporation_status: str | None = None
    stage_signal: Stage = Stage.UNKNOWN
    team_size_estimate: int | None = None
    founders: list[Founder] = Field(default_factory=list)
    traction_signals: list[str] = Field(default_factory=list)
    funding_signals: list[str] = Field(default_factory=list)


class ExtractedScore(BaseModel):
    """LLM scoring output. Orchestrator computes `overall` from weights and
    sets `canonical_id` + `scored_at` afterwards."""

    thesis_fit: int = Field(ge=1, le=5)
    team_quality: int = Field(ge=1, le=5)
    earliness: int = Field(ge=1, le=5)
    traction: int = Field(ge=1, le=5)
    contactability: int = Field(ge=1, le=5)
    rationale: str
    red_flags: list[str] = Field(default_factory=list)


class Score(BaseModel):
    """LLM-generated, per startup."""

    canonical_id: str
    thesis_fit: int = Field(ge=1, le=5)
    team_quality: int = Field(ge=1, le=5)
    earliness: int = Field(ge=1, le=5)
    traction: int = Field(ge=1, le=5)
    contactability: int = Field(ge=1, le=5)
    overall: float
    rationale: str
    red_flags: list[str] = Field(default_factory=list)
    scored_at: datetime
