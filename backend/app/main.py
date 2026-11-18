"""FastAPI app. Run from the repo root with `python run.py` (see README)."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from . import config, flows, github, ingest, levels, mermaid, search, storage
from .ids import mermaid_id

app = FastAPI(title="Ariadne demo API")
_views_cache: dict[tuple, levels.Views] = {}


class UrlBody(BaseModel):
    url: str
    confirmed: bool = False


class SettingsBody(BaseModel):
    nodeCeiling: int | None = None
    leaveDiagram: str | None = None
    theme: str | None = None


def _model(owner: str, repo: str) -> dict:
    m = storage.load_model(owner, repo)
    if not m:
        raise HTTPException(404, "Repository has not been analyzed yet")
    return m


def _views(owner: str, repo: str, ceiling: int | None = None) -> tuple[dict, levels.Views]:
    model = _model(owner, repo)
    c = ceiling or storage.settings()["nodeCeiling"]
    key = (owner, repo, model["meta"]["commit"], model["meta"].get("analyzedAt"), c)
    if key not in _views_cache:
        if len(_views_cache) > 20:
            _views_cache.clear()
        _views_cache[key] = levels.build_views(model, c)
    return model, _views_cache[key]


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/settings")
def get_settings():
    return storage.settings()


@app.put("/api/settings")
def put_settings(body: SettingsBody):
    return storage.save_settings({k: v for k, v in body.model_dump().items() if v is not None})


# ---------------------------------------------------------------- repositories & ingestion
@app.get("/api/repos")
def repos():
    return storage.list_repos()


@app.delete("/api/repos/{owner}/{repo}")
def delete_repo(owner: str, repo: str):
    storage.delete_repo(owner, repo)
    return {"ok": True}


@app.post("/api/ingest/preflight")
async def preflight(body: UrlBody):
    try:
        owner, repo = github.parse_url(body.url)
        meta = await github.fetch_metadata(owner, repo)
    except github.GitHubError as e:
        raise HTTPException(e.status, str(e))
    meta["large"] = meta["sizeMb"] >= config.LARGE_REPO_MB
    meta["estimateSeconds"] = github.estimate_seconds(meta["sizeMb"])
    meta["thresholdMb"] = config.LARGE_REPO_MB
    return meta


@app.post("/api/ingest")
async def start_ingest(body: UrlBody):
    info = await preflight(body)
    if info["large"] and not body.confirmed:
        raise HTTPException(409, {"needsConfirmation": True, **info})
    meta = {k: info[k] for k in ("owner", "repo", "branch", "commit", "sizeMb")}
    return ingest.start_job(meta).to_dict()


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    j = ingest.JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Unknown job")
    return j.to_dict()


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: str):
    j = ingest.JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Unknown job")
    j.cancel()
    return j.to_dict()


# ---------------------------------------------------------------- viewing
def _breadcrumb(v: levels.Views, diagram_id: str) -> list[dict]:
    chain, cur, seen = [], diagram_id, set()
    while cur and cur not in seen:
        seen.add(cur)
        d = v.diagrams[cur]
        chain.append({"id": d["id"], "label": d["crumb"]})
        cur = d["parent"]
    return list(reversed(chain))


@app.get("/api/repos/{owner}/{repo}/diagram/{diagram_id:path}")
def diagram(owner: str, repo: str, diagram_id: str, expanded: str = "", ceiling: int | None = None):
    model, v = _views(owner, repo, ceiling)
    diagram_id = unquote(diagram_id)
    d = v.diagrams.get(diagram_id) or flows.build(model, v, diagram_id)   # flow:/calls: are built on demand
    if not d:
        raise HTTPException(404, f"No diagram {diagram_id}")
    exp = {e for e in expanded.split(",") if e}
    meta = model["meta"]
    meta["lastOpened"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if diagram_id == levels.OVERVIEW_ID:  # opening the overview counts as opening the repo
        model["meta"] = meta
        storage.save_model(owner, repo, model)
    comp = v.components.get(d["compId"]) if d["compId"] else None
    id_map = {mermaid_id(n["id"]): n["id"] for n in d["nodes"]}
    id_map.update({mermaid_id(g["id"]): g["id"] for g in d.get("groups", [])})
    classes = {}
    for n in d["nodes"]:
        c = [k for k, on in (("edge", n.get("edgeCase")), ("unresolved", n.get("unresolved")), ("focus", n.get("focus"))) if on]
        if c:
            classes[n["id"]] = c
    return {"diagram": d, "idMap": id_map, "classes": classes, "mermaid": mermaid.to_mermaid(d, exp), "breadcrumb": _breadcrumb(v, diagram_id),
            "component": comp, "siblings": comp["diagrams"] if comp else {}, "meta": meta}


@app.get("/api/repos/{owner}/{repo}/component/{comp_id:path}")
def component(owner: str, repo: str, comp_id: str):
    model, v = _views(owner, repo)
    c = v.components.get(unquote(comp_id))
    if not c:
        raise HTTPException(404, "No such component")
    files = [model["files"][f] for f in c["files"] if f in model["files"]]
    return {**c, "fileDetails": [{"id": f["id"], "path": f["path"], "kind": f["kind"], "lines": f["lines"],
                                   "classes": len(f["classes"]), "functions": len(f["functions"])}
                                  for f in files[:500]]}


@app.get("/api/repos/{owner}/{repo}/element/{element_id:path}")
def element(owner: str, repo: str, element_id: str):
    """Details for any stable id (file/class/function) plus the roll-up chain used for comment badges."""
    model, v = _views(owner, repo)
    eid = unquote(element_id)
    rec = model["files"].get(eid) or model["classes"].get(eid) or model["functions"].get(eid) or v.components.get(eid)
    if not rec:
        raise HTTPException(404, "Unknown element")
    chain, cur = [], v.parents.get(eid)
    while cur:
        chain.append(cur)
        cur = v.parents.get(cur)
    out = {"element": rec, "ancestors": chain, "diagram": v.locate.get(eid)}
    if eid in model["files"]:   # "a function listed in a file's detail panel" (spec 5.4)
        out["functions"] = sorted(
            ({"id": f["id"], "qualname": f["qualname"], "line": f["line"], "endLine": f["endLine"],
              "hasFlow": f["id"] in v.locate} for f in model["functions"].values() if f["file"] == eid),
            key=lambda x: x["line"])
    return out


@app.get("/api/repos/{owner}/{repo}/source")
async def source(owner: str, repo: str, path: str, start: int | None = None, end: int | None = None):
    model = _model(owner, repo)
    meta = model["meta"]
    if meta.get("localPath"):
        full = (Path(meta["localPath"]) / path).resolve()
        if not str(full).startswith(str(Path(meta["localPath"]).resolve())) or not full.is_file():
            raise HTTPException(404, "File not found")
        text = full.read_text(encoding="utf-8", errors="replace")
    else:
        try:
            text = await github.fetch_source(owner, repo, meta["commit"], path)
        except github.GitHubError as e:
            raise HTTPException(e.status, str(e))
    gh = None if meta.get("localPath") else (
        f"https://github.com/{owner}/{repo}/blob/{meta['commit']}/{path}"
        + (f"#L{start}-L{end}" if start and end else ""))
    return {"path": path, "text": text, "commit": meta["commit"], "githubUrl": gh, "start": start, "end": end}


@app.get("/api/repos/{owner}/{repo}/search-index")
def search_index(owner: str, repo: str):
    model, v = _views(owner, repo)
    return search.build_index(model, v, _breadcrumb)


# Serve the built frontend (npm run build) from the same port when present.
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
