# Code Diagram Generator: Demo Specification

Implementation spec for a local-web-app proof of concept. Working product name in the UI references: Ariadne. Status: requirements settled, ready to build. Written 17 Nov 2026.

## 1. Purpose and success criteria

The demo parses a public GitHub repository (Python only) into an internal model and renders it as navigable, layered Mermaid diagrams that help someone understand unfamiliar code. Collaboration features (comments, amendments, plans) are what give the generated diagrams lasting value, so they are a first-class part of the demo, not an add-on.

The demo exists to collect feedback on ease of use and points of tension. Testing is done in person and the team records observations manually, so there is no in-app feedback button or action logging. Feedback is also expected to arrive as comments inside the app.

The demo is a proof of concept for a future website that reads from a company or group's repos (permissions are a later concern), and eventually stores diagrams in the repos themselves so Mermaid can be viewed directly in a code editor.

## 2. Scope at a glance

**In the demo:** repo ingestion by GitHub URL; Python analysis with tree-sitter; the diagram hierarchy in section 5; edit mode with amendments and plans; comments, notes and tags; search; breadcrumbs; Mermaid, SVG and PNG export; deep links; export and import of annotations and drafts; update via diffs; light and dark themes.

**Deferred (section 14):** walkthroughs, sticky notes, plan promotion, real-time collaboration, user identity, other languages, private repos.

## 3. Architecture and stack

- **Backend:** Python with FastAPI. Parsing uses the tree-sitter Python bindings with the Python grammar.
- **Frontend:** React, TypeScript and Vite. Diagrams render with Mermaid.js inside a pan and zoom canvas.
- **Run:** one command starts both. Document it in the README.
- **Storage:** JSON files under a data folder (section 11).
- **Search index:** built client-side from the model and annotations (MiniSearch or Fuse.js).
- **Mermaid settings:** raise the maximum text size and edge limits well above the defaults. Interactivity (click, hover, badges, highlights) is attached to the rendered SVG by node id, not through Mermaid click directives.

## 4. Repo ingestion

**Home screen:** a GitHub URL field (github.com / owner / repository) with an Explore button, a note that only public repos are supported, and a card grid of previously opened repos (name, owner, language, file count, component count, last opened, small diagram thumbnail). Include two or three bundled example repos. Sort, filter and grid or list toggle as in the light reference.

**Flow:**

1. Validate the URL and fetch metadata from the GitHub API: size, default branch, latest commit id.
2. If the repo is large (default threshold 100 MB, configurable), show a warning with the size and a rough time estimate, with Confirm and Cancel buttons.
3. Run `git clone --depth 1` with no file filtering. Role detection at Level 0 needs context files such as Dockerfile, docker-compose, requirements, pyproject and terraform.
4. Scan, parse, build the model, build the diagrams.
5. Show staged progress: Downloading, Scanning files, Parsing, Building diagrams. A Cancel button must work at every stage and clean up partial work.

**Guards:** ignore `.git`, `venv`, `.venv`, `__pycache__`, `node_modules`. Skip files over about 1 MB, minified or generated files. Cap analyzed files at about 5,000 with a clear message when hit.

**What is stored:** only the parsed model and the latest analyzed commit id, not the source. When source is needed (code panel), fetch it on demand from GitHub at the stored commit.

## 5. Internal model and diagram hierarchy

### 5.1 Raw model

Built from tree-sitter. It holds directories, files, imports, classes (attributes from `__init__` assignments and annotations, methods, base classes, composition via attributes typed as project classes), functions and methods (calls, branches), and detected config files. Every item has a **stable id**, a qualified path such as `file:api/routes/users.py` or `func:api/routes/users.py::create_user`. Annotations and drafts attach to these ids.

### 5.2 Level 0: System Overview

One diagram for the repo. A node is a logical component. Detection is a hybrid: directories by default (descend through single-child wrapper folders such as `src` or `packages`), with role-tag labels layered on top using heuristics on names and dependencies (frontend, backend, api, auth, db, infra, and so on). Loose root files group into a root or config node. Users can rename and re-tag components in edit mode. Edges are aggregated imports between components, labeled with counts.

Tests get their own node (see 5.5).

### 5.3 Level 1: inside a component

