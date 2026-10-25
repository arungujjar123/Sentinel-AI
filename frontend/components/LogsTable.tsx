'use client'

import { useState } from 'react'
import { ArrowDown, ArrowUp, ChevronRight } from 'lucide-react'
import { capitalize, fmtCost, fmtMs, fmtTime, shortId } from '@/lib/format'
import { T, providerColor } from '@/lib/theme'
import type { LogEntry } from '@/lib/types'
import { Card, CardHead, Empty, StatusBadge, Tag } from './ui'

type SortKey = 'latency_ms' | 'cost_usd' | 'created_at'

export function statusBadge(log: LogEntry) {
  if (log.status === 'error') return <StatusBadge status="critical" label="Error" />
  if (log.fallback_from || log.status === 'fallback') return <StatusBadge status="serious" label="Fallback" />
  return <StatusBadge status="good" label="Success" />
}

export function LogsTable({ logs, offline, onSelect }: { logs: LogEntry[]; offline: boolean; onSelect: (l: LogEntry) => void }) {
  const [statusF, setStatusF] = useState('')
  const [providerF, setProviderF] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('created_at')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const rows = logs
    .filter(l => !statusF || l.status === statusF)
    .filter(l => !providerF || l.provider === providerF)
    .sort((a, b) => {
      const va = a[sortKey], vb = b[sortKey]
      const cmp = va < vb ? -1 : va > vb ? 1 : 0
      return sortDir === 'desc' ? -cmp : cmp
    })

  const toggleSort = (k: SortKey) => {
    if (sortKey === k) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(k); setSortDir('desc') }
  }

  const SortHead = ({ k, label }: { k: SortKey; label: string }) => (
    <th aria-sort={sortKey === k ? (sortDir === 'desc' ? 'descending' : 'ascending') : undefined}>
      <button type="button" onClick={() => toggleSort(k)}>
        {label}
        {sortKey === k && (sortDir === 'desc' ? <ArrowDown size={12} aria-hidden /> : <ArrowUp size={12} aria-hidden />)}
      </button>
    </th>
  )

  return (
    <Card>
      <CardHead
        title="Request log"
        sub={logs.length ? `${rows.length} of ${logs.length} most recent requests · click a row for details` : 'Most recent requests'}
        right={
          <div className="filters">
            <select className="select" value={statusF} onChange={e => setStatusF(e.target.value)} aria-label="Filter by status">
              <option value="">All statuses</option>
              <option value="success">Success</option>
              <option value="fallback">Fallback</option>
              <option value="error">Error</option>
            </select>
            <select className="select" value={providerF} onChange={e => setProviderF(e.target.value)} aria-label="Filter by provider">
              <option value="">All providers</option>
              <option value="groq">Groq</option>
              <option value="gemini">Gemini</option>
            </select>
          </div>
        }
      />

      {logs.length === 0 ? (
        <Empty minHeight={120}>{offline ? 'No data while the backend is offline' : 'No requests logged yet'}</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Request</th>
                <th>Provider</th>
                <th>Cache</th>
                <th>Status</th>
                <SortHead k="latency_ms" label="Latency" />
                <SortHead k="cost_usd" label="Cost" />
                <SortHead k="created_at" label="Time" />
                <th aria-hidden style={{ width: 32 }} />
              </tr>
            </thead>
            <tbody>
              {rows.map(log => (
                <tr
                  key={log.id}
                  tabIndex={0}
                  onClick={() => onSelect(log)}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(log) } }}
                >
                  <td className="mono" style={{ color: T.ink }}>{shortId(log.id)}</td>
                  <td>
                    {log.provider && log.provider !== 'none'
                      ? <Tag color={providerColor(log.provider)} label={capitalize(log.provider)} />
                      : <span style={{ color: T.ink3 }}>—</span>}
                  </td>
                  <td><Tag color={log.cache_hit ? T.hit : T.miss} label={log.cache_hit ? 'Hit' : 'Miss'} /></td>
                  <td>{statusBadge(log)}</td>
                  <td className="num" style={{ color: T.ink }}>{fmtMs(log.latency_ms)}</td>
                  <td className="num">{log.cache_hit ? '$0' : fmtCost(log.cost_usd)}</td>
                  <td className="num mono" style={{ fontSize: 12 }}>{fmtTime(log.created_at)}</td>
                  <td style={{ color: T.ink3 }}><ChevronRight size={14} aria-hidden /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <div style={{ padding: 24, textAlign: 'center', color: T.ink3 }}>No requests match these filters</div>}
        </div>
      )}
    </Card>
  )
}
