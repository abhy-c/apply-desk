from __future__ import annotations

from dataclasses import dataclass
from datetime import date


def parse_tags(value: str) -> set[str]:
    return {part.strip().lower() for part in value.split(",") if part.strip()}


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    return date.fromisoformat(value)


@dataclass(frozen=True)
class Company:
    company: str
    domain_tags: set[str]
    location_preference: str
    employee_band: str
    priority: str
    notes: str


@dataclass(frozen=True)
class Job:
    role_id: str
    company: str
    role_title: str
    role_url: str
    source: str
    posted_date: date | None
    location: str
    workplace: str
    domain_tags: set[str]
    seniority: str
    status: str
    description: str


@dataclass(frozen=True)
class Contact:
    contact_id: str
    company: str
    name: str
    title: str
    email: str
    email_status: str
    profile_url: str
    evidence_type: str
    evidence_url: str
    role_id: str
    source: str
    notes: str

