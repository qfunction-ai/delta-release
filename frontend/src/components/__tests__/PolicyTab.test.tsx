import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { fireEvent } from '@testing-library/react'
import PolicyTab from '../PolicyTab'

// Mock apiFetch
vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual('../../lib/api')
  return {
    ...actual,
    apiFetch: vi.fn(),
  }
})

import { apiFetch } from '../../lib/api'
const mockApiFetch = vi.mocked(apiFetch)

const MOCK_POLICY = {
  agent_id: 'agent-1',
  denied_tools: ['web_search', 'fetch_webpage'],
  approval_required_tools: ['core_memory_append'],
  rules: [
    {
      name: 'deny_archival_after_5',
      condition: { field: 'tool_name', operator: 'eq', value: 'archival_memory_insert' },
      action: 'deny',
      priority: 10,
      message: 'No more archival writes after 5 calls',
      pattern: null,
    },
  ],
  max_calls_per_tool: { archival_memory_insert: 5 },
  defaults: { action: 'allow', max_tool_calls: 100, max_tokens: null, timeout_seconds: null },
}

const MOCK_EMPTY_POLICY = {
  agent_id: 'agent-1',
  denied_tools: [],
  approval_required_tools: [],
  rules: [],
  max_calls_per_tool: {},
  defaults: null,
}

function setupPolicyFetch(policy: Record<string, unknown> = MOCK_POLICY) {
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(policy),
  } as unknown as Response)
}

function setupPatchResponse(updated: Record<string, unknown>) {
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(updated),
  } as unknown as Response)
}

function renderPolicyTab(agentId = 'agent-1') {
  return render(<PolicyTab agentId={agentId} />)
}

