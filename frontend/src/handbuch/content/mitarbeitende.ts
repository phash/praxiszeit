import type { Handbook, ShotDef } from '../types';

/**
 * Handbuch für Mitarbeitende (Kapitel 1–9).
 * Quelle: docs/handbuch/HANDBUCH-MITARBEITER.md und die Seiten in frontend/src/pages.
 * Reine Daten (R5). Aufgaben-IDs sind Sprungmarken der Kontexthilfe – nicht umbenennen.
 */

const shots: ShotDef[] = [
  // ── 1. Anmelden ──────────────────────────────────────────────────────────
  {
    id: 'ma-anmelden',
    persona: 'anon',
    viewport: 'desktop',
    route: '/login',
    prepare: [
      { fill: { role: 'textbox', name: 'Benutzername' }, value: 'maria' },
      { fill: { role: 'textbox', name: 'Passwort', exact: true }, value: 'Handbuch2026!' },
    ],
    crop: { around: ['benutzername', 'anmelden'], pad: 150 },
    markers: [
      { n: 1, id: 'benutzername', locator: { role: 'textbox', name: 'Benutzername' } },
      { n: 2, id: 'passwort', locator: { role: 'textbox', name: 'Passwort', exact: true } },
      { n: 3, id: 'anmelden', locator: { role: 'button', name: 'Anmelden', exact: true } },
    ],
    alt: 'Anmeldeseite von PraxisZeit mit ausgefülltem Benutzernamen, verdecktem Passwort und dem Knopf „Anmelden“',
  },
  {
    id: 'ma-navigation',
    persona: 'maria',
    viewport: 'desktop',
    route: '/',
    crop: { around: ['dashboard', 'profil'], pad: 24 },
    markers: [
      { n: 1, id: 'dashboard', locator: { role: 'link', name: 'Dashboard', exact: true, within: 'nav' }, badge: 'right' },
      { n: 2, id: 'zeiterfassung', locator: { role: 'link', name: 'Zeiterfassung', exact: true, within: 'nav' }, badge: 'right' },
      { n: 3, id: 'abwesenheiten', locator: { role: 'link', name: 'Abwesenheiten', exact: true, within: 'nav' }, badge: 'right' },
      { n: 4, id: 'profil', locator: { role: 'link', name: 'Profil', exact: true, within: 'nav' }, badge: 'right' },
    ],
    alt: 'Linke Seitenleiste mit den vier Bereichen Dashboard, Zeiterfassung, Abwesenheiten und Profil',
  },

  // ── 2. Dashboard ─────────────────────────────────────────────────────────
  {
    id: 'ma-dashboard',
    persona: 'maria',
    viewport: 'desktop',
    route: '/',
    crop: 'main',
    markers: [
      { n: 1, id: 'stempelkarte', locator: { css: 'main >> text=Eingestempelt seit >> visible=true' }, badge: 'top' },
      { n: 2, id: 'monatssaldo', locator: { role: 'heading', name: 'Monatssaldo', exact: true }, badge: 'top' },
      { n: 3, id: 'ueberstunden', locator: { role: 'heading', name: 'Überstundenkonto', exact: true }, badge: 'top' },
      { n: 4, id: 'urlaubskonto', locator: { role: 'heading', name: 'Urlaubskonto', exact: true }, badge: 'top' },
      { n: 5, id: 'countdown', locator: { role: 'heading', name: 'Urlaubscountdown', exact: true }, badge: 'top' },
    ],
    alt: 'Dashboard mit Stempelkarte „Eingestempelt seit 07:45“ und den Kacheln Monatssaldo, Überstundenkonto, Urlaubskonto und Urlaubscountdown',
  },
  {
    id: 'ma-wochenuebersicht',
    persona: 'maria',
    viewport: 'desktop',
    route: '/',
    prepare: [
      { click: { role: 'button', name: 'Woche', exact: true, within: 'main' } },
      { waitFor: { role: 'columnheader', name: 'Woche', exact: true } },
      { scrollTo: { role: 'button', name: 'Details anzeigen (Jahresübersicht & Team-Kalender)', exact: true } },
    ],
    crop: 'main',
    markers: [
      { n: 1, id: 'umschalter', locator: { role: 'group', name: 'Zeitraum-Ansicht', exact: true } },
      { n: 2, id: 'saldo', locator: { role: 'columnheader', name: 'Saldo', exact: true } },
      { n: 3, id: 'kumuliert', locator: { role: 'columnheader', name: 'Überstunden kum.' } },
    ],
    alt: 'Wochenübersicht auf dem Dashboard: die letzten acht Kalenderwochen mit Soll, Ist, Saldo und kumuliertem Überstundenkonto',
  },
  {
    id: 'ma-jahresuebersicht',
    persona: 'maria',
    viewport: 'desktop',
    route: '/',
    prepare: [
      { click: { role: 'button', name: 'Details anzeigen (Jahresübersicht & Team-Kalender)', exact: true } },
      { waitFor: { role: 'heading', name: 'Geplante Abwesenheiten im Team', exact: true } },
      { scrollTo: { role: 'heading', name: 'Geplante Abwesenheiten im Team', exact: true } },
    ],
    crop: 'main',
    markers: [
      { n: 1, id: 'stunden', locator: { role: 'heading', name: 'Stunden 01.01. bis heute', exact: true } },
      {
        n: 2,
        id: 'abwesenheiten',
        // die Zahlenreihe unter der Überschrift (Kreis darüber, ohne die Überschrift zu verdecken)
        locator: { css: "xpath=//main//h3[normalize-space()='Abwesenheiten']/following-sibling::div[1]" },
        badge: 'top',
      },
      { n: 3, id: 'team', locator: { role: 'heading', name: 'Geplante Abwesenheiten im Team', exact: true }, badge: 'top' },
    ],
    alt: 'Aufgeklappte Jahresübersicht mit Stunden seit dem 1. Januar, Abwesenheitstagen nach Art und den geplanten Abwesenheiten im Team',
  },

  // ── 3. Zeiterfassung ─────────────────────────────────────────────────────
  {
    id: 'ma-einstempeln',
    persona: 'thomas',
    viewport: 'desktop',
    route: '/',
    crop: { around: ['status', 'einstempeln'], pad: 46 },
    markers: [
      { n: 1, id: 'status', locator: { css: 'main >> text=Nicht eingestempelt >> visible=true' }, badge: 'top' },
      { n: 2, id: 'einstempeln', locator: { role: 'button', name: 'Einstempeln', exact: true, within: 'main' }, badge: 'corner' },
    ],
    alt: 'Stempelkarte auf dem Dashboard mit dem Hinweis „Nicht eingestempelt“ und dem grünen Knopf „Einstempeln“',
  },
  {
    id: 'ma-ausstempeln',
    persona: 'maria',
    viewport: 'desktop',
    route: '/',
    prepare: [
      { click: { role: 'button', name: 'Ausstempeln', exact: true, within: 'main' } },
      { fill: { label: 'Pause (Min.)', within: 'main' }, value: '30' },
    ],
    crop: { around: ['pause', 'jetzt'], pad: 100 },
    markers: [
      { n: 1, id: 'pause', locator: { label: 'Pause (Min.)', within: 'main' }, badge: 'top' },
      { n: 2, id: 'jetzt', locator: { role: 'button', name: 'Jetzt ausstempeln', exact: true, within: 'main' }, badge: 'top' },
      { n: 3, id: 'abbrechen', locator: { role: 'button', name: 'Abbrechen', exact: true, within: 'main' }, badge: 'top' },
    ],
    alt: 'Stempelkarte beim Ausstempeln: Feld „Pause (Min.)“ mit 30 Minuten, daneben „Abbrechen“ und „Jetzt ausstempeln“',
  },
  {
    id: 'ma-eintraege',
    persona: 'maria',
    viewport: 'desktop',
    route: '/time-tracking',
    crop: 'main',
    markers: [
      { n: 1, id: 'tab', locator: { role: 'button', name: 'Einträge', exact: true, within: 'main' }, badge: 'right' },
      { n: 2, id: 'monat', locator: { role: 'button', name: 'Vorheriger Monat', exact: true, within: 'main' }, badge: 'top' },
      { n: 3, id: 'netto', locator: { role: 'columnheader', name: 'Netto', exact: true }, badge: 'top' },
      { n: 4, id: 'aktionen', locator: { role: 'columnheader', name: 'Aktionen', exact: true }, badge: 'top' },
    ],
    alt: 'Zeiterfassung, Tab Einträge: Monatsliste mit Datum, Von, Bis, Pause, Netto und Aktionen, oben der laufende Eintrag von heute',
  },
  {
    id: 'ma-neuer-eintrag',
    persona: 'maria',
    viewport: 'desktop',
    route: '/time-tracking',
    prepare: [{ click: { role: 'button', name: 'Neuer Eintrag', exact: true, within: 'main' } }],
    crop: 'dialog',
    markers: [
      { n: 1, id: 'von', locator: { label: 'Von', within: 'dialog' }, badge: 'top' },
      { n: 2, id: 'bis', locator: { label: 'Bis', within: 'dialog' }, badge: 'top' },
      { n: 3, id: 'speichern', locator: { role: 'button', name: 'Speichern', exact: true, within: 'dialog' }, badge: 'top' },
    ],
    alt: 'Formular „Neuer Zeiteintrag“ mit den Feldern Datum, Von, Bis, Pause (Min.) und Notiz sowie dem Knopf „Speichern“',
  },
  {
    id: 'ma-vergangener-tag',
    persona: 'thomas',
    viewport: 'desktop',
    route: '/time-tracking',
    prepare: [
      { click: { role: 'button', name: 'Antrag', exact: true, within: 'main' } },
      // Seed: an diesem Werktag hat Thomas keinen Eintrag (THOMAS_FORGOTTEN_WORKDAY, R19)
      { fill: { label: 'Datum', within: 'dialog' }, value: '{{werktag-4}}' },
      { fill: { label: 'Bis', within: 'dialog' }, value: '16:30' },
      { fill: { label: 'Pause (Min.)', within: 'dialog' }, value: '30' },
      { fill: { label: 'Begründung', within: 'dialog' }, value: 'Einstempeln vergessen – ich war von 8:00 bis 16:30 Uhr in der Praxis.' },
    ],
    crop: 'dialog',
    markers: [
      { n: 1, id: 'datum', locator: { label: 'Datum', within: 'dialog' }, badge: 'top' },
      { n: 2, id: 'von', locator: { label: 'Von', within: 'dialog' }, badge: 'top' },
      { n: 3, id: 'begruendung', locator: { label: 'Begründung', within: 'dialog' }, badge: 'top' },
      { n: 4, id: 'senden', locator: { role: 'button', name: 'Antrag stellen', exact: true, within: 'dialog' }, badge: 'top' },
    ],
    alt: 'Dialog „Änderungsantrag: Neuer Eintrag (vergangener Tag)“ mit Datum, Von, Bis, Pause, Notiz und ausgefüllter Begründung',
  },
  {
    id: 'ma-nicht-angerechnet',
    persona: 'sarah',
    viewport: 'desktop',
    route: '/time-tracking',
    crop: { around: ['zeile'], pad: 32 },
    markers: [
      // Neuester durchgestempelter Tag (die Liste steht absteigend nach Datum): die ganze Tabellenzeile
      { n: 1, id: 'zeile', locator: { css: 'main >> tr:has-text("zwischen den Blöcken nicht angerechnet") >> nth=0' }, badge: 'corner' },
    ],
    alt: 'Zeiteintrag mit Zusatzzeile „gestempelt 08:00–16:00 · angerechnet 5:30 h“ und dem Link „Anrechnung beantragen“',
  },
  {
    id: 'ma-journal',
    persona: 'maria',
    viewport: 'desktop',
    route: '/time-tracking',
    prepare: [
      { click: { role: 'button', name: 'Journal', exact: true, within: 'main' } },
      { waitFor: { role: 'heading', name: 'Mein Journal', exact: true } },
    ],
    crop: 'main',
    markers: [
      { n: 1, id: 'tab', locator: { role: 'button', name: 'Journal', exact: true, within: 'main' }, badge: 'top' },
      { n: 2, id: 'saldo', locator: { role: 'columnheader', name: 'Saldo', exact: true }, badge: 'top' },
    ],
    alt: 'Journal in der Zeiterfassung: jeder Tag des Monats mit Art, Von–Bis, Pause, Ist, Soll und Saldo, Urlaubstage blau',
  },

  // ── 4. Abwesenheiten ─────────────────────────────────────────────────────
  {
    id: 'ma-kalender',
    persona: 'maria',
    viewport: 'desktop',
    route: '/absences',
    crop: 'main',
    markers: [
      // Monat/Jahr ohne Nummer: jede Kreislage verdeckt dort „Kalender“, die Überschrift oder den Pfeil (R20-Rahmen)
      { n: 1, id: 'monat', locator: { role: 'button', name: 'Nächster Monat', exact: true, within: 'main' }, badge: 'right' },
    ],
    alt: 'Abwesenheitskalender des Teams im Monat: farbige Kreise mit Kürzeln, Feiertag und ein verkürzter Tag sind beschriftet',
  },
  {
    id: 'ma-abwesenheit-eintragen',
    persona: 'maria',
    viewport: 'desktop',
    route: '/absences',
    prepare: [{ click: { role: 'button', name: 'Abwesenheit eintragen', exact: true, within: 'main' } }],
    crop: { around: ['zeitraum', 'speichern'], pad: 72 },
    markers: [
      { n: 1, id: 'zeitraum', locator: { css: 'main >> label:has-text("Zeitraum (mehrere Tage)") >> xpath=..' }, badge: 'top' },
      { n: 2, id: 'datum', locator: { css: 'main form input[type="date"]' } },
      { n: 3, id: 'typ', locator: { css: 'main form select' }, badge: 'top' },
      { n: 4, id: 'speichern', locator: { role: 'button', name: 'Speichern', exact: true, within: 'main' }, badge: 'top' },
    ],
    alt: 'Formular „Abwesenheit eintragen“ mit Zeitraum, Halber Tag, Datum, Typ Urlaub, ausgegrautem Stundenfeld mit Hinweis zum Tagessoll und dem Knopf „Speichern“',
  },
  {
    id: 'ma-halber-tag',
    persona: 'maria',
    viewport: 'desktop',
    route: '/absences',
    prepare: [
      { click: { role: 'button', name: 'Abwesenheit eintragen', exact: true, within: 'main' } },
      { click: { label: 'Halber Tag (zählt als 0,5 Tag)', within: 'main' } },
    ],
    crop: { around: ['halbtag', 'stunden'], pad: 72 },
    markers: [
      { n: 1, id: 'halbtag', locator: { css: 'main >> label:has-text("Halber Tag (zählt als 0,5 Tag)") >> xpath=..' }, badge: 'top' },
      { n: 2, id: 'stunden', locator: { css: 'main form input[type="number"]' }, badge: 'top' },
      { n: 3, id: 'speichern', locator: { role: 'button', name: 'Speichern', exact: true, within: 'main' }, badge: 'top' },
    ],
    alt: 'Formular „Abwesenheit eintragen“ mit Haken bei „Halber Tag (zählt als 0,5 Tag)“ und ausgegrautem Stundenfeld mit dem Hinweis zum halben Tagessoll',
  },
  {
    id: 'ma-loeschung-beantragen',
    persona: 'maria',
    viewport: 'desktop',
    route: '/absences',
    prepare: [{ scrollTo: { css: "main button:has-text('Löschung beantragen') >> visible=true >> nth=0" } }],
    crop: { around: ['knopf'], pad: 520 },
    markers: [
      { n: 1, id: 'knopf', locator: { css: "main button:has-text('Löschung beantragen') >> visible=true >> nth=0" }, badge: 'left' },
    ],
    alt: 'Liste „Meine Abwesenheiten“: an vergangenen Urlaubstagen der Knopf „Löschung beantragen“, an den künftigen Betriebsferien-Tagen kein Knopf',
  },
  {
    id: 'ma-meine-antraege',
    persona: 'maria',
    viewport: 'desktop',
    route: '/absences',
    prepare: [
      { click: { role: 'button', name: 'Meine Anträge', exact: true, within: 'main' } },
      { waitFor: { text: 'Kurzurlaub', within: 'main' } },
    ],
    crop: { around: ['tab', 'karte'], pad: 24 },
    markers: [
      { n: 1, id: 'tab', locator: { role: 'button', name: 'Meine Anträge', exact: true, within: 'main' }, badge: 'right' },
      {
        n: 2,
        id: 'karte',
        locator: { css: "xpath=//main//div[contains(@class,'rounded-xl') and contains(@class,'p-5')][.//text()[contains(.,'Kurzurlaub')]]" },
        badge: 'top',
      },
      { n: 3, id: 'tage', locator: { text: '3 Tage', within: 'main' }, badge: 'right' },
    ],
    alt: 'Tab „Meine Anträge“ mit einem genehmigten Urlaubsantrag über drei Tage und dem Datum, an dem er gestellt wurde',
  },
  // ── 5. Anträge ───────────────────────────────────────────────────────────
  {
    id: 'ma-antrag-knoepfe',
    persona: 'maria',
    viewport: 'desktop',
    route: '/time-tracking',
    // Ausschnitt um die Aktionen-Spalte: die kleinen Symbole bleiben groß genug zum Erkennen
    crop: { around: ['aendern', 'loeschen'], pad: 120 },
    markers: [
      // Neuester gesperrter Eintrag (Liste absteigend; der heutige oben hat Stift und Papierkorb)
      { n: 1, id: 'aendern', locator: { css: 'main >> button[aria-label^="Änderungsantrag für"] >> nth=0' }, badge: 'top' },
      { n: 2, id: 'loeschen', locator: { css: 'main >> button[aria-label^="Löschantrag für"] >> nth=0' }, badge: 'right' },
    ],
    alt: 'Zeile eines gesperrten Zeiteintrags mit Schloss und den Knöpfen für Änderungsantrag und Löschantrag in der Spalte Aktionen',
  },
  {
    id: 'ma-antrag-aendern',
    persona: 'maria',
    viewport: 'desktop',
    route: '/time-tracking',
    prepare: [
      { click: { css: 'main >> button[aria-label^="Änderungsantrag für"] >> nth=0' } },
      { fill: { label: 'Von', within: 'dialog' }, value: '08:30' },
      { fill: { label: 'Begründung', within: 'dialog' }, value: 'Einstempeln vergessen – ich war ab 8:30 Uhr in der Praxis.' },
    ],
    crop: 'dialog',
    markers: [
      { n: 1, id: 'aktuell', locator: { role: 'heading', name: 'Aktuelle Werte', exact: true }, badge: 'top' },
      { n: 2, id: 'von', locator: { label: 'Von', within: 'dialog' }, badge: 'top' },
      { n: 3, id: 'begruendung', locator: { label: 'Begründung', within: 'dialog' }, badge: 'top' },
      { n: 4, id: 'senden', locator: { role: 'button', name: 'Antrag stellen', exact: true, within: 'dialog' }, badge: 'top' },
    ],
    alt: 'Dialog „Änderungsantrag: Eintrag ändern“: oben die aktuellen Werte des Eintrags, darunter die neuen Werte und die ausgefüllte Begründung',
  },
  {
    id: 'ma-antrag-loeschen',
    persona: 'maria',
    viewport: 'desktop',
    route: '/time-tracking',
    prepare: [
      { click: { css: 'main >> button[aria-label^="Löschantrag für"] >> nth=0' } },
      { fill: { label: 'Begründung', within: 'dialog' }, value: 'Eintrag versehentlich doppelt angelegt.' },
    ],
    crop: 'dialog',
    markers: [
      { n: 1, id: 'eintrag', locator: { role: 'heading', name: 'Eintrag zum Löschen', exact: true }, badge: 'top' },
      { n: 2, id: 'begruendung', locator: { label: 'Begründung', within: 'dialog' }, badge: 'top' },
      { n: 3, id: 'senden', locator: { role: 'button', name: 'Antrag stellen', exact: true, within: 'dialog' }, badge: 'top' },
    ],
    alt: 'Dialog „Änderungsantrag: Eintrag löschen“ mit dem Eintrag, der gelöscht werden soll, und einer ausgefüllten Begründung',
  },
  {
    id: 'ma-antraege-status',
    persona: 'maria',
    viewport: 'desktop',
    route: '/time-tracking?tab=requests',
    prepare: [{ waitFor: { role: 'button', name: 'Zurückziehen', exact: true, within: 'main' } }],
    crop: { around: ['tab', 'karte'], pad: 24 },
    markers: [
      { n: 1, id: 'tab', locator: { role: 'button', name: 'Anträge', exact: true, within: 'main' }, badge: 'top' },
      // Kreis über der Kartenmitte: dort ist rechts neben den Filterknöpfen Platz
      { n: 2, id: 'karte', locator: { css: "xpath=//main//div[contains(@class,'rounded-xl') and contains(@class,'p-6')][.//button[normalize-space()='Zurückziehen']]" }, badge: 'top' },
      { n: 3, id: 'zurueckziehen', locator: { role: 'button', name: 'Zurückziehen', exact: true, within: 'main' }, badge: 'top' },
    ],
    alt: 'Tab „Anträge“ in der Zeiterfassung: offener Änderungsantrag mit aktuellen und gewünschten Werten, Begründung und dem Knopf „Zurückziehen“',
  },
  {
    id: 'ma-antrag-abgelehnt',
    persona: 'thomas',
    viewport: 'desktop',
    route: '/time-tracking?tab=requests',
    prepare: [
      { click: { role: 'button', name: 'Abgelehnt', exact: true, within: 'main' } },
      { waitFor: { text: 'Ablehnungsgrund:', within: 'main' } },
    ],
    // pad 80: der Kreis links neben dem Rahmen des Ablehnungsgrunds (R20) passt ganz hinein (verdeckt sonst „Begründung“)
    crop: { around: ['filter', 'grund'], pad: 80 },
    markers: [
      // Filterknopf „Abgelehnt“ (rechts daneben ist frei); das Kennzeichen „Abgelehnt“ steht dann an jeder Karte
      { n: 1, id: 'filter', locator: { role: 'button', name: 'Abgelehnt', exact: true, within: 'main' }, badge: 'right' },
      { n: 2, id: 'grund', locator: { css: "xpath=//main//div[contains(@class,'bg-red-50')][.//text()[contains(.,'Ablehnungsgrund')]]" }, badge: 'left' },
    ],
    alt: 'Filter „Abgelehnt“ mit einem abgelehnten Änderungsantrag, rotem Kasten „Ablehnungsgrund“ und dem Vermerk, wer ihn wann bearbeitet hat',
  },

  // ── 6. Auf dem Handy ─────────────────────────────────────────────────────
  {
    id: 'ma-handy-start',
    persona: 'maria',
    viewport: 'mobile',
    route: '/',
    crop: 'full',
    markers: [
      { n: 1, id: 'menue', locator: { role: 'button', name: 'Menü öffnen', exact: true }, badge: 'left' },
      { n: 2, id: 'stempel', locator: { role: 'button', name: 'Eingestempelt – Stempeluhr öffnen', exact: true }, badge: 'top' },
      // Die ganze Leiste ist in der Mitte vom Stempel-Knopf verdeckt — Marker auf den ersten Eintrag „Home“.
      // Ecke: am linken Bildrand liegt kein Text der Seite dahinter (über der Mitte stünde „Monatssaldo“).
      { n: 3, id: 'leiste', locator: { role: 'link', name: 'Home', exact: true, within: 'nav' }, badge: 'corner' },
    ],
    alt: 'PraxisZeit auf dem Smartphone: oben das Menü, unten die Leiste mit Home, Journal, Abwes. und Profil, in der Mitte der runde Stempel-Knopf',
  },
  {
    id: 'ma-handy-stempeluhr',
    persona: 'maria',
    viewport: 'mobile',
    route: '/',
    prepare: [
      { click: { role: 'button', name: 'Eingestempelt – Stempeluhr öffnen', exact: true } },
      { waitFor: { text: 'Arbeitszeit heute', within: 'dialog' } },
    ],
    crop: 'full',
    markers: [
      { n: 1, id: 'uhr', locator: { text: 'Arbeitszeit heute', within: 'dialog' }, badge: 'left' },
      { n: 2, id: 'ausstempeln', locator: { role: 'button', name: 'Ausstempeln', exact: true, within: 'dialog' }, badge: 'top' },
    ],
    alt: 'Geöffnete Stempeluhr auf dem Smartphone mit laufender Arbeitszeit, Start 07:45, Pause und dem roten Knopf „Ausstempeln“',
  },
  {
    id: 'ma-handy-zeiterfassung',
    persona: 'maria',
    viewport: 'mobile',
    route: '/time-tracking',
    crop: 'full',
    markers: [
      { n: 1, id: 'antrag', locator: { role: 'button', name: 'Antrag', exact: true, within: 'main' }, badge: 'left' },
      { n: 2, id: 'neu', locator: { css: 'main >> button:has(svg.lucide-plus)' }, badge: 'top' },
      { n: 3, id: 'aendern', locator: { css: 'main >> button:has-text("Ändern") >> visible=true >> nth=0' }, badge: 'top' },
    ],
    alt: 'Zeiterfassung auf dem Smartphone: oben die Knöpfe Antrag und Plus, darunter die Einträge als Karten mit Ändern und Löschen',
  },

  // ── 7. Profil ────────────────────────────────────────────────────────────
  {
    id: 'ma-profil',
    persona: 'maria',
    viewport: 'desktop',
    route: '/profile',
    crop: 'main',
    markers: [
      { n: 1, id: 'bearbeiten', locator: { role: 'button', name: 'Bearbeiten', exact: true, within: 'main' }, badge: 'top' },
      { n: 2, id: 'passwort', locator: { role: 'button', name: 'Ändern', exact: true, within: 'main' }, badge: 'top' },
      { n: 3, id: 'arbeitszeit', locator: { role: 'heading', name: 'Meine Arbeitszeit', exact: true }, badge: 'top' },
      { n: 4, id: 'weitere', locator: { role: 'button', name: 'Weitere Einstellungen', exact: true, within: 'main' }, badge: 'top' },
    ],
    alt: 'Profilseite mit persönlichen Daten, der Karte „Passwort ändern“, „Meine Arbeitszeit“ und dem Bereich „Weitere Einstellungen“',
  },
  {
    id: 'ma-meine-arbeitszeit',
    persona: 'sarah',
    viewport: 'desktop',
    route: '/profile',
    prepare: [{ scrollTo: { role: 'heading', name: 'Meine Arbeitszeit', exact: true } }],
    crop: { around: ['karte'], pad: 16 },
    markers: [
      // Ecke: der Kreis liegt auf dem Uhr-Symbol, nicht auf der Überschrift
      { n: 1, id: 'karte', locator: { css: "xpath=//main//h2[normalize-space()='Meine Arbeitszeit']/ancestor::div[contains(@class,'rounded-xl')][1]" }, badge: 'corner' },
      // Kreise über der Listenmitte: Überschrift und „Wochenstunden“ stehen links
      { n: 2, id: 'heute', locator: { role: 'list', name: 'Arbeitszeit heute', exact: true }, badge: 'top' },
      { n: 3, id: 'verlauf', locator: { role: 'list', name: 'Verlauf der Arbeitszeit', exact: true }, badge: 'top' },
    ],
    alt: 'Karte „Meine Arbeitszeit“: Arbeitszeit-Blöcke je Wochentag mit Tagessoll, Wochenstunden und darunter der Verlauf der Änderungen',
  },
  {
    id: 'ma-passwort-aendern',
    persona: 'maria',
    viewport: 'desktop',
    route: '/profile',
    prepare: [{ click: { role: 'button', name: 'Ändern', exact: true, within: 'main' } }],
    crop: 'main',
    markers: [
      // Die Beschriftungen stehen links über den Feldern; Kreise über der Feldmitte verdecken sie nicht.
      { n: 1, id: 'aktuell', locator: { css: 'main >> input[type="password"] >> nth=0' }, badge: 'top' },
      { n: 2, id: 'neu', locator: { css: 'main >> input[type="password"] >> nth=1' }, badge: 'top' },
      { n: 3, id: 'bestaetigen', locator: { css: 'main >> input[type="password"] >> nth=2' }, badge: 'top' },
    ],
    alt: 'Karte „Passwort ändern“ mit den Feldern Aktuelles Passwort, Neues Passwort und Passwort bestätigen sowie dem Knopf „Speichern“',
  },
  {
    id: 'ma-2fa-einrichten',
    persona: 'maria',
    viewport: 'desktop',
    route: '/profile',
    prepare: [
      // „Weitere Einstellungen“ ist beim Öffnen der Seite schon aufgeklappt
      { click: { role: 'button', name: '2FA aktivieren', exact: true, within: 'main' } },
      { fill: { css: 'main input[placeholder="Ihr aktuelles Passwort"]' }, value: 'Handbuch2026!' },
      { click: { role: 'button', name: 'Weiter', exact: true, within: 'main' } },
      { waitFor: { text: 'Schritt 1: Scannen Sie den QR-Code mit Ihrer Authenticator-App', within: 'main' } },
      // Knöpfe in die Fenstermitte holen: dann stehen QR-Code bis Knöpfe ganz im Fenster
      { scrollTo: { role: 'button', name: 'Bestätigen & 2FA aktivieren', exact: true, within: 'main' } },
    ],
    crop: { around: ['qr', 'code'], pad: 56 },
    markers: [
      { n: 1, id: 'qr', locator: { css: 'main >> svg:has(path) >> xpath=ancestor::div[contains(@class,"bg-white") and contains(@class,"p-3")][1]' }, badge: 'left' },
      // über der Feldmitte: „Schritt 2: …“ steht links
      { n: 2, id: 'code', locator: { css: 'main input[placeholder="000000"]' }, badge: 'top' },
    ],
    alt: 'Einrichtung der Zwei-Faktor-Authentifizierung: QR-Code für die Authenticator-App, Schlüssel zum Abtippen und Feld für den 6-stelligen Code',
  },

  // ── 8. Schichtplan ───────────────────────────────────────────────────────
  {
    id: 'ma-schichtplan',
    persona: 'maria',
    viewport: 'desktop',
    route: '/shift-planning',
    settings: { shift_planning_enabled: true },
    prepare: [{ waitFor: { text: '» Telefondienst bis 9:00', within: 'main' } }],
    // Nur der Hauptbereich: mit Seitenleiste wäre die Schrift im Raster zu klein (Menüpunkt steht im Intro).
    crop: 'main',
    markers: [
      { n: 1, id: 'plan', locator: { role: 'heading', name: 'Wochenplan Praxis', exact: true }, badge: 'right' },
      { n: 2, id: 'pdf', locator: { role: 'button', name: 'PDF', exact: true, within: 'main' }, badge: 'left' },
    ],
    alt: 'Seite Schichtplan: Plan „Wochenplan Praxis“ mit Wochenraster Montag bis Freitag mit den Arbeitsplätzen Anmeldung und Labor und den eingeteilten Personen',
  },
  {
    id: 'ma-einteilung-heute',
    persona: 'maria',
    viewport: 'desktop',
    route: '/',
    settings: { shift_planning_enabled: true },
    prepare: [{ waitFor: { role: 'heading', name: 'Deine Einteilung heute', exact: true } }],
    crop: { around: ['karte'], pad: 24 },
    markers: [
      { n: 1, id: 'karte', locator: { css: "xpath=//main//h3[normalize-space()='Deine Einteilung heute']/ancestor::div[contains(@class,'rounded-2xl')][1]" }, badge: 'corner' },
    ],
    alt: 'Dashboard-Karte „Deine Einteilung heute“ mit Arbeitsplatz, Uhrzeit, Planname und dem Hinweis zur Einteilung',
  },
];

