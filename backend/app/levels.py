"""Diagram hierarchy builder: Level 0 overview, recursive component splitting, file maps, UML (spec 5.2-5.5).

Diagrams are built on demand from the stored raw model and the user's node ceiling, so changing the
ceiling never requires re-ingesting. Output is an intermediate representation (IR) of plain dicts;
`mermaid.py` turns IR into Mermaid text, and the frontend overlays interactivity by node id.
"""
from __future__ import annotations
import posixpath
from collections import defaultdict
from typing import Optional

from . import config, ids
from .roles import detect_roles

OVERVIEW_ID = "L0"
ROOT_ID = "comp:@root"
TESTS_ID = "comp:@tests"
MAX_LISTED_OTHER_FILES = 400


# ---------------------------------------------------------------- helpers
def _rel(path: str, base: str) -> str:
    return path[len(base) + 1:] if base and path.startswith(base + "/") else path


def _immediate(paths: list[str], base: str) -> tuple[list[str], list[str]]:
    """(child directory names, files directly inside base) for a set of repo-relative paths."""
    children, direct = set(), []
    for p in paths:
        r = _rel(p, base) if base else p
        if "/" in r:
            children.add(r.split("/", 1)[0])
        else:
            direct.append(p)
    return sorted(children), sorted(direct)


