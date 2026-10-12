from __future__ import annotations

from .storage import transactional, atomic_csv, atomic_json, atomic_text

import csv
from datetime import date, timedelta
from pathlib import Path


CONTACTS_CRM_FIELDS = [
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
    "source",
    "notes",
    "company_domain",
    "relationship_type",
    "linkedin_connection_status",
    "priority_bucket",
    "warmth_score",
    "last_contacted_date",
    "last_channel",
    "last_touch_type",
    "next_follow_up_date",
    "follow_up_frequency_days",
    "outreach_status",
    "approval_status",
    "do_not_contact",
    "pending_invite",
    "reply_status",
    "owner_notes",
    "draft_override",
    "fullenrich_status",
    "apify_source",
]

MESSAGE_LOG_FIELDS = [
    "log_id",
    "date",
    "contact_id",
    "name",
    "company",
    "channel",
    "touch_type",
    "message_summary",
    "sent_status",
    "response_status",
    "next_follow_up_date",
    "notes",
]

CONFIG_FIELDS = ["setting", "value", "notes"]

CONFIG_DEFAULTS = [
    {
        "setting": "new_contacts_per_week",
        "value": "10",
        "notes": "Human-approved new outreach cap.",
    },
    {
        "setting": "follow_ups_per_week",
        "value": "5",
        "notes": "Follow-ups are in addition to the 10 new contacts.",
    },
    {
        "setting": "follow_up_frequency_days",
        "value": "14",
        "notes": "Previous connections are eligible every second week.",
    },
    {
        "setting": "linkedin_policy",
        "value": "manual_only",
        "notes": "Do not automate LinkedIn scraping, profile views, invites, or messages.",
    },
    {
        "setting": "gmail_policy",
        "value": "draft_or_manual_send",
        "notes": "Create drafts/reminders; keep sends human-approved.",
    },
]

ENRICHMENT_QUEUE_FIELDS = [
    "contact_id",
    "name",
    "company",
    "company_domain",
    "title",
    "profile_url",
    "role_id",
    "email",
    "email_status",
    "priority_reason",
    "fullenrich_status",
    "notes",
]

WEEKLY_QUEUE_FIELDS = [
    "queue_rank",
    "scheduled_week",
    "touch_type",
    "contact_id",
    "name",
    "company",
    "title",
    "channel_suggestion",
    "email",
    "profile_url",
    "why_useful",
    "draft_subject",
    "draft_body",
    "follow_up_date",
    "approval_status",
    "send_status",
    "notes",
]


@transactional('data_dir', 'data')
def ensure_workflow_files(data_dir: Path) -> dict[str, Path]:
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "contacts": data_dir / "contacts_seed.csv",
        "message_log": data_dir / "message_log.csv",
        "config": data_dir / "workflow_config.csv",
    }
    _ensure_csv(paths["contacts"], CONTACTS_CRM_FIELDS)
    _ensure_csv(paths["message_log"], MESSAGE_LOG_FIELDS)
    _ensure_csv(paths["config"], CONFIG_FIELDS, CONFIG_DEFAULTS)
    return paths


