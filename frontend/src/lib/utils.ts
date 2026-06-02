/**
 * Shared utility functions.
 */

/**
 * Toggle an item in an array — add if absent, remove if present.
 */
export function toggleInArray<T>(arr: T[], item: T): T[] {
  return arr.includes(item) ? arr.filter(x => x !== item) : [...arr, item]
}
