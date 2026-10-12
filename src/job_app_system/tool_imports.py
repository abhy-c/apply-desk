from __future__ import annotations

from .validation import public_url

from .storage import transactional, atomic_csv, atomic_json, atomic_text

import csv
import hashlib
import json
import re
from pathlib import Path

from .adapters import JOB_FIELDS, clean_text, infer_seniority, infer_workplace, is_product_role
from .workflow import CONTACTS_CRM_FIELDS, ensure_workflow_files


@transactional('contacts_path', 'file')
def import_fullenrich_export(export_path: Path, contacts_path: Path) -> dict[str, int]:
    ensure_workflow_files(contacts_path.parent)
    incoming = _read_any(export_path)
    contacts = _read_rows(contacts_path)
    updated = 0
    added = 0

    for raw in incoming:
        normalized = _normalize_fullenrich_row(raw)
        if not normalized.get("email") and not normalized.get("profile_url"):
            continue

        match = _find_contact(contacts, normalized)
        if match is None:
            contacts.append(_new_contact_from_enrichment(normalized))
            added += 1
            continue

        if normalized.get("email") and not match.get("email"):
            match["email"] = normalized["email"]
        if normalized.get("email_status"):
            match["email_status"] = normalized["email_status"]
        if normalized.get("company_domain") and not match.get("company_domain"):
            match["company_domain"] = normalized["company_domain"]
        if normalized.get("profile_url") and not match.get("profile_url"):
            match["profile_url"] = normalized["profile_url"]
        match["fullenrich_status"] = normalized.get("fullenrich_status", "completed")
        match["source"] = _append_source(match.get("source", ""), "fullenrich")
        updated += 1

    _write_rows(contacts_path, contacts, _merged_fields(contacts, CONTACTS_CRM_FIELDS))
    return {"updated": updated, "added": added}


@transactional('jobs_path', 'file')
def import_apify_jobs(export_path: Path, jobs_path: Path, source_label: str = "apify_public") -> dict[str, int]:
    incoming = _read_any(export_path)
    jobs = _read_rows(jobs_path)
    known_urls = {row.get("role_url", "").strip() for row in jobs if row.get("role_url", "").strip()}
    known_ids = {row.get("role_id", "").strip() for row in jobs if row.get("role_id", "").strip()}
    added = 0
    skipped_linkedin = 0
    skipped_non_product = 0

    for raw in incoming:
        normalized = _normalize_apify_job(raw, source_label)
        url_blob = " ".join([normalized.get("role_url", ""), raw.get("url", ""), raw.get("profileUrl", "")]).lower()
        if "linkedin.com" in url_blob:
            skipped_linkedin += 1
            continue
        if not normalized.get("role_title") or not normalized.get("company"):
            continue
        if not is_product_role(normalized["role_title"]):
            skipped_non_product += 1
            continue
        if normalized["role_url"] in known_urls or normalized["role_id"] in known_ids:
            continue
        jobs.append(normalized)
        known_urls.add(normalized["role_url"])
        known_ids.add(normalized["role_id"])
        added += 1

    from .validation import job
    jobs = [job(row) for row in jobs]
    _write_rows(jobs_path, jobs, JOB_FIELDS)
    return {"added": added, "skipped_linkedin": skipped_linkedin, "skipped_non_product": skipped_non_product}


def _normalize_fullenrich_row(row: dict[str, object]) -> dict[str, str]:
    flat = _flat_keys(row)
    first_name = _pick(flat, "first_name", "firstname", "first name")
    last_name = _pick(flat, "last_name", "lastname", "last name")
    name = _pick(flat, "name", "full_name", "fullname", "person_name") or " ".join(
        part for part in [first_name, last_name] if part
    )
    email = _pick(
        flat,
        "email",
        "work_email",
        "professional_email",
        "business_email",
        "best_email",
        "email_address",
    )
    status = _pick(flat, "email_status", "verification_status", "validation_status", "status")
    if email and not status:
        status = "enriched"
    return {
        "contact_id": _pick(flat, "contact_id", "id", "external_id"),
        "name": name,
        "company": _pick(flat, "company", "company_name", "organization"),
        "title": _pick(flat, "title", "job_title", "position"),
        "email": email,
        "email_status": _normalize_email_status(status),
        "profile_url": public_url(_pick(flat, "profile_url", "linkedin_url", "linkedin", "linkedin_profile_url")),
        "company_domain": _pick(flat, "company_domain", "domain", "website", "company_website"),
        "fullenrich_status": "completed",
    }


