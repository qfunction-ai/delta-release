import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import WorkflowRunViewer from '../WorkflowRunViewer'
import { Tool, Skill, WorkflowDetail } from '../../lib/types'

// Mock apiFetch
vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ lessons: [] }) })),
  extractApiError: vi.fn(),
}))

// Mock useSSEStream
vi.mock('../../hooks/useSSEStream', () => ({
  useSSEStream: () => ({
    streaming: false,
    startStream: vi.fn(),
  }),
}))

const mockWorkflow: WorkflowDetail = {
  id: 'wf-1',
  name: 'daily-scan',
  agent_id: 'agent-1',
  description: 'Run daily security scan',
  prompt_template: 'Scan {{target}}',
  tool_ids: ['tool-1'],
  skill_ids: ['skill-1'],
  schedule_cron: '0 9 * * *',
  default_variables: null,
  include_reasoning: false,
  created_at: '2026-01-10T00:00:00Z',
  runs: [],
}

const mockTools: Tool[] = [
  { id: 'tool-1', name: 'search_splunk', description: 'Search Splunk', source: 'manual', tags: ['splunk'], pip_requirements: null, created_at: '2026-01-10T00:00:00Z', updated_at: '2026-01-10T00:00:00Z' },
]

const mockSkills: Skill[] = [
  { id: 'skill-1', name: 'Threat Intel', description: 'Threat intelligence lookup', source: 'manual', file_path: '/skills/threat-intel/SKILL.md', created_at: '2026-01-10T00:00:00Z', updated_at: '2026-01-10T00:00:00Z' },
]

describe('WorkflowRunViewer', () => {
  it('renders workflow name and description', () => {
    render(
      <WorkflowRunViewer
        workflow={mockWorkflow}
        tools={mockTools}
        skills={mockSkills}
        onWorkflowUpdated={vi.fn()}
      />
    )

    expect(screen.getByText('daily-scan')).toBeInTheDocument()
    expect(screen.getByText('Run daily security scan')).toBeInTheDocument()
  })

  it('shows schedule when workflow has schedule_cron', () => {
    render(
      <WorkflowRunViewer
        workflow={mockWorkflow}
        tools={mockTools}
        skills={mockSkills}
        onWorkflowUpdated={vi.fn()}
      />
    )

    expect(screen.getByText('0 9 * * *')).toBeInTheDocument()
  })

  it('shows Execute and Stream buttons', () => {
    render(
      <WorkflowRunViewer
        workflow={mockWorkflow}
        tools={mockTools}
        skills={mockSkills}
        onWorkflowUpdated={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Execute' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Stream' })).toBeInTheDocument()
  })

  it('renders variable inputs for template variables', async () => {
    render(
      <WorkflowRunViewer
        workflow={mockWorkflow}
        tools={mockTools}
        skills={mockSkills}
        onWorkflowUpdated={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Enter target')).toBeInTheDocument()
    })
  })

  it('shows tool names when workflow has tool_ids', () => {
    render(
      <WorkflowRunViewer
        workflow={mockWorkflow}
        tools={mockTools}
        skills={mockSkills}
        onWorkflowUpdated={vi.fn()}
      />
    )

    expect(screen.getByText('search_splunk')).toBeInTheDocument()
  })

  it('shows skill names when workflow has skill_ids', () => {
    render(
      <WorkflowRunViewer
        workflow={mockWorkflow}
        tools={mockTools}
        skills={mockSkills}
        onWorkflowUpdated={vi.fn()}
      />
    )

    expect(screen.getByText('Threat Intel')).toBeInTheDocument()
  })

  it('shows reasoning indicator when include_reasoning is true', () => {
    render(
      <WorkflowRunViewer
        workflow={{ ...mockWorkflow, include_reasoning: true }}
        tools={mockTools}
        skills={mockSkills}
        onWorkflowUpdated={vi.fn()}
      />
    )

    expect(screen.getByText('Reasoning included in output')).toBeInTheDocument()
  })
})
