/**
 * Parsing and validation logic extracted from Tools.tsx.
 * Pure functions — no side effects, no React state.
 */

export function parseTags(tagsStr: string): string[] | null {
  if (!tagsStr) return null
  return tagsStr.split(',').map(t => t.trim())
}

export function parsePipReqs(reqsStr: string): string[] | null {
  if (!reqsStr) return null
  return reqsStr.split(',').map(p => p.trim()).filter(p => p)
}

export function parseSchema(
  schemaStr: string
): { ok: true; value: unknown } | { ok: false; error: string } {
  try {
    return { ok: true, value: JSON.parse(schemaStr) }
  } catch {
    return { ok: false, error: 'Invalid JSON schema' }
  }
}
