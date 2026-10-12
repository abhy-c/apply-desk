from __future__ import annotations

from .storage import transactional, atomic_csv, atomic_json, atomic_text

import hashlib
import ipaddress
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from .network import download
from .validation import public_url

from .adapters import JOB_FIELDS, clean_text, infer_seniority, infer_workplace
from .io import write_csv
from .scoring import is_us_location


MAX_IMPORT_URLS = 25
MAX_PAGE_BYTES = 2_000_000
HIRINGCAFE_HOSTS = {"hiringcafe.com", "www.hiringcafe.com", "hiring.cafe", "www.hiring.cafe"}
NO_SPONSORSHIP = re.compile(
    r"(?:unable to (?:provide )?(?:visa )?sponsor|will not (?:provide )?(?:visa )?sponsor|"
    r"no (?:visa )?sponsorship|not (?:eligible|available) for (?:visa )?sponsorship|"
    r"without (?:the need for )?sponsorship(?: now or in the future)?|"
    r"do not sponsor|does not sponsor|cannot sponsor)",
    re.IGNORECASE,
)
PageLoader = Callable[[str], tuple[str, str]]


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._capturing = False
        self._chunks: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attributes = {key.lower(): (value or "").lower() for key, value in attrs}
        if "ld+json" in attributes.get("type", ""):
            self._capturing = True
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capturing:
            self.scripts.append("".join(self._chunks).strip())
            self._capturing = False
            self._chunks = []


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        _validate_official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@transactional('data_dir', 'data')
def import_official_job_urls(
    data_dir: Path,
    raw_urls: str,
    *,
    today: date | None = None,
    page_loader: PageLoader | None = None,
) -> dict[str, object]:
    urls = parse_import_urls(raw_urls)
    today = today or date.today()
    loader = page_loader or _load_page
    path = data_dir / "jobs_seed.csv"
    existing = _read_rows(path)
    comparison_rows = [
        *existing,
        *_read_rows(data_dir / "jobs_fetched.csv"),
        *_read_rows(data_dir / "legaltech_roles.csv"),
    ]
    known_urls = {_canonical_url(row.get("role_url", "")) for row in comparison_rows if row.get("role_url")}
    known_ids = {row.get("role_id", "") for row in comparison_rows}
    accepted: list[dict[str, str]] = []
    results: list[dict[str, str]] = []

    def fetch_one(url: str) -> tuple[str, dict[str, str] | None, str]:
        try:
            return url, fetch_official_job(url, today=today, page_loader=loader), ""
        except Exception as exc:  # Each URL should report its own failure without aborting the batch.
            return url, None, str(exc)

    with ThreadPoolExecutor(max_workers=min(5, len(urls))) as executor:
        fetched = list(executor.map(fetch_one, urls))

    for url, row, error in fetched:
        if row is None:
            results.append({"url": url, "final_url": "", "status": "rejected", "message": error})
            continue
        try:
            canonical = _canonical_url(row["role_url"])
            if canonical in known_urls or row["role_id"] in known_ids:
                results.append(
                    {
                        "url": url,
                        "final_url": row["role_url"],
                        "status": "duplicate",
                        "message": f"Already in Apply Desk: {row['company']} - {row['role_title']}",
                    }
                )
                continue
            known_urls.add(canonical)
            known_ids.add(row["role_id"])
            accepted.append(row)
            results.append(
                {
                    "url": url,
                    "final_url": row["role_url"],
                    "status": "imported",
                    "message": f"{row['company']} - {row['role_title']}",
                }
            )
        except Exception as exc:
            results.append({"url": url, "final_url": "", "status": "rejected", "message": str(exc)})

    if accepted:
        write_csv(path, [*existing, *accepted], JOB_FIELDS)

    return {
        "submitted": len(urls),
        "imported": len(accepted),
        "duplicates": sum(result["status"] == "duplicate" for result in results),
        "rejected": sum(result["status"] == "rejected" for result in results),
        "results": results,
    }


def parse_import_urls(raw_urls: str) -> list[str]:
    candidates = []
    for part in re.split(r"\s+", raw_urls or ""):
        value = part.strip()
        if not value:
            continue
        if value not in candidates:
            candidates.append(value)
    if not candidates:
        raise ValueError("Paste at least one official employer job URL.")
    if len(candidates) > MAX_IMPORT_URLS:
        raise ValueError(f"Import at most {MAX_IMPORT_URLS} URLs at a time.")
    return candidates


def fetch_official_job(url: str, *, today: date, page_loader: PageLoader | None = None) -> dict[str, str]:
    _validate_official_url(url)
    final_url, html = (page_loader or _load_page)(url)
    _validate_official_url(final_url)
    final_url = public_url(final_url,required=True)
    posting = extract_job_posting(html)
    return normalize_job_posting(posting, final_url, today=today)


def extract_job_posting(html: str) -> dict[str, object]:
    parser = _JsonLdParser()
    parser.feed(html)
    for script in parser.scripts:
        if not script:
            continue
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            continue
        posting = _find_job_posting(payload)
        if posting:
            return posting
    raise ValueError("The official page does not expose structured JobPosting metadata.")


