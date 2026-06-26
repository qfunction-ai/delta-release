import { useState, useEffect } from 'react'
import { apiFetch, extractApiError } from '../lib/api'
import { ERROR_MESSAGES } from '../lib/errors'
import { useAuth } from '../hooks/useAuth'
import { useNavigate } from 'react-router-dom'
import { useConfirmDialog } from '../hooks/useConfirmDialog'
import { LoadingSpinner } from './LoadingSpinner'

interface Package {
  name: string
  version: string
}

export default function PackagesSection() {
  const navigate = useNavigate()
  const { isAuthenticated } = useAuth()
  const [packages, setPackages] = useState<Package[]>([])
  const [packageInput, setPackageInput] = useState('')
  const [installing, setInstalling] = useState(false)
  const [packageError, setPackageError] = useState('')
  const { confirm, dialog } = useConfirmDialog()
  const [packageLoading, setPackageLoading] = useState(true)

  useEffect(() => {
    if (!isAuthenticated) { navigate('/login'); return }
    fetchPackages()
  }, [navigate, isAuthenticated])

  const fetchPackages = async () => {
    try {
      const res = await apiFetch('/api/tools/packages')
      if (res.ok) {
        setPackages(await res.json())
        setPackageError('')
      } else if (res.status === 503) {
        setPackageError('Package manager service is not available')
        setPackages([])
      } else {
        setPackageError(ERROR_MESSAGES.LOAD_PACKAGES)
      }
    } catch {
      setPackageError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setPackageLoading(false)
    }
  }

  const handleInstall = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!packageInput.trim()) return
    setPackageError('')
    setInstalling(true)

    try {
      const res = await apiFetch('/api/tools/packages/install', {
        method: 'POST',
        body: JSON.stringify({ packages: packageInput.split(',').map(p => p.trim()).filter(Boolean) }),
      })

      if (!res.ok) {
        setPackageError(await extractApiError(res, 'Failed to install packages'))
        return
      }

      setPackageInput('')
      await fetchPackages()
    } catch {
      setPackageError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setInstalling(false)
    }
  }

  const handleUninstall = (pkgName: string) => {
    confirm({
      title: 'Uninstall Package',
      message: `Uninstall "${pkgName}"? This cannot be undone.`,
      confirmLabel: 'Uninstall',
      action: async () => {
        try {
          const res = await apiFetch(`/api/tools/packages/${pkgName}`, {
            method: 'DELETE',
          })
          if (!res.ok) {
            setPackageError(await extractApiError(res, 'Failed to uninstall package'))
            return
          }
          await fetchPackages()
        } catch {
          setPackageError(ERROR_MESSAGES.CONNECTION)
        }
      },
    })
  }

  return (
    <div className="animate-fade-in">
      {/* Install Form */}
      <div className="card mb-8">
        <h2 className="section-header" data-symbol="+">
          Install Package
        </h2>

        <form onSubmit={handleInstall}>
          <div className="form-group">
            <label className="form-label" htmlFor="field-packages-name">Package(s)</label>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <input
                id="field-packages-name"
                type="text"
                className="input font-mono"
                aria-label="Package(s)"
                value={packageInput}
                onChange={(e) => { setPackageInput(e.target.value); setPackageError('') }}
                placeholder="requests, paramiko==2.12.0"
                style={{ flex: 1 }}
              />
              <button
                type="submit"
                className="btn btn-primary"
                disabled={installing || !packageInput.trim()}
                style={{ flexShrink: 0 }}
              >
                {installing ? 'Installing...' : 'Install'}
              </button>
            </div>
            <span className="form-hint">
              Comma-separated package names with optional version specifiers
            </span>
          </div>

          {packageError && <div className="error">{packageError}</div>}
        </form>
      </div>

      {/* Package List */}
      <h2 className="section-header mb-6" data-symbol="pkg">
        Installed Packages
      </h2>

      {packageLoading ? (
        <div className="loading-center">
          <LoadingSpinner />
        </div>
      ) : packageError && packages.length === 0 ? (
        <div className="card">
          <p className="text-sm text-danger">
            {packageError}
          </p>
        </div>
      ) : packages.length === 0 ? (
        <div className="card">
          <p className="text-sm text-muted font-sans">
            No packages installed. Install one above to get started.
          </p>
        </div>
      ) : (
        <div className="gap-4" style={{ display: 'grid' }}>
          {packages.map((pkg) => (
            <div key={pkg.name} className="card animate-fade-in">
              <div className="flex items-center justify-between">
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="flex items-center gap-3">
                    <span
                      className="font-mono"
                      style={{
                        fontSize: '0.9375rem',
                        fontWeight: 600,
                        color: 'var(--text-primary)',
                      }}
                    >
                      {pkg.name}
                    </span>
                    <span className="badge badge-accent font-mono" style={{ fontSize: '0.75rem' }}>
                      v{pkg.version}
                    </span>
                  </div>
                </div>
                <button
                  className="btn btn-danger btn-sm item-actions-col"
                  onClick={() => handleUninstall(pkg.name)}
                >
                  Uninstall
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {dialog}
    </div>
  )
}
