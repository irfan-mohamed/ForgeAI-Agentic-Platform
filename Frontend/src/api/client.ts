import axios from 'axios';

/**
 * Axios instance pre-configured for the FlowForge API.
 *
 * - Reads the base URL from the Vite env variable (defaults to '' which
 *   means the dev proxy handles /api → http://localhost:8000).
 * - Attaches the JWT bearer token from localStorage on every request.
 * - On 401 responses, clears the stored token and redirects to /login so the
 *   user is not silently stuck in an unauthenticated state.
 */
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  headers: { 'Content-Type': 'application/json' },
  timeout: 15_000,
});

// ── Request interceptor — attach token ────────────────────────────────────────
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor — handle 401 ────────────────────────────────────────
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      // Avoid redirect loops on the login page itself
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

export default apiClient;
