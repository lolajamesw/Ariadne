import { useEffect, useMemo, useRef, useState } from 'react';
import MiniSearch from 'minisearch';
import { api, enc } from '../api';
import type { SearchItem } from '../types';

type Props = { repo: { owner: string; repo: string } | null; currentDiagramId: string | null; onPick: (item: SearchItem) => void };
const TYPES: SearchItem['type'][] = ['component', 'file', 'class', 'function'];
const ICON: Record<SearchItem['type'], string> = { component: '▣', file: '📄', class: '◇', function: 'ƒ' };

export default function Search({ repo, currentDiagramId, onPick }: Props) {
  const [items, setItems] = useState<SearchItem[]>([]);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [types, setTypes] = useState<Set<string>>(new Set());
  const [tag, setTag] = useState('');
  const [scope, setScope] = useState<'repo' | 'diagram'>('repo');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const key = repo ? `${repo.owner}/${repo.repo}` : '';

  useEffect(() => {
    setItems([]); setQ('');
    if (!repo) return;
    let live = true;
    api<SearchItem[]>(`/repos/${enc(repo.owner)}/${enc(repo.repo)}/search-index`).then((r) => live && setItems(r)).catch(() => {});
    return () => { live = false; };
  }, [key]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); inputRef.current?.focus(); setOpen(true); }
      if (e.key === 'Escape') { setOpen(false); inputRef.current?.blur(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const index = useMemo(() => {
    const ms = new MiniSearch<SearchItem & { routeText: string }>({
      fields: ['name', 'path', 'routeText'], storeFields: ['id'], idField: 'id',
      searchOptions: { prefix: true, fuzzy: 0.2, boost: { name: 3, path: 1.5 } },
    });
    ms.addAll(items.map((i) => ({ ...i, routeText: i.route.join(' ') })));
    return ms;
  }, [items]);

  const allTags = useMemo(() => Array.from(new Set(items.flatMap((i) => i.tags))).sort(), [items]);
  const byId = useMemo(() => new Map(items.map((i) => [i.id, i])), [items]);

  const results = useMemo(() => {
    let list: SearchItem[] = q.trim()
      ? index.search(q).map((r) => byId.get(r.id as string)!).filter(Boolean)
      : [];
    if (types.size) list = list.filter((i) => types.has(i.type));
    if (tag) list = list.filter((i) => i.tags.includes(tag));
    if (scope === 'diagram' && currentDiagramId) list = list.filter((i) => i.diagramId === currentDiagramId);
    return list.slice(0, 12);
  }, [q, index, byId, types, tag, scope, currentDiagramId]);

  useEffect(() => setActive(0), [q, types, tag, scope]);

  const pick = (i: SearchItem) => { setOpen(false); setQ(''); onPick(i); };
  const toggleType = (t: string) => setTypes((s) => { const n = new Set(s); n.has(t) ? n.delete(t) : n.add(t); return n; });

  return (
    <div className="search">
      <input ref={inputRef} value={q} disabled={!repo}
             placeholder={repo ? 'Search components, files, classes…  (Ctrl/⌘ K)' : 'Open a repository to search'}
             onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true); }}
             onKeyDown={(e) => {
               if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(results.length - 1, a + 1)); }
               if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
               if (e.key === 'Enter' && results[active]) pick(results[active]);
             }} />
      {open && repo && (
        <div className="search-pop" onMouseDown={(e) => e.preventDefault()}>
          <div className="search-filters">
            {TYPES.map((t) => (
              <button key={t} className={types.has(t) ? 'chip on' : 'chip'} onClick={() => toggleType(t)}>{t}</button>
            ))}
            <select value={tag} onChange={(e) => setTag(e.target.value)} title="Filter by role tag">
              <option value="">any tag</option>
              {allTags.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <button className="chip" disabled title="Available once comments exist (Part 4)">open comments</button>
            <span className="scope">
              <button className={scope === 'repo' ? 'chip on' : 'chip'} onClick={() => setScope('repo')}>whole repo</button>
              <button className={scope === 'diagram' ? 'chip on' : 'chip'} onClick={() => setScope('diagram')}>this diagram</button>
            </span>
          </div>
          {q.trim() && results.length === 0 && <div className="search-empty">No matches</div>}
          {results.map((r, i) => (
            <div key={r.id} className={i === active ? 'search-row active' : 'search-row'}
                 onMouseEnter={() => setActive(i)} onClick={() => pick(r)}>
              <span className="icon">{ICON[r.type]}</span>
              <span className="name">{r.name}</span>
              <span className="route">{[...r.route, r.type === 'function' ? r.where : ''].filter(Boolean).join(' › ')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
