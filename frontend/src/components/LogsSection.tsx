import { useState, useEffect, useCallback } from 'react'
import { apiFetch, extractApiError } from '../lib/api'
import { ERROR_MESSAGES } from '../lib/errors'
import { useAuth } from '../hooks/useAuth'
import { LoadingSpinner } from './LoadingSpinner'

interface LogEntry {
  timestamp: string | null
  service: string
  level: string
  module: string
  message: string
}

const LOG_SERVICES = [
  { id: '', display_name: 'All' },
  { id: 'audit', display_name: 'Audit' },
  { id: 'security', display_name: 'Security' },
  { id: 'backend', display_name: 'Backend' },
  { id: 'letta', display_name: 'Letta' },
  { id: 'postgres', display_name: 'Postgres' },
  { id: 'pip-sidecar', display_name: 'Pip Sidecar' },
]

const LOG_LEVELS = [
  { id: '', display_name: 'All' },
  { id: 'ERROR', display_name: 'Error' },
  { id: 'WARNING', display_name: 'Warning' },
  { id: 'INFO', display_name: 'Info' },
  { id: 'DEBUG', display_name: 'Debug' },
]

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'var(--text-tertiary)',
  INFO: 'var(--info)',
  WARNING: 'var(--warning)',
  ERROR: 'var(--danger)',
  CRITICAL: 'var(--danger-dim)',
}

