// ── Domain types aligned to FlowForge PRD §23 ─────────────────────────────

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
  manager: 'Manager',
  employee: 'Employee',
};

export const ROLE_COLORS: Record<MemberRole, string> = {
  company_admin: 'bg-forge-600/20 text-forge-300',
  hr_admin:      'bg-emerald-500/20 text-emerald-300',
  it_admin:      'bg-blue-500/20 text-blue-300',
  manager:       'bg-amber-500/20 text-amber-300',
  employee:      'bg-surface-700/60 text-surface-300',
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
  connecting:     'bg-amber-100 text-amber-700',
  syncing:        'bg-blue-100 text-blue-700',
  indexing:       'bg-purple-100 text-purple-700',
  ready:          'bg-emerald-100 text-emerald-700',
  failed:         'bg-red-100 text-red-700',
  access_revoked: 'bg-orange-100 text-orange-700',
  disconnected:   'bg-gray-100 text-gray-500',
};

