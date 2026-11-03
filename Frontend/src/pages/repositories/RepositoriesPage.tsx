/**
 * RepositoriesPage — connected repositories management.
 */
import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { repositoryApi } from '@/api/repository';
import { organizationsApi } from '@/api/organizations';
import { PageLayout, PageHeader } from '@/components/layout/PageLayout';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import type {
  Organization,
  Repository,
  GitHubConnectionStatus,
  GitHubAvailableRepo,
  RepositorySyncStatus,
  RepositoryStatus,
} from '@/types';
import { REPO_STATUS_LABELS, REPO_STATUS_COLORS } from '@/types';

// ── Status badge ──────────────────────────────────────────────────────────────

function RepoStatusBadge({ status }: { status: RepositoryStatus }) {
  return (
    <span className={`badge text-[11px] font-medium font-mono ${REPO_STATUS_COLORS[status]}`}>
      {status === 'syncing' || status === 'indexing' || status === 'connecting' ? (
        <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5 animate-pulse inline-block" />
      ) : null}
      {REPO_STATUS_LABELS[status] ?? status}
    </span>
  );
}

// ── Visibility badge ──────────────────────────────────────────────────────────

function VisibilityBadge({ visibility }: { visibility: 'public' | 'private' }) {
  return (
    <span className={`badge text-[10px] font-mono border ${
      visibility === 'private'
        ? 'bg-surface-800 text-surface-400 border-white/10'
        : 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
    }`}>
      {visibility === 'private' ? '🔒 Private' : '🌐 Public'}
    </span>
  );
}

// ── GitHub not connected banner ───────────────────────────────────────────────

function GitHubConnectBanner({ orgId }: { orgId: number }) {
  const [error, setError] = useState<string | null>(null);

  const handleConnect = async () => {
    setError(null);
    try {
      const installUrl = await repositoryApi.getInstallUrl(orgId);
      window.location.href = installUrl;
    } catch (err) {
      setError('Failed to get GitHub installation URL. Please verify GitHub App credentials.');
      console.error('Failed to get GitHub install URL', err);
    }
  };

  return (
    <div className="glass-card p-10 flex flex-col items-center text-center gap-6 animate-slide-up max-w-2xl mx-auto border border-white/10">
      <div className="w-20 h-20 rounded-3xl bg-surface-900 border border-white/10 flex items-center justify-center shadow-2xl text-white">
        <svg className="w-10 h-10" fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
        </svg>
      </div>

      <div>
        <h2 className="text-xl font-bold text-white tracking-tight mb-2">Connect Your GitHub Organization</h2>
        <p className="text-surface-400 text-xs max-w-md mx-auto leading-relaxed">
          Install the ForgeAI GitHub App to grant read-only access to select repositories.
          ForgeAI indexes code semantics into an isolated vector store for AI reasoning.
        </p>
      </div>

      <div className="flex flex-col gap-2.5 text-left w-full max-w-md bg-surface-900/60 p-4 rounded-xl border border-white/5">
        {[
          'Granular permissions: select only the repositories you choose',
          'Read-only code inspection: ForgeAI never pushes unreviewed commits',
          'Immediate synchronization: automatic branch & push webhook tracking',
        ].map((item) => (
          <div key={item} className="flex items-start gap-2.5 text-xs text-surface-300">
            <svg className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            <span>{item}</span>
          </div>
        ))}
      </div>

      {error && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 px-3 py-2 rounded-lg">{error}</p>
      )}

      <Button
        variant="primary"
        size="lg"
        onClick={handleConnect}
        leftIcon={
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
          </svg>
        }
      >
        Install GitHub App
      </Button>
    </div>
  );
}

// ── Add Repo Modal ────────────────────────────────────────────────────────────

