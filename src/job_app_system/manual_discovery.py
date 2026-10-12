"""Codex-triggered discovery intake: evidence, review gates, deduplication and run status.

The local app does not invoke chat connectors. Codex performs reader calls and
imports their raw structured evidence through these functions/CLI commands.
"""
from __future__ import annotations

from .storage import transactional, atomic_csv, atomic_json, atomic_text

import hashlib
import json
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from .adapters import JOB_FIELDS, clean_text, infer_seniority, infer_workplace, lever_description
from .discovery_import import _canonical_url, _infer_domain_tags, _job_location, NO_SPONSORSHIP
from .io import write_csv
from .scoring import is_us_location

LOCK = threading.RLock()
SOURCES = {"indeed": "Indeed", "builtin": "Built In", "yc": "Y Combinator",
           "wellfound": "Wellfound", "lennys_jobs": "Lenny's Jobs", "mind_the_product": "Mind the Product",
           "a16z": "a16z", "rlegaltech": "R Legal Tech"}
STORE = "discovery_records.json"
RUNS = "discovery_runs.json"
BOARD_HOSTS = {"indeed.com", "builtin.com", "ycombinator.com", "wellfound.com", "lennysjobs.com",
               "mindtheproduct.com", "jobs.a16z.com", "rlegaltech.com"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def _save(path: Path, value) -> None:
    atomic_json(path, value)


def _url(value: str) -> str:
    from .validation import public_url
    return _canonical_url(public_url(value, required=True))


def _is_official(url: str) -> bool:
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").removeprefix("www.")
    return not any(host == board or host.endswith("." + board) for board in BOARD_HOSTS)


def _iso_date(value) -> str:
    value = str(value or "")
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return ""


@transactional('project_dir', 'project')
def start_run(project_dir: Path, source_ids: list[str] | None = None) -> dict:
    ids = source_ids if source_ids is not None else list(SOURCES)
    if not ids or any(s not in SOURCES for s in ids) or len(ids) != len(set(ids)):
        raise ValueError("Choose valid, unique discovery sources")
    with LOCK:
        path = project_dir / "data" / RUNS
        runs = _read(path, [])
        if runs and runs[-1]["status"] == "running":
            raise ValueError("A discovery run is already in progress; finish it before starting another")
        run = {"run_id": uuid.uuid4().hex, "status": "running", "started_at": _now(), "finished_at": "",
               "reader": "Codex + connected readers", "scheduled": False,
               "sources": {s: {"name": SOURCES[s], "status": "queued", "phase": "Waiting for reader",
                               "fetched": 0, "new": 0, "updated": 0, "duplicates": 0,
                               "ready": 0, "needs_review": 0, "error": "", "coverage": "", "finished_at": ""} for s in ids}}
        runs.append(run)
        _save(path, runs[-20:])
    return run


@transactional('project_dir', 'project')
def update_source(project_dir: Path, run_id: str, source_id: str, *, phase: str = "", error: str = "") -> dict:
    with LOCK:
        path = project_dir / "data" / RUNS
        runs = _read(path, [])
        run = next((r for r in runs if r["run_id"] == run_id), None)
        if not run or run["status"] != "running" or source_id not in run["sources"]:
            raise ValueError("No matching active discovery source")
        entry = run["sources"][source_id]
        entry.update(status="failed" if error else "reading", phase=phase or "Reading job details", error=error[:1000])
        if error:
            entry["finished_at"] = _now()
        _save(path, runs)
    return entry


def evidence_record(document: dict) -> dict:
    """Normalize source fields without model-generated claims or guessed dates."""
    url = _url(document.get("url", ""))
    data = document.get("data")
    fmt = document.get("format")
    if not isinstance(data, dict):
        raise ValueError("Expected structured source data")
    record = {"role_url": url, "company": "", "role_title": "", "description": "", "location": "", "workplace": "",
              "posted_date": "", "posted_at": "", "listed_at": "", "date_basis": "unknown", "status": "open",
              "salary": {}, "employment_type": [], "requisition_id": "", "reposted": None}
    if fmt == "indeed":
        record.update(company=str((data.get("employer") or {}).get("name") or data.get("source_name") or ""),
                      role_title=str(data.get("title", "")), description=clean_text(str(data.get("description_text") or data.get("description_html") or "")),
                      location=str((data.get("location") or {}).get("formatted") or ""),
                      posted_at=str(data.get("posted_at") or ""), listed_at=str(data.get("listed_at") or ""),
                      salary=data.get("salary") or {}, requisition_id=str(data.get("job_key") or ""),
                      reposted=data.get("reposted"), status="closed" if data.get("expired") else "open",
                      date_basis="board_repost" if data.get("reposted") else "board_posting")
        labels = " ".join(str(a.get("label", "")) for a in data.get("attributes", []) if isinstance(a, dict))
        record["workplace"] = infer_workplace(labels)
        if data.get("apply_url"):
            record["employer_url"] = _url(data["apply_url"])
    elif fmt == "builtin":
        record.update(company=str(data.get("company_name", "")), role_title=str(data.get("title", "")),
                      description=clean_text(str(data.get("description", ""))), posted_at=str(data.get("date_posted") or ""),
                      date_basis="board_posting", workplace=infer_workplace(str(data.get("remote_type", ""))),
                      employment_type=data.get("employment_types", []), requisition_id=str(data.get("job_id") or ""),
                      salary={key: data.get(key) for key in ("salary_min", "salary_max", "salary_currency", "salary_unit")})
        locations = data.get("locations", [])
        record["location"] = " · ".join(str(l.get("formatted") or l.get("name") or ", ".join(str(l.get(k) or "") for k in ("city", "region", "country"))) if isinstance(l, dict) else str(l) for l in locations)
    elif fmt == "jobposting":
        types = data.get("@type")
        if "JobPosting" not in (types if isinstance(types, list) else [types]):
            raise ValueError("Expected JobPosting source metadata")
        record.update(company=str((data.get("hiringOrganization") or {}).get("name", "")), role_title=str(data.get("title", "")),
                      description=clean_text(str(data.get("description", ""))), location=_job_location(data),
                      workplace=infer_workplace(str(data.get("jobLocationType", ""))), posted_at=str(data.get("datePosted") or ""),
                      date_basis="official_publication" if _is_official(url) else "board_posting",
                      salary=data.get("baseSalary") or {}, employment_type=data.get("employmentType") or [])
        identifier = data.get("identifier")
        record["requisition_id"] = str(identifier.get("value", "")) if isinstance(identifier, dict) else str(identifier or "")
        expiration = _iso_date(data.get("validThrough"))
        if expiration and date.fromisoformat(expiration) < date.today():
            record["status"] = "closed"
    elif fmt in {"ashby", "lever"}:
        if not _is_official(url):
            raise ValueError("ATS evidence must come from an employer ATS URL")
        record["company"] = str(document.get("company", ""))
        record["role_title"] = str(data.get("title") or data.get("text") or "")
        record["requisition_id"] = str(data.get("id") or "")
        record["date_basis"] = "official_publication"
        if fmt == "ashby":
            record.update(location=str(data.get("location") or ""), posted_at=str(data.get("publishedAt") or ""),
                          description=clean_text(str(data.get("descriptionPlain") or data.get("descriptionHtml") or "")),
                          workplace=infer_workplace(str(data.get("workplaceType") or ("remote" if data.get("isRemote") is True else ""))),
                          status="closed" if data.get("isListed") is False else "open")
        else:
            created = data.get("createdAt")
            record.update(location=str((data.get("categories") or {}).get("location") or ""),
                          posted_at=datetime.fromtimestamp(created / 1000, timezone.utc).isoformat() if isinstance(created, (int, float)) else "",
                          description=lever_description(data), workplace=infer_workplace(str(data.get("workplaceType") or "")))
    elif fmt == "page":
        # Visible full page evidence can be retained, but does not establish job metadata.
        record.update(role_title=str(document.get("title") or "Unverified posting"),
                      description=str(data.get("markdown") or ""), date_basis="unknown")
    else:
        raise ValueError("Unsupported discovery evidence format")
    record["posted_date"] = _iso_date(record["posted_at"])
    return record


@transactional('project_dir', 'project')
def import_source(project_dir: Path, payload: dict) -> dict:
    run_id, source_id = payload.get("run_id"), payload.get("source_id")
    documents = payload.get("documents", [])
    if not isinstance(documents, list) or len(documents) > 250:
        raise ValueError("Import at most 250 source documents per batch")
    if not payload.get("coverage"):
        raise ValueError("Describe the actual search/pagination coverage")
    with LOCK:
        run_path = project_dir / "data" / RUNS
        runs = _read(run_path, [])
        run = next((r for r in runs if r["run_id"] == run_id), None)
        if not run or run["status"] != "running" or source_id not in run["sources"]:
            raise ValueError("No matching active discovery source")
        records = _read(project_dir / "data" / STORE, [])
        aliases = {alias: r for r in records for alias in r["aliases"]}
        counts = {"fetched": 0, "new": 0, "updated": 0, "duplicates": 0, "ready": 0, "needs_review": 0}
        now = _now()
        for document in documents:
            listing = evidence_record(document)
            official = document.get("official")
            evidence = [document]
            current_aliases = {listing["role_url"]}
            if listing.get("employer_url"):
                current_aliases.add(listing["employer_url"])
            if official:
                confirmed = evidence_record(official)
                if not _is_official(confirmed["role_url"]):
                    raise ValueError("Official evidence cannot be another aggregator page")
                listing = confirmed
                current_aliases.add(listing["role_url"])
                evidence.append(official)
            matches = [r for r in records if current_aliases.intersection(r["aliases"])]
            matches.sort(key=lambda r: r["first_seen_at"])
            existing = matches[0] if matches else None
            for duplicate in matches[1:]:
                existing["aliases"] = sorted(set(existing["aliases"]) | set(duplicate["aliases"]))
                existing["source_ids"] = list(dict.fromkeys(existing["source_ids"] + duplicate["source_ids"]))
                existing["evidence"].extend(duplicate["evidence"])
                records.remove(duplicate)
                for alias in duplicate["aliases"]: aliases[alias] = existing
            # Preserve stronger evidence, but recheck its age on every observation.
            if existing and existing["date_basis"] == "official_publication" and listing["date_basis"] != "official_publication":
                for key in listing:
                    if key in existing: listing[key] = existing[key]
            reasons = []
            if not listing["company"]: reasons.append("Employer metadata missing")
            if not listing["role_title"]: reasons.append("Title missing")
            if not listing["description"]: reasons.append("Full job description missing")
            if listing["date_basis"] != "official_publication": reasons.append("Original employer publication date not verified")
            if not listing["posted_date"]: reasons.append("Publication date missing")
            else:
                age = (date.today() - date.fromisoformat(listing["posted_date"])).days
                if age < 0: reasons.append("Publication date is in the future")
                if age > 14: reasons.append("Older than 14 days")
            if not is_us_location(listing["location"]): reasons.append("US location not confirmed")
            if listing["status"] != "open": reasons.append("Posting is closed or expired")
            if NO_SPONSORSHIP.search(listing["description"]): reasons.append("Posting excludes sponsorship")
            if "security test" in listing["role_title"].lower() or "secprobe" in listing["role_title"].lower(): reasons.append("Test listing, not a vacancy")
            status = "needs_review" if reasons else "ready"
            if existing:
                counts["duplicates"] += 1
                counts["updated"] += 1
            row = {**listing, "role_id": existing["role_id"] if existing else "discovered_" + hashlib.sha256(listing["role_url"].encode()).hexdigest()[:16],
                   "source": "discovery:" + source_id, "source_ids": list(dict.fromkeys((existing or {}).get("source_ids", []) + [source_id])),
                   "aliases": sorted(set((existing or {}).get("aliases", [])) | current_aliases),
                   "first_seen_at": existing["first_seen_at"] if existing else now, "last_verified_at": now,
                   "review_status": status, "review_reasons": reasons, "evidence": (existing or {}).get("evidence", []) + evidence,
                   "domain_tags": ",".join(_infer_domain_tags(f"{listing['company']} {listing['role_title']} {listing['description']}")),
                   "seniority": infer_seniority(listing["role_title"])}
            if existing: existing.update(row); row = existing
            else: records.append(row); counts["new"] += 1
            for alias in row["aliases"]: aliases[alias] = row
            counts["fetched"] += 1
            counts["ready" if status == "ready" else "needs_review"] += 1
        _save(project_dir / "data" / STORE, records)
        write_csv(project_dir / "data/jobs_discovered.csv", [r for r in records if r["review_status"] == "ready"], JOB_FIELDS)
        entry = run["sources"][source_id]
        entry.update(counts, status="complete" if payload.get("complete") is True else "partial",
                     phase="Imported full details", coverage=str(payload["coverage"]), finished_at=now, error="")
        _save(run_path, runs)
    return entry


@transactional('project_dir', 'project')
def finish_run(project_dir: Path, run_id: str) -> dict:
    with LOCK:
        path = project_dir / "data" / RUNS
        runs = _read(path, [])
        run = next((r for r in runs if r["run_id"] == run_id), None)
        if not run or run["status"] != "running": raise ValueError("No matching active discovery run")
        for source in run["sources"].values():
            if source["status"] in {"queued", "reading"}:
                source.update(status="failed", error="Reader did not finish; existing results retained", finished_at=_now())
        run.update(status="complete" if all(s["status"] == "complete" for s in run["sources"].values()) else "partial", finished_at=_now())
        _save(path, runs)
    return run


def discovery_state(project_dir: Path) -> dict:
    runs = _read(project_dir / "data" / RUNS, [])
    records = _read(project_dir / "data" / STORE, [])
    latest_sources = {}
    for run in runs:
        latest_sources.update({sid: {**entry, "started_at": run["started_at"]} for sid, entry in run["sources"].items()})
    return {"reader_mode": "codex_manual", "api_key_required": False, "scheduled": False,
            "latest_run": runs[-1] if runs else None, "source_status": latest_sources,
            "stats": {"total": len(records), "ready": sum(r["review_status"] == "ready" for r in records),
                      "needs_review": sum(r["review_status"] == "needs_review" for r in records)},
            "needs_review": [{key: r[key] for key in ("role_id", "company", "role_title", "role_url", "review_reasons", "source_ids")} for r in records if r["review_status"] == "needs_review"]}
