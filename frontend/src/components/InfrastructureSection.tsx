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
  const dotClass =
    status === 'healthy'
      ? 'health-dot healthy'
      : status === 'unhealthy'
        ? 'health-dot unhealthy'
        : 'health-dot degraded'

  return <span className={dotClass} title={status} />
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
    <div>
      {/* Section header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <div>
          <h3 style={{ fontFamily: 'var(--font-sans)', fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Service Infrastructure
          </h3>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
            Connectivity status for all dependent services
          </p>
        </div>
        <button
          onClick={fetchHealth}
          disabled={loading}
          className="btn btn-sm btn-secondary"
        >
          {loading ? 'Checking...' : 'Refresh'}
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="alert-inline alert-inline-danger" style={{ marginBottom: '1rem' }}>
          {error}
        </div>
      )}

      {/* Health data */}
      {health && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {/* Overall status banner */}
          <div
            className={health.status === 'healthy' ? 'badge-success' : 'badge-warning'}
            style={{
              padding: '0.625rem 1rem',
              borderRadius: 'var(--radius-md)',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.75rem',
              letterSpacing: '0.02em',
            }}
          >
            {health.status === 'healthy' ? 'All systems operational' : 'Degraded — some services unavailable'}
          </div>

          {/* Per-service cards */}
          {Object.entries(health.services).map(([name, svc]) => (
            <div
              key={name}
              className="card"
              style={{ padding: '1rem 1.25rem' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                <StatusDot status={svc.status} />
                <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {SERVICE_LABELS[name] || name}
                </span>
                {svc.optional && (
                  <span className="badge badge-idle">optional</span>
                )}
                <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}
                  className={`health-status ${svc.status}`}
                >
                  {svc.status}
                </span>
              </div>

              {/* Status detail */}
              <div style={{ marginTop: '0.5rem', paddingLeft: '1.375rem' }}>
                {svc.status === 'healthy' && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    Healthy
                    {svc.version && (
                      <span style={{ marginLeft: '0.5rem', color: 'var(--text-tertiary)' }}>
                        v{svc.version}
                      </span>
                    )}
                  </span>
                )}
                {svc.status === 'unhealthy' && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--danger)' }}>
                    Unhealthy (HTTP {svc.status_code})
                  </span>
                )}
                {svc.status === 'unreachable' && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--danger)' }}>
                    Unreachable — service is not responding
                  </span>
                )}

                {/* Models list */}
                {svc.models && svc.models.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem', marginTop: '0.5rem' }}>
                    {svc.models.map((m) => (
                      <span key={m} className="badge badge-info">
                        {m}
                      </span>
                    ))}
                  </div>
                )}

                {/* Error message */}
                {svc.error && (
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', color: 'var(--danger)', marginTop: '0.375rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {svc.error}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Loading state */}
      {!health && !error && loading && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>
          Checking services...
        </div>
      )}
    </div>
  )
}
