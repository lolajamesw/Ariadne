# Ariadne demo

Proof-of-concept code diagram generator (see `Ariadne_Demo_Specification.md`).

## Status
| Part | Spec build-order items | State |
|---|---|---|
| 1 Backend: ingestion, raw model, Level 0/1 diagrams, Mermaid, API | 1-3 (+ source endpoint) | **done** |
| 2 Frontend viewer: canvas, breadcrumbs, inspector, source panel, search | 4-5 | next |
| 3 Level 2: flowcharts + call graph (fills `analyzer.FLOW_HOOK`) | 6 | |
| 4 Comments, notes, tags, roll-up badges | 7 | |
| 5 Edit mode: amendments, plans, diff, undo/redo | 8 | |
| 6 Export/import, deep links, SVG/PNG | 9 | |
| 7 Update via diffs, orphans | 10 | |
| 8 Dark mode and polish | 11 | |

## Run (Part 1)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests                               # or: python tests/test_levels.py
python -m app.cli load-examples                      # analyze bundled examples (no network)
cd .. && python run.py                               # API at http://localhost:8000/docs
```
Then try `GET /api/repos`, `GET /api/repos/examples/todo_api/diagram/L0`.

## Design decisions to know about
* **Diagrams are built on demand** from the stored raw model plus the node ceiling, so changing the ceiling never needs a re-ingest. `model.json` holds only the parsed model and commit id.
* **Mermaid is emitted by the backend** (`app/mermaid.py`) so exports are byte-for-byte deterministic. Edit-mode drafts will be applied server-side too (Part 5) so there is one implementation.
* **Ids** (`app/ids.py`): stable qualified ids for annotations; Mermaid ids are a readable slug plus a short hash of the stable id.
* `GET /api/repos/{o}/{r}/element/{id}` returns the roll-up chain (class -> file -> component -> parent) for comment badges.
