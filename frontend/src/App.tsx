import { useCallback, useEffect, useState } from 'react';
import { api, enc } from './api';
import type { RepoMeta, SearchItem, Settings } from './types';
import Home from './components/Home';
import RepoView from './components/RepoView';
import Search from './components/Search';
import Sidebar from './components/Sidebar';

type Route = { owner: string; repo: string; diagramId: string } | null;

function parseHash(): Route {
  const m = location.hash.match(/^#\/repo\/([^/]+)\/([^/]+)\/(.+)$/);
  return m ? { owner: decodeURIComponent(m[1]), repo: decodeURIComponent(m[2]), diagramId: decodeURIComponent(m[3]) } : null;
}
const hashFor = (owner: string, repo: string, diagramId: string) => `#/repo/${enc(owner)}/${enc(repo)}/${enc(diagramId)}`;

export default function App() {
  const [route, setRoute] = useState<Route>(parseHash());
  const [repos, setRepos] = useState<RepoMeta[]>([]);
  const [settings, setSettings] = useState<Settings>({ nodeCeiling: 20, leaveDiagram: 'ask', theme: 'light' });
  const [focus, setFocus] = useState<{ id: string; nonce: number } | null>(null);
  const [ceilingVersion, setCeilingVersion] = useState(0);
  const [currentDiagram, setCurrentDiagram] = useState<string | null>(null);
  const [modal, setModal] = useState<'help' | 'prefs' | null>(null);

  const loadRepos = useCallback(() => api<RepoMeta[]>('/repos').then(setRepos).catch(() => {}), []);
  useEffect(() => { loadRepos(); api<Settings>('/settings').then(setSettings).catch(() => {}); }, []);
  useEffect(() => {
    const h = () => setRoute(parseHash());
    window.addEventListener('hashchange', h);
    return () => window.removeEventListener('hashchange', h);
  }, []);
  useEffect(() => { document.documentElement.dataset.theme = settings.theme; }, [settings.theme]);

  const go = (owner: string, repo: string, diagramId = 'L0') => { location.hash = hashFor(owner, repo, diagramId); };
  const home = () => { location.hash = '#/'; };
  const saveSettings = async (patch: Partial<Settings>) => {
    const next = await api<Settings>('/settings', { method: 'PUT', body: JSON.stringify(patch) });
    setSettings(next);
    if (patch.nodeCeiling !== undefined) setCeilingVersion((v) => v + 1);
  };

  const pick = (item: SearchItem) => {
    if (!route) return;
    setFocus({ id: item.target, nonce: Date.now() });
    if (item.diagramId !== route.diagramId) go(route.owner, route.repo, item.diagramId);
  };

  const dark = settings.theme === 'dark';
  const current = route ? `${route.owner}/${route.repo}` : null;

  return (
    <div className="app">
      <Sidebar repos={repos} current={current} onHome={home} onOpen={(r) => go(r.owner, r.repo)}
               onHelp={() => setModal('help')} onPrefs={() => setModal('prefs')}
               search={<Search repo={route} currentDiagramId={route ? currentDiagram : null} onPick={pick} />} />
      <main className="main">
        {route ? (
          <RepoView key={`${route.owner}/${route.repo}/${route.diagramId}`} owner={route.owner} repo={route.repo}
                    diagramId={route.diagramId} dark={dark} ceilingVersion={ceilingVersion} focus={focus}
                    onNavigate={(id) => { setFocus(null); go(route.owner, route.repo, id); }} onHome={home} onDiagram={setCurrentDiagram} />
        ) : (
          <Home repos={repos} dark={dark} onChanged={loadRepos} onOpen={(r) => go(r.owner, r.repo)} />
        )}
      </main>

      {modal === 'prefs' && (
        <div className="modal-backdrop" onClick={() => setModal(null)}>
          <div className="modal small-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Preferences</h3>
            <label className="field">Node ceiling: <strong>{settings.nodeCeiling}</strong>
              <input type="range" min={5} max={50} value={settings.nodeCeiling}
                     onChange={(e) => setSettings({ ...settings, nodeCeiling: +e.target.value })}
                     onMouseUp={(e) => saveSettings({ nodeCeiling: +(e.target as HTMLInputElement).value })}
                     onKeyUp={(e) => saveSettings({ nodeCeiling: +(e.target as HTMLInputElement).value })}
                     onTouchEnd={(e) => saveSettings({ nodeCeiling: +(e.target as HTMLInputElement).value })} />
              <span className="muted small">Largest number of nodes a diagram shows before it splits into sub-components or collapses into groups. Applies to your view only.</span>
            </label>
            <label className="field">Theme
              <select value={settings.theme} onChange={(e) => saveSettings({ theme: e.target.value as Settings['theme'] })}>
                <option value="light">Light</option><option value="dark">Dark</option>
              </select>
            </label>
            <div className="row end"><button className="btn primary" onClick={() => setModal(null)}>Done</button></div>
          </div>
        </div>
      )}
      {modal === 'help' && (
        <div className="modal-backdrop" onClick={() => setModal(null)}>
          <div className="modal small-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Help</h3>
            <ul className="help">
              <li><strong>Dive in:</strong> double-click a component, or use the hover button.</li>
              <li><strong>Move around:</strong> drag to pan, Ctrl/⌘ + scroll (or pinch) to zoom, Fit to recentre.</li>
              <li><strong>Groups:</strong> collapsed groups expand in place; use Collapse group to fold them back.</li>
              <li><strong>Search:</strong> Ctrl/⌘ K. Picking a result jumps to the deepest diagram showing it.</li>
              <li><strong>Source:</strong> files and classes open read-only code with an Open on GitHub link.</li>
              <li><strong>Breadcrumbs</strong> at the top are the way back up.</li>
            </ul>
            <div className="row end"><button className="btn primary" onClick={() => setModal(null)}>Close</button></div>
          </div>
        </div>
      )}
    </div>
  );
}
