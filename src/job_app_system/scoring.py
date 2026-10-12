from __future__ import annotations

import re
from datetime import date

from .models import Company, Contact, Job

TARGET_DOMAINS = {
    "fintech",
    "regtech",
    "enterprise_ai",
    "legaltech",
    "edtech",
    "b2b_saas",
    "enterprise_workflow",
    "identity",
    "enterprise_api",
}

TARGET_SENIORITIES = {"pm", "product manager", "senior pm", "senior product manager", "lead pm", "lead product manager"}
EXCLUDED_SENIORITIES = {
    "director",
    "director of product",
    "group pm",
    "group product manager",
    "principal pm",
    "principal product manager",
    "staff pm",
    "staff product manager",
}
TIER1_EVIDENCE = {"posted_role", "recruiter_hiring", "product_leader_match"}
US_STATE_PATTERN = re.compile(
    r"(?:,|[-–—])\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|"
    r"MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)(?:\b|$)",
    re.IGNORECASE,
)
US_LOCATION_MARKERS = {
    "united states",
    "u.s.",
    "usa",
    "remote - us",
    "remote, us",
    "us remote",
    "new york",
    "nyc",
    "san francisco",
    "mountain view",
    "boston",
    "seattle",
    "austin",
    "chicago",
    "los angeles",
    "washington, dc",
    "washington dc",
    "district of columbia",
    "denver",
    "atlanta",
    "miami",
    "philadelphia",
    "pittsburgh",
    "raleigh",
    "durham",
    "charlotte",
    "portland",
    "salt lake city",
}


def score_job(job: Job, company: Company | None, today: date, preferences: dict[str, str] | None = None) -> dict[str, object]:
    score = 0
    reasons: list[str] = []

    eligible = job.status == "open"
    if eligible:
        score += 10
        reasons.append("open")
    else:
        score -= 40
        reasons.append("not_open")

    seniority = job.seniority.strip().lower()
    title = job.role_title.strip().lower()
    excluded = EXCLUDED_SENIORITIES if preferences is None else _title_terms(preferences.get('avoid',''))
    target_titles = TARGET_SENIORITIES if preferences is None else _title_terms(preferences.get('target_titles',''))
    if any(term in seniority or term in title for term in excluded):
        if preferences is not None: eligible = False
        score -= 35
        reasons.append("excluded_seniority")
    elif preferences is None and ("lead" in seniority or title.startswith("lead ")):
        score += 8
        reasons.append("selective_lead")
    elif any(term in seniority or term in title for term in target_titles):
        score += 20
        reasons.append("target_seniority")

    domains = TARGET_DOMAINS if preferences is None else _domain_terms(preferences.get("must_have", ""))
    domain_overlap = job.domain_tags & domains
    if domain_overlap:
        score += 8 + min(len(domain_overlap), 3) * 6
        reasons.append("domain:" + "|".join(sorted(domain_overlap)))
    elif domains:
        score -= 15
        reasons.append("weak_domain")

    location = job.location.lower()
    workplace = job.workplace.lower()
    us_location = is_us_location(job.location)
    if not us_location:
        eligible = False
        score -= 100
        reasons.append("excluded_non_us_or_ambiguous_location")
    elif preferences is not None:
        location_terms = [term.strip().lower() for term in preferences.get('target_locations','').split(';') if term.strip()]
        remote_preferred = any('remote' in term for term in location_terms)
        cities = [term.split(',')[0].replace(' hybrid','').replace(' onsite','').strip() for term in location_terms if 'remote' not in term and term not in {'united states','us','usa'}]
        match = any(city in location or city=='nyc' and 'new york' in location for city in cities)
        nationwide = any(term in {'united states','us','usa'} for term in location_terms)
        if match:
            score += 22; reasons.append('preferred_location')
            if workplace in {'hybrid','onsite','on-site'}:
                score += 5; reasons.append('preferred_local_workplace')
        elif nationwide or remote_preferred and (workplace=='remote' or 'remote' in location):
            score += 8; reasons.append('preferred_us_or_remote')
        elif location_terms:
            score -= 12; reasons.append('outside_location_preferences')
    elif "new york" in location or "nyc" in location:
        score += 22
        reasons.append("nyc")
    elif "remote" in workplace or "remote" in location or "united states" in location:
        score += 8
        reasons.append("remote_us")
    else:
        score -= 12
        reasons.append("location_penalty")

    if preferences is None:
        if workplace in {"onsite", "on-site"} and ("new york" in location or "nyc" in location):
            score += 6; reasons.append("in_person_preference")
        elif workplace == "hybrid" and ("new york" in location or "nyc" in location):
            score += 5; reasons.append("hybrid_nyc")

    age_days: int | None = None
    freshness_bucket = "Excluded - undated"
    if job.posted_date is None:
        eligible = False
        score -= 100
        reasons.append("excluded_undated")
    else:
        age_days = (today - job.posted_date).days
        if age_days < 0:
            eligible = False
            freshness_bucket = "Excluded - future date"
            score -= 100
            reasons.append("excluded_future_date")
        elif age_days <= 7:
            freshness_bucket = "Fresh - 0 to 7 days"
            score += 32
            reasons.append("fresh_0_7")
        elif age_days <= 21:
            freshness_bucket = "Eligible - 8 to 21 days"
            score += 8
            reasons.append("fresh_8_21")
        else:
            eligible = False
            freshness_bucket = "Excluded - older than 21 days"
            score -= 100
            reasons.append("excluded_stale_21_plus")

    if company:
        if company.priority == "high":
            score += 12
            reasons.append("curated_high_priority")
        elif company.priority == "medium":
            score += 6
            reasons.append("curated_medium_priority")
        if company.employee_band in {"50-200", "200-500", "500-2000"}:
            score += 8
            reasons.append("employee_sweet_spot")

    return {
        "role_score": score,
        "role_tier": role_tier(score),
        "role_score_reasons": "; ".join(reasons),
        "role_eligible": eligible,
        "role_age_days": age_days if age_days is not None else "",
        "freshness_bucket": freshness_bucket,
    }


