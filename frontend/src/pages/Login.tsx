import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, extractApiError } from '../lib/api'
import { ERROR_MESSAGES } from '../lib/errors'
import { validateRegistration } from './login.utils'
import { useAuth } from '../hooks/useAuth'
import { useApiFetch } from '../hooks/useApiFetch'
import { CornerDecorations } from '../components/CornerDecorations'

interface SetupStatus {
  needs_setup: boolean
  requires_setup_token?: boolean
}

export default function Login() {
  const navigate = useNavigate()
  const { refreshAuth } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Registration state
  const { data: setupData, loading: checkingSetup } = useApiFetch<SetupStatus>('/api/auth/setup-status', {
    errorMessage: 'Failed to check setup status',
  })
  const needsSetup = setupData?.needs_setup ?? false
  const requiresSetupToken = setupData?.requires_setup_token ?? false
  const [setupToken, setSetupToken] = useState('')

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const response = await apiFetch('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })

      if (!response.ok) {
        setError(await extractApiError(response, 'An error occurred'))
        return
      }

      // Server sets httpOnly cookie — refresh auth state then navigate
      await refreshAuth()
      navigate('/')
    } catch {
      setError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()

    const validationError = validateRegistration(username, password, confirmPassword)
    if (validationError) {
      setError(validationError)
      return
    }

    setLoading(true)

    try {
      const body: Record<string, string> = { username, password }
      if (setupToken) body.setup_token = setupToken

      const response = await apiFetch('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify(body),
      })

      if (!response.ok) {
        setError(await extractApiError(response, 'Registration failed'))
        return
      }

      // Server sets httpOnly cookie — refresh auth state then navigate
      await refreshAuth()
      navigate('/')
    } catch {
      setError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setLoading(false)
    }
  }

  if (checkingSetup) {
    return null
  }

  // Shared logo header
  const logoHeader = (
    <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
      <div className="font-mono" style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 56,
        height: 56,
        borderRadius: 'var(--radius-md)',
        background: 'var(--accent-subtle)',
        border: '2px solid var(--accent)',
        fontSize: '1.75rem',
        fontWeight: 700,
        color: 'var(--accent)',
        marginBottom: '1rem',
        position: 'relative',
      }}>
        Δ
        <div style={{
          position: 'absolute',
          inset: 4,
          border: '1px solid rgba(253, 176, 34, 0.3)',
          borderRadius: 0,
        }} />
      </div>
      <h1 style={{ fontSize: '1.75rem', letterSpacing: '-0.02em' }}>
        <span style={{ color: 'var(--accent)' }}>Δ</span> delta
      </h1>
      <div className="font-mono" style={{
        fontSize: '0.6875rem',
        color: 'var(--text-tertiary)',
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        marginTop: '0.375rem',
      }}>
        QFunction
      </div>
      <div className="font-mono" style={{
        fontSize: '0.625rem',
        color: 'var(--text-tertiary)',
        letterSpacing: '0.05em',
        marginTop: '0.5rem',
        opacity: 0.6,
      }}>
        f : X → Y &nbsp;|&nbsp; δ(x,y) → 0
      </div>
    </div>
  )

  // Registration form
  if (needsSetup) {
    return (
      <div className="login-page">
        <CornerDecorations />

        <div className="login-container">
          <div className="card" style={{ borderTop: '2px solid var(--accent)', padding: '2.5rem 2rem' }}>
            {logoHeader}
            <form onSubmit={handleRegister}>
              <div className="form-group">
                <label className="form-label" htmlFor="field-login-reg-username">Username</label>
                <input
                  id="field-login-reg-username"
                  type="text"
                  className="input"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  minLength={3}
                  maxLength={50}
                  pattern="[a-zA-Z0-9_]+"
                  title="Letters, numbers, and underscores only"
                  aria-label="Username"
                />
                <p className="form-hint">3-50 characters, letters/numbers/underscores</p>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="field-login-reg-password">Password</label>
                <input
                  id="field-login-reg-password"
                  type="password"
                  className="input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  aria-label="Password"
                />
                <p className="form-hint">Minimum 8 characters</p>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="field-login-reg-confirm-password">Confirm Password</label>
                <input
                  id="field-login-reg-confirm-password"
                  type="password"
                  className="input"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  aria-label="Confirm Password"
                />
              </div>
              {requiresSetupToken && (
                <div className="form-group">
                  <label className="form-label" htmlFor="field-login-setup-token">Setup Token</label>
                  <input
                    id="field-login-setup-token"
                    type="password"
                    className="input"
                    value={setupToken}
                    onChange={(e) => setSetupToken(e.target.value)}
                    required
                    aria-label="Setup Token"
                  />
                  <p className="form-hint">Required — provided by your administrator</p>
                </div>
              )}
              {error && <div className="error">{error}</div>}
              <button type="submit" className="btn btn-primary w-full" style={{ marginTop: '0.5rem' }} disabled={loading}>
                {loading ? 'Creating...' : 'Create Account'}
              </button>
            </form>
          </div>
        </div>
      </div>
    )
  }

  // Login form
  return (
    <div className="login-page">
      <CornerDecorations />

      <div className="login-container">
        <div className="card" style={{ borderTop: '2px solid var(--accent)', padding: '2.5rem 2rem' }}>
          {logoHeader}
          <form onSubmit={handleLogin}>
            <div className="form-group">
              <label className="form-label" htmlFor="field-login-username">Username</label>
              <input id="field-login-username" type="text" className="input" value={username} onChange={(e) => setUsername(e.target.value)} required aria-label="Username" />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="field-login-password">Password</label>
              <input id="field-login-password" type="password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} required aria-label="Password" />
            </div>
            {error && <div className="error">{error}</div>}
            <button type="submit" className="btn btn-primary w-full" style={{ marginTop: '0.5rem' }} disabled={loading}>
              {loading ? 'Please wait...' : 'Login'}
            </button>
          </form>
        </div>
      </div>

      {/* Version stamp */}
      <div className="font-mono" style={{ position: 'fixed', bottom: '1rem', right: '1.5rem', fontSize: '0.625rem', color: 'var(--text-tertiary)', opacity: 0.4, letterSpacing: '0.05em', zIndex: 1 }}>v0.1.0 // δ-build</div>
    </div>
  )
}
