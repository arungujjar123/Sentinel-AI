'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { CacheStats, CircuitState, Connection, LogEntry, Metrics, TimeWindow, WorkerStats } from '@/lib/types'
import { CachePanel } from '@/components/CachePanel'
import { CircuitPanel } from '@/components/CircuitPanel'
import { ConnectionBanner } from '@/components/ConnectionBanner'
import { Header } from '@/components/Header'
import { KpiRow } from '@/components/KpiRow'
import { LatencyChart } from '@/components/LatencyChart'
import { LogModal } from '@/components/LogModal'
import { LogsTable } from '@/components/LogsTable'
import { PipelinePanel } from '@/components/PipelinePanel'
import { ProviderPanel } from '@/components/ProviderPanel'

const REFRESH_MS = 15_000

export default function Dashboard() {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [cache, setCache] = useState<CacheStats | null>(null)
  const [circuits, setCircuits] = useState<Record<string, CircuitState>>({})
  const [worker, setWorker] = useState<WorkerStats | null>(null)
  const [connection, setConnection] = useState<Connection>({ state: 'connecting' })
  const [win, setWin] = useState<TimeWindow>('24h')
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdate, setLastUpdate] = useState('')
  const [selected, setSelected] = useState<LogEntry | null>(null)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    const [m, l, cs, ci, ws] = await Promise.all([
      api.metrics(win), api.logs(100), api.cacheStats(), api.circuits(), api.worker(),
    ])

    // A failed poll keeps the previous data on screen rather than blanking
    // panels; the connection state below is what tells the reader.
    if (m.ok) setMetrics(m.data)
    if (l.ok) setLogs(l.data)
    if (cs.ok) setCache(cs.data)
    if (ci.ok) setCircuits(ci.data)
    if (ws.ok) setWorker(ws.data)

    const results = [m, l, cs, ci, ws]
    const firstError = results.find(r => !r.ok)
    if (results.some(r => r.ok)) setConnection({ state: 'online' })
    else if (firstError && !firstError.ok) setConnection({ state: 'offline', message: firstError.error })

    setLastUpdate(new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' }))
    setRefreshing(false)
  }, [win])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, REFRESH_MS)
    return () => clearInterval(t)
  }, [refresh])

  const offline = connection.state === 'offline'

  return (
    <main className="shell">
      <div className="stack">
        <Header
          connection={connection}
          worker={worker}
          win={win}
          onWin={setWin}
          refreshing={refreshing}
          lastUpdate={lastUpdate}
          onRefresh={refresh}
        />

        {connection.state === 'offline' && <ConnectionBanner message={connection.message} />}

        <KpiRow metrics={metrics} logs={logs} cache={cache} offline={offline} />

        <div className="row-2-1">
          <LatencyChart logs={logs} offline={offline} />
          <CircuitPanel circuits={circuits} offline={offline} />
        </div>

        <div className="row-2-1">
          <div className="stack">
            <PipelinePanel log={logs[0] ?? null} offline={offline} />
            <ProviderPanel metrics={metrics} logs={logs} offline={offline} />
          </div>
          <CachePanel metrics={metrics} cache={cache} offline={offline} />
        </div>

        <LogsTable logs={logs} offline={offline} onSelect={setSelected} />
      </div>

      <footer className="footer">
        SentinelAI · refreshes every 15s ·{' '}
        <a href="https://github.com/arungujjar123/Sentinel-AI" style={{ color: 'inherit' }}>source on GitHub</a>
      </footer>

      {selected && <LogModal log={selected} onClose={() => setSelected(null)} />}
    </main>
  )
}
