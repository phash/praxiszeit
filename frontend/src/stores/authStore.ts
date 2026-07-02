import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import apiClient, { setAccessToken, getAccessToken, setImpersonating, tryRefreshSession } from '../api/client';
import type { User } from '../types/user';

// #370: the admin's own access token, parked in module memory while a read-only
// impersonation session is active. Never persisted.
let impersonationParentToken: string | null = null;

// #370: shared in-flight guard so a "Zurück zu Admin" click and a concurrent
// impersonation:expired event collapse into ONE stop (otherwise the second call
// races on impersonationParentToken and can null the just-restored admin token).
let stopImpersonationPromise: Promise<void> | null = null;

// #370: fully clear impersonation state (module vars + client flag). Called on
// login/logout so stale flags can never leak into a fresh session.
function resetImpersonationState() {
  impersonationParentToken = null;
  setImpersonating(false);
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  // True while the app is trying to silently restore a session from the
  // HttpOnly refresh cookie on first load. UI must gate routing on this.
  isHydrating: boolean;
  // #370: non-null while impersonating an employee (read-only "Login als …").
  impersonation: { targetName: string } | null;
  login: (username: string, password: string, totpCode?: string) => Promise<void>;
  logout: () => Promise<void>;
  setTokens: (accessToken: string, user: User) => void;
  setUser: (user: User) => void;
  hydrate: () => Promise<void>;
  startImpersonation: (userId: string, userName: string) => Promise<void>;
  stopImpersonation: () => Promise<void>;
  isImpersonating: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isHydrating: true,
      impersonation: null,

      login: async (username: string, password: string, totpCode?: string) => {
        // #370: a fresh login must never inherit stale impersonation flags from a
        // prior session in the same tab (SPA navigation, no reload).
        resetImpersonationState();

        const body: Record<string, unknown> = { username, password };
        if (totpCode) body.totp_code = totpCode;

        const response = await apiClient.post('/auth/login', body);
        const { access_token, user } = response.data;

        // F-023: access token lives in module memory only, never localStorage
        setAccessToken(access_token);

        set({
          user,
          isAuthenticated: true,
          isHydrating: false,
          impersonation: null,
        });

        // Lazily fetch full profile (incl. profile_picture) — excluded
        // from login response for performance. Token already in memory,
        // so the request interceptor attaches it automatically.
        try {
          const meResponse = await apiClient.get('/auth/me');
          set((state) => ({ user: { ...state.user!, ...meResponse.data } }));
        } catch {
          // Non-fatal: app works without profile_picture
        }
      },

      logout: async () => {
        // #370: if impersonating, drop back to the ADMIN token first. Otherwise
        // the /auth/logout POST carries the impersonation token → the read-only
        // middleware 403s it (server session survives) AND, if it got through, it
        // would bump the *employee's* token_version. Restoring the admin token
        // makes logout invalidate the admin's own session + refresh cookie.
        if (get().impersonation) {
          setAccessToken(impersonationParentToken);
          set({ impersonation: null });
        }
        resetImpersonationState();

        // Best-effort server logout (bumps token_version, clears refresh cookie)
        try {
          await apiClient.post('/auth/logout');
        } catch {
          // Ignore — we still clear client state below
        }

        setAccessToken(null);

        // Clear service worker caches (security: remove any cached API data)
        if ('caches' in window) {
          try {
            const names = await caches.keys();
            await Promise.all(names.map((name) => caches.delete(name)));
          } catch {
            // Ignore cache-clear failures
          }
        }

        set({
          user: null,
          isAuthenticated: false,
          isHydrating: false,
        });

        // Explicitly drop the zustand persist entry — removeItem alone is
        // racy because persist re-serializes on the next set().
        try {
          useAuthStore.persist.clearStorage();
        } catch {
          // noop — clearStorage may not exist on older zustand versions
        }
      },

      setTokens: (accessToken: string, user: User) => {
        setAccessToken(accessToken);
        set({ user, isAuthenticated: true });
      },

      setUser: (user: User) => {
        set({ user });
      },

      // #370: start a read-only impersonation session. Parks the admin token,
      // swaps in the impersonation token, and switches the UI to the MA view.
      startImpersonation: async (userId: string, userName: string) => {
        const parent = getAccessToken();
        const response = await apiClient.post(`/admin/users/${userId}/impersonate`);
        const { access_token, user } = response.data;
        impersonationParentToken = parent;
        setAccessToken(access_token);
        setImpersonating(true);
        set({ user, isAuthenticated: true, impersonation: { targetName: userName } });
        // Fetch the target's full profile (profile_picture etc.), same as login.
        try {
          const me = await apiClient.get('/auth/me');
          set((state) => ({ user: { ...state.user!, ...me.data } }));
        } catch {
          // Non-fatal — the list payload already populated the essentials.
        }
      },

      // #370: end the impersonation session and return to the admin account.
      // Guarded so a banner click + an impersonation:expired event collapse into
      // one execution instead of racing on impersonationParentToken.
      stopImpersonation: async () => {
        if (stopImpersonationPromise) return stopImpersonationPromise;
        if (!get().impersonation) return;

        stopImpersonationPromise = (async () => {
          // End server-side while the impersonation token is still active (the
          // read-only middleware whitelists this one write). Best-effort.
          try {
            await apiClient.post('/admin/impersonate/end');
          } catch {
            // Ignore — we restore the admin session regardless.
          }
          setImpersonating(false);
          setAccessToken(impersonationParentToken);
          impersonationParentToken = null;
          set({ impersonation: null });
          // Restore the admin identity.
          try {
            const me = await apiClient.get('/auth/me');
            set({ user: me.data, isAuthenticated: true });
          } catch {
            // If the admin token is no longer valid, fall back to a clean logout.
            await get().logout();
          }
        })().finally(() => {
          stopImpersonationPromise = null;
        });
        return stopImpersonationPromise;
      },

      isImpersonating: () => get().impersonation !== null,

      hydrate: async () => {
        // Called once on app start. If the persist storage claims we were
        // authenticated, try a silent refresh via the HttpOnly cookie; if
        // successful, re-fetch the profile and unlock the UI.
        const { user } = get();
        if (!user) {
          // Nothing persisted → fresh visit, just unlock the UI.
          set({ isHydrating: false });
          return;
        }

        const token = await tryRefreshSession();
        if (!token) {
          // Refresh cookie gone/expired → wipe persisted user
          set({ user: null, isAuthenticated: false, isHydrating: false });
          try {
            useAuthStore.persist.clearStorage();
          } catch {
            // noop
          }
          return;
        }

        try {
          const meResponse = await apiClient.get('/auth/me');
          set({
            user: meResponse.data,
            isAuthenticated: true,
            isHydrating: false,
          });
        } catch {
          setAccessToken(null);
          set({ user: null, isAuthenticated: false, isHydrating: false });
          try {
            useAuthStore.persist.clearStorage();
          } catch {
            // noop
          }
        }
      },
    }),
    {
      name: 'auth-storage',
      // profile_picture is deliberately excluded — it can be ~500 KB base64
      // and exhausts localStorage quota on admin machines. Re-fetched via
      // /auth/me during hydrate().
      partialize: (state) => ({
        user: state.user
          ? { ...state.user, profile_picture: null }
          : null,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);

// Global listener: when the refresh interceptor gives up, clear auth state.
// This ensures every tab in the same window coordinates via one code path.
//
// Defense-in-depth (paired with the /auth/logout interceptor guard): a single
// broken session can fire MANY 'auth:session-expired' events nearly at once —
// e.g. the dashboard's 7 parallel requests all fail the shared refresh together.
// The re-entrancy flag collapses such a burst into ONE logout; otherwise each
// event would POST /auth/logout again, amplifying the storm. The `!user` check
// drops events that arrive after we're already logged out (stale in-flight reqs).
if (typeof window !== 'undefined') {
  let loggingOut = false;
  window.addEventListener('auth:session-expired', () => {
    if (loggingOut || !useAuthStore.getState().user) return;
    loggingOut = true;
    void useAuthStore
      .getState()
      .logout()
      .finally(() => {
        loggingOut = false;
      });
  });

  // #370: an impersonation token hit a 401 (expired / revoked). It is not
  // refreshable, so return to the admin session instead of logging out.
  let returning = false;
  window.addEventListener('impersonation:expired', () => {
    if (returning || !useAuthStore.getState().isImpersonating()) return;
    returning = true;
    void useAuthStore
      .getState()
      .stopImpersonation()
      .finally(() => {
        returning = false;
      });
  });
}
