# E2E Tests – New Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** E2E-Abdeckung für vier neue Features aus Commit 3d61853: Admin-Einstellungsseite (#41), OVERTIME-Abwesenheit (#36), Profilbild-Upload (#30), Arbeitstag-Grenzen (#29).

**Architecture:** Playwright E2E-Tests (TypeScript). Neue Tests werden in bestehende `spec.ts`-Dateien eingebettet oder als neue Dateien angelegt. Auth via API-Login → localStorage (bereits etabliertes Muster). Kein Mocking – echte Backend-Requests.

**Tech Stack:** Playwright, TypeScript, `import { test, expect } from '../../fixtures/base.fixture'`, Fixtures: `adminPage`, `adminApi`, `testEmployee`, `employeePage`, `employeeApi`, `createAbsence`

---

## Context: Wie E2E-Tests hier funktionieren

**Ausführen (aus `e2e/`-Verzeichnis):**
```bash
cd E:\claude\zeiterfassung\praxiszeit\e2e
npx playwright test tests/admin/settings.spec.ts --project=chromium
npx playwright test tests/employee/absences.spec.ts --project=chromium
# Alle neuen Tests:
npx playwright test --project=chromium --grep "Settings|OVERTIME|Profilbild|Arbeitstag"
```

**Standard-Import:**
```typescript
import { test, expect } from '../../fixtures/base.fixture';
```

**Verfügbare Fixtures:**
- `adminPage` – Browser als Admin eingeloggt
- `adminApi` – API-Client als Admin (hat `.get()`, `.post()`, `.put()`, `.delete()`)
- `testEmployee` – Frisch erstellter Testmitarbeiter `{ id, username, password, first_name, last_name }`
- `employeePage` – Browser als testEmployee eingeloggt
- `employeeApi` – API-Client als testEmployee
- `createAbsence(data)` – Erstellt Abwesenheit + Auto-Cleanup

**Toast-Selektor (Erfolg/Fehler):**
```typescript
adminPage.locator('[role="alert"]').filter({ hasText: 'Text' })
```

**Timeout für API-Antworten:** `{ timeout: 10000 }` bei `toBeVisible()`

**Einzelnen Test ausführen:**
```bash
npx playwright test tests/admin/settings.spec.ts -g "zeigt Bundesland" --project=chromium
```

**Sichtbarkeit prüfen ohne zu failen:**
```typescript
const visible = await locator.isVisible({ timeout: 2000 }).catch(() => false);
```

---

## Task 1: `e2e/tests/admin/settings.spec.ts` – Admin-Einstellungsseite (#41)

**Files:**
- Create: `e2e/tests/admin/settings.spec.ts`

**Was die Seite macht** (`frontend/src/pages/admin/Settings.tsx`):
- Route: `/admin/settings`
- Heading: `"Einstellungen"`
- Bundesland-Section: `<select id="holiday-state">` mit allen 16 deutschen Bundesländern
- Speichern-Button für Bundesland → PUT `/admin/settings/holiday_state` → Toast: `"Bundesland aktualisiert. Feiertage wurden neu berechnet."`
- Urlaubsgenehmigung-Toggle: `role="switch"` → PUT `/admin/settings/vacation_approval_required` → Toast: `"Urlaubsgenehmigung-Einstellung gespeichert."`
- Speichern-Button ist `disabled` wenn Wert unverändert

**Step 1: Testdatei anlegen**

