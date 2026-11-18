"""Resolve imports, class bases and composition against the project (spec 5.1, 5.3).
Runs once at ingestion; results are stored in the model so diagrams can be built cheaply."""
from __future__ import annotations
import re
import posixpath
from collections import defaultdict
from . import config, ids

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _module_index(py_paths: list[str]) -> dict[str, list[str]]:
    """dotted module name -> candidate file paths. Strips leading non-package dirs (src/, packages/...)."""
    pathset = set(py_paths)
    idx: dict[str, list[str]] = defaultdict(list)
    for p in py_paths:
        parts = p[:-3].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        for k in range(len(parts)):
            prefix = parts[:k]
            ok = all(
                seg in config.WRAPPER_DIRS or "/".join(prefix[: i + 1]) + "/__init__.py" not in pathset
                for i, seg in enumerate(prefix)
            )
            if not ok:
                break
            idx[".".join(parts[k:])].append(p)
    return idx


def _pick(cands: list[str], importer: str) -> str | None:
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    # ambiguous: prefer the one sharing the longest directory prefix with the importer
    def shared(c):
        a, b = importer.split("/"), c.split("/")
        n = 0
        for x, y in zip(a, b):
            if x != y:
                break
            n += 1
        return (-n, c)
    return sorted(cands, key=shared)[0]


def resolve(model: dict) -> None:
    files = model["files"]
    py_paths = sorted(f["path"] for f in files.values() if f["kind"] == "python")
    pathset = set(py_paths)
    idx = _module_index(py_paths)

    def lookup_abs(dotted: str, importer: str) -> str | None:
        return _pick(idx.get(dotted, []), importer)

    def lookup_rel(level: int, module: str, importer: str) -> str | None:
        base = posixpath.dirname(importer)
        for _ in range(level - 1):
            base = posixpath.dirname(base)
        target = posixpath.join(base, *module.split(".")) if module else base
        for cand in (target + ".py", posixpath.join(target, "__init__.py")):
            if cand in pathset:
                return cand
        return None

    def sub_rel(level: int, module: str, name: str, importer: str) -> str | None:
        return lookup_rel(level, (module + "." + name) if module else name, importer)

    top_level_names = {p.split("/")[0].removesuffix(".py") for p in py_paths}
    for f in files.values():
        if f["kind"] != "python":
            continue
        targets, external = set(), set()
        for imp in f["imports"]:
            hit: set[str] = set()
            mod, names, level = imp["module"], imp["names"], imp["level"]
            if level:
                m = lookup_rel(level, mod, f["path"])
                if m:
                    hit.add(m)
                for n in names:
                    s = sub_rel(level, mod, n, f["path"])
                    if s:
                        hit.add(s)
            else:
                m = lookup_abs(mod, f["path"]) if mod else None
                if m:
                    hit.add(m)
                for n in names:
                    s = lookup_abs(f"{mod}.{n}" if mod else n, f["path"])
                    if s:
                        hit.add(s)
                if not hit and mod:
                    external.add(mod.split(".")[0])
            hit.discard(f["path"])
            imp["resolved"] = sorted(ids.file_id(h) for h in hit)
            targets |= {ids.file_id(h) for h in hit}
        f["importsFiles"] = sorted(targets)
        f["external"] = sorted(external)

    # ---- classes: bases and composition ----
    classes = model["classes"]
    by_name: dict[str, list[str]] = defaultdict(list)
    for c in classes.values():
        by_name[c["name"]].append(c["id"])

    def resolve_class(name: str, from_file: str) -> str | None:
        cands = by_name.get(name, [])
        if not cands:
            return None
        same = [c for c in cands if classes[c]["file"] == from_file]
        if same:
            return same[0]
        imported = set(files[from_file].get("importsFiles", []))
        via = [c for c in cands if classes[c]["file"] in imported]
        if via:
            return sorted(via)[0]
        return cands[0] if len(cands) == 1 else None

    for c in classes.values():
        c["baseIds"] = sorted({r for b in c["bases"]
                               if (r := resolve_class(_IDENT.findall(b)[-1], c["file"]) if _IDENT.findall(b) else None)})
        comp = set()
        for a in c["attrs"]:
            for tok in _IDENT.findall(a.get("type", "")):
                r = resolve_class(tok, c["file"])
                if r and r != c["id"]:
                    comp.add(r)
        c["composes"] = sorted(comp)
