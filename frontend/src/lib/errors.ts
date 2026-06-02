/**
 * Centralized error messages.
 *
 * All user-facing error strings should reference these constants
 * so that wording changes happen in one place.
 */
export const ERROR_MESSAGES = {
  CONNECTION: 'Failed to connect to server',
  LOAD_TOOLS: 'Failed to load tools',
  LOAD_SKILLS: 'Failed to load skills',
  LOAD_WORKFLOWS: 'Failed to load workflows. Check that the server is running.',
  LOAD_AGENTS: 'Failed to load agents',
  LOAD_CREDENTIALS: 'Failed to load credentials',
  LOAD_SETTINGS: 'Failed to load settings',
  LOAD_MODELS: 'Failed to load models',
  LOAD_EMBEDDING: 'Failed to load embedding models',
  LOAD_LOGS: 'Failed to load logs',
  LOAD_PACKAGES: 'Failed to load packages',
  EXPORT: 'Failed to export data',
  IMPORT: 'Failed to import data',
} as const
