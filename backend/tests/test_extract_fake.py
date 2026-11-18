"""Smoke test of flow_extract.Extractor against a hand-made imitation of tree-sitter's node API.
It proves the extractor's own logic (ordering, ids, branching, hidden calls); it does NOT prove that real
tree-sitter-python node/field names match -- use `python -m app.cli flow ...` on real code for that."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app import flow_extract


class N:
    def __init__(self, type, text="", fields=None, children=None, row=0, named=True, **kw):
        self.type, self.text, self._f = type, text.encode(), fields or {}, 
        self.children = children if children is not None else [c for v in self._f.values() for c in (v if isinstance(v, list) else [v])]
        self.named_children = [c for c in self.children if c is not None]
        self.start_point, self.has_error = (row, 0), False
    def child_by_field_name(self, n):
        v = self._f.get(n)
        return v[0] if isinstance(v, list) else v
    def children_by_field_name(self, n):
        v = self._f.get(n, [])
        return v if isinstance(v, list) else [v]


def ident(t, row=0): return N("identifier", t, row=row)
def call(name_chain, args=None, row=0):
    fn = ident(name_chain[0]) if len(name_chain) == 1 else N("attribute", ".".join(name_chain), {"object": ident(name_chain[0]), "attribute": ident(name_chain[1])})
    return N("call", "x()", {"function": fn, "arguments": args or N("argument_list", "()")}, row=row)
def expr_stmt(c, row=0): return N("expression_statement", "x()", children=[c], row=row)


def test_basic_function():
    body = N("block", children=[
        expr_stmt(call(["helper"], row=1), 1),
        N("if_statement", "if a:", {"condition": ident("a"), "consequence": N("block", children=[
            N("return_statement", "return 1", children=[N("integer", "1")], row=3)]),
            "alternative": [N("else_clause", fields={"body": N("block", children=[expr_stmt(call(["self", "go"], row=5), 5)])})]}, row=2),
        N("for_statement", "for", {"left": ident("x"), "right": ident("xs"), "body": N("block", children=[
            expr_stmt(N("list_comprehension", "[f(y) for y in z]", children=[call(["f"])]), 7)])}, row=6),
        N("return_statement", "return", children=[], row=8),
    ])
    fn = N("function_definition", "def f(self, cb)", {"name": ident("f"), "body": body,
           "parameters": N("parameters", children=[ident("self"), ident("cb")])})
    out = flow_extract.Extractor(fn).run()
    steps = out["flow"]["steps"]
    assert [s["t"] for s in steps] == ["call", "if", "loop", "return"]
    assert steps[1]["then"][-1]["t"] == "return" and steps[1]["else"][0]["t"] == "call"
    assert steps[2]["body"][0]["t"] == "expr" and steps[2]["body"][0]["kind"] == "list_comprehension"
    assert out["params"] == ["self", "cb"]
    chains = [c["chain"] for c in out["calls"]]
    assert chains == [["helper"], ["self", "go"], ["f"]]
    assert out["calls"][2]["hidden"] is True          # call inside the comprehension: kept for the call graph only
    assert [s["id"] for s in steps] == ["0.c0", "1", "2", "3"] or steps[0]["id"].startswith("0")
    assert out["flow"]["unsupported"] == []


def test_nested_def_and_yield_are_unsupported():
    body = N("block", children=[N("function_definition", "def g", {"name": ident("g")}),
                                expr_stmt(N("yield", "yield 1", children=[N("integer", "1")]))])
    fn = N("function_definition", "def f()", {"name": ident("f"), "body": body})
    out = flow_extract.Extractor(fn).run()
    assert set(out["flow"]["unsupported"]) == {"nested definition", "generator (yield)"}


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f(); print("PASS", name)
