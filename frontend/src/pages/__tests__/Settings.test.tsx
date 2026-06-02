import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Settings from '../Settings'

// Mock child components — they have their own API calls and we don't want to mock those
vi.mock('../../components/PackagesSection', () => ({
  default: () => <div data-testid="packages-section">Packages Section</div>,
}))
vi.mock('../../components/CredentialsSection', () => ({
  default: () => <div data-testid="credentials-section">Credentials Section</div>,
}))
vi.mock('../../components/LogsSection', () => ({
  default: () => <div data-testid="logs-section">Logs Section</div>,
}))
vi.mock('../../components/AgentSection', () => ({
  default: () => <div data-testid="agent-section">Agent Section</div>,
}))

function renderSettings() {
  return render(
    <MemoryRouter>
      <Settings />
    </MemoryRouter>
  )
}

describe('Settings page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders settings page with tabs', () => {
    renderSettings()

    expect(screen.getByText('SETTINGS')).toBeInTheDocument()
    expect(screen.getByText('Packages')).toBeInTheDocument()
    expect(screen.getByText('Credentials')).toBeInTheDocument()
    expect(screen.getByText('Agent')).toBeInTheDocument()
    expect(screen.getByText('Logs')).toBeInTheDocument()
  })

  it('shows packages section by default', () => {
    renderSettings()

    expect(screen.getByTestId('packages-section')).toBeInTheDocument()
  })

  it('switches to credentials section on tab click', async () => {
    const user = userEvent.setup()
    renderSettings()

    await user.click(screen.getByText('Credentials'))

    expect(screen.getByTestId('credentials-section')).toBeInTheDocument()
    expect(screen.queryByTestId('packages-section')).not.toBeInTheDocument()
  })

  it('switches to agent section on tab click', async () => {
    const user = userEvent.setup()
    renderSettings()

    await user.click(screen.getByText('Agent'))

    expect(screen.getByTestId('agent-section')).toBeInTheDocument()
  })

  it('switches to logs section on tab click', async () => {
    const user = userEvent.setup()
    renderSettings()

    await user.click(screen.getByText('Logs'))

    expect(screen.getByTestId('logs-section')).toBeInTheDocument()
  })

  it('switches back to packages from another section', async () => {
    const user = userEvent.setup()
    renderSettings()

    await user.click(screen.getByText('Credentials'))
    expect(screen.getByTestId('credentials-section')).toBeInTheDocument()

    await user.click(screen.getByText('Packages'))
    expect(screen.getByTestId('packages-section')).toBeInTheDocument()
  })
})
