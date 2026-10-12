from pathlib import Path

MESSAGE = 'Resume tailoring and bullet-library tools are not included in this public preview. Supply your own resume manually.'


def resume_templates(project_dir: Path) -> list:
    return []


def unavailable(*args, **kwargs):
    raise ValueError(MESSAGE)


rank_resume_plan = build_tailored_resume = unavailable
