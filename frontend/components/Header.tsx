'use client'

import { useState } from 'react'
import { Loader2, Play, RefreshCw, ShieldCheck } from 'lucide-react'
import { api } from '@/lib/api'
import { T } from '@/lib/theme'
import type { Connection, TimeWindow, WorkerStats } from '@/lib/types'

const WINDOWS: TimeWindow[] = ['1h', '6h', '24h', '7d']

// Fixed (not randomized) so repeated clicks — by this visitor or others —
// land on the same semantic-cache entry after the first run, producing a
// real cache hit rather than simulating one. Bounded ("in one sentence")
// to keep demo responses fast: open-ended prompts ran to the token cap,
// taking ~30s and cutting off mid-sentence.
const DEMO_PROMPTS = [
  'Explain what a circuit breaker pattern is, in one sentence.',
  'Name one benefit of semantic caching for LLM APIs, in one sentence.',
]

type DemoState = { phase: 'idle' | 'running' | 'done' | 'error'; note: string }

function ConnectionChip({ connection, worker }: { connection: Connection; worker: WorkerStats | null }) {
  let color: string = T.ink3
  let label = 'Connecting…'
  if (connection.state === 'offline') {
    color = T.critical
    label = 'Backend offline'
  } else if (connection.state === 'online') {
    const workerUp = worker?.status === 'connected'
    color = workerUp ? T.good : T.warning
    label = workerUp ? 'Live' : 'Live · worker down'
  }
  return (
    <span className="chip" role="status">
      <span className={`dot ${connection.state === 'connecting' ? 'dot-pulse' : ''}`} style={{ background: color }} aria-hidden />
      {label}
      {connection.state === 'online' && (worker?.queue_depth ?? 0) > 0 && (
        <span style={{ color: T.ink3 }}>· queue {worker?.queue_depth}</span>
      )}
    </span>
  )
}

export function Header(props: {
  connection: Connection
  worker: WorkerStats | null
  win: TimeWindow
  onWin: (w: TimeWindow) => void
  refreshing: boolean
  lastUpdate: string
  onRefresh: () => void
}) {
  const { connection, worker, win, onWin, refreshing, lastUpdate, onRefresh } = props
  const [demo, setDemo] = useState<DemoState>({ phase: 'idle', note: '' })

  const runDemo = async () => {
    setDemo({ phase: 'running', note: 'Sending two live requests through the gateway…' })
    let anyOk = false
    let sawHit = false
    for (const prompt of DEMO_PROMPTS) {
      const res = await api.chat(prompt)
      if (!res.ok && res.status === 429) {
        setDemo({ phase: 'error', note: 'The demo key is rate-limited right now. Try again in a minute.' })
        return
      }
      if (res.ok) {
        anyOk = true
        sawHit = sawHit || !!res.data.meta?.cache_hit
      } else if (res.status !== 503) {
        setDemo({ phase: 'error', note: res.error })
        return
      }
    }
    if (!anyOk) {
      setDemo({ phase: 'error', note: 'All providers failed. The backend may be waking up, so try again shortly.' })
      return
    }
    setDemo({
      phase: 'done',
      note: sawHit ? 'Done. At least one response came straight from the semantic cache.' : 'Done. Run it again to see a cache hit.',
    })
    onRefresh()
    setTimeout(() => setDemo({ phase: 'idle', note: '' }), 6000)
  }

  return (
    <header>
      <div className="header">
        <div className="brand">
          <div className="brand-mark"><ShieldCheck size={20} aria-hidden /></div>
          <div style={{ minWidth: 0 }}>
            <h1 className="brand-name" style={{ margin: 0 }}>Sentinel<span>AI</span></h1>
            <div className="brand-sub">LLM gateway · failover, semantic cache, cost tracking</div>
          </div>
        </div>

        <div className="controls">
          <ConnectionChip connection={connection} worker={worker} />

          <div className="segmented" role="group" aria-label="Time window">
            {WINDOWS.map(w => (
              <button key={w} type="button" aria-pressed={win === w} onClick={() => onWin(w)}>{w}</button>
            ))}
          </div>

          <button type="button" className="btn" onClick={onRefresh} disabled={refreshing} title="Refresh now (auto-refreshes every 15s)">
            <RefreshCw size={14} aria-hidden className={refreshing ? 'spin' : undefined} />
            {lastUpdate ? <span className="num">{lastUpdate}</span> : 'Refresh'}
          </button>

          <button
            type="button"
            className="btn btn-primary"
            onClick={runDemo}
            disabled={demo.phase === 'running' || connection.state !== 'online'}
            title={connection.state !== 'online' ? 'Needs a connected backend' : 'Send two real chat requests through the gateway'}
          >
            {demo.phase === 'running' ? <Loader2 size={14} aria-hidden className="spin" /> : <Play size={14} aria-hidden />}
            {demo.phase === 'running' ? 'Running…' : 'Run live demo'}
          </button>
        </div>
      </div>
      {demo.note && (
        <div className="demo-note" data-tone={demo.phase === 'error' ? 'error' : undefined} role="status">{demo.note}</div>
      )}
    </header>
  )
}
