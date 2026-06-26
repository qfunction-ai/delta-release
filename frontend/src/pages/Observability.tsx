import { useState, useEffect, useCallback } from 'react'
import { useRequireAuth } from '../hooks/useRequireAuth'
import { useApiFetch } from '../hooks/useApiFetch'
import { apiFetch } from '../lib/api'
import { ObservabilityRun } from '../lib/types'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { relativeTime, fmtTime, fmtTokens, formatNs, msToHuman, statusBadge, levelBadge } from '../lib/formatters'

type Tab = 'overview' | 'runs' | 'tool-calls' | 'security'

interface OverviewData {
  total_runs: number
  completed_runs: number
  failed_runs: number
  success_rate: number
  avg_step_ms: number | null
  total_prompt_tokens: number
  total_completion_tokens: number
  total_tool_calls: number
  total_security_events: number
}

function OverviewTab() {
  const { data, loading, error, refetch } = useApiFetch<OverviewData>('/api/observability/overview')

  if (loading && !data) return <LoadingSpinner />
  if (error) return <div className="error">{error}</div>
  if (!data) return null

  const stats = [
    { label: 'Total Runs', value: data.total_runs, color: 'var(--accent)' },
    { label: 'Success Rate', value: `${(data.success_rate * 100).toFixed(1)}%`, color: data.success_rate >= 0.9 ? 'var(--success)' : 'var(--warning)' },
    { label: 'Avg Step Latency', value: msToHuman(data.avg_step_ms), color: 'var(--accent)' },
    { label: 'Prompt Tokens', value: fmtTokens(data.total_prompt_tokens), color: 'var(--info)' },
    { label: 'Completion Tokens', value: fmtTokens(data.total_completion_tokens), color: 'var(--info)' },
    { label: 'Tool Calls', value: data.total_tool_calls, color: 'var(--accent)' },
    { label: 'Security Events', value: data.total_security_events, color: data.total_security_events > 0 ? 'var(--danger)' : 'var(--success)' },
  ]

  return (
    <div className="animate-fade-in">
      <div className="stats-grid">
        {stats.map(s => (
          <div key={s.label} className="stat-card obs-stat-card-default">
            <div className="stat-value" style={{ color: s.color }}>{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </div>
      <div className="obs-refresh-row">
        <button className="btn btn-secondary btn-sm" onClick={() => refetch()}>Refresh</button>
      </div>
    </div>
  )
}

interface Step {
  id: string
  agent_id: string | null
  model: string | null
  model_handle: string | null
  completion_tokens: number | null
  prompt_tokens: number | null
  total_tokens: number | null
  stop_reason: string | null
  status: string | null
  error_type: string | null
  created_at: string | null
}

interface StepMetrics {
  id: string
  step_ns: number | null
  llm_request_ns: number | null
  tool_execution_ns: number | null
}

interface TraceSpan {
  span_id: string
  parent_span_id: string | null
  operation_name: string
  start_time_us: number
  duration_us: number
  tags: Record<string, string>
  has_children: boolean
}

interface TraceData {
  trace_id: string | null
  spans: TraceSpan[]
}

function spanColor(op: string): string {
  if (op.startsWith('GET ') || op.startsWith('POST ') || op.startsWith('PUT ') || op.startsWith('PATCH ') || op.startsWith('DELETE ')) return 'var(--info)'
  if (op.startsWith('agent_step') || op.startsWith('time_to_first_token')) return 'var(--accent)'
  if (op.includes('tool') || op.includes('_execute_tool')) return 'var(--success)'
  if (op.includes('OpenAI') || op.includes('llm_request') || op.includes('LLM')) return '#a78bfa'
  if (op.includes('redis_cache')) return 'var(--text-tertiary)'
  if (op.startsWith('middleware') || op.startsWith('trace.') || op.startsWith('dependency.') || op.startsWith('coroutine.')) return 'var(--text-tertiary)'
  return 'var(--text-secondary)'
}

function buildSpanTree(spans: TraceSpan[]): { span: TraceSpan; depth: number }[] {
  const childMap = new Map<string, TraceSpan[]>()
  const spanMap = new Map<string, TraceSpan>()
  const roots: TraceSpan[] = []

  for (const s of spans) {
    spanMap.set(s.span_id, s)
    if (s.parent_span_id && spanMap.has(s.parent_span_id)) {
      const children = childMap.get(s.parent_span_id) || []
      children.push(s)
      childMap.set(s.parent_span_id, children)
    } else if (!s.parent_span_id) {
      roots.push(s)
    }
  }

  // Second pass: spans whose parent isn't in the set become roots
  for (const s of spans) {
    if (s.parent_span_id && !spanMap.has(s.parent_span_id) && !roots.includes(s)) {
      roots.push(s)
    }
  }

  const result: { span: TraceSpan; depth: number }[] = []

  function walk(span: TraceSpan, depth: number) {
    result.push({ span, depth })
    const children = childMap.get(span.span_id) || []
    children.sort((a, b) => a.start_time_us - b.start_time_us)
    for (const c of children) walk(c, depth + 1)
  }

  roots.sort((a, b) => a.start_time_us - b.start_time_us)
  for (const r of roots) walk(r, 0)

  return result
}

function TraceWaterfall({ spans }: { spans: TraceSpan[] }) {
  const [expandedSpan, setExpandedSpan] = useState<string | null>(null)

  if (spans.length === 0) return null

  const tree = buildSpanTree(spans)
  const minTime = Math.min(...spans.map(s => s.start_time_us))
  const maxTime = Math.max(...spans.map(s => s.start_time_us + s.duration_us))
  const totalDuration = maxTime - minTime || 1

  return (
    <div className="obs-trace-container">
      <h4 className="obs-trace-heading">
        Trace Waterfall ({spans.length} spans)
      </h4>
      <div className="obs-trace-body">
        {tree.map(({ span, depth }) => {
          const leftPct = ((span.start_time_us - minTime) / totalDuration) * 100
          const widthPct = Math.max((span.duration_us / totalDuration) * 100, 0.2)
          const durMs = span.duration_us / 1000
          const color = spanColor(span.operation_name)
          const isExpanded = expandedSpan === span.span_id

          return (
            <div key={span.span_id} className="obs-trace-row">
              <div
                className="obs-trace-row-inner"
                style={{ cursor: span.tags && Object.keys(span.tags).length > 0 ? 'pointer' : 'default' }}
                role="button"
                tabIndex={0}
                onClick={() => {
                  if (span.tags && Object.keys(span.tags).length > 0) {
                    setExpandedSpan(isExpanded ? null : span.span_id)
                  }
                }}
                onKeyDown={(e) => {
                  if (span.tags && Object.keys(span.tags).length > 0 && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault()
                    setExpandedSpan(isExpanded ? null : span.span_id)
                  }
                }}
              >
                {/* Operation name with indentation */}
                <div className="obs-trace-op-name" style={{ paddingLeft: `${depth * 12}px`, color }}>
                  {span.has_children ? (isExpanded ? '▼ ' : '▶ ') : '  '}
                  {span.operation_name}
                </div>
                {/* Duration bar */}
                <div className="obs-trace-bar-track">
                  <div
                    className="obs-trace-bar-fill"
                    style={{ left: `${leftPct}%`, width: `${widthPct}%`, background: color }}
                  />
                </div>
                {/* Duration text */}
                <div className="obs-trace-duration">
                  {durMs < 1 ? `${(durMs * 1000).toFixed(0)}μs` : durMs < 1000 ? `${durMs.toFixed(1)}ms` : `${(durMs / 1000).toFixed(2)}s`}
                </div>
              </div>
              {/* Expanded tags */}
              {isExpanded && span.tags && Object.keys(span.tags).length > 0 && (
                <div className="obs-trace-tags" style={{ paddingLeft: `${(depth + 1) * 12}px` }}>
                  {Object.entries(span.tags).map(([k, v]) => (
                    <div key={k}><span className="obs-trace-tag-key">{k}</span>: {String(v)}</div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function RunsTab() {
  const [runs, setRuns] = useState<ObservabilityRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expandedRun, setExpandedRun] = useState<string | null>(null)
  const [steps, setSteps] = useState<Step[]>([])
  const [stepsLoading, setStepsLoading] = useState(false)
  const [stepMetrics, setStepMetrics] = useState<Record<string, StepMetrics>>({})
  const [traceData, setTraceData] = useState<TraceData | null>(null)
  const [traceLoading, setTraceLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('')

  const fetchRuns = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      let url = '/api/observability/runs?limit=50'
      if (statusFilter) url += `&statuses=${statusFilter}`
      const res = await apiFetch(url)
      if (res.ok) {
        const data = await res.json()
        setRuns(Array.isArray(data) ? data : [])
      } else {
        setError('Failed to load runs')
      }
    } catch {
      setError('Connection error')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { fetchRuns() }, [fetchRuns])

  const expandRun = async (runId: string) => {
    if (expandedRun === runId) {
      setExpandedRun(null)
      return
    }
    setExpandedRun(runId)
    setStepsLoading(true)
    setStepMetrics({})
    setTraceData(null)
    setTraceLoading(true)
    try {
      const res = await apiFetch(`/api/observability/runs/${runId}/steps?limit=100`)
      if (res.ok) {
        const data = await res.json()
        const stepList = Array.isArray(data) ? data : []
        setSteps(stepList)
        const metricsMap: Record<string, StepMetrics> = {}
        await Promise.all(stepList.map(async (s: Step) => {
          try {
            const mr = await apiFetch(`/api/observability/steps/${s.id}/metrics`)
            if (mr.ok) {
              const md = await mr.json()
              if (md && md.id) metricsMap[s.id] = md
            }
          } catch { /* skip */ }
        }))
        setStepMetrics(metricsMap)
      }
    } catch { /* skip */ }
    setStepsLoading(false)

    try {
      const tr = await apiFetch(`/api/observability/runs/${runId}/trace`)
      if (tr.ok) {
        setTraceData(await tr.json())
      }
    } catch { /* skip */ }
    setTraceLoading(false)
  }

  if (loading && runs.length === 0) return <LoadingSpinner />
  if (error) return <div className="error">{error}</div>

  return (
    <div className="animate-fade-in">
      <div className="obs-filter-bar">
        <span className="obs-filter-label">Status:</span>
        {['', 'completed', 'failed', 'running'].map(s => (
          <button
            key={s}
            className={`btn btn-sm ${statusFilter === s ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setStatusFilter(s)}
          >
            {s || 'All'}
          </button>
        ))}
        <div className="obs-spacer" />
        <button className="btn btn-secondary btn-sm" onClick={fetchRuns}>Refresh</button>
      </div>

      {runs.length === 0 ? (
        <div className="empty-state">No runs found</div>
      ) : (
        <div className="row-list">
          {runs.map(run => (
            <div key={run.id}>
              <div
                className="row-item"
                role="button"
                tabIndex={0}
                onClick={() => expandRun(run.id)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); expandRun(run.id) } }}
              >
                <div className="obs-run-left">
                  {statusBadge(run.status)}
                  <span className="obs-run-id">
                    {run.id.slice(0, 16)}
                  </span>
                  <span className="obs-run-time">
                    {relativeTime(run.created_at)}
                  </span>
                </div>
                <div className="obs-run-right">
                  {run.total_duration_ns != null && (
                    <span className="obs-run-duration">{formatNs(run.total_duration_ns)}</span>
                  )}
                  {run.stop_reason && (
                    <span className="badge badge-info obs-badge-small">{run.stop_reason}</span>
                  )}
                  <span style={{ color: expandedRun === run.id ? 'var(--accent)' : 'var(--text-tertiary)' }}>
                    {expandedRun === run.id ? '▼' : '▶'}
                  </span>
                </div>
              </div>

              {expandedRun === run.id && (
                <div className="obs-step-detail">
                  {stepsLoading ? (
                    <LoadingSpinner />
                  ) : steps.length === 0 ? (
                    <div className="obs-no-steps">No steps recorded</div>
                  ) : (
                    <table className="obs-table">
                      <thead>
                        <tr className="obs-thead-row">
                          <th className="obs-th-left-sm">Step</th>
                          <th className="obs-th-left-sm">Model</th>
                          <th className="obs-th-right-sm">Prompt</th>
                          <th className="obs-th-right-sm">Completion</th>
                          <th className="obs-th-right-sm">LLM</th>
                          <th className="obs-th-right-sm">Tool</th>
                          <th className="obs-th-right-sm">Total</th>
                          <th className="obs-th-left-sm">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {steps.map(step => {
                          const m = stepMetrics[step.id]
                          return (
                            <tr key={step.id} className="obs-tbody-row">
                              <td className="obs-td-step-id">
                                {step.id.slice(0, 12)}
                              </td>
                              <td className="obs-td-model">
                                {step.model_handle || step.model || '—'}
                              </td>
                              <td className="obs-td-right-sm">
                                {fmtTokens(step.prompt_tokens)}
                              </td>
                              <td className="obs-td-right-sm">
                                {fmtTokens(step.completion_tokens)}
                              </td>
                              <td className="obs-td-right-sm">
                                {m?.llm_request_ns ? formatNs(m.llm_request_ns) : '—'}
                              </td>
                              <td className="obs-td-right-sm">
                                {m?.tool_execution_ns ? formatNs(m.tool_execution_ns) : '—'}
                              </td>
                              <td className="obs-td-right-sm">
                                {m?.step_ns ? formatNs(m.step_ns) : '—'}
                              </td>
                              <td className="obs-td-status-sm">
                                {step.status ? statusBadge(step.status) : '—'}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  )}
                  {/* Trace waterfall */}
                  {traceLoading ? (
                    <div className="obs-loading-msg">Loading trace...</div>
                  ) : traceData && traceData.spans.length > 0 ? (
                    <TraceWaterfall spans={traceData.spans} />
                  ) : traceData && !traceData.trace_id ? (
                    <div className="obs-loading-msg">No trace data available</div>
                  ) : null}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

interface ToolCall {
  id: string
  step_id: string
  agent_id: string | null
  tool_name: string
  duration_ms: number | null
  success: boolean
  error: string | null
  created_at: string | null
}

function ToolCallsTab() {
  const [calls, setCalls] = useState<ToolCall[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toolFilter, setToolFilter] = useState('')
  const [successFilter, setSuccessFilter] = useState<string>('')

  const fetchCalls = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      let url = '/api/observability/tool-calls?limit=100'
      if (toolFilter) url += `&tool_name=${encodeURIComponent(toolFilter)}`
      if (successFilter === 'true') url += '&success=true'
      else if (successFilter === 'false') url += '&success=false'
      const res = await apiFetch(url)
      if (res.ok) {
        const data = await res.json()
        setCalls(data?.tool_calls || [])
      } else {
        setError('Failed to load tool calls')
      }
    } catch {
      setError('Connection error')
    } finally {
      setLoading(false)
    }
  }, [toolFilter, successFilter])

  useEffect(() => { fetchCalls() }, [fetchCalls])

  if (loading && calls.length === 0) return <LoadingSpinner />
  if (error) return <div className="error">{error}</div>

  return (
    <div className="animate-fade-in">
      <div className="obs-filter-bar">
        <span className="obs-filter-label">Tool:</span>
        <input
          className="input obs-input-filter"
          placeholder="Filter by tool name"
          value={toolFilter}
          onChange={e => setToolFilter(e.target.value)}
          aria-label="Filter by tool name"
        />
        <span className="obs-filter-label-ml">Result:</span>
        {['', 'true', 'false'].map(s => (
          <button
            key={s}
            className={`btn btn-sm ${successFilter === s ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setSuccessFilter(s)}
          >
            {s === '' ? 'All' : s === 'true' ? 'Success' : 'Failed'}
          </button>
        ))}
        <div className="obs-spacer" />
        <button className="btn btn-secondary btn-sm" onClick={fetchCalls}>Refresh</button>
      </div>

      {calls.length === 0 ? (
        <div className="empty-state">No tool calls found</div>
      ) : (
        <table className="obs-table">
          <thead>
            <tr className="obs-thead-row">
              <th className="obs-th-left">Tool</th>
              <th className="obs-th-left">Agent</th>
              <th className="obs-th-right">Duration</th>
              <th className="obs-th-center">Result</th>
              <th className="obs-th-left">Error</th>
              <th className="obs-th-left">Time</th>
            </tr>
          </thead>
          <tbody>
            {calls.map(tc => (
              <tr key={tc.id} className="obs-tbody-row">
                <td className="obs-td-tool-name">
                  {tc.tool_name}
                </td>
                <td className="obs-td-agent-id">
                  {tc.agent_id ? tc.agent_id.slice(0, 16) : '—'}
                </td>
                <td className="obs-td-right">
                  {msToHuman(tc.duration_ms)}
                </td>
                <td className="obs-td-center">
                  {tc.success
                    ? <span className="badge badge-success">OK</span>
                    : <span className="badge badge-danger">FAIL</span>
                  }
                </td>
                <td className="obs-td-error">
                  {tc.error || '—'}
                </td>
                <td className="obs-td-muted">
                  {relativeTime(tc.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

interface SecurityEvent {
  id: string
  agent_id: string
  event_type: string
  event_data: Record<string, unknown> | null
  created_at: string | null
}

function SecurityTab() {
  const [events, setEvents] = useState<SecurityEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  const fetchEvents = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      let url = '/api/observability/security-events?limit=100'
      if (typeFilter) url += `&event_type=${encodeURIComponent(typeFilter)}`
      const res = await apiFetch(url)
      if (res.ok) {
        const data = await res.json()
        setEvents(data?.events || [])
      } else {
        setError('Failed to load security events')
      }
    } catch {
      setError('Connection error')
    } finally {
      setLoading(false)
    }
  }, [typeFilter])

  useEffect(() => { fetchEvents() }, [fetchEvents])

  const eventLevel = (type: string) => {
    if (['tool_denied', 'policy_violation', 'canary_detected', 'canary_output_detected'].includes(type)) return 'ERROR'
    if (['tool_approval_requested', 'tool_approval_denied'].includes(type)) return 'WARNING'
    return 'INFO'
  }

  if (loading && events.length === 0) return <LoadingSpinner />
  if (error) return <div className="error">{error}</div>

  return (
    <div className="animate-fade-in">
      <div className="obs-filter-bar">
        <span className="obs-filter-label">Type:</span>
        {['', 'tool_executed', 'tool_denied', 'policy_violation', 'canary_output_detected', 'tool_approval_requested'].map(t => (
          <button
            key={t}
            className={`btn btn-sm ${typeFilter === t ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setTypeFilter(t)}
          >
            {t || 'All'}
          </button>
        ))}
        <div className="obs-spacer" />
        <button className="btn btn-secondary btn-sm" onClick={fetchEvents}>Refresh</button>
      </div>

      {events.length === 0 ? (
        <div className="empty-state">No security events found</div>
      ) : (
        <table className="obs-table">
          <thead>
            <tr className="obs-thead-row">
              <th className="obs-th-left">Time</th>
              <th className="obs-th-left">Level</th>
              <th className="obs-th-left">Type</th>
              <th className="obs-th-left">Tool</th>
              <th className="obs-th-left">Agent</th>
            </tr>
          </thead>
          <tbody>
            {events.map(ev => {
              const level = eventLevel(ev.event_type)
              const toolName = (ev.event_data as Record<string, string>)?.tool_name || '—'
              return (
                <tr key={ev.id} className="obs-tbody-row">
                  <td className="obs-td-muted">
                    {fmtTime(ev.created_at)}
                  </td>
                  <td className="obs-td-default">
                    {levelBadge(level)}
                  </td>
                  <td className="obs-td-tool-name">
                    {ev.event_type}
                  </td>
                  <td className="obs-td-secondary">
                    {toolName}
                  </td>
                  <td className="obs-td-agent-id">
                    {ev.agent_id ? ev.agent_id.slice(0, 16) : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default function Observability() {
  useRequireAuth()
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  const tabs: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'runs', label: 'Runs' },
    { id: 'tool-calls', label: 'Tool Calls' },
    { id: 'security', label: 'Security' },
  ]

  return (
    <div className="animate-fade-in">
      <div className="page-header animate-entry">
        <h1 className="page-title-mockup" data-symbol="∇">Observability</h1>
        <p className="page-subtitle-mockup">∇(events) → awareness</p>
      </div>

      <div className="pill-tabs obs-pill-tabs">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`pill-tab ${activeTab === tab.id ? 'pill-tab-active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && <OverviewTab />}
      {activeTab === 'runs' && <RunsTab />}
      {activeTab === 'tool-calls' && <ToolCallsTab />}
      {activeTab === 'security' && <SecurityTab />}
    </div>
  )
}
