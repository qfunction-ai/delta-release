import { useState, useEffect, useCallback, useRef } from 'react'
import { apiFetch, extractApiError } from '../lib/api'
import { useSSEStream } from '../hooks/useSSEStream'
import { Tool, Skill, Lesson, WorkflowDetail } from '../lib/types'

interface WorkflowRunViewerProps {
  workflow: WorkflowDetail
  tools: Tool[]
  skills: Skill[]
  onWorkflowUpdated: () => void
}

const RUNS_PER_PAGE = 10

function extractVariables(template: string): string[] {
  const regex = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g
  const vars: string[] = []
  let match
  while ((match = regex.exec(template)) !== null) {
    if (!vars.includes(match[1])) {
      vars.push(match[1])
    }
  }
  return vars
}

export default function WorkflowRunViewer({
  workflow,
  tools,
  skills,
  onWorkflowUpdated,
}: WorkflowRunViewerProps) {
  const [variables, setVariables] = useState<Record<string, string>>({})
  const [streamOutput, setStreamOutput] = useState('')
  const [reasoningOutput, setReasoningOutput] = useState('')
  const [executing, setExecuting] = useState(false)
  const [error, setError] = useState('')
  const [runPage, setRunPage] = useState(0)
  const [lessons, setLessons] = useState<Lesson[]>([])
  const [lessonsLoading, setLessonsLoading] = useState(false)

  // Reset state when workflow changes
  useEffect(() => {
    setVariables({})
    setStreamOutput('')
    setReasoningOutput('')
    setRunPage(0)
    setError('')
    setExecuting(false)

    setLessonsLoading(true)
    apiFetch(`/api/lessons/${workflow.id}`)
      .then(res => res.ok ? res.json() : { lessons: [] })
      .then(data => setLessons(data.lessons || []))
      .catch(() => setLessons([]))
      .finally(() => setLessonsLoading(false))
  }, [workflow.id])

  // Ref for current workflow in SSE callbacks
  const workflowRef = useRef(workflow)
  workflowRef.current = workflow

  // SSE streaming
  const { startStream } = useSSEStream({
    onContent: useCallback((content: string, reasoning: string) => {
      if (content) setStreamOutput(prev => prev + content)
      const wf = workflowRef.current
      if (reasoning && wf.include_reasoning) setReasoningOutput(prev => prev + reasoning)
    }, []),
    onError: useCallback((err: string) => setError(err), []),
    onCompleted: useCallback(() => {
      onWorkflowUpdated()
    }, [onWorkflowUpdated]),
  })

  const handleExecute = async () => {
    setExecuting(true)
    setStreamOutput('')
    setReasoningOutput('')

    try {
      const response = await apiFetch(`/api/workflows/${workflow.id}/run`, {
        method: 'POST',
        body: JSON.stringify({ variables }),
      })

      if (!response.ok) {
        setError(await extractApiError(response, 'Failed to execute workflow'))
        return
      }

      const run = await response.json()
      setStreamOutput(run.output || run.error_message || 'No output')
      onWorkflowUpdated()
    } catch {
      setError('Failed to execute workflow')
    } finally {
      setExecuting(false)
    }
  }

  const handleStream = async () => {
    setExecuting(true)
    setStreamOutput('')
    setReasoningOutput('')

    try {
      const response = await apiFetch(
        `/api/workflows/${workflow.id}/stream`,
        {
          method: 'POST',
          body: JSON.stringify({ variables }),
        }
      )

      if (!response.ok) {
        const errData = await response.json().catch(() => null)
        setError(errData?.detail || `Stream failed (${response.status})`)
        return
      }

      await startStream(response)
    } catch {
      setError('Failed to stream workflow')
    } finally {
      setExecuting(false)
    }
  }

  const handleDeleteLesson = async (lessonId: string) => {
    try {
      const response = await apiFetch(`/api/lessons/${lessonId}`, {
        method: 'DELETE',
      })
      if (response.ok) {
        setLessons(prev => prev.filter(l => l.id !== lessonId))
      }
    } catch {
      setError('Failed to delete lesson')
    }
  }

  const templateVariables = extractVariables(workflow.prompt_template)

  return (
    <div className="card">
      <h2 className="mb-4">{workflow.name}</h2>
      {workflow.description && (
        <p className="text-sm text-muted mb-4">{workflow.description}</p>
      )}

      {/* Show schedule if set */}
      {workflow.schedule_cron && (
        <div className="wrv-schedule-box">
          <span className="text-sm wrv-schedule-label">Schedule:</span>
          <code className="font-mono text-sm wrv-schedule-cron">
            {workflow.schedule_cron}
          </code>
          {workflow.default_variables && Object.keys(workflow.default_variables).length > 0 && (
            <div className="text-xs text-muted mt-1">
              Default vars: {JSON.stringify(workflow.default_variables)}
            </div>
          )}
        </div>
      )}

      {/* Show attached tools/skills */}
      <div className="mb-4">
        {workflow.tool_ids && workflow.tool_ids.length > 0 && (
          <div className="mb-2">
            <span className="text-xs text-muted wrv-section-label">Tools:</span>
            <div className="wrv-badge-row">
              {workflow.tool_ids.map(tid => {
                const tool = tools.find(t => t.id === tid)
                return tool ? (
                  <span key={tid} className="badge badge-info font-mono">{tool.name}</span>
                ) : null
              })}
            </div>
          </div>
        )}
        {workflow.skill_ids && workflow.skill_ids.length > 0 && (
          <div>
            <span className="text-xs text-muted wrv-section-label">Skills:</span>
            <div className="wrv-badge-row">
              {workflow.skill_ids.map(sid => {
                const skill = skills.find(s => s.id === sid)
                return skill ? (
                  <span key={sid} className="badge badge-success font-mono">{skill.name}</span>
                ) : null
              })}
            </div>
          </div>
        )}
      </div>

      {/* Execution Lessons */}
      {lessons.length > 0 && (
        <div className="mb-4">
          <span className="text-xs text-muted wrv-section-label">Execution Lessons:</span>
          <div className="wrv-lesson-list">
            {lessons.map(lesson => (
              <div key={lesson.id} className="wrv-lesson-card" style={{ borderLeft: `3px solid ${lesson.category === 'recovery' ? 'var(--danger)' : lesson.category === 'optimization' ? 'var(--warning)' : 'var(--purple)'}` }}>
                <div className="wrv-lesson-header">
                  <span className="badge font-mono wrv-lesson-badge" style={{ background: lesson.category === 'recovery' ? 'var(--danger)' : lesson.category === 'optimization' ? 'var(--warning)' : 'var(--purple)' }}>
                    {lesson.category}
                  </span>
                  <div className="wrv-lesson-actions">
                    <span className="text-xs text-muted" title="Utility score">
                      {lesson.utility_score > 0 ? '+' : ''}{lesson.utility_score.toFixed(1)}
                    </span>
                    <span className="text-xs text-muted" title="Times used">
                      {lesson.times_used}x
                    </span>
                    <button
                      className="btn btn-danger btn-sm wrv-lesson-delete-btn"
                      onClick={() => handleDeleteLesson(lesson.id)}
                    >
                      &times;
                    </button>
                  </div>
                </div>
                <p className="text-sm wrv-lesson-content">{lesson.content}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      {lessonsLoading && (
        <div className="mb-4 text-xs text-muted">Loading lessons...</div>
      )}

      {/* Reasoning indicator */}
      {workflow.include_reasoning && (
        <div className="wrv-reasoning-indicator">
          Reasoning included in output
        </div>
      )}

      {/* Variable inputs */}
      {templateVariables.length > 0 && (
        <div className="mb-4">
          <h3 className="section-header" data-symbol="x">Variables</h3>
          {templateVariables.map(v => (
            <div key={v} className="form-group">
              <label className="form-label font-mono">{v}</label>
              <input
                type="text"
                className="input"
                aria-label={`Variable ${v}`}
                value={variables[v] || ''}
                onChange={(e) => setVariables(prev => ({ ...prev, [v]: e.target.value }))}
                placeholder={`Enter ${v}`}
              />
            </div>
          ))}
        </div>
      )}

      {/* Execute buttons */}
      <div className="mb-4 flex gap-2">
        <button
          className="btn btn-primary"
          onClick={handleExecute}
          disabled={executing}
        >
          {executing ? 'Executing...' : 'Execute'}
        </button>
        <button
          className="btn btn-secondary"
          onClick={handleStream}
          disabled={executing}
        >
          Stream
        </button>
      </div>

      {/* Output */}
      {streamOutput && (
        <div className="mb-4">
          <h3 className="section-header" data-symbol="→">Output</h3>
          <div className="code-block wrv-output-block">
            {streamOutput}
          </div>
        </div>
      )}

      {/* Reasoning */}
      {reasoningOutput && (
        <div className="mb-4">
          <h3 className="section-header" data-symbol="λ">Reasoning</h3>
          <div className="code-block wrv-reasoning-block">
            {reasoningOutput}
          </div>
        </div>
      )}

      {/* Run history */}
      {workflow.runs.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="section-header" data-symbol="∫">Run History</h3>
            <span className="text-xs text-tertiary">
              {runPage * RUNS_PER_PAGE + 1}–{Math.min((runPage + 1) * RUNS_PER_PAGE, workflow.runs.length)} of {workflow.runs.length}
            </span>
          </div>
          <div className="wrv-run-history">
            {workflow.runs.slice(runPage * RUNS_PER_PAGE, (runPage + 1) * RUNS_PER_PAGE).map(run => (
              <div
                key={run.id}
                className="wrv-run-card"
                style={{
                  background: run.status === 'completed' ? 'var(--success-subtle)' :
                              run.status === 'failed' ? 'var(--danger-subtle)' : 'var(--bg-hover)',
                  border: '1px solid ' + (run.status === 'completed' ? 'var(--success-border)' :
                              run.status === 'failed' ? 'var(--danger-border)' : 'var(--border)'),
                }}
              >
                <div className="flex justify-between items-center">
                  <span className="flex items-center">
                    <span className={`status-dot ${run.status === 'completed' ? 'status-dot-success' : run.status === 'failed' ? 'status-dot-danger' : 'status-dot-neutral'}`} />
                    <span className="text-sm wrv-run-status" style={{
                      color: run.status === 'completed' ? 'var(--success)' :
                             run.status === 'failed' ? 'var(--danger)' : 'var(--text-tertiary)',
                    }}>
                      {run.status}
                    </span>
                  </span>
                  <span className="text-xs text-tertiary">
                    {new Date(run.created_at).toLocaleString()}
                  </span>
                </div>
                {run.output && (
                  <div className="code-block mt-2 wrv-run-output">
                    {run.output}
                  </div>
                )}
                {run.reasoning_output && (
                  <details className="wrv-run-details">
                    <summary className="wrv-run-summary">
                      λ reasoning
                    </summary>
                    <div className="code-block mt-1 wrv-run-reasoning">
                      {run.reasoning_output}
                    </div>
                  </details>
                )}
              </div>
            ))}
          </div>
          {workflow.runs.length > RUNS_PER_PAGE && (
            <div className="flex items-center justify-between mt-4">
              <button
                className="btn btn-secondary btn-sm"
                disabled={runPage === 0}
                onClick={() => setRunPage(prev => prev - 1)}
              >
                Previous
              </button>
              <span className="text-xs text-tertiary">
                Page {runPage + 1} of {Math.ceil(workflow.runs.length / RUNS_PER_PAGE)}
              </span>
              <button
                className="btn btn-secondary btn-sm"
                disabled={(runPage + 1) * RUNS_PER_PAGE >= workflow.runs.length}
                onClick={() => setRunPage(prev => prev + 1)}
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}

      {error && <div className="error">{error}</div>}
    </div>
  )
}
