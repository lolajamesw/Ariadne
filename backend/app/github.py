"""GitHub helpers: URL validation, metadata, on-demand source (spec section 4, 5.6)."""
from __future__ import annotations
import re
import httpx
from . import config

_URL = re.compile(r"^https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?(?:[/#?].*)?$")


class GitHubError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def parse_url(url: str) -> tuple[str, str]:
    m = _URL.match(url.strip())
    if not m:
        raise GitHubError("Enter a public GitHub URL like https://github.com/owner/repository")
    return m.group(1), m.group(2)


def _headers(accept: str = "application/vnd.github+json") -> dict:
    h = {"Accept": accept, "User-Agent": "ariadne-demo"}
    if config.GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return h


async def fetch_metadata(owner: str, repo: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"https://api.github.com/repos/{owner}/{repo}", headers=_headers())
        if r.status_code == 404:
            raise GitHubError("Repository not found. Only public repositories are supported.", 404)
        if r.status_code in (403, 429):
            raise GitHubError("GitHub rate limit reached. Set GITHUB_TOKEN or try again later.", 429)
        r.raise_for_status()
        info = r.json()
        branch = info["default_branch"]
        r2 = await c.get(f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}",
                         headers=_headers("application/vnd.github.sha"))
        r2.raise_for_status()
        sha = r2.text.strip()
    size_mb = round(info.get("size", 0) / 1024, 1)  # API reports KB
    return {"owner": owner, "repo": repo, "branch": branch, "commit": sha, "sizeMb": size_mb,
            "private": info.get("private", False), "description": info.get("description")}


def estimate_seconds(size_mb: float) -> int:
    """Deliberately rough: ~3 MB/s clone plus fixed overhead and parse time."""
    return int(5 + size_mb / 3 + size_mb / 10)


async def fetch_source(owner: str, repo: str, commit: str, path: str) -> str:
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{path}"
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
        r = await c.get(url, headers={"User-Agent": "ariadne-demo"})
        if r.status_code != 200:
            raise GitHubError(f"Could not fetch {path} at {commit[:7]} ({r.status_code})", r.status_code)
        return r.text
