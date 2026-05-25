"""Export orchestrator: assemble rows from SQLite, fan out to writers (§12).

Run order: assemble → write CSV → write XLSX → write per-top-N one-pagers →
write run_summary.md → (optional) push to Google Sheets.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

from loguru import logger
from pydantic import ValidationError

from . import db
from .enrich import canonical_id_for
from .exporters.csv_writer import LIST_SEPARATOR, write_csv, write_xlsx
from .exporters.markdown_onepager import write_onepager
from .fetch import normalize_url
from .models import EnrichedStartup, Score

DEFAULT_OUTPUT_DIR = Path("outputs")


def export_all(
    *,
    db_path: Path = db.DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    top_n_onepagers: int | None = None,
    no_sheets: bool = False,
) -> dict:
    """Run every exporter. Returns a summary dict consumed by the CLI."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "onepagers").mkdir(parents=True, exist_ok=True)

    rows, scored_items = assemble_rows(db_path=db_path)

    csv_path = write_csv(rows, output_dir / "leads.csv")
    xlsx_path = write_xlsx(rows, output_dir / "leads.xlsx")

    # One-pagers — only generated for scored startups; rank set in assemble_rows.
    onepager_dir = output_dir / "onepagers"
    written_onepagers: list[Path] = []
    total_scored = len(scored_items)
    limit = top_n_onepagers if top_n_onepagers is not None else total_scored
    for rank, (startup, score) in enumerate(scored_items[:limit], start=1):
        path = write_onepager(
            startup, score, rank=rank, total=total_scored, out_dir=onepager_dir
        )
        written_onepagers.append(path)

    summary_path = write_run_summary(rows, db_path=db_path, path=output_dir / "run_summary.md")

    sheets_status = _push_sheets_if_configured(rows, no_sheets=no_sheets)

    return {
        "csv": csv_path,
        "xlsx": xlsx_path,
        "onepagers_written": len(written_onepagers),
        "run_summary": summary_path,
        "sheets": sheets_status,
        "total_rows": len(rows),
        "total_scored": total_scored,
    }


# ---- row assembly --------------------------------------------------------


def assemble_rows(
    *, db_path: Path = db.DEFAULT_DB_PATH
) -> tuple[list[dict], list[tuple[EnrichedStartup, Score]]]:
    """Return (csv-row dicts, sorted scored items).

    `csv-row dicts` matches the CSV column order including unscored rows
    (rank/score blank). `scored items` is sorted by overall DESC for the
    one-pager generator.
    """
    enriched_rows, score_map = _load_payloads(db_path)
    discovered_map = _build_discovered_map(db_path)

    items: list[tuple[EnrichedStartup, Score | None, datetime | None]] = []
    for startup in enriched_rows:
        score = score_map.get(startup.canonical_id)
        discovered = discovered_map.get(startup.canonical_id)
        items.append((startup, score, discovered))

    # Sort: scored entries first (by overall DESC), unscored entries last
    # (by last_enriched DESC as a stable tiebreaker).
    def sort_key(triple):
        s, sc, _ = triple
        if sc is not None:
            return (0, -sc.overall, s.last_enriched.timestamp() * -1)
        return (1, 0, s.last_enriched.timestamp() * -1)

    items.sort(key=sort_key)

    rows: list[dict] = []
    scored_items: list[tuple[EnrichedStartup, Score]] = []
    rank = 0
    for startup, score, discovered in items:
        if score is not None:
            rank += 1
            current_rank = rank
            scored_items.append((startup, score))
        else:
            current_rank = None
        rows.append(_build_row(startup, score, current_rank, discovered))
    return rows, scored_items


def _load_payloads(
    db_path: Path,
) -> tuple[list[EnrichedStartup], dict[str, Score]]:
    enriched: list[EnrichedStartup] = []
    scores: dict[str, Score] = {}
    with db.connect(db_path) as conn:
        for row in conn.execute("SELECT payload FROM enriched_startups").fetchall():
            try:
                enriched.append(EnrichedStartup.model_validate_json(row["payload"]))
            except (ValidationError, json.JSONDecodeError):
                continue
        for row in conn.execute(
            "SELECT canonical_id, payload FROM scores"
        ).fetchall():
            try:
                scores[row["canonical_id"]] = Score.model_validate_json(row["payload"])
            except (ValidationError, json.JSONDecodeError):
                continue
    return enriched, scores


def _build_discovered_map(db_path: Path) -> dict[str, datetime]:
    """Map canonical_id → earliest `discovered_at` across matching leads.

    Computed in Python because we can't join leads.website ↔ enriched.canonical_id
    in SQL (the latter is a hash of the *normalized* website).
    """
    out: dict[str, datetime] = {}
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT website, discovered_at FROM leads WHERE website IS NOT NULL AND website != ''"
        ).fetchall()
    for row in rows:
        try:
            cid = canonical_id_for(normalize_url(row["website"]))
        except Exception:  # noqa: BLE001
            continue
        ts = _parse_ts(row["discovered_at"])
        if ts is None:
            continue
        if cid not in out or ts < out[cid]:
            out[cid] = ts
    return out


