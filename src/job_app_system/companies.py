from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path


SPONSORSHIP_DISCLAIMER = (
    "DOL LCA history shows that an employer pursued H-1B labor certification; it does not prove that "
    "a current opening will sponsor. The exact posting and recruiter confirmation control."
)

COMPANY_ALIASES = {
    "american express": {"american express", "american express global business travel"},
    "bank of america": {"bank of america", "bank of america merrill lynch"},
    "google": {"google", "google cloud"},
    "ibm": {"ibm", "international business machines"},
    "jpmorganchase": {"j p morgan", "jpmorgan", "jpmorgan chase", "jpmorganchase"},
    "meta": {"facebook", "meta", "meta platforms"},
    "thomson reuters": {"thomson reuters", "thomson reuters foundation"},
    "walmart": {"wal mart", "walmart"},
}

STRATEGIC_CONNECTION_TITLE = re.compile(
    r"\b(?:product|recruit|talent|sourc|hiring|chief|vice president|vp|director)\b",
    re.IGNORECASE,
)


def build_target_company_rows(
    data_dir: Path,
    out_dir: Path,
    connections: list[dict[str, str]],
    roles: list[dict[str, str]],
    ats_sources: list[dict[str, str]],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    targets = _read_rows(data_dir / "target_companies.csv")
    evidence_by_company = {
        row.get("company", "").strip().casefold(): row
        for row in _read_rows(out_dir / "company_sponsorship_evidence.csv")
    }
    connection_counts = _connection_counts(connections, targets)
    role_counts = Counter(_company_key(row.get("company", "")) for row in roles)
    monitored = {
        _company_key(row.get("company", ""))
        for row in ats_sources
        if row.get("enabled", "").strip().lower() in {"true", "yes", "1"}
    }

    merged: list[dict[str, object]] = []
    for target in targets:
        company = target.get("company", "").strip()
        key = _company_key(company)
        evidence = evidence_by_company.get(company.casefold(), {})
        lca_cases = _integer(evidence.get("lca_cases", ""))
        relevant_cases = _integer(evidence.get("relevant_lca_cases", ""))
        preferred_location = _integer(evidence.get("preferred_location_lca_cases", ""))
        total_connections, strategic_connections = connection_counts.get(key, (0, 0))
        row: dict[str, object] = dict(target)
        row.update(
            {
                "target_score": _integer(target.get("target_score", "")),
                "network_connections": total_connections,
                "strategic_connections": strategic_connections,
                "current_roles": role_counts.get(key, 0),
                "source_status": "monitored" if key in monitored else target.get("source_status", "not_monitored"),
                "lca_cases": lca_cases,
                "lca_worker_positions": _integer(evidence.get("lca_worker_positions", "")),
                "relevant_lca_cases": relevant_cases,
                "preferred_location_lca_cases": preferred_location,
                "relevant_titles_sample": evidence.get("relevant_titles_sample", ""),
                "sponsorship_evidence": _evidence_label(lca_cases, relevant_cases),
                "sponsorship_risk": _sponsorship_risk(target.get("sponsorship_posture", "")),
                "evidence_period": evidence.get("evidence_period", ""),
                "evidence_source_url": evidence.get("evidence_source_url", ""),
                "evidence_generated_at": evidence.get("generated_at", ""),
            }
        )
        merged.append(row)

    merged.sort(key=lambda row: (-int(row["target_score"]), str(row["company"]).casefold()))
    stats = {
        "total": len(merged),
        "tier1": sum(row.get("tier") == "Tier 1" for row in merged),
        "relevant_sponsor_history": sum(int(row["relevant_lca_cases"]) > 0 for row in merged),
        "monitored": sum(row.get("source_status") == "monitored" for row in merged),
    }
    return merged, stats


def _connection_counts(
    connections: list[dict[str, str]],
    targets: list[dict[str, str]],
) -> dict[str, tuple[int, int]]:
    counts: dict[str, list[int]] = {_company_key(row.get("company", "")): [0, 0] for row in targets}
    for connection in connections:
        connection_key = _company_key(connection.get("company", ""))
        target_key = next((key for key in counts if _company_match(key, connection_key)), None)
        if not target_key:
            continue
        counts[target_key][0] += 1
        if STRATEGIC_CONNECTION_TITLE.search(connection.get("title", "")):
            counts[target_key][1] += 1
    return {key: (values[0], values[1]) for key, values in counts.items()}


def _company_match(target_key: str, connection_key: str) -> bool:
    if target_key == connection_key:
        return True
    aliases = COMPANY_ALIASES.get(target_key, {target_key})
    return connection_key in aliases


def _company_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _evidence_label(lca_cases: int, relevant_cases: int) -> str:
    if relevant_cases:
        return "Relevant recent LCA history"
    if lca_cases:
        return "Company LCA history; no relevant-title case found"
    return "No matching recent DOL LCA found"


def _sponsorship_risk(posture: str) -> str:
    lowered = posture.casefold()
    if lowered.startswith("established"):
        return "verify_role"
    if lowered.startswith("selective"):
        return "selective"
    return "unverified"


def _integer(value: object) -> int:
    try:
        return int(float(str(value or 0)))
    except ValueError:
        return 0


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]