Every component has a file map. A component with at least one class also has a UML class diagram. Double-click opens UML when it exists, otherwise the file map, and both are reachable from the node (node menu or inspector). Non-Python components show a plain file list labeled not analyzed, with no edges.

- **File map:** a node per file. An edge exists when one file imports another (imports only in the demo).
- **UML:** Mermaid classDiagram with attributes, methods, inheritance and composition.

**Recursive splitting.** Large components split into sub-components first:

1. No nested directories: stop and render.
2. Estimated node count of the next diagram at or under the node ceiling: stop.
3. Otherwise split into one sub-component per child directory, with loose files grouped into an other node, then repeat for each.
4. Flat folder over the ceiling: stop splitting and show collapsed groups (for example by filename prefix) that expand in place.

The **node ceiling** is a user setting from 5 to 50, default 20, and applies to every diagram level. It is a per-user view setting, not shared project data.

### 5.4 Level 2: control flow

Reached by clicking a method in a UML diagram, or a function listed in a file's detail panel.

- **Primary (flowchart per function):** only branches, calls to project code, returns and raises are charted; plain statements collapse away. Decisions come from if and elif, loops, try and except, match. Calls resolve through imports and `self.method()`. Resolved calls link to the callee's own flowchart. Unresolved calls (callbacks, getattr, wrapping decorators) are drawn dashed so users can fix them in edit mode. Comprehensions, lambdas and generators are single nodes.
- **Edge-case tagging (heuristic):** except blocks, guard-clause early returns and raise paths are styled as edge cases. Everything else is the main path. The labeling is visibly heuristic and editable.
- **Fallback (call graph):** if a function's flowchart would exceed the node ceiling or hits constructs the parser cannot chart, show a call graph around the function (callers and callees, one or two hops).

### 5.5 Tests

Tests have their own Level 0 node. It opens a test-specific overview diagram, which may break into file maps. Nothing else for now: no UML and no flowcharts for tests.

### 5.6 Linking to source

Where a node maps to code, offer two links: an in-app read-only code panel with syntax highlighting, and an open-on-GitHub link at the stored commit with the line range.

## 6. Mermaid output

- Level 0, file maps and function flowcharts use `flowchart`. UML uses `classDiagram`. Call graphs use `flowchart LR`.
- The effective model (generated model plus amendments, or a selected plan) can be exported as Mermaid code. Output must be **deterministic and diff-friendly** (stable ordering, no random ids), because it will eventually be stored in repos.
- Comment badges, the diagram-level comment node, highlights and plan styling are overlays added to the rendered SVG. Only structure goes into the exported Mermaid.
- Also export SVG and PNG.

## 7. Edit mode, amendments and plans

Edit mode is entered from any diagram. On entering, the user picks a sub-mode.

|  | Amendment | Plan |
| --- | --- | --- |
| Purpose | Correct or enrich how the diagram describes the code as it is now | Describe a future or proposed state |
| Stored | Separately, as an overlay | Separately, as an overlay, one file per plan |
| Shown | Merged into the base diagram for everyone, as if part of it | Only when the plan is selected in a view switcher |
| Styling | None (looks like the base) | Planned additions styled distinctly (dashed or colored) |
| Reversible | Each amendment can be reverted (reset to generated) | Delete or edit the plan |

The generated model is never rewritten by users. Multiple amendments apply in creation order.

**Operations** (recorded as overlay operations on stable ids): add node, remove node, edit node text, add link, remove link, edit link label or type, re-tag or rename a component, merge nodes, split node, resolve an unresolved call, mark a path as edge case or main path.

- **Merge:** one node with a combined label and the union of the edges, with the original members listed inside it.
- **Split:** the user creates two nodes and assigns the original's edges and members between them, linked back to the source node.

**Scope and leaving a diagram.** A draft is scoped to one diagram. When the user navigates away from a diagram with unsaved edits, a popup offers: save, expand the draft's scope to include the other diagrams, or discard. A remember-my-choice option sets a default, changeable in Settings.

**Undo and redo** within a session: Ctrl+Z and Ctrl+Y.

**Diff view:** compare a plan to the current diagram, with added, removed and changed elements highlighted.

Every diagram can be switched between Current and any plan from the same control.

## 8. Comments, notes and tags

