import axios from 'axios';
import { withCollectionSlash } from '../utils/apiPaths';
import { AUTH_REFRESHED_EVENT } from '../utils/polling';
import { useReportStore } from '../stores/reportStore';

// Security (F-023): the access token is held ONLY in module-scoped memory.
// It is NEVER written to localStorage / sessionStorage so that an XSS attacker
// cannot exfiltrate it. On full page reload the token is recovered via the
// HttpOnly refresh-token cookie (see tryRefreshSession / authStore.hydrate).
let accessToken: string | null = null;

// Shared in-flight refresh promise: when several requests race on an expired
// access token we must only issue ONE /auth/refresh call — otherwise backend
// refresh-token rotation would invalidate concurrent retries.
let refreshPromise: Promise<string> | null = null;

// #370: true while a read-only impersonation token is active. Impersonation
// tokens are NOT refreshable — refreshing would use the admin's HttpOnly cookie
// and silently upgrade the MA view to a full admin token. On 401 we bail back to
// the admin session instead (see the response interceptor below).
let impersonating = false;

export function setImpersonating(active: boolean) {
  impersonating = active;
}

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
    // Log-Audit 2026-11-15 (Punkt 17): Basis-Routen mit Schrägstrich rufen —
    // sonst je Aufruf eine 307-Umleitung und eine zweite Anfrage.
    config.url = withCollectionSlash(config.url);
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
  // Log-Audit 2026-11-15 (Punkt 17): das Layout setzt sein nach 401/403
  // pausiertes Polling erst nach einer erfolgreichen Erneuerung fort.
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(AUTH_REFRESHED_EVENT));
  }
  return access_token;
}

/** auth-04: true, wenn der Server den Refresh ausdrücklich verweigert hat (401/403). */
export function isRefreshRejection(err: unknown): boolean {
  const status = (err as { response?: { status?: number } } | null)?.response?.status;
  return status === 401 || status === 403;
}

// #382: systemic guard against a poisoned 200 body. In an auth/proxy/SPA-fallback
// edge, an /api call can resolve HTTP 200 with the SPA's index.html (a string)
// instead of JSON. Downstream code assumes JSON and does res.data.map/.toFixed/
// .length during render → a synchronous throw caught by the app ErrorBoundary →
// full-screen "Etwas ist schiefgelaufen". Convert such a response into a normal
// rejection so callers hit their existing .catch/error path instead of crashing
// the whole app. (Per-view shape guards remain as belt-and-suspenders for
// wrong-shape *JSON* bodies, which this cannot detect.)
function looksLikeHtml(data: unknown): boolean {
  return typeof data === 'string' && /^\s*(<!doctype html|<html[\s>])/i.test(data);
}

// #557: 5xx-Antworten für „An Entwickler schicken“ merken. Der Server findet die
// error_logs-Zeile über Methode, Status und Pfad (request.url.path, ohne Abfrage),
// daher wird genau dieser Pfad festgehalten — sonst nichts (keine Daten, keine Abfrage).
const REPORTABLE_METHODS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']);
const MAX_REPORT_PATH = 500;

export function serverErrorPath(baseURL: string | undefined, url: string | undefined): string | null {
  const rawUrl = url ?? '';
  let joined: string;
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(rawUrl)) {
    joined = rawUrl;
  } else {
    const base = (baseURL ?? '').replace(/\/+$/, '');
    joined = rawUrl ? `${base}/${rawUrl.replace(/^\/+/, '')}` : base;
  }
  let path: string;
  try {
    path = new URL(joined, 'http://local.invalid').pathname;
  } catch {
    return null;
  }
  // Wie Starlettes request.url.path: Prozent-Kodierung je Segment aufgelöst,
  // auch %2F/%3F/%23 (decodeURI ließe sie stehen, #557 D6). Ein kaputtes
  // Segment bleibt, wie es ist.
  path = path
    .split('/')
    .map((segment) => {
      try {
        return decodeURIComponent(segment);
      } catch {
        return segment;
      }
    })
    .join('/');
  if (!path.startsWith('/api/') || path.length > MAX_REPORT_PATH) return null;
  return path;
}

