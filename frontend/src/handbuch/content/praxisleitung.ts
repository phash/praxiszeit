import type { Handbook, PrepareStep, ShotDef } from '../types';

/**
 * Handbuch für die Praxisleitung (Kapitel 1–17).
 * Quelle: docs/handbuch/HANDBUCH-ADMIN.md, docs/handbuch/SCHNELLSTART.md und die
 * Seiten in frontend/src/pages/admin. Reine Daten (R5). Aufgaben-IDs sind
 * Sprungmarken der Kontexthilfe – nicht umbenennen.
 */

/** Sarahs Zeile in der Benutzerverwaltung (Arbeitszeit-Dialog, Monatsjournal). */
const SARAH_HOURS = { role: 'button', name: 'Arbeitszeit & Wochenstunden für Sarah Klein', exact: true } as const;
const PETRA_HOURS = { role: 'button', name: 'Arbeitszeit & Wochenstunden für Petra Schulz', exact: true } as const;

const JULIA_HOURS = { role: 'button', name: 'Arbeitszeit & Wochenstunden für Julia Meyer', exact: true } as const;

/** Import: Petra, Beispieldatei aus e2e/test-data (Januar 2026). Die Vorschau schreibt nichts, bestätigt wird nie. */
const IMPORT_UPLOAD: PrepareStep[] = [
  { select: { css: 'main select' }, value: 'Petra Schulz (petra)' },
  { upload: { css: "main input[type='file']" }, file: 'e2e/test-data/timerec_20260101_20260131_e11_p03.xls' },
];
const IMPORT_PREVIEW: PrepareStep[] = [
  ...IMPORT_UPLOAD,
  { click: { css: "main button:has-text('Datei analysieren')" } },
  { waitFor: { css: "main >> text=/Eintr(ag|äge) gefunden/" } },
];

/** Rückwirkende Änderung für Sarah: Montag-Nachmittag endet ab Stichtag − 14 Tage um 15:30. Nur Vorschau, nie speichern. */
const RETRO_PREPARE: PrepareStep[] = [
  { click: SARAH_HOURS },
  { waitFor: { label: 'Mo Block 2 bis', within: 'dialog' } },
  { fill: { label: 'Gültig ab', within: 'dialog' }, value: '{{stichtag-14d}}' },
  { fill: { label: 'Mo Block 2 bis', within: 'dialog' }, value: '15:30' },
  // erst die Vorschau abwarten, dann die Option über ihren Text wählen (wie ein Mensch)
  { waitFor: { css: "[role='dialog'] >> text=/verlieren angerechnete Zeit/" } },
  { click: { css: "[role='dialog'] label:has-text('mit Neuberechnung') > span" } },
  { waitFor: { css: "[role='dialog'] >> text=/^Rückwirkende Änderung:/" } },
  { fill: { css: '#wh-short-reason-text' }, value: 'Der Montagnachmittag war seit der Aufstockung falsch hinterlegt (vereinbart: bis 15:30 Uhr).' },
];

