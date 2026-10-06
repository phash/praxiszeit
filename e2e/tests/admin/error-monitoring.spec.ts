import { test, expect } from '../../fixtures/base.fixture';

test.describe('Admin Error Monitoring', () => {
  test('page loads with heading and tabs', async ({ adminPage }) => {
    await adminPage.goto('/admin/errors');
    await expect(adminPage.getByRole('heading', { name: 'Fehler-Monitoring' })).toBeVisible();

    // Check that status filter tabs exist (use the tab bar container)
    // The tabs are: Alle, Offen (may have count badge), Ignoriert, Behoben
    const tabBar = adminPage.locator('.flex.space-x-1.mb-6');
    await expect(tabBar.getByText('Alle')).toBeVisible();
    await expect(tabBar.getByText('Offen')).toBeVisible();
    await expect(tabBar.getByText('Ignoriert')).toBeVisible();
    await expect(tabBar.getByText('Behoben')).toBeVisible();

    // Check that the refresh button exists
    await expect(adminPage.getByRole('button', { name: 'Aktualisieren' })).toBeVisible();
  });

  test('status filter tabs switch correctly', async ({ adminPage }) => {
    await adminPage.goto('/admin/errors');
    await expect(adminPage.getByRole('heading', { name: 'Fehler-Monitoring' })).toBeVisible();
    await adminPage.waitForLoadState('networkidle');

    // Use the tab bar to find the correct buttons
    const tabBar = adminPage.locator('.flex.space-x-1.mb-6');

    // Click through each tab
    await tabBar.getByText('Alle').click();
    await adminPage.waitForLoadState('networkidle');
    await expect(adminPage.getByRole('heading', { name: 'Fehler-Monitoring' })).toBeVisible();

    await tabBar.getByText('Ignoriert').click();
    await adminPage.waitForLoadState('networkidle');
    await expect(adminPage.getByRole('heading', { name: 'Fehler-Monitoring' })).toBeVisible();

    await tabBar.getByText('Behoben').click();
    await adminPage.waitForLoadState('networkidle');
    await expect(adminPage.getByRole('heading', { name: 'Fehler-Monitoring' })).toBeVisible();

    await tabBar.getByText('Offen').click();
    await adminPage.waitForLoadState('networkidle');
    await expect(adminPage.getByRole('heading', { name: 'Fehler-Monitoring' })).toBeVisible();
  });

  /**
   * Legt die Voraussetzung der beiden folgenden Tests an: EINEN offenen
   * Fehlereintrag.
   *
   * Fehlereinträge entstehen ausschließlich über die Fehler-Middleware — es
   * gibt (bewusst) keinen Endpunkt zum Anlegen. Der Auslöser ist deshalb ein
   * echter Serverfehler.
   *
   * Bis 1.19.2 war das eine Ressourcen-ID, die keine UUID ist (Postgres:
   * `invalid input syntax for type uuid` → 500). Genau diese Antwort hat #483
   * zu einer sauberen 422 gemacht — der Test hat das vorausgesagt und ist
   * daran rot geworden. Ein anderer Validierungsfehler als Ersatz wäre nur der
   * nächste Bug, den irgendwann jemand behebt.
   *
   * Jetzt: das Kundenportal der Zahlungsabwicklung auf einer Instanz OHNE
   * Stripe-Konfiguration. `POST /api/billing/portal` antwortet dort mit 503
   * „Zahlungsabwicklung nicht konfiguriert" — ein Betriebszustand, kein
   * Programmfehler, und der Eintrag trägt den Mandanten des Admins (die
   * Anfrage ist authentifiziert), ist in seinem Fehler-Monitoring also
   * sichtbar. Der Pfad ist fest, der Eintrag aggregiert deshalb; beide Tests
   * räumen ihn im `finally` wieder weg, und ein erledigter Eintrag aggregiert
   * nicht weiter (ein neuer Fehler legt eine neue offene Zeile an).
   *
   * Ist Stripe auf der Zielinstanz konfiguriert, schlägt die erste Zusicherung
   * mit einer Meldung fehl, die genau darauf zeigt.
   */
  async function provokeError(adminApi: any): Promise<{ id: string; path: string }> {
    const probe = '/billing/portal';
    const res = await adminApi.postRaw(probe, { return_url: 'http://localhost/e2e' });
    expect(
      res.status,
      `Voraussetzung: POST ${probe} muss auf einer Instanz ohne Stripe-Konfiguration mit 503 antworten, ` +
      `damit ein Eintrag im Fehler-Monitoring entsteht. Ist Stripe hier konfiguriert, braucht dieser Test einen anderen Auslöser.`
    ).toBe(503);

    const errors = await adminApi.get('/admin/errors/?status=open&limit=200');
    const row = errors.find((e: any) => e.path === `/api${probe}`);
    expect(row, 'Voraussetzung: der Serverfehler muss im Fehler-Monitoring gelandet sein').toBeTruthy();
    return row;
  }

  // Vorher stand am Ende dieses Tests wörtlich `expect(hasNoErrors || true)` —
  // ein Ausdruck, der nicht fehlschlagen KANN. Ohne vorhandenen Fehlereintrag
  // prüfte der Test also gar nichts, und ob überhaupt je einer da war, hing am
  // Zufall des Datenbestands.
  test('resolve button marks an error as resolved', async ({ adminPage, adminApi }) => {
    const err = await provokeError(adminApi);

    try {
      await adminPage.goto('/admin/errors');
      await expect(adminPage.getByRole('heading', { name: 'Fehler-Monitoring' })).toBeVisible();

      // Auf "Alle" wechseln — sonst fällt die Zeile durch das Erledigen aus dem
      // Filter "Offen" und der Statuswechsel wäre nicht mehr nachprüfbar.
      const tabBar = adminPage.locator('.flex.space-x-1.mb-6');
      await tabBar.getByText('Alle').click();
      await adminPage.waitForLoadState('networkidle');

      // Genau die Karte DIESES Fehlers (der Pfad steht in der Kopfzeile)
      const card = adminPage.locator('div.bg-white').filter({ hasText: err.path }).last();
      await expect(card).toBeVisible({ timeout: 10000 });
      await card.locator('button[title="Als behoben markieren"]').click();

      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: /Status/ })
      ).toBeVisible({ timeout: 10000 });

      // Der Status muss wirklich umgesprungen sein: die Karte bietet danach
      // "Wieder öffnen" an und nicht mehr "Als behoben markieren".
      await expect(card.locator('button[title="Wieder öffnen"]')).toBeVisible({ timeout: 10000 });
      await expect(card.locator('button[title="Als behoben markieren"]')).toHaveCount(0);
    } finally {
      try { await adminApi.delete(`/admin/errors/${err.id}`); } catch { /* schon weg */ }
    }
  });

  test('delete error removes the entry', async ({ adminPage, adminApi }) => {
    const err = await provokeError(adminApi);

    try {
      await adminPage.goto('/admin/errors');
      await expect(adminPage.getByRole('heading', { name: 'Fehler-Monitoring' })).toBeVisible();

      // Show all errors (not just open)
      const tabBar = adminPage.locator('.flex.space-x-1.mb-6');
      await tabBar.getByText('Alle').click();
      await adminPage.waitForLoadState('networkidle');

      const card = adminPage.locator('div.bg-white').filter({ hasText: err.path }).last();
      await expect(card).toBeVisible({ timeout: 10000 });
      await card.locator('button[title="Löschen"]').click();

      // Confirm dialog
      const dialog = adminPage.getByRole('alertdialog');
      await expect(dialog).toBeVisible();
      await dialog.getByRole('button', { name: 'Löschen' }).click();

      // Check for success toast
      await expect(
        adminPage.locator('[role="alert"]').filter({ hasText: /gelöscht/ })
      ).toBeVisible({ timeout: 10000 });

      // Und die Karte ist wirklich fort.
      await expect(card).toHaveCount(0, { timeout: 10000 });
    } finally {
      try { await adminApi.delete(`/admin/errors/${err.id}`); } catch { /* erwartet: schon gelöscht */ }
    }
  });
});
