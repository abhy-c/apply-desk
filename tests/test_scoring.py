import csv
from datetime import date
from pathlib import Path

from job_app_system.models import Company, Contact, Job
from job_app_system.pipeline import build
from job_app_system.scoring import score_contact, score_job


def test_nyc_fresh_fintech_role_scores_high() -> None:
    company = Company("Alloy", {"fintech", "regtech"}, "NYC", "200-500", "high", "")
    job = Job(
        role_id="1",
        company="Alloy",
        role_title="Senior Product Manager",
        role_url="https://example.com",
        source="test",
        posted_date=date(2026, 5, 28),
        location="New York, NY",
        workplace="hybrid",
        domain_tags={"fintech", "regtech"},
        seniority="Senior PM",
        status="open",
        description="",
    )

    result = score_job(job, company, date(2026, 6, 9))

    assert result["role_tier"] == "High-fit apply first"
    assert int(result["role_score"]) >= 75


def test_company_level_contact_cannot_be_tier1() -> None:
    contact = Contact(
        contact_id="1",
        company="Betterment",
        name="Person",
        title="Recruiter",
        email="person@example.com",
        email_status="verified",
        profile_url="",
        evidence_type="company_level",
        evidence_url="",
        role_id="role",
        source="test",
        notes="",
    )
    role_row = {"role_score": 90, "role_score_reasons": "high"}

    result = score_contact(contact, role_row)

    assert result["outreach_tier"] == "Tier 2 - dedicated domain"


def test_jobs_older_than_21_days_are_ineligible() -> None:
    job = Job(
        role_id="stale",
        company="Example",
        role_title="Product Manager",
        role_url="https://example.com",
        source="test",
        posted_date=date(2026, 6, 1),
        location="New York, NY",
        workplace="hybrid",
        domain_tags={"fintech"},
        seniority="PM",
        status="open",
        description="",
    )

    result = score_job(job, None, date(2026, 7, 14))

    assert result["role_eligible"] is False
    assert result["freshness_bucket"] == "Excluded - older than 21 days"


def test_job_posted_in_last_week_outranks_second_week() -> None:
    def job(posted_date: date) -> Job:
        return Job(
            role_id=posted_date.isoformat(),
            company="Example",
            role_title="Product Manager",
            role_url="https://example.com",
            source="test",
            posted_date=posted_date,
            location="New York, NY",
            workplace="hybrid",
            domain_tags={"fintech"},
            seniority="PM",
            status="open",
            description="",
        )

    today = date(2026, 7, 14)
    fresh = score_job(job(date(2026, 7, 10)), None, today)
    older = score_job(job(date(2026, 7, 4)), None, today)

    assert fresh["role_eligible"] is True
    assert older["role_eligible"] is True
    assert int(fresh["role_score"]) > int(older["role_score"])


def test_india_role_is_ineligible() -> None:
    job = Job(
        role_id="india",
        company="Example",
        role_title="Product Manager",
        role_url="https://example.com/india",
        source="test",
        posted_date=date(2026, 7, 18),
        location="Bangalore, India",
        workplace="hybrid",
        domain_tags={"enterprise_ai"},
        seniority="PM",
        status="open",
        description="",
    )

    result = score_job(job, None, date(2026, 7, 20))

    assert result["role_eligible"] is False
    assert "excluded_non_us_or_ambiguous_location" in result["role_score_reasons"]


def test_ambiguous_remote_role_is_ineligible() -> None:
    job = Job(
        role_id="remote",
        company="Example",
        role_title="Product Manager",
        role_url="https://example.com/remote",
        source="test",
        posted_date=date(2026, 7, 18),
        location="Remote",
        workplace="remote",
        domain_tags={"enterprise_ai"},
        seniority="PM",
        status="open",
        description="",
    )

    result = score_job(job, None, date(2026, 7, 20))

    assert result["role_eligible"] is False


def test_pipeline_omits_stale_and_undated_jobs(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    data_dir.mkdir()
    (data_dir / "companies.csv").write_text(
        "company,domain_tags,location_preference,employee_band,priority,notes\n",
        encoding="utf-8",
    )
    (data_dir / "contacts_seed.csv").write_text(
        "contact_id,company,name,title,email,email_status,profile_url,evidence_type,evidence_url,role_id,source,notes\n",
        encoding="utf-8",
    )
    (data_dir / "jobs_seed.csv").write_text(
        "role_id,company,role_title,role_url,source,posted_date,location,workplace,domain_tags,seniority,status,description\n"
        "fresh,Example,Product Manager,https://example.com/fresh,test,2026-07-10,New York,hybrid,fintech,PM,open,Fresh\n"
        "india,Example,Product Manager,https://example.com/india,test,2026-07-10,Bangalore India,hybrid,fintech,PM,open,India\n"
        "stale,Example,Product Manager,https://example.com/stale,test,2026-06-01,New York,hybrid,fintech,PM,open,Stale\n"
        "undated,Example,Product Manager,https://example.com/undated,test,,New York,hybrid,fintech,PM,open,Undated\n",
        encoding="utf-8",
    )

    counts = build(data_dir, out_dir, today=date(2026, 7, 14))
    with (out_dir / "roles_scored.csv").open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    assert counts["roles"] == 1
    assert [row["role_id"] for row in rows] == ["fresh"]
