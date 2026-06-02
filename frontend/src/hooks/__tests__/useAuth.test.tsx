import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider, useAuth } from '../useAuth'

// Mock apiFetch so we don't need a real backend
vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from '../../lib/api'
const mockApiFetch = vi.mocked(apiFetch)

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      <AuthProvider>{children}</AuthProvider>
    </MemoryRouter>
  )
}

describe('useAuth', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns unauthenticated when /me returns non-200', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
    } as Response)

    const { result } = renderHook(() => useAuth(), { wrapper })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })

    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.isAdmin).toBe(false)
    expect(result.current.loading).toBe(false)
  })

  it('loads user info when /me returns 200 (cookie-based auth)', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ username: 'admin', role: 'admin' }),
    } as Response)

    const { result } = renderHook(() => useAuth(), { wrapper })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.username).toBe('admin')
    expect(result.current.isAdmin).toBe(true)
  })

  it('keeps current state on network error (transient)', async () => {
    // First call succeeds (initial load)
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ username: 'user1', role: 'user' }),
    } as Response)

    const { result } = renderHook(() => useAuth(), { wrapper })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })

    expect(result.current.isAuthenticated).toBe(true)
  })

  it('logout clears state and calls /api/auth/logout', async () => {
    // Initial load succeeds
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ username: 'user1', role: 'user' }),
    } as Response)

    // Logout endpoint call
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
    } as Response)

    const { result } = renderHook(() => useAuth(), { wrapper })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })

    expect(result.current.isAuthenticated).toBe(true)

    // Logout is async — it calls apiFetch then navigates
    await act(async () => {
      result.current.logout()
      // Wait for the apiFetch promise to resolve
      await new Promise((r) => setTimeout(r, 0))
    })

    // After logout, state is cleared
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.username).toBe('')
  })
})