```typescript
import { test, expect } from '../../fixtures/base.fixture';

test.describe('Admin Einstellungen', () => {
  test.slow();

  test.beforeEach(async ({ adminPage }) => {
    await adminPage.goto('/admin/settings');
    await expect(adminPage.getByRole('heading', { name: 'Einstellungen' })).toBeVisible();
  });

  test('zeigt Bundesland-Dropdown mit allen Optionen', async ({ adminPage }) => {
    const select = adminPage.locator('#holiday-state');
    await expect(select).toBeVisible();
    // 16 Bundesländer müssen geladen sein
    const options = select.locator('option');
    await expect(options).toHaveCount(16);
    // Bayern muss eine Option sein
    await expect(select.locator('option[value="Bayern"]')).toBeAttached();
  });

  test('speichert Bundesland und zeigt Erfolgstoast', async ({ adminPage, adminApi }) => {
    const select = adminPage.locator('#holiday-state');
    await expect(select).toBeVisible();

    // Aktuellen Wert lesen
    const currentValue = await select.inputValue();

    // Anderen Wert wählen (wenn Bayern, dann Berlin; sonst Bayern)
    const newValue = currentValue === 'Bayern' ? 'Berlin' : 'Bayern';
    await select.selectOption(newValue);

    // Speichern-Button klicken (jetzt aktiv, da Wert geändert)
    const saveBtn = adminPage.locator('button', { hasText: 'Speichern' }).first();
    await saveBtn.click();

    // Erfolgstoast prüfen
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: 'Bundesland aktualisiert' })
    ).toBeVisible({ timeout: 15000 });

    // Cleanup: Originalwert wiederherstellen
    try {
      await adminApi.put('/admin/settings/holiday_state', { value: currentValue });
    } catch { /* best effort */ }
  });

  test('Speichern-Button ist disabled wenn Wert unverändert', async ({ adminPage }) => {
    const saveBtn = adminPage.locator('button', { hasText: 'Speichern' }).first();
    // Ohne Änderung ist Button disabled
    await expect(saveBtn).toBeDisabled();
  });

  test('Urlaubsgenehmigung-Toggle ändert Zustand', async ({ adminPage, adminApi }) => {
    // Toggle finden
    const toggle = adminPage.locator('button[role="switch"]');
    await expect(toggle).toBeVisible();

    // Aktuellen Zustand lesen
    const isChecked = await toggle.getAttribute('aria-checked');

    // Toggle klicken
    await toggle.click();

    // Speichern
    const saveApprovalBtn = adminPage.locator('button', { hasText: 'Speichern' }).last();
    await saveApprovalBtn.click();

    // Erfolgstoast
    await expect(
      adminPage.locator('[role="alert"]').filter({ hasText: 'Urlaubsgenehmigung' })
    ).toBeVisible({ timeout: 10000 });

    // Cleanup: Originalzustand wiederherstellen
    try {
      await adminApi.put('/admin/settings/vacation_approval_required', {
        value: isChecked === 'true' ? 'true' : 'false',
      });
    } catch { /* best effort */ }
  });
});
```

**Step 2: Test ausführen (sollte FAIL – Datei existiert noch nicht)**

```bash
cd E:\claude\zeiterfassung\praxiszeit\e2e
npx playwright test tests/admin/settings.spec.ts --project=chromium
```
Erwartet: 4 neue Tests, alle PASS (die Seite existiert bereits)

**Step 3: Falls Fehler – typische Ursachen**
- Route `/admin/settings` nicht im Router → App.tsx/Router prüfen
- `#holiday-state` Selector falsch → In Settings.tsx nachschauen (Zeile 109: `id="holiday-state"`)
- Anzahl der Options ≠ 16 → `holiday_service.SUPPORTED_STATES` hat 16 Einträge

**Step 4: Commit**

```bash
git add e2e/tests/admin/settings.spec.ts
git commit -m "test(e2e): add admin settings page tests (#41)"
```

---

## Task 2: `e2e/tests/employee/absences.spec.ts` – OVERTIME-Abwesenheit (#36)

**Files:**
- Modify: `e2e/tests/employee/absences.spec.ts` (2 neue Tests anhängen)

**Was zu testen ist:**
- Overtime-Option ist schon teilweise getestet (Option existiert) – jetzt: Eintrag tatsächlich erstellen
- Employee erstellt Überstundenausgleich → erscheint in der Liste mit Label "Überstundenausgleich"

**Step 1: Bestehende Datei lesen**

```bash
# Letzte Zeile der Datei prüfen
tail -5 E:\claude\zeiterfassung\praxiszeit\e2e\tests\employee\absences.spec.ts
```
Die Datei endet mit `});` – neue Tests VOR der letzten `});` einfügen, also innerhalb von `test.describe`.

**Step 2: 2 neue Tests anhängen** (VOR dem letzten `});` der `test.describe`-Klammer)

