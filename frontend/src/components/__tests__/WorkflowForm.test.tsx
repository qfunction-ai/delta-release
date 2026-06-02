import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import WorkflowForm from '../WorkflowForm'
import { Agent, Tool, Skill } from '../../lib/types'

// Mock apiFetch
vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(),
  extractApiError: vi.fn(),
}))

vi.mock('../../lib/errors', () => ({
  ERROR_MESSAGES: { CONNECTION: 'Connection failed' },
}))

const mockAgents: Agent[] = [
  {
    id: 'agent-1',
    letta_agent_id: 'letta-1',
    name: 'Security Agent',
    model: 'gpt-4',
    embedding: 'text-embedding-3-small',
    created_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 'agent-2',
    letta_agent_id: 'letta-2',
    name: 'Analysis Agent',
    model: 'gpt-4',
    embedding: 'text-embedding-3-small',
    created_at: '2025-01-01T00:00:00Z',
  },
]

const mockTools: Tool[] = [
  { id: 'tool-1', name: 'search_splunk', description: 'Search Splunk', source: 'manual', tags: ['splunk'], pip_requirements: ['httpx'], created_at: '2025-01-01T00:00:00Z', updated_at: '2025-01-01T00:00:00Z' },
  { id: 'tool-2', name: 'query_virusotal', description: 'Query VirusTotal', source: 'manual', tags: ['virustotal'], pip_requirements: null, created_at: '2025-01-01T00:00:00Z', updated_at: '2025-01-01T00:00:00Z' },
]

const mockSkills: Skill[] = [
  { id: 'skill-1', name: 'Threat Intel', description: 'Threat intelligence lookup', source: 'manual', file_path: '/skills/threat-intel/SKILL.md', created_at: '2025-01-01T00:00:00Z', updated_at: '2025-01-01T00:00:00Z' },
  { id: 'skill-2', name: 'Log Analysis', description: 'Analyze log files', source: 'manual', file_path: '/skills/log-analysis/SKILL.md', created_at: '2025-01-01T00:00:00Z', updated_at: '2025-01-01T00:00:00Z' },
]

describe('WorkflowForm', () => {
  it('renders form with all fields', () => {
    render(
      <WorkflowForm
        agents={mockAgents}
        tools={mockTools}
        skills={mockSkills}
        onCreated={vi.fn()}
      />
    )

    expect(screen.getByLabelText(/Name/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Agent/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Description/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Prompt Template/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Schedule/)).toBeInTheDocument()
    expect(screen.getByText('Include Reasoning')).toBeInTheDocument()
  })

  it('renders agent options in select', () => {
    render(
      <WorkflowForm
        agents={mockAgents}
        tools={mockTools}
        skills={mockSkills}
        onCreated={vi.fn()}
      />
    )

    expect(screen.getByText('Security Agent')).toBeInTheDocument()
    expect(screen.getByText('Analysis Agent')).toBeInTheDocument()
  })

  it('shows tool checkboxes when tools provided', () => {
    render(
      <WorkflowForm
        agents={mockAgents}
        tools={mockTools}
        skills={mockSkills}
        onCreated={vi.fn()}
      />
    )

    expect(screen.getByLabelText('search_splunk')).toBeInTheDocument()
    expect(screen.getByLabelText('query_virusotal')).toBeInTheDocument()
  })

  it('shows skill checkboxes when skills provided', () => {
    render(
      <WorkflowForm
        agents={mockAgents}
        tools={mockTools}
        skills={mockSkills}
        onCreated={vi.fn()}
      />
    )

    expect(screen.getByLabelText('Threat Intel')).toBeInTheDocument()
    expect(screen.getByLabelText('Log Analysis')).toBeInTheDocument()
  })

  it('shows default variables textarea when schedule is entered', async () => {
    const user = userEvent.setup()
    render(
      <WorkflowForm
        agents={mockAgents}
        tools={mockTools}
        skills={mockSkills}
        onCreated={vi.fn()}
      />
    )

    // Default variables textarea is hidden until schedule is entered
    expect(screen.queryByLabelText(/Default Variables/)).not.toBeInTheDocument()

    await user.type(screen.getByLabelText(/Schedule/), '0 9 * * *')
    expect(screen.getByLabelText(/Default Variables/)).toBeInTheDocument()
  })

  it('submit button is disabled when required fields are empty', () => {
    render(
      <WorkflowForm
        agents={mockAgents}
        tools={mockTools}
        skills={mockSkills}
        onCreated={vi.fn()}
      />
    )

    // Name and promptTemplate are empty, but agentId auto-selects first agent
    // So the button is disabled because name and promptTemplate are empty
    expect(screen.getByRole('button', { name: 'Create Workflow' })).toBeDisabled()
  })

  it('tool checkbox toggles on click', async () => {
    const user = userEvent.setup()
    render(
      <WorkflowForm
        agents={mockAgents}
        tools={mockTools}
        skills={mockSkills}
        onCreated={vi.fn()}
      />
    )

    const checkbox = screen.getByLabelText('search_splunk')
    expect(checkbox).not.toBeChecked()
    await user.click(checkbox)
    expect(checkbox).toBeChecked()
  })

  it('skill checkbox toggles on click', async () => {
    const user = userEvent.setup()
    render(
      <WorkflowForm
        agents={mockAgents}
        tools={mockTools}
        skills={mockSkills}
        onCreated={vi.fn()}
      />
    )

    const checkbox = screen.getByLabelText('Threat Intel')
    expect(checkbox).not.toBeChecked()
    await user.click(checkbox)
    expect(checkbox).toBeChecked()
  })
})
