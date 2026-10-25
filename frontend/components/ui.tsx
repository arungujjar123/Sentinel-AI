import type { ReactNode } from 'react'
import { AlertTriangle, Check, CircleDashed, X } from 'lucide-react'
import { T } from '@/lib/theme'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>
}

export function CardHead({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <div className="card-head">
      <div>
        <h2 className="card-title" style={{ margin: 0 }}>{title}</h2>
        {sub && <div className="card-sub">{sub}</div>}
      </div>
      {right}
    </div>
  )
}

export function Empty({ children, minHeight }: { children: ReactNode; minHeight?: number }) {
  return <div className="empty" style={minHeight ? { minHeight } : undefined}>{children}</div>
}

export type Status = 'good' | 'warning' | 'serious' | 'critical' | 'neutral'

const STATUS_COLOR: Record<Status, string> = {
  good: T.good,
  warning: T.warning,
  serious: T.serious,
  critical: T.critical,
  neutral: T.ink3,
}

const STATUS_ICON: Record<Status, typeof Check> = {
  good: Check,
  warning: CircleDashed,
  serious: AlertTriangle,
  critical: X,
  neutral: CircleDashed,
}

// Status is never carried by color alone: every badge pairs the status
// color with an icon and a text label.
export function StatusBadge({ status, label }: { status: Status; label: string }) {
  const Icon = STATUS_ICON[status]
  const color = STATUS_COLOR[status]
  return (
    <span className="badge" style={{ borderColor: `${color}55`, background: `${color}14` }}>
      <Icon size={12} color={color} strokeWidth={2.5} aria-hidden />
      {label}
    </span>
  )
}

// Identity tag (provider, cache hit/miss): swatch carries the hue, text stays ink.
export function Tag({ color, label }: { color: string; label: string }) {
  return (
    <span className="badge">
      <span className="swatch" style={{ background: color, width: 8, height: 8, borderRadius: 2 }} aria-hidden />
      {label}
    </span>
  )
}

export function LegendItem({ color, label, round }: { color: string; label: string; round?: boolean }) {
  return (
    <span className="legend-item">
      <span className="swatch" style={{ background: color, borderRadius: round ? '50%' : 3 }} aria-hidden />
      {label}
    </span>
  )
}
