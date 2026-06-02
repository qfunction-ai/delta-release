/**
 * Time, duration, and token formatters.
 * Pure functions — no side effects, no state.
 * All functions are null-safe: pass null/undefined to get '—'.
 */

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    const now = Date.now()
    const diff = now - d.getTime()
    if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
    return `${Math.floor(diff / 86_400_000)}d ago`
  } catch {
    return iso
  }
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString()
  } catch {
    return iso
  }
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

/** Format nanoseconds to human-readable duration. */
export function formatNs(ns: number | null | undefined): string {
  if (ns == null) return '—'
  if (ns < 1_000_000) return `${(ns / 1_000).toFixed(1)}μs`
  if (ns < 1_000_000_000) return `${(ns / 1_000_000).toFixed(1)}ms`
  return `${(ns / 1_000_000_000).toFixed(2)}s`
}

/** Format milliseconds to human-readable duration. */
export function msToHuman(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms.toFixed(1)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

export function fmtTokens(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n < 1000) return String(n)
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`
  return `${(n / 1_000_000).toFixed(2)}M`
}

export function statusBadge(status: string) {
  const cls = status === 'completed' ? 'badge-success'
    : status === 'failed' ? 'badge-danger'
    : status === 'running' ? 'badge-info'
    : 'badge-warning'
  return <span className={`badge ${cls}`}>{status}</span>
}

export function levelBadge(level: string) {
  const cls = level === 'ERROR' ? 'badge-danger'
    : level === 'WARNING' ? 'badge-warning'
    : 'badge-info'
  return <span className={`badge ${cls}`}>{level}</span>
}
