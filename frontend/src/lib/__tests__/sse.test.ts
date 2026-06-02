import { describe, it, expect } from 'vitest'
import { parseSSEStream } from '../sse'
import type { SSEEvent } from '../sse'

/** Build a ReadableStream from chunks of SSE-formatted text. */
function makeStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    pull(controller) {
      if (chunks.length === 0) {
        controller.close()
        return
      }
      controller.enqueue(encoder.encode(chunks.shift()!))
    },
  })
}

async function collect(gen: AsyncGenerator<SSEEvent>): Promise<SSEEvent[]> {
  const results: SSEEvent[] = []
  for await (const event of gen) {
    results.push(event)
  }
  return results
}

describe('parseSSEStream', () => {
  it('parses single-line data events', async () => {
    const stream = makeStream(['data: {"type":"status","content":"ok"}\n\n'])
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    const events = await collect(parseSSEStream(reader, decoder))

    expect(events).toHaveLength(1)
    expect(events[0]).toEqual({ type: 'status', content: 'ok' })
  })

  it('parses multiple events in one chunk', async () => {
    const stream = makeStream([
      'data: {"type":"a"}\ndata: {"type":"b"}\n\n',
    ])
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    const events = await collect(parseSSEStream(reader, decoder))

    expect(events).toHaveLength(2)
    expect(events[0].type).toBe('a')
    expect(events[1].type).toBe('b')
  })

  it('handles partial lines split across chunks', async () => {
    const stream = makeStream([
      'data: {"type":"',
      'progress","content":"50%"}\n\n',
    ])
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    const events = await collect(parseSSEStream(reader, decoder))

    expect(events).toHaveLength(1)
    expect(events[0]).toEqual({ type: 'progress', content: '50%' })
  })

  it('ignores non-data lines', async () => {
    const stream = makeStream([
      'event: update\nid: 1\ndata: {"type":"tick"}\nretry: 5000\n\n',
    ])
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    const events = await collect(parseSSEStream(reader, decoder))

    expect(events).toHaveLength(1)
    expect(events[0].type).toBe('tick')
  })

  it('silently skips malformed JSON', async () => {
    const stream = makeStream([
      'data: not-json\n\ndata: {"type":"ok"}\n\n',
    ])
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    const events = await collect(parseSSEStream(reader, decoder))

    expect(events).toHaveLength(1)
    expect(events[0].type).toBe('ok')
  })

  it('handles empty stream', async () => {
    const stream = makeStream([])
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    const events = await collect(parseSSEStream(reader, decoder))

    expect(events).toHaveLength(0)
  })
})
