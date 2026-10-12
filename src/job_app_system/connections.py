from __future__ import annotations

from .validation import public_url, iso_date

from .storage import transactional, atomic_csv, atomic_json, atomic_text

import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


CONNECTION_FIELDS = [
    "connection_id",
    "first_name",
    "last_name",
    "name",
    "profile_url",
    "email",
    "company",
    "title",
    "connected_on",
    "message_inbound_count",
    "message_outbound_count",
    "last_message_date",
    "direct_hiring_evidence_date",
    "direct_hiring_evidence_type",
    "source",
]

CONNECTION_REVIEW_FIELDS = [
    "connection_id",
    "status",
    "notes",
    "do_not_contact",
    "hiring_evidence_date",
    "hiring_evidence_type",
    "hiring_evidence_url",
    "updated_at",
]

RANKED_CONNECTION_FIELDS = [
    *CONNECTION_FIELDS,
    "relationship_label",
    "warmth_score",
    "strategic_score",
    "connection_score",
    "outreach_tier",
    "recent_hiring",
    "hiring_evidence_date",
    "hiring_evidence_type",
    "hiring_evidence_url",
    "matching_role_id",
    "matching_role_title",
    "matching_role_url",
    "matching_role_posted_date",
    "priority_reasons",
    "review_status",
    "review_notes",
    "do_not_contact",
]

HIRING_EVIDENCE_TYPES = {
    "direct_hiring_message",
    "hiring_post",
    "direct_conversation",
    "recruiter_owned_opening",
    "other_person_specific",
}

RECRUITING_PATTERN = re.compile(r"\b(recruit|talent acquisition|sourc(?:er|ing))", re.IGNORECASE)
PRODUCT_LEADERSHIP_PATTERN = re.compile(
    r"\b(chief product|cpo|vp.{0,12}product|vice president.{0,12}product|head of product|"
    r"director of product|product director)",
    re.IGNORECASE,
)
PRODUCT_PATTERN = re.compile(r"\b(product manager|product management|product lead|product owner)\b", re.IGNORECASE)
FOUNDER_PATTERN = re.compile(r"\b(founder|co-founder|chief executive|ceo|president)\b", re.IGNORECASE)
DIRECT_HIRING_PATTERN = re.compile(
    r"\b(?:i(?:'m| am)|we(?:'re| are)|my team is|our team is)\s+(?:actively\s+)?hiring\b|"
    r"\b(?:hiring|looking)\s+for\s+(?:an?\s+)?(?:product|senior product|lead product|technical product|"
    r"associate product)\s+(?:manager|lead|owner)\b|"
    r"\bopen(?:ing)?\s+(?:for|on my team|role|position)\b",
    re.IGNORECASE,
)


