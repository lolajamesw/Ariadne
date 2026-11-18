"""One command starts everything:  python run.py
Backend on :8000. If frontend/ exists (added in Part 2), Vite dev server on :5173 is started too."""
import subprocess, sys, shutil
from pathlib import Path

root = Path(__file__).parent
procs = [subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"],
                          cwd=root / "backend")]
if (root / "frontend" / "package.json").exists() and shutil.which("npm"):
    procs.append(subprocess.Popen(["npm", "run", "dev"], cwd=root / "frontend", shell=sys.platform == "win32"))
try:
    for p in procs:
        p.wait()
except KeyboardInterrupt:
    for p in procs:
        p.terminate()
