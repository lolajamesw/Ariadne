"""Call resolution (spec 5.4): resolve each extracted call through imports, `self.method()`, `self.attr.method()`,
`Class.method()`, `module.func()` and constructors. Anything that cannot be resolved but plausibly targets project
code is kept as an *unresolved* call (drawn dashed) rather than guessed silently.

status values on each call:
  resolved   -> `resolved` holds a function id (or None with `targetClass` for a class without __init__)
  probable   -> exactly one project method has that name but the receiver type is unknown (dashed)
  ambiguous  -> several project methods share the name (dashed, `candidates`)
  callback   -> calling one of the function's own parameters (dashed)
  dynamic    -> getattr(...)(...) or calling a call result (dashed)
  external   -> builtin / third-party / unrelated: not charted
"""
from __future__ import annotations
import re
from collections import defaultdict

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Method names so common on builtins that matching them to project methods would only add noise.
COMMON = {
    "append", "extend", "insert", "pop", "remove", "clear", "copy", "get", "items", "keys", "values", "update", "add",
    "discard", "setdefault", "join", "split", "strip", "lstrip", "rstrip", "replace", "format", "startswith", "endswith",
    "lower", "upper", "encode", "decode", "read", "write", "close", "open", "sort", "count", "index", "find", "seek",
    "flush", "readline", "readlines", "mkdir", "exists", "is_file", "is_dir", "resolve", "isoformat", "dumps", "loads",
    "send", "run", "start", "stop", "put", "post", "delete", "commit", "rollback", "execute", "save", "load", "dump",
}


