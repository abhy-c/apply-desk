from pathlib import Path

import pytest

from job_app_system.application import DEFAULT_PROFILE, build_application_packet, save_profile
from job_app_system.bullet_library import create_proposal
from job_app_system.resume_customization import resume_templates
from job_app_system.web import _state


def test_clean_workspace_loads_without_private_resume_files(tmp_path: Path):
    import shutil
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / 'src/job_app_system/assets/examples', tmp_path / 'data')
    state = _state(tmp_path)
    assert state['roles'] == []
    assert state['resume_templates'] == []
    assert state['profile']['full_name'] == 'Your Name'


def test_packet_uses_saved_profile_without_claiming_owner_experience(tmp_path: Path):
    profile = save_profile(tmp_path, {'full_name': 'Alex Example'})
    packet = build_application_packet(profile, {'role_id': 'example', 'company': 'Example Co', 'role_title': 'Product Manager', 'domain_tags': 'fintech'})
    assert 'Alex Example' in packet['cover_letter']
    assert 'IBM' not in str(packet)
    assert packet['screening_answers'][0]['answer'] == ''


def test_private_resume_actions_are_explicitly_unavailable(tmp_path: Path):
    assert resume_templates(tmp_path) == []
    with pytest.raises(ValueError, match='not included'):
        create_proposal(tmp_path, {})
