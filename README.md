# Ariadne demo

Proof-of-concept code diagram generator (see `Ariadne_Demo_Specification.md`).

## Status
| Part | Spec build-order items | State |
|---|---|---|
| 1 Backend: ingestion, raw model, Level 0/1 diagrams, Mermaid, API | 1-3 (+ source endpoint) | **done** |
| 2 Frontend viewer: home, canvas (pan/zoom/minimap), breadcrumbs, inspector, source panel, search, preferences, dark theme | 4-5 | **done (not yet run, see below)** |
| 3 Level 2: per-function flowcharts, call resolution, call-graph fallback | 6 | **done (extractor untested on real tree-sitter output, see below)** |
| 4 Comments, notes, tags, roll-up badges | 7 | |
| 5 Edit mode: amendments, plans, diff, undo/redo | 8 | |
| 6 Export/import, deep links, SVG/PNG | 9 | |
| 7 Update via diffs, orphans | 10 | |
| 8 Polish against the references | 11 | |

## Run
```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests                               # or: python tests/test_levels.py
python -m app.cli load-examples                      # analyze bundled examples (no network)
python -m app.cli analyze .. ariadne                 # analyze any local folder, here Ariadne itself -> #/repo/local/ariadne/L0
cd ../frontend && npm install && cd ..               # once
python run.py                                        # API :8000 (docs at /docs) + app at http://localhost:5173
```
In the app: open an example from the repository grid, double-click a component to dive in, press Ctrl/Cmd+K to search.
API only: `GET /api/repos/examples/todo_api/diagram/L0`.

Production-style: `cd frontend && npm run build`; the backend then serves `frontend/dist` itself on :8000.
`npm run typecheck` runs the TypeScript checker.

## Design decisions to know about
* **Diagrams are built on demand** from the stored raw model plus the node ceiling, so changing the ceiling never needs a re-ingest. `model.json` holds only the parsed model and commit id.
* **Mermaid is emitted by the backend** (`app/mermaid.py`) so exports are byte-for-byte deterministic. Edit-mode drafts will be applied server-side too (Part 5) so there is one implementation.
* **Ids** (`app/ids.py`): stable qualified ids for annotations; Mermaid ids are a readable slug plus a short hash of the stable id.
* `GET /api/repos/{o}/{r}/element/{id}` returns the roll-up chain (class -> file -> component -> parent) for comment badges.

## Frontend map (Part 2)
* `src/App.tsx`: hash routing (`#/repo/<owner>/<repo>/<diagramId>`), preferences, help.
* `src/components/Canvas.tsx`: pan/zoom, minimap, hover actions. Interactivity is attached to the rendered SVG by stable id using the `idMap` the API returns (spec section 3), never Mermaid click directives.
* `src/components/RepoView.tsx`: loads a diagram, renders Mermaid, owns selection, group expansion and focus-from-search.
* `src/components/Search.tsx`: MiniSearch over `/search-index`; filters for type, tag and scope.
* `src/mermaidRender.ts`: Mermaid config (strict sanitizer, raised size and edge limits, light/dark).
* Expand-in-place groups call the same diagram endpoint with `?expanded=<group ids>`.

## Level 2 (Part 3)
* Reached from a method in a UML diagram, from a function in a file's inspector panel, from a call node in another flowchart, or from search.
* `flow:<function id>` is the flowchart; if it would exceed your node ceiling, or the function has constructs that cannot be charted (nested defs, `yield`, syntax errors), the same id shows the **call graph** instead and says why. `calls:<function id>` always shows the call graph (callers and callees, two hops, one hop if that is over the ceiling).
* Extraction is `flow_extract.py`; call resolution is `calls.py` (imports, aliases, `self.method()`, `self.attr.method()`, `Class.method()`, constructors, simple re-exports). Unresolved calls that plausibly hit project code (unknown receiver with a unique or ambiguous method name, callbacks, `getattr(...)()`) are drawn dashed. Very common builtin method names (`append`, `get`, ...) are ignored on purpose.
* Edge-case styling (except blocks, raises, guard-clause early exits) is a heuristic overlay on the SVG, not part of exported Mermaid.
* Tests never get flowcharts (spec 5.5).
* Debugging: `python -m app.cli flow <owner> <repo> <text>` prints the extracted step tree and each call's resolution for functions whose id contains `<text>`. Flowcharts are built per request, so a ceiling change takes effect immediately.
