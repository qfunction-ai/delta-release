import { useState, useCallback } from 'react'
import { apiFetch } from '../lib/api'
import { ERROR_MESSAGES } from '../lib/errors'

interface UseGithubImportOptions {
  endpoint: string
  errorLabel: string
  onSuccess: (data: unknown) => void
  onError: (message: string) => void
}

/**
 * Hook for GitHub URL import flow.
 *
 * Encapsulates the githubUrl input state, fetching state, and the
 * submit handler that POSTs to the given endpoint. The caller handles
 * the response via `onSuccess` since Tools and Skills have different
 * response shapes. Errors are reported via `onError`.
 *
 * Usage:
 *   const { githubUrl, setGithubUrl, fetchingGithub, handleGithub } = useGithubImport({
 *     endpoint: '/api/tools/github',
 *     errorLabel: 'tool',
 *     onSuccess: (data) => setTools(prev => [...prev, data]),
 *     onError: (msg) => setError(msg),
 *   })
 */
export function useGithubImport({ endpoint, errorLabel, onSuccess, onError }: UseGithubImportOptions) {
  const [githubUrl, setGithubUrl] = useState('')
  const [fetchingGithub, setFetchingGithub] = useState(false)

  const handleGithub = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!githubUrl.trim()) return

    setFetchingGithub(true)
    try {
      const response = await apiFetch(endpoint, {
        method: 'POST',
        body: JSON.stringify({ github_url: githubUrl.trim() }),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => null)
        onError(data?.detail || `Failed to fetch ${errorLabel} from GitHub (${response.status})`)
        return
      }

      const data = await response.json()
      onSuccess(data)
      setGithubUrl('')
    } catch {
      onError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setFetchingGithub(false)
    }
  }, [githubUrl, endpoint, errorLabel, onSuccess, onError])

  return { githubUrl, setGithubUrl, fetchingGithub, handleGithub }
}
