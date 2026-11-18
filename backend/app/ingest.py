"""Ingestion jobs: clone -> scan -> parse -> build, with staged progress and cancel at every stage (spec 4)."""
from __future__ import annotations
import shutil, subprocess, threading, time, uuid, os
from datetime import datetime, timezone
from pathlib import Path

from . import analyzer, calls, config, levels, mermaid, resolver, scanner, storage
from .scanner import Cancelled

STAGES = ["Downloading", "Scanning files", "Parsing", "Building diagrams"]


class Job:
    def __init__(self, owner: str, repo: str):
        self.id = uuid.uuid4().hex[:12]
        self.owner, self.repo = owner, repo
        self.stage = "Queued"
        self.stage_index = -1
        self.progress = 0.0           # 0..1 inside the current stage
        self.status = "running"       # running | done | cancelled | error
        self.message = ""
        self.cancel_flag = threading.Event()
        self.proc: subprocess.Popen | None = None
        self.work: Path | None = None

    def check(self):
        if self.cancel_flag.is_set():
            raise Cancelled()

    def set_stage(self, i: int):
        self.check()
        self.stage_index, self.stage, self.progress = i, STAGES[i], 0.0

    def to_dict(self):
        return {"id": self.id, "owner": self.owner, "repo": self.repo, "status": self.status, "stage": self.stage,
                "stageIndex": self.stage_index, "stages": STAGES, "progress": self.progress, "message": self.message}

    def cancel(self):
        self.cancel_flag.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


JOBS: dict[str, Job] = {}


def _cleanup(job: Job):
    if job.work:
        shutil.rmtree(job.work, ignore_errors=True)


def _clone(job: Job, owner: str, repo: str, branch: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    job.proc = subprocess.Popen(
        ["git", "clone", "--depth", "1", "--single-branch", "--branch", branch,
         f"https://github.com/{owner}/{repo}.git", str(dest)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
    while job.proc.poll() is None:
        if job.cancel_flag.is_set():
            job.proc.terminate()
            raise Cancelled()
        time.sleep(0.2)
        job.progress = min(0.95, job.progress + 0.02)  # git gives no reliable percentage when piped
    if job.proc.returncode != 0:
        err = (job.proc.stderr.read() or b"").decode(errors="replace")[-300:]
        raise RuntimeError(f"git clone failed: {err.strip()}")


def build_model(root: Path, meta: dict, job: Job | None = None) -> dict:
    """Scan -> parse -> resolve. Shared by remote clones and local example folders."""
    check = job.check if job else (lambda: None)
    if job:
        job.set_stage(1)
    sr = scanner.scan(root, check)
    if job:
        job.set_stage(2)
    def prog(i, n):
        if job:
            job.progress = i / max(1, n)
    raw = analyzer.analyze(root, sr, check, prog)
    model = {"meta": meta, **raw, "contextFiles": sorted(sr.context_files)}
    resolver.resolve(model)
    calls.resolve_all(model)
    if job:
        job.set_stage(3)
    views = levels.build_views(model, storage.settings()["nodeCeiling"])
    meta.update({
        "language": "Python", "fileCount": sum(1 for f in model["files"].values() if f["kind"] == "python"),
        "componentCount": len(views.diagrams["L0"]["nodes"]), "truncated": sr.truncated, "skipped": sr.skipped,
        "analyzedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "thumbnail": mermaid.to_mermaid(views.diagrams["L0"]),
    })
    return model


def run_job(job: Job, meta: dict):
    try:
        job.work = config.WORK_DIR / job.id
        job.set_stage(0)
        _clone(job, meta["owner"], meta["repo"], meta["branch"], job.work / "src")
        model = build_model(job.work / "src", meta, job)
        job.check()
        storage.save_model(meta["owner"], meta["repo"], model)  # only after full success => cancel leaves nothing
        job.status, job.stage, job.progress = "done", "Done", 1.0
    except Cancelled:
        job.status, job.message = "cancelled", "Cancelled. Partial work was removed."
    except Exception as e:  # noqa: BLE001
        job.status, job.message = "error", str(e)
    finally:
        _cleanup(job)


def start_job(meta: dict) -> Job:
    job = Job(meta["owner"], meta["repo"])
    JOBS[job.id] = job
    threading.Thread(target=run_job, args=(job, meta), daemon=True).start()
    return job


def ingest_local(path: Path, owner: str, repo: str) -> dict:
    """Used for bundled examples: same pipeline, no network."""
    meta = {"owner": owner, "repo": repo, "branch": "local", "commit": "local", "sizeMb": 0,
            "localPath": str(path.resolve()), "bundled": True}
    model = build_model(path, meta)
    storage.save_model(owner, repo, model)
    return model
