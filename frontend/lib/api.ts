// Every call goes to the same-origin proxy at app/api/gateway/[...path]/route.ts,
// which forwards to the backend server-side and injects the API key there.
// The browser never sees a key or a backend URL.
import type { CacheStats, CircuitState, LogEntry, Metrics, TimeWindow, WorkerStats } from './types'

const BASE = '/api/gateway'

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number | null; error: string }

// The proxy reports its own failures as { error }, FastAPI as { detail }.
function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === 'object') {
    const b = body as Record<string, unknown>
    if (typeof b.error === 'string') return b.error
    if (typeof b.detail === 'string') return b.detail
    if (b.detail && typeof b.detail === 'object' && typeof (b.detail as any).error === 'string') {
      return (b.detail as any).error
    }
  }
  return `Request failed with HTTP ${status}`
}

async function request<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { cache: 'no-store', ...init })
  } catch {
    return { ok: false, status: null, error: 'Network error — the dashboard server could not be reached' }
  }
  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    // Non-JSON body (e.g. an HTML error page) — handled below.
  }
  if (!res.ok) return { ok: false, status: res.status, error: errorMessage(body, res.status) }
  return { ok: true, data: body as T }
}

export const api = {
  metrics: (win: TimeWindow) => request<Metrics>(`/v1/metrics?window=${win}`),
  logs: async (limit = 100): Promise<ApiResult<LogEntry[]>> => {
    const r = await request<{ logs: LogEntry[] }>(`/v1/logs?limit=${limit}`)
    return r.ok ? { ok: true, data: r.data.logs ?? [] } : r
  },
  cacheStats: () => request<CacheStats>('/v1/cache/stats'),
  circuits: () => request<Record<string, CircuitState>>('/v1/circuit/states'),
  worker: () => request<WorkerStats>('/v1/worker/stats'),
  chat: (content: string) =>
    request<{ meta?: { cache_hit?: boolean } }>('/v1/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: [{ role: 'user', content }], max_tokens: 150 }),
    }),
}
