export interface Agent {
  id: string
  letta_agent_id: string
  name: string
  model: string
  embedding: string
  created_at: string
}

export interface Tool {
  id: string
  name: string
  description: string | null
  source: string
  tags: string[] | null
  pip_requirements: string[] | null
  created_at: string
  updated_at: string
}

export interface ToolDetail extends Tool {
  source_code: string
  json_schema: Record<string, unknown> | string
}

export interface Skill {
  id: string
  name: string
  description: string | null
  source: string
  tool_ids: string[]
  file_path: string
  created_at: string
  updated_at: string
}

export interface SkillFile {
  id: string
  skill_id: string
  path: string
  mime_type: string
  size: number
}

export interface SkillContent {
  id: string
  name: string
  description: string | null
  content: string
  files: SkillFile[]
  tool_ids: string[]
}

export interface Workflow {
  id: string
  name: string
  agent_id: string
  description: string | null
  prompt_template: string
  tool_ids: string[] | null
  skill_ids: string[] | null
  schedule_cron: string | null
  default_variables: Record<string, string> | null
  include_reasoning: boolean
  created_at: string
}

export interface Run {
  id: string
  status: string
  input_variables: Record<string, string> | null
  output: string | null
  reasoning_output: string | null
  error_message: string | null
  steps_count: number
  started_at: string | null
  completed_at: string | null
  created_at: string
}

export interface WorkflowDetail extends Workflow {
  runs: Run[]
}

export interface Lesson {
  id: string
  workflow_id: string
  run_id: string | null
  category: string
  content: string
  utility_score: number
  times_used: number
  created_at: string
}

export interface Credential {
  id: string
  key: string
  name: string
  provider: string
  url: string | null
  has_secondary_key: boolean
  created_at: string
  updated_at: string
}

export interface ToolProposal {
  id: string
  name: string
  description: string | null
  source_code: string
  json_schema: Record<string, unknown>
  tags: string[] | null
  pip_requirements: string[] | null
  proposed_by: string
  dry_run_output: string | null
  dry_run_error: string | null
  created_at: string
}

// Policy types — mirror the fork's ToolCallPolicyPatchRequest / response schemas

export interface PolicyCondition {
  field: string
  operator: string
  value: unknown
}

export interface PolicyRule {
  name: string
  condition: PolicyCondition
  action: string
  priority: number
  message: string | null
  pattern: string | null
}

export interface PolicyDefaults {
  action: string
  max_tool_calls: number | null
  max_tokens: number | null
  timeout_seconds: number | null
}

export interface ToolCallPolicy {
  agent_id: string
  denied_tools: string[]
  approval_required_tools: string[]
  rules: PolicyRule[]
  max_calls_per_tool: Record<string, number>
  defaults: PolicyDefaults | null
}

export interface PolicyDecision {
  allowed: boolean
  action: string
  matched_rule: string | null
  reason: string
}

export interface Model {
  id: string
  name: string
  provider: string
}

export interface EmbeddingModel {
  id: string
  name: string
  provider: string
  dimensions: number | null
}

export interface AgentInfo {
  id: string
  name: string
  model: string
  embedding: string
  created_at: string
  workflows_count: number
  has_schedule: boolean
  last_activity: string
}

export interface Stats {
  agents: number
  tools: number
  skills: number
  workflows: number
  credentials: number
}

export interface DashboardData {
  agents: AgentInfo[]
  stats: Stats
}

export interface ObservabilityRun {
  id: string
  status: string
  agent_id: string
  created_at: string
  completed_at: string | null
  ttft_ns: number | null
  total_duration_ns: number | null
  stop_reason: string | null
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  timestamp?: string
  tokens?: number
  duration?: number
  toolCalls?: { name: string; status: string }[]
}

export interface CredentialType {
  id: string
  display_name: string
  fields: string[]
}
