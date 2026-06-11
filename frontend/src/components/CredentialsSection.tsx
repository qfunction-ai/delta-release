import { useState, useEffect, useCallback } from 'react'
import { apiFetch, extractApiError } from '../lib/api'
import { ERROR_MESSAGES } from '../lib/errors'
import { useAuth } from '../hooks/useAuth'
import { useConfirmDialog } from '../hooks/useConfirmDialog'
import { useEntityDelete } from '../hooks/useEntityDelete'
import { LoadingSpinner } from './LoadingSpinner'
import { EncryptedField } from './EncryptedField'
import { Credential, CredentialType } from '../lib/types'

const CREDENTIAL_TYPES: CredentialType[] = [
  { id: 'api_key_only', display_name: 'API Key', fields: ['primary_key'] },
  { id: 'api_key_pair', display_name: 'API Key Pair', fields: ['primary_key', 'secondary_key'] },
  { id: 'basic_auth', display_name: 'Username / Password', fields: ['primary_key', 'secondary_key'] },
]

const TYPE_DISPLAY: Record<string, string> = {
  api_key_only: 'API Key',
  api_key_pair: 'API Key Pair',
  basic_auth: 'Username / Password',
  splunk: 'Splunk',
  crowdstrike: 'CrowdStrike',
  sentinelone: 'SentinelOne',
  elastic: 'Elastic Security',
  custom: 'Custom API',
}

