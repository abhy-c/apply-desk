import json
from pathlib import Path
from datetime import date

import pytest

from job_app_system.manual_discovery import start_run, import_source, finish_run, discovery_state


def official(url="https://jobs.example.com/product-manager", posted=None, description="Enterprise AI roadmap ownership."):
    return {"url": url, "format": "jobposting", "data": {"@type": "JobPosting", "title": "Product Manager", "datePosted": posted or date.today().isoformat(),
        "hiringOrganization": {"name": "Example"}, "jobLocation": {"address": {"addressLocality": "New York", "addressRegion": "NY", "addressCountry": "US"}}, "description": description}}


def submit(root, run, source, document, complete=False):
    return import_source(root, {"run_id": run["run_id"], "source_id": source, "documents": [document], "coverage": "One test result; pagination not exhausted", "complete": complete})


def test_board_timestamp_is_not_verified_original_publication(tmp_path):
    run = start_run(tmp_path, ["indeed"])
    doc = {"url": "https://www.indeed.com/viewjob?jk=0000000000000001", "format": "indeed", "data": {"title": "Product Manager", "employer": {"name": "Example"}, "description_text": "Requirements. " * 200,
        "location": {"formatted": "New York, NY"}, "posted_at": date.today().isoformat(), "listed_at": date.today().isoformat()}}
    counts = submit(tmp_path, run, "indeed", doc)
    assert counts["ready"] == 0
    assert counts["needs_review"] == 1
    assert "Original employer publication date not verified" in discovery_state(tmp_path)["needs_review"][0]["review_reasons"]
    assert len((tmp_path / "data/jobs_discovered.csv").read_text().splitlines()) == 1
    finish_run(tmp_path, run["run_id"])


def test_official_details_deduplicate_across_boards_and_preserve_first_seen(tmp_path):
    run = start_run(tmp_path, ["indeed", "builtin"])
    evidence = official(description="Qualifications. " * 200 + "Required: SQL and product analytics.")
    doc = {"url": "https://www.indeed.com/viewjob?jk=0000000000000001", "format": "indeed", "data": {"title": "Product Manager", "apply_url": evidence["url"]}, "official": evidence}
    assert submit(tmp_path, run, "indeed", doc)["ready"] == 1
    first = json.loads((tmp_path / "data/discovery_records.json").read_text())[0]
    other = {"url": "https://builtin.com/job/pm/1", "format": "builtin", "data": {"title": "Product Manager"}, "official": evidence}
    counts = submit(tmp_path, run, "builtin", other)
    assert counts["duplicates"] == 1
    rows = json.loads((tmp_path / "data/discovery_records.json").read_text())
    assert len(rows) == 1
    assert rows[0]["first_seen_at"] == first["first_seen_at"]
    assert rows[0]["source_ids"] == ["indeed", "builtin"]
    assert rows[0]["description"].endswith("Required: SQL and product analytics.")
    assert len(rows[0]["evidence"]) == 4


def test_closed_stale_and_missing_metadata_remain_visible_but_unranked(tmp_path):
    run = start_run(tmp_path, ["yc", "wellfound", "a16z"])
    stale = official(posted="2020-01-01")
    stale["data"]["validThrough"] = "2020-02-01T12:00:00Z"
    assert submit(tmp_path, run, "yc", stale)["ready"] == 0
    assert "Posting is closed or expired" in discovery_state(tmp_path)["needs_review"][0]["review_reasons"]
    missing = {"url": "https://wellfound.com/jobs/1-product-manager", "format": "page", "title": "Product Manager", "data": {"markdown": "Full visible posting text."}}
    assert submit(tmp_path, run, "wellfound", missing)["needs_review"] == 1
    failed = finish_run(tmp_path, run["run_id"])
    assert failed["status"] == "partial"
    assert failed["sources"]["a16z"]["status"] == "failed"
    assert len(discovery_state(tmp_path)["needs_review"]) == 2


def test_failed_refresh_keeps_previous_results_and_disallows_overlap(tmp_path):
    run = start_run(tmp_path, ["indeed"])
    with pytest.raises(ValueError, match="already in progress"):
        start_run(tmp_path)
    submit(tmp_path, run, "indeed", official())
    finish_run(tmp_path, run["run_id"])
    next_run = start_run(tmp_path, ["indeed"])
    finish_run(tmp_path, next_run["run_id"])
    assert discovery_state(tmp_path)["stats"]["ready"] == 1
    assert discovery_state(tmp_path)["api_key_required"] is False


def test_source_evidence_validation_rejects_aggregator_as_official(tmp_path):
    run = start_run(tmp_path, ["indeed"])
    doc = {"url": "https://www.indeed.com/viewjob?jk=0000000000000001", "format": "indeed", "data": {"title": "Product Manager"}, "official": official(url="https://builtin.com/job/pm/1")}
    with pytest.raises(ValueError, match="aggregator"):
        submit(tmp_path, run, "indeed", doc)
    assert discovery_state(tmp_path)["stats"]["total"] == 0


def test_application_url_and_later_alias_bridge_merge_existing_records(tmp_path):
    run = start_run(tmp_path, ["indeed", "builtin", "yc"])
    ats = official(url="https://jobs.ashbyhq.com/example/123/application?utm_source=board")
    submit(tmp_path, run, "indeed", ats)
    board = {"url": "https://builtin.com/job/pm/1", "format": "builtin", "data": {"title": "Product Manager"}}
    submit(tmp_path, run, "builtin", board)
    board["official"] = official(url="https://jobs.ashbyhq.com/example/123")
    submit(tmp_path, run, "yc", board)
    rows = json.loads((tmp_path / "data/discovery_records.json").read_text())
    assert len(rows) == 1
    assert rows[0]["source_ids"] == ["indeed", "builtin", "yc"]
    assert rows[0]["review_status"] == "ready"


def test_weaker_board_observation_rechecks_age_of_retained_official_evidence(tmp_path):
    run = start_run(tmp_path, ["indeed", "builtin"])
    ats = official(posted="2020-01-01")
    submit(tmp_path, run, "indeed", ats)
    store = tmp_path / "data/discovery_records.json"
    rows = json.loads(store.read_text())
    rows[0].update(review_status="ready", review_reasons=[])
    store.write_text(json.dumps(rows))
    board = {"url": "https://www.indeed.com/viewjob?jk=0000000000000001", "format": "indeed", "data": {"apply_url": ats["url"]}}
    assert submit(tmp_path, run, "builtin", board)["ready"] == 0
    assert "Older than 14 days" in discovery_state(tmp_path)["needs_review"][0]["review_reasons"]
