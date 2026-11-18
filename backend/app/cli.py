"""Command line helpers.
  python -m app.cli load-examples                 analyze the bundled example projects (no network needed)
  python -m app.cli analyze <folder> [name]       analyze any local folder, e.g. this project itself:  analyze .. ariadne
  python -m app.cli flow <owner> <repo> <text>    debug: print the extracted flow tree and resolved calls of functions
                                                  whose qualified id contains <text>
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from . import ingest, storage

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _report(owner: str, name: str, m: dict) -> None:
    print(f"analyzed {owner}/{name}: {m['meta']['fileCount']} Python files, {m['meta']['componentCount']} components")


def main(argv: list[str]) -> int:
    if argv[:1] == ["load-examples"]:
        for d in sorted(p for p in EXAMPLES.iterdir() if p.is_dir()):
            _report("examples", d.name, ingest.ingest_local(d, "examples", d.name))
        return 0
    if argv[:1] == ["analyze"] and len(argv) >= 2:
        path = Path(argv[1]).resolve()
        if not path.is_dir():
            print(f"not a folder: {path}")
            return 1
        name = argv[2] if len(argv) > 2 else path.name
        _report("local", name, ingest.ingest_local(path, "local", name))
        print(f"open it in the app: #/repo/local/{name}/L0")
        return 0
    if argv[:1] == ["flow"] and len(argv) == 4:
        model = storage.load_model(argv[1], argv[2])
        if not model:
            print("repo not analyzed")
            return 1
        hits = [f for fid, f in model["functions"].items() if argv[3] in fid]
        for f in hits[:5]:
            print("==", f["id"])
            print(json.dumps({"unsupported": f.get("flow", {}).get("unsupported"), "steps": f.get("flow", {}).get("steps")}, indent=1))
            for c in f.get("calls", []):
                print("  call", c["text"], "->", c.get("status"), c.get("resolved") or c.get("candidates") or "")
        print(f"{len(hits)} match(es)")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
