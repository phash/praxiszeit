import axios from 'axios';

// Security (F-023): the access token is held ONLY in module-scoped memory.
// It is NEVER written to localStorage / sessionStorage so that an XSS attacker
// cannot exfiltrate it. On full page reload the token is recovered via the
// HttpOnly refresh-token cookie (see tryRefreshSession / authStore.hydrate).
let accessToken: string | null = null;

// Shared in-flight refresh promise: when several requests race on an expired
// access token we must only issue ONE /auth/refresh call — otherwise backend
// refresh-token rotation would invalidate concurrent retries.
let refreshPromise: Promise<string> | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

// Create axios instance
// withCredentials: true ensures the HttpOnly refresh-token cookie is sent
// on cross-origin requests and on the /api/auth/refresh call.
const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Request interceptor: Add JWT access token (from module memory) to
// Authorization header and a CSRF token (from non-HttpOnly cookie) to
// X-CSRF-Token on unsafe methods — see Sprint 1.2.
apiClient.interceptors.request.use(
  (config) => {
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }

    // CSRF double-submit: read csrf_token cookie, send via header on
    // mutating requests. Backend compares header == cookie.
    const method = (config.method || 'get').toLowerCase();
    if (method !== 'get' && method !== 'head' && method !== 'options') {
      const csrfCookie = document.cookie
        .split('; ')
        .find((c) => c.startsWith('csrf_token='));
      if (csrfCookie) {
        config.headers['X-CSRF-Token'] = decodeURIComponent(
          csrfCookie.split('=')[1] || ''
        );
      }
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

async function performRefresh(): Promise<string> {
  // F-010: refresh token is in the HttpOnly cookie – no body needed
  const response = await axios.post('/api/auth/refresh', null, {
    withCredentials: true,
  });
  const { access_token } = response.data as { access_token: string };
  accessToken = access_token;
  return access_token;
}

// Response interceptor: Handle 401 errors with automatic token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Don't intercept auth endpoint errors (login / refresh themselves)
    // to avoid masking TOTP-required responses or refresh failures.
    const url: string = originalRequest?.url || '';
    if (url.includes('/auth/login') || url.includes('/auth/refresh')) {
      return Promise.reject(error);
    }

    // If 401 and we haven't retried yet, try to refresh the access token
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // Deduplicate parallel refresh attempts
        if (!refreshPromise) {
          refreshPromise = performRefresh().finally(() => {
            refreshPromise = null;
          });
        }
        const newToken = await refreshPromise;

        // Retry the original request with the new access token
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Refresh failed (expired or revoked) – drop token and signal
        // the auth store to clear state. A global event is used so this
        // module stays independent of the zustand store.
        accessToken = null;
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('auth:session-expired'));
        }
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

/**
 * Silently try to restore a session via the HttpOnly refresh cookie.
 * Returns the new access token on success, null if no valid cookie / refresh
 * failed. Safe to call during app hydration.
 */
export async function tryRefreshSession(): Promise<string | null> {
  try {
    if (!refreshPromise) {
      refreshPromise = performRefresh().finally(() => {
        refreshPromise = null;
      });
    }
    return await refreshPromise;
  } catch {
    accessToken = null;
    return null;
  }
}

export default apiClient;