const shots: ShotDef[] = [
  // ── 1. Erste Einrichtung ─────────────────────────────────────────────────
  {
    id: 'pl-navigation',
    persona: 'admin',
    viewport: 'desktop',
    route: '/',
    crop: { around: ['admin-dashboard', 'schnellstart'], pad: 24 },
    markers: [
      { n: 1, id: 'admin-dashboard', locator: { role: 'link', name: 'Admin-Dashboard', exact: true, within: 'nav' }, badge: 'right' },
      { n: 2, id: 'benutzerverwaltung', locator: { role: 'link', name: 'Benutzerverwaltung', exact: true, within: 'nav' }, badge: 'right' },
      { n: 3, id: 'team', locator: { role: 'link', name: 'Arbeitszeiten im Team', exact: true, within: 'nav' }, badge: 'right' },
      { n: 4, id: 'schnellstart', locator: { role: 'button', name: 'Schnellstart', exact: true }, badge: 'right' },
    ],
    alt: 'Seitenleiste der Praxisleitung: unter „Administration“ Admin-Dashboard, Benutzerverwaltung und Arbeitszeiten im Team, unten der Knopf „Schnellstart“',
  },
  {
    id: 'pl-bundesland',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    prepare: [{ scrollTo: { role: 'heading', name: 'Feiertage', exact: true } }],
    crop: { around: ['bundesland', 'speichern'], pad: 56 },
    markers: [
      { n: 1, id: 'bundesland', locator: { label: 'Bundesland', within: 'main' }, badge: 'left' },
      {
        n: 2,
        id: 'speichern',
        // der Speichern-Knopf direkt neben der Bundesland-Auswahl
        locator: { css: "xpath=//main//select[@id=//main//label[normalize-space()='Bundesland']/@for]/following::button[1]" },
        badge: 'right',
      },
    ],
    alt: 'Einstellungen, Abschnitt Feiertage: Auswahl des Bundeslands (Bayern) für die gesetzlichen Feiertage mit dem Knopf „Speichern“',
  },

  // ── 2. Dashboard & Teamübersicht ─────────────────────────────────────────
  {
    id: 'pl-fehlende-buchungen',
    persona: 'admin',
    viewport: 'desktop',
    route: '/',
    crop: { around: ['kasten'], pad: 24 },
    markers: [
      // Kreis an der Ecke: verdeckt nur das Warnsymbol, keinen Text
      {
        n: 1,
        id: 'kasten',
        locator: { css: "xpath=//main//h3[normalize-space()='Fehlende Buchungen im Team']/ancestor::div[contains(@class,'rounded-2xl')][1]" },
        badge: 'corner',
      },
    ],
    alt: 'Gelber Kasten „Fehlende Buchungen im Team“ auf dem Dashboard der Praxisleitung mit dem Eintrag „Thomas Bauer: 22.10.“',
  },
  {
    id: 'pl-admin-dashboard',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin',
    crop: { around: ['umschalter', 'details'], pad: 56 },
    markers: [
      { n: 1, id: 'umschalter', locator: { role: 'group', name: 'Zeitraum-Ansicht', exact: true }, badge: 'left' },
      { n: 2, id: 'monat', locator: { role: 'button', name: 'Nächster Monat', exact: true, within: 'main' }, badge: 'right' },
      { n: 3, id: 'soll-basis', locator: { css: 'main select[title^="Soll nur bis"]' }, badge: 'top' },
      { n: 4, id: 'saldo', locator: { role: 'columnheader', name: 'Saldo', exact: true }, badge: 'top' },
      // der Pfeil in der letzten Zelle der Zeile (die ganze Zeile ist der Knopf)
      { n: 5, id: 'details', locator: { css: "main tr[aria-label='Details für Hoffmann, Maria anzeigen'] td >> nth=-1" }, badge: 'left' },
    ],
    alt: 'Admin-Dashboard, Monatsübersicht Oktober: je Person Wochenstunden, Soll, Ist, Saldo, kumulierte Überstunden, Urlaub und Krank',
  },
  {
    id: 'pl-mitarbeiter-details',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin',
    prepare: [
      { click: { role: 'button', name: 'Details für Hoffmann, Maria anzeigen', exact: true } },
      { waitFor: { role: 'button', name: 'Neuer Eintrag', exact: true, within: 'dialog' } },
    ],
    crop: { around: ['kennzahlen', 'aktionen'], pad: 48 },
    markers: [
      { n: 1, id: 'kennzahlen', locator: { css: "xpath=//*[@role='dialog']//p[normalize-space()='Überstunden kum.']/ancestor::div[contains(@class,'grid')][1]" }, badge: 'left' },
      { n: 2, id: 'neuer-eintrag', locator: { role: 'button', name: 'Neuer Eintrag', exact: true, within: 'dialog' }, badge: 'left' },
      { n: 3, id: 'aktionen', locator: { css: "[role='dialog'] tbody tr >> nth=0 >> td >> nth=-1" }, badge: 'left' },
    ],
    alt: 'Detailansicht von Maria Hoffmann im Admin-Dashboard mit Benutzerinformationen, Soll, Ist, Saldo und der Liste ihrer Zeiteinträge',
  },
  {
    id: 'pl-team-arbeitszeiten',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/team-schedule',
    crop: 'main',
    markers: [
      { n: 1, id: 'stand-am', locator: { label: 'Stand am', within: 'main' }, badge: 'left' },
      { n: 2, id: 'abteilung', locator: { role: 'button', name: 'Alle', exact: true, within: 'main' }, badge: 'right' },
      { n: 3, id: 'besetzung', locator: { css: 'main >> text=Besetzung >> visible=true' }, badge: 'top' },
      { n: 4, id: 'sarah', locator: { css: "main >> text='Klein, Sarah'" }, badge: 'right' },
    ],
    alt: 'Übersicht „Arbeitszeiten im Team“: je Person die Arbeitszeit-Blöcke von Montag bis Freitag als Balken, darüber die Besetzung je halbe Stunde',
  },
  {
    id: 'pl-team-bearbeiten',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/team-schedule',
    prepare: [{ click: { role: 'switch', name: 'Bearbeiten', exact: true } }],
    crop: 'main',
    markers: [
      { n: 1, id: 'schalter', locator: { role: 'switch', name: 'Bearbeiten', exact: true }, badge: 'top' },
      { n: 2, id: 'block', locator: { css: 'main [aria-label^="Klein, Sarah · Mo 08:00"]' }, badge: 'top' },
    ],
    alt: 'Arbeitszeiten im Team mit eingeschaltetem Schieber „Bearbeiten“: Hinweis zum Ziehen der Blöcke und bei jeder Person der Link „Ändern…“',
  },

  // ── 3. Mitarbeitende anlegen, Vertragsdaten, Vertragsverlauf ─────────────
  {
    id: 'pl-benutzerliste',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/users',
    crop: 'main',
    markers: [
      // die Gruppe oben rechts: zwei Filter und der Knopf zum Anlegen
      { n: 1, id: 'kopf', locator: { css: "main label:has-text('Inaktive anzeigen') >> xpath=.." }, badge: 'left' },
      { n: 2, id: 'urlaubskonto', locator: { role: 'columnheader', name: 'Urlaubskonto', exact: true }, badge: 'top' },
      { n: 3, id: 'ueberstunden', locator: { role: 'columnheader', name: 'Überstunden (JTD)' }, badge: 'top' },
    ],
    alt: 'Benutzerverwaltung: Liste aller Mitarbeitenden mit Benutzername, Rolle, Wochenstunden, Arbeitstagen, Urlaubskonto und Überstunden seit Jahresbeginn',
  },
  {
    id: 'pl-benutzer-aktionen',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/users',
    prepare: [{ scrollTo: { css: "main tr:has-text('Klein, Sarah') button[title='Deaktivieren']" } }],
    crop: { around: ['bearbeiten', 'deaktivieren'], pad: 56 },
    markers: [
      { n: 1, id: 'journal', locator: { css: "main tr:has-text('Klein, Sarah') button[title='Monatsjournal anzeigen']" }, badge: 'left' },
      { n: 2, id: 'bearbeiten', locator: { css: "main tr:has-text('Klein, Sarah') button[title='Bearbeiten']" }, badge: 'left' },
      { n: 3, id: 'arbeitszeit', locator: SARAH_HOURS, badge: 'right' },
      { n: 4, id: 'deaktivieren', locator: { css: "main tr:has-text('Klein, Sarah') button[title='Deaktivieren']" }, badge: 'left' },
    ],
    alt: 'Aktionsspalte einer Person in der Benutzerverwaltung mit den Symbolen für Monatsjournal, Bearbeiten, Arbeitszeit und Deaktivieren',
  },
  {
    id: 'pl-neu-anlegen',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/users',
    prepare: [
      { click: { role: 'button', name: 'Neue:r Mitarbeiter:in', exact: true } },
      { fill: { label: 'Benutzername *', within: 'main' }, value: 'lena' },
      { fill: { label: 'E-Mail (optional)', within: 'main' }, value: 'lena.wagner@praxis-lindenplatz.example' },
      { fill: { label: 'Passwort *', within: 'main' }, value: 'Willkommen2026!' },
      { fill: { label: 'Vorname', within: 'main' }, value: 'Lena' },
      { fill: { label: 'Nachname', within: 'main' }, value: 'Wagner' },
      { fill: { css: '#f-weekly-hours' }, value: '30' },
      { fill: { css: '#f-work-days' }, value: '4' },
    ],
    crop: { around: ['benutzername', 'arbeitstage', 'urlaub'], pad: 80 },
    markers: [
      { n: 1, id: 'benutzername', locator: { label: 'Benutzername *', within: 'main' }, badge: 'left' },
      { n: 2, id: 'passwort', locator: { label: 'Passwort *', within: 'main' }, badge: 'top' },
      { n: 3, id: 'wochenstunden', locator: { css: '#f-weekly-hours' }, badge: 'top' },
      { n: 4, id: 'arbeitstage', locator: { css: '#f-work-days' }, badge: 'top' },
      { n: 5, id: 'urlaub', locator: { css: "main >> text=Empfehlung: >> xpath=.." }, badge: 'right' },
    ],
    alt: 'Formular „Neue:n Benutzer:in anlegen“ für Lena Wagner mit Benutzername, Passwort, 30 Wochenstunden, 4 Arbeitstagen und der Urlaubs-Empfehlung 24 Tage',
  },
  {
    id: 'pl-neu-anlegen-optionen',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/users',
    prepare: [
      { click: { role: 'button', name: 'Neue:r Mitarbeiter:in', exact: true } },
      { scrollTo: { css: "main form button[type='submit']" } },
    ],
    crop: { around: ['erster-tag', 'speichern'], pad: 80 },
    markers: [
      { n: 1, id: 'erster-tag', locator: { css: "xpath=//main//label[normalize-space()='Erster Arbeitstag']/following-sibling::input[1]" }, badge: 'left' },
      { n: 2, id: 'modus', locator: { css: "xpath=//main//legend[normalize-space()='Arbeitszeit']/.." }, badge: 'left' },
      { n: 3, id: 'speichern', locator: { css: "main form button[type='submit']" }, badge: 'top' },
    ],
    alt: 'Unterer Teil des Anlegeformulars: erster und letzter Arbeitstag, Abteilung/Bereich, die Wahl der Arbeitszeit (Gleichmäßig, Nach Tagen, Nach Arbeitsblöcken) und Speichern',
  },
  {
    id: 'pl-bearbeiten',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/users',
    prepare: [
      { click: { css: "main tr:has-text('Schulz, Petra') button[title='Bearbeiten']" } },
      { waitFor: { role: 'button', name: 'Arbeitszeit anpassen…', exact: true } },
      { scrollTo: { css: '#f-contract-terms' } },
    ],
    crop: { around: ['anpassen', 'vertrag'], pad: 32 },
    markers: [
      { n: 1, id: 'anpassen', locator: { role: 'button', name: 'Arbeitszeit anpassen…', exact: true }, badge: 'top' },
      { n: 2, id: 'vertrag', locator: { css: '#f-contract-terms' }, badge: 'top' },
    ],
    alt: 'Formular „Benutzer bearbeiten“ von Petra Schulz: Wochenstunden als Anzeige mit dem Knopf „Arbeitszeit anpassen…“ und darunter „Urlaub und Abrechnung“',
  },
  {
    id: 'pl-vertragsverlauf',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/users',
    prepare: [
      { click: PETRA_HOURS },
      { waitFor: { role: 'heading', name: 'Verlauf', exact: true } },
    ],
    crop: 'dialog',
    markers: [
      { n: 1, id: 'anspruch', locator: { label: 'Urlaubsanspruch pro Jahr ab diesem Datum', within: 'dialog' }, badge: 'right' },
      { n: 2, id: 'speichern', locator: { role: 'button', name: 'Speichern', exact: true, within: 'dialog' }, badge: 'left' },
      { n: 3, id: 'verlauf', locator: { css: "[role='dialog'] >> text=/^Ab \\d\\d\\.\\d\\d\\.\\d{4} bis heute/ >> xpath=../.." }, badge: 'top' },
    ],
    alt: 'Dialog „Arbeitszeit & Wochenstunden“ von Petra Schulz: Gültig ab, Urlaubsanspruch 18 Tage und der Verlauf mit zwei Zeilen (16 und 18 Tage/Jahr)',
  },

  // ── 4. Arbeitszeit-Blöcke & Änderungen ───────────────────────────────────
  {
    id: 'pl-bloecke',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/users',
    prepare: [{ click: SARAH_HOURS }, { waitFor: { label: 'Mo Block 1 von', within: 'dialog' } }],
    crop: { around: ['gueltig-ab', 'pause', 'block'], pad: 56 },
    markers: [
      { n: 1, id: 'gueltig-ab', locator: { label: 'Gültig ab', within: 'dialog' }, badge: 'left' },
      { n: 2, id: 'modus', locator: { css: "[role='dialog'] label:has-text('Nach Arbeitsblöcken')" }, badge: 'top' },
      { n: 3, id: 'block', locator: { label: 'Di Block 2 von', within: 'dialog' }, badge: 'top' },
      { n: 4, id: 'plus', locator: { role: 'button', name: 'Mo: Block hinzufügen', exact: true, within: 'dialog' }, badge: 'top' },
      { n: 5, id: 'pause', locator: { label: 'Mo Pause innerhalb der Blöcke (Min)', within: 'dialog' }, badge: 'top' },
    ],
    alt: 'Block-Editor im Dialog „Arbeitszeit & Wochenstunden“ für Sarah Klein: Gültig ab, Modus „Nach Arbeitsblöcken“ und Montag und Dienstag mit den Blöcken 08:00–12:00 und 15:00–16:00 samt Pause',
  },
  {
    id: 'pl-rueckwirkend',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/users',
    prepare: RETRO_PREPARE,
    crop: { around: ['verkuerzung', 'begruendung'], pad: 44 },
    markers: [
      { n: 1, id: 'verkuerzung', locator: { css: '#wh-short-title' }, badge: 'left' },
      { n: 2, id: 'ab-heute', locator: { css: "[role='dialog'] label:has-text('vergangene Einträge bleiben unverändert') > span" }, badge: 'right' },
      { n: 3, id: 'rueckwirkend', locator: { css: "[role='dialog'] label:has-text('mit Neuberechnung') > span" }, badge: 'right' },
      { n: 4, id: 'grund', locator: { css: '#wh-short-reason-type' }, badge: 'left' },
      { n: 5, id: 'begruendung', locator: { css: '#wh-short-reason-text' }, badge: 'left' },
    ],
    alt: 'Kasten „Verkürzung“ bei einer rückwirkenden Arbeitszeit-Änderung: Wahl zwischen „Ab heute“ und „Rückwirkend mit Neuberechnung“, darunter Grund und Begründung',
  },
  {
    id: 'pl-auswirkung',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/users',
    // scrollTo zentriert: die Tabelle in die Mitte, Überschrift und Haken bleiben sichtbar
    prepare: [...RETRO_PREPARE, { scrollTo: { css: "[role='dialog'] [role='status'] table" } }],
    crop: { around: ['bereich', 'bestaetigen'], pad: 56 },
    markers: [
      { n: 1, id: 'bereich', locator: { css: "[role='dialog'] >> text=/^Rückwirkende Änderung:/" }, badge: 'left' },
      { n: 2, id: 'eintraege', locator: { css: "[role='dialog'] >> text=/^Zeiteinträge: \\d+ neu berechnet/" }, badge: 'left' },
      { n: 3, id: 'tabelle', locator: { css: "[role='dialog'] [role='status'] table" }, badge: 'left' },
      { n: 4, id: 'einzelheiten', locator: { role: 'button', name: 'Einzelheiten', within: 'dialog' }, badge: 'right' },
      { n: 5, id: 'bestaetigen', locator: { css: "[role='dialog'] label:has-text('Ich habe die Auswirkungen geprüft')" }, badge: 'left' },
    ],
    alt: 'Auswirkungs-Kasten einer rückwirkenden Änderung: Wirkungsbereich, Tagessoll vorher und nachher, zwei neu berechnete Einträge und die Tabelle für Soll, Überstunden und Urlaub',
  },
  {
    id: 'pl-anerkennen',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/users',
    prepare: [
      { click: { css: "main tr:has-text('Klein, Sarah') button[title='Monatsjournal anzeigen']" } },
      { waitFor: { role: 'heading', name: 'Monatsjournal: Sarah Klein', exact: true } },
      { waitFor: { css: "main >> text=/^gestempelt 08:00/ >> visible=true >> nth=0" } },
      { scrollTo: { css: "main tr:has-text('zwischen den Blöcken nicht angerechnet') >> visible=true >> nth=-1" } },
    ],
    crop: { around: ['zeile', 'anerkennen'], pad: 56 },
    markers: [
      { n: 1, id: 'zeile', locator: { css: "main tr:has-text('zwischen den Blöcken nicht angerechnet') >> visible=true >> nth=-1 >> text=/^gestempelt /" }, badge: 'left' },
      { n: 2, id: 'anerkennen', locator: { css: "main tr:has-text('zwischen den Blöcken nicht angerechnet') >> visible=true >> nth=-1 >> button:has-text('Anerkennen')" }, badge: 'left' },
    ],
    alt: 'Zeile im Monatsjournal von Sarah Klein: gestempelt 08:00–16:00, angerechnet 5:30 h, 2:30 h zwischen den Blöcken nicht angerechnet, darunter der Knopf „Anerkennen“',
  },

  // ── 5. Anträge genehmigen ────────────────────────────────────────────────
  {
    id: 'pl-urlaubsantraege',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/vacation-approvals',
    crop: 'main',
    markers: [
      { n: 1, id: 'pflicht', locator: { css: "main button[role='switch']" }, badge: 'left' },
      // die Knopfzeile der Karte: Genehmigen, Bearbeiten, Ablehnen
      { n: 2, id: 'aktionen', locator: { css: "main div.border-t:has(button:has-text('Genehmigen'))" }, badge: 'left' },
    ],
    alt: 'Seite „Abwesenheitsanträge“: Schalter für die Genehmigungspflicht und der offene Urlaubsantrag von Thomas Bauer über 5 Arbeitstage',
  },

  {
    id: 'pl-korrekturantrag',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/change-requests',
    crop: { around: ['aktuell', 'gewuenscht', 'begruendung', 'genehmigen'], pad: 48 },
    markers: [
      { n: 1, id: 'aktuell', locator: { css: "main div.rounded-xl:has-text('Hoffmann, Maria') >> div.rounded-lg:has(h4:text-is('Aktuell')) >> p:has-text('Zeit:') > span" }, badge: 'right' },
      { n: 2, id: 'gewuenscht', locator: { css: "main div.rounded-xl:has-text('Hoffmann, Maria') >> div.rounded-lg:has(h4:text-is('Gewünscht')) >> p:has-text('Zeit:') > span" }, badge: 'right' },
      { n: 3, id: 'begruendung', locator: { css: "main div.rounded-xl:has-text('Hoffmann, Maria') >> div.text-sm:has(> span:text-is('Begründung:')) > span >> nth=1" }, badge: 'right' },
      { n: 4, id: 'genehmigen', locator: { css: "main div.rounded-xl:has-text('Hoffmann, Maria') >> button:has(span:text-is('Genehmigen'))" }, badge: 'left' },
    ],
    alt: 'Offener Änderungsantrag: aktuell 09:15–17:30, gewünscht 08:00–16:45, darunter die Begründung und die Knöpfe Genehmigen und Ablehnen',
  },

  {
    id: 'pl-anrechnung-beantragt',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/change-requests',
    prepare: [{ scrollTo: { role: 'button', name: 'Ohne Anerkennen genehmigen', exact: true, within: 'main' } }],
    crop: { around: ['kennzeichen', 'luecke', 'ohne'], pad: 48 },
    markers: [
      { n: 1, id: 'kennzeichen', locator: { css: "main >> text='Anrechnung beantragt'" }, badge: 'right' },
      { n: 2, id: 'luecke', locator: { css: 'main >> text=/^Nicht angerechnet \\(Lücke\\)/' }, badge: 'left' },
      { n: 3, id: 'anerkennen', locator: { role: 'button', name: 'Genehmigen und anerkennen', exact: true, within: 'main' }, badge: 'top' },
      { n: 4, id: 'ohne', locator: { role: 'button', name: 'Ohne Anerkennen genehmigen', exact: true, within: 'main' }, badge: 'top' },
    ],
    alt: 'Antrag „Anrechnung beantragt“ von Sarah Klein: 2:30 h Lücke nicht angerechnet, gestempelt 08:00–16:00, Knöpfe „Genehmigen und anerkennen“ und „Ohne Anerkennen genehmigen“',
  },
  {
    id: 'pl-sammel-genehmigung',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/change-requests',
    prepare: [{ click: { label: 'Alle 2 auswählen', within: 'main' } }],
    crop: { around: ['auswahl', 'sammel', 'karte'], pad: 48 },
    markers: [
      { n: 1, id: 'auswahl', locator: { css: "main label:has-text('ausgewählt')" }, badge: 'left' },
      { n: 2, id: 'karte', locator: { role: 'checkbox', name: 'Antrag von Maria Hoffmann auswählen', exact: true }, badge: 'left' },
      { n: 3, id: 'sammel', locator: { css: "main button:has-text('genehmigen, davon')" }, badge: 'top' },
    ],
    alt: 'Zwei offene Änderungsanträge ausgewählt („2 ausgewählt“); oben der Knopf „2 genehmigen, davon 1 mit Anerkennen“',
  },

  // ── 6. Abwesenheiten & Betriebsferien ────────────────────────────────────
  {
    id: 'pl-abwesenheit-eintragen',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/absences',
    prepare: [
      { click: { css: "main div.rounded-xl:has(span:text-is('Sarah Klein')) button:text-is('+ Eintragen')" } },
      { waitFor: { css: "main >> text=/^Abwesenheit eintragen für Sarah Klein/" } },
      { fill: { css: "main form input[type='date']" }, value: '{{stichtag+7d}}' },
    ],
    crop: { around: ['mitarbeiter', 'speichern'], pad: 90 },
    markers: [
      { n: 1, id: 'mitarbeiter', locator: { css: '#absence-employee-filter' }, badge: 'left' },
      { n: 2, id: 'zeitraum', locator: { css: "main form label[for='isDateRange'] >> xpath=.." }, badge: 'left' },
      { n: 3, id: 'datum', locator: { css: "main form input[type='date']" }, badge: 'left' },
      { n: 4, id: 'typ', locator: { css: 'main form select' }, badge: 'top' },
      { n: 5, id: 'speichern', locator: { css: "main form button[type='submit']" }, badge: 'left' },
    ],
    alt: 'Seite „Abwesenheiten verwalten“: Mitarbeiterin Sarah Klein gewählt, darunter das Formular „Abwesenheit eintragen“ mit Datum, Typ Urlaub, ausgegrautem Stundenfeld mit Hinweis zum Tagessoll und Speichern',
  },
  {
    id: 'pl-betriebsferien',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/absences',
    prepare: [
      { click: { role: 'button', name: 'Betriebsferien', exact: true, within: 'main' } },
      { click: { role: 'button', name: 'Betriebsferien erstellen', exact: true, within: 'main' } },
      { fill: { css: "main form input[type='text']" }, value: 'Umbau Empfang' },
      { fill: { css: "main form input[type='date'] >> nth=0" }, value: '{{stichtag+35d}}' },
      { fill: { css: "main form input[type='date'] >> nth=1" }, value: '{{stichtag+37d}}' },
    ],
    crop: { around: ['bezeichnung', 'erstellen'], pad: 90 },
    markers: [
      { n: 1, id: 'bezeichnung', locator: { css: "main form input[type='text']" }, badge: 'left' },
      { n: 2, id: 'zeitraum', locator: { css: "main form div.grid:has(input[type='date'])" }, badge: 'left' },
      { n: 3, id: 'verrechnung', locator: { css: "main form label:has-text('Als Urlaub werten') >> xpath=.." }, badge: 'left' },
      { n: 4, id: 'erstellen', locator: { css: "main form button[type='submit']" }, badge: 'left' },
    ],
    alt: 'Formular „Betriebsferien erstellen“ mit Bezeichnung „Umbau Empfang“, Von und Bis, der Verrechnung „Als Urlaub werten“ oder „Bezahlte Freistellung“ und dem Knopf zum Erstellen',
  },
  {
    id: 'pl-betriebsferien-liste',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/absences',
    prepare: [{ click: { role: 'button', name: 'Betriebsferien', exact: true, within: 'main' } }],
    crop: { around: ['tabelle', 'aktionen'], pad: 90 },
    markers: [
      { n: 1, id: 'tabelle', locator: { css: "main table:has(th:text-is('Betroffene MA')) thead" }, badge: 'left' },
      { n: 2, id: 'aktionen', locator: { css: "main table:has(th:text-is('Betroffene MA')) tbody tr >> td >> nth=-1" }, badge: 'left' },
    ],
    alt: 'Tabelle der Betriebsferien: „Teamklausur“ mit Zeitraum, Verrechnung Urlaub, Zahl der betroffenen Mitarbeitenden und in der Spalte Aktion den Symbolen Bearbeiten und Löschen',
  },
  {
    id: 'pl-betriebsferien-urlaub',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    prepare: [{ scrollTo: { role: 'heading', name: 'Betriebsferien & Urlaub', exact: true } }],
    crop: 'main',
    markers: [
      { n: 1, id: 'schalter', locator: { css: '#closure-overtime-toggle' }, badge: 'right' },
      {
        n: 2,
        id: 'speichern',
        locator: { css: "xpath=//main//button[@id='closure-overtime-toggle']/following::button[1]" },
        badge: 'right',
      },
    ],
    alt: 'Einstellungen, Abschnitt „Betriebsferien & Urlaub“: Erklärtext, Hinweis zum erneuten Speichern und der Schalter „Überzählige Betriebsferien als Überstundenabbau“',
  },

  // ── 7. Sondertage & verkürzte Tage ───────────────────────────────────────
  {
    id: 'pl-sondertage',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    // Beispiel: 24.12. Halbtag (Seed), 31.12. frei als Urlaub – nur für die Aufnahme gesetzt, danach zurückgestellt
    settings: { special_day_dec31_mode: 'free', special_day_dec31_counts_as_vacation: 'true' },
    prepare: [{ scrollTo: { role: 'heading', name: 'Sondertage (24./31.12.)', exact: true } }],
    crop: { around: ['modus', 'anrechnung', 'speichern'], pad: 70 },
    markers: [
      { n: 1, id: 'modus', locator: { css: '#special-dec24-mode' }, badge: 'right' },
      { n: 2, id: 'anrechnung', locator: { css: '#special-dec31-vacation' }, badge: 'right' },
      {
        n: 3,
        id: 'speichern',
        locator: { css: "xpath=//main//select[@id='special-dec31-vacation']/following::button[1]" },
        badge: 'right',
      },
    ],
    alt: 'Einstellungen, Abschnitt „Sondertage (24./31.12.)“: 24.12. im Modus Halbtag, 31.12. im Modus Frei mit der Anrechnung Urlaub, darunter Speichern',
  },
  {
    id: 'pl-verkuerzte-tage',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    prepare: [
      { scrollTo: { role: 'heading', name: 'Verkürzte Tage', exact: true } },
      { fill: { css: '#reduced-new-date' }, value: '{{stichtag+16d}}' },
      { fill: { css: '#reduced-new-label' }, value: 'Betriebsausflug' },
      { fill: { css: '#reduced-new-hours' }, value: '5' },
    ],
    crop: { around: ['jahr', 'zeile'], pad: 90 },
    markers: [
      { n: 1, id: 'jahr', locator: { css: '#reduced-days-year' }, badge: 'left' },
      { n: 2, id: 'eingabe', locator: { css: "xpath=//*[@id='reduced-new-date']/ancestor::div[contains(@class,'items-end')][1]" }, badge: 'left' },
      { n: 3, id: 'zeile', locator: { css: "main tr:has-text('Brückentag')" }, badge: 'left' },
    ],
    alt: 'Einstellungen, Abschnitt „Verkürzte Tage“: Eingabe Datum, Bezeichnung „Betriebsausflug“ und Höchstens 5 Stunden, darunter der eingetragene Brückentag mit höchstens 4 Stunden',
  },

  // ── 8. Berichte & Exporte ────────────────────────────────────────────────
  {
    id: 'pl-monatsreport',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/reports',
    crop: { around: ['monat', 'ausgeblendete'], pad: 90 },
    markers: [
      { n: 1, id: 'monat', locator: { css: "main input[type='month']" }, badge: 'left' },
      { n: 2, id: 'krankheit', locator: { css: "main label:has-text('Krankheitsdaten einschließen (Art. 9 DSGVO)')" }, badge: 'left' },
      { n: 3, id: 'ausgeblendete', locator: { css: "label[for='export-hidden-month']" }, badge: 'left' },
      { n: 4, id: 'formate', locator: { role: 'button', name: 'PDF (.pdf)', exact: true, within: 'main' }, badge: 'right' },
    ],
    alt: 'Berichte & Export, Monatsreport: Monat auswählen, Knöpfe Excel, ODS und PDF, darunter „Krankheitsdaten einschließen“ und „Ausgeblendete Mitarbeitende einbeziehen“',
  },
  {
    id: 'pl-jahresreport',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/reports',
    prepare: [{ scrollTo: { css: "main div.rounded-lg:has(> h3:has-text('Detailliertes Format'))" } }],
    crop: { around: ['jahr', 'detailliert'], pad: 90 },
    markers: [
      { n: 1, id: 'jahr', locator: { css: "xpath=//main//label[normalize-space()='Jahr auswählen']/following-sibling::input[1]" }, badge: 'left' },
      { n: 2, id: 'classic', locator: { css: "main div.rounded-lg:has(> h3:has-text('Classic Format'))" }, badge: 'left' },
      { n: 3, id: 'detailliert', locator: { css: "main div.rounded-lg:has(> h3:has-text('Detailliertes Format'))" }, badge: 'right' },
    ],
    alt: 'Berichte & Export, Jahresreport: Jahr auswählen und die beiden Formate „Classic“ und „Detailliert“ mit je einem Knopf für Excel und ODS',
  },

  // ── 9. ArbZG-Prüfung & §4-Ausnahme ───────────────────────────────────────
  {
    id: 'pl-arbzg-24wochen',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/reports',
    prepare: [
      { click: { role: 'button', name: '24-Wochen-Durchschnitt prüfen', exact: true } },
      { waitFor: { role: 'table', name: '24-Wochen-Durchschnitt', exact: true } },
      { scrollTo: { role: 'table', name: '24-Wochen-Durchschnitt', exact: true } },
    ],
    crop: { around: ['stichtag', 'tabelle'], pad: 90 },
    markers: [
      { n: 1, id: 'stichtag', locator: { css: '#avg-end-date' }, badge: 'left' },
      { n: 2, id: 'pruefen', locator: { role: 'button', name: '24-Wochen-Durchschnitt prüfen', exact: true }, badge: 'right' },
      { n: 3, id: 'tabelle', locator: { role: 'table', name: '24-Wochen-Durchschnitt', exact: true }, badge: 'left' },
    ],
    alt: 'Auswertung „24-Wochen-Durchschnitt §3 ArbZG“ zum Stichtag: je Person Durchschnitt angerechnet und laut Stempel je Werktag, Summen, Wochen über 48 Stunden, Tage über 8 Stunden und Status',
  },
  {
    id: 'pl-arbzg-hoechstarbeitszeit',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/reports',
    prepare: [
      { click: { role: 'button', name: 'Höchstarbeitszeit und Pausenausnahmen prüfen', exact: true } },
      { waitFor: { css: "main button:has-text('Pausenausnahme(n)')" } },
      { click: { css: "main button:has-text('Pausenausnahme(n)')" } },
      { waitFor: { role: 'table', name: 'Pausenausnahmen Thomas Bauer', exact: true } },
      { scrollTo: { role: 'table', name: 'Pausenausnahmen Thomas Bauer', exact: true } },
    ],
    crop: { around: ['filter', 'ausnahmen'], pad: 90 },
    markers: [
      { n: 1, id: 'filter', locator: { css: "xpath=//*[@id='limits-year']/ancestor::div[contains(@class,'items-end')][1]" }, badge: 'left' },
      { n: 2, id: 'zahlen', locator: { css: "main div.flex:has(> span:has-text('Pause zu kurz:'))" }, badge: 'left' },
      { n: 3, id: 'person', locator: { css: "main button:has-text('Pausenausnahme(n)')" }, badge: 'left' },
      { n: 4, id: 'ausnahmen', locator: { role: 'table', name: 'Pausenausnahmen Thomas Bauer', exact: true }, badge: 'left' },
    ],
    alt: 'Auswertung „Höchstarbeitszeit und Pausenausnahmen §3/§4 ArbZG“: Zähler je Befund und aufgeklappt eine dokumentierte Pausenausnahme von Thomas Bauer mit Zeit, Pause und Begründung',
  },
  {
    id: 'pl-pflicht-pause',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    prepare: [{ scrollTo: { role: 'heading', name: 'Pflicht-Pause-Ausnahme', exact: true } }],
    crop: 'main',
    markers: [
      { n: 1, id: 'erlauben', locator: { css: '#break-exception-allowed-toggle' }, badge: 'right' },
      { n: 2, id: 'genehmigung', locator: { css: '#break-approval-toggle' }, badge: 'right' },
      {
        n: 3,
        id: 'speichern',
        locator: { css: "xpath=//main//button[@id='break-approval-toggle']/following::button[1]" },
        badge: 'right',
      },
    ],
    alt: 'Einstellungen, Abschnitt „Pflicht-Pause-Ausnahme“: Schalter „Ausnahme Pflicht-Pause war nicht möglich erlauben“ und „Genehmigung erforderlich“ mit Erklärtext und Speichern',
  },

  // ── 10. Eigene Abwesenheitsgründe, Kind krank, Minijob ───────────────────
  {
    id: 'pl-abwesenheitsgrund',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    // nur ausgefüllt, nie auf „Hinzufügen“ geklickt
    prepare: [{ fill: { css: "main input[placeholder='z. B. Schule']" }, value: 'Berufsschule' }],
    crop: { around: ['bezeichnung', 'liste'], pad: 90 },
    markers: [
      { n: 1, id: 'bezeichnung', locator: { css: "main input[placeholder='z. B. Schule']" }, badge: 'left' },
      { n: 2, id: 'verhalten', locator: { css: "xpath=//main//label[normalize-space()='Verhalten']/following-sibling::select" }, badge: 'left' },
      { n: 3, id: 'hinzufuegen', locator: { css: "xpath=(//main//button[normalize-space()='Hinzufügen'])[1]" }, badge: 'top' },
      { n: 4, id: 'vorlagen', locator: { css: "xpath=//main//p[normalize-space()='Vorlagen (1-Klick aktivieren)']/following-sibling::div[1]" }, badge: 'left' },
      { n: 5, id: 'liste', locator: { css: "main li:has(input[value='Fortbildung extern'])" }, badge: 'left' },
    ],
    alt: 'Einstellungen, Bereich „Eigene Abwesenheitsgründe“: Eingabezeile mit Bezeichnung, Verhalten, Farbe und Hinzufügen, darunter die Vorlagen und der vorhandene Grund „Fortbildung extern“ mit „Zählt als gearbeitet“',
  },
  {
    id: 'pl-kind-krank-grund',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    prepare: [
      { select: { css: "xpath=//main//label[normalize-space()='Verhalten']/following-sibling::select" }, value: 'Unbezahlt frei' },
      { waitFor: { css: "main label:has-text('Gegen das Kind-krank-Jahreslimit')" } },
    ],
    crop: { around: ['verhalten', 'haken', 'vorlage'], pad: 90 },
    markers: [
      // die ganze Reihe der Vorlagen; „+ Kind krank“ steht links in der Reihe
      { n: 1, id: 'vorlage', locator: { css: "xpath=//main//p[normalize-space()='Vorlagen (1-Klick aktivieren)']/following-sibling::div[1]" }, badge: 'left' },
      { n: 2, id: 'verhalten', locator: { css: "xpath=//main//label[normalize-space()='Verhalten']/following-sibling::select" }, badge: 'left' },
      { n: 3, id: 'haken', locator: { css: "main label:has-text('Gegen das Kind-krank-Jahreslimit') >> input[type='checkbox']" }, badge: 'left' },
    ],
    alt: 'Eigene Abwesenheitsgründe mit Verhalten „Unbezahlt frei“: darunter der Haken „Gegen das Kind-krank-Jahreslimit zählen (§45 SGB V)“ und in der Reihe der Vorlagen der Knopf „Kind krank“',
  },
  {
    id: 'pl-kind-krank-limit',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    prepare: [{ scrollTo: { role: 'heading', name: 'Kind-krank-Standardanspruch', exact: true } }],
    crop: { around: ['anspruch', 'mindestlohn'], pad: 90 },
    markers: [
      { n: 1, id: 'anspruch', locator: { label: 'Standard Kind-krank-Tage/Jahr', within: 'main' }, badge: 'left' },
      { n: 2, id: 'speichern', locator: { css: "xpath=//main//input[@id='child-sick-default']/ancestor::div[contains(@class,'items-end')][1]//button" }, badge: 'right' },
      { n: 3, id: 'mindestlohn', locator: { css: "xpath=//main//h2[normalize-space()='Gesetzlicher Mindestlohn']/following-sibling::p[1]" }, badge: 'left' },
    ],
    alt: 'Einstellungen: Bereich „Kind-krank-Standardanspruch“ mit dem Feld „Standard Kind-krank-Tage/Jahr“ (15) und Speichern, darunter „Gesetzlicher Mindestlohn“ mit 13,90 €/h seit 1.1.2026',
  },
  {
    id: 'pl-minijob-konto',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/users',
    // nur Entwurf, nie speichern (der Dialog bleibt bei „Gültig ab“ = heute; Minijob-Felder gelten nur ab Monatserstem)
    prepare: [
      { click: JULIA_HOURS },
      { waitFor: { label: 'Vereinbarte Monatsarbeitszeit (h)', within: 'dialog' } },
      { fill: { label: 'Vereinbarte Monatsarbeitszeit (h)', within: 'dialog' }, value: '43' },
      { scrollTo: { css: "[role='dialog']:not([aria-hidden='true']) >> text=/^Statt aus Wochenstunden/" } },
    ],
    crop: { around: ['konto', 'monat', 'fest'], pad: 56 },
    markers: [
      { n: 1, id: 'konto', locator: { css: '#wh-milog_working_time_account' }, badge: 'left' },
      { n: 2, id: 'monat', locator: { label: 'Vereinbarte Monatsarbeitszeit (h)', within: 'dialog' }, badge: 'left' },
      { n: 3, id: 'fest', locator: { css: '#wh-use_fixed_monthly_target' }, badge: 'left' },
    ],
    alt: 'Dialog „Arbeitszeit & Wochenstunden“ von Julia Meyer, Abschnitt „Urlaub und Abrechnung“: Haken „Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)“, Vereinbarte Monatsarbeitszeit 43 Stunden mit 50-%-Grenze und Haken „Feste Monatsarbeitszeit“',
  },

  // ── 11. Einstellungen ────────────────────────────────────────────────────
  {
    id: 'pl-eigene-feiertage',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    // nur ausgefüllt, nie auf „Hinzufügen“ geklickt (Stichtag 28.10.2026 → 20.07.2026)
    prepare: [
      { scrollTo: { css: "main thead th:has-text('Typ')" } },
      { fill: { css: '#new-holiday-name' }, value: 'Schützenfest' },
      { fill: { css: '#new-holiday-date' }, value: '{{stichtag-100d}}' },
    ],
    crop: { around: ['jahr', 'name', 'hinzufuegen'], pad: 90 },
    markers: [
      { n: 1, id: 'jahr', locator: { css: '#holiday-year' }, badge: 'left' },
      { n: 2, id: 'name', locator: { css: '#new-holiday-name' }, badge: 'left' },
      { n: 3, id: 'datum', locator: { css: '#new-holiday-date' }, badge: 'top' },
      { n: 4, id: 'hinzufuegen', locator: { css: "xpath=//main//input[@id='new-holiday-date']/ancestor::div[contains(@class,'flex-wrap')][1]//button" }, badge: 'right' },
    ],
    alt: 'Einstellungen, Bereich „Eigene Feiertage“: Jahresauswahl, Eingabezeile mit Name „Schützenfest“, Datum 20.07.2026 und dem Knopf „Hinzufügen“',
  },
  {
    id: 'pl-urlaubsgenehmigung',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    prepare: [{ scrollTo: { role: 'heading', name: 'Urlaubsgenehmigung', exact: true } }],
    crop: 'main',
    markers: [
      { n: 1, id: 'schalter', locator: { css: '#approval-toggle' }, badge: 'right' },
      { n: 2, id: 'speichern', locator: { css: "xpath=//main//button[@id='approval-toggle']/ancestor::div[contains(@class,'max-w-sm')][1]/following-sibling::div[1]//button" }, badge: 'right' },
    ],
    alt: 'Einstellungen, Bereich „Urlaubsgenehmigung“: Schalter „Genehmigung erforderlich“ mit Erklärtext und dem Knopf „Speichern“',
  },
  {
    id: 'pl-onboarding-schichtplanung',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    prepare: [{ scrollTo: { role: 'heading', name: 'Onboarding / Willkommens-Tour', exact: true } }],
    crop: 'main',
    markers: [
      { n: 1, id: 'tour', locator: { css: '#onboarding-toggle' }, badge: 'right' },
      { n: 2, id: 'schichtplanung', locator: { css: '#shift-planning-toggle' }, badge: 'right' },
    ],
    alt: 'Einstellungen: Bereiche „Onboarding / Willkommens-Tour“ mit dem Schalter „Willkommens-Tour anzeigen“ und „Schichtplanung“ mit dem Schalter „Schichtplanung aktivieren“, beide mit eigenem Speichern',
  },
  {
    id: 'pl-projektion',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    prepare: [{ scrollTo: { role: 'heading', name: 'Überstunden-Projektion zum Jahresende', exact: true } }],
    crop: 'main',
    markers: [
      { n: 1, id: 'mitarbeiter', locator: { css: '#employee-year-end-projection-toggle' }, badge: 'right' },
      { n: 2, id: 'admin', locator: { css: '#admin-year-end-projection-toggle' }, badge: 'right' },
      { n: 3, id: 'speichern', locator: { css: "xpath=//main//button[@id='admin-year-end-projection-toggle']/ancestor::div[contains(@class,'space-y-5')][1]/following-sibling::div[1]//button" }, badge: 'right' },
    ],
    alt: 'Einstellungen, Bereich „Überstunden-Projektion zum Jahresende“: zwei Schalter „Im Mitarbeiter-Dashboard anzeigen“ und „Im Admin-Dashboard anzeigen“ mit Erklärtexten und Speichern',
  },
  {
    id: 'pl-puffer',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    prepare: [{ scrollTo: { role: 'heading', name: 'Soll-Arbeitszeit-Fenster', exact: true } }],
    crop: 'main',
    markers: [
      { n: 1, id: 'puffer', locator: { css: '#grace-minutes' }, badge: 'right' },
      { n: 2, id: 'speichern', locator: { css: "xpath=//main//input[@id='grace-minutes']/ancestor::div[contains(@class,'items-end')][1]//button" }, badge: 'right' },
    ],
    alt: 'Einstellungen, Bereich „Soll-Arbeitszeit-Fenster“: Erklärtext zum Puffer, das Feld „Puffer für Soll-Arbeitszeit-Fenster (Min.)“ mit 15 und der Knopf „Speichern“',
  },
  {
    id: 'pl-farben',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    prepare: [{ scrollTo: { css: "xpath=//main//h2[normalize-space()='Farben']/following-sibling::div[last()]//button" } }],
    crop: 'main',
    markers: [
      { n: 1, id: 'farben', locator: { css: "xpath=//main//h2[normalize-space()='Farben']/following-sibling::div[contains(@class,'grid')]" }, badge: 'right' },
      { n: 2, id: 'speichern', locator: { css: "xpath=//main//h2[normalize-space()='Farben']/following-sibling::div[last()]//button" }, badge: 'right' },
    ],
    alt: 'Einstellungen, Bereich „Farben“: je Anwesenheits- und Abwesenheitstyp ein Farbfeld mit „Aa“-Vorschau, darunter der Knopf „Speichern“',
  },

  // ── 12. Jahresabschluss ──────────────────────────────────────────────────
  {
    id: 'pl-jahresuebersicht',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin',
    prepare: [{ scrollTo: { css: 'main th:has-text("Resturlaub")' } }],
    crop: 'main',
    markers: [
      { n: 1, id: 'jahr', locator: { css: '#year-select' }, badge: 'left' },
      { n: 2, id: 'abschluss', locator: { css: "main button[title='Jahresabschluss 2026 erstellen']" }, badge: 'corner' },
      { n: 3, id: 'loeschen', locator: { css: "main button[title='Jahresabschluss 2026 löschen']" }, badge: 'top' },
      { n: 4, id: 'resturlaub', locator: { css: 'main th:has-text("Resturlaub")' }, badge: 'top' },
    ],
    alt: 'Jahresübersicht auf dem Admin-Dashboard: Jahr 2026 mit den Knöpfen Jahresabschluss, Abschluss löschen und Berichte, darunter die gelbe Jahresend-Warnung und die Tabelle mit Urlaub, Resturlaub, Krank und Überstunden',
  },
  {
    id: 'pl-jahresabschluss-dialog',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin',
    // nur der Bestätigungsdialog; „Jahresabschluss erstellen“ wird nie angeklickt
    prepare: [
      { click: { css: "main button[title='Jahresabschluss 2026 erstellen']" } },
      { waitFor: { css: "[role='alertdialog']" } },
    ],
    crop: { around: ['text', 'bestaetigen'], pad: 90 },
    markers: [
      { n: 1, id: 'text', locator: { css: "[role='alertdialog'] #confirm-dialog-desc" }, badge: 'left' },
      { n: 2, id: 'abbrechen', locator: { css: "[role='alertdialog'] button:text-is('Abbrechen')" }, badge: 'top' },
      { n: 3, id: 'bestaetigen', locator: { css: "[role='alertdialog'] button:text-is('Jahresabschluss erstellen')" }, badge: 'top' },
    ],
    alt: 'Bestätigungsdialog „Jahresabschluss 2026“: Überstunden-Saldo und Resturlaub aller aktiven Mitarbeiter werden als Übernahme in 2027 gespeichert, bestehende Übernahmen werden überschrieben; Knöpfe Abbrechen und Jahresabschluss erstellen',
  },
  {
    id: 'pl-uebernahme',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/users',
    // nur geöffnet, nie gespeichert
    prepare: [
      { click: { css: "main tr:has-text('Hoffmann') button[title='Vorjahresübernahme']" } },
      { waitFor: { css: "div.fixed.inset-0:has(h3:has-text('Vorjahresübernahme')) >> select" } },
    ],
    crop: { around: ['jahr', 'speichern'], pad: 200 },
    markers: [
      { n: 1, id: 'jahr', locator: { css: "div.fixed.inset-0:has(h3:has-text('Vorjahresübernahme')) >> select" }, badge: 'left' },
      { n: 2, id: 'ueberstunden', locator: { css: "div.fixed.inset-0:has(h3:has-text('Vorjahresübernahme')) >> input[type='number'] >> nth=0" }, badge: 'left' },
      { n: 3, id: 'resturlaub', locator: { css: "div.fixed.inset-0:has(h3:has-text('Vorjahresübernahme')) >> input[type='number'] >> nth=1" }, badge: 'left' },
      { n: 4, id: 'speichern', locator: { css: "div.fixed.inset-0:has(h3:has-text('Vorjahresübernahme')) >> button:has-text('Speichern')" }, badge: 'left' },
    ],
    alt: 'Dialog „Vorjahresübernahme“ von Maria Hoffmann: Auswahl des Jahres, Überstunden aus dem Vorjahr in Stunden, Resturlaub aus dem Vorjahr in Tagen und der Knopf „Speichern“',
  },

  // ── 13. Import ───────────────────────────────────────────────────────────
  {
    id: 'pl-import-hochladen',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/import',
    // Beispieldatei aus e2e/test-data; die Vorschau schreibt nichts
    prepare: IMPORT_UPLOAD,
    crop: { around: ['benutzer', 'datei', 'analysieren'], pad: 48 },
    markers: [
      { n: 1, id: 'benutzer', locator: { css: 'main select' }, badge: 'left' },
      { n: 2, id: 'datei', locator: { css: 'main div.border-dashed' }, badge: 'right' },
      { n: 3, id: 'analysieren', locator: { css: "main button:has-text('Datei analysieren')" }, badge: 'right' },
    ],
    alt: 'Import, Schritt „Hochladen“: Auswahl der Person Petra Schulz, das gestrichelte Feld mit der gewählten TimeRec-Datei im Format xls und der Knopf „Datei analysieren“',
  },
  {
    id: 'pl-import-vorschau',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/import',
    prepare: IMPORT_PREVIEW,
    crop: { around: ['zahlen', 'konflikt', 'neu'], pad: 80 },
    markers: [
      { n: 1, id: 'zahlen', locator: { css: 'main div.flex-wrap.text-sm' }, badge: 'top' },
      { n: 2, id: 'konflikt', locator: { css: "main tr:has-text('Konflikt') >> nth=0 >> td >> nth=-1 >> span >> nth=0" }, badge: 'right' },
      { n: 3, id: 'hinweis', locator: { css: "main tr:has-text('Hinweis') >> nth=1 >> td >> nth=-1 >> span >> nth=0" }, badge: 'right' },
      { n: 4, id: 'neu', locator: { css: "main tr:has-text('Neu') >> nth=1 >> td >> nth=-1 >> span >> nth=0" }, badge: 'right' },
    ],
    alt: 'Import, Schritt „Vorschau“: 20 Einträge gefunden, 1 Konflikt und 14 Hinweise; in der Tabelle die Zeilen mit Datum, Von, Bis, Pause, Netto und Status „Konflikt“, „Hinweis“ oder „Neu“',
  },
  {
    id: 'pl-import-bestaetigen',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/import',
    prepare: [...IMPORT_PREVIEW, { scrollTo: { css: "main button:has-text('Import bestätigen')" } }],
    crop: { around: ['ueberschreiben', 'zurueck', 'bestaetigen'], pad: 140 },
    markers: [
      { n: 1, id: 'ueberschreiben', locator: { css: "main label:has-text('Konflikte überschreiben') >> span" }, badge: 'right' },
      { n: 2, id: 'zurueck', locator: { css: "main button:has-text('Zurück')" }, badge: 'left' },
      { n: 3, id: 'bestaetigen', locator: { css: "main button:has-text('Import bestätigen')" }, badge: 'right' },
    ],
    alt: 'Import, Ende der Vorschau: Haken „Konflikte überschreiben (1 Eintrag)“ und die Knöpfe „Zurück“ und „Import bestätigen“ unter der Tabelle der gefundenen Einträge',
  },

  // ── 14. Protokoll & Fehler-Monitoring ────────────────────────────────────
  {
    id: 'pl-protokoll',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/audit-log',
    prepare: [{ waitFor: { role: 'columnheader', name: 'Quelle', exact: true } }],
    crop: 'main',
    markers: [
      { n: 1, id: 'monat', locator: { css: "xpath=//main//button[@aria-label='Vorheriger Monat']/.." }, badge: 'left' },
      { n: 2, id: 'person', locator: { css: 'main select' }, badge: 'right' },
      { n: 3, id: 'quelle', locator: { role: 'columnheader', name: 'Quelle', exact: true }, badge: 'top' },
      { n: 4, id: 'werte', locator: { role: 'columnheader', name: 'Alte Werte', exact: true }, badge: 'top' },
    ],
    alt: 'Änderungsprotokoll: Monatswähler, Auswahl der Person und die Tabelle mit Zeitpunkt, Mitarbeiter, Geändert von, Aktion, Quelle sowie alten und neuen Werten',
  },
  {
    id: 'pl-protokoll-pruefung',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/audit-log',
    prepare: [{ scrollTo: { role: 'heading', name: 'Prüfung des Änderungsprotokolls', exact: true } }],
    crop: { around: ['jetzt-pruefen', 'ergebnis'], pad: 56 },
    markers: [
      { n: 1, id: 'jetzt-pruefen', locator: { role: 'button', name: 'Jetzt prüfen', exact: true }, badge: 'left' },
      { n: 2, id: 'ergebnis', locator: { css: "xpath=//main//h2[normalize-space()='Prüfung des Änderungsprotokolls']/ancestor::div[contains(@class,'rounded-xl')][1]//p[starts-with(normalize-space(),'Letzte Prüfung') or starts-with(normalize-space(),'Noch keine Prüfung')]" }, badge: 'left' },
    ],
    alt: 'Karte „Prüfung des Änderungsprotokolls“ mit dem Knopf „Jetzt prüfen“ und der Zeile zum Ergebnis der letzten Prüfung',
  },
  {
    id: 'pl-konto-vorgaenge',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/audit-log',
    prepare: [{ scrollTo: { role: 'heading', name: 'Konto-Vorgänge', exact: true } }],
    crop: { around: ['kopf', 'vorgang', 'durch'], pad: 90 },
    markers: [
      { n: 1, id: 'kopf', locator: { css: "xpath=//main//h2[normalize-space()='Konto-Vorgänge']/.." }, badge: 'left' },
      // erste Zeile der Liste: die Zelle trägt die Nummer, die Spaltenköpfe bleiben frei
      { n: 2, id: 'vorgang', locator: { css: "xpath=//main//h2[normalize-space()='Konto-Vorgänge']/ancestor::div[contains(@class,'rounded-xl')][1]//tbody/tr[1]/td[2]" }, badge: 'left' },
      { n: 3, id: 'durch', locator: { css: "xpath=//main//h2[normalize-space()='Konto-Vorgänge']/ancestor::div[contains(@class,'rounded-xl')][1]//tbody/tr[1]/td[4]" }, badge: 'left' },
    ],
    alt: 'Liste „Konto-Vorgänge“ unter dem Änderungsprotokoll mit den Spalten Zeitpunkt, Vorgang, Konto, Durch und Detail',
  },
  {
    id: 'pl-fehler-monitoring',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/errors',
    crop: { around: ['aktualisieren', 'reiter', 'liste'], pad: 56 },
    markers: [
      { n: 1, id: 'aktualisieren', locator: { role: 'button', name: 'Aktualisieren', exact: true }, badge: 'left' },
      { n: 2, id: 'reiter', locator: { role: 'button', name: 'Offen', exact: false, within: 'main' }, badge: 'corner' },
      { n: 3, id: 'liste', locator: { css: 'main div.bg-green-50' }, badge: 'corner' },
    ],
    alt: 'Fehler-Monitoring: oben der Knopf „Aktualisieren“, darunter die Reiter Alle, Offen, Ignoriert und Behoben und der grüne Hinweis „Keine Fehler gefunden“',
  },

  // ── 15. Datensicherung ───────────────────────────────────────────────────
  {
    id: 'pl-datensicherung',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/backups',
    crop: { around: ['jetzt-sichern', 'liste'], pad: 110 },
    markers: [
      { n: 1, id: 'jetzt-sichern', locator: { role: 'button', name: 'Jetzt sichern', exact: true }, badge: 'left' },
      { n: 2, id: 'taeglich', locator: { label: 'Tägliche automatische Sicherung aktivieren', within: 'main' }, badge: 'left' },
      { n: 3, id: 'uhrzeit', locator: { css: "xpath=//main//label[normalize-space()='Uhrzeit (Stunde, 0–23)']/.." }, badge: 'left' },
      { n: 4, id: 'aufbewahrung', locator: { css: "xpath=//main//label[normalize-space()='Aufbewahrung (Tage)']/.." }, badge: 'right' },
      { n: 5, id: 'speicherort', locator: { css: "xpath=//main//label[normalize-space()='Speicherort (optional)']/.." }, badge: 'left' },
      { n: 6, id: 'speichern', locator: { role: 'button', name: 'Einstellungen speichern', exact: true }, badge: 'left' },
      { n: 7, id: 'liste', locator: { css: "main h2:has-text('Vorhandene Sicherungen')" }, badge: 'left' },
    ],
    alt: 'Datensicherung: „Jetzt sichern“, die Einstellungen der geplanten Sicherung mit Uhrzeit, Aufbewahrung und Speicherort und darunter die Liste der vorhandenen Sicherungen',
  },

  // ── 16. Schichtplanung ───────────────────────────────────────────────────
  {
    id: 'pl-schicht-wochentage',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/settings',
    settings: { shift_planning_enabled: true },
    prepare: [{ scrollTo: { role: 'heading', name: 'Geplante Wochentage', exact: true } }],
    crop: { around: ['wochentage', 'speichern-wt'], pad: 90 },
    markers: [
      { n: 1, id: 'wochentage', locator: { css: "xpath=//main//button[@aria-label='Montag']/.." }, badge: 'left' },
      { n: 2, id: 'speichern-wt', locator: { role: 'button', name: 'Wochentage speichern', exact: true }, badge: 'left' },
    ],
    alt: 'Einstellungen, Bereich Schichtplanung: die Wochentage Montag bis Sonntag als Auswahlfelder mit dem Knopf „Wochentage speichern“',
  },
  {
    id: 'pl-schicht-stammdaten',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/shift-planning',
    settings: { shift_planning_enabled: true },
    prepare: [
      { click: { role: 'button', name: 'Stammdaten', exact: true } },
      { waitFor: { role: 'heading', name: 'Arbeitsplätze', exact: true } },
    ],
    crop: { around: ['standort', 'bearbeiten'], pad: 90 },
    markers: [
      { n: 1, id: 'standort', locator: { css: "xpath=//main//label[normalize-space()='Neuer Standort']/.." }, badge: 'left' },
      { n: 2, id: 'name', locator: { css: "xpath=//main//h3[normalize-space()='Arbeitsplätze']/..//label[starts-with(normalize-space(),'Name')]/.." }, badge: 'left' },
      { n: 3, id: 'farbe', locator: { css: "xpath=//main//input[@aria-label='Farbe']/.." }, badge: 'left' },
      { n: 4, id: 'hinzufuegen', locator: { css: "xpath=//main//h3[normalize-space()='Arbeitsplätze']/..//button[normalize-space()='Hinzufügen']" }, badge: 'right' },
      { n: 5, id: 'bearbeiten', locator: { css: "xpath=(//main//h3[normalize-space()='Arbeitsplätze']/..//button[@aria-label='Bearbeiten'])[1]" }, badge: 'left' },
    ],
    alt: 'Schichtplanung, Reiter Stammdaten: links die Standorte, rechts die Arbeitsplätze Anmeldung und Labor mit Namensfeld, Farbwähler und Knopf „Hinzufügen“',
  },
  {
    id: 'pl-schicht-einweisungen',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/shift-planning',
    settings: { shift_planning_enabled: true },
    prepare: [
      { click: { role: 'button', name: 'Einweisungen', exact: true } },
      { waitFor: { role: 'columnheader', name: 'Labor', exact: true } },
    ],
    crop: 'main',
    markers: [
      { n: 1, id: 'arbeitsplatz', locator: { role: 'columnheader', name: 'Labor', exact: true }, badge: 'left' },
      { n: 2, id: 'haken', locator: { css: "main input[aria-label='Maria Hoffmann – Anmeldung']" }, badge: 'left' },
      { n: 3, id: 'kein-haken', locator: { css: "main input[aria-label='Maria Hoffmann – Labor']" }, badge: 'right' },
    ],
    alt: 'Schichtplanung, Reiter Einweisungen: Tabelle mit den Mitarbeitenden in den Zeilen und den Arbeitsplätzen Anmeldung und Labor in den Spalten, Häkchen bei eingewiesenen Personen',
  },
  {
    id: 'pl-schicht-editor',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/shift-planning',
    settings: { shift_planning_enabled: true },
    prepare: [
      { click: { css: "main button:has-text('Wochenplan Praxis')" } },
      { waitFor: { role: 'heading', name: 'Wochenplan Praxis', exact: true } },
    ],
    crop: 'main',
    markers: [
      { n: 1, id: 'neuer-plan', locator: { css: "xpath=//main//label[normalize-space()='Neuer Plan']/.." }, badge: 'left' },
      // Die Werkzeugleiste läuft bei 1440 px über den Kartenrand hinaus (Papierkorb außerhalb): nur Knöpfe im Fenster markieren.
      { n: 2, id: 'aktiv', locator: { css: "main button:text-matches('^(Aktiv schalten|Deaktivieren)$')" }, badge: 'left' },
      { n: 3, id: 'bearbeiten', locator: { role: 'button', name: 'Bearbeiten', exact: true, within: 'main' }, badge: 'top' },
      { n: 4, id: 'pdf', locator: { role: 'button', name: 'PDF', exact: true, within: 'main' }, badge: 'top' },
      { n: 5, id: 'woche-tag', locator: { css: "xpath=//main//button[normalize-space()='Woche']/.." }, badge: 'left' },
      { n: 6, id: 'mitarbeiter', locator: { role: 'heading', name: 'Mitarbeiter', exact: true, within: 'main' }, badge: 'corner' },
    ],
    alt: 'Schichtplanung, Plan „Wochenplan Praxis“: Werkzeugleiste mit Deaktivieren, Slot, Automatisch füllen, Bearbeiten, PDF und Duplizieren, darunter das Wochenraster und rechts die Mitarbeitenden',
  },
  {
    id: 'pl-schicht-slot',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/shift-planning',
    settings: { shift_planning_enabled: true },
    prepare: [
      { click: { css: "main button:has-text('Wochenplan Praxis')" } },
      { waitFor: { role: 'heading', name: 'Wochenplan Praxis', exact: true } },
      { click: { role: 'button', name: 'Slot', exact: true, within: 'main' } },
      { waitFor: { role: 'heading', name: 'Neuer Zeitslot', exact: true } },
    ],
    crop: { around: ['arbeitsplatz', 'zugewiesen'], pad: 130 },
    markers: [
      { n: 1, id: 'arbeitsplatz', locator: { label: 'Arbeitsplatz' }, badge: 'left' },
      { n: 2, id: 'wochentag', locator: { label: 'Wochentag' }, badge: 'left' },
      { n: 3, id: 'von-bis', locator: { css: "xpath=//label[starts-with(normalize-space(),'Von')]/ancestor::div[contains(@class,'grid')][1]" }, badge: 'left' },
      { n: 4, id: 'mindest', locator: { label: 'Mindestbesetzung' }, badge: 'left' },
      { n: 5, id: 'hinweis', locator: { label: 'Hinweis (optional)' }, badge: 'left' },
      { n: 6, id: 'zugewiesen', locator: { css: "xpath=//span[normalize-space()='Zugewiesene Mitarbeiter']/following-sibling::div[1]" }, badge: 'left' },
    ],
    alt: 'Dialog „Neuer Zeitslot“ mit Arbeitsplatz, Wochentag, Von und Bis, Mindestbesetzung, Hinweis und der Liste der zugewiesenen Mitarbeitenden',
  },
  {
    id: 'pl-schicht-plan-einstellungen',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/shift-planning',
    settings: { shift_planning_enabled: true },
    prepare: [
      { click: { css: "main button:has-text('Wochenplan Praxis')" } },
      { waitFor: { role: 'heading', name: 'Wochenplan Praxis', exact: true } },
      { click: { role: 'button', name: 'Bearbeiten', exact: true, within: 'main' } },
      { waitFor: { role: 'heading', name: 'Plan-Einstellungen', exact: true } },
    ],
    crop: { around: ['name', 'speichern'], pad: 110 },
    markers: [
      { n: 1, id: 'name', locator: { label: 'Name' }, badge: 'left' },
      { n: 2, id: 'zeitraum', locator: { css: "xpath=//label[starts-with(normalize-space(),'von')]/ancestor::div[contains(@class,'grid')][1]" }, badge: 'left' },
      { n: 3, id: 'sichtbar', locator: { css: "xpath=//span[starts-with(normalize-space(),'Für Mitarbeitende sichtbar')]/ancestor::label[1]" }, badge: 'left' },
      { n: 4, id: 'speichern', locator: { css: "xpath=//form[.//span[starts-with(normalize-space(),'Für Mitarbeitende sichtbar')]]//button[normalize-space()='Speichern']" }, badge: 'right' },
    ],
    alt: 'Dialog „Plan-Einstellungen“ mit Name, Beschreibung, dem Zeitraum für die automatische Aktivierung und dem Haken „Für Mitarbeitende sichtbar“',
  },
  {
    id: 'pl-schicht-fuellen',
    persona: 'admin',
    viewport: 'desktop',
    route: '/admin/shift-planning',
    settings: { shift_planning_enabled: true },
    prepare: [
      { click: { css: "main button:has-text('Wochenplan Praxis')" } },
      { waitFor: { role: 'heading', name: 'Wochenplan Praxis', exact: true } },
      { click: { role: 'button', name: 'Automatisch füllen', exact: true, within: 'main' } },
      { waitFor: { css: "xpath=//h3[normalize-space()='Automatisch füllen']" } },
    ],
    crop: { around: ['zielwoche', 'generieren'], pad: 210 },
    markers: [
      { n: 1, id: 'zielwoche', locator: { label: 'Zielwoche (für Abwesenheiten/Stunden)' }, badge: 'left' },
      { n: 2, id: 'modus', locator: { css: "xpath=//span[normalize-space()='Modus']/.." }, badge: 'left' },
      { n: 3, id: 'generieren', locator: { css: "xpath=//button[normalize-space()='Generieren']" }, badge: 'right' },
    ],
    alt: 'Dialog „Automatisch füllen“ mit der Zielwoche, der Wahl zwischen „Alle Zuweisungen neu verteilen“ und „Nur Lücken auffüllen“ und dem Knopf „Generieren“',
  },
];

