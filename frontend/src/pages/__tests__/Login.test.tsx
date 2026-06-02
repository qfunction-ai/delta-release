import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Login from '../Login'

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

// Mock useAuth — Login calls refreshAuth after login/register
const mockRefreshAuth = vi.fn().mockResolvedValue(undefined)
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    refreshAuth: mockRefreshAuth,
    isAuthenticated: false,
    loading: false,
    username: '',
    role: 'user',
    isAdmin: false,
    logout: vi.fn(),
  }),
}))

// Mock localStorage
let store: Record<string, string> = {}
vi.stubGlobal('localStorage', {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => { store[key] = value },
  removeItem: (key: string) => { delete store[key] },
  clear: () => { store = {} },
  get length() { return Object.keys(store).length },
  key: (_i: number) => null,
})

// Capture navigate calls
let navigateArgs: string[] = []
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => (path: string) => { navigateArgs.push(path) },
  }
})

function renderLogin() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  )
}

describe('Login page', () => {
  beforeEach(() => {
    store = {}
    mockApiFetch.mockReset()
    mockRefreshAuth.mockReset().mockResolvedValue(undefined)
    navigateArgs = []
  })

  it('shows login form when setup is not needed', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ needs_setup: false, requires_setup_token: false }),
    } as unknown as Response)

    renderLogin()

    await waitFor(() => {
      expect(screen.getByText('Login')).toBeInTheDocument()
    })
  })

  it('shows registration form when setup is needed', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ needs_setup: true, requires_setup_token: false }),
    } as unknown as Response)

    renderLogin()

    await waitFor(() => {
      expect(screen.getByText('Create Account')).toBeInTheDocument()
    })
  })

  it('shows setup token field when required', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ needs_setup: true, requires_setup_token: true }),
    } as unknown as Response)

    renderLogin()

    await waitFor(() => {
      expect(screen.getByText('Setup Token')).toBeInTheDocument()
    })
  })

  it('submits login form and navigates to home', async () => {
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ needs_setup: false, requires_setup_token: false }),
    } as unknown as Response)

    // Login response
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ access_token: 'test-jwt' }),
    } as unknown as Response)

    renderLogin()

    await waitFor(() => {
      expect(screen.getByText('Login')).toBeInTheDocument()
    })

    const usernameInput = screen.getByLabelText('Username')
    const passwordInput = screen.getByLabelText('Password')

    await user.type(usernameInput, 'admin')
    await user.type(passwordInput, 'password123')
    await user.click(screen.getByRole('button', { name: 'Login' }))

    await waitFor(() => {
      expect(mockRefreshAuth).toHaveBeenCalled()
      expect(navigateArgs).toContain('/')
    })
  })

  it('shows API error on failed login', async () => {
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ needs_setup: false, requires_setup_token: false }),
    } as unknown as Response)

    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: 'Invalid credentials' }),
    } as unknown as Response)

    renderLogin()

    await waitFor(() => {
      expect(screen.getByText('Login')).toBeInTheDocument()
    })

    const usernameInput = screen.getByLabelText('Username')
    const passwordInput = screen.getByLabelText('Password')

    await user.type(usernameInput, 'admin')
    await user.type(passwordInput, 'wrongpassword')
    await user.click(screen.getByRole('button', { name: 'Login' }))

    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument()
    })
  })
})
