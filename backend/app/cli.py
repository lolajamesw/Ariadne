"""python -m app.cli load-examples   -> analyze the bundled example projects (no network needed)."""
from __future__ import annotations
import sys
from pathlib import Path
from . import ingest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def main(argv: list[str]) -> int:
    if argv[:1] == ["load-examples"]:
        for d in sorted(p for p in EXAMPLES.iterdir() if p.is_dir()):
            m = ingest.ingest_local(d, "examples", d.name)
            print(f"analyzed examples/{d.name}: {m['meta']['fileCount']} files, {m['meta']['componentCount']} components")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
