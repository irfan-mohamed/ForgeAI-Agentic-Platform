// ── ForgeAI TypeScript Domain Types ──────────────────────────────────────────

export type UserStatus = 'active' | 'pending' | 'suspended';

export interface User {
  id: number;
  name: string;
  email: string;
  status: UserStatus;
  created_at: string;
  updated_at: string;
}

export type MemberRole =
  | 'company_admin'
  | 'hr_admin'
  | 'it_admin'
  | 'manager'
  | 'employee';

export type MemberStatus = 'active' | 'deactivated' | 'pending_invite';

export interface Membership {
  id: number;
  user_id: number;
  organization_id: number;
  role: MemberRole;
  status: MemberStatus;
  joined_at: string;
  user?: User;
}

export type OrgStatus = 'active' | 'suspended' | 'inactive';

export interface Organization {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  status: OrgStatus;
  created_at: string;
  updated_at: string;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// ── API error ─────────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string | { msg: string; type: string }[];
}

// ── Role display helpers ──────────────────────────────────────────────────────

export const ROLE_LABELS: Record<MemberRole, string> = {
  company_admin: 'Company Admin',
  hr_admin: 'HR Admin',
  it_admin: 'IT Admin',
  manager: 'Engineering Manager',
  employee: 'Software Engineer',
};

export const ROLE_COLORS: Record<MemberRole, string> = {
  company_admin: 'bg-forge-600/20 text-forge-300 border border-forge-500/30',
  hr_admin:      'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
  it_admin:      'bg-blue-500/20 text-blue-300 border border-blue-500/30',
  manager:       'bg-amber-500/20 text-amber-300 border border-amber-500/30',
  employee:      'bg-surface-700/60 text-surface-300 border border-white/10',
};

// ── Repository Service Types ──────────────────────────────────────────────────

export type RepositoryStatus =
  | 'connecting'
  | 'syncing'
  | 'indexing'
  | 'ready'
  | 'failed'
  | 'access_revoked'
  | 'disconnected';

