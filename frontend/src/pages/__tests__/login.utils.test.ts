import { describe, it, expect } from 'vitest'
import { validateRegistration } from '../login.utils'

describe('validateRegistration', () => {
  it('returns null for valid input', () => {
    expect(validateRegistration('admin', 'password123', 'password123')).toBeNull()
  })

  it('rejects username shorter than 3 characters', () => {
    expect(validateRegistration('ab', 'password123', 'password123'))
      .toBe('Username must be at least 3 characters')
  })

  it('rejects password shorter than 8 characters', () => {
    expect(validateRegistration('admin', 'short', 'short'))
      .toBe('Password must be at least 8 characters')
  })

  it('rejects mismatched passwords', () => {
    expect(validateRegistration('admin', 'password123', 'different123'))
      .toBe('Passwords do not match')
  })

  it('checks username length before password match', () => {
    expect(validateRegistration('a', 'short', 'different'))
      .toBe('Username must be at least 3 characters')
  })

  it('checks password length before password match', () => {
    expect(validateRegistration('admin', 'short', 'short'))
      .toBe('Password must be at least 8 characters')
  })
})
