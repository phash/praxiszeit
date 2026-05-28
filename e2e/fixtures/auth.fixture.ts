import { test as base, Page } from '@playwright/test';
import { ApiHelper } from '../helpers/api.helper';

const ADMIN_USER = 'admin';
const ADMIN_PASS = 'Admin2025!';

export type AuthFixtures = {
  adminPage: Page;
  adminApi: ApiHelper;
};

export const authTest = base.extend<AuthFixtures, { adminApi: ApiHelper }>({
  // Worker-scoped: login once per worker, share token across all tests in that worker
  adminApi: [
    async ({}, use) => {
      const api = new ApiHelper();
      await api.login(ADMIN_USER, ADMIN_PASS);
      // #132: ensure the onboarding modal (full-screen overlay) never blocks
      // admin interactions on a fresh DB where the bootstrap admin still has
      // onboarding_completed_at == null. Idempotent; best-effort.
      await api.post('/auth/onboarding/complete').catch(() => {});
      if (api.userData) api.userData.onboarding_completed_at = new Date().toISOString();
      await use(api);
    },
    { scope: 'worker' },
  ],

  adminPage: async ({ adminApi, context, page }, use) => {
    // F-023: The frontend no longer reads the access token from
    // localStorage — it lives in module memory only. To seed an
    // authenticated session we piggy-back on the Node-side login that
    // the worker-scoped `adminApi` fixture already did:
    //
    //   1. Copy the captured refresh_token cookie into this Playwright
    //      BrowserContext (one real login per worker — respects the
    //      5/minute rate limit).
    //   2. Persist `user + isAuthenticated` in the zustand persist
    //      slot so authStore.hydrate() thinks we were logged in.
    //   3. On first mount hydrate() calls tryRefreshSession() — the
    //      refresh cookie is there, backend issues a fresh access
    //      token, the frontend pushes it into memory.
    if (!adminApi.refreshCookie) {
      throw new Error('adminApi.login() did not capture a refresh cookie');
    }
    await context.addCookies([
      {
        name: 'refresh_token',
        value: adminApi.refreshCookie,
        url: 'http://localhost/api/auth/refresh',
        httpOnly: true,
        sameSite: 'Lax',
      },
    ]);
    await page.addInitScript((user) => {
      localStorage.setItem(
        'auth-storage',
        JSON.stringify({
          state: { user, isAuthenticated: true },
          version: 0,
        })
      );
    }, adminApi.userData);

    await page.goto('/');
    await page.waitForURL('/');
    await use(page);
  },
});
