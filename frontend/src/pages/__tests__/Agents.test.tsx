import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Agents from '../Agents'

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

// Mock useAuth to always return authenticated
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true, isAdmin: false, loading: false, logout: vi.fn() }),
}))

// Mock useOllamaStatus — no polling in tests
vi.mock('../../hooks/useOllamaStatus', () => ({
  useOllamaStatus: () => ({ available: true, models: ['gemma4:latest'], loading: false, error: '' }),
}))

const MOCK_MODELS = [
  { id: 'gpt-4', name: 'GPT-4', provider: 'openai' },
  { id: 'claude-3', name: 'Claude 3', provider: 'anthropic' },
]

const MOCK_EMBEDDINGS = [
  { id: 'letta/letta-free', name: 'Letta Free', provider: 'letta', dimensions: 1024 },
  { id: 'text-embedding-3', name: 'Text Embed 3', provider: 'openai', dimensions: 1536 },
]

const MOCK_AGENTS = [
  { id: 'agent-1', letta_agent_id: 'letta-agent-1-abc', name: 'sec-agent', model: 'gpt-4', embedding: 'letta/letta-free', created_at: '2026-01-10T00:00:00Z' },
  { id: 'agent-2', letta_agent_id: 'letta-agent-2-def', name: 'log-agent', model: 'claude-3', embedding: 'text-embedding-3', created_at: '2026-01-11T00:00:00Z' },
]

const MOCK_HEALTH = {
  services: {
    ollama: { status: 'healthy', models: ['gemma4:latest'] },
  },
}

function setupFetchMocks() {
  mockApiFetch
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_MODELS) } as unknown as Response)
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_EMBEDDINGS) } as unknown as Response)
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_AGENTS) } as unknown as Response)
    .mockResolvedValue({ ok: true, json: () => Promise.resolve(MOCK_HEALTH) } as unknown as Response)
}

function renderAgents() {
  return render(
    <MemoryRouter>
      <Agents />
    </MemoryRouter>
  )
}

