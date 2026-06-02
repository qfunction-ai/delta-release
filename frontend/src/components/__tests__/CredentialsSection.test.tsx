import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CredentialsSection from '../CredentialsSection'

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

// Mock useConfirmDialog
vi.mock('../../hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn(), dialog: null }),
}))

// Mock LoadingSpinner
vi.mock('./LoadingSpinner', () => ({
  LoadingSpinner: () => <div data-testid="loading-spinner" />,
}))

const MOCK_CREDENTIALS = [
  {
    id: 'cred-1',
    key: 'SPLUNK_CREDS',
    name: 'Splunk Login',
    provider: 'basic_auth',
    url: null,
    has_secondary_key: true,
    created_at: '2026-01-10T00:00:00Z',
    updated_at: '2026-01-10T00:00:00Z',
  },
]

function setupFetchMocks(credentials = MOCK_CREDENTIALS) {
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(credentials),
  } as unknown as Response)
}

function renderCredentials() {
  return render(
    <MemoryRouter>
      <CredentialsSection />
    </MemoryRouter>
  )
}

describe('CredentialsSection', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('renders credential list after loading', async () => {
    setupFetchMocks()
    renderCredentials()

    await waitFor(() => {
      expect(screen.getByText('Splunk Login')).toBeInTheDocument()
    })
    expect(screen.getByText('SPLUNK_CREDS')).toBeInTheDocument()
  })

  it('shows empty state when no credentials exist', async () => {
    setupFetchMocks([])
    renderCredentials()

    await waitFor(() => {
      expect(screen.getByText('No credentials stored. Add one above to get started.')).toBeInTheDocument()
    })
  })

  it('renders Add Credential form with type selector', async () => {
    setupFetchMocks()
    renderCredentials()

    await waitFor(() => {
      expect(screen.getByText('Add Credential')).toBeInTheDocument()
    })
    // Type selector pills
    expect(screen.getAllByText('Username / Password').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('API Key').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('API Key Pair').length).toBeGreaterThanOrEqual(1)
  })

  it('shows Key and Name fields in the create form', async () => {
    setupFetchMocks()
    renderCredentials()

    await waitFor(() => {
      expect(screen.getByLabelText('Key')).toBeInTheDocument()
      expect(screen.getByLabelText('Name')).toBeInTheDocument()
    })
  })

  it('shows Delete button for each credential', async () => {
    setupFetchMocks()
    renderCredentials()

    await waitFor(() => {
      expect(screen.getByText('Splunk Login')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })

  it('shows error when credential fetch fails', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('Network error'))
    renderCredentials()

    await waitFor(() => {
      expect(screen.getByText('Failed to connect to server')).toBeInTheDocument()
    })
  })
})
