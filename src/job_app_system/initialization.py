from pathlib import Path
from importlib.resources import files
from .storage import transaction, atomic_text
from .workflow import ensure_workflow_files

def initialize_workspace(project_dir: Path):
    data=Path(project_dir)/'data'
    with transaction(data):
        for source in files('job_app_system').joinpath('assets/examples').iterdir():
            target=data/source.name
            if not target.exists(): atomic_text(target,source.read_text(encoding='utf-8'))
        ensure_workflow_files(data)