def score_contact(contact: Contact, job_row: dict[str, object] | None) -> dict[str, object]:
    score = int(job_row["role_score"]) if job_row else 0
    reasons = [str(job_row["role_score_reasons"])] if job_row else ["no_role_match"]

    evidence = contact.evidence_type
    if evidence == "posted_role":
        score += 30
        reasons.append("person_posted_role")
    elif evidence == "recruiter_hiring":
        score += 22
        reasons.append("recruiter_hiring")
    elif evidence == "product_leader_match":
        score += 18
        reasons.append("product_leader_match")
    elif evidence == "company_level":
        score += 4
        reasons.append("company_level_only")
    else:
        score -= 10
        reasons.append("unknown_evidence")

    title = contact.title.lower()
    if any(term in title for term in ["recruiter", "talent", "sourcer"]):
        score += 8
        reasons.append("recruiting_title")
    if any(term in title for term in ["product", "chief product", "cpo"]):
        score += 8
        reasons.append("product_title")

    if contact.email_status == "verified":
        score += 10
        reasons.append("verified_email")
    elif contact.email:
        score += 2
        reasons.append("email_unverified")
    else:
        score -= 12
        reasons.append("missing_email")

    tier = "Tier 1 - Evidence review" if evidence in TIER1_EVIDENCE and score >= 85 else "Tier 2 - dedicated domain"
    if evidence == "company_level":
        tier = "Tier 2 - dedicated domain"

    return {
        "contact_score": score,
        "outreach_tier": tier,
        "contact_score_reasons": "; ".join(reasons),
    }


def role_tier(score: int) -> str:
    if score >= 75:
        return "High-fit apply first"
    if score >= 50:
        return "Review"
    return "Low priority"


def is_us_location(value: str) -> bool:
    location = (value or "").strip().lower()
    if not location:
        return False
    if any(marker in location for marker in US_LOCATION_MARKERS):
        return True
    return bool(US_STATE_PATTERN.search(value))


def _title_terms(value):
    terms=[]
    for term in re.split(r'[,;/]',value.lower()):
        term=re.sub(r'\bpm\b','product manager',term).strip().rstrip('+')
        if term: terms.append(term)
    return terms

def _domain_terms(value):
    aliases={'fintech':'fintech','regtech':'regtech','enterpriseai':'enterprise_ai','workflowautomation':'enterprise_workflow','enterpriseworkflow':'enterprise_workflow','legaltech':'legaltech','edtech':'edtech','b2bsaas':'b2b_saas','identity':'identity','enterpriseapi':'enterprise_api'}
    result=set()
    for phrase in value.lower().split(','):
        clean=re.sub(r'[^a-z0-9]','',phrase)
        matches={tag for alias,tag in aliases.items() if alias in clean}
        result.update(matches or {phrase.strip().replace(' ','_')} if clean else set())
    return result
