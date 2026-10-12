from __future__ import annotations


def suggested_angle(role_row: dict[str, object]) -> str:
    return "Review the posting and add one specific example from your own approved experience."


def draft_email(contact_row: dict[str, object]) -> tuple[str, str]:
    company = contact_row.get("company", "your team")
    title = contact_row.get("role_title", "the role")
    first_name = str(contact_row.get("name", "")).split()
    first_name = first_name[0] if first_name else "there"
    # No applicant facts or application status are assumed.
    return (f"Question about {title} at {company}",
            f"Hi {first_name},\n\nI'm interested in {title} at {company}. "
            "Are you the right person to speak with about the role?\n\nBest,\n[Your name]")
