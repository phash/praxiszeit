import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import apiClient from '../api/client';

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
  is_active: boolean;
  totp_enabled: boolean;
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
  accessToken: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string, totpCode?: string) => Promise<void>;
  logout: () => void;
  setTokens: (accessToken: string, user: User) => void;
  setUser: (user: User) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      isAuthenticated: false,

      login: async (username: string, password: string, totpCode?: string) => {
        const body: Record<string, unknown> = { username, password };
        if (totpCode) body.totp_code = totpCode;

        const response = await apiClient.post('/auth/login', body);
        const { access_token, user } = response.data;

        // F-010: refresh token is now an HttpOnly cookie – only store access token
        localStorage.setItem('access_token', access_token);

        set({
          user,
          accessToken: access_token,
          isAuthenticated: true,
        });
      },

      logout: () => {
        // Clear access token from localStorage
        localStorage.removeItem('access_token');
        localStorage.removeItem('auth-storage');

        // Clear service worker caches (security: remove any cached API data)
        if ('caches' in window) {
          caches.keys().then((names) => {
            names.forEach((name) => caches.delete(name));
          });
        }

        set({
          user: null,
          accessToken: null,
          isAuthenticated: false,
        });
      },

      setTokens: (accessToken: string, user: User) => {
        localStorage.setItem('access_token', accessToken);
        set({ user, accessToken, isAuthenticated: true });
      },

      setUser: (user: User) => {
        set({ user });
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
