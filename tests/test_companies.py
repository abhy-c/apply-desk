import csv
from pathlib import Path

from job_app_system.companies import build_target_company_rows


def test_target_company_rows_merge_sponsorship_network_and_source_evidence(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    data_dir.mkdir()
    out_dir.mkdir()
    _write_rows(
        data_dir / "target_companies.csv",
        [
            {
                "company": "JPMorganChase",
                "tier": "Tier 1",
                "target_score": "91",
                "sponsorship_posture": "Established sponsor; role-specific",
                "source_status": "not_monitored",
            },
            {
                "company": "IBM",
                "tier": "Tier 2",
                "target_score": "72",
                "sponsorship_posture": "Selective; highly role-specific",
                "source_status": "not_monitored",
            },
        ],
    )
    _write_rows(
        out_dir / "company_sponsorship_evidence.csv",
        [
            {"company": "JPMorganChase", "lca_cases": "100", "relevant_lca_cases": "12", "relevant_nyc_lca_cases": "5"},
            {"company": "IBM", "lca_cases": "80", "relevant_lca_cases": "2", "relevant_nyc_lca_cases": "0"},
        ],
    )
    connections = [
        {"company": "J.P. Morgan", "title": "Senior Product Manager"},
        {"company": "JPMorganChase", "title": "Associate"},
        {"company": "IBM", "title": "Talent Partner"},
    ]
    roles = [{"company": "IBM", "role_title": "Product Manager"}]
    sources = [{"company": "IBM", "enabled": "true"}]

    rows, stats = build_target_company_rows(data_dir, out_dir, connections, roles, sources)
    by_company = {row["company"]: row for row in rows}

    assert by_company["JPMorganChase"]["network_connections"] == 2
    assert by_company["JPMorganChase"]["strategic_connections"] == 1
    assert by_company["IBM"]["sponsorship_risk"] == "selective"
    assert by_company["IBM"]["current_roles"] == 1
    assert by_company["IBM"]["source_status"] == "monitored"
    assert stats == {"total": 2, "tier1": 1, "relevant_sponsor_history": 2, "monitored": 1}




def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
