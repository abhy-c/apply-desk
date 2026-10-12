from pathlib import Path

from job_app_system.web import (
    _actions,
    _ats_sources,
    _delete_ats_source,
    _discovery_sources,
    _focus_roles,
    _upsert_action,
    _upsert_ats_source,
)


def test_discovery_sources_preserve_manual_only_policy(tmp_path: Path) -> None:
    (tmp_path / "discovery_sources.json").write_text(
        '[{"id":"hiringcafe","mode":"manual_discovery","searches":[]}]',
        encoding="utf-8",
    )

    assert _discovery_sources(tmp_path) == [
        {"id": "hiringcafe", "mode": "manual_discovery", "searches": []}
    ]


def test_checked_in_hiringcafe_source_cannot_be_mistaken_for_an_automated_feed() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    sources = _discovery_sources(project_dir / "data")
    hiringcafe = next(source for source in sources if source.get("id") == "hiringcafe")

    assert hiringcafe["mode"] == "manual_discovery"
    assert "Do not scrape" in str(hiringcafe["policy"])
    assert all(str(search["url"]).startswith("https://hiringcafe.com/") for search in hiringcafe["searches"])


def test_discovery_directory_does_not_claim_working_board_collectors():
    sources = _discovery_sources(Path(__file__).resolve().parents[1] / "data")
    by_id = {source["id"]: source for source in sources}
    assert {"indeed", "builtin", "ziprecruiter", "wellfound", "hiringcafe", "linkedin_jobs"} <= by_id.keys()
    assert len(by_id) == len(sources)
    assert all(source["mode"] == "manual_discovery" for source in sources)
    assert all(source["recommended_reader"] and source["coverage_note"] for source in sources)


def test_ats_source_upsert_replaces_by_original_key(tmp_path: Path) -> None:
    first = _upsert_ats_source(
        tmp_path,
        {
            "enabled": "on",
            "company": "Example Co",
            "ats": "Ashby",
            "slug": "example",
            "domain_tags": "fintech,b2b_saas",
            "location_hint": "New York, NY",
        },
    )

    updated = _upsert_ats_source(
        tmp_path,
        {
            "original_key": first["key"],
            "enabled": "false",
            "company": "Example Co",
            "ats": "Lever",
            "slug": "example-jobs",
            "domain_tags": "fintech",
            "location_hint": "Remote",
        },
    )
    sources = _ats_sources(tmp_path)

    assert updated["key"] == "lever:example-jobs"
    assert len(sources) == 1
    assert sources[0]["enabled"] == "false"
    assert sources[0]["ats"] == "lever"


def test_ats_source_delete_removes_matching_key(tmp_path: Path) -> None:
    source = _upsert_ats_source(
        tmp_path,
        {
            "enabled": "true",
            "company": "Example Co",
            "ats": "greenhouse",
            "slug": "example",
            "domain_tags": "",
            "location_hint": "",
        },
    )

    assert _delete_ats_source(tmp_path, source["key"]) is True
    assert _ats_sources(tmp_path) == []


def test_actions_are_saved_sorted_and_can_be_completed(tmp_path: Path) -> None:
    later = _upsert_action(
        tmp_path,
        {
            "title": "Tailor the resume",
            "priority": "normal",
            "due_date": "2026-08-05",
        },
    )
    sooner = _upsert_action(
        tmp_path,
        {
            "title": "Confirm next conversation step",
            "priority": "high",
            "due_date": "2026-08-04",
        },
    )

    assert [action["action_id"] for action in _actions(tmp_path)] == [sooner["action_id"], later["action_id"]]

    completed = _upsert_action(
        tmp_path,
        {
            **sooner,
            "status": "done",
        },
    )

    assert completed["status"] == "done"
    assert _actions(tmp_path)[-1]["action_id"] == sooner["action_id"]


def test_focus_roles_avoids_filling_the_daily_list_with_one_company() -> None:
    roles = [
        {"company": "Plaid", "role_title": "One", "application_status": ""},
        {"company": "Plaid", "role_title": "Two", "application_status": "saved"},
        {"company": "Plaid", "role_title": "Three", "application_status": ""},
        {"company": "Ramp", "role_title": "Four", "application_status": ""},
    ]

    selected = _focus_roles(roles, limit=5, per_company_limit=2)

    assert [role["role_title"] for role in selected] == ["One", "Two", "Four"]
