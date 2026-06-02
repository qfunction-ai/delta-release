import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ToolProposalList from '../ToolProposalList'
import { ToolProposal } from '../../lib/types'

const mockProposal: ToolProposal = {
  id: 'prop-1',
  name: 'search_splunk',
  description: 'Search Splunk for events',
  source_code: 'def search_splunk(): pass',
  json_schema: { type: 'object', properties: { query: { type: 'string' } } },
  tags: ['splunk'],
  pip_requirements: ['httpx'],
  proposed_by: 'agent-1',
  dry_run_output: 'OK',
  dry_run_error: null,
  created_at: '2026-01-10T00:00:00Z',
}

const defaultProps = {
  proposals: [mockProposal] as ToolProposal[],
  viewingProposal: null as ToolProposal | null,
  onViewProposal: vi.fn(),
  onClose: vi.fn(),
  onApprove: vi.fn(),
  onReject: vi.fn(),
  approving: false,
  error: '',
}

describe('ToolProposalList', () => {
  it('renders pending proposals list', () => {
    render(<ToolProposalList {...defaultProps} />)

    expect(screen.getByText('Pending Proposals')).toBeInTheDocument()
    expect(screen.getByText('search_splunk')).toBeInTheDocument()
    expect(screen.getByText('AI-generated')).toBeInTheDocument()
  })

  it('shows dry run status for each proposal', () => {
    render(<ToolProposalList {...defaultProps} />)

    expect(screen.getByText('Dry run passed')).toBeInTheDocument()
  })

  it('shows dry run failed when proposal has dry_run_error', () => {
    const failedProposal = {
      ...mockProposal,
      dry_run_error: 'ImportError: no module named foo',
      dry_run_output: null,
    }
    render(<ToolProposalList {...defaultProps} proposals={[failedProposal]} />)

    expect(screen.getByText('Dry run failed')).toBeInTheDocument()
  })

  it('calls onViewProposal when clicking a proposal card', async () => {
    const user = userEvent.setup()
    const onViewProposal = vi.fn()
    render(<ToolProposalList {...defaultProps} onViewProposal={onViewProposal} />)

    await user.click(screen.getByText('search_splunk'))
    expect(onViewProposal).toHaveBeenCalledWith(mockProposal)
  })

  it('renders review panel with approve and reject buttons when viewingProposal is set', () => {
    render(
      <ToolProposalList
        {...defaultProps}
        viewingProposal={mockProposal}
      />
    )

    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
    expect(screen.getByText('Source Code')).toBeInTheDocument()
    expect(screen.getByText('Schema')).toBeInTheDocument()
  })

  it('shows Approving... button when approving is true', () => {
    render(
      <ToolProposalList
        {...defaultProps}
        viewingProposal={mockProposal}
        approving={true}
      />
    )

    expect(screen.getByRole('button', { name: 'Approving...' })).toBeInTheDocument()
  })

  it('calls onApprove when Approve button is clicked', async () => {
    const user = userEvent.setup()
    const onApprove = vi.fn()
    render(
      <ToolProposalList
        {...defaultProps}
        viewingProposal={mockProposal}
        onApprove={onApprove}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Approve' }))
    expect(onApprove).toHaveBeenCalledWith('prop-1')
  })

  it('calls onReject when Reject button is clicked', async () => {
    const user = userEvent.setup()
    const onReject = vi.fn()
    render(
      <ToolProposalList
        {...defaultProps}
        viewingProposal={mockProposal}
        onReject={onReject}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Reject' }))
    expect(onReject).toHaveBeenCalledWith('prop-1')
  })

  it('renders nothing when proposals list is empty', () => {
    const { container } = render(
      <ToolProposalList {...defaultProps} proposals={[]} />
    )

    expect(container.innerHTML).toBe('')
  })
})
