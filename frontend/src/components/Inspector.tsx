import { useEffect, useState } from 'react';
import { api, enc } from '../api';
import type { ComponentDetail, DGroup, DNode, DiagramResponse, FileFunctions } from '../types';

type Props = {
  owner: string; repo: string; data: DiagramResponse; selectedId: string | null; expanded: Set<string>;
  onDive: (diagramId: string) => void; onSource: (path: string, start?: number, end?: number) => void;
  onToggleGroup: (id: string) => void; onSelect: (id: string | null) => void;
};

export default function Inspector({ owner, repo, data, selectedId, expanded, onDive, onSource, onToggleGroup, onSelect }: Props) {
  const { diagram: d, meta } = data;
  const node = d.nodes.find((n) => n.id === selectedId) ?? null;
  const group = d.groups.find((g) => g.id === selectedId) ?? null;
  return (
    <aside className="inspector">
      {group ? <GroupPanel d={d} group={group} open={expanded.has(group.id)} onToggle={() => onToggleGroup(group.id)} onSelect={onSelect} />
        : node?.type === 'component' ? <ComponentPanel owner={owner} repo={repo} node={node} onDive={onDive} onSource={onSource} />
        : node?.type === 'file' ? <FilePanel owner={owner} repo={repo} d={d} node={node} onSource={onSource} onSelect={onSelect} onDive={onDive} />
        : node?.type === 'class' ? <ClassPanel d={d} node={node} onSource={onSource} onSelect={onSelect} onDive={onDive} />
        : node?.type === 'step' ? <StepPanel node={node} onDive={onDive} onSource={onSource} />
        : node?.type === 'function' ? <FunctionPanel node={node} onDive={onDive} onSource={onSource} />
        : <DiagramPanel data={data} meta={meta} onDive={onDive} onSource={onSource} />}
    </aside>
  );
}

function Chips({ tags }: { tags?: string[] }) {
  return <div className="chips">{(tags ?? []).map((t) => <span key={t} className="chip tag">{t}</span>)}</div>;
}

function DiagramPanel({ data, meta, onDive, onSource }: { data: DiagramResponse; meta: DiagramResponse['meta']; onDive: (id: string) => void; onSource: Props['onSource'] }) {
  const d = data.diagram;
  const fn = d.meta.function as string | undefined;
  const reason = d.meta.fallbackReason as string | undefined;
  return (
    <>
      <div className="muted small">Diagram</div>
      <h3>{d.title}</h3>
      <div className="kv"><span>Type</span><span>{d.kind}</span></div>
      <div className="kv"><span>Elements</span><span>{d.nodes.length} nodes · {d.edges.length} connections</span></div>
      <div className="kv"><span>Branch</span><span>{meta.branch}{meta.commit && meta.commit !== 'local' ? ` @ ${meta.commit.slice(0, 7)}` : ''}</span></div>
      {fn && (
        <>
          {reason && <p className="note">Showing the call graph instead of a flowchart: {reason}.</p>}
          {!!d.meta.omitted && <p className="note">{String(d.meta.omitted)} more related functions are not shown (node ceiling).</p>}
          {d.kind === 'flowchart' && <button className="btn block" onClick={() => onDive(`calls:${fn}`)}>Show call graph</button>}
          {d.kind === 'callgraph' && !reason && <button className="btn block" onClick={() => onDive(`flow:${fn}`)}>Show flowchart</button>}
          <button className="btn block" onClick={() => onSource(String(d.meta.path), Number(d.meta.line), Number(d.meta.endLine))}>View source</button>
          {d.kind === 'flowchart' && <p className="muted small">Dashed boxes are calls that could not be resolved to project code. Amber outlines are edge cases (except blocks, raises, guard-clause exits), a heuristic you will be able to correct in edit mode.</p>}
        </>
      )}
      {data.component && (data.siblings.uml || data.siblings.filemap) && (
        <>
          <h4>Explore this component</h4>
          {data.siblings.uml && <button className="btn block" onClick={() => onDive(data.siblings.uml)}>Open UML</button>}
          {data.siblings.filemap && <button className="btn block" onClick={() => onDive(data.siblings.filemap)}>Open file map</button>}
        </>
      )}
      <p className="muted small">Click a node to inspect it. Double-click to dive in. Ctrl/⌘ + scroll zooms; drag pans.</p>
    </>
  );
}

