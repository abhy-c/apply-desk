from __future__ import annotations

from .storage import transactional, atomic_csv, atomic_json, atomic_text

import hashlib
from .validation import text, public_url

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROFILE_PATH = "app_profile.json"
APPLICATION_REVIEW_FIELDS = ["role_id", "status", "decision", "notes", "last_updated"]
PACKET_DRAFT_DIR = "application_packets"

DEFAULT_PROFILE = {
    "full_name": "Your Name",
    "target_titles": "",
    "target_locations": "",
    "work_authorization": "",
    "salary_range": "",
    "must_have": "",
    "avoid": "",
    "standard_answers": (
        "Use only factual experience from the resume/fact bank. Keep application answers concise, "
        "specific, and human-reviewable before submission."
    ),
}


def load_profile(data_dir: Path) -> dict[str, str]:
    path = data_dir / PROFILE_PATH
    if not path.exists():
        return DEFAULT_PROFILE.copy()
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload,dict): raise ValueError('Profile data must be a JSON object')
    profile = DEFAULT_PROFILE.copy()
    profile.update({str(key): str(value) for key, value in payload.items()})
    return profile


@transactional('data_dir', 'data')
def save_profile(data_dir: Path, payload: dict[str, object]) -> dict[str, str]:
    profile = load_profile(data_dir)
    for key in DEFAULT_PROFILE:
        if key in payload: profile[key]=text(payload[key],key,10000)
    atomic_json(data_dir / PROFILE_PATH, profile)
    return profile


def read_application_reviews(data_dir: Path) -> dict[str, dict[str, str]]:
    path = data_dir / "application_reviews.csv"
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {row["role_id"]: dict(row) for row in csv.DictReader(handle) if row.get("role_id")}


@transactional('data_dir', 'data')
def upsert_application_review(data_dir: Path, role_id: str, status: str, decision: str = '', notes: str = '') -> dict[str, str]:
    role_id=text(role_id,'role_id',1000,True)
    if status not in {'saved','ready_to_apply','applied','skip'}: raise ValueError('Invalid application status')
    row={'role_id':role_id,'status':status,'decision':text(decision,'decision'),'notes':text(notes,'notes'), 'last_updated':datetime.now(timezone.utc).isoformat()}
    rows=read_application_reviews(data_dir); rows[role_id]=row
    atomic_csv(data_dir / 'application_reviews.csv', sorted(rows.values(),key=lambda v:v['role_id']),APPLICATION_REVIEW_FIELDS)
    return row


def build_application_packet(profile: dict[str, str], role: dict[str, str]) -> dict[str, object]:
    company = role.get("company", "the company")
    title = role.get("role_title", "the role")
    tags = _split_terms(role.get("domain_tags", ""))
    reasons = _split_terms(role.get("role_score_reasons", "").replace(";", ","))
    score = role.get("role_score", "")

    focus_points = _focus_points(tags, reasons)
    cover_letter = _cover_letter(profile, role, focus_points)
    screening_answers = _screening_answers(profile, role, focus_points)

    return {
        "role_id": role.get("role_id", ""),
        "company": company,
        "role_title": title,
        "role_url": role.get("role_url", ""),
        "fit_score": score,
        "resume_focus": focus_points,
        "cover_letter": cover_letter,
        "screening_answers": screening_answers,
        "review_gate": [
            "Confirm every claim is supported by the resume or fact bank.",
            "Confirm work authorization, salary, and location answers are accurate.",
            "Open the application URL manually before submitting.",
        ],
    }


def build_packet_with_saved_draft(data_dir: Path, profile: dict[str, str], role: dict[str, str]) -> dict[str, object]:
    packet = build_application_packet(profile, role)
    saved = load_application_packet(data_dir, str(packet.get("role_id", "")))
    if saved:
        for key in ("cover_letter", "resume_focus", "screening_answers", "interview_brief", "saved_at", "exported_at"):
            if saved.get(key):
                packet[key] = saved[key]
    return packet


def load_application_packet(data_dir: Path, role_id: str) -> dict[str, object] | None:
    path = _packet_path(data_dir,role_id)
    if not path.exists():
        # Read legacy files only when the stored full identity agrees. Never migrate a collision silently.
        path=data_dir / PACKET_DRAFT_DIR / (slugify(role_id)+'.json')
    if not path.exists(): return None
    payload=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload,dict) or payload.get('role_id')!=role_id: return None
    return _packet_payload(payload)


@transactional('data_dir', 'data')
def save_application_packet(data_dir: Path, payload: dict[str, object]) -> dict[str, object]:
    if not isinstance(payload,dict): raise ValueError('Packet must be an object')
    role_id=text(payload.get('role_id',''),'role_id',1000,True)
    for key in ('cover_letter','company','role_title'):
        if key in payload: text(payload[key],key,200000)
    if 'role_url' in payload: public_url(payload['role_url'])
    packet=_packet_payload(payload)
    packet['saved_at']=datetime.now(timezone.utc).isoformat()
    atomic_json(_packet_path(data_dir,role_id),packet)
    return packet


