import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, enc } from '../api';
import { renderMermaid } from '../mermaidRender';
import type { DiagramResponse } from '../types';
import Canvas, { CanvasHandle, NodeAction } from './Canvas';
import Inspector from './Inspector';
import SourceModal from './SourceModal';

type Props = {
  owner: string; repo: string; diagramId: string; dark: boolean; ceilingVersion: number;
  focus: { id: string; nonce: number } | null;
  onNavigate: (diagramId: string) => void; onHome: () => void; onDiagram: (id: string) => void;
};
type Src = { path: string; start?: number; end?: number } | null;

export default function RepoView({ owner, repo, diagramId, dark, ceilingVersion, focus, onNavigate, onHome, onDiagram }: Props) {
  const [data, setData] = useState<DiagramResponse | null>(null);
  const [svg, setSvg] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [focusNonce, setFocusNonce] = useState(0);
  const [resetCount, setResetCount] = useState(0);
  const [source, setSource] = useState<Src>(null);
  const canvas = useRef<CanvasHandle>(null);
  const req = useRef(0);
  const expandedKey = [...expanded].sort().join(',');

  useEffect(() => { onDiagram(diagramId); }, [diagramId]);

  useEffect(() => {
    const my = ++req.current;
    setLoading(true); setError('');
    (async () => {
      try {
        const qs = expandedKey ? `?expanded=${enc(expandedKey)}` : '';
        const r = await api<DiagramResponse>(`/repos/${enc(owner)}/${enc(repo)}/diagram/${enc(diagramId)}${qs}`);
        const out = await renderMermaid(r.mermaid, dark ? 'dark' : 'light');
        if (my !== req.current) return;
        setData(r); setSvg(out); setLoading(false);
      } catch (e) {
        if (my !== req.current) return;
        if (e instanceof ApiError && e.status === 404 && diagramId !== 'L0') { onNavigate('L0'); return; }
        setError((e as Error).message); setLoading(false);
      }
    })();
  }, [owner, repo, diagramId, expandedKey, dark, ceilingVersion]);

  // Search / deep-link focus: expand a collapsed group that contains the target, then center + highlight it.
  useEffect(() => {
    if (!focus || !data) return;
    const g = data.diagram.groups.find((x) => x.members.includes(focus.id));
    if (g && !expanded.has(g.id)) { setExpanded((s) => new Set(s).add(g.id)); return; }
    setHighlight(focus.id); setSelected(focus.id); setFocusNonce((n) => n + 1);
  }, [focus?.nonce, data]);

  const toggleGroup = useCallback((id: string) => setExpanded((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; }), []);

  const nodeById = (id: string) => data?.diagram.nodes.find((n) => n.id === id);
  const actionsFor = (id: string): NodeAction[] => {
    if (!data) return [];
    const g = data.diagram.groups.find((x) => x.id === id);
    if (g) return [{ label: expanded.has(id) ? 'Collapse group' : 'Expand group', run: () => toggleGroup(id) }];
    const n = nodeById(id);
    if (!n) return [];
    const details: NodeAction = { label: 'Details', run: () => setSelected(id) };
    const acts: NodeAction[] = [details];
    if (n.drill && n.drill !== diagramId) acts.push({ label: n.type === 'function' || n.type === 'step' ? 'Open flowchart' : 'Dive in', run: () => onNavigate(n.drill!) });
    if (n.type !== 'component' && n.path) acts.push({ label: 'View source', run: () => setSource({ path: n.path!, start: n.meta?.line, end: n.meta?.endLine }) });
    return acts;
  };
  const open = (id: string) => {
    const g = data?.diagram.groups.find((x) => x.id === id);
    if (g) return toggleGroup(id);
    const n = nodeById(id);
    if (!n) return;
    if (n.drill && n.drill !== diagramId) onNavigate(n.drill);
    else if (n.path) setSource({ path: n.path, start: n.meta?.line, end: n.meta?.endLine });
  };

  const d = data?.diagram;
  const unit = d?.kind === 'uml' ? 'classes' : d?.kind === 'flowchart' ? 'steps' : d?.kind === 'callgraph' ? 'functions' : d?.kind === 'filemap' || d?.kind === 'filelist' ? 'files' : 'components';

  return (
    <div className="repo-view">
      <header className="repo-header">
        <button className="btn" onClick={onHome}>← Back</button>
        <div className="repo-title">
          <div className="muted small">{owner}/{repo}{data?.meta && <span className="branch"> ⎇ {data.meta.branch}{data.meta.commit !== 'local' ? ` @ ${data.meta.commit.slice(0, 7)}` : ''}</span>}</div>
          <h2>{d ? d.title : 'Loading…'}{d && <span className="chip kind">{d.kind === 'overview' ? 'System overview' : d.kind}</span>}</h2>
        </div>
        <button className="btn" onClick={() => { setResetCount((c) => c + 1); setExpanded(new Set()); setSelected(null); setHighlight(null); }}>Reset view</button>
      </header>
      <div className="crumbs">
        {data?.breadcrumb.map((c, i, arr) => (
          <span key={c.id}>
            {i === arr.length - 1 ? <strong>{c.label}</strong> : <button className="crumb" onClick={() => onNavigate(c.id)}>{c.label}</button>}
            {i < arr.length - 1 && <span className="sep"> › </span>}
          </span>
        ))}
      </div>
      <div className="workspace">
        <div className="canvas-wrap">
          {error && <div className="error banner">{error}</div>}
          {loading && <div className="loading">Drawing…</div>}
          {data && (
            <Canvas ref={canvas} svg={svg} idMap={data.idMap} selectedId={selected} highlightId={highlight} nodeClasses={data.classes ?? {}} focusNonce={focusNonce}
                    fitKey={`${diagramId}#${resetCount}`} onSelect={setSelected} onOpen={open} actionsFor={actionsFor} />
          )}
          {d && (
            <div className="statusbar">
              <span>{d.nodes.length} {unit} · {d.edges.length} connections{d.groups.length ? ` · ${d.groups.length} groups` : ''}</span>
              <span className="muted">Double-click to dive in · Ctrl/⌘ + scroll to zoom · drag to pan</span>
            </div>
          )}
        </div>
        {data && <Inspector owner={owner} repo={repo} data={data} selectedId={selected} expanded={expanded}
                            onDive={onNavigate} onSource={(path, start, end) => setSource({ path, start, end })}
                            onToggleGroup={toggleGroup} onSelect={setSelected} />}
      </div>
      {source && <SourceModal owner={owner} repo={repo} dark={dark} {...source} onClose={() => setSource(null)} />}
    </div>
  );
}
