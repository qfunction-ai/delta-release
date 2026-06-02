import { useState } from 'react'
import { apiFetch, extractApiError } from '../lib/api'
import { ERROR_MESSAGES } from '../lib/errors'
import { Agent, Tool, Skill, Workflow } from '../lib/types'

interface WorkflowFormProps {
  agents: Agent[]
  tools: Tool[]
  skills: Skill[]
  onCreated: (workflow: Workflow) => void
}

export default function WorkflowForm({ agents, tools, skills, onCreated }: WorkflowFormProps) {
  const [name, setName] = useState('')
  const [agentId, setAgentId] = useState(agents.length > 0 ? agents[0].letta_agent_id : '')
  const [description, setDescription] = useState('')
  const [promptTemplate, setPromptTemplate] = useState('')
  const [selectedTools, setSelectedTools] = useState<string[]>([])
  const [selectedSkills, setSelectedSkills] = useState<string[]>([])
  const [scheduleCron, setScheduleCron] = useState('')
  const [defaultVariables, setDefaultVariables] = useState<Record<string, string>>({})
  const [includeReasoning, setIncludeReasoning] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [jsonError, setJsonError] = useState('')

  const toggleTool = (toolId: string) => {
    setSelectedTools(prev => {
      const next = [...prev]
      const idx = next.indexOf(toolId)
      if (idx >= 0) next.splice(idx, 1)
      else next.push(toolId)
      return next
    })
  }

  const toggleSkill = (skillId: string) => {
    setSelectedSkills(prev => {
      const next = [...prev]
      const idx = next.indexOf(skillId)
      if (idx >= 0) next.splice(idx, 1)
      else next.push(skillId)
      return next
    })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setCreating(true)

    try {
      const response = await apiFetch('/api/workflows/', {
        method: 'POST',
        body: JSON.stringify({
          name,
          agent_id: agentId,
          description,
          prompt_template: promptTemplate,
          tool_ids: selectedTools.length > 0 ? selectedTools : null,
          skill_ids: selectedSkills.length > 0 ? selectedSkills : null,
          schedule_cron: scheduleCron.trim() || null,
          default_variables: Object.keys(defaultVariables).length > 0 ? defaultVariables : null,
          include_reasoning: includeReasoning,
        }),
      })

      if (!response.ok) {
        setError(await extractApiError(response, 'Failed to create workflow'))
        return
      }

      const newWorkflow = await response.json()
      onCreated(newWorkflow)
      setName('')
      setDescription('')
      setPromptTemplate('')
      setSelectedTools([])
      setSelectedSkills([])
      setScheduleCron('')
      setDefaultVariables({})
      setIncludeReasoning(false)
    } catch {
      setError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="card mb-6">
      <h2 className="section-header" data-symbol="+">Create Workflow</h2>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label" htmlFor="field-workflows-name">Name</label>
          <input
            id="field-workflows-name"
            type="text"
            className="input"
            aria-label="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Threat Analysis"
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="field-workflows-agent">Agent</label>
          <select
            id="field-workflows-agent"
            className="input"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
            required
          >
            {agents.map(a => (
              <option key={a.letta_agent_id} value={a.letta_agent_id}>
                {a.name}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="field-workflows-description">Description</label>
          <input
            id="field-workflows-description"
            type="text"
            className="input"
            aria-label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Analyze security alerts"
          />
        </div>

        {/* Tool selection */}
        {tools.length > 0 && (
          <div className="form-group">
            <label className="form-label" htmlFor="field-workflows-tools">Tools</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
              {tools.map(t => (
                <label
                  key={t.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.375rem',
                    padding: '0.375rem 0.625rem',
                    background: selectedTools.includes(t.id) ? 'var(--accent-subtle)' : 'var(--bg-hover)',
                    border: selectedTools.includes(t.id) ? '1px solid var(--accent-border)' : '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer',
                    fontSize: '0.8125rem',
                    color: selectedTools.includes(t.id) ? 'var(--accent)' : 'var(--text-secondary)',
                    fontFamily: 'var(--font-display)',
                    transition: 'all var(--transition-fast)',
                  }}
                >
                  <input
                    id={t.id === tools[0]?.id ? 'field-workflows-tools' : undefined}
                    type="checkbox"
                    aria-label={`Select ${t.name} tool`}
                    checked={selectedTools.includes(t.id)}
                    onChange={() => toggleTool(t.id)}
                    style={{ accentColor: 'var(--accent)' }}
                  />
                  {t.name}
                </label>
              ))}
            </div>
          </div>
        )}

        {/* Skill selection */}
        {skills.length > 0 && (
          <div className="form-group">
            <label className="form-label" htmlFor="field-workflows-skills">Skills</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
              {skills.map(s => (
                <label
                  key={s.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.375rem',
                    padding: '0.375rem 0.625rem',
                    background: selectedSkills.includes(s.id) ? 'var(--accent-subtle)' : 'var(--bg-hover)',
                    border: selectedSkills.includes(s.id) ? '1px solid var(--accent-border)' : '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer',
                    fontSize: '0.8125rem',
                    color: selectedSkills.includes(s.id) ? 'var(--accent)' : 'var(--text-secondary)',
                    fontFamily: 'var(--font-display)',
                    transition: 'all var(--transition-fast)',
                  }}
                >
                  <input
                    id={s.id === skills[0]?.id ? 'field-workflows-skills' : undefined}
                    type="checkbox"
                    aria-label={`Select ${s.name} skill`}
                    checked={selectedSkills.includes(s.id)}
                    onChange={() => toggleSkill(s.id)}
                    style={{ accentColor: 'var(--accent)' }}
                  />
                  {s.name}
                </label>
              ))}
            </div>
          </div>
        )}

        {/* Schedule */}
        <div className="form-group">
          <label className="form-label" htmlFor="field-workflows-cron">Schedule (Cron Expression — optional)</label>
          <input
            id="field-workflows-cron"
            type="text"
            className="input font-mono"
            aria-label="Schedule (Cron Expression)"
            value={scheduleCron}
            onChange={(e) => setScheduleCron(e.target.value)}
            placeholder="0 9 * * * (daily at 9 AM UTC)"
          />
          <p className="form-hint">5-field cron: minute hour day month weekday</p>
        </div>

        {/* Default Variables for scheduled runs */}
        {scheduleCron && (
          <div className="form-group">
            <label className="form-label" htmlFor="field-workflows-variables">Default Variables (for scheduled runs)</label>
            <textarea
              id="field-workflows-variables"
              className="input font-mono"
              aria-label="Default Variables (for scheduled runs)"
              value={JSON.stringify(defaultVariables, null, 2)}
              onChange={(e) => {
                try {
                  setDefaultVariables(JSON.parse(e.target.value))
                  setJsonError('')
                } catch (err) {
                  setJsonError(err instanceof SyntaxError ? err.message : 'Invalid JSON')
                }
              }}
              rows={4}
              style={{ fontSize: '0.8125rem' }}
              placeholder='{"alert_name": "default", "source": "system"}'
            />
            {jsonError ? (
              <p className="form-hint" style={{ color: 'var(--danger)' }}>Invalid JSON: {jsonError}</p>
            ) : (
              <p className="form-hint">JSON object with default values for template variables</p>
            )}
          </div>
        )}

        <div className="form-group">
          <label className="form-label" htmlFor="field-workflows-prompt">Prompt Template (use {'{{variable}}'} for variables)</label>
          <textarea
            id="field-workflows-prompt"
            className="input font-mono"
            aria-label="Prompt Template"
            value={promptTemplate}
            onChange={(e) => setPromptTemplate(e.target.value)}
            rows={8}
            required
            style={{ fontSize: '0.8125rem' }}
            placeholder={`Analyze this security alert:\n\nAlert: {{alert_name}}\nSource: {{source}}\nSeverity: {{severity}}\n\nProvide recommendations.`}
          />
        </div>

        {/* Include Reasoning checkbox */}
        <div className="form-group">
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              aria-label="Include Reasoning"
              checked={includeReasoning}
              onChange={(e) => setIncludeReasoning(e.target.checked)}
              style={{ accentColor: 'var(--accent)' }}
            />
            <span className="text-sm" style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>Include Reasoning</span>
          </label>
          <p className="form-hint">Show the agent's internal reasoning/thinking process in the output</p>
        </div>

        {error && <div className="error">{error}</div>}

        <button
          type="submit"
          className="btn btn-primary"
          disabled={creating || !name || !promptTemplate || !agentId}
          style={{ marginTop: '1rem' }}
        >
          {creating ? 'Creating...' : 'Create Workflow'}
        </button>
      </form>
    </div>
  )
}