@transactional('out_dir', 'out')
def export_application_packet(out_dir: Path, payload: dict[str, object]) -> dict[str, str]:
    packet=_packet_payload(payload)
    role_id=text(packet['role_id'],'role_id',1000,True)
    path=out_dir / PACKET_DRAFT_DIR / (_packet_stem(role_id)+'.md')
    exported_at=datetime.now(timezone.utc).isoformat()
    atomic_text(path,_packet_markdown(packet,exported_at))
    return {'path':str(path),'exported_at':exported_at}


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value[:72] or "role"


def _packet_path(data_dir: Path, role_id: str) -> Path:
    return data_dir / PACKET_DRAFT_DIR / (_packet_stem(role_id)+'.json')


def _packet_payload(payload: dict[str, object]) -> dict[str, object]:
    screening_answers = payload.get("screening_answers", [])
    if not isinstance(screening_answers, list):
        screening_answers = []

    resume_focus = payload.get("resume_focus", [])
    if not isinstance(resume_focus, list):
        resume_focus = []

    review_gate = payload.get("review_gate", [])
    if not isinstance(review_gate, list):
        review_gate = []

    interview_brief = payload.get("interview_brief", {})
    if not isinstance(interview_brief, dict):
        interview_brief = {}

    return {
        "role_id": str(payload.get("role_id", "")).strip(),
        "company": str(payload.get("company", "")).strip(),
        "role_title": str(payload.get("role_title", "")).strip(),
        "role_url": str(payload.get("role_url", "")).strip(),
        "fit_score": str(payload.get("fit_score", "")).strip(),
        "resume_focus": [str(item).strip() for item in resume_focus if str(item).strip()],
        "cover_letter": str(payload.get("cover_letter", "")).strip(),
        "screening_answers": [_answer_payload(item) for item in screening_answers if isinstance(item, dict)],
        "interview_brief": _interview_brief_payload(interview_brief),
        "review_gate": [str(item).strip() for item in review_gate if str(item).strip()],
        "saved_at": str(payload.get("saved_at", "")).strip(),
        "exported_at": str(payload.get("exported_at", "")).strip(),
    }


def _answer_payload(item: dict[str, Any]) -> dict[str, str]:
    return {
        "question": str(item.get("question", "")).strip() or "Screening answer",
        "answer": str(item.get("answer", "")).strip(),
    }


def _interview_brief_payload(value: dict[str, object]) -> dict[str, object]:
    """Keep interview material structured, local, and safe to export as a draft."""

    fit_map = value.get("fit_map", [])
    if not isinstance(fit_map, list):
        fit_map = []
    stories = value.get("star_stories", [])
    if not isinstance(stories, list):
        stories = []

    return {
        "thread_context": _clean_strings(value.get("thread_context", [])),
        "positioning": str(value.get("positioning", "")).strip(),
        "fit_map": [
            {
                "jd_need": str(item.get("jd_need", "")).strip(),
                "evidence": str(item.get("evidence", "")).strip(),
                "evidence_ids": _clean_strings(item.get("evidence_ids", [])),
                "readout": str(item.get("readout", "")).strip(),
            }
            for item in fit_map
            if isinstance(item, dict)
        ],
        "pitch_60_seconds": str(value.get("pitch_60_seconds", "")).strip(),
        "star_stories": [
            {
                "title": str(item.get("title", "")).strip(),
                "situation": str(item.get("situation", "")).strip(),
                "task": str(item.get("task", "")).strip(),
                "action": str(item.get("action", "")).strip(),
                "result": str(item.get("result", "")).strip(),
                "evidence_ids": _clean_strings(item.get("evidence_ids", [])),
            }
            for item in stories
            if isinstance(item, dict)
        ],
        "questions_for_interviewer": _clean_strings(value.get("questions_for_interviewer", [])),
        "follow_up_note": str(value.get("follow_up_note", "")).strip(),
        "accuracy_note": str(value.get("accuracy_note", "")).strip(),
    }


