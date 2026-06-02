import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import AlertBox from '../AlertBox'

describe('AlertBox', () => {
  it('renders with role="alert"', () => {
    render(<AlertBox variant="warning">Watch out</AlertBox>)
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('renders children text', () => {
    render(<AlertBox variant="info">Some info message</AlertBox>)
    expect(screen.getByRole('alert')).toHaveTextContent('Some info message')
  })

  it('applies warning variant styles', () => {
    const { container } = render(<AlertBox variant="warning">Warning</AlertBox>)
    const el = container.firstChild as HTMLElement
    expect(el.style.background).toBe('var(--warning-subtle)')
    expect(el.style.border).toBe('1px solid var(--warning-border)')
  })

  it('applies danger variant styles', () => {
    const { container } = render(<AlertBox variant="danger">Danger</AlertBox>)
    const el = container.firstChild as HTMLElement
    expect(el.style.background).toBe('var(--danger-subtle)')
    expect(el.style.border).toBe('1px solid var(--danger-border)')
  })

  it('applies info variant styles', () => {
    const { container } = render(<AlertBox variant="info">Info</AlertBox>)
    const el = container.firstChild as HTMLElement
    expect(el.style.background).toBe('var(--info-subtle)')
    expect(el.style.border).toBe('1px solid var(--info-border)')
  })

  it('renders React nodes as children', () => {
    render(
      <AlertBox variant="info">
        <strong>Bold</strong> text
      </AlertBox>
    )
    const alert = screen.getByRole('alert')
    expect(alert).toContainHTML('<strong>Bold</strong> text')
  })
})
