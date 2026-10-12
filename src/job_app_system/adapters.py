from __future__ import annotations

from .storage import transactional, atomic_csv, atomic_json, atomic_text

import json
import html
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from .network import json_download

from .io import read_ats_sources, write_csv

JOB_FIELDS = [
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
    "description",
]


def fetch_greenhouse_board(board_token: str) -> list[dict[str, object]]:
    url=f'https://boards-api.greenhouse.io/v1/boards/{urllib.parse.quote(board_token,safe="")}/jobs?content=true'
    return list(json_download(url).get('jobs',[]))


def fetch_lever_postings(company_slug: str) -> list[dict[str, object]]:
    return list(json_download(f'https://api.lever.co/v0/postings/{urllib.parse.quote(company_slug,safe="")}?mode=json'))


def fetch_ashby_postings(company_slug: str) -> list[dict[str, object]]:
    return list(json_download(f'https://api.ashbyhq.com/posting-api/job-board/{urllib.parse.quote(company_slug,safe="")}').get('jobs',[]))


def load_apify_dataset_export(path: Path) -> list[dict[str, object]]:
    """Load a JSON export downloaded from an Apify dataset."""
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and "items" in payload:
        return list(payload["items"])
    raise ValueError(f"Unsupported Apify export shape: {path}")


@transactional('sources_path', 'file')
def fetch_enabled_ats_sources(sources_path: Path, out_path: Path) -> int:
    rows: list[dict[str, object]] = []
    for source in read_ats_sources(sources_path):
        if source.get("enabled", "").strip().lower() not in {"true", "yes", "1"}:
            continue
        from .workspace import read
        configured = read(sources_path.parent.parent)["setup"]
        if configured.get("titles"):
            source = {**source, "target_titles": configured["titles"], "excluded_titles": configured.get("excluded_titles", "")}
        ats = source.get("ats", "").strip().lower()
        try:
            if ats == "greenhouse":
                raw_jobs = fetch_greenhouse_board(source["slug"].strip())
                rows.extend(normalize_greenhouse_jobs(source, raw_jobs))
            elif ats == "ashby":
                raw_jobs = fetch_ashby_postings(source["slug"].strip())
                rows.extend(normalize_ashby_jobs(source, raw_jobs))
            elif ats == "lever":
                raw_jobs = fetch_lever_postings(source["slug"].strip())
                rows.extend(normalize_lever_jobs(source, raw_jobs))
            else:
                raise ValueError(f"Unsupported ATS type: {ats}")
            matches = [row for row in rows if row.get('company') == source.get('company')]
            _record_source_check(sources_path.parent.parent, source, len(raw_jobs), len(matches), '')
        except (ValueError, OSError) as exc:
            _record_source_check(sources_path.parent.parent, source, 0, 0, str(exc))
            continue

    from .validation import job
    rows=[job(row) for row in rows]
    write_csv(out_path, rows, JOB_FIELDS)
    return len(rows)


