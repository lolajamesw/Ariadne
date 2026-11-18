"""Stable ids (spec 5.1). Annotations and drafts attach to these, so never randomize them."""
from __future__ import annotations


def dir_id(path: str) -> str:
    return f"dir:{path}"


def file_id(path: str) -> str:
    return f"file:{path}"


def class_id(path: str, qualname: str) -> str:
    return f"class:{path}::{qualname}"


def func_id(path: str, qualname: str) -> str:
    return f"func:{path}::{qualname}"


def comp_id(path: str) -> str:
    """Component = a directory (or the synthetic root/other groups)."""
    return f"comp:{path or '.'}"


def mermaid_id(stable_id: str) -> str:
    """Deterministic Mermaid-safe node id derived from a stable id.
    Readable prefix + short stable hash, so exports are diff-friendly and collision-free."""
    import hashlib, re
    h = hashlib.sha1(stable_id.encode("utf-8")).hexdigest()[:6]
    slug = re.sub(r"[^A-Za-z0-9]+", "_", stable_id.split(":", 1)[-1]).strip("_")[-24:] or "n"
    return f"n_{slug}_{h}"
