import { fmtCost, fmtInt, fmtPct, safeDiv } from '@/lib/format'
import { T } from '@/lib/theme'
import type { Metrics } from '@/lib/types'
import { Card, CardHead, Empty, LegendItem } from './ui'

export function RoutingPanel({ metrics, offline }: { metrics: Metrics | null; offline: boolean }) {
  const r = metrics?.routing
  const routed = r ? r.small + r.large : 0

  return (
    <Card>
      <CardHead title="Model routing" sub="A trained classifier sends easy prompts to the small model, hard ones to the large" />
      {!r ? (
        <Empty>{offline ? 'Unavailable while the backend is offline' : metrics === null ? 'Loading…' : 'This backend has no routing stats'}</Empty>
      ) : routed === 0 ? (
        <Empty>No routed model calls in this window</Empty>
      ) : (
        <div className="stack" style={{ gap: 14 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8 }}>
              <span className="kpi-value" style={{ marginTop: 0, fontSize: 22 }}>{fmtPct(safeDiv(r.small, routed), 0)}</span>
              <span className="list-meta">of calls handled by the small model</span>
            </div>
            <div className="meter" role="img" aria-label={`${r.small} calls to the small model, ${r.large} to the large model`}>
              {r.small > 0 && <span style={{ width: `${safeDiv(r.small, routed) * 100}%`, background: T.small }} />}
              {r.large > 0 && <span style={{ width: `${safeDiv(r.large, routed) * 100}%`, background: T.large }} />}
            </div>
            <div className="legend" style={{ marginTop: 8 }}>
              <LegendItem color={T.small} label={`Small ${fmtInt(r.small)}`} />
              <LegendItem color={T.large} label={`Large ${fmtInt(r.large)}`} />
            </div>
          </div>
          <dl className="kv" style={{ margin: 0, gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
            <div><dt>Saved vs all-large</dt><dd className="num">{fmtCost(r.saved_usd)}</dd></div>
            <div><dt>Pinned by caller</dt><dd className="num">{fmtInt(r.pinned)}</dd></div>
            <div><dt>Unrouted</dt><dd className="num">{fmtInt(r.default)}</dd></div>
          </dl>
        </div>
      )}
    </Card>
  )
}
