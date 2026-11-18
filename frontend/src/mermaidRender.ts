import mermaid from 'mermaid';

let counter = 0;
let currentTheme: string | null = null;
let queue: Promise<unknown> = Promise.resolve();

function configure(theme: 'light' | 'dark') {
  if (currentTheme === theme) return;
  currentTheme = theme;
  const dark = theme === 'dark';
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',             // repo-derived labels are untrusted: keep Mermaid's sanitizer on
    maxTextSize: 5_000_000,              // spec section 3: raise limits well above the defaults
    maxEdges: 5000,
    theme: 'base',
    themeVariables: dark
      ? { background: '#1b1d23', primaryColor: '#262a33', primaryTextColor: '#e6e8ee', primaryBorderColor: '#4b5263',
          lineColor: '#8b93a7', secondaryColor: '#2b303b', tertiaryColor: '#1b1d23', fontFamily: 'Inter, system-ui, sans-serif' }
      : { background: '#ffffff', primaryColor: '#ffffff', primaryTextColor: '#1d2433', primaryBorderColor: '#c5cbd8',
          lineColor: '#7a8499', secondaryColor: '#f3f5fa', tertiaryColor: '#ffffff', fontFamily: 'Inter, system-ui, sans-serif' },
    flowchart: { htmlLabels: true, curve: 'basis', nodeSpacing: 40, rankSpacing: 60, useMaxWidth: false },
    class: { useMaxWidth: false },
  });
}

/** Mermaid's renderer is not re-entrant, so renders are serialized. */
export function renderMermaid(text: string, theme: 'light' | 'dark'): Promise<string> {
  const run = async () => {
    configure(theme);
    const { svg } = await mermaid.render(`ariadne-${++counter}`, text);
    return svg;
  };
  const p = queue.then(run, run);
  queue = p.catch(() => undefined);
  return p;
}
