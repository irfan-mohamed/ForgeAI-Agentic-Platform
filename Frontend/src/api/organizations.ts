import apiClient from './client';
import type { Organization, Membership } from '@/types';

export const organizationsApi = {
  /** Create a new organization. The caller automatically becomes COMPANY_ADMIN. */
  create: (payload: { name: string; slug: string; description?: string }) =>
    apiClient.post<Organization>('/api/v1/organizations', payload),

  /** List all organizations the current user belongs to. */
  list: () => apiClient.get<Organization[]>('/api/v1/organizations'),

  /** Get a single organization by ID. */
  get: (orgId: number) =>
    apiClient.get<Organization>(`/api/v1/organizations/${orgId}`),

  /** List all active members of an organization. */
  listMembers: (orgId: number) =>
    apiClient.get<Membership[]>(`/api/v1/organizations/${orgId}/members`),

  /** Update a member's role within an organization. */
  updateRole: (orgId: number, userId: number, role: string) =>
    apiClient.patch<Membership>(
      `/api/v1/organizations/${orgId}/members/${userId}/role`,
      { role },
    ),
};
