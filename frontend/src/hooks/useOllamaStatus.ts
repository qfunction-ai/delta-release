import { useState, useEffect, useCallback, useRef } from 'react'
import { apiFetch } from '../lib/api'

interface OllamaStatus {
  available: boolean
  models: string[]
  loading: boolean
  error: string
}

/**
 * Hook to check Ollama availability via /api/health/detailed.
 * Polls every 30s and on window focus. Returns Ollama status
 * for use in Chat and Agents pages.
 */
export function useOllamaStatus(pollMs = 30_000): OllamaStatus {
  const [status, setStatus] = useState<OllamaStatus>({
    available: true,
    models: [],
    loading: true,
    error: '',
  })
  const mounted = useRef(true)

  const check = useCallback(async () => {
    try {
      const res = await apiFetch('/api/health/detailed')
      if (res.ok) {
        const data = await res.json()
        const ollama = data.services?.ollama
        if (mounted.current) {
          setStatus({
            available: ollama?.status === 'healthy',
            models: ollama?.models ?? [],
            loading: false,
            error: ollama?.status !== 'healthy' ? (ollama?.error ?? 'Ollama is not running') : '',
          })
        }
      } else if (mounted.current) {
        setStatus({ available: false, models: [], loading: false, error: 'Failed to check Ollama status' })
      }
    } catch {
      if (mounted.current) {
        setStatus({ available: false, models: [], loading: false, error: 'Cannot reach backend' })
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    check()
    const interval = setInterval(check, pollMs)
    const onFocus = () => check()
    window.addEventListener('focus', onFocus)
    return () => {
      mounted.current = false
      clearInterval(interval)
      window.removeEventListener('focus', onFocus)
    }
  }, [check, pollMs])

  return status
}
