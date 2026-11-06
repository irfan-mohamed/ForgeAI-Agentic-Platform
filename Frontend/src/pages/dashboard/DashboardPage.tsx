import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { organizationsApi } from '@/api/organizations';
import { repositoryApi } from '@/api/repository';
import { reviewsApi } from '@/api/reviews';
import { PageLayout, PageHeader } from '@/components/layout/PageLayout';
import { Card, StatCard } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { StatusBadge, RoleBadge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import type { Organization, Membership, Repository, CodeReviewSummary } from '@/types';
import type { AxiosError } from 'axios';

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [orgs, setOrgs]                       = useState<Organization[]>([]);
  const [selectedOrg, setSelectedOrg]         = useState<Organization | null>(null);
  const [members, setMembers]                 = useState<Membership[]>([]);
  const [repos, setRepos]                     = useState<Repository[]>([]);
  const [reviews, setReviews]                 = useState<CodeReviewSummary[]>([]);
  const [loadingOrgs, setLoadingOrgs]         = useState(true);
  const [loadingDetails, setLoadingDetails]   = useState(false);

  // Fetch user's organizations
  useEffect(() => {
    organizationsApi
      .list()
      .then((res) => {
        setOrgs(res.data);
        if (res.data.length > 0) {
          setSelectedOrg(res.data[0]);
        }
      })
      .catch((err: AxiosError) => {
        if (err.response?.status === 401) navigate('/login');
      })
      .finally(() => setLoadingOrgs(false));
  }, [navigate]);

  // Fetch details when selectedOrg changes
  useEffect(() => {
    if (!selectedOrg) return;
    setLoadingDetails(true);

    Promise.all([
      organizationsApi.listMembers(selectedOrg.id),
      repositoryApi.listRepos(selectedOrg.id),
      reviewsApi.listReviews(selectedOrg.id).catch(() => ({ data: { reviews: [], total: 0 } })),
    ])
      .then(([memberRes, repoRes, reviewRes]) => {
        setMembers(memberRes.data);
        setRepos(repoRes.data.repositories);
        setReviews(reviewRes.data.reviews || []);
      })
      .catch(console.error)
      .finally(() => setLoadingDetails(false));
  }, [selectedOrg]);

  const greeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  };

  const readyRepos = repos.filter(r => r.status === 'ready');

  return (
    <PageLayout>
      {/* ── Page Header ── */}
      <PageHeader
        title={`${greeting()}, ${user?.name?.split(' ')[0] || 'Engineer'} ⚡`}
        subtitle="Manage your connected repositories, AI conversations, and automated code reviews."
        action={
          <div className="flex items-center gap-3">
            {selectedOrg && (
              <Button
                variant="secondary"
                size="md"
                onClick={() => navigate(`/organizations/${selectedOrg.id}/ai`)}
                leftIcon={
                  <svg className="w-4 h-4 text-forge-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                }
              >
                Open AI Workspace
              </Button>
            )}
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
              New Workspace
            </Button>
          </div>
        }
      />

      {/* ── Platform Stat Cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Workspaces"
          value={orgs.length}
          icon={
            <svg className="w-4 h-4 text-forge-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5" />
            </svg>
          }
        />
        <StatCard
          label="Connected Repos"
          value={repos.length}
          color="text-emerald-400"
          icon={
            <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          }
        />
        <StatCard
          label="Indexed & Ready"
          value={readyRepos.length}
          color="text-cyan-400"
          icon={
            <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
        <StatCard
          label="PR Code Reviews"
          value={reviews.length}
          color="text-purple-400"
          icon={
            <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          }
        />
      </div>

      {/* ── Main Content Grid ── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left: Organizations List */}
        <div className="lg:col-span-2">
          <Card>
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="font-semibold text-white text-sm">Workspaces</h2>
                <p className="text-surface-400 text-xs">Switch your active tenant</p>
              </div>
              {orgs.length > 0 && (
                <span className="text-xs font-mono text-surface-500">{orgs.length} total</span>
              )}
            </div>

            {loadingOrgs ? (
              <div className="flex justify-center py-10">
                <Spinner />
              </div>
            ) : orgs.length === 0 ? (
              <div className="flex flex-col items-center py-10 gap-3 text-center">
                <div className="w-12 h-12 rounded-2xl bg-surface-800 border border-white/10 flex items-center justify-center text-forge-400">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                      d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5" />
                  </svg>
                </div>
                <p className="text-surface-400 text-xs">
                  No organization workspaces found.<br />Create your first workspace to begin.
                </p>
                <Button variant="primary" size="sm" onClick={() => navigate('/setup')}>
                  Create Workspace
                </Button>
              </div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {orgs.map((org) => {
                  const isSelected = selectedOrg?.id === org.id;
                  return (
                    <div
                      key={org.id}
                      onClick={() => setSelectedOrg(org)}
                      className={`p-4 rounded-xl border cursor-pointer transition-all ${
                        isSelected
                          ? 'bg-forge-600/15 border-forge-500/40 shadow-lg shadow-forge-950/40'
                          : 'bg-surface-800/60 border-white/5 hover:border-white/15 hover:bg-surface-800'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-forge-500/20 to-purple-600/20 border border-forge-500/30 flex items-center justify-center text-forge-300 font-bold text-xs flex-shrink-0">
                            {org.name.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <h3 className="text-white font-semibold text-xs leading-snug">{org.name}</h3>
                            <p className="text-surface-500 text-[11px] font-mono">/{org.slug}</p>
                          </div>
                        </div>
                        <StatusBadge status={org.status} />
                      </div>

                      {/* Quick Links inside selected org card */}
                      <div className="mt-3 pt-3 border-t border-white/5 flex items-center gap-4 text-xs">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/organizations/${org.id}/repositories`);
                          }}
                          className="text-forge-400 hover:text-forge-300 font-medium flex items-center gap-1 transition-colors"
                        >
                          Repos →
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/organizations/${org.id}/ai`);
                          }}
                          className="text-purple-400 hover:text-purple-300 font-medium flex items-center gap-1 transition-colors"
                        >
                          AI Chat →
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/organizations/${org.id}/reviews`);
                          }}
                          className="text-cyan-400 hover:text-cyan-300 font-medium flex items-center gap-1 transition-colors"
                        >
                          Reviews →
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </div>

        {/* Right: Selected Workspace Overview */}
        <div className="lg:col-span-3">
          {selectedOrg ? (
            <Card>
              <div className="flex items-start justify-between pb-5 border-b border-white/8 mb-6">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-bold text-white tracking-tight">{selectedOrg.name}</h2>
                    <StatusBadge status={selectedOrg.status} />
                  </div>
                  <p className="text-xs text-surface-400 font-mono mt-0.5">slug: {selectedOrg.slug}</p>
                  {selectedOrg.description && (
                    <p className="text-xs text-surface-400 mt-2 leading-relaxed">{selectedOrg.description}</p>
                  )}
                </div>

                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate(`/organizations/${selectedOrg.id}/repositories`)}
                >
                  Manage Repos
                </Button>
              </div>

              {/* Repositories in this org */}
              <div className="mb-6">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-semibold text-white uppercase tracking-wider">
                    Connected Repositories ({repos.length})
                  </h3>
                  <button
                    onClick={() => navigate(`/organizations/${selectedOrg.id}/repositories`)}
                    className="text-xs text-forge-400 hover:text-forge-300 font-medium"
                  >
                    View All →
                  </button>
                </div>

                {loadingDetails ? (
                  <div className="flex justify-center py-6"><Spinner size="sm" /></div>
                ) : repos.length === 0 ? (
                  <div className="p-5 rounded-xl bg-surface-900/60 border border-white/5 text-center">
                    <p className="text-xs text-surface-400 mb-3">No repositories connected to this workspace yet.</p>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => navigate(`/organizations/${selectedOrg.id}/repositories`)}
                    >
                      Connect GitHub Repository
                    </Button>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {repos.slice(0, 4).map((r) => (
                      <div
                        key={r.id}
                        onClick={() => navigate(`/organizations/${selectedOrg.id}/ai`)}
                        className="p-3.5 rounded-xl bg-surface-900/80 border border-white/5 hover:border-forge-500/30 transition-all cursor-pointer group"
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <p className="text-xs font-semibold text-white truncate group-hover:text-forge-300 transition-colors">
                            {r.name}
                          </p>
                          <span className={`text-[10px] font-mono uppercase px-1.5 py-0.5 rounded ${
                            r.status === 'ready'
                              ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                              : 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                          }`}>
                            {r.status}
                          </span>
                        </div>
                        <p className="text-[11px] text-surface-500 font-mono truncate">{r.full_name}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Members in this org */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-semibold text-white uppercase tracking-wider">
                    Engineering Team ({members.length})
                  </h3>
                  <button
                    onClick={() => navigate(`/organizations/${selectedOrg.id}/members`)}
                    className="text-xs text-forge-400 hover:text-forge-300 font-medium"
                  >
                    Manage Team →
                  </button>
                </div>

                {loadingDetails ? (
                  <div className="flex justify-center py-6"><Spinner size="sm" /></div>
                ) : (
                  <div className="divide-y divide-white/5 bg-surface-900/50 rounded-xl border border-white/5 px-4">
                    {members.slice(0, 5).map((m) => (
                      <div key={m.id} className="py-2.5 flex items-center justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <div className="w-7 h-7 rounded-full bg-forge-600/30 border border-forge-500/30 text-forge-300 flex items-center justify-center text-xs font-bold">
                            {m.user?.name?.charAt(0).toUpperCase() || 'U'}
                          </div>
                          <div>
                            <p className="text-xs font-medium text-white">{m.user?.name || 'Engineer'}</p>
                            <p className="text-[11px] text-surface-500">{m.user?.email}</p>
                          </div>
                        </div>
                        <RoleBadge role={m.role} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          ) : (
            <Card>
              <div className="flex flex-col items-center justify-center py-16 text-center text-surface-400">
                <p className="text-sm">Select an organization workspace to view details</p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </PageLayout>
  );
}
