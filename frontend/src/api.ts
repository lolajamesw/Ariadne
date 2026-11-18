export class ApiError extends Error {
  status: number;
  detail: any;
  constructor(status: number, detail: any) {
    super(typeof detail === 'string' ? detail : detail?.message ?? `Request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch('/api' + path, { headers: { 'Content-Type': 'application/json' }, ...init });
  if (!r.ok) {
    let detail: any = null;
    try { detail = (await r.json()).detail; } catch { /* non-JSON error body */ }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

export const enc = encodeURIComponent;
export const post = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });
