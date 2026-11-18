export type Settings = { nodeCeiling: number; leaveDiagram: string; theme: 'light' | 'dark' };

export type RepoMeta = {
  owner: string; repo: string; branch: string; commit: string; language?: string; fileCount?: number;
  componentCount?: number; analyzedAt?: string; lastOpened?: string; thumbnail?: string; bundled?: boolean;
  truncated?: boolean; sizeMb?: number;
};

export type DNode = {
  id: string; type: 'component' | 'file' | 'class' | 'step' | 'function'; label: string; path?: string; tags?: string[];
  drill?: string | null; diagrams?: Record<string, string>; analyzed?: boolean;
  meta?: Record<string, number>;
  attrs?: { name: string; type: string }[]; methods?: { id: string; name: string; signature: string }[];
  file?: string;
  shape?: string; edgeCase?: boolean; edgeReason?: string; unresolved?: boolean; status?: string;
  focus?: boolean; candidates?: string[];
};
export type DGroup = { id: string; label: string; members: string[]; collapsed: boolean };
export type DEdge = { id: string; source: string; target: string; kind: string; label: string };
export type Diagram = {
  id: string; kind: 'overview' | 'subcomponents' | 'filemap' | 'uml' | 'filelist' | 'flowchart' | 'callgraph'; title: string;
  compId: string | null; parent: string | null; crumb: string; direction: string;
  nodes: DNode[]; edges: DEdge[]; groups: DGroup[]; meta: Record<string, unknown>;
};
export type Component = {
  id: string; label: string; path: string; tags: string[]; analyzed: boolean; fileCount: number; classCount: number;
  children: string[]; diagrams: Record<string, string>; defaultDiagram: string | null; files: string[];
};
export type DiagramResponse = {
  diagram: Diagram; idMap: Record<string, string>; classes: Record<string, string[]>; mermaid: string;
  breadcrumb: { id: string; label: string }[]; component: Component | null;
  siblings: Record<string, string>; meta: RepoMeta;
};
export type ComponentDetail = Component & {
  fileDetails: { id: string; path: string; kind: string; lines: number; classes: number; functions: number }[];
};
export type SearchItem = {
  id: string; type: 'component' | 'file' | 'class' | 'function'; name: string; path: string; tags: string[];
  diagramId: string; target: string; route: string[]; where: string;
};
export type Job = {
  id: string; owner: string; repo: string; status: 'running' | 'done' | 'cancelled' | 'error';
  stage: string; stageIndex: number; stages: string[]; progress: number; message: string;
};
export type SourceResponse = { path: string; text: string; commit: string; githubUrl: string | null };

export type FileFunctions = { functions: { id: string; qualname: string; line: number; endLine: number; hasFlow: boolean }[] };