export default function CredentialsSection() {
  const { isAuthenticated } = useAuth()
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [credLoading, setCredLoading] = useState(true)
  const [selectedType, setSelectedType] = useState('api_key_only')
  const [key, setKey] = useState('')
  const [name, setName] = useState('')
  const [primaryValue, setPrimaryValue] = useState('')
  const [secondaryValue, setSecondaryValue] = useState('')
  const [creating, setCreating] = useState(false)
  const [credError, setCredError] = useState('')
  const [credFetchError, setCredFetchError] = useState('')
  const { confirm, dialog } = useConfirmDialog()

  const handleDeleteCredential = useEntityDelete(
    '/api/credentials',
    (id) => setCredentials(prev => prev.filter(c => c.id !== id)),
    confirm,
    'credential',
    undefined,
    (msg) => setCredError(msg),
  )

  const fetchCredentials = useCallback(async () => {
    if (!isAuthenticated) return
    setCredLoading(true)
    try {
      const res = await apiFetch('/api/credentials/')
      if (res.ok) {
        setCredentials(await res.json())
      } else {
        setCredFetchError(ERROR_MESSAGES.LOAD_CREDENTIALS)
      }
    } catch {
      setCredFetchError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setCredLoading(false)
    }
  }, [isAuthenticated])

  useEffect(() => {
    fetchCredentials()
  }, [fetchCredentials])

  const resetCredForm = () => {
    setKey('')
    setName('')
    setPrimaryValue('')
    setSecondaryValue('')
    setCredError('')
  }

  const handleCreateCredential = async (e: React.FormEvent) => {
    e.preventDefault()
    setCredError('')
    setCreating(true)

    try {
      const response = await apiFetch('/api/credentials/', {
        method: 'POST',
        body: JSON.stringify({
          key,
          name,
          provider: selectedType,
          url: null,
          primary_key: primaryValue,
          secondary_key: selectedType !== 'api_key_only' ? secondaryValue : null,
        }),
      })

      if (!response.ok) {
        setCredError(await extractApiError(response, 'Failed to create credential'))
        return
      }

      const newCredential = await response.json()
      setCredentials(prev => [...prev, newCredential])
      resetCredForm()
    } catch {
      setCredError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setCreating(false)
    }
  }

  const isCredFormValid = () => {
    if (!key || !name) return false
    if (!primaryValue) return false
    if (selectedType !== 'api_key_only' && !secondaryValue) return false
    return true
  }

  const primaryLabel = selectedType === 'basic_auth' ? 'Username' : 'Primary Key'
  const secondaryLabel = selectedType === 'basic_auth' ? 'Password' : 'Secondary Key'
  const primaryPlaceholder = selectedType === 'basic_auth' ? 'admin' : 'Enter API key or token'
  const secondaryPlaceholder = selectedType === 'basic_auth' ? 'Enter password' : 'Enter secret key'

  return (
    <div className="animate-fade-in">
      {credFetchError && <div className="error mb-6">{credFetchError}</div>}

      {/* Create Credential Form */}
      <div className="card mb-8">
        <h2 className="section-header" data-symbol="+">
          Add Credential
        </h2>

        <form onSubmit={handleCreateCredential}>
          {/* Credential Type Selector */}
          <div className="form-group">
            <label className="form-label" htmlFor="field-credentials-type">Type</label>
            <div className="pill-tabs gap-4">
              {CREDENTIAL_TYPES.map((ct) => (
                <button
                  key={ct.id}
                  type="button"
                  className={`pill-tab ${selectedType === ct.id ? 'pill-tab-active' : ''}`}
                  onClick={() => { setSelectedType(ct.id); setCredError('') }}
                >
                  {ct.display_name}
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="field-credentials-key">Key</label>
            <input
              id="field-credentials-key"
              type="text"
              className="input font-mono"
              aria-label="Key"
              value={key}
              onChange={(e) => setKey(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ''))}
              placeholder="TOOL_KEY"
              required
            />
            <span className="form-hint">Unique identifier used by tools to reference this credential</span>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="field-credentials-name">Name</label>
            <input
              id="field-credentials-name"
              type="text"
              className="input"
              aria-label="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="credential-name"
              required
            />
          </div>

          {/* Primary key field (always shown) */}
          <div className="form-group">
            <label className="form-label" htmlFor="field-credentials-primary">{primaryLabel}</label>
            <input
              id="field-credentials-primary"
              type="password"
              className="input font-mono"
              aria-label={primaryLabel}
              value={primaryValue}
              onChange={(e) => setPrimaryValue(e.target.value)}
              placeholder={primaryPlaceholder}
              required
            />
          </div>

          {/* Secondary key field (shown for pair types) */}
          {selectedType !== 'api_key_only' && (
            <div className="form-group">
              <label className="form-label" htmlFor="field-credentials-secondary">{secondaryLabel}</label>
              <input
                id="field-credentials-secondary"
                type="password"
                className="input font-mono"
                aria-label={secondaryLabel}
                value={secondaryValue}
                onChange={(e) => setSecondaryValue(e.target.value)}
                placeholder={secondaryPlaceholder}
                required
              />
            </div>
          )}

          {credError && <div className="error mb-4">{credError}</div>}

          <button
            type="submit"
            className="btn btn-primary mt-4"
            disabled={creating || !isCredFormValid()}
          >
            {creating ? 'Encrypting & Saving...' : 'Save Credential'}
          </button>
        </form>
      </div>

      {/* Credentials List */}
      <h2 className="section-header mb-6" data-symbol="🔒">
        Saved Credentials
      </h2>

      {credLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
          <LoadingSpinner />
        </div>
      ) : credentials.length === 0 ? (
        <div className="card">
          <p className="text-sm text-muted" style={{ fontFamily: 'var(--font-sans)' }}>
            No credentials stored. Add one above to get started.
          </p>
        </div>
      ) : (
        <div className="gap-4" style={{ display: 'grid' }}>
          {credentials.map((credential) => {
            const typeLabel = TYPE_DISPLAY[credential.provider] || credential.provider
            const isCredType = credential.provider in TYPE_DISPLAY && ['api_key_only', 'api_key_pair', 'basic_auth'].includes(credential.provider)

            return (
              <div key={credential.id} className="card animate-fade-in">
                <div className="flex items-center justify-between">
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <h3
                      className="mb-4"
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '1rem',
                        fontWeight: 600,
                        color: 'var(--text-primary)',
                      }}
                    >
                      {credential.name}
                    </h3>

                    <div className="mb-4">
                      <span
                        className="badge badge-accent font-mono"
                        style={{ fontSize: '0.8rem' }}
                      >
                        {credential.key}
                      </span>
                    </div>

                    <div className="mb-4">
                      <span className="text-xs text-tertiary" style={{ fontFamily: 'var(--font-sans)' }}>
                        Type
                      </span>
                      <div className="flex items-center gap-4" style={{ marginTop: '0.25rem' }}>
                        <span className="badge badge-info">{typeLabel}</span>
                      </div>
                    </div>

                    {credential.url && (
                      <div className="mb-4">
                        <span className="text-xs text-tertiary" style={{ fontFamily: 'var(--font-sans)' }}>
                          URL
                        </span>
                        <p
                          className="text-sm font-mono text-accent"
                          style={{ marginTop: '0.25rem', wordBreak: 'break-all' }}
                        >
                          {credential.url}
                        </p>
                      </div>
                    )}

                    {/* Encrypted fields display */}
                    {isCredType && credential.provider === 'basic_auth' && (
                      <div className="gap-4" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
                        <EncryptedField label="Username" />
                        <EncryptedField label="Password" />
                      </div>
                    )}

                    {isCredType && credential.provider === 'api_key_only' && (
                      <div>
                        <EncryptedField label="Primary Key" />
                      </div>
                    )}

                    {isCredType && credential.provider === 'api_key_pair' && (
                      <div className="gap-4" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
                        <EncryptedField label="Primary Key" />
                        <EncryptedField label="Secondary Key" />
                      </div>
                    )}

                    {!isCredType && (
                      <div className="gap-4" style={{ display: 'grid', gridTemplateColumns: credential.has_secondary_key ? '1fr 1fr' : '1fr' }}>
                        <EncryptedField label="Primary Key" />
                        {credential.has_secondary_key && (
                          <EncryptedField label="Secondary Key" />
                        )}
                      </div>
                    )}

                    <p
                      className="text-xs text-tertiary mt-4"
                      style={{ fontFamily: 'var(--font-sans)' }}
                    >
                      Updated {new Date(credential.updated_at).toLocaleString()}
                    </p>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.5rem', marginLeft: '1.5rem', flexShrink: 0 }}>
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={() => handleDeleteCredential(credential.id, credential.name)}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {dialog}
    </div>
  )
}
