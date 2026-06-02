import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../lib/api'

interface ServiceStatus {
  status: 'healthy' | 'unhealthy' | 'unreachable'
  error?: string
  status_code?: number
  version?: string
  models?: string[]
  optional?: boolean
}

interface HealthResponse {
  status: 'healthy' | 'degraded'
  services: Record<string, ServiceStatus>
}

const SERVICE_LABELS: Record<string, string> = {
  postgres: 'PostgreSQL',
  letta: 'Letta Agent Server',
  ollama: 'Ollama (Local LLM)',
  eval: 'Eval Service',
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === 'healthy'
      ? 'bg-emerald-400'
      : status === 'unhealthy'
        ? 'bg-amber-400'
        : 'bg-red-400'

  return (
    <span
      className={`inline-block w-2.5 h-2.5 rounded-full ${color}`}
      title={status}
    />
  )
}

export default function InfrastructureSection() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchHealth = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await apiFetch('/api/health/detailed')
      if (res.ok) {
        setHealth(await res.json())
      } else {
        setError('Failed to load service status')
      }
    } catch {
      setError('Cannot reach backend')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchHealth()
  }, [fetchHealth])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-mono font-semibold text-[var(--text-primary)]">
            Service Infrastructure
          </h3>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            Connectivity status for all dependent services
          </p>
        </div>
        <button
          onClick={fetchHealth}
          disabled={loading}
          className="text-xs font-mono px-3 py-1.5 rounded border border-[var(--border-primary)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors disabled:opacity-50"
        >
          {loading ? 'Checking...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="p-3 rounded border border-red-500/30 bg-red-500/10 text-red-400 text-xs font-mono">
          {error}
        </div>
      )}

      {health && (
        <div className="space-y-3">
          {/* Overall status */}
          <div
            className={`p-3 rounded border font-mono text-xs ${
              health.status === 'healthy'
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                : 'border-amber-500/30 bg-amber-500/10 text-amber-400'
            }`}
          >
            Overall: {health.status === 'healthy' ? 'All systems operational' : 'Degraded — some services unavailable'}
          </div>

          {/* Per-service status */}
          <div className="space-y-2">
            {Object.entries(health.services).map(([name, svc]) => (
              <div
                key={name}
                className="flex items-start gap-3 p-3 rounded border border-[var(--border-primary)] bg-[var(--bg-secondary)]"
              >
                <StatusDot status={svc.status} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-semibold text-[var(--text-primary)]">
                      {SERVICE_LABELS[name] || name}
                    </span>
                    {svc.optional && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-muted)]">
                        optional
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] font-mono text-[var(--text-muted)] mt-0.5">
                    {svc.status === 'healthy' && (
                      <>
                        Healthy
                        {svc.version && (
                          <span className="ml-2 text-[var(--text-secondary)]">
                            v{svc.version}
                          </span>
                        )}
                      </>
                    )}
                    {svc.status === 'unhealthy' && (
                      <>Unhealthy (HTTP {svc.status_code})</>
                    )}
                    {svc.status === 'unreachable' && (
                      <>Unreachable — service is not responding</>
                    )}
                  </div>
                  {svc.models && svc.models.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-1.5">
                      {svc.models.map((m) => (
                        <span
                          key={m}
                          className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)]"
                        >
                          {m}
                        </span>
                      ))}
                    </div>
                  )}
                  {svc.error && (
                    <div className="text-[10px] font-mono text-red-400 mt-1 truncate">
                      {svc.error}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!health && !error && loading && (
        <div className="text-xs font-mono text-[var(--text-muted)] animate-pulse">
          Checking services...
        </div>
      )}
    </div>
  )
}