- **Comments:** attach to a node, a link, or the diagram as a whole. Threads with replies; resolve and reopen. A diagram-level comment is a small disconnected comment node placed apart from the graph. Open-comment counts roll up as badges to parent nodes at higher levels, so unresolved discussion is visible from the overview. Filter by open or resolved.
- **Scoping:** comments written while a plan is active belong to that plan and do not appear outside it, because they may discuss changes that do not exist in the base. Comments written otherwise (including in amendment mode) are global and visible in the base and in plans.
- **Notes:** persistent documentation on a node, distinct from threads. A note follows the element it is attached to.
- **Tags:** free-text chips on nodes (for example deprecated, needs refactor), with a few presets.
- **No identity in the demo:** users share one computer, so comments carry timestamps but no author.
- **Node panel:** an inspector panel on the right shows details, tags, notes, comments, source links, and Open UML and Open file map actions.

## 9. Search and navigation

- **Search box:** persistent and always visible (top bar or top of the sidebar, matching the references). Fuzzy search over names and paths (components, files, classes, functions) plus annotations (comments, notes, tags). It searches the active plan's version of the model when one is selected.
- **Results dropdown** shows a type icon, the name, and the route the app will take (for example: Overview, api, routes, users.py, create\_user in UML).
- **On selecting a result:** navigate to the deepest diagram where the item appears as a node, center and highlight it, and expand any collapsed group containing it.
- **Filters:** type, tag, has open comments, and a scope switch between this diagram and the whole repo.
- **Breadcrumbs** across the top show the path from the overview and are clickable. There are no back and forward buttons and no go-up shortcut.
- Double-click a node to dive in.

## 10. Updating a repo

An Update button fetches the latest commit id. If unchanged, do nothing. Otherwise use GitHub's compare endpoint between the stored and latest commits to get the changed files, re-fetch the latest snapshot, re-parse changed files (plus files that import them, to refresh edges) and update the model. Fall back to a full re-parse if the compare fails, the change is very large, or history was rewritten.

**Orphans:** any amendment or plan operation, comment, note or tag that points at an id that no longer exists is marked orphaned and listed in an Orphaned items view. Everything that is not orphaned must persist exactly as before, as if nothing happened. Renames count as a remove plus an add in the demo.

## 11. Persistence and export

JSON files, one folder per repo, for example `data/owner__repo/`:

- `model.json` (parsed model and latest commit id)
- `amendments.json`
- `plans/<planId>.json`
- `comments.json`, `notes.json`
- `data/settings.json` (global): node ceiling, leave-diagram behavior, theme

Export and import a bundle of annotations and drafts (not the model) as a file, to stand in for sharing in a local demo. Deep links point at a specific diagram, node, or plan.

## 12. UI direction

Three references, ranked by the team. Follow them in this order of priority.

1. **Light-mode recording (highest priority).** Left sidebar (Repositories with count, Recently viewed, an intro card, Help and documentation, Preferences). Home screen with the hero line, the Start with a repository card and the repository grid. Repo view has a back button, owner and repo name, branch label, title with a System overview subtitle, a Reset view button, a dotted canvas with component cards (name, path, Expand component button), groups that expand in place with a Collapse group action, a right-hand Component inspector listing files, and a Source file modal showing read-only code.
2. **Figma Make link (second).** https://www.figma.com/make/6I4fMO3sx2HCVUgzcbpsSU/Website-for-Code-Diagram-Generator?t=Hd9nmXpa5MSqCrAX-1 . Described here from a screenshot of the Ariadne workspace page: a narrow icon rail and a left sidebar with a project search box (Ctrl or Cmd plus K), workspace navigation and a list of diagram views with counts by type; a top bar with a breadcrumb, a Saved indicator and a download button; a page header with the diagram title, a diagram-type chip and a branch selector (main); an Exploration path row showing the diagrams visited so far; a toolbar with an Edit diagram toggle, select and pan tools, zoom, undo and share, plus an inline Editing status with Discard and Save changes buttons; a canvas of component cards with comment and resolved badges, a groups count chip, dashed edges, a dashed external-services box, a diagram-type label and a minimap; and a right-hand Selected component panel with Details and Comments tabs (with a count), a type chip, Explore this component links (one per sub-diagram, for example a connection map and an implementation map), an editable description and a connections list.
3. **Dark-mode recording (third).** Top bar with logo and breadcrumb, Back and Step up buttons, title and subtitle, Diagram and list toggle, search, a New component button, a canvas with minimap and zoom controls, hover actions Details and Dive in, role-icon cards, grouped containers, a status line with component and connection counts, and a hint line (double-click to dive in, Ctrl or Cmd plus scroll to zoom).