def _normalize_apify_job(row: dict[str, object], source_label: str) -> dict[str, str]:
    flat = _flat_keys(row)
    title = _pick(flat, "role_title", "title", "job_title", "position", "name")
    company = _pick(flat, "company", "company_name", "organization", "hiring_company")
    role_url = _pick(flat, "role_url", "url", "job_url", "apply_url", "link")
    location = _pick(flat, "location", "job_location", "locations")
    posted_date = _pick(flat, "posted_date", "date_posted", "published_at", "created_at", "listed_at")[:10]
    description = clean_text(_pick(flat, "description", "job_description", "content", "text"))
    role_id = _pick(flat, "role_id", "id", "job_id") or f"apify_{_slug(company)}_{_short_hash(role_url or title)}"

    return {
        "role_id": role_id,
        "company": company,
        "role_title": title,
        "role_url": role_url,
        "source": source_label,
        "posted_date": posted_date if re.match(r"\d{4}-\d{2}-\d{2}", posted_date) else "",
        "location": location,
        "workplace": infer_workplace(f"{location} {title}"),
        "domain_tags": _pick(flat, "domain_tags", "tags"),
        "seniority": infer_seniority(title),
        "status": "open",
        "description": description,
    }


def _find_contact(contacts: list[dict[str, str]], incoming: dict[str, str]) -> dict[str, str] | None:
    contact_id = incoming.get("contact_id", "").strip()
    profile_url = incoming.get("profile_url", "").strip().lower()
    name_company = (incoming.get("name", "").strip().lower(), incoming.get("company", "").strip().lower())

    for contact in contacts:
        if contact_id and contact.get("contact_id", "").strip() == contact_id:
            return contact
        if profile_url and contact.get("profile_url", "").strip().lower() == profile_url:
            return contact
        if name_company[0] and name_company[1]:
            if (contact.get("name", "").strip().lower(), contact.get("company", "").strip().lower()) == name_company:
                return contact
    return None


def _new_contact_from_enrichment(row: dict[str, str]) -> dict[str, str]:
    contact_id = row.get("contact_id") or f"fe_{_slug(row.get('company', 'company'))}_{_slug(row.get('name', 'contact'))}"
    return {
        "contact_id": contact_id,
        "company": row.get("company", ""),
        "name": row.get("name", ""),
        "title": row.get("title", ""),
        "email": row.get("email", ""),
        "email_status": row.get("email_status", ""),
        "profile_url": row.get("profile_url", ""),
        "evidence_type": "company_level",
        "evidence_url": "",
        "role_id": "",
        "source": "fullenrich",
        "notes": "Added from FullEnrich export; review before outreach.",
        "company_domain": row.get("company_domain", ""),
        "fullenrich_status": "completed",
        "outreach_status": "not_contacted",
        "approval_status": "needs_review",
    }


def _read_any(path: Path) -> list[dict[str, object]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ["items", "data", "results"]:
                if isinstance(payload.get(key), list):
                    return [dict(item) for item in payload[key] if isinstance(item, dict)]
        raise ValueError(f"Unsupported JSON export shape: {path}")
    return [dict(row) for row in _read_rows(path)]


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    atomic_csv(path, rows, fieldnames, spreadsheet_safe=path.name in {'connections_ranked.csv','weekly_queue.csv','fullenrich_queue.csv'})


def _merged_fields(rows: list[dict[str, str]], defaults: list[str]) -> list[str]:
    fields = list(defaults)
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    return fields


def _flat_keys(row: dict[str, object]) -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in row.items():
        normalized = _key(key)
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                flat[_key(f"{key}_{nested_key}")] = _string(nested_value)
                flat[_key(nested_key)] = _string(nested_value)
        else:
            flat[normalized] = _string(value)
    return flat


def _pick(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(_key(name), "").strip()
        if value:
            return value
    return ""


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(_string(item) for item in value)
    return str(value).strip()


def _normalize_email_status(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"valid", "verified", "deliverable"}:
        return "verified"
    if lowered in {"risky", "catch_all", "catch-all"}:
        return "risky"
    if lowered in {"invalid", "undeliverable"}:
        return "invalid"
    return lowered or "enriched"


def _append_source(existing: str, addition: str) -> str:
    parts = [part.strip() for part in existing.split(",") if part.strip()]
    if addition not in parts:
        parts.append(addition)
    return ",".join(parts)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "unknown"


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
