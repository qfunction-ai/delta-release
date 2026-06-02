import { useCallback } from 'react'
import { apiFetch, extractApiError } from '../lib/api'

interface ConfirmOptions {
  title: string
  message: string
  confirmLabel?: string
  danger?: boolean
  action: () => Promise<void>
}

/**
 * Returns a delete-with-confirmation handler for entity pages.
 *
 * Usage:
 *   const { confirm, dialog } = useConfirmDialog()
 *   const handleDelete = useEntityDelete(
 *     '/api/tools',
 *     (id) => setTools(prev => prev.filter(t => t.id !== id)),
 *     confirm,
 *     'tool',
 *     (id) => { if (viewingTool?.id === id) setViewingTool(null) },
 *     (msg) => setError(msg),
 *   )
 */
export function useEntityDelete(
  basePath: string,
  onDeleted: (id: string) => void,
  confirm: (opts: ConfirmOptions) => void,
  entityLabel: string = 'item',
  onAfterDelete?: (id: string) => void,
  onError?: (message: string) => void,
) {
  return useCallback(
    (id: string, name: string) => {
      confirm({
        title: `Delete ${entityLabel.charAt(0).toUpperCase() + entityLabel.slice(1)}`,
        message: `Delete ${entityLabel} "${name}"? This cannot be undone.`,
        danger: true,
        action: async () => {
          try {
            const res = await apiFetch(`${basePath}/${id}`, { method: 'DELETE' })
            if (!res.ok) {
              const err = await extractApiError(res, `Failed to delete ${entityLabel}`)
              throw new Error(err)
            }
            onDeleted(id)
            onAfterDelete?.(id)
          } catch (err) {
            const message = err instanceof Error ? err.message : `Failed to delete ${entityLabel}`
            console.error(`Failed to delete ${entityLabel}:`, err)
            onError?.(message)
          }
        },
      })
    },
    [confirm, basePath, onDeleted, onAfterDelete, entityLabel, onError],
  )
}
