import apiClient from './client';
import type {
  CodeReviewDetail,
  CodeReviewListResponse,
  CodeReviewSummary,
  StartReviewRequest,
} from '@/types';

export const reviewsApi = {
  /** Start a new AI Code Review on a GitHub pull request. */
  startReview: (orgId: number, payload: StartReviewRequest) =>
    apiClient.post<CodeReviewSummary>(
      `/api/v1/organizations/${orgId}/code-reviews`,
      payload,
    ),

  /** List reviews in an organization with optional repo and PR filter. */
  listReviews: (
    orgId: number,
    params?: {
      repository_id?: number;
      pull_number?: number;
      page?: number;
      limit?: number;
    },
  ) =>
    apiClient.get<CodeReviewListResponse>(
      `/api/v1/organizations/${orgId}/code-reviews`,
      { params },
    ),

  /** Get a single code review with all its findings. */
  getReview: (reviewId: string) =>
    apiClient.get<CodeReviewDetail>(`/api/v1/code-reviews/${reviewId}`),
};
