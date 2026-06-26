import { useState, useEffect, useRef, useCallback } from 'react'
import { apiFetch, API_URL, extractApiError } from '../lib/api'
import { useRequireAuth } from '../hooks/useRequireAuth'
import { useConfirmDialog } from '../hooks/useConfirmDialog'
import { useEntityDelete } from '../hooks/useEntityDelete'
import { useGithubImport } from '../hooks/useGithubImport'
import { ERROR_MESSAGES } from '../lib/errors'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { isValidSkillFile } from './skills.utils'
import { Skill, SkillFile, SkillContent as SkillContentType, Tool } from '../lib/types'

export default function Skills() {
  useRequireAuth()
  const [skills, setSkills] = useState<Skill[]>([])
  const [tools, setTools] = useState<Tool[]>([])
  const [loading, setLoading] = useState(true)

  // Upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)

  // GitHub import
  const { githubUrl, setGithubUrl, fetchingGithub, handleGithub } = useGithubImport({
    endpoint: '/api/skills/github',
    errorLabel: 'skill',
    onSuccess: (data) => {
      const result = data as { skill?: Skill; tool?: Tool; tool_status?: string }
      const skill = result.skill || data as Skill
      setSkills(prev => [...prev, skill])
      if (result.tool) {
        setTools(prev => [...prev, result.tool!])
      }
      if (result.tool_status === 'linked_existing') {
        setSuccessMsg('Skill created. Tool linked (already existed).')
      } else if (result.tool_status === 'created') {
        setSuccessMsg('Skill and tool created.')
      } else {
        setSuccessMsg('Skill created.')
      }
    },
    onError: (msg) => setError(msg),
  })

  // Active tab
  const [activeTab, setActiveTab] = useState<'upload' | 'github'>('github')

  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')
  const { confirm, dialog } = useConfirmDialog()

  const handleDelete = useEntityDelete(
    '/api/skills',
    (id) => setSkills(prev => prev.filter(s => s.id !== id)),
    confirm,
    'skill',
    (id) => { if (viewingSkill?.id === id) setViewingSkill(null) },
    (msg) => setError(msg),
  )
  const [fetchError, setFetchError] = useState('')

  // View/edit state
  const [viewingSkill, setViewingSkill] = useState<SkillContentType | null>(null)
  const [editing, setEditing] = useState(false)

  // Drag state
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const fetchSkills = useCallback(async () => {
    try {
      const [skillsRes, toolsRes] = await Promise.all([
        apiFetch('/api/skills/'),
        apiFetch('/api/tools/'),
      ])
      if (skillsRes.ok) {
        setSkills(await skillsRes.json())
      } else {
        setFetchError(ERROR_MESSAGES.LOAD_SKILLS)
      }
      if (toolsRes.ok) {
        setTools(await toolsRes.json())
      }
    } catch {
      setFetchError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSkills()
  }, [fetchSkills])

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!uploadFile) return
    setError(''); setSuccessMsg('')
    setUploading(true)

    try {
      const formData = new FormData()
      formData.append('file', uploadFile)

      // apiFetch detects FormData and omits Content-Type so the browser
      // sets the correct multipart/form-data boundary automatically.
      const response = await apiFetch('/api/skills/upload', {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()

      if (!response.ok) {
        setError(data.detail || 'Failed to upload skill')
        return
      }

      setSkills(prev => [...prev, data])
      setUploadFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (_err) {
      setError(ERROR_MESSAGES.CONNECTION)
    } finally {
      setUploading(false)
    }
  }

  const handleView = async (skillId: string) => {
    setError(''); setSuccessMsg('')
    try {
      const response = await apiFetch(`/api/skills/${skillId}/content`)
      if (response.ok) {
        setViewingSkill(await response.json())
      } else {
        setError(await extractApiError(response, 'Failed to load skill content'))
        setViewingSkill(null)
      }
    } catch {
      setError(ERROR_MESSAGES.CONNECTION)
      setViewingSkill(null)
    }
  }

  const handleUpdate = async () => {
    if (!viewingSkill) return
    setError(''); setSuccessMsg('')

    try {
      const response = await apiFetch(`/api/skills/${viewingSkill.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          content: viewingSkill.content,
          name: viewingSkill.name,
          description: viewingSkill.description,
          tool_ids: viewingSkill.tool_ids,
        }),
      })

      if (!response.ok) {
        setError(await extractApiError(response, 'Failed to update skill'))
        return
      }

      const updated = await response.json()
      setSkills(prev => prev.map(s => s.id === updated.id ? { ...s, ...updated } : s))
      setEditing(false)
      setViewingSkill(prev => prev ? { ...prev, ...updated } : prev)
    } catch (_err) {
      setError(ERROR_MESSAGES.CONNECTION)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = () => {
    setDragOver(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const files = e.dataTransfer.files
    if (files.length > 0) {
      const file = files[0]
      if (isValidSkillFile(file.name)) {
        setUploadFile(file)
        setError(''); setSuccessMsg('')
      } else {
        setError('Please upload a .zip or .skill file')
      }
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      setUploadFile(files[0])
      setError(''); setSuccessMsg('')
    }
  }

  if (loading) {
    return <LoadingSpinner />
  }

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="page-header animate-entry">
        <h1 className="page-title-mockup" data-symbol="σ">Skills</h1>
        <p className="page-subtitle-mockup">σ(skills) → ∪(capabilities) | attach → execute</p>
      </div>

      {fetchError && <div className="error">{fetchError}</div>}

      <div className="two-column">
        {/* Left column: Add + List */}
        <div>
          {/* Add Skill Card */}
          <div className="card mb-6">
            <h2 className="section-header" data-symbol="+">
              Add Skill
            </h2>

            {/* Pill Tabs */}
            <div className="pill-tabs mb-6">
              <button
                className={`pill-tab ${activeTab === 'github' ? 'pill-tab-active' : ''}`}
                onClick={() => { setActiveTab('github'); setError(''); setSuccessMsg('') }}
              >
                GitHub URL
              </button>
              <button
                className={`pill-tab ${activeTab === 'upload' ? 'pill-tab-active' : ''}`}
                onClick={() => { setActiveTab('upload'); setError(''); setSuccessMsg('') }}
              >
                Upload File
              </button>
            </div>

            {/* Upload Tab */}
            {activeTab === 'upload' && (
              <form onSubmit={handleUpload}>
                {/* Drag-Drop Zone */}
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInputRef.current?.click() } }}
                  role="button"
                  tabIndex={0}
                  className={`skills-drop-zone${dragOver ? ' skills-drop-zone-active' : ''}`}
                >
                  {uploadFile ? (
                    <div>
                      <p className="skills-upload-filename">
                        {uploadFile.name}
                      </p>
                      <p className="text-xs text-tertiary">
                        {(uploadFile.size / 1024).toFixed(1)} KB — click to change
                      </p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-muted skills-drop-hint">
                        Drop a <span className="font-mono text-accent">.zip</span> or{' '}
                        <span className="font-mono text-accent">.skill</span> file here
                      </p>
                      <p className="text-xs text-tertiary">or click to browse</p>
                    </div>
                  )}
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip,.skill"
                  onChange={handleFileSelect}
                  className="skills-file-input-hidden"
                  aria-label="Upload skill file"
                />

                <p className="form-hint mb-4">
                  Must contain a <span className="font-mono">SKILL.md</span> with YAML frontmatter (name + description)
                </p>

                {error && <div className="error mb-4">{error}</div>}
                {successMsg && <div className="success mb-4">{successMsg}</div>}

                <button
                  type="submit"
                  className="btn btn-primary w-full"
                  disabled={uploading || !uploadFile}
                >
                  {uploading ? 'Uploading...' : 'Upload Skill'}
                </button>
              </form>
            )}

            {/* GitHub Tab */}
            {activeTab === 'github' && (
              <form onSubmit={handleGithub}>
                <div className="form-group">
                  <label className="form-label" htmlFor="field-skills-github-url">GitHub Repository URL</label>
                  <input
                    id="field-skills-github-url"
                    type="url"
                    className="input"
                    value={githubUrl}
                    onChange={(e) => setGithubUrl(e.target.value)}
                    placeholder="https://github.com/user/repo/tree/main/skill-dir"
                    required
                    aria-label="GitHub repository URL"
                  />
                  <p className="form-hint">
                    URL to a directory containing a <span className="font-mono">SKILL.md</span> file
                  </p>
                </div>

                {error && <div className="error mb-4">{error}</div>}

                <button
                  type="submit"
                  className="btn btn-primary w-full mt-4"
                  disabled={fetchingGithub || !githubUrl.trim()}
                >
                  {fetchingGithub ? 'Fetching from GitHub...' : 'Fetch Skill'}
                </button>
              </form>
            )}
          </div>

          {/* Skills List */}
          <h2 className="section-header" data-symbol="σ">
            Your Skills
          </h2>

          {skills.length === 0 ? (
            <div className="card">
              <p className="text-muted text-sm">No skills loaded yet. Upload a file or fetch from GitHub to get started.</p>
            </div>
          ) : (
            <div className="skills-grid">
              {skills.map((skill) => (
                <div
                  key={skill.id}
                  className={`card card-interactive${viewingSkill?.id === skill.id ? ' card-selected' : ''}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleView(skill.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleView(skill.id) } }}
                >
                  <div className="flex items-center justify-between">
                    <div className="skills-item-body">
                      <h3 className="skills-item-name">
                        {skill.name}
                      </h3>
                      {skill.description && (
                        <p className="text-sm text-muted skills-item-description">
                          {skill.description}
                        </p>
                      )}
                      <div className="flex items-center gap-4">
                        <span className={`badge ${skill.source === 'upload' ? 'badge-info' : 'badge-success'}`}>
                          {skill.source}
                        </span>
                        <span className="text-xs text-tertiary font-mono">
                          {new Date(skill.updated_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={(e) => { e.stopPropagation(); handleDelete(skill.id, skill.name) }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right column: View/Edit */}
        <div>
          {viewingSkill && (
            <div className="card animate-fade-in">
              <div className="flex items-center justify-between mb-4">
                <div className="skills-detail-body">
                  {editing ? (
                    <div className="form-group skills-edit-form-group">
                      <label className="form-label" htmlFor="field-skills-edit-name">Name</label>
                      <input
                        id="field-skills-edit-name"
                        type="text"
                        className="input"
                        value={viewingSkill.name}
                        onChange={(e) => setViewingSkill(prev => prev ? { ...prev, name: e.target.value } : prev)}
                        aria-label="Skill name"
                      />
                    </div>
                  ) : (
                    <h2 className="skills-detail-title">
                      {viewingSkill.name}
                    </h2>
                  )}
                </div>
                <div className="flex gap-4 skills-detail-actions">
                  {editing ? (
                    <>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={handleUpdate}
                      >
                        Save
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          setEditing(false)
                          fetchSkills().then(() => handleView(viewingSkill.id))
                        }}
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => setEditing(true)}
                    >
                      Edit
                    </button>
                  )}
                </div>
              </div>

              {editing ? (
                <div className="form-group">
                  <label className="form-label" htmlFor="field-skills-edit-description">Description</label>
                  <input
                    id="field-skills-edit-description"
                    type="text"
                    className="input"
                    value={viewingSkill.description || ''}
                    onChange={(e) => setViewingSkill(prev => prev ? { ...prev, description: e.target.value } : prev)}
                    placeholder="Skill description"
                    aria-label="Skill description"
                  />
                </div>
              ) : (
                viewingSkill.description && (
                  <p className="text-sm text-muted mb-4">{viewingSkill.description}</p>
                )
              )}

              {/* Required Tools */}
              {editing && tools.length > 0 && (
                <div className="form-group">
                  <label className="form-label" id="field-skills-required-tools-label">Required Tools</label>
                  <div className="skills-tools-grid" role="group" aria-labelledby="field-skills-required-tools-label">
                    {tools.map(t => (
                      <label key={t.id} className="skills-tool-checkbox" style={{ color: (viewingSkill.tool_ids || []).includes(t.id) ? 'var(--accent)' : 'var(--text-secondary)' }}>
                        <input
                          type="checkbox"
                          checked={(viewingSkill.tool_ids || []).includes(t.id)}
                          onChange={(e) => {
                            const current = viewingSkill.tool_ids || []
                            const updated = e.target.checked
                              ? [...current, t.id]
                              : current.filter((id: string) => id !== t.id)
                            setViewingSkill(prev => prev ? { ...prev, tool_ids: updated } : prev)
                          }}
                          className="skills-tool-checkbox-input"
                          aria-label={t.name}
                        />
                        <span className="font-mono">{t.name}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
              {!editing && viewingSkill.tool_ids && viewingSkill.tool_ids.length > 0 && (
                <div className="skills-required-tools-section">
                  <h3 className="skills-section-heading">
                    Required Tools
                  </h3>
                  <div className="skills-tool-badges">
                    {viewingSkill.tool_ids.map((tid: string) => {
                      const tool = tools.find(t => t.id === tid)
                      return tool ? (
                        <span key={tid} className="font-mono text-xs skills-tool-badge">
                          {tool.name}
                        </span>
                      ) : null
                    })}
                  </div>
                </div>
              )}

              {editing ? (
                <textarea
                  className="input font-mono skills-edit-textarea"
                  value={viewingSkill.content}
                  onChange={(e) => setViewingSkill(prev => prev ? { ...prev, content: e.target.value } : prev)}
                  rows={20}
                  aria-label="Skill content"
                />
              ) : (
                <div className="code-block">
                  {viewingSkill.content}
                </div>
              )}

              {/* Skill Files */}
              {!editing && viewingSkill.files && viewingSkill.files.length > 0 && (
                <div className="skills-files-section">
                  <h3 className="skills-section-heading skills-section-heading-spaced">
                    Files
                  </h3>
                  <div className="skills-files-grid">
                    {viewingSkill.files.map((file: SkillFile) => (
                      <a
                        key={file.id}
                        href={`${API_URL}/api/skills/${viewingSkill.id}/files/${file.id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="skills-file-link"
                      >
                        <span className="font-mono text-sm skills-file-path">
                          {file.path}
                        </span>
                        <span className="text-xs text-tertiary">
                          {file.mime_type} · {file.size > 1024 ? `${(file.size / 1024).toFixed(1)} KB` : `${file.size} B`}
                        </span>
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {error && <div className="error mt-4">{error}</div>}
            </div>
          )}

          {!viewingSkill && (
            <div className="card">
              <div className="empty-state">
                <p className="text-muted text-sm skills-empty-hint">
                  Select a skill to inspect its contents.
                </p>
                <p className="text-xs text-tertiary">
                  Click any skill card on the left to view its source and configuration.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {dialog}
    </div>
  )
}
