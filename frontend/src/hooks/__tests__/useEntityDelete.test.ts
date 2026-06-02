import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useEntityDelete } from '../useEntityDelete'

// Mock apiFetch and extractApiError
vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(),
  extractApiError: vi.fn(),
}))

import { apiFetch, extractApiError } from '../../lib/api'
const mockApiFetch = vi.mocked(apiFetch)
const mockExtractApiError = vi.mocked(extractApiError)

describe('useEntityDelete', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
    mockExtractApiError.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('calls confirm with correct title and message', () => {
    const confirm = vi.fn()
    const onDeleted = vi.fn()

    const { result } = renderHook(() => useEntityDelete(
      '/api/tools',
      onDeleted,
      confirm,
      'tool',
    ))

    result.current('tool-1', 'search_splunk')

    expect(confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Delete Tool',
        message: 'Delete tool "search_splunk"? This cannot be undone.',
        danger: true,
      })
    )
  })

  it('calls confirm with default entity label "item"', () => {
    const confirm = vi.fn()
    const onDeleted = vi.fn()

    const { result } = renderHook(() => useEntityDelete(
      '/api/tools',
      onDeleted,
      confirm,
    ))

    result.current('id-1', 'something')

    expect(confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Delete Item',
        message: 'Delete item "something"? This cannot be undone.',
      })
    )
  })

  it('calls apiFetch with DELETE on confirm action', async () => {
    const confirm = vi.fn()
    const onDeleted = vi.fn()
    mockApiFetch.mockResolvedValueOnce({ ok: true })

    const { result } = renderHook(() => useEntityDelete(
      '/api/tools',
      onDeleted,
      confirm,
      'tool',
    ))

    result.current('tool-1', 'search_splunk')

    // Extract the action callback from confirm
    const confirmOpts = confirm.mock.calls[0][0]
    await act(async () => {
      await confirmOpts.action()
    })

    expect(mockApiFetch).toHaveBeenCalledWith('/api/tools/tool-1', { method: 'DELETE' })
  })

  it('calls onDeleted after successful delete', async () => {
    const confirm = vi.fn()
    const onDeleted = vi.fn()
    mockApiFetch.mockResolvedValueOnce({ ok: true })

    const { result } = renderHook(() => useEntityDelete(
      '/api/tools',
      onDeleted,
      confirm,
      'tool',
    ))

    result.current('tool-1', 'search_splunk')

    const confirmOpts = confirm.mock.calls[0][0]
    await act(async () => {
      await confirmOpts.action()
    })

    expect(onDeleted).toHaveBeenCalledWith('tool-1')
  })

  it('calls onAfterDelete after successful delete', async () => {
    const confirm = vi.fn()
    const onDeleted = vi.fn()
    const onAfterDelete = vi.fn()
    mockApiFetch.mockResolvedValueOnce({ ok: true })

    const { result } = renderHook(() => useEntityDelete(
      '/api/tools',
      onDeleted,
      confirm,
      'tool',
      onAfterDelete,
    ))

    result.current('tool-1', 'search_splunk')

    const confirmOpts = confirm.mock.calls[0][0]
    await act(async () => {
      await confirmOpts.action()
    })

    expect(onAfterDelete).toHaveBeenCalledWith('tool-1')
  })

  it('does not call onDeleted on API failure', async () => {
    const confirm = vi.fn()
    const onDeleted = vi.fn()
    mockApiFetch.mockResolvedValueOnce({ ok: false })
    mockExtractApiError.mockResolvedValueOnce('Delete failed')

    const { result } = renderHook(() => useEntityDelete(
      '/api/tools',
      onDeleted,
      confirm,
      'tool',
    ))

    result.current('tool-1', 'search_splunk')

    const confirmOpts = confirm.mock.calls[0][0]
    // The action catches the error internally
    await act(async () => {
      await confirmOpts.action()
    })

    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('does not call onAfterDelete on API failure', async () => {
    const confirm = vi.fn()
    const onDeleted = vi.fn()
    const onAfterDelete = vi.fn()
    mockApiFetch.mockResolvedValueOnce({ ok: false })
    mockExtractApiError.mockResolvedValueOnce('Delete failed')

    const { result } = renderHook(() => useEntityDelete(
      '/api/tools',
      onDeleted,
      confirm,
      'tool',
      onAfterDelete,
    ))

    result.current('tool-1', 'search_splunk')

    const confirmOpts = confirm.mock.calls[0][0]
    await act(async () => {
      await confirmOpts.action()
    })

    expect(onAfterDelete).not.toHaveBeenCalled()
  })

  it('calls onError with error message on API failure', async () => {
    const confirm = vi.fn()
    const onDeleted = vi.fn()
    const onError = vi.fn()
    mockApiFetch.mockResolvedValueOnce({ ok: false })
    mockExtractApiError.mockResolvedValueOnce('Delete failed')

    const { result } = renderHook(() => useEntityDelete(
      '/api/tools',
      onDeleted,
      confirm,
      'tool',
      undefined,
      onError,
    ))

    result.current('tool-1', 'search_splunk')

    const confirmOpts = confirm.mock.calls[0][0]
    await act(async () => {
      await confirmOpts.action()
    })

    expect(onError).toHaveBeenCalledWith('Delete failed')
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('does not call onError on success', async () => {
    const confirm = vi.fn()
    const onDeleted = vi.fn()
    const onError = vi.fn()
    mockApiFetch.mockResolvedValueOnce({ ok: true })

    const { result } = renderHook(() => useEntityDelete(
      '/api/tools',
      onDeleted,
      confirm,
      'tool',
      undefined,
      onError,
    ))

    result.current('tool-1', 'search_splunk')

    const confirmOpts = confirm.mock.calls[0][0]
    await act(async () => {
      await confirmOpts.action()
    })

    expect(onError).not.toHaveBeenCalled()
    expect(onDeleted).toHaveBeenCalledWith('tool-1')
  })
})
