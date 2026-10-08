/**
 * repositoryApi — all calls to the Repository Service (port 8001).
 *
 * The Vite proxy routes /api/v1/github and /api/v1/repositories to :8001.
 * Organization-scoped github/* and repositories/* also go to :8001.
 */
import apiClient from './client';
import type {
  GitHubConnectionStatus,
  GitHubAvailableRepo,
  Repository,
  RepositorySyncStatus,
} from '@/types';

export const repositoryApi = {
  // ── GitHub connection ───────────────────────────────────────────────────────

  /** Returns whether the org has an active GitHub App installation. */
  getGitHubStatus: (orgId: number) =>
    apiClient.get<GitHubConnectionStatus>(`/api/v1/organizations/${orgId}/github`),

  /**
   * Returns the GitHub App install URL (as a redirect).
   * Must be called via fetch (to include auth header) and then redirect the browser.
   */
  getInstallUrl: (orgId: number): Promise<string> =>
    apiClient.get<{ install_url: string }>(`/api/v1/organizations/${orgId}/github/install`)
      .then(res => res.data.install_url),

  /** Lists all repositories visible through the GitHub App installation. */
  listAvailableRepos: (orgId: number) =>
    apiClient.get<{ repositories: GitHubAvailableRepo[] }>(
      `/api/v1/organizations/${orgId}/github/repositories`,
    ),

  // ── Repository management ──────────────────────────────────────────────────

  /** Lists all connected repositories for the organization. */
  listRepos: (orgId: number) =>
    apiClient.get<{ repositories: Repository[] }>(
      `/api/v1/organizations/${orgId}/repositories`,
    ),

  /** Connects a GitHub repository to ForgeAI. */
  connectRepo: (orgId: number, githubRepositoryId: string) =>
    apiClient.post<Repository>(`/api/v1/organizations/${orgId}/repositories`, {
      github_repository_id: githubRepositoryId,
    }),

  /** Gets a single repository by ID. */
  getRepo: (repoId: number) =>
    apiClient.get<Repository>(`/api/v1/repositories/${repoId}`),

  /** Requests a manual re-sync for a repository. */
  requestSync: (repoId: number) =>
    apiClient.post<{ id: number; status: string; trigger: string }>(
      `/api/v1/repositories/${repoId}/sync`,
    ),

  /** Gets the latest sync status for a repository. */
  getSyncStatus: (repoId: number) =>
    apiClient.get<RepositorySyncStatus>(
      `/api/v1/repositories/${repoId}/sync/status`,
    ),

  /** Disconnects a repository from ForgeAI. */
  disconnectRepo: (repoId: number) =>
    apiClient.delete(`/api/v1/repositories/${repoId}`),
};