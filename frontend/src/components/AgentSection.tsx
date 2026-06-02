import { useState } from 'react'
import { apiFetch, extractApiError } from '../lib/api'
import { ERROR_MESSAGES } from '../lib/errors'
import { useApiFetch } from '../hooks/useApiFetch'
import ToggleSwitch from './ToggleSwitch'
import AlertBox from './AlertBox'

interface Settings {
  agent_tool_creation: boolean
  web_search_enabled: boolean
  docs_fetch_enabled: boolean
  exa_key_configured: boolean
}

export default function AgentSection() {
  const { data: settings, loading, error: fetchError, setData: setSettings } = useApiFetch<Settings>('/api/settings/', {
    errorMessage: 'Failed to load settings',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const toggleSetting = async (key: keyof Settings) => {
    if (!settings) return
    setError('')
    setSaving(true)
    const newValue = !settings[key]
    try {
      const response = await apiFetch('/api/settings/', {
        method: 'PUT',
        body: JSON.stringify({ [key]: newValue }),
      })
      if (response.ok) {
        setSettings(await response.json())
      } else {
        setError(await extractApiError(response, 'Failed to update setting'))
      }
    } catch (_err) {
      setError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="text-sm text-muted">Loading settings...</div>
  }

  if (fetchError) {
    return <div className="error">{fetchError}</div>
  }

  if (!settings) {
    return <div className="text-sm text-muted">Loading settings...</div>
  }

  return (
    <div>
      {/* Agent Tool Creation Toggle */}
      <div className="card mb-6">
        <div className="flex items-center justify-between">
          <div style={{ maxWidth: 'calc(100% - 80px)' }}>
            <h3 style={{ margin: 0, marginBottom: '0.375rem' }}>Allow agents to propose tools</h3>
            <p className="text-sm text-muted" style={{ margin: 0 }}>
              When enabled, agents can draft new tools during conversations.
              Proposed tools require your approval before they can be used.
            </p>
          </div>
          <ToggleSwitch
            checked={settings.agent_tool_creation}
            onChange={() => toggleSetting('agent_tool_creation')}
            disabled={saving}
            aria-label="Allow agents to create tools"
          />
        </div>

        {settings.agent_tool_creation && (
          <AlertBox variant="warning">
            Agent-proposed tools are AI-generated. Always review the behavior before approving.
          </AlertBox>
        )}
      </div>

      {/* Web Search Toggle */}
      <div className="card mb-6">
        <div className="flex items-center justify-between">
          <div style={{ maxWidth: 'calc(100% - 80px)' }}>
            <h3 style={{ margin: 0, marginBottom: '0.375rem' }}>Allow agents to search the web</h3>
            <p className="text-sm text-muted" style={{ margin: 0 }}>
              When enabled, agents can search the web for library documentation before proposing tools.
              Requires EXA_API_KEY to be configured.
            </p>
          </div>
          <ToggleSwitch
            checked={settings.web_search_enabled}
            onChange={() => toggleSetting('web_search_enabled')}
            disabled={saving}
            aria-label="Allow agents to search the web"
          />
        </div>

        {settings.web_search_enabled && !settings.exa_key_configured && (
          <AlertBox variant="danger">
            EXA_API_KEY is not configured. The web_search tool will be attached but calls will fail until the API key is set in the environment.
          </AlertBox>
        )}

        {settings.web_search_enabled && settings.exa_key_configured && (
          <AlertBox variant="warning">
            Web search allows agents to query the internet. Searches are limited to documentation lookups via persona instructions, but the capability cannot be technically restricted to specific topics.
          </AlertBox>
        )}
      </div>

      {/* Documentation Fetch Toggle */}
      <div className="card mb-6">
        <div className="flex items-center justify-between">
          <div style={{ maxWidth: 'calc(100% - 80px)' }}>
            <h3 style={{ margin: 0, marginBottom: '0.375rem' }}>Allow agents to fetch documentation</h3>
            <p className="text-sm text-muted" style={{ margin: 0 }}>
              When enabled, agents can fetch full documentation pages from allowed domains before proposing tools.
              This provides more detailed API references than web search snippets.
            </p>
          </div>
          <ToggleSwitch
            checked={settings.docs_fetch_enabled}
            onChange={() => toggleSetting('docs_fetch_enabled')}
            disabled={saving}
            aria-label="Allow agents to fetch documentation"
          />
        </div>

        {settings.docs_fetch_enabled && (
          <AlertBox variant="warning">
            Fetched documentation is injected into the agent's context as untrusted text. Although domains are restricted and SSRF-protected, pages on allowed domains may contain adversarial content (e.g., prompt injection). Review proposed tools carefully before approving.
          </AlertBox>
        )}
      </div>

      {error && <div className="error">{error}</div>}
    </div>
  )
}
