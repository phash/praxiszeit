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
const SHIFT_PLANNING_SPECS = [
  'admin/shift-planning.spec.ts',
  'admin/shift-planning-m2.spec.ts',
  'admin/shift-planning-followups.spec.ts',
  'admin/shift-planning-visibility.spec.ts',
];
const SHIFT_PLANNING_FLAG_OFF_SPEC = 'admin/shift-planning-flag-off.spec.ts';

export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
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
      testIgnore: [...SHIFT_PLANNING_SPECS, SHIFT_PLANNING_FLAG_OFF_SPEC],
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
  ],
});
