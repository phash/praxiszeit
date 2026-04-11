import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import apiClient, { setAccessToken, tryRefreshSession } from '../api/client';

interface User {
  id: string;
  username: string;
  email: string | null;
  first_name: string;
  last_name: string;
  role: 'admin' | 'employee';
  weekly_hours: number;
  work_days_per_week: number;
  vacation_days: number;
  calendar_color: string;
  track_hours: boolean;
  is_active: boolean;
  totp_enabled: boolean;
  profile_picture?: string | null;
  created_at: string;
  use_daily_schedule: boolean;
  hours_monday: number | null;
  hours_tuesday: number | null;
  hours_wednesday: number | null;
  hours_thursday: number | null;
  hours_friday: number | null;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  // True while the app is trying to silently restore a session from the
  // HttpOnly refresh cookie on first load. UI must gate routing on this.
  isHydrating: boolean;
  login: (username: string, password: string, totpCode?: string) => Promise<void>;
  logout: () => Promise<void>;
  setTokens: (accessToken: string, user: User) => void;
  setUser: (user: User) => void;
  hydrate: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isHydrating: true,

      login: async (username: string, password: string, totpCode?: string) => {
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
if (typeof window !== 'undefined') {
  window.addEventListener('auth:session-expired', () => {
    void useAuthStore.getState().logout();
  });
}
