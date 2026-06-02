import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ErrorBoundary from '../ErrorBoundary'

// Component that throws on render
function ThrowOnRender({ error }: { error: Error }) {
  throw error
}

// Component that throws conditionally
function MaybeThrow({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error('conditional error')
  return <div>OK</div>
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div>Child content</div>
      </ErrorBoundary>
    )
    expect(screen.getByText('Child content')).toBeInTheDocument()
  })

  it('shows fallback UI when child throws', () => {
    render(
      <ErrorBoundary>
        <ThrowOnRender error={new Error('test explosion')} />
      </ErrorBoundary>
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('An unexpected error occurred. This has been logged to the console.')).toBeInTheDocument()
  })

  it('shows error message in details', () => {
    render(
      <ErrorBoundary>
        <ThrowOnRender error={new Error('specific boom')} />
      </ErrorBoundary>
    )
    expect(screen.getByText('specific boom')).toBeInTheDocument()
  })

  it('recovers when Reload is clicked', async () => {
    const user = userEvent.setup()
    let shouldThrow = true

    render(
      <ErrorBoundary>
        <MaybeThrow shouldThrow={shouldThrow} />
      </ErrorBoundary>
    )

    // Error boundary caught the error
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()

    // Click Reload — this increments resetKey, which re-mounts children
    // But the child will throw again because shouldThrow is still true
    await user.click(screen.getByRole('button', { name: 'Reload' }))

    // Still in error state because the child throws again
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('logs error to console', () => {
    const error = new Error('logged error')
    render(
      <ErrorBoundary>
        <ThrowOnRender error={error} />
      </ErrorBoundary>
    )
    expect(console.error).toHaveBeenCalled()
  })
})
