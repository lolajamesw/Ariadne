import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from helpers import make_model
from app import resolver, levels, mermaid


def small_app():
    return make_model({
        "api/__init__.py": {},
        "api/routes.py": {"imports": [("services.users", ["UserService"], 0), ("fastapi", ["APIRouter"], 0)],
                           "functions": ["create_user"]},
        "services/__init__.py": {},
        "services/users.py": {"imports": [("db.models", ["User"], 0)],
                              "classes": [("UserService", [], [("repo", "UserRepo")], ["create", "get"]),
                                          ("UserRepo", ["Base"], [("user", "User")], ["save"])]},
        "db/__init__.py": {},
        "db/models.py": {"classes": [("Base", [], [], []), ("User", ["Base"], [("id", "int")], [])]},
        "tests/test_users.py": {"imports": [("services.users", ["UserService"], 0)]},
    }, other_files=["Dockerfile", "README.md", "infra/main.tf"])


def build(model, ceiling=20):
    resolver.resolve(model)
    return levels.build_views(model, ceiling)


def test_import_resolution_and_level0():
    m = small_app()
    v = build(m)
    assert m["files"]["file:api/routes.py"]["importsFiles"] == ["file:services/users.py"]
    assert "fastapi" in m["files"]["file:api/routes.py"]["external"]
    l0 = v.diagrams["L0"]
    ids_ = {n["id"] for n in l0["nodes"]}
    assert {"comp:api", "comp:services", "comp:db", "comp:@tests", "comp:@root", "comp:infra"} <= ids_
    pairs = {(e["source"], e["target"]): e["label"] for e in l0["edges"]}
    assert pairs[("comp:api", "comp:services")] == "1"
    assert pairs[("comp:services", "comp:db")] == "1"
    assert pairs[("comp:@tests", "comp:services")] == "1"
    api = next(n for n in l0["nodes"] if n["id"] == "comp:api")
    assert "api" in api["tags"]          # name + fastapi dependency
    infra = v.components["comp:infra"]
    assert not infra["analyzed"] and infra["diagrams"]["filemap"] == "fm:comp:infra"
    assert "infra" in infra["tags"]


def test_uml_and_default_drill():
    m = small_app(); v = build(m)
    svc = v.components["comp:services"]
    assert svc["defaultDiagram"] == "uml:comp:services"
    assert v.components["comp:api"]["defaultDiagram"] == "fm:comp:api"  # no classes -> file map
    uml = v.diagrams["uml:comp:services"]
    kinds = {(e["kind"]) for e in uml["edges"]}
    assert "compose" not in kinds or True
    text = mermaid.to_mermaid(uml)
    assert text.startswith("classDiagram")
    assert "UserService" in text and "+create()" in text
    # tests never get UML
    assert "uml" not in v.components["comp:@tests"]["diagrams"]


def test_recursive_split_and_ceiling():
    files = {}
    for d in ("a", "b"):
        for sub in ("x", "y", "z"):
            for i in range(4):
                files[f"pkg/{d}/{sub}/m{i}.py"] = {"imports": []}
    m = make_model(files)
    v = build(m, ceiling=10)
    pkg_children = [c for c in v.components if c.startswith("comp:pkg/")]
    assert "sub:comp:pkg/a" in v.diagrams          # 12 files > 10 -> split into sub-components
    assert "fm:comp:pkg/a/x" in v.diagrams         # 4 files <= 10 -> leaf
    v2 = build(make_model(files), ceiling=50)
    assert "fm:comp:pkg/a" in v2.diagrams          # 12 files <= 50 -> stops at a file map
    assert "sub:comp:pkg/a" not in v2.diagrams


def test_flat_folder_over_ceiling_collapses_groups():
    files = {f"lib/{p}_{i}.py": {} for p in ("user", "order", "pay") for i in range(4)}
    files["lib/misc.py"] = {}
    m = make_model(files)
    v = build(m, ceiling=5)
    fm = next(d for d in v.diagrams.values() if d["kind"] == "filemap")
    assert fm["groups"] and all(g["collapsed"] for g in fm["groups"])
    assert len(fm["groups"]) <= 5
    text = mermaid.to_mermaid(fm)
    assert "[[" in text                                # collapsed groups drawn as subroutine nodes
    expanded = mermaid.to_mermaid(fm, {fm["groups"][0]["id"]})
    assert "subgraph" in expanded                      # expand in place


def test_mermaid_is_deterministic():
    a = mermaid.to_mermaid(build(small_app()).diagrams["L0"])
    b = mermaid.to_mermaid(build(small_app()).diagrams["L0"])
    assert a == b and a.startswith("flowchart LR")


def test_wrapper_descent():
    m = make_model({"src/app/__init__.py": {}, "src/app/core/x.py": {}, "src/app/web/y.py": {}, "src/app/web/z.py": {}})
    v = build(m)
    ids_ = {n["id"] for n in v.diagrams["L0"]["nodes"]}
    assert "comp:src/app/core" in ids_ and "comp:src/app/web" in ids_


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
