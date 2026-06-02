import { describe, it, expect, vi, beforeEach } from 'vitest'
import { relativeTime, formatDuration, fmtTokens, formatNs, msToHuman, fmtTime } from '../formatters'

describe('relativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-15T12:00:00Z'))
  })

  it('returns seconds for events within 60 seconds', () => {
    expect(relativeTime('2026-01-15T11:59:30Z')).toBe('30s ago')
  })

  it('returns minutes for events within 60 minutes', () => {
    expect(relativeTime('2026-01-15T11:30:00Z')).toBe('30m ago')
  })

  it('returns hours for events within 24 hours', () => {
    expect(relativeTime('2026-01-15T09:00:00Z')).toBe('3h ago')
  })

  it('returns days for older events', () => {
    expect(relativeTime('2026-01-12T12:00:00Z')).toBe('3d ago')
  })

  it('handles zero difference', () => {
    expect(relativeTime('2026-01-15T12:00:00Z')).toBe('0s ago')
  })

  it('returns — for null/undefined', () => {
    expect(relativeTime(null)).toBe('—')
    expect(relativeTime(undefined)).toBe('—')
  })
})

describe('formatDuration', () => {
  it('formats milliseconds for values under 1 second', () => {
    expect(formatDuration(500)).toBe('500ms')
    expect(formatDuration(0)).toBe('0ms')
    expect(formatDuration(999)).toBe('999ms')
  })

  it('formats seconds with one decimal for values under 1 minute', () => {
    expect(formatDuration(1500)).toBe('1.5s')
    expect(formatDuration(30000)).toBe('30.0s')
    expect(formatDuration(59999)).toBe('60.0s')
  })

  it('formats minutes and seconds for values >= 1 minute', () => {
    expect(formatDuration(60000)).toBe('1m 0s')
    expect(formatDuration(90000)).toBe('1m 30s')
    expect(formatDuration(125000)).toBe('2m 5s')
  })
})

describe('fmtTokens', () => {
  it('formats small numbers directly', () => {
    expect(fmtTokens(0)).toBe('0')
    expect(fmtTokens(999)).toBe('999')
  })

  it('formats thousands with k suffix', () => {
    expect(fmtTokens(1500)).toBe('1.5k')
    expect(fmtTokens(999999)).toBe('1000.0k')
  })

  it('formats millions with M suffix', () => {
    expect(fmtTokens(1500000)).toBe('1.50M')
  })

  it('returns — for null/undefined', () => {
    expect(fmtTokens(null)).toBe('—')
    expect(fmtTokens(undefined)).toBe('—')
  })
})

describe('formatNs', () => {
  it('formats microseconds for sub-millisecond values', () => {
    expect(formatNs(500_000)).toBe('500.0μs')
  })

  it('formats milliseconds for sub-second values', () => {
    expect(formatNs(50_000_000)).toBe('50.0ms')
  })

  it('formats seconds for larger values', () => {
    expect(formatNs(1_500_000_000)).toBe('1.50s')
  })

  it('returns — for null/undefined', () => {
    expect(formatNs(null)).toBe('—')
    expect(formatNs(undefined)).toBe('—')
  })
})

describe('msToHuman', () => {
  it('formats milliseconds for sub-second values', () => {
    expect(msToHuman(500)).toBe('500.0ms')
  })

  it('formats seconds for larger values', () => {
    expect(msToHuman(1500)).toBe('1.50s')
  })

  it('returns — for null/undefined', () => {
    expect(msToHuman(null)).toBe('—')
    expect(msToHuman(undefined)).toBe('—')
  })
})

describe('fmtTime', () => {
  it('returns — for null/undefined', () => {
    expect(fmtTime(null)).toBe('—')
    expect(fmtTime(undefined)).toBe('—')
  })

  it('returns locale string for valid ISO', () => {
    const result = fmtTime('2026-01-15T12:00:00Z')
    expect(result).not.toBe('—')
  })
})
