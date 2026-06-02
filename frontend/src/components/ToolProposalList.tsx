import { ToolProposal } from '../lib/types'

interface ToolProposalListProps {
  proposals: ToolProposal[]
  viewingProposal: ToolProposal | null
  onViewProposal: (proposal: ToolProposal) => void
  onClose: () => void
  onApprove: (proposalId: string) => void
  onReject: (proposalId: string) => void
  approving: boolean
  error: string
}

export default function ToolProposalList({
  proposals,
  viewingProposal,
  onViewProposal,
  onClose,
  onApprove,
  onReject,
  approving,
  error,
}: ToolProposalListProps) {
  return (
    <>
      {/* Pending Proposals */}
      {proposals.length > 0 && (
        <div className="card mb-4" style={{ borderColor: 'var(--warning)' }}>
          <h3 className="section-header" data-symbol="!">Pending Proposals</h3>
          {proposals.map(proposal => (
            <div
              key={proposal.id}
              className="card card-interactive mb-2"
              role="button"
              tabIndex={0}
              onClick={() => onViewProposal(proposal)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onViewProposal(proposal) }}
              style={{ cursor: 'pointer' }}
            >
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-mono" style={{ fontWeight: 600 }}>{proposal.name}</span>
                  <span className="badge badge-warning ml-4">AI-generated</span>
                </div>
                <span className="text-sm text-muted">
                  {proposal.dry_run_error ? 'Dry run failed' : 'Dry run passed'}
                </span>
              </div>
              {proposal.description && (
                <p className="text-sm text-muted mt-2" style={{ margin: 0 }}>{proposal.description}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Proposal Review Panel */}
      {viewingProposal && (
        <div className="card mb-4" style={{ borderColor: 'var(--accent)' }}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-mono" style={{ margin: 0 }}>{viewingProposal.name}</h3>
              <span className="badge badge-warning">AI-generated</span>
            </div>
            <button
              className="btn btn-ghost"
              onClick={onClose}
            >
              Close
            </button>
          </div>

          {viewingProposal.description && (
            <p className="text-sm mb-4">{viewingProposal.description}</p>
          )}

          {/* Dry Run Results */}
          <div className="mb-4">
            <h4 style={{ margin: 0, marginBottom: '0.375rem' }}>Dry Run Results</h4>
            {viewingProposal.dry_run_error ? (
              <div className="error" style={{ fontSize: '0.8125rem' }}>{viewingProposal.dry_run_error}</div>
            ) : (
              <div style={{
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                background: 'var(--accent-subtle)',
                border: '1px solid var(--accent-border)',
                fontSize: '0.8125rem',
                fontFamily: 'var(--font-mono)',
                whiteSpace: 'pre-wrap',
              }}>
                {viewingProposal.dry_run_output || 'No output'}
              </div>
            )}
          </div>

          {/* Source Code — always visible */}
          <div className="mb-4">
            <h4 style={{ margin: 0, marginBottom: '0.375rem' }}>Source Code</h4>
            <pre style={{
              padding: '1rem',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              fontSize: '0.8125rem',
              fontFamily: 'var(--font-mono)',
              lineHeight: '1.6',
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
              maxWidth: '100%',
            }}>
              {viewingProposal.source_code}
            </pre>
          </div>

          {/* JSON Schema */}
          <div className="mb-4">
            <h4 style={{ margin: 0, marginBottom: '0.375rem' }}>Schema</h4>
            <pre style={{
              padding: '0.75rem 1rem',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              fontSize: '0.8125rem',
              fontFamily: 'var(--font-mono)',
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
              maxWidth: '100%',
            }}>
              {JSON.stringify(viewingProposal.json_schema, null, 2)}
            </pre>
          </div>

          {viewingProposal.pip_requirements && viewingProposal.pip_requirements.length > 0 && (
            <div className="mb-4">
              <h4 style={{ margin: 0, marginBottom: '0.375rem' }}>Dependencies</h4>
              <div className="flex gap-2 flex-wrap">
                {viewingProposal.pip_requirements.map(pkg => (
                  <span key={pkg} className="badge badge-info">{pkg}</span>
                ))}
              </div>
            </div>
          )}

          {error && <div className="error mb-4">{error}</div>}

          <div className="flex gap-3">
            <button
              className="btn btn-primary"
              disabled={approving}
              onClick={() => onApprove(viewingProposal.id)}
            >
              {approving ? 'Approving...' : 'Approve'}
            </button>
            <button
              className="btn btn-ghost"
              onClick={() => onReject(viewingProposal.id)}
            >
              Reject
            </button>
          </div>
        </div>
      )}
    </>
  )
}
