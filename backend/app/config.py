"""Central configuration. Override with environment variables."""
from __future__ import annotations
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("ARIADNE_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
WORK_DIR = DATA_DIR / "_work"  # temporary clones; always cleaned up
LARGE_REPO_MB = int(os.environ.get("ARIADNE_LARGE_REPO_MB", "100"))
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # optional, raises API rate limits only

IGNORED_DIRS = {".git", "venv", ".venv", "__pycache__", "node_modules"}
MAX_FILE_BYTES = 1_000_000
MAX_FILES = 5_000
DEFAULT_NODE_CEILING = 20
MIN_NODE_CEILING, MAX_NODE_CEILING = 5, 50
WRAPPER_DIRS = {"src", "packages", "lib", "source"}
CONTEXT_FILE_NAMES = {
    "dockerfile", "docker-compose.yml", "docker-compose.yaml", "requirements.txt",
    "pyproject.toml", "setup.py", "setup.cfg", "pipfile",
}
