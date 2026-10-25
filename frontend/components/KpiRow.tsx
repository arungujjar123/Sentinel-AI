import { fmtCost, fmtInt, fmtMs, fmtPct, mean, safeDiv } from '@/lib/format'
import { T } from '@/lib/theme'
import type { CacheStats, LogEntry, Metrics } from '@/lib/types'

type Kpi = { label: string; value: string; sub: string; status?: string }

const DASH = '—'

// One row of headline numbers. Replaces four panels that each repeated
// some subset of these (impact summary, fallback card, cache-vs-miss
// comparison, window overview).
export function KpiRow({ metrics, logs, cache, offline }: { metrics: Metrics | null; logs: LogEntry[]; cache: CacheStats | null; offline: boolean }) {
  const total = metrics?.total_requests ?? 0
  const has = metrics !== null && total > 0

  const hits = metrics ? Math.round(metrics.cache_hit_rate * total) : 0

  // Hit-vs-miss latency comes from the recent log sample: /v1/metrics
  // doesn't split latency by cache outcome.
  const ok = logs.filter(l => l.status !== 'error')
  const hitAvg = mean(ok.filter(l => l.cache_hit).map(l => l.latency_ms))
  const missAvg = mean(ok.filter(l => !l.cache_hit).map(l => l.latency_ms))
  const hasBoth = ok.some(l => l.cache_hit) && ok.some(l => !l.cache_hit)
  const speedup = hasBoth && missAvg > 0 ? Math.max(0, (missAvg - hitAvg) / missAvg) : null

  const errorRate = safeDiv(metrics?.failed_requests ?? 0, total)
  const errorStatus = errorRate >= 0.2 ? T.critical : errorRate >= 0.05 ? T.warning : T.good

  const kpis: Kpi[] = [
    {
      label: 'Requests',
      value: has ? fmtInt(total) : DASH,
      sub: has
        ? `${fmtInt(metrics!.fallback_requests)} via fallback`
        : 'No requests in this window',
    },
    {
      label: 'Cache hit rate',
      value: has ? fmtPct(metrics!.cache_hit_rate) : DASH,
      sub: has ? `${fmtInt(hits)} served from cache` : 'Waiting for traffic',
    },
    {
      label: 'Faster on cache hit',
      value: speedup !== null ? fmtPct(speedup, 0) : DASH,
      sub: speedup !== null ? `${fmtMs(missAvg)} → ${fmtMs(hitAvg)}` : 'Needs a hit and a miss',
    },
    {
      label: 'p95 latency',
      value: has ? fmtMs(metrics!.latency.p95_ms) : DASH,
      sub: has ? `p50 ${fmtMs(metrics!.latency.p50_ms)} · p99 ${fmtMs(metrics!.latency.p99_ms)}` : 'Successful requests only',
    },
    {
      label: 'Error rate',
      value: has ? fmtPct(errorRate) : DASH,
      sub: has ? `${fmtInt(metrics!.failed_requests)} failed after all providers` : 'Requests no provider could serve',
      status: has ? errorStatus : undefined,
    },
    {
      label: 'Cost saved by cache',
      value: cache ? fmtCost(cache.total_saved_usd) : DASH,
      sub: has ? `${fmtCost(metrics!.total_cost_usd)} spent in window` : 'Cached answers cost $0',
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
          <div className="kpi-value">
            {k.status && <span className="dot" style={{ background: k.status }} aria-hidden />}
            {k.value}
          </div>
          <div className="kpi-sub">{unknown ?? k.sub}</div>
        </div>
      ))}
    </div>
  )
}
