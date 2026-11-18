import type { ReactNode } from 'react';
import type { RepoMeta } from '../types';

type Props = {
  repos: RepoMeta[]; current: string | null; search: ReactNode;
  onHome: () => void; onOpen: (r: RepoMeta) => void; onHelp: () => void; onPrefs: () => void;
};

export default function Sidebar({ repos, current, search, onHome, onOpen, onHelp, onPrefs }: Props) {
  const recent = [...repos].filter((r) => r.lastOpened).sort((a, b) => (b.lastOpened! > a.lastOpened! ? 1 : -1)).slice(0, 5);
  const row = (r: RepoMeta) => (
    <button key={r.owner + r.repo} className={current === `${r.owner}/${r.repo}` ? 'side-row on' : 'side-row'} onClick={() => onOpen(r)}>
      {r.owner === 'examples' ? r.repo : `${r.owner}/${r.repo}`}
    </button>
  );
  return (
    <nav className="sidebar">
      <button className="logo" onClick={onHome}><span className="logo-mark">◈</span> Ariadne</button>
      {search}
      <div className="side-section">
        <div className="side-title">Repositories <span className="count">{repos.length}</span></div>
        {repos.map(row)}
        {repos.length === 0 && <div className="muted small pad-s">Nothing analyzed yet</div>}
      </div>
      {recent.length > 0 && <div className="side-section"><div className="side-title">Recently viewed</div>{recent.map(row)}</div>}
      <div className="intro-card">
        <strong>Find your way in</strong>
        <p className="small">Start at the system overview, then double-click a component to follow its thread inward, down to individual classes.</p>
      </div>
      <div className="side-spacer" />
      <button className="side-row" onClick={onHelp}>Help and documentation</button>
      <button className="side-row" onClick={onPrefs}>Preferences</button>
    </nav>
  );
}
