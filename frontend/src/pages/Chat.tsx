import { useState, useEffect, useRef, useCallback } from 'react'
import { apiFetch } from '../lib/api'
import { useRequireAuth } from '../hooks/useRequireAuth'
import { useSSEStream } from '../hooks/useSSEStream'
import { useOllamaStatus } from '../hooks/useOllamaStatus'
import { Agent, Tool, Skill, ChatMessage } from '../lib/types'
import { LoadingSpinner } from '../components/LoadingSpinner'
import ToggleSwitch from '../components/ToggleSwitch'



export default function Chat() {
  useRequireAuth()
  const ollama = useOllamaStatus()
  const [ollamaDismissed, setOllamaDismissed] = useState(false)
  const [agents, setAgents] = useState<Agent[]>([])
  const [tools, setTools] = useState<Tool[]>([])
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)

  // Config
  const [agentId, setAgentId] = useState('')
  const [selectedTools, setSelectedTools] = useState<Set<string>>(new Set())
  const [configOpen, setConfigOpen] = useState(false)
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null)
  const skillAutoToolsRef = useRef<string[]>([])
  const [includeReasoning, setIncludeReasoning] = useState(true)

  // Chat
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [securityWarning, setSecurityWarning] = useState('')
  const [secretWarnings, setSecretWarnings] = useState<string[]>([])

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messageIdRef = useRef(0)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isAtBottomRef = useRef(true)

  // SSE streaming
  const includeReasoningRef = useRef(includeReasoning)
  includeReasoningRef.current = includeReasoning

  const { streaming, startStream, cancelStream } = useSSEStream({
    onContent: useCallback((content: string, reasoning: string) => {
      setMessages(prev => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last && last.role === 'assistant') {
          updated[updated.length - 1] = {
            ...last,
            content: (last.content || '') + content,
            reasoning: includeReasoningRef.current
              ? (last.reasoning || '') + reasoning
              : last.reasoning,
          }
        }
        return updated
      })
    }, []),
    onError: useCallback((err: string) => setError(err), []),
    onCompleted: useCallback(() => {
      setMessages(prev => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last && last.role === 'assistant') {
          updated[updated.length - 1] = {
            ...last,
            reasoning: last.reasoning || undefined,
            content: last.content || '(no response)',
          }
        }
        return updated
      })
    }, []),
    onSecurityEvent: useCallback((_event: string, message: string) => {
      setSecurityWarning(message)
    }, []),
    onSecretWarning: useCallback((warnings: string[]) => {
      setSecretWarnings(warnings)
    }, []),
  })

  const fetchData = useCallback(async () => {
    try {
      const [agentsRes, toolsRes, skillsRes] = await Promise.all([
        apiFetch('/api/agents/'),
        apiFetch('/api/tools/'),
        apiFetch('/api/skills/'),
      ])

      if (agentsRes.ok) setAgents(await agentsRes.json())
      if (toolsRes.ok) setTools(await toolsRes.json())
      if (skillsRes.ok) setSkills(await skillsRes.json())
    } catch {
      setError('Failed to load chat data. Please try refreshing the page.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const loadHistory = useCallback(async (id: string) => {
    try {
      const res = await apiFetch(`/api/chat/history/${encodeURIComponent(id)}`)
      if (res.ok) {
        const data = await res.json()
        setMessages(
          (data.messages || []).map((m: { role: string; content: string; reasoning?: string }, i: number) => ({
            id: i,
            role: m.role as 'user' | 'assistant',
            content: m.content,
            reasoning: m.reasoning || undefined,
          }))
        )
        messageIdRef.current = (data.messages || []).length
      } else {
        setMessages([])
      }
    } catch {
      setMessages([])
      setError('Failed to load chat history.')
    }
  }, [])

  useEffect(() => {
    if (agentId) {
      loadHistory(agentId)
    } else {
      setMessages([])
    }
  }, [agentId, loadHistory])

  useEffect(() => {
    if (isAtBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  const toggleTool = useCallback((id: string) => {
    setSelectedTools(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }, [])

  const toggleSkill = (id: string) => {
    setSelectedSkill(prev => {
      if (prev === id) {
        setSelectedTools(prev => {
          const next = new Set(prev)
          for (const t of skillAutoToolsRef.current) next.delete(t)
          return next
        })
        skillAutoToolsRef.current = []
        return null
      }
      setSelectedTools(prev => {
        const next = new Set(prev)
        for (const t of skillAutoToolsRef.current) next.delete(t)
        const skill = skills.find(s => s.id === id)
        const newAutoTools = skill?.tool_ids ?? []
        skillAutoToolsRef.current = newAutoTools
        for (const t of newAutoTools) next.add(t)
        return next
      })
      return id
    })
  }

  const handleSend = async () => {
    if (!input.trim() || !agentId || streaming) return

    const userMessage = input.trim()
    setInput('')
    setError('')
    setSecurityWarning('')
    setSecretWarnings([])
    const now = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
    const userId = ++messageIdRef.current
    const assistantId = ++messageIdRef.current
    setMessages(prev => [...prev, { id: userId, role: 'user', content: userMessage, timestamp: now }])
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '', reasoning: '', timestamp: now }])

    try {
      const response = await apiFetch('/api/chat/stream', {
        method: 'POST',
        body: JSON.stringify({
          agent_id: agentId,
          message: userMessage,
          tool_ids: [...selectedTools],
          skill_ids: selectedSkill ? [selectedSkill] : [],
          include_reasoning: includeReasoning,
        }),
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => null)
        setError(errData?.detail || `Request failed (${response.status}). Check that the agent is running and try again.`)
        setMessages(prev => prev.slice(0, -1))
        return
      }

      await startStream(response)
    } catch (_err) {
      setError('Failed to send message. Check your connection and try again.')
      setMessages(prev => prev.slice(0, -1))
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const selectedAgent = agents.find(a => a.letta_agent_id === agentId)

  if (loading) return (
    <div className="chat-loading-container">
      <LoadingSpinner />
    </div>
  )

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 4rem)', margin: '-2rem' }}>
      {/* Header */}
      <div className="animate-entry" style={{
        padding: '1rem 2rem',
        borderBottom: '1px solid var(--border)',
        background: 'rgba(19, 23, 32, 0.95)',
        backdropFilter: 'blur(12px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <select
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              aria-label="Select agent"
              style={{
                background: 'var(--bg-input)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-sans)',
                fontSize: '0.85rem',
                padding: '0.4rem 0.75rem',
                cursor: 'pointer',
              }}
            >
              <option value="">Select agent...</option>
              {agents.map(a => (
                <option key={a.letta_agent_id} value={a.letta_agent_id}>{a.name}</option>
              ))}
            </select>
            {selectedAgent && (
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.65rem', color: 'var(--text-tertiary)', background: 'var(--bg-tertiary)', padding: '0.15rem 0.5rem', border: '1px solid var(--border)' }}>{selectedAgent.model}</span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <label htmlFor="toggle-reasoning" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontFamily: 'var(--font-sans)', fontSize: '0.75rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
            <span>Reasoning</span>
            <ToggleSwitch id="toggle-reasoning" checked={includeReasoning} onChange={() => setIncludeReasoning(!includeReasoning)} aria-label="Toggle reasoning" />
          </label>
          <button
            onClick={() => setConfigOpen(!configOpen)}
            style={{
              background: 'none',
              border: '1px solid var(--border)',
              color: configOpen ? 'var(--accent)' : 'var(--text-secondary)',
              padding: '0.35rem 0.75rem',
              fontFamily: 'var(--font-sans)',
              fontSize: '0.7rem',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            ⚙ Config
          </button>
        </div>
      </div>

      {/* Ollama-down banner */}
      {!ollama.loading && !ollama.available && !ollamaDismissed && (
        <div style={{
          padding: '0.5rem 2rem',
          background: 'rgba(251, 191, 36, 0.1)',
          borderBottom: '1px solid rgba(251, 191, 36, 0.3)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.75rem', color: '#FDB022' }}>
            Ollama is not running. Start Ollama on your machine to use chat.
          </span>
          <button
            onClick={() => setOllamaDismissed(true)}
            aria-label="Dismiss Ollama warning"
            style={{ background: 'none', border: 'none', color: '#FDB022', cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: '0.85rem', padding: '0 0.5rem' }}
          >
            ×
          </button>
        </div>
      )}

      {/* Config panel (slide-down) */}
      {configOpen && (
        <div style={{
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border)',
          padding: '1rem 2rem',
          display: 'grid',
          gridTemplateColumns: '1fr 1fr 1fr',
          gap: '2rem',
          flexShrink: 0,
        }}>
          {/* Agent selector (if not selected in header) */}
          {selectedAgent && (
            <div>
              <div className="config-section-label">Agent</div>
              <select
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                aria-label="Select agent"
                style={{
                  width: '100%',
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-sans)',
                  fontSize: '0.75rem',
                  padding: '0.4rem 0.75rem',
                }}
              >
                <option value="">Select agent...</option>
                {agents.map(a => (
                  <option key={a.letta_agent_id} value={a.letta_agent_id}>{a.name}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <div className="config-section-label">Skills</div>
            {skills.length === 0 ? (
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>No skills available</span>
            ) : (
              skills.map(s => (
                <label key={s.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontFamily: 'var(--font-sans)', fontSize: '0.75rem', color: selectedSkill === s.id ? 'var(--accent)' : 'var(--text-secondary)', cursor: 'pointer', marginBottom: '0.25rem' }}>
                  <input type="checkbox" checked={selectedSkill === s.id} onChange={() => toggleSkill(s.id)} style={{ accentColor: 'var(--accent)' }} aria-label={s.name} />
                  <span>{s.name}</span>
                </label>
              ))
            )}
          </div>
          <div>
            <div className="config-section-label">Tools</div>
            <div style={{ maxHeight: '150px', overflowY: 'auto' }}>
              {tools.length === 0 ? (
                <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>No tools available</span>
              ) : (
                tools.map(t => (
                  <label key={t.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontFamily: 'var(--font-sans)', fontSize: '0.75rem', color: selectedTools.has(t.id) ? 'var(--accent)' : 'var(--text-secondary)', cursor: 'pointer', marginBottom: '0.25rem' }}>
                    <input type="checkbox" checked={selectedTools.has(t.id)} onChange={() => toggleTool(t.id)} style={{ accentColor: 'var(--accent)' }} aria-label={t.name} />
                    <span>{t.name}</span>
                  </label>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Messages */}
      <div
        ref={scrollContainerRef}
        onScroll={() => {
          const el = scrollContainerRef.current
          if (!el) return
          const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
          isAtBottomRef.current = distFromBottom < 50
        }}
        style={{ flex: 1, overflowY: 'auto', padding: '1.5rem 2rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}
      >
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--text-tertiary)', marginTop: '3rem' }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: '3rem', color: 'var(--accent)', opacity: 0.15, marginBottom: '1rem' }}>f(x)</div>
            {agentId ? 'Send a message to start chatting' : 'Select an agent to begin'}
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: 'flex',
              gap: '0.75rem',
              maxWidth: '85%',
              alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
              flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
            }}
          >
            {/* Avatar */}
            <div className={`message-avatar ${msg.role === 'user' ? 'user' : 'agent'}`}>
              {msg.role === 'user' ? 'CS' : 'Δ'}
            </div>

            {/* Content */}
            <div style={{
              background: msg.role === 'user' ? 'var(--bg-hover)' : 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              borderColor: msg.role === 'user' ? 'rgba(255,255,255,0.08)' : 'var(--border)',
              padding: '0.75rem 1rem',
              position: 'relative',
              minWidth: 0,
            }}>
              {/* Reasoning block */}
              {msg.role === 'assistant' && msg.reasoning && (
                <div className="reasoning-block">
                  <span className="reasoning-label">REASONING</span>
                  <div className="reasoning-content">{msg.reasoning}</div>
                </div>
              )}

              {/* Message text */}
              <div style={{ fontSize: '0.9rem', lineHeight: 1.6, color: 'var(--text-primary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {msg.content || (streaming && msg.role === 'assistant' ? (
                  <div className="typing-indicator">
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                  </div>
                ) : null)}
              </div>

              {/* AI label */}
              {msg.role === 'assistant' && msg.content && (
                <span className="ai-label">AI-generated</span>
              )}

              {/* Tool call blocks */}
              {msg.role === 'assistant' && msg.toolCalls && msg.toolCalls.map((tc, j) => (
                <div key={`${tc.name}-${j}`} className="tool-call-block">
                  <span className="tool-call-icon">⚡</span>
                  <span className="tool-call-name">{tc.name}</span>
                  <span className="tool-call-status">✓ {tc.status}</span>
                </div>
              ))}

              {/* Meta */}
              <div className="message-meta" style={{ marginTop: '0.5rem' }}>
                {msg.timestamp && <span>{msg.timestamp}</span>}
                {msg.duration != null && <span>· {msg.duration}s</span>}
                {msg.tokens != null && <span>· {msg.tokens} tokens</span>}
              </div>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Error */}
      {error && (
        <div className="chat-error-bar">
          {error}
        </div>
      )}

      {/* Security warning */}
      {securityWarning && (
        <div className="chat-security-bar">
          <span>{securityWarning}</span>
          <button onClick={() => setSecurityWarning('')} aria-label="Dismiss security warning" className="chat-security-dismiss">×</button>
        </div>
      )}

      {/* Secret detection warning */}
      {secretWarnings.length > 0 && (
        <div className="chat-secret-warning-bar">
          <span>
            Your message may contain {secretWarnings.join(', ')}. Consider storing credentials in the Credentials page instead.
          </span>
          <button onClick={() => setSecretWarnings([])} aria-label="Dismiss secret warning" className="chat-security-dismiss">×</button>
        </div>
      )}

      {/* Input area */}
      <div style={{ padding: '1rem 2rem 1.5rem', borderTop: '1px solid var(--border)', background: 'var(--bg-secondary)', flexShrink: 0 }}>
        <div style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: '0.75rem',
          background: 'var(--bg-input)',
          border: '1px solid var(--border)',
          padding: '0.75rem 1rem',
          transition: 'all 0.2s ease',
        }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={agentId ? `Send a message to ${selectedAgent?.name || 'agent'}...` : 'Select an agent first'}
            disabled={!agentId || streaming}
            aria-label="Chat message input"
            rows={1}
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-sans)',
              fontSize: '0.9rem',
              resize: 'none',
              minHeight: '24px',
              maxHeight: '120px',
            }}
          />
          {streaming ? (
            <button
              onClick={cancelStream}
              aria-label="Stop generating"
              style={{
                width: 36,
                height: 36,
                background: 'var(--danger)',
                border: 'none',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                flexShrink: 0,
                color: 'white',
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <rect x="4" y="4" width="16" height="16" rx="2" />
              </svg>
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim() || !agentId}
              aria-label="Send message"
              style={{
                width: 36,
                height: 36,
                background: !input.trim() || !agentId ? 'var(--bg-tertiary)' : 'var(--accent)',
                border: 'none',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: !input.trim() || !agentId ? 'not-allowed' : 'pointer',
                flexShrink: 0,
                transition: 'all 0.2s ease',
                opacity: !input.trim() || !agentId ? 0.5 : 1,
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="var(--bg-primary)" aria-hidden="true"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" /></svg>
            </button>
          )}
        </div>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: '0.6rem', color: 'var(--text-tertiary)', marginTop: '0.5rem', textAlign: 'center' }}>
          λ(msg) → f(agent) → Δ(response)
        </div>
      </div>
    </div>
  )
}
