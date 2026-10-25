import { capitalize } from '@/lib/format'
import { providerColor } from '@/lib/theme'
import type { CircuitState } from '@/lib/types'
import { Card, CardHead, Empty, StatusBadge, type Status } from './ui'

// Must match FAILURE_THRESHOLD in backend/app/services/circuit_breaker.py.
const FAILURE_THRESHOLD = 3

const STATE: Record<CircuitState['state'], { status: Status; label: string; meaning: string }> = {
  closed:    { status: 'good',     label: 'Healthy', meaning: 'Taking traffic' },
  half_open: { status: 'warning',  label: 'Testing', meaning: 'One probe request allowed' },
  open:      { status: 'critical', label: 'Open',    meaning: 'Skipped, traffic goes to fallback' },
}

export function CircuitPanel({ circuits, offline }: { circuits: Record<string, CircuitState>; offline: boolean }) {
  const entries = Object.entries(circuits).sort(([a], [b]) => a.localeCompare(b))
  const open = entries.filter(([, c]) => c.state === 'open').map(([n]) => capitalize(n))
  const testing = entries.filter(([, c]) => c.state === 'half_open').map(([n]) => capitalize(n))
  const summary = open.length
    ? `${open.join(', ')} ${open.length > 1 ? 'are' : 'is'} open. Requests skip ${open.length > 1 ? 'them' : 'it'} and go to the next provider.`
    : testing.length
      ? `${testing.join(', ')} ${testing.length > 1 ? 'are' : 'is'} recovering. The next request is a probe; success closes the circuit.`
      : 'All circuits closed. Requests go to the primary provider first.'

  return (
    <Card>
      <CardHead
        title="Circuit breakers"
        sub={`Opens after ${FAILURE_THRESHOLD} consecutive failures, retries after 60s`}
      />
      {entries.length === 0 ? (
        <Empty>{offline ? 'Unavailable while the backend is offline' : 'No provider has been called yet'}</Empty>
      ) : (
        <div className="list">
          {entries.map(([name, c]) => {
            const s = STATE[c.state]
            return (
              <div key={name} className="list-row">
                <div style={{ minWidth: 0 }}>
                  <div className="list-name" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className="swatch" style={{ background: providerColor(name), width: 8, height: 8, borderRadius: 2 }} aria-hidden />
                    {capitalize(name)}
                  </div>
                  <div className="list-meta">
                    {s.meaning} · <span className="num">{c.failure_count}/{FAILURE_THRESHOLD}</span> failures
                  </div>
                </div>
                <StatusBadge status={s.status} label={s.label} />
              </div>
            )
          })}
          <div className="list-meta" style={{ marginTop: 4 }}>
            {summary}
          </div>
        </div>
      )}
    </Card>
  )
}
