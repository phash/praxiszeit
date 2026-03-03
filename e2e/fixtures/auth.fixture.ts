import { test as base, Page } from '@playwright/test';
import { ApiHelper } from '../helpers/api.helper';

const ADMIN_USER = 'admin';
const ADMIN_PASS = 'Admin2025!';

async function loginViaApi(page: Page, username: string, password: string) {
  const api = new ApiHelper();
  const { access_token, user } = await api.login(username, password);

  await page.goto('/');
  await page.evaluate(
    ({ token, user }) => {
      localStorage.setItem('access_token', token);
      localStorage.setItem(
        'auth-storage',
        JSON.stringify({
          state: { user, isAuthenticated: true },
          version: 0,
        })
      );
    },
    { token: access_token, user }
  );
  await page.goto('/');
  await page.waitForURL('/');
}

export type AuthFixtures = {
  adminPage: Page;
  adminApi: ApiHelper;
};

export const authTest = base.extend<AuthFixtures>({
  adminPage: async ({ page }, use) => {
    await loginViaApi(page, ADMIN_USER, ADMIN_PASS);
    await use(page);
  },
  adminApi: async ({}, use) => {
    const api = new ApiHelper();
    await api.login(ADMIN_USER, ADMIN_PASS);
    await use(api);
  },
});
