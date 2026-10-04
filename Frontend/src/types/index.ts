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
