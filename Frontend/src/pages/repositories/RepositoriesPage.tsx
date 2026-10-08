/**
 * RepositoriesPage — the main repository management page.
 *
 * Shows:
 * 1. GitHub connection status with a "Connect GitHub" CTA if not connected
 * 2. List of connected repositories with status badges
 * 3. "Add Repository" flow — lists available repos from GitHub, lets user connect
 * 4. Per-repo: sync status, manual re-sync trigger, disconnect
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
    <span className={`badge text-xs font-medium ${REPO_STATUS_COLORS[status]}`}>
      {status === 'syncing' || status === 'indexing' || status === 'connecting' ? (
        <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5 animate-pulse inline-block" />
      ) : null}
      {REPO_STATUS_LABELS[status]}
    </span>
  );
}

// ── Visibility badge ──────────────────────────────────────────────────────────

function VisibilityBadge({ visibility }: { visibility: 'public' | 'private' }) {
  return (
    <span className={`badge text-xs ${
      visibility === 'private'
        ? 'bg-gray-100 text-gray-600'
        : 'bg-emerald-50 text-emerald-700'
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
      setError('Failed to get GitHub installation URL. Please try again.');
      console.error('Failed to get GitHub install URL', err);
    }
  };

  return (
    <div className="glass-card p-8 flex flex-col items-center text-center gap-6 animate-slide-up">
      {/* GitHub mark */}
      <div className="w-20 h-20 rounded-3xl bg-gray-900 flex items-center justify-center shadow-xl">
        <svg className="w-10 h-10 text-white" fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
          </svg>
        </div>

        <div>
          <h2 className="text-xl font-bold text-gray-900 mb-2">Connect your GitHub account</h2>
          <p className="text-gray-500 text-sm max-w-md">
            Install the ForgeAI GitHub App to let ForgeAI access your repositories.
            You choose exactly which repos to grant access to.
          </p>
        </div>

        <div className="flex flex-col gap-2 text-left w-full max-w-sm">
          {[
            'Choose which repositories to grant access to',
            'ForgeAI reads code — never writes or modifies',
            'Revoke access any time from GitHub settings',
          ].map((item) => (
            <div key={item} className="flex items-start gap-2.5 text-sm text-gray-600">
              <svg className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              {item}
            </div>
          ))}
        </div>

        {error && (
          <p className="text-red-500 text-sm">{error}</p>
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
          Connect GitHub
        </Button>
      </div>
    );
}