@transactional('data_dir', 'data')
def build_enrichment_queue(data_dir: Path, out_dir: Path, limit: int = 30) -> dict[str, int]:
    ensure_workflow_files(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    source_path = out_dir / "contacts_scored.csv"
    if not source_path.exists():
        source_path = data_dir / "contacts_seed.csv"

    contacts = _read_rows(source_path)
    seed_by_id = {row.get("contact_id", ""): row for row in _read_rows(data_dir / "contacts_seed.csv")}

    rows: list[dict[str, str]] = []
    for contact in contacts:
        seed = seed_by_id.get(contact.get("contact_id", ""), {})
        merged = {**contact, **{key: value for key, value in seed.items() if value}}
        if _truthy(merged.get("do_not_contact", "")):
            continue
        if merged.get("email_status", "").strip().lower() == "verified":
            continue
        if merged.get("email", "").strip() and merged.get("email_status", "").strip().lower() in {"valid", "verified"}:
            continue
        if merged.get("fullenrich_status", "").strip().lower() in {"done", "complete", "completed"}:
            continue
        if not merged.get("name", "").strip() or not merged.get("company", "").strip():
            continue

        rows.append(
            {
                "contact_id": merged.get("contact_id", ""),
                "name": merged.get("name", ""),
                "company": merged.get("company", ""),
                "company_domain": merged.get("company_domain", ""),
                "title": merged.get("title", ""),
                "profile_url": merged.get("profile_url", ""),
                "role_id": merged.get("role_id", ""),
                "email": merged.get("email", ""),
                "email_status": merged.get("email_status", ""),
                "priority_reason": merged.get("contact_score_reasons", merged.get("notes", "")),
                "fullenrich_status": merged.get("fullenrich_status", "queued"),
                "notes": merged.get("notes", ""),
            }
        )
        if len(rows) >= limit:
            break

    _write_rows(out_dir / "fullenrich_queue.csv", rows, ENRICHMENT_QUEUE_FIELDS)
    return {"queued": len(rows)}


@transactional('data_dir', 'data')
def build_weekly_queue(
    data_dir: Path,
    out_dir: Path,
    today: date | None = None,
    new_limit: int | None = None,
    follow_up_limit: int | None = None,
) -> dict[str, int]:
    ensure_workflow_files(data_dir)
    today = today or date.today()
    out_dir.mkdir(parents=True, exist_ok=True)

    config = _config_values(data_dir / "workflow_config.csv")
    new_limit = new_limit if new_limit is not None else int(config.get("new_contacts_per_week", "10"))
    follow_up_limit = follow_up_limit if follow_up_limit is not None else int(config.get("follow_ups_per_week", "5"))
    default_follow_up_days = int(config.get("follow_up_frequency_days", "14"))

    scored_path = out_dir / "contacts_scored.csv"
    contacts = _read_rows(scored_path if scored_path.exists() else data_dir / "contacts_seed.csv")
    seed_by_id = {row.get("contact_id", ""): row for row in _read_rows(data_dir / "contacts_seed.csv")}
    log_by_contact = _latest_logs_by_contact(data_dir / "message_log.csv")

    new_candidates: list[dict[str, str]] = []
    follow_up_candidates: list[dict[str, str]] = []

    for contact in contacts:
        contact_id = contact.get("contact_id", "")
        seed = seed_by_id.get(contact_id, {})
        merged = {**contact, **{key: value for key, value in seed.items() if value}}

        if _truthy(merged.get("do_not_contact", "")):
            continue
        if merged.get("reply_status", "").strip().lower() in {"closed", "not_interested", "no_fit"}:
            continue

        latest_log = log_by_contact.get(contact_id, {})
        last_contacted = _date_value(merged.get("last_contacted_date", "")) or _date_value(latest_log.get("date", ""))
        next_follow_up = _date_value(merged.get("next_follow_up_date", "")) or _date_value(
            latest_log.get("next_follow_up_date", "")
        )
        follow_up_days = int(merged.get("follow_up_frequency_days", "") or default_follow_up_days)

        if last_contacted and not next_follow_up:
            next_follow_up = last_contacted + timedelta(days=follow_up_days)

        if last_contacted:
            if next_follow_up and next_follow_up <= today:
                follow_up_candidates.append(_queue_candidate(merged, "follow_up", today, follow_up_days))
            continue

        if merged.get("outreach_status", "").strip().lower() in {"sent", "contacted", "replied", "closed"}:
            continue
        new_candidates.append(_queue_candidate(merged, "new", today, follow_up_days))

    new_candidates.sort(key=_queue_sort_key)
    follow_up_candidates.sort(key=_queue_sort_key)

    selected = new_candidates[:new_limit] + follow_up_candidates[:follow_up_limit]
    rows: list[dict[str, str]] = []
    for index, row in enumerate(selected, start=1):
        rows.append({"queue_rank": str(index), **row})

    _write_rows(out_dir / "weekly_queue.csv", rows, WEEKLY_QUEUE_FIELDS)
    return {"new": min(len(new_candidates), new_limit), "follow_ups": min(len(follow_up_candidates), follow_up_limit), "total": len(rows)}


def _queue_candidate(contact: dict[str, str], touch_type: str, today: date, follow_up_days: int) -> dict[str, str]:
    email = contact.get("email", "").strip()
    profile_url = contact.get("profile_url", "").strip()
    channel = "email" if email else "linkedin_manual" if profile_url else "research_needed"
    follow_up_date = today + timedelta(days=follow_up_days)
    why = contact.get("suggested_angle", "") or contact.get("contact_score_reasons", "") or contact.get("notes", "")

    return {
        "scheduled_week": today.isoformat(),
        "touch_type": touch_type,
        "contact_id": contact.get("contact_id", ""),
        "name": contact.get("name", ""),
        "company": contact.get("company", ""),
        "title": contact.get("title", ""),
        "channel_suggestion": channel,
        "email": email,
        "profile_url": profile_url,
        "why_useful": why,
        "draft_subject": contact.get("draft_subject", ""),
        "draft_body": contact.get("draft_override", "") or contact.get("draft_body", ""),
        "follow_up_date": follow_up_date.isoformat(),
        "approval_status": "needs_review",
        "send_status": "not_sent",
        "notes": contact.get("owner_notes", "") or contact.get("notes", ""),
        "_score": contact.get("contact_score", "0"),
    }


def _queue_sort_key(row: dict[str, str]) -> tuple[int, str, str]:
    try:
        score = int(row.get("_score", "0"))
    except ValueError:
        score = 0
    return (-score, row.get("company", ""), row.get("name", ""))


def _latest_logs_by_contact(path: Path) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    if not path.exists():
        return latest
    for row in _read_rows(path):
        contact_id = row.get("contact_id", "")
        if not contact_id:
            continue
        sent_status = row.get("sent_status", "").strip().lower()
        if sent_status not in {"sent", "confirmed", "done"}:
            continue
        if contact_id not in latest or row.get("date", "") > latest[contact_id].get("date", ""):
            latest[contact_id] = row
    return latest


def _config_values(path: Path) -> dict[str, str]:
    return {row.get("setting", ""): row.get("value", "") for row in _read_rows(path) if row.get("setting")}


def _ensure_csv(path: Path, fieldnames: list[str], default_rows: list[dict[str, str]] | None = None) -> None:
    if not path.exists() or path.stat().st_size == 0:
        _write_rows(path, default_rows or [], fieldnames)
        return

    rows = _read_rows(path)
    existing_fields = _fieldnames(path)
    if existing_fields == fieldnames:
        return
    merged_fields = list(dict.fromkeys(existing_fields + fieldnames))
    _write_rows(path, rows, merged_fields)


def _fieldnames(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    atomic_csv(path, rows, fieldnames, spreadsheet_safe=path.name in {'connections_ranked.csv','weekly_queue.csv','fullenrich_queue.csv'})


def _date_value(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _truthy(value: str) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y"}
