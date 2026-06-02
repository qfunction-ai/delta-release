import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Skills from '../Skills'

vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual('../../lib/api')
  return {
    ...actual,
    apiFetch: vi.fn(),
  }
})

import { apiFetch } from '../../lib/api'
const mockApiFetch = vi.mocked(apiFetch)

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true, isAdmin: false, loading: false, logout: vi.fn() }),
}))

vi.mock('../../hooks/useRequireAuth', () => ({
  useRequireAuth: () => {},
}))

const MOCK_SKILLS = [
  { id: 'skill-1', name: 'Splunk Search', description: 'Search Splunk logs', source: 'upload', tool_ids: [], file_path: '/skills/splunk.md', created_at: '2026-01-10T00:00:00Z', updated_at: '2026-01-10T00:00:00Z' },
  { id: 'skill-2', name: 'Network Scan', description: 'Scan networks', source: 'github', tool_ids: [], file_path: '/skills/network.md', created_at: '2026-01-11T00:00:00Z', updated_at: '2026-01-11T00:00:00Z' },
]

const MOCK_TOOLS = [
  { id: 'tool-1', name: 'splunk_search', description: 'Search Splunk', source: 'github', tags: null, pip_requirements: null, created_at: '2026-01-10T00:00:00Z', updated_at: '2026-01-10T00:00:00Z' },
]

const MOCK_SKILL_CONTENT = {
  id: 'skill-1',
  name: 'Splunk Search',
  description: 'Search Splunk logs',
  content: '# Splunk Search\n\nSearch Splunk for security events.',
  tool_ids: [],
  files: [],
  file_path: '/skills/splunk.md',
}

function setupFetchMocks() {
  // Skills list
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(MOCK_SKILLS),
  } as unknown as Response)
  // Tools list
  mockApiFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(MOCK_TOOLS),
  } as unknown as Response)
}

function renderSkills() {
  return render(
    <MemoryRouter>
      <Skills />
    </MemoryRouter>
  )
}

describe('Skills page', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('renders skills list after loading', async () => {
    setupFetchMocks()
    renderSkills()

    await waitFor(() => {
      expect(screen.getByText('Splunk Search')).toBeInTheDocument()
    })
    expect(screen.getByText('Network Scan')).toBeInTheDocument()
  })

  it('shows empty state when no skills exist', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([]),
    } as unknown as Response)

    renderSkills()

    await waitFor(() => {
      expect(screen.getByText('No skills loaded yet. Upload a file or fetch from GitHub to get started.')).toBeInTheDocument()
    })
  })

  it('shows fetch error when API fails', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
    } as unknown as Response)
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([]),
    } as unknown as Response)

    renderSkills()

    await waitFor(() => {
      expect(screen.getByText('Failed to load skills')).toBeInTheDocument()
    })
  })

  it('switches between upload and GitHub tabs', async () => {
    const user = userEvent.setup()
    setupFetchMocks()
    renderSkills()

    await waitFor(() => {
      expect(screen.getByText('Splunk Search')).toBeInTheDocument()
    })

    // GitHub tab is active by default
    expect(screen.getByText('GitHub URL').closest('button')).toHaveClass('pill-tab-active')

    // Switch to Upload tab
    await user.click(screen.getByText('Upload File'))
    expect(screen.getByLabelText('Upload skill file')).toBeInTheDocument()
  })

  it('shows source badges on skill cards', async () => {
    setupFetchMocks()
    renderSkills()

    await waitFor(() => {
      expect(screen.getByText('Splunk Search')).toBeInTheDocument()
    })
    expect(screen.getByText('upload')).toBeInTheDocument()
    expect(screen.getByText('github')).toBeInTheDocument()
  })

  it('shows confirm dialog on delete click', async () => {
    const user = userEvent.setup()
    setupFetchMocks()
    renderSkills()

    await waitFor(() => {
      expect(screen.getByText('Splunk Search')).toBeInTheDocument()
    })

    const deleteButtons = screen.getAllByText('Delete')
    await user.click(deleteButtons[0])

    await waitFor(() => {
      expect(screen.getByText('Delete Skill')).toBeInTheDocument()
    })
  })

  it('shows placeholder when no skill is selected', async () => {
    setupFetchMocks()
    renderSkills()

    await waitFor(() => {
      expect(screen.getByText('Select a skill to inspect its contents.')).toBeInTheDocument()
    })
  })

  it('shows skill detail when clicking a skill card', async () => {
    setupFetchMocks()
    // Mock the content fetch for when user clicks a skill
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(MOCK_SKILL_CONTENT),
    } as unknown as Response)

    const user = userEvent.setup()
    renderSkills()

    await waitFor(() => {
      expect(screen.getByText('Splunk Search')).toBeInTheDocument()
    })

    // Click the skill card
    await user.click(screen.getByText('Splunk Search'))

    // The detail panel should show the Edit button (unique to detail view)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    })
  })

  it('shows Edit button in skill detail panel', async () => {
    setupFetchMocks()
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(MOCK_SKILL_CONTENT),
    } as unknown as Response)

    const user = userEvent.setup()
    renderSkills()

    await waitFor(() => {
      expect(screen.getByText('Splunk Search')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Splunk Search'))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    })
  })

  it('shows connection error when fetch throws', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('Network error'))

    renderSkills()

    await waitFor(() => {
      expect(screen.getByText('Failed to connect to server')).toBeInTheDocument()
    })
  })

  it('adds tool to local state after GitHub import with tool', async () => {
    const user = userEvent.setup()
    setupFetchMocks()

    // Mock the GitHub import response — skill with tool_ids, plus a tool
    const importedSkill = {
      id: 'skill-imported',
      name: 'imported-skill',
      description: 'An imported skill',
      source: 'github',
      tool_ids: ['tool-imported'],
      file_path: '/skills/imported.md',
      created_at: '2026-01-12T00:00:00Z',
      updated_at: '2026-01-12T00:00:00Z',
    }
    const importedTool = {
      id: 'tool-imported',
      name: 'imported_tool',
      description: 'An imported tool',
      source: 'github',
      tags: null,
      pip_requirements: null,
      created_at: '2026-01-12T00:00:00Z',
      updated_at: '2026-01-12T00:00:00Z',
    }
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ skill: importedSkill, tool: importedTool }),
    } as unknown as Response)

    renderSkills()

    await waitFor(() => {
      expect(screen.getByText('Splunk Search')).toBeInTheDocument()
    })

    // Switch to GitHub tab
    await user.click(screen.getByText('GitHub URL'))

    // Type URL and submit
    const input = screen.getByLabelText('GitHub Repository URL')
    await user.type(input, 'https://github.com/org/repo/tree/main/skills/test')
    await user.click(screen.getByRole('button', { name: 'Fetch Skill' }))

    // The imported skill should appear in the list
    await waitFor(() => {
      expect(screen.getByText('imported-skill')).toBeInTheDocument()
    })

    // Click the imported skill to view it
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        id: 'skill-imported',
        name: 'imported-skill',
        description: 'An imported skill',
        content: '---\nname: imported-skill\n---\nContent',
        tool_ids: ['tool-imported'],
        files: [],
      }),
    } as unknown as Response)

    await user.click(screen.getByText('imported-skill'))

    // The "Required Tools" section should show the imported tool name
    await waitFor(() => {
      expect(screen.getByText('imported_tool')).toBeInTheDocument()
    })
  })
})
