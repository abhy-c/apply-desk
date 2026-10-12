from datetime import date

from job_app_system.adapters import normalize_ashby_jobs, normalize_greenhouse_jobs, normalize_lever_jobs, infer_workplace
from job_app_system.discovery_import import normalize_job_posting


SOURCE = {"slug": "example", "company": "Example", "domain_tags": "b2b_saas"}
LONG_DESCRIPTION = "Build useful products. " * 150 + "Required: enterprise procurement and SQL. Sponsorship unavailable."


def test_ats_descriptions_retain_late_requirements_and_all_lever_sections():
    greenhouse = normalize_greenhouse_jobs(SOURCE, [{"id": 1, "title": "Product Manager", "content": LONG_DESCRIPTION}])[0]
    ashby = normalize_ashby_jobs(SOURCE, [{"id": 2, "title": "Product Manager", "descriptionPlain": LONG_DESCRIPTION}])[0]
    lever = normalize_lever_jobs(SOURCE, [{"id": 3, "text": "Product Manager", "descriptionPlain": "Introduction.",
        "lists": [{"text": "Requirements", "content": f"<ul><li>{LONG_DESCRIPTION}</li></ul>"}],
        "additionalPlain": "Closing: no sponsorship for this position."}])[0]
    assert greenhouse["description"] == LONG_DESCRIPTION
    assert ashby["description"] == LONG_DESCRIPTION
    assert "Required: enterprise procurement and SQL." in lever["description"]
    assert "Requirements" in lever["description"]
    assert lever["description"].endswith("Closing: no sponsorship for this position.")


def test_workplace_uses_explicit_metadata_and_does_not_infer_remote_from_us():
    jobs = [{"id": 1, "title": "Product Manager", "location": "United States", "isRemote": True},
            {"id": 2, "title": "Product Manager", "location": "United States", "workplaceType": "OnSite"},
            {"id": 3, "title": "Product Manager", "location": "United States", "workplaceType": "Hybrid", "isRemote": True},
            {"id": 4, "title": "Product Manager", "location": "United States", "isRemote": False}]
    assert [r["workplace"] for r in normalize_ashby_jobs(SOURCE, jobs)] == ["remote", "onsite", "hybrid", ""]
    assert infer_workplace("United States") == ""
    assert infer_workplace("New York, NY") == ""


def test_official_import_retains_requirements_beyond_the_former_preview_limit():
    row = normalize_job_posting({"title": "Product Manager", "hiringOrganization": {"name": "Example"},
        "datePosted": "2026-10-07", "applicantLocationRequirements": {"name": "United States"},
        "description": "Build products. " * 150 + "Required: enterprise SQL and Jira."},
        "https://example.com/jobs/1", today=date(2026, 10, 7))
    assert row["description"].endswith("Required: enterprise SQL and Jira.")
    assert len(row["description"]) > 1200
