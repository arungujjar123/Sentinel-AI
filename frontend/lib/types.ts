// Response shapes of the gateway endpoints the dashboard polls.
// Mirrors backend/app/models.py and the dict-returning routes in
// backend/app/routers/observability.py.

export interface Metrics {
  window: string
  total_requests: number
  successful_requests: number
  failed_requests: number
  fallback_requests: number
  cache_hit_rate: number
  total_cost_usd: number
  latency: { p50_ms: number; p95_ms: number; p99_ms: number; avg_ms: number }
  providers: Record<string, { requests: number; errors: number; avg_latency_ms: number; error_rate: number }>
  // Optional so the dashboard still renders against a backend that
  // predates guardrails.
  guardrails?: GuardrailStats
  routing?: RoutingStats
}

export interface GuardrailStats {
  blocked_requests: number
  redacted_requests: number
  redactions_total: number
  redacted_requests_by_type: Record<string, number>
}

export interface RoutingStats {
  small: number
  large: number
  pinned: number
  default: number
  saved_usd: number
}

export type Route = 'small' | 'large' | 'pinned' | 'default'

export interface LogEntry {
  id: string
  provider: string
  model: string
  input_tokens: number
  output_tokens: number
  cost_usd: number
  latency_ms: number
  cache_hit: boolean
  status: string
  error_type: string | null
  fallback_from: string | null
  prompt_preview?: string | null
  response_preview?: string | null
  injection_score?: number | null
  redaction_count?: number
  redaction_types?: string | null
  route?: Route | null
  router_score?: number | null
  created_at: string
}

export interface CacheStats {
  total_entries: number
  total_hits: number
  total_saved_usd: number
  threshold: number
  top_cached: Array<{ prompt_preview: string; hit_count: number; saved_usd: number }>
}

export interface CircuitState {
  state: 'closed' | 'open' | 'half_open'
  failure_count: number
  last_failure: number
}

export interface WorkerStats {
  status: string
  queue_depth: number
}

export type TimeWindow = '1h' | '6h' | '24h' | '7d'

// Whether the dashboard can currently reach the backend at all, and if
// not, the error the proxy or backend reported — shown verbatim in the
// connection banner instead of letting every panel silently render zeros.
export type Connection =
  | { state: 'connecting' }
  | { state: 'online' }
  | { state: 'offline'; message: string }
