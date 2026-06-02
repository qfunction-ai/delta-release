import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useGithubImport } from '../useGithubImport'

// Mock apiFetch
vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from '../../lib/api'
const mockApiFetch = vi.mocked(apiFetch)

describe('useGithubImport', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('initializes with empty url and not fetching', () => {
    const { result } = renderHook(() => useGithubImport({
      endpoint: '/api/tools/github',
      errorLabel: 'tool',
      onSuccess: vi.fn(),
      onError: vi.fn(),
    }))

    expect(result.current.githubUrl).toBe('')
    expect(result.current.fetchingGithub).toBe(false)
  })

  it('updates githubUrl via setGithubUrl', () => {
    const { result } = renderHook(() => useGithubImport({
      endpoint: '/api/tools/github',
      errorLabel: 'tool',
      onSuccess: vi.fn(),
      onError: vi.fn(),
    }))

    act(() => {
      result.current.setGithubUrl('https://github.com/example/repo')
    })

    expect(result.current.githubUrl).toBe('https://github.com/example/repo')
  })

  it('calls apiFetch with correct endpoint and body on submit', async () => {
    const onSuccess = vi.fn()
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 'tool-1', name: 'new-tool' }),
    })

    const { result } = renderHook(() => useGithubImport({
      endpoint: '/api/tools/github',
      errorLabel: 'tool',
      onSuccess,
      onError: vi.fn(),
    }))

    act(() => {
      result.current.setGithubUrl('https://github.com/example/repo')
    })

    await act(async () => {
      await result.current.handleGithub({ preventDefault: vi.fn() } as unknown as React.FormEvent)
    })

    expect(mockApiFetch).toHaveBeenCalledWith('/api/tools/github', {
      method: 'POST',
      body: JSON.stringify({ github_url: 'https://github.com/example/repo' }),
    })
  })

  it('calls onSuccess with response data on success', async () => {
    const onSuccess = vi.fn()
    const responseData = { id: 'tool-1', name: 'new-tool' }
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => responseData,
    })

    const { result } = renderHook(() => useGithubImport({
      endpoint: '/api/tools/github',
      errorLabel: 'tool',
      onSuccess,
      onError: vi.fn(),
    }))

    act(() => {
      result.current.setGithubUrl('https://github.com/example/repo')
    })

    await act(async () => {
      await result.current.handleGithub({ preventDefault: vi.fn() } as unknown as React.FormEvent)
    })

    expect(onSuccess).toHaveBeenCalledWith(responseData)
  })

  it('clears githubUrl after successful import', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 'tool-1' }),
    })

    const { result } = renderHook(() => useGithubImport({
      endpoint: '/api/tools/github',
      errorLabel: 'tool',
      onSuccess: vi.fn(),
      onError: vi.fn(),
    }))

    act(() => {
      result.current.setGithubUrl('https://github.com/example/repo')
    })

    await act(async () => {
      await result.current.handleGithub({ preventDefault: vi.fn() } as unknown as React.FormEvent)
    })

    expect(result.current.githubUrl).toBe('')
  })

  it('calls onError with detail on API failure', async () => {
    const onError = vi.fn()
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Repository not found' }),
    })

    const { result } = renderHook(() => useGithubImport({
      endpoint: '/api/tools/github',
      errorLabel: 'tool',
      onSuccess: vi.fn(),
      onError,
    }))

    act(() => {
      result.current.setGithubUrl('https://github.com/example/bad')
    })

    await act(async () => {
      await result.current.handleGithub({ preventDefault: vi.fn() } as unknown as React.FormEvent)
    })

    expect(onError).toHaveBeenCalledWith('Repository not found')
  })

  it('calls onError with fallback message when API has no detail', async () => {
    const onError = vi.fn()
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({}),
    })

    const { result } = renderHook(() => useGithubImport({
      endpoint: '/api/skills/github',
      errorLabel: 'skill',
      onSuccess: vi.fn(),
      onError,
    }))

    act(() => {
      result.current.setGithubUrl('https://github.com/example/bad')
    })

    await act(async () => {
      await result.current.handleGithub({ preventDefault: vi.fn() } as unknown as React.FormEvent)
    })

    expect(onError).toHaveBeenCalledWith('Failed to fetch skill from GitHub (500)')
  })

  it('calls onError with CONNECTION on network failure', async () => {
    const onError = vi.fn()
    mockApiFetch.mockRejectedValueOnce(new Error('Network error'))

    const { result } = renderHook(() => useGithubImport({
      endpoint: '/api/tools/github',
      errorLabel: 'tool',
      onSuccess: vi.fn(),
      onError,
    }))

    act(() => {
      result.current.setGithubUrl('https://github.com/example/repo')
    })

    await act(async () => {
      await result.current.handleGithub({ preventDefault: vi.fn() } as unknown as React.FormEvent)
    })

    expect(onError).toHaveBeenCalledWith('Failed to connect to server')
  })

  it('does not submit when githubUrl is empty', async () => {
    const { result } = renderHook(() => useGithubImport({
      endpoint: '/api/tools/github',
      errorLabel: 'tool',
      onSuccess: vi.fn(),
      onError: vi.fn(),
    }))

    await act(async () => {
      await result.current.handleGithub({ preventDefault: vi.fn() } as unknown as React.FormEvent)
    })

    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  it('does not submit when githubUrl is whitespace only', async () => {
    const { result } = renderHook(() => useGithubImport({
      endpoint: '/api/tools/github',
      errorLabel: 'tool',
      onSuccess: vi.fn(),
      onError: vi.fn(),
    }))

    act(() => {
      result.current.setGithubUrl('   ')
    })

    await act(async () => {
      await result.current.handleGithub({ preventDefault: vi.fn() } as unknown as React.FormEvent)
    })

    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  it('sets fetchingGithub to false after successful fetch', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 'tool-1' }),
    })

    const { result } = renderHook(() => useGithubImport({
      endpoint: '/api/tools/github',
      errorLabel: 'tool',
      onSuccess: vi.fn(),
      onError: vi.fn(),
    }))

    act(() => {
      result.current.setGithubUrl('https://github.com/example/repo')
    })

    await act(async () => {
      await result.current.handleGithub({ preventDefault: vi.fn() } as unknown as React.FormEvent)
    })

    expect(result.current.fetchingGithub).toBe(false)
  })

  it('sets fetchingGithub to false even on error', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('fail'))

    const { result } = renderHook(() => useGithubImport({
      endpoint: '/api/tools/github',
      errorLabel: 'tool',
      onSuccess: vi.fn(),
      onError: vi.fn(),
    }))

    act(() => {
      result.current.setGithubUrl('https://github.com/example/repo')
    })

    await act(async () => {
      await result.current.handleGithub({ preventDefault: vi.fn() } as unknown as React.FormEvent)
    })

    expect(result.current.fetchingGithub).toBe(false)
  })
})
