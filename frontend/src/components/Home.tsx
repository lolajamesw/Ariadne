import { useEffect, useRef, useState } from 'react';
import { api, ApiError, post, enc } from '../api';
import { renderMermaid } from '../mermaidRender';
import type { Job, RepoMeta } from '../types';

type Props = { repos: RepoMeta[]; dark: boolean; onOpen: (r: { owner: string; repo: string }) => void; onChanged: () => void };

export default function Home({ repos, dark, onOpen, onChanged }: Props) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<any>(null);
  const [job, setJob] = useState<Job | null>(null);

  const start = async (confirmed: boolean) => {
    setError(''); setBusy(true);
    try {
      const j = await post<Job>('/ingest', { url, confirmed });
      setConfirm(null); setJob(j);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.detail?.needsConfirmation) setConfirm(e.detail);
      else setError((e as Error).message);
    } finally { setBusy(false); }
  };

  useEffect(() => {
    if (!job || job.status !== 'running') return;
    const h = window.setInterval(async () => {
      try {
        const j = await api<Job>(`/jobs/${job.id}`);
        setJob(j);
        if (j.status === 'done') { onChanged(); onOpen({ owner: j.owner, repo: j.repo }); }
        if (j.status !== 'running') onChanged();
      } catch { /* keep polling */ }
    }, 700);
    return () => window.clearInterval(h);
  }, [job?.id, job?.status]);

  const cancel = async () => { if (job) setJob(await post<Job>(`/jobs/${job.id}/cancel`)); };

  return (
    <div className="home">
      <h1>Find your way through any codebase.</h1>
      <p className="muted">Paste a public GitHub repository and Ariadne draws the map: components, files, and classes, one layer at a time.</p>

      <div className="card start">
        <strong>Start with a repository</strong>
        <div className="row">
          <input value={url} placeholder="https://github.com/owner/repository" disabled={busy || job?.status === 'running'}
                 onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && url && start(false)} />
          <button className="btn primary" disabled={!url || busy || job?.status === 'running'} onClick={() => start(false)}>
            {busy ? 'Checking…' : 'Analyze'}
          </button>
        </div>
        {error && <div className="error">{error}</div>}
        {job && (
          <div className="progress">
            <ol>
              {job.stages.map((s, i) => (
                <li key={s} className={i < job.stageIndex || job.status === 'done' ? 'done' : i === job.stageIndex ? 'now' : ''}>{s}</li>
              ))}
            </ol>
            <div className="bar"><div style={{ width: `${Math.round(((Math.max(0, job.stageIndex) + job.progress) / job.stages.length) * 100)}%` }} /></div>
            {job.status === 'running' && <button className="btn" onClick={cancel}>Cancel</button>}
            {job.status === 'cancelled' && <div className="muted">{job.message}</div>}
            {job.status === 'error' && <div className="error">{job.message}</div>}
          </div>
        )}
      </div>

      <h2>Repositories</h2>
      {repos.length === 0 ? <p className="muted">Nothing analyzed yet. Run <code>python -m app.cli load-examples</code> in <code>backend/</code> for two bundled examples, or analyze a repository above.</p> : (
        <div className="grid">
          {repos.map((r) => <RepoCard key={r.owner + r.repo} r={r} dark={dark} onOpen={() => onOpen(r)} onChanged={onChanged} />)}
        </div>
      )}

      {confirm && (
        <div className="modal-backdrop" onClick={() => setConfirm(null)}>
          <div className="modal small-modal" onClick={(e) => e.stopPropagation()}>
            <h3>This is a large repository</h3>
            <p>{confirm.owner}/{confirm.repo} is about {confirm.sizeMb} MB (the warning threshold is {confirm.thresholdMb} MB). Analysis may take roughly {Math.ceil(confirm.estimateSeconds / 60)} minute(s). You can cancel at any point.</p>
            <div className="row end"><button className="btn" onClick={() => setConfirm(null)}>Not now</button>
              <button className="btn primary" onClick={() => start(true)}>Analyze anyway</button></div>
          </div>
        </div>
      )}
    </div>
  );
}

function RepoCard({ r, dark, onOpen, onChanged }: { r: RepoMeta; dark: boolean; onOpen: () => void; onChanged: () => void }) {
  const thumb = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!r.thumbnail) return;
    let live = true;
    renderMermaid(r.thumbnail, dark ? 'dark' : 'light').then((svg) => { if (live && thumb.current) thumb.current.innerHTML = svg; }).catch(() => {});
    return () => { live = false; };
  }, [r.thumbnail, dark]);
  const remove = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm(`Remove ${r.owner}/${r.repo} and its saved data from this machine?`)) {
      await api(`/repos/${enc(r.owner)}/${enc(r.repo)}`, { method: 'DELETE' }); onChanged();
    }
  };
  return (
    <div className="card repo-card" onClick={onOpen}>
      <div className="thumb" ref={thumb} />
      <div className="repo-head"><strong>{r.owner === 'examples' ? r.repo : `${r.owner}/${r.repo}`}</strong>{r.bundled && <span className="chip">example</span>}</div>
      <div className="muted small">{r.fileCount} Python files · {r.componentCount} components · {r.branch}{r.commit && r.commit !== 'local' ? ` @ ${r.commit.slice(0, 7)}` : ''}</div>
      {r.truncated && <div className="small warn">Analysis was capped at the file limit.</div>}
      <button className="link-btn" onClick={remove}>Remove</button>
    </div>
  );
}
