import csv
import json
from datetime import date
from pathlib import Path

from job_app_system.discovery_import import fetch_official_job, import_official_job_urls


def _posting_html(
    *,
    title: str = "Legal Engineer",
    company: str = "Example Legal AI",
    posted: str = "2026-08-23",
    country: str = "US",
    region: str = "NY",
    locality: str = "New York",
    description: str = "Build legal AI contract workflows for enterprise customers.",
) -> str:
    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": title,
        "datePosted": posted,
        "hiringOrganization": {"@type": "Organization", "name": company},
        "jobLocationType": "TELECOMMUTE",
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": locality,
                "addressRegion": region,
                "addressCountry": country,
            },
        },
        "description": description,
    }
    return f'<html><script type="application/ld+json">{json.dumps(posting)}</script></html>'


def _expect_value_error(action, message: str) -> None:
    try:
        action()
    except ValueError as exc:
        assert message in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_official_job_import_extracts_structured_metadata_and_provenance() -> None:
    row = fetch_official_job(
        "https://jobs.example.com/legal-engineer",
        today=date(2026, 8, 27),
        page_loader=lambda url: (url, _posting_html()),
    )

    assert row["company"] == "Example Legal AI"
    assert row["role_title"] == "Legal Engineer"
    assert row["posted_date"] == "2026-08-23"
    assert row["location"] == "New York, NY · United States"
    assert row["workplace"] == "remote"
    assert row["source"] == "official_url_import"
    assert row["seniority"] == "Individual contributor"
    assert "legaltech" in row["domain_tags"]


def test_official_job_import_rejects_stale_non_us_undated_and_hiringcafe_urls() -> None:
    _expect_value_error(
        lambda: fetch_official_job(
            "https://jobs.example.com/stale",
            today=date(2026, 8, 27),
            page_loader=lambda url: (url, _posting_html(posted="2026-08-01")),
        ),
        "posted 26 days ago",
    )
    _expect_value_error(
        lambda: fetch_official_job(
            "https://jobs.example.com/london",
            today=date(2026, 8, 27),
            page_loader=lambda url: (url, _posting_html(country="GB", region="London", locality="London")),
        ),
        "not clearly US-only",
    )
    _expect_value_error(
        lambda: fetch_official_job(
            "https://jobs.example.com/undated",
            today=date(2026, 8, 27),
            page_loader=lambda url: (url, _posting_html(posted="")),
        ),
        "no original publication date",
    )
    _expect_value_error(
        lambda: fetch_official_job(
            "https://hiringcafe.com/jobs/legal",
            today=date(2026, 8, 27),
            page_loader=lambda url: (url, _posting_html()),
        ),
        "employer's official posting URL",
    )
    _expect_value_error(
        lambda: fetch_official_job(
            "https://jobs.example.com/no-sponsorship",
            today=date(2026, 8, 27),
            page_loader=lambda url: (
                url,
                _posting_html(description="Candidates must work without sponsorship now or in the future."),
            ),
        ),
        "visa sponsorship is unavailable",
    )


def test_batch_import_writes_once_and_reports_duplicate(tmp_path: Path) -> None:
    url = "https://jobs.example.com/legal-engineer"
    loader = lambda requested_url: (requested_url, _posting_html())

    first = import_official_job_urls(tmp_path, url, today=date(2026, 8, 27), page_loader=loader)
    second = import_official_job_urls(tmp_path, url, today=date(2026, 8, 27), page_loader=loader)

    with (tmp_path / "jobs_seed.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert first["imported"] == 1
    assert second["duplicates"] == 1
    assert len(rows) == 1
    assert rows[0]["source"] == "official_url_import"
