import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiHeaders, apiFetch, API_URL, _setMixedContentBlocked } from '../api'

describe('apiHeaders', () => {
  it('returns Content-Type header (auth is via httpOnly cookies)', () => {
    const headers = apiHeaders()
    expect(headers).toEqual({ 'Content-Type': 'application/json' })
  })
})

describe('apiFetch', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('prepends API_URL to the path and calls fetch with merged headers', async () => {
    const mockResponse = new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse)

    await apiFetch('/api/agents/')

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [url, init] = fetchSpy.mock.calls[0]
    expect(url).toBe(`${API_URL}/api/agents/`)
    expect(init?.headers).toHaveProperty('Content-Type', 'application/json')
  })

  it('includes credentials: include for cookie-based auth', async () => {
    const mockResponse = new Response('{}', { status: 200 })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse)

    await apiFetch('/api/test')

    const init = fetchSpy.mock.calls[0][1]
    expect(init?.credentials).toBe('include')
  })

  it('allows caller headers to override defaults', async () => {
    const mockResponse = new Response('{}', { status: 200 })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse)

    await apiFetch('/api/test', {
      headers: { 'Content-Type': 'text/plain' },
    })

    const init = fetchSpy.mock.calls[0][1]
    expect(init?.headers).toHaveProperty('Content-Type', 'text/plain')
  })

  it('dispatches api:unauthorized event on 401 response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 401 }))
    const handler = vi.fn()
    window.addEventListener('api:unauthorized', handler)

    await apiFetch('/api/test')

    expect(handler).toHaveBeenCalledTimes(1)
    window.removeEventListener('api:unauthorized', handler)
  })

  it('does not dispatch api:unauthorized on non-401 responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 403 }))
    const handler = vi.fn()
    window.addEventListener('api:unauthorized', handler)

    await apiFetch('/api/test')

    expect(handler).not.toHaveBeenCalled()
    window.removeEventListener('api:unauthorized', handler)
  })
})

describe('apiFetch mixed-content blocking', () => {
  afterEach(() => {
    _setMixedContentBlocked(false)
  })

  it('throws when mixed-content is detected', async () => {
    _setMixedContentBlocked(true)

    await expect(apiFetch('/api/agents')).rejects.toThrow(
      'Blocked: API URL uses HTTP while page is served over HTTPS. Set VITE_API_URL to an HTTPS URL.'
    )
  })

  it('does not throw when mixed-content is not detected', async () => {
    _setMixedContentBlocked(false)
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }))

    await expect(apiFetch('/api/agents')).resolves.toBeDefined()
    fetchSpy.mockRestore()
  })
})
