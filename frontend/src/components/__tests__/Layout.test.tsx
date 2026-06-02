import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Layout from '../Layout'

// Mutable mock state so individual tests can override
const mockAuth = {
  username: 'testuser',
  isAdmin: false,
  logout: vi.fn(),
}

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => mockAuth,
}))
vi.mock('../../lib/api', () => ({ apiFetch: vi.fn() }))

function renderWithRouter(ui: React.ReactElement, { initialEntries = ['/'] } = {}) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
  )
}

describe('Layout', () => {
  beforeEach(() => {
    mockAuth.username = 'testuser'
    mockAuth.isAdmin = false
    mockAuth.logout = vi.fn()
  })

  it('renders all non-admin navigation items', () => {
    renderWithRouter(<Layout><div>Test Content</div></Layout>)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Agents')).toBeInTheDocument()
    expect(screen.getByText('Chat')).toBeInTheDocument()
    expect(screen.getByText('Skills')).toBeInTheDocument()
    expect(screen.getByText('Tools')).toBeInTheDocument()
    expect(screen.getByText('Workflows')).toBeInTheDocument()
  })

  it('hides Settings nav item when user is not admin', () => {
    renderWithRouter(<Layout><div>Test Content</div></Layout>)
    expect(screen.queryByText('Settings')).not.toBeInTheDocument()
  })

  it('shows Settings nav item when user is admin', () => {
    mockAuth.isAdmin = true
    mockAuth.username = 'admin'
    renderWithRouter(<Layout><div>Test Content</div></Layout>)
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('highlights active nav item based on current path', () => {
    renderWithRouter(<Layout><div>Test Content</div></Layout>, { initialEntries: ['/agents'] })
    const agentsButton = screen.getByText('Agents').closest('button')!
    expect(agentsButton).toHaveClass('active')
    const dashboardButton = screen.getByText('Dashboard').closest('button')!
    expect(dashboardButton).not.toHaveClass('active')
  })

  it('displays username initial in avatar', () => {
    renderWithRouter(<Layout><div>Test Content</div></Layout>)
    expect(screen.getByText('T')).toBeInTheDocument()
  })

  it('renders children content', () => {
    renderWithRouter(<Layout><div>Test Content</div></Layout>)
    expect(screen.getByText('Test Content')).toBeInTheDocument()
  })
})
