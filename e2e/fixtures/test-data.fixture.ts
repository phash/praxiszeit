import { Page } from '@playwright/test';
import { ApiHelper } from '../helpers/api.helper';
import { authTest } from './auth.fixture';

let testUserCounter = 0;

interface TestUser {
  id: string;
  username: string;
  password: string;
  first_name: string;
  last_name: string;
}

interface EmployeeLogin {
  api: ApiHelper;
  access_token: string;
  user: any;
}

export type TestDataFixtures = {
  testEmployee: TestUser;
  testEmployeeLogin: EmployeeLogin;
  employeePage: Page;
  employeeApi: ApiHelper;
  createTimeEntry: (userId: string, data: {
    date: string;
    start_time: string;
    end_time: string;
    break_minutes?: number;
    note?: string;
  }) => Promise<any>;
  createAbsence: (data: {
    date: string;
    end_date?: string;
    type: string;
    hours: number;
    note?: string;
    user_id?: string;
  }) => Promise<any>;
  createChangeRequest: (data: Record<string, unknown>) => Promise<any>;
  createVacationRequest: (data: {
    date: string;
    end_date?: string;
    hours: number;
    note?: string;
  }) => Promise<any>;
};

export const testDataTest = authTest.extend<TestDataFixtures>({
  testEmployee: async ({ adminApi }, use) => {
    testUserCounter++;
    const username = `e2e_test_${Date.now()}_${testUserCounter}`;
    const password = 'TestPass123!';
    const userData = {
      username,
      password,
      first_name: 'Test',
      last_name: `User${testUserCounter}`,
      role: 'employee',
      weekly_hours: 40,
      work_days_per_week: 5,
      vacation_days: 30,
      track_hours: true,
    };
    const response = await adminApi.post('/admin/users', userData);
    const createdUser = response.user ?? response;
    const userId = createdUser.id;

    await use({
      id: userId,
      username,
      password,
      first_name: userData.first_name,
      last_name: userData.last_name,
    });

    // Teardown: deactivate user
    try {
      await adminApi.delete(`/admin/users/${userId}`);
    } catch {
      // already deactivated
    }
  },

  // Single login shared between employeePage and employeeApi — halves login API calls
  testEmployeeLogin: async ({ testEmployee }, use) => {
    const api = new ApiHelper();
    const loginData = await api.login(testEmployee.username, testEmployee.password);
    // #132: the role-specific onboarding modal renders a full-screen overlay
    // (bg-black/40, z-50) for users with onboarding_completed_at == null and
    // intercepts ALL pointer events (logout button, forms, …). Fresh E2E users
    // always hit it, which made every post-login interaction time out. Mark it
    // complete server-side (idempotent — same call the modal's close button
    // makes) and reflect it in the seeded user so the modal never renders.
    await api.post('/auth/onboarding/complete').catch(() => {});
    if (loginData.user) loginData.user.onboarding_completed_at = new Date().toISOString();
    await use({ api, access_token: loginData.access_token, user: loginData.user });
  },

  employeePage: async ({ browser, testEmployeeLogin }, use) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    const { api, user } = testEmployeeLogin;

    // F-023: Reuse the refresh_token captured by testEmployeeLogin's
    // Node-side login and seed it into this fresh BrowserContext.
    // hydrate() then restores the in-memory access token on mount —
    // no second login, no rate-limit issue.
    if (!api.refreshCookie) {
      throw new Error('testEmployeeLogin did not capture a refresh cookie');
    }
    await context.addCookies([
      {
        name: 'refresh_token',
        value: api.refreshCookie,
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
    }, user);

    await page.goto('/');
    await page.waitForURL('/');
    await use(page);
    await context.close();
  },

  employeeApi: async ({ testEmployeeLogin }, use) => {
    // Reuse the same ApiHelper instance — no second login call
    await use(testEmployeeLogin.api);
  },

  createTimeEntry: async ({ adminApi }, use) => {
    const createdIds: string[] = [];
    const factory = async (userId: string, data: any) => {
      const entry = await adminApi.post(`/admin/users/${userId}/time-entries`, data);
      createdIds.push(entry.id);
      return entry;
    };
    await use(factory);
    for (const id of createdIds) {
      try {
        await adminApi.delete(`/admin/time-entries/${id}`);
      } catch { /* already deleted */ }
    }
  },

  createAbsence: async ({ employeeApi, adminApi }, use) => {
    const createdIds: string[] = [];
    const factory = async (data: any) => {
      const api = data.user_id ? adminApi : employeeApi;
      const result = await api.post('/absences', data);
      const absences = Array.isArray(result) ? result : [result];
      for (const a of absences) createdIds.push(a.id);
      return result;
    };
    await use(factory);
    for (const id of createdIds) {
      try {
        await adminApi.delete(`/absences/${id}`);
      } catch { /* already deleted */ }
    }
  },

  createChangeRequest: async ({ employeeApi, adminApi }, use) => {
    const createdIds: string[] = [];
    const factory = async (data: Record<string, unknown>) => {
      const result = await employeeApi.post('/change-requests', data);
      if (result?.id) createdIds.push(result.id);
      return result;
    };
    await use(factory);
    for (const id of createdIds) {
      try {
        await adminApi.delete(`/admin/change-requests/${id}`);
      } catch { /* already resolved or deleted */ }
    }
  },

  // VacationRequests don't share /absences cleanup; the admin endpoint
  // ``DELETE /admin/vacation-requests/{id}`` deletes pending rows and
  // withdraws still-future approved ones, so it's a safe one-shot teardown
  // even after a test has approved or rejected the request mid-run.
  createVacationRequest: async ({ employeeApi, adminApi }, use) => {
    const createdIds: string[] = [];
    const factory = async (data: {
      date: string;
      end_date?: string;
      hours: number;
      note?: string;
    }) => {
      const result = await employeeApi.post('/vacation-requests', data);
      if (result?.id) createdIds.push(result.id);
      return result;
    };
    await use(factory);
    for (const id of createdIds) {
      try {
        await adminApi.delete(`/admin/vacation-requests/${id}`);
      } catch { /* already withdrawn / not found */ }
    }
  },
});
