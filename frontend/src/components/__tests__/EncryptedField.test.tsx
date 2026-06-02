import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EncryptedField } from '../EncryptedField'

describe('EncryptedField', () => {
  it('renders the label', () => {
    render(<EncryptedField label="API Key" />)
    expect(screen.getByText('API Key')).toBeInTheDocument()
  })

  it('renders masked value', () => {
    render(<EncryptedField label="Secret" />)
    expect(screen.getByText('••••••••')).toBeInTheDocument()
  })

  it('renders encrypted indicator', () => {
    render(<EncryptedField label="Token" />)
    expect(screen.getByText(/encrypted/)).toBeInTheDocument()
  })

  it('renders lock emoji', () => {
    const { container } = render(<EncryptedField label="Password" />)
    expect(container.textContent).toContain('🔒')
  })
})