function ComponentPanel({ owner, repo, node, onDive, onSource }: { owner: string; repo: string; node: DNode; onDive: Props['onDive']; onSource: Props['onSource'] }) {
  const [detail, setDetail] = useState<ComponentDetail | null>(null);
  useEffect(() => {
    let live = true;
    setDetail(null);
    api<ComponentDetail>(`/repos/${enc(owner)}/${enc(repo)}/component/${enc(node.id)}`).then((r) => live && setDetail(r)).catch(() => {});
    return () => { live = false; };
  }, [owner, repo, node.id]);
  const dg = node.diagrams ?? {};
  return (
    <>
      <div className="muted small">Component</div>
      <h3>{node.label}</h3>
      <Chips tags={node.tags} />
      <div className="kv"><span>Path</span><span className="mono">{node.path || '(repo root)'}</span></div>
      <div className="kv"><span>Files</span><span>{node.meta?.files ?? 0}</span></div>
      {!!node.meta?.classes && <div className="kv"><span>Classes</span><span>{node.meta.classes}</span></div>}
      {node.analyzed === false && <p className="muted small">No Python was found here, so this component is listed but not analyzed.</p>}
      <h4>Explore this component</h4>
      {dg.sub && <button className="btn primary block" onClick={() => onDive(dg.sub)}>Expand component</button>}
      {dg.uml && <button className="btn block" onClick={() => onDive(dg.uml)}>Open UML</button>}
      {dg.filemap && <button className="btn block" onClick={() => onDive(dg.filemap)}>{node.analyzed === false ? 'Open file list' : 'Open file map'}</button>}
      <h4>Files{detail ? ` (${detail.files.length})` : ''}</h4>
      <div className="list">
        {detail?.fileDetails.map((f) => (
          <button key={f.id} className="list-row" onClick={() => onSource(f.path)}>
            <span className="mono">{f.path.replace(node.path ? node.path + '/' : '', '')}</span>
            <span className="muted small">{f.kind === 'python' ? `${f.lines} lines` : 'not analyzed'}</span>
          </button>
        ))}
        {!detail && <div className="muted small">Loading…</div>}
      </div>
    </>
  );
}

function neighbours(d: DiagramResponse['diagram'], id: string) {
  const label = (x: string) => d.nodes.find((n) => n.id === x)?.label ?? x;
  return {
    uses: d.edges.filter((e) => e.source === id).map((e) => ({ id: e.target, label: label(e.target), kind: e.kind })),
    usedBy: d.edges.filter((e) => e.target === id).map((e) => ({ id: e.source, label: label(e.source), kind: e.kind })),
  };
}

function Links({ title, rows, onSelect }: { title: string; rows: { id: string; label: string; kind: string }[]; onSelect: (id: string) => void }) {
  if (!rows.length) return null;
  return (
    <>
      <h4>{title} ({rows.length})</h4>
      <div className="list">{rows.map((r) => (
        <button key={r.id + r.kind} className="list-row" onClick={() => onSelect(r.id)}>
          <span className="mono">{r.label}</span><span className="muted small">{r.kind}</span>
        </button>))}</div>
    </>
  );
}

function FilePanel({ owner, repo, d, node, onSource, onSelect, onDive }: { owner: string; repo: string; d: Props['data']['diagram']; node: DNode; onSource: Props['onSource']; onSelect: Props['onSelect']; onDive: Props['onDive'] }) {
  const n = neighbours(d, node.id);
  const [fns, setFns] = useState<FileFunctions['functions'] | null>(null);
  useEffect(() => {
    let live = true;
    setFns(null);
    api<FileFunctions>(`/repos/${enc(owner)}/${enc(repo)}/element/${enc(node.id)}`).then((r) => live && setFns(r.functions ?? [])).catch(() => {});
    return () => { live = false; };
  }, [owner, repo, node.id]);
  return (
    <>
      <div className="muted small">File</div>
      <h3>{node.label}</h3>
      <div className="kv"><span>Path</span><span className="mono">{node.path}</span></div>
      {node.meta?.lines != null && <div className="kv"><span>Lines</span><span>{node.meta.lines}</span></div>}
      {node.meta?.classes != null && <div className="kv"><span>Classes / functions</span><span>{node.meta.classes} / {node.meta.functions}</span></div>}
      <button className="btn primary block" onClick={() => node.path && onSource(node.path)}>View source</button>
      {!!fns?.length && <><h4>Functions and methods ({fns.length})</h4>
        <div className="list">{fns.map((f) => (
          <button key={f.id} className="list-row" disabled={!f.hasFlow} onClick={() => onDive(`flow:${f.id}`)}>
            <span className="mono">{f.qualname}</span><span className="muted small">{f.hasFlow ? 'flowchart' : `line ${f.line}`}</span>
          </button>))}</div></>}
      <Links title="Imports" rows={n.uses} onSelect={onSelect} />
      <Links title="Imported by" rows={n.usedBy} onSelect={onSelect} />
    </>
  );
}

