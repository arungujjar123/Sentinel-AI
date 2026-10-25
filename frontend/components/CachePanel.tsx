import { fmtCost, fmtInt, fmtPct } from '@/lib/format'
import { T } from '@/lib/theme'
import type { CacheStats, Metrics } from '@/lib/types'
import { Card, CardHead, Empty, LegendItem } from './ui'

export function CachePanel({ metrics, cache, offline }: { metrics: Metrics | null; cache: CacheStats | null; offline: boolean }) {
  const total = metrics?.total_requests ?? 0
  const hits = metrics ? Math.round(metrics.cache_hit_rate * total) : 0
  const misses = total - hits

  return (
    <Card>
      <CardHead
        title="Semantic cache"
        sub={cache ? `Matches prompts at ≥ ${cache.threshold} cosine similarity` : 'Embedding match, then pgvector search'}
      />

      {total === 0 && !cache ? (
        <Empty>{offline ? 'Unavailable while the backend is offline' : metrics === null ? 'Loading…' : 'No requests in this window'}</Empty>
      ) : (
        <div className="stack" style={{ gap: 14 }}>
          {total > 0 && (
            <div>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8 }}>
                <span className="kpi-value" style={{ marginTop: 0, fontSize: 22 }}>{fmtPct(metrics!.cache_hit_rate)}</span>
                <span className="list-meta">hit rate</span>
              </div>
              <div
                className="meter"
                role="img"
                aria-label={`${hits} cache hits and ${misses} misses`}
              >
                {hits > 0 && <span style={{ width: `${(hits / total) * 100}%`, background: T.hit }} />}
                {misses > 0 && <span style={{ width: `${(misses / total) * 100}%`, background: T.miss }} />}
              </div>
              <div className="legend" style={{ marginTop: 8 }}>
                <LegendItem color={T.hit} label={`Hits ${fmtInt(hits)}`} />
                <LegendItem color={T.miss} label={`Misses ${fmtInt(misses)}`} />
              </div>
            </div>
          )}

          {cache && (
            <dl className="kv" style={{ margin: 0, gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
              <div><dt>Entries</dt><dd className="num">{fmtInt(cache.total_entries)}</dd></div>
              <div><dt>Total hits</dt><dd className="num">{fmtInt(cache.total_hits)}</dd></div>
              <div><dt>Saved</dt><dd className="num">{fmtCost(cache.total_saved_usd)}</dd></div>
            </dl>
          )}

          {cache && cache.top_cached.length > 0 && (
            <div>
              <div className="list-meta" style={{ marginBottom: 6 }}>Most reused prompts</div>
              <div className="list">
                {cache.top_cached.slice(0, 3).map((t, i) => (
                  <div key={i} className="list-row" style={{ alignItems: 'flex-start' }}>
                    <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 13 }} title={t.prompt_preview}>
                      {t.prompt_preview}
                    </span>
                    <span className="list-meta num" style={{ flexShrink: 0 }}>{fmtInt(t.hit_count)} hits</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
