import { expect } from '@playwright/test';
import { test } from '../../fixtures/base.fixture';

/**
 * #376 Kind krank (§45 SGB V): a custom "unpaid_free" reason that tracks a
 * yearly limit. Booking over the limit must produce a SOFT, non-blocking
 * CHILD_SICK_LIMIT warning — the absence is still created (the excused day
 * must be recordable even when Kinderkrankengeld no longer applies).
 *
 * API-driven end-to-end (real nginx → backend → Postgres, real JWT). Fully
 * isolated + self-cleaning: it creates its OWN ephemeral employee (no
 * employment window, no pre-existing absences) and removes the employee,
 * reason and booked absences in teardown. Runs against the frontend /api
 * proxy (E2E_API_BASE overrides the port when :80 is taken).
 */
test.describe('#376 Kind krank soft limit', () => {
  test('booking over the yearly cap warns but still books the day', async ({ adminApi, createUser }) => {
    // Two past weekdays in the same year; a fresh user has no window + no
    // conflicting absences on them.
    const DAY1 = '2026-03-02'; // Montag
    const DAY2 = '2026-03-03'; // Dienstag

    const stamp = Date.now();
    let empId: string | undefined;
    let reasonId: string | undefined;
    const createdAbsenceIds: string[] = [];

    try {
      // dedicated ephemeral employee (no first_work_day → window open)
      const created = await createUser({
        username: `e2e-childsick-${stamp}`,
        first_name: 'E2E', last_name: 'ChildSick',
        password: 'E2ePass1234!',
        role: 'employee', weekly_hours: 40, vacation_days: 30, work_days_per_week: 5,
        child_sick_days_per_year: 1, // cap = 1 day
      });
      empId = created.id;

      // activate a Kind-krank reason (unpaid_free + tracks the limit)
      const reason = await adminApi.post('/admin/absence-reasons', {
        name: `E2E Kind krank ${stamp}`,
        base_behavior: 'unpaid_free',
        tracks_child_sick_limit: true,
        color: '#e67e22',
      });
      reasonId = reason.id;

      // Day 1 — reaches the cap (used 1 of 1) → NO warning
      const r1 = await adminApi.post('/absences/', {
        user_id: empId, date: DAY1, type: 'other', hours: 8, reason_id: reasonId,
      });
      (Array.isArray(r1) ? r1 : []).forEach((a: { id: string }) => createdAbsenceIds.push(a.id));
      const warn1 = (Array.isArray(r1) ? r1 : []).flatMap((a: { warnings?: string[] }) => a.warnings ?? []);
      expect(warn1.some((w) => w.includes('CHILD_SICK_LIMIT'))).toBe(false);

      // Day 2 — over the cap (used 2 of 1) → soft warning, but STILL created
      const r2 = await adminApi.post('/absences/', {
        user_id: empId, date: DAY2, type: 'other', hours: 8, reason_id: reasonId,
      });
      const rows2 = Array.isArray(r2) ? r2 : [];
      rows2.forEach((a: { id: string }) => createdAbsenceIds.push(a.id));
      expect(rows2.length, 'the over-limit day is still booked').toBeGreaterThan(0);
      const warn2 = rows2.flatMap((a: { warnings?: string[] }) => a.warnings ?? []);
      expect(warn2.some((w) => w.includes('CHILD_SICK_LIMIT'))).toBe(true);
    } finally {
      for (const id of createdAbsenceIds) await adminApi.delete(`/absences/${id}`).catch(() => {});
      if (reasonId) await adminApi.delete(`/admin/absence-reasons/${reasonId}`).catch(() => {});
      // Das Konto räumt die createUser-Fixture endgültig ab (purge statt deaktivieren).
    }
  });
});
