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
    await use({ api, access_token: loginData.access_token, user: loginData.user });
  },

  employeePage: async ({ browser, testEmployeeLogin }, use) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    const { access_token, user } = testEmployeeLogin;

    // Inject token before navigation — single goto instead of two
    await page.addInitScript(({ token, user }) => {
      localStorage.setItem('access_token', token);
      localStorage.setItem(
        'auth-storage',
        JSON.stringify({
          state: { user, isAuthenticated: true },
          version: 0,
        })
      );
    }, { token: access_token, user });

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
});
