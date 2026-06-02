import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useSSEStream } from '../useSSEStream'
import { SSEEvent } from '../../lib/sse'

// Mock parseSSEStream
vi.mock('../../lib/sse', () => ({
  parseSSEStream: vi.fn(),
}))

import { parseSSEStream } from '../../lib/sse'
const mockParseSSEStream = vi.mocked(parseSSEStream)

// rAF mock — store callbacks and let us flush them manually
let rafCallbacks: Map<number, FrameRequestCallback> = new Map()
let rafIdCounter = 0

beforeEach(() => {
  rafCallbacks.clear()
  rafIdCounter = 0
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
    const id = ++rafIdCounter
    rafCallbacks.set(id, cb)
    return id
  })
  vi.spyOn(window, 'cancelAnimationFrame').mockImplementation((id) => {
    rafCallbacks.delete(id)
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

/** Flush all pending rAF callbacks */
function flushRAF() {
  const callbacks = [...rafCallbacks.values()]
  rafCallbacks.clear()
  callbacks.forEach(cb => cb(0))
}

/** Create a mock Response with a ReadableStream body */
function mockResponse(events: SSEEvent[]): Response {
  const reader = {
    read: vi.fn(),
    cancel: vi.fn(),
  }

  let callIndex = 0
  reader.read.mockImplementation(async () => {
    if (callIndex < events.length) {
      return { done: false, value: events[callIndex++] }
    }
    return { done: true, value: undefined }
  })

  const response = {
    body: {
      getReader: () => reader,
    },
  } as unknown as Response

  return response
}

/** Set up parseSSEStream to yield the given events */
async function* yieldEvents(events: SSEEvent[]) {
  for (const event of events) {
    yield event
  }
}

describe('useSSEStream', () => {
  it('sets streaming to false after stream completes', async () => {
    mockParseSSEStream.mockReturnValue(yieldEvents([]))

    const { result } = renderHook(() => useSSEStream({
      onContent: vi.fn(),
      onError: vi.fn(),
    }))

    expect(result.current.streaming).toBe(false)

    const response = mockResponse([])
    await result.current.startStream(response)

    expect(result.current.streaming).toBe(false)
  })

  it('calls onContent with buffered content on rAF flush', async () => {
    const onContent = vi.fn()
    const events: SSEEvent[] = [
      { type: 'content', message_type: 'assistant_message', content: 'Hello ' },
      { type: 'content', message_type: 'assistant_message', content: 'World' },
    ]
    mockParseSSEStream.mockReturnValue(yieldEvents(events))

    const { result } = renderHook(() => useSSEStream({
      onContent,
      onError: vi.fn(),
    }))

    const response = mockResponse(events)
    await result.current.startStream(response)

    // Flush the final rAF (the hook does cancelAnimationFrame + flush after the loop)
    flushRAF()

    // onContent should have been called with the accumulated content
    expect(onContent).toHaveBeenCalledWith('Hello World', '')
  })

  it('accumulates reasoning from reasoning_message events', async () => {
    const onContent = vi.fn()
    const events: SSEEvent[] = [
      { type: 'content', message_type: 'assistant_message', content: 'answer' },
      { type: 'content', message_type: 'reasoning_message', content: 'thinking' },
    ]
    mockParseSSEStream.mockReturnValue(yieldEvents(events))

    const { result } = renderHook(() => useSSEStream({
      onContent,
      onError: vi.fn(),
    }))

    const response = mockResponse(events)
    await result.current.startStream(response)
    flushRAF()

    expect(onContent).toHaveBeenCalledWith('answer', 'thinking')
  })

  it('calls onError on error event and stops streaming', async () => {
    const onError = vi.fn()
    const events: SSEEvent[] = [
      { type: 'content', message_type: 'assistant_message', content: 'partial' },
      { type: 'error', error: 'Something broke' },
    ]
    mockParseSSEStream.mockReturnValue(yieldEvents(events))

    const { result } = renderHook(() => useSSEStream({
      onContent: vi.fn(),
      onError,
    }))

    const response = mockResponse(events)
    await result.current.startStream(response)
    flushRAF()

    expect(onError).toHaveBeenCalledWith('Something broke')
    expect(result.current.streaming).toBe(false)
  })

  it('breaks on status completed', async () => {
    const onContent = vi.fn()
    const onCompleted = vi.fn()
    const events: SSEEvent[] = [
      { type: 'content', message_type: 'assistant_message', content: 'done' },
      { type: 'status', status: 'completed' },
      // This event should NOT be yielded — the loop breaks on completed
    ]
    mockParseSSEStream.mockReturnValue(yieldEvents(events))

    const { result } = renderHook(() => useSSEStream({
      onContent,
      onError: vi.fn(),
      onCompleted,
    }))

    const response = mockResponse(events)
    await result.current.startStream(response)
    flushRAF()

    expect(onContent).toHaveBeenCalledWith('done', '')
    expect(onCompleted).toHaveBeenCalled()
  })

  it('calls onCompleted after stream ends', async () => {
    const onCompleted = vi.fn()
    mockParseSSEStream.mockReturnValue(yieldEvents([]))

    const { result } = renderHook(() => useSSEStream({
      onContent: vi.fn(),
      onError: vi.fn(),
      onCompleted,
    }))

    const response = mockResponse([])
    await result.current.startStream(response)

    expect(onCompleted).toHaveBeenCalledTimes(1)
  })

  it('cancels the reader after streaming', async () => {
    mockParseSSEStream.mockReturnValue(yieldEvents([]))

    const { result } = renderHook(() => useSSEStream({
      onContent: vi.fn(),
      onError: vi.fn(),
    }))

    const response = mockResponse([])
    const reader = response.body!.getReader()
    await result.current.startStream(response)

    expect(reader.cancel).toHaveBeenCalled()
  })

  it('sets streaming to false when response has no body', async () => {
    mockParseSSEStream.mockReturnValue(yieldEvents([]))

    const { result } = renderHook(() => useSSEStream({
      onContent: vi.fn(),
      onError: vi.fn(),
    }))

    const response = { body: null } as unknown as Response
    await result.current.startStream(response)

    expect(result.current.streaming).toBe(false)
  })

  it('sets streaming to false even on error in the stream loop', async () => {
    mockParseSSEStream.mockImplementation(function* () {
      throw new Error('Stream error')
    })

    const { result } = renderHook(() => useSSEStream({
      onContent: vi.fn(),
      onError: vi.fn(),
    }))

    const response = mockResponse([])
    const reader = response.body!.getReader()

    // The hook catches errors in the finally block
    await result.current.startStream(response).catch(() => {})

    expect(result.current.streaming).toBe(false)
    expect(reader.cancel).toHaveBeenCalled()
  })
})