export interface Repository {
  id: number;
  organization_id: number;
  github_repository_id: string;
  name: string;
  full_name: string;
  owner: string;
  description: string | null;
  visibility: 'public' | 'private';
  default_branch: string;
  status: RepositoryStatus;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface GitHubAccountInfo {
  login: string;
  account_type: string;
}

export interface GitHubConnectionStatus {
  connected: boolean;
  account: GitHubAccountInfo | null;
}

export interface GitHubAvailableRepo {
  github_repository_id: string;
  name: string;
  full_name: string;
  owner: string;
  visibility: 'public' | 'private';
  default_branch: string;
  description: string | null;
}

export interface SyncProgress {
  files_discovered: number;
  files_processed: number;
  files_failed: number;
}

export interface RepositorySyncStatus {
  id: number;
  repository_id: number;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  trigger: 'initial' | 'manual' | 'webhook_push';
  commit_sha: string | null;
  started_at: string | null;
  completed_at: string | null;
  progress: SyncProgress;
  error_message: string | null;
  created_at: string;
}

export const REPO_STATUS_LABELS: Record<RepositoryStatus, string> = {
  connecting:     'Connecting',
  syncing:        'Syncing',
  indexing:       'Indexing',
  ready:          'Ready',
  failed:         'Failed',
  access_revoked: 'Access Revoked',
  disconnected:   'Disconnected',
};

export const REPO_STATUS_COLORS: Record<RepositoryStatus, string> = {
  connecting:     'bg-amber-500/20 text-amber-300 border border-amber-500/30',
  syncing:        'bg-blue-500/20 text-blue-300 border border-blue-500/30',
  indexing:       'bg-purple-500/20 text-purple-300 border border-purple-500/30',
  ready:          'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
  failed:         'bg-red-500/20 text-red-300 border border-red-500/30',
  access_revoked: 'bg-orange-500/20 text-orange-300 border border-orange-500/30',
  disconnected:   'bg-surface-700/60 text-surface-400 border border-white/10',
};

// ── Pull Requests ─────────────────────────────────────────────────────────────

export interface PullRequestSummary {
  number: number;
  title: string;
  state: 'open' | 'closed' | 'merged';
  draft: boolean;
  author: string | null;
  source_branch: string | null;
  target_branch: string | null;
  head_sha: string | null;
  html_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface PullRequestFile {
  filename: string;
  status: 'added' | 'removed' | 'modified' | 'renamed';
  additions: number;
  deletions: number;
  patch: string | null;
}

export interface PullRequestDetail extends PullRequestSummary {
  body: string | null;
  additions: number;
  deletions: number;
  changed_files: number;
  files: PullRequestFile[];
  files_truncated: boolean;
}

export interface PullRequestListResponse {
  pull_requests: PullRequestSummary[];
  page: number;
  limit: number;
}

// ── AI Service: Conversations & Messages ──────────────────────────────────────

export type MessageRole = 'user' | 'assistant';

export interface ConversationMessage {
  id: string;
  role: MessageRole;
  content: string;
  created_at: string;
  token_count?: number;
  streaming?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  repository_id: string | null;
  repository_full_name?: string | null;
  updated_at: string;
  created_at: string;
  messages?: ConversationMessage[];
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
}

export interface CreateConversationPayload {
  repository_id: string;
  title: string;
}

export interface SendMessageResponse {
  message_id: string;
  agent_run_id: string;
  status: string;
  content: string;
}

export interface TestAssistanceRequest {
  file_path?: string;
  pull_number?: number;
  instructions?: string;
}

// ── AI Service: Code Review ───────────────────────────────────────────────────

export interface SeverityCounts {
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
}

export interface ReviewFinding {
  id: string;
  category: 'BUG' | 'SECURITY' | 'ARCHITECTURE' | 'TESTING' | 'MAINTAINABILITY' | string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';
  title: string;
  description: string;
  file_path: string | null;
  line_start: number | null;
  line_end: number | null;
  recommendation: string | null;
}

export interface CodeReviewSummary {
  id: string;
  repository_id: number;
  pull_number: number;
  pull_title: string;
  pull_url: string | null;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  assessment: string | null;
  overall_score: number | null;
  summary: string | null;
  head_sha: string | null;
  files_reviewed: number;
  files_omitted: number;
  severity_counts: SeverityCounts;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface CodeReviewDetail extends CodeReviewSummary {
  findings: ReviewFinding[];
}

export interface CodeReviewListResponse {
  reviews: CodeReviewSummary[];
  total: number;
}

export interface StartReviewRequest {
  repository_id: number;
  pull_number: number;
}

// ── AI Service: Feature Plans (Phase 3 LangGraph) ──────────────────────────────

export interface AffectedFile {
  file_path: string;
  reason: string;
  change_type: 'create' | 'modify' | 'delete';
}

export interface PlanTask {
  id: string;
  title: string;
  description: string;
  file_path: string;
  estimated_complexity: 'low' | 'medium' | 'high';
  dependencies?: string[];
  unit_tests_needed?: string[];
}

export interface PlanData {
  overview?: string;
  architecture_notes?: string;
  affected_files?: AffectedFile[];
  tasks?: PlanTask[];
  testing_strategy?: string;
  risks_and_mitigations?: string[];
}

export interface ApprovalOut {
  id: string;
  action: 'approved' | 'rejected' | 'changes_requested';
  comment: string | null;
  created_at: string;
}

export interface PlanOut {
  id: string;
  organization_id: number;
  repository_id: number;
  conversation_id: string | null;
  feature_request: string;
  plan_data: PlanData | null;
  status: 'awaiting_approval' | 'approved' | 'rejected' | 'changes_requested' | 'failed';
  version: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  approvals: ApprovalOut[];
}

export interface CreatePlanResponse {
  plan_id: string | null;
  status: string;
  plan_data: PlanData | null;
  error_message: string | null;
  message: string;
}

export interface RequestChangesRequest {
  feedback: string;
  comment?: string;
}
