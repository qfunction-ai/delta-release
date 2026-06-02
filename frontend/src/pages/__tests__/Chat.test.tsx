import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Chat from '../Chat'

// Mock apiFetch
vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(),
}))

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

// Mock useOllamaStatus — no polling in tests
vi.mock('../../hooks/useOllamaStatus', () => ({
  useOllamaStatus: () => ({ available: true, models: ['gemma4:latest'], loading: false, error: '' }),
}))

// Mock scrollIntoView (not available in jsdom)
Element.prototype.scrollIntoView = vi.fn()

const MOCK_AGENTS = [
  { id: '1', name: 'sec-agent', letta_agent_id: 'agent-1', model: 'gpt-4', embedding: 'letta-free', created_at: '2026-01-10T00:00:00Z' },
]
const MOCK_TOOLS = [
  { id: 'tool-1', name: 'query_splunk', description: 'Search Splunk' },
]
const MOCK_SKILLS = [
  { id: 'skill-1', name: 'security-scan', description: 'Run security scan' },
]

const MOCK_HEALTH = {
  services: {
    ollama: { status: 'healthy', models: ['gemma4:latest'] },
  },
}

function setupFetchMocks() {
  mockApiFetch
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_AGENTS) } as unknown as Response)
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_TOOLS) } as unknown as Response)
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_SKILLS) } as unknown as Response)
    .mockResolvedValue({ ok: true, json: () => Promise.resolve(MOCK_HEALTH) } as unknown as Response)
}

function renderChat() {
  return render(
    <MemoryRouter>
      <Chat />
    </MemoryRouter>
  )
}

describe('Chat page', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('renders chat interface with agent selector', async () => {
    setupFetchMocks()
    renderChat()

    await waitFor(() => {
      expect(screen.getByText('Select agent...')).toBeInTheDocument()
    })
    expect(screen.getByText('sec-agent')).toBeInTheDocument()
  })

  it('shows tools and skills in config panel when opened', async () => {
    setupFetchMocks()
    const user = userEvent.setup()
    renderChat()

    await waitFor(() => {
      expect(screen.getByText('⚙ Config')).toBeInTheDocument()
    })

    // Open the config panel
    await user.click(screen.getByText('⚙ Config'))

    await waitFor(() => {
      expect(screen.getByText('query_splunk')).toBeInTheDocument()
    })
    expect(screen.getByText('security-scan')).toBeInTheDocument()
  })

  it('shows prompt to select agent when none selected', async () => {
    setupFetchMocks()
    renderChat()

    await waitFor(() => {
      expect(screen.getByText('Select an agent to begin')).toBeInTheDocument()
    })
  })

  it('shows no tools/skills message in config panel when empty', async () => {
    mockApiFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_AGENTS) } as unknown as Response)
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([]) } as unknown as Response)
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([]) } as unknown as Response)
    const user = userEvent.setup()
    renderChat()

    await waitFor(() => {
      expect(screen.getByText('⚙ Config')).toBeInTheDocument()
    })

    // Open the config panel
    await user.click(screen.getByText('⚙ Config'))

    await waitFor(() => {
      expect(screen.getByText('No tools available')).toBeInTheDocument()
    })
    expect(screen.getByText('No skills available')).toBeInTheDocument()
  })

  it('shows error when API fails', async () => {
    mockApiFetch
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
    renderChat()

    // Should still render without crashing
    await waitFor(() => {
      expect(screen.getByText('Select an agent to begin')).toBeInTheDocument()
    })
  })

  it('selects an agent and shows chat input', async () => {
    setupFetchMocks()
    // Mock history fetch for when agent is selected
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ messages: [] }),
    } as unknown as Response)

    const user = userEvent.setup()
    renderChat()

    await waitFor(() => {
      expect(screen.getByText('sec-agent')).toBeInTheDocument()
    })

    // Select the agent from dropdown
    await user.selectOptions(screen.getByRole('combobox'), 'agent-1')

    // Chat input should appear after selecting an agent
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Send a message to sec-agent...')).toBeInTheDocument()
    })
  })

  it('shows reasoning toggle', async () => {
    setupFetchMocks()
    renderChat()

    await waitFor(() => {
      expect(screen.getByText('Reasoning')).toBeInTheDocument()
    })
  })

  it('shows tool checkboxes in config panel that can be toggled', async () => {
    setupFetchMocks()
    const user = userEvent.setup()
    renderChat()

    await waitFor(() => {
      expect(screen.getByText('⚙ Config')).toBeInTheDocument()
    })

    // Open the config panel
    await user.click(screen.getByText('⚙ Config'))

    await waitFor(() => {
      expect(screen.getByText('query_splunk')).toBeInTheDocument()
    })

    // Tool checkbox should be present
    const checkbox = screen.getByRole('checkbox', { name: /query_splunk/i })
    expect(checkbox).not.toBeChecked()

    // Click to toggle
    await user.click(checkbox)
    expect(checkbox).toBeChecked()
  })
})
