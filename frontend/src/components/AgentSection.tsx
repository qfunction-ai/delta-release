import { useState, useEffect } from 'react'
import { apiFetch, extractApiError } from '../lib/api'
import { ERROR_MESSAGES } from '../lib/errors'
import { useApiFetch } from '../hooks/useApiFetch'
import ToggleSwitch from './ToggleSwitch'
import AlertBox from './AlertBox'

interface Settings {
  agent_tool_creation: boolean
  eval_enabled: boolean
}

interface DomainsResponse {
  domains: string[]
}

export default function AgentSection() {
  const { data: settings, loading, error: fetchError, setData: setSettings } = useApiFetch<Settings>('/api/settings/', {
    errorMessage: 'Failed to load settings',
  })
  const { data: domainsData, loading: domainsLoading, refetch: refetchDomains } = useApiFetch<DomainsResponse>(
    '/api/docs/domains',
    { errorMessage: 'Failed to load domains', immediate: false }
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Fetch allowed domains when tool creation is enabled
  useEffect(() => {
    if (settings?.agent_tool_creation) {
      refetchDomains()
    }
  }, [settings?.agent_tool_creation, refetchDomains])

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
          <div className="toggle-card-description">
            <h3 className="toggle-card-heading">Allow agents to propose tools</h3>
            <p className="text-sm text-muted">
              When enabled, agents can draft new tools during conversations and fetch documentation
              from allowed domains. Proposed tools require your approval before use.
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
          <>
            <AlertBox variant="warning">
              Agent-proposed tools are AI-generated. Always review the behavior before approving.
              Fetched documentation is from external sources and may contain adversarial content.
            </AlertBox>

            {!domainsLoading && domainsData && domainsData.domains.length > 0 && (
              <div className="mt-4">
                <p className="text-sm text-muted mb-2">Allowed documentation domains:</p>
                <div className="flex flex-wrap gap-2">
                  {domainsData.domains.map((domain) => (
                    <span
                      key={domain}
                      className="px-2 py-1 text-xs rounded bg-surface text-muted border border-border"
                    >
                      {domain}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {error && <div className="error">{error}</div>}
    </div>
  )
}
