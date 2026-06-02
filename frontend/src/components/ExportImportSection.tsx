import { useState, useRef } from 'react'
import { apiFetch } from '../lib/api'
import { ERROR_MESSAGES } from '../lib/errors'
import { useRequireAuth } from '../hooks/useRequireAuth'

interface ImportResult {
  tools_imported: number
  tools_skipped: number
  skills_imported: number
  skills_skipped: number
  workflows_imported: number
  workflows_skipped: number
  workflows_needing_agent: number
  errors: string[]
}

export default function ExportImportSection() {
  useRequireAuth()
  const [exporting, setExporting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleExport = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setExporting(true)

    try {
      const res = await apiFetch('/api/export-import/export/')

      if (!res.ok) {
        setError(ERROR_MESSAGES.EXPORT)
        return
      }

      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'delta-export.json'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      // Delay revocation — the browser download is asynchronous and may not
      // have captured the blob URL before revocation completes.
      setTimeout(() => window.URL.revokeObjectURL(url), 1000)
    } catch {
      setError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setExporting(false)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setSelectedFile(file)
      setError('')
    }
  }

  const handleImport = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile) return

    setError('')
    setImportResult(null)
    setImporting(true)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const res = await apiFetch('/api/export-import/import/', {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) {
        const data = await res.json().catch(() => null)
        setError(data?.detail || `Import failed (${res.status})`)
        return
      }

      const result: ImportResult = await res.json()
      setImportResult(result)
      setSelectedFile(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    } catch {
      setError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="animate-fade-in">
      {/* Export Section */}
      <div className="card mb-8">
        <h2 className="section-header" data-symbol="↑">
          Export Data
        </h2>
        <p className="text-sm text-muted mb-4">
          Export your tools, skills, and workflows to a JSON file. Use this file to migrate to another Delta instance or as a backup.
        </p>

        {error && (
          <div className="error mb-4">{error}</div>
        )}

        <form onSubmit={handleExport}>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={exporting}
          >
            {exporting ? 'Exporting...' : 'Export All'}
          </button>
        </form>
      </div>

      {/* Import Section */}
      <div className="card mb-8">
        <h2 className="section-header" data-symbol="↓">
          Import Data
        </h2>
        <p className="text-sm text-muted mb-4">
          Import tools, skills, and workflows from a previously exported JSON file. Existing items with the same name will be renamed.
        </p>

        <form onSubmit={handleImport}>
          <div className="form-group">
            <label className="form-label" htmlFor="field-import-file">JSON File</label>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <input
                ref={fileInputRef}
                id="field-import-file"
                type="file"
                aria-label="JSON File"
                accept=".json"
                onChange={handleFileSelect}
                disabled={importing}
                className="input"
                style={{ flex: 1 }}
              />
              <button
                type="submit"
                className="btn btn-primary"
                disabled={importing || !selectedFile}
                style={{ flexShrink: 0 }}
              >
                {importing ? 'Importing...' : 'Import'}
              </button>
            </div>
            <span className="form-hint">
              Maximum file size: 10MB
            </span>
          </div>
        </form>
      </div>

      {/* Import Result */}
      {importResult && (
        <div className="card animate-fade-in">
          <h2 className="section-header" data-symbol="✓">
            Import Complete
          </h2>
          <div style={{ display: 'grid', gap: '0.5rem', fontSize: '0.8125rem' }}>
            {importResult.tools_imported > 0 && (
              <div style={{ color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--accent)', fontWeight: 500 }}>{importResult.tools_imported}</span> tools imported
                {importResult.tools_skipped > 0 && <span> ({importResult.tools_skipped} skipped)</span>}
              </div>
            )}
            {importResult.skills_imported > 0 && (
              <div style={{ color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--accent)', fontWeight: 500 }}>{importResult.skills_imported}</span> skills imported
                {importResult.skills_skipped > 0 && <span> ({importResult.skills_skipped} skipped)</span>}
              </div>
            )}
            {importResult.workflows_imported > 0 && (
              <div style={{ color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--accent)', fontWeight: 500 }}>{importResult.workflows_imported}</span> workflows imported
                {importResult.workflows_skipped > 0 && <span> ({importResult.workflows_skipped} skipped)</span>}
              </div>
            )}
            {importResult.workflows_needing_agent > 0 && (
              <div style={{ color: 'var(--warning)', fontSize: '0.75rem', marginTop: '0.25rem' }}>
                ⚠ {importResult.workflows_needing_agent} workflow{importResult.workflows_needing_agent !== 1 ? 's' : ''} need{importResult.workflows_needing_agent === 1 ? 's' : ''} an agent assignment. Visit the Workflows page to configure.
              </div>
            )}
            {importResult.errors.length > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                <div style={{ color: 'var(--danger)', fontSize: '0.75rem', marginBottom: '0.25rem' }}>
                  {importResult.errors.length} error{importResult.errors.length !== 1 ? 's' : ''}:
                </div>
                {importResult.errors.slice(0, 5).map((err, i) => (
                  <div key={i} style={{ color: 'var(--danger)', fontSize: '0.75rem' }}>
                    • {err}
                  </div>
                ))}
                {importResult.errors.length > 5 && (
                  <div style={{ color: 'var(--text-tertiary)', fontSize: '0.75rem' }}>
                    ...and {importResult.errors.length - 5} more
                  </div>
                )}
              </div>
            )}
            {importResult.tools_imported === 0 && importResult.skills_imported === 0 && importResult.workflows_imported === 0 && (
              <div style={{ color: 'var(--text-tertiary)' }}>
                No items were imported.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
