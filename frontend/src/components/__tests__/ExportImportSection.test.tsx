import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ExportImportSection from '../ExportImportSection'

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

function renderSection() {
  return render(
    <MemoryRouter>
      <ExportImportSection />
    </MemoryRouter>
  )
}

describe('ExportImportSection', () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('renders Export and Import sections', () => {
    renderSection()
    expect(screen.getByText('Export Data')).toBeInTheDocument()
    expect(screen.getByText('Import Data')).toBeInTheDocument()
  })

  it('renders Export All button', () => {
    renderSection()
    expect(screen.getByRole('button', { name: 'Export All' })).toBeInTheDocument()
  })

  it('renders file input for import', () => {
    renderSection()
    expect(screen.getByLabelText('JSON File')).toBeInTheDocument()
  })

  it('calls export API on Export All click', async () => {
    const mockBlob = new Blob(['{"version":"1.0"}'], { type: 'application/json' })
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      blob: () => Promise.resolve(mockBlob),
    } as unknown as Response)

    renderSection()
    fireEvent.click(screen.getByRole('button', { name: 'Export All' }))

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith('/api/export-import/export/')
    })
  })

  it('shows error when export fails', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
    } as unknown as Response)

    renderSection()
    fireEvent.click(screen.getByRole('button', { name: 'Export All' }))

    await waitFor(() => {
      expect(screen.getByText('Failed to export data')).toBeInTheDocument()
    })
  })

  it('shows import result after successful import', async () => {
    const importResult = {
      tools_imported: 2,
      tools_skipped: 0,
      skills_imported: 1,
      skills_skipped: 0,
      workflows_imported: 1,
      workflows_skipped: 0,
      workflows_needing_agent: 1,
      errors: [],
    }

    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(importResult),
    } as unknown as Response)

    renderSection()

    // Select a file
    const fileInput = screen.getByLabelText('JSON File') as HTMLInputElement
    const file = new File(['{"version":"1.0"}'], 'export.json', { type: 'application/json' })
    Object.defineProperty(fileInput, 'files', { value: [file], configurable: true })
    fireEvent.change(fileInput)

    // Click Import button
    const importButton = screen.getByRole('button', { name: 'Import' })
    fireEvent.click(importButton)

    await waitFor(() => {
      expect(screen.getByText('Import Complete')).toBeInTheDocument()
    })
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText(/tools imported/)).toBeInTheDocument()
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText(/skills imported/)).toBeInTheDocument()
    expect(screen.getByText(/workflows imported/)).toBeInTheDocument()
  })

  it('shows error when import fails', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'Invalid JSON' }),
    } as unknown as Response)

    renderSection()

    // Select a file
    const fileInput = screen.getByLabelText('JSON File') as HTMLInputElement
    const file = new File(['not json'], 'bad.json', { type: 'application/json' })
    Object.defineProperty(fileInput, 'files', { value: [file], configurable: true })
    fireEvent.change(fileInput)

    // Click Import button
    const importButton = screen.getByRole('button', { name: 'Import' })
    fireEvent.click(importButton)

    await waitFor(() => {
      expect(screen.getByText('Invalid JSON')).toBeInTheDocument()
    })
  })
})
