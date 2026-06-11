import { useState, useEffect, useCallback, useMemo } from 'react'
import { apiFetch } from '../lib/api'
import { ERROR_MESSAGES } from '../lib/errors'
import { useRequireAuth } from '../hooks/useRequireAuth'
import { useConfirmDialog } from '../hooks/useConfirmDialog'
import { useEntityDelete } from '../hooks/useEntityDelete'
import { Agent, Tool, Skill, Workflow, Lesson, WorkflowDetail } from '../lib/types'
import WorkflowForm from '../components/WorkflowForm'
import WorkflowRunViewer from '../components/WorkflowRunViewer'
import { LoadingSpinner } from '../components/LoadingSpinner'

export default function Workflows() {
  useRequireAuth()
  const [agents, setAgents] = useState<Agent[]>([])
  const [tools, setTools] = useState<Tool[]>([])
  const [skills, setSkills] = useState<Skill[]>([])
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [loading, setLoading] = useState(true)
  const [allLessons, setAllLessons] = useState<Lesson[]>([])
  const [error, setError] = useState('')

  const lessonsByWorkflow = useMemo(() => {
    const map = new Map<string, Lesson[]>()
    for (const l of allLessons) {
      const list = map.get(l.workflow_id) || []
      list.push(l)
      map.set(l.workflow_id, list)
    }
    return map
  }, [allLessons])
  const { confirm, dialog } = useConfirmDialog()

  // View state — which workflow is selected
  const [viewingWorkflow, setViewingWorkflow] = useState<WorkflowDetail | null>(null)

  const handleDelete = useEntityDelete(
    '/api/workflows',
    (id) => setWorkflows(prev => prev.filter(w => w.id !== id)),
    confirm,
    'workflow',
    (id) => { if (viewingWorkflow?.id === id) setViewingWorkflow(null) },
    (msg) => setError(msg),
  )

  const fetchData = useCallback(async () => {
    try {
      const [agentsRes, toolsRes, skillsRes, workflowsRes, lessonsRes] = await Promise.all([
        apiFetch('/api/agents/'),
        apiFetch('/api/tools/'),
        apiFetch('/api/skills/'),
        apiFetch('/api/workflows/'),
        apiFetch('/api/lessons/'),
      ])

      if (agentsRes.ok) setAgents(await agentsRes.json())
      if (toolsRes.ok) setTools(await toolsRes.json())
      if (skillsRes.ok) setSkills(await skillsRes.json())
      if (workflowsRes.ok) setWorkflows(await workflowsRes.json())
      if (lessonsRes.ok) {
        const lessonsData = await lessonsRes.json()
        setAllLessons(lessonsData.lessons || [])
      }
    } catch {
      setError(ERROR_MESSAGES.LOAD_WORKFLOWS)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleView = async (workflowId: string) => {
    try {
      const response = await apiFetch(`/api/workflows/${workflowId}`)
      if (response.ok) {
        setViewingWorkflow(await response.json())
      }
    } catch {
      setError('Failed to load workflow details.')
    }
  }

  const handleWorkflowCreated = (newWorkflow: Workflow) => {
    setWorkflows(prev => [...prev, newWorkflow])
  }

  const handleWorkflowUpdated = useCallback(() => {
    if (viewingWorkflow) {
      handleView(viewingWorkflow.id)
    }
  }, [viewingWorkflow])

  if (loading) return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
      <LoadingSpinner />
    </div>
  )

  return (
    <div className="animate-fade-in">
      <div className="page-header animate-entry">
        <h1 className="page-title-mockup" data-symbol="∫">Workflows</h1>
        <p className="page-subtitle-mockup">∫[t₀→t₁] f(agent, tools, skills) dt → Δ(automation)</p>
      </div>

      <div className="two-column">
        {/* Left column: Create + List */}
        <div>
          <WorkflowForm
            agents={agents}
            tools={tools}
            skills={skills}
            onCreated={handleWorkflowCreated}
          />

          {/* Workflows List */}
          <h2 className="section-header" data-symbol="∫">Your Workflows</h2>

          {workflows.length === 0 ? (
            <div className="card">
              <p className="text-sm text-muted">No workflows yet. Create one above.</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: '0.75rem' }}>
              {workflows.map((workflow) => (
                <div
                  key={workflow.id}
                  className={`card card-interactive${viewingWorkflow?.id === workflow.id ? ' card-selected' : ''}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleView(workflow.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleView(workflow.id) } }}
                >
                  <div className="flex justify-between items-center">
                    <div style={{ minWidth: 0 }}>
                      <h3 className="font-mono" style={{ marginBottom: '0.25rem' }}>{workflow.name}</h3>
                      {workflow.description && (
                        <p className="text-sm text-muted">{workflow.description}</p>
                      )}
                      {workflow.schedule_cron && (
                        <div style={{ marginTop: '0.375rem' }}>
                          <span className="badge badge-warning font-mono">
                            {workflow.schedule_cron}
                          </span>
                        </div>
                      )}
                      <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        {workflow.tool_ids && workflow.tool_ids.length > 0 && (
                          <span className="badge badge-info">
                            {workflow.tool_ids.length} tool{workflow.tool_ids.length > 1 ? 's' : ''}
                          </span>
                        )}
                        {workflow.skill_ids && workflow.skill_ids.length > 0 && (
                          <span className="badge badge-success">
                            {workflow.skill_ids.length} skill{workflow.skill_ids.length > 1 ? 's' : ''}
                          </span>
                        )}
                        {(() => { const cnt = lessonsByWorkflow.get(workflow.id)?.length ?? 0; return cnt > 0 ? (
                          <span className="badge" style={{ background: 'var(--purple-subtle)', color: 'var(--purple)', border: '1px solid var(--purple-border)' }}>
                            {cnt} lesson{cnt > 1 ? 's' : ''}
                          </span>
                        ) : null })()}
                      </div>
                    </div>
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={(e) => { e.stopPropagation(); handleDelete(workflow.id, workflow.name) }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right column: View/Execute */}
        <div>
          {viewingWorkflow && (
            <WorkflowRunViewer
              workflow={viewingWorkflow}
              tools={tools}
              skills={skills}
              onWorkflowUpdated={handleWorkflowUpdated}
            />
          )}

          {!viewingWorkflow && (
            <div className="card">
              <p className="text-sm text-muted">Select a workflow to view and execute.</p>
            </div>
          )}
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {dialog}
    </div>
  )
}
