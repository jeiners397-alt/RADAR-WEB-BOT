// Cliente API. El CSRF vive solo en memoria (nunca en localStorage); la cookie de sesión es HttpOnly.
let csrf = ''
export const setCsrf = (v: string) => { csrf = v }

export class ApiError extends Error {
  status: number
  constructor(status: number, msg: string) { super(msg); this.status = status }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = opts.method ?? 'GET'
  const r = await fetch('/api/v1' + path, {
    method,
    credentials: 'same-origin',
    headers: { ...(opts.body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(method !== 'GET' ? { 'x-csrf-token': csrf } : {}) },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  })
  if (!r.ok) {
    let msg = r.statusText
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* noop */ }
    if (r.status === 401) window.dispatchEvent(new Event('crp-unauth'))
    throw new ApiError(r.status, msg)
  }
  const ct = r.headers.get('content-type') ?? ''
  return (ct.includes('json') ? r.json() : r.text()) as Promise<T>
}

export const fmt = {
  usd: (v: number | null | undefined, d = 2) => v == null ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }),
  signed: (v: number | null | undefined, d = 2) => v == null ? '—' : (v >= 0 ? '+' : '') + v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }),
  pct: (v: number | null | undefined, d = 2) => v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(d) + '%',
  pf: (v: number | null | undefined) => v == null ? 'N/A' : v.toFixed(2),
  time: (iso: string) => new Date(iso).toLocaleTimeString('es-PE', { timeZone: 'America/Lima', hour12: false }),
  dt: (iso: string) => new Date(iso).toLocaleString('es-PE', { timeZone: 'America/Lima', hour12: false }),
  dur: (s: number | null | undefined) => { if (s == null) return '—'; const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60; return [h, m, x].map(n => String(n).padStart(2, '0')).join(':') },
}