```typescript
  test('erstellt Überstundenausgleich-Abwesenheit', async ({ employeePage, adminApi, testEmployee }) => {
    // Form öffnen
    await employeePage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();

    // Typ auf Überstundenausgleich setzen
    const typeSelect = employeePage.locator('select').first();
    await typeSelect.selectOption('overtime');
    await expect(typeSelect).toHaveValue('overtime');

    // Datum setzen (morgigen Werktag)
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    // Wochenende überspringen
    if (tomorrow.getDay() === 6) tomorrow.setDate(tomorrow.getDate() + 2);
    if (tomorrow.getDay() === 0) tomorrow.setDate(tomorrow.getDate() + 1);
    const dateStr = tomorrow.toISOString().split('T')[0];

    const dateInput = employeePage.locator('input[type="date"]').first();
    await dateInput.fill(dateStr);

    // Speichern
    await employeePage.getByRole('button', { name: 'Eintragen' }).click();

    // Erfolgstoast
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /Abwesenheit|eingetragen|gespeichert/i })
    ).toBeVisible({ timeout: 10000 });

    // Cleanup via API
    try {
      const absences = await adminApi.get(`/admin/users/${testEmployee.id}/absences?year=${tomorrow.getFullYear()}&month=${tomorrow.getMonth() + 1}`);
      const overtimeAbsences = Array.isArray(absences) ? absences.filter((a: any) => a.type === 'overtime') : [];
      for (const a of overtimeAbsences) {
        await adminApi.delete(`/absences/${a.id}`);
      }
    } catch { /* best effort cleanup */ }
  });

  test('Überstundenausgleich erscheint als "Überstundenausgleich" in der Liste', async ({ employeePage, createAbsence, testEmployee }) => {
    // Abwesenheit per API erstellen
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    if (tomorrow.getDay() === 6) tomorrow.setDate(tomorrow.getDate() + 2);
    if (tomorrow.getDay() === 0) tomorrow.setDate(tomorrow.getDate() + 1);
    const dateStr = tomorrow.toISOString().split('T')[0];

    await createAbsence({
      date: dateStr,
      type: 'overtime',
      hours: 8,
    });

    // Seite neu laden
    await employeePage.reload();
    await employeePage.waitForLoadState('networkidle');

    // "Überstundenausgleich" in der Tabelle sehen
    const table = employeePage.locator('table');
    await expect(table.getByText('Überstundenausgleich')).toBeVisible({ timeout: 10000 });
  });
```

**Step 3: Test ausführen**

```bash
cd E:\claude\zeiterfassung\praxiszeit\e2e
npx playwright test tests/employee/absences.spec.ts --project=chromium -g "Überstundenausgleich"
```
Erwartet: 2 PASSED

**Step 4: Commit**

```bash
git add e2e/tests/employee/absences.spec.ts
git commit -m "test(e2e): add OVERTIME absence creation tests (#36)"
```

---

## Task 3: `e2e/tests/employee/profile.spec.ts` – Profilbild-Upload (#30)

**Files:**
- Modify: `e2e/tests/employee/profile.spec.ts` (3 neue Tests anhängen)
- Create: `e2e/fixtures/test-image.jpg` (kleines gültiges JPEG, Base64-encoded)

**Was das Backend erwartet:**
- Endpoint: `PUT /api/auth/profile-picture`
- Max. 500 KB, nur JPEG oder PNG
- Magic Bytes: JPEG = `\xff\xd8\xff`, PNG = `\x89PNG`
- Erfolgstoast: Irgendeine Meldung wie "Profilbild aktualisiert" (aus dem Frontend prüfen)

**Was die Frontend-Seite hat** (in `pages/Profile.tsx` nachschauen):
- `<input type="file" accept="image/jpeg,image/png">` oder ähnlich
- Erfolgsanzeige nach Upload

**Step 1: Minimales Test-JPEG erstellen**

Erstelle `e2e/fixtures/test-image.jpg` als Hilfsdatei – ein minimal gültiges JPEG (44 Bytes):

```bash
# Minimales JPEG (44 Bytes, gültig laut JFIF-Standard)
node -e "
const buf = Buffer.from([
  0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
  0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
  0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
  0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
  0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
  0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
  0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
  0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
  0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
  0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
  0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
  0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0xFB, 0xFF, 0xD9
]);
require('fs').writeFileSync('e2e/fixtures/test-image.jpg', buf);
console.log('Created test-image.jpg, size:', buf.length, 'bytes');
"
```

**Alternative (simpler):** Das Playwright-Test selbst erzeugt den Buffer zur Laufzeit mit `page.evaluate` oder schreibt eine temporäre Datei. Das ist sauberer:

**Step 2: Profile-Seite untersuchen**

Zuerst die Profile-Seite auf den genauen Selektor für den Datei-Upload prüfen:
```bash
grep -n "file\|upload\|Profilbild\|profile_picture\|profile-picture" \
  E:\claude\zeiterfassung\praxiszeit\frontend\src\pages\Profile.tsx | head -30
```

Den genauen Selector des `<input type="file">` und den Erfolgstext notieren.

**Step 3: 3 neue Tests schreiben** (VOR dem letzten `});` in profile.spec.ts)