function AddRepositoryModal({
  orgId,
  onClose,
  onConnected,
}: {
  orgId: number;
  onClose: () => void;
  onConnected: (repo: Repository) => void;
}) {
  const [availableRepos, setAvailableRepos] = useState<GitHubAvailableRepo[]>([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    repositoryApi.listAvailableRepos(orgId)
      .then((res) => setAvailableRepos(res.data.repositories))
      .catch(() => setError('Failed to load repositories from GitHub App installation.'))
      .finally(() => setLoading(false));
  }, [orgId]);

  const handleConnect = async (githubRepoId: string) => {
    setConnecting(githubRepoId);
    setError('');
    try {
      const res = await repositoryApi.connectRepo(orgId, githubRepoId);
      onConnected(res.data);
      onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof msg === 'string' ? msg : 'Failed to connect repository.');
    } finally {
      setConnecting(null);
    }
  };

  const filtered = availableRepos.filter((r) =>
    r.full_name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-xl glass-card flex flex-col max-h-[80vh] border border-white/10 shadow-2xl animate-slide-up">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-white/8">
          <div>
            <h2 className="font-bold text-white text-base">Connect Repository</h2>
            <p className="text-surface-400 text-xs mt-0.5">
              Select a repository to index for ForgeAI assistance
            </p>
          </div>
          <button onClick={onClose} className="text-surface-400 hover:text-white transition-colors">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Search */}
        <div className="px-5 py-3 border-b border-white/8">
          <input
            type="text"
            placeholder="Search authorized GitHub repositories…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-base text-xs py-2"
            autoFocus
          />
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 p-3">
          {loading ? (
            <div className="flex justify-center py-12"><Spinner /></div>
          ) : error ? (
            <div className="flex flex-col items-center py-8 gap-3 text-center">
              <p className="text-red-400 text-xs">{error}</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center py-10 gap-2 text-center text-surface-400 text-xs">
              <p>{search ? 'No repositories match your search.' : 'No accessible repositories found.'}</p>
              <p className="text-surface-500 text-[11px]">Check the GitHub App permissions to grant repo access.</p>
            </div>
          ) : (
            filtered.map((repo) => (
              <div
                key={repo.github_repository_id}
                className="flex items-center gap-3.5 px-4 py-3 rounded-xl hover:bg-surface-800/80 transition-colors border border-transparent hover:border-white/5"
              >
                <div className="w-8 h-8 rounded-lg bg-surface-800 border border-white/10 flex items-center justify-center flex-shrink-0 text-white">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                  </svg>
                </div>

                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-white text-xs truncate">{repo.full_name}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <VisibilityBadge visibility={repo.visibility} />
                    <span className="text-surface-500 text-[11px] font-mono">{repo.default_branch}</span>
                  </div>
                </div>

                <Button
                  variant="primary"
                  size="sm"
                  isLoading={connecting === repo.github_repository_id}
                  onClick={() => handleConnect(repo.github_repository_id)}
                >
                  Connect
                </Button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

// ── Repository Row ────────────────────────────────────────────────────────────

function RepositoryRow({
  repo,
  orgId,
  onSync,
  onDisconnect,
}: {
  repo: Repository;
  orgId: number;
  onSync: (repoId: number) => void;
  onDisconnect: (repoId: number) => void;
}) {
  const navigate = useNavigate();
  const [syncStatus, setSyncStatus] = useState<RepositorySyncStatus | null>(null);
  const [loadingSync, setLoadingSync] = useState(false);

  const fetchSyncStatus = useCallback(async () => {
    try {
      const res = await repositoryApi.getSyncStatus(repo.id);
      setSyncStatus(res.data);
    } catch {
      // Normal if sync record not yet present
    }
  }, [repo.id]);

  useEffect(() => {
    fetchSyncStatus();
    // Poll sync status if running or queued
    if (syncStatus && ['queued', 'running'].includes(syncStatus.status)) {
      const timer = setInterval(fetchSyncStatus, 2500);
      return () => clearInterval(timer);
    }
  }, [fetchSyncStatus, syncStatus]);

  const handleSync = async () => {
    setLoadingSync(true);
    try {
      await repositoryApi.requestSync(repo.id);
      onSync(repo.id);
      setTimeout(fetchSyncStatus, 800);
    } finally {
      setLoadingSync(false);
    }
  };

  const progressPct = syncStatus?.progress?.files_discovered
    ? Math.round(
        (syncStatus.progress.files_processed / syncStatus.progress.files_discovered) * 100,
      )
    : 0;

  return (
    <div className="glass-card p-5 flex flex-col gap-3.5 border border-white/10 hover:border-forge-500/30 transition-all animate-fade-in">
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 rounded-xl bg-surface-900 border border-white/10 flex items-center justify-center text-white flex-shrink-0">
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
          </svg>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h3 className="font-semibold text-white text-sm">{repo.full_name}</h3>
            <RepoStatusBadge status={repo.status} />
            <VisibilityBadge visibility={repo.visibility} />
          </div>
          <p className="text-surface-400 text-xs mt-0.5">
            Default Branch: <span className="font-mono text-white">{repo.default_branch}</span>
            {repo.last_synced_at && (
              <> · Last Synced: <span className="text-surface-300">{new Date(repo.last_synced_at).toLocaleString()}</span></>
            )}
          </p>
          {repo.description && (
            <p className="text-surface-400 text-xs mt-1 line-clamp-1">{repo.description}</p>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate(`/organizations/${orgId}/ai`)}
          >
            Chat
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate(`/organizations/${orgId}/reviews`)}
          >
            PR Reviews
          </Button>

          <Button
            variant="secondary"
            size="sm"
            isLoading={loadingSync}
            onClick={handleSync}
            title="Re-synchronize repository vectors"
          >
            Sync
          </Button>

          <button
            onClick={() => onDisconnect(repo.id)}
            title="Disconnect repository"
            className="w-8 h-8 rounded-xl flex items-center justify-center text-surface-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
          </button>
        </div>
      </div>

      {/* Sync progress bar */}
      {syncStatus && ['queued', 'running'].includes(syncStatus.status) && (
        <div className="space-y-1.5 bg-surface-900/60 p-3 rounded-xl border border-white/5">
          <div className="flex justify-between text-xs text-surface-400">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-forge-400 animate-pulse" />
              {syncStatus.status === 'queued' ? 'Sync queued in Kafka…' : 'Processing & embedding files into Qdrant…'}
            </span>
            {syncStatus.progress?.files_discovered > 0 && (
              <span className="font-mono text-white">
                {syncStatus.progress.files_processed} / {syncStatus.progress.files_discovered} files ({progressPct}%)
              </span>
            )}
          </div>
          <div className="h-1.5 bg-surface-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-forge-500 to-cyan-400 rounded-full transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      )}

      {syncStatus?.status === 'failed' && syncStatus.error_message && (
        <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2">
          Sync error: {syncStatus.error_message}
        </p>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function RepositoriesPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const navigate = useNavigate();
  const parsedOrgId = Number(orgId);

  const [org, setOrg]                   = useState<Organization | null>(null);
  const [githubStatus, setGithubStatus] = useState<GitHubConnectionStatus | null>(null);
  const [repos, setRepos]               = useState<Repository[]>([]);
  const [loadingPage, setLoadingPage]   = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      const [orgRes, statusRes, reposRes] = await Promise.all([
        organizationsApi.get(parsedOrgId),
        repositoryApi.getGitHubStatus(parsedOrgId),
        repositoryApi.listRepos(parsedOrgId),
      ]);
      setOrg(orgRes.data);
      setGithubStatus(statusRes.data);
      setRepos(reposRes.data.repositories);
    } catch {
      navigate('/dashboard');
    } finally {
      setLoadingPage(false);
    }
  }, [parsedOrgId, navigate]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleRepoConnected = (newRepo: Repository) => {
    setRepos((prev) => [newRepo, ...prev]);
  };

  const handleDisconnect = async (repoId: number) => {
    if (!confirm('Disconnect this repository from ForgeAI? Indexed vector knowledge will be removed.')) return;
    try {
      await repositoryApi.disconnectRepo(repoId);
      setRepos((prev) => prev.filter((r) => r.id !== repoId));
    } catch (err) {
      console.error('Failed to disconnect repository', err);
    }
  };

  if (loadingPage) {
    return (
      <PageLayout>
        <div className="flex items-center justify-center h-64">
          <Spinner size="lg" />
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <PageHeader
        title="Repositories"
        subtitle={
          githubStatus?.connected
            ? `Connected as ${githubStatus.account?.login} · ${repos.length} ${repos.length === 1 ? 'repository' : 'repositories'} managed`
            : `${org?.name ?? 'Workspace'} · Connect GitHub App to begin repository synchronization`
        }
        action={
          githubStatus?.connected ? (
            <Button
              variant="primary"
              size="md"
              onClick={() => setShowAddModal(true)}
              leftIcon={
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
              }
            >
              Add Repository
            </Button>
          ) : null
        }
      />

      {/* GitHub connection pill */}
      {githubStatus?.connected && (
        <div className="flex items-center gap-2 mb-6 px-1 text-xs">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          <span className="text-surface-300">
            GitHub App Active: <strong className="text-white font-medium">{githubStatus.account?.login}</strong>{' '}
            <span className="text-surface-500 font-mono">({githubStatus.account?.account_type})</span>
          </span>
        </div>
      )}

      {/* Content */}
      {!githubStatus?.connected ? (
        <GitHubConnectBanner orgId={parsedOrgId} />
      ) : repos.length === 0 ? (
        <div className="glass-card p-12 flex flex-col items-center text-center gap-4 animate-slide-up border border-white/10">
          <div className="w-16 h-16 rounded-2xl bg-surface-900 border border-white/10 flex items-center justify-center text-forge-400">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          </div>
          <div>
            <h2 className="font-bold text-white text-base mb-1">No repositories connected yet</h2>
            <p className="text-surface-400 text-xs">
              Select an authorized repository from your GitHub App installation to index it.
            </p>
          </div>
          <Button variant="primary" onClick={() => setShowAddModal(true)}>
            Connect Repository
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {repos.map((repo) => (
            <RepositoryRow
              key={repo.id}
              repo={repo}
              orgId={parsedOrgId}
              onSync={() => {}}
              onDisconnect={handleDisconnect}
            />
          ))}
        </div>
      )}

      {showAddModal && (
        <AddRepositoryModal
          orgId={parsedOrgId}
          onClose={() => setShowAddModal(false)}
          onConnected={handleRepoConnected}
        />
      )}
    </PageLayout>
  );
}
