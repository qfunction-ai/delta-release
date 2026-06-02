import { useState, useEffect, useCallback, useRef } from 'react'
import { useRequireAuth } from '../hooks/useRequireAuth'
import { useConfirmDialog } from '../hooks/useConfirmDialog'
import { useEntityDelete } from '../hooks/useEntityDelete'
import { useGithubImport } from '../hooks/useGithubImport'

import { apiFetch, extractApiError } from '../lib/api'
import { ERROR_MESSAGES } from '../lib/errors'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { parseTags, parsePipReqs, parseSchema } from './tools.utils'
import ToolForm, { DEFAULT_SOURCE_CODE } from '../components/ToolForm'
import ToolProposalList from '../components/ToolProposalList'
import { Tool, ToolDetail, ToolProposal } from '../lib/types'

export default function Tools() {
  useRequireAuth()
  const [tools, setTools] = useState<Tool[]>([])
  const [loading, setLoading] = useState(true)

  // Form state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [sourceCode, setSourceCode] = useState(DEFAULT_SOURCE_CODE)
  const [schemaJson, setSchemaJson] = useState('')
  const [tags, setTags] = useState('')
  const [pipReqs, setPipReqs] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const { confirm, dialog } = useConfirmDialog()

  const handleDelete = useEntityDelete(
    '/api/tools',
    (id) => setTools(prev => prev.filter(t => t.id !== id)),
    confirm,
    'tool',
    (id) => { if (viewingTool?.id === id) setViewingTool(null) },
    (msg) => setError(msg),
  )
  const [fetchError, setFetchError] = useState('')

  // GitHub import
  const { githubUrl, setGithubUrl, fetchingGithub, handleGithub } = useGithubImport({
    endpoint: '/api/tools/github',
    errorLabel: 'tool',
    onSuccess: (data) => setTools(prev => [...prev, data as Tool]),
    onError: (msg) => setError(msg),
  })

  // Active tab
  const [activeTab, setActiveTab] = useState<'manual' | 'github'>('github')

  // Proposals state
  const [proposals, setProposals] = useState<ToolProposal[]>([])
  const [viewingProposal, setViewingProposal] = useState<ToolProposal | null>(null)
  const [approving, setApproving] = useState(false)

  // View/edit state
  const [viewingTool, setViewingTool] = useState<ToolDetail | null>(null)
  const [editing, setEditing] = useState(false)

  const fetchTools = useCallback(async () => {
    try {
      const response = await apiFetch('/api/tools/')
      if (response.ok) {
        setTools(await response.json())
      } else {
        setFetchError(ERROR_MESSAGES.LOAD_TOOLS)
      }
    } catch {
      setFetchError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchProposals = useCallback(async () => {
    try {
      const response = await apiFetch('/api/tools/proposals')
      if (response.ok) {
        setProposals(await response.json())
      }
    } catch {
      // Non-fatal — proposals are supplementary data
    }
  }, [])

  useEffect(() => {
    fetchTools()
    fetchProposals()
  }, [fetchTools, fetchProposals])

  // Auto-generate schema from source code
  const schemaAbortRef = useRef<AbortController | null>(null)
  const generateSchema = useCallback(async (code: string) => {
    if (!code.trim() || !code.includes('def ')) return

    schemaAbortRef.current?.abort()
    const controller = new AbortController()
    schemaAbortRef.current = controller

    try {
      const response = await apiFetch('/api/tools/generate-schema', {
        method: 'POST',
        body: JSON.stringify({ source_code: code }),
        signal: controller.signal,
      })

      if (response.ok) {
        const schema = await response.json()
        setSchemaJson(JSON.stringify(schema, null, 2))
      }
    } catch (_err) {
      // Silently fail - user can still edit manually
    }
  }, [])

  // Generate schema when source code changes (debounced)
  useEffect(() => {
    const timer = setTimeout(() => {
      generateSchema(sourceCode)
    }, 500)
    return () => clearTimeout(timer)
  }, [sourceCode, generateSchema])

  const handleApproveProposal = async (proposalId: string) => {
    setApproving(true)
    try {
      const response = await apiFetch(`/api/tools/proposals/${proposalId}/approve`, {
        method: 'POST',
      })
      if (response.ok) {
        const newTool = await response.json()
        setTools(prev => [...prev, newTool])
        setProposals(prev => prev.filter(p => p.id !== proposalId))
        setViewingProposal(null)
      } else {
        setError(await extractApiError(response, 'Failed to approve tool'))
      }
    } catch {
      setError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setApproving(false)
    }
  }

  const handleRejectProposal = async (proposalId: string) => {
    try {
      const response = await apiFetch(`/api/tools/proposals/${proposalId}/reject`, {
        method: 'POST',
      })
      if (response.ok) {
        setProposals(prev => prev.filter(p => p.id !== proposalId))
        setViewingProposal(null)
      }
    } catch {
      // Non-fatal — rejection is best-effort
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setCreating(true)

    const schemaResult = parseSchema(schemaJson)
    if (!schemaResult.ok) {
      setError(schemaResult.error)
      setCreating(false)
      return
    }

    try {
      const response = await apiFetch('/api/tools/', {
        method: 'POST',
        body: JSON.stringify({
          name,
          description,
          source_code: sourceCode,
          json_schema: schemaResult.value,
          tags: parseTags(tags),
          pip_requirements: parsePipReqs(pipReqs),
        }),
      })

      if (!response.ok) {
        setError(await extractApiError(response, 'Failed to create tool'))
        return
      }

      const newTool = await response.json()
      setTools(prev => [...prev, newTool])
      setName('')
      setDescription('')
      setSourceCode(DEFAULT_SOURCE_CODE)
      setTags('')
      setPipReqs('')
    } catch (_err) {
      setError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setCreating(false)
    }
  }

  const handleView = async (toolId: string) => {
    try {
      const response = await apiFetch(`/api/tools/${toolId}`)
      if (response.ok) {
        setViewingTool(await response.json())
        setEditing(false)
      }
    } catch {
      setError('Failed to load tool details.')
    }
  }

  const handleUpdate = async () => {
    if (!viewingTool) return
    setError('')

    const schemaResult = parseSchema(
      typeof viewingTool.json_schema === 'string'
        ? viewingTool.json_schema as string
        : JSON.stringify(viewingTool.json_schema)
    )
    if (!schemaResult.ok) {
      setError(schemaResult.error)
      return
    }

    try {
      const response = await apiFetch(`/api/tools/${viewingTool.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          source_code: viewingTool.source_code,
          json_schema: schemaResult.value,
          pip_requirements: viewingTool.pip_requirements,
          name: viewingTool.name,
          description: viewingTool.description,
          tags: viewingTool.tags,
        }),
      })

      if (!response.ok) {
        setError(await extractApiError(response, 'Failed to update tool'))
        return
      }

      const updated = await response.json()
      setTools(prev => prev.map(t => t.id === updated.id ? { ...t, ...updated } : t))
      setEditing(false)
    } catch (_err) {
      setError(ERROR_MESSAGES.CONNECTION)
    }
  }

  if (loading) {
    return <LoadingSpinner />
  }

  return (
    <div className="animate-fade-in">
      {/* Page header */}
      <div className="page-header">
        <h1 className="page-title-mockup" data-symbol="ƒ">TOOLS</h1>
        <p className="page-subtitle-mockup">ƒ(tools) → ∪(actions) | define → attach → execute</p>
      </div>

      {fetchError && <div className="error">{fetchError}</div>}

      <div className="two-column">
        {/* Left column: Create + List */}
        <div className="flex flex-col gap-6">
          <ToolForm
            activeTab={activeTab}
            onTabChange={(tab) => { setActiveTab(tab); setError('') }}
            name={name}
            setName={setName}
            description={description}
            setDescription={setDescription}
            sourceCode={sourceCode}
            setSourceCode={setSourceCode}
            tags={tags}
            setTags={setTags}
            pipReqs={pipReqs}
            setPipReqs={setPipReqs}
            githubUrl={githubUrl}
            setGithubUrl={setGithubUrl}
            error={error}
            creating={creating}
            fetchingGithub={fetchingGithub}
            onCreate={handleCreate}
            onGithub={handleGithub}
          />

          {/* Tools List */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="section-header" data-symbol="ƒ">Your Tools</h2>
              <div className="flex items-center gap-3">
                {proposals.length > 0 && (
                  <button
                    className="badge badge-warning"
                    style={{ cursor: 'pointer', border: 'none' }}
                    onClick={() => setViewingProposal(viewingProposal ? null : proposals[0])}
                  >
                    {proposals.length} pending review
                  </button>
                )}
                <span className="badge badge-accent">{tools.length}</span>
              </div>
            </div>

            <ToolProposalList
              proposals={proposals}
              viewingProposal={viewingProposal}
              onViewProposal={setViewingProposal}
              onClose={() => setViewingProposal(null)}
              onApprove={handleApproveProposal}
              onReject={handleRejectProposal}
              approving={approving}
              error={error}
            />

            {tools.length === 0 ? (
              <div className="card">
                <p className="text-sm text-muted">No tools yet. Create one above.</p>
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                {tools.map((tool) => (
                  <div
                    key={tool.id}
                    className={`card card-interactive ${viewingTool?.id === tool.id ? 'card-selected' : ''}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => handleView(tool.id)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleView(tool.id) } }}
                  >
                    <div className="flex items-center justify-between">
                      <div style={{ minWidth: 0 }}>
                        <div className="flex items-center gap-4 mb-2">
                          <h3 className="font-mono" style={{ margin: 0 }}>{tool.name}</h3>
                          <span className={`badge ${tool.source === 'github' ? 'badge-success' : 'badge-info'}`}>
                            {tool.source}
                          </span>
                        </div>
                        {tool.description && (
                          <p className="text-sm text-muted" style={{ marginBottom: '0.375rem' }}>{tool.description}</p>
                        )}
                        {tool.tags && tool.tags.length > 0 && (
                          <div className="flex gap-2">
                            {tool.tags.map(tag => (
                              <span key={tag} className="badge badge-accent">{tag}</span>
                            ))}
                          </div>
                        )}
                      </div>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={(e) => { e.stopPropagation(); handleDelete(tool.id, tool.name) }}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right column: View/Edit */}
        <div>
          {viewingTool && (
            <div className="card animate-fade-in">
              <div className="flex items-center justify-between mb-4">
                <div style={{ flex: 1, minWidth: 0 }}>
                  {editing ? (
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label className="form-label" htmlFor="field-tools-edit-name">Name</label>
                      <input
                        id="field-tools-edit-name"
                        type="text"
                        className="input font-mono"
                        value={viewingTool.name}
                        onChange={(e) => setViewingTool(prev => prev ? { ...prev, name: e.target.value } : prev)}
                        aria-label="Tool name"
                      />
                    </div>
                  ) : (
                    <h2 className="font-mono" style={{ margin: 0, marginBottom: '0.25rem' }}>{viewingTool.name}</h2>
                  )}
                </div>
                <div className="flex gap-2" style={{ marginLeft: '1rem', flexShrink: 0 }}>
                  {editing ? (
                    <>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={handleUpdate}
                      >
                        Save
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => { setEditing(false); handleView(viewingTool.id) }}
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => setEditing(true)}
                    >
                      Edit
                    </button>
                  )}
                </div>
              </div>

              {/* Description */}
              {editing ? (
                <div className="form-group">
                  <label className="form-label" htmlFor="field-tools-edit-description">Description</label>
                  <input
                    id="field-tools-edit-description"
                    type="text"
                    className="input"
                    value={viewingTool.description || ''}
                    onChange={(e) => setViewingTool(prev => prev ? { ...prev, description: e.target.value } : prev)}
                    placeholder="Tool description"
                    aria-label="Tool description"
                  />
                </div>
              ) : (
                viewingTool.description && (
                  <p className="text-sm text-muted mb-4">{viewingTool.description}</p>
                )
              )}

              {/* Source Code Section */}
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs text-tertiary font-mono">{'// source'}</span>
                </div>
                {editing ? (
                  <textarea
                    className="input font-mono"
                    value={viewingTool.source_code}
                    onChange={(e) => setViewingTool(prev => prev ? { ...prev, source_code: e.target.value } : prev)}
                    rows={14}
                    style={{ fontSize: '0.8125rem', lineHeight: '1.6' }}
                    aria-label="Source code"
                  />
                ) : (
                  <pre className="code-block">
                    {viewingTool.source_code}
                  </pre>
                )}
              </div>

              {/* Pip Requirements Section */}
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs text-tertiary font-mono">{'// pip_requirements'}</span>
                </div>
                {editing ? (
                  <input
                    type="text"
                    className="input font-mono"
                    value={viewingTool.pip_requirements?.join(', ') || ''}
                    onChange={(e) => setViewingTool(prev => prev ? {
                      ...prev,
                      pip_requirements: e.target.value ? e.target.value.split(',').map(p => p.trim()).filter(p => p) : null
                    } : prev)}
                    placeholder="requests, paramiko==2.12.0"
                    aria-label="Pip requirements"
                  />
                ) : (
                  viewingTool.pip_requirements && viewingTool.pip_requirements.length > 0 ? (
                    <div className="flex gap-2 flex-wrap">
                      {viewingTool.pip_requirements.map(req => (
                        <span key={req} className="badge" style={{ background: 'var(--indigo-subtle)', color: 'var(--indigo)', border: '1px solid var(--indigo-border)' }}>
                          {req}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-sm text-tertiary">None</span>
                  )
                )}
              </div>

              {/* Tags */}
              <div className="mb-4">
                <span className="text-xs text-tertiary font-mono" style={{ display: 'block', marginBottom: '0.5rem' }}>
                  {'// tags'}
                </span>
                {editing ? (
                  <input
                    type="text"
                    className="input"
                    value={viewingTool.tags?.join(', ') || ''}
                    onChange={(e) => setViewingTool(prev => prev ? {
                      ...prev,
                      tags: e.target.value ? e.target.value.split(',').map(t => t.trim()).filter(t => t) : []
                    } : prev)}
                    placeholder="tag1, tag2, tag3"
                    aria-label="Tags"
                  />
                ) : (
                  viewingTool.tags && viewingTool.tags.length > 0 ? (
                    <div className="flex gap-2">
                      {viewingTool.tags.map(tag => (
                        <span key={tag} className="badge badge-accent">{tag}</span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-sm text-tertiary">None</span>
                  )
                )}
              </div>

              {error && <div className="error mt-4">{error}</div>}
            </div>
          )}

          {!viewingTool && (
            <div className="card" style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: '300px',
              textAlign: 'center',
            }}>
              <p className="text-sm text-muted">Select a tool to view its source.</p>
              <p className="text-xs text-tertiary mt-2 font-mono">click a tool card ←</p>
            </div>
          )}
        </div>
      </div>

      {dialog}
    </div>
  )
}
