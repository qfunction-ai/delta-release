import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import PackagesSection from '../PackagesSection'

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

const MOCK_PACKAGES = [
  { name: 'requests', version: '2.31.0' },
  { name: 'httpx', version: '0.27.0' },
]

function setupFetchMocks(packages = MOCK_PACKAGES) {
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(packages),
  } as unknown as Response)
}

function renderPackages() {
  return render(
    <MemoryRouter>
      <PackagesSection />
    </MemoryRouter>
  )
}

describe('PackagesSection', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('renders installed packages list', async () => {
    setupFetchMocks()
    renderPackages()

    await waitFor(() => {
      expect(screen.getByText('requests')).toBeInTheDocument()
    })
    expect(screen.getByText('httpx')).toBeInTheDocument()
  })

  it('shows version badges for each package', async () => {
    setupFetchMocks()
    renderPackages()

    await waitFor(() => {
      expect(screen.getByText('v2.31.0')).toBeInTheDocument()
    })
    expect(screen.getByText('v0.27.0')).toBeInTheDocument()
  })

  it('shows empty state when no packages installed', async () => {
    setupFetchMocks([])
    renderPackages()

    await waitFor(() => {
      expect(screen.getByText('No packages installed. Install one above to get started.')).toBeInTheDocument()
    })
  })

  it('renders Install Package form with input and button', async () => {
    setupFetchMocks()
    renderPackages()

    await waitFor(() => {
      expect(screen.getByText('Install Package')).toBeInTheDocument()
    })
    expect(screen.getByPlaceholderText('requests, paramiko==2.12.0')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Install' })).toBeInTheDocument()
  })

  it('shows Uninstall button for each package', async () => {
    setupFetchMocks()
    renderPackages()

    await waitFor(() => {
      expect(screen.getByText('requests')).toBeInTheDocument()
    })
    expect(screen.getAllByRole('button', { name: 'Uninstall' })).toHaveLength(2)
  })

  it('shows error when package fetch fails', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('Network error'))
    renderPackages()

    await waitFor(() => {
      expect(screen.getAllByText('Failed to connect to server').length).toBeGreaterThanOrEqual(1)
    })
  })
})
