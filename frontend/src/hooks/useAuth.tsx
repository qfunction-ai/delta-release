import { useState, useEffect, useCallback, createContext, useContext } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'

interface AuthContextType {
  username: string
  role: string
  isAdmin: boolean
  isAuthenticated: boolean
  loading: boolean
  logout: () => void
  refreshAuth: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  username: '',
  role: 'user',
  isAdmin: false,
  isAuthenticated: false,
  loading: true,
  logout: () => {},
  refreshAuth: async () => {},
})

export function useAuth(): AuthContextType {
  return useContext(AuthContext)
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // Auth state is tracked via /api/auth/me — the actual JWT is in an
  // httpOnly cookie set by the server, so we never handle the raw token
  // in JavaScript. This prevents token theft via XSS.
  const navigate = useNavigate()
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [username, setUsername] = useState('')
  const [role, setRole] = useState('user')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Check if the httpOnly cookie is valid by hitting /api/auth/me
    apiFetch('/api/auth/me')
      .then(res => {
        if (res.ok) {
          return res.json().then(data => {
            setIsAuthenticated(true)
            setUsername(data.username || '')
            setRole(data.role || 'user')
          })
        } else {
          setIsAuthenticated(false)
        }
      })
      .catch(() => {
        // Network error — might be transient, keep current state
      })
      .finally(() => setLoading(false))
  }, [])

  const logout = useCallback(() => {
    // Call logout endpoint to clear the httpOnly cookie
    apiFetch('/api/auth/logout', { method: 'POST' })
      .catch(() => {}) // Best effort
      .finally(() => {
        setIsAuthenticated(false)
        setUsername('')
        setRole('user')
        navigate('/login')
      })
  }, [navigate])

  // Listen for centralized 401 events from apiFetch().
  // When any API call returns 401 (expired/revoked JWT), log out
  // and redirect to login. This avoids every page checking 401 manually.
  useEffect(() => {
    const handleUnauthorized = () => {
      logout()
    }
    window.addEventListener('api:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('api:unauthorized', handleUnauthorized)
  }, [logout])

  const refreshAuth = useCallback(async () => {
    try {
      const res = await apiFetch('/api/auth/me')
      if (res.ok) {
        const data = await res.json()
        setIsAuthenticated(true)
        setUsername(data.username || '')
        setRole(data.role || 'user')
      } else {
        setIsAuthenticated(false)
      }
    } catch {
      // Network error — keep current state
    }
  }, [])

  return (
    <AuthContext.Provider value={{
      username,
      role,
      isAdmin: role === 'admin',
      isAuthenticated,
      loading,
      logout,
      refreshAuth,
    }}>
      {children}
    </AuthContext.Provider>
  )
}
