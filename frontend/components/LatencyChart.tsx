'use client'

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { capitalize, fmtMs, fmtTime } from '@/lib/format'
import { T } from '@/lib/theme'
import type { LogEntry } from '@/lib/types'
import { Card, CardHead, Empty, LegendItem } from './ui'

type Point = { n: number; latency: number; raw: number; hit: boolean; provider: string; time: string; error: boolean }

function ChartTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: Point }> }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="tooltip">
      <div className="tooltip-title num">{fmtMs(p.raw)}</div>
      <div>{p.error ? 'Failed' : p.hit ? 'Cache hit' : `LLM call · ${capitalize(p.provider)}`}</div>
      <div className="num" style={{ color: T.ink3 }}>{fmtTime(p.time)}</div>
    </div>
  )
}

export function LatencyChart({ logs, offline }: { logs: LogEntry[]; offline: boolean }) {
  const data: Point[] = [...logs].reverse().slice(-30).map((l, i) => ({
    n: i + 1,
    latency: Math.max(10, l.latency_ms),
    raw: l.latency_ms,
    hit: l.cache_hit,
    provider: l.provider,
    time: l.created_at,
    error: l.status === 'error',
  }))
  const hasErrors = data.some(d => d.error)
  const top = Math.max(1000, ...data.map(d => d.latency)) * 1.3
  const ticks = [10, 100, 1000, 10000, 100000].filter(t => t <= top)

  return (
    <Card>
      <CardHead
        title="Latency per request"
        sub="Last 30 requests, oldest to newest · log scale"
        right={
          <div className="legend">
            <LegendItem color={T.hit} label="Cache hit" round />
            <LegendItem color={T.miss} label="LLM call" round />
            {hasErrors && <LegendItem color={T.critical} label="Failed" round />}
          </div>
        }
      />
      {data.length === 0 ? (
        <Empty minHeight={220}>{offline ? 'No data while the backend is offline' : 'No requests yet. Click “Run live demo” to send some.'}</Empty>
      ) : (
        <div style={{ height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke={T.grid} />
              <XAxis
                dataKey="n"
                tick={{ fontSize: 11, fill: T.ink3 }}
                tickLine={false}
                axisLine={{ stroke: T.axis }}
                interval="preserveStartEnd"
                minTickGap={24}
              />
              <YAxis
                width={48}
                scale="log"
                domain={[10, top]}
                ticks={ticks}
                allowDataOverflow
                tick={{ fontSize: 11, fill: T.ink3 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => (v >= 1000 ? `${v / 1000}s` : `${v}ms`)}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: T.axis, strokeWidth: 1 }} />
              <Line
                type="linear"
                dataKey="latency"
                stroke={T.ink3}
                strokeOpacity={0.5}
                strokeWidth={2}
                isAnimationActive={false}
                dot={(props: any) => {
                  const { cx, cy, payload, index } = props
                  const fill = payload.error ? T.critical : payload.hit ? T.hit : T.miss
                  return <circle key={index} cx={cx} cy={cy} r={4.5} fill={fill} stroke={T.surface} strokeWidth={2} />
                }}
                activeDot={(props: any) => {
                  const { cx, cy, payload } = props
                  const fill = payload.error ? T.critical : payload.hit ? T.hit : T.miss
                  return <circle cx={cx} cy={cy} r={6} fill={fill} stroke={T.surface} strokeWidth={2} />
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}
