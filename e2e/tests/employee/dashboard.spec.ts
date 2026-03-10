import { test, expect } from '../../fixtures/base.fixture';

test.describe('Employee Dashboard', () => {
  test('shows monthly balance card', async ({ employeePage }) => {
    await expect(employeePage.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(employeePage.getByText('Monatssaldo')).toBeVisible();
    await expect(employeePage.getByText('Soll:')).toBeVisible();
    await expect(employeePage.getByText('Ist:')).toBeVisible();
  });

  test('shows overtime account card', async ({ employeePage }) => {
    await expect(employeePage.getByText('Überstundenkonto')).toBeVisible();
    await expect(employeePage.getByText('Kumulierter Saldo')).toBeVisible();
  });

  test('shows vacation account card', async ({ employeePage }) => {
    await expect(employeePage.getByText('Urlaubskonto')).toBeVisible();
    await expect(employeePage.getByText('Budget:')).toBeVisible();
    await expect(employeePage.getByText('Genommen:')).toBeVisible();
  });

  test('stamp widget: clock in and out', async ({ employeePage }) => {
    // Should start as "Nicht eingestempelt"
    await expect(employeePage.getByText('Nicht eingestempelt')).toBeVisible();

    // Clock in
    await employeePage.getByRole('button', { name: 'Einstempeln' }).click();

    // Wait for success toast
    await expect(employeePage.locator('[role="alert"]').filter({ hasText: 'eingestempelt' })).toBeVisible({ timeout: 10000 });

    // Check clocked-in state
    await expect(employeePage.getByText(/Eingestempelt seit/)).toBeVisible();

    // Click clock out to reveal break input
    await employeePage.getByRole('button', { name: 'Ausstempeln' }).click();

    // Break input should appear
    await expect(employeePage.getByText('Pause (Min.):')).toBeVisible();

    // Click "Jetzt ausstempeln"
    await employeePage.getByRole('button', { name: 'Jetzt ausstempeln' }).click();

    // Wait for clock-out success toast
    await expect(employeePage.locator('[role="alert"]').filter({ hasText: 'ausgestempelt' })).toBeVisible({ timeout: 10000 });

    // Should be back to not clocked in
    await expect(employeePage.getByText('Nicht eingestempelt')).toBeVisible();
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
    await expect(employeePage.getByText('Geplante Abwesenheiten im Team')).toBeVisible();
  });
});
