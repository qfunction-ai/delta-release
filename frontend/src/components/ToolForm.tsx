export const DEFAULT_SOURCE_CODE = `def search_splunk(query: str, time_range: str = "24h", index: str = "main") -> str:
    """Search Splunk logs for security events.

    Args:
        query: SPL search query
        time_range: Time range to search (e.g. 24h, 7d)
        index: Splunk index to search

    Returns:
        Search results as string
    """
    import os, json, httpx
    creds = json.loads(os.getenv("CREDENTIAL_SPLUNK_API_KEY", "{}"))
    primary_key = creds.get("primary_key", "")
    secondary_key = creds.get("secondary_key")
    url = creds.get("url", "")
    resp = httpx.get(f"{url}/services/search/jobs", params={"query": query}, headers={"Authorization": f"Bearer {primary_key}"}, timeout=30)
    return resp.text[:2000] if resp.status_code == 200 else f"Error: {resp.status_code}"`

interface ToolFormProps {
  activeTab: 'manual' | 'github'
  onTabChange: (tab: 'manual' | 'github') => void
  name: string
  setName: (v: string) => void
  description: string
  setDescription: (v: string) => void
  sourceCode: string
  setSourceCode: (v: string) => void
  tags: string
  setTags: (v: string) => void
  pipReqs: string
  setPipReqs: (v: string) => void
  githubUrl: string
  setGithubUrl: (v: string) => void
  error: string
  creating: boolean
  fetchingGithub: boolean
  onCreate: (e: React.FormEvent) => void
  onGithub: (e: React.FormEvent) => void
}

export default function ToolForm({
  activeTab,
  onTabChange,
  name,
  setName,
  description,
  setDescription,
  sourceCode,
  setSourceCode,
  tags,
  setTags,
  pipReqs,
  setPipReqs,
  githubUrl,
  setGithubUrl,
  error,
  creating,
  fetchingGithub,
  onCreate,
  onGithub,
}: ToolFormProps) {
  return (
    <div className="card">
      <h2 className="section-header" data-symbol="+">Add Tool</h2>

      {/* Pill Tabs */}
      <div className="pill-tabs mb-6">
        <button
          className={`pill-tab ${activeTab === 'github' ? 'pill-tab-active' : ''}`}
          onClick={() => { onTabChange('github') }}
        >
          GitHub URL
        </button>
        <button
          className={`pill-tab ${activeTab === 'manual' ? 'pill-tab-active' : ''}`}
          onClick={() => { onTabChange('manual') }}
        >
          Manual
        </button>
      </div>

      {/* Manual Tab */}
      {activeTab === 'manual' && (
      <form onSubmit={onCreate}>
        <div className="form-group">
          <label className="form-label" htmlFor="field-tools-name">Name (snake_case)</label>
          <input
            id="field-tools-name"
            type="text"
            className="input font-mono"
            aria-label="Name (snake_case)"
            value={name}
            onChange={(e) => setName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
            placeholder="search_splunk"
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="field-tools-description">Description</label>
          <input
            id="field-tools-description"
            type="text"
            className="input"
            aria-label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Search Splunk logs for security events"
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="field-tools-tags">Tags (comma-separated)</label>
          <input
            id="field-tools-tags"
            type="text"
            className="input"
            aria-label="Tags (comma-separated)"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="splunk, search, logs"
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="field-tools-pip-reqs">Pip Requirements (comma-separated)</label>
          <input
            id="field-tools-pip-reqs"
            type="text"
            className="input font-mono"
            aria-label="Pip Requirements (comma-separated)"
            value={pipReqs}
            onChange={(e) => setPipReqs(e.target.value)}
            placeholder="requests, paramiko==2.12.0"
          />
          <p className="form-hint">
            Packages installed in the tool's sandbox environment
          </p>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="field-tools-source-code">Source Code</label>
          <textarea
            id="field-tools-source-code"
            className="input font-mono"
            aria-label="Source Code"
            value={sourceCode}
            onChange={(e) => setSourceCode(e.target.value)}
            rows={12}
            required
            style={{ fontSize: '0.8125rem', lineHeight: '1.6' }}
          />
          <p className="form-hint">
            JSON Schema is auto-generated from the function signature
          </p>
        </div>

        {error && <div className="error">{error}</div>}

        <button
          type="submit"
          className="btn btn-primary mt-4"
          disabled={creating || !name || !sourceCode}
        >
          {creating ? 'Creating...' : 'Create Tool'}
        </button>
      </form>
      )}

      {/* GitHub Tab */}
      {activeTab === 'github' && (
      <form onSubmit={onGithub}>
        <div className="form-group">
          <label className="form-label" htmlFor="field-tools-github-url">GitHub Repository URL</label>
          <input
            id="field-tools-github-url"
            type="url"
            className="input"
            aria-label="GitHub Repository URL"
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
            placeholder="https://github.com/user/repo/tree/main/splunk-tool"
            required
          />
          <p className="form-hint">
            URL to a directory containing a <span className="font-mono">tool.yaml</span> file
          </p>
        </div>

        {error && <div className="error mb-4">{error}</div>}

        <button
          type="submit"
          className="btn btn-primary w-full mt-4"
          disabled={fetchingGithub || !githubUrl.trim()}
        >
          {fetchingGithub ? 'Fetching from GitHub...' : 'Fetch Tool'}
        </button>
      </form>
      )}
    </div>
  )
}