class Index:
    def __init__(self, model: dict):
        self.model = model
        self.files, self.classes, self.funcs = model["files"], model["classes"], model["functions"]
        self.top_funcs: dict[str, dict[str, str]] = defaultdict(dict)
        self.top_classes: dict[str, dict[str, str]] = defaultdict(dict)
        self.methods: dict[str, dict[str, str]] = defaultdict(dict)
        self.methods_by_name: dict[str, list[str]] = defaultdict(list)
        self.class_by_name: dict[str, list[str]] = defaultdict(list)
        for fid, f in self.funcs.items():
            if f["class"]:
                self.methods[f["class"]][f["name"]] = fid
                self.methods_by_name[f["name"]].append(fid)
            elif "." not in f["qualname"]:
                self.top_funcs[f["file"]][f["name"]] = fid
        for cid, c in self.classes.items():
            self.class_by_name[c["name"]].append(cid)
            if "." not in c["qualname"]:
                self.top_classes[c["file"]][c["name"]] = cid
        self._sym: dict[str, tuple[dict, dict]] = {}

    # ---- per-file import tables ----
    def sym(self, file_id: str) -> tuple[dict, dict]:
        """(modules, symbols): local/dotted name -> module file id ; local name -> (module file id, symbol name)."""
        if file_id in self._sym:
            return self._sym[file_id]
        modules: dict[str, str] = {}
        symbols: dict[str, tuple[str, str]] = {}
        for imp in self.files[file_id].get("imports", []):
            for b in imp.get("bindings", []):
                if b["name"] is None:
                    if b.get("moduleFile"):
                        modules[b["local"] if b.get("alias") else b["module"]] = b["moduleFile"]
                else:
                    if b.get("subFile"):
                        modules[b["local"]] = b["subFile"]
                    elif b.get("moduleFile"):
                        symbols[b["local"]] = (b["moduleFile"], b["name"])
        self._sym[file_id] = (modules, symbols)
        return self._sym[file_id]

    def find_symbol(self, file_id: str, name: str, depth: int = 0):
        """Top-level function/class `name` in a file, following simple re-exports (`from .x import name`)."""
        if name in self.top_funcs[file_id]:
            return ("func", self.top_funcs[file_id][name])
        if name in self.top_classes[file_id]:
            return ("class", self.top_classes[file_id][name])
        if depth < 3:
            _, symbols = self.sym(file_id)
            if name in symbols:
                return self.find_symbol(symbols[name][0], symbols[name][1], depth + 1)
        return None

    def mro(self, class_id: str) -> list[str]:
        out, queue, seen = [], [class_id], set()
        while queue:
            c = queue.pop(0)
            if c in seen or c not in self.classes:
                continue
            seen.add(c)
            out.append(c)
            queue.extend(self.classes[c].get("baseIds", []))
        return out

    def find_method(self, class_id: str, name: str, skip_self: bool = False) -> str | None:
        for c in self.mro(class_id)[1 if skip_self else 0:]:
            if name in self.methods[c]:
                return self.methods[c][name]
        return None

    def class_of_type(self, type_str: str, file_id: str) -> str | None:
        for tok in _IDENT.findall(type_str or ""):
            sym = self.find_symbol(file_id, tok)
            if sym and sym[0] == "class":
                return sym[1]
            cands = self.class_by_name.get(tok, [])
            if len(cands) == 1:
                return cands[0]
        return None

    def attr_class(self, class_id: str, attr: str) -> str | None:
        for c in self.mro(class_id):
            for a in self.classes[c]["attrs"]:
                if a["name"] == attr:
                    return self.class_of_type(a.get("type", ""), self.classes[c]["file"])
        return None

    # ---- resolution ----
    def _target(self, sym) -> dict:
        kind, ident = sym
        if kind == "func":
            return {"status": "resolved", "resolved": ident}
        init = self.find_method(ident, "__init__")
        return {"status": "resolved", "resolved": init, "targetClass": ident}

    def _by_name(self, name: str, exclude: str) -> dict:
        if name in COMMON or name.startswith("__"):
            return {"status": "external", "resolved": None}
        cands = sorted(set(self.methods_by_name.get(name, [])) - {exclude})
        if not cands:
            return {"status": "external", "resolved": None}
        if len(cands) == 1:
            return {"status": "probable", "resolved": cands[0]}
        return {"status": "ambiguous", "resolved": None, "candidates": cands[:5]}

    def resolve(self, call: dict, func: dict) -> dict:
        chain = call["chain"]
        file_id, cls = func["file"], func["class"]
        modules, symbols = self.sym(file_id)
        params = set(func.get("params", []))
        self_name = (func.get("params") or [None])[0] if cls else None

        if chain == ["?"]:
            return {"status": "dynamic", "resolved": None}
        if len(chain) == 1:
            name = chain[0]
            if name in params and name != self_name:
                return {"status": "callback", "resolved": None}
            sym = self.find_symbol(file_id, name)
            if sym:
                return self._target(sym)
            if name in symbols:
                sf = self.find_symbol(*symbols[name])
                return self._target(sf) if sf else {"status": "external", "resolved": None}
            return {"status": "external", "resolved": None}

        head, last = chain[0], chain[-1]
        if cls and (head == self_name or head == "cls"):
            if len(chain) == 2:
                m = self.find_method(cls, chain[1])
                if m:
                    return {"status": "resolved", "resolved": m}
            elif len(chain) == 3:
                target_cls = self.attr_class(cls, chain[1])
                if target_cls:
                    m = self.find_method(target_cls, chain[2])
                    if m:
                        return {"status": "resolved", "resolved": m}
                    return {"status": "external", "resolved": None}
            return self._by_name(last, func["id"])
        if head == "super" and cls and len(chain) == 2:
            m = self.find_method(cls, chain[1], skip_self=True)
            return {"status": "resolved", "resolved": m} if m else {"status": "external", "resolved": None}
        if head == "?":
            return self._by_name(last, func["id"])

        # module.func(), module.Class(), module.Class.method(), including dotted plain imports
        for k in range(len(chain) - 1, 0, -1):
            prefix = ".".join(chain[:k])
            if prefix in modules:
                rest = chain[k:]
                sym = self.find_symbol(modules[prefix], rest[0])
                if sym and len(rest) == 1:
                    return self._target(sym)
                if sym and sym[0] == "class" and len(rest) == 2:
                    m = self.find_method(sym[1], rest[1])
                    if m:
                        return {"status": "resolved", "resolved": m}
                return {"status": "external", "resolved": None}
        # Class.method() for a class defined here or imported by name
        sym = self.find_symbol(file_id, head)
        if sym is None and head in symbols:
            sym = self.find_symbol(*symbols[head])
        if sym and sym[0] == "class" and len(chain) == 2:
            m = self.find_method(sym[1], chain[1])
            return {"status": "resolved", "resolved": m} if m else {"status": "external", "resolved": None}
        if head in symbols or head in modules:
            return {"status": "external", "resolved": None}   # known third-party/unresolvable import: not project code
        return self._by_name(last, func["id"])               # receiver is a local variable of unknown type


def resolve_all(model: dict) -> None:
    idx = Index(model)
    for f in model["functions"].values():
        for c in f.get("calls", []):
            c.update(idx.resolve(c, f))
