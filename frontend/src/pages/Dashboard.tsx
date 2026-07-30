import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { useRequireAuth } from '../hooks/useRequireAuth'
import { useApiFetch } from '../hooks/useApiFetch'

import { ERROR_MESSAGES } from '../lib/errors'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { relativeTime } from '../lib/formatters'
import { DashboardData } from '../lib/types'

function ConcentricCircles() {
  return (
    <svg className="agent-geo" viewBox="0 0 100 100" style={{ position: 'absolute', top: 0, right: 0, width: 100, height: 100, opacity: 0.08, color: 'var(--accent)', pointerEvents: 'none' }} aria-hidden="true">
      <circle cx="50" cy="50" r="45" fill="none" stroke="currentColor" strokeWidth="0.5" />
      <circle cx="50" cy="50" r="30" fill="none" stroke="currentColor" strokeWidth="0.5" />
      <circle cx="50" cy="50" r="15" fill="none" stroke="currentColor" strokeWidth="0.5" />
    </svg>
  )
}

export default function Dashboard() {
  useRequireAuth()
  const navigate = useNavigate()
  const { loading: authLoading } = useAuth()
  const { data, loading, error } = useApiFetch<DashboardData>('/api/dashboard/', {
    errorMessage: 'Failed to load dashboard',
    connectionErrorMessage: ERROR_MESSAGES.CONNECTION,
  })

  if (authLoading || loading) return <LoadingSpinner />

  if (error) return (
    <div className="animate-fade-in">
      <div className="error">{error}</div>
    </div>
  )

  if (!data) return <LoadingSpinner />

  const statCards = [
    { key: 'agents', label: 'Active Agents', count: data.stats.agents, path: '/agents' },
    { key: 'tools', label: 'Tools Available', count: data.stats.tools, path: '/tools' },
    { key: 'skills', label: 'Skills Loaded', count: data.stats.skills, path: '/skills' },
    { key: 'workflows', label: 'Workflows', count: data.stats.workflows, path: '/workflows' },
  ]

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="page-header animate-entry">
        <h1 className="page-title-mockup" data-symbol="Ω">Dashboard</h1>
        <p className="page-subtitle-mockup">f(x) = monitor → analyze → respond</p>
      </div>

      {/* Stats Grid (4 columns) */}
      <div className="stats-grid-4">
        {statCards.map(({ key, label, count, path }, i) => (
          <button
            key={key}
            className={`stat-card-mockup animate-stagger stagger-${i + 1}`}
            onClick={() => navigate(path)}
            style={{ cursor: 'pointer', textAlign: 'left', width: '100%' }}
          >
            <div className="stat-label-mockup">{label}</div>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: '0.5rem' }}>
              <div className="stat-value-mockup" style={{ color: 'var(--accent)' }}>{count}</div>
            </div>
          </button>
        ))}
      </div>

      {/* Agent Fleet */}
      <div className="animate-entry" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: '1rem', fontWeight: 600, color: 'var(--accent)' }}>Agent Fleet</div>
      </div>

      {data.agents.length === 0 ? (
        <div className="card dash-empty-card">
          <p className="text-sm text-muted dash-empty-text">No agents yet</p>
          <button className="btn btn-primary" onClick={() => navigate('/agents')}>Create Agent</button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
          {data.agents.slice(0, 4).map((agent) => (
            <div
              key={agent.id}
              className="card"
              role="button"
              tabIndex={0}
              onClick={() => navigate('/agents')}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate('/agents') } }}
              style={{
                cursor: 'pointer',
                padding: '1.5rem',
                position: 'relative',
                overflow: 'hidden',
              }}
            >
              <ConcentricCircles />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem', position: 'relative', zIndex: 1 }}>
                <div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)' }}>{agent.name}</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>{agent.model}</div>
                </div>
                <div style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: agent.has_schedule ? 'var(--accent)' : 'var(--text-tertiary)',
                }} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginTop: '1.25rem', position: 'relative', zIndex: 1 }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>⚡ Workflows</div>
                  <div style={{ fontFamily: 'var(--font-serif)', fontSize: '1.1rem', fontWeight: 400, color: 'var(--text-primary)', marginTop: '0.15rem' }}>{agent.workflows_count}</div>
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>📅 Scheduled</div>
                  <div style={{ fontFamily: 'var(--font-serif)', fontSize: '1.1rem', fontWeight: 400, color: agent.has_schedule ? 'var(--success)' : 'var(--text-tertiary)', marginTop: '0.15rem' }}>{agent.has_schedule ? 'Yes' : 'No'}</div>
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>🕐 Active</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9rem', fontWeight: 400, color: 'var(--text-primary)', marginTop: '0.15rem' }}>{relativeTime(agent.last_activity)}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {data.agents.length > 4 && (
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <button className="btn btn-secondary" onClick={() => navigate('/agents')}>View all {data.agents.length} agents →</button>
        </div>
      )}

    </div>
  )
}