export const mitarbeitende: Handbook = {
  id: 'mitarbeitende',
  title: 'Handbuch für Mitarbeitende',
  lead:
    'So erfassen Sie Ihre Arbeitszeit, behalten Saldo und Urlaub im Blick und tragen Abwesenheiten ein. ' +
    'Jede Aufgabe beginnt mit einer Frage – suchen Sie sich die passende heraus.',
  chapters: [
    // ── 1 ───────────────────────────────────────────────────────────────────
    {
      id: 'anmelden-und-erster-start',
      title: 'Anmelden & erster Start',
      blocks: [
        {
          kind: 'comic',
          scene: 'hero',
          text:
            'PraxisZeit läuft im Browser – am Praxis-PC, am Tablet oder auf dem Smartphone. ' +
            'Sie brauchen nur Ihren **Benutzernamen** und Ihr **Passwort** von Ihrer Verwaltung.',
        },
        {
          kind: 'task',
          id: 'anmelden-mit-passwort',
          title: 'Wie melde ich mich an?',
          intro: 'Öffnen Sie PraxisZeit im Browser unter der Adresse, die Ihnen Ihre Verwaltung genannt hat.',
          shot: 'ma-anmelden',
          steps: [
            { n: 1, text: 'Geben Sie Ihren **Benutzernamen** ein.' },
            { n: 2, text: 'Geben Sie Ihr **Passwort** ein. Das Auge rechts im Feld zeigt es zur Kontrolle an.' },
            { n: 3, text: 'Klicken Sie auf [[Anmelden]]. Sie landen auf dem Dashboard.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Passwort vergessen?** Wenden Sie sich an Ihre Verwaltung. ' +
            'Achten Sie beim Eintippen auf Groß- und Kleinschreibung und die Feststelltaste.',
        },
        {
          kind: 'task',
          id: 'anmelden-mit-2fa',
          title: 'Wie melde ich mich mit Zwei-Faktor-Code an?',
          intro:
            'Nur wenn Sie die Zwei-Faktor-Authentifizierung (2FA) in Ihrem Profil eingeschaltet haben. ' +
            'Dann brauchen Sie zusätzlich den wechselnden 6-stelligen Code aus Ihrer Authenticator-App.',
          steps: [
            { n: 1, text: 'Geben Sie wie gewohnt Benutzername und Passwort ein und klicken Sie auf [[Anmelden]].' },
            { n: 2, text: 'Es erscheint das Feld [[2FA-Code (Authenticator-App)]]. Öffnen Sie Ihre Authenticator-App und tippen Sie den 6-stelligen Code ab.' },
            { n: 3, text: 'Klicken Sie erneut auf [[Anmelden]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Handy verloren?** Die Verwaltung setzt Ihre 2FA zurück. Danach melden Sie sich nur mit dem Passwort an ' +
            'und richten 2FA im Profil neu ein.',
        },
        {
          kind: 'task',
          id: 'erster-start',
          title: 'Was erscheint beim ersten Anmelden?',
          intro: 'Beim allerersten Anmelden begrüßt Sie PraxisZeit in der Regel mit einem kurzen Überblick – sofern Ihre Praxis das eingeschaltet hat.',
          steps: [
            { n: 1, text: 'Das Fenster [[Willkommen bei PraxisZeit]] zeigt, was Sie in Zeiterfassung, Abwesenheiten, Änderungsanträgen und Profil tun können.' },
            { n: 2, text: 'Klicken Sie auf [[Los geht\'s]]. Das Fenster erscheint danach nicht wieder.' },
          ],
        },
        {
          kind: 'task',
          id: 'seiten-navigation',
          title: 'Wo finde ich was?',
          intro: 'Am PC steht die Navigation links. Auf dem Smartphone liegt sie unten am Bildschirmrand.',
          shot: 'ma-navigation',
          steps: [
            { n: 1, text: '[[Dashboard]]: Ihre Stempelkarte, Saldo und Urlaubskonto auf einen Blick.' },
            { n: 2, text: '[[Zeiterfassung]]: Ihre Zeiteinträge, das Journal und Ihre Anträge.' },
            { n: 3, text: '[[Abwesenheiten]]: Teamkalender, Urlaub und andere Abwesenheiten eintragen.' },
            { n: 4, text: '[[Profil]]: Ihre Daten, Ihre Arbeitszeit, Passwort und 2FA.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Unten links in der Seitenleiste: [[Hilfe]] öffnet die Hilfe zur aktuellen Seite; darüber stehen [[Mitarbeiter-Handbuch]] und [[Cheat-Sheet]]. ' +
            '[[Abmelden]] beendet Ihre Sitzung.',
        },
      ],
    },

    // ── 2 ───────────────────────────────────────────────────────────────────
    {
      id: 'dashboard-saldo-urlaub',
      title: 'Dashboard: Saldo, Urlaub, heute',
      blocks: [
        {
          kind: 'comic',
          scene: 'uebersicht',
          text:
            'Das Dashboard ist Ihre Startseite. Es zeigt, ob Sie gerade eingestempelt sind, wie Ihr Saldo steht ' +
            'und wie viele Urlaubstage Ihnen noch bleiben.',
        },
        {
          kind: 'task',
          id: 'dashboard-ueberblick',
          title: 'Was zeigt mir das Dashboard?',
          shot: 'ma-dashboard',
          steps: [
            { n: 1, text: '**Stempelkarte:** ob Sie eingestempelt sind, seit wann und wie lange Sie heute schon arbeiten.' },
            { n: 2, text: '**Monatssaldo:** Soll und Ist des laufenden Monats. Das Soll zählt nur bis zum letzten abgeschlossenen Arbeitstag – heute zählt mit, sobald Sie ausgestempelt haben.' },
            { n: 3, text: '**Überstundenkonto:** Ihr kumulierter Saldo über alle Monate.' },
            { n: 4, text: '**Urlaubskonto:** Budget, genommene und verbleibende Urlaubstage.' },
            { n: 5, text: '**Urlaubscountdown:** Tage bis zu Ihrem nächsten Urlaub oder zur nächsten Praxisschließung, an der Sie teilnehmen – das frühere Datum zählt.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Stunden stehen als Stunden:Minuten, z. B. **8:30** für 8 Stunden 30 Minuten. ' +
            'Ein Minus wie **-2:15** heißt: weniger gearbeitet als das Soll. Grün sind Plusstunden, rot Minusstunden.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Gelber Hinweis im Urlaubskonto:** Im letzten Quartal erinnert PraxisZeit an offenen Urlaub, ' +
            'sobald noch mindestens ein ganzer Urlaubstag offen ist – mit dem Datum, bis wann Sie ihn nehmen sollten.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Roter Kasten „Buchung fehlt“:** Er nennt zwei Fälle. „kein Eintrag“: An einem vergangenen Arbeitstag des laufenden Monats ' +
            'steht weder ein Zeiteintrag noch eine Abwesenheit – Feiertage und Tage ohne Tagessoll zählen nicht. Tragen Sie den Tag per Antrag nach, ' +
            'siehe [Vergangenen Tag nachtragen](#vergangenen-tag-nachtragen). „offen seit …“: Ein Eintrag eines früheren Tages hat noch kein Ende. ' +
            'Tragen Sie das Ende per [Änderungsantrag](#aenderungsantrag-stellen) nach.',
        },
        {
          kind: 'task',
          id: 'saldo-je-monat-oder-woche',
          title: 'Wie sehe ich meinen Saldo je Monat oder je Woche?',
          intro: 'Unter den Kacheln steht die Monatsübersicht, die neueste Zeile oben.',
          shot: 'ma-wochenuebersicht',
          steps: [
            { n: 1, text: 'Schalten Sie mit [[Monat]] und [[Woche]] um. Die Wochenansicht zeigt die letzten 8 Kalenderwochen; Ihre Wahl merkt sich der Browser.' },
            { n: 2, text: '**Saldo** je Zeile: Ist minus Soll. So fällt sofort auf, wenn in einer Woche etwas fehlt – etwa ein vergessener Eintrag.' },
            { n: 3, text: '**Überstunden kum.**: der Stand Ihres Überstundenkontos am Ende des Monats bzw. der Woche.' },
          ],
        },
        {
          kind: 'task',
          id: 'jahresuebersicht-team',
          title: 'Wo sehe ich mein Jahr und die Abwesenheiten im Team?',
          intro: 'Klicken Sie unter der Tabelle auf [[Details anzeigen (Jahresübersicht & Team-Kalender)]].',
          shot: 'ma-jahresuebersicht',
          steps: [
            { n: 1, text: '**Stunden 01.01. bis heute:** Soll, Ist und Überstunden seit Jahresbeginn.' },
            { n: 2, text: '**Abwesenheiten:** Ihre Tage im laufenden Jahr nach Art – Urlaub, Krank, Fortbildung, Überstundenausgleich, Sonstiges.' },
            { n: 3, text: '**Geplante Abwesenheiten im Team:** wer in den nächsten 3 Monaten fehlt.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Keine Stundenzählung für Sie?** Dann fehlen die Stempelkarte mit der Tagesanzeige („x von y h heute“), ' +
            'Monatssaldo und Überstundenkonto – das ist so eingestellt und kein Fehler. Ihr Urlaubskonto wird trotzdem geführt.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Hinweis zu Ihrer Arbeitszeit:** Ändert die Verwaltung Ihre Arbeitszeit, steht 30 Tage lang ein Kasten ' +
            'mit der Änderung auf dem Dashboard. Der Link [[Arbeitszeit im Profil ansehen]] führt zu den Details.',
        },
      ],
    },

    // ── 3 ───────────────────────────────────────────────────────────────────
    {
      id: 'zeiterfassung-stempeln-eintraege',
      title: 'Zeiterfassung: stempeln, Pause, Einträge, Journal',
      blocks: [
        {
          kind: 'comic',
          scene: 'stempeln',
          text:
            'Am einfachsten erfassen Sie Ihre Zeit live: morgens einstempeln, abends ausstempeln und die Pause eintragen. ' +
            'Jeder Stempel wird zu einem **Zeiteintrag**.',
        },
        {
          kind: 'task',
          id: 'jetzt-einstempeln',
          title: 'Wie stempele ich ein?',
          intro: 'Die Stempelkarte steht oben auf dem Dashboard.',
          shot: 'ma-einstempeln',
          steps: [
            { n: 1, text: 'Steht dort [[Nicht eingestempelt]], läuft gerade keine Uhr.' },
            { n: 2, text: 'Klicken Sie auf [[Einstempeln]]. Die Uhr läuft und zeigt Ihre heutige Arbeitszeit.' },
          ],
        },
        {
          kind: 'task',
          id: 'ausstempeln-mit-pause',
          title: 'Wie stempele ich aus und trage die Pause ein?',
          intro: 'Klicken Sie auf der Stempelkarte auf [[Ausstempeln]]. Daneben erscheint das Pausenfeld.',
          shot: 'ma-ausstempeln',
          steps: [
            { n: 1, text: 'Tragen Sie in [[Pause (Min.)]] ein, wie viele Minuten Pause Sie heute gemacht haben, z. B. 30.' },
            { n: 2, text: 'Klicken Sie auf [[Jetzt ausstempeln]].' },
            { n: 3, text: 'Verklickt? [[Abbrechen]] schließt das Pausenfeld, die Uhr läuft weiter.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Pflicht-Pause (§ 4 ArbZG):** Bei mehr als 6 Stunden am Tag mindestens 30 Minuten, bei mehr als 9 Stunden ' +
            'mindestens 45 Minuten. Es zählen alle Einträge des Tages zusammen; eine Unterbrechung gilt erst ab 15 Minuten als Pause. ' +
            'Reicht die Pause nicht, tragen Sie sie nach – oder begründen, warum sie nicht möglich war (mindestens 10 Zeichen), ' +
            'sofern Ihre Praxis diese Ausnahme erlaubt.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Vergessen auszustempeln?** PraxisZeit schließt einen offenen Eintrag eines früheren Tages automatisch. ' +
            'Die Stempelkarte bietet dann [[Arbeitsende per Antrag nachtragen]] an – tragen Sie dort Ihr tatsächliches Ende ein.',
        },
        {
          kind: 'task',
          id: 'zeiteintraege-ansehen',
          title: 'Wo sehe ich meine Zeiteinträge?',
          intro: 'Klicken Sie in der Navigation auf [[Zeiterfassung]].',
          shot: 'ma-eintraege',
          steps: [
            { n: 1, text: 'Der Tab [[Einträge]] listet alle Zeiteinträge des Monats, der neueste oben. Ein laufender Eintrag steht als **offen** da.' },
            { n: 2, text: 'Mit den Pfeilen neben dem Monatsnamen blättern Sie zwischen den Monaten.' },
            { n: 3, text: '**Netto** ist die angerechnete Arbeitszeit nach Abzug der Pause.' },
            { n: 4, text: 'Unter **Aktionen** bearbeiten (Stift) oder löschen (Papierkorb) Sie heutige Einträge selbst. Ältere Einträge sind gesperrt (Schloss); für sie stellen Sie einen Änderungs- oder Löschantrag.' },
          ],
        },
        {
          kind: 'task',
          id: 'zeiteintrag-heute',
          title: 'Wie trage ich die Zeit für heute von Hand ein?',
          intro:
            'Haben Sie heute nicht gestempelt, klicken Sie oben rechts auf [[Neuer Eintrag]]. ' +
            'Das Formular erscheint über der Liste, das **Datum** ist mit heute vorbelegt.',
          shot: 'ma-neuer-eintrag',
          steps: [
            { n: 1, text: '**Von:** Ihr Arbeitsbeginn, z. B. 08:00.' },
            { n: 2, text: '**Bis:** Ihr Arbeitsende. Es darf nicht in der Zukunft liegen – tragen Sie nur bereits geleistete Zeit ein.' },
            { text: '**Pause (Min.):** Ihre Pause in Minuten, z. B. 30. Unter **Notiz** können Sie etwas anmerken (keine Gesundheitsangaben).' },
            { n: 3, text: 'Klicken Sie auf [[Speichern]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Einträge desselben Tages dürfen sich nicht überschneiden; aneinanderstoßende Zeiten wie 08:00–12:00 und 12:00–13:00 sind erlaubt. ' +
            'Ist ein Eintrag länger als 6 Stunden und ohne Pause, schlägt das Formular eine Pause vor.',
        },
        {
          kind: 'task',
          id: 'vergangenen-tag-nachtragen',
          title: 'Ich habe vergessen zu stempeln – wie trage ich einen vergangenen Tag nach?',
          intro:
            'Vergangene Tage tragen Sie nicht selbst ein, Sie beantragen sie. ' +
            'Klicken Sie in der Zeiterfassung oben rechts auf [[Antrag]] (links neben [[Neuer Eintrag]]).',
          shot: 'ma-vergangener-tag',
          steps: [
            { n: 1, text: 'Wählen Sie das **Datum** des vergessenen Tages.' },
            { n: 2, text: 'Tragen Sie **Von**, **Bis** und **Pause (Min.)** ein.' },
            { n: 3, text: 'Schreiben Sie eine **Begründung** – sie ist Pflicht.' },
            { n: 4, text: 'Klicken Sie auf [[Antrag stellen]]. Die Verwaltung prüft den Antrag; den Stand sehen Sie unter Zeiterfassung → Tab [[Anträge]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Im **Journal** geht es auch über das **+** in der Zeile des Tages. Fehlt an einem vergangenen Werktag ein Eintrag, ' +
            'zeigt das Dashboard oben den roten Kasten „Buchung fehlt“ mit dem Tag und dem Link [[Zur Zeiterfassung →]].',
        },
        {
          kind: 'task',
          id: 'nicht-angerechnete-zeit',
          title: 'Warum wird ein Teil meiner Zeit nicht angerechnet?',
          intro:
            'Hat Ihre Praxis **Arbeitszeit-Blöcke** für Sie hinterlegt, wird nur die Zeit innerhalb der Blöcke angerechnet – ' +
            'mit einem Puffer (Standard 15 Minuten) an jedem Blockrand. Ihre Blöcke stehen im Profil unter „Meine Arbeitszeit“.',
          shot: 'ma-nicht-angerechnet',
          steps: [
            { n: 1, text: 'In der Zeile des Eintrags steht unter der Uhrzeit eine Zusatzzeile, z. B. „gestempelt 08:00–16:00 · angerechnet 5:30 h · 2:30 h zwischen den Blöcken nicht angerechnet“. Ihre gestempelte Zeit bleibt gespeichert.' },
            { text: 'Haben Sie in dieser Zeit gearbeitet, klicken Sie darunter auf [[Anrechnung beantragen]], begründen Sie kurz und senden Sie den Antrag ab. Die Verwaltung entscheidet.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Nicht angerechnet heißt nicht unbezahlt.** Ob gearbeitete Zeit vergütet wird, entscheidet nicht diese Anrechnung. ' +
            'Sprechen Sie Ihre Verwaltung an oder beantragen Sie die Anrechnung. Hat Ihre Praxis gar keine Blöcke für Sie hinterlegt, ' +
            'zählt Ihre gestempelte Zeit ganz normal.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Werktag ohne Block = freier Tag:** Sind Blöcke für Sie hinterlegt und haben Sie an einem Werktag (Mo–Fr) keinen Block, stempeln dort aber trotzdem, ' +
            'wird die Zeit gespeichert, aber mit **0 Stunden** angerechnet – auch ein vergessenes Ausstempeln. Haben Sie gearbeitet, ' +
            'beantragen Sie die Anrechnung über [[Anrechnung beantragen]]; angerechnet wird erst, wenn die Verwaltung den Antrag genehmigt und anerkennt oder den Eintrag anerkennt. ' +
            'Am Wochenende und an Feiertagen gelten keine Blöcke – dort wird die ganze Zeit angerechnet.',
        },
        {
          kind: 'task',
          id: 'journal-monat',
          title: 'Wie sehe ich meinen Monat Tag für Tag?',
          intro: 'Das Journal zeigt jeden Tag des Monats – Arbeitstage, Wochenenden, Feiertage und Abwesenheiten.',
          shot: 'ma-journal',
          steps: [
            { n: 1, text: 'Klicken Sie in der Zeiterfassung auf den Tab [[Journal]].' },
            { n: 2, text: 'Je Tag stehen Art, Von–Bis, Pause, Ist und Soll; **Saldo** ist die Differenz des Tages.' },
            { text: 'Mit den Pfeilen neben dem Monatsnamen blättern Sie zwischen den Monaten.' },
          ],
        },
      ],
    },

    // ── 4 ───────────────────────────────────────────────────────────────────
    {
      id: 'urlaub-und-abwesenheit',
      title: 'Urlaub & Abwesenheit: Kalender, Antrag, Halbtag',
      blocks: [
        {
          kind: 'comic',
          scene: 'urlaub',
          text:
            'Urlaub, Krankheit, Fortbildung: Abwesenheiten tragen Sie unter **Abwesenheiten** ein. ' +
            'Verlangt Ihre Praxis eine Genehmigung, wird aus dem Urlaub ein Antrag an die Verwaltung.',
        },
        {
          kind: 'task',
          id: 'team-abwesenheitskalender',
          title: 'Wer ist wann abwesend?',
          intro:
            'Klicken Sie in der Navigation auf [[Abwesenheiten]]. Der Tab [[Kalender]] zeigt die Abwesenheiten des ganzen Teams: ' +
            'je Person ein Kreis mit ihrem Kürzel – der Ring ist die Farbe der Person, die Mitte die Art der Abwesenheit.',
          shot: 'ma-kalender',
          steps: [
            { text: 'Mit [[Monat]] und [[Jahr]] wechseln Sie die Ansicht.' },
            { n: 1, text: 'Mit den Pfeilen neben dem Monatsnamen blättern Sie weiter. Die **Legende** unter dem Kalender erklärt die Farben.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Datenschutz:** Bei Kolleginnen und Kollegen sehen Sie nur Urlaub und Fortbildung mit ihrer Art. ' +
            'Krankheit, bezahlte Freistellung, Sonstiges und eigene Gründe der Praxis erscheinen neutral als **Abwesend**. ' +
            'Ihre eigenen Abwesenheiten sehen Sie immer mit der echten Art.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Verkürzte Tage und Sondertage:** Ein verkürzter Tag steht im Kalender z. B. als „Brückentag: verkürzter Tag (max. 4 h)“. ' +
            'An diesem Tag ist Ihr Tagessoll höchstens so hoch wie angegeben, Urlaub kostet einen halben Tag.',
        },
        {
          kind: 'task',
          id: 'abwesenheit-eintragen',
          title: 'Wie trage ich Urlaub oder eine andere Abwesenheit ein?',
          intro: 'Klicken Sie oben rechts auf [[Abwesenheit eintragen]].',
          shot: 'ma-abwesenheit-eintragen',
          steps: [
            { n: 1, text: 'Mehrere Tage? Setzen Sie den Haken bei [[Zeitraum (mehrere Tage)]]. Wochenenden, Feiertage und Ihre freien Tage werden ausgelassen.' },
            { n: 2, text: 'Wählen Sie das **Datum** – beim Zeitraum **Von** und **Bis**.' },
            { n: 3, text: 'Wählen Sie den **Typ**: Urlaub, Krank, Fortbildung (außer Haus), Überstundenausgleich, Sonstiges – oder einen eigenen Grund Ihrer Praxis.' },
            { text: 'Das Feld **Stunden** bleibt ausgegraut: Gebucht wird Ihr Tagessoll laut Vertrag („Es wird das Tagessoll laut Vertrag gebucht“). Nur beim Überstundenausgleich können Sie es ausfüllen.' },
            { n: 4, text: 'Klicken Sie auf [[Speichern]]. Urlaubstage gehen automatisch von Ihrem Budget ab – verlangt Ihre Praxis eine Genehmigung, erst nachdem die Verwaltung den Antrag genehmigt hat.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Stunden** sind bei allen Arten außer **Überstundenausgleich** gesperrt – gebucht wird Ihr Tagessoll. Beim Überstundenausgleich ' +
            'zählt der eingetragene Wert und wird von Ihrem Überstundenkonto abgezogen; haben Sie einen Tagesplan, bucht das System stattdessen das Tagessoll des Tages.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Vergangene Tage nur per Antrag:** Liegt das Datum in der Vergangenheit, ist [[Speichern]] gesperrt. ' +
            'Stellen Sie den Antrag in Zeiterfassung → [[Journal]] über das **+** in der Zeile des Tages und wählen Sie dort die Art, z. B. Krank für gestern. Das **+** steht an vergangenen Tagen ohne Eintrag und ohne Abwesenheit.',
        },
        {
          kind: 'task',
          id: 'halben-tag-urlaub',
          title: 'Wie nehme ich einen halben Tag Urlaub?',
          intro: 'Wie oben über [[Abwesenheit eintragen]] – für einen einzelnen Tag.',
          shot: 'ma-halber-tag',
          steps: [
            { n: 1, text: 'Setzen Sie den Haken bei [[Halber Tag (zählt als 0,5 Tag)]]. Er steht nur bei einem einzelnen Tag bereit, nicht bei Krank oder Überstundenausgleich.' },
            { n: 2, text: 'Das Feld **Stunden** bleibt ausgegraut („Halber Tag: 0,5 × Tagessoll wird automatisch gebucht“): Gebucht wird das halbe Tagessoll.' },
            { n: 3, text: 'Wählen Sie Datum und Typ und klicken Sie auf [[Speichern]]. Vom Urlaubskonto gehen 0,5 Tage ab.' },
          ],
        },
        {
          kind: 'task',
          id: 'urlaubsantrag-status',
          title: 'Wie stelle ich einen Urlaubsantrag, und wo sehe ich, ob er genehmigt ist?',
          intro:
            'Verlangt Ihre Praxis eine Genehmigung für Urlaub, tragen Sie ihn wie oben ein. Nach [[Speichern]] erscheint ' +
            '„Urlaubsantrag gestellt“, und die Seite wechselt zum Tab [[Meine Anträge]].',
          shot: 'ma-meine-antraege',
          steps: [
            { n: 1, text: 'Unter [[Meine Anträge]] stehen alle Ihre Urlaubsanträge.' },
            { n: 2, text: 'Jeder Antrag steht als Karte mit seinem Status – **Offen**, **Genehmigt**, **Abgelehnt** (mit Ablehnungsgrund) oder **Zurückgezogen** – und dem Datum, an dem er gestellt wurde.' },
            { n: 3, text: 'Neben dem Zeitraum steht, wie viele Tage der Antrag kostet. Es zählen nur Ihre Arbeitstage; ein halber Tag zählt 0,5.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Zurückziehen oder stornieren:** Unter [[Meine Anträge]] steht neben einem offenen Antrag das Löschen-Symbol [[Antrag zurückziehen]], ' +
            'neben einem genehmigten Urlaub, der noch nicht begonnen hat, [[Urlaub stornieren]]. Bestätigen Sie jeweils im Dialog.',
        },
        {
          kind: 'task',
          id: 'abwesenheit-loeschen',
          title: 'Wie lösche ich eine eingetragene Abwesenheit?',
          intro: 'Unter dem Kalender stehen Ihre Abwesenheiten des Jahres als Liste. Was in der Spalte **Aktionen** steht, hängt vom Tag ab.',
          shot: 'ma-loeschung-beantragen',
          steps: [
            { text: '**Heute oder später:** Klicken Sie in der Zeile auf [[Löschen]] und bestätigen Sie im Dialog.' },
            { n: 1, text: '**Vergangener Tag:** Dort steht [[Löschung beantragen]]. Es öffnet sich der Dialog „Änderungsantrag: Löschung beantragen“ mit der Abwesenheit.' },
            { text: 'Geben Sie die **Begründung** an und klicken Sie auf [[Antrag stellen]]. Erst wenn die Verwaltung genehmigt, wird die Abwesenheit gelöscht; den Stand sehen Sie unter Zeiterfassung → Tab [[Anträge]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Im **Journal** geht es genauso: Neben der Abwesenheit eines vergangenen Tages steht der Papierkorb **Löschung beantragen**.',
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Betriebsferien-Tage** ändert nur die Verwaltung – dort steht kein Knopf. Genehmigten Urlaub, der noch nicht begonnen hat, nehmen Sie mit [[Urlaub stornieren]] unter [[Meine Anträge]] zurück. ' +
            'Ebenfalls nicht selbst löschen können Sie Urlaub bei eingeschalteter Genehmigungspflicht, Abwesenheiten, die die Verwaltung für Sie eingetragen hat, und Tage eines abgeschlossenen Jahres – wenden Sie sich dann an Ihre Verwaltung.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**So zählt Urlaub:** Ein freier Arbeitstag ist genau 1 Urlaubstag – egal, wie viele Stunden Sie an dem Tag arbeiten würden. ' +
            'Eine freie Woche kostet so viele Tage, wie Sie Arbeitstage pro Woche haben. **Betriebsferien** trägt PraxisZeit automatisch für Sie ein.',
        },
      ],
    },

    // ── 5 ───────────────────────────────────────────────────────────────────
    {
      id: 'antraege-korrektur-loeschung',
      title: 'Anträge: Korrektur, Löschung, Status, zurückziehen',
      blocks: [
        {
          kind: 'comic',
          scene: 'antrag',
          text:
            'Heutige Zeiteinträge ändern Sie selbst. Ab dem nächsten Tag ist ein Eintrag gesperrt – dann beantragen Sie die Korrektur oder Löschung, ' +
            'und die Verwaltung entscheidet. So bleibt jede Änderung nachvollziehbar (§ 16 ArbZG).',
        },
        {
          kind: 'task',
          id: 'antrag-wann-noetig',
          title: 'Wann brauche ich einen Antrag?',
          intro:
            'In Zeiterfassung → Tab [[Einträge]] zeigt die Spalte **Aktionen**, was Sie tun können: Bei heutigen Einträgen stehen Stift und Papierkorb – ' +
            'Sie bearbeiten oder löschen selbst. Bei älteren Einträgen steht ein Schloss, daneben zwei Antragsknöpfe.',
          shot: 'ma-antrag-knoepfe',
          steps: [
            { n: 1, text: '**Änderungsantrag stellen** (Blatt mit Stift): Zeiten, Pause oder Datum eines gesperrten Eintrags korrigieren.' },
            { n: 2, text: '**Löschantrag stellen** (Papierkorb neben dem Schloss): einen gesperrten Eintrag ganz entfernen lassen.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Ganz vergessen zu stempeln? Für einen vergangenen Tag ohne Eintrag gibt es oben rechts den Knopf [[Antrag]] – ' +
            'siehe [Vergangenen Tag nachtragen](#vergangenen-tag-nachtragen).',
        },
        {
          kind: 'task',
          id: 'aenderungsantrag-stellen',
          title: 'Wie korrigiere ich einen älteren Eintrag?',
          intro: 'Klicken Sie in der Zeile des Eintrags auf **Änderungsantrag stellen**. Es öffnet sich der Dialog „Änderungsantrag: Eintrag ändern“.',
          shot: 'ma-antrag-aendern',
          steps: [
            { n: 1, text: '**Aktuelle Werte** zeigt, was heute gespeichert ist.' },
            { n: 2, text: 'Darunter tragen Sie die richtigen Werte ein: **Datum**, **Von**, **Bis**, **Pause (Min.)** und bei Bedarf eine **Notiz**. Im Beispiel wird nur der Beginn korrigiert.' },
            { n: 3, text: 'Schreiben Sie eine **Begründung** – sie ist Pflicht.' },
            { n: 4, text: 'Klicken Sie auf [[Antrag stellen]]. Der Eintrag bleibt unverändert, bis die Verwaltung den Antrag genehmigt.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Pflicht-Pause nicht möglich? (§ 4 ArbZG)** Erfüllen die neuen Zeiten die Pausenregel nicht, erscheint das Feld ' +
            '[[Pflicht-Pause war nicht möglich – Begründung]]. Begründen Sie dort (mindestens 10 Zeichen) und senden Sie mit ' +
            '[[Mit dokumentierter Ausnahme senden]]. Hat Ihre Praxis diese Ausnahme abgeschaltet, fehlt das Feld – tragen Sie dann die Pause ein.',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Sonn- oder Feiertag (§ 10 ArbZG):** Liegt das Datum auf einem Sonntag oder Feiertag, fragt der Antrag zusätzlich nach dem ' +
            '[[Ausnahmegrund (§10 ArbZG)]], z. B. „Notdienst“. Er wird mit der Genehmigung am Eintrag gespeichert.',
        },
        {
          kind: 'task',
          id: 'loeschantrag-stellen',
          title: 'Wie lasse ich einen falschen Eintrag löschen?',
          intro: 'Klicken Sie in der Zeile des Eintrags auf **Löschantrag stellen**. Es öffnet sich der Dialog „Änderungsantrag: Eintrag löschen“.',
          shot: 'ma-antrag-loeschen',
          steps: [
            { n: 1, text: '**Eintrag zum Löschen** zeigt Datum, Von, Bis und Pause des Eintrags. Prüfen Sie, ob es der richtige ist.' },
            { n: 2, text: 'Schreiben Sie eine **Begründung**.' },
            { n: 3, text: 'Klicken Sie auf [[Antrag stellen]]. Gelöscht wird erst, wenn die Verwaltung genehmigt.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Heutiger Eintrag am falschen Tag?** Beim Bearbeiten bleibt das Datum fest. Löschen Sie den heutigen Eintrag und beantragen Sie ' +
            'den richtigen Tag über den Knopf [[Antrag]].',
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Schloss schon heute?** Dann hat die Verwaltung die ganze gestempelte Zeit dieses Eintrags anerkannt ' +
            '(„Anerkannter Eintrag – Änderung per Änderungsantrag oder über die Verwaltung“). Ändern oder löschen Sie ihn auch heute per Antrag.',
        },
        {
          kind: 'task',
          id: 'antrag-status',
          title: 'Wo sehe ich, ob mein Antrag genehmigt ist – und wie ziehe ich ihn zurück?',
          intro: 'Klicken Sie in der Zeiterfassung auf den Tab [[Anträge]]. Darunter stehen unter **Änderungsanträge** alle Ihre Anträge, der neueste oben.',
          shot: 'ma-antraege-status',
          steps: [
            { n: 1, text: 'Der Tab [[Anträge]] öffnet die Liste.' },
            { text: 'Mit [[Alle]], [[Offen]], [[Genehmigt]] und [[Abgelehnt]] filtern Sie nach Status.' },
            { n: 2, text: 'Jeder Antrag ist eine Karte: oben Status (**Offen**, **Genehmigt** oder **Abgelehnt**), Art (**Neuer Eintrag**, **Änderung** oder **Löschung**) und wann Sie ihn gestellt haben; darunter **Aktuell** und **Gewünscht** sowie Ihre Begründung.' },
            { n: 3, text: 'Solange ein Antrag **Offen** ist, steht rechts [[Zurückziehen]]. Bestätigen Sie im Dialog „Antrag zurückziehen“ – der Antrag verschwindet aus der Liste.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Genehmigte oder abgelehnte Anträge lassen sich nicht zurückziehen. Bei einem Antrag aus [[Anrechnung beantragen]] steht zusätzlich ' +
            '„Anrechnung beantragt“; nach der Genehmigung „anerkannt“ oder „ohne Anerkennen genehmigt“.',
        },
        {
          kind: 'task',
          id: 'antrag-abgelehnt',
          title: 'Mein Antrag wurde abgelehnt – warum?',
          intro: 'Die Verwaltung gibt bei jeder Ablehnung einen Grund an.',
          shot: 'ma-antrag-abgelehnt',
          steps: [
            { n: 1, text: 'Klicken Sie im Tab [[Anträge]] auf den Filter [[Abgelehnt]].' },
            { n: 2, text: 'Der rote Kasten **Ablehnungsgrund** sagt, was fehlt. Darunter steht, wer den Antrag wann bearbeitet hat.' },
            { text: 'Ist der Grund behoben, stellen Sie einen neuen Antrag – oder sprechen Sie die Verwaltung an.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Urlaubsanträge** stehen nicht hier, sondern unter Abwesenheiten → [[Meine Anträge]] – ' +
            'siehe [Urlaubsantrag und Status](#urlaubsantrag-status).',
        },
      ],
    },

    // ── 6 ───────────────────────────────────────────────────────────────────
    {
      id: 'auf-dem-handy',
      title: 'Auf dem Handy: Stempel-Knopf, untere Leiste',
      blocks: [
        {
          kind: 'comic',
          scene: 'handy',
          text:
            'PraxisZeit läuft auch im Browser Ihres Smartphones – ohne eigene App. Auf dem schmalen Bildschirm sitzt die Navigation unten, ' +
            'und der runde Stempel-Knopf liegt in der Mitte, gut mit dem Daumen erreichbar.',
        },
        {
          kind: 'task',
          id: 'handy-navigation',
          title: 'Wie finde ich mich auf dem Smartphone zurecht?',
          shot: 'ma-handy-start',
          steps: [
            { n: 1, text: 'Oben rechts öffnet das **Menü** (drei Striche) die ganze Navigation – auch Hilfe, Handbuch und Abmelden.' },
            { n: 2, text: 'Der runde **Stempel-Knopf** in der Mitte der unteren Leiste öffnet die Stempeluhr. Grün mit Uhr heißt: Sie sind eingestempelt.' },
            { n: 3, text: 'Die **untere Leiste**: [[Home]] (Dashboard), [[Journal]] (Zeiterfassung, Tab Journal), [[Abwes.]] (Abwesenheiten) und [[Profil]].' },
          ],
        },
        {
          kind: 'task',
          id: 'handy-stempeln',
          title: 'Wie stempele ich auf dem Smartphone ein und aus?',
          intro: 'Tippen Sie auf den runden Stempel-Knopf. Von unten fährt die Stempeluhr herein.',
          shot: 'ma-handy-stempeluhr',
          steps: [
            { n: 1, text: 'Die große Uhr zeigt Ihre **Arbeitszeit heute**, darunter **Start** und **Pause**.' },
            { n: 2, text: 'Tippen Sie auf [[Einstempeln]] bzw. [[Ausstempeln]]. Beim Ausstempeln erscheint das Feld **Pause (Minuten)** – tragen Sie Ihre Pause ein und tippen Sie auf [[Jetzt ausstempeln]].' },
            { text: '[[Abbrechen]] schließt das Pausenfeld, das **X** oben rechts die Stempeluhr.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Es gelten dieselben Regeln wie am PC – auch die Pflicht-Pause nach § 4 ArbZG, siehe [Ausstempeln mit Pause](#ausstempeln-mit-pause). ' +
            'Führt Ihre Praxis für Sie keine Stundenzählung, fehlt der Stempel-Knopf.',
        },
        {
          kind: 'task',
          id: 'handy-zeiterfassung',
          title: 'Wie trage ich auf dem Smartphone Zeiten nach oder korrigiere sie?',
          intro: 'Öffnen Sie über das Menü die **Zeiterfassung**. Die Einträge stehen dort als Karten, der neueste oben.',
          shot: 'ma-handy-zeiterfassung',
          steps: [
            { n: 1, text: '[[Antrag]]: einen vergangenen Tag ohne Eintrag beantragen.' },
            { n: 2, text: 'Das **Plus** öffnet das Formular für einen neuen Eintrag von heute. Es fährt von unten herein.' },
            { n: 3, text: 'Bei gesperrten Einträgen (Schloss neben dem Datum) stellt [[Ändern]] einen Änderungsantrag und [[Löschen]] einen Löschantrag. Heutige Einträge haben [[Bearbeiten]] und [[Löschen]].' },
          ],
        },
        {
          kind: 'task',
          id: 'handy-qr-code',
          title: 'Wie öffne ich PraxisZeit schnell auf dem Smartphone?',
          intro: 'Sie müssen die Adresse nicht abtippen.',
          steps: [
            { n: 1, text: 'Öffnen Sie PraxisZeit am PC und klicken Sie auf der Anmeldeseite auf [[Auf dem Smartphone öffnen (QR-Code)]].' },
            { n: 2, text: 'Scannen Sie den QR-Code mit der Kamera Ihres Smartphones. Der Browser öffnet dieselbe Anmeldeseite.' },
            { n: 3, text: 'Melden Sie sich wie gewohnt mit Benutzername und Passwort an.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Der QR-Code öffnet nur die Seite, er meldet Sie nicht an. Ihr Smartphone muss im selben Netz sein wie der Server (meist das Praxis-WLAN). ' +
            'Bei einem selbst ausgestellten Zertifikat bestätigen Sie die Sicherheitswarnung einmal.',
        },
        {
          kind: 'task',
          id: 'als-app-installieren',
          title: 'Kann ich PraxisZeit wie eine App auf den Startbildschirm legen?',
          intro: 'Ja, auf unterstützten Geräten.',
          steps: [
            { n: 1, text: '**Android (Chrome):** Menü des Browsers → „Zum Startbildschirm hinzufügen“.' },
            { n: 2, text: '**iPhone (Safari):** Teilen-Symbol → „Zum Home-Bildschirm“.' },
          ],
        },
      ],
    },

    // ── 7 ───────────────────────────────────────────────────────────────────
    {
      id: 'profil-passwort-2fa',
      title: 'Profil, Passwort, 2FA',
      blocks: [
        {
          kind: 'comic',
          scene: 'zweifaktor',
          text:
            'Im **Profil** stehen Ihre Daten und Ihre Arbeitszeit. Dort ändern Sie Ihr Passwort und schützen Ihr Konto auf Wunsch zusätzlich ' +
            'mit einem Code aus einer Authenticator-App.',
        },
        {
          kind: 'task',
          id: 'profil-ueberblick',
          title: 'Was steht in meinem Profil, und was kann ich selbst ändern?',
          intro: 'Klicken Sie in der Navigation auf [[Profil]].',
          shot: 'ma-profil',
          steps: [
            { n: 1, text: '[[Bearbeiten]]: Vorname, Nachname und E-Mail ändern und mit [[Speichern]] übernehmen. Ein Profilbild setzen Sie per Klick auf das runde Bild.' },
            { n: 2, text: '**Passwort ändern** → [[Ändern]], siehe unten.' },
            { n: 3, text: '**Meine Arbeitszeit**: Ihre heute gültige Arbeitszeit, siehe unten.' },
            { n: 4, text: '**Weitere Einstellungen** (aufgeklappt): Zwei-Faktor-Authentifizierung, **Kalenderfarbe** für den Teamkalender und **Meine Daten exportieren** ([[JSON herunterladen]]).' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Benutzername, Rolle, Urlaubstage und Ihre Arbeitszeit legt die Verwaltung fest. Fehlt dort etwas oder stimmt es nicht, sprechen Sie sie an.',
        },
        {
          kind: 'task',
          id: 'meine-arbeitszeit',
          title: 'Wo sehe ich meine Arbeitszeit und wann sie sich geändert hat?',
          shot: 'ma-meine-arbeitszeit',
          steps: [
            { n: 1, text: 'Die Karte **Meine Arbeitszeit** im Profil.' },
            { n: 2, text: 'Je Wochentag Ihre **Arbeitszeit-Blöcke** und Ihr **Tagessoll**, darunter Ihre **Wochenstunden**. Sind keine Blöcke hinterlegt, steht „–“ statt der Zeiten.' },
            { n: 3, text: 'Der **Verlauf** listet jede Änderung mit dem Datum, ab dem sie gilt.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Ändert die Verwaltung Ihre Arbeitszeit, kündigt das Dashboard es 30 Tage lang an. Arbeiten Sie im Minijob mit fester Monatsarbeitszeit, ' +
            'heißen die Tageswerte „geplant“; ohne Stundenzählung gibt es kein Tagessoll.',
        },
        {
          kind: 'task',
          id: 'passwort-aendern',
          title: 'Wie ändere ich mein Passwort?',
          intro: 'Klicken Sie in der Karte **Passwort ändern** auf [[Ändern]].',
          shot: 'ma-passwort-aendern',
          steps: [
            { n: 1, text: '**Aktuelles Passwort** eingeben.' },
            { n: 2, text: '**Neues Passwort** eingeben: mindestens 10 Zeichen, 1 Großbuchstabe, 1 Kleinbuchstabe, 1 Ziffer.' },
            { n: 3, text: 'Unter **Passwort bestätigen** das neue Passwort wiederholen.' },
            { text: 'Klicken Sie auf [[Speichern]].' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Nach dem Ändern bleiben Sie hier angemeldet. Alle anderen Sitzungen – etwa auf dem Smartphone – werden abgemeldet; ' +
            'dort melden Sie sich mit dem neuen Passwort wieder an.',
        },
        {
          kind: 'task',
          id: 'zwei-faktor-einrichten',
          title: 'Wie schütze ich mein Konto mit Zwei-Faktor-Authentifizierung (2FA)?',
          intro:
            'Sie brauchen eine Authenticator-App auf dem Smartphone, z. B. Google Authenticator oder Authy. ' +
            'Im Profil unter **Weitere Einstellungen** → **Zwei-Faktor-Authentifizierung (2FA)** klicken Sie auf [[2FA aktivieren]], ' +
            'bestätigen Ihr aktuelles Passwort und klicken auf [[Weiter]].',
          shot: 'ma-2fa-einrichten',
          steps: [
            { n: 1, text: 'Scannen Sie den **QR-Code** mit Ihrer Authenticator-App. Alternativ tippen Sie den Schlüssel darunter in die App ein.' },
            { n: 2, text: 'Geben Sie den **6-stelligen Code** ein, den die App jetzt anzeigt.' },
            { text: 'Klicken Sie auf [[Bestätigen & 2FA aktivieren]]. Ab jetzt fragt die Anmeldung nach dem Code, siehe [Anmelden mit 2FA](#anmelden-mit-2fa).' },
          ],
        },
        {
          kind: 'task',
          id: 'zwei-faktor-ausschalten',
          title: 'Wie schalte ich 2FA aus, z. B. vor einem Handywechsel?',
          intro: 'Solange 2FA aktiv ist, lässt sie sich nicht neu einrichten. Schalten Sie sie erst mit dem alten Gerät aus.',
          steps: [
            { n: 1, text: 'Klicken Sie im Profil unter **Zwei-Faktor-Authentifizierung (2FA)** auf [[2FA deaktivieren]].' },
            { n: 2, text: 'Geben Sie Ihr aktuelles Passwort und den aktuellen 6-stelligen Code aus der App ein.' },
            { n: 3, text: 'Klicken Sie auf [[2FA deaktivieren]]. Danach richten Sie 2FA auf dem neuen Gerät neu ein.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            '**Handy verloren?** Dann haben Sie keinen Code mehr. Die Verwaltung setzt Ihre 2FA zurück; danach melden Sie sich nur mit dem Passwort an ' +
            'und richten 2FA neu ein.',
        },
      ],
    },

    // ── 8 ───────────────────────────────────────────────────────────────────
    {
      id: 'schichtplan',
      title: 'Schichtplan (wenn eingeschaltet)',
      blocks: [
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Nur wenn eingeschaltet:** Den Schichtplan gibt es nur, wenn Ihre Praxis die Schichtplanung nutzt. Sonst fehlt der Menüpunkt – ' +
            'dieses Kapitel können Sie dann überspringen.',
        },
        {
          kind: 'comic',
          scene: 'schichtplan',
          text:
            'Der Schichtplan zeigt, wer wann an welchem Arbeitsplatz eingeteilt ist. Er ist ein reines Planungswerkzeug: ' +
            'Ihre Zeiteinträge, Ihr Urlaub und Ihr Überstundenkonto ändern sich dadurch nicht.',
        },
        {
          kind: 'task',
          id: 'schichtplan-ansehen',
          title: 'Wo sehe ich, wann ich wo eingeteilt bin?',
          intro: 'Klicken Sie in der Navigation auf [[Schichtplan]].',
          shot: 'ma-schichtplan',
          steps: [
            { n: 1, text: 'Jeder Plan steht mit seinem Namen und seiner Beschreibung über einem Wochenraster: je Tag die Arbeitsplätze mit Uhrzeit und den eingeteilten Personen. Ein **»** vor einem Text ist ein Hinweis zur Einteilung, z. B. „» Telefondienst bis 9:00“.' },
            { n: 2, text: '[[PDF]] erstellt den angezeigten Plan als Aushang zum Ausdrucken.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Gelten heute mehrere Pläne, z. B. einer je Standort, stehen alle untereinander. Hat die Verwaltung einen Plan für später freigegeben, ' +
            'wählen Sie ihn unter „Vorschau — freigegeben, gilt aber (noch) nicht heute:“. Er trägt dann den Hinweis ' +
            '„Dieser Plan gilt noch nicht — er ist zur Ansicht freigegeben.“ bzw. „Dieser Plan gilt nicht mehr — er ist zur Ansicht freigegeben.“',
        },
        {
          kind: 'task',
          id: 'einteilung-heute',
          title: 'Wo sehe ich meine Einteilung für heute?',
          intro: 'Auf dem Dashboard, sobald Sie heute eingeteilt sind.',
          shot: 'ma-einteilung-heute',
          steps: [
            { n: 1, text: 'Die Karte **Deine Einteilung heute** zeigt je Einsatz Arbeitsplatz, Uhrzeit und Plan – und den Hinweis mit **»**, falls einer gesetzt ist.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            'Für welche Arbeitsplätze Sie eingewiesen sind, steht im Profil unter **Meine Einweisungen**. Einteilung und Einweisungen pflegt die Verwaltung.',
        },
      ],
    },

    // ── 9 ───────────────────────────────────────────────────────────────────
    {
      id: 'haeufige-fragen',
      title: 'Häufige Fragen',
      blocks: [
        {
          kind: 'task',
          id: 'faq-eintrag-verschwunden',
          title: 'Ich sehe meinen gespeicherten Eintrag nicht mehr.',
          steps: [
            { text: 'Prüfen Sie, ob der richtige Monat angezeigt wird. Blättern Sie mit den Pfeilen neben dem Monatsnamen.' },
          ],
        },
        {
          kind: 'task',
          id: 'faq-warnung-arbeitszeit',
          title: 'Beim Eintragen erscheint eine Warnung zur Arbeitszeit.',
          intro: 'PraxisZeit prüft die Grenzen des Arbeitszeitgesetzes:',
          steps: [
            { text: '**Mehr als 8 Stunden netto:** Hinweis – zulässig, wenn es ausgeglichen wird (§ 3 ArbZG).' },
            { text: '**Mehr als 10 Stunden netto:** beim Eintragen von Hand gesperrt; beim Ausstempeln nur eine Warnung, weil die Zeit schon geleistet ist.' },
            { text: '**Zu kurze Pause (§ 4 ArbZG):** Speichern und Ausstempeln erst mit ausreichender Pause oder – wenn Ihre Praxis das erlaubt – mit Begründung.' },
            { text: '**Überschneidung** mit einem anderen Eintrag desselben Tages: Speichern und Einstempeln sind gesperrt; der Hinweis nennt den Eintrag.' },
          ],
        },
        {
          kind: 'task',
          id: 'faq-angerechnet-ab',
          title: 'Bei meinem Eintrag steht „gestempelt 07:30 · angerechnet ab 07:45“.',
          steps: [
            { text: 'Für diesen Wochentag sind Arbeitszeit-Blöcke hinterlegt. Vor dem ersten und nach dem letzten Block wird nur bis zum Puffer angerechnet; Ihre Stempelzeit bleibt gespeichert. Siehe [Nicht angerechnete Zeit](#nicht-angerechnete-zeit).' },
          ],
        },
        {
          kind: 'task',
          id: 'faq-datum-grau',
          title: 'Ich will das Datum eines Eintrags ändern, aber das Feld ist grau.',
          steps: [
            { text: 'Beim Bearbeiten bleibt das Datum fest. Löschen Sie den Eintrag und beantragen Sie den richtigen Tag über [[Antrag]] – siehe [Vergangenen Tag nachtragen](#vergangenen-tag-nachtragen).' },
          ],
        },
        {
          kind: 'task',
          id: 'faq-arbeitszeit-geaendert',
          title: 'Auf dem Dashboard steht, dass meine Arbeitszeit geändert wurde.',
          steps: [
            { text: 'Die Verwaltung hat Ihre Arbeitszeit geändert – Wochenstunden, Tagesplan oder Arbeitszeit-Blöcke. Der Hinweis nennt das Datum und, falls erfasste Einträge neu berechnet wurden, wie viele. Er verschwindet nach 30 Tagen; die Einzelheiten stehen unter [Meine Arbeitszeit](#meine-arbeitszeit).' },
          ],
        },
        {
          kind: 'task',
          id: 'faq-urlaubsanspruch',
          title: 'Wie berechnet sich mein Urlaubsanspruch?',
          steps: [
            { text: 'Der Jahresanspruch richtet sich nach Ihren Arbeitstagen pro Woche (z. B. 5 Tage → 30 Tage, 3 Tage → 18 Tage); den genauen Wert legt die Verwaltung fest. Verbraucht wird nach Tagen: ein freier Arbeitstag ist ein Urlaubstag, ein halber Tag 0,5.' },
          ],
        },
        {
          kind: 'task',
          id: 'faq-ueberstundenausgleich',
          title: 'Was passiert bei „Überstundenausgleich“?',
          steps: [
            { text: 'Sie bauen Überstunden ab. Ihr Soll für den Tag bleibt, der Tag zählt mit 0 Ist-Stunden; die Stunden, die Sie eintragen, gehen von Ihrem Überstundenkonto ab. Urlaub wird nicht abgezogen.' },
          ],
        },
        {
          kind: 'task',
          id: 'faq-keine-stunden',
          title: 'Bei mir fehlen Monatssaldo, Überstundenkonto und Stempel-Knopf. Ist das ein Fehler?',
          steps: [
            { text: 'Nein. Für manche Mitarbeitende führt die Praxis keine Stundenzählung. Urlaub und Krankheit werden trotzdem nach Tagen geführt, und Abwesenheiten tragen Sie ganz normal ein.' },
          ],
        },
        {
          kind: 'task',
          id: 'faq-minus',
          title: 'Was bedeutet ein rotes Minus beim Saldo?',
          steps: [
            { text: 'Sie haben weniger gearbeitet als Ihr Soll. Ein grüner Wert heißt: mindestens das Soll.' },
          ],
        },
        {
          kind: 'task',
          id: 'faq-wochenende-feiertag',
          title: 'Wie trage ich Arbeit am Wochenende oder Feiertag ein, z. B. einen Notdienst?',
          steps: [
            { text: '**Am selben Tag:** stempeln Sie wie gewohnt oder legen Sie über [[Neuer Eintrag]] einen Eintrag an. An Sonn- und Feiertagen fragt das Formular nach dem **Ausnahmegrund**.' },
            { text: '**Nachträglich:** über den Knopf [[Antrag]] oder im Journal über das **+** in der Zeile des Tages – beide fragen an Sonn- und Feiertagen nach dem [[Ausnahmegrund (§10 ArbZG)]].' },
            { text: 'An diesen Tagen ist Ihr Soll 0 – die angerechneten Stunden erhöhen Ihren Saldo. Solche Einträge tragen in der Liste das Kennzeichen „So/FT“.' },
          ],
        },
        {
          kind: 'task',
          id: 'faq-passwort-vergessen',
          title: 'Ich habe mein Passwort vergessen.',
          steps: [
            { text: 'Wenden Sie sich an Ihre Verwaltung. Sie setzt Ihr Passwort zurück.' },
          ],
        },
      ],
    },
  ],
  shots,
};
