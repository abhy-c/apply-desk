import csv
import zipfile
from datetime import date
from pathlib import Path

from job_app_system.connections import (
    build_connection_rankings,
    import_linkedin_export,
    save_connection_review,
)


def test_import_and_rank_linkedin_export_with_direct_hiring_evidence(tmp_path: Path) -> None:
    archive = tmp_path / "linkedin.zip"
    _write_export(archive)
    _write_company_and_job_data(tmp_path)

    counts = import_linkedin_export(archive, tmp_path, today=date(2026, 7, 14))
    ranking_counts = build_connection_rankings(tmp_path / "data", tmp_path / "out", today=date(2026, 7, 14))
    rows = _rows(tmp_path / "out" / "connections_ranked.csv")

    assert counts == {"connections": 2, "with_messages": 2, "recent_hiring_signals": 1}
    assert ranking_counts["tier1"] == 1
    assert rows[0]["name"] == "Taylor Recruiter"
    assert rows[0]["outreach_tier"] == "Tier 1 - Recent hiring"
    assert rows[0]["hiring_evidence_type"] == "direct_hiring_message"
    assert "CONTENT" not in rows[0]


def test_manual_hiring_evidence_expires_after_90_days(tmp_path: Path) -> None:
    archive = tmp_path / "linkedin.zip"
    _write_export(archive)
    _write_company_and_job_data(tmp_path)
    import_linkedin_export(archive, tmp_path, today=date(2026, 7, 14))
    source_rows = _rows(tmp_path / "data" / "linkedin_connections.csv")
    connection_id = next(row["connection_id"] for row in source_rows if row["name"] == "Jordan Product")

    save_connection_review(
        tmp_path / "data",
        {
            "connection_id": connection_id,
            "status": "approved_to_contact",
            "hiring_evidence_date": "2026-01-01",
            "hiring_evidence_type": "hiring_post",
            "hiring_evidence_url": "https://example.com/evidence",
        },
    )
    build_connection_rankings(tmp_path / "data", tmp_path / "out", today=date(2026, 7, 14))
    row = next(row for row in _rows(tmp_path / "out" / "connections_ranked.csv") if row["connection_id"] == connection_id)

    assert row["recent_hiring"] == "false"
    assert row["outreach_tier"] != "Tier 1 - Recent hiring"


def _write_export(path: Path) -> None:
    connections = """Notes:
\"Export note\"

First Name,Last Name,URL,Email Address,Company,Position,Connected On
Taylor,Recruiter,https://www.linkedin.com/in/taylor,,Example Co,Talent Acquisition Partner,14 May 2026
Jordan,Product,https://www.linkedin.com/in/jordan,,Other Co,Director of Product Management,10 May 2025
"""
    profile = "First Name,Last Name,Headline\nAlex,Example,Product Manager\n"
    messages = """\"CONVERSATION ID\",\"CONVERSATION TITLE\",\"FROM\",\"SENDER PROFILE URL\",\"TO\",\"RECIPIENT PROFILE URLS\",\"DATE\",\"SUBJECT\",\"CONTENT\",\"FOLDER\",\"ATTACHMENTS\",\"IS MESSAGE DRAFT\"
\"1\",\"\",\"Taylor Recruiter\",\"https://www.linkedin.com/in/taylor\",\"Alex Example\",\"https://www.linkedin.com/in/alex-example\",\"2026-05-14 10:00:00 UTC\",\"\",\"We're hiring for a Product Manager on my team.\",\"INBOX\",\"\",\"No\"
\"1\",\"\",\"Alex Example\",\"https://www.linkedin.com/in/alex-example\",\"Taylor Recruiter\",\"https://www.linkedin.com/in/taylor\",\"2026-05-14 10:05:00 UTC\",\"\",\"Thanks for sharing.\",\"SENT\",\"\",\"No\"
\"2\",\"\",\"Jordan Product\",\"https://www.linkedin.com/in/jordan\",\"Alex Example\",\"https://www.linkedin.com/in/alex-example\",\"2025-11-01 10:00:00 UTC\",\"\",\"Good to connect.\",\"INBOX\",\"\",\"No\"
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Connections.csv", connections)
        archive.writestr("Profile.csv", profile)
        archive.writestr("messages.csv", messages)


def _write_company_and_job_data(project_dir: Path) -> None:
    data_dir = project_dir / "data"
    data_dir.mkdir()
    (data_dir / "companies.csv").write_text(
        "company,domain_tags,location_preference,employee_band,priority,notes\n"
        "Example Co,b2b_saas,NYC,200-500,high,Test\n",
        encoding="utf-8",
    )
    (data_dir / "jobs_seed.csv").write_text(
        "role_id,company,role_title,role_url,source,posted_date,location,workplace,domain_tags,seniority,status,description\n"
        "role_1,Example Co,Product Manager,https://example.com/role,test,2026-07-10,New York,hybrid,b2b_saas,PM,open,Test role\n",
        encoding="utf-8",
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]
