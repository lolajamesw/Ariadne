"""Per-function control-flow extraction from tree-sitter nodes (spec 5.4).

Output stored on each function record:
  params : parameter names (callback detection)
  calls  : every call in evaluation order  [{text, chain, line, hidden}]  (resolved later by calls.py)
  flow   : {"steps": [...], "unsupported": [reasons]}   -- structured tree, charted by flows.py

Only branches, calls, returns and raises become steps; plain statements collapse away.
Comprehensions, lambdas and generator expressions become single `expr` steps.
Step ids are position paths (e.g. "2.t.1" = third statement, then-branch, second statement) so they stay
stable when unrelated code elsewhere in the function changes.
"""
from __future__ import annotations
import re

LAMBDA_LIKE = {"lambda", "list_comprehension", "set_comprehension", "dictionary_comprehension", "generator_expression"}
NESTED_DEF = {"function_definition", "class_definition", "decorated_definition"}
MAX_TEXT = 48


def _t(node) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None else ""


def short(s: str, n: int = MAX_TEXT) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _line(node) -> int:
    return node.start_point[0] + 1


class Extractor:
    def __init__(self, fn_node):
        self.fn = fn_node
        self.calls: list[dict] = []
        self.unsupported: set[str] = set()
        self._sink: list[tuple] = []

    # ---------------------------------------------------------------- expressions
    def chain_of(self, node) -> list[str]:
        if node is None:
            return ["?"]
        if node.type == "identifier":
            return [_t(node)]
        if node.type == "attribute":
            obj = node.child_by_field_name("object")
            attr = node.child_by_field_name("attribute")
            base = self.chain_of(obj)
            if obj is not None and obj.type == "call":
                f = obj.child_by_field_name("function")
                if f is not None and _t(f) == "super":
                    base = ["super"]
            return base + [_t(attr)]
        return ["?"]

    def scan(self, node, hidden: bool = False):
        """Collect calls in evaluation order. Calls inside lambdas/comprehensions are recorded as hidden
        (kept for the call graph) and surface as one `expr` step."""
        if node is None:
            return
        t = node.type
        if t in NESTED_DEF:
            self.unsupported.add("nested definition")
            return
        if t == "yield":
            self.unsupported.add("generator (yield)")
        if t in LAMBDA_LIKE:
            before = len(self.calls)
            for ch in node.children:
                self.scan(ch, True)
            if len(self.calls) > before and not hidden:
                self._sink.append(("expr", t, short(_t(node)), _line(node)))
            return
        if t == "call":
            fn = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            if fn is not None and fn.type == "attribute":
                self.scan(fn.child_by_field_name("object"), hidden)
            elif fn is not None and fn.type != "identifier":
                self.scan(fn, hidden)
            self.scan(args, hidden)
            chain = self.chain_of(fn)
            idx = len(self.calls)
            self.calls.append({"text": ".".join(chain) if "?" not in chain else short(_t(fn)),
                               "chain": chain, "line": _line(node), "hidden": hidden})
            if not hidden:
                self._sink.append(("call", idx, _line(node)))
            return
        for ch in node.children:
            self.scan(ch, hidden)

    def steps_from(self, node, pid: str) -> list[dict]:
        self._sink = []
        self.scan(node)
        out = []
        for j, item in enumerate(self._sink):
            if item[0] == "call":
                out.append({"t": "call", "id": f"{pid}.c{j}", "ci": item[1], "line": item[2]})
            else:
                out.append({"t": "expr", "id": f"{pid}.c{j}", "kind": item[1], "text": item[2], "line": item[3]})
        return out

    # ---------------------------------------------------------------- statements
    def block(self, node, pid: str) -> list[dict]:
        steps: list[dict] = []
        if node is None:
            return steps
        for i, st in enumerate(node.named_children):
            steps.extend(self.stmt(st, f"{pid}{i}"))
        return steps

    def first_named(self, node):
        return node.named_children[0] if node is not None and node.named_children else None

    def stmt(self, st, p: str) -> list[dict]:
        t = st.type
        if t == "comment":
            return []
        if t == "return_statement":
            e = self.first_named(st)
            return self.steps_from(e, p) + [{"t": "return", "id": p, "expr": short(_t(e)), "line": _line(st)}]
        if t == "raise_statement":
            e = self.first_named(st)
            return self.steps_from(e, p) + [{"t": "raise", "id": p, "expr": short(_t(e)), "line": _line(st)}]
        if t in ("break_statement", "continue_statement"):
            return [{"t": t.split("_")[0], "id": p, "line": _line(st)}]
        if t == "if_statement":
            return self.if_step(st, p)
        if t in ("for_statement", "while_statement"):
            return self.loop_step(st, p)
        if t == "try_statement":
            return self.try_step(st, p)
        if t == "with_statement":
            pre: list[dict] = []
            for ch in st.children:
                if ch.type == "with_clause":
                    pre = self.steps_from(ch, p + ".k")
            return pre + self.block(st.child_by_field_name("body"), p + ".w.")
        if t == "match_statement":
            return self.match_step(st, p)
        if t in NESTED_DEF:
            self.unsupported.add("nested definition")
            return []
        if t in ("pass_statement", "global_statement", "nonlocal_statement", "import_statement",
                 "import_from_statement", "future_import_statement"):
            return []
        return self.steps_from(st, p)   # expression_statement, assert, delete, ...

    def if_step(self, st, p: str) -> list[dict]:
        cond = st.child_by_field_name("condition")
        pre = self.steps_from(cond, p + ".k")
        then = self.block(st.child_by_field_name("consequence"), p + ".t.")
        alts = st.children_by_field_name("alternative")
        return pre + [{"t": "if", "id": p, "cond": short(_t(cond)), "line": _line(st), "then": then,
                       "else": self.alt_chain(alts, p)}]

    def alt_chain(self, alts, p: str) -> list[dict]:
        if not alts:
            return []
        first, rest = alts[0], alts[1:]
        if first.type == "elif_clause":
            q = p + ".e"
            cond = first.child_by_field_name("condition")
            pre = self.steps_from(cond, q + ".k")
            then = self.block(first.child_by_field_name("consequence"), q + ".t.")
            return pre + [{"t": "if", "id": q, "cond": short(_t(cond)), "line": _line(first), "then": then,
                           "else": self.alt_chain(rest, q)}]
        return self.block(first.child_by_field_name("body"), p + ".e.")

    def loop_step(self, st, p: str) -> list[dict]:
        is_for = st.type == "for_statement"
        header = st.child_by_field_name("right" if is_for else "condition")
        pre = self.steps_from(header, p + ".k")
        if is_for:
            cond = f"for {short(_t(st.child_by_field_name('left')), 20)} in {short(_t(header), 28)}"
        else:
            cond = f"while {short(_t(header))}"
        orelse = []
        alt = st.child_by_field_name("alternative")
        if alt is not None:
            orelse = self.block(alt.child_by_field_name("body"), p + ".o.")
        return pre + [{"t": "loop", "id": p, "kind": "for" if is_for else "while", "cond": short(cond, 56),
                       "line": _line(st), "body": self.block(st.child_by_field_name("body"), p + ".b."), "else": orelse}]

    def try_step(self, st, p: str) -> list[dict]:
        handlers, orelse, final = [], [], []
        for i, ch in enumerate(st.named_children):
            if ch.type in ("except_clause", "except_group_clause"):
                kids = [c for c in ch.named_children if c.type != "block"]
                exc = re.split(r"\s+as\s+", _t(kids[0]))[0] if kids else ""
                blk = next((c for c in ch.named_children if c.type == "block"), None)
                handlers.append({"exc": short(exc, 32), "line": _line(ch), "id": f"{p}.h{len(handlers)}",
                                 "body": self.block(blk, f"{p}.h{len(handlers)}.")})
            elif ch.type == "else_clause":
                orelse = self.block(ch.child_by_field_name("body"), p + ".o.")
            elif ch.type == "finally_clause":
                blk = next((c for c in ch.named_children if c.type == "block"), None) or ch
                final = self.block(blk, p + ".f.")
        return [{"t": "try", "id": p, "line": _line(st), "body": self.block(st.child_by_field_name("body"), p + ".b."),
                 "handlers": handlers, "else": orelse, "finally": final}]

    def match_step(self, st, p: str) -> list[dict]:
        subject = st.child_by_field_name("subject")
        pre = self.steps_from(subject, p + ".k")
        cases = []
        body = st.child_by_field_name("body")
        for i, c in enumerate(body.named_children if body is not None else []):
            if c.type != "case_clause":
                continue
            pat = next((x for x in c.named_children if x.type == "case_pattern"), None)
            cases.append({"pat": short(_t(pat), 28), "body": self.block(c.child_by_field_name("consequence"), f"{p}.m{i}.")})
        return pre + [{"t": "match", "id": p, "subject": short(_t(subject), 28), "line": _line(st), "cases": cases}]

    # ---------------------------------------------------------------- entry
    def params(self) -> list[str]:
        out: list[str] = []
        ps = self.fn.child_by_field_name("parameters")
        for p in (ps.named_children if ps is not None else []):
            if p.type == "identifier":
                out.append(_t(p))
            elif p.type in ("default_parameter", "typed_default_parameter"):
                n = p.child_by_field_name("name")
                if n is not None:
                    out.append(_t(n))
            else:
                ident = next((c for c in p.named_children if c.type == "identifier"), None)
                if ident is not None:
                    out.append(_t(ident))
        return out

    def run(self) -> dict:
        if self.fn.has_error:
            self.unsupported.add("syntax error in function")
        steps = self.block(self.fn.child_by_field_name("body"), "")
        return {"params": self.params(), "calls": self.calls,
                "flow": {"steps": steps, "unsupported": sorted(self.unsupported)}}


def extract(fn_node, source: bytes, ctx: dict) -> dict:
    """FLOW_HOOK for analyzer.parse_python_file. Failures degrade to the call-graph fallback, never crash ingestion."""
    from .analyzer import is_test_path   # lazy: analyzer imports this module
    if is_test_path(ctx["path"]):
        return {}                         # spec 5.5: no flowcharts for tests
    try:
        return Extractor(fn_node).run()
    except Exception as e:  # noqa: BLE001
        return {"params": [], "calls": [], "flow": {"steps": [], "unsupported": [f"extraction error: {type(e).__name__}"]}}
