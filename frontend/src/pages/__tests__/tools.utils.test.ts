import { describe, it, expect } from 'vitest'
import { parseTags, parsePipReqs, parseSchema } from '../tools.utils'

describe('parseTags', () => {
  it('returns null for empty string', () => {
    expect(parseTags('')).toBeNull()
  })

  it('splits comma-separated tags and trims whitespace', () => {
    expect(parseTags('splunk, search , logs')).toEqual(['splunk', 'search', 'logs'])
  })

  it('handles single tag', () => {
    expect(parseTags('security')).toEqual(['security'])
  })
})

describe('parsePipReqs', () => {
  it('returns null for empty string', () => {
    expect(parsePipReqs('')).toBeNull()
  })

  it('splits, trims, and filters empty segments', () => {
    expect(parsePipReqs('requests, paramiko==2.12.0, , ')).toEqual(['requests', 'paramiko==2.12.0'])
  })

  it('handles single requirement', () => {
    expect(parsePipReqs('requests')).toEqual(['requests'])
  })
})

describe('parseSchema', () => {
  it('parses valid JSON', () => {
    const result = parseSchema('{"type":"object"}')
    expect(result).toEqual({ ok: true, value: { type: 'object' } })
  })

  it('returns error for invalid JSON', () => {
    const result = parseSchema('not-json')
    expect(result).toEqual({ ok: false, error: 'Invalid JSON schema' })
  })

  it('parses arrays', () => {
    const result = parseSchema('[1, 2, 3]')
    expect(result).toEqual({ ok: true, value: [1, 2, 3] })
  })
})
