import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ConfirmDialog from '../ConfirmDialog'

describe('ConfirmDialog', () => {
  it('renders nothing when open is false', () => {
    const { container } = render(
      <ConfirmDialog
        open={false}
        title="Delete?"
        message="Are you sure?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders title and message when open', () => {
    render(
      <ConfirmDialog
        open={true}
        title="Delete Item"
        message="This cannot be undone."
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getByText('Delete Item')).toBeInTheDocument()
    expect(screen.getByText('This cannot be undone.')).toBeInTheDocument()
  })

  it('calls onCancel on Escape key', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        open={true}
        title="Delete?"
        message="Sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    )
    await user.keyboard('{Escape}')
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('calls onCancel on overlay click', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        open={true}
        title="Delete?"
        message="Sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    )
    // The overlay is the outermost div
    const overlay = screen.getByText('Delete?').parentElement!.parentElement!
    await user.click(overlay)
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('calls onConfirm on confirm button click', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        open={true}
        title="Delete?"
        message="Sure?"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    )
    await user.click(screen.getByText('Delete'))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('does not call onCancel on card body click', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        open={true}
        title="Delete?"
        message="Sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    )
    await user.click(screen.getByText('Delete?'))
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('renders custom confirm label', () => {
    render(
      <ConfirmDialog
        open={true}
        title="Logout?"
        message="Are you sure?"
        confirmLabel="Logout Everywhere"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getByText('Logout Everywhere')).toBeInTheDocument()
  })

  it('removes Escape listener when closed', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    const { rerender } = render(
      <ConfirmDialog
        open={true}
        title="Delete?"
        message="Sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    )
    // Close the dialog
    rerender(
      <ConfirmDialog
        open={false}
        title="Delete?"
        message="Sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    )
    // Escape should not fire onCancel anymore
    await user.keyboard('{Escape}')
    expect(onCancel).not.toHaveBeenCalled()
  })
})
