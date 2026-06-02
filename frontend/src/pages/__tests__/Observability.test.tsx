import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Observability from '../Observability'

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

// Mock useAuth
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true, isAdmin: false, loading: false, logout: vi.fn() }),
}))

// Mock useRequireAuth
vi.mock('../../hooks/useRequireAuth', () => ({
  useRequireAuth: () => {},
}))

const MOCK_OVERVIEW = {
  total_runs: 5,
  completed_runs: 4,
  failed_runs: 1,
  success_rate: 0.8,
  avg_step_ms: 1500,
  total_prompt_tokens: 10000,
  total_completion_tokens: 5000,
  total_tool_calls: 20,
  total_security_events: 2,
}

const MOCK_RUNS = [
  {
    id: 'run-abc123def456',
    status: 'completed',
    agent_id: 'agent-1',
    created_at: '2026-05-26T19:00:00Z',
    completed_at: '2026-05-26T19:00:15Z',
    ttft_ns: 500000000,
    total_duration_ns: 15000000000,
    stop_reason: 'end_turn',
  },
]

const MOCK_STEPS = [
  {
    id: 'step-1',
    agent_id: 'agent-1',
    model: 'gpt-4',
    model_handle: 'gpt-4',
    completion_tokens: 100,
    prompt_tokens: 500,
    total_tokens: 600,
    stop_reason: 'end_turn',
    status: 'success',
    error_type: null,
    created_at: '2026-05-26T19:00:01Z',
  },
]

const MOCK_TRACE = {
  trace_id: 'cd36d818137fd155b0152d19d4fe0548',
  spans: [
    {
      span_id: 'span-1',
      parent_span_id: null,
      operation_name: 'POST /v1/agents/{agent_id}/messages',
      start_time_us: 1000000,
      duration_us: 13614700,
      tags: {},
      has_children: true,
    },
    {
      span_id: 'span-2',
      parent_span_id: 'span-1',
      operation_name: 'LettaAgentV3.step',
      start_time_us: 1100000,
      duration_us: 13486400,
      tags: { step_id: 'step-1' },
      has_children: true,
    },
    {
      span_id: 'span-3',
      parent_span_id: 'span-2',
      operation_name: 'OpenAIClient.request_async',
      start_time_us: 1200000,
      duration_us: 13360800,
      tags: {},
      has_children: false,
    },
    {
      span_id: 'span-4',
      parent_span_id: 'span-2',
      operation_name: 'time_to_first_token',
      start_time_us: 1300000,
      duration_us: 13548400,
      tags: {},
      has_children: false,
    },
  ],
}

function setupOverviewFetch() {
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(MOCK_OVERVIEW),
  } as unknown as Response)
}

function setupRunsFetch() {
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(MOCK_RUNS),
  } as unknown as Response)
}

function setupStepsFetch() {
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(MOCK_STEPS),
  } as unknown as Response)
}

function setupStepMetricsFetch() {
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve({ id: 'step-1', step_ns: 13486400000, llm_request_ns: 13360800000, tool_execution_ns: null }),
  } as unknown as Response)
}

function setupTraceFetch() {
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(MOCK_TRACE),
  } as unknown as Response)
}

function renderObservability() {
  return render(
    <MemoryRouter>
      <Observability />
    </MemoryRouter>
  )
}

describe('Observability page', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('renders overview tab by default', async () => {
    setupOverviewFetch()
    renderObservability()

    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument()
    })
    expect(screen.getByText('Total Runs')).toBeInTheDocument()
  })

  it('switches to Runs tab', async () => {
    const user = userEvent.setup()
    setupOverviewFetch()
    renderObservability()

    await waitFor(() => {
      expect(screen.getByText('Total Runs')).toBeInTheDocument()
    })

    setupRunsFetch()
    await user.click(screen.getByText('Runs'))

    await waitFor(() => {
      expect(screen.getByText('run-abc123def456')).toBeInTheDocument()
    })
  })

  it('shows trace waterfall when run is expanded', async () => {
    const user = userEvent.setup()
    setupOverviewFetch()
    renderObservability()

    await waitFor(() => {
      expect(screen.getByText('Total Runs')).toBeInTheDocument()
    })

    // Set up runs mock BEFORE clicking the tab (RunsTab fetches on mount)
    setupRunsFetch()
    await user.click(screen.getByText('Runs'))

    await waitFor(() => {
      expect(screen.getByText('run-abc123def456')).toBeInTheDocument()
    })

    // Expand run — steps, metrics, and trace fetches need to be set up
    // The expandRun function fetches steps first, then trace
    setupStepsFetch()
    setupStepMetricsFetch()
    setupTraceFetch()

    await user.click(screen.getByText('run-abc123def456'))

    // Should show trace waterfall
    await waitFor(() => {
      expect(screen.getByText(/Trace Waterfall/)).toBeInTheDocument()
    }, { timeout: 3000 })

    // Should show span operation names
    expect(screen.getByText(/POST \/v1\/agents/)).toBeInTheDocument()
    expect(screen.getAllByText(/LettaAgentV3\.step/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/OpenAIClient\.request_async/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/time_to_first_token/).length).toBeGreaterThan(0)
  })

  it('shows "No trace data available" when trace has no trace_id', async () => {
    const user = userEvent.setup()
    setupOverviewFetch()
    renderObservability()

    await waitFor(() => {
      expect(screen.getByText('Total Runs')).toBeInTheDocument()
    })

    setupRunsFetch()
    await user.click(screen.getByText('Runs'))

    await waitFor(() => {
      expect(screen.getByText('run-abc123def456')).toBeInTheDocument()
    })

    setupStepsFetch()
    setupStepMetricsFetch()
    // Return trace with no trace_id
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ trace_id: null, spans: [] }),
    } as unknown as Response)

    await user.click(screen.getByText('run-abc123def456'))

    await waitFor(() => {
      expect(screen.getByText('No trace data available')).toBeInTheDocument()
    })
  })

  it('shows span tags when span is clicked', async () => {
    const user = userEvent.setup()
    setupOverviewFetch()
    renderObservability()

    await waitFor(() => {
      expect(screen.getByText('Total Runs')).toBeInTheDocument()
    })

    setupRunsFetch()
    await user.click(screen.getByText('Runs'))

    await waitFor(() => {
      expect(screen.getByText('run-abc123def456')).toBeInTheDocument()
    })

    setupStepsFetch()
    setupStepMetricsFetch()
    setupTraceFetch()

    await user.click(screen.getByText('run-abc123def456'))

    await waitFor(() => {
      expect(screen.getByText(/Trace Waterfall/)).toBeInTheDocument()
    }, { timeout: 3000 })

    // Click on span-2 which has tags
    await user.click(screen.getAllByText(/LettaAgentV3\.step/)[0])

    // Should show the tag
    expect(screen.getByText('step_id')).toBeInTheDocument()
    expect(screen.getByText('step-1')).toBeInTheDocument()
  })
})
