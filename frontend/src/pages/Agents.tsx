import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useRequireAuth } from '../hooks/useRequireAuth'
import { useConfirmDialog } from '../hooks/useConfirmDialog'
import { useEntityDelete } from '../hooks/useEntityDelete'
import { useOllamaStatus } from '../hooks/useOllamaStatus'

import { apiFetch, extractApiError } from '../lib/api'
import { ERROR_MESSAGES } from '../lib/errors'
import { LoadingSpinner } from '../components/LoadingSpinner'
import CustomSelect from '../components/CustomSelect'
import PolicyTab from '../components/PolicyTab'
import { Agent, Model, EmbeddingModel } from '../lib/types'

type DetailTab = 'details' | 'policy'



export default function Agents() {
  useRequireAuth()
  const navigate = useNavigate()
  const ollama = useOllamaStatus()
  const [models, setModels] = useState<Model[]>([])
  const [embeddingModels, setEmbeddingModels] = useState<EmbeddingModel[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)

  // Form state
  const [name, setName] = useState('')
  const [selectedModel, setSelectedModel] = useState('')
  const [selectedEmbedding, setSelectedEmbedding] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [fetchError, setFetchError] = useState('')
  const { confirm, dialog } = useConfirmDialog()

  const handleDelete = useEntityDelete(
    '/api/agents',
    (id) => setAgents(prev => prev.filter(a => a.id !== id)),
    confirm,
    'agent',
    (id) => { if (viewingAgent?.id === id) setViewingAgent(null) },
    (msg) => setError(msg),
  )

  // Detail/edit state
  const [viewingAgent, setViewingAgent] = useState<Agent | null>(null)
  const [detailTab, setDetailTab] = useState<DetailTab>('details')
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [saving, setSaving] = useState(false)
  const [editError, setEditError] = useState('')

  const fetchData = useCallback(async () => {
    try {
      const [modelsRes, embeddingRes, agentsRes] = await Promise.all([
        apiFetch('/api/agents/models'),
        apiFetch('/api/agents/embedding-models'),
        apiFetch('/api/agents/'),
      ])

      if (modelsRes.ok) {
        const modelsData = await modelsRes.json()
        setModels(modelsData)
        if (modelsData.length > 0) {
          setSelectedModel(modelsData[0].id)
        }
      } else {
        setFetchError('Failed to load models')
      }

      if (embeddingRes.ok) {
        const embeddingData = await embeddingRes.json()
        setEmbeddingModels(embeddingData)
        const defaultEmbedding = embeddingData.find((m: EmbeddingModel) => m.id === 'letta/letta-free')
        setSelectedEmbedding(defaultEmbedding?.id || embeddingData[0]?.id || '')
      } else {
        setFetchError('Failed to load embedding models')
      }

      if (agentsRes.ok) {
        setAgents(await agentsRes.json())
      } else {
        setFetchError(ERROR_MESSAGES.LOAD_AGENTS)
      }
    } catch {
      setFetchError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setCreating(true)

    try {
      const response = await apiFetch('/api/agents/', {
        method: 'POST',
        body: JSON.stringify({
          name,
          model: selectedModel,
          embedding_model: selectedEmbedding,
        }),
      })

      if (!response.ok) {
        setError(await extractApiError(response, 'Failed to create agent'))
        return
      }

      const newAgent = await response.json()
      setAgents(prev => [...prev, newAgent])
      setName('')
    } catch (_err) {
      setError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setCreating(false)
    }
  }

  const handleView = (agent: Agent) => {
    setViewingAgent(agent)
    setDetailTab('details')
    setEditing(false)
    setEditName(agent.name)
    setEditError('')
  }

  const handleSave = async () => {
    if (!viewingAgent || !editName.trim()) return
    setSaving(true)
    setEditError('')

    try {
      const res = await apiFetch(`/api/agents/${viewingAgent.id}`, {
        method: 'PUT',
        body: JSON.stringify({ name: editName.trim() }),
      })

      if (!res.ok) {
        setEditError(await extractApiError(res, 'Failed to update agent'))
        return
      }

      const updated = await res.json()
      setAgents(prev => prev.map(a => a.id === viewingAgent.id ? { ...a, name: updated.name } : a))
      setViewingAgent(prev => prev ? { ...prev, name: updated.name } : null)
      setEditing(false)
    } catch {
      setEditError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <LoadingSpinner />
  }

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="page-header animate-entry">
        <div>
          <h1 className="page-title-mockup" data-symbol="∈">Agents</h1>
          <p className="page-subtitle-mockup">∀ a ∈ Agents : monitor(a) → Δ(state)</p>
        </div>
      </div>

      {fetchError && <div className="error">{fetchError}</div>}

      {/* Ollama warning */}
      {!ollama.loading && !ollama.available && (
        <div style={{
          padding: '0.6rem 1rem',
          background: 'rgba(251, 191, 36, 0.1)',
          border: '1px solid rgba(251, 191, 36, 0.3)',
          marginBottom: '1rem',
          fontFamily: 'var(--font-sans)',
          fontSize: '0.75rem',
          color: '#FDB022',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
        }}>
          <span>Ollama is not running. Start Ollama to see available models and create agents.</span>
        </div>
      )}

      {/* Create Agent Form — collapsed inline */}
      <details className="agent-create-details" open={agents.length === 0}>
        <summary className="agent-create-summary">
          <span className="section-header" data-symbol="+">Create Agent</span>
        </summary>
        <div className="card agent-create-card">
          <form onSubmit={handleCreate} className="flex gap-3" style={{ alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div className="form-group" style={{ flex: '1 1 200px', marginBottom: 0 }}>
              <label className="form-label" htmlFor="field-agents-name">Name</label>
              <input
                id="field-agents-name"
                type="text"
                className="input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="security-agent"
                required
                aria-label="Agent name"
              />
            </div>
            <div className="form-group" style={{ flex: '1 1 200px', marginBottom: 0 }}>
              <label className="form-label" htmlFor="field-agents-model">LLM Model</label>
              <CustomSelect
                id="field-agents-model"
                value={selectedModel}
                onChange={setSelectedModel}
                options={models.map(m => ({
                  value: m.id,
                  label: `${m.name} (${m.provider})`,
                }))}
              />
            </div>
            <div className="form-group" style={{ flex: '1 1 200px', marginBottom: 0 }}>
              <label className="form-label" htmlFor="field-agents-embedding">Embedding</label>
              <CustomSelect
                id="field-agents-embedding"
                value={selectedEmbedding}
                onChange={setSelectedEmbedding}
                options={embeddingModels.map(m => ({
                  value: m.id,
                  label: `${m.name} (${m.provider})${m.dimensions ? ` - ${m.dimensions}d` : ''}`,
                }))}
              />
            </div>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={creating || !name}
              style={{ flexShrink: 0 }}
            >
              {creating ? 'Deploying...' : 'Deploy Agent'}
            </button>
          </form>
          {error && <div className="error mt-4">{error}</div>}
        </div>
      </details>

      {/* Agent List — table-style */}
      {agents.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem 1.5rem', marginTop: '1.5rem' }}>
          <p className="text-muted text-sm">No agents deployed yet. Create one above.</p>
        </div>
      ) : (
        <div className="agent-list" style={{ marginTop: '1.5rem' }}>
          {/* Header row */}
          <div className="agent-row agent-row-header">
            <span></span>
            <span>AGENT</span>
            <span>MODEL</span>
            <span>EMBEDDING</span>
            <span>CREATED</span>
            <span>ACTIONS</span>
          </div>

          {agents.map((agent) => (
            <div
              key={agent.id}
              className={`agent-row ${viewingAgent?.id === agent.id ? 'agent-row-selected' : ''}`}
              role="button"
              tabIndex={0}
              onClick={() => handleView(agent)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleView(agent) } }}
              style={viewingAgent?.id === agent.id ? { borderLeft: '2px solid var(--accent)' } : {}}
            >
              <div className="agent-status-dot active" />

              <div className="agent-name-cell">
                <div className="agent-name">{agent.name}</div>
                <div className="agent-id">{agent.letta_agent_id.slice(0, 12)}...</div>
              </div>

              <div className="agent-model">{agent.model}</div>

              <div className="agent-type">{agent.embedding}</div>

              <div className="agent-metric-cell">
                <div className="agent-metric-label">{new Date(agent.created_at).toLocaleDateString()}</div>
              </div>

              <div className="agent-actions">
                <button
                  className="action-btn"
                  title="Chat"
                  aria-label="Chat with agent"
                  onClick={(e) => { e.stopPropagation(); navigate('/chat') }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
                </button>
                <button
                  className="action-btn action-btn-danger"
                  title="Delete"
                  aria-label="Delete agent"
                  onClick={(e) => { e.stopPropagation(); handleDelete(agent.id, agent.name) }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail Panel */}
      {viewingAgent && (
        <div className="detail-panel animate-fade-in" style={{ marginTop: '1.5rem' }}>
          <div className="detail-header">
            <div>
              <div className="detail-title">{viewingAgent.name}</div>
              <div className="detail-subtitle">{viewingAgent.letta_agent_id}</div>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <span className="badge badge-success">Active</span>
              <div className="pill-tabs" style={{ marginBottom: 0 }}>
                <button
                  className={`pill-tab ${detailTab === 'details' ? 'pill-tab-active' : ''}`}
                  onClick={() => setDetailTab('details')}
                >
                  Details
                </button>
                <button
                  className={`pill-tab ${detailTab === 'policy' ? 'pill-tab-active' : ''}`}
                  onClick={() => setDetailTab('policy')}
                >
                  Policy
                </button>
              </div>
              {!editing ? (
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => { setEditing(true); setEditName(viewingAgent.name) }}
                >
                  Edit
                </button>
              ) : (
                <>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => { setEditing(false); setEditError('') }}
                    disabled={saving}
                  >
                    Cancel
                  </button>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleSave}
                    disabled={saving || !editName.trim()}
                  >
                    {saving ? 'Saving...' : 'Save'}
                  </button>
                </>
              )}
            </div>
          </div>

          {detailTab === 'details' && (
            <>
              {editError && <div className="error" style={{ margin: '1rem 1.5rem' }}>{editError}</div>}

              <div className="detail-grid">
                <div className="detail-cell">
                  <div className="detail-cell-label">Name</div>
                  <div className="detail-cell-value">
                    {editing ? (
                      <input
                        type="text"
                        className="input"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        style={{ fontSize: '0.85rem', padding: '0.25rem 0.5rem' }}
                        aria-label="Edit agent name"
                      />
                    ) : (
                      viewingAgent.name
                    )}
                  </div>
                </div>
                <div className="detail-cell">
                  <div className="detail-cell-label">Model</div>
                  <div className="detail-cell-value cyan">{viewingAgent.model}</div>
                </div>
                <div className="detail-cell">
                  <div className="detail-cell-label">Embedding</div>
                  <div className="detail-cell-value">{viewingAgent.embedding}</div>
                </div>
                <div className="detail-cell">
                  <div className="detail-cell-label">Agent ID</div>
                  <div className="detail-cell-value detail-id">{viewingAgent.id}</div>
                </div>
                <div className="detail-cell">
                  <div className="detail-cell-label">Letta ID</div>
                  <div className="detail-cell-value detail-id">{viewingAgent.letta_agent_id}</div>
                </div>
                <div className="detail-cell">
                  <div className="detail-cell-label">Created</div>
                  <div className="detail-cell-value">{new Date(viewingAgent.created_at).toLocaleString()}</div>
                </div>
              </div>
            </>
          )}

          {detailTab === 'policy' && (
            <div style={{ padding: '1.25rem 1.5rem' }}>
              <PolicyTab agentId={viewingAgent.id} />
            </div>
          )}
        </div>
      )}

      {dialog}
    </div>
  )
}
