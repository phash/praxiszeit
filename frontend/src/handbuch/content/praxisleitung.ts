import type { Handbook, PrepareStep, ShotDef } from '../types';

/**
 * Handbuch für die Praxisleitung (Kapitel 1–5; Task 9b ergänzt 6–9).
 * Quelle: docs/handbuch/HANDBUCH-ADMIN.md, docs/handbuch/SCHNELLSTART.md und die
 * Seiten in frontend/src/pages/admin. Reine Daten (R5). Aufgaben-IDs sind
 * Sprungmarken der Kontexthilfe – nicht umbenennen.
 */

/** Sarahs Zeile in der Benutzerverwaltung (Arbeitszeit-Dialog, Monatsjournal). */
const SARAH_HOURS = { role: 'button', name: 'Arbeitszeit & Wochenstunden für Sarah Klein', exact: true } as const;
const PETRA_HOURS = { role: 'button', name: 'Arbeitszeit & Wochenstunden für Petra Schulz', exact: true } as const;

/** Rückwirkende Änderung für Sarah: Montag-Nachmittag endet ab Stichtag − 14 Tage um 15:30. Nur Vorschau, nie speichern. */
const RETRO_PREPARE: PrepareStep[] = [
  { click: SARAH_HOURS },
  { waitFor: { label: 'Mo Block 2 bis', within: 'dialog' } },
  { fill: { label: 'Gültig ab', within: 'dialog' }, value: '{{stichtag-14d}}' },
  { fill: { label: 'Mo Block 2 bis', within: 'dialog' }, value: '15:30' },
  // erst die Vorschau abwarten, sonst setzt ihre Antwort die Wahl zurück; das Label selbst nimmt den Klick nicht an
  { waitFor: { css: "[role='dialog'] >> text=/verlieren angerechnete Zeit/" } },
  { click: { css: "[role='dialog'] label:has-text('mit Neuberechnung') input" } },
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
            { n: 3, text: '**Tabelle:** Soll im Zeitraum, angerechnete Zeit, Überstunden und Urlaub – jeweils bisher, neu und Differenz.' },
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
  ],
  shots,
};