export default function LogsSection() {
  const { isAuthenticated } = useAuth()
  const [logEntries, setLogEntries] = useState<LogEntry[]>([])
  const [logTotal, setLogTotal] = useState(0)
  const [logLoading, setLogLoading] = useState(false)
  const [logError, setLogError] = useState('')
  const [logService, setLogService] = useState('')
  const [logLevel, setLogLevel] = useState('')
  const [logSearch, setLogSearch] = useState('')
  const [logAutoRefresh, setLogAutoRefresh] = useState(false)
  const [logOffset, setLogOffset] = useState(0)
  const [exporting, setExporting] = useState(false)

  const fetchLogs = useCallback(async (offset = 0) => {
    if (!isAuthenticated) return
    setLogLoading(true)
    setLogError('')
    try {
      const params = new URLSearchParams()
      if (logService) params.set('service', logService)
      if (logLevel) params.set('level', logLevel)
      if (logSearch) params.set('search', logSearch)
      params.set('limit', '100')
      params.set('offset', String(offset))
      params.set('hours', '24')

      const res = await apiFetch(`/api/logs/?${params}`)
      if (res.ok) {
        const data = await res.json()
        if (offset === 0) {
          setLogEntries(data.entries)
        } else {
          setLogEntries(prev => [...prev, ...data.entries])
        }
        setLogTotal(data.total)
      } else {
        setLogError(await extractApiError(res, ERROR_MESSAGES.LOAD_LOGS))
      }
    } catch {
      setLogError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setLogLoading(false)
    }
  }, [isAuthenticated, logService, logLevel, logSearch])

  const exportLogs = useCallback(async () => {
    if (!isAuthenticated) return
    setExporting(true)
    try {
      const params = new URLSearchParams()
      if (logService) params.set('service', logService)
      if (logLevel) params.set('level', logLevel)
      if (logSearch) params.set('search', logSearch)
      params.set('hours', '24')

      const res = await apiFetch(`/api/logs/export?${params}`)
      if (res.ok) {
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        const disposition = res.headers.get('content-disposition') || ''
        const match = disposition.match(/filename="?([^"]+)"?/)
        a.download = match ? match[1] : 'delta_logs.csv'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
      }
    } catch {
      // Silently fail — export is a convenience feature
    } finally {
      setExporting(false)
    }
  }, [isAuthenticated, logService, logLevel, logSearch])

  // Fetch logs when filters change
  useEffect(() => {
    if (!isAuthenticated) return
    setLogOffset(0)  // Reset pagination when filters change
    fetchLogs(0)
  }, [isAuthenticated, fetchLogs, logService, logLevel, logSearch])

  // Auto-refresh
  useEffect(() => {
    if (!logAutoRefresh) return
    const interval = setInterval(() => fetchLogs(), 5000)
    return () => clearInterval(interval)
  }, [logAutoRefresh, fetchLogs])

  return (
    <div className="animate-fade-in">
      {logError && <div className="error mb-6">{logError}</div>}

      {/* Filters */}
      <div className="card mb-6">
        <div className="logs-filter-row">
          {/* Service filter */}
          <div>
            <label className="form-label logs-filter-label" htmlFor="field-logs-service">Service</label>
            <div className="pill-tabs gap-2 logs-filter-pills">
              {LOG_SERVICES.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={`pill-tab logs-filter-pill ${logService === s.id ? 'pill-tab-active' : ''}`}
                  onClick={() => setLogService(s.id)}
                >
                  {s.display_name}
                </button>
              ))}
            </div>
          </div>

          {/* Level filter */}
          <div>
            <label className="form-label logs-filter-label" htmlFor="field-logs-level">Level</label>
            <div className="pill-tabs gap-2 logs-filter-pills">
              {LOG_LEVELS.map((l) => (
                <button
                  key={l.id}
                  type="button"
                  className={`pill-tab logs-filter-pill ${logLevel === l.id ? 'pill-tab-active' : ''}`}
                  onClick={() => setLogLevel(l.id)}
                >
                  {l.display_name}
                </button>
              ))}
            </div>
          </div>

          {/* Search */}
          <div className="logs-search-field">
            <label className="form-label logs-filter-label" htmlFor="field-logs-search">Search</label>
            <input
              id="field-logs-search"
              type="text"
              className="input font-mono logs-search-input"
              aria-label="Search logs"
              value={logSearch}
              onChange={(e) => setLogSearch(e.target.value)}
              placeholder="Filter by text..."
            />
          </div>

          {/* Auto-refresh toggle */}
          <div className="logs-autorefresh-row">
            <label className="logs-autorefresh-label">
              <input
                type="checkbox"
                className="logs-autorefresh-checkbox"
                aria-label="Auto-refresh"
                checked={logAutoRefresh}
                onChange={(e) => setLogAutoRefresh(e.target.checked)}
              />
              Auto-refresh
            </label>
          </div>
        </div>
      </div>

      {/* Log count + export */}
      <div className="logs-count-bar">
        <span className="text-sm text-muted logs-count-text">
          {logTotal} {logTotal === 1 ? 'entry' : 'entries'}
        </span>
        <div className="logs-count-actions">
          <button
            className="btn btn-secondary btn-sm"
            onClick={exportLogs}
            disabled={exporting || logLoading}
          >
            {exporting ? 'Exporting...' : 'Export CSV'}
          </button>
          {logLoading && <LoadingSpinner />}
        </div>
      </div>

      {/* Log viewer */}
      <div className="card logs-viewer-card">
        <div className="logs-viewer-scroll">
          {logEntries.length === 0 && !logLoading ? (
            <div className="empty-state">
              No log entries found
            </div>
          ) : (
            logEntries.map((entry, i) => {
              const levelColor = LEVEL_COLORS[entry.level] || 'var(--text-tertiary)'
              const timeStr = entry.timestamp
                ? new Date(entry.timestamp).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                : '--:--:--'

              return (
                <div
                  key={`${entry.timestamp}-${i}`}
                  className="logs-entry"
                  style={{ backgroundColor: entry.level === 'ERROR' ? 'var(--danger-subtle)' : 'transparent' }}
                >
                  <span className="logs-timestamp">
                    {timeStr}
                  </span>
                  <span
                    className="logs-level-badge"
                    style={{ color: levelColor, backgroundColor: `${levelColor}15` }}
                  >
                    {entry.level}
                  </span>
                  <span className="logs-service-name">
                    {entry.service}
                  </span>
                  <span className="logs-message">
                    {entry.message}
                  </span>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* Load more */}
      {logEntries.length > 0 && logEntries.length < logTotal && (
        <div className="logs-load-more">
          <button
            className="btn btn-secondary"
            onClick={() => {
              const newOffset = logOffset + 100
              setLogOffset(newOffset)
              fetchLogs(newOffset)
            }}
            disabled={logLoading}
          >
            {logLoading ? 'Loading...' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  )
}
