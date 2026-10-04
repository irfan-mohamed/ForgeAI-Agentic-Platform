import apiClient from './client';
import type { LoginCredentials, RegisterPayload, TokenResponse, User } from '@/types';

export const authApi = {
  /** Register a new user account. */
  register: (payload: RegisterPayload) =>
    apiClient.post<{ status: string }>('/api/v1/auth/register', payload),

  /**
   * Logs in and returns a JWT.
   * The API uses OAuth2 form encoding (application/x-www-form-urlencoded).
   */
  login: (credentials: LoginCredentials) => {
    const form = new URLSearchParams({
      username: credentials.email,
      password: credentials.password,
    });
    return apiClient.post<TokenResponse>('/api/v1/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
  },

  /** Fetches the current user's profile. */
  me: () => apiClient.get<User>('/api/v1/users/me'),
};