// ── Add repo modal ────────────────────────────────────────────────────────────

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
      .catch(() => setError('Failed to load repositories from GitHub.'))
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-2xl glass-card flex flex-col max-h-[80vh] animate-slide-up">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-100">
          <div>
            <h2 className="font-bold text-gray-900 text-lg">Add Repository</h2>
            <p className="text-gray-500 text-sm mt-0.5">
              Select a repository to connect to ForgeAI
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Search */}
        <div className="px-6 py-3 border-b border-gray-100">
          <input
            type="text"
            placeholder="Search repositories…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-base text-sm py-2"
            autoFocus
          />
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 p-2">
          {loading ? (
            <div className="flex justify-center py-12"><Spinner /></div>
          ) : error ? (
            <div className="flex flex-col items-center py-10 gap-3 text-center">
              <p className="text-red-500 text-sm">{error}</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center py-10 gap-3 text-center">
              <p className="text-gray-500 text-sm">
                {search ? 'No repositories match your search.' : 'No repositories available.'}
              </p>
            </div>
          ) : (
            filtered.map((repo) => (
              <div
                key={repo.github_repository_id}
                className="flex items-center gap-4 px-4 py-3 rounded-xl hover:bg-gray-50 transition-colors group"
              >
                {/* Repo icon */}
                <div className="w-9 h-9 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
                  <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                  </svg>
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-900 text-sm truncate">{repo.full_name}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <VisibilityBadge visibility={repo.visibility} />
                    <span className="text-gray-400 text-xs">{repo.default_branch}</span>
                  </div>
                  {repo.description && (
                    <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{repo.description}</p>
                  )}
                </div>

                {/* Connect button */}
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

// ── Repository row ────────────────────────────────────────────────────────────

function RepositoryRow({
  repo,
  onSync,
  onDisconnect,
}: {
  repo: Repository;
  onSync: (repoId: number) => void;
  onDisconnect: (repoId: number) => void;
}) {
  const [syncStatus, setSyncStatus] = useState<RepositorySyncStatus | null>(null);
  const [loadingSync, setLoadingSync] = useState(false);

  const fetchSyncStatus = useCallback(async () => {
    try {
      const res = await repositoryApi.getSyncStatus(repo.id);
      setSyncStatus(res.data);
    } catch {
      // No sync record yet — normal for a brand new repo
    }
  }, [repo.id]);

  useEffect(() => {
    fetchSyncStatus();
  }, [fetchSyncStatus]);

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

  const progressPct = syncStatus?.progress.files_discovered
    ? Math.round(
        (syncStatus.progress.files_processed / syncStatus.progress.files_discovered) * 100,
      )
    : 0;

  return (
    <div className="glass-card p-5 flex flex-col gap-3 hover:border-forge-200 transition-all animate-fade-in">
      {/* Row 1: name + status + actions */}
      <div className="flex items-start gap-4">
        {/* Icon */}
        <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center flex-shrink-0">
          <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
          </svg>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-gray-900 text-sm">{repo.full_name}</h3>
            <RepoStatusBadge status={repo.status} />
            <VisibilityBadge visibility={repo.visibility} />
          </div>
          <p className="text-gray-400 text-xs mt-0.5">
            Branch: <span className="font-mono">{repo.default_branch}</span>
            {repo.last_synced_at && (
              <> · Last synced: {new Date(repo.last_synced_at).toLocaleDateString()}</>
            )}
          </p>
          {repo.description && (
            <p className="text-gray-500 text-xs mt-1 line-clamp-1">{repo.description}</p>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {repo.status === 'ready' || repo.status === 'failed' ? (
            <Button
              variant="secondary"
              size="sm"
              isLoading={loadingSync}
              onClick={handleSync}
              leftIcon={
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              }
            >
              Sync
            </Button>
          ) : null}

          <button
            onClick={() => onDisconnect(repo.id)}
            title="Disconnect repository"
            className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
          </button>
        </div>
      </div>

      {/* Row 2: sync progress bar (only when syncing/indexing/queued) */}
      {syncStatus && ['queued', 'running'].includes(syncStatus.status) && (
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs text-gray-500">
            <span>
              {syncStatus.status === 'queued' ? 'Queued…' : `Processing files`}
            </span>
            {syncStatus.progress.files_discovered > 0 && (
              <span>
                {syncStatus.progress.files_processed} / {syncStatus.progress.files_discovered} files
              </span>
            )}
          </div>
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-forge-500 to-purple-500 rounded-full transition-all duration-700"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      )}

      {/* Error message */}
      {syncStatus?.status === 'failed' && syncStatus.error_message && (
        <p className="text-xs text-red-500 bg-red-50 rounded-lg px-3 py-2">
          {syncStatus.error_message}
        </p>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function RepositoriesPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const navigate = useNavigate();
  const parsedOrgId = Number(orgId);

  const [org, setOrg]                           = useState<Organization | null>(null);
  const [githubStatus, setGithubStatus]         = useState<GitHubConnectionStatus | null>(null);
  const [repos, setRepos]                       = useState<Repository[]>([]);
  const [loadingPage, setLoadingPage]           = useState(true);
  const [showAddModal, setShowAddModal]         = useState(false);
  const [, setDisconnecting]       = useState<number | null>(null);

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
    if (!confirm('Disconnect this repository? This cannot be undone.')) return;
    setDisconnecting(repoId);
    try {
      await repositoryApi.disconnectRepo(repoId);
      setRepos((prev) => prev.filter((r) => r.id !== repoId));
    } finally {
      setDisconnecting(null);
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
            ? `Connected as ${githubStatus.account?.login} · ${repos.length} ${repos.length === 1 ? 'repository' : 'repositories'}`
            : `${org?.name ?? ''} · Connect GitHub to get started`
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

      {/* GitHub connected indicator */}
      {githubStatus?.connected && (
        <div className="flex items-center gap-2 mb-6 px-1">
          <div className="w-2 h-2 rounded-full bg-emerald-500" />
          <span className="text-sm text-gray-600">
            GitHub connected ·{' '}
            <span className="font-medium">{githubStatus.account?.login}</span>{' '}
            <span className="text-gray-400">({githubStatus.account?.account_type})</span>
          </span>
        </div>
      )}

      {/* Content */}
      {!githubStatus?.connected ? (
        <GitHubConnectBanner orgId={parsedOrgId} />
      ) : repos.length === 0 ? (
        <div className="glass-card p-12 flex flex-col items-center text-center gap-5 animate-slide-up">
          <div className="w-16 h-16 rounded-2xl bg-forge-50 flex items-center justify-center">
            <svg className="w-8 h-8 text-forge-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          </div>
          <div>
            <h2 className="font-bold text-gray-900 mb-2">No repositories connected</h2>
            <p className="text-gray-500 text-sm">
              Click "Add Repository" to connect a GitHub repo to ForgeAI.
            </p>
          </div>
          <Button variant="primary" onClick={() => setShowAddModal(true)}>
            Add your first repository
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {repos.map((repo) => (
            <RepositoryRow
              key={repo.id}
              repo={repo}
              onSync={() => {/* status refresh handled inside row */}}
              onDisconnect={handleDisconnect}
            />
          ))}
        </div>
      )}

      {/* Add repo modal */}
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