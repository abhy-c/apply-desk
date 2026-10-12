from __future__ import annotations

from .storage import transactional, atomic_csv, atomic_json, atomic_text

import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .workflow import ensure_workflow_files


LOCAL_CONFIG = ".job-system.local.json"

EDITABLE_TABS = {
    "Config": "data/workflow_config.csv",
    "Companies": "data/companies.csv",
    "Jobs Seed": "data/jobs_seed.csv",
    "Contacts CRM": "data/contacts_seed.csv",
    "Message Log": "data/message_log.csv",
}

GENERATED_TABS = {
    "Roles Scored": "out/roles_scored.csv",
    "Contacts Scored": "out/contacts_scored.csv",
    "Tier 1 Review": "out/tier1_evidence_review.csv",
    "Tier 2 Review": "out/tier2_dedicated_domain_review.csv",
    "Weekly Queue": "out/weekly_queue.csv",
    "FullEnrich Queue": "out/fullenrich_queue.csv",
}


@transactional('project_dir', 'project')
def create_google_sheet(project_dir: Path, title: str) -> dict[str, str]:
    ensure_workflow_files(project_dir / "data")
    tabs = list(EDITABLE_TABS) + list(GENERATED_TABS)
    body = {
        "properties": {"title": title},
        "sheets": [{"properties": {"title": tab}} for tab in tabs],
    }
    result = _gws_json(["sheets", "spreadsheets", "create", "--json", json.dumps(body)])
    spreadsheet_id = result["spreadsheetId"]
    url = result.get("spreadsheetUrl", f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")
    _write_local_config(project_dir, {"spreadsheet_id": spreadsheet_id, "spreadsheet_url": url, "created_at": _now()})
    push_to_sheet(project_dir, spreadsheet_id)
    return {"spreadsheet_id": spreadsheet_id, "spreadsheet_url": url}


@transactional('project_dir', 'project')
def push_to_sheet(project_dir: Path, spreadsheet_id: str | None = None) -> dict[str, int]:
    spreadsheet_id = spreadsheet_id or _read_local_config(project_dir)["spreadsheet_id"]
    ensure_workflow_files(project_dir / "data")
    pushed = 0
    for tab, rel_path in {**EDITABLE_TABS, **GENERATED_TABS}.items():
        path = project_dir / rel_path
        if not path.exists():
            continue
        rows = _csv_values(path)
        _clear_values(spreadsheet_id, tab)
        if rows:
            _update_values(spreadsheet_id, tab, rows)
        pushed += 1
    return {"tabs": pushed}


@transactional('project_dir', 'project')
def pull_from_sheet(project_dir: Path, spreadsheet_id: str | None = None) -> dict[str, int]:
    spreadsheet_id = spreadsheet_id or _read_local_config(project_dir)["spreadsheet_id"]
    pulled = 0
    for tab, rel_path in EDITABLE_TABS.items():
        values = _get_values(spreadsheet_id, tab)
        if not values:
            continue
        _write_csv_values(project_dir / rel_path, values)
        pulled += 1
    ensure_workflow_files(project_dir / "data")
    return {"tabs": pulled}


def _gws_json(args: list[str]) -> dict[str, object]:
    command = ["gws", *args]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        output = "\n".join(part for part in [exc.stdout, exc.stderr] if part)
        if "invalid_grant" in output or "Authentication failed" in output:
            raise RuntimeError(
                "Google Workspace auth needs to be refreshed. Run: "
                "gws auth login"
            ) from exc
        raise RuntimeError(output or f"gws command failed: {' '.join(command)}") from exc
    if not completed.stdout.strip():
        return {}
    return json.loads(completed.stdout)


def _clear_values(spreadsheet_id: str, tab: str) -> None:
    _gws_json(
        [
            "sheets",
            "spreadsheets",
            "values",
            "clear",
            "--params",
            json.dumps({"spreadsheetId": spreadsheet_id, "range": f"{_quoted(tab)}!A:ZZ"}),
            "--json",
            "{}",
        ]
    )


def _update_values(spreadsheet_id: str, tab: str, rows: list[list[str]]) -> None:
    _gws_json(
        [
            "sheets",
            "spreadsheets",
            "values",
            "update",
            "--params",
            json.dumps({"spreadsheetId": spreadsheet_id, "range": f"{_quoted(tab)}!A1", "valueInputOption": "RAW"}),
            "--json",
            json.dumps({"range": f"{_quoted(tab)}!A1", "majorDimension": "ROWS", "values": rows}),
        ]
    )


def _get_values(spreadsheet_id: str, tab: str) -> list[list[str]]:
    result = _gws_json(
        [
            "sheets",
            "spreadsheets",
            "values",
            "get",
            "--params",
            json.dumps({"spreadsheetId": spreadsheet_id, "range": f"{_quoted(tab)}!A1:ZZ"}),
        ]
    )
    return [[str(cell) for cell in row] for row in result.get("values", [])]


def _csv_values(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [[cell for cell in row] for row in csv.reader(handle)]


def _write_csv_values(path: Path, values: list[list[str]]) -> None:
    if not values: return
    fields = values[0]
    if len(fields)!=len(set(fields)) or not all(fields): raise ValueError('Invalid spreadsheet headers')
    rows=[dict(zip(fields,row)) for row in values[1:]]
    if path.name=='jobs_seed.csv':
        from .validation import job
        rows=[job(row) for row in rows]
    atomic_csv(path, rows, fields)


def _quoted(tab: str) -> str:
    return "'" + tab.replace("'", "''") + "'"


def _read_local_config(project_dir: Path) -> dict[str, str]:
    config_path = project_dir / LOCAL_CONFIG
    if not config_path.exists():
        raise FileNotFoundError(
            f"No {LOCAL_CONFIG} found. Run create-google-sheet first or pass --spreadsheet-id."
        )
    with config_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_local_config(project_dir: Path, payload: dict[str, str]) -> None:
    atomic_json(project_dir / LOCAL_CONFIG, payload)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
