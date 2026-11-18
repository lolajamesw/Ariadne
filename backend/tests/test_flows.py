import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from helpers import make_model
from app import resolver, calls, levels, flows, mermaid, search

C = lambda text, **kw: {**{"text": text, "chain": text.split(".")}, **kw}
create_steps = [
    {"t": "call", "id": "0", "ci": 0, "line": 3},                       # validate(title)  -> resolved
    {"t": "if", "id": "1", "cond": "not title", "line": 4, "else": [],
     "then": [{"t": "raise", "id": "1.t.0", "expr": "ValueError()", "line": 5}]},        # guard raise
    {"t": "if", "id": "2", "cond": "cached", "line": 6, "else": [],
     "then": [{"t": "return", "id": "2.t.0", "expr": "cached", "line": 7}]},             # guard return
    {"t": "try", "id": "3", "line": 8, "else": [], "finally": [],
     "body": [{"t": "call", "id": "3.b.0", "ci": 1, "line": 9}],                        # self.repo.save -> resolved
     "handlers": [{"exc": "KeyError", "id": "3.h0", "line": 10,
                   "body": [{"t": "call", "id": "3.h0.0", "ci": 2, "line": 11}]}]},    # cb() callback
    {"t": "loop", "id": "4", "kind": "for", "cond": "for x in items", "line": 12, "else": [],
     "body": [{"t": "call", "id": "4.b.0", "ci": 3, "line": 13}]},                      # svc.fetch -> probable
    {"t": "return", "id": "5", "expr": "task", "line": 14},
]


def model():
    m = make_model({
        "services/users.py": {
            "imports": [("util.checks", ["validate"], 0)],
            "classes": [("UserService", [], [("repo", "UserRepo")], ["create", "fetch"]),
                        ("UserRepo", [], [], ["save"])],
            "flows": {
                "UserService.create": {"params": ["self", "title", "cb"], "steps": create_steps, "calls": [
                    C("validate"), C("self.repo.save"), C("cb"), C("svc.fetch")]},
                "UserService.fetch": {"params": ["self"], "steps": [], "calls": [C("print")]},
                "UserRepo.save": {"params": ["self", "obj"], "steps": [], "calls": []},
            }},
        "util/checks.py": {"functions": ["validate"], "flows": {"validate": {"params": ["x"], "steps": [], "calls": []}}},
        "api/routes.py": {
            "imports": [("services.users", ["UserService"], 0)],
            "functions": ["create_user", "huge", "gen"],
            "flows": {
                "create_user": {"params": ["title"], "steps": [
                    {"t": "call", "id": "0", "ci": 0, "line": 2}, {"t": "call", "id": "1", "ci": 1, "line": 3},
                    {"t": "call", "id": "2", "ci": 2, "line": 4}], "calls": [
                    C("UserService"), C("svc.create"), C("getattr(x)", chain=["?"])]},
                "huge": {"params": [], "steps": [{"t": "call", "id": str(i), "ci": 0, "line": i} for i in range(30)],
                         "calls": [C("UserService.create")]},
                "gen": {"params": [], "steps": [], "calls": [], "unsupported": ["generator (yield)"]},
            }},
        "tests/test_x.py": {"functions": ["test_it"]},
    })
    resolver.resolve(m)
    calls.resolve_all(m)
    return m


def status(m, fn, i):
    return m["functions"][fn]["calls"][i]


def test_call_resolution():
    m = model()
    create = "func:services/users.py::UserService.create"
    assert status(m, create, 0)["resolved"] == "func:util/checks.py::validate"         # via from-import
    assert status(m, create, 1)["resolved"] == "func:services/users.py::UserRepo.save"  # self.attr.method via attr type
    assert status(m, create, 2)["status"] == "callback"
    assert status(m, create, 3)["status"] == "probable"                                 # svc.fetch: unknown receiver, one candidate
    cu = "func:api/routes.py::create_user"
    ctor = status(m, cu, 0)
    assert ctor["status"] == "resolved" and ctor["targetClass"] == "class:services/users.py::UserService"
    assert status(m, cu, 1)["status"] == "probable"
    assert status(m, cu, 2)["status"] == "dynamic"
    assert status(m, "func:services/users.py::UserService.fetch", 0)["status"] == "external"   # print


