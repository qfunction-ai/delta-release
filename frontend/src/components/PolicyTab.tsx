import { useCallback, useEffect, useState } from 'react'
import { apiFetch, extractApiError } from '../lib/api'
import { LoadingSpinner } from './LoadingSpinner'
import type { ToolCallPolicy, PolicyRule, PolicyDecision } from '../lib/types'

const ACTIONS = ['allow', 'deny', 'require_approval', 'audit'] as const
const OPERATORS = ['eq', 'ne', 'gt', 'lt', 'gte', 'lte', 'in', 'not_in', 'matches', 'contains'] as const
const CONDITION_FIELDS = ['tool_name', 'tool_args', 'tool_call_count', 'actor_id', 'agent_id'] as const

interface Props {
  agentId: string
}

export default function PolicyTab({ agentId }: Props) {
  const [policy, setPolicy] = useState<ToolCallPolicy | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  // Evaluate state
  const [evalToolName, setEvalToolName] = useState('')
  const [evalToolArgs, setEvalToolArgs] = useState('')
  const [evalResult, setEvalResult] = useState<PolicyDecision | null>(null)
  const [evaluating, setEvaluating] = useState(false)
  const [evalError, setEvalError] = useState('')

  // Edit state for denied/approval tools
  const [newDeniedTool, setNewDeniedTool] = useState('')
  const [newApprovalTool, setNewApprovalTool] = useState('')

  // Edit state for rate limits
  const [newRateTool, setNewRateTool] = useState('')
  const [newRateLimit, setNewRateLimit] = useState('')

  // Edit state for rules
  const [newRule, setNewRule] = useState<PolicyRule>({
    name: '',
    condition: { field: 'tool_name', operator: 'eq', value: '' },
    action: 'deny',
    priority: 0,
    message: null,
    pattern: null,
  })

  const loadPolicy = useCallback(async () => {
    setLoading(true)
    setFetchError('')
    try {
      const res = await apiFetch(`/api/agents/${agentId}/policy`)
      if (res.ok) {
        setPolicy(await res.json())
      } else {
        setFetchError(await extractApiError(res, 'Failed to load policy'))
      }
    } catch {
      setFetchError('Connection error')
    } finally {
      setLoading(false)
    }
  }, [agentId])

  useEffect(() => {
    loadPolicy()
  }, [loadPolicy])

  async function patchPolicy(patch: Record<string, unknown>) {
    if (!policy) return
    setSaving(true)
    setSaveError('')
    try {
      const res = await apiFetch(`/api/agents/${agentId}/policy`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      })
      if (res.ok) {
        setPolicy(await res.json())
      } else {
        setSaveError(await extractApiError(res, 'Failed to update policy'))
      }
    } catch {
      setSaveError('Connection error')
    } finally {
      setSaving(false)
    }
  }

  async function deletePolicy() {
    setSaving(true)
    setSaveError('')
    try {
      const res = await apiFetch(`/api/agents/${agentId}/policy`, {
        method: 'DELETE',
      })
      if (res.ok) {
        setPolicy(await res.json())
      } else {
        setSaveError(await extractApiError(res, 'Failed to reset policy'))
      }
    } catch {
      setSaveError('Connection error')
    } finally {
      setSaving(false)
    }
  }

  async function evaluate() {
    if (!evalToolName.trim()) return
    setEvaluating(true)
    setEvalError('')
    setEvalResult(null)
    try {
      let toolArgs: Record<string, unknown> | undefined
      if (evalToolArgs.trim()) {
        try {
          toolArgs = JSON.parse(evalToolArgs)
        } catch {
          setEvalError('Invalid JSON in tool_args')
          setEvaluating(false)
          return
        }
      }
      const res = await apiFetch(`/api/agents/${agentId}/policy/evaluate`, {
        method: 'POST',
        body: JSON.stringify({ tool_name: evalToolName.trim(), tool_args: toolArgs }),
      })
      if (res.ok) {
        setEvalResult(await res.json())
      } else {
        setEvalError(await extractApiError(res, 'Evaluation failed'))
      }
    } catch {
      setEvalError('Connection error')
    } finally {
      setEvaluating(false)
    }
  }

  function addDeniedTool() {
    if (!policy || !newDeniedTool.trim()) return
    const tool = newDeniedTool.trim()
    if (policy.denied_tools.includes(tool)) return
    patchPolicy({ denied_tools: [...policy.denied_tools, tool] })
    setNewDeniedTool('')
  }

  function removeDeniedTool(tool: string) {
    if (!policy) return
    patchPolicy({ denied_tools: policy.denied_tools.filter(t => t !== tool) })
  }

  function addApprovalTool() {
    if (!policy || !newApprovalTool.trim()) return
    const tool = newApprovalTool.trim()
    if (policy.approval_required_tools.includes(tool)) return
    patchPolicy({ approval_required_tools: [...policy.approval_required_tools, tool] })
    setNewApprovalTool('')
  }

  function removeApprovalTool(tool: string) {
    if (!policy) return
    patchPolicy({ approval_required_tools: policy.approval_required_tools.filter(t => t !== tool) })
  }

  function addRateLimit() {
    if (!policy || !newRateTool.trim() || !newRateLimit.trim()) return
    const tool = newRateTool.trim()
    const limit = parseInt(newRateLimit.trim(), 10)
    if (isNaN(limit) || limit < 1) return
    patchPolicy({ max_calls_per_tool: { ...policy.max_calls_per_tool, [tool]: limit } })
    setNewRateTool('')
    setNewRateLimit('')
  }

  function removeRateLimit(tool: string) {
    if (!policy) return
    const updated = { ...policy.max_calls_per_tool }
    delete updated[tool]
    patchPolicy({ max_calls_per_tool: updated })
  }

  function addRule() {
    if (!policy || !newRule.name.trim()) return
    patchPolicy({ rules: [...policy.rules, { ...newRule }] })
    setNewRule({
      name: '',
      condition: { field: 'tool_name', operator: 'eq', value: '' },
      action: 'deny',
      priority: 0,
      message: null,
      pattern: null,
    })
  }

  function removeRule(index: number) {
    if (!policy) return
    patchPolicy({ rules: policy.rules.filter((_, i) => i !== index) })
  }

  if (loading) return <LoadingSpinner />
  if (fetchError) return <div className="error">{fetchError}</div>
  if (!policy) return null

  return (
    <div className="animate-fade-in">
      {saveError && <div className="error mb-4">{saveError}</div>}

      {/* Denied Tools */}
      <div className="card mb-6">
        <h3 className="section-header" data-symbol="⊘">Denied Tools</h3>
        <p className="text-sm text-muted mb-4">Tools that are always blocked by the security policy.</p>

        {policy.denied_tools.length > 0 ? (
          <div className="gap-2" style={{ display: 'grid', marginBottom: '1rem' }}>
            {policy.denied_tools.map(tool => (
              <div key={tool} className="flex items-center justify-between policy-list-item">
                <span className="font-mono text-sm">{tool}</span>
                <button className="btn btn-danger btn-sm" onClick={() => removeDeniedTool(tool)} disabled={saving}>Remove</button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted mb-4">No denied tools. All tools are allowed by default.</p>
        )}

        <div className="flex gap-2">
          <input
            type="text"
            className="input"
            placeholder="Add denied tool..."
            aria-label="Add denied tool"
            value={newDeniedTool}
            onChange={e => setNewDeniedTool(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addDeniedTool()}
            disabled={saving}
          />
          <button className="btn btn-secondary" onClick={addDeniedTool} disabled={saving || !newDeniedTool.trim()}>Add</button>
        </div>
      </div>

      {/* Approval-Required Tools */}
      <div className="card mb-6">
        <h3 className="section-header" data-symbol="⚠">Approval Required</h3>
        <p className="text-sm text-muted mb-4">Tools that require human approval before execution.</p>

        {policy.approval_required_tools.length > 0 ? (
          <div className="gap-2" style={{ display: 'grid', marginBottom: '1rem' }}>
            {policy.approval_required_tools.map(tool => (
              <div key={tool} className="flex items-center justify-between policy-list-item">
                <span className="font-mono text-sm">{tool}</span>
                <button className="btn btn-danger btn-sm" onClick={() => removeApprovalTool(tool)} disabled={saving}>Remove</button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted mb-4">No tools require approval.</p>
        )}

        <div className="flex gap-2">
          <input
            type="text"
            className="input"
            placeholder="Add approval tool..."
            aria-label="Add approval tool"
            value={newApprovalTool}
            onChange={e => setNewApprovalTool(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addApprovalTool()}
            disabled={saving}
          />
          <button className="btn btn-secondary" onClick={addApprovalTool} disabled={saving || !newApprovalTool.trim()}>Add</button>
        </div>
      </div>

      {/* Rules */}
      <div className="card mb-6">
        <h3 className="section-header" data-symbol="∀">Policy Rules</h3>
        <p className="text-sm text-muted mb-4">Ordered rules with conditions, actions, and priorities. Higher priority rules override lower ones.</p>

        {policy.rules.length > 0 ? (
          <div style={{ display: 'grid', gap: '0.75rem', marginBottom: '1rem' }}>
            {policy.rules.map((rule, i) => (
              <div key={i} style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)', borderLeft: `3px solid ${rule.action === 'deny' ? 'var(--danger)' : rule.action === 'require_approval' ? 'var(--warning)' : 'var(--accent)'}` }}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm">{rule.name}</span>
                    <span className="badge" style={{ background: rule.action === 'deny' ? 'var(--danger)' : rule.action === 'require_approval' ? 'var(--warning)' : 'var(--accent)', color: '#fff', fontSize: '0.7rem', padding: '0.125rem 0.5rem' }}>
                      {rule.action}
                    </span>
                    <span className="text-xs text-muted">priority: {rule.priority}</span>
                  </div>
                  <button className="btn btn-danger btn-sm" onClick={() => removeRule(i)} disabled={saving}>Remove</button>
                </div>
                <p className="text-xs text-muted font-mono">
                  {rule.condition.field} {rule.condition.operator} {JSON.stringify(rule.condition.value)}
                </p>
                {rule.message && <p className="text-xs text-secondary mt-1">{rule.message}</p>}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted mb-4">No policy rules configured.</p>
        )}

        {/* Add rule form */}
        <div style={{ padding: '0.75rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}>
          <p className="text-sm font-semibold mb-3">Add Rule</p>
          <div style={{ display: 'grid', gap: '0.5rem' }}>
            <input
              type="text"
              className="input"
              placeholder="Rule name"
              aria-label="Rule name"
              value={newRule.name}
              onChange={e => setNewRule({ ...newRule, name: e.target.value })}
              disabled={saving}
            />
            <div className="flex gap-2">
              <select
                className="input"
                value={newRule.condition.field}
                onChange={e => setNewRule({ ...newRule, condition: { ...newRule.condition, field: e.target.value } })}
                disabled={saving}
              >
                {CONDITION_FIELDS.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
              <select
                className="input"
                value={newRule.condition.operator}
                onChange={e => setNewRule({ ...newRule, condition: { ...newRule.condition, operator: e.target.value } })}
                disabled={saving}
              >
                {OPERATORS.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
              <input
                type="text"
                className="input"
                placeholder="Value"
                aria-label="Condition value"
                value={String(newRule.condition.value)}
                onChange={e => setNewRule({ ...newRule, condition: { ...newRule.condition, value: e.target.value } })}
                disabled={saving}
              />
            </div>
            <div className="flex gap-2">
              <select
                className="input"
                value={newRule.action}
                onChange={e => setNewRule({ ...newRule, action: e.target.value })}
                disabled={saving}
              >
                {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
              <input
                type="number"
                className="input"
                placeholder="Priority"
                aria-label="Priority"
                value={newRule.priority}
                onChange={e => setNewRule({ ...newRule, priority: parseInt(e.target.value, 10) || 0 })}
                disabled={saving}
                style={{ width: '5rem' }}
              />
              <input
                type="text"
                className="input"
                placeholder="Message (optional)"
                aria-label="Message (optional)"
                value={newRule.message || ''}
                onChange={e => setNewRule({ ...newRule, message: e.target.value || null })}
                disabled={saving}
              />
            </div>
            <button className="btn btn-secondary" onClick={addRule} disabled={saving || !newRule.name.trim()}>Add Rule</button>
          </div>
        </div>
      </div>

      {/* Rate Limits */}
      <div className="card mb-6">
        <h3 className="section-header" data-symbol="⏱">Rate Limits</h3>
        <p className="text-sm text-muted mb-4">Per-tool per-run call limits. Overrides the global default.</p>

        {Object.keys(policy.max_calls_per_tool).length > 0 ? (
          <div className="gap-2" style={{ display: 'grid', marginBottom: '1rem' }}>
            {Object.entries(policy.max_calls_per_tool).map(([tool, limit]) => (
              <div key={tool} className="flex items-center justify-between policy-list-item">
                <span className="font-mono text-sm">{tool}</span>
                <div className="flex items-center gap-2">
                  <span className="badge badge-info">{limit} calls/run</span>
                  <button className="btn btn-danger btn-sm" onClick={() => removeRateLimit(tool)} disabled={saving}>Remove</button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted mb-4">No per-tool rate limits configured.</p>
        )}

        <div className="flex gap-2">
          <input
            type="text"
            className="input"
            placeholder="Tool name"
            aria-label="Tool name for rate limit"
            value={newRateTool}
            onChange={e => setNewRateTool(e.target.value)}
            disabled={saving}
          />
          <input
            type="number"
            className="input"
            placeholder="Max calls"
            aria-label="Max calls for rate limit"
            value={newRateLimit}
            onChange={e => setNewRateLimit(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addRateLimit()}
            disabled={saving}
            style={{ width: '8rem' }}
          />
          <button className="btn btn-secondary" onClick={addRateLimit} disabled={saving || !newRateTool.trim() || !newRateLimit.trim()}>Add</button>
        </div>
      </div>

      {/* Defaults */}
      <div className="card mb-6">
        <h3 className="section-header" data-symbol="∗">Defaults</h3>
        <p className="text-sm text-muted mb-4">Default policy settings when no rule matches.</p>

        <div style={{ display: 'grid', gap: '0.75rem' }}>
          <div className="form-group">
            <label className="form-label" htmlFor="field-policy-default-action">Default Action</label>
            <select
              id="field-policy-default-action"
              className="input"
              value={policy.defaults?.action || 'allow'}
              onChange={e => {
                const newDefaults = { action: e.target.value, max_tool_calls: policy.defaults?.max_tool_calls ?? null, max_tokens: null, timeout_seconds: null }
                patchPolicy({ defaults: newDefaults })
              }}
              disabled={saving}
            >
              {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="field-policy-max-tool-calls">Max Tool Calls (per run)</label>
            <input
              id="field-policy-max-tool-calls"
              type="number"
              className="input"
              placeholder="No limit"
              aria-label="Max Tool Calls (per run)"
              value={policy.defaults?.max_tool_calls ?? ''}
              onChange={e => {
                const val = e.target.value ? parseInt(e.target.value, 10) : null
                const newDefaults = { action: policy.defaults?.action || 'allow', max_tool_calls: val, max_tokens: null, timeout_seconds: null }
                patchPolicy({ defaults: newDefaults })
              }}
              disabled={saving}
            />
          </div>
        </div>
      </div>

      {/* Evaluate Panel */}
      <div className="card mb-6">
        <h3 className="section-header" data-symbol="?">Evaluate</h3>
        <p className="text-sm text-muted mb-4">Dry-run a tool call against the current policy without executing it.</p>

        <div className="gap-2" style={{ display: 'grid', marginBottom: '1rem' }}>
          <input
            type="text"
            className="input"
            placeholder="Tool to evaluate..."
            aria-label="Tool to evaluate"
            value={evalToolName}
            onChange={e => setEvalToolName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && evaluate()}
            disabled={evaluating}
          />
          <textarea
            className="input font-mono"
            placeholder='Tool arguments (JSON, e.g. {"query": "test"})'
            aria-label="Tool arguments (JSON)"
            value={evalToolArgs}
            onChange={e => setEvalToolArgs(e.target.value)}
            rows={3}
            disabled={evaluating}
            style={{ fontSize: '0.8rem', resize: 'vertical' }}
          />
          <button className="btn btn-primary" onClick={evaluate} disabled={evaluating || !evalToolName.trim()}>
            {evaluating ? 'Evaluating...' : 'Evaluate'}
          </button>
        </div>

        {evalError && <div className="error mb-4">{evalError}</div>}

        {evalResult && (
          <div style={{
            padding: '0.75rem',
            borderRadius: 'var(--radius-sm)',
            borderLeft: `3px solid ${evalResult.allowed ? 'var(--success)' : evalResult.action === 'require_approval' ? 'var(--warning)' : 'var(--danger)'}`,
            background: evalResult.allowed ? 'rgba(34, 197, 94, 0.08)' : evalResult.action === 'require_approval' ? 'rgba(234, 179, 8, 0.08)' : 'rgba(239, 68, 68, 0.08)',
          }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="font-semibold text-sm" style={{ color: evalResult.allowed ? 'var(--success)' : evalResult.action === 'require_approval' ? 'var(--warning)' : 'var(--danger)' }}>
                {evalResult.action.toUpperCase()}
              </span>
              <span className="text-xs text-muted">
                {evalResult.matched_rule ? `matched: ${evalResult.matched_rule}` : 'no rule matched'}
              </span>
            </div>
            <p className="text-sm">{evalResult.reason}</p>
          </div>
        )}
      </div>

      {/* Reset */}
      <div className="flex justify-end">
        <button className="btn btn-danger" onClick={deletePolicy} disabled={saving}>
          Reset to Default (Allow All)
        </button>
      </div>
    </div>
  )
}
