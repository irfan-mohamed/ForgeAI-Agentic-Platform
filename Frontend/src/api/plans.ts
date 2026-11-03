import apiClient from './client';
import type { CreatePlanResponse, PlanOut, RequestChangesRequest } from '@/types';

export const plansApi = {
  /** Generate a structured implementation plan from a natural language request. */
  createPlan: (conversationId: string, feature_request: string) =>
    apiClient.post<CreatePlanResponse>(
      `/api/v1/conversations/${conversationId}/feature-plans`,
      { feature_request },
    ),

  /** Get plan details, task list, and approval audit trail. */
  getPlan: (planId: string) =>
    apiClient.get<PlanOut>(`/api/v1/feature-plans/${planId}`),

  /** Approve a plan (human-in-the-loop gate). */
  approvePlan: (planId: string, comment?: string, commit_sha?: string) =>
    apiClient.post<PlanOut>(`/api/v1/feature-plans/${planId}/approve`, {
      comment,
      commit_sha,
    }),

  /** Reject a plan. */
  rejectPlan: (planId: string, comment?: string) =>
    apiClient.post<PlanOut>(`/api/v1/feature-plans/${planId}/reject`, {
      comment,
    }),

  /** Request changes to a plan with feedback (triggers automatic revision). */
  requestChanges: (planId: string, payload: RequestChangesRequest) =>
    apiClient.post<CreatePlanResponse>(
      `/api/v1/feature-plans/${planId}/request-changes`,
      payload,
    ),
};
