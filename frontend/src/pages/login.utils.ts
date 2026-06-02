/**
 * Registration validation logic extracted from Login.tsx.
 * Pure function — no side effects, no React state.
 */

export function validateRegistration(
  username: string,
  password: string,
  confirmPassword: string
): string | null {
  if (username.length < 3) return 'Username must be at least 3 characters'
  if (password.length < 8) return 'Password must be at least 8 characters'
  if (password !== confirmPassword) return 'Passwords do not match'
  return null
}
