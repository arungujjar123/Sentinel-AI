import { capitalize, fmtInt, fmtMs, fmtPct, safeDiv } from '@/lib/format'
import { providerColor } from '@/lib/theme'
import type { LogEntry, Metrics } from '@/lib/types'
import { Card, CardHead, Empty, StatusBadge } from './ui'

// Primary first, then fallback — the order the gateway tries them in.
const ORDER = ['groq', 'gemini']
const ROLE: Record<string, string> = { groq: 'primary', gemini: 'fallback' }

export function ProviderPanel({ metrics, logs, offline }: { metrics: Metrics | null; logs: LogEntry[]; offline: boolean }) {
  const providers = metrics ? Object.entries(metrics.providers) : []
  providers.sort(([a], [b]) => {
    const ia = ORDER.indexOf(a), ib = ORDER.indexOf(b)
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.localeCompare(b)
  })
  const total = providers.reduce((sum, [, p]) => sum + p.requests, 0)

  // /v1/metrics doesn't break out fallback-served requests per provider;
  // the recent log sample does.
  const fallbackServed = logs.reduce<Record<string, number>>((acc, l) => {
    if (l.fallback_from && l.provider) acc[l.provider] = (acc[l.provider] ?? 0) + 1
    return acc
  }, {})

  return (
    <Card>
      <CardHead title="Providers" sub="Share of LLM calls in this window. Groq is tried first, Gemini is the fallback." />
      {providers.length === 0 ? (
        <Empty minHeight={100}>
          {offline ? 'Unavailable while the backend is offline' : metrics === null ? 'Loading…' : 'No provider calls in this window'}
        </Empty>
      ) : (
        <div className="list">
          {providers.map(([name, p]) => {
            const share = safeDiv(p.requests, total)
            const color = providerColor(name)
            const errStatus = p.error_rate >= 0.2 ? 'critical' : p.error_rate >= 0.05 ? 'warning' : 'good'
            return (
              <div key={name} className="provider-row">
                <div className="provider-top">
                  <div className="list-name" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className="swatch" style={{ background: color }} aria-hidden />
                    {capitalize(name)}
                    {ROLE[name] && <span className="list-meta" style={{ fontWeight: 400 }}>{ROLE[name]}</span>}
                  </div>
                  <StatusBadge status={errStatus} label={`${fmtPct(p.error_rate)} errors`} />
                </div>
                <div className="share-track" role="img" aria-label={`${fmtPct(share, 0)} of calls`}>
                  <span style={{ width: `${share * 100}%`, background: color }} />
                </div>
                <div className="provider-stats num">
                  <span><b>{fmtPct(share, 0)}</b> of calls</span>
                  <span><b>{fmtInt(p.requests)}</b> requests</span>
                  <span><b>{fmtMs(p.avg_latency_ms)}</b> avg latency</span>
                  {(fallbackServed[name] ?? 0) > 0 && <span><b>{fmtInt(fallbackServed[name])}</b> served as fallback (recent)</span>}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