**Theme:** light mode is the primary design. Provide a dark mode for every screen, since users like cleanliness and would appreciate dark versions of the higher-ranked designs.

**Mapping the references to this spec:**

- New component maps to add node in edit mode.
- Component inspector maps to the node panel in section 8.
- Source modal maps to the in-app code panel.
- Expand in place is used for collapsed groups. Normal drilling navigates to a new diagram.
- Minimap, zoom and fit controls are included on the canvas.
- Left out: login, avatar and organization views, the Ask Ariadne assistant, and the background, edge and node style pickers.
- Free dragging of nodes (shown in the references) is confirmed out of the demo, because Mermaid controls layout and does not support it. Use pan and zoom only; revisit later.

**Mapping the Figma screenshot (reference 2):**

- The Edit diagram toggle with the inline Editing status, Discard and Save changes is the model for edit mode and the leave-diagram save prompt in section 7.
- The Exploration path row is the breadcrumb trail in section 9.
- Explore this component links map to the Open UML and Open file map actions in the node panel.
- The Details and Comments tabs, with a comment count, map to the node panel in section 8. Comment and resolved badges on cards match the roll-up badges.
- The branch selector shows the analyzed branch and commit in the UI.
- Search sits at the top of the sidebar with a Ctrl or Cmd plus K shortcut. Section 9 only requires a persistent search box, so use this placement to match the references.
- Left out: the organization switcher, and the Documentation, Decisions and Overview pages. The sidebar list of diagram views by type could be reused for filtering by role tag, but that is not required.

## 13. Assumptions (confirmed)

These are interpretations made while writing the spec. The team confirmed all of them on 17 Nov 2026.

1. A component that splits into sub-components opens a sub-component overview first, and the file map and UML live on the leaf sub-components.
2. Expand scope means the same draft continues across the other diagrams the user visits. A discard option was added to the leave-diagram popup.
3. Notes follow their element. Comments are plan-scoped when written in a plan and global otherwise.
4. Amendments apply automatically to the displayed base and are individually revertable.
5. SVG and PNG export is in the demo.
6. Ctrl+Z and Ctrl+Y are undo and redo.
7. The size warning threshold defaults to 100 MB.
8. Source for the code panel is fetched from GitHub at the stored commit because the source itself is not stored.

## 14. Deferred and future

- Guided walkthroughs, bookmarks, understood marks, sticky notes (conflict with Mermaid auto-layout)
- Plan promotion, compare two plans, review and approval workflow, stale-plan detection, history
- Regroup nodes, manual layout hints and free dragging of nodes, @mentions, reactions, owners, external links on nodes
- Real-time co-editing, presence, notifications, roles and permissions, user identity
- Command palette, tree sidebar, in-diagram filter
- Other languages, API-call and database edges, per-file deep diagrams for non-object-oriented resources (tables with keys, APIs mapped to code, terraform), sequence diagrams, test-specific diagrams beyond file maps
- Private repos and company repo permissions, storage inside repos, Mermaid viewable in code editors, rename-aware updates

## 15. Suggested build order

1. Project skeleton, GitHub ingestion with size check, progress and cancel.
2. Raw model with tree-sitter and stable ids.
3. Level 0 with role tags, file maps and UML, plus the node ceiling and recursive splitting.
4. Viewer: canvas, breadcrumbs, double-click navigation, inspector, source panel.
5. Search with filters.
6. Function flowcharts with call graph fallback.
7. Comments, notes and tags with roll-up badges.
8. Edit mode: overlays, amendments, plans, diff, undo and redo, leave-diagram popup.
9. Export and import, deep links, Mermaid, SVG and PNG export.
10. Update via diffs and orphan handling.
11. Dark mode and polish against the references.

Test against at least three repos: a small Flask or FastAPI app, a mid-sized Python library, and a repo with tests, a Dockerfile and infrastructure files.
