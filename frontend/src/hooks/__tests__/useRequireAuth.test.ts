import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'

// Mock everything at module level with vi.hoisted
const { mockNavigate, mockIsAuthenticated } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockIsAuthenticated: vi.fn<() => boolean>().mockReturnValue(true),
}))

vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}))

vi.mock('../useAuth', () => ({
  useAuth: () => ({ isAuthenticated: mockIsAuthenticated() }),
}))

// Import after mocks are set up
import { useRequireAuth } from '../useRequireAuth'

describe('useRequireAuth', () => {
  beforeEach(() => {
    mockNavigate.mockClear()
    mockIsAuthenticated.mockReturnValue(true)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('does not navigate when authenticated', () => {
    mockIsAuthenticated.mockReturnValue(true)
    renderHook(() => useRequireAuth())
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('redirects to /login when not authenticated', () => {
    mockIsAuthenticated.mockReturnValue(false)
    renderHook(() => useRequireAuth())
    expect(mockNavigate).toHaveBeenCalledWith('/login', { replace: true })
  })

  it('uses replace navigation to prevent back-button return', () => {
    mockIsAuthenticated.mockReturnValue(false)
    renderHook(() => useRequireAuth())
    expect(mockNavigate).toHaveBeenCalledWith(expect.any(String), { replace: true })
  })
})
