"""Deterministic Mermaid emitter (spec section 6). Same IR in -> byte-identical text out:
sorted nodes/edges, ids derived from stable ids, no timestamps or random values."""
from __future__ import annotations
from .ids import mermaid_id

MAX_UML_ATTRS = 10
MAX_UML_METHODS = 12
SHAPES = {"rect": ("[", "]"), "stadium": ("([", "])"), "diamond": ("{", "}"), "hexagon": ("{{", "}}"), "round": ("(", ")")}
DASHED_KINDS = {"flow_dashed", "call_unresolved"}


def _q(text: str) -> str:
    return str(text).replace('"', "#quot;").replace("\n", " ")


def _visible_map(d: dict, expanded: set[str]) -> dict[str, str]:
    """node id -> id of what represents it on screen (itself, or its collapsed group)."""
    rep = {n["id"]: n["id"] for n in d["nodes"]}
    for g in d.get("groups", []):
        if g["id"] not in expanded and g.get("collapsed", True):
            for m in g["members"]:
                rep[m] = g["id"]
    return rep


def _edges(d: dict, rep: dict[str, str]):
    """Edges re-pointed at collapsed groups; parallel edges merge, counts add up when numeric."""
    merged: dict[tuple, dict] = {}
    for e in d["edges"]:
        a, b = rep.get(e["source"], e["source"]), rep.get(e["target"], e["target"])
        if a == b:
            continue
        key = (a, b, e["kind"], "" if e["label"].isdigit() else e["label"])
        if key in merged:
            m = merged[key]
            if m["label"].isdigit() and e["label"].isdigit():
                m["label"] = str(int(m["label"]) + int(e["label"]))
            elif a != e["source"] or b != e["target"]:
                m["_n"] += 1
        else:
            merged[key] = {"source": a, "target": b, "kind": e["kind"], "label": e["label"], "_n": 1}
    for m in merged.values():
        if not m["label"] and m["_n"] > 1:
            m["label"] = str(m["_n"])
    return [merged[k] for k in sorted(merged)]


def to_mermaid(d: dict, expanded: set[str] | None = None) -> str:
    expanded = expanded or set()
    if d["kind"] == "uml":
        return _uml(d, expanded)
    return _flowchart(d, expanded)


def _node_line(n: dict) -> str:
    label = n["label"]
    if n["type"] == "component":
        extra = []
        if n.get("tags"):
            extra.append("/".join(n["tags"]))
        if not n.get("analyzed", True):
            extra.append("not analyzed")
        elif n.get("meta", {}).get("files"):
            extra.append(f"{n['meta']['files']} file{'' if n['meta']['files'] == 1 else 's'}")
        if extra:
            label = f'{label}<br/><small>{_q(" · ".join(extra))}</small>'
        return f'{mermaid_id(n["id"])}["{label if "<br/>" in label else _q(label)}"]'
    if n["type"] == "function":
        base = n["path"].rsplit("/", 1)[-1] if n.get("path") else ""
        return f'{mermaid_id(n["id"])}["{_q(label)}<br/><small>{_q(base)}</small>"]'
    shape = n.get("shape", "rect")
    open_, close = SHAPES.get(shape, SHAPES["rect"])
    return f'{mermaid_id(n["id"])}{open_}"{_q(label)}"{close}'


def _flowchart(d: dict, expanded: set[str]) -> str:
    rep = _visible_map(d, expanded)
    direction = d.get("direction", "TD")
    lines = [f"flowchart {direction}"]
    in_group = set()
    node_by_id = {n["id"]: n for n in d["nodes"]}
    for g in sorted(d.get("groups", []), key=lambda g: g["id"]):
        if g["id"] in expanded or not g.get("collapsed", True):
            lines.append(f'  subgraph {mermaid_id(g["id"])}["{_q(g["label"])}"]')
            for m in sorted(g["members"]):
                lines.append("    " + _node_line(node_by_id[m]))
                in_group.add(m)
            lines.append("  end")
        else:
            lines.append(f'  {mermaid_id(g["id"])}[["{_q(g["label"])}"]]')
            in_group.update(g["members"])
    for n in sorted(d["nodes"], key=lambda n: n["id"]):
        if n["id"] not in in_group:
            lines.append("  " + _node_line(n))
    for e in _edges(d, rep):
        a, b = mermaid_id(e["source"]), mermaid_id(e["target"])
        arrow = "-.->" if e["kind"] in DASHED_KINDS else "-->"
        lines.append(f'  {a} {arrow}|{_q(e["label"])}| {b}' if e["label"] else f"  {a} {arrow} {b}")
    return "\n".join(lines) + "\n"


def _class_block(n: dict, indent: str) -> list[str]:
    mid = mermaid_id(n["id"])
    out = [f'{indent}class {mid}["{_q(n["label"])}"] {{']
    attrs = n.get("attrs", [])
    for a in attrs[:MAX_UML_ATTRS]:
        out.append(f'{indent}  +{_q(a["name"])}{(": " + _q(a["type"])) if a.get("type") else ""}')
    if len(attrs) > MAX_UML_ATTRS:
        out.append(f"{indent}  +… {len(attrs) - MAX_UML_ATTRS} more attributes")
    methods = n.get("methods", [])
    for m in methods[:MAX_UML_METHODS]:
        out.append(f'{indent}  +{_q(m["name"])}()')
    if len(methods) > MAX_UML_METHODS:
        out.append(f"{indent}  +… {len(methods) - MAX_UML_METHODS} more methods")
    out.append(f"{indent}}}")
    return out


def _uml(d: dict, expanded: set[str]) -> str:
    rep = _visible_map(d, expanded)
    lines = ["classDiagram"]
    node_by_id = {n["id"]: n for n in d["nodes"]}
    in_group = set()
    for g in sorted(d.get("groups", []), key=lambda g: g["id"]):
        in_group.update(g["members"])
        if g["id"] in expanded or not g.get("collapsed", True):
            lines.append(f'  namespace {mermaid_id(g["id"])} {{')
            for m in sorted(g["members"]):
                lines.extend(_class_block(node_by_id[m], "    "))
            lines.append("  }")
        else:
            gid = mermaid_id(g["id"])
            lines.append(f'  class {gid}["{_q(g["label"])}"]')
            lines.append(f"  <<group>> {gid}")
    for n in sorted(d["nodes"], key=lambda n: n["id"]):
        if n["id"] not in in_group:
            lines.extend(_class_block(n, "  "))
    for e in _edges(d, rep):
        a, b = mermaid_id(e["source"]), mermaid_id(e["target"])
        if e["kind"] == "inherit":
            lines.append(f"  {a} <|-- {b}")
        else:
            lines.append(f"  {a} *-- {b}")
    return "\n".join(lines) + "\n"
