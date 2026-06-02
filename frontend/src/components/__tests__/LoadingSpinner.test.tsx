import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LoadingSpinner } from '../LoadingSpinner'

describe('LoadingSpinner', () => {
  it('renders loading text', () => {
    render(<LoadingSpinner />)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('applies the loading-spinner CSS class', () => {
    const { container } = render(<LoadingSpinner />)
    expect(container.firstChild).toHaveClass('loading-spinner')
  })
})
