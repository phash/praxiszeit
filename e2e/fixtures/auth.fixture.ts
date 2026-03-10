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
      await use(api);
    },
    { scope: 'worker' },
  ],

  adminPage: async ({ adminApi, page }, use) => {
    // Inject the already-valid admin token — no extra login call needed
    await page.addInitScript(({ token, user }) => {
      localStorage.setItem('access_token', token);
      localStorage.setItem(
        'auth-storage',
        JSON.stringify({
          state: { user, isAuthenticated: true },
          version: 0,
        })
      );
    }, { token: adminApi.token, user: adminApi.userData });
    await page.goto('/');
    await page.waitForURL('/');
    await use(page);
  },
});
