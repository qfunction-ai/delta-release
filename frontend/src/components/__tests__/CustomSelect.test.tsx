import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CustomSelect from '../CustomSelect'

const OPTIONS = [
  { value: 'a', label: 'Option A' },
  { value: 'b', label: 'Option B' },
  { value: 'c', label: 'Option C' },
]

describe('CustomSelect', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders with placeholder when no value selected', () => {
    render(<CustomSelect value="" onChange={vi.fn()} options={OPTIONS} placeholder="Pick one" />)
    expect(screen.getByRole('combobox')).toHaveTextContent('Pick one')
  })

  it('renders selected option label', () => {
    render(<CustomSelect value="b" onChange={vi.fn()} options={OPTIONS} />)
    expect(screen.getByRole('combobox')).toHaveTextContent('Option B')
  })

  it('opens dropdown on click', async () => {
    const user = userEvent.setup()
    render(<CustomSelect value="" onChange={vi.fn()} options={OPTIONS} />)
    await user.click(screen.getByRole('combobox'))
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    expect(screen.getAllByRole('option')).toHaveLength(3)
  })

  it('calls onChange and closes dropdown on option click', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<CustomSelect value="" onChange={onChange} options={OPTIONS} />)
    await user.click(screen.getByRole('combobox'))
    await user.click(screen.getByText('Option B'))
    expect(onChange).toHaveBeenCalledWith('b')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('closes dropdown on Escape', async () => {
    const user = userEvent.setup()
    render(<CustomSelect value="" onChange={vi.fn()} options={OPTIONS} />)
    await user.click(screen.getByRole('combobox'))
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('navigates options with ArrowDown', async () => {
    const user = userEvent.setup()
    render(<CustomSelect value="" onChange={vi.fn()} options={OPTIONS} />)
    const combobox = screen.getByRole('combobox')
    combobox.focus()
    await user.keyboard('{ArrowDown}')
    expect(combobox).toHaveAttribute('aria-activedescendant', 'custom-select-option-0')
    await user.keyboard('{ArrowDown}')
    expect(combobox).toHaveAttribute('aria-activedescendant', 'custom-select-option-1')
  })

  it('navigates options with ArrowUp', async () => {
    const user = userEvent.setup()
    render(<CustomSelect value="" onChange={vi.fn()} options={OPTIONS} />)
    const combobox = screen.getByRole('combobox')
    combobox.focus()
    await user.keyboard('{ArrowUp}')
    // ArrowUp from closed opens at last option
    expect(combobox).toHaveAttribute('aria-activedescendant', 'custom-select-option-2')
  })

  it('selects active option with Enter', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<CustomSelect value="" onChange={onChange} options={OPTIONS} />)
    const combobox = screen.getByRole('combobox')
    combobox.focus()
    await user.keyboard('{ArrowDown}') // open + activate first
    await user.keyboard('{Enter}')
    expect(onChange).toHaveBeenCalledWith('a')
  })

  it('marks selected option with aria-selected', async () => {
    const user = userEvent.setup()
    render(<CustomSelect value="b" onChange={vi.fn()} options={OPTIONS} />)
    await user.click(screen.getByRole('combobox'))
    const options = screen.getAllByRole('option')
    expect(options[1]).toHaveAttribute('aria-selected', 'true')
    expect(options[0]).toHaveAttribute('aria-selected', 'false')
  })

  it('disables trigger when disabled prop is true', () => {
    render(<CustomSelect value="" onChange={vi.fn()} options={OPTIONS} disabled />)
    expect(screen.getByRole('combobox')).toBeDisabled()
  })

  it('does not open dropdown when disabled', async () => {
    const user = userEvent.setup()
    render(<CustomSelect value="" onChange={vi.fn()} options={OPTIONS} disabled />)
    await user.click(screen.getByRole('combobox'))
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('uses custom id for aria attributes', async () => {
    const user = userEvent.setup()
    render(<CustomSelect id="my-select" value="" onChange={vi.fn()} options={OPTIONS} />)
    const combobox = screen.getByRole('combobox')
    expect(combobox).toHaveAttribute('aria-controls', 'my-select-listbox')
    await user.click(combobox)
    expect(screen.getByRole('listbox')).toHaveAttribute('id', 'my-select-listbox')
  })

  it('uses custom aria-label', () => {
    render(<CustomSelect value="" onChange={vi.fn()} options={OPTIONS} aria-label="Choose model" />)
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-label', 'Choose model')
  })

  it('closes dropdown on click outside', async () => {
    const user = userEvent.setup()
    render(
      <div>
        <div data-testid="outside">Outside</div>
        <CustomSelect value="" onChange={vi.fn()} options={OPTIONS} />
      </div>
    )
    await user.click(screen.getByRole('combobox'))
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    await user.click(screen.getByTestId('outside'))
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
})
