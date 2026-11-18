"""Build a synthetic raw model without tree-sitter, so levels/mermaid/resolver can be tested anywhere."""
from app import ids


def make_model(py_files: dict[str, dict], other_files=(), classes=None):
    """py_files: path -> {"imports": [(module, names, level)], "classes": [ (name, bases, [(attr,type)], [methods]) ]}"""
    files, cls, funcs = {}, {}, {}
    from app.analyzer import is_test_path
    for path, spec in py_files.items():
        fid = ids.file_id(path)
        rec = {"id": fid, "path": path, "kind": "python", "lines": 10, "classes": [], "functions": [],
               "imports": [{"module": m, "names": list(n), "level": lv, "line": 1} for m, n, lv in spec.get("imports", [])],
               "isTest": is_test_path(path)}
        for name, bases, attrs, methods in spec.get("classes", []):
            cid = ids.class_id(path, name)
            mids = []
            for m in methods:
                f_id = ids.func_id(path, f"{name}.{m}")
                funcs[f_id] = {"id": f_id, "file": fid, "name": m, "qualname": f"{name}.{m}", "class": cid,
                               "line": 1, "endLine": 2, "signature": "(self)", "async": False}
                mids.append(f_id)
            cls[cid] = {"id": cid, "file": fid, "name": name, "qualname": name, "bases": list(bases),
                        "attrs": [{"name": a, "type": t} for a, t in attrs], "methods": mids, "line": 1, "endLine": 5}
            rec["classes"].append(cid)
        for fn in spec.get("functions", []):
            f_id = ids.func_id(path, fn)
            funcs[f_id] = {"id": f_id, "file": fid, "name": fn, "qualname": fn, "class": None,
                           "line": 1, "endLine": 2, "signature": "()", "async": False}
            rec["functions"].append(f_id)
        files[fid] = rec
    for p in other_files:
        fid = ids.file_id(p)
        files[fid] = {"id": fid, "path": p, "kind": "other", "lines": 0, "imports": [], "classes": [],
                      "functions": [], "isTest": is_test_path(p)}
    return {"meta": {"owner": "o", "repo": "r"}, "files": files, "classes": cls, "functions": funcs}
