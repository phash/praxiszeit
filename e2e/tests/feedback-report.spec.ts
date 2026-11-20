import { readFile } from 'node:fs/promises';
import { test, expect } from '../fixtures/base.fixture';
import type { Page } from '@playwright/test';

/**
 * #557: „Problem melden" — Vorschau und „Als Datei speichern".
 * Es wird nie gesendet (der E2E-Stack hat keinen Meldeschlüssel und keinen
 * Zugang nach außen).
 */
async function openFeedbackDialog(page: Page) {
  await page.getByRole('button', { name: 'Hilfe öffnen' }).click();
  await page.getByRole('button', { name: /Fehler melden \/ Feedback/ }).click();
  const dialog = page.getByRole('dialog', { name: 'Problem melden' });
  await expect(dialog).toBeVisible();
  return dialog;
}

test.describe('Problem melden', () => {
  test('employee: preview masks e-mail, save as file downloads sanitized text', async ({ employeePage }) => {
    await employeePage.goto('/');
    const dialog = await openFeedbackDialog(employeePage);

    await dialog.getByLabel('Titel').fill('E2E Meldung Vorschau');
    await dialog
      .getByLabel('Beschreibung')
      .fill('Fehler beim Stempeln, Rueckfrage an test.person@example.invalid bitte.');
    await dialog.getByRole('button', { name: 'Vorschau' }).click();

    const pre = dialog.getByTestId('feedback-preview-description');
    await expect(pre).toContainText('---- Kontext (automatisch) ----');
    await expect(pre).toContainText('<email>');
    await expect(pre).not.toContainText('test.person@example.invalid');

    const downloadPromise = employeePage.waitForEvent('download');
    await dialog.getByRole('button', { name: 'Als Datei speichern' }).click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toMatch(/^praxiszeit-meldung-\d{8}-\d{4}\.txt$/);
    const path = await download.path();
    const content = await readFile(path, 'utf-8');
    expect(content).toContain('<email>');
    expect(content).not.toContain('test.person@example.invalid');
    expect(content).not.toContain('mrk_');
  });

  test('admin: log extract checkbox is checked and preview contains the log section', async ({ adminPage }) => {
    const dialog = await openFeedbackDialog(adminPage);

    const checkbox = dialog.getByLabel('Protokollauszug anhängen (bereinigt)');
    await expect(checkbox).toBeVisible();
    await expect(checkbox).toBeChecked();

    await dialog.getByLabel('Titel').fill('E2E Admin Vorschau');
    await dialog.getByLabel('Beschreibung').fill('Pruefung des Protokollauszugs.');
    await dialog.getByRole('button', { name: 'Vorschau' }).click();

    await expect(dialog.getByTestId('feedback-preview-description')).toContainText(
      'Protokoll (bereinigt, letzte',
    );
  });
});