def _clean_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _packet_markdown(packet: dict[str, object], exported_at: str) -> str:
    resume_focus = "\n".join(f"- {point}" for point in packet.get("resume_focus", []))
    answers = "\n\n".join(
        f"### {item.get('question', 'Screening answer')}\n\n{item.get('answer', '')}"
        for item in packet.get("screening_answers", [])
        if isinstance(item, dict)
    )
    review_gate = "\n".join(f"- {item}" for item in packet.get("review_gate", []))
    interview_brief = packet.get("interview_brief", {})
    interview_markdown = _interview_brief_markdown(interview_brief if isinstance(interview_brief, dict) else {})
    return (
        f"# {packet.get('role_title', 'Application')} - {packet.get('company', '')}\n\n"
        f"- Role ID: {packet.get('role_id', '')}\n"
        f"- Role URL: {packet.get('role_url', '')}\n"
        f"- Fit score: {packet.get('fit_score', '')}\n"
        f"- Exported: {exported_at}\n\n"
        "## Resume Focus\n\n"
        f"{resume_focus or '- Review manually.'}\n\n"
        "## Cover Letter\n\n"
        f"{packet.get('cover_letter', '')}\n\n"
        "## Screening Answers\n\n"
        f"{answers or 'Review manually.'}\n\n"
        f"{interview_markdown}"
        "## Review Gate\n\n"
        f"{review_gate or '- Human approval required before external submission.'}\n"
    )


def _interview_brief_markdown(brief: dict[str, object]) -> str:
    if not brief:
        return ""

    context = "\n".join(f"- {item}" for item in brief.get("thread_context", []))
    fit_map = "\n\n".join(
        "### {need}\n\n**Resume evidence:** {evidence}\n\n**How to frame it:** {readout}\n\n"
        "Evidence: {ids}".format(
            need=item.get("jd_need", "Role requirement"),
            evidence=item.get("evidence", ""),
            readout=item.get("readout", ""),
            ids=", ".join(item.get("evidence_ids", [])),
        )
        for item in brief.get("fit_map", [])
        if isinstance(item, dict)
    )
    stories = "\n\n".join(
        "### {title}\n\n**Situation:** {situation}\n\n**Task:** {task}\n\n**Action:** {action}\n\n"
        "**Result:** {result}\n\nEvidence: {ids}".format(
            title=item.get("title", "STAR story"),
            situation=item.get("situation", ""),
            task=item.get("task", ""),
            action=item.get("action", ""),
            result=item.get("result", ""),
            ids=", ".join(item.get("evidence_ids", [])),
        )
        for item in brief.get("star_stories", [])
        if isinstance(item, dict)
    )
    questions = "\n".join(f"- {item}" for item in brief.get("questions_for_interviewer", []))

    return (
        "## Interview Brief\n\n"
        "### Thread Context\n\n"
        f"{context or '- Review manually.'}\n\n"
        "### Positioning\n\n"
        f"{brief.get('positioning', '')}\n\n"
        "### JD-to-Resume Evidence Map\n\n"
        f"{fit_map or 'Review manually.'}\n\n"
        "### 60-Second Pitch\n\n"
        f"{brief.get('pitch_60_seconds', '')}\n\n"
        "### STAR Stories\n\n"
        f"{stories or 'Review manually.'}\n\n"
        "### Questions for the Interviewer\n\n"
        f"{questions or '- Review manually.'}\n\n"
        "### Follow-Up Note Draft (not sent)\n\n"
        f"{brief.get('follow_up_note', '')}\n\n"
        "### Accuracy Note\n\n"
        f"{brief.get('accuracy_note', '')}\n\n"
    )


def _focus_points(tags: list[str], reasons: list[str]) -> list[str]:
    return [f"Review your approved experience relevant to {tag.replace('_', ' ')}" for tag in tags[:4]] or ["Review your approved experience against the job description"]


def _legacy_cover_letter(profile: dict[str, str], role: dict[str, str], focus_points: list[str]) -> str:
    return _cover_letter(profile, role, focus_points)


def _cover_letter(profile: dict[str, str], role: dict[str, str], focus_points: list[str]) -> str:
    return (f"Dear Hiring Team,\n\nI am applying for the {role.get('role_title', 'role')} role at {role.get('company', 'your company')}. "
            "I would welcome a conversation about the problems this team is working on and where my experience could be useful."
            f"\n\nSincerely,\n{profile.get('full_name', 'Your Name')}")


def _screening_answers(profile: dict[str, str], role: dict[str, str], focus_points: list[str]) -> list[dict[str, str]]:
    return [
        {"question": "Why are you interested in this role?", "answer": ""},
        {"question": "What locations or work modes are you open to?", "answer": profile.get("target_locations", "")},
        {"question": "What should the reviewer know about your fit?", "answer": ""},
        {"question": "Work authorization / salary", "answer": _sensitive_answer(profile)},
    ]


def _sensitive_answer(profile: dict[str, str]) -> str:
    parts = []
    if profile.get("work_authorization", "").strip():
        parts.append(f"Work authorization: {profile['work_authorization'].strip()}")
    if profile.get("salary_range", "").strip():
        parts.append(f"Salary range: {profile['salary_range'].strip()}")
    return "; ".join(parts) or "Needs manual review before submission."


def _split_terms(value: str) -> list[str]:
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def _packet_stem(role_id):
    return slugify(role_id)[:48] + '-' + hashlib.sha256(role_id.encode()).hexdigest()[:24]