```typescript
  test('Profilbild hochladen – gültiges JPEG', async ({ employeePage }) => {
    // Minimales gültiges JPEG erzeugen
    const jpegBytes = Buffer.from([
      0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
      0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
      0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
      0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
      0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
      0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
      0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
      0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
      0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
      0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
      0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
      0x09, 0x0A, 0x0B, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F,
      0x00, 0xFB, 0xFF, 0xD9,
    ]);

    // Datei-Input finden und Bild hochladen
    const fileInput = employeePage.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'test.jpg',
      mimeType: 'image/jpeg',
      buffer: jpegBytes,
    });

    // Erfolgstoast prüfen
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /Profilbild|aktualisiert/i })
    ).toBeVisible({ timeout: 10000 });
  });

  test('Profilbild hochladen – ungültiger Typ zeigt Fehler', async ({ employeePage }) => {
    // Ungültige Datei (kein JPEG/PNG – keine Magic Bytes)
    const invalidBytes = Buffer.from('This is not an image file content');

    const fileInput = employeePage.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'test.txt',
      mimeType: 'text/plain',
      buffer: invalidBytes,
    });

    // Fehlertoast prüfen
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /JPEG|PNG|erlaubt|Fehler/i })
    ).toBeVisible({ timeout: 10000 });
  });

  test('Profilbild hochladen – Datei zu groß zeigt Fehler', async ({ employeePage }) => {
    // 501 KB großen Puffer erstellen (> 500 KB Limit)
    // Beginnt mit JPEG Magic Bytes, dann Nullen
    const oversizeBuffer = Buffer.alloc(501 * 1024, 0);
    oversizeBuffer[0] = 0xFF;
    oversizeBuffer[1] = 0xD8;
    oversizeBuffer[2] = 0xFF;

    const fileInput = employeePage.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'too-large.jpg',
      mimeType: 'image/jpeg',
      buffer: oversizeBuffer,
    });

    // Fehlertoast prüfen
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /groß|500|KB|Limit|Fehler/i })
    ).toBeVisible({ timeout: 10000 });
  });
```

**WICHTIG:** Den genauen Toast-Text aus `frontend/src/pages/Profile.tsx` prüfen und den Regex anpassen.

**Step 4: Tests ausführen**

```bash
cd E:\claude\zeiterfassung\praxiszeit\e2e
npx playwright test tests/employee/profile.spec.ts --project=chromium -g "Profilbild"
```
Erwartet: 3 PASSED

**Step 5: Commit**

```bash
git add e2e/tests/employee/profile.spec.ts
git commit -m "test(e2e): add profile picture upload tests (#30)"
```

---

## Task 4: `e2e/tests/admin/user-management.spec.ts` – Arbeitstag-Grenzen (#29)

**Files:**
- Modify: `e2e/tests/admin/user-management.spec.ts` (2 neue Tests anhängen)

**Was zu testen ist:**
- Admin setzt `first_work_day` via API auf einen zukünftigen Termin
- Employee versucht, eine Abwesenheit VOR `first_work_day` zu erstellen → Fehlertoast
- Backend gibt HTTP 400 zurück mit Text wie `"Datum liegt vor dem ersten Arbeitstag (DD.MM.YYYY)"`
- Gleiches für `last_work_day` (nach dem letzten Arbeitstag)

**Warum via API statt UI:** Die Benutzerbearbeitungsmaske im Admin hat `first_work_day`/`last_work_day`-Felder, aber das Wichtigste ist das Validierungsverhalten auf Endpunkte für Abwesenheiten/Einträge.

**Step 1: Testen ob das Admin-Bearbeitungsformular die Felder hat**

```bash
grep -n "first_work_day\|last_work_day\|Erster Arbeitstag\|Letzter Arbeitstag" \
  E:\claude\zeiterfassung\praxiszeit\frontend\src\pages\admin\Users.tsx | head -20
```

**Step 2: 2 neue Tests am Ende der `test.describe`-Klammer anfügen** (VOR dem letzten `});`)

