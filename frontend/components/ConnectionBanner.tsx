import { AlertTriangle } from 'lucide-react'

// Shown instead of letting every panel quietly render zeros when the
// dashboard can't reach the backend — the reader should know the data is
// missing, not conclude the gateway has had no traffic.
export function ConnectionBanner({ message }: { message: string }) {
  return (
    <div className="banner" role="alert">
      <AlertTriangle size={18} className="banner-icon" aria-hidden />
      <div style={{ minWidth: 0 }}>
        <div className="banner-title">Live data is unavailable</div>
        <div className="banner-body">
          The dashboard can&apos;t reach the SentinelAI backend, so the panels below have nothing to show yet.
          It retries every 15 seconds.
        </div>
        <code className="banner-detail">{message}</code>
      </div>
    </div>
  )
}
