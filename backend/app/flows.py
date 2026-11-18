"""Level 2 diagrams (spec 5.4): per-function flowcharts, with a call-graph fallback.

Ids:  flow:<function id>   flowchart, or the call graph automatically when the flowchart cannot be drawn
      calls:<function id>  always the call graph
Built on demand (never eagerly for the whole repo) and cached on the Views object.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Optional

from . import ids

DASHED_STATUS = {"probable", "ambiguous", "callback", "dynamic"}


def split_id(did: str) -> tuple[str, str]:
    kind, rest = did.split(":", 1)
    return kind, rest


def is_test_func(model: dict, fid: str) -> bool:
    f = model["functions"][fid]
    return bool(model["files"][f["file"]].get("isTest"))


def flow_parent(model: dict, v, fid: str) -> Optional[str]:
    """Diagram the user came from: the class's UML if there is one, else the file's file map."""
    f = model["functions"][fid]
    if f["class"] and f["class"] in v.locate:
        return v.locate[f["class"]]
    return v.locate.get(f["file"])


# ------------------------------------------------------------------ callers index
def callers_index(model: dict, v) -> dict[str, list[tuple[str, bool]]]:
    """callee id -> [(caller id, dashed)], built once per Views. Test code is excluded (no tests in flows)."""
    if getattr(v, "_callers", None) is None:
        idx: dict[str, set[tuple[str, bool]]] = defaultdict(set)
        for f in model["functions"].values():
            if is_test_func(model, f["id"]):
                continue
            for c in f.get("calls", []):
                for tgt, dashed in call_targets(c):
                    idx[tgt].add((f["id"], dashed))
        v._callers = {k: sorted(s) for k, s in idx.items()}
    return v._callers


def call_targets(c: dict) -> list[tuple[str, bool]]:
    st = c.get("status")
    if st == "resolved" and c.get("resolved"):
        return [(c["resolved"], False)]
    if st == "probable" and c.get("resolved"):
        return [(c["resolved"], True)]
    if st == "ambiguous":
        return [(x, True) for x in c.get("candidates", [])[:3]]
    return []


# ------------------------------------------------------------------ flowchart
class _Flow:
    def __init__(self, model: dict, fid: str):
        self.model, self.fid = model, fid
        self.f = model["functions"][fid]
        self.calls = self.f.get("calls", [])
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}
        self.loops: list[dict] = []
        self.path = model["files"][self.f["file"]]["path"]

    def node(self, sid: str, shape: str, label: str, line: Optional[int] = None, **extra) -> str:
        nid = f"{self.fid}#{sid}"
        n = {"id": nid, "type": "step", "shape": shape, "label": label, "path": self.path,
             "meta": {"line": line} if line else {}, **extra}
        self.nodes[nid] = n
        return nid

    def connect(self, entries, nid: str, dashed: bool = False):
        for src, label in entries:
            kind = "flow_dashed" if dashed else "flow"
            eid = f"{src}->{nid}:{label}"
            self.edges[eid] = {"id": eid, "source": src, "target": nid, "kind": kind, "label": label}

    def mark(self, nid: str, reason: str):
        self.nodes[nid]["edgeCase"] = True
        self.nodes[nid]["edgeReason"] = reason

    def run(self, steps: list[dict], entries: list, edge: Optional[str], after: bool) -> list:
        cur = list(entries)
        for i, s in enumerate(steps):
            cur = self.step(s, cur, edge, after or i < len(steps) - 1)
        return cur

    def step(self, s: dict, cur: list, edge: Optional[str], after: bool) -> list:
        t = s["t"]
        if t == "call":
            c = self.calls[s["ci"]]
            if c.get("status") == "external":
                return cur
            return self.call_node(s, c, cur, edge)
        if t == "expr":
            nid = self.node(s["id"], "round", f'{s["kind"].replace("_", " ")}: {s["text"]}', s["line"])
            self.connect(cur, nid)
            if edge:
                self.mark(nid, edge)
            return [(nid, "")]
        if t in ("return", "raise"):
            label = f'{t} {s["expr"]}'.strip()
            nid = self.node(s["id"], "stadium", label, s["line"])
            self.connect(cur, nid)
            if t == "raise":
                self.mark(nid, "raise path")
            elif edge:
                self.mark(nid, edge)
            return []
        if t == "break":
            if self.loops:
                self.loops[-1]["breaks"].extend(cur)
            return []
        if t == "continue":
            if self.loops:
                self.connect(cur, self.loops[-1]["node"])
            return []
        if t == "if":
            d = self.node(s["id"], "diamond", s["cond"] + "?", s["line"])
            self.connect(cur, d)
            then, els = s["then"], s["else"]
            ends_early = bool(then) and then[-1]["t"] in ("return", "raise")
            guard = "guard-clause early exit" if (ends_early and not els and after) else None
            a = self.run(then, [(d, "yes")], edge or guard, after)
            b = self.run(els, [(d, "no")], edge, after) if els else [(d, "no")]
            return a + b
        if t == "loop":
            L = self.node(s["id"], "hexagon", s["cond"], s["line"])
            self.connect(cur, L)
            ctx = {"node": L, "breaks": []}
            self.loops.append(ctx)
            body = self.run(s["body"], [(L, "each" if s["kind"] == "for" else "true")], edge, True)
            self.loops.pop()
            for e in body:
                if e[0] != L:
                    self.connect([(e[0], e[1] or "next")], L)
            done = self.run(s["else"], [(L, "done")], edge, after) if s["else"] else [(L, "done")]
            return done + ctx["breaks"]
        if t == "try":
            handlers = s["handlers"]
            entry = cur
            if handlers:
                T = self.node(s["id"], "round", "try", s["line"])
                self.connect(cur, T)
                entry = [(T, "")]
            body = self.run(s["body"], entry, edge, after)
            if s["else"]:
                body = self.run(s["else"], body, edge, after)
            outs = list(body)
            for h in handlers:
                H = self.node(h["id"], "rect", f'except {h["exc"]}'.strip(), h["line"])
                self.mark(H, "except block")
                self.connect([(T, "on error")], H, dashed=True)
                outs += self.run(h["body"], [(H, "")], "except block", after)
            if s["finally"]:
                outs = self.run(s["finally"], outs, edge, after)
            return outs
        if t == "match":
            M = self.node(s["id"], "diamond", f'match {s["subject"]}', s["line"])
            self.connect(cur, M)
            outs, has_default = [], False
            for c in s["cases"]:
                has_default = has_default or c["pat"].strip() in ("_", "case _")
                outs += self.run(c["body"], [(M, c["pat"] or "case")], edge, after)
            return outs + ([] if has_default else [(M, "no match")])
        return cur

    def call_node(self, s: dict, c: dict, cur: list, edge: Optional[str]) -> list:
        model, status = self.model, c.get("status")
        dashed = status in DASHED_STATUS
        label, drill = c["text"] + "()", None
        rid = c.get("resolved")
        if rid and rid in model["functions"]:
            label = model["functions"][rid]["qualname"] + "()"
            if not is_test_func(model, rid):
                drill = f"flow:{rid}"
        elif c.get("targetClass"):
            label = f'new {model["classes"][c["targetClass"]]["name"]}'
        if status == "ambiguous":
            label += "  (?)"
        elif status == "dynamic":
            label = "dynamic: " + c["text"]
        elif status == "callback":
            label = f'callback: {c["text"]}()'
        nid = self.node(s["id"], "rect", label, s["line"], drill=drill, unresolved=dashed, status=status,
                        **({"candidates": c["candidates"]} if c.get("candidates") else {}))
        self.connect(cur, nid, dashed=dashed)
        if edge:
            self.mark(nid, edge)
        return [(nid, "")]

    def build(self) -> list[dict]:
        sig = self.f["qualname"] + (self.f["signature"] if len(self.f["signature"]) <= 28 else "(…)")
        S = self.node("start", "stadium", sig, self.f["line"])
        out = self.run(self.f["flow"]["steps"], [(S, "")], None, False)
        if out:
            E = self.node("end", "stadium", "end")
            self.connect(out, E)
        return sorted(self.nodes.values(), key=lambda n: n["id"])


def flowchart(model: dict, fid: str, ceiling: int) -> tuple[Optional[dict], Optional[str]]:
    """(diagram parts, None) or (None, reason the call graph is shown instead)."""
    f = model["functions"][fid]
    flow = f.get("flow")
    if not flow:
        return None, "no flow data for this function"
    if flow["unsupported"]:
        return None, "uses constructs the parser cannot chart (" + ", ".join(flow["unsupported"]) + ")"
    fl = _Flow(model, fid)
    nodes = fl.build()
    if len(nodes) > ceiling:
        return None, f"flowchart would have {len(nodes)} nodes, over your ceiling of {ceiling}"
    return {"nodes": nodes, "edges": sorted(fl.edges.values(), key=lambda e: e["id"])}, None


# ------------------------------------------------------------------ call graph
def callgraph(model: dict, v, fid: str, ceiling: int) -> dict:
    funcs = model["functions"]
    callers = callers_index(model, v)

    def callees(x: str) -> list[tuple[str, bool]]:
        out: dict[str, bool] = {}
        for c in funcs[x].get("calls", []):
            for tgt, dashed in call_targets(c):
                if tgt in funcs and not is_test_func(model, tgt):
                    out[tgt] = out.get(tgt, True) and dashed
        return sorted(out.items())

    def expand(hops: int) -> dict[str, int]:
        dist = {fid: 0}
        frontier = [fid]
        for h in range(1, hops + 1):
            nxt = []
            for x in frontier:
                for y, _ in callees(x):
                    if y not in dist:
                        dist[y] = h
                        nxt.append(y)
                for y, _ in callers.get(x, []):
                    if y not in dist:
                        dist[y] = h
                        nxt.append(y)
            frontier = sorted(set(nxt))
        return dist

    chosen, hops_used = expand(2), 2
    if len(chosen) > ceiling:
        chosen, hops_used = expand(1), 1
    omitted = 0
    if len(chosen) > ceiling:
        keep = sorted((d, k) for k, d in chosen.items() if k != fid)[: ceiling - 1]
        omitted = len(chosen) - 1 - len(keep)
        chosen = {fid: 0, **{k: d for d, k in keep}}

    nodes, edges = [], {}
    for x in sorted(chosen):
        fx = funcs[x]
        nodes.append({"id": x, "type": "function", "label": fx["qualname"], "path": model["files"][fx["file"]]["path"],
                      "drill": f"flow:{x}", "focus": x == fid, "meta": {"line": fx["line"], "endLine": fx["endLine"]}})
        for y, dashed in callees(x):
            if y in chosen:
                eid = f"{x}->{y}:call"
                edges[eid] = {"id": eid, "source": x, "target": y, "kind": "call_unresolved" if dashed else "call", "label": ""}
    return {"nodes": nodes, "edges": sorted(edges.values(), key=lambda e: e["id"]), "hops": hops_used, "omitted": omitted}


# ------------------------------------------------------------------ entry point
def build(model: dict, v, did: str) -> Optional[dict]:
    if did in v.diagrams:
        return v.diagrams[did]
    kind, fid = split_id(did)
    if kind not in ("flow", "calls") or fid not in model["functions"] or is_test_func(model, fid):
        return None
    f = model["functions"][fid]
    parent = flow_parent(model, v, fid)
    leaf = v.parents.get(f["file"])
    base = {"id": did, "compId": leaf, "parent": parent, "nodes": [], "edges": [], "groups": [],
            "meta": {"function": fid, "path": model["files"][f["file"]]["path"], "line": f["line"], "endLine": f["endLine"]}}
    reason = None
    if kind == "flow":
        parts, reason = flowchart(model, fid, v.ceiling)
        if parts:
            d = {**base, "kind": "flowchart", "title": f'{f["qualname"]} · flowchart', "crumb": f["name"], "direction": "TD", **parts}
            v.diagrams[did] = d
            return d
    g = callgraph(model, v, fid, v.ceiling)
    d = {**base, "kind": "callgraph", "title": f'{f["qualname"]} · call graph',
         "crumb": f["name"] + (" (calls)" if kind == "calls" else ""), "direction": "LR",
         "nodes": g["nodes"], "edges": g["edges"]}
    d["meta"].update({"fallbackReason": reason, "hops": g["hops"], "omitted": g["omitted"]})
    v.diagrams[did] = d
    return d
