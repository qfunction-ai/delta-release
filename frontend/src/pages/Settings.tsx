import { useState } from 'react'
import PackagesSection from '../components/PackagesSection'
import CredentialsSection from '../components/CredentialsSection'
import LogsSection from '../components/LogsSection'
import AgentSection from '../components/AgentSection'
import ExportImportSection from '../components/ExportImportSection'
import InfrastructureSection from '../components/InfrastructureSection'

type Section = 'packages' | 'credentials' | 'agent' | 'logs' | 'export-import' | 'infrastructure'

export default function Settings() {
  const [activeSection, setActiveSection] = useState<Section>('packages')

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="page-header animate-entry">
        <h1 className="page-title-mockup" data-symbol="⚙">SETTINGS</h1>
        <p className="page-subtitle-mockup">configure(Δ) → optimize(runtime)</p>
      </div>

      {/* Section Tabs */}
      <div className="pill-tabs mb-8">
        <button
          className={`pill-tab ${activeSection === 'packages' ? 'pill-tab-active' : ''}`}
          onClick={() => setActiveSection('packages')}
        >
          <span className="flex-center-gap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
              <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
              <line x1="12" y1="22.08" x2="12" y2="12" />
            </svg>
            Packages
          </span>
        </button>
        <button
          className={`pill-tab ${activeSection === 'credentials' ? 'pill-tab-active' : ''}`}
          onClick={() => setActiveSection('credentials')}
        >
          <span className="flex-center-gap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            Credentials
          </span>
        </button>
        <button
          className={`pill-tab ${activeSection === 'agent' ? 'pill-tab-active' : ''}`}
          onClick={() => setActiveSection('agent')}
        >
          <span className="flex-center-gap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 8V4H8" />
              <rect x="4" y="8" width="16" height="12" rx="2" />
              <circle cx="12" cy="14" r="2" />
            </svg>
            Agent
          </span>
        </button>
        <button
          className={`pill-tab ${activeSection === 'logs' ? 'pill-tab-active' : ''}`}
          onClick={() => setActiveSection('logs')}
        >
          <span className="flex-center-gap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
            Logs
          </span>
        </button>
        <button
          className={`pill-tab ${activeSection === 'export-import' ? 'pill-tab-active' : ''}`}
          onClick={() => setActiveSection('export-import')}
        >
          <span className="flex-center-gap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <ellipse cx="12" cy="5" rx="9" ry="3" />
              <path d="M3 5v14a9 3 0 0 0 18 0V5" />
              <path d="M3 12a9 3 0 0 0 18 0" />
            </svg>
            Backup
          </span>
        </button>
        <button
          className={`pill-tab ${activeSection === 'infrastructure' ? 'pill-tab-active' : ''}`}
          onClick={() => setActiveSection('infrastructure')}
        >
          <span className="flex-center-gap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
              <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
              <line x1="6" y1="6" x2="6.01" y2="6" />
              <line x1="6" y1="18" x2="6.01" y2="18" />
            </svg>
            Infrastructure
          </span>
        </button>
      </div>

      {/* Section Content */}
      {activeSection === 'packages' && <PackagesSection />}
      {activeSection === 'credentials' && <CredentialsSection />}
      {activeSection === 'agent' && <AgentSection />}
      {activeSection === 'logs' && <LogsSection />}
      {activeSection === 'export-import' && <ExportImportSection />}
      {activeSection === 'infrastructure' && <InfrastructureSection />}
    </div>
  )
}