def views(m, ceiling=20):
    return levels.build_views(m, ceiling)


def test_flowchart_structure_and_edge_cases():
    m = model(); v = views(m)
    d = flows.build(m, v, "flow:func:services/users.py::UserService.create")
    assert d["kind"] == "flowchart" and d["parent"] == "uml:comp:services"
    by_label = {n["label"]: n for n in d["nodes"]}
    assert by_label["not title?"]["shape"] == "diamond"
    assert by_label["raise ValueError()"]["edgeCase"]                                   # raise path
    assert by_label["return cached"]["edgeReason"] == "guard-clause early exit"          # early return before more code
    assert by_label["except KeyError"]["edgeReason"] == "except block"
    assert by_label["callback: cb()"]["unresolved"] and by_label["callback: cb()"]["edgeCase"]  # inside except
    assert not by_label["return task"].get("edgeCase")                                   # final return is the main path
    assert by_label["UserRepo.save()"]["drill"] == "flow:func:services/users.py::UserRepo.save"
    kinds = {e["kind"] for e in d["edges"]}
    assert "flow_dashed" in kinds
    text = mermaid.to_mermaid(d)
    assert text.startswith("flowchart TD") and "-.->" in text and "{" in text and "([" in text
    assert mermaid.to_mermaid(d) == mermaid.to_mermaid(d)


def test_fallbacks_to_call_graph():
    m = model(); v = views(m)
    big = flows.build(m, v, "flow:func:api/routes.py::huge")
    assert big["kind"] == "callgraph" and "over your ceiling" in big["meta"]["fallbackReason"]
    gen = flows.build(m, v, "flow:func:api/routes.py::gen")
    assert gen["kind"] == "callgraph" and "yield" in gen["meta"]["fallbackReason"]
    # under a bigger ceiling the 32-node flowchart fits
    v2 = views(m, 50)
    assert flows.build(m, v2, "flow:func:api/routes.py::huge")["kind"] == "flowchart"


def test_call_graph_callers_and_callees():
    m = model(); v = views(m)
    d = flows.build(m, v, "calls:func:services/users.py::UserService.create")
    ids = {n["id"] for n in d["nodes"]}
    assert "func:api/routes.py::create_user" in ids                 # caller (probable -> dashed)
    assert "func:services/users.py::UserRepo.save" in ids           # callee
    assert "func:util/checks.py::validate" in ids
    assert next(n for n in d["nodes"] if n["focus"])["id"] == "func:services/users.py::UserService.create"
    dashed = {(e["source"], e["target"]) for e in d["edges"] if e["kind"] == "call_unresolved"}
    assert ("func:api/routes.py::create_user", "func:services/users.py::UserService.create") in dashed
    assert "-.->" in mermaid.to_mermaid(d) and mermaid.to_mermaid(d).startswith("flowchart LR")
    # tests never get flows
    assert flows.build(m, v, "flow:func:tests/test_x.py::test_it") is None


def test_ceiling_truncates_call_graph():
    m = model(); v = views(m, 5)
    d = flows.build(m, v, "calls:func:services/users.py::UserService.create")
    assert len(d["nodes"]) <= 5


def test_search_lands_on_flow():
    m = model(); v = views(m)
    def crumbs(vv, did):
        out, cur = [], did
        while cur:
            dd = vv.diagrams.get(cur) or flows.build(m, vv, cur)
            out.append({"id": cur, "label": dd["crumb"]}); cur = dd["parent"]
        return list(reversed(out))
    idx = {i["id"]: i for i in search.build_index(m, v, crumbs)}
    fn = idx["func:services/users.py::UserService.create"]
    assert fn["diagramId"] == "flow:func:services/users.py::UserService.create" and fn["target"] == fn["id"]
    assert fn["route"] == ["Overview", "services (UML)"]
    assert idx["func:tests/test_x.py::test_it"]["where"] != "flowchart"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
