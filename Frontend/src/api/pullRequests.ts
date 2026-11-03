import apiClient from './client';
import type { PullRequestDetail, PullRequestListResponse } from '@/types';

export const pullRequestsApi = {
  /** List pull requests for a connected repository. */
  list: (
    repoId: number,
    params?: {
      state?: 'open' | 'closed' | 'all';
      page?: number;
      limit?: number;
    },
  ) =>
    apiClient.get<PullRequestListResponse>(
      `/api/v1/repositories/${repoId}/pull-requests`,
      { params },
    ),

  /** Get pull request details including changed files and patch diffs. */
  get: (repoId: number, pullNumber: number) =>
    apiClient.get<PullRequestDetail>(
      `/api/v1/repositories/${repoId}/pull-requests/${pullNumber}`,
    ),
};