describe('Agents page', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('shows loading spinner then renders agent list', async () => {
    setupFetchMocks()
    renderAgents()

    // Should show loading first
    expect(screen.getByText('Loading...')).toBeInTheDocument()

    // Then agents appear
    await waitFor(() => {
      expect(screen.getByText('sec-agent')).toBeInTheDocument()
    })
    expect(screen.getByText('log-agent')).toBeInTheDocument()
  })

  it('shows model and embedding for each agent', async () => {
    setupFetchMocks()
    renderAgents()

    await waitFor(() => {
      expect(screen.getByText('sec-agent')).toBeInTheDocument()
    })
    expect(screen.getByText('gpt-4')).toBeInTheDocument()
    expect(screen.getByText('letta/letta-free')).toBeInTheDocument()
  })

  it('shows empty state when no agents exist', async () => {
    mockApiFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_MODELS) } as unknown as Response)
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_EMBEDDINGS) } as unknown as Response)
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([]) } as unknown as Response)

    renderAgents()

    await waitFor(() => {
      expect(screen.getByText('No agents deployed yet. Create one above.')).toBeInTheDocument()
    })
  })

  it('shows fetch error when API fails', async () => {
    mockApiFetch
      .mockResolvedValueOnce({ ok: false } as unknown as Response)
      .mockResolvedValueOnce({ ok: false } as unknown as Response)
      .mockResolvedValueOnce({ ok: false } as unknown as Response)

    renderAgents()

    // The last failing request (agents) sets the error
    await waitFor(() => {
      expect(screen.getByText('Failed to load agents')).toBeInTheDocument()
    })
  })

  it('creates a new agent on form submit', async () => {
    const user = userEvent.setup()
    setupFetchMocks()

    const newAgent = { id: 'agent-3', letta_agent_id: 'letta-agent-3-ghi', name: 'new-agent', model: 'gpt-4', embedding: 'letta/letta-free', created_at: '2026-01-12T00:00:00Z' }
    mockApiFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(newAgent) } as unknown as Response)

    renderAgents()

    await waitFor(() => {
      expect(screen.getByText('sec-agent')).toBeInTheDocument()
    })

    // Fill in the form
    const nameInput = screen.getByPlaceholderText('security-agent')
    await user.type(nameInput, 'new-agent')

    await user.click(screen.getByText('Deploy Agent'))

    await waitFor(() => {
      expect(screen.getByText('new-agent')).toBeInTheDocument()
    })
  })

  it('shows detail panel on agent click', async () => {
    const user = userEvent.setup()
    setupFetchMocks()
    renderAgents()

    await waitFor(() => {
      expect(screen.getByText('sec-agent')).toBeInTheDocument()
    })

    // Click on the first agent row
    await user.click(screen.getByText('sec-agent'))

    // Detail panel should appear with agent name as title
    await waitFor(() => {
      // The detail-title shows the agent name
      expect(screen.getAllByText('sec-agent').length).toBeGreaterThanOrEqual(2)
    })
  })

  it('shows confirm dialog on delete click', async () => {
    const user = userEvent.setup()
    setupFetchMocks()
    renderAgents()

    await waitFor(() => {
      expect(screen.getByText('sec-agent')).toBeInTheDocument()
    })

    // Click the delete action button (has title="Delete")
    const deleteButtons = screen.getAllByTitle('Delete')
    await user.click(deleteButtons[0])

    await waitFor(() => {
      expect(screen.getByText('Delete Agent')).toBeInTheDocument()
    })
  })

  it('shows Details and Policy tabs in detail panel', async () => {
    const user = userEvent.setup()
    setupFetchMocks()
    renderAgents()

    await waitFor(() => {
      expect(screen.getByText('sec-agent')).toBeInTheDocument()
    })

    await user.click(screen.getByText('sec-agent'))

    await waitFor(() => {
      expect(screen.getByText('Details')).toBeInTheDocument()
      expect(screen.getByText('Policy')).toBeInTheDocument()
    })
  })

  it('switches to Policy tab and renders PolicyTab', async () => {
    const user = userEvent.setup()
    setupFetchMocks()
    renderAgents()

    await waitFor(() => {
      expect(screen.getByText('sec-agent')).toBeInTheDocument()
    })

    await user.click(screen.getByText('sec-agent'))

    await waitFor(() => {
      expect(screen.getByText('Policy')).toBeInTheDocument()
    })

    // Mock the policy fetch that PolicyTab will make
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        agent_id: 'agent-1',
        denied_tools: [],
        approval_required_tools: [],
        rules: [],
        max_calls_per_tool: {},
        defaults: null,
      }),
    } as unknown as Response)

    await user.click(screen.getByText('Policy'))

    await waitFor(() => {
      expect(screen.getByText('Denied Tools')).toBeInTheDocument()
    })
  })

  it('resets tab to Details when switching agents', async () => {
    const user = userEvent.setup()
    setupFetchMocks()
    renderAgents()

    await waitFor(() => {
      expect(screen.getByText('sec-agent')).toBeInTheDocument()
    })

    // Click first agent, switch to Policy tab
    await user.click(screen.getByText('sec-agent'))

    await waitFor(() => {
      expect(screen.getByText('Policy')).toBeInTheDocument()
    })

    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        agent_id: 'agent-1',
        denied_tools: [],
        approval_required_tools: [],
        rules: [],
        max_calls_per_tool: {},
        defaults: null,
      }),
    } as unknown as Response)

    await user.click(screen.getByText('Policy'))

    await waitFor(() => {
      expect(screen.getByText('Denied Tools')).toBeInTheDocument()
    })

    // Click second agent — tab should reset to Details
    await user.click(screen.getByText('log-agent'))

    await waitFor(() => {
      // Details tab content should be visible (agent-2 id in detail grid)
      expect(screen.getByText('agent-2')).toBeInTheDocument()
    })
  })
})
