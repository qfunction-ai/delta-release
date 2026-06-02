import { describe, it, expect } from 'vitest'
import { isValidSkillFile } from '../skills.utils'

describe('isValidSkillFile', () => {
  it('accepts .zip files', () => {
    expect(isValidSkillFile('package.zip')).toBe(true)
  })

  it('accepts .skill files', () => {
    expect(isValidSkillFile('module.skill')).toBe(true)
  })

  it('rejects other extensions', () => {
    expect(isValidSkillFile('readme.md')).toBe(false)
    expect(isValidSkillFile('script.py')).toBe(false)
    expect(isValidSkillFile('data.json')).toBe(false)
  })

  it('rejects files with no extension', () => {
    expect(isValidSkillFile('Dockerfile')).toBe(false)
  })

  it('handles case-sensitive extensions', () => {
    expect(isValidSkillFile('package.ZIP')).toBe(false)
    expect(isValidSkillFile('package.Skill')).toBe(false)
  })
})
