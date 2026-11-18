"""Raw model builder using tree-sitter (spec 5.1).

Part 1 extracts: files, imports, classes (bases, attributes, methods), functions.
Part 3 will add per-function `calls` and `flow` (branches) via the FLOW_HOOK below.

NOTE: written against py-tree-sitter >= 0.23 (Language(tspython.language()), Parser(language)).
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Callable, Optional

from . import ids

_parser = None


def _get_parser():
    global _parser
    if _parser is None:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
        _parser = Parser(Language(tspython.language()))
    return _parser


def _text(node) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None else ""


def _line(node) -> int:
    return node.start_point[0] + 1


def _end_line(node) -> int:
    return node.end_point[0] + 1


# Part 3 plugs in here: (function_node, src_bytes, ctx) -> dict | None
FLOW_HOOK: Optional[Callable] = None


def parse_python_file(rel_path: str, source: bytes) -> dict:
    """Return a per-file record plus its classes and functions."""
    tree = _get_parser().parse(source)
    root = tree.root_node
    fid = ids.file_id(rel_path)
    rec = {
        "id": fid, "path": rel_path, "kind": "python",
        "lines": source.count(b"\n") + 1,
        "imports": [], "classes": [], "functions": [],
        "parseError": bool(root.has_error),
    }
    classes: dict[str, dict] = {}
    funcs: dict[str, dict] = {}

    def handle_import(node):
        if node.type == "import_statement":
            for ch in node.named_children:
                alias = None
                target = ch
                if ch.type == "aliased_import":
                    target = ch.child_by_field_name("name")
                    a = ch.child_by_field_name("alias")
                    alias = _text(a) if a is not None else None
                if target is not None and target.type == "dotted_name":
                    mod = _text(target)
                    rec["imports"].append({
                        "module": mod, "names": [], "level": 0, "line": _line(node),
                        "bindings": [{"local": alias or mod.split(".")[0], "module": mod, "name": None, "alias": bool(alias)}]})
        elif node.type == "import_from_statement":
            mod = node.child_by_field_name("module_name")
            level, module = 0, ""
            if mod is not None:
                if mod.type == "relative_import":
                    for c in mod.children:
                        if c.type == "import_prefix":
                            level = _text(c).count(".")
                        elif c.type == "dotted_name":
                            module = _text(c)
                else:
                    module = _text(mod)
            names, bindings = [], []
            for n in node.children_by_field_name("name"):
                t = n.child_by_field_name("name") if n.type == "aliased_import" else n
                al = n.child_by_field_name("alias") if n.type == "aliased_import" else None
                if t is not None:
                    names.append(_text(t))
                    bindings.append({"local": _text(al) if al is not None else _text(t), "module": module,
                                     "name": _text(t), "level": level})
            if any(c.type == "wildcard_import" for c in node.children):
                names.append("*")
            rec["imports"].append({"module": module, "names": names, "level": level, "line": _line(node), "bindings": bindings})

    def collect_self_attrs(fn_node, attrs: dict):
        """Attributes from `self.x = ...` / `self.x: T = ...` anywhere in __init__ (not nested defs)."""
        stack = [fn_node.child_by_field_name("body")]
        while stack:
            n = stack.pop()
            if n is None:
                continue
            if n.type in ("function_definition", "class_definition", "lambda"):
                continue
            if n.type == "assignment":
                left = n.child_by_field_name("left")
                if left is not None and left.type == "attribute":
                    obj, attr = left.child_by_field_name("object"), left.child_by_field_name("attribute")
                    if obj is not None and _text(obj) == "self" and attr is not None:
                        ann = n.child_by_field_name("type")
                        right = n.child_by_field_name("right")
                        typ = _text(ann) if ann is not None else ""
                        if not typ and right is not None and right.type == "call":
                            fn = right.child_by_field_name("function")
                            if fn is not None:
                                typ = _text(fn)  # constructor call heuristic: self.x = Foo(...)
                        attrs.setdefault(_text(attr), {"name": _text(attr), "type": typ})
            stack.extend(reversed(n.children))

    def visit_function(node, parent_qual: str, owner_class: Optional[str]):
        name = _text(node.child_by_field_name("name"))
        qual = f"{parent_qual}.{name}" if parent_qual else name
        f_id = ids.func_id(rel_path, qual)
        params = node.child_by_field_name("parameters")
        frec = {
            "id": f_id, "file": fid, "name": name, "qualname": qual, "class": owner_class,
            "line": _line(node), "endLine": _end_line(node),
            "signature": _text(params) if params is not None else "()",
            "async": any(c.type == "async" for c in node.children),
        }
        if FLOW_HOOK is not None:
            frec.update(FLOW_HOOK(node, source, {"path": rel_path, "qualname": qual}) or {})
        funcs[f_id] = frec
        return f_id, name

    def visit_class(node, parent_qual: str):
        name = _text(node.child_by_field_name("name"))
        qual = f"{parent_qual}.{name}" if parent_qual else name
        c_id = ids.class_id(rel_path, qual)
        sup = node.child_by_field_name("superclasses")
        bases = []
        if sup is not None:
            for a in sup.named_children:
                if a.type != "keyword_argument":
                    bases.append(_text(a))
        crec = {"id": c_id, "file": fid, "name": name, "qualname": qual, "bases": bases,
                "attrs": [], "methods": [], "line": _line(node), "endLine": _end_line(node)}
        attrs: dict[str, dict] = {}
        body = node.child_by_field_name("body")
        for stmt in (body.named_children if body is not None else []):
            inner = stmt.child_by_field_name("definition") if stmt.type == "decorated_definition" else stmt
            if inner is None:
                continue
            if inner.type == "function_definition":
                f_id, fname = visit_function(inner, qual, c_id)
                crec["methods"].append(f_id)
                if fname == "__init__":
                    collect_self_attrs(inner, attrs)
            elif inner.type == "class_definition":
                visit_class(inner, qual)
            elif inner.type == "expression_statement":
                for e in inner.named_children:
                    if e.type == "assignment":
                        left, ann = e.child_by_field_name("left"), e.child_by_field_name("type")
                        if left is not None and left.type == "identifier":
                            attrs.setdefault(_text(left), {"name": _text(left), "type": _text(ann) if ann is not None else ""})
        crec["attrs"] = sorted(attrs.values(), key=lambda a: a["name"])
        classes[c_id] = crec
        return c_id

    def walk(node, parent_qual: str = ""):
        for stmt in node.named_children:
            inner = stmt.child_by_field_name("definition") if stmt.type == "decorated_definition" else stmt
            if inner is None:
                continue
            if inner.type in ("import_statement", "import_from_statement"):
                handle_import(inner)
            elif inner.type == "function_definition":
                visit_function(inner, parent_qual, None)
            elif inner.type == "class_definition":
                visit_class(inner, parent_qual)
            elif inner.type in ("if_statement", "try_statement", "with_statement"):
                # imports / defs guarded by `if TYPE_CHECKING:`, `try: import x`
                for blk in inner.named_children:
                    if blk.type in ("block", "else_clause", "except_clause", "elif_clause", "finally_clause"):
                        walk(blk, parent_qual)

    walk(root)
    rec["classes"] = sorted(classes)
    rec["functions"] = sorted(funcs)
    return {"file": rec, "classes": classes, "functions": funcs}


def is_test_path(path: str) -> bool:
    p = path.lower()
    parts = p.split("/")
    name = parts[-1]
    return (any(x in ("tests", "test") for x in parts[:-1]) or name.startswith("test_")
            or name.endswith("_test.py") or name == "conftest.py")


def analyze(root: Path, scan_result, check_cancel: Callable[[], None] = lambda: None,
            on_progress: Callable[[int, int], None] = lambda i, n: None) -> dict:
    """Parse every scanned file into the raw model dicts (no diagrams yet)."""
    files, classes, funcs = {}, {}, {}
    n = len(scan_result.py_files)
    for i, rel in enumerate(scan_result.py_files):
        check_cancel()
        try:
            parsed = parse_python_file(rel, (root / rel).read_bytes())
        except Exception as e:  # one bad file must not sink the whole repo
            files[ids.file_id(rel)] = {"id": ids.file_id(rel), "path": rel, "kind": "python", "lines": 0,
                                       "imports": [], "classes": [], "functions": [], "parseError": True, "error": str(e)}
            continue
        parsed["file"]["isTest"] = is_test_path(rel)
        files[parsed["file"]["id"]] = parsed["file"]
        classes.update(parsed["classes"])
        funcs.update(parsed["functions"])
        if i % 25 == 0:
            on_progress(i, n)
    for rel in scan_result.other_files:
        fid = ids.file_id(rel)
        files[fid] = {"id": fid, "path": rel, "kind": "other", "lines": 0, "imports": [], "classes": [],
                      "functions": [], "isTest": is_test_path(rel)}
    on_progress(n, n)
    return {"files": files, "classes": classes, "functions": funcs}


from . import flow_extract as _flow_extract  # noqa: E402  (imported last: flow_extract lazily imports this module)

FLOW_HOOK = _flow_extract.extract
