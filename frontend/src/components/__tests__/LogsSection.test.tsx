import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import LogsSection from '../LogsSection'

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

// Mock LoadingSpinner
vi.mock('./LoadingSpinner', () => ({
  LoadingSpinner: () => <div data-testid="loading-spinner" />,
}))

const MOCK_LOG_DATA = {
  entries: [
    { timestamp: '2026-01-10T09:00:00Z', service: 'backend', level: 'INFO', module: 'api', message: 'Server started' },
    { timestamp: '2026-01-10T09:01:00Z', service: 'audit', level: 'WARNING', module: 'auth', message: 'Failed login attempt' },
    { timestamp: '2026-01-10T09:02:00Z', service: 'letta', level: 'ERROR', module: 'agent', message: 'Agent timeout' },
  ],
  total: 3,
}

function setupFetchMocks(data = MOCK_LOG_DATA) {
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(data),
  } as unknown as Response)
}

describe('LogsSection', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('renders log entries after loading', async () => {
    setupFetchMocks()
    render(<LogsSection />)

    await waitFor(() => {
      expect(screen.getByText('Server started')).toBeInTheDocument()
    })
    expect(screen.getByText('Failed login attempt')).toBeInTheDocument()
    expect(screen.getByText('Agent timeout')).toBeInTheDocument()
  })

  it('shows log level badges', async () => {
    setupFetchMocks()
    render(<LogsSection />)

    await waitFor(() => {
      expect(screen.getByText('INFO')).toBeInTheDocument()
    })
    expect(screen.getByText('WARNING')).toBeInTheDocument()
    expect(screen.getByText('ERROR')).toBeInTheDocument()
  })

  it('shows service filter pills', async () => {
    setupFetchMocks()
    render(<LogsSection />)

    await waitFor(() => {
      expect(screen.getByText('Server started')).toBeInTheDocument()
    })
    // 'All' appears twice (service and level filters)
    expect(screen.getAllByText('All')).toHaveLength(2)
    expect(screen.getByText('Audit')).toBeInTheDocument()
    expect(screen.getByText('Backend')).toBeInTheDocument()
    expect(screen.getByText('Letta')).toBeInTheDocument()
  })

  it('shows empty state when no logs found', async () => {
    setupFetchMocks({ entries: [], total: 0 })
    render(<LogsSection />)

    await waitFor(() => {
      expect(screen.getByText('No log entries found')).toBeInTheDocument()
    })
  })

  it('shows search input for filtering', async () => {
    setupFetchMocks()
    render(<LogsSection />)

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Filter by text...')).toBeInTheDocument()
    })
  })

  it('shows total entry count', async () => {
    setupFetchMocks()
    render(<LogsSection />)

    await waitFor(() => {
      expect(screen.getByText('3 entries')).toBeInTheDocument()
    })
  })
})
