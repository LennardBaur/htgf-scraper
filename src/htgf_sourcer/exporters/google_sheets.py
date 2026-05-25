"""Google Sheets push (§13). Service-account OAuth via gspread.

Writes to a tab named `leads_YYYY-MM-DD` (history preserved across runs) and
appends one row per push to a `runs` summary tab. Skipped via `--no-sheets`
or by missing credentials — the caller handles those checks.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loguru import logger

from .csv_writer import COLUMNS

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DEFAULT_RUNS_TAB = "runs"


def push_to_sheets(
    rows: list[dict],
    *,
    sa_path: Path,
    sheet_id: str,
    runs_tab: str = DEFAULT_RUNS_TAB,
) -> str:
    """Push rows to a dated tab and append a run-summary row. Returns the tab name."""
    import gspread
    from google.oauth2.service_account import Credentials

    sa_path = Path(sa_path).expanduser()
    if not sa_path.exists():
        raise FileNotFoundError(f"service account file not found: {sa_path}")

    creds = Credentials.from_service_account_file(str(sa_path), scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)

    tab_name = f"leads_{datetime.utcnow().strftime('%Y-%m-%d')}"
    ws = _get_or_create_tab(
        sh, tab_name, rows_count=max(len(rows) + 5, 10), cols_count=len(COLUMNS)
    )
    ws.clear()

    data = [COLUMNS] + [[_cell(row.get(col, "")) for col in COLUMNS] for row in rows]
    ws.update(values=data, range_name="A1")
    ws.freeze(rows=1, cols=1)
    # Bold the header.
    ws.format("1:1", {"textFormat": {"bold": True}})

    _append_runs_row(sh, runs_tab, rows=rows, leads_tab=tab_name)
    logger.info(f"sheets: wrote {len(rows)} row(s) to tab '{tab_name}'")
    return tab_name


# ---- internals -----------------------------------------------------------


def _get_or_create_tab(sh, title: str, *, rows_count: int, cols_count: int):
    """Idempotent worksheet handle."""
    import gspread

    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=rows_count, cols=cols_count)


def _append_runs_row(sh, runs_tab: str, *, rows: list[dict], leads_tab: str) -> None:
    """Append one row to the runs summary tab."""
    ws = _get_or_create_tab(sh, runs_tab, rows_count=200, cols_count=6)
    # Ensure header exists.
    if not (ws.row_values(1) or []):
        ws.update(
            values=[["run_at_utc", "leads_tab", "n_rows", "n_scored", "top_score", "top_name"]],
            range_name="A1",
        )
        ws.format("1:1", {"textFormat": {"bold": True}})

    n_scored = sum(1 for r in rows if r.get("overall_score") not in (None, ""))
    top = next((r for r in rows if r.get("rank") == 1), None)
    summary = [
        datetime.utcnow().isoformat(timespec="seconds"),
        leads_tab,
        len(rows),
        n_scored,
        (top or {}).get("overall_score", ""),
        (top or {}).get("name", ""),
    ]
    ws.append_row(summary, value_input_option="USER_ENTERED")


def _cell(value) -> str:
    """gspread serializes lists/dicts oddly — coerce to str defensively."""
    if value is None:
        return ""
    if isinstance(value, (int, float, str)):
        return value
    return str(value)
