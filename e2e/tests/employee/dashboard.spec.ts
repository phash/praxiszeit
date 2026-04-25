import { test, expect } from '../../fixtures/base.fixture';

test.describe('Employee Dashboard', () => {
  // Most card-content text appears once on the dashboard but a second time
  // in the Hilfe-Sidebar (Cheat-Sheet). All assertions therefore scope to
  // <main> to avoid strict-mode violations when the sidebar's open.
  test('shows monthly balance card', async ({ employeePage }) => {
    const main = employeePage.locator('main');
    await expect(main.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(main.getByText('Monatssaldo')).toBeVisible();
    await expect(main.getByText('Soll:')).toBeVisible();
    await expect(main.getByText('Ist:')).toBeVisible();
  });

  test('shows overtime account card', async ({ employeePage }) => {
    const main = employeePage.locator('main');
    await expect(main.getByText('Überstundenkonto')).toBeVisible();
    await expect(main.getByText('Kumulierter Saldo')).toBeVisible();
  });

  test('shows vacation account card', async ({ employeePage }) => {
    const main = employeePage.locator('main');
    await expect(main.getByText('Urlaubskonto')).toBeVisible();
    await expect(main.getByText('Budget:')).toBeVisible();
    await expect(main.getByText('Genommen:')).toBeVisible();
  });

  test('stamp widget: clock in and out', async ({ employeePage }) => {
    const main = employeePage.locator('main');
    // "Nicht eingestempelt" appears twice on the dashboard: once as <p> in
    // the StampWidget, once as <span> in the today-progress status pill.
    // Both are inside <main>, so scope to the StampWidget's <p> tag
    // explicitly via element + text.
    const stampStatus = main.locator('p').filter({ hasText: /^Nicht eingestempelt$/ });
    await expect(stampStatus).toBeVisible();

    // Clock in
    await main.getByRole('button', { name: 'Einstempeln' }).click();

    // Wait for success toast
    await expect(employeePage.locator('[role="alert"]').filter({ hasText: 'eingestempelt' })).toBeVisible({ timeout: 10000 });

    // Check clocked-in state (fetchStatus() is called after toast, needs extra time)
    await expect(main.getByText(/Eingestempelt seit/)).toBeVisible({ timeout: 10000 });

    // Click clock out to reveal break input
    await main.getByRole('button', { name: 'Ausstempeln' }).click();

    // Break input should appear
    await expect(main.getByText('Pause (Min.):')).toBeVisible();

    // Click "Jetzt ausstempeln"
    await main.getByRole('button', { name: 'Jetzt ausstempeln' }).click();

    // Wait for clock-out success toast
    await expect(employeePage.locator('[role="alert"]').filter({ hasText: 'ausgestempelt' })).toBeVisible({ timeout: 10000 });

    // Should be back to not clocked in — stamp widget renders the <p>
    await expect(main.locator('p').filter({ hasText: /^Nicht eingestempelt$/ })).toBeVisible();
  });

  test('monthly overview table visible', async ({ employeePage, testEmployee, createTimeEntry }) => {
    // Create a time entry so the overtime history has data
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    // Find a recent weekday
    while (yesterday.getDay() === 0 || yesterday.getDay() === 6) {
      yesterday.setDate(yesterday.getDate() - 1);
    }
    const dateStr = yesterday.toISOString().split('T')[0];
    await createTimeEntry(testEmployee.id, {
      date: dateStr,
      start_time: '09:00',
      end_time: '17:00',
      break_minutes: 30,
    });

    await employeePage.reload();
    await employeePage.waitForLoadState('networkidle');

    // The monthly overview table should be visible if there is overtime history
    await expect(employeePage.getByText('Monatsübersicht')).toBeVisible({ timeout: 10000 });
  });

  test('team absences calendar visible', async ({ employeePage }) => {
    await employeePage.waitForLoadState('networkidle');
    // Team calendar is inside the "Details" toggle section - expand it first
    await employeePage.getByRole('button', { name: /Details anzeigen/ }).click();
    await expect(employeePage.getByText('Geplante Abwesenheiten im Team')).toBeVisible({ timeout: 10000 });
  });
});
