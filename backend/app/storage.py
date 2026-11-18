"""JSON-file persistence: one folder per repo under data/ (spec section 11)."""
from __future__ import annotations
import json, os, shutil, tempfile
from pathlib import Path
from typing import Any
from . import config


def repo_key(owner: str, repo: str) -> str:
    return f"{owner}__{repo}"


def repo_dir(owner: str, repo: str) -> Path:
    return config.DATA_DIR / repo_key(owner, repo)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data: Any) -> None:
    """Atomic write so a crash or cancel never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_model(owner: str, repo: str) -> dict | None:
    return read_json(repo_dir(owner, repo) / "model.json")


def save_model(owner: str, repo: str, model: dict) -> None:
    write_json(repo_dir(owner, repo) / "model.json", model)


def list_repos() -> list[dict]:
    out = []
    if not config.DATA_DIR.exists():
        return out
    for d in sorted(config.DATA_DIR.iterdir()):
        m = read_json(d / "model.json") if d.is_dir() and not d.name.startswith("_") else None
        if m:
            out.append(m["meta"])
    return out


def delete_repo(owner: str, repo: str) -> None:
    shutil.rmtree(repo_dir(owner, repo), ignore_errors=True)


def settings() -> dict:
    defaults = {"nodeCeiling": config.DEFAULT_NODE_CEILING, "leaveDiagram": "ask", "theme": "light"}
    return {**defaults, **(read_json(config.DATA_DIR / "settings.json", {}) or {})}


def save_settings(s: dict) -> dict:
    s = dict(s)
    if "nodeCeiling" in s:
        s["nodeCeiling"] = max(config.MIN_NODE_CEILING, min(config.MAX_NODE_CEILING, int(s["nodeCeiling"])))
    merged = {**settings(), **s}
    write_json(config.DATA_DIR / "settings.json", merged)
    return merged
