import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Help from '../Help'

// jsdom doesn't implement scrollIntoView or IntersectionObserver
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
  class MockIntersectionObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  // @ts-expect-error partial mock
  window.IntersectionObserver = MockIntersectionObserver
})

// Mock useNavigate and useLocation
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useLocation: () => ({ hash: '' }),
  }
})

function renderHelp() {
  return render(
    <MemoryRouter>
      <Help />
    </MemoryRouter>
  )
}

describe('Help', () => {
  it('renders the page title', () => {
    renderHelp()
    expect(screen.getByText('Help')).toBeInTheDocument()
  })

  it('renders the page subtitle', () => {
    renderHelp()
    expect(screen.getByText(/help.*guidance/i)).toBeInTheDocument()
  })

  it('renders all section titles in the TOC', () => {
    renderHelp()
    // Section titles appear in both TOC and content, so use getAllByText
    expect(screen.getAllByText('Getting Started').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Dashboard').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Agents').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Chat').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Skills').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Tools').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Workflows').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Observability').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Settings').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('FAQ').length).toBeGreaterThanOrEqual(1)
  })

  it('renders section content headings', () => {
    renderHelp()
    // Section headings in the content area (with icon prefix)
    expect(screen.getAllByText(/Getting Started/).length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText(/Agents/).length).toBeGreaterThanOrEqual(2)
  })

  it('highlights the initial active section in TOC', () => {
    const { container } = renderHelp()
    const activeTocBtn = container.querySelector('.help-toc-active')
    expect(activeTocBtn).not.toBeNull()
    expect(activeTocBtn?.textContent).toContain('Getting Started')
  })

  it('navigates to section on TOC click', async () => {
    const user = userEvent.setup()
    renderHelp()

    // Click "Tools" in the TOC
    const tocButtons = screen.getAllByText('Tools').map(el => el.closest('button')).filter(Boolean)
    if (tocButtons.length > 0) {
      await user.click(tocButtons[0]!)
      expect(mockNavigate).toHaveBeenCalledWith('/help#tools', { replace: true })
    }
  })

  it('renders code blocks in skill section', () => {
    const { container } = renderHelp()
    const preElements = container.querySelectorAll('pre')
    expect(preElements.length).toBeGreaterThan(0)
  })
})