def group_items(items: list[tuple[str, str]], ceiling: int) -> list[tuple[str, list[str]]]:
    """Collapse a flat list of (id, name) into <= ceiling groups: by filename prefix first,
    falling back to alphabetical ranges. Returns [(label, [ids])]."""
    items = sorted(items, key=lambda t: t[1].lower())
    by_prefix: dict[str, list[str]] = defaultdict(list)
    for _id, name in items:
        stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        token = stem.replace("-", "_").split("_", 1)[0].lower() or "_"
        by_prefix[token].append(_id)
    names = {i: n for i, n in items}
    groups = [(f"{tok}_*", mem) for tok, mem in sorted(by_prefix.items()) if len(mem) >= 2]
    singles = [m[0] for tok, m in sorted(by_prefix.items()) if len(m) < 2]
    if singles:
        groups.append(("misc", singles))
    if 2 <= len(groups) <= ceiling and max(len(m) for _, m in groups) < len(items):
        return groups
    # alphabetical chunks
    size = -(-len(items) // max(2, ceiling))
    out = []
    for i in range(0, len(items), size):
        chunk = items[i:i + size]
        a, b = chunk[0][1].rsplit("/", 1)[-1], chunk[-1][1].rsplit("/", 1)[-1]
        out.append((f"{a[:1].lower()}…{b[:1].lower()}" if a[:1].lower() != b[:1].lower() else f"{a[:1].lower()}…", [c[0] for c in chunk]))
    return out


class Views:
    def __init__(self):
        self.components: dict[str, dict] = {}
        self.diagrams: dict[str, dict] = {}
        self.parents: dict[str, Optional[str]] = {}   # element id -> parent element id (roll-up chain)
        self.locate: dict[str, str] = {}               # element id -> deepest diagram id where it is a node
        self.ceiling = config.DEFAULT_NODE_CEILING
        self._callers = None                           # built lazily by flows.callers_index

    def as_dict(self):
        return {"components": self.components, "diagrams": self.diagrams, "parents": self.parents,
                "locate": self.locate, "ceiling": self.ceiling}


# ---------------------------------------------------------------- main entry
def build_views(model: dict, ceiling: int = config.DEFAULT_NODE_CEILING) -> Views:
    ceiling = max(config.MIN_NODE_CEILING, min(config.MAX_NODE_CEILING, int(ceiling)))
    v = Views()
    v.ceiling = ceiling
    files, classes = model["files"], model["classes"]
    funcs = model["functions"]

    test_py = sorted(f["path"] for f in files.values() if f.get("isTest") and f["kind"] == "python")
    test_other = sorted(f["path"] for f in files.values() if f.get("isTest") and f["kind"] != "python")
    main_paths = sorted(f["path"] for f in files.values() if not f.get("isTest"))

    # ---- top-level component discovery (hybrid: directories, descending wrapper folders) ----
    comp_dirs: list[str] = []
    loose: list[str] = []

    def process(base: str):
        children, direct = _immediate([p for p in main_paths if not base or p.startswith(base + "/")], base)
        loose.extend(direct)
        for ch in children:
            p = posixpath.join(base, ch) if base else ch
            if ch in config.WRAPPER_DIRS:
                process(p)
            else:
                comp_dirs.append(p)

    process("")

    def nontrivial_loose_py() -> bool:
        return any(p.endswith(".py") and not p.endswith("__init__.py") for p in loose)

    while len(comp_dirs) == 1 and not nontrivial_loose_py():
        base = comp_dirs.pop()
        before = len(loose)
        process(base)
        if not comp_dirs and len(loose) == before:  # nothing underneath, restore
            comp_dirs.append(base)
            break

    # ---- file -> top-level component mapping ----
    top: dict[str, str] = {}
    comp_files_all: dict[str, list[str]] = {}
    for d in comp_dirs:
        cid = ids.comp_id(d)
        comp_files_all[cid] = sorted(p for p in main_paths if p.startswith(d + "/"))
        for p in comp_files_all[cid]:
            top[ids.file_id(p)] = cid
    comp_files_all[ROOT_ID] = sorted(set(main_paths) - {p for ps in comp_files_all.values() for p in ps})
    for p in comp_files_all[ROOT_ID]:
        top[ids.file_id(p)] = ROOT_ID
    if test_py or test_other:
        comp_files_all[TESTS_ID] = sorted(test_py + test_other)
        for p in comp_files_all[TESTS_ID]:
            top[ids.file_id(p)] = TESTS_ID
    if not comp_files_all[ROOT_ID]:
        del comp_files_all[ROOT_ID]

    # ---- build each top-level component (recursive) ----
    labels = {ROOT_ID: "root / config", TESTS_ID: "tests"}
    for cid, paths in comp_files_all.items():
        is_tests = cid == TESTS_ID
        base = "" if cid in (ROOT_ID, TESTS_ID) else cid[len("comp:"):]
        label = labels.get(cid, posixpath.basename(base))
        _build_component(model, v, cid, label, paths, base, parent_diagram=OVERVIEW_ID,
                         parent_comp=None, ceiling=ceiling, no_uml=is_tests, top_name=label)

    # ---- Level 0 ----
    nodes, edge_counts = [], defaultdict(int)
    for cid in sorted(v.components):
        if v.components[cid]["parent"] is not None:
            continue
        nodes.append(_component_node(v, cid))
    for f in files.values():
        a = top.get(f["id"])
        for t in f.get("importsFiles", []):
            b = top.get(t)
            if a and b and a != b:
                edge_counts[(a, b)] += 1
    v.diagrams[OVERVIEW_ID] = {
        "id": OVERVIEW_ID, "kind": "overview", "title": "System overview", "compId": None, "parent": None,
        "crumb": "Overview", "direction": "LR", "nodes": nodes, "groups": [],
        "edges": [_edge(a, b, "aggregate", str(n)) for (a, b), n in sorted(edge_counts.items())],
        "meta": {"ceiling": ceiling, "truncated": model["meta"].get("truncated", False)},
    }
    for n in nodes:
        v.locate[n["id"]] = OVERVIEW_ID
        v.parents[n["id"]] = None

    # ---- roll-up parents for elements below components ----
    leaf_of_file = {}
    for cid, c in v.components.items():
        for fid in c.get("leafFiles", []):
            leaf_of_file[fid] = cid
    for fid, cid in leaf_of_file.items():
        v.parents[fid] = cid
    for c in classes.values():
        v.parents[c["id"]] = c["file"]
    for fn in funcs.values():
        v.parents[fn["id"]] = fn["class"] or fn["file"]
        if fn.get("flow") is not None and not files[fn["file"]].get("isTest"):
            v.locate[fn["id"]] = f"flow:{fn['id']}"     # built on demand by flows.build
    return v


def _edge(a: str, b: str, kind: str, label: str = "") -> dict:
    return {"id": f"{a}->{b}:{kind}", "source": a, "target": b, "kind": kind, "label": label}


def _component_node(v: Views, cid: str) -> dict:
    c = v.components[cid]
    return {"id": cid, "type": "component", "label": c["label"], "tags": c["tags"], "path": c["path"],
            "drill": c["defaultDiagram"], "diagrams": c["diagrams"], "analyzed": c["analyzed"],
            "meta": {"files": c["fileCount"], "classes": c["classCount"]}}


# ---------------------------------------------------------------- recursive component builder
def _build_component(model, v: Views, cid: str, label: str, paths: list[str], base: str,
                     parent_diagram: str, parent_comp: Optional[str], ceiling: int,
                     no_uml: bool, top_name: str) -> None:
    files, classes = model["files"], model["classes"]
    py = [p for p in paths if files[ids.file_id(p)]["kind"] == "python"]
    other = [p for p in paths if files[ids.file_id(p)]["kind"] != "python"]
    ext_imports = {e for p in py for e in files[ids.file_id(p)].get("external", [])}
    comp = {
        "id": cid, "label": label, "path": base, "parent": parent_comp, "children": [],
        "tags": detect_roles(posixpath.basename(base) if base else label, ext_imports, paths),
        "analyzed": bool(py), "files": [ids.file_id(p) for p in paths], "leafFiles": [],
        "fileCount": len(py) if py else len(other),
        "classCount": sum(len(files[ids.file_id(p)]["classes"]) for p in py),
        "diagrams": {}, "defaultDiagram": None, "diagram": parent_diagram,
    }
    v.components[cid] = comp

    # Non-Python component: plain file list, no edges
    if not py:
        shown = other[:MAX_LISTED_OTHER_FILES]
        nodes = [{"id": ids.file_id(p), "type": "file", "label": _rel(p, base), "path": p, "meta": {}} for p in shown]
        did = f"fm:{cid}"
        v.diagrams[did] = {"id": did, "kind": "filelist", "title": f"{label} · files (not analyzed)",
                           "compId": cid, "parent": parent_diagram, "crumb": label, "direction": "TD",
                           "nodes": nodes, "edges": [], "groups": [],
                           "meta": {"notAnalyzed": True, "omitted": max(0, len(other) - len(shown))}}
        comp["diagrams"]["filemap"] = did
        comp["defaultDiagram"] = did
        comp["leafFiles"] = [n["id"] for n in nodes]
        for n in nodes:
            v.locate[n["id"]] = did
        return

    nested = any("/" in _rel(p, base) for p in py) if base else any("/" in p for p in py)
    est = len(py)

    # Rule 1/2: stop at leaf when not nested, or the next diagram fits under the ceiling.
    if not nested or est <= ceiling:
        _build_leaf(model, v, comp, py, base, parent_diagram, ceiling, no_uml)
        return

    # Rule 3: split into one sub-component per child directory, loose files -> "other".
    children, direct = _immediate(py, base)
    sub_nodes, sub_of = [], {}
    child_specs = []
    for ch in children:
        child_base = posixpath.join(base, ch) if base else ch
        ccid = f"{cid}/{ch}"
        cpaths = sorted(p for p in paths if p.startswith((child_base + "/")))
        child_specs.append((ccid, ch, cpaths, child_base))
    if direct:
        child_specs.append((f"{cid}/@other", "other", sorted(direct), base))
    sub_id = f"sub:{cid}"
    for ccid, clabel, cpaths, cbase in child_specs:
        _build_component(model, v, ccid, clabel, cpaths, cbase, parent_diagram=sub_id, parent_comp=cid,
                         ceiling=ceiling, no_uml=no_uml, top_name=top_name)
        comp["children"].append(ccid)
        for p in cpaths:
            sub_of[ids.file_id(p)] = ccid
        sub_nodes.append(_component_node(v, ccid))
    # non-python files at this level stay listed in the inspector via comp["files"]
    counts = defaultdict(int)
    for p in py:
        f = files[ids.file_id(p)]
        for t in f.get("importsFiles", []):
            a, b = sub_of.get(f["id"]), sub_of.get(t)
            if a and b and a != b:
                counts[(a, b)] += 1
    v.diagrams[sub_id] = {
        "id": sub_id, "kind": "subcomponents", "title": f"{label} · sub-components", "compId": cid,
        "parent": parent_diagram, "crumb": label, "direction": "LR", "nodes": sub_nodes, "groups": [],
        "edges": [_edge(a, b, "aggregate", str(n)) for (a, b), n in sorted(counts.items())], "meta": {},
    }
    comp["diagrams"]["sub"] = sub_id
    comp["defaultDiagram"] = sub_id
    for n in sub_nodes:
        v.locate[n["id"]] = sub_id
        v.parents[n["id"]] = cid


def _build_leaf(model, v: Views, comp: dict, py: list[str], base: str, parent_diagram: str,
                ceiling: int, no_uml: bool) -> None:
    files, classes = model["files"], model["classes"]
    cid, label = comp["id"], comp["label"]
    fids = {ids.file_id(p) for p in py}
    comp["leafFiles"] = sorted(fids)

    # ---- file map ----
    nodes = [{"id": ids.file_id(p), "type": "file", "label": _rel(p, base) if base else p, "path": p,
              "meta": {"lines": files[ids.file_id(p)]["lines"],
                       "classes": len(files[ids.file_id(p)]["classes"]),
                       "functions": len(files[ids.file_id(p)]["functions"])}} for p in py]
    edges = []
    for p in py:
        f = files[ids.file_id(p)]
        for t in f.get("importsFiles", []):
            if t in fids:
                edges.append(_edge(f["id"], t, "import"))
    groups = []
    if len(nodes) > ceiling:  # rule 4: flat folder over ceiling -> collapsed groups
        for i, (glabel, members) in enumerate(group_items([(n["id"], n["label"]) for n in nodes], ceiling)):
            groups.append({"id": f"grp:fm:{cid}:{i}", "label": f"{glabel} ({len(members)})", "members": sorted(members), "collapsed": True})
    fm_id = f"fm:{cid}"
    v.diagrams[fm_id] = {"id": fm_id, "kind": "filemap", "title": f"{label} · file map", "compId": cid,
                         "parent": parent_diagram, "crumb": f"{label} (files)", "direction": "LR",
                         "nodes": nodes, "edges": sorted(edges, key=lambda e: e["id"]), "groups": groups, "meta": {}}
    comp["diagrams"]["filemap"] = fm_id
    for n in nodes:
        v.locate[n["id"]] = fm_id

    # ---- UML (components with >= 1 class; never for tests) ----
    cls = sorted(c for p in py for c in files[ids.file_id(p)]["classes"])
    if cls and not no_uml:
        cset = set(cls)
        cnodes = []
        for c in cls:
            r = classes[c]
            cnodes.append({"id": c, "type": "class", "label": r["name"], "file": r["file"], "path": files[r["file"]]["path"],
                           "attrs": r["attrs"], "methods": [{"id": m, "name": model["functions"][m]["name"],
                                                             "signature": model["functions"][m]["signature"]} for m in r["methods"]],
                           "meta": {"line": r["line"], "endLine": r["endLine"]}})
        cedges = []
        for c in cls:
            for b in classes[c].get("baseIds", []):
                if b in cset:
                    cedges.append(_edge(b, c, "inherit"))
            for t in classes[c].get("composes", []):
                if t in cset:
                    cedges.append(_edge(c, t, "compose"))
        cgroups = []
        if len(cnodes) > ceiling:
            by_file = defaultdict(list)
            for n in cnodes:
                by_file[n["path"]].append(n["id"])
            items = [(f"file:{p}", p) for p in sorted(by_file)]
            if len(items) <= ceiling:
                parts = [(posixpath.basename(p), by_file[p]) for _, p in items]
            else:
                parts = []
                for glabel, fid_list in group_items(items, ceiling):
                    parts.append((glabel, [c for fid in fid_list for c in by_file[fid[len("file:"):]]]))
            for i, (glabel, members) in enumerate(parts):
                cgroups.append({"id": f"grp:uml:{cid}:{i}", "label": f"{glabel} ({len(members)})",
                                "members": sorted(members), "collapsed": True})
        uml_id = f"uml:{cid}"
        v.diagrams[uml_id] = {"id": uml_id, "kind": "uml", "title": f"{label} · UML", "compId": cid,
                              "parent": parent_diagram, "crumb": f"{label} (UML)", "direction": "TD",
                              "nodes": cnodes, "edges": sorted(cedges, key=lambda e: e["id"]), "groups": cgroups, "meta": {}}
        comp["diagrams"]["uml"] = uml_id
        for n in cnodes:
            v.locate[n["id"]] = uml_id   # classes are deepest here (methods get flowcharts in a later part)
    comp["defaultDiagram"] = comp["diagrams"].get("uml") or fm_id
