/**
 * MembersPage — organization team directory, member invitations, and role management.
 */
import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PageLayout, PageHeader } from '@/components/layout/PageLayout';
import { organizationsApi } from '@/api/organizations';
import { repositoryApi } from '@/api/repository';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { RoleBadge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import type { Membership, Organization, GitHubConnectionStatus, MemberRole } from '@/types';

export function MembersPage() {
  const { orgId: orgIdStr } = useParams<{ orgId: string }>();
  const navigate = useNavigate();
  const orgId = Number(orgIdStr);

  const [org, setOrg]                   = useState<Organization | null>(null);
  const [members, setMembers]           = useState<Membership[]>([]);
  const [githubStatus, setGithubStatus] = useState<GitHubConnectionStatus | null>(null);
  const [loading, setLoading]           = useState(true);

  // Invite modal state
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail]         = useState('');
  const [inviting, setInviting]               = useState(false);
  const [inviteError, setInviteError]         = useState('');

  // Role edit state
  const [editingUserId, setEditingUserId]     = useState<number | null>(null);
  const [updatingRole, setUpdatingRole]       = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [orgRes, memberRes, githubRes] = await Promise.all([
        organizationsApi.get(orgId),
        organizationsApi.listMembers(orgId),
        repositoryApi.getGitHubStatus(orgId),
      ]);
      setOrg(orgRes.data);
      setMembers(memberRes.data);
      setGithubStatus(githubRes.data);
    } catch {
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  }, [orgId, navigate]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    setInviteError('');
    try {
      await organizationsApi.addMember(orgId, inviteEmail.trim());
      setShowInviteModal(false);
      setInviteEmail('');
      loadData();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setInviteError(typeof msg === 'string' ? msg : 'Failed to invite member. Ensure the user is registered.');
    } finally {
      setInviting(false);
    }
  };

  const handleRoleChange = async (userId: number, newRole: MemberRole) => {
    setUpdatingRole(true);
    try {
      await organizationsApi.updateRole(orgId, userId, newRole);
      setMembers(prev =>
        prev.map(m => m.user_id === userId ? { ...m, role: newRole } : m)
      );
      setEditingUserId(null);
    } catch {
      alert('Failed to update member role. Only Company Admins can modify roles.');
    } finally {
      setUpdatingRole(false);
    }
  };

  if (loading) {
    return (
      <PageLayout>
        <div className="flex justify-center py-20"><Spinner size="lg" /></div>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <PageHeader
        title="Team & Access Control"
        subtitle={`Workspace: ${org?.name} · Manage engineering team members, role assignments, and tenant settings.`}
        action={
          <Button
            variant="primary"
            size="md"
            onClick={() => setShowInviteModal(true)}
            leftIcon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
              </svg>
            }
          >
            Invite Member
          </Button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Members Directory */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <div className="flex items-center justify-between pb-4 border-b border-white/8 mb-4">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  Organization Members ({members.length})
                </h3>
                <p className="text-xs text-surface-400">Team members with repository & AI workspace access</p>
              </div>
            </div>

            <div className="divide-y divide-white/5">
              {members.map((member) => {
                const isEditing = editingUserId === member.user_id;

                return (
                  <div key={member.id} className="py-3.5 flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3.5 min-w-0">
                      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-forge-500/20 to-purple-600/20 border border-forge-500/30 flex items-center justify-center text-forge-300 font-bold text-xs flex-shrink-0">
                        {member.user?.name?.charAt(0).toUpperCase() || 'U'}
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-white truncate">{member.user?.name || 'Engineer'}</p>
                        <p className="text-[11px] text-surface-400 font-mono truncate">{member.user?.email}</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 flex-shrink-0">
                      {isEditing ? (
                        <div className="flex items-center gap-2">
                          <select
                            defaultValue={member.role}
                            onChange={(e) => handleRoleChange(member.user_id, e.target.value as MemberRole)}
                            disabled={updatingRole}
                            className="bg-surface-850 border border-white/10 rounded-lg px-2 py-1 text-xs text-white focus:outline-none"
                          >
                            <option value="company_admin">Company Admin</option>
                            <option value="manager">Engineering Manager</option>
                            <option value="employee">Software Engineer</option>
                            <option value="it_admin">IT Admin</option>
                          </select>
                          <button
                            onClick={() => setEditingUserId(null)}
                            className="text-xs text-surface-500 hover:text-white"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <RoleBadge role={member.role} />
                          <button
                            onClick={() => setEditingUserId(member.user_id)}
                            title="Edit Role"
                            className="text-surface-500 hover:text-white p-1 transition-colors"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                            </svg>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>

        {/* Workspace Settings / Integration Summary */}
        <div className="space-y-4">
          <Card>
            <h3 className="text-sm font-bold text-white mb-4 uppercase tracking-wider">Workspace Summary</h3>
            <div className="space-y-3 text-xs">
              <div className="flex justify-between py-2 border-b border-white/5">
                <span className="text-surface-400">Organization Name</span>
                <span className="font-semibold text-white">{org?.name}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-white/5">
                <span className="text-surface-400">API Slug</span>
                <span className="font-mono text-forge-300">/{org?.slug}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-white/5">
                <span className="text-surface-400">Status</span>
                <span className="text-emerald-400 font-mono uppercase">{org?.status}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-white/5">
                <span className="text-surface-400">GitHub Connection</span>
                <span className={`font-mono ${githubStatus?.connected ? 'text-emerald-400' : 'text-surface-500'}`}>
                  {githubStatus?.connected ? `Connected (${githubStatus.account?.login})` : 'Not Connected'}
                </span>
              </div>
            </div>

            <div className="mt-5 pt-4 border-t border-white/6">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigate(`/organizations/${orgId}/repositories`)}
                className="w-full"
              >
                Manage GitHub Repositories →
              </Button>
            </div>
          </Card>
        </div>
      </div>

      {/* Invite Member Modal */}
      {showInviteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md glass-card p-6 border border-white/10 shadow-2xl animate-slide-up space-y-4">
            <h3 className="text-sm font-bold text-white">Invite Team Member</h3>
            <p className="text-xs text-surface-400">
              Enter the registered email of the team member to add them to this organization workspace.
            </p>
            <div>
              <label className="block text-xs font-medium text-surface-300 mb-1.5">
                Email Address <span className="text-red-400">*</span>
              </label>
              <input
                type="email"
                placeholder="colleague@company.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleInvite()}
                className="input-base text-xs"
                autoFocus
              />
            </div>

            {inviteError && (
              <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 p-2.5 rounded-xl">
                {inviteError}
              </p>
            )}

            <div className="flex gap-2 justify-end pt-2">
              <Button variant="secondary" size="sm" onClick={() => setShowInviteModal(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleInvite}
                disabled={!inviteEmail.trim() || inviting}
                isLoading={inviting}
              >
                Send Invite
              </Button>
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  );
}
