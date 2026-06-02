import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ToggleSwitch from '../ToggleSwitch'

describe('ToggleSwitch', () => {
  it('renders in checked state (knob positioned right)', () => {
    const { container } = render(<ToggleSwitch checked={true} onChange={vi.fn()} />)
    const button = container.querySelector('button')!
    expect(button).toHaveStyle({ background: 'var(--accent-subtle)' })
    const knob = button.querySelector('span')!
    expect(knob).toHaveStyle({ left: '19px' })
  })

  it('renders in unchecked state (knob positioned left)', () => {
    const { container } = render(<ToggleSwitch checked={false} onChange={vi.fn()} />)
    const button = container.querySelector('button')!
    expect(button).toHaveStyle({ background: 'var(--bg-input)' })
    const knob = button.querySelector('span')!
    expect(knob).toHaveStyle({ left: '1px' })
  })

  it('calls onChange when clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const { container } = render(<ToggleSwitch checked={false} onChange={onChange} />)
    const button = container.querySelector('button')!
    await user.click(button)
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('shows disabled state with wait cursor', () => {
    const { container } = render(<ToggleSwitch checked={false} onChange={vi.fn()} disabled={true} />)
    const button = container.querySelector('button')!
    expect(button).toBeDisabled()
    expect(button).toHaveStyle({ cursor: 'wait' })
  })

  it('does not call onChange when disabled (button is disabled)', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const { container } = render(<ToggleSwitch checked={false} onChange={onChange} disabled={true} />)
    const button = container.querySelector('button')!
    await user.click(button)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('has role="switch" and aria-checked', () => {
    const { container } = render(<ToggleSwitch checked={true} onChange={vi.fn()} />)
    const button = container.querySelector('button')!
    expect(button).toHaveAttribute('role', 'switch')
    expect(button).toHaveAttribute('aria-checked', 'true')
  })

  it('updates aria-checked when unchecked', () => {
    const { container } = render(<ToggleSwitch checked={false} onChange={vi.fn()} />)
    const button = container.querySelector('button')!
    expect(button).toHaveAttribute('aria-checked', 'false')
  })

  it('uses custom aria-label when provided', () => {
    const { container } = render(<ToggleSwitch checked={false} onChange={vi.fn()} aria-label="Dark mode" />)
    const button = container.querySelector('button')!
    expect(button).toHaveAttribute('aria-label', 'Dark mode')
  })

  it('falls back to default aria-label', () => {
    const { container } = render(<ToggleSwitch checked={false} onChange={vi.fn()} />)
    const button = container.querySelector('button')!
    expect(button).toHaveAttribute('aria-label', 'Toggle')
  })
})
