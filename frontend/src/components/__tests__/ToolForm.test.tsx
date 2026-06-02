import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ToolForm from '../ToolForm'

const defaultProps = {
  activeTab: 'manual' as const,
  onTabChange: vi.fn(),
  name: '',
  setName: vi.fn(),
  description: '',
  setDescription: vi.fn(),
  sourceCode: '',
  setSourceCode: vi.fn(),
  tags: '',
  setTags: vi.fn(),
  pipReqs: '',
  setPipReqs: vi.fn(),
  githubUrl: '',
  setGithubUrl: vi.fn(),
  error: '',
  creating: false,
  fetchingGithub: false,
  onCreate: vi.fn(),
  onGithub: vi.fn(),
}

describe('ToolForm', () => {
  it('renders manual tab by default with all form fields', () => {
    render(<ToolForm {...defaultProps} />)

    expect(screen.getByLabelText(/Name \(snake_case\)/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Description/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Tags \(comma-separated\)/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Pip Requirements \(comma-separated\)/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Source Code/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create Tool' })).toBeInTheDocument()
  })

  it('switches to GitHub tab on click', async () => {
    const user = userEvent.setup()
    const onTabChange = vi.fn()
    render(<ToolForm {...defaultProps} onTabChange={onTabChange} />)

    await user.click(screen.getByRole('button', { name: 'GitHub URL' }))
    expect(onTabChange).toHaveBeenCalledWith('github')
  })

  it('shows "Creating..." when creating is true', () => {
    render(<ToolForm {...defaultProps} creating={true} />)
    expect(screen.getByRole('button', { name: 'Creating...' })).toBeInTheDocument()
  })

  it('shows "Fetching from GitHub..." when fetchingGithub is true', () => {
    render(
      <ToolForm {...defaultProps} activeTab="github" fetchingGithub={true} />
    )
    expect(screen.getByRole('button', { name: 'Fetching from GitHub...' })).toBeInTheDocument()
  })

  it('displays error message when error prop is set', () => {
    render(<ToolForm {...defaultProps} error="Something went wrong" />)
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('calls onCreate on manual form submit', async () => {
    const user = userEvent.setup()
    const onCreate = vi.fn()
    render(
      <ToolForm
        {...defaultProps}
        name="search_splunk"
        sourceCode="def search_splunk(): pass"
        onCreate={onCreate}
      />
    )

    const submitButton = screen.getByRole('button', { name: 'Create Tool' })
    await user.click(submitButton)
    expect(onCreate).toHaveBeenCalledTimes(1)
  })

  it('calls onGithub on GitHub form submit', async () => {
    const user = userEvent.setup()
    const onGithub = vi.fn()
    render(
      <ToolForm
        {...defaultProps}
        activeTab="github"
        githubUrl="https://github.com/user/repo"
        onGithub={onGithub}
      />
    )

    const submitButton = screen.getByRole('button', { name: 'Fetch Tool' })
    await user.click(submitButton)
    expect(onGithub).toHaveBeenCalledTimes(1)
  })

  it('Create button is disabled when name is empty', () => {
    render(<ToolForm {...defaultProps} name="" sourceCode="some code" />)
    expect(screen.getByRole('button', { name: 'Create Tool' })).toBeDisabled()
  })

  it('Fetch button is disabled when githubUrl is empty/whitespace', () => {
    const { rerender } = render(
      <ToolForm {...defaultProps} activeTab="github" githubUrl="" />
    )
    expect(screen.getByRole('button', { name: 'Fetch Tool' })).toBeDisabled()

    rerender(
      <ToolForm {...defaultProps} activeTab="github" githubUrl="   " />
    )
    expect(screen.getByRole('button', { name: 'Fetch Tool' })).toBeDisabled()
  })
})
