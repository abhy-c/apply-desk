from pathlib import Path

from job_app_system.application import (
    DEFAULT_PROFILE,
    build_application_packet,
    build_packet_with_saved_draft,
    export_application_packet,
    load_application_packet,
    save_application_packet,
    slugify,
)


def test_application_packet_uses_role_context() -> None:
    role = {
        "role_id": "role_1",
        "company": "Ramp",
        "role_title": "Senior Product Manager",
        "role_url": "https://example.com",
        "role_score": "92",
        "role_score_reasons": "open; nyc; fresh_0_30",
        "domain_tags": "fintech,enterprise_workflow",
        "location": "New York, NY",
    }

    packet = build_application_packet(DEFAULT_PROFILE, role)

    assert packet["company"] == "Ramp"
    assert packet["fit_score"] == "92"
    assert "Senior Product Manager" in packet["cover_letter"]
    assert any("fintech" in point.lower() for point in packet["resume_focus"])
    assert packet["review_gate"]


def test_slugify_keeps_generated_ids_url_safe() -> None:
    assert slugify("Senior PM, AI / Workflow!") == "senior-pm-ai-workflow"


def test_application_packet_draft_can_be_saved_loaded_merged_and_exported(tmp_path: Path) -> None:
    role = {
        "role_id": "role_1",
        "company": "Ramp",
        "role_title": "Senior Product Manager",
        "role_url": "https://example.com",
        "role_score": "92",
        "role_score_reasons": "open; nyc; fresh_0_30",
        "domain_tags": "fintech,enterprise_workflow",
        "location": "New York, NY",
    }
    packet = build_application_packet(DEFAULT_PROFILE, role)
    packet["cover_letter"] = "Edited cover letter."
    packet["screening_answers"][0]["answer"] = "Edited answer."

    saved = save_application_packet(tmp_path, packet)
    loaded = load_application_packet(tmp_path, "role_1")
    merged = build_packet_with_saved_draft(tmp_path, DEFAULT_PROFILE, role)
    export = export_application_packet(tmp_path / "out", saved)

    assert loaded is not None
    assert loaded["cover_letter"] == "Edited cover letter."
    assert merged["screening_answers"][0]["answer"] == "Edited answer."
    assert "saved_at" in saved
    assert "Edited cover letter." in Path(export["path"]).read_text(encoding="utf-8")


def test_application_packet_preserves_structured_interview_brief(tmp_path: Path) -> None:
    packet = {
        "role_id": "example_program_manager",
        "company": "Example Consulting",
        "role_title": "Senior Program Manager, Pharmaceutical R&D",
        "interview_brief": {
            "thread_context": ["Jordan is co-leading the pursuit."],
            "positioning": "Transformation operator with regulated-industry experience.",
            "fit_map": [
                {
                    "jd_need": "Integrated planning",
                    "evidence": "Built operating cadence and workflows.",
                    "evidence_ids": ["F0001"],
                    "readout": "Lead with execution discipline.",
                }
            ],
            "pitch_60_seconds": "A concise pitch.",
            "star_stories": [
                {
                    "title": "Workflow redesign",
                    "situation": "A slow process.",
                    "task": "Improve it.",
                    "action": "Redesigned workflow.",
                    "result": "Faster cycle time.",
                    "evidence_ids": ["F0001"],
                }
            ],
            "questions_for_interviewer": ["Where is the program stuck?"],
            "follow_up_note": "Hi Jordan,\n\nThank you.",
            "accuracy_note": "Draft only; do not send automatically.",
        },
        "review_gate": ["Manual review required."],
    }

    saved = save_application_packet(tmp_path, packet)
    export = export_application_packet(tmp_path / "out", saved)
    markdown = Path(export["path"]).read_text(encoding="utf-8")

    assert saved["interview_brief"]["fit_map"][0]["evidence_ids"] == ["F0001"]
    assert "## Interview Brief" in markdown
    assert "Follow-Up Note Draft (not sent)" in markdown
    assert "Where is the program stuck?" in markdown