export const praxisleitung: Handbook = {
  id: 'praxisleitung',
  title: 'Handbuch für die Praxisleitung',
  lead:
    'So richten Sie PraxisZeit ein, behalten Ihr Team im Blick, pflegen Verträge und Arbeitszeiten und entscheiden über Anträge. ' +
    'Jede Aufgabe beginnt mit einer Frage – suchen Sie sich die passende heraus.',
  chapters: [
    // ── 1 ───────────────────────────────────────────────────────────────────
    {
      id: 'erste-einrichtung',
      title: 'Erste Einrichtung',
      blocks: [
        {
          kind: 'comic',
          scene: 'einrichtung',
          text:
            'Einmal einrichten, dann läuft es: Einstellungen prüfen, das Team anlegen, die Arbeitszeiten hinterlegen. ' +
            'Als Praxisleitung sehen Sie alles, was Ihre Mitarbeitenden sehen – und zusätzlich den Bereich **Administration**.',
        },
        {
          kind: 'task',
          id: 'verwaltung-finden',
          title: 'Wo finde ich die Verwaltung?',
          intro:
            'Melden Sie sich mit den Admin-Zugangsdaten an, die bei der Installation gesetzt wurden. Oben in der Seitenleiste steht Ihre eigene Zeiterfassung, ' +
            'darunter der Abschnitt **Administration**.',
          shot: 'pl-navigation',
          steps: [
            { n: 1, text: '[[Admin-Dashboard]]: Soll, Ist und Saldo des ganzen Teams für den Monat oder die Woche.' },
            { n: 2, text: '[[Benutzerverwaltung]]: Mitarbeitende anlegen, bearbeiten, deaktivieren, Arbeitszeit anpassen.' },
            { n: 3, text: '[[Arbeitszeiten im Team]]: wer laut Arbeitszeit-Blöcken wann arbeitet. Darunter folgen u. a. [[Änderungsanträge]], [[Berichte]], [[Anträge]] und [[Einstellungen]].' },
            { n: 4, text: '[[Schnellstart]] öffnet die Kurzanleitung für die ersten Schritte. Daneben stehen [[Cheat-Sheet]] und [[Admin-Handbuch]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Eine rote Zahl neben [[Änderungsanträge]] oder [[Anträge]] zeigt, wie viele Anträge auf Ihre Entscheidung warten.',
        },
        {
          kind: 'task',
          id: 'erste-schritte-checkliste',
          title: 'Was richte ich zuerst ein?',
          intro: 'Die Reihenfolge aus dem Schnellstart – einmal durchgehen, danach läuft die Zeiterfassung.',
          steps: [
            { n: 1, text: '**Eigenes Passwort ändern:** [[Profil]] → [[Passwort ändern]].' },
            { n: 2, text: '**Einstellungen:** Bundesland für die Feiertage, Genehmigungspflicht für Urlaub, Sondertage 24./31.12. und die Willkommens-Tour für neue Mitarbeitende.' },
            { n: 3, text: '**Team anlegen:** je Person ein Konto mit Wochenstunden, Arbeitstagen und Urlaubsanspruch, siehe [Neue Person anlegen](#mitarbeiter-anlegen).' },
            { n: 4, text: '**Arbeitszeit hinterlegen:** gleichmäßig, nach Tagen oder als Arbeitszeit-Blöcke, siehe [Arbeitszeit-Blöcke hinterlegen](#bloecke-hinterlegen).' },
            { n: 5, text: '**Erste Zeiterfassung prüfen:** Die Mitarbeitenden melden sich an und stempeln; im [[Admin-Dashboard]] sehen Sie Stunden, Salden und fehlende Buchungen.' },
          ],
        },
        {
          kind: 'task',
          id: 'bundesland-einstellen',
          title: 'Wie stelle ich das Bundesland für die Feiertage ein?',
          intro: 'Klicken Sie in der Navigation auf [[Einstellungen]].',
          shot: 'pl-bundesland',
          steps: [
            { text: 'Scrollen Sie zum Abschnitt **Feiertage**.' },
            { n: 1, text: 'Wählen Sie Ihr **Bundesland**. PraxisZeit trägt dessen gesetzliche Feiertage ein; an Feiertagen gibt es kein Soll.' },
            { n: 2, text: 'Klicken Sie auf [[Speichern]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Später das Bundesland wechseln?** Dann berechnet PraxisZeit die gesetzlichen Feiertage aller Jahre neu – auch zurückliegender; Soll und Salden dieser Jahre ändern sich entsprechend. ' +
            'Eigene Feiertage bleiben erhalten. Betrifft die Änderung ein bereits abgeschlossenes Jahr, weist PraxisZeit auf den veralteten Übertrag hin.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Aufbewahrungspflicht (§ 16 ArbZG):** Arbeitszeitaufzeichnungen sind mindestens 2 Jahre aufzubewahren. Sorgen Sie von Anfang an für Datensicherungen.',
        },
      ],
    },

    // ── 2 ───────────────────────────────────────────────────────────────────
    {
      id: 'dashboard-teamuebersicht',
      title: 'Dashboard & Teamübersicht',
      blocks: [
        {
          kind: 'comic',
          scene: 'uebersicht',
          text:
            'Das **Admin-Dashboard** zeigt Soll, Ist und Saldo aller Mitarbeitenden. **Arbeitszeiten im Team** zeigt, wer laut Vertrag wann da ist – ' +
            'so fallen Lücken in der Besetzung sofort auf.',
        },
        {
          kind: 'task',
          id: 'fehlende-buchungen-team',
          title: 'Wer hat vergessen zu stempeln?',
          intro: 'Auf Ihrem eigenen [[Dashboard]] steht oben ein gelber Kasten, sobald im Team etwas fehlt.',
          shot: 'pl-fehlende-buchungen',
          steps: [
            {
              n: 1,
              text:
                '**Fehlende Buchungen im Team** erscheint nur, wenn bei mindestens einer Person etwas fehlt. Er nennt je Person die Tage: ein vergangener Arbeitstag des laufenden Monats ohne Zeiteintrag und ohne Abwesenheit, ' +
                'oder „(offen)“ für einen Eintrag eines früheren Tages ohne Ende. Feiertage und Tage ohne Tagessoll zählen nicht.',
            },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Die Mitarbeitenden sehen denselben Hinweis als roten Kasten „Buchung fehlt“ auf ihrem Dashboard und tragen den Tag per Antrag nach. ' +
            'Den Antrag entscheiden Sie unter [[Änderungsanträge]], siehe [Korrekturantrag prüfen](#korrekturantrag-pruefen).',
        },
        {
          kind: 'task',
          id: 'team-monatsuebersicht',
          title: 'Wie steht mein Team in diesem Monat?',
          intro: 'Klicken Sie in der Navigation auf [[Admin-Dashboard]]. Die Monatsübersicht zeigt alle aktiven Mitarbeitenden.',
          shot: 'pl-admin-dashboard',
          steps: [
            { n: 1, text: 'Mit [[Monat]] und [[Woche]] schalten Sie zwischen Monats- und Wochenansicht um. Ihre Wahl merkt sich der Browser.' },
            { n: 2, text: 'Mit den Pfeilen blättern Sie monats- bzw. wochenweise.' },
            { n: 3, text: '**Soll:** [[bis heute]] zählt das Soll nur bis zum letzten abgeschlossenen Arbeitstag, [[Monatsende]] den vollen Monat (in der Woche: [[volle Woche]]). Für abgeschlossene Monate sind beide gleich.' },
            { n: 4, text: '**Saldo** ist Ist minus Soll (Plus = Überstunden, Minus = Fehlstunden); **Überstd. kum.** ist der Stand des Überstundenkontos.' },
            { n: 5, text: 'Der Pfeil am Zeilenende öffnet die Details der Person.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Ist** ist die angerechnete Zeit – bei Arbeitszeit-Blöcken nach der Kappung – samt Gutschrift für Krankheit und Fortbildung. ' +
            'Die Einstellung „bis heute“ gilt nur für die Live-Übersichten. Datei-Exporte, Monatsjournal und Jahresabschluss rechnen immer den vollen Monat bzw. das volle Jahr.',
        },
        {
          kind: 'task',
          id: 'mitarbeiter-details-ansehen',
          title: 'Wie sehe ich die Einträge einer Person?',
          intro: 'Klicken Sie im Admin-Dashboard am Ende der Zeile auf den Pfeil.',
          shot: 'pl-mitarbeiter-details',
          steps: [
            { n: 1, text: 'Oben stehen Benutzerinformationen sowie Soll, Ist, Saldo und Überstunden kum. des gewählten Monats.' },
            { n: 2, text: '[[Neuer Eintrag]] legt für die Person einen Zeiteintrag oder eine Abwesenheit an.' },
            { n: 3, text: 'In der Liste der Zeiteinträge bearbeiten (Stift) oder löschen (Papierkorb) Sie einzelne Einträge. Ist Zeit nicht angerechnet, steht hier auch [[Anerkennen]].' },
          ],
        },
        {
          kind: 'task',
          id: 'arbeitszeiten-im-team',
          title: 'Wer arbeitet laut Vertrag wann?',
          intro: 'Klicken Sie in der Navigation auf [[Arbeitszeiten im Team]]. Je Person stehen die Arbeitszeit-Blöcke von Montag bis Freitag als Balken in ihrer Kalenderfarbe.',
          shot: 'pl-team-arbeitszeiten',
          steps: [
            { n: 1, text: '**Stand am:** Gezeigt werden die Blöcke, die an diesem Tag gelten. Ein späterer Tag zeigt schon eingetragene künftige Arbeitszeiten.' },
            { n: 2, text: '[[Alle]] oder eine Abteilung filtert die Liste. Die Auswahl entsteht aus dem Feld „Abteilung/Bereich“ der Mitarbeitenden.' },
            { n: 3, text: '**Besetzung** zeigt je halbe Stunde, wie viele der gefilterten Personen eingeplant sind – der Tooltip nennt die Namen.' },
            { n: 4, text: 'Je Person: Name, Wochenstunden und die Blöcke. Personen ohne Blöcke stehen mit „keine Arbeitszeit-Blöcke“ in der Liste.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Steht bei einer Person „ab … neu“, ist für sie eine spätere Änderung hinterlegt; die neuen Zeiten stehen im Tooltip. ' +
            'Wer am gewählten Tag außerhalb seines Beschäftigungszeitraums liegt, wird nicht aufgeführt.',
        },
        {
          kind: 'task',
          id: 'team-arbeitszeiten-bearbeiten',
          title: 'Kann ich Blöcke direkt in der Übersicht verschieben?',
          intro: 'Ja, als Entwurf. Gespeichert wird immer über den Dialog „Arbeitszeit & Wochenstunden“ – mit Vorschau und denselben Schutzregeln wie jede Arbeitszeit-Änderung.',
          shot: 'pl-team-bearbeiten',
          steps: [
            { n: 1, text: 'Schalten Sie rechts oben den Schieber [[Bearbeiten]] ein. Vorher lässt sich nichts verschieben.' },
            { n: 2, text: 'Einen Block **ziehen** verschiebt ihn; am linken oder rechten Rand ziehen ändert Beginn bzw. Ende, im 15-Minuten-Raster. Geänderte Zeilen sind gelb hinterlegt; [[Verwerfen]] stellt den gespeicherten Stand wieder her.' },
            { text: '[[Ändern…]] unter dem Namen öffnet den Dialog direkt – für Personen ohne Blöcke der einzige Weg. Nach dem Ziehen steht dort [[Änderung speichern…]]: Der Dialog öffnet mit den neuen Blöcken, „Gültig ab“ ist der Tag unter „Stand am“.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Per Tastatur: Block anwählen, Pfeiltasten verschieben um 15 Minuten, mit Umschalt ändert sich das Ende. Feinere Zeiten (5-Minuten-Raster), weitere Blöcke ' +
            'und die Pause innerhalb der Blöcke stellen Sie im Dialog ein. Solange Änderungen offen sind, ist „Stand am“ gesperrt.',
        },
      ],
    },

    // ── 3 ───────────────────────────────────────────────────────────────────
    {
      id: 'mitarbeitende-vertrag',
      title: 'Mitarbeitende anlegen, Vertragsdaten und Vertragsverlauf',
      blocks: [
        {
          kind: 'comic',
          scene: 'neuimteam',
          text:
            'Jede Person bekommt ein eigenes Konto. Wochenstunden, Arbeitstage, Urlaubsanspruch und Stundenzählung bilden ihren **Vertrag** – ' +
            'und jede spätere Änderung gilt ab einem Datum, damit frühere Monate stimmen.',
        },
        {
          kind: 'task',
          id: 'benutzerliste',
          title: 'Wo sehe ich alle Mitarbeitenden?',
          intro: 'Klicken Sie in der Navigation auf [[Benutzerverwaltung]].',
          shot: 'pl-benutzerliste',
          steps: [
            { n: 1, text: 'Oben rechts: [[Inaktive anzeigen]] bzw. [[Ausgeblendete anzeigen]] blendet deaktivierte bzw. ausgeblendete Konten ein; [[Neue:r Mitarbeiter:in]] öffnet das Anlegeformular.' },
            { n: 2, text: '**Urlaubskonto:** Budget, genommen und übrig in Tagen, mit Ampelbalken.' },
            { n: 3, text: '**Überstunden (JTD):** der Überstundensaldo seit Jahresbeginn. Bei Mitarbeitenden ohne Stundenzählung steht hier „—“.' },
          ],
        },
        {
          kind: 'task',
          id: 'benutzer-aktionen',
          title: 'Welche Aktionen gibt es je Person?',
          intro: 'Die Symbole stehen rechts in der Spalte **Aktionen**; ist das Fenster schmal, scrollen Sie die Tabelle nach rechts.',
          shot: 'pl-benutzer-aktionen',
          steps: [
            { n: 1, text: '**Monatsjournal anzeigen** (Buch): jeder Tag des Monats mit Zeiteinträgen und Abwesenheiten. Hier tragen Sie auch an Wochenend- und Feiertagen ein.' },
            { n: 2, text: '**Bearbeiten** (Stift): Name, Rolle, E-Mail, Abteilung, Ein- und Austritt.' },
            { n: 3, text: '**Arbeitszeit & Wochenstunden** (Uhr): Arbeitszeit und Vertragsdaten mit Wirkungsdatum ändern.' },
            { n: 4, text: '**Deaktivieren** (Person mit X): Die Person kann sich nicht mehr anmelden, ihre Daten bleiben erhalten. Über [[Inaktive anzeigen]] holen Sie sie mit „Reaktivieren“ zurück.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Weitere Symbole: **Passwort setzen**, **Vorjahresübernahme**, **Ausblenden** und **Als diese:n Mitarbeiter:in ansehen (nur Lesen)**. ' +
            'Diese Ansicht zeigt PraxisZeit aus Sicht der Person, ändern lässt sich dort nichts; ein Banner führt mit [[Zurück zu Admin]] zurück. ' +
            'Jede solche Sitzung wird protokolliert, Gesundheitsdaten erscheinen dort nur als „Abwesend“.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Nicht löschen, deaktivieren:** Arbeitszeitaufzeichnungen sind mindestens 2 Jahre aufzubewahren (§ 16 ArbZG). ' +
            'Das letzte aktive Admin-Konto lässt sich weder deaktivieren noch herabstufen – ernennen Sie vorher eine weitere Person zum Admin.',
        },
        {
          kind: 'task',
          id: 'mitarbeiter-anlegen',
          title: 'Wie lege ich eine neue Person an?',
          intro: 'Klicken Sie in der Benutzerverwaltung auf [[Neue:r Mitarbeiter:in]]. Über der Liste erscheint das Formular.',
          shot: 'pl-neu-anlegen',
          steps: [
            { n: 1, text: '**Benutzername:** eindeutiger Login-Name, z. B. „lena“. Dazu optional E-Mail, Vor- und Nachname.' },
            { n: 2, text: '**Passwort:** Startpasswort mit mindestens 10 Zeichen, einem Groß- und einem Kleinbuchstaben und einer Ziffer. Die Person ändert es danach selbst.' },
            { n: 3, text: '**Wochenstunden:** vertraglich vereinbart, in Viertelstunden-Schritten (z. B. 20,25).' },
            { n: 4, text: '**Arbeitstage pro Woche** (1–7).' },
            { n: 5, text: '**Urlaubstage:** Jahresanspruch in Tagen. Der Vorschlag rechnet 30 × Arbeitstage ÷ 5 – bei 4 Tagen also 24; [[Übernehmen]] trägt ihn ein, Sie können ihn überschreiben.' },
          ],
        },
        {
          kind: 'task',
          id: 'mitarbeiter-optionen',
          title: 'Was bedeuten die weiteren Felder im Anlegeformular?',
          intro: 'Scrollen Sie im Formular nach unten.',
          shot: 'pl-neu-anlegen-optionen',
          steps: [
            { text: '**Stundenzählung aktiv** (weiter oben): Haken weg für Mitarbeitende ohne Stundenzählung – kein Soll und Ist, keine Überstunden; Urlaub und Krankheit werden trotzdem tagebasiert geführt.' },
            { text: '**ArbZG-Prüfungen aussetzen (§18 ArbZG – leitende Angestellte):** nur für Personen, die tatsächlich unter § 18 ArbZG fallen. Darunter: **Nachtarbeitnehmer** (§ 6 ArbZG).' },
            { text: '**Nimmt an Betriebsferien teil:** Die Person bekommt bei Betriebsferien automatisch die Abwesenheiten – unabhängig von der Rolle. Für reine Verwaltungskonten abwählbar.' },
            { n: 1, text: '**Erster / Letzter Arbeitstag:** Soll wird nur innerhalb dieses Zeitraums berechnet, der Urlaubsanspruch im Ein- und Austrittsjahr anteilig.' },
            { n: 2, text: '**Arbeitszeit:** [[Gleichmäßig]], [[Nach Tagen]] (Stunden je Wochentag) oder [[Nach Arbeitsblöcken]] (Zeiten je Wochentag).' },
            { n: 3, text: 'Klicken Sie auf [[Speichern]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Eintritt im laufenden Jahr:** Tragen Sie den **Ersten Arbeitstag** ein. Ohne ihn zählt PraxisZeit das Soll auch für die Tage vor dem Eintritt – es entstehen Minusstunden, die es nicht gibt.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Zwei getrennte Haken:** „Stundenzählung aktiv“ entscheidet nur, ob Soll und Ist geführt werden; mit § 18 ArbZG hat das nichts zu tun. ' +
            'Die § 18-Ausnahme ist eine eigene Einstellung – beide lassen sich frei kombinieren. ' +
            'Wer aus einem anderen System kommt, trägt den bisherigen Stand unter **Anfangssaldo Überstunden** und **Übertrag Urlaubstage** ein.',
        },
        {
          kind: 'task',
          id: 'mitarbeiter-bearbeiten',
          title: 'Warum kann ich die Wochenstunden im Bearbeiten-Formular nicht ändern?',
          intro: 'Klicken Sie in der Aktionsspalte auf **Bearbeiten**. Alles, was das Soll oder den Urlaub bestimmt, gilt ab einem Datum und wird deshalb nicht hier geändert.',
          shot: 'pl-bearbeiten',
          steps: [
            { text: '**Wochenstunden** und Arbeitstage stehen nur als Anzeige da – immer die heute gültigen Werte.' },
            { n: 1, text: '[[Arbeitszeit anpassen…]] öffnet den Dialog „Arbeitszeit & Wochenstunden“; dort ändern Sie mit Wirkungsdatum.' },
            { n: 2, text: '**Urlaub und Abrechnung:** Urlaubsanspruch, Stundenzählung und Minijob-Einstellungen, ebenfalls nur Anzeige („Ändern über „Arbeitszeit anpassen…““).' },
            { text: '**Resturlaub verfällt am:** eine eigene Verfallsfrist für diese Person. Es ist ein festes Datum für alle Jahre – nach Ablauf anpassen oder leeren; leer gilt der 31.03. des Folgejahres. Liegt das Datum in der Vergangenheit, warnt das Formular (Speichern bleibt möglich). Das Datum steht im Urlaubskonto der Person und in der Jahresend-Warnung der Verwaltung.' },
          ],
        },
        {
          kind: 'task',
          id: 'vertragsverlauf',
          title: 'Wie ändere ich den Urlaubsanspruch oder die Arbeitszeit ab einem Datum?',
          intro:
            'Klicken Sie auf [[Arbeitszeit anpassen…]] oder in der Benutzerliste auf das Uhr-Symbol. Jede Änderung wird zu einer Zeile im **Verlauf** – ' +
            'dem Vertragsverlauf der Person.',
          shot: 'pl-vertragsverlauf',
          steps: [
            { text: '**Gültig ab:** ab wann die neue Regelung gilt.' },
            { n: 1, text: 'Unter **Urlaub und Abrechnung** stehen „Urlaubsanspruch pro Jahr ab diesem Datum“, „Stundenzählung aktiv“ und die Minijob-Einstellungen. Ändern Sie die Arbeitstage, schlägt der Dialog einen neuen Anspruch vor ([[Vorschlag übernehmen (N)]]).' },
            { n: 2, text: 'Prüfen Sie die Auswirkung über dem Knopf und klicken Sie auf [[Speichern]]. Solange die Eingabe dem Stand entspricht, der an diesem Datum ohnehin gilt, bleibt der Knopf gesperrt.' },
            { n: 3, text: '**Verlauf:** jede Regelung als „Ab … bis …“; die jüngste läuft „bis heute“.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Anspruch wechselt im Jahr:** Dann rechnet PraxisZeit jeden Abschnitt anteilig nach Monaten. Beispiel: 16 Tage bis September, 18 Tage ab 1. Oktober ergeben ' +
            '16 × 9/12 + 18 × 3/12 = **16,5 Tage** für das Jahr, ab dem Folgejahr 18.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Minijob-Einstellungen** (MiLoG-Arbeitszeitkonto, vereinbarte Monatsarbeitszeit, festes Monats-Soll) lassen sich nur zum **Monatsersten** ändern. ' +
            'Sinkt der Urlaubsanspruch rückwirkend, ist das eine Verkürzung und braucht einen Grund, siehe [Rückwirkend ändern](#rueckwirkend-aendern).',
        },
      ],
    },

    // ── 4 ───────────────────────────────────────────────────────────────────
    {
      id: 'arbeitszeit-bloecke-aenderungen',
      title: 'Arbeitszeit-Blöcke & Änderungen',
      blocks: [
        {
          kind: 'comic',
          scene: 'bloecke',
          text:
            '**Arbeitszeit-Blöcke** legen je Wochentag fest, wann eine Person laut Vertrag arbeitet – z. B. 08:00–12:00 und 15:00–16:00. ' +
            'Daraus folgen das Tagessoll und die Anrechnung: Zeit vor, nach und zwischen den Blöcken zählt nur bis zum Puffer.',
        },
        {
          kind: 'task',
          id: 'bloecke-hinterlegen',
          title: 'Wie hinterlege ich Arbeitszeit-Blöcke?',
          intro: 'Öffnen Sie den Dialog „Arbeitszeit & Wochenstunden“ (Uhr-Symbol in der Benutzerliste oder [[Arbeitszeit anpassen…]]).',
          shot: 'pl-bloecke',
          steps: [
            { n: 1, text: '**Gültig ab:** ab wann die Blöcke gelten.' },
            { n: 2, text: 'Wählen Sie [[Nach Arbeitsblöcken]]. Den Modus gibt es nur bei aktiver Stundenzählung.' },
            { n: 3, text: 'Je Wochentag (Mo–Fr) tragen Sie „von–bis“ ein, im 5-Minuten-Raster. Blöcke dürfen sich nicht überschneiden und nicht direkt aneinanderstoßen – 08:00–12:00 und 12:00–16:00 erfassen Sie als einen Block.' },
            { n: 4, text: '[[+ Block]] fügt einen weiteren Block hinzu (höchstens drei je Tag), das **×** entfernt einen. Ein Tag ohne Block ist kein Arbeitstag.' },
            { n: 5, text: '**Pause innerhalb** der Blöcke in Minuten. Tagessoll = Summe der Blöcke minus diese Pause; der Dialog zeigt es je Tag live.' },
            { text: 'Unter dem Freitag steht die Woche mit Gesamtzeit, Wochensoll und Arbeitstagen. Prüfen Sie die Auswirkung und speichern Sie.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Beispiel:** Blöcke 08:00–12:00 und 15:00–18:00, Pause 0, Puffer 15 Minuten. Wer von 08:00 bis 18:00 durchstempelt, bekommt 08:00–12:15 und 14:45–18:00 = **7:30 h** angerechnet; ' +
            'die 2:30 h dazwischen werden nicht angerechnet. Die gestempelten Zeiten bleiben unverändert gespeichert (§ 16 ArbZG). ' +
            'Eine geplante Pause erfassen Sie als „Pause innerhalb der Blöcke“, nicht als kurze Lücke – eine Lücke bis zum doppelten Puffer verschwindet ganz.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Werktag ohne Block = 0 Stunden:** Hat eine Person Blöcke, aber an einem Werktag keinen, wird dort gestempelte Zeit gespeichert, aber nicht angerechnet – erst wenn Sie den Eintrag anerkennen oder den Antrag „Anrechnung beantragen“ mit [[Genehmigen und anerkennen]] annehmen. ' +
            'Ein aus früheren Versionen übernommenes Arbeitszeit-Fenster ist davon nicht betroffen: Ein Tag ohne Fenster wird dort weiter nicht gekappt. ' +
            'An Wochenenden, Feiertagen und als „frei“ eingestellten Sondertagen wird nichts gekappt. Mitarbeitende ohne Stundenzählung und anerkannte Einträge sind ausgenommen; ' +
            'bei § 18-befreiten Personen wird trotzdem gekappt.',
        },
        {
          kind: 'task',
          id: 'rueckwirkend-aendern',
          title: 'Was passiert, wenn ich die Arbeitszeit rückwirkend ändere?',
          intro:
            'Liegt „Gültig ab“ in der Vergangenheit, rechnet PraxisZeit die erfassten Zeiteinträge an den geänderten Wochentagen neu – immer vom Stempel aus – und danach die gebuchten Abwesenheiten. ' +
            'Im Beispiel endet Sarahs Montagnachmittag rückwirkend um 15:30 statt 16:00.',
          shot: 'pl-rueckwirkend',
          steps: [
            { n: 1, text: '**Verkürzung:** Verliert ein Eintrag angerechnete Zeit, sinkt das Überstundenkonto im Wirkungsbereich oder sinkt die Gutschrift einer Abwesenheit an einem Tag mit Arbeit stärker als das Tagessoll, erscheint dieser Kasten mit den Gründen, z. B. „2 Einträge verlieren angerechnete Zeit (zusammen 0:30 h)“.' },
            { n: 2, text: '**Ab heute … wirksam** (Standard): Die Änderung gilt ab dem frühesten Tag, an dem nichts verloren geht. Vergangene Einträge bleiben unverändert; ein Grund ist nicht nötig.' },
            { n: 3, text: '**Rückwirkend ab … mit Neuberechnung:** nur mit Grund, Begründung und Bestätigung.' },
            { n: 4, text: '**Grund:** „Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)“, „Mit der beschäftigten Person vereinbart“ oder „Sonstiges“.' },
            { n: 5, text: '**Begründung:** 10 bis 400 Zeichen. Danach bestätigen Sie den Haken zum gewählten Grund.' },
          ],
        },
        {
          kind: 'task',
          id: 'auswirkung-pruefen',
          title: 'Was zeigt mir die Auswirkung vor dem Speichern?',
          intro:
            'Ist „Gültig ab“ rückwirkend oder betrifft die Änderung schon Erfasstes, steht über [[Speichern]] ein Auswirkungs-Kasten. ' +
            'Er zeigt die gewählte Variante – hier die rückwirkende.',
          shot: 'pl-auswirkung',
          steps: [
            { n: 1, text: '**Überschrift:** der Anlass und der Wirkungsbereich, z. B. „Rückwirkende Änderung: 14.10.2026 – …“. Darunter Puffer, geänderte Tage und das Tagessoll je Wochentag vorher → nachher.' },
            { n: 2, text: '**Zeiteinträge:** wie viele neu berechnet werden, je Monat mit der angerechneten Zeit vorher → nachher; übersprungene mit Grund. Danach die Zahl der Abwesenheiten, deren Stunden umgestellt werden.' },
            { n: 3, text: '**Tabelle** mit den Spalten bisher, neu und Δ: **Überstunden** und **Urlaub verbraucht** (bei geändertem Anspruch auch **Urlaubsanspruch**) mit allen drei Werten; für **Soll im Zeitraum** und **Angerechnet** steht nur die Differenz Δ.' },
            { n: 4, text: '[[Einzelheiten]] listet jeden Eintrag mit seinen Zeiten vorher → nachher.' },
            { n: 5, text: 'Setzen Sie den Haken [[Ich habe die Auswirkungen geprüft und möchte speichern]] und klicken Sie auf [[Speichern]]. PraxisZeit meldet danach, wie viele Einträge neu berechnet wurden.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit.** Eine rückwirkende Arbeitszeit-Änderung berichtigt nur eine falsch hinterlegte Arbeitszeit. ' +
            'Bei „Sonstiges“ warnt der Dialog zusätzlich: Eine einseitige rückwirkende Kürzung deckt das Direktionsrecht nicht (§ 106 GewO); geleistete Arbeit bleibt zu vergüten.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Auch eine Erhöhung kann eine Verkürzung sein:** Steigt das Soll rückwirkend (längere Blöcke, mehr Wochenstunden), sinkt das Überstundenkonto – dann gelten dieselben Regeln. ' +
            'Reicht die Änderung in ein abgeschlossenes Jahr, weist der Dialog darauf hin. Führen Sie danach den Jahresabschluss für **jedes** genannte Jahr erneut aus, vom frühesten an. ' +
            '**Achtung:** Ein erneuter Jahresabschluss überschreibt die Überträge **aller** Mitarbeitenden für das Folgejahr – auch von Hand korrigierte Werte in der **Vorjahresübernahme**; tragen Sie solche Korrekturen danach erneut ein.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Änderung löschen:** Das Papierkorb-Symbol steht nur an der jüngsten Zeile des Verlaufs. Das Löschen rechnet Einträge und Abwesenheiten zurück; ' +
            'verkürzt es, setzt PraxisZeit standardmäßig ab heute auf den vorherigen Stand zurück ([[Zurücksetzen]]) – rückwirkend nur mit Grund.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Wer davon erfährt:** Die Person sieht nach jeder Arbeitszeit-Änderung 30 Tage lang den Kasten „Hinweis zu Ihrer Arbeitszeit“ auf ihrem Dashboard – bei einer rückwirkenden Verkürzung mit dem Grundtyp, nie mit Ihrer Begründung. ' +
            'Das Änderungsprotokoll hält jede Neuberechnung fest.',
        },
        {
          kind: 'task',
          id: 'nicht-angerechnet-anerkennen',
          title: 'Wie rechne ich Zeit außerhalb der Blöcke doch an?',
          intro:
            'Nicht angerechnete Zeit steht als Zusatzzeile unter der Uhrzeit – im Monatsjournal (Buch-Symbol in der Benutzerliste) und in der Detailansicht des Admin-Dashboards.',
          shot: 'pl-anerkennen',
          steps: [
            { n: 1, text: 'Die Zusatzzeile nennt Stempel, angerechnete Zeit und den nicht angerechneten Teil, z. B. „gestempelt 08:00–16:00 · angerechnet 5:30 h · 2:30 h zwischen den Blöcken nicht angerechnet“.' },
            {
              n: 2,
              text:
                'Wurde in dieser Zeit tatsächlich gearbeitet, klicken Sie auf [[Anerkennen]] und bestätigen. Dann wird die gesamte gestempelte Zeit angerechnet – dauerhaft, auch bei späteren Neuberechnungen. Der Vorgang wird protokolliert.',
            },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Anerkennen lässt sich nicht zurücknehmen.** Wurde nur ein Teil der Zeit gearbeitet, teilen oder korrigieren Sie den Eintrag besser. ' +
            'Ein offener Eintrag lässt sich erst nach dem Ausstempeln anerkennen, ein automatisch geschlossener erst, wenn das tatsächliche Ende eingetragen ist. ' +
            'Nichtanrechnung ersetzt keine Vergütungsentscheidung: angeordnete, gebilligte oder geduldete Arbeit ist zu vergüten.',
        },
      ],
    },

    // ── 5 ───────────────────────────────────────────────────────────────────
    {
      id: 'antraege-genehmigen',
      title: 'Anträge genehmigen: Urlaub und Korrektur',
      blocks: [
        {
          kind: 'comic',
          scene: 'antrag',
          text:
            'Urlaubsanträge landen unter **Anträge**, Korrekturen an Zeiteinträgen unter **Änderungsanträge**. ' +
            'Eine rote Zahl in der Navigation zeigt, was offen ist.',
        },
        {
          kind: 'task',
          id: 'urlaubsantrag-genehmigen',
          title: 'Wie genehmige ich einen Urlaubsantrag?',
          intro: 'Klicken Sie in der Navigation auf [[Anträge]]. Die Seite heißt „Abwesenheitsanträge“.',
          shot: 'pl-urlaubsantraege',
          steps: [
            { n: 1, text: '**Abwesenheitsanträge genehmigungspflichtig:** Ist der Schalter an, landen Urlaubsanträge hier als „Offen“. Aus, buchen die Mitarbeitenden direkt. Krankmeldungen brauchen nie eine Freigabe.' },
            { text: 'Mit [[Offen]], [[Genehmigt]], [[Abgelehnt]] und [[Alle]] filtern Sie die Anträge.' },
            { text: '**Arbeitstage** auf der Karte: was der Antrag nach der Genehmigung tatsächlich kostet – nur Tage, an denen die Person laut ihrem Arbeitsplan arbeitet; Wochenenden, Feiertage und freie Sondertage zählen nicht, ein halber Tag 0,5.' },
            { n: 2, text: '[[Genehmigen]] trägt die Abwesenheiten für diese Arbeitstage ein und zieht sie vom Urlaubskonto ab.' },
            { text: '[[Bearbeiten]] ändert den Zeitraum vor der Entscheidung, z. B. wenn er über den letzten Arbeitstag hinausgeht.' },
            { text: '[[Ablehnen]] öffnet ein Feld für den Ablehnungsgrund (optional); bestätigen Sie mit [[Ablehnen]]. Die Person sieht den Grund unter „Meine Anträge“.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Vorhandene Zeiteinträge** an den genehmigten Tagen werden durch die Abwesenheit ersetzt (im Änderungsprotokoll dokumentiert). ' +
            'Zeigt die Karte **0** Arbeitstage, lehnt PraxisZeit die Genehmigung ab – lehnen Sie den Antrag dann ab oder passen Sie ihn an.',
        },
        {
          kind: 'task',
          id: 'urlaub-stornieren-admin',
          title: 'Wie nehme ich einen genehmigten Urlaub zurück?',
          intro: 'Das geht, solange der Urlaub noch nicht begonnen hat.',
          steps: [
            { n: 1, text: 'Wählen Sie auf der Seite „Abwesenheitsanträge“ den Filter [[Genehmigt]].' },
            { n: 2, text: 'Klicken Sie am Antrag auf [[Urlaub stornieren]] und bestätigen Sie mit [[Stornieren]].' },
            { n: 3, text: 'Die zugehörigen Abwesenheitstage werden gelöscht; der Antrag steht danach als „Zurückgezogen“ da.' },
          ],
        },
        {
          kind: 'task',
          id: 'korrekturantrag-pruefen',
          title: 'Wie prüfe ich einen Korrekturantrag?',
          intro: 'Klicken Sie in der Navigation auf [[Änderungsanträge]]. Mitarbeitende beantragen hier Änderungen, Löschungen und Nachträge für vergangene Tage.',
          shot: 'pl-korrekturantrag',
          steps: [
            { text: 'Mit [[Offen]], [[Genehmigt]], [[Abgelehnt]] und [[Alle]] filtern Sie; die Auswahl darunter zeigt nur eine Person.' },
            { n: 1, text: '**Aktuell:** der Eintrag, wie er heute gespeichert ist.' },
            { n: 2, text: '**Gewünscht:** die beantragten Werte.' },
            { n: 3, text: 'Lesen Sie die **Begründung** – sie ist Pflicht.' },
            { n: 4, text: '[[Genehmigen]] übernimmt die Werte in den Zeiteintrag. [[Ablehnen]] fragt nach einem optionalen Ablehnungsgrund.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Die Genehmigung prüft dieselben Regeln wie ein direkter Eintrag: Arbeitszeit-Blöcke, Pausen nach § 4 ArbZG und den Beschäftigungszeitraum. ' +
            'Liegt der Tag eines neuen Eintrags – oder das neue Datum eines verschobenen – vor dem ersten oder nach dem inzwischen eingetragenen letzten Arbeitstag, lehnt PraxisZeit die Genehmigung ab – lehnen Sie den Antrag dann ab. ' +
            'Ein Abwesenheits-Antrag für einen vergangenen Tag ersetzt bei Genehmigung die Zeiteinträge dieses Tages.',
        },
        {
          kind: 'task',
          id: 'anrechnung-beantragt',
          title: 'Eine Person beantragt die Anrechnung – was tue ich?',
          intro:
            'Hat eine Person an einem Eintrag mit nicht angerechneter Zeit [[Anrechnung beantragen]] gewählt, trägt ihr Antrag ein eigenes Kennzeichen. ' +
            'Vorbelegt sind die gestempelten Zeiten.',
          shot: 'pl-anrechnung-beantragt',
          steps: [
            { n: 1, text: '**Anrechnung beantragt:** das Kennzeichen des Antrags.' },
            { n: 2, text: 'Unter **Aktuell** stehen die nicht angerechnete Lücke und die Stempel des Eintrags. Weichen die beantragten Zeiten von den Stempeln ab, steht das rot unter **Gewünscht**.' },
            { n: 3, text: '[[Genehmigen und anerkennen]] übernimmt den Antrag und rechnet die Zeiten ungekappt an – dauerhaft, wie [[Anerkennen]].' },
            { n: 4, text: '[[Ohne Anerkennen genehmigen]] übernimmt nur die Zeiten; die Zeit vor, nach oder zwischen den Blöcken bleibt nicht angerechnet.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Auch bei einem gewöhnlichen Änderungsantrag zu einem Eintrag mit nicht angerechneter Zeit bietet die Prüfung neben [[Genehmigen]] zusätzlich [[Genehmigen und anerkennen]] an. ' +
            'Ihren eigenen Antrag genehmigt eine weitere Admin, sofern es eine gibt.',
        },
        {
          kind: 'task',
          id: 'sammel-genehmigung',
          title: 'Kann ich mehrere Anträge auf einmal genehmigen?',
          intro: 'Ja – auf der Seite „Änderungsanträge“ im Filter [[Offen]].',
          shot: 'pl-sammel-genehmigung',
          steps: [
            { n: 1, text: 'Das Kästchen oben wählt alle offenen Anträge aus.' },
            { n: 2, text: 'Einzelne Anträge markieren oder abwählen Sie über das Kästchen an der Karte.' },
            {
              n: 3,
              text:
                'Klicken Sie auf **… genehmigen** bzw. **… ablehnen**. Sind Anrechnungsanträge dabei, nennt der Knopf ihre Zahl („2 genehmigen, davon 1 mit Anerkennen“) und fragt vor dem Absenden nach; diese werden dann anerkannt.',
            },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Einen Anrechnungsantrag ohne Anerkennen zu genehmigen geht nur einzeln. Hinweise wie bei der Einzel-Genehmigung (Kappung, Wochen- oder Nachtarbeitszeit) ' +
            'erscheinen auch hier, jeweils mit dem Namen der Person. Prüfen Sie Anträge zeitnah, damit die Salden aktuell bleiben.',
        },
      ],
    },

    // ── 6 ───────────────────────────────────────────────────────────────────
    {
      id: 'abwesenheiten-betriebsferien',
      title: 'Abwesenheiten & Betriebsferien',
      blocks: [
        {
          kind: 'comic',
          scene: 'urlaub',
          text:
            'Unter **Abwesenheiten** im Bereich Administration tragen Sie Urlaub, Krankheit oder Fortbildung für eine Person ein. ' +
            '**Betriebsferien** schließen die ganze Praxis – PraxisZeit bucht die Tage für alle Teilnehmenden auf einmal.',
        },
        {
          kind: 'task',
          id: 'abwesenheit-fuer-person',
          title: 'Wie trage ich eine Abwesenheit für eine Person ein?',
          intro:
            'Klicken Sie in der Navigation unter Administration auf [[Abwesenheiten]]. Die Seite heißt „Abwesenheiten verwalten“; ' +
            'der Tab [[Mitarbeiter-Abwesenheiten]] listet alle Personen mit ihren Abwesenheiten im gewählten Monat.',
          shot: 'pl-abwesenheit-eintragen',
          steps: [
            { n: 1, text: 'Wählen Sie unter **Mitarbeiter** die Person – oder klicken Sie in der Liste bei ihr auf [[+ Eintragen]]. Oben rechts steht dann [[Abwesenheit eintragen]].' },
            { n: 2, text: 'Mehrere Tage? Setzen Sie den Haken bei [[Zeitraum (mehrere Tage)]]. Für einen einzelnen Tag gibt es [[Halber Tag (zählt als 0,5 Tag)]] – nicht bei Krank und Überstundenausgleich.' },
            { n: 3, text: 'Wählen Sie das **Datum** – beim Zeitraum **Von** und **Bis**. Anders als die Mitarbeitenden tragen Sie auch vergangene Tage direkt ein.' },
            { n: 4, text: '**Typ:** Urlaub, Krank, Fortbildung (außer Haus), Überstundenausgleich, Bezahlte Freistellung (kein Urlaubsabzug), Sonstiges – oder unter „Eigene Gründe“ ein Grund Ihrer Praxis.' },
            { text: '**Stunden:** Das Feld bleibt ausgegraut, solange es nichts einzutragen gibt – gebucht wird immer das Tagessoll des Tages laut Vertrag („Es wird das Tagessoll laut Vertrag gebucht“). Nur beim Überstundenausgleich (auch als eigener Grund „Überstundenabbau“) ist das Feld frei: Der eingetragene Wert geht vom Überstundenkonto ab – bei Personen mit Tagesplan bucht das System stattdessen das Tagessoll des Tages.' },
            { n: 5, text: 'Klicken Sie auf [[Speichern]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Nur an Arbeitstagen:** Wochenenden, Feiertage, als „frei“ eingestellte Sondertage und Tage ohne geplante Arbeitszeit (freie Wochentage, 0 Wochenstunden etwa in der Elternzeit) bleiben ausgenommen; ' +
            'bei Mitarbeitenden ohne Stundenzählung zählt jeder Werktag. Zeiteinträge der eingetragenen Tage werden ersetzt, Einträge an ausgenommenen Tagen bleiben stehen. ' +
            'Liegt im Zeitraum kein einziger Tag mit geplanter Arbeitszeit, lehnt PraxisZeit die Buchung ab.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Löschen:** Ohne gewählte Person klappt ein Klick auf den Namen die Abwesenheiten auf; der Papierkorb ([[Löschen]]) löscht eine Abwesenheit. ' +
            'Mitarbeitende beantragen die Löschung einer vergangenen Abwesenheit mit [[Löschung beantragen]] – der Antrag kommt als **Löschung** unter [[Änderungsanträge]] zu Ihnen. ' +
            'Betriebsferien-Tage ändert nur die Verwaltung.',
        },
        {
          kind: 'task',
          id: 'betriebsferien-anlegen',
          title: 'Wie lege ich Betriebsferien an?',
          intro: 'Wechseln Sie auf derselben Seite zum Tab [[Betriebsferien]] und klicken Sie oben rechts auf [[Betriebsferien erstellen]].',
          shot: 'pl-betriebsferien',
          steps: [
            { n: 1, text: '**Bezeichnung**, z. B. „Weihnachtsschließzeit 2026“.' },
            { n: 2, text: '**Von** und **Bis**: der Zeitraum der Schließung.' },
            { n: 3, text: '**Verrechnung:** [[Als Urlaub werten]] (Standard) zieht jeden gebuchten Schließtag vom Urlaubskonto ab – 1 Tag je Arbeitstag. [[Bezahlte Freistellung]] wirkt wie ein Feiertag: kein Urlaubsabzug, das Überstundenkonto bleibt unberührt.' },
            { n: 4, text: 'Klicken Sie auf [[Betriebsferien erstellen & Urlaub eintragen]]. Jede teilnehmende Person bekommt für jeden ihrer Arbeitstage im Zeitraum eine Abwesenheit; vorhandene Zeiteinträge dieser Tage werden ersetzt (im Änderungsprotokoll dokumentiert).' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Wer bekommt die Tage?** Alle aktiven Mitarbeitenden mit dem Haken **Nimmt an Betriebsferien teil** (Standard) – unabhängig von der Rolle. ' +
            'Kein Eintrag entsteht an Wochenenden, Feiertagen, „frei“ eingestellten Sondertagen, Tagen ohne geplante Arbeitszeit, außerhalb des Beschäftigungszeitraums ' +
            'und an Tagen mit einer anderen Abwesenheit. Fällt diese später weg, bucht PraxisZeit den Schließtag nach – außer es steht inzwischen ein Zeiteintrag am Tag. ' +
            'Setzen Sie den Haken nachträglich, trägt PraxisZeit die laufenden und künftigen Betriebsferien automatisch nach.',
        },
        {
          kind: 'task',
          id: 'betriebsferien-aendern',
          title: 'Wie ändere oder lösche ich Betriebsferien?',
          intro: 'Unter dem Tab [[Betriebsferien]] stehen alle Schließungen als Tabelle.',
          shot: 'pl-betriebsferien-liste',
          steps: [
            { n: 1, text: 'Je Schließung: Bezeichnung, Zeitraum, Verrechnung und unter **Betroffene MA**, für wie viele Personen Tage gebucht sind.' },
            { n: 2, text: 'In der Spalte **Aktion**: **Bearbeiten** (Stift) – Ändern Sie den Zeitraum, bekommen neu hinzukommende Arbeitstage einen Eintrag und entfallene werden entfernt; eine umgestellte Verrechnung ändert den Typ der Einträge. Abweichende Einträge einzelner Personen bleiben unberührt. Speichern mit [[Änderungen speichern]]. Das erneute Speichern entfernt auch alte 0-Stunden-Einträge (Betriebsferien von vor 1.20.0) an Tagen ohne Soll; liegen sie in einem abgeschlossenen Jahr, prüfen Sie danach den Übertrag. **Löschen** (Papierkorb) – Die Abwesenheiten werden bei allen Personen entfernt.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Abgeschlossenes Jahr:** Ändert das Anlegen, Speichern oder Löschen Buchungen in einem Jahr mit Jahresabschluss, meldet PraxisZeit z. B. ' +
            '„Jahresabschluss 2026 bereits erfolgt — Carryover 2027 ist nun veraltet, bitte Jahresabschluss erneut ausführen.“ Der Übertrag ändert sich nicht von selbst: ' +
            'Prüfen und korrigieren Sie ihn oder führen Sie den Jahresabschluss erneut aus (dabei werden von Hand korrigierte Überträge überschrieben). Reines Umbenennen löst den Hinweis nicht aus.',
        },
        {
          kind: 'task',
          id: 'betriebsferien-ueberstundenabbau',
          title: 'Die Betriebsferien sind länger als der Resturlaub – was passiert?',
          intro: 'Das steuert ein Schalter unter [[Einstellungen]] → **Betriebsferien & Urlaub**. Er gilt nur für Betriebsferien, die als Urlaub zählen.',
          shot: 'pl-betriebsferien-urlaub',
          steps: [
            {
              n: 1,
              text:
                '**Überzählige Betriebsferien als Überstundenabbau** – aus (Standard): Alle Schließtage zählen als Urlaub, reicht der Resturlaub nicht, entstehen Minus-Urlaubstage. ' +
                'An: Erst wird der Urlaub aufgezehrt, die übrigen Tage bucht PraxisZeit als Überstundenausgleich – das Überstundenkonto darf dabei ins Minus gehen.',
            },
            { n: 2, text: 'Klicken Sie auf [[Speichern]].' },
            { text: 'Der Schalter wirkt beim Anlegen und erneuten Speichern. Bereits eingetragene Betriebsferien öffnen Sie einmal und speichern sie erneut – dann rechnet PraxisZeit sie nach derselben Regel neu.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Pflichturlaub darf ins Minus:** Betriebsferien werden zwingend gebucht, auch über das Urlaubsbudget hinaus – anders als ein Urlaubsantrag oder eine direkte Buchung, die PraxisZeit bei fehlendem Resturlaub ablehnt. ' +
            'Mit eingeschaltetem Schalter verteilt PraxisZeit den Urlaub nach Datum (frühere Schließung zuerst); privater Urlaub im selben Jahr geht immer vor.',
        },
      ],
    },

    // ── 7 ───────────────────────────────────────────────────────────────────
    {
      id: 'sondertage-verkuerzte-tage',
      title: 'Sondertage & verkürzte Tage',
      blocks: [
        {
          kind: 'comic',
          scene: 'sondertage',
          text:
            'Heiligabend und Silvester sind keine gesetzlichen Feiertage. Ob dort voll, halb oder gar nicht gearbeitet wird, legen Sie selbst fest – ' +
            'ebenso einzelne **verkürzte Tage** wie Rosenmontag oder einen Betriebsausflug.',
        },
        {
          kind: 'task',
          id: 'sondertage-einstellen',
          title: 'Wie stelle ich den 24. und 31.12. ein?',
          intro: 'Klicken Sie auf [[Einstellungen]] und scrollen Sie zum Abschnitt **Sondertage (24./31.12.)**. Beide Tage stellen Sie getrennt ein.',
          shot: 'pl-sondertage',
          steps: [
            { n: 1, text: '**Modus** je Tag: [[Arbeitstag]] (Standard), [[Halbtag]], [[Frei]] oder [[Verkürzt auf X Stunden]]. Bei „Verkürzt“ erscheint daneben **Höchstens (Stunden)**: 0,25 bis 12 Stunden in Schritten von 0,25.' },
            { n: 2, text: '**Anrechnung** (nur bei „Frei“): [[Urlaub]] zieht den freien Tag vom Urlaubskonto ab, [[Bezahlte Freistellung]] nicht – wie ein Feiertag.' },
            { n: 3, text: 'Klicken Sie auf [[Speichern]]. Der Knopf wird erst aktiv, wenn Sie etwas geändert haben.' },
          ],
        },
        {
          kind: 'table',
          head: ['Modus', 'Tagessoll', 'Ein Urlaubstag an diesem Tag kostet'],
          rows: [
            ['Arbeitstag', 'volles Tagessoll', '1 Tag'],
            ['Halbtag', 'halbes Tagessoll', '0,5 Tage'],
            ['Frei', '0, wie ein Feiertag', 'mit Anrechnung „Urlaub“ zieht der Tag selbst 1 Urlaubstag ab; mit „Bezahlte Freistellung“ nichts'],
            ['Verkürzt auf X Stunden', 'die kleinere Zahl aus Tagessoll und X', '0,5 Tage'],
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Die Einstellung gilt für **alle Jahre**, auch zurückliegende. Betroffene Betriebsferien bucht PraxisZeit beim Speichern selbst neu; ' +
            'ändert sich ein Jahr mit Jahresabschluss, erscheint dort nur der Hinweis auf den veralteten Übertrag. ' +
            'Wechselt ein Tag zwischen „Frei“ und Arbeitstag bzw. Halbtag, nennt PraxisZeit bestehende Zeiteinträge dieses Tages, deren Anrechnung sich ändern müsste – unverändert neu speichern berechnet sie neu.',
        },
        {
          kind: 'task',
          id: 'verkuerzte-tage',
          title: 'Wie verkürze ich einen einzelnen Tag, z. B. Rosenmontag?',
          intro: 'Unter [[Einstellungen]] → **Verkürzte Tage**, direkt unter den Sondertagen.',
          shot: 'pl-verkuerzte-tage',
          steps: [
            { n: 1, text: 'Wählen Sie oben rechts das **Jahr**.' },
            { n: 2, text: 'Tragen Sie in der Eingabezeile das **Datum** des Tages ein (für den 24. und 31.12. nimmt PraxisZeit keinen Eintrag an – dafür gibt es die Sondertage), eine **Bezeichnung** wie „Rosenmontag“ oder „Betriebsausflug“ und **Höchstens (Stunden)**: 0,25 bis 12, in Schritten von 0,25. Klicken Sie auf [[Hinzufügen]]. Je Datum gibt es genau einen Eintrag.' },
            { n: 3, text: 'Eingetragene Tage stehen darunter. Ein Klick auf die Bezeichnung macht sie änderbar, ebenso die Stunden; danach erscheint [[Speichern]]. [[Löschen]] entfernt den Tag.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**So wirkt ein verkürzter Tag:** Das Soll ist die kleinere Zahl aus Tagessoll und Höchstwert – wer ohnehin weniger Soll hat, behält es. Ein Feiertag geht vor, am Wochenende wirkt der Tag nicht. ' +
            'Urlaub kostet 0,5 Tage; Krank und Fortbildung zählen anteilig (8 h Soll, höchstens 4 h → 4 h Soll und 4 h Gutschrift, Saldo 0). ' +
            'Angerechnet wird weiter die gestempelte Zeit, sie wird nicht auf den Höchstwert gekappt; die Arbeitszeit-Blöcke bleiben unverändert.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Mitarbeitende sehen den Tag im Kalender als „Brückentag: verkürzter Tag (max. 4 h)“ und auf der Stempelkarte als „verkürzter Tag (max. 4 h)“. ' +
            'Auch jede Änderung hier bucht betroffene Betriebsferien neu; in abgeschlossenen Jahren erscheint nur der Hinweis.',
        },
      ],
    },

    // ── 8 ───────────────────────────────────────────────────────────────────
    {
      id: 'berichte-exporte',
      title: 'Berichte & Exporte',
      blocks: [
        {
          kind: 'comic',
          scene: 'nachweise',
          text:
            'Für Lohnbuchhaltung, Steuerberatung und Betriebsprüfung exportieren Sie Monats- und Jahresberichte als Excel, ODS oder PDF. ' +
            'Die Dateien sind Ihr Nachweis nach § 16 ArbZG.',
        },
        {
          kind: 'task',
          id: 'monatsreport-exportieren',
          title: 'Wie exportiere ich den Monatsreport?',
          intro: 'Klicken Sie in der Navigation auf [[Berichte]]. Die Seite heißt „Berichte & Export“; oben steht **Monatsreport exportieren**.',
          shot: 'pl-monatsreport',
          steps: [
            { n: 1, text: 'Wählen Sie unter **Monat auswählen** den Monat.' },
            { n: 2, text: 'Optional: [[Krankheitsdaten einschließen (Art. 9 DSGVO)]]. Ohne den Haken steht im Export „Abwesenheit“ statt „Krank“.' },
            { n: 3, text: 'Optional: [[Ausgeblendete Mitarbeitende einbeziehen]] – etwa die Praxisinhaberin, wenn sie stempelt. Ausgeschiedene sind immer enthalten, wenn sie im Zeitraum Einträge oder Abwesenheiten haben.' },
            { n: 4, text: 'Klicken Sie auf das Format – die Markierung sitzt am Knopf [[PDF (.pdf)]], daneben stehen [[Excel (.xlsx)]] und [[ODS (.ods)]]. Die Datei wird heruntergeladen – je Person ein Blatt mit allen Tagen und einer Zusammenfassung.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Krankheitsdaten (Art. 9 DSGVO)** sind besondere Kategorien personenbezogener Daten; jeder Export mit dem Haken wird im Änderungsprotokoll vermerkt. ' +
            'Ohne den Haken steht auch bei eigenen Abwesenheitsgründen „Abwesenheit“ (die Notiz entfällt), und das Kennzeichen „Nachtarbeitnehmer“ im Kopf jedes Blatts zeigt „–“. ' +
            '„Sonstiges“/„unbezahlt frei“ und „Bez. Freistellung“ stehen immer im Klartext.',
        },
        {
          kind: 'table',
          head: ['Spalte (Tageszeile)', 'Bedeutung'],
          rows: [
            ['Von / Bis', 'Rahmen des Tages: erster Beginn, letztes Ende – bei Arbeitszeit-Blöcken die gekappten Zeiten'],
            ['Pause (Min)', 'die erfasste Pause'],
            ['Netto (Std)', 'die angerechnete Arbeitszeit der Zeiteinträge'],
            ['Soll (Std)', 'das Tagessoll'],
            ['Differenz', 'Netto plus Gutschrift für Krankheit und Fortbildung minus Soll – ein Krank- oder Fortbildungstag ist ±0; die Summe ist der „Saldo Monat“'],
            ['Abwesenheit, Bemerkung', 'Art der Abwesenheit und Notizen'],
            ['Unterbrechung (Min), Zeiteinträge', 'nur Excel und ODS: Zeit zwischen den Einträgen eines Tages und die Einträge einzeln, z. B. „07:45–12:00, 14:15–17:00“'],
            ['Nicht angerechnet (Min)', 'gestempelte, aber nicht angerechnete Zeit vor, nach und zwischen den Arbeitszeit-Blöcken'],
            ['Gestempelt (Von–Bis), Anwesenheit laut Stempel (Std), Pausenausnahme (§4 ArbZG)', 'die tatsächlichen Stempel, die Anwesenheit abzüglich Pausen (über 10 h hervorgehoben) und die Begründung einer Pausenausnahme; im PDF als Spalte „Gestempelt (Anwesenheit)“ und in der Bemerkung'],
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Neue Spalten hängt PraxisZeit immer hinten an – bestehende Auswertungen funktionieren weiter. Die **Zusammenfassung** je Person nennt Soll- und Ist-Stunden, Saldo Monat, Überstunden kumuliert, Urlaub und Nachtarbeitstage. ' +
            'Bei fester Monatsarbeitszeit (Minijob-Modus) ist nur die Zusammenfassung verbindlich, denn das Monats-Soll ist dort nicht die Summe der Tage.',
        },
        {
          kind: 'task',
          id: 'jahresreport-exportieren',
          title: 'Wie exportiere ich einen Jahresbericht?',
          intro: 'Weiter unten auf derselben Seite: **Jahresreport exportieren**. Krankheitsdaten und ausgeblendete Mitarbeitende wählen Sie dort genauso.',
          shot: 'pl-jahresreport',
          steps: [
            { n: 1, text: 'Tragen Sie unter **Jahr auswählen** das Jahr ein.' },
            { n: 2, text: '**Classic Format** ([[Excel]] oder [[ODS]]): je Person ein Blatt mit den 12 Monatswerten – Soll, Ist, Saldo, Urlaub und Krankheit in Stunden, Überstunden kumuliert und Resturlaub.' },
            { n: 3, text: '**Detailliertes Format** ([[Excel]] oder [[ODS]]): jeder Tag des Jahres je Person, mit denselben Tagesspalten wie der Monatsreport. Die Erstellung dauert einige Sekunden.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Aufbewahrung (§ 16 ArbZG):** Exportieren Sie regelmäßig, mindestens jährlich, und bewahren Sie die Dateien **2 Jahre** sicher auf. Das PDF-Format gibt es nur für den Monatsreport.',
        },
      ],
    },

    // ── 9 ───────────────────────────────────────────────────────────────────
    {
      id: 'arbzg-pruefung',
      title: 'ArbZG-Prüfung & §4-Ausnahme',
      blocks: [
        {
          kind: 'comic',
          scene: 'pause',
          text:
            'PraxisZeit prüft beim Erfassen das Arbeitszeitgesetz und warnt oder sperrt. Unter **Berichte** werten Sie nachträglich aus – ' +
            'und unter **Einstellungen** legen Sie fest, ob es die Ausnahme „Pflicht-Pause war nicht möglich“ gibt.',
        },
        {
          kind: 'table',
          head: ['Auswertung unter Berichte', 'Prüft'],
          rows: [
            ['Ruhezeitprüfung', '§ 5: mindestens 11 Stunden Ruhezeit zwischen zwei Arbeitstagen (Mindestruhezeit einstellbar)'],
            ['Sonntagsarbeit §11 ArbZG', 'gearbeitete und freie Sonntage – mindestens 15 Sonntage im Jahr müssen frei sein'],
            ['Nachtarbeit §6 ArbZG', 'Nachtarbeitstage und Nachtarbeitnehmer, mit Monatsdurchschnitt je Werktag'],
            ['Ersatzruhetage §11 ArbZG', 'Ersatzruhetag innerhalb von 2 Wochen nach Sonntags- und 8 Wochen nach Feiertagsarbeit'],
            ['24-Wochen-Durchschnitt §3 ArbZG', 'höchstens 8 Stunden je Werktag im Schnitt über 24 Wochen'],
            ['Höchstarbeitszeit und Pausenausnahmen §3/§4 ArbZG', 'Tage über 10 Stunden, Wochen über 48 Stunden, Pausenausnahmen und zu kurze Pausen'],
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Wer erscheint?** Alle aktiven Mitarbeitenden und ausgeschiedene, die im Zeitraum Einträge oder Abwesenheiten haben. ' +
            'Ausgeblendete nur mit [[Ausgeblendete Mitarbeitende einbeziehen]] über den Auswertungen; § 18-befreite Mitarbeitende erscheinen nie.',
        },
        {
          kind: 'task',
          id: 'arbzg-24-wochen',
          title: 'Hält mein Team den 8-Stunden-Durchschnitt ein?',
          intro: 'Auf der Seite „Berichte & Export“ im Abschnitt **24-Wochen-Durchschnitt §3 ArbZG**.',
          shot: 'pl-arbzg-24wochen',
          steps: [
            { n: 1, text: '**Stichtag** (Standard heute): ausgewertet werden die 24 Wochen bis zu diesem Tag.' },
            { n: 2, text: 'Klicken Sie auf [[Prüfen]]. Über der Tabelle stehen der Zeitraum und, falls jemand die Grenze überschreitet, die Zahl der nicht konformen Mitarbeitenden.' },
            {
              n: 3,
              text:
                '**Ø angerechnet / Werktag** und **Status** rechnen mit der angerechneten Zeit, geteilt durch die Werktage – Montag bis Samstag ohne Feiertage und ohne Tage mit Urlaub, Krankheit, Fortbildung, Sonstiges oder Freistellung. ' +
                '**Anwesenheit laut Stempel** ist die gestempelte Zeit abzüglich Pausen; liegt ihr Schnitt über 8 Stunden, ist sie rot hervorgehoben.',
            },
          ],
        },
        {
          kind: 'task',
          id: 'arbzg-hoechstarbeitszeit',
          title: 'Wo sehe ich lange Tage und dokumentierte Pausenausnahmen?',
          intro: 'Im Abschnitt **Höchstarbeitszeit und Pausenausnahmen §3/§4 ArbZG**.',
          shot: 'pl-arbzg-hoechstarbeitszeit',
          steps: [
            { n: 1, text: 'Wählen Sie das **Jahr**, optional einen **Monat**, und klicken Sie auf [[Prüfen]].' },
            { n: 2, text: 'Die Zähler: Tage > 10 h, Wochen > 48 h, Pausenausnahmen und Pause zu kurz. Es erscheinen nur Personen mit mindestens einem Befund.' },
            { n: 3, text: 'Ein Klick auf die Person klappt die Einzelheiten auf.' },
            { n: 4, text: '**Pausenausnahmen:** jeder Eintrag mit dokumentierter Ausnahme mit Zeit, erfasster Pause und Begründung. **Pause zu kurz** zeigt Tage, an denen die Pause nicht reicht und keine Ausnahme anerkannt ist – etwa weil die beantragte Ausnahme noch offen ist oder abgelehnt wurde.' },
          ],
        },
        {
          kind: 'task',
          id: 'pflicht-pause-ausnahme',
          title: 'Wie lege ich fest, ob eine fehlende Pause begründet werden darf?',
          intro: 'Klicken Sie auf [[Einstellungen]] und scrollen Sie zum Abschnitt **Pflicht-Pause-Ausnahme**.',
          shot: 'pl-pflicht-pause',
          steps: [
            {
              n: 1,
              text:
                '[[Ausnahme „Pflicht-Pause war nicht möglich“ erlauben]] (Standard: an): Mitarbeitende und Admins können eine fehlende Pause begründen. ' +
                'Aus: Die Auswahl verschwindet überall, PraxisZeit lehnt jede Ausnahme ab – auch für Admins; ein Tag über 6 bzw. 9 Stunden lässt sich nur mit eingetragener Pause speichern.',
            },
            {
              n: 2,
              text:
                '[[Genehmigung erforderlich]] (Standard: aus): Ist er an, wird eine Ausnahme aus der Zeiterfassung erst nach Ihrer Genehmigung gespeichert (4-Augen-Prinzip). ' +
                'Beim Ausstempeln wird der Eintrag sofort mit der echten Zeit geschlossen, die Ausnahme ist nur beantragt: Es entsteht ein Änderungsantrag mit unveränderten Zeiten und der Begründung.',
            },
            { n: 3, text: 'Klicken Sie auf [[Speichern]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**§ 4 ArbZG:** mindestens 30 Minuten Pause bei mehr als 6 Stunden, 45 Minuten bei mehr als 9 Stunden. Maßstab ist der ganze Tag; eine Unterbrechung zählt erst ab 15 Minuten als Pause. ' +
            'Fehlt die Pause, sperrt PraxisZeit an jedem Erfassungsweg – auch beim Ausstempeln –, bis eine Pause eingetragen oder, falls erlaubt, eine Ausnahme mit mindestens 10 Zeichen begründet ist.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Beantragte Ausnahme entscheiden:** Den Antrag finden Sie unter [[Änderungsanträge]]. Genehmigt, steht die Ausnahme am Eintrag; abgelehnt, bleibt der Eintrag ohne Ausnahme und erscheint unter „Pause zu kurz“. ' +
            'Ihre **eigene** Ausnahme genehmigt ein weiteres Admin-Konto. Gibt es nur eines, lässt sie sich nur ablehnen – brauchen Sie dann selbst Ausnahmen, schalten Sie „Genehmigung erforderlich“ aus.',
        },
        {
          kind: 'table',
          head: ['Automatische Prüfung', 'Verhalten'],
          rows: [
            ['§ 3: mehr als 10 Stunden am Tag', 'beim Ausstempeln Warnung (die Zeit ist geleistet), bei manueller Eingabe und im Antrag Sperre'],
            ['§ 3: mehr als 8 Stunden am Tag, mehr als 48 Stunden in der Woche', 'Warnung'],
            ['§ 4: Pause fehlt', 'Sperre, auch beim Ausstempeln; Ausnahme mit Begründung, sofern erlaubt'],
            ['§ 5: weniger als 11 Stunden Ruhezeit', 'Warnung beim Einstempeln'],
            ['§ 6: Nachtarbeitnehmer über 8 Stunden', 'Warnung'],
            ['Arbeit an Sonn- und Feiertagen', 'Warnung; ohne Ausnahmegrund nach § 10 ArbZG fordert PraxisZeit ihn an (Feld auch beim Ausstempeln)'],
          ],
        },
      ],
    },

    // ── 10 ──────────────────────────────────────────────────────────────────
    {
      id: 'gruende-kind-krank-minijob',
      title: 'Eigene Abwesenheitsgründe, Kind krank, Minijob',
      blocks: [
        {
          kind: 'comic',
          scene: 'gruende',
          text:
            'Nicht jede Abwesenheit passt zu Urlaub, Krank oder Fortbildung. Mit **eigenen Gründen** – etwa „Berufsschule“ oder „Kind krank“ – bilden Sie solche Fälle ab; ' +
            'das **Verhalten** des Grundes sagt PraxisZeit, wie die Tage zu rechnen sind. Für Minijobs auf Arbeitszeitkonto gibt es zusätzlich Hinweise nach dem Mindestlohngesetz.',
        },
        {
          kind: 'task',
          id: 'eigenen-grund-anlegen',
          title: 'Wie lege ich einen eigenen Abwesenheitsgrund an?',
          intro: 'Klicken Sie auf [[Einstellungen]]. Der Bereich **Eigene Abwesenheitsgründe** steht ganz oben.',
          shot: 'pl-abwesenheitsgrund',
          steps: [
            { n: 1, text: 'Tragen Sie die **Bezeichnung** ein, zum Beispiel „Berufsschule“ (höchstens 80 Zeichen).' },
            { n: 2, text: 'Wählen Sie das **Verhalten**. Es bestimmt die Berechnung und lässt sich nach dem Anlegen **nicht mehr ändern**. Die **Farbe** daneben dürfen Sie jederzeit ändern.' },
            { n: 3, text: 'Klicken Sie auf [[Hinzufügen]]. Der Grund erscheint in der Liste und steht beim Eintragen einer Abwesenheit in der Typ-Auswahl unter „Eigene Gründe“.' },
            { n: 4, text: 'Die **Vorlagen (1-Klick aktivieren)** legen gängige Gründe mit einem Klick an, siehe [Kind krank und Sonderurlaub](#kind-krank-vorlage).' },
            { n: 5, text: 'In der Liste ändern Sie Farbe und Bezeichnung (Eingabe verlassen = speichern) und schalten mit dem Haken [[aktiv]] einen Grund ein oder aus. Der Papierkorb löscht ihn.' },
          ],
        },
        {
          kind: 'table',
          head: ['Verhalten', 'Wirkung', 'Typisch für'],
          rows: [
            ['Zählt als gearbeitet', 'Die geplanten Stunden werden als Arbeitszeit gutgeschrieben (wie Fortbildung), es entstehen keine Stundenverluste', 'Berufsschule (Arbeitszeit nach § 15 JArbSchG)'],
            ['Bezahlt frei', 'Das Tagessoll wird 0 (saldoneutral), kein Urlaubsabzug – der Arbeitgeber zahlt weiter', 'Todesfall, Hochzeit, Geburt'],
            ['Unbezahlt frei', 'Das Tagessoll wird 0 (saldoneutral), kein Urlaubsabzug, aber unbezahlt (Lohn gekürzt)', 'Kind krank (§ 45 SGB V), unbezahlter Sonderurlaub'],
            ['Überstundenabbau', 'Das Überstundenkonto sinkt um das Tagessoll', 'Freizeitausgleich mit eigener Bezeichnung'],
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Deaktivieren statt löschen:** Deaktivierte Gründe stehen beim Buchen nicht mehr zur Auswahl, bleiben aber an bestehenden Abwesenheiten erhalten. ' +
            'Löschen geht nur, solange keine Abwesenheit den Grund nutzt – sonst fordert PraxisZeit Sie auf, ihn zu deaktivieren. ' +
            'Berechnet wird ausschließlich nach dem Verhalten; Farbe und Bezeichnung ändern nichts an den Zahlen.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Datenschutz:** Ein eigener Grund kann sensibel sein (z. B. „Reha“). Im Team-Kalender sehen andere Mitarbeitende eine Abwesenheit mit eigenem Grund nur als „abwesend“; ' +
            'die Bezeichnung sehen Admins und die betroffene Person selbst.',
        },
        {
          kind: 'task',
          id: 'kind-krank-vorlage',
          title: 'Wie richte ich „Kind krank“ und andere Sonderurlaub-Gründe ein?',
          intro:
            'Unter der Eingabezeile stehen die **Vorlagen**: Kind krank, Todesfall naher Angehöriger, Eigene Hochzeit, Geburt eines Kindes, Umzug (betrieblich), Arztbesuch (unvermeidbar) und Pflege naher Angehöriger.',
          shot: 'pl-kind-krank-grund',
          steps: [
            { n: 1, text: 'Klicken Sie auf die Vorlage [[+ Kind krank]]. PraxisZeit legt den Grund sofort an: Verhalten **Unbezahlt frei**, mit Zählung gegen das Jahreslimit. Eine aktivierte Vorlage verschwindet aus der Reihe.' },
            { n: 2, text: 'Wollen Sie einen Grund selbst anlegen, der gegen das Limit zählt, wählen Sie als **Verhalten** [[Unbezahlt frei]].' },
            { n: 3, text: 'Dann erscheint der Haken [[Gegen das Kind-krank-Jahreslimit zählen (§45 SGB V)]]. Setzen Sie ihn, bevor Sie auf [[Hinzufügen]] klicken – nur Gründe mit diesem Haken zählen.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Die Vorlagen sind Vorschläge.** Bezahlt oder unbezahlt hängt von Ihrem Betrieb ab – die rechtliche Einordnung (etwa ob § 616 BGB im Arbeitsvertrag ausgeschlossen ist) liegt bei Ihnen. ' +
            'Weil das Verhalten nach dem Anlegen feststeht, legen Sie einen Grund mit anderem Verhalten selbst an. PraxisZeit bildet nur die Zeiterfassung ab; die Meldung an Krankenkasse und Lohnbuchhaltung erfolgt außerhalb.',
        },
        {
          kind: 'task',
          id: 'kind-krank-anspruch',
          title: 'Wie viele Kind-krank-Tage stehen Mitarbeitenden zu?',
          intro: 'PraxisZeit zählt die Tage eines Kind-krank-Grundes je Kalenderjahr. Den Standardanspruch stellen Sie unter [[Einstellungen]] im Bereich **Kind-krank-Standardanspruch** ein.',
          shot: 'pl-kind-krank-limit',
          steps: [
            { n: 1, text: 'Tragen Sie unter [[Standard Kind-krank-Tage/Jahr]] die Zahl der Tage ein (Voreinstellung 15). Sie gilt für alle ohne eigenen Wert.' },
            { n: 2, text: 'Klicken Sie auf [[Speichern]].' },
            { n: 3, text: 'Darunter zeigt der Bereich **Gesetzlicher Mindestlohn** den aktuellen Wert und die nächste Stufe an (13,90 € pro Stunde seit 1.1.2026, 14,60 € ab 1.1.2027). Das ist nur eine Anzeige.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Eigener Wert je Person:** Im Formular zum Bearbeiten einer Person gibt es das Feld „Kind-krank-Tage/Jahr (§45 SGB V)“; leer gilt der Standard, siehe [Mitarbeiter bearbeiten](#mitarbeiter-bearbeiten).',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Nur ein Hinweis, keine Sperre:** Wird der Anspruch beim Buchen überschritten, weist PraxisZeit darauf hin – die Abwesenheit wird **trotzdem erfasst**, denn der Fehltag muss dokumentiert werden. ' +
            'Das gilt beim Eintragen, im Monatsjournal und bei der Genehmigung eines Änderungsantrags. Den Jahresverbrauch sehen Sie in der **Benutzerverwaltung** unter dem Namen („Kind krank“ mit genommenen Tagen und Anspruch, rot bei Überschreitung), sobald ein Tag verbraucht ist.',
        },
        {
          kind: 'task',
          id: 'minijob-konto',
          title: 'Wie führe ich eine Minijob-Beschäftigte auf Arbeitszeitkonto?',
          intro:
            'Für Minijobber:innen auf **Arbeitszeitkonto** (§ 2 Abs. 2 MiLoG, „sonstige flexible Arbeitszeitregelung“) stellen Sie die Felder beim Anlegen im Formular ein, bei bestehenden Mitarbeitenden über [[Arbeitszeit anpassen…]] im Abschnitt **Urlaub und Abrechnung**, siehe [Vertragsverlauf](#vertragsverlauf). Im Bild: Julia Meyer, 10 Stunden pro Woche.',
          shot: 'pl-minijob-konto',
          steps: [
            { text: '**Gültig ab:** Minijob-Einstellungen gelten immer ab dem Monatsersten. Ein anderes Datum lehnt PraxisZeit mit „Änderungen an Minijob-Einstellungen gelten immer ab dem Monatsersten.“ ab.' },
            { n: 1, text: 'Setzen Sie den Haken [[Arbeitszeitkonto (§ 2 Abs. 2 MiLoG) – 50-%-Prüfung & 12-Monats-Ausgleichsfrist]]. Er setzt aktive Stundenzählung voraus.' },
            { n: 2, text: 'Tragen Sie die **Vereinbarte Monatsarbeitszeit (h)** ein, im Bild 43. Bleibt das Feld leer, rechnet PraxisZeit Wochenstunden × 13/3 (bei 10 Stunden etwa 43,3). Die Zeile darunter nennt den aktuellen Mindestlohn und die Obergrenze des Kontos: die Hälfte, hier etwa 21,5 Stunden im Monat.' },
            { n: 3, text: 'Optional: [[Feste Monatsarbeitszeit (Monats-Soll = vereinbarte Monatsarbeitszeit)]]. Der Haken erscheint nur bei aktivem Arbeitszeitkonto und macht die vereinbarte Monatsarbeitszeit zur Pflichtangabe.' },
          ],
        },
        {
          kind: 'table',
          head: ['Hinweis', 'Regel', 'Wo erscheint er?'],
          rows: [
            ['50-%-Regel', 'Die auf das Konto eingestellten Plusstunden dürfen pro Monat 50 % der vereinbarten Arbeitszeit nicht übersteigen. Beispiel 10 h/Woche: Monatszeit etwa 43,33 h, Grenze 21,67 h', 'beim Buchen und Ausstempeln, im eigenen Überstundenkonto, in der Benutzerverwaltung (Kennzeichen „MiLoG“)'],
            ['12-Monats-Ausgleichsfrist', 'Zeitguthaben auf dem Konto muss binnen 12 Kalendermonaten ausgeglichen werden; bei Überfälligkeit erscheint ein Hinweis', 'wie oben'],
            ['Monatszeit überschritten', 'Nur bei fester Monatsarbeitszeit: das Monats-Ist inklusive Gutschriften übersteigt die vereinbarte Monatsarbeitszeit', 'wie oben'],
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Alle Hinweise sind weich, nichts wird blockiert.** Die 50-%-Grenze bindet nur die mindestlohnwirksamen Stunden; wird über dem Mindestlohn vergütet, sind mehr Stunden möglich. ' +
            'PraxisZeit speichert **keine Lohndaten** und prüft die Verdienstgrenze von 603 € nicht – das bleibt der Lohnbuchhaltung.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Wozu die vereinbarte Monatsarbeitszeit dient:** Sie ist die Bezugsgröße der 50-%-Prüfung. Die 12-Monats-Frist rechnet dagegen bewusst gegen das tatsächliche Monats-Soll, ' +
            'damit Urlaub und Feiertage das Konto nicht belasten.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Feste Monatsarbeitszeit:** Das Monats-Soll ist jeden Monat die vereinbarte Monatsarbeitszeit – egal, ob der Monat vier oder fünf Montage hat; bei Ein- oder Austritt im Monat anteilig nach Kalendertagen. ' +
            'Die Tagesstunden heißen dann „Geplante Anwesenheit“ und bestimmen nur noch, wie viele Stunden an Feiertagen, Urlaubs- und Freistellungstagen als Ist gutgeschrieben werden. ' +
            'Unbezahlt entschuldigte Tage (Typ „Sonstiges“, z. B. Kind krank) mindern stattdessen das Monats-Soll um die geplanten Stunden. ' +
            'Im Monatsjournal heißt die Spalte dann „Geplant“, einen Tages-Saldo gibt es nicht; **verbindlich ist die Monatsübersicht**.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Bekannte Grenze:** Fällt ein **ganzer Monat** durch Urlaub oder Krankheit aus, schreibt PraxisZeit nur den geplanten Anteil gut. Der flexible Rest bleibt als Defizit auf dem Konto stehen; ' +
            'dann ist eine manuelle Korrektur nötig, etwa über das Überstundenkonto oder den Jahresübertrag. Bei einzelnen Fehltagen rechnet PraxisZeit korrekt von selbst.',
        },
      ],
    },

    // ── 11 ──────────────────────────────────────────────────────────────────
    {
      id: 'einstellungen',
      title: 'Einstellungen',
      blocks: [
        {
          kind: 'comic',
          scene: 'einstellungen',
          text:
            'Unter **Einstellungen** legen Sie fest, wie PraxisZeit für die ganze Praxis arbeitet. **Jeder Bereich hat einen eigenen Speichern-Knopf** – eine Änderung gilt erst, wenn Sie ihn drücken. ' +
            'Die Tabelle zeigt, wo Sie die Bereiche in diesem Handbuch finden.',
        },
        {
          kind: 'table',
          head: ['Bereich in den Einstellungen', 'Wofür', 'Mehr dazu'],
          rows: [
            ['Eigene Abwesenheitsgründe', 'zusätzliche Gründe mit eigenem Verhalten, Vorlagen', '[Eigenen Grund anlegen](#eigenen-grund-anlegen)'],
            ['Feiertage', 'Bundesland der gesetzlichen Feiertage', '[Bundesland einstellen](#bundesland-einstellen)'],
            ['Eigene Feiertage', 'regionale Feiertage wie Schützenfest', '[Regionalen Feiertag anlegen](#eigene-feiertage)'],
            ['Sondertage (24./31.12.)', 'Modus je Tag: Arbeitstag, Halbtag, Frei, Verkürzt', '[Sondertage](#sondertage-einstellen)'],
            ['Verkürzte Tage', 'einzelne Tage mit Höchststunden', '[Verkürzte Tage](#verkuerzte-tage)'],
            ['Urlaubsgenehmigung', 'Genehmigungspflicht für Urlaub', '[Urlaubsgenehmigung](#urlaubsgenehmigung)'],
            ['Pflicht-Pause-Ausnahme', 'Ausnahme bei fehlender Pause erlauben', '[Pflicht-Pause-Ausnahme](#pflicht-pause-ausnahme)'],
            ['Onboarding / Willkommens-Tour', 'Tour beim ersten Login', '[Tour und Schichtplanung](#tour-schichtplanung)'],
            ['Schichtplanung', 'Planungswerkzeug ein- oder ausschalten', '[Tour und Schichtplanung](#tour-schichtplanung), [Wochentage](#schicht-wochentage)'],
            ['Betriebsferien & Urlaub', 'überzählige Betriebsferien als Überstundenabbau', '[Betriebsferien länger als der Urlaub](#betriebsferien-ueberstundenabbau)'],
            ['Überstunden-Projektion zum Jahresende', 'Anzeige des voraussichtlichen Saldos', '[Saldo zum Jahresende](#jahresende-projektion)'],
            ['Soll-Arbeitszeit-Fenster', 'Puffer an den Rändern der Arbeitszeit-Blöcke', '[Puffer einstellen](#puffer-einstellen)'],
            ['Kind-krank-Standardanspruch', 'Tage je Jahr', '[Kind-krank-Anspruch](#kind-krank-anspruch)'],
            ['Gesetzlicher Mindestlohn', 'reine Anzeige', '[Kind-krank-Anspruch](#kind-krank-anspruch)'],
            ['Farben', 'Farbe je Anwesenheits- und Abwesenheitstyp', '[Farben ändern](#farben)'],
          ],
        },
        {
          kind: 'task',
          id: 'eigene-feiertage',
          title: 'Wie lege ich einen regionalen Feiertag an?',
          intro: 'Im Bereich **Eigene Feiertage** unter [[Einstellungen]]. Gesetzliche Feiertage stehen dort nur zur Information und lassen sich nicht ändern.',
          shot: 'pl-eigene-feiertage',
          steps: [
            { n: 1, text: 'Wählen Sie oben rechts das **Jahr**; darüber blättern Sie auch durch die Liste der Feiertage.' },
            { n: 2, text: 'Tragen Sie den **Namen** ein, zum Beispiel „Schützenfest“.' },
            { n: 3, text: 'Wählen Sie das **Datum**.' },
            { n: 4, text: 'Klicken Sie auf [[Hinzufügen]]. In der Liste bearbeiten Sie einen eigenen Feiertag mit dem Stift und löschen ihn mit dem Papierkorb.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Eigene Feiertage senken das Soll wie gesetzliche Feiertage und bleiben erhalten, wenn Sie das Bundesland wechseln.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Liegt der Tag in einem abgeschlossenen Jahr,** weist PraxisZeit auf den veralteten Übertrag hin, sobald Sie einen eigenen Feiertag anlegen, verschieben oder löschen; ein reines Umbenennen löst keinen Hinweis aus. ' +
            'Stehen am Tag schon Zeiteinträge von Mitarbeitenden mit Arbeitszeit-Blöcken, nennt PraxisZeit sie – sie behalten ihre Anrechnung, bis Sie sie unverändert neu speichern. Siehe [Übertrag korrigieren](#vorjahresuebernahme).',
        },
        {
          kind: 'task',
          id: 'urlaubsgenehmigung',
          title: 'Müssen Urlaubsanträge genehmigt werden?',
          intro: 'Im Bereich **Urlaubsgenehmigung** unter [[Einstellungen]].',
          shot: 'pl-urlaubsgenehmigung',
          steps: [
            { n: 1, text: 'Schalten Sie [[Genehmigung erforderlich]] an oder aus. **Aus** (Standard): Mitarbeitende buchen Urlaub direkt. **An:** Urlaubsanträge landen als „Offen“ unter [[Anträge]] bei Ihnen.' },
            { n: 2, text: 'Klicken Sie auf [[Speichern]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Denselben Schalter finden Sie oben auf der Seite „Abwesenheitsanträge“, siehe [Urlaubsantrag genehmigen](#urlaubsantrag-genehmigen).',
        },
        {
          kind: 'task',
          id: 'tour-schichtplanung',
          title: 'Wie schalte ich die Willkommens-Tour und die Schichtplanung ein oder aus?',
          intro: 'Die beiden Bereiche **Onboarding / Willkommens-Tour** und **Schichtplanung** stehen untereinander. Jeder hat seinen eigenen Speichern-Knopf.',
          shot: 'pl-onboarding-schichtplanung',
          steps: [
            { n: 1, text: '[[Willkommens-Tour anzeigen]] (Standard: an): Neue Mitarbeitende und Admins sehen beim ersten Login eine kurze Tour mit den wichtigsten Bereichen. Bereits gesehene Touren erscheinen nicht erneut.' },
            { n: 2, text: '[[Schichtplanung aktivieren]] (Standard: aus): Erst dann gibt es Wochen-Schichtpläne, Arbeitsplätze und Standorte. Solange der Schalter aus ist, sehen weder Admins noch Mitarbeitende die Schichtplanung.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Die Schichtplanung ist ein reines Planungswerkzeug und verändert **keine** Zeiterfassungs-, Urlaubs- oder Überstundendaten. Ist sie eingeschaltet, wählen Sie darunter die **geplanten Wochentage** (Standard Montag bis Freitag, mindestens ein Tag bleibt aktiv) und klicken auf [[Wochentage speichern]]. ' +
            'Eine Anleitung für die Ersteinrichtung finden Sie jederzeit über den Knopf [[Schnellstart]] unten links in der Seitenleiste.',
        },
        {
          kind: 'task',
          id: 'jahresende-projektion',
          title: 'Wie blende ich den voraussichtlichen Saldo zum Jahresende aus?',
          intro: 'Im Bereich **Überstunden-Projektion zum Jahresende** unter [[Einstellungen]]. Beide Anzeigen sind standardmäßig an.',
          shot: 'pl-projektion',
          steps: [
            { n: 1, text: '[[Im Mitarbeiter-Dashboard anzeigen]]: Aus, sehen Mitarbeitende die Vorschau-Zeile in ihrem eigenen Überstundenkonto nicht mehr; die Berechnung entfällt dann ganz.' },
            { n: 2, text: '[[Im Admin-Dashboard anzeigen]]: Aus, entfällt die Spalte „Überstd. Jahresende“ im Monats- und Wochenbericht. Sie erscheint ohnehin nur im laufenden Monat und nur, wenn mindestens eine Person schon künftigen Ausgleich gebucht hat.' },
            { n: 3, text: 'Klicken Sie auf [[Speichern]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Was die Projektion zeigt:** den Saldo bis heute, abzüglich der Stunden aller bereits gebuchten künftigen **Überstundenausgleich**-Tage. Urlaub, Krankheit und Fortbildung sind saldoneutral und fließen nicht ein. ' +
            'Beide Schalter wirken nur auf die Anzeige – das Überstundenkonto selbst rechnet PraxisZeit unverändert weiter.',
        },
        {
          kind: 'task',
          id: 'puffer-einstellen',
          title: 'Wie stelle ich den Puffer für die Arbeitszeit-Blöcke ein?',
          intro: 'Im Bereich **Soll-Arbeitszeit-Fenster** unter [[Einstellungen]]. Der Puffer entscheidet, wie viel gestempelte Zeit vor, nach und zwischen den Arbeitszeit-Blöcken noch angerechnet wird.',
          shot: 'pl-puffer',
          steps: [
            { n: 1, text: 'Tragen Sie im Feld [[Puffer für Soll-Arbeitszeit-Fenster (Min.)]] die Minuten ein (Standard 15, zulässig 0 bis 1439). Der Puffer gilt an jedem Blockrand, auch zwischen zwei Blöcken; eine Lücke bis zum doppelten Puffer wird angerechnet. Stempelzeit weiter außerhalb zählt nicht. Ab 1439 Minuten, einem ganzen Tag, kappt PraxisZeit nichts mehr.' },
            { n: 2, text: 'Klicken Sie auf [[Speichern]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Eine Änderung wirkt nur auf neue Einträge.** Jeder gekappte Eintrag merkt sich seinen Puffer und behält ihn, auch wenn er später bearbeitet wird; gespeicherte Einträge ändern sich durch das Speichern allein nicht. ' +
            'Einträge aus der Zeit vor Version 1.20.0 tragen keinen gespeicherten Puffer und werden bei einer Bearbeitung mit dem aktuellen gekappt. ' +
            'Nur eine Arbeitszeit-Änderung mit Neuberechnung kappt die betroffenen Einträge mit dem dann gültigen Puffer neu – die Vorschau nennt ihn; verliert ein Eintrag dabei angerechnete Zeit, gilt der Verkürzungsschutz, siehe [Rückwirkend ändern](#rueckwirkend-aendern).',
        },
        {
          kind: 'task',
          id: 'farben',
          title: 'Wie ändere ich die Farben der Abwesenheitstypen?',
          intro: 'Im Bereich **Farben** unter [[Einstellungen]]: je Typ eine Farbe – Arbeit/Anwesenheit, Fortbildung, Urlaub, Krank, Überstundenausgleich, Sonstiges und Bezahlte Freistellung. Sie gelten im Kalender, in den Übersichten und bei der Zeiterfassung.',
          shot: 'pl-farben',
          steps: [
            { n: 1, text: 'Klicken Sie neben dem Typ auf das Farbfeld und wählen Sie die Farbe. Die kleine „Aa“-Vorschau zeigt, ob die Schrift auf der gewählten Farbe lesbar bleibt.' },
            { n: 2, text: 'Klicken Sie auf [[Speichern]].' },
          ],
        },
      ],
    },

    // ── 12 ──────────────────────────────────────────────────────────────────
    {
      id: 'jahresabschluss',
      title: 'Jahresabschluss',
      blocks: [
        {
          kind: 'comic',
          scene: 'jahresabschluss',
          text:
            'Zum Jahreswechsel berechnet PraxisZeit für alle aktiven Mitarbeitenden den **Überstunden-Saldo zum 31.12.** und den **Resturlaub** und trägt beides als **Übernahme** ins Folgejahr ein. ' +
            'Diesen Schritt lösen Sie selbst aus – am besten, wenn alle Anträge für das Jahr entschieden sind.',
        },
        {
          kind: 'task',
          id: 'jahresuebersicht',
          title: 'Wo finde ich den Jahresabschluss?',
          intro: 'Auf dem [[Admin-Dashboard]] unterhalb der Monatsübersicht steht die **Jahresübersicht** mit Urlaubs- und Krankheitstagen aller Mitarbeitenden – und den Knöpfen für den Abschluss.',
          shot: 'pl-jahresuebersicht',
          steps: [
            { n: 1, text: 'Wählen Sie im Feld [[Jahr]] das Jahr, das Sie abschließen oder prüfen wollen.' },
            { n: 2, text: 'Der orangefarbene Knopf [[Jahresabschluss]] startet den Abschluss, siehe [Jahresabschluss erstellen](#jahresabschluss-erstellen).' },
            { n: 3, text: 'Der rote Knopf [[Abschluss löschen]] nimmt ihn zurück, siehe [Jahresabschluss löschen](#jahresabschluss-loeschen).' },
            { n: 4, text: 'Die Spalte **Resturlaub** zeigt die offenen Urlaubstage: grün über 5 Tage, gelb bis 5 Tage, rot bei 0 oder weniger.' },
            { text: 'Im letzten Quartal des laufenden Jahres erscheint die gelbe **Jahresend-Warnung: Offene Urlaubstage** mit allen, die noch mindestens einen ganzen Urlaubstag offen haben, und dem Verfallsdatum.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Kleine Reste lösen keine Warnung aus:** Bruchteile unter einem Tag – typisch bei Teilzeit, etwa 0,3 oder 0,5 Tage – lassen sich nicht als ganzer Tag nehmen und werden im Folgejahr üblicherweise mit weiteren Bruchteilen zusammengelegt. ' +
            'In der Tabelle, im Urlaubskonto und beim Jahresabschluss zählen sie unverändert mit. Das Verfallsdatum ist in der Regel der 31.03. des Folgejahres, sonst die für die Person hinterlegte Frist; bei unterschiedlichen Fristen steht das Datum hinter jedem Namen. ' +
            'Dieselbe Schwelle und dasselbe Datum gelten für den Hinweis im Urlaubskonto auf dem Dashboard der Mitarbeitenden.',
        },
        {
          kind: 'task',
          id: 'jahresabschluss-erstellen',
          title: 'Wie erstelle ich den Jahresabschluss?',
          intro: 'Wählen Sie in der Jahresübersicht das Jahr und klicken Sie auf [[Jahresabschluss]]. Es öffnet sich ein Bestätigungsdialog; erst Ihre Bestätigung löst den Abschluss aus.',
          shot: 'pl-jahresabschluss-dialog',
          steps: [
            { n: 1, text: 'Lesen Sie den Text: Überstunden-Saldo und Resturlaub aller **aktiven** Mitarbeitenden werden berechnet und als Übernahme ins Folgejahr gespeichert. **Bestehende Übernahmen für das Folgejahr werden überschrieben.**' },
            { n: 2, text: 'Mit [[Abbrechen]] geschieht nichts.' },
            { n: 3, text: 'Mit [[Jahresabschluss erstellen]] bestätigen Sie. Die Meldung nennt, wie viele Mitarbeitende nach dem Folgejahr übernommen wurden.' },
          ],
        },
        {
          kind: 'table',
          head: ['PraxisZeit berechnet', 'Bedeutung im Folgejahr'],
          rows: [
            ['Überstunden-Saldo zum 31.12. des Jahres (immer der volle Zeitraum, nicht „bis heute“)', 'Startwert des Überstundenkontos'],
            ['Resturlaub in Tagen', 'wird dem Jahresurlaub des Folgejahres hinzugerechnet'],
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Der Abschluss schließt auch Mitarbeitende **ohne Stundenzählung** ein: Für sie ist der Überstundenwert 0, der Resturlaub wird tagebasiert übernommen – sonst ginge er beim Jahreswechsel verloren.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**PraxisZeit lehnt den Abschluss ab, solange offene Anträge das Jahr betreffen:** noch nicht entschiedene Änderungsanträge oder offene Urlaubsanträge. ' +
            'Die Meldung lautet zum Beispiel „Jahresabschluss 2026 abgelehnt: es gibt noch 2 offene Änderungsanträge für dieses Jahr. Bitte erst bearbeiten, dann erneut versuchen.“ ' +
            'Ein später genehmigter Antrag würde sonst den eingefrorenen Saldo verschieben. Entscheiden Sie die Anträge unter [[Änderungsanträge]] und [[Anträge]] und starten Sie den Abschluss dann erneut.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Erneut ausführen überschreibt:** Ein zweiter Abschluss für dasselbe Jahr ersetzt die Übernahmen **aller** aktiven Mitarbeitenden für das Folgejahr – auch von Hand eingetragene. Die Zeile gilt danach wieder als Abschluss-Zeile.',
        },
        {
          kind: 'task',
          id: 'jahresabschluss-loeschen',
          title: 'Wie nehme ich einen Jahresabschluss zurück?',
          intro: 'Das geht, wenn ein Abschluss versehentlich erstellt wurde. Die Löschung ist **unwiderruflich**.',
          steps: [
            { n: 1, text: 'Wählen Sie in der Jahresübersicht das Jahr, dessen Abschluss Sie löschen möchten.' },
            { n: 2, text: 'Klicken Sie auf den roten Knopf [[Abschluss löschen]].' },
            { n: 3, text: 'Lesen Sie den Dialog „Jahresabschluss … löschen“ sorgfältig: Alle Übernahmen für das Folgejahr, die durch diesen Jahresabschluss erzeugt wurden, werden gelöscht – für alle Mitarbeitenden.' },
            { n: 4, text: 'Bestätigen Sie mit [[Jahresabschluss löschen]]. Gibt es keinen Abschluss für das Jahr, meldet PraxisZeit „Kein Jahresabschluss für … gefunden“.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Von Hand eingetragene Übernahmen bleiben stehen.** Das Löschen entfernt nur Übernahmen, die der Jahresabschluss erzeugt hat – Werte, die Sie in der Vorjahresübernahme eingetragen oder korrigiert haben, nicht.',
        },
        {
          kind: 'task',
          id: 'vorjahresuebernahme',
          title: 'Wie trage ich einen Übertrag von Hand ein oder korrigiere ihn?',
          intro: 'Für einzelne Personen, etwa beim Start mit PraxisZeit oder nach einer Korrektur. Klicken Sie in der [[Benutzerverwaltung]] in der Zeile der Person auf den Knopf [[Vorjahresübernahme]].',
          shot: 'pl-uebernahme',
          steps: [
            { n: 1, text: 'Wählen Sie das **Jahr**. Die Werte gelten als Übernahme **in** das gewählte Jahr.' },
            { n: 2, text: '**Überstunden aus Vorjahr (Stunden):** positiv ist ein Guthaben, negativ sind Minusstunden.' },
            { n: 3, text: '**Resturlaub aus Vorjahr (Tage):** wird zum Jahresurlaub des gewählten Jahres addiert.' },
            { n: 4, text: 'Klicken Sie auf [[Speichern]]. Unter „Gespeicherte Übernahmen“ stehen alle Jahre der Person; ein Klick auf eine Zeile lädt ihre Werte ins Formular.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Rückwirkende Änderungen rechnet PraxisZeit nie von selbst nach.** Ändert sich etwas in einem bereits abgeschlossenen Jahr – Bundesland-Wechsel, Storno eines genehmigten Urlaubs, gelöschte Betriebsferien, geänderte Sondertage oder eigene Feiertage –, ' +
            'meldet PraxisZeit zum Beispiel „Jahresabschluss 2025 bereits erfolgt — Carryover 2026 ist nun veraltet, bitte Jahresabschluss erneut ausführen.“ Eine automatische Neuberechnung würde Ihre von Hand korrigierten Werte überschreiben. ' +
            'Prüfen Sie den Übertrag und führen Sie den Abschluss bei Bedarf erneut aus, danach tragen Sie Handkorrekturen noch einmal ein.',
        },
      ],
    },

    // ── 13 ──────────────────────────────────────────────────────────────────
    {
      id: 'import',
      title: 'Import',
      blocks: [
        {
          kind: 'comic',
          scene: 'import',
          text:
            'Unter **Import** übernehmen Sie historische **Zeiteinträge** aus einer TimeRec-Datei, zum Beispiel Altdaten aus Ihrer bisherigen Zeiterfassung. ' +
            'Gedacht ist der Import für die einmalige Datenübernahme bei der Einführung. **Abwesenheiten** (Urlaub, Krank usw.) werden nicht importiert.',
        },
        {
          kind: 'table',
          head: ['Anforderung', 'Wert'],
          rows: [
            ['Format', 'echtes .xls (TimeRec-Export, BIFF) – keine .xlsx- und keine CSV-Dateien'],
            ['Größe', 'höchstens 5 MB'],
            ['Tabellenblatt', '„Zeiterfassung“ mit den Spalten Datum, Tag, Total, Ein, Aus, Tagesnotiz'],
            ['Vorlage', 'Es gibt keine Vorlagendatei zum Herunterladen.'],
          ],
        },
        {
          kind: 'task',
          id: 'import-hochladen',
          title: 'Wie lade ich eine TimeRec-Datei hoch?',
          intro: 'Klicken Sie in der Navigation auf [[Import]]. Der Assistent hat drei Schritte: [[Hochladen]], [[Vorschau]] und [[Ergebnis]].',
          shot: 'pl-import-hochladen',
          steps: [
            { n: 1, text: 'Wählen Sie unter **Benutzer** die Person, der die Einträge zugeordnet werden.' },
            { n: 2, text: 'Ziehen Sie die .xls-Datei in das gestrichelte Feld oder klicken Sie hinein und wählen Sie die Datei aus. Der Dateiname erscheint im Feld.' },
            { n: 3, text: 'Klicken Sie auf [[Datei analysieren]]. Dabei wird die Datei nur gelesen – gespeichert ist noch nichts.' },
          ],
        },
        {
          kind: 'task',
          id: 'import-vorschau',
          title: 'Wie lese ich die Vorschau?',
          intro: 'Die Vorschau zeigt alle gefundenen Einträge mit Datum, Von, Bis, Pause und Netto. Die Netto-Stunden rechnet der Server so, wie er sie anschließend speichert.',
          shot: 'pl-import-vorschau',
          steps: [
            { n: 1, text: 'Über der Tabelle stehen die Zahl der **Einträge**, der **Konflikte** (rot) und der **Hinweise** (gelb).' },
            { n: 2, text: '**Konflikt:** Ein Eintrag mit demselben Beginn am selben Tag ist schon vorhanden. Ob er ersetzt wird, entscheiden Sie im nächsten Schritt.' },
            { n: 3, text: '**Hinweis:** Fahren Sie mit der Maus über das Kennzeichen – die Kurzinfo nennt den genauen Text. Das sind ArbZG-Warnungen (z. B. Ruhezeit, Höchstarbeitszeit), bei hinterlegten Arbeitszeit-Blöcken die Kappung der importierten Zeit und die Gründe, aus denen eine Zeile übersprungen wird.' },
            { n: 4, text: '**Neu:** Die Zeile wird ohne Beanstandung importiert. Unter Netto steht bei gekappten Zeilen die nicht angerechnete Zeit, zum Beispiel „2:30 h nicht angerechnet“.' },
          ],
        },
        {
          kind: 'table',
          head: ['Der Import überspringt …', 'Kurzinfo in der Vorschau'],
          rows: [
            ['einen ganzen Tag, an dem sich die Pause nach § 4 ArbZG nicht abziehen lässt', '„Wird übersprungen — die Pause nach § 4 ArbZG lässt sich mit den Zeilen dieses Tages nicht abziehen (es fehlen 10 Min). Bitte den Tag von Hand erfassen.“'],
            ['einen Tag mit mehr als 10 Stunden angerechneter Arbeitszeit', '„Wird übersprungen — die Tagesarbeitszeit beträgt 11:15 h und überschreitet die Höchstgrenze von 10 h nach § 3 ArbZG. Bitte den Tag von Hand erfassen.“'],
            ['eine Zeile, die sich mit einem vorhandenen Eintrag oder einer früheren Zeile des Tages überschneidet', '„Wird übersprungen — die Zeile überschneidet sich mit dem Eintrag 08:00–12:00 (Zeiteinträge einer Person dürfen sich nicht überschneiden).“'],
            ['Zeilen vor dem ersten oder nach dem letzten Arbeitstag der Person', '„Wird übersprungen — Datum liegt nach dem letzten Arbeitstag (25.09.2026).“'],
            ['Zeilen mit einem Datum nach heute', '„Wird übersprungen — Datum liegt in der Zukunft.“'],
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Die Pause rechnet der Import je Tag:** Mehrere Zeilen desselben Tages (z. B. ein geteilter Dienst) und dort schon vorhandene Einträge zählen zusammen; ein Abstand von mindestens 15 Minuten zwischen zwei Einträgen deckt die Pausenpflicht ab. ' +
            'Abgezogen wird nur, was dann noch fehlt – an der längsten Zeile des Tages. Reicht das nicht, übernimmt der Import den Tag **nicht**, auch wenn die Ausnahme „Pflicht-Pause war nicht möglich“ erlaubt ist, denn der Import kennt keine Begründung. Erfassen Sie solche Tage von Hand.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Altdaten:** Prüfen Sie vorher, dass als **Erster Arbeitstag** der tatsächliche Eintritt eingetragen ist und nicht der Starttag von PraxisZeit – Zeilen davor überspringt der Import. ' +
            'Eine Zeile ganz außerhalb der Arbeitszeit-Blöcke (z. B. 18:00–20:00 bei einem Block 08:00–12:00) übernimmt er dagegen wie jeden gestempelten Eintrag: angerechnet werden 0 Stunden, die Zeiten bleiben als Rohstempel gespeichert.',
        },
        {
          kind: 'task',
          id: 'import-bestaetigen',
          title: 'Wie bestätige ich den Import und was steht im Ergebnis?',
          intro: 'Unter der Tabelle entscheiden Sie über Konflikte und starten den Import.',
          shot: 'pl-import-bestaetigen',
          steps: [
            { n: 1, text: '[[Konflikte überschreiben]] (nur sichtbar, wenn es Konflikte gibt): Angekreuzt ersetzt der Import die vorhandenen Einträge, sonst bleiben sie stehen und zählen für die Pause des Tages mit. Die Vorschau rechnet jeden Konflikt als überschrieben.' },
            { n: 2, text: '[[← Zurück]] bringt Sie zur Auswahl von Person und Datei.' },
            { n: 3, text: 'Klicken Sie auf [[Import bestätigen]]. Sollen vorhandene Einträge überschrieben werden, fragt PraxisZeit noch einmal nach („Einträge überschreiben?“).' },
            { text: 'Das **Ergebnis** nennt die Zahl der importierten, überschriebenen und übersprungenen Einträge. Die **Hinweise** klappen Sie auf: Ruhezeit (§ 5) und Nachtarbeit (§ 6), die der Server bei der Bestätigung prüft, eine angepasste Pause („Pause an den Tag angepasst (0 → 30 Min)“) und der Grund jeder übersprungenen Zeile. Der Import steht im **Änderungsprotokoll**. Mit [[Weiteren Import starten]] beginnen Sie von vorn.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Bestätigung = Vorschau, neu gerechnet:** Höchstarbeitszeit, Pause und Überschneidungen rechnet die Bestätigung noch einmal und überspringt betroffene Tage oder Zeilen – die Hinweise der Vorschau übernimmt das Ergebnis nicht ungeprüft. ' +
            'Überschreibt der Import einen **anerkannten** Eintrag, steht in der Kurzinfo „Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet.“',
        },
      ],
    },

    // ── 14 ──────────────────────────────────────────────────────────────────
    {
      id: 'protokoll-fehler-monitoring',
      title: 'Protokoll & Fehler-Monitoring',
      blocks: [
        {
          kind: 'comic',
          scene: 'protokoll',
          text:
            'Das **Änderungsprotokoll** hält fest, wer wann an Zeiteinträgen, Abwesenheiten und Verwaltungseinstellungen etwas geändert hat. Es dient als Nachweis nach § 16 Abs. 2 ArbZG. ' +
            'Im laufenden Betrieb wird das Protokoll nur ergänzt; jede Zeile trägt eine Prüfsumme. Entfernt werden Zeilen nur beim endgültigen Löschen einer Person (Art. 17 DSGVO, selbst protokolliert) und durch die Aufbewahrungsfrist: Protokollzeilen zu Anträgen werden nach 730 Tagen gelöscht. Bei der Anonymisierung einer Person wird Klartext in Notizen ersetzt. Daneben zeigen **Konto-Vorgänge** die sicherheitsrelevanten Handlungen und das **Fehler-Monitoring** technische Störungen.',
        },
        {
          kind: 'task',
          id: 'protokoll-lesen',
          title: 'Wie lese ich das Änderungsprotokoll?',
          intro: 'Klicken Sie in der Navigation auf [[Änderungsprotokoll]]. Die Tabelle zeigt die Änderungen des gewählten Monats, die neuesten zuerst. Ihre Spalten: **Zeitpunkt**, **Mitarbeiter** (die Person, deren Eintrag sich geändert hat), **Geändert von** (die handelnde Person), **Aktion**, **Quelle** sowie **Alte Werte** und **Neue Werte**.',
          shot: 'pl-protokoll',
          steps: [
            { n: 1, text: '**Monat wählen:** mit den Pfeilen neben dem Monatsnamen. [[Zum aktuellen Monat springen]] bringt Sie zurück.' },
            { n: 2, text: '**Person filtern:** Die Auswahl steht auf „Alle Mitarbeitende“; wählen Sie eine Person, sehen Sie nur ihre Zeilen.' },
            { n: 3, text: '**Quelle** zeigt, auf welchem Weg die Änderung entstand, zum Beispiel „Manuell“, „Ausstempeln“, „Antrag“, „Import“, „Jahresabschluss“, „Einstellungen“ oder „Stundenänderung“. Wurde die Person unter **Geändert von** später endgültig gelöscht (Art. 17 DSGVO), steht dort „Gelöschte Person“.' },
            { n: 4, text: '**Alte Werte** und **Neue Werte** zeigen Datum, Zeiten, Pause und Notiz vorher und nachher; bei einer Einstellung steht dort der Wert vor und nach der Änderung.' },
          ],
        },
        {
          kind: 'table',
          head: ['Was PraxisZeit protokolliert', 'Beispiele'],
          rows: [
            ['Zeiteinträge', 'Erstellen, Ändern, Löschen, Ausstempeln – auch Einträge, die Mitarbeitende selbst am selben Tag anlegen'],
            ['Abwesenheiten', 'neue Abwesenheiten, Stornierungen'],
            ['Anträge', 'Korrekturanträge stellen, genehmigen, ablehnen'],
            ['Arbeitszeit-Änderungen und Anerkennungen', 'je Änderung eine Sammelzeile (Wirkungsdatum, neu berechnete Einträge, Grund), dazu eine Zeile je neu berechnetem Eintrag; Quelle „Stundenänderung“, „Neukappung (Arbeitszeit-Änderung)“ oder „Anrechnung anerkannt“'],
            ['Pflicht-Pause-Ausnahmen', 'die erfasste § 4-Ausnahme samt Begründung (Quelle „Pausen-Verzicht“)'],
            ['Überträge und Jahresabschluss', 'manuell gesetzte Überträge und je Person der Übertrag beim Anlegen oder Löschen eines Jahresabschlusses'],
            ['Einstellungen, Feiertage, verkürzte Tage', 'jede geänderte Einstellung mit altem und neuem Wert („Einstellung geändert“)'],
            ['Benutzerangaben mit Wirkung auf Auswertungen', '„Ausgenommen nach § 18 ArbZG“, „Nachtarbeitnehmer“, erster und letzter Arbeitstag („Benutzerangabe geändert“)'],
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Tatsächliche Stempel:** Weichen die angerechnete und die gestempelte Zeit eines Eintrags voneinander ab, nennt die Zeile beide, zum Beispiel „07:45 - 16:15“ und darunter „gestempelt 06:00 - 18:00“. Das gilt auch beim Löschen.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Das Protokoll ist kein unveränderbares Archiv.** Es macht nachträgliche Veränderungen **erkennbar**, verhindern kann sie nur der Schutz des Servers. Bewahren Sie deshalb auch die Datensicherungen auf, siehe [Datensicherung](#sicherung-einrichten).',
        },
        {
          kind: 'task',
          id: 'protokoll-pruefen',
          title: 'Wie prüfe ich, ob das Protokoll unverändert ist?',
          intro: 'Unter der Tabelle steht die Karte **Prüfung des Änderungsprotokolls**. PraxisZeit prüft jede Nacht (03:15 Uhr) jede Zeile gegen ihre Prüfsumme, versiegelt neue Zeilen zu einer Kette und prüft, ob Glieder fehlen.',
          shot: 'pl-protokoll-pruefung',
          steps: [
            { n: 1, text: 'Klicken Sie auf [[Jetzt prüfen]], wenn Sie nicht bis zur nächsten Nacht warten möchten.' },
            { n: 2, text: 'Die Zeile **Letzte Prüfung** nennt Zeitpunkt und Ergebnis. Solange noch keine Prüfung gelaufen ist, steht dort „Noch keine Prüfung gelaufen.“' },
          ],
        },
        {
          kind: 'table',
          head: ['Ergebnis', 'Bedeutung und was Sie tun'],
          rows: [
            ['**in Ordnung**', 'Keine Zeile verändert, keine entfernt. Ältere Zeilen ohne prüfbare Prüfsumme (Altbestand) werden nur gezählt.'],
            ['**Abweichung gefunden**', 'Zeilen wurden außerhalb von PraxisZeit verändert oder entfernt, zum Beispiel direkt in der Datenbank. Der Vorgang steht zusätzlich unter „Konto-Vorgänge“ und im Fehler-Monitoring. Bewahren Sie die Datensicherungen auf und informieren Sie den Support.'],
            ['**Kettenende fehlt** oder **ungültig**', 'Der versiegelte Abschluss der Kette ist weg oder verändert. PraxisZeit legt ihn **nicht** von selbst neu an. Bis zur Klärung sind das endgültige Löschen von Personen und das automatische Entfernen nach der Aufbewahrungsfrist gesperrt. Erst wenn die Ursache geklärt ist (zum Beispiel eine Datensicherung geprüft), setzen Sie ihn mit [[Kettenende neu setzen…]] und einem **Grund** (mindestens 10 Zeichen) neu. Das Neusetzen steht danach dauerhaft im Protokoll.'],
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Der Schlüssel SECRET_KEY gehört zur Prüfung:** Die Prüfsummen hängen am geheimen Schlüssel des Servers. Geht er verloren (zum Beispiel bei einer Neuinstallation ohne die Datei config/.secret-key), lassen sich die Prüfsummen nicht mehr prüfen. Bewahren Sie ihn getrennt von den Sicherungen auf.',
        },
        {
          kind: 'task',
          id: 'konto-vorgaenge',
          title: 'Wo sehe ich Konto-Vorgänge?',
          intro: 'Die Liste **Konto-Vorgänge** steht ganz unten auf der Seite [[Änderungsprotokoll]]: Konten, Rollen, Passwörter, Zwei-Faktor und Datenbank-Sicherungen, also wer wann was getan hat. Sie zeigt die neuesten 200 Vorgänge und ist nicht gefiltert.',
          shot: 'pl-konto-vorgaenge',
          steps: [
            { n: 1, text: 'Die Liste beginnt mit dem neuesten Vorgang. **Zeitpunkt** nennt Datum und Uhrzeit, **Konto** die betroffene Person, **Detail** ergänzt Einzelheiten, zum Beispiel die Rolle eines neuen Kontos.' },
            { n: 2, text: '**Vorgang** nennt, was geschah, zum Beispiel „Konto angelegt“, „Konto deaktiviert“, „Rolle geändert“, „Sicherung erstellt“, „Sicherung heruntergeladen“ oder „Sicherung gelöscht“.' },
            { n: 3, text: '**Durch** nennt die handelnde Stelle. Bei Notfall-Vorgängen auf dem Server steht dort „Kommandozeile (Benutzer@Rechner)“, siehe [Admin-Passwort verloren](#passwort-zuruecksetzen).' },
          ],
        },
        {
          kind: 'table',
          head: ['In den Konto-Vorgängen stehen', 'Hinweis'],
          rows: [
            ['Konten angelegt (mit Rolle), Benutzernamen geändert, Konten deaktiviert oder reaktiviert, Rolle gewechselt', 'Admin ↔ Mitarbeitende'],
            ['fremdes Passwort durch die Verwaltung gesetzt', 'Das eigene Passwort ändern Sie unter **Profil → Passwort ändern**, nicht über die Benutzerverwaltung.'],
            ['Zwei-Faktor im Profil ein- oder abgeschaltet, durch die Verwaltung zurückgesetzt, falsche Zwei-Faktor-Codes', 'Nach 10 falschen Codes in einer Stunde ist die Anmeldung des Kontos für eine Stunde gesperrt.'],
            ['Abmeldung nach 5 falschen Passworteingaben in einer offenen Sitzung', 'zum Beispiel beim Passwort ändern oder beim Herunterladen einer Sicherung'],
            ['Datenbank-Sicherungen erstellt, heruntergeladen, gelöscht, Einstellungen geändert', 'Die geplante tägliche Sicherung steht nicht darin.'],
            ['Notfall-Vorgänge auf dem Server (Passwort-Reset, Zwei-Faktor abschalten, Reaktivieren)', 'Siehe das letzte Kapitel dieses Handbuchs.'],
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Fehlgeschlagene Anmeldungen stehen hier nicht.** Sie stehen im Protokoll des Servers (AUTH login_failed …), nicht im Änderungsprotokoll.',
        },
        {
          kind: 'task',
          id: 'fehler-monitoring',
          title: 'Wie lese ich das Fehler-Monitoring?',
          intro: 'Klicken Sie in der Navigation auf [[Fehler-Monitoring]]. Die Seite zeigt technische Fehler, die im Betrieb aufgetreten sind.',
          shot: 'pl-fehler-monitoring',
          steps: [
            { n: 1, text: '[[Aktualisieren]] lädt die Liste und die Zähler neu. Liegen Fehler vor, zeigen Zähler oben die Anzahl je Status (open, ignored, resolved).' },
            { n: 2, text: 'Die Reiter [[Alle]], [[Offen]], [[Ignoriert]] und [[Behoben]] filtern die Liste. Am Reiter „Offen“ steht die Zahl der offenen Fehler, sobald es welche gibt.' },
            { n: 3, text: 'Die Liste zeigt jeden Fehler als eigene Karte. Gibt es keinen, steht hier „Keine Fehler gefunden“, wie im Bild.' },
          ],
        },
        {
          kind: 'table',
          head: ['Jeder Eintrag zeigt', 'Bedeutung'],
          rows: [
            ['Stufe (zum Beispiel ERROR)', 'Schweregrad des Fehlers'],
            ['×Zahl', 'wie oft derselbe Fehler aufgetreten ist; einmalige Fehler sind meist unkritisch'],
            ['Methode und Pfad', 'welcher Aufruf betroffen war'],
            ['Meldung', 'die Fehlermeldung, oft mit verständlicher Beschreibung'],
            ['Zuerst und Zuletzt', 'wann der Fehler zum ersten und zum letzten Mal auftrat'],
          ],
        },
        {
          kind: 'table',
          head: ['Symbol am Eintrag', 'Wirkung'],
          rows: [
            ['Häkchen („Als behoben markieren“)', 'setzt den Fehler auf „Behoben“'],
            ['durchgestrichenes Auge („Ignorieren“)', 'blendet einen offenen Fehler aus der Liste „Offen“ aus'],
            ['Warndreieck („Wieder öffnen“)', 'setzt einen behobenen oder ignorierten Fehler zurück auf „Offen“'],
            ['Papierkorb („Löschen“)', 'entfernt den Eintrag nach Rückfrage'],
            ['Pfeil', 'klappt Stack Trace und GitHub-Issue auf'],
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Was tun bei Fehlern?** Lesen Sie die Meldung, prüfen Sie die Häufigkeit und notieren Sie bei wiederkehrenden Fehlern Zeitstempel und Meldung. Wenden Sie sich an Ihren IT-Support oder melden Sie den Fehler als GitHub-Issue: Im aufgeklappten Eintrag öffnet [[Issue auf GitHub erstellen]] ein vorbereitetes Issue; die Adresse eines bestehenden Issues können Sie dort eintragen und speichern.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Datenschutz (Art. 28 DSGVO):** Fehlermeldungen können personenbezogene Daten enthalten. Prüfen Sie vor der Übertragung zu GitHub, ob der Stack Trace sensible Angaben enthält; GitHub ist als Auftragsverarbeiter einzustufen. Die Seite weist im aufgeklappten Eintrag selbst darauf hin.',
        },
      ],
    },

    // ── 15 ──────────────────────────────────────────────────────────────────
    {
      id: 'datensicherung',
      title: 'Datensicherung',
      blocks: [
        {
          kind: 'comic',
          scene: 'datensicherung',
          text:
            'PraxisZeit speichert alle Zeitdaten in einer Datenbank. **§ 16 ArbZG verlangt, Zeitaufzeichnungen mindestens 2 Jahre aufzubewahren.** Unter **Datensicherung** erstellen und verwalten Sie Sicherungen ohne Kommandozeile, in der Docker- **und** in der nativen Installation. ' +
            'Stellen Sie die Aufbewahrungsdauer entsprechend ein, halten Sie eine Kopie **außerhalb** des Servers vor und sichern Sie vor jedem Update zusätzlich.',
        },
        {
          kind: 'task',
          id: 'sicherung-einrichten',
          title: 'Wie sichere ich jetzt und wie richte ich die tägliche Sicherung ein?',
          intro: 'Klicken Sie in der Navigation auf [[Datensicherung]]. Eine Sicherung ist ein komprimierter Datenbank-Dump (praxiszeit_<Zeitstempel>.sql.gz).',
          shot: 'pl-datensicherung',
          steps: [
            { n: 1, text: '[[Jetzt sichern]] erstellt sofort eine vollständige Sicherung. Sie erscheint danach in der Liste.' },
            { n: 2, text: 'Haken bei [[Tägliche automatische Sicherung aktivieren]], wenn PraxisZeit täglich selbst sichern soll.' },
            { n: 3, text: '**Uhrzeit (Stunde, 0–23), nur Docker:** lokale Zeit (Europe/Berlin); die Sicherung läuft um HH:30. Das gilt für die Docker-Installation; nativ sichert der Timer des Betriebssystems (Linux 02:00, Windows und macOS 03:00).' },
            { n: 4, text: '**Aufbewahrung (Tage), nur Docker:** ältere Sicherungen löscht PraxisZeit automatisch. Für § 16 ArbZG sind mindestens 2 Jahre (730 Tage) nötig; die Seite schlägt zunächst 30 Tage vor. Nativ gilt stattdessen retention_days im Abschnitt [backup] der Datei config/praxiszeit.conf (Standard 31 Tage). Sonst zusätzlich Jahresarchive außerhalb des Servers ablegen.' },
            { n: 5, text: '**Speicherort (optional, nur Docker):** leer bedeutet Standardverzeichnis. Der Pfad muss für den Dienst beschreibbar sein.' },
            { n: 6, text: 'Klicken Sie auf [[Einstellungen speichern]]. Erst dann gelten Uhrzeit, Aufbewahrung und Speicherort, und zwar nur in der Docker-Installation; nativ steuert der Timer des Betriebssystems die geplante Sicherung.' },
            { n: 7, text: 'Unter **Vorhandene Sicherungen** stehen Datei, Größe und Zeitpunkt. Dort laden Sie eine Sicherung herunter oder löschen sie, siehe die Tipps unten.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Wo die Sicherungen liegen:** Docker im Volume praxiszeit_backups, nativ im Verzeichnis data/backups/. **Native Installation:** Die *geplante* Sicherung läuft dort weiterhin über den Timer des Betriebssystems (Linux: täglich 02:00 über systemd, Windows: täglich 03:00 als geplante Aufgabe, macOS: täglich 03:00 über launchd). ' +
            'Die Einstellung auf dieser Seite steuert die Docker-Variante; „Jetzt sichern“ und die Liste funktionieren überall. Die Aufbewahrungsdauer der nativen Timer steht in config/praxiszeit.conf (retention_days, Standard 31 Tage).',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Herunterladen und Löschen:** In der Liste lädt das Symbol „Herunterladen“ die Datei auf Ihren PC; vorher fragt PraxisZeit nach **Ihrem Passwort** (Dialog „Sicherung herunterladen“), weil die Datei die gesamte Datenbank mit allen Gesundheitsdaten enthält. Das Symbol „Löschen“ entfernt eine Sicherung nach Rückfrage endgültig. ' +
            'Erstellen, Herunterladen, Löschen und geänderte Einstellungen stehen unter „Konto-Vorgänge“, siehe [Konto-Vorgänge](#konto-vorgaenge).',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Sicherungen sind nicht verschlüsselt:** Sie enthalten die ganze Datenbank einschließlich Krankheitstagen. Legen Sie eine Kopie außer Haus nur verschlüsselt ab, zum Beispiel als 7-Zip-Archiv mit AES-256 oder auf einem BitLocker-USB-Stick, und löschen Sie heruntergeladene Dateien danach aus dem Download-Ordner. Spielen Sie nur eigene Sicherungen ein.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Speicherort:** PraxisZeit lehnt Netzwerkpfade (\\\\Server\\Freigabe), Netzlaufwerke, für alle Konten lesbare Ordner, Systemordner und Laufwerkswurzeln ab, unter Windows auch alles unter C:\\Users, C:\\ProgramData und C:\\Program Files. ' +
            'Tragen Sie unter Windows am besten einen **neuen** Ordnernamen ein: PraxisZeit legt ihn an und gibt ihm die Rechte „nur SYSTEM und Administratoren“. Die Rechte eines bestehenden Ordners ändert PraxisZeit nicht; ist er für andere Konten zugänglich, erscheint ein Hinweis.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Den Schlüssel SECRET_KEY mitsichern:** Für einen neuen Rechner reicht die Datenbanksicherung nicht. Der Schlüssel (nativ config/.secret-key, Docker SECRET_KEY in der .env) verschlüsselt die Zwei-Faktor-Geheimnisse und bildet die Prüfsummen des Änderungsprotokolls. Bewahren Sie ihn einmalig, verschlüsselt und **getrennt** von den Sicherungen auf, zum Beispiel im Passwort-Safe der Praxis. Ohne ihn müssen alle die Zwei-Faktor-Anmeldung neu einrichten.',
        },
        {
          kind: 'prose',
          text:
            '**Wiederherstellen:** Die Oberfläche kann Sicherungen erstellen, laden und löschen, aber nicht einspielen. Das Einspielen geschieht auf dem Server mit einem Kommando. Eingespielt wird nur eine Sicherung mit passender **Signatur**: PraxisZeit signiert jede Sicherung mit dem SECRET_KEY der Installation. ' +
            'Eine Sicherung einer älteren Version oder vom alten Rechner geht nur mit dem Zusatz --force-unverified, und nur, wenn sie sicher aus der eigenen Praxis stammt. Bei der nativen Installation bricht das Einspielen ab, wenn die Sicherung von einer **neueren** Version stammt oder das Einspielen scheitert; die bisherige Datenbank bleibt dann unverändert.',
        },
        {
          kind: 'table',
          head: ['Installation', 'Befehl zum Einspielen'],
          rows: [
            ['Docker (neben der docker-compose.yml)', 'bash restore.sh backups/praxiszeit_<zeitstempel>.sql.gz'],
            ['Linux nativ, 1. Dienst anhalten', 'sudo systemctl stop praxiszeit'],
            ['Linux nativ, 2. Sicherung einspielen', 'sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py restore /opt/praxiszeit/data/backups/<datei>.sql.gz'],
            ['Linux nativ, 3. Dienst starten', 'sudo systemctl start praxiszeit'],
            ['macOS nativ, 1. Dienst anhalten', 'sudo launchctl unload /Library/LaunchDaemons/de.praxiszeit.server.plist'],
            ['macOS nativ, 2. Sicherung einspielen (Dienstkonto _praxiszeit)', 'sudo -u _praxiszeit /usr/local/praxiszeit/bin/python/bin/python3 /usr/local/praxiszeit/praxiszeit-server.py restore /usr/local/praxiszeit/data/backups/<datei>.sql.gz'],
            ['macOS nativ, 3. Dienst starten', 'sudo launchctl load /Library/LaunchDaemons/de.praxiszeit.server.plist'],
            ['Windows nativ (Eingabeaufforderung als Administrator im Installationsordner)', 'restore-backup.bat data\\backups\\<datei>.sql.gz'],
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Nach dem Einspielen** startet das Backend neu; erst dieser Start hebt eine Sicherung einer älteren Version per Migration auf den Stand der installierten Version. Nativ unter Linux und macOS muss der Dienst vor dem Einspielen **angehalten** sein, sonst bricht das Kommando ab, ohne etwas anzufassen. Führen Sie es als Dienstkonto aus, nicht als root. ' +
            'Alle Kommandozeilen-Varianten, auch das Sichern ohne Oberfläche, stehen in docs/BACKUP.md.',
        },
      ],
    },

    // ── 16 ──────────────────────────────────────────────────────────────────
    {
      id: 'schichtplanung',
      title: 'Schichtplanung',
      blocks: [
        {
          kind: 'comic',
          scene: 'schichtplan',
          text:
            'Mit der **Schichtplanung** erstellen Sie wöchentliche Einsatzpläne: wer steht wann an welchem Arbeitsplatz. Sie ist ein **reines Planungswerkzeug** und verändert **nicht** Zeiterfassung, Soll und Ist, ArbZG-Prüfungen, Urlaub oder Überstunden. ' +
            'Das Modul ist nach der Installation **aus**; nur Admins können es einschalten, den Schalter beschreibt [Tour und Schichtplanung](#tour-schichtplanung). Erst danach erscheinen die Menüpunkte und die Dashboard-Karte „Deine Einteilung heute“.',
        },
        {
          kind: 'table',
          head: ['Begriff', 'Bedeutung'],
          rows: [
            ['Standort', 'optionale Gruppierung für Arbeitsplätze, zum Beispiel Hauptstelle oder Filiale'],
            ['Arbeitsplatz', 'ein zu besetzender Platz (Anmeldung, Labor, Springer …) mit Farbe für die Wochenansicht'],
            ['Schichtplan', 'ein benannter Wochenplan, zum Beispiel „Normalzustand“ oder „Azubis Schulferien“; beliebig viele'],
            ['Zeitslot', 'ein Arbeitsplatz an einem Wochentag in einem Zeitfenster, mit optionaler Mindestbesetzung'],
            ['Einweisung', 'für welche Arbeitsplätze eine Person eingewiesen ist'],
          ],
        },
        {
          kind: 'task',
          id: 'schicht-wochentage',
          title: 'Wie lege ich die geplanten Wochentage fest?',
          intro: 'Bei eingeschalteter Schichtplanung steht unter dem Schalter in den [[Einstellungen]] der Bereich **Geplante Wochentage**. Standard ist Montag bis Freitag.',
          shot: 'pl-schicht-wochentage',
          steps: [
            { n: 1, text: 'Klicken Sie die Wochentage an, die der Schichtplaner anzeigen und planen soll. Samstag, Sonntag oder ein Schließtag lassen sich einzeln zu- und abschalten; **mindestens ein Tag** muss aktiv bleiben.' },
            { n: 2, text: 'Klicken Sie auf [[Wochentage speichern]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Ein abgeschalteter Tag verschwindet aus der Wochenansicht, nimmt keine neuen Slots auf und wird beim automatischen Füllen übersprungen. Bereits angelegte Slots bleiben erhalten und kehren zurück, sobald Sie den Tag wieder aktivieren.',
        },
        {
          kind: 'task',
          id: 'schicht-stammdaten',
          title: 'Wie lege ich Standorte und Arbeitsplätze an?',
          intro: 'Klicken Sie in der Navigation auf [[Schichtplanung]] und wählen Sie den Reiter [[Stammdaten]]. Links stehen die **Standorte**, rechts die **Arbeitsplätze**.',
          shot: 'pl-schicht-stammdaten',
          steps: [
            { n: 1, text: '**Standorte** sind optional: Tragen Sie unter **Neuer Standort** einen Namen ein, zum Beispiel „Hauptstelle“, und bestätigen Sie mit dem Plus-Knopf. Arbeitsplätze können auch ohne Standort („global“) bestehen.' },
            { n: 2, text: '**Arbeitsplätze:** Tragen Sie unter **Name** zum Beispiel „Anmeldung“ oder „Labor“ ein; **Standort (optional)** ordnet ihn einem Standort zu.' },
            { n: 3, text: 'Wählen Sie die **Farbe**, in der der Arbeitsplatz in der Wochenansicht erscheint.' },
            { n: 4, text: 'Klicken Sie auf [[Hinzufügen]]. Der Arbeitsplatz erscheint in der Liste darunter.' },
            { n: 5, text: 'In der Liste ändern Sie einen Eintrag mit dem Stift-Symbol („Bearbeiten“) oder entfernen ihn mit dem Papierkorb („Löschen“).' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Löschen geht nur, solange nichts daran hängt: ein Standort nur, wenn kein Arbeitsplatz ihm zugeordnet ist, ein Arbeitsplatz nur, wenn er in keinem Slot verwendet wird.',
        },
        {
          kind: 'task',
          id: 'schicht-einweisungen',
          title: 'Wie halte ich fest, wer für welchen Arbeitsplatz eingewiesen ist?',
          intro: 'Wählen Sie in der [[Schichtplanung]] den Reiter [[Einweisungen]]. Die Tabelle zeigt die Mitarbeitenden in den Zeilen und die Arbeitsplätze in den Spalten.',
          shot: 'pl-schicht-einweisungen',
          steps: [
            { n: 1, text: 'Jede Spalte ist ein **Arbeitsplatz**, hier zum Beispiel „Labor“.' },
            { n: 2, text: 'Ein **Häkchen** bedeutet: Die Person ist für diesen Arbeitsplatz eingewiesen. Die Änderung wird sofort gespeichert.' },
            { n: 3, text: 'Ohne Häkchen ist die Person nicht eingewiesen. Ziehen Sie sie trotzdem auf einen Slot dieses Arbeitsplatzes, erscheint die **gelbe Warnung „nicht eingewiesen“**.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Die Warnung blockiert nicht. Sie entscheiden bewusst, zum Beispiel bei einer Einarbeitung unter Aufsicht. Mitarbeitende sehen ihre eigenen Einweisungen im Profil unter „Meine Einweisungen“.',
        },
        {
          kind: 'task',
          id: 'schicht-plan-bearbeiten',
          title: 'Wie lege ich einen Schichtplan an und bearbeite ihn?',
          intro: 'Im Reiter [[Schichtpläne]] steht links die Liste der Pläne, rechts der Editor des gewählten Plans. Die ausklappbare **Jahresübersicht** darüber zeigt als Zeitstrahl, welcher Plan in welchem Zeitraum des Jahres läuft.',
          shot: 'pl-schicht-editor',
          steps: [
            { n: 1, text: 'Tragen Sie unter **Neuer Plan** einen Namen ein, zum Beispiel „Normalzustand“, und legen Sie den Plan mit dem Plus-Knopf an. Ein Klick auf einen Plan in der Liste öffnet ihn; ein Punkt oder Haken zeigt, ob er aktiv ist.' },
            { n: 2, text: '[[Aktiv schalten]] macht den Plan für alle sichtbar; bei einem aktiven Plan, wie im Bild, heißt der Knopf [[Deaktivieren]]. **Mehrere Pläne können gleichzeitig aktiv** sein, zum Beispiel einer je Standort.' },
            { n: 3, text: '[[Bearbeiten]] öffnet die Plan-Einstellungen mit Name, Zeitraum und Freigabe, siehe [Plan freigeben](#schicht-plan-einstellungen).' },
            { n: 4, text: '[[PDF]] erzeugt einen Aushang im Querformat mit einer Tabelle Arbeitsplatz × Wochentag, zum Aushängen am Schwarzen Brett.' },
            { n: 5, text: 'Der Umschalter [[Woche]] / [[Tag]] wechselt zwischen der Wochenansicht und einem einzelnen Wochentag in voller Breite; das ist beim Einrichten übersichtlich. Im Raster ziehen Sie einen Slot per Drag & Drop auf einen anderen Tag oder eine andere Uhrzeit (15-Minuten-Raster); ein Klick auf eine freie Fläche legt einen Slot an, ein Klick auf einen Slot bearbeitet ihn.' },
            { n: 6, text: 'Rechts stehen die **Mitarbeitenden**. Ziehen Sie eine Person auf einen Slot, um sie zuzuweisen. Unter jedem Namen zeigt die **Auslastung** die zugewiesenen Schichtstunden zur Wochenarbeitszeit, zum Beispiel „15,25 / 17 h“: grün bei ±30 Minuten, gelb bei ±1 Stunde, sonst rot.' },
          ],
        },
        {
          kind: 'table',
          head: ['Weitere Knöpfe der Werkzeugleiste', 'Wirkung'],
          rows: [
            ['[[Slot]]', 'legt einen Zeitslot an, siehe [Zeitslot anlegen](#schicht-slot)'],
            ['[[Automatisch füllen]]', 'besetzt die Slots selbst, siehe [Automatisch füllen](#schicht-fuellen)'],
            ['[[Duplizieren]]', 'kopiert den Plan als Entwurf, siehe den Tipp darunter'],
            ['Papierkorb („Plan löschen“)', 'löscht den Plan samt Slots und Zuweisungen nach Rückfrage'],
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Duplizieren** kopiert einen Plan mit allen Slots und Zuweisungen. Die Kopie ist ein **inaktiver Entwurf** ohne Zeitraum und ohne Freigabe für Mitarbeitende; so leiten Sie Varianten wie „Sommer“ oder „Schulferien“ aus einem Bestandsplan ab. Arbeitsplätze und Einweisungen gehören keinem Plan und werden nicht mitkopiert.',
        },
        {
          kind: 'task',
          id: 'schicht-slot',
          title: 'Wie lege ich einen Zeitslot an?',
          intro: 'Klicken Sie im Editor auf [[Slot]]. Der Dialog **Neuer Zeitslot** öffnet sich; ein vorhandener Slot heißt im Dialog **Zeitslot bearbeiten**.',
          shot: 'pl-schicht-slot',
          steps: [
            { n: 1, text: 'Wählen Sie den **Arbeitsplatz**.' },
            { n: 2, text: 'Wählen Sie den **Wochentag**.' },
            { n: 3, text: 'Tragen Sie **Von** und **Bis** ein.' },
            { n: 4, text: '**Mindestbesetzung:** 0 bedeutet keine Mindestbesetzung; sonst markiert PraxisZeit den Slot bei Unterbesetzung. Das ist eine **weiche Warnung**, Speichern und Aktivieren bleiben möglich.' },
            { n: 5, text: '**Hinweis (optional):** bis zu 500 Zeichen, zum Beispiel „Einarbeitung Azubi“. Er erscheint mit vorangestelltem **»** im Wochenraster, im PDF-Aushang und auf der Dashboard-Karte „Deine Einteilung heute“.' },
            { n: 6, text: 'Haken Sie unter **Zugewiesene Mitarbeiter** die Personen an. Wer nicht eingewiesen ist, trägt das Kennzeichen „nicht eingewiesen“. Zum Schluss speichern Sie den Slot mit [[Speichern]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Der Hinweis ist für alle sichtbar:** Alle Mitarbeitenden, die den Plan sehen dürfen, lesen ihn, und der PDF-Aushang druckt ihn mit; ein Schwarzes Brett hängt oft an einem Ort, den auch Patientinnen und Patienten einsehen. Tragen Sie dort **keine Gesundheitsangaben** oder andere sensible Daten ein.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Slot kopieren:** Beim Bearbeiten eines Slots legt „Auf Wochentage kopieren“ ihn auf weiteren Wochentagen zusätzlich an, mit Arbeitsplatz, Zeit, Mindestbesetzung, Zuweisungen **und Hinweis**. Bei einem personenbezogenen Hinweis wie „Vertretung für Frau Schmidt“ bedenken Sie, dass er mitkopiert wird.',
        },
        {
          kind: 'task',
          id: 'schicht-fuellen',
          title: 'Wie lasse ich einen Plan automatisch füllen?',
          intro: 'Klicken Sie im Editor auf [[Automatisch füllen]]. Der Dialog besetzt die Slots mit eingewiesenen, verfügbaren Mitarbeitenden, ausgewogen nach Auslastung und Überstundenkonto.',
          shot: 'pl-schicht-fuellen',
          steps: [
            { n: 1, text: 'Wählen Sie die **Zielwoche**. Sie bestimmt, welche Abwesenheiten und Stunden berücksichtigt werden; der Dialog nennt darunter den Montag der Woche.' },
            { n: 2, text: 'Wählen Sie den **Modus**: „Alle Zuweisungen neu verteilen“ oder „Nur Lücken auffüllen (vorhandene behalten)“.' },
            { n: 3, text: 'Klicken Sie auf [[Generieren]]. Das Ergebnis ist ein **Entwurf** zum Prüfen; der Plan wird dabei **nicht** aktiviert.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Der Generator liest Abwesenheiten, Wochenstunden und Überstundenkonto nur und verändert daran nichts. Er setzt niemanden ein, der an dem Tag abwesend oder außerhalb seines Beschäftigungsfensters ist, und keine Person auf zwei überlappende Slots. Slots, die sich nicht besetzen lassen, bleiben offen; eine Meldung und die Unterbesetzungs-Markierung sagen es Ihnen.',
        },
        {
          kind: 'task',
          id: 'schicht-plan-einstellungen',
          title: 'Wie gebe ich einen Plan für Mitarbeitende frei?',
          intro: 'Klicken Sie im Editor auf [[Bearbeiten]]. Der Dialog **Plan-Einstellungen** öffnet sich.',
          shot: 'pl-schicht-plan-einstellungen',
          steps: [
            { n: 1, text: 'Ändern Sie bei Bedarf den **Namen** und die Beschreibung.' },
            { n: 2, text: '**Automatisch aktiv im Zeitraum (optional):** Liegt das heutige Datum zwischen **von** und **bis**, gilt der Plan automatisch als aktiv, zusätzlich zum Knopf „Aktiv schalten“. Eine offene Grenze ist erlaubt.' },
            { n: 3, text: 'Mit dem Haken **Für Mitarbeitende sichtbar** erscheint der Plan in der Mitarbeiteransicht, auch wenn er heute noch nicht gilt, zum Beispiel um einen ab September geltenden Plan früh bekannt zu machen.' },
            { n: 4, text: 'Klicken Sie auf [[Speichern]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Falle bei befristeten Plänen:** Die Freigabe gilt in beide Richtungen. Ein befristeter Plan, zum Beispiel ein Sommerplan Juli bis August, bleibt für Mitarbeitende sichtbar, solange der Haken gesetzt ist, auch Wochen nach Ablauf; dort steht er dann mit dem Vermerk „Nicht mehr gültig“. Nehmen Sie die Freigabe selbst zurück. ' +
            'Ein heute aktiver Plan ist ohnehin sichtbar. Eine **Kopie** übernimmt die Freigabe nicht. Welche Pläne freigegeben sind, sehen Sie am Augen-Symbol in der Planliste und am Abzeichen „Sichtbar“ im Kopf des geöffneten Plans.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**PDF-Aushang:** Gilt der gedruckte Plan gerade nicht (Vorschau oder abgelaufen), steht fett in der Kopfzeile „Vorschau — gilt derzeit nicht“ beziehungsweise „Nicht mehr gültig“, damit er am Schwarzen Brett nicht mit dem geltenden Plan verwechselt wird. Haben alle Arbeitsplätze denselben Standort, steht er einmal in der Kopfzeile, sonst hinter dem Namen jedes Arbeitsplatzes. Auch Mitarbeitende können den Plan, den sie sehen, mit dem Knopf „PDF“ drucken. Mitarbeitende sehen ihre heutige Einteilung auf dem Dashboard; ihre Seite beschreibt das Handbuch für Mitarbeitende.',
        },
      ],
    },

    // ── 17 ──────────────────────────────────────────────────────────────────
    {
      id: 'admin-passwort-verloren',
      title: 'Admin-Passwort verloren',
      blocks: [
        {
          kind: 'comic',
          scene: 'passwort',
          text:
            'Kommt niemand mehr mit einem Administrator-Konto in die Anwendung, hilft ein Kommando **auf dem Server selbst**. Es setzt das Passwort direkt in der Datenbank neu und braucht dafür **keine Anmeldung**. Dieses Kapitel hat keine Bildschirmfotos, weil es keine Oberfläche dafür gibt: Sie arbeiten in einer Eingabeaufforderung oder einem Terminal auf dem Server.',
        },
        {
          kind: 'task',
          id: 'passwort-zuruecksetzen',
          title: 'Wie setze ich das Admin-Passwort zurück?',
          intro: 'Führen Sie den Befehl für Ihre Installation aus. Die lange Form ist nötig: praxiszeit-server.py liegt nicht im Suchpfad, und die Programmbibliotheken stecken nur im mitgelieferten Python unter bin/python.',
          steps: [
            { n: 1, text: 'Öffnen Sie auf dem Server ein Terminal (Windows: Eingabeaufforderung **als Administrator** im Installationsordner).' },
            { n: 2, text: 'Führen Sie den Befehl aus der Tabelle aus.' },
            { n: 3, text: 'Geben Sie das neue Passwort zweimal ein. Es wird nicht mit eingetippt, damit es nicht in der Befehls-Historie landet. PraxisZeit prüft dieselben Regeln wie die Anwendung: mindestens 10 Zeichen, Groß- und Kleinbuchstabe, Ziffer.' },
            { n: 4, text: 'Melden Sie sich mit dem Benutzernamen und dem neuen Passwort an. Alle laufenden Sitzungen dieses Kontos sind danach ungültig; wer damit angemeldet war, muss sich neu anmelden.' },
          ],
        },
        {
          kind: 'table',
          head: ['Installation', 'Befehl'],
          rows: [
            ['Linux (Standardordner /opt/praxiszeit)', 'sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py reset-admin-password'],
            ['macOS (Standardordner /usr/local/praxiszeit, Dienstkonto _praxiszeit mit Unterstrich)', 'sudo -u _praxiszeit /usr/local/praxiszeit/bin/python/bin/python3 /usr/local/praxiszeit/praxiszeit-server.py reset-admin-password'],
            ['Windows (Installationsordner zum Beispiel C:\\PraxisZeit)', 'bin\\python\\python.exe praxiszeit-server.py reset-admin-password'],
            ['Docker (neben der docker-compose.yml)', 'docker compose exec backend python -m app.cli.reset_admin_password'],
          ],
        },
        {
          kind: 'table',
          head: ['Option (hinten anhängen)', 'Wirkung'],
          rows: [
            ['--username <name>', 'setzt das Passwort eines anderen Kontos als admin'],
            ['--reactivate', 'ist das Konto **deaktiviert**, genügt ein neues Passwort nicht, die Anmeldung bleibt gesperrt (Meldung „Das Konto ist derzeit deaktiviert und bleibt es auch“); mit dieser Option setzt das Kommando das Passwort neu **und** aktiviert das Konto wieder'],
            ['--disable-2fa', 'ist auch das Handy mit der Zwei-Faktor-Anmeldung weg, verlangt der Login nach dem neuen Passwort weiter einen Code; diese Option schaltet die Zwei-Faktor-Anmeldung ab, danach richten Sie im Profil eine neue ein'],
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Alles wird protokolliert:** Jeder solche Vorgang wird dauerhaft festgehalten, mit Zeitpunkt, betroffenem Konto und dem Betriebssystem-Konto, das ihn ausgelöst hat (Nachweispflicht nach Art. 5 Abs. 2 DSGVO). Sie finden ihn unter „Konto-Vorgänge“ mit der handelnden Stelle „Kommandozeile (Benutzer@Rechner)“, siehe [Konto-Vorgänge](#konto-vorgaenge). Ein Eingriff von Hand in die Datenbank ist weder nötig noch empfohlen; dabei entfiele die Protokollzeile.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Der Eintrag [admin] password in config/praxiszeit.conf ist keine Antwort:** Er ist nur der Startwert der Erstinstallation und wird bei einer späteren Passwortänderung nicht nachgeführt. Nach einem Reset überschreibt ihn das Kommando mit einem Zufallswert. Löschen Sie den Eintrag nicht, die Anwendung setzt das Feld beim Start voraus.',
        },
        {
          kind: 'task',
          id: 'zwei-faktor-zuruecksetzen',
          title: 'Wie setze ich die Zwei-Faktor-Anmeldung einer Mitarbeiterin zurück?',
          intro: 'Das geht ohne Kommandozeile: Hat eine Person ihr Handy verloren, setzen Sie die Zwei-Faktor-Anmeldung in der [[Benutzerverwaltung]] zurück.',
          steps: [
            { n: 1, text: 'Klicken Sie in der Zeile der Person auf das Schild-Symbol [[Zwei-Faktor zurücksetzen]]. Es erscheint nur bei Personen mit aktiver Zwei-Faktor-Anmeldung.' },
            { n: 2, text: 'Bestätigen Sie mit **Ihrem** Passwort.' },
            { n: 3, text: 'PraxisZeit schaltet die Zwei-Faktor-Anmeldung der Person ab und meldet sie ab. Sie meldet sich danach nur mit dem Passwort an und richtet Zwei-Faktor im Profil neu ein. Der Vorgang steht unter „Konto-Vorgänge“.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Die **eigene** Zwei-Faktor-Anmeldung setzen Sie so nicht zurück. Das geht im Profil, mit Passwort und Code; ein zweites Admin-Konto kann es für Sie übernehmen.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Vorher prüfen: Ist das Passwort wirklich falsch?** Die Anmeldung geht nur mit dem **Benutzernamen**, nicht mit der E-Mail-Adresse; Passwortmanager tragen gern die E-Mail ein. ' +
            'Nach **5 Fehlversuchen in 15 Minuten von demselben Rechner** sperrt PraxisZeit den Benutzer an diesem Rechner vorübergehend („Konto vorübergehend gesperrt“), an anderen Rechnern geht die Anmeldung weiter; erst nach **50 Fehlversuchen insgesamt** ist der Benutzer überall gesperrt, dann hilft Warten oder ein Neustart des Dienstes. ' +
            'Nach **10 falschen Zwei-Faktor-Codes in einer Stunde** ist die Anmeldung des Kontos für eine Stunde gesperrt; dann ist das Passwort bekannt geworden, ändern Sie es. ' +
            'Welcher Fall vorliegt, steht im Protokoll des Servers: AUTH login_failed user=<name> reason=bad_password heißt Passwort falsch, reason=unknown_user heißt Benutzername unbekannt **oder Konto deaktiviert**, dann hilft --reactivate.',
        },
      ],
    },
  ],
  shots,
};
