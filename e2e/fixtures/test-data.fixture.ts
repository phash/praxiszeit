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

/**
 * Endgültiges Aufräumen eines Testkontos (DSGVO Art. 17 „purge").
 *
 * ``DELETE /admin/users/{id}`` **deaktiviert** nur — die Benutzerzeile bleibt
 * mitsamt ihren automatisch eingebuchten Betriebsferien-Abwesenheiten stehen
 * (``admin_users._enroll_user_in_open_closures`` läuft bei JEDER Neuanlage), und
 * seit dem Release-Review 1.16.0 nimmt der Jahresexport **inaktive** Mitarbeiter
 * mit Daten bewusst auf (§16: der Beleg gilt fürs Jahr, nicht für den heutigen
 * Personalstand). Jedes je angelegte Testkonto landete damit dauerhaft im
 * Export: 735 Karteileichen, 750 statt 16 Mitarbeiterblätter, 56 s Laufzeit
 * gegen ein 60-s-Timeout in ``admin/reports.spec.ts``.
 *
 * Der einzige echte Löschpfad ist ``DELETE /admin/users/{id}/purge``. Der prüft
 * aber die ArbZG-§16-Aufbewahrungsfrist (730 Tage ab der jüngsten Aufzeichnung)
 * und antwortet sonst mit 409 — ein sekundenaltes Testkonto mit Closure-
 * Abwesenheit fällt genau in diese Sperre. Deshalb in dieser Reihenfolge:
 *
 *   1. Zeiteinträge + Abwesenheiten des Kontos über die App löschen
 *      (danach ist die Frist gegenstandslos: es gibt keine Aufzeichnung mehr),
 *   2. deaktivieren (Vorbedingung des Purge),
 *   3. purgen — der Endpunkt räumt Anträge, Schichtzuweisungen, Prüfprotokoll-
 *      Verweise usw. selbst auf (deshalb API statt SQL).
 *
 * Best effort: wirft nie. Ein fehlgeschlagenes Teardown darf keinen grünen
 * Test nachträglich rot färben — der schlimmste Fall ist eine Karteileiche
 * mehr, also exakt der Zustand vor dieser Vorrichtung.
 */
export async function purgeUser(adminApi: ApiHelper, userId: string): Promise<void> {
  const drain = async (listPath: string, deletePath: (id: string) => string) => {
    // Die Listen-Endpunkte cappen bei limit=500; in Runden leeren, bis nichts
    // mehr kommt (Schleifendeckel gegen einen Endpunkt, der trotz Löschung
    // weiter Zeilen liefert).
    for (let round = 0; round < 20; round++) {
      let rows: any[];
      try {
        rows = await adminApi.get(`${listPath}?user_id=${userId}&limit=500`);
      } catch {
        return;
      }
      if (!Array.isArray(rows) || rows.length === 0) return;
      let deleted = 0;
      for (const row of rows) {
        try {
          await adminApi.delete(deletePath(row.id));
          deleted++;
        } catch { /* schon weg */ }
      }
      if (deleted === 0) return;
    }
  };

  await drain('/time-entries/', (id) => `/admin/time-entries/${id}`);
  await drain('/absences/', (id) => `/absences/${id}`);

  try {
    await adminApi.delete(`/admin/users/${userId}`);
  } catch { /* bereits deaktiviert */ }
  try {
    await adminApi.delete(`/admin/users/${userId}/purge`);
  } catch { /* z.B. 409: noch aufbewahrungspflichtige Daten — dann bleibt das Konto inaktiv stehen */ }
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
  /**
   * Legt einen zusätzlichen Mitarbeiter an (für Tests, denen die eine
   * ``testEmployee``-Zeile nicht reicht: Tagesplan, Minijob/MiLoG, Kind-krank,
   * De-/Reaktivieren). Teardown purged ihn — siehe ``purgeUser``.
   * Gibt die Benutzerzeile zurück (``response.user ?? response``).
   */
  createUser: (data: Record<string, unknown>) => Promise<any>;
};

export const testDataTest = authTest.extend<TestDataFixtures>({
  testEmployee: async ({ adminApi }, use, testInfo) => {
    testUserCounter++;
    // #451-Folgefix: `testUserCounter` ist ein PROZESSLOKALER Zähler — mit
    // `workers: 2` startet jeder Worker-Prozess unabhängig bei 0. Der
    // Benutzername trug schon `Date.now()` (worker-übergreifend eindeutig
    // genug), der Nachname aber nur den nackten Zähler (`User1`, `User2`, …)
    // — zwei Worker konnten so gleichzeitig einen exakt gleich benannten
    // "Test User1" anlegen. Der Zuweisungsdialog in shift-planning.spec.ts
    // listet mandantenweit ALLE Mitarbeitenden und matcht über
    // `${first_name} ${last_name}\b` → strict-mode-Verstoß (zwei Treffer).
    // Ein einmal gebildeter, gemeinsamer eindeutiger Teil für Username UND
    // Nachname behebt das an der Quelle. Bewusst nur Ziffern + Unterstrich
    // (kein Trennzeichen, das eine Regex sprengen könnte) — mehrere Specs
    // bauen aus `last_name` ein Suchmuster (`new RegExp(...)`) oder einen
    // CSS-Attribut-Selektor (`[aria-label*="..."]`); Sonderzeichen dort
    // wären ein neuer, subtilerer Bruch.
    // #461 K-8: `workerIndex` mit hinein. `Date.now()` + prozesslokaler Zähler
    // kollidieren weiterhin, wenn zwei Worker in DERSELBEN Millisekunde je
    // ihren ersten Benutzer anlegen (→ 400 "Benutzername bereits vergeben").
    // Der Worker-Index ist über den Lauf hinweg eindeutig und bleibt
    // ziffernsicher — die Specs bauen aus `last_name` Regexe und
    // CSS-Attribut-Selektoren, Sonderzeichen wären dort ein neuer Bruch.
    const unique = `${Date.now()}_${testInfo.workerIndex}_${testUserCounter}`;
    const username = `e2e_test_${unique}`;
    const password = 'TestPass123!';
    const userData = {
      username,
      password,
      first_name: 'Test',
      last_name: `User${unique}`,
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

    // Teardown: Konto endgültig löschen, nicht nur deaktivieren — siehe purgeUser.
    await purgeUser(adminApi, userId);
  },

  createUser: async ({ adminApi }, use) => {
    const createdIds: string[] = [];
    const factory = async (data: Record<string, unknown>) => {
      const response = await adminApi.post('/admin/users', data);
      const created = (response as any).user ?? response;
      if (created?.id) createdIds.push(created.id);
      return created;
    };
    await use(factory);
    for (const id of createdIds) {
      await purgeUser(adminApi, id);
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
