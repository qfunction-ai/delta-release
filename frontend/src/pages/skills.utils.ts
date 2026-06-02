/**
 * File validation logic extracted from Skills.tsx.
 * Pure function — no side effects.
 */

const VALID_EXTENSIONS = ['.zip', '.skill']

export function isValidSkillFile(filename: string): boolean {
  return VALID_EXTENSIONS.some(ext => filename.endsWith(ext))
}
