from __future__ import annotations

from .storage import transactional, atomic_csv, atomic_json, atomic_text

from datetime import date
from dataclasses import replace
from pathlib import Path

from .application import load_profile

from .drafting import draft_email, suggested_angle
from .io import read_companies, read_contacts, read_jobs, write_csv
from .scoring import score_contact, score_job
from .discovery_import import _canonical_url


ROLE_FIELDS = [
    "role_id",
    "company",
    "role_title",
    "role_url",
    "source",
    "posted_date",
    "location",
    "workplace",
    "domain_tags",
    "seniority",
    "status",
    "role_score",
    "role_tier",
    "role_score_reasons",
    "role_age_days",
    "freshness_bucket",
    "description",
]

CONTACT_FIELDS = [
    "contact_id",
    "company",
    "name",
    "title",
    "email",
    "email_status",
    "profile_url",
    "evidence_type",
    "evidence_url",
    "role_id",
    "role_title",
    "role_url",
    "location",
    "workplace",
    "domain_tags",
    "role_score",
    "contact_score",
    "outreach_tier",
    "contact_score_reasons",
    "suggested_angle",
    "draft_subject",
    "draft_body",
    "application_status",
    "outreach_status",
    "source",
    "notes",
]


@transactional('data_dir', 'data')
def build(data_dir: Path, out_dir: Path, today: date | None = None) -> dict[str, int]:
    today = today or date.today()
    preferences = load_profile(data_dir)
    companies = read_companies(data_dir / "companies.csv")
    jobs = read_jobs(data_dir / "jobs_seed.csv")
    fetched_jobs = data_dir / "jobs_fetched.csv"
    if fetched_jobs.exists():
        jobs.extend(read_jobs(fetched_jobs))
    discovered_jobs = data_dir / "jobs_discovered.csv"
    if discovered_jobs.exists():
        jobs.extend(read_jobs(discovered_jobs))
    unique_jobs = {}
    for job in jobs:
        key = _canonical_url(job.role_url) if job.role_url else job.role_id
        previous = unique_jobs.get(key)
        if previous:
            # Preserve application history IDs while accepting verified discovery detail.
            job = replace(job, role_id=previous.role_id) if job.source.startswith("discovery:") else previous
        unique_jobs[key] = job
    jobs = list(unique_jobs.values())
    contacts = read_contacts(data_dir / "contacts_seed.csv")

    company_by_key = {company.company.lower(): company for company in companies}

    role_rows: list[dict[str, object]] = []
    for job in jobs:
        company = company_by_key.get(job.company.lower())
        score = score_job(job, company, today, preferences=preferences)
        if not score["role_eligible"]:
            continue
        row = {
            "role_id": job.role_id,
            "company": normalized_company(job.company, company),
            "role_title": job.role_title,
            "role_url": job.role_url,
            "source": job.source,
            "posted_date": job.posted_date.isoformat() if job.posted_date else "",
            "location": job.location,
            "workplace": job.workplace,
            "domain_tags": ",".join(sorted(job.domain_tags)),
            "seniority": job.seniority,
            "status": job.status,
            "description": job.description,
        }
        row.update(score)
        role_rows.append(row)

    role_rows.sort(key=lambda item: int(item["role_score"]), reverse=True)
    role_by_id = {str(row["role_id"]): row for row in role_rows}

    contact_rows: list[dict[str, object]] = []
    for contact in contacts:
        role_row = role_by_id.get(contact.role_id)
        row = {
            "contact_id": contact.contact_id,
            "company": normalized_company(contact.company, company_by_key.get(contact.company.lower())),
            "name": contact.name,
            "title": contact.title,
            "email": contact.email,
            "email_status": contact.email_status,
            "profile_url": contact.profile_url,
            "evidence_type": contact.evidence_type,
            "evidence_url": contact.evidence_url,
            "role_id": contact.role_id,
            "role_title": role_row.get("role_title", "") if role_row else "",
            "role_url": role_row.get("role_url", "") if role_row else "",
            "location": role_row.get("location", "") if role_row else "",
            "workplace": role_row.get("workplace", "") if role_row else "",
            "domain_tags": role_row.get("domain_tags", "") if role_row else "",
            "role_score": role_row.get("role_score", "") if role_row else "",
            "source": contact.source,
            "notes": contact.notes,
            "application_status": "not_applied",
            "outreach_status": "not_contacted",
        }
        row.update(score_contact(contact, role_row))
        row["suggested_angle"] = suggested_angle(row)
        row["draft_subject"], row["draft_body"] = draft_email(row)
        contact_rows.append(row)

    contact_rows.sort(key=lambda item: int(item["contact_score"]), reverse=True)

    tier1 = [row for row in contact_rows if str(row["outreach_tier"]).startswith("Tier 1")]
    tier2 = [row for row in contact_rows if str(row["outreach_tier"]).startswith("Tier 2")]

    write_csv(out_dir / "roles_scored.csv", role_rows, ROLE_FIELDS)
    write_csv(out_dir / "contacts_scored.csv", contact_rows, CONTACT_FIELDS)
    write_csv(out_dir / "tier1_evidence_review.csv", tier1, CONTACT_FIELDS)
    write_csv(out_dir / "tier2_dedicated_domain_review.csv", tier2, CONTACT_FIELDS)

    return {
        "roles": len(role_rows),
        "contacts": len(contact_rows),
        "tier1": len(tier1),
        "tier2": len(tier2),
    }


def normalized_company(value: str, company: object | None) -> str:
    return getattr(company, "company", value)
