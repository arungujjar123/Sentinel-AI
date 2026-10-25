'use client'

import { useEffect, useRef } from 'react'
import { ArrowRight, X } from 'lucide-react'
import { capitalize, fmtCost, fmtInt, fmtMs } from '@/lib/format'
import { T, providerColor } from '@/lib/theme'
import type { LogEntry } from '@/lib/types'
import { Tag } from './ui'
import { statusBadge } from './LogsTable'

export function LogModal({ log, onClose }: { log: LogEntry; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const prompt = (log.prompt_preview || '').trim()
  const response = (log.response_preview || '').trim()
  const hasProvider = log.provider && log.provider !== 'none'

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="log-modal-title" onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 16 }}>
          <div style={{ minWidth: 0 }}>
            <div className="card-sub" style={{ marginTop: 0 }}>Request</div>
            <h2 id="log-modal-title" className="mono" style={{ margin: 0, color: T.ink, fontSize: 14, fontWeight: 500, overflowWrap: 'anywhere' }}>
              {log.id}
            </h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
              {statusBadge(log)}
              <Tag color={log.cache_hit ? T.hit : T.miss} label={log.cache_hit ? 'Cache hit' : 'Cache miss'} />
              {hasProvider && <Tag color={providerColor(log.provider)} label={capitalize(log.provider)} />}
            </div>
          </div>
          <button ref={closeRef} type="button" className="modal-close" onClick={onClose} aria-label="Close">
            <X size={16} aria-hidden />
          </button>
        </div>

        <dl className="kv" style={{ margin: 0 }}>
          <div><dt>Model</dt><dd>{log.model || '—'}</dd></div>
          <div><dt>Latency</dt><dd className="num">{fmtMs(log.latency_ms)}</dd></div>
          <div><dt>Cost</dt><dd className="num">{log.cache_hit ? '$0 (cached)' : fmtCost(log.cost_usd)}</dd></div>
          <div><dt>Input tokens</dt><dd className="num">{fmtInt(log.input_tokens)}</dd></div>
          <div><dt>Output tokens</dt><dd className="num">{fmtInt(log.output_tokens)}</dd></div>
          <div><dt>Time (UTC)</dt><dd className="num mono" style={{ fontSize: 12 }}>{new Date(log.created_at).toISOString().replace('T', ' ').slice(0, 19)}</dd></div>
        </dl>

        {log.fallback_from && (
          <div className="banner" style={{ marginTop: 12, padding: '10px 12px' }}>
            <div style={{ fontSize: 13, color: T.ink2, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <b style={{ color: T.ink }}>Failover:</b> {capitalize(log.fallback_from)} failed
              <ArrowRight size={12} aria-hidden /> {capitalize(log.provider)} answered
            </div>
          </div>
        )}

        {log.error_type && (
          <div className="banner" style={{ marginTop: 12, padding: '10px 12px' }}>
            <div style={{ fontSize: 13, color: T.ink2 }}><b style={{ color: T.ink }}>Error:</b> <span className="mono">{log.error_type}</span></div>
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          <div className="preview-label">Prompt</div>
          <div className="preview">{prompt || <span style={{ color: T.ink3 }}>Not stored for this request</span>}</div>
        </div>
        <div style={{ marginTop: 12 }}>
          <div className="preview-label">Response</div>
          <div className="preview">{response || <span style={{ color: T.ink3 }}>Not stored for this request</span>}</div>
        </div>
      </div>
    </div>
  )
}