describe('PolicyTab', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('renders policy sections with data', async () => {
    setupPolicyFetch()
    renderPolicyTab()

    await waitFor(() => {
      expect(screen.getByText('Denied Tools')).toBeInTheDocument()
    })
    expect(screen.getByText('web_search')).toBeInTheDocument()
    expect(screen.getByText('fetch_webpage')).toBeInTheDocument()
    expect(screen.getByText('core_memory_append')).toBeInTheDocument()
    expect(screen.getByText('deny_archival_after_5')).toBeInTheDocument()
    expect(screen.getByText('archival_memory_insert')).toBeInTheDocument()
    expect(screen.getByText('Rate Limits')).toBeInTheDocument()
    expect(screen.getByText('Defaults')).toBeInTheDocument()
    expect(screen.getAllByText('Evaluate').length).toBeGreaterThanOrEqual(1)
  })

  it('renders empty policy with empty states', async () => {
    setupPolicyFetch(MOCK_EMPTY_POLICY)
    renderPolicyTab()

    await waitFor(() => {
      expect(screen.getByText('No denied tools. All tools are allowed by default.')).toBeInTheDocument()
    })
    expect(screen.getByText('No tools require approval.')).toBeInTheDocument()
    expect(screen.getByText('No policy rules configured.')).toBeInTheDocument()
    expect(screen.getByText('No per-tool rate limits configured.')).toBeInTheDocument()
  })

  it('adds a denied tool via PATCH', async () => {
    const user = userEvent.setup()
    setupPolicyFetch()
    renderPolicyTab()

    await waitFor(() => {
      expect(screen.getByText('web_search')).toBeInTheDocument()
    })

    // Type new tool name and add
    const input = screen.getByPlaceholderText('Add denied tool...')
    await user.type(input, 'send_email')

    // Setup PATCH response
    const updatedPolicy = {
      ...MOCK_POLICY,
      denied_tools: ['web_search', 'fetch_webpage', 'send_email'],
    }
    setupPatchResponse(updatedPolicy)

    await user.click(screen.getAllByText('Add')[0])

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/agents/agent-1/policy',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ denied_tools: ['web_search', 'fetch_webpage', 'send_email'] }),
        }),
      )
    })
  })

  it('removes a denied tool via PATCH', async () => {
    const user = userEvent.setup()
    setupPolicyFetch()
    renderPolicyTab()

    await waitFor(() => {
      expect(screen.getByText('web_search')).toBeInTheDocument()
    })

    const updatedPolicy = {
      ...MOCK_POLICY,
      denied_tools: ['fetch_webpage'],
    }
    setupPatchResponse(updatedPolicy)

    // Click Remove next to web_search
    const removeButtons = screen.getAllByText('Remove')
    await user.click(removeButtons[0])

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/agents/agent-1/policy',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ denied_tools: ['fetch_webpage'] }),
        }),
      )
    })
  })

  it('adds an approval-required tool via PATCH', async () => {
    const user = userEvent.setup()
    setupPolicyFetch()
    renderPolicyTab()

    await waitFor(() => {
      expect(screen.getByText('core_memory_append')).toBeInTheDocument()
    })

    const input = screen.getByPlaceholderText('Add approval tool...')
    await user.type(input, 'archival_memory_insert')

    const updatedPolicy = {
      ...MOCK_POLICY,
      approval_required_tools: ['core_memory_append', 'archival_memory_insert'],
    }
    setupPatchResponse(updatedPolicy)

    // The second "Add" button is for approval tools
    const addButtons = screen.getAllByText('Add')
    await user.click(addButtons[1])

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/agents/agent-1/policy',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ approval_required_tools: ['core_memory_append', 'archival_memory_insert'] }),
        }),
      )
    })
  })

  it('adds a rate limit via PATCH', async () => {
    const user = userEvent.setup()
    setupPolicyFetch()
    renderPolicyTab()

    await waitFor(() => {
      expect(screen.getByText('Rate Limits')).toBeInTheDocument()
    })

    const toolInput = screen.getByPlaceholderText('Tool name')
    const limitInput = screen.getByPlaceholderText('Max calls')
    await user.type(toolInput, 'web_search')
    await user.type(limitInput, '10')

    const updatedPolicy = {
      ...MOCK_POLICY,
      max_calls_per_tool: { archival_memory_insert: 5, web_search: 10 },
    }
    setupPatchResponse(updatedPolicy)

    const addButtons = screen.getAllByText('Add')
    // Rate limit Add button is after the two tool Add buttons
    await user.click(addButtons[2])

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/agents/agent-1/policy',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ max_calls_per_tool: { archival_memory_insert: 5, web_search: 10 } }),
        }),
      )
    })
  })

  it('evaluates a tool call via POST with JSON body', async () => {
    const user = userEvent.setup()
    setupPolicyFetch()
    renderPolicyTab()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Evaluate' })).toBeInTheDocument()
    })

    const toolInput = screen.getByPlaceholderText('Tool to evaluate...')
    await user.type(toolInput, 'web_search')

    // Mock evaluate response
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        allowed: false,
        action: 'deny',
        matched_rule: 'denied_tools',
        reason: "Tool 'web_search' is in denied_tools list",
      }),
    } as unknown as Response)

    await user.click(screen.getByRole('button', { name: 'Evaluate' }))

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/agents/agent-1/policy/evaluate',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ tool_name: 'web_search', tool_args: undefined }),
        }),
      )
    })

    // Verify decision rendered
    expect(screen.getByText('DENY')).toBeInTheDocument()
    expect(screen.getByText(/matched: denied_tools/)).toBeInTheDocument()
  })

  it('evaluates with tool_args JSON body', async () => {
    const user = userEvent.setup()
    setupPolicyFetch()
    renderPolicyTab()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Evaluate' })).toBeInTheDocument()
    })

    const toolInput = screen.getByPlaceholderText('Tool to evaluate...')
    await user.type(toolInput, 'archival_memory_search')

    const argsInput = screen.getByPlaceholderText(/Tool arguments/)
    // Use fireEvent to set JSON value (userEvent.type treats { as special key)
    await user.click(argsInput)
    fireEvent.change(argsInput, { target: { value: '{"query": "test"}' } })

    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        allowed: true,
        action: 'allow',
        matched_rule: null,
        reason: 'No rules matched; default action applied',
      }),
    } as unknown as Response)

    await user.click(screen.getByRole('button', { name: 'Evaluate' }))

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/agents/agent-1/policy/evaluate',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ tool_name: 'archival_memory_search', tool_args: { query: 'test' } }),
        }),
      )
    })

    expect(screen.getByText('ALLOW')).toBeInTheDocument()
  })

  it('shows error on evaluate failure', async () => {
    const user = userEvent.setup()
    setupPolicyFetch()
    renderPolicyTab()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Evaluate' })).toBeInTheDocument()
    })

    const toolInput = screen.getByPlaceholderText('Tool to evaluate...')
    await user.type(toolInput, 'test')

    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      text: () => Promise.resolve('Agent not found'),
    } as unknown as Response)

    await user.click(screen.getByRole('button', { name: 'Evaluate' }))

    await waitFor(() => {
      expect(screen.getByText('Evaluation failed')).toBeInTheDocument()
    })
  })

  it('shows error for invalid JSON in tool_args', async () => {
    const user = userEvent.setup()
    setupPolicyFetch()
    renderPolicyTab()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Evaluate' })).toBeInTheDocument()
    })

    const toolInput = screen.getByPlaceholderText('Tool to evaluate...')
    await user.type(toolInput, 'test')

    const argsInput = screen.getByPlaceholderText(/Tool arguments/)
    await user.type(argsInput, 'not-json')

    await user.click(screen.getByRole('button', { name: 'Evaluate' }))

    await waitFor(() => {
      expect(screen.getByText('Invalid JSON in tool_args')).toBeInTheDocument()
    })
  })

  it('resets policy via DELETE', async () => {
    const user = userEvent.setup()
    setupPolicyFetch()
    renderPolicyTab()

    await waitFor(() => {
      expect(screen.getByText('Reset to Default (Allow All)')).toBeInTheDocument()
    })

    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(MOCK_EMPTY_POLICY),
    } as unknown as Response)

    await user.click(screen.getByText('Reset to Default (Allow All)'))

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/agents/agent-1/policy',
        expect.objectContaining({ method: 'DELETE' }),
      )
    })
  })

  it('shows loading state during fetch', () => {
    // Don't resolve the fetch — keep it pending
    mockApiFetch.mockReturnValue(new Promise(() => {}))
    renderPolicyTab()

    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('shows fetch error on API failure', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      text: () => Promise.resolve('Server error'),
    } as unknown as Response)

    renderPolicyTab()

    await waitFor(() => {
      expect(screen.getByText('Failed to load policy')).toBeInTheDocument()
    })
  })
})
