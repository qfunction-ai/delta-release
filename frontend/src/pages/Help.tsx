import { useState, useRef, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'

interface HelpSection {
  id: string
  title: string
  icon: string
  content: React.ReactNode
}

const sections: HelpSection[] = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    icon: '🚀',
    content: (
      <>
        <p>
          <strong>Delta</strong> is a security operations platform that brings together AI agents, custom tools,
          reusable skills, and automated workflows. Think of it as your team's command center for
          orchestrating intelligent security operations.
        </p>
        <h4>Prerequisites</h4>
        <ul>
          <li><strong>Docker and Docker Compose</strong> installed on your machine</li>
          <li><strong>Ollama</strong> running on the host with at least one model pulled (e.g., <code>gemma4:latest</code>)</li>
          <li>At least 4GB RAM for the Docker stack</li>
        </ul>
        <h4>First Steps</h4>
        <ol>
          <li><strong>Start Delta</strong> — Run <code>docker compose up -d</code> and wait for all services to become healthy (<code>docker compose ps</code>).</li>
          <li><strong>Log in</strong> — Open <code>http://localhost:3000</code>. The first account is automatically assigned the admin role. Secrets (JWT, encryption key, service token) are auto-generated on first run — no <code>.env</code> configuration required.</li>
          <li><strong>Create an Agent</strong> — Head to the Agents page and spin up your first AI agent. Pick a model, give it a name, and it's ready to chat.</li>
          <li><strong>Chat with your Agent</strong> — Use the Chat page to interact with your agent. Ask questions, run tools, and see reasoning in real time.</li>
          <li><strong>Add Tools & Skills</strong> — Equip your agent with custom tools (Python functions) and skills (instruction documents) so it can take action.</li>
          <li><strong>Build a Workflow</strong> — Chain tools and skills into automated workflows that run on a schedule or on demand.</li>
        </ol>
      </>
    ),
  },
  {
    id: 'dashboard',
    title: 'Dashboard',
    icon: '📊',
    content: (
      <>
        <p>
          The Dashboard is your landing page — a quick overview of what's happening in your Delta instance.
        </p>
        <h4>What You'll See</h4>
        <ul>
          <li><strong>Stats</strong> — Counts of active agents, available tools, loaded skills, and workflows at a glance</li>
          <li><strong>Service Health</strong> — Status indicators for backend, Letta, database, and Ollama connectivity</li>
          <li><strong>Agent Fleet</strong> — List of your agents with quick links to chat or view details</li>
          <li><strong>Recent Runs</strong> — The latest workflow executions with status and timing</li>
        </ul>
      </>
    ),
  },
  {
    id: 'agents',
    title: 'Agents',
    icon: '🤖',
    content: (
      <>
        <p>
          Agents are AI-powered assistants backed by large language models. Each agent has its own memory,
          personality, and set of tools and skills.
        </p>
        <h4>Creating an Agent</h4>
        <ol>
          <li>Go to <strong>Agents</strong> in the sidebar</li>
          <li>Click <strong>Create Agent</strong></li>
          <li>Choose a <strong>model</strong> (e.g., Gemma 4) and an <strong>embedding model</strong> for memory</li>
          <li>Give it a name and click <strong>Create</strong></li>
        </ol>
        <h4>Agent Detail Tabs</h4>
        <p>Click on an agent to see its detail view with two tabs:</p>
        <ul>
          <li><strong>Details</strong> — Agent name, model, memory blocks, attached tools and skills, and chat shortcut</li>
          <li><strong>Policy</strong> — Configure tool call policies: allow, deny, or require approval for specific tools. Policies are enforced at runtime by the Letta Local fork — the agent cannot bypass them regardless of prompting.</li>
        </ul>
        <h4>Agent Memory</h4>
        <p>
          Each agent has four memory blocks: <strong>persona</strong> (its identity and role),
          <strong>human</strong> (information about the user), <strong>workflow_context</strong> (current task context),
          and <strong>findings</strong> (accumulated discoveries). The persona and workflow_context blocks are
          read-only — the agent cannot modify them through tool calls.
        </p>
        <h4>File Persistence</h4>
        <p>
          Every agent gets four file tools auto-attached at creation: <code>file_list</code>, <code>file_read</code>,
          <code>file_write</code>, and <code>grep_files</code>. These let the agent read, write, and search files
          in its own per-agent workspace. Tools that produce large output write to a staging directory first, then
          the runtime validates and promotes files to the persistent workspace. This lets agents work
          with data that exceeds the tool return character limit.
        </p>
      </>
    ),
  },
  {
    id: 'chat',
    title: 'Chat',
    icon: '💬',
    content: (
      <>
        <p>
          The Chat page is your primary interface for interacting with agents. Send messages, run tools,
          and observe the agent's reasoning process.
        </p>
        <h4>How to Chat</h4>
        <ol>
          <li>Select an <strong>agent</strong> from the dropdown at the top</li>
          <li>Click the <strong>gear icon</strong> to open the Config panel and attach tools or select skills</li>
          <li>Type your message in the input box and press <strong>Enter</strong> (or Shift+Enter for a newline)</li>
          <li>Watch the agent's response stream in real time</li>
        </ol>
        <h4>Features</h4>
        <ul>
          <li><strong>Include Reasoning</strong> — Toggle this to see the agent's internal thought process alongside its response</li>
          <li><strong>Skill Selection</strong> — Skills are checkboxes in the Config panel. Check a skill to include its instructions with your message. The skill stays selected across messages — important for multi-step skills that require back-and-forth conversation. Uncheck the skill when you're done and want to ask general questions.</li>
          <li><strong>Tool Attachment</strong> — Attach specific tools from the Config panel before sending a message</li>
          <li><strong>Tool Execution</strong> — When the agent decides to use a tool, you'll see the tool call and its result inline</li>
          <li><strong>Message History</strong> — Previous messages are preserved within the session</li>
          <li><strong>Scroll Behavior</strong> — The chat auto-scrolls to the bottom only when you're already near the bottom. If you scroll up during a streaming response, the view stays where you are — you won't be jerked back down.</li>
        </ul>
      </>
    ),
  },
  {
    id: 'skills',
    title: 'Skills',
    icon: '📖',
    content: (
      <>
        <p>
          Skills are instruction documents that teach agents how to perform specific tasks. They're written
          in Markdown with YAML frontmatter and attached to agents to expand their capabilities.
        </p>
        <h4>Creating a Skill</h4>
        <p>There are three ways to add a skill:</p>
        <ol>
          <li><strong>Manual</strong> — Write the skill content directly in the form. Include a name and Markdown body.</li>
          <li><strong>Upload a Zip</strong> — Upload a <code>.zip</code> file containing a <code>SKILL.md</code> file (with optional supporting files like scripts and <code>requirements.txt</code>).</li>
          <li><strong>GitHub Import</strong> — Paste a GitHub URL pointing to a skill repository. Delta will fetch and parse the <code>SKILL.md</code> automatically.</li>
        </ol>
        <h4>Skill Format</h4>
        <p>Skills use YAML frontmatter for metadata:</p>
        <pre>{`---
name: my-skill
description: What this skill does
---

# Skill Content

Instructions for the agent...`}</pre>
        <h4>How Skills Work at Runtime</h4>
        <p>
          When you select a skill in the Chat Config panel and send a message, the skill's full instructions are
          injected inline into the message. The agent follows every step in order. Skills are provided per-message:
          the agent is instructed to respond directly to general questions unrelated to a skill, even when a skill
          is selected. If you send a follow-up message that doesn't need the skill, the agent should respond
          normally.
        </p>
        <h4>Required-Tool Enforcement</h4>
        <p>
          When a skill has linked tools (via the skill-tool join table), Delta injects a metadata block into the
          message that tells the Letta Local fork to enforce those tools as required — the agent cannot stop
          (call <code>send_message</code>) until all linked tools have been called at least once. This prevents
          the agent from stopping mid-skill.
        </p>
        <p>
          <strong>Important for skill creators:</strong> Only link tools that are mandatory in every execution of
          the skill. If a tool is optional or conditional (e.g., "use grep_files if the file is large"), do not
          link it — attach it separately instead. Linked tools are binary: the agent must call them before it
          can stop, even when the skill logic doesn't need them for that particular run.
        </p>
        <h4>Multi-Step Skills</h4>
        <p>
          Some skills require back-and-forth conversation — the agent asks for input (e.g., a SumoLogic query and
          timerange), the user provides it, and the agent continues. The skill checkbox stays selected across
          messages, so the skill context is injected on each message until you uncheck it. Keep the skill selected
          for the entire multi-step interaction.
        </p>
      </>
    ),
  },
  {
    id: 'tools',
    title: 'Tools',
    icon: '🔧',
    content: (
      <>
        <p>
          Tools are Python functions that agents can call to take actions — querying APIs,
          running searches, executing scripts, and more.
        </p>
        <h4>Creating a Tool</h4>
        <ol>
          <li>Go to <strong>Tools</strong> in the sidebar</li>
          <li>Click <strong>Create Tool</strong></li>
          <li>Write the Python source code for your tool function</li>
          <li>Provide a name and description (the agent uses these to decide when to call the tool)</li>
          <li>Click <strong>Create</strong></li>
        </ol>
        <h4>Tool Authoring Rules</h4>
        <ul>
          <li><strong>No credentials in signatures</strong> — Never put API keys, passwords, or connection parameters in the function signature. Read them from environment variables inside the function body. The agent should only see the domain parameters it needs to fill.</li>
          <li><strong>Large output goes to staging</strong> — Tools that return more than 50K characters should write to the staging directory and return a compact summary with <code>file_path</code> and <code>hint</code> fields. The agent can then use <code>file_read</code> or <code>grep_files</code> to access the full data.</li>
        </ul>
        <h4>Tool Proposals</h4>
        <p>
          When the <strong>Agent Tool Creation</strong> setting is enabled (Settings → Agent), agents can propose
          new tools at runtime. The agent calls <code>propose_tool</code> with a name, description, source code,
          and JSON schema. The proposal enters a pending state with dry-run results, requiring human review and
          approval before activation. Enabling this setting also attaches three companion tools:
        </p>
        <ul>
          <li><code>fetch_docs</code> — Fetches documentation from allowed domains (readthedocs.io, pypi.org, github.com, raw.githubusercontent.com, etc.) with SSRF protection</li>
          <li><code>list_github_repo</code> — Lists the file tree of a GitHub repository (public repos, 60 req/hr unauthenticated)</li>
          <li><code>read_github_file</code> — Reads raw file content from GitHub with optional line ranges for large files</li>
        </ul>
        <p>
          Agents are instructed to never guess API signatures from memory — they must fetch documentation first
          or tell the operator that documentation could not be retrieved.
        </p>
        <h4>GitHub Import</h4>
        <p>
          Import tools directly from GitHub repositories by pasting a URL. Delta fetches the source code
          and registers it as a tool.
        </p>
      </>
    ),
  },
  {
    id: 'workflows',
    title: 'Workflows',
    icon: '⚡',
    content: (
      <>
        <p>
          Workflows are automated sequences that chain tools and skills together. They can run on a
          schedule (cron) or be triggered on demand.
        </p>
        <h4>Creating a Workflow</h4>
        <ol>
          <li>Go to <strong>Workflows</strong> in the sidebar</li>
          <li>Click <strong>Create Workflow</strong></li>
          <li>Select the <strong>agent</strong> that will execute the workflow</li>
          <li>Choose which <strong>tools</strong> and <strong>skills</strong> to include</li>
          <li>Write a <strong>prompt template</strong> — use <code>{'{{variable}}'}</code> syntax for input variables</li>
          <li>Optionally set a <strong>schedule</strong> (cron expression) for automatic execution</li>
          <li>Click <strong>Create</strong></li>
        </ol>
        <h4>Running a Workflow</h4>
        <ul>
          <li><strong>Execute</strong> — Run the workflow immediately with variable inputs</li>
          <li><strong>Stream</strong> — Run and watch the output in real time</li>
          <li><strong>Schedule</strong> — If a cron is set, the workflow runs automatically at the specified times</li>
        </ul>
        <h4>Execution Feedback Loop</h4>
        <p>
          After each workflow run, a <strong>lesson</strong> is extracted from the output or error. Lessons
          are categorized as strategy (what worked), recovery (how to avoid failures), or optimization
          (efficiency tips). They're injected into the agent's archival memory before subsequent runs,
          so the agent learns from its own history without model fine-tuning. Max 3 lessons per workflow;
          lowest-utility lessons are replaced when the cap is reached. Lessons scoring below -3 are auto-deleted.
        </p>
      </>
    ),
  },
  {
    id: 'observability',
    title: 'Observability',
    icon: '🔍',
    content: (
      <>
        <p>
          The Observability page (admin only) provides full-stack visibility into agent execution,
          security events, and tool calls.
        </p>
        <h4>Tabs</h4>
        <ul>
          <li><strong>Overview</strong> — High-level stats and recent activity</li>
          <li><strong>Runs</strong> — Workflow and chat execution history with timing and status</li>
          <li><strong>Tool Calls</strong> — Detailed record of every tool the agent called, including arguments, duration, and success/failure</li>
          <li><strong>Security</strong> — Real-time feed of security events: tool denials, policy violations, canary token detections, and approval requests. Filter by event type and time range.</li>
        </ul>
        <h4>Security Events</h4>
        <p>
          Security events come from the Letta Local fork's enforcement layer. When a tool call is denied
          by policy, a canary token is detected in tool arguments, or a policy violation occurs, it's
          logged to the append-only <code>security_events</code> table and surfaced here. Events are also
          visible in the Logs viewer (Settings → Logs) with severity levels: tool_denied and
          policy_violation map to ERROR, approval requests to WARNING, everything else to INFO.
        </p>
      </>
    ),
  },
  {
    id: 'settings',
    title: 'Settings',
    icon: '⚙',
    content: (
      <>
        <p>
          The Settings page is available to admin users and provides system-level configuration
          across six sections.
        </p>
        <h4>Packages</h4>
        <p>
          Manage Python packages available to agent tools. Install packages from PyPI or remove
          ones that are no longer needed. Packages are installed to a shared volume accessible
          by the Letta agent container.
        </p>
        <h4>Credentials</h4>
        <p>
          Store API keys and secrets securely. Credentials are encrypted at rest with Fernet
          symmetric encryption and delivered to agents via Letta secrets at runtime — scoped per
          user, never globally. Supported providers include Splunk, CrowdStrike, SentinelOne,
          Elastic, and custom token-based auth.
        </p>
        <h4>Agent</h4>
        <p>
          Configure the agent runtime — toggle <strong>Agent Tool Creation</strong> to let agents
          propose new tools, fetch documentation, and read GitHub repositories at runtime. When
          enabled, the allowed documentation domains are shown for reference. Manage agent memory
          and view system prompts.
        </p>
        <h4>Logs</h4>
        <p>
          View system logs from the backend, Letta, and other services. Filter by service or
          severity. Search across log messages. Enable auto-refresh to see new entries as they
          arrive. Security events are surfaced with appropriate severity levels. Use the
          <strong> Export CSV</strong> button to download all matching log entries as a CSV file
          (admin only, applies current filters).
        </p>
        <h4>Backup</h4>
        <p>
          Migrate tools, skills, and workflows between Delta instances. Export produces a JSON
          file with all user-owned resources; import recreates them on the target instance,
          resolving tool name references to the target's tool IDs. Name collisions are skipped.
          Import file size limited to 10MB.
        </p>
        <h4>Infrastructure</h4>
        <p>
          View the health status of core services: PostgreSQL, Letta Agent Server, Ollama, and
          the Eval Service. Each service shows a status indicator (healthy, unhealthy, or
          unreachable) with error details when available. The Eval Service is optional and
          shown as unreachable when not running.
        </p>
      </>
    ),
  },
  {
    id: 'faq',
    title: 'FAQ',
    icon: '❓',
    content: (
      <>
        <h4>How do I ask my agent a general question without running a skill?</h4>
        <p>
          Uncheck the skill checkbox in the Config panel before sending your message. When a skill is
          selected, the agent receives skill instructions with the message. The agent is instructed to
          respond directly to general questions even when a skill is selected, but for cleanest results,
          deselect the skill first.
        </p>
        <h4>My agent stopped mid-skill. What happened?</h4>
        <p>
          The agent may have forgotten to signal for a follow-up step after a tool call — this is a known
          limitation of smaller local models. Send a follow-up message like "continue" to resume. Make
          sure the skill checkbox stays selected — if it gets deselected, the skill context is lost and
          the agent won't have the skill instructions for the next message.
        </p>
        <h4>Why does my agent have file_read / file_list / file_write / grep_files?</h4>
        <p>
          These four file tools are auto-attached to every agent at creation time. They let the agent
          read, write, and search files in its own per-agent workspace. Tools that produce large output
          write to a staging directory first, then the runtime promotes validated files to the persistent
          workspace.
        </p>
        <h4>Do I need to configure .env?</h4>
        <p>
          No. Secrets (JWT, encryption key, service token) are auto-generated on first run and persisted
          to a Docker volume. The <code>.env</code> file is for optional overrides only — see
          <code>.env.example</code> for available settings.
        </p>
        <h4>How do I update Delta?</h4>
        <p>
          If using pre-built images: <code>docker compose pull &amp;&amp; docker compose up -d</code>.
          If building from source: <code>docker compose up -d --build</code> to pick up code changes.
          Note: <code>docker compose up -d</code> without <code>--build</code> reuses the existing image
          and will not pick up source code changes.
        </p>
        <h4>Where is my data stored?</h4>
        <p>
          Docker volumes. <code>docker compose down</code> preserves all data. <code>docker compose down -v</code>
          destroys all data permanently (databases, agent data, credentials, settings).
        </p>
        <h4>Ollama isn't running / my agent can't respond</h4>
        <p>
          Start Ollama on the host machine (<code>ollama serve</code> or launch the Ollama desktop app).
          Delta shows an amber banner on the Chat and Agents pages when Ollama is unreachable. Make sure
          you have at least one model pulled (e.g., <code>ollama pull gemma4:latest</code>).
        </p>
      </>
    ),
  },
]

