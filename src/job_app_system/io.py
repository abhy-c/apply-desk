from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .storage import atomic_csv
from .validation import job as validate_job

from .models import Company, Contact, Job, parse_date, parse_tags


def read_companies(path: Path) -> list[Company]:
    rows = _read_dicts(path)
    return [
        Company(
            company=row["company"].strip(),
            domain_tags=parse_tags(row.get("domain_tags", "")),
            location_preference=row.get("location_preference", "").strip(),
            employee_band=row.get("employee_band", "").strip(),
            priority=row.get("priority", "").strip().lower(),
            notes=row.get("notes", "").strip(),
        )
        for row in rows
    ]


def read_jobs(path: Path) -> list[Job]:
    rows = []
    for row in _read_dicts(path):
        try: rows.append(validate_job(row))
        except ValueError: continue
    return [
        Job(
            role_id=row["role_id"].strip(),
            company=row["company"].strip(),
            role_title=row["role_title"].strip(),
            role_url=row["role_url"].strip(),
            source=row.get("source", "").strip(),
            posted_date=parse_date(row.get("posted_date", "")),
            location=row.get("location", "").strip(),
            workplace=row.get("workplace", "").strip().lower(),
            domain_tags=parse_tags(row.get("domain_tags", "")),
            seniority=row.get("seniority", "").strip(),
            status=row.get("status", "").strip().lower(),
            description=row.get("description", "").strip(),
        )
        for row in rows
    ]


def read_ats_sources(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return _read_dicts(path)


def read_contacts(path: Path) -> list[Contact]:
    rows = _read_dicts(path)
    return [
        Contact(
            contact_id=row["contact_id"].strip(),
            company=row["company"].strip(),
            name=row["name"].strip(),
            title=row["title"].strip(),
            email=row.get("email", "").strip(),
            email_status=row.get("email_status", "").strip().lower(),
            profile_url=row.get("profile_url", "").strip(),
            evidence_type=row.get("evidence_type", "").strip().lower(),
            evidence_url=row.get("evidence_url", "").strip(),
            role_id=row.get("role_id", "").strip(),
            source=row.get("source", "").strip(),
            notes=row.get("notes", "").strip(),
        )
        for row in rows
    ]


def write_csv(path: Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> None:
    atomic_csv(path, rows, fieldnames, spreadsheet_safe=path.name in {'roles_scored.csv','contacts_scored.csv','tier1_evidence_review.csv','tier2_dedicated_domain_review.csv','recruiters_validated.csv'})


def _read_dicts(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def job_warnings(data_dir: Path):
    warnings=[]
    for name in ('jobs_seed.csv','jobs_fetched.csv','jobs_discovered.csv'):
        path=data_dir/name
        if not path.exists(): continue
        for number,row in enumerate(_read_dicts(path),start=2):
            try: validate_job(row)
            except ValueError as exc: warnings.append(f'{name} row {number}: {exc}')
    return warnings[:50]