function recordServerErrorFrom(error: unknown) {
  const err = error as {
    response?: { status?: number };
    config?: { baseURL?: string; url?: string; method?: string };
  } | null;
  const status = err?.response?.status;
  if (typeof status !== 'number' || status < 500 || status > 599) {
    // #557 D4: jede andere Fehlerantwort (4xx, Netzfehler) beendet das Fenster —
    // sonst übernähme ihr Toast den Hinweis eines älteren 5xx (z. B. Hintergrundabfrage).
    useReportStore.getState().clearServerError();
    return;
  }
  const config = err?.config;
  if (!config) return;
  const method = (config.method || 'get').toUpperCase();
  if (!REPORTABLE_METHODS.has(method)) return;
  if ((config.url || '').includes('/feedback/')) return;
  const path = serverErrorPath(config.baseURL, config.url);
  if (!path || path.includes('/feedback/')) return;
  useReportStore.getState().recordServerError({ status, method, path });
}

// Response interceptor: Handle 401 errors with automatic token refresh
apiClient.interceptors.response.use(
  (response) => {
    if (looksLikeHtml(response.data)) {
      return Promise.reject(
        new Error('Unerwartete Server-Antwort (kein JSON) — bitte neu anmelden.'),
      );
    }
    return response;
  },
  async (error) => {
    recordServerErrorFrom(error);
    const originalRequest = error.config;

    // Don't intercept auth endpoint errors (login / refresh / logout).
    // - login/refresh: avoid masking TOTP-required responses or refresh failures.
    // - logout: a 401 here must NOT trigger a refresh. logout() is reached via
    //   the 'auth:session-expired' handler, so refreshing on a logout 401 (which
    //   then fails again) re-dispatches 'auth:session-expired' → logout() → an
    //   infinite logout↔refresh storm that saturates the connection pool and
    //   hangs every other request (incident: logout 401 ×382, refresh 429 ×50).
    //   The logout path is /auth/refresh/logout (Sicherheits-Review 2026-10),
    //   already covered by '/auth/refresh'; listed explicitly so removing the
    //   refresh guard can never re-open the loop. /auth/logout stays excluded.
    const url: string = originalRequest?.url || '';
    if (
      url.includes('/auth/login') ||
      url.includes('/auth/refresh') ||
      url.includes('/auth/refresh/logout') ||
      url.includes('/auth/logout')
    ) {
      return Promise.reject(error);
    }

    // If 401 and we haven't retried yet, try to refresh the access token
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      // #370: during impersonation the token is intentionally non-refreshable.
      // Signal the store to return to the admin session rather than refreshing
      // (which would mint a full admin token behind the read-only MA view).
      if (impersonating) {
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('impersonation:expired'));
        }
        return Promise.reject(error);
      }

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
        // auth-04: nur eine tatsächlich abgelehnte Sitzung (401/403) meldet ab.
        // Netzfehler, 5xx (Neustart beim Update) und 429 lassen das gültige
        // 7-Tage-Cookie und die Sitzung in Ruhe — der ursprüngliche Fehler geht durch.
        if (!isRefreshRejection(refreshError)) {
          return Promise.reject(error);
        }
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
 * was rejected (401/403); throws on transient errors. Safe to call during app hydration.
 */
export async function tryRefreshSession(): Promise<string | null> {
  try {
    if (!refreshPromise) {
      refreshPromise = performRefresh().finally(() => {
        refreshPromise = null;
      });
    }
    return await refreshPromise;
  } catch (err) {
    // auth-04: nur eine verweigerte Sitzung ergibt „kein Token“; vorübergehende
    // Fehler (Netz, 5xx, 429) werden weitergereicht, damit der Aufrufer die
    // gespeicherte Anmeldung behalten kann.
    if (isRefreshRejection(err)) {
      accessToken = null;
      return null;
    }
    throw err;
  }
}

export default apiClient;
