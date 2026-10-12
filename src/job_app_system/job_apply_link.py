from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def read_job_apply_profile() -> dict[str, Any]:
    """Read the Job Apply profile through its supported store helper."""
    helper = _store_helper()
    if helper is None:
        return {"connected": False, "message": "Job Apply store helper was not found."}

    try:
        result = subprocess.run(
            [sys.executable, str(helper), "profile-get"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"connected": False, "message": "Job Apply profile is unavailable."}

    if result.returncode != 0:
        return {"connected": False, "message": "Job Apply profile is unavailable."}
    try:
        profile = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"connected": False, "message": "Job Apply profile could not be read."}
    if not isinstance(profile, dict) or not profile:
        return {"connected": False, "message": "No Job Apply profile is saved yet."}

    location = profile.get("location")
    if isinstance(location, dict):
        location_text = ", ".join(
            str(location.get(key, "")).strip()
            for key in ("city", "state", "country")
            if str(location.get(key, "")).strip()
        )
    else:
        location_text = str(location or "").strip()

    return {
        "connected": True,
        "profile": {
            "full_name": " ".join(
                str(profile.get(key, "")).strip()
                for key in ("firstName", "lastName")
                if str(profile.get(key, "")).strip()
            ),
            "email": str(profile.get("email", "")),
            "phone": str(profile.get("phone", "")),
            "location": location_text,
            "linkedin_url": str(profile.get("linkedInUrl", "")),
            "resume_path": str(profile.get("resumePath", "")),
            "work_history": _work_history(profile.get("workHistory")),
            "education": _education(profile.get("education")),
            "skills": _strings(profile.get("skills")),
        },
    }


def _store_helper() -> Path | None:
    configured = os.environ.get("JOB_APPLY_STORE_HELPER", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_file() else None

    plugin_root = Path.home() / ".codex/plugins/cache/neonwatty-plugins/job-apply"
    candidates = list(plugin_root.glob("*/scripts/job-apply-store.py"))
    if not candidates:
        return None

    def version_key(path: Path) -> tuple[int, int, int, str]:
        version = path.parents[1].name
        match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", version)
        if not match:
            return (0, 0, 0, version)
        return tuple(int(part or 0) for part in match.groups()) + (version,)

    return max(candidates, key=version_key)


def _work_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    fields = ("company", "title", "startDate", "endDate", "current")
    return [
        {key: item.get(key, "") for key in fields}
        for item in value
        if isinstance(item, dict)
    ]


def _education(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    fields = ("school", "degree", "field", "endDate")
    return [
        {key: str(item.get(key, "")) for key in fields}
        for item in value
        if isinstance(item, dict)
    ]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