def normalize_greenhouse_jobs(source: dict[str, str], jobs: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized = []
    for job in jobs:
        title = str(job.get("title", ""))
        if not _source_title_matches(title, source):
            continue
        location_data = job.get("location") if isinstance(job.get("location"), dict) else {}
        location = str(location_data.get("name") or source.get("location_hint", ""))
        normalized.append(
            {
                "role_id": f"greenhouse_{source['slug']}_{job.get('id')}",
                "company": source["company"],
                "role_title": title,
                "role_url": str(job.get("absolute_url", "")),
                "source": "greenhouse",
                "posted_date": greenhouse_date(job),
                "location": location,
                "workplace": infer_workplace(location + " " + title),
                "domain_tags": source.get("domain_tags", ""),
                "seniority": infer_seniority(title),
                "status": "open",
                "description": clean_text(str(job.get("content", ""))),
            }
        )
    return normalized


def normalize_ashby_jobs(source: dict[str, str], jobs: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized = []
    for job in jobs:
        title = str(job.get("title", ""))
        if not _source_title_matches(title, source):
            continue
        if job.get("isListed") is False:
            continue
        location = str(job.get("location") or source.get("location_hint", ""))
        published_at = str(job.get("publishedAt", ""))
        normalized.append(
            {
                "role_id": f"ashby_{source['slug']}_{job.get('id')}",
                "company": source["company"],
                "role_title": title,
                "role_url": str(job.get("jobUrl") or job.get("applyUrl") or ""),
                "source": "ashby",
                "posted_date": published_at[:10],
                "location": location,
                "workplace": ashby_workplace(job, location),
                "domain_tags": source.get("domain_tags", ""),
                "seniority": infer_seniority(title),
                "status": "open",
                "description": clean_text(str(job.get("descriptionPlain") or job.get("descriptionHtml") or "")),
            }
        )
    return normalized


def normalize_lever_jobs(source: dict[str, str], jobs: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized = []
    for job in jobs:
        title = str(job.get("text", ""))
        if not _source_title_matches(title, source):
            continue
        categories = job.get("categories") if isinstance(job.get("categories"), dict) else {}
        location = str(categories.get("location") or source.get("location_hint", ""))
        created_at = job.get("createdAt")
        posted_date = ""
        if isinstance(created_at, int):
            posted_date = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc).date().isoformat()
        normalized.append(
            {
                "role_id": f"lever_{source['slug']}_{job.get('id')}",
                "company": source["company"],
                "role_title": title,
                "role_url": str(job.get("hostedUrl", "")),
                "source": "lever",
                "posted_date": posted_date,
                "location": location,
                "workplace": infer_workplace(str(job.get("workplaceType", ""))) or infer_workplace(location),
                "domain_tags": source.get("domain_tags", ""),
                "seniority": infer_seniority(title),
                "status": "open",
                "description": lever_description(job),
            }
        )
    return normalized


def infer_seniority(title: str) -> str:
    lowered = title.lower()
    if "senior" in lowered or "sr." in lowered or "sr " in lowered:
        return "Senior PM"
    if "lead" in lowered:
        return "Lead PM"
    if "director" in lowered:
        return "Director"
    if "principal" in lowered:
        return "Principal PM"
    if "group" in lowered:
        return "Group PM"
    return "PM"


def infer_workplace(text: str) -> str:
    lowered = text.lower()
    if "hybrid" in lowered:
        return "hybrid"
    if "remote" in lowered or "telecommute" in lowered:
        return "remote"
    if "onsite" in lowered or "on-site" in lowered or "office" in lowered:
        return "onsite"
    return ""


def ashby_workplace(job: dict[str, object], location: str) -> str:
    explicit = infer_workplace(str(job.get("workplaceType", "")))
    if explicit:
        return explicit
    if job.get("isRemote") is True:
        return "remote"
    return infer_workplace(location)


def lever_description(job: dict[str, object]) -> str:
    """Lever separates the introduction, requirements lists, and closing text."""
    parts = [str(job.get("descriptionPlain") or job.get("description") or "")]
    for section in job.get("lists", []) or []:
        if isinstance(section, dict):
            parts.extend([str(section.get("text", "")), str(section.get("content", ""))])
    parts.append(str(job.get("additionalPlain") or job.get("additional") or ""))
    return clean_text(" ".join(parts))


def greenhouse_date(job: dict[str, object]) -> str:
    updated_at = str(job.get("updated_at", ""))
    if not updated_at:
        return ""
    return updated_at[:10]


def clean_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _source_title_matches(title, source):
    if source.get('target_titles'):
        from .workspace import title_matches
        return title_matches(title, {'titles':source['target_titles'],'excluded_titles':source.get('excluded_titles','')})
    return bool(str(title).strip())


def _record_source_check(root, source, usable, matches, error):
    from .workspace import read, source_result
    configured=read(root)
    item=next((x for x in configured['sources'] if x['name']==source.get('company') and x['method']=='feed'),None)
    if item:
        source_result(root,{'id':item['id'],'state':'failed' if error else 'working','usable':usable,'matches':min(matches,usable),
                            'error':error,'evidence':'Employer ATS public JSON response' if not error else 'ATS request failed',
                            'coverage':'Configured employer board: '+source.get('ats','')+'/'+source.get('slug','')})
