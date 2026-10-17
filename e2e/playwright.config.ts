import { defineConfig } from '@playwright/test';

// #451: die vier "echten" Schichtplanungs-Specs schalten die mandantenweite
// Einstellung `shift_planning_enabled` nicht mehr selbst — global-setup.ts/
// global-teardown.ts sind der einzige Besitzer für den gesamten Lauf (siehe
// deren Kommentare).
//
// Der eine bewusst negative Test ("feature hidden + endpoints 404 when flag
// is off", shift-planning-flag-off.spec.ts) MUSS das Flag zwischenzeitlich
// abschalten, um genau das zu belegen. Zwei Varianten wurden erprobt:
//
// 1. Im selben Projekt mitlaufen lassen und das Flag im `finally` sofort
//    wieder einschalten (kleines, aber reales Zeitfenster). In der Erprobung
//    genügte dieses eine verbliebene Zeitfenster bereits einmal, um eine
//    PARALLEL laufende Spec (shift-planning-followups.spec.ts) mit genau dem
//    404 zu treffen, den #451 beheben soll — nur an einer von statt elf
//    Stellen, aber nicht bei null.
// 2. Ein eigenes Playwright-Projekt für genau diesen einen Test, das per
//    `dependencies` GARANTIERT erst startet, nachdem die vier anderen Specs
//    (Projekt "shift-planning") vollständig durchgelaufen sind — kein
//    Worker kann ihm mehr in die Quere kommen. Nebenwirkung: Playwright
//    überspringt ALLE Tests eines abhängigen Projekts, sobald das
//    Dependency-Projekt einen (auch unabhängigen) Fehlschlag hat — der
//    Flag-Aus-Test zeigt dann "did not run" statt eines eigenen Ergebnisses.
//
// Variante 2 gewinnt: ein übersprungener Test bei einem BEREITS roten Lauf
// ist ein selbsterklärendes, harmloses Bild (der Build war ohnehin schon
// rot); ein durch Variante 1 spontan rot werdender, VÖLLIG UNBETEILIGTER
// Test sieht dagegen exakt wie die irreführende Regression aus, die dieses
// Ticket beheben soll — nur seltener. Determinismus schlägt hier ein kleines,
// weiterhin nicht-null Restrisiko.
//
// #461 K-8: Muster statt handgepflegter Dateiliste. Eine kuenftige
// `shift-planning-*.spec.ts` fiel vorher still NICHT in das Projekt
// "shift-planning" — sie lief stattdessen im Projekt "chromium" mit, also
// ohne die Serialisierung gegenueber dem Flag-Aus-Test, und brachte genau die
// 404-Wettlaeufe zurueck, die #451 beseitigt hat.
const SHIFT_PLANNING_FLAG_OFF_SPEC = /admin[\\/]shift-planning-flag-off\.spec\.ts$/;
const SHIFT_PLANNING_SPECS = /admin[\\/]shift-planning(?!-flag-off)[^\\/]*\.spec\.ts$/;
const ALL_SHIFT_PLANNING_SPECS = /admin[\\/]shift-planning[^\\/]*\.spec\.ts$/;

// Review Task 22 (Arbeitszeit-Blöcke), dasselbe Muster für den mandantenweiten
// Puffer `work_window_grace_minutes`: grace-setting.spec.ts schaltet ihn für
// einige Sekunden um, work-blocks.spec.ts rechnet seine erwarteten Werte mit
// dem Puffer 15 (Anlegen und Neukappung lesen den AKTUELLEN Mandantenwert).
// Im selben Projekt liefen beide Dateien bei `workers: 2` gleichzeitig — die
// Puffer-Spec startet deshalb erst, wenn das ganze Projekt "chromium" fertig
// ist.
//
// Gesamtreview 1.20 (B9): dasselbe galt für die Genehmigungspflicht
// (`vacation_approval_required`, vacation-approvals.spec.ts, settings.spec.ts
// und zwei Tests aus employee/absences.spec.ts), das Bundesland
// (`holiday_state`, settings.spec.ts — löscht und erzeugt die Feiertage neu)
// und den #314-Schalter (`closure_overtime_after_vacation`). Alle Specs, die
// eine mandantenweite Einstellung umschalten, liegen jetzt in
// tests/tenant-settings/ — Muster statt Dateiliste (#461 K-8): eine neue Spec
// dort fällt automatisch ins Folgeprojekt. Das Projekt läuft erst nach
// "chromium" und mit `workers: 1`: zwei seiner Dateien schalten sonst
// gegeneinander (die Bundesland-Umschaltung neben einem Urlaubsantrag). Die
// Genehmigungspflicht steht im Projekt "chromium" durchgehend auf dem Wert aus
// global-setup.ts (`false`).
const TENANT_SETTINGS_SPECS = /tests[\\/]tenant-settings[\\/][^\\/]*\.spec\.ts$/;

export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  // #461 W-2: Deckel ueber den GESAMTEN Lauf. Ohne ihn haengt ein Host, der die
  // Verbindung annimmt aber nie antwortet, unbegrenzt im "global setup" — ohne
  // Ausgabe, ohne Abbruch.
  globalTimeout: 60 * 60_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: 2,
  reporter: [['html', { open: 'never' }], ['list']],
  globalSetup: require.resolve('./global-setup'),
  globalTeardown: require.resolve('./global-teardown'),
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    locale: 'de-DE',
    timezoneId: 'Europe/Berlin',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
      testIgnore: [ALL_SHIFT_PLANNING_SPECS, TENANT_SETTINGS_SPECS],
    },
    {
      name: 'shift-planning',
      use: { browserName: 'chromium' },
      testMatch: SHIFT_PLANNING_SPECS,
    },
    {
      name: 'shift-planning-flag-off',
      use: { browserName: 'chromium' },
      testMatch: SHIFT_PLANNING_FLAG_OFF_SPEC,
      // Startet garantiert erst, nachdem alle vier "echten" Schichtplanungs-
      // Specs (Projekt "shift-planning") vollständig durchgelaufen sind —
      // siehe die Abwägung oben.
      dependencies: ['shift-planning'],
    },
    {
      name: 'tenant-settings',
      use: { browserName: 'chromium' },
      testMatch: TENANT_SETTINGS_SPECS,
      // Startet garantiert erst, nachdem das ganze Projekt "chromium"
      // durchgelaufen ist, und fährt seine Dateien einzeln nacheinander —
      // siehe TENANT_SETTINGS_SPECS oben. Nebenwirkung wie beim Flag-Aus-Test:
      // ein Fehlschlag in "chromium" lässt diese Tests als "did not run" stehen.
      // Die Schichtplanungs-Projekte laufen weiter daneben: keine dieser
      // Einstellungen wirkt auf sie (der Generator liest Abwesenheiten, keine
      // Feiertage, und die Specs buchen keinen Urlaub).
      dependencies: ['chromium'],
      workers: 1,
    },
  ],
});