def normalize_job_posting(posting: dict[str, object], final_url: str, *, today: date) -> dict[str, str]:
    title = clean_text(str(posting.get("title", "")))
    organization = posting.get("hiringOrganization")
    company = clean_text(str(organization.get("name", ""))) if isinstance(organization, dict) else ""
    posted_date = _iso_date(str(posting.get("datePosted", "")))
    if not title or not company:
        raise ValueError("The official posting is missing a job title or employer name.")
    if not posted_date:
        raise ValueError("Rejected: no original publication date on the official posting.")

    age_days = (today - posted_date).days
    if age_days < 0:
        raise ValueError("Rejected: the posting date is in the future.")
    if age_days > 14:
        raise ValueError(f"Rejected: posted {age_days} days ago; Apply Desk allows at most 14 days.")

    valid_through = _iso_date(str(posting.get("validThrough", "")))
    if valid_through and valid_through < today:
        raise ValueError("Rejected: the official posting has expired.")

    location = _job_location(posting)
    if not is_us_location(location):
        raise ValueError(f"Rejected: location is not clearly US-only ({location or 'missing location'}).")

    raw_description = str(posting.get("description", ""))
    if NO_SPONSORSHIP.search(raw_description):
        raise ValueError("Rejected: the official posting says visa sponsorship is unavailable.")
    description = clean_text(raw_description)
    workplace_text = f"{posting.get('jobLocationType', '')} {location} {description[:300]}"
    workplace = "remote" if "telecommute" in workplace_text.lower() else infer_workplace(workplace_text)
    canonical_url = _canonical_url(final_url)
    return {
        "role_id": f"official_{hashlib.sha256(canonical_url.encode('utf-8')).hexdigest()[:16]}",
        "company": company,
        "role_title": title,
        "role_url": final_url,
        "source": "official_url_import",
        "posted_date": posted_date.isoformat(),
        "location": location,
        "workplace": workplace,
        "domain_tags": ",".join(_infer_domain_tags(f"{company} {title} {description}")),
        "seniority": _role_seniority(title),
        "status": "open",
        "description": description,
    }


def _load_page(url: str) -> tuple[str, str]:
    return download(url,max_bytes=MAX_PAGE_BYTES,content_types={'text/html','application/xhtml+xml'})


def _validate_official_url(url: str) -> None:
    normalized=public_url(url,required=True)
    hostname=urllib.parse.urlparse(normalized).hostname
    if hostname in HIRINGCAFE_HOSTS or hostname.endswith('.hiringcafe.com'):
        raise ValueError("Paste the employer's official posting URL, not a HiringCafe page.")


def _find_job_posting(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        raw_type = value.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if any(str(item).lower() == "jobposting" for item in types):
            return value
        for nested in value.values():
            posting = _find_job_posting(nested)
            if posting:
                return posting
    elif isinstance(value, list):
        for nested in value:
            posting = _find_job_posting(nested)
            if posting:
                return posting
    return None


def _job_location(posting: dict[str, object]) -> str:
    parts: list[str] = []
    for location in _as_list(posting.get("jobLocation")):
        if not isinstance(location, dict):
            continue
        address = location.get("address")
        if isinstance(address, dict):
            parts.extend(_address_parts(address))
        elif isinstance(address, str):
            parts.append(clean_text(address))
    for requirement in _as_list(posting.get("applicantLocationRequirements")):
        if not isinstance(requirement, dict):
            continue
        name = clean_text(str(requirement.get("name", "")))
        if name:
            parts.append(_normalize_country(name))
        address = requirement.get("address")
        if isinstance(address, dict):
            parts.extend(_address_parts(address))
    return " · ".join(dict.fromkeys(part for part in parts if part))


def _address_parts(address: dict[str, object]) -> list[str]:
    locality = _clean_value(address.get("addressLocality"))
    region = _clean_value(address.get("addressRegion"))
    country_value = address.get("addressCountry", "")
    if isinstance(country_value, dict):
        country_value = country_value.get("name") or country_value.get("@id") or ""
    country = _normalize_country(_clean_value(country_value))
    local = ", ".join(part for part in [locality, region] if part)
    return [part for part in [local, country] if part]


def _normalize_country(value: str) -> str:
    return "United States" if value.strip().lower() in {"us", "usa", "u.s.", "united states of america"} else value


def _clean_value(value: object) -> str:
    return "" if value is None else clean_text(str(value))


def _iso_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _infer_domain_tags(text: str) -> list[str]:
    lowered = text.lower()
    tags = []
    patterns = {
        "legaltech": ["legal ai", "legal technology", "legal engineer", "contract lifecycle", "legal operations"],
        "fintech": ["fintech", "payments", "banking", "financial services"],
        "regtech": ["regtech", "compliance", "regulatory", "risk management"],
        "enterprise_ai": ["enterprise ai", "artificial intelligence", "generative ai", "large language model", "llm"],
        "enterprise_workflow": ["workflow", "automation", "operations platform"],
        "b2b_saas": ["b2b", "saas", "enterprise software"],
        "edtech": ["edtech", "education technology", "learning platform"],
    }
    for tag, terms in patterns.items():
        if any(term in lowered for term in terms):
            tags.append(tag)
    return tags


def _role_seniority(title: str) -> str:
    lowered = title.lower()
    if "product manager" in lowered or re.search(r"\bproduct lead\b", lowered):
        return infer_seniority(title)
    if "director" in lowered:
        return "Director"
    if "principal" in lowered:
        return "Principal"
    if "staff" in lowered:
        return "Staff"
    if "senior" in lowered or re.search(r"\bsr\.?\b", lowered):
        return "Senior"
    if "lead" in lowered:
        return "Lead"
    return "Individual contributor"


def _canonical_url(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    if parsed.hostname in {"jobs.ashbyhq.com", "jobs.lever.co"} and path.endswith(("/application", "/apply")):
        path = path.rsplit("/", 1)[0]
    query = urllib.parse.urlencode(
        [
            (key, value)
            for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in {"source", "ref", "gh_src", "lever-source"}
        ]
    )
    return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    import csv

    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]