@transactional('project_dir', 'project')
def import_linkedin_export(
    archive_path: Path,
    project_dir: Path,
    today: date | None = None,
) -> dict[str, int]:
    today = today or date.today()
    if not archive_path.exists():
        raise FileNotFoundError(f"LinkedIn export not found: {archive_path}")

    if archive_path.stat().st_size > 100000000: raise ValueError('LinkedIn archive exceeds 100 MB')
    with zipfile.ZipFile(archive_path) as archive:
        members=archive.infolist()
        if len(members)>1000 or sum(m.file_size for m in members)>50000000 or any(m.file_size>20000000 for m in members):
            raise ValueError('LinkedIn export exceeds the supported decompression limits')
        names = set(archive.namelist())
        if "Connections.csv" not in names:
            raise ValueError("The archive does not contain Connections.csv")
        connections = _linkedin_csv(archive.read("Connections.csv"), "First Name")
        own_name = _profile_name(archive) or ""
        messages = _linkedin_csv(archive.read("messages.csv"), "CONVERSATION ID") if "messages.csv" in names else []

    url_to_connection = {
        _clean_url(row.get("URL", "")): row for row in connections if _clean_url(row.get("URL", ""))
    }
    message_signals = _message_signals(messages, set(url_to_connection), own_name, today)

    rows: list[dict[str, str]] = []
    for connection in connections:
        first_name = connection.get("First Name", "").strip()
        last_name = connection.get("Last Name", "").strip()
        profile_url = _clean_url(connection.get("URL", ""))
        if not profile_url and not first_name and not last_name:
            continue
        identity = profile_url or "|".join([first_name, last_name, connection.get("Company", "")])
        signal = message_signals.get(profile_url, {})
        rows.append(
            {
                "connection_id": "li_" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:14],
                "first_name": first_name,
                "last_name": last_name,
                "name": " ".join(part for part in [first_name, last_name] if part),
                "profile_url": profile_url,
                "email": connection.get("Email Address", "").strip(),
                "company": connection.get("Company", "").strip(),
                "title": connection.get("Position", "").strip(),
                "connected_on": _linkedin_date(connection.get("Connected On", "")),
                "message_inbound_count": str(signal.get("inbound", 0)),
                "message_outbound_count": str(signal.get("outbound", 0)),
                "last_message_date": str(signal.get("last_message_date", "")),
                "direct_hiring_evidence_date": str(signal.get("hiring_evidence_date", "")),
                "direct_hiring_evidence_type": (
                    "direct_hiring_message" if signal.get("hiring_evidence_date") else ""
                ),
                "source": "linkedin_export",
            }
        )

    rows.sort(key=lambda row: (row["last_name"].lower(), row["first_name"].lower()))
    data_dir = project_dir / "data"
    _write_rows(data_dir / "linkedin_connections.csv", rows, CONNECTION_FIELDS)
    _ensure_reviews(data_dir)
    _update_local_config(
        project_dir,
        {
            "linkedin_export_path": str(archive_path.resolve()),
            "linkedin_imported_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {
        "connections": len(rows),
        "with_messages": sum(
            int(row["message_inbound_count"]) + int(row["message_outbound_count"]) > 0 for row in rows
        ),
        "recent_hiring_signals": sum(bool(row["direct_hiring_evidence_date"]) for row in rows),
    }


@transactional('project_dir', 'project')
def refresh_linkedin_export(project_dir: Path, today: date | None = None) -> dict[str, int]:
    config = _local_config(project_dir)
    archive_path = config.get("linkedin_export_path", "")
    if not archive_path:
        raise FileNotFoundError("No LinkedIn export has been imported yet")
    return import_linkedin_export(Path(archive_path), project_dir, today=today)


@transactional('data_dir', 'data')
def build_connection_rankings(
    data_dir: Path,
    out_dir: Path,
    today: date | None = None,
) -> dict[str, int]:
    today = today or date.today()
    out_dir.mkdir(parents=True, exist_ok=True)
    _ensure_reviews(data_dir)
    connections = _read_rows(data_dir / "linkedin_connections.csv")
    reviews = {row.get("connection_id", ""): row for row in _read_rows(data_dir / "connection_reviews.csv")}
    target_companies = {
        _company_key(row.get("company", "")): row for row in _read_rows(data_dir / "companies.csv")
    }
    recent_roles = _recent_roles(data_dir, today, days=90)
    roles_by_company: dict[str, list[dict[str, str]]] = {}
    for role in recent_roles:
        roles_by_company.setdefault(_company_key(role.get("company", "")), []).append(role)

    ranked: list[dict[str, str]] = []
    for connection in connections:
        review = reviews.get(connection.get("connection_id", ""), {})
        company_key = _company_key(connection.get("company", ""))
        company_roles = roles_by_company.get(company_key, [])
        matching_role = company_roles[0] if company_roles else {}
        row = _rank_connection(connection, review, matching_role, company_key in target_companies, today)
        ranked.append(row)

    tier_order = {
        "Tier 1 - Recent hiring": 0,
        "Tier 2 - Warm relevance": 1,
        "Watchlist": 2,
        "Unranked": 3,
        "Excluded": 4,
    }
    ranked.sort(
        key=lambda row: (
            tier_order.get(row["outreach_tier"], 9),
            -int(row["connection_score"]),
            row["name"].lower(),
        )
    )
    _write_rows(out_dir / "connections_ranked.csv", ranked, RANKED_CONNECTION_FIELDS)
    return connection_stats(ranked)


def connection_stats(rows: list[dict[str, str]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "tier1": sum(row.get("outreach_tier") == "Tier 1 - Recent hiring" for row in rows),
        "tier2": sum(row.get("outreach_tier") == "Tier 2 - Warm relevance" for row in rows),
        "watchlist": sum(row.get("outreach_tier") == "Watchlist" for row in rows),
        "with_history": sum(
            int(row.get("message_inbound_count", "0") or 0) + int(row.get("message_outbound_count", "0") or 0) > 0
            for row in rows
        ),
        "approved": sum(row.get("review_status") == "approved_to_contact" for row in rows),
    }


@transactional('data_dir', 'data')
def save_connection_review(data_dir: Path, payload: dict[str, object]) -> dict[str, str]:
    connection_id = str(payload.get("connection_id", "")).strip()
    if not connection_id:
        raise ValueError("connection_id is required")
    status = str(payload.get("status", "needs_review")).strip() or "needs_review"
    allowed_statuses = {"needs_review", "approved_to_contact", "contacted", "follow_up", "skip"}
    if status not in allowed_statuses:
        raise ValueError("invalid connection review status")

    evidence_type = str(payload.get("hiring_evidence_type", "")).strip()
    evidence_date = str(payload.get("hiring_evidence_date", "")).strip()
    if evidence_type and evidence_type not in HIRING_EVIDENCE_TYPES - {"direct_hiring_message"}:
        raise ValueError("invalid hiring evidence type")
    if evidence_date:
        try:
            date.fromisoformat(evidence_date)
        except ValueError as exc:
            raise ValueError("hiring_evidence_date must be YYYY-MM-DD") from exc

    row = {
        "connection_id": connection_id,
        "status": status,
        "notes": str(payload.get("notes", "")).strip(),
        "do_not_contact": "true" if _truthy(str(payload.get("do_not_contact", ""))) or status == "skip" else "false",
        "hiring_evidence_date": evidence_date,
        "hiring_evidence_type": evidence_type,
        "hiring_evidence_url": public_url(payload.get("hiring_evidence_url", "")),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = data_dir / "connection_reviews.csv"
    rows = _read_rows(path)
    updated = [existing for existing in rows if existing.get("connection_id") != connection_id]
    updated.append(row)
    _write_rows(path, updated, CONNECTION_REVIEW_FIELDS)
    return row


def linkedin_source_status(project_dir: Path) -> dict[str, str]:
    config = _local_config(project_dir)
    source_path = config.get("linkedin_export_path", "")
    return {
        "path": source_path,
        "filename": Path(source_path).name if source_path else "",
        "imported_at": config.get("linkedin_imported_at", ""),
        "available": "true" if source_path and Path(source_path).exists() else "false",
    }


def _rank_connection(
    connection: dict[str, str],
    review: dict[str, str],
    matching_role: dict[str, str],
    is_target_company: bool,
    today: date,
) -> dict[str, str]:
    title = connection.get("title", "")
    company = connection.get("company", "")
    text = f"{company} {title}"
    inbound = int(connection.get("message_inbound_count", "0") or 0)
    outbound = int(connection.get("message_outbound_count", "0") or 0)
    last_message = _date_value(connection.get("last_message_date", ""))
    connected_on = _date_value(connection.get("connected_on", ""))
    reasons: list[str] = []

    warmth = 0
    if inbound and outbound:
        warmth += 35
        reasons.append("two-way message history")
        relationship = "Warm: two-way history"
    elif inbound:
        warmth += 22
        reasons.append("inbound message history")
        relationship = "Known: inbound history"
    elif outbound:
        warmth += 12
        reasons.append("previously contacted")
        relationship = "Reached out before"
    else:
        relationship = "No recorded messages"
    if last_message:
        age = (today - last_message).days
        if 0 <= age <= 90:
            warmth += 20
            reasons.append("message in last 90 days")
        elif age <= 365:
            warmth += 10
            reasons.append("message in last year")
        else:
            warmth += 4
    if connected_on:
        connection_age = (today - connected_on).days
        if 0 <= connection_age <= 90:
            warmth += 8
            reasons.append("connected in last 90 days")
        elif connection_age <= 365:
            warmth += 4

    strategic = 0
    if matching_role:
        strategic += 35
        reasons.append("company has a role posted in last 90 days")
        posted_date = _date_value(matching_role.get("posted_date", ""))
        if posted_date and (today - posted_date).days <= 7:
            strategic += 10
            reasons.append("company role posted in last week")
    if is_target_company:
        strategic += 20
        reasons.append("target company")
    is_recruiter = bool(RECRUITING_PATTERN.search(title))
    if is_recruiter:
        strategic += 15
        reasons.append("recruiting role")
    if PRODUCT_LEADERSHIP_PATTERN.search(title):
        strategic += 15
        reasons.append("product decision-maker")
    elif PRODUCT_PATTERN.search(title):
        strategic += 8
        reasons.append("product peer")
    if FOUNDER_PATTERN.search(title):
        strategic += 6
        reasons.append("founder or executive")
    direct_date = _date_value(connection.get("direct_hiring_evidence_date", ""))
    manual_date = _date_value(review.get("hiring_evidence_date", ""))
    evidence_date = max((value for value in [direct_date, manual_date] if value), default=None)
    if evidence_date == manual_date and manual_date:
        evidence_type = review.get("hiring_evidence_type", "")
        evidence_url = review.get("hiring_evidence_url", "")
    else:
        evidence_type = connection.get("direct_hiring_evidence_type", "")
        evidence_url = ""

    if not evidence_date and is_recruiter and matching_role:
        evidence_date = _date_value(matching_role.get("posted_date", ""))
        evidence_type = "recruiter_owned_opening"
        evidence_url = matching_role.get("role_url", "")
    recent_hiring = bool(evidence_date and 0 <= (today - evidence_date).days <= 90 and evidence_type)
    hiring_score = 50 if recent_hiring else 0
    if recent_hiring:
        reasons.insert(0, "person-specific hiring evidence in last 90 days")

    status = review.get("status", "needs_review") or "needs_review"
    do_not_contact = _truthy(review.get("do_not_contact", "")) or status == "skip"
    if do_not_contact:
        tier = "Excluded"
    elif recent_hiring:
        tier = "Tier 1 - Recent hiring"
    elif (warmth >= 20 and strategic >= 8) or (is_target_company and strategic >= 28):
        tier = "Tier 2 - Warm relevance"
    elif warmth >= 20 or strategic >= 8:
        tier = "Watchlist"
    else:
        tier = "Unranked"

    return {
        **{field: connection.get(field, "") for field in CONNECTION_FIELDS},
        "relationship_label": relationship,
        "warmth_score": str(warmth),
        "strategic_score": str(strategic),
        "connection_score": str(hiring_score + warmth + strategic),
        "outreach_tier": tier,
        "recent_hiring": "true" if recent_hiring else "false",
        "hiring_evidence_date": evidence_date.isoformat() if evidence_date else "",
        "hiring_evidence_type": evidence_type,
        "hiring_evidence_url": evidence_url,
        "matching_role_id": matching_role.get("role_id", ""),
        "matching_role_title": matching_role.get("role_title", ""),
        "matching_role_url": matching_role.get("role_url", ""),
        "matching_role_posted_date": matching_role.get("posted_date", ""),
        "priority_reasons": "; ".join(reasons) or "No qualifying relevance signal",
        "review_status": status,
        "review_notes": review.get("notes", ""),
        "do_not_contact": "true" if do_not_contact else "false",
    }


def _message_signals(
    messages: list[dict[str, str]],
    connection_urls: set[str],
    own_name: str,
    today: date,
) -> dict[str, dict[str, object]]:
    signals: dict[str, dict[str, object]] = {}
    recent_cutoff = today - timedelta(days=90)
    for message in messages:
        message_date = _datetime_date(message.get("DATE", ""))
        if not message_date:
            continue
        sender_url = _clean_url(message.get("SENDER PROFILE URL", ""))
        sender_name = message.get("FROM", "").strip().lower()
        recipients = {_clean_url(url) for url in _profile_urls(message.get("RECIPIENT PROFILE URLS", ""))}
        if sender_name == own_name.lower():
            target_urls = recipients & connection_urls
            direction = "outbound"
        elif sender_url in connection_urls:
            target_urls = {sender_url}
            direction = "inbound"
        else:
            continue

        for target_url in target_urls:
            signal = signals.setdefault(
                target_url,
                {"inbound": 0, "outbound": 0, "last_message_date": "", "hiring_evidence_date": ""},
            )
            signal[direction] = int(signal[direction]) + 1
            signal["last_message_date"] = max(str(signal["last_message_date"]), message_date.isoformat())
            if direction == "inbound" and message_date >= recent_cutoff:
                evidence_text = " ".join(
                    [
                        message.get("SUBJECT", ""),
                        message.get("CONVERSATION TITLE", ""),
                        message.get("CONTENT", ""),
                    ]
                )
                if DIRECT_HIRING_PATTERN.search(evidence_text):
                    signal["hiring_evidence_date"] = max(
                        str(signal["hiring_evidence_date"]), message_date.isoformat()
                    )
    return signals


def _recent_roles(data_dir: Path, today: date, days: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for filename in ["jobs_seed.csv", "jobs_fetched.csv"]:
        rows.extend(_read_rows(data_dir / filename))
    eligible: list[dict[str, str]] = []
    for row in rows:
        posted_date = _date_value(row.get("posted_date", ""))
        age = (today - posted_date).days if posted_date else days + 1
        if row.get("status", "").strip().lower() == "open" and 0 <= age <= days:
            eligible.append(row)
    eligible.sort(key=lambda row: row.get("posted_date", ""), reverse=True)
    return eligible


def _profile_name(archive: zipfile.ZipFile) -> str:
    if "Profile.csv" not in archive.namelist():
        return ""
    rows = _linkedin_csv(archive.read("Profile.csv"), "First Name")
    if not rows:
        return ""
    return " ".join(part for part in [rows[0].get("First Name", ""), rows[0].get("Last Name", "")] if part)


def _linkedin_csv(raw: bytes, header_prefix: str) -> list[dict[str, str]]:
    lines = raw.decode("utf-8-sig", errors="replace").splitlines()
    try:
        start = next(
            index
            for index, line in enumerate(lines)
            if (next(csv.reader([line]), [""]) or [""])[0].strip() == header_prefix
        )
    except StopIteration:
        return []
    return [dict(row) for row in csv.DictReader(io.StringIO("\n".join(lines[start:])))]


def _profile_urls(value: str) -> set[str]:
    return set(re.findall(r"https://www\.linkedin\.com/in/[^,;\s\]\"]+", value or ""))


def _linkedin_date(value: str) -> str:
    try:
        return datetime.strptime(value.strip(), "%d %b %Y").date().isoformat()
    except ValueError:
        return ""


def _datetime_date(value: str) -> date | None:
    value = (value or "").strip()
    try:
        if value.endswith(" UTC"):
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC").date()
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _date_value(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def _clean_url(value: str) -> str:
    from .validation import public_url
    try: return public_url(value).rstrip('/')
    except ValueError: return '' 


def _company_key(value: str) -> str:
    normalized = (value or "").lower().replace("&", "and")
    normalized = re.sub(r"\b(incorporated|inc|llc|ltd|corp|corporation|company|co)\b", "", normalized)
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _truthy(value: str) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _ensure_reviews(data_dir: Path) -> None:
    path = data_dir / "connection_reviews.csv"
    if not path.exists():
        _write_rows(path, [], CONNECTION_REVIEW_FIELDS)


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_rows(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    atomic_csv(path, rows, fields, spreadsheet_safe=path.name in {'connections_ranked.csv','weekly_queue.csv','fullenrich_queue.csv'})


def _local_config(project_dir: Path) -> dict[str, str]:
    path = project_dir / ".job-system.local.json"
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            return {str(key): str(value) for key, value in json.load(handle).items()}
    except (json.JSONDecodeError, OSError):
        return {}


def _update_local_config(project_dir: Path, updates: dict[str, str]) -> None:
    atomic_json(project_dir / '.job-system.local.json', {**_local_config(project_dir), **updates})
