import * as fs from 'fs';
import * as path from 'path';
import { test, expect } from '../../fixtures/base.fixture';

const API_BASE = 'http://localhost/api';
const XLS_JAN = 'E:/claude/zeiterfassung/import/timerec_20260101_20260131_e11_p03.xls';
const XLS_FEB = 'E:/claude/zeiterfassung/import/timerec_20260201_20260228_e11_p03.xls';

async function previewImport(token: string, userId: string, xlsPath: string) {
  const formData = new FormData();
  const fileBytes = fs.readFileSync(xlsPath);
  const blob = new Blob([fileBytes], { type: 'application/vnd.ms-excel' });
  formData.append('file', blob, path.basename(xlsPath));
  formData.append('user_id', userId);
  const res = await fetch(`${API_BASE}/admin/import/preview`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!res.ok) throw new Error(`Preview failed: ${res.status} ${await res.text()}`);
  return res.json();
}

test.describe('Admin XLS Import', () => {

  // ── API Tests ─────────────────────────────────────────────────────────────

  test('API: preview gibt Einträge für Januar-XLS zurück', async ({ testEmployee, adminApi }) => {
    test.slow();
    const preview = await previewImport(adminApi.token, testEmployee.id, XLS_JAN);
    expect(preview.total).toBeGreaterThan(0);
    expect(preview.entries).toHaveLength(preview.total);
    expect(preview.conflicts).toBe(0);
    const e = preview.entries[0];
    expect(e.date).toMatch(/^2026-01-/);
    expect(e.start_time).toBeTruthy();
    expect(e.end_time).toBeTruthy();
    expect(e.has_conflict).toBe(false);
    expect(e.break_minutes).toBeGreaterThanOrEqual(0);
  });

  test('API: confirm importiert Januar-XLS vollständig', async ({ testEmployee, adminApi }) => {
    test.slow();
    const preview = await previewImport(adminApi.token, testEmployee.id, XLS_JAN);
    const result = await adminApi.post('/admin/import/confirm', {
      user_id: testEmployee.id,
      overwrite: false,
      entries: preview.entries,
      filename: path.basename(XLS_JAN),
    });
    expect(result.imported).toBe(preview.total);
    expect(result.skipped).toBe(0);
    expect(result.overwritten).toBe(0);
  });

  test('API: zweiter Import überspringt alle (kein overwrite)', async ({ testEmployee, adminApi }) => {
    test.slow();
    const preview1 = await previewImport(adminApi.token, testEmployee.id, XLS_JAN);
    await adminApi.post('/admin/import/confirm', {
      user_id: testEmployee.id, overwrite: false,
      entries: preview1.entries, filename: path.basename(XLS_JAN),
    });

    const preview2 = await previewImport(adminApi.token, testEmployee.id, XLS_JAN);
    expect(preview2.conflicts).toBe(preview1.total);

    const result2 = await adminApi.post('/admin/import/confirm', {
      user_id: testEmployee.id, overwrite: false,
      entries: preview2.entries, filename: path.basename(XLS_JAN),
    });
    expect(result2.skipped).toBe(preview1.total);
    expect(result2.imported).toBe(0);
  });

  test('API: overwrite überschreibt bestehende Einträge', async ({ testEmployee, adminApi }) => {
    test.slow();
    const preview1 = await previewImport(adminApi.token, testEmployee.id, XLS_JAN);
    await adminApi.post('/admin/import/confirm', {
      user_id: testEmployee.id, overwrite: false,
      entries: preview1.entries, filename: path.basename(XLS_JAN),
    });

    const preview2 = await previewImport(adminApi.token, testEmployee.id, XLS_JAN);
    const result2 = await adminApi.post('/admin/import/confirm', {
      user_id: testEmployee.id, overwrite: true,
      entries: preview2.entries, filename: path.basename(XLS_JAN),
    });
    expect(result2.overwritten).toBe(preview1.total);
    expect(result2.skipped).toBe(0);
  });

  test('API: Februar-XLS nach Januar hat keine Konflikte', async ({ testEmployee, adminApi }) => {
    test.slow();
    const jan = await previewImport(adminApi.token, testEmployee.id, XLS_JAN);
    await adminApi.post('/admin/import/confirm', {
      user_id: testEmployee.id, overwrite: false,
      entries: jan.entries, filename: path.basename(XLS_JAN),
    });

    const feb = await previewImport(adminApi.token, testEmployee.id, XLS_FEB);
    expect(feb.total).toBeGreaterThan(0);
    expect(feb.conflicts).toBe(0);

    const result = await adminApi.post('/admin/import/confirm', {
      user_id: testEmployee.id, overwrite: false,
      entries: feb.entries, filename: path.basename(XLS_FEB),
    });
    expect(result.imported).toBe(feb.total);
  });

  // ── UI Tests ──────────────────────────────────────────────────────────────

  test('UI: Import-Link in der Admin-Sidebar sichtbar', async ({ adminPage }) => {
    await adminPage.goto('/admin/import');
    await expect(adminPage.getByRole('link', { name: 'Import' })).toBeVisible();
  });

  test('UI: Wizard durchläuft alle 3 Schritte', async ({ adminPage, testEmployee }) => {
    test.slow();
    await adminPage.goto('/admin/import');
    await expect(adminPage.getByRole('heading', { name: 'XLS-Import' })).toBeVisible();

    // Step 1: Benutzer auswählen + Datei hochladen
    const select = adminPage.locator('select');
    await select.focus();
    await adminPage.waitForTimeout(800);
    await select.selectOption({ value: testEmployee.id });

    await adminPage.locator('input[type="file"]').setInputFiles(XLS_JAN);
    await expect(adminPage.getByText('timerec_20260101_20260131_e11_p03.xls')).toBeVisible();

    await adminPage.getByRole('button', { name: /Datei analysieren/ }).click();

    // Step 2: Vorschau
    await expect(adminPage.getByRole('heading', { name: 'Vorschau' })).toBeVisible({ timeout: 20000 });
    await expect(adminPage.getByText('Einträge gefunden')).toBeVisible();
    await expect(adminPage.locator('table')).toBeVisible();

    await adminPage.getByRole('button', { name: /Import bestätigen/ }).click();

    // Step 3: Ergebnis
    await expect(adminPage.getByRole('heading', { name: 'Import abgeschlossen' })).toBeVisible({ timeout: 20000 });
    await expect(adminPage.getByText('Importiert')).toBeVisible();
    await expect(adminPage.getByText('Import wurde im Änderungsprotokoll gespeichert')).toBeVisible();

    // Reset
    await adminPage.getByRole('button', { name: /Weiteren Import starten/ }).click();
    await expect(adminPage.getByText('Datei hochladen')).toBeVisible();
  });

});