function ClassPanel({ d, node, onSource, onSelect, onDive }: { d: Props['data']['diagram']; node: DNode; onSource: Props['onSource']; onSelect: Props['onSelect']; onDive: Props['onDive'] }) {
  const n = neighbours(d, node.id);
  const m = node.meta ?? {};
  return (
    <>
      <div className="muted small">Class</div>
      <h3>{node.label}</h3>
      <div className="kv"><span>File</span><span className="mono">{node.path}</span></div>
      <button className="btn primary block" onClick={() => node.path && onSource(node.path, m.line, m.endLine)}>View source</button>
      {!!node.attrs?.length && <><h4>Attributes ({node.attrs.length})</h4>
        <div className="list">{node.attrs.map((a) => <div key={a.name} className="list-row static"><span className="mono">{a.name}</span><span className="muted small">{a.type}</span></div>)}</div></>}
      {!!node.methods?.length && <><h4>Methods ({node.methods.length})</h4>
        <div className="list">{node.methods.map((x) => (
          <button key={x.id} className="list-row" onClick={() => onDive(`flow:${x.id}`)} title="Open this method's flowchart">
            <span className="mono">{x.name}{x.signature}</span><span className="muted small">flowchart</span>
          </button>))}</div></>}
      <Links title="Extends / extended by" rows={[...n.usedBy.filter((r) => r.kind === 'inherit'), ...n.uses.filter((r) => r.kind === 'inherit')]} onSelect={onSelect} />
      <Links title="Has" rows={n.uses.filter((r) => r.kind === 'compose')} onSelect={onSelect} />
      <Links title="Part of" rows={n.usedBy.filter((r) => r.kind === 'compose')} onSelect={onSelect} />
    </>
  );
}

function GroupPanel({ d, group, open, onToggle, onSelect }: { d: Props['data']['diagram']; group: DGroup; open: boolean; onToggle: () => void; onSelect: Props['onSelect'] }) {
  return (
    <>
      <div className="muted small">Group</div>
      <h3>{group.label}</h3>
      <button className="btn primary block" onClick={onToggle}>{open ? 'Collapse group' : 'Expand group'}</button>
      <h4>Members ({group.members.length})</h4>
      <div className="list">{group.members.map((m) => (
        <button key={m} className="list-row" onClick={() => onSelect(m)}>
          <span className="mono">{d.nodes.find((n) => n.id === m)?.label ?? m}</span></button>))}</div>
    </>
  );
}

function StepPanel({ node, onDive, onSource }: { node: DNode; onDive: Props['onDive']; onSource: Props['onSource'] }) {
  return (
    <>
      <div className="muted small">Step</div>
      <h3>{node.label}</h3>
      {node.edgeCase && <p className="note">Styled as an edge case ({node.edgeReason}). This is a heuristic, not a fact about the code.</p>}
      {node.unresolved && <p className="note">Unresolved call ({node.status}). Ariadne could not tie this to one piece of project code.
        {node.candidates?.length ? ` Possible targets: ${node.candidates.map((c) => c.split('::').pop()).join(', ')}.` : ''}</p>}
      {node.meta?.line && <div className="kv"><span>Line</span><span>{node.meta.line}</span></div>}
      {node.drill && <button className="btn primary block" onClick={() => onDive(node.drill!)}>Open flowchart</button>}
      {node.path && <button className="btn block" onClick={() => onSource(node.path!, node.meta?.line)}>View source</button>}
    </>
  );
}

function FunctionPanel({ node, onDive, onSource }: { node: DNode; onDive: Props['onDive']; onSource: Props['onSource'] }) {
  return (
    <>
      <div className="muted small">Function</div>
      <h3>{node.label}</h3>
      <div className="kv"><span>File</span><span className="mono">{node.path}</span></div>
      {node.drill && <button className="btn primary block" onClick={() => onDive(node.drill!)}>Open flowchart</button>}
      {node.path && <button className="btn block" onClick={() => onSource(node.path!, node.meta?.line, node.meta?.endLine)}>View source</button>}
    </>
  );
}
