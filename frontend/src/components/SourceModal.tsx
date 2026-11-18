import { useEffect, useRef, useState } from 'react';
import { Highlight, themes } from 'prism-react-renderer';
import { api, enc } from '../api';
import type { SourceResponse } from '../types';

type Props = { owner: string; repo: string; path: string; start?: number; end?: number; dark: boolean; onClose: () => void };

export default function SourceModal({ owner, repo, path, start, end, dark, onClose }: Props) {
  const [src, setSrc] = useState<SourceResponse | null>(null);
  const [err, setErr] = useState('');
  const hit = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    setSrc(null); setErr('');
    const qs = new URLSearchParams({ path, ...(start ? { start: String(start) } : {}), ...(end ? { end: String(end) } : {}) });
    api<SourceResponse>(`/repos/${enc(owner)}/${enc(repo)}/source?${qs}`)
      .then((r) => live && setSrc(r)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [owner, repo, path, start, end]);

  useEffect(() => { hit.current?.scrollIntoView({ block: 'center' }); }, [src]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const language = path.endsWith('.py') ? 'python' : path.endsWith('.json') ? 'json' : path.endsWith('.yml') || path.endsWith('.yaml') ? 'yaml' : 'plain';

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal source-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div><div className="muted small">Source file · read-only</div><strong>{path}</strong></div>
          <div className="row">
            {src?.githubUrl && <a className="btn" href={src.githubUrl} target="_blank" rel="noreferrer">Open on GitHub</a>}
            <button className="btn" onClick={onClose}>Close</button>
          </div>
        </div>
        {err && <div className="error">{err}</div>}
        {!src && !err && <div className="muted pad">Loading…</div>}
        {src && (
          <Highlight theme={dark ? themes.vsDark : themes.github} code={src.text.replace(/\n$/, '')} language={language}>
            {({ tokens, getLineProps, getTokenProps }) => (
              <pre className="code">
                {tokens.map((line, i) => {
                  const n = i + 1, on = !!start && n >= start && n <= (end ?? start);
                  return (
                    <div key={i} {...getLineProps({ line })} ref={n === start ? hit : undefined}
                         className={on ? 'code-line hl' : 'code-line'}>
                      <span className="ln">{n}</span>
                      <span>{line.map((token, k) => <span key={k} {...getTokenProps({ token })} />)}</span>
                    </div>
                  );
                })}
              </pre>
            )}
          </Highlight>
        )}
        {src && <div className="modal-foot muted small">Commit {src.commit.slice(0, 7)}</div>}
      </div>
    </div>
  );
}
