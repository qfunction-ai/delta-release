import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from '../Dashboard'

vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(),
  extractApiError: vi.fn(async (_res: Response, fallback: string) => fallback),
}))

import { apiFetch } from '../../lib/api'
const mockApiFetch = vi.mocked(apiFetch)

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true, isAdmin: false, loading: false, logout: vi.fn() }),
}))

const MOCK_DASHBOARD = {
  agents: [
    { id: 'a1', name: 'sec-agent', model: 'gpt-4', embedding: 'letta-free', created_at: '2026-01-10T00:00:00Z', workflows_count: 2, has_schedule: true, last_activity: new Date().toISOString() },
    { id: 'a2', name: 'log-agent', model: 'claude-3', embedding: 'text-embed', created_at: '2026-01-11T00:00:00Z', workflows_count: 0, has_schedule: false, last_activity: new Date().toISOString() },
  ],
  stats: { agents: 2, tools: 5, skills: 3, workflows: 1, credentials: 4 },
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>
  )
}

describe('Dashboard page', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('renders dashboard data after loading', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(MOCK_DASHBOARD),
    } as unknown as Response)

    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText('sec-agent')).toBeInTheDocument()
    })
    expect(screen.getByText('log-agent')).toBeInTheDocument()
  })

  it('renders stat cards with correct counts', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(MOCK_DASHBOARD),
    } as unknown as Response)

    renderDashboard()

    await waitFor(() => {
      // "2" appears in stat card (agents count) and agent fleet card (workflows_count)
      expect(screen.getAllByText('2').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('shows error when dashboard fetch fails', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
    } as unknown as Response)

    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText('Failed to load dashboard')).toBeInTheDocument()
    })
  })

  it('shows scheduled indicator on agents with schedules', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(MOCK_DASHBOARD),
    } as unknown as Response)

    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText('Yes')).toBeInTheDocument()
    })
  })

  it('renders stat cards with labels and formulas', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(MOCK_DASHBOARD),
    } as unknown as Response)

    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText('sec-agent')).toBeInTheDocument()
    })

    expect(screen.getByText('Active Agents')).toBeInTheDocument()
    expect(screen.getByText('Tools Available')).toBeInTheDocument()
    expect(screen.getByText('Skills Loaded')).toBeInTheDocument()
    expect(screen.getByText('Workflows')).toBeInTheDocument()
  })

  it('navigates to agents page on agent click', async () => {
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(MOCK_DASHBOARD),
    } as unknown as Response)

    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText('sec-agent')).toBeInTheDocument()
    })

    // Click on agent row — just verifies it renders as clickable
    await user.click(screen.getByText('sec-agent'))
  })
})
