import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from 'react';

type T = { x: number; y: number; k: number };
export type CanvasHandle = { fit: () => void; zoomBy: (factor: number) => void };
export type NodeAction = { label: string; run: () => void };

type Props = {
  svg: string;
  idMap: Record<string, string>;          // mermaid id -> stable id (from the API)
  selectedId: string | null;
  highlightId: string | null;
  nodeClasses: Record<string, string[]>;  // stable id -> overlay styles (edge, unresolved, focus); never part of exported Mermaid
  focusNonce: number;                     // bump to center on highlightId
  fitKey: string;                         // refit when this changes (diagram switch / reset view)
  onSelect: (id: string | null) => void;
  onOpen: (id: string) => void;           // double-click
  actionsFor: (id: string) => NodeAction[];
};

const MIN_K = 0.1, MAX_K = 4;
const NODE_SEL = 'g.node, g.cluster';

const Canvas = forwardRef<CanvasHandle, Props>(function Canvas(props, ref) {
  const { svg, idMap, selectedId, highlightId, nodeClasses, focusNonce, fitKey, onSelect, onOpen, actionsFor } = props;
  const wrapRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [t, setT] = useState<T>({ x: 0, y: 0, k: 1 });
  const tRef = useRef(t);
  tRef.current = t;
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [view, setView] = useState({ w: 0, h: 0 });
  const lastFit = useRef<string | null>(null);
  const drag = useRef<{ sx: number; sy: number; ox: number; oy: number; moved: boolean } | null>(null);
  const [hover, setHover] = useState<{ id: string; left: number; top: number } | null>(null);
  const hideTimer = useRef<number | undefined>(undefined);

  const keys = useRef<string[]>([]);
  keys.current = Object.keys(idMap).sort((a, b) => b.length - a.length);

  const stableIdOf = useCallback((el: Element | null): string | null => {
    const node = el?.closest(NODE_SEL);
    if (!node) return null;
    const id = node.getAttribute('id') || '';
    for (const k of keys.current) if (id.includes(k)) return idMap[k];
    return null;
  }, [idMap]);

  // ---- inject svg, measure natural size ----
  useLayoutEffect(() => {
    const host = contentRef.current;
    if (!host) return;
    host.innerHTML = svg;
    const el = host.querySelector('svg');
    if (!el) { setSize(null); return; }
    const vb = el.viewBox?.baseVal;
    const w = vb && vb.width ? vb.width : el.getBoundingClientRect().width;
    const h = vb && vb.height ? vb.height : el.getBoundingClientRect().height;
    el.setAttribute('width', String(w));
    el.setAttribute('height', String(h));
    el.style.maxWidth = 'none';
    setSize({ w, h });
  }, [svg]);

  const measure = () => {
    const r = wrapRef.current?.getBoundingClientRect();
    if (r) setView({ w: r.width, h: r.height });
    return r;
  };
  useEffect(() => {
    measure();
    const ro = new ResizeObserver(() => measure());
    if (wrapRef.current) ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const fit = useCallback(() => {
    const r = wrapRef.current?.getBoundingClientRect();
    if (!r || !size) return;
    const k = Math.max(MIN_K, Math.min((r.width - 80) / size.w, (r.height - 80) / size.h, 1.25));
    setT({ k, x: (r.width - size.w * k) / 2, y: (r.height - size.h * k) / 2 });
  }, [size]);

  useEffect(() => {
    if (size && lastFit.current !== fitKey) { lastFit.current = fitKey; fit(); }
  }, [size, fitKey, fit]);

  const zoomAt = useCallback((factor: number, px?: number, py?: number) => {
    const r = wrapRef.current?.getBoundingClientRect();
    if (!r) return;
    const cx = px ?? r.width / 2, cy = py ?? r.height / 2;
    setT(({ x, y, k }) => {
      const nk = Math.max(MIN_K, Math.min(MAX_K, k * factor));
      const f = nk / k;
      return { k: nk, x: cx - (cx - x) * f, y: cy - (cy - y) * f };
    });
  }, []);

  useImperativeHandle(ref, () => ({ fit, zoomBy: (f: number) => zoomAt(f) }), [fit, zoomAt]);

  // ---- wheel: Ctrl/Cmd (or trackpad pinch) zooms, plain scroll pans ----
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      setHover(null);
      if (e.ctrlKey || e.metaKey) {
        const r = el.getBoundingClientRect();
        zoomAt(Math.exp(-e.deltaY * 0.01), e.clientX - r.left, e.clientY - r.top);
      } else {
        setT((p) => ({ ...p, x: p.x - e.deltaX, y: p.y - e.deltaY }));
      }
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [zoomAt]);

  // ---- selection / highlight classes on the SVG ----
  useEffect(() => {
    const host = contentRef.current;
    if (!host) return;
    host.querySelectorAll(NODE_SEL).forEach((n) => {
      const sid = stableIdOf(n);
      n.classList.toggle('ar-selected', !!sid && sid === selectedId);
      n.classList.toggle('ar-highlight', !!sid && sid === highlightId);
      for (const c of ['edge', 'unresolved', 'focus']) n.classList.toggle('ar-' + c, !!sid && !!nodeClasses[sid]?.includes(c));
    });
  }, [svg, selectedId, highlightId, nodeClasses, stableIdOf]);

  // ---- center on highlighted node ----
  useEffect(() => {
    if (!highlightId || !focusNonce) return;
    const host = contentRef.current, wrap = wrapRef.current;
    if (!host || !wrap) return;
    const el = Array.from(host.querySelectorAll(NODE_SEL)).find((n) => stableIdOf(n) === highlightId);
    if (!el) return;
    const nr = el.getBoundingClientRect(), wr = wrap.getBoundingClientRect();
    const cx = nr.left + nr.width / 2 - wr.left, cy = nr.top + nr.height / 2 - wr.top;
    setT((p) => ({ ...p, x: p.x + wr.width / 2 - cx, y: p.y + wr.height / 2 - cy }));
  }, [focusNonce, highlightId, svg, stableIdOf]);

  // ---- pointer: drag to pan, click to select, double-click to open ----
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    drag.current = { sx: e.clientX, sy: e.clientY, ox: tRef.current.x, oy: tRef.current.y, moved: false };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.sx, dy = e.clientY - d.sy;
    if (!d.moved && Math.hypot(dx, dy) > 4) { d.moved = true; setHover(null); }
    if (d.moved) setT((p) => ({ ...p, x: d.ox + dx, y: d.oy + dy }));
  };
  const onPointerUp = () => { window.setTimeout(() => { drag.current = null; }, 0); };

  const onClick = (e: React.MouseEvent) => {
    if (drag.current?.moved) return;
    onSelect(stableIdOf(e.target as Element));
  };
  const onDoubleClick = (e: React.MouseEvent) => {
    const id = stableIdOf(e.target as Element);
    if (id) onOpen(id);
  };

  // ---- hover action bar (Details / Dive in) ----
  const scheduleHide = () => {
    window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => setHover(null), 250);
  };
  const onMouseOver = (e: React.MouseEvent) => {
    if (drag.current?.moved) return;
    const node = (e.target as Element).closest(NODE_SEL);
    const id = node ? stableIdOf(node) : null;
    if (!node || !id || actionsFor(id).length === 0) { scheduleHide(); return; }
    window.clearTimeout(hideTimer.current);
    const nr = node.getBoundingClientRect(), wr = wrapRef.current!.getBoundingClientRect();
    setHover({ id, left: Math.max(4, nr.right - wr.left - 8), top: Math.max(4, nr.top - wr.top - 30) });
  };

  // ---- minimap ----
  const MM_W = 170, MM_H = 110;
  const mmScale = size ? Math.min(MM_W / size.w, MM_H / size.h) : 1;
  const centerFromMinimap = (e: React.PointerEvent) => {
    if (!size) return;
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const u = (e.clientX - r.left) / mmScale, v = (e.clientY - r.top) / mmScale;
    setT((p) => ({ ...p, x: view.w / 2 - u * p.k, y: view.h / 2 - v * p.k }));
  };
  const mmSvg = svg.replace(/ id="/g, ' data-mid="');   // avoid duplicate DOM ids (arrowheads are lost in the thumbnail)

  return (
    <div className="canvas" ref={wrapRef} onPointerDown={onPointerDown} onPointerMove={onPointerMove}
         onPointerUp={onPointerUp} onClick={onClick} onDoubleClick={onDoubleClick}
         onMouseOver={onMouseOver} onMouseLeave={scheduleHide}>
      <div className="canvas-content" ref={contentRef}
           style={{ transform: `translate(${t.x}px, ${t.y}px) scale(${t.k})` }} />
      {hover && (
        <div className="hover-actions" style={{ left: hover.left, top: hover.top, transform: 'translateX(-100%)' }}
             onMouseEnter={() => window.clearTimeout(hideTimer.current)} onMouseLeave={scheduleHide}
             onPointerDown={(e) => e.stopPropagation()} onClick={(e) => e.stopPropagation()}>
          {actionsFor(hover.id).map((a) => (
            <button key={a.label} onClick={() => { setHover(null); a.run(); }}>{a.label}</button>
          ))}
        </div>
      )}
      <div className="zoom-controls" onPointerDown={(e) => e.stopPropagation()} onClick={(e) => e.stopPropagation()}>
        <button title="Zoom in" onClick={() => zoomAt(1.25)}>+</button>
        <span>{Math.round(t.k * 100)}%</span>
        <button title="Zoom out" onClick={() => zoomAt(0.8)}>−</button>
        <button title="Fit to screen" onClick={fit}>Fit</button>
      </div>
      {size && (
        <div className="minimap" style={{ width: size.w * mmScale, height: size.h * mmScale }}
             onPointerDown={(e) => { e.stopPropagation(); (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); centerFromMinimap(e); }}
             onPointerMove={(e) => { if (e.buttons === 1) centerFromMinimap(e); }}
             onClick={(e) => e.stopPropagation()}>
          <div className="minimap-svg" dangerouslySetInnerHTML={{ __html: mmSvg }} />
          <div className="minimap-view" style={{
            left: (-t.x / t.k) * mmScale, top: (-t.y / t.k) * mmScale,
            width: (view.w / t.k) * mmScale, height: (view.h / t.k) * mmScale }} />
        </div>
      )}
    </div>
  );
});

export default Canvas;