export default function Help() {
  const navigate = useNavigate()
  const location = useLocation()
  const [activeSection, setActiveSection] = useState('getting-started')
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const hash = location.hash.replace('#', '')
    if (hash && sections.some(s => s.id === hash)) {
      setActiveSection(hash)
    }
  }, [location.hash])

  // Scroll to section when activeSection changes
  useEffect(() => {
    const el = document.getElementById(`help-section-${activeSection}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [activeSection])

  const handleTocClick = (id: string) => {
    setActiveSection(id)
    navigate(`/help#${id}`, { replace: true })
  }

  // Track scroll position to update active TOC item
  useEffect(() => {
    const container = contentRef.current
    if (!container) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const id = entry.target.id.replace('help-section-', '')
            setActiveSection(id)
          }
        }
      },
      { rootMargin: '-80px 0px -60% 0px', threshold: 0 }
    )

    sections.forEach((s) => {
      const el = document.getElementById(`help-section-${s.id}`)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [])

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="page-header animate-entry">
        <h1 className="page-title">
          <span className="accent">?</span> Help
        </h1>
        <p className="page-subtitle">
          App guide and feature documentation — <span className="math">δ</span>(help) → guidance
        </p>
      </div>

      {/* Two-column layout */}
      <div className="help-layout">
        {/* Table of Contents */}
        <nav className="help-toc">
          {sections.map((section) => (
            <button
              key={section.id}
              className={`help-toc-link ${activeSection === section.id ? 'help-toc-active' : ''}`}
              onClick={() => handleTocClick(section.id)}
            >
              <span className="help-toc-icon">{section.icon}</span>
              {section.title}
            </button>
          ))}
        </nav>
        {/* Content */}
        <div className="help-content" ref={contentRef}>
          {sections.map((section) => (
            <section
              key={section.id}
              id={`help-section-${section.id}`}
              className="help-section"
            >
              <h2 className="help-section-title">
                <span className="accent">{section.icon}</span> {section.title}
              </h2>
              <div className="help-section-body">
                {section.content}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}
