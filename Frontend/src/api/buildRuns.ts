/**
 * buildRuns.ts — API client for Build Run endpoints.
 *
 * Uses the shared apiClient (relative base URL) so the same code works in
 * Vite dev (proxy) and behind nginx in Docker. EventSource cannot set an
 * Authorization header, so the JWT is passed as a query param for SSE only.
 */
import apiClient from './client';
import type { BuildRunOut } from '@/types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

export const buildRunsApi = {
  /**
   * Trigger a build run for an approved plan.
   * Returns build_run_id immediately (202 Accepted).
   */
  triggerBuild: (planId: string) =>
    apiClient.post<{ build_run_id: string; trace_id: string | null; message: string }>(
      `/api/v1/feature-plans/${planId}/build`
    ),

  /**
   * Poll build run status, test results, generated patches, and PR URL.
   */
  getBuildRun: (buildRunId: string) =>
    apiClient.get<BuildRunOut>(`/api/v1/build-runs/${buildRunId}`),

  /**
   * Create an EventSource for SSE log streaming.
   * EventSource doesn't support custom headers, so the JWT goes in the query.
   */
  createLogStream: (buildRunId: string): EventSource => {
    const token = localStorage.getItem('access_token') ?? '';
    const url = `${API_BASE}/api/v1/build-runs/${buildRunId}/stream?token=${encodeURIComponent(token)}`;
    return new EventSource(url, { withCredentials: true });
  },
};
