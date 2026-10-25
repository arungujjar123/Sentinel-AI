import type { ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { capitalize, fmtCost, fmtInt, fmtMs, fmtTime } from '@/lib/format'
import { T, providerColor } from '@/lib/theme'
import type { LogEntry } from '@/lib/types'
import { Card, CardHead, Empty, StatusBadge, Tag } from './ui'

type Step = { label: string; detail: ReactNode; active: boolean }

// The path the most recent request took through the gateway.
export function PipelinePanel({ log, offline }: { log: LogEntry | null; offline: boolean }) {
  if (!log) {
    return (
      <Card>
        <CardHead title="Last request" sub="The path it took through the gateway" />
        <Empty>{offline ? 'No data while the backend is offline' : 'No requests yet. Click “Run live demo” to send one.'}</Empty>
      </Card>
    )
  }

  const hit = log.cache_hit
  const failed = log.status === 'error'
  const fellBack = !!log.fallback_from

  const steps: Step[] = [
    { label: 'Auth + rate limit', detail: 'Accepted', active: true },
    { label: 'Semantic cache', detail: <Tag color={hit ? T.hit : T.miss} label={hit ? 'Hit' : 'Miss'} />, active: true },
    {
      label: 'Provider',
      detail: hit
        ? 'Skipped'
        : failed
          ? 'All failed'
          : fellBack
            ? <>{capitalize(log.fallback_from!)} <ArrowRight size={12} aria-hidden /> {capitalize(log.provider)}</>
            : capitalize(log.provider),
      active: !hit,
    },
    { label: 'Response', detail: failed ? 'HTTP 503' : fmtMs(log.latency_ms), active: true },
  ]

  return (
    <Card>
      <CardHead
        title="Last request"
        sub={`The path it took through the gateway · ${fmtTime(log.created_at)}`}
        right={
          failed
            ? <StatusBadge status="critical" label="Failed" />
            : fellBack
              ? <StatusBadge status="serious" label="Served by fallback" />
              : <StatusBadge status="good" label="Success" />
        }
      />

      <ol className="pipeline" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {steps.map((s, i) => (
          <li key={s.label} className="step" data-active={s.active}>
            <div className="step-n">Step {i + 1}</div>
            <div className="step-label">{s.label}</div>
            <div className="step-detail">{s.detail}</div>
          </li>
        ))}
      </ol>

      <dl className="kv" style={{ margin: '12px 0 0' }}>
        <div><dt>Latency</dt><dd className="num">{fmtMs(log.latency_ms)}</dd></div>
        <div>
          <dt>Provider</dt>
          <dd style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {log.provider && log.provider !== 'none' && (
              <span className="swatch" style={{ background: providerColor(log.provider), width: 8, height: 8, borderRadius: 2 }} aria-hidden />
            )}
            {log.provider && log.provider !== 'none' ? capitalize(log.provider) : '—'}
          </dd>
        </div>
        <div><dt>Tokens in / out</dt><dd className="num">{fmtInt(log.input_tokens)} / {fmtInt(log.output_tokens)}</dd></div>
        <div><dt>Cost</dt><dd className="num">{hit ? '$0 (cached)' : fmtCost(log.cost_usd)}</dd></div>
      </dl>
    </Card>
  )
}
