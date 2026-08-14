import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Workflows from '../Workflows'

// Mock apiFetch
vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual('../../lib/api')
  return {
    ...actual,
    apiFetch: vi.fn(),
  }
})

import { apiFetch } from '../../lib/api'
const mockApiFetch = vi.mocked(apiFetch)

// Mock useAuth
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true, isAdmin: false, loading: false, logout: vi.fn() }),
}))

// Mock useRequireAuth
vi.mock('../../hooks/useRequireAuth', () => ({
  useRequireAuth: () => {},
}))

// Mock useConfirmDialog
vi.mock('../../hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn(), dialog: null }),
}))

const MOCK_AGENTS = [
  { id: '1', name: 'sec-agent', letta_agent_id: 'agent-1', model: 'gpt-4', embedding: 'letta-free', created_at: '2026-01-10T00:00:00Z' },
]
const MOCK_TOOLS: { id: string; name: string }[] = []
const MOCK_SKILLS: { id: string; name: string }[] = []
const MOCK_WORKFLOWS: { id: string; name: string; description: string; agent_id: string; prompt_template: string; tool_ids: string[]; skill_ids: string[]; schedule_cron: string; include_reasoning: boolean; created_at: string }[] = [
  { id: 'wf-1', name: 'daily-scan', description: 'Run daily security scan', agent_id: 'agent-1', prompt_template: 'Scan {{target}}', tool_ids: [], skill_ids: [], schedule_cron: '0 9 * * *', include_reasoning: false, created_at: '2026-01-10T00:00:00Z' },
]
const MOCK_LESSONS = { lessons: [] }

function setupFetchMocks(workflows = MOCK_WORKFLOWS) {
  mockApiFetch
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_AGENTS) } as unknown as Response)
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_TOOLS) } as unknown as Response)
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_SKILLS) } as unknown as Response)
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(workflows) } as unknown as Response)
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_LESSONS) } as unknown as Response)
}

function renderWorkflows() {
  return render(
    <MemoryRouter>
      <Workflows />
    </MemoryRouter>
  )
}

describe('Workflows page', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('renders workflow list', async () => {
    setupFetchMocks()
    renderWorkflows()

    await waitFor(() => {
      expect(screen.getByText('daily-scan')).toBeInTheDocument()
    })
    expect(screen.getByText('Run daily security scan')).toBeInTheDocument()
  })

  it('shows empty state when no workflows', async () => {
    setupFetchMocks([])
    renderWorkflows()

    await waitFor(() => {
      expect(screen.getByText('No workflows yet. Create one above.')).toBeInTheDocument()
    })
  })

  it('shows cron badge for scheduled workflows', async () => {
    setupFetchMocks()
    renderWorkflows()

    await waitFor(() => {
      expect(screen.getByText('0 9 * * *')).toBeInTheDocument()
    })
  })

  it('shows error on API failure', async () => {
    mockApiFetch
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
    renderWorkflows()

    await waitFor(() => {
      expect(screen.getByText('Failed to load workflows. Check that the server is running.')).toBeInTheDocument()
    })
  })

  it('shows select prompt when no workflow is selected', async () => {
    setupFetchMocks()
    renderWorkflows()

    await waitFor(() => {
      expect(screen.getByText('Select a workflow to view and execute.')).toBeInTheDocument()
    })
  })

  it('shows tool count badge on workflow cards when workflow has tools', async () => {
    const workflowsWithTools = [
      { ...MOCK_WORKFLOWS[0], tool_ids: ['tool-1'] },
    ]
    setupFetchMocks(workflowsWithTools)
    renderWorkflows()

    await waitFor(() => {
      expect(screen.getByText('1 tool')).toBeInTheDocument()
    })
  })

  it('shows skill count badge on workflow cards when workflow has skills', async () => {
    const workflowsWithSkills = [
      { ...MOCK_WORKFLOWS[0], skill_ids: ['skill-1'] },
    ]
    setupFetchMocks(workflowsWithSkills)
    renderWorkflows()

    await waitFor(() => {
      expect(screen.getByText('1 skill')).toBeInTheDocument()
    })
  })

  it('shows lesson count badge when workflow has lessons', async () => {
    const lessonsWithWorkflow = {
      lessons: [
        { id: 'lesson-1', workflow_id: 'wf-1', run_id: null, category: 'recovery', content: 'Retry on timeout', utility_score: 1.5, times_used: 3, created_at: '2026-01-10T00:00:00Z' },
      ],
    }
    mockApiFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_AGENTS) } as unknown as Response)
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_TOOLS) } as unknown as Response)
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_SKILLS) } as unknown as Response)
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_WORKFLOWS) } as unknown as Response)
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(lessonsWithWorkflow) } as unknown as Response)
    renderWorkflows()

    await waitFor(() => {
      expect(screen.getByText('1 lesson')).toBeInTheDocument()
    })
  })

  it('shows delete button on workflow cards', async () => {
    setupFetchMocks()
    renderWorkflows()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    })
  })

  it('shows edit button on workflow cards', async () => {
    setupFetchMocks()
    renderWorkflows()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    })
  })

  it('clicking Edit opens the form pre-filled with the workflow', async () => {
    setupFetchMocks()
    renderWorkflows()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))

    await waitFor(() => {
      expect(screen.getByText('Edit Workflow')).toBeInTheDocument()
      expect(screen.getByDisplayValue('daily-scan')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Scan {{target}}')).toBeInTheDocument()
      expect(screen.getByDisplayValue('0 9 * * *')).toBeInTheDocument()
    })
  })

  it('shows Create Workflow form with Name field', async () => {
    setupFetchMocks()
    renderWorkflows()

    await waitFor(() => {
      expect(screen.getByLabelText(/Name/)).toBeInTheDocument()
    })
  })
})
