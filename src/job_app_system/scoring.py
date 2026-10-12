from __future__ import annotations

import re
from datetime import date

from .models import Company, Contact, Job

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


def score_job(job: Job, company: Company | None, today: date, preferences=None) -> dict[str, object]:
    from .workspace import assess
    profile=preferences or {}
    rules=[]
    for field,label,key,weight in [('domain_tags','Domain','must_have',3),('location','Location','target_locations',2)]:
        if profile.get(key):rules.append({'id':key,'field':field,'label':label,'operator':'contains','value':profile[key],'mode':'preferred','weight':weight})
    if profile.get('avoid'):rules.append({'id':'avoid','field':'role_title','label':'Excluded title','operator':'excludes','value':profile['avoid'],'mode':'required','weight':1})
    row={'role_id':job.role_id,'role_title':job.role_title,'status':job.status,'domain_tags':','.join(sorted(job.domain_tags)),
         'location':job.location,'workplace':job.workplace,'description':job.description,'posted_date':job.posted_date.isoformat() if job.posted_date else ''}
    config={'setup':{'titles':profile.get('target_titles',''),'excluded_titles':profile.get('avoid','')},'rules':rules,'assessments':{}}
    return assess(None,row,config,today)


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
