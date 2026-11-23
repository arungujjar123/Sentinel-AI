import { fmtCost, fmtInt, fmtMs, fmtPct, mean, safeDiv } from '@/lib/format'
import type { CacheStats, LogEntry, Metrics } from '@/lib/types'

type Kpi = { label: string; value: string; sub: string }

const DASH = '—'

// The headline numbers the gateway exists to move: traffic, attacks
// stopped, personal data kept in, latency, cache effectiveness, money saved.
export function KpiRow({ metrics, logs, cache, offline }: {
  metrics: Metrics | null; logs: LogEntry[]; cache: CacheStats | null; offline: boolean
}) {
  const total = metrics?.total_requests ?? 0
  const has = metrics !== null && total > 0
  const g = metrics?.guardrails
  const r = metrics?.routing

  // Hit-vs-miss latency comes from the recent log sample: /v1/metrics
  // doesn't split latency by cache outcome.
  const ok = logs.filter(l => l.status === 'success' || l.status === 'fallback')
  const hitAvg = mean(ok.filter(l => l.cache_hit).map(l => l.latency_ms))
  const missAvg = mean(ok.filter(l => !l.cache_hit).map(l => l.latency_ms))
  const hasBoth = ok.some(l => l.cache_hit) && ok.some(l => !l.cache_hit)
  const speedup = hasBoth && missAvg > 0 ? Math.max(0, (missAvg - hitAvg) / missAvg) : null

  const savedCache = cache?.total_saved_usd ?? 0
  const savedRouting = r?.saved_usd ?? 0

  const kpis: Kpi[] = [
    {
      label: 'Requests',
      value: has ? fmtInt(total) : DASH,
      sub: has
        ? `${fmtPct(safeDiv(metrics!.failed_requests, total))} failed · ${fmtInt(metrics!.fallback_requests)} via fallback`
        : 'No requests in this window',
    },
    {
      label: 'Attacks blocked',
      value: has && g ? fmtInt(g.blocked_requests) : DASH,
      sub: has && g ? `${fmtPct(safeDiv(g.blocked_requests, total))} of requests` : 'Prompt-injection classifier',
    },
    {
      label: 'PII redacted',
      value: has && g ? fmtInt(g.redactions_total) : DASH,
      sub: has && g ? `values, in ${fmtInt(g.redacted_requests)} requests` : 'Names, emails, phones, cards',
    },
    {
      label: 'p95 latency',
      value: has ? fmtMs(metrics!.latency.p95_ms) : DASH,
      sub: has ? `p50 ${fmtMs(metrics!.latency.p50_ms)} · p99 ${fmtMs(metrics!.latency.p99_ms)}` : 'Served requests only',
    },
    {
      label: 'Cache hit rate',
      value: has ? fmtPct(metrics!.cache_hit_rate) : DASH,
      sub: speedup !== null ? `hits ${fmtPct(speedup, 0)} faster than a model call` : 'Semantic match on redacted prompts',
    },
    {
      label: 'Cost saved',
      value: has || cache ? fmtCost(savedCache + savedRouting) : DASH,
      sub: has
        ? `cache ${fmtCost(savedCache)} · routing ${fmtCost(savedRouting)} · spent ${fmtCost(metrics!.total_cost_usd)}`
        : 'By the cache and the router',
    },
  ]

  // Without a metrics response we know nothing, so say that rather than
  // implying the window was empty.
  const unknown = metrics === null ? (offline ? 'Unavailable' : 'Loading…') : null

  return (
    <div className="kpis">
      {kpis.map(k => (
        <div key={k.label} className="card kpi">
          <div className="kpi-label">{k.label}</div>
          <div className="kpi-value">{k.value}</div>
          <div className="kpi-sub">{unknown ?? k.sub}</div>
        </div>
      ))}
    </div>
  )
}
