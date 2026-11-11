import type { ShotDef } from '../types';

/** Probe-Aufnahme fuer die Aufnahme-Kette (Task 6); Task 8 loescht sie. */
export const PROBE_SHOTS: ShotDef[] = [
  {
    id: 'probe-zeiterfassung',
    persona: 'maria',
    viewport: 'desktop',
    route: '/time-tracking',
    crop: 'main',
    markers: [
      { n: 1, id: 'neu', locator: { role: 'button', name: 'Neuer Eintrag', exact: true, within: 'main' } },
      { n: 2, id: 'monat-zurueck', locator: { role: 'button', name: 'Vorheriger Monat', exact: true, within: 'main' } },
    ],
    alt: 'Seite Zeiterfassung mit dem Knopf „Neuer Eintrag“ und der Monatsauswahl über der Liste der Zeiteinträge',
  },
];
