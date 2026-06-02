import { useState, useCallback, useRef, useEffect } from 'react'
import { parseSSEStream } from '../lib/sse'

interface UseSSEStreamOptions {
  /** Called with accumulated content/reasoning at most once per animation frame. */
  onContent: (content: string, reasoning: string) => void
  /** Called when the stream sends an error event. */
  onError: (error: string) => void
  /** Called after the stream ends (completed, error, or reader done). */
  onCompleted?: () => void
  /** Called when a security event is detected in the stream (e.g. canary output redaction). */
  onSecurityEvent?: (event: string, message: string) => void
  /** Called when a secret is detected in the user's message (warn only, not blocked). */
  onSecretWarning?: (warnings: string[]) => void
}

/**
 * Hook for consuming an SSE stream with rAF-throttled content updates.
 *
 * Buffers incoming SSE content chunks in a ref and flushes to state
 * at most once per animation frame via `onContent`. This prevents
 * rapid re-renders from high-frequency streaming chunks.
 *
 * Returns `cancelStream` to abort an in-progress stream, and
 * automatically cancels on component unmount.
 *
 * Usage:
 *   const { streaming, startStream, cancelStream } = useSSEStream({
 *     onContent: (content, reasoning) => {
 *       if (content) setOutput(prev => prev + content)
 *       if (reasoning) setReasoning(prev => prev + reasoning)
 *     },
 *     onError: (error) => setError(error),
 *     onCompleted: () => finalizeMessage(),
 *   })
 *
 *   const response = await apiFetch('/api/chat/stream', { ... })
 *   if (!response.ok) { handleError(); return }
 *   await startStream(response)
 */
export function useSSEStream({ onContent, onError, onCompleted, onSecurityEvent, onSecretWarning }: UseSSEStreamOptions) {
  const [streaming, setStreaming] = useState(false)
  const bufferRef = useRef({ content: '', reasoning: '' })
  const rafIdRef = useRef<number | null>(null)
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null)

  const flush = useCallback(() => {
    const { content, reasoning } = bufferRef.current
    if (!content && !reasoning) {
      rafIdRef.current = null
      return
    }
    bufferRef.current = { content: '', reasoning: '' }
    onContent(content, reasoning)
    rafIdRef.current = null
  }, [onContent])

  const cancelStream = useCallback(() => {
    readerRef.current?.cancel()
    readerRef.current = null
  }, [])

  // Cancel the reader on unmount
  useEffect(() => {
    return () => {
      readerRef.current?.cancel()
      readerRef.current = null
    }
  }, [])

  const startStream = useCallback(async (response: Response) => {
    setStreaming(true)
    const reader = response.body?.getReader() as ReadableStreamDefaultReader<Uint8Array> | undefined
    const decoder = new TextDecoder()

    if (!reader) {
      setStreaming(false)
      return
    }

    readerRef.current = reader

    try {
      for await (const data of parseSSEStream(reader, decoder)) {
        if (data.type === 'content') {
          const isAssistant = data.message_type === 'assistant_message'
          const isReasoning = data.message_type === 'reasoning_message'
          if (isAssistant) {
            bufferRef.current.content += data.content || ''
          } else if (isReasoning) {
            bufferRef.current.reasoning += data.content || ''
          }
          if (!rafIdRef.current) {
            rafIdRef.current = requestAnimationFrame(flush)
          }
        } else if (data.type === 'status' && data.status === 'completed') {
          break
        } else if (data.type === 'error') {
          onError(data.error as string)
          break
        } else if (data.type === 'security_event') {
          onSecurityEvent?.(data.event as string, data.message as string)
        } else if (data.type === 'secret_warning') {
          onSecretWarning?.(data.warnings as string[])
        }
      }

      // Final flush — drain any remaining buffered content
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current)
        rafIdRef.current = null
      }
      flush()
    } finally {
      reader.cancel()
      readerRef.current = null
      setStreaming(false)
      onCompleted?.()
    }
  }, [flush, onError, onCompleted, onSecurityEvent, onSecretWarning])

  return { streaming, startStream, cancelStream }
}
