"""Flat search index for the client (MiniSearch builds the fuzzy index in the browser, spec section 3/9).
`target` is the deepest element that actually appears as a node, so a function resolves to its class (UML)
or file (file map) until Part 3 adds function flowcharts."""
from __future__ import annotations

KIND_LABEL = {"uml": "UML", "filemap": "file map", "subcomponents": "sub-components",
              "overview": "overview", "filelist": "file list", "flowchart": "flowchart", "callgraph": "call graph"}


def build_index(model: dict, v, breadcrumb) -> list[dict]:
    items: list[dict] = []

    def route(did: str) -> list[str]:
        return [c["label"] for c in breadcrumb(v, did)]

    for cid, c in v.components.items():
        did = v.locate.get(cid)
        if did:
            items.append({"id": cid, "type": "component", "name": c["label"], "path": c["path"], "tags": c["tags"],
                          "diagramId": did, "target": cid, "route": route(did), "where": KIND_LABEL[v.diagrams[did]["kind"]]})
    for fid, f in model["files"].items():
        did = v.locate.get(fid)
        if did:
            items.append({"id": fid, "type": "file", "name": f["path"].rsplit("/", 1)[-1], "path": f["path"], "tags": [],
                          "diagramId": did, "target": fid, "route": route(did), "where": KIND_LABEL[v.diagrams[did]["kind"]]})
    for cid, c in model["classes"].items():
        did = v.locate.get(cid)
        if did:
            items.append({"id": cid, "type": "class", "name": c["name"], "path": model["files"][c["file"]]["path"], "tags": [],
                          "diagramId": did, "target": cid, "route": route(did), "where": KIND_LABEL[v.diagrams[did]["kind"]]})
    from . import flows
    for fid, fn in model["functions"].items():
        if fid in v.locate:      # has a flowchart (non-test code): land on it
            parent = flows.flow_parent(model, v, fid)
            items.append({"id": fid, "type": "function", "name": fn["qualname"], "path": model["files"][fn["file"]]["path"],
                          "tags": [], "diagramId": v.locate[fid], "target": fid,
                          "route": route(parent) if parent else [], "where": "flowchart"})
            continue
        target = fn["class"] or fn["file"]
        did = v.locate.get(target)
        if did:
            items.append({"id": fid, "type": "function", "name": fn["qualname"], "path": model["files"][fn["file"]]["path"],
                          "tags": [], "diagramId": did, "target": target,
                          "route": route(did), "where": KIND_LABEL[v.diagrams[did]["kind"]]})
    return items
