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
    caption: 'Das Dashboard einer Mitarbeiterin: Monatssaldo, Überstundenkonto und Urlaubskonto auf einen Blick.',
    shot: {
      id: 'br-uebersicht',
      persona: 'sarah',
      viewport: 'desktop',
      route: '/',
      crop: 'main',
      markers: [
        { n: 1, id: 'monatssaldo', locator: { role: 'heading', name: 'Monatssaldo', exact: true }, badge: 'top' },
        { n: 2, id: 'ueberstunden', locator: { role: 'heading', name: 'Überstundenkonto', exact: true }, badge: 'top' },
        { n: 3, id: 'urlaubskonto', locator: { role: 'heading', name: 'Urlaubskonto', exact: true }, badge: 'top' },
      ],
      alt: 'Dashboard einer Mitarbeiterin mit laufender Stempelkarte und den Kacheln Monatssaldo, Überstundenkonto und Urlaubskonto mit Pluswerten',
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
      // Stand = erster Montag ab Stichtag + 35 Tagen: dort beginnen die Arbeitszeit-Blöcke aller Demo-Personen (Seed `team_blocks_effective`)
      prepare: [
        { fill: { label: 'Stand am', within: 'main' }, value: '{{montag+35d}}' },
        { waitFor: { text: 'Meyer, Julia', within: 'main' } },
      ],
      crop: { mainTo: ['julia'], pad: 32 },
      markers: [
        { n: 1, id: 'stand-am', locator: { label: 'Stand am', within: 'main' }, badge: 'left' },
        { n: 2, id: 'besetzung', locator: { css: 'main >> text=Besetzung >> visible=true' }, badge: 'right' },
        { n: 3, id: 'julia', locator: { css: "main >> text='Meyer, Julia'" }, badge: 'right' },
      ],
      alt: 'Übersicht „Arbeitszeiten im Team“ mit den Arbeitszeit-Blöcken der Mitarbeitenden als Balken von Montag bis Freitag und der Besetzungszeile darüber',
    },
  },
  {
    section: 'urlaub',
    caption: 'Der Abwesenheitskalender des Teams: Feiertage und Abwesenheiten auf einen Blick, jede Person mit Kürzel und Kalenderfarbe.',
    shot: {
      id: 'br-urlaub',
      persona: 'maria',
      viewport: 'desktop',
      route: '/absences',
      prepare: [{ click: { role: 'button', name: 'Nächster Monat', exact: true, within: 'main' } }],
      crop: 'main',
      markers: [],
      alt: 'Abwesenheitskalender des Teams im November mit farbigen Kürzeln der abwesenden Personen an den Tagen der Teamklausur und dem beschrifteten Feiertag Allerheiligen',
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
