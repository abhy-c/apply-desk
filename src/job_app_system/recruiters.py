from __future__ import annotations

import csv
from pathlib import Path

from .io import write_csv


RECRUITER_FIELDS = [
    "recruiter_id",
    "name",
    "title",
    "location",
    "company",
    "profile_url",
    "email",
    "source",
    "notes",
]

VALIDATED_RECRUITER_FIELDS = RECRUITER_FIELDS + [
    "validation_score",
    "validation_status",
    "validation_reasons",
    "recommended_next_step",
]


def read_recruiters(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def validate_recruiters(data_dir: Path, out_dir: Path) -> dict[str, int]:
    recruiters = read_recruiters(data_dir / "recruiters_seed.csv")
    rows = [score_recruiter(row) for row in recruiters]
    rows.sort(key=lambda item: int(item["validation_score"]), reverse=True)
    write_csv(out_dir / "recruiters_validated.csv", rows, VALIDATED_RECRUITER_FIELDS)
    return {
        "recruiters": len(rows),
        "high": sum(1 for row in rows if row["validation_status"] == "High-priority search seed"),
        "review": sum(1 for row in rows if row["validation_status"] == "Review manually"),
        "low": sum(1 for row in rows if row["validation_status"] == "Low priority"),
    }


def score_recruiter(row: dict[str, str]) -> dict[str, object]:
    score = 0
    reasons: list[str] = []
    title = row.get("title", "").lower()
    location = row.get("location", "").lower()
    company = row.get("company", "").strip()
    profile_url = row.get("profile_url", "").strip()
    email = row.get("email", "").strip()

    if "us" in location or "united states" in location:
        score += 18
        reasons.append("us_location")
    elif "canada" in location:
        score += 4
        reasons.append("canada_lower_priority")
    else:
        reasons.append("unknown_location")

    if "technical recruiter" in title or "tech recruiter" in title:
        score += 18
        reasons.append("technical_recruiting")
    elif "product" in title:
        score += 18
        reasons.append("product_recruiting")
    elif "talent" in title or "recruiter" in title:
        score += 10
        reasons.append("general_recruiting")
    elif "human resources" in title or title == "hr":
        score += 2
        reasons.append("hr_broad")
    else:
        score -= 8
        reasons.append("weak_recruiting_signal")

    if company:
        score += 20
        reasons.append("has_company")
    else:
        score -= 10
        reasons.append("missing_company")

    if profile_url:
        score += 16
        reasons.append("has_profile_url")
    else:
        score -= 8
        reasons.append("missing_profile_url")

    if email:
        score += 12
        reasons.append("has_email")
    else:
        reasons.append("email_needed")

    if score >= 40:
        status = "High-priority search seed"
        next_step = "Validate current company and hiring focus, then match to target roles before enriching email."
    elif score >= 15:
        status = "Review manually"
        next_step = "Search name plus LinkedIn and product recruiter terms; keep only if tied to relevant roles."
    else:
        status = "Low priority"
        next_step = "Skip unless later evidence ties this person to a target company or product hiring."

    scored = dict(row)
    scored.update(
        {
            "validation_score": score,
            "validation_status": status,
            "validation_reasons": "; ".join(reasons),
            "recommended_next_step": next_step,
        }
    )
    return scored

