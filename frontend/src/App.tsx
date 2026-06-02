import { Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Agents from './pages/Agents'
import Settings from './pages/Settings'
import Skills from './pages/Skills'
import Tools from './pages/Tools'
import Workflows from './pages/Workflows'
import Observability from './pages/Observability'
import Chat from './pages/Chat'
import Help from './pages/Help'
import Layout from './components/Layout'
import { AuthProvider, useAuth } from './hooks/useAuth'

function AppRoutes() {
  const { isAuthenticated, isAdmin, loading } = useAuth()

  if (loading) {
    return null
  }

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" /> : <Login />} />
      <Route
        path="/*"
        element={
          isAuthenticated ? (
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/agents" element={<Agents />} />
                <Route path="/settings" element={isAdmin ? <Settings /> : <Navigate to="/" replace />} />
                <Route path="/credentials" element={<Navigate to="/settings" replace />} />
                <Route path="/skills" element={<Skills />} />
                <Route path="/tools" element={<Tools />} />
                <Route path="/workflows" element={<Workflows />} />
                <Route path="/observability" element={isAdmin ? <Observability /> : <Navigate to="/" replace />} />
                <Route path="/chat" element={<Chat />} />
                <Route path="/help" element={<Help />} />
              </Routes>
            </Layout>
          ) : (
            <Navigate to="/login" />
          )
        }
      />
    </Routes>
  )
}

function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}

export default App
