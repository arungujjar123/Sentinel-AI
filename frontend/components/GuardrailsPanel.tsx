import { ShieldAlert } from 'lucide-react'
import { fmtInt, fmtPct, safeDiv } from '@/lib/format'
import { T } from '@/lib/theme'
import type { LogEntry, Metrics } from '@/lib/types'
import { Card, CardHead, Empty } from './ui'

const PII_TYPES: Array<[string, string]> = [
  ['PERSON', 'Names'],
  ['EMAIL', 'Emails'],
  ['PHONE', 'Phones'],
  ['CARD', 'Cards'],
]

export function GuardrailsPanel({ metrics, logs, offline }: { metrics: Metrics | null; logs: LogEntry[]; offline: boolean }) {
  const g = metrics?.guardrails
  const total = metrics?.total_requests ?? 0
  const lastBlocked = logs.find(l => l.status === 'blocked')
  const byType = g?.redacted_requests_by_type ?? {}
  const maxType = Math.max(1, ...Object.values(byType))

  return (
    <Card>
      <CardHead title="Guardrails" sub="Checked on every request before the cache or a model sees it" />
      {!g ? (
        <Empty>{offline ? 'Unavailable while the backend is offline' : metrics === null ? 'Loading…' : 'This backend has no guardrail stats'}</Empty>
      ) : (
        <div className="stack" style={{ gap: 16 }}>
          <div className="list-row" style={{ alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', gap: 10, minWidth: 0 }}>
              <ShieldAlert size={18} color={T.critical} aria-hidden style={{ flexShrink: 0, marginTop: 2 }} />
              <div style={{ minWidth: 0 }}>
                <div className="list-name">
                  <span className="num">{fmtInt(g.blocked_requests)}</span> prompt-injection {g.blocked_requests === 1 ? 'attempt' : 'attempts'} blocked
                </div>
                <div className="list-meta">
                  {fmtPct(safeDiv(g.blocked_requests, total))} of requests in this window, refused before any model call
                </div>
                {lastBlocked?.prompt_preview && (
                  <div className="list-meta mono" style={{ marginTop: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={lastBlocked.prompt_preview}>
                    latest: “{lastBlocked.prompt_preview}”
                  </div>
                )}
              </div>
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
              <span className="list-meta">Requests with PII removed, by type</span>
              <span className="list-meta num">{fmtInt(g.redacted_requests)} requests</span>
            </div>
            <div className="bars" role="list">
              {PII_TYPES.map(([key, label]) => {
                const n = byType[key] ?? 0
                return (
                  <div key={key} className="bar-row" role="listitem" aria-label={`${label}: ${n} requests`}>
                    <span className="label">{label}</span>
                    <div className="share-track"><span style={{ width: `${(n / maxType) * 100}%`, background: T.ink3 }} /></div>
                    <span className="value num">{fmtInt(n)}</span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
