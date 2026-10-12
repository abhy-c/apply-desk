"""Compatibility launcher for source checkouts; the CLI also supports init."""
from pathlib import Path
from job_app_system.initialization import initialize_workspace

initialize_workspace(Path.cwd())
print("Local data initialized. Run: python -m job_app_system.cli serve --port 8767")