def _build_row(
    startup: EnrichedStartup,
    score: Score | None,
    rank: int | None,
    discovered_at: datetime | None,
) -> dict:
    founders = startup.founders
    return {
        "rank": rank if rank is not None else "",
        "overall_score": score.overall if score else "",
        "thesis_fit": score.thesis_fit if score else "",
        "team_quality": score.team_quality if score else "",
        "earliness": score.earliness if score else "",
        "traction": score.traction if score else "",
        "contactability": score.contactability if score else "",
        "name": startup.name,
        "website": str(startup.website) if startup.website else "",
        "one_liner": startup.one_liner,
        "sector": startup.sector,
        "sub_sector": startup.sub_sector or "",
        "hq_city": startup.hq_city or "",
        "hq_country": startup.hq_country or "",
        "founded_year": startup.founded_year or "",
        "stage_signal": startup.stage_signal.value,
        "team_size_estimate": startup.team_size_estimate or "",
        "founder_names": LIST_SEPARATOR.join(f.name for f in founders),
        "founder_linkedins": LIST_SEPARATOR.join(
            str(f.linkedin_url) for f in founders if f.linkedin_url
        ),
        "founder_emails": LIST_SEPARATOR.join(f.email for f in founders if f.email),
        "traction_signals": LIST_SEPARATOR.join(startup.traction_signals),
        "funding_signals": LIST_SEPARATOR.join(startup.funding_signals),
        "sources": LIST_SEPARATOR.join(s.value for s in startup.sources),
        "source_urls": LIST_SEPARATOR.join(str(u) for u in startup.source_urls),
        "rationale_de": score.rationale if score else "",
        "red_flags": LIST_SEPARATOR.join(score.red_flags) if (score and score.red_flags) else "",
        "discovered_at": discovered_at.isoformat() if discovered_at else "",
        "last_enriched": startup.last_enriched.isoformat(),
        "scored_at": score.scored_at.isoformat() if score else "",
        "canonical_id": startup.canonical_id,
    }


# ---- run summary ---------------------------------------------------------


def write_run_summary(
    rows: list[dict], *, db_path: Path, path: Path
) -> Path:
    """Render outputs/run_summary.md (§12.3)."""
    path.parent.mkdir(parents=True, exist_ok=True)

    leads_per_source: Counter[str] = Counter()
    with db.connect(db_path) as conn:
        counts = db.counts(conn)
        cost = db.total_llm_cost(conn)
        for row in conn.execute("SELECT source FROM leads").fetchall():
            leads_per_source[row["source"]] += 1

    scored_rows = [r for r in rows if r.get("overall_score") not in (None, "")]
    top_5 = scored_rows[:5]

    lines = [
        f"# Run Summary — {datetime.utcnow().isoformat(timespec='seconds')} UTC",
        "",
        "## Counts",
        "",
        f"- Leads total: **{counts['leads']}**",
        f"- Enriched startups: **{counts['enriched_startups']}**",
        f"- Scored: **{counts['scores']}**",
        f"- LLM cost so far: **${cost:.4f}**",
        "",
        "## Leads per source",
        "",
    ]
    if leads_per_source:
        for src, n in sorted(leads_per_source.items(), key=lambda p: -p[1]):
            lines.append(f"- `{src}`: {n}")
    else:
        lines.append("_(none)_")

    lines += ["", "## Top 5 by overall score", ""]
    if top_5:
        for r in top_5:
            slug = _slug_for_link(r["name"], r["rank"])
            lines.append(
                f"- **#{r['rank']}** · {r['name']} · {r['overall_score']:.2f}"
                f" — [one-pager](onepagers/{slug}.md)"
            )
    else:
        lines.append("_(nothing scored yet)_")
    lines.append("")

    path.write_text("\n".join(lines))
    return path


def _slug_for_link(name: str, rank: int) -> str:
    """Mirror markdown_onepager.slugify naming so cross-links work."""
    from .exporters.markdown_onepager import slugify

    return f"{rank:02d}_{slugify(name)}"


def _parse_ts(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


# ---- sheets push gate ----------------------------------------------------


def _push_sheets_if_configured(rows: list[dict], *, no_sheets: bool) -> str:
    if no_sheets:
        return "skipped (--no-sheets)"
    sa_path = os.environ.get("GOOGLE_SA_PATH")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sa_path or not sheet_id:
        return "skipped (GOOGLE_SA_PATH / GOOGLE_SHEET_ID not set)"
    if not Path(sa_path).expanduser().exists():
        return f"skipped (service-account file missing: {sa_path})"
    try:
        from .exporters.google_sheets import push_to_sheets

        tab = push_to_sheets(rows, sa_path=Path(sa_path), sheet_id=sheet_id)
        return f"pushed → tab '{tab}'"
    except Exception as e:  # noqa: BLE001
        logger.warning(f"sheets: push failed — {e}")
        return f"failed: {e}"
