"""German one-pager generator. Template per PLAN.md §12.2."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from ..models import EnrichedStartup, Score

ONE_PAGER_TEMPLATE = """\
# {name}

**Rang:** {rank} / {total}   **Score:** {overall:.2f} / 5.00

| | |
|---|---|
| Website | {website_md} |
| Sitz | {hq_line} |
| Gegründet | {founded} |
| Stage | {stage_label} |
| Sektor | {sector_line} |

## In einem Satz
{one_liner}

## Was sie machen
{long_description}

## Gründer
{founders_block}

## Traction
{traction_block}

## Finanzierung
{funding_block}

## Bewertung (LLM)

| Dimension | Score |
|---|---|
| Thesis-Fit | {thesis_fit}/5 |
| Team-Qualität | {team_quality}/5 |
| Frühphasen-Vorteil | {earliness}/5 |
| Traction | {traction_score}/5 |
| Erreichbarkeit | {contactability}/5 |

**Begründung:** {rationale}

**Red Flags:**
{red_flags_block}

## Quellen
{sources_block}

---
*Generiert am {scored_at} · canonical_id: `{canonical_id}`*
"""

STAGE_LABELS_DE = {
    "pre_incorporation": "Vor Gründung",
    "stealth": "Stealth",
    "pre_launch": "Pre-Launch",
    "pre_seed": "Pre-Seed",
    "seed": "Seed",
    "unknown": "Unbekannt",
}

EM_DASH = "—"


def write_onepager(
    startup: EnrichedStartup,
    score: Score,
    *,
    rank: int,
    total: int,
    out_dir: Path,
) -> Path:
    """Render and write a German one-pager. Returns the written path."""
    out_dir.mkdir(parents=True, exist_ok=True)

    sector_line = startup.sector
    if startup.sub_sector:
        sector_line += f" · {startup.sub_sector}"

    hq_parts = [startup.hq_city, startup.hq_country]
    hq_line = ", ".join(p for p in hq_parts if p) or EM_DASH

    if startup.website:
        web = str(startup.website)
        website_md = f"[{web}]({web})"
    else:
        website_md = EM_DASH

    content = ONE_PAGER_TEMPLATE.format(
        name=startup.name,
        rank=rank,
        total=total,
        overall=score.overall,
        website_md=website_md,
        hq_line=hq_line,
        founded=startup.founded_year or EM_DASH,
        stage_label=STAGE_LABELS_DE.get(startup.stage_signal.value, startup.stage_signal.value),
        sector_line=sector_line,
        one_liner=startup.one_liner,
        long_description=startup.long_description,
        founders_block=_format_founders(startup),
        traction_block=_format_bullets(startup.traction_signals),
        funding_block=_format_bullets(startup.funding_signals),
        thesis_fit=score.thesis_fit,
        team_quality=score.team_quality,
        earliness=score.earliness,
        traction_score=score.traction,
        contactability=score.contactability,
        rationale=score.rationale,
        red_flags_block=_format_bullets(score.red_flags, empty_label="keine"),
        sources_block=_format_bullets([str(u) for u in startup.source_urls]),
        scored_at=score.scored_at.strftime("%Y-%m-%d"),
        canonical_id=startup.canonical_id,
    )

    filename = f"{rank:02d}_{slugify(startup.name)}.md"
    path = out_dir / filename
    path.write_text(content)
    return path


def slugify(name: str) -> str:
    """Filesystem-safe slug, ASCII fold for German umlauts."""
    if not name:
        return "startup"
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return (slug or "startup")[:50]


# ---- helpers -------------------------------------------------------------


def _format_founders(startup: EnrichedStartup) -> str:
    if not startup.founders:
        return f"{EM_DASH} (in den Quellen keine Gründer gefunden)"
    lines: list[str] = []
    for f in startup.founders:
        role = f" — {f.role}" if f.role else ""
        lines.append(f"- **{f.name}**{role}")
        lines.append(f"  - LinkedIn: {str(f.linkedin_url) if f.linkedin_url else EM_DASH}")
        lines.append(f"  - E-Mail: {f.email or EM_DASH}")
        if f.background:
            lines.append(f"  - Hintergrund: {f.background}")
    return "\n".join(lines)


def _format_bullets(items: list[str], empty_label: str = EM_DASH) -> str:
    if not items:
        return empty_label
    return "\n".join(f"- {item}" for item in items)