```typescript
  test('Abwesenheit vor erstem Arbeitstag zeigt Fehler', async ({ adminApi, employeePage, testEmployee }) => {
    // first_work_day auf übermorgen setzen (Grenztag liegt in der Zukunft)
    const futureDate = new Date();
    futureDate.setDate(futureDate.getDate() + 30);
    const futureDateStr = futureDate.toISOString().split('T')[0];

    await adminApi.put(`/admin/users/${testEmployee.id}`, {
      first_work_day: futureDateStr,
    });

    // Employee navigiert zu Abwesenheiten
    await employeePage.goto('/absences');
    await employeePage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();

    // Versucht, heute eine Abwesenheit zu erstellen (liegt vor first_work_day)
    const today = new Date().toISOString().split('T')[0];
    const dateInput = employeePage.locator('input[type="date"]').first();
    await dateInput.fill(today);

    await employeePage.getByRole('button', { name: 'Eintragen' }).click();

    // Fehlertoast prüfen
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /ersten Arbeitstag|Datum liegt vor/i })
    ).toBeVisible({ timeout: 10000 });

    // Cleanup: Grenze wieder entfernen
    try {
      await adminApi.put(`/admin/users/${testEmployee.id}`, { first_work_day: null });
    } catch { /* best effort */ }
  });

  test('Abwesenheit nach letztem Arbeitstag zeigt Fehler', async ({ adminApi, employeePage, testEmployee }) => {
    // last_work_day auf gestern setzen
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const yesterdayStr = yesterday.toISOString().split('T')[0];

    await adminApi.put(`/admin/users/${testEmployee.id}`, {
      last_work_day: yesterdayStr,
    });

    // Employee versucht, heute eine Abwesenheit einzutragen
    await employeePage.goto('/absences');
    await employeePage.getByRole('button', { name: 'Abwesenheit eintragen' }).click();

    const today = new Date().toISOString().split('T')[0];
    const dateInput = employeePage.locator('input[type="date"]').first();
    await dateInput.fill(today);

    await employeePage.getByRole('button', { name: 'Eintragen' }).click();

    // Fehlertoast prüfen
    await expect(
      employeePage.locator('[role="alert"]').filter({ hasText: /letzten Arbeitstag|Datum liegt nach/i })
    ).toBeVisible({ timeout: 10000 });

    // Cleanup
    try {
      await adminApi.put(`/admin/users/${testEmployee.id}`, { last_work_day: null });
    } catch { /* best effort */ }
  });
```

**Step 3: Tests ausführen**

```bash
cd E:\claude\zeiterfassung\praxiszeit\e2e
npx playwright test tests/admin/user-management.spec.ts --project=chromium -g "Arbeitstag"
```
Erwartet: 2 PASSED

**Step 4: Alle neuen Tests zusammen ausführen**

```bash
cd E:\claude\zeiterfassung\praxiszeit\e2e
npx playwright test tests/admin/settings.spec.ts tests/employee/absences.spec.ts tests/employee/profile.spec.ts tests/admin/user-management.spec.ts --project=chromium
```
Erwartet: ~11 neue Tests PASSED (4 + 2 + 3 + 2)

**Step 5: Commit**

```bash
git add e2e/tests/admin/user-management.spec.ts
git commit -m "test(e2e): add work day boundary validation tests (#29)"
```

---

## Task 5: Gesamte E2E-Suite ausführen

**Files:** Keine Änderungen

**Step 1: Vollständige Suite prüfen**

```bash
cd E:\claude\zeiterfassung\praxiszeit\e2e
npx playwright test --project=chromium
```

Erwartet: ~97+ Tests gesamt, davon ~6 bekannte Skips (Enum-Bug + Pydantic-Bug aus früherer Session).

**Bekannte Skips (nicht beheben):**
- `admin/change-requests.spec.ts`: 2 Tests skip (DB enum case mismatch)
- `admin/vacation-approvals.spec.ts`: Mehrere Tests skip (gleicher Bug)
- `employee/change-requests.spec.ts`: 2 Tests skip (Pydantic v2 Bug)

**Step 2: Falls neue Tests failen**

Typische Ursachen und Fixes:
- **Toast-Text stimmt nicht:** Echten Text aus Frontend-Quellcode lesen und Regex anpassen
- **Selector nicht gefunden:** `await employeePage.pause()` einfügen um UI manuell zu inspizieren
- **Timeout:** `test.slow()` am Anfang des `describe`-Blocks ergänzen
- **401 Unauthorized:** Auth-Fixtures prüfen, evtl. Rate-Limiting (Login 5/min)

**Step 3: Final Commit (falls nötig)**

```bash
git add -A
git commit -m "test(e2e): fix E2E suite after new feature tests"
```

---

## Erfolgskriterien

- ~11 neue Tests grün
- Bestehende 81+ Tests unberührt
- Bekannte Skips (6) bleiben unverändert
- Keine Änderungen an Produktionscode
