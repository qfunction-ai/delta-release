import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AgentSection from '../AgentSection'

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

// Mock ToggleSwitch
vi.mock('../ToggleSwitch', () => ({
  default: ({ checked, onChange, disabled }: { checked: boolean; onChange: () => void; disabled?: boolean }) => (
    <button
      data-testid="toggle-switch"
      onClick={onChange}
      disabled={disabled}
      aria-pressed={checked}
    >
      {checked ? 'On' : 'Off'}
    </button>
  ),
}))

const defaultSettings = {
  agent_tool_creation: false,
  eval_enabled: false,
  web_search_enabled: false,
  docs_fetch_enabled: false,
  exa_key_configured: false,
}

function setupMock(settings = defaultSettings) {
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(settings),
  } as unknown as Response)
}

describe('AgentSection', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('loads and displays settings from API', async () => {
    setupMock({ ...defaultSettings, agent_tool_creation: true })
    render(<AgentSection />)

    await waitFor(() => {
      expect(screen.getByText('Allow agents to propose tools')).toBeInTheDocument()
    })
    // The toggle should reflect the loaded setting
    const toggles = screen.getAllByTestId('toggle-switch')
    expect(toggles[0]).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows warning when agent_tool_creation is enabled', async () => {
    setupMock({ ...defaultSettings, agent_tool_creation: true })
    render(<AgentSection />)

    await waitFor(() => {
      expect(screen.getByText(/Agent-proposed tools are AI-generated/)).toBeInTheDocument()
    })
  })

  it('shows EXA_API_KEY warning when web_search is enabled but key is not configured', async () => {
    setupMock({ ...defaultSettings, web_search_enabled: true, exa_key_configured: false })
    render(<AgentSection />)

    await waitFor(() => {
      expect(screen.getByText(/EXA_API_KEY is not configured/)).toBeInTheDocument()
    })
  })

  it('toggles setting on click and calls API', async () => {
    const user = userEvent.setup()
    setupMock()
    // Mock the PUT response
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ...defaultSettings, agent_tool_creation: true }),
    } as unknown as Response)

    render(<AgentSection />)

    await waitFor(() => {
      expect(screen.getByText('Allow agents to propose tools')).toBeInTheDocument()
    })

    const toggles = screen.getAllByTestId('toggle-switch')
    await user.click(toggles[0])

    expect(mockApiFetch).toHaveBeenCalledWith('/api/settings/', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ agent_tool_creation: true }),
    }))
  })

  it('shows error when settings fetch fails', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('Network error'))
    render(<AgentSection />)

    await waitFor(() => {
      expect(screen.getByText('Failed to load settings')).toBeInTheDocument()
    })
  })

  it('shows risk warning when docs_fetch_enabled is enabled', async () => {
    setupMock({ ...defaultSettings, docs_fetch_enabled: true })
    render(<AgentSection />)

    await waitFor(() => {
      expect(screen.getByText(/adversarial content/)).toBeInTheDocument()
    })
  })
})
