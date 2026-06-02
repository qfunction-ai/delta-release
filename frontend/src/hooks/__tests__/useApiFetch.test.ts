import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useApiFetch } from '../useApiFetch'

// Mock the api module
vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(),
  extractApiError: vi.fn(),
}))

import { apiFetch, extractApiError } from '../../lib/api'

const mockApiFetch = vi.mocked(apiFetch)
const mockExtractApiError = vi.mocked(extractApiError)

describe('useApiFetch', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches data on mount by default', async () => {
    const mockData = { id: 1, name: 'test' }
    const mockResponse = { ok: true, json: vi.fn().mockResolvedValue(mockData) } as unknown as Response
    mockApiFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useApiFetch('/api/test'))

    // Initially loading
    expect(result.current.loading).toBe(true)

    // Wait for fetch to complete
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })

    expect(mockApiFetch).toHaveBeenCalledWith('/api/test', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(result.current.data).toEqual(mockData)
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe('')
  })

  it('does not fetch on mount when immediate is false', async () => {
    const { result } = renderHook(() => useApiFetch('/api/test', { immediate: false }))

    expect(result.current.loading).toBe(false)
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  it('sets error on non-ok response', async () => {
    const mockResponse = { ok: false, status: 404 } as unknown as Response
    mockApiFetch.mockResolvedValue(mockResponse)
    mockExtractApiError.mockResolvedValue('Not found')

    const { result } = renderHook(() => useApiFetch('/api/test', { errorMessage: 'Load failed' }))

    await act(async () => { await new Promise(r => setTimeout(r, 0)) })

    expect(mockExtractApiError).toHaveBeenCalledWith(mockResponse, 'Load failed')
    expect(result.current.error).toBe('Not found')
    expect(result.current.data).toBeNull()
  })

  it('sets connection error on network failure', async () => {
    mockApiFetch.mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useApiFetch('/api/test', { connectionErrorMessage: 'Cannot connect' }))

    await act(async () => { await new Promise(r => setTimeout(r, 0)) })

    expect(result.current.error).toBe('Cannot connect')
  })

  it('uses errorMessage as fallback for connection errors', async () => {
    mockApiFetch.mockRejectedValue(new Error('fail'))

    const { result } = renderHook(() => useApiFetch('/api/test', { errorMessage: 'Load failed' }))

    await act(async () => { await new Promise(r => setTimeout(r, 0)) })

    expect(result.current.error).toBe('Load failed')
  })

  it('refetch fetches with override URL', async () => {
    const mockData = { items: [] }
    const mockResponse = { ok: true, json: vi.fn().mockResolvedValue(mockData) } as unknown as Response
    mockApiFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useApiFetch('/api/test', { immediate: false }))

    await act(async () => {
      await result.current.refetch('/api/other')
    })

    expect(mockApiFetch).toHaveBeenCalledWith('/api/other', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(result.current.data).toEqual(mockData)
  })

  it('aborts previous request on refetch', async () => {
    let resolveFirst: (v: Response) => void
    const firstPromise = new Promise<Response>(resolve => { resolveFirst = resolve })
    const secondData = { fresh: true }
    const secondResponse = { ok: true, json: vi.fn().mockResolvedValue(secondData) } as unknown as Response

    mockApiFetch
      .mockReturnValueOnce(firstPromise)
      .mockResolvedValueOnce(secondResponse)

    const { result } = renderHook(() => useApiFetch('/api/test', { immediate: false }))

    // Start first fetch
    let firstFetchDone: () => void
    const firstFetchPromise = new Promise<void>(resolve => { firstFetchDone = resolve })
    act(() => { result.current.refetch().then(firstFetchDone) })

    // Start second fetch (should abort first)
    await act(async () => {
      await result.current.refetch()
    })

    // Second fetch should have completed
    expect(result.current.data).toEqual(secondData)
  })

  it('ignores AbortError', async () => {
    const abortError = new DOMException('The operation was aborted', 'AbortError')
    mockApiFetch.mockRejectedValue(abortError)

    const { result } = renderHook(() => useApiFetch('/api/test', { immediate: false }))

    await act(async () => {
      await result.current.refetch()
    })

    // Should not set error for aborted requests
    expect(result.current.error).toBe('')
  })

  it('exposes setData and setError', async () => {
    const mockResponse = { ok: true, json: vi.fn().mockResolvedValue({ id: 1 }) } as unknown as Response
    mockApiFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useApiFetch('/api/test', { immediate: false }))

    act(() => {
      result.current.setData({ id: 99 } as never)
      result.current.setError('manual error')
    })

    expect(result.current.data).toEqual({ id: 99 })
    expect(result.current.error).toBe('manual error')
  })
})
