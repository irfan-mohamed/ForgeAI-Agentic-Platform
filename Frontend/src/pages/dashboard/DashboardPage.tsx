import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { organizationsApi } from '@/api/organizations';
import { PageLayout, PageHeader } from '@/components/layout/PageLayout';
import { Card, StatCard } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { StatusBadge, RoleBadge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import type { Organization, Membership } from '@/types';
import type { AxiosError } from 'axios';

// ── Org card in the list ──────────────────────────────────────────────────────

function OrgCard({
  org,
  membership,
  onSelect,
}: {
  org: Organization;
  membership?: Membership;
  onSelect: (org: Organization) => void;
}) {
  return (
    <button
      onClick={() => onSelect(org)}
      className="glass-card p-5 text-left hover:border-forge-300/60 transition-all duration-200 group w-full"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-forge-100 to-purple-100 border border-forge-200/60 flex items-center justify-center text-forge-600 font-bold text-sm flex-shrink-0 group-hover:scale-105 transition-transform">
          {org.name.charAt(0).toUpperCase()}
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={org.status} />
          {membership && <RoleBadge role={membership.role} />}
        </div>
      </div>
      <h3 className="text-gray-900 font-semibold text-sm group-hover:text-forge-700 transition-colors">{org.name}</h3>
      <p className="text-gray-400 text-xs mt-0.5 font-mono">/{org.slug}</p>
      {org.description && (
        <p className="text-gray-500 text-xs mt-2 line-clamp-2">{org.description}</p>
      )}
    </button>
  );
}

// ── Member list in the selected org panel ─────────────────────────────────────

function MemberRow({ member }: { member: Membership }) {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-gray-100 last:border-0">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-forge-100 to-purple-100 flex items-center justify-center text-forge-600 text-xs font-bold flex-shrink-0">
        {member.user?.name?.charAt(0).toUpperCase() ?? '?'}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 truncate">{member.user?.name ?? '—'}</p>
        <p className="text-xs text-gray-400 truncate">{member.user?.email ?? '—'}</p>
      </div>
      <RoleBadge role={member.role} />
    </div>
  );
}

// ── Main dashboard page ───────────────────────────────────────────────────────

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [orgs, setOrgs]                 = useState<Organization[]>([]);
  const [members, setMembers]           = useState<Membership[]>([]);
  const [selectedOrg, setSelectedOrg]   = useState<Organization | null>(null);
  const [loadingOrgs, setLoadingOrgs]   = useState(true);
  const [loadingMembers, setLoadingMembers] = useState(false);

  // Fetch user's organizations on mount
  useEffect(() => {
    organizationsApi
      .list()
      .then((res) => {
        setOrgs(res.data);
        if (res.data.length === 1) setSelectedOrg(res.data[0]);
      })
      .catch((err: AxiosError) => {
        if (err.response?.status === 401) navigate('/login');
      })
      .finally(() => setLoadingOrgs(false));
  }, [navigate]);

  // Fetch members when selectedOrg changes
  useEffect(() => {
    if (!selectedOrg) return;
    setLoadingMembers(true);
    organizationsApi
      .listMembers(selectedOrg.id)
      .then((res) => setMembers(res.data))
      .finally(() => setLoadingMembers(false));
  }, [selectedOrg]);

  const greeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  };

  return (
    <PageLayout>
      {/* ── Page header ── */}
      <PageHeader
        title={`${greeting()}, ${user?.name?.split(' ')[0]} 👋`}
        subtitle="Here's an overview of your FlowForge workspace."
        action={
          <Button
            variant="primary"
            size="md"
            onClick={() => navigate('/setup')}
            leftIcon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            }
          >
            New Organization
          </Button>
        }
      />

      {/* ── Stats row ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Organizations"
          value={orgs.length}
          icon={
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5" />
            </svg>
          }
        />
        <StatCard
          label="Team members"
          value={selectedOrg ? members.length : '—'}
          color="text-emerald-400"
          icon={
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          }
        />
        <StatCard
          label="Onboarding tasks"
          value="Coming soon"
          color="text-amber-400"
          icon={
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          }
        />
        <StatCard
          label="AI questions answered"
          value="Coming soon"
          color="text-purple-400"
          icon={
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          }
        />
      </div>

      {/* ── Main content grid ── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Org list */}
        <div className="lg:col-span-2">
          <Card>
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-semibold text-gray-900">Your Organizations</h2>
              {orgs.length > 0 && (
                <span className="text-xs text-gray-400">{orgs.length} total</span>
              )}
            </div>

            {loadingOrgs ? (
              <div className="flex justify-center py-8">
                <Spinner />
              </div>
            ) : orgs.length === 0 ? (
              <div className="flex flex-col items-center py-10 gap-3">
                <div className="w-12 h-12 rounded-2xl bg-violet-50 flex items-center justify-center text-forge-400">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                      d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5" />
                  </svg>
                </div>
                <p className="text-gray-500 text-sm text-center">
                  No organizations yet.<br />Create one to get started.
                </p>
                <Button variant="primary" size="sm" onClick={() => navigate('/setup')}>
                  Create organization
                </Button>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {orgs.map((org) => (
                  <OrgCard
                    key={org.id}
                    org={org}
                    onSelect={setSelectedOrg}
                  />
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Selected org detail */}
        <div className="lg:col-span-3">
          {selectedOrg ? (
            <Card>
              <div className="flex items-start justify-between mb-6">
                <div>
                  <h2 className="font-semibold text-gray-900">{selectedOrg.name}</h2>
                  <p className="text-xs text-gray-400 font-mono mt-0.5">/{selectedOrg.slug}</p>
                </div>
                <StatusBadge status={selectedOrg.status} />
              </div>

              {selectedOrg.description && (
                <p className="text-gray-500 text-sm mb-5">{selectedOrg.description}</p>
              )}

              <h3 className="text-sm font-medium text-gray-700 mb-3">
                Members
                {!loadingMembers && (
                  <span className="ml-2 text-gray-400 font-normal">{members.length}</span>
                )}
              </h3>

              {loadingMembers ? (
                <div className="flex justify-center py-6">
                  <Spinner size="sm" />
                </div>
              ) : (
                <div>
                  {members.map((m) => (
                    <MemberRow key={m.id} member={m} />
                  ))}
                </div>
              )}
            </Card>
          ) : (
            <Card>
              <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
                <div className="w-14 h-14 rounded-2xl bg-violet-50 flex items-center justify-center text-forge-400">
                  <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M15 19l-7-7 7-7" />
                  </svg>
                </div>
                <p className="text-gray-500 text-sm">
                  Select an organization to view details
                </p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </PageLayout>
  );
}
