import type { BroschuereShot } from '../types';

/**
 * Echte Screenshots der Vertriebsbroschüre (pzweb /broschuere), je Abschnitt einer.
 * Reine Daten (Ruling R5). Höchstens 3 Markierungen, keine Schritte — die Zahlen im Bild genügen.
 */
export const BROSCHUERE_SHOTS: BroschuereShot[] = [
  {
    section: 'stempeln',
    caption: 'Die Stempeluhr auf dem Smartphone: Arbeitszeit des Tages auf einen Blick, Ausstempeln mit einem Tipp.',
    shot: {
      id: 'br-stempeln',
      persona: 'maria',
      viewport: 'mobile',
      route: '/',
      prepare: [
        { click: { role: 'button', name: 'Eingestempelt – Stempeluhr öffnen', exact: true } },
        { waitFor: { text: 'Arbeitszeit heute', within: 'dialog' } },
      ],
      crop: 'full',
      markers: [],
      alt: 'Stempeluhr auf dem Smartphone mit der Arbeitszeit des heutigen Tages und dem Knopf „Ausstempeln“ für laufenden Eintrag',
    },
  },
  {
    section: 'uebersicht',
    caption: 'Das Dashboard einer Mitarbeiterin: Stempelkarte, Monatssaldo, Überstundenkonto und Urlaubskonto.',
    shot: {
      id: 'br-uebersicht',
      persona: 'maria',
      viewport: 'desktop',
      route: '/',
      crop: 'main',
      markers: [
        { n: 1, id: 'stempelkarte', locator: { role: 'button', name: 'Ausstempeln', exact: true, within: 'main' }, badge: 'left' },
        { n: 2, id: 'ueberstunden', locator: { role: 'heading', name: 'Überstundenkonto', exact: true }, badge: 'top' },
        { n: 3, id: 'urlaubskonto', locator: { role: 'heading', name: 'Urlaubskonto', exact: true }, badge: 'top' },
      ],
      alt: 'Dashboard einer Mitarbeiterin mit Stempelkarte, Monatssaldo, Überstundenkonto und Urlaubskonto in Kacheln',
    },
  },
  {
    section: 'team',
    caption: 'Arbeitszeiten im Team: die Arbeitszeit-Blöcke aller Mitarbeitenden als Balken, darüber die Besetzung je halbe Stunde.',
    shot: {
      id: 'br-team',
      persona: 'admin',
      viewport: 'desktop',
      route: '/admin/team-schedule',
      crop: 'main',
      markers: [
        { n: 1, id: 'stand-am', locator: { label: 'Stand am', within: 'main' }, badge: 'left' },
        { n: 2, id: 'besetzung', locator: { css: 'main >> text=Besetzung >> visible=true' }, badge: 'right' },
        { n: 3, id: 'sarah', locator: { css: "main >> text='Klein, Sarah'" }, badge: 'right' },
      ],
      alt: 'Übersicht „Arbeitszeiten im Team“ mit den Arbeitszeit-Blöcken aller Mitarbeitenden als Balken von Montag bis Freitag und der Besetzungszeile',
    },
  },
  {
    section: 'urlaub',
    caption: 'Der Abwesenheitskalender des Teams: Urlaub, Fortbildung und Feiertage im Monat.',
    shot: {
      id: 'br-urlaub',
      persona: 'maria',
      viewport: 'desktop',
      route: '/absences',
      crop: 'main',
      markers: [],
      alt: 'Abwesenheitskalender des Teams im Monat mit farbigen Kreisen für Urlaub und Fortbildung sowie beschrifteten Feiertagen',
    },
  },
  {
    section: 'nachweise',
    caption: 'Berichte und Export: Monatsreport als Excel, ODS oder PDF, auf Wunsch mit Krankheitsdaten.',
    shot: {
      id: 'br-nachweise',
      persona: 'admin',
      viewport: 'desktop',
      route: '/admin/reports',
      crop: 'main',
      markers: [
        { n: 1, id: 'monat', locator: { css: "main input[type='month']" }, badge: 'left' },
        { n: 2, id: 'formate', locator: { role: 'button', name: 'PDF (.pdf)', exact: true, within: 'main' }, badge: 'right' },
        { n: 3, id: 'ausgeblendete', locator: { css: "label[for='export-hidden-month']" }, badge: 'left' },
      ],
      alt: 'Berichte und Export mit Monatswahl und den Knöpfen für Excel, ODS und PDF zum Monatsreport der Praxis',
    },
  },
];
