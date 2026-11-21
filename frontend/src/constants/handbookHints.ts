import type { HandbookId } from '../handbuch/types';

/**
 * Register der „?“-Kurzhilfen neben Feldern (`<HandbookHint hintId="…" />`).
 *
 * Je Eintrag: Handbuch und Sprungmarke (Kapitel- oder Aufgaben-ID, geprüft in
 * `handbookHints.test.ts` über `anchorExists`), Titel und ein Kurztext mit
 * höchstens drei Sätzen in Sie-Form, sinngemäß aus dem verlinkten Abschnitt.
 * Mitarbeiterseiten verlinken `book: 'mitarbeitende'`.
 *
 * Titel: Der Knopf heißt „Hilfe: <Titel>“. Playwright sucht `getByLabel('…')`
 * und `getByRole('button', { name: '…' })` ohne `exact` als Teilstring, RTL-Tests
 * oft mit regulären Ausdrücken. Ein Titel darf deshalb keine Feldbeschriftung
 * oder Knopfbeschriftung derselben Seite enthalten (z. B. „Speichern“, „Datum“,
 * „Bis“, „Arbeitszeitkonto“, „Gültig ab“) – sonst findet der Locator zwei Elemente.
 */
export interface HandbookHintEntry {
  book: HandbookId;
  anchor: string;
  title: string;
  text: string;
}

const HINTS = {
  // ── Benutzerformular (UserForm, ContractTermsFields) ─────────────────────
  'user-vacation-days': {
    book: 'praxisleitung',
    anchor: 'mitarbeiter-anlegen',
    title: 'Urlaubsanspruch beim Anlegen',
    text:
      'Der Jahresanspruch in Tagen. ' +
      'Der Vorschlag rechnet 30 × Arbeitstage ÷ 5, bei 4 Arbeitstagen also 24 Tage; Sie können ihn übernehmen oder überschreiben.',
  },
  'user-track-hours': {
    book: 'praxisleitung',
    anchor: 'mitarbeiter-optionen',
    title: 'Stundenzählung',
    text:
      'Ohne Haken führt PraxisZeit für die Person kein Soll und Ist und keine Überstunden; Urlaub und Krankheit zählen trotzdem tagebasiert. ' +
      'Mit der Ausnahme nach § 18 ArbZG hat der Haken nichts zu tun, beide lassen sich frei kombinieren.',
  },
  'user-arbzg-exempt': {
    book: 'praxisleitung',
    anchor: 'mitarbeiter-optionen',
    title: 'Ausnahme nach § 18 ArbZG',
    text:
      'Setzen Sie den Haken nur für Personen, die tatsächlich unter § 18 ArbZG fallen. ' +
      'Er ist eine eigene Einstellung und unabhängig von der Stundenzählung.',
  },
  'user-night-worker': {
    book: 'praxisleitung',
    anchor: 'arbzg-pruefung',
    title: 'Nachtarbeitnehmer',
    text:
      'Arbeitet ein Nachtarbeitnehmer (§ 6 ArbZG) an einem Tag mehr als 8 Stunden, warnt PraxisZeit. ' +
      'Unter Berichte wertet „Nachtarbeit §6 ArbZG“ die Nachtarbeitstage und Nachtarbeitnehmer aus.',
  },
  'user-company-closures': {
    book: 'praxisleitung',
    anchor: 'mitarbeiter-optionen',
    title: 'Teilnahme an Betriebsferien',
    text:
      'Mit Haken bekommt die Person bei Betriebsferien automatisch die Abwesenheiten, unabhängig von ihrer Rolle. ' +
      'Für reine Verwaltungskonten können Sie ihn abwählen.',
  },
  'user-work-period': {
    book: 'praxisleitung',
    anchor: 'mitarbeiter-optionen',
    title: 'Beschäftigungszeitraum',
    text:
      'Das Soll wird nur zwischen erstem und letztem Arbeitstag berechnet, der Urlaubsanspruch im Ein- und Austrittsjahr anteilig. ' +
      'Tragen Sie bei einem Eintritt im laufenden Jahr den ersten Arbeitstag ein, sonst entstehen für die Tage davor Minusstunden.',
  },
  'user-carryover': {
    book: 'praxisleitung',
    anchor: 'mitarbeiter-optionen',
    title: 'Startwerte aus einem anderen System',
    text:
      'Kommt die Person aus einem anderen System, tragen Sie hier den dort erreichten Stand ein: ' +
      'die Überstunden unter „Anfangssaldo Überstunden“, den Resturlaub unter „Übertrag Urlaubstage“.',
  },
  'user-child-sick-days': {
    book: 'praxisleitung',
    anchor: 'kind-krank-anspruch',
    title: 'Eigener Kind-krank-Anspruch',
    text:
      'Ein eigener Jahresanspruch an Kind-krank-Tagen für diese Person; leer gilt der Standard aus den Einstellungen. ' +
      'Wird er überschritten, weist PraxisZeit beim Buchen darauf hin, erfasst die Abwesenheit aber trotzdem.',
  },
  'user-carryover-deadline': {
    book: 'praxisleitung',
    anchor: 'mitarbeiter-bearbeiten',
    title: 'Eigene Verfallsfrist',
    text:
      'Eine eigene Verfallsfrist für den Resturlaub dieser Person, als festes Datum für alle Jahre; leer gilt der 31.03. des Folgejahres. ' +
      'Nach Ablauf passen Sie das Datum an oder leeren es.',
  },
  'minijob-account': {
    book: 'praxisleitung',
    anchor: 'minijob-konto',
    title: 'Minijob und Mindestlohn',
    text:
      'Für Minijobber:innen auf Arbeitszeitkonto (§ 2 Abs. 2 MiLoG) weist PraxisZeit auf die 50-%-Grenze und die 12-Monats-Ausgleichsfrist hin, blockiert aber nichts. ' +
      'Bleibt die vereinbarte Monatsarbeitszeit leer, rechnet PraxisZeit Wochenstunden × 13/3; mit fester Monatsarbeitszeit ist sie jeden Monat das Monats-Soll. ' +
      'Änderungen an den Minijob-Einstellungen gelten immer ab dem Monatsersten.',
  },
  'work-blocks': {
    book: 'praxisleitung',
    anchor: 'bloecke-hinterlegen',
    title: 'Arbeitszeit-Blöcke',
    text:
      'Je Wochentag tragen Sie die Zeiten im 5-Minuten-Raster ein, höchstens drei Blöcke; ein Tag ohne Block ist kein Arbeitstag. ' +
      'Das Tagessoll ist die Summe der Blöcke minus der Pause innerhalb. ' +
      'Gestempelte Zeit vor, nach und zwischen den Blöcken zählt nur bis zum Puffer.',
  },

  // ── Dialog „Arbeitszeit & Wochenstunden“ ─────────────────────────────────
  'wh-effective-date': {
    book: 'praxisleitung',
    anchor: 'rueckwirkend-aendern',
    title: 'Wirksam ab',
    text:
      'Ab diesem Tag gilt die neue Arbeitszeit. ' +
      'Liegt das Datum in der Vergangenheit, rechnet PraxisZeit die Zeiteinträge und danach die Abwesenheiten ab diesem Tag neu. ' +
      'Verliert dabei ein Eintrag angerechnete Zeit oder sinkt das Überstundenkonto, gilt die Änderung standardmäßig erst ab dem frühesten Tag ohne Verlust, meist ab heute – rückwirkend nur mit Grund.',
  },
  'wh-first-work-day': {
    book: 'praxisleitung',
    anchor: 'vertrag-ab-eintritt',
    title: 'Vertrag ab dem ersten Arbeitstag',
    text:
      'Wurde die Arbeitszeit einer neuen Person mit dem heutigen Datum gespeichert, gilt bis gestern noch der Vertrag vom Anlegen. ' +
      'Mit dem Knopf daneben springt „Gültig ab“ auf den ersten Arbeitstag, und die Auswirkung wird neu berechnet. ' +
      'Einträge an Tagen, die danach keine Arbeitstage mehr sind, können Sie beim Speichern gleich anerkennen.',
  },
  'wh-vacation-days': {
    book: 'praxisleitung',
    anchor: 'vertragsverlauf',
    title: 'Neuer Urlaubsanspruch',
    text:
      'Der Anspruch gilt ab „Gültig ab“; wechselt er im Jahr, rechnet PraxisZeit jeden Abschnitt anteilig nach Monaten. ' +
      'Sinkt er rückwirkend, ist das eine Verkürzung und braucht einen Grund.',
  },
  'wh-impact': {
    book: 'praxisleitung',
    anchor: 'auswirkung-pruefen',
    title: 'Auswirkung der Änderung',
    text:
      'Der Kasten zeigt vor dem Speichern, wie viele Zeiteinträge und Abwesenheiten neu berechnet werden und wie sich Überstunden und Urlaubsverbrauch ändern. ' +
      '„Einzelheiten“ listet jeden Eintrag mit seinen Zeiten vorher und nachher.',
  },
  'wh-recognize': {
    book: 'praxisleitung',
    anchor: 'auswirkung-pruefen',
    title: 'Einträge, die Zeit verlieren',
    text:
      'Gewählte Einträge werden beim Speichern anerkannt und zählen mit der ganzen gestempelten Zeit; das lässt sich nicht zurücknehmen. ' +
      'Vorausgewählt sind Einträge an einem Tag ohne Block und an Tagen, die bisher gar nicht gekappt wurden. ' +
      'Für nicht gewählte Einträge gilt die Verkürzung wie bisher; bei „Ab heute … wirksam“ wird nichts anerkannt.',
  },
  'wh-shortening': {
    book: 'praxisleitung',
    anchor: 'rueckwirkend-aendern',
    title: 'Wenn Zeit verloren geht',
    text:
      'Verliert ein Eintrag angerechnete Zeit, sinkt das Überstundenkonto oder sinkt an einem Tag mit Arbeit die Gutschrift einer Abwesenheit stärker als das Tagessoll, ist die Änderung eine Verkürzung. ' +
      'Standard ist der früheste Tag ohne Verlust, meist heute: Vergangene Einträge bleiben unverändert, ein Grund ist nicht nötig. ' +
      'Rückwirkend mit Neuberechnung geht es nur mit Grund, Begründung und Bestätigung.',
  },
  'wh-history': {
    book: 'praxisleitung',
    anchor: 'vertragsverlauf',
    title: 'Vertragsverlauf',
    text:
      'Jede Änderung wird zu einer Zeile im Verlauf, mit „Ab … bis …“; die jüngste läuft „bis heute“. ' +
      'So stimmen auch frühere Monate, wenn sich Arbeitszeit oder Urlaubsanspruch ab einem Datum ändern.',
  },

  // ── Monatsjournal ────────────────────────────────────────────────────────
  'journal-recognize': {
    book: 'praxisleitung',
    anchor: 'nicht-angerechnet-anerkennen',
    title: 'Mehrere Einträge auf einmal',
    text:
      'Setzen Sie bei jedem Eintrag das Häkchen „Auswählen“ oder wählen Sie alle nicht angerechneten aus. ' +
      'PraxisZeit erkennt dann alle gewählten Einträge an oder keinen; sie zählen mit der ganzen gestempelten Zeit. ' +
      'Anerkennen lässt sich nicht zurücknehmen.',
  },
  'journal-balance': {
    book: 'so-rechnet',
    anchor: 'soll-ist-journal',
    title: 'Soll, Ist und Saldo',
    text:
      'Das Soll ist, was laut Vertrag zu arbeiten wäre, das Ist die angerechnete Zeit plus Gutschriften für Krankheit und Fortbildung. ' +
      'Der Saldo ist Ist minus Soll; die Summe der Tages-Differenzen ergibt in der Regel den Monatssaldo.',
  },

  // ── Einstellungen ────────────────────────────────────────────────────────
  'settings-absence-reasons': {
    book: 'praxisleitung',
    anchor: 'eigenen-grund-anlegen',
    title: 'Eigene Abwesenheitsgründe',
    text:
      'Das Verhalten bestimmt die Berechnung und lässt sich nach dem Anlegen nicht mehr ändern; Farbe und Bezeichnung ändern nichts an den Zahlen. ' +
      'Deaktivierte Gründe stehen beim Buchen nicht mehr zur Auswahl, bleiben an bestehenden Abwesenheiten aber erhalten.',
  },
  'settings-reason-presets': {
    book: 'praxisleitung',
    anchor: 'kind-krank-vorlage',
    title: 'Vorlagen für Sonderurlaub',
    text:
      'Eine Vorlage legt den Grund mit einem Klick an; „Kind krank“ zählt als unbezahlt frei gegen das Jahreslimit. ' +
      'Ob ein Grund bezahlt oder unbezahlt ist, hängt von Ihrem Betrieb ab – mit anderem Verhalten legen Sie ihn selbst an.',
  },
  'settings-holidays': {
    book: 'praxisleitung',
    anchor: 'bundesland-einstellen',
    title: 'Gesetzliche Feiertage',
    text:
      'PraxisZeit trägt die gesetzlichen Feiertage des gewählten Bundeslands ein; an Feiertagen gibt es kein Soll. ' +
      'Ein späterer Wechsel berechnet die Feiertage aller Jahre neu, auch zurückliegender, und ändert Soll und Salden dieser Jahre. ' +
      'Eigene Feiertage bleiben erhalten.',
  },
  'settings-own-holidays': {
    book: 'praxisleitung',
    anchor: 'eigene-feiertage',
    title: 'Regionale Feiertage',
    text:
      'Eigene Feiertage wie ein Schützenfest senken das Soll wie gesetzliche Feiertage. ' +
      'Sie bleiben erhalten, wenn Sie das Bundesland wechseln.',
  },
  'settings-special-days': {
    book: 'praxisleitung',
    anchor: 'sondertage-einstellen',
    title: 'Heiligabend und Silvester',
    text:
      'Je Tag legen Sie fest: Arbeitstag, Halbtag, Frei oder verkürzt auf eine Höchstzahl an Stunden. ' +
      'Bei „Frei“ entscheidet die Anrechnung, ob der Tag vom Urlaubskonto abgeht oder bezahlt frei ist. ' +
      'Die Einstellung gilt für alle Jahre, auch zurückliegende.',
  },
  'settings-reduced-days': {
    book: 'praxisleitung',
    anchor: 'verkuerzte-tage',
    title: 'Einzelne Tage verkürzen',
    text:
      'Für einzelne Tage wie Rosenmontag oder einen Betriebsausflug: Das Soll ist die kleinere Zahl aus Tagessoll und Höchstwert. ' +
      'Urlaub kostet an diesem Tag 0,5 Tage; die gestempelte Zeit wird nicht auf den Höchstwert gekappt.',
  },
  'settings-vacation-approval': {
    book: 'praxisleitung',
    anchor: 'urlaubsgenehmigung',
    title: 'Urlaub direkt oder per Antrag',
    text:
      'Aus (Standard) buchen Mitarbeitende Urlaub direkt. ' +
      'An landen Urlaubsanträge als „Offen“ unter Anträge bei Ihnen.',
  },
  'settings-break-exception': {
    book: 'praxisleitung',
    anchor: 'pflicht-pause-ausnahme',
    title: 'Fehlende Pause begründen',
    text:
      'An (Standard) können Mitarbeitende und Admins eine fehlende Pause begründen; aus lehnt PraxisZeit jede Ausnahme ab. ' +
      'Mit „Genehmigung erforderlich“ wird eine Ausnahme aus der Zeiterfassung erst nach Ihrer Genehmigung gespeichert.',
  },
  'settings-shift-planning': {
    book: 'praxisleitung',
    anchor: 'tour-schichtplanung',
    title: 'Schichtplanung ein- und ausschalten',
    text:
      'Erst mit dem Schalter gibt es Wochen-Schichtpläne, Arbeitsplätze und Standorte; solange er aus ist, sieht niemand die Schichtplanung. ' +
      'Sie ist ein reines Planungswerkzeug und ändert keine Zeiterfassungs-, Urlaubs- oder Überstundendaten.',
  },
  'settings-closure-overtime': {
    book: 'praxisleitung',
    anchor: 'betriebsferien-ueberstundenabbau',
    title: 'Betriebsferien länger als der Resturlaub',
    text:
      'Aus (Standard) zählen alle Schließtage als Urlaub; reicht der Resturlaub nicht, entstehen Minus-Urlaubstage. ' +
      'An wird erst der Urlaub aufgezehrt, die übrigen Tage bucht PraxisZeit als Überstundenausgleich. ' +
      'Bereits eingetragene Betriebsferien speichern Sie einmal erneut, damit die Regel für sie greift.',
  },
  'settings-projection': {
    book: 'praxisleitung',
    anchor: 'jahresende-projektion',
    title: 'Projektion des Saldos',
    text:
      'Die Projektion zeigt den Saldo bis heute abzüglich der bereits gebuchten künftigen Tage Überstundenausgleich. ' +
      'Die Schalter wirken nur auf die Anzeige, das Überstundenkonto selbst bleibt unverändert.',
  },
  'settings-grace': {
    book: 'praxisleitung',
    anchor: 'puffer-einstellen',
    title: 'Puffer für die Anrechnung',
    text:
      'Der Puffer gilt an jedem Blockrand, auch zwischen zwei Blöcken; gestempelte Zeit weiter außerhalb zählt nicht. ' +
      'Eine Änderung wirkt nur auf neue Einträge, gespeicherte behalten ihren Puffer.',
  },
  'settings-child-sick-default': {
    book: 'praxisleitung',
    anchor: 'kind-krank-anspruch',
    title: 'Kind-krank-Standardanspruch',
    text:
      'Die Zahl der Kind-krank-Tage je Jahr für alle ohne eigenen Wert (Voreinstellung 15). ' +
      'Wird der Anspruch beim Buchen überschritten, weist PraxisZeit darauf hin, erfasst die Abwesenheit aber trotzdem.',
  },

  // ── Admin-Dashboard: Soll-Basis und Jahresabschluss ──────────────────────
  'admin-target-basis': {
    book: 'praxisleitung',
    anchor: 'team-monatsuebersicht',
    title: 'Stichtag für das Soll',
    text:
      '„bis heute“ zählt das Soll nur bis zum letzten abgeschlossenen Arbeitstag, „Monatsende“ den vollen Monat (in der Wochenansicht „volle Woche“). ' +
      'Für abgeschlossene Monate sind beide gleich; Datei-Exporte, Monatsjournal und Jahresabschluss rechnen immer den vollen Zeitraum.',
  },
  'admin-year-closing': {
    book: 'praxisleitung',
    anchor: 'jahresabschluss-erstellen',
    title: 'Abschluss und Übertrag',
    text:
      'Der Jahresabschluss übernimmt den Überstunden-Saldo zum 31.12. und den Resturlaub aller aktiven Mitarbeitenden ins Folgejahr. ' +
      'Schließen Sie ein Jahr erst nach seinem Ende ab, wenn alle Anträge entschieden sind. ' +
      'Ein erneuter Abschluss überschreibt die Übernahmen, auch von Hand eingetragene.',
  },

  // ── Mitarbeitende: Dashboard, Zeiterfassung, Anträge ─────────────────────
  'stamp-card': {
    book: 'mitarbeitende',
    anchor: 'zeiterfassung-stempeln-eintraege',
    title: 'Stempelkarte',
    text:
      'Mit Einstempeln läuft die Uhr und zeigt Ihre heutige Arbeitszeit. ' +
      'Beim Ausstempeln tragen Sie Ihre Pause in Minuten ein; bei mehr als 6 Stunden am Tag sind mindestens 30 Minuten Pflicht.',
  },
  'dashboard-month-balance': {
    book: 'mitarbeitende',
    anchor: 'dashboard-ueberblick',
    title: 'Monatssaldo',
    text:
      'Soll und Ist des laufenden Monats; der Saldo ist Ist minus Soll. ' +
      'Das Soll zählt nur bis zum letzten abgeschlossenen Arbeitstag – heute zählt mit, sobald Sie ausgestempelt haben.',
  },
  'dashboard-overtime': {
    book: 'mitarbeitende',
    anchor: 'dashboard-ueberblick',
    title: 'Überstundenkonto',
    text:
      'Ihr kumulierter Saldo über alle Monate. ' +
      'Ein Minus heißt, dass Sie weniger gearbeitet haben als das Soll.',
  },
  'dashboard-vacation': {
    book: 'mitarbeitende',
    anchor: 'dashboard-ueberblick',
    title: 'Urlaubskonto',
    text:
      'Budget, genommene und verbleibende Urlaubstage. ' +
      'Im letzten Quartal erinnert ein gelber Hinweis an offenen Urlaub, sobald noch mindestens ein ganzer Tag offen ist – mit dem Datum, bis wann Sie ihn nehmen sollten.',
  },
  'not-credited': {
    book: 'mitarbeitende',
    anchor: 'nicht-angerechnete-zeit',
    title: 'Nicht angerechnete Zeit',
    text:
      'Mit Arbeitszeit-Blöcken wird nur die Zeit innerhalb der Blöcke angerechnet, mit einem Puffer an jedem Blockrand; Ihre gestempelte Zeit bleibt gespeichert. ' +
      'Haben Sie in dieser Zeit gearbeitet, beantragen Sie die Anrechnung, und die Verwaltung entscheidet.',
  },
  'cr-create': {
    book: 'mitarbeitende',
    anchor: 'vergangenen-tag-nachtragen',
    title: 'Vergangenen Tag nachtragen',
    text:
      'Vergangene Tage tragen Sie nicht selbst ein, Sie beantragen sie mit Zeiten, Pause und einer Begründung. ' +
      'Die Verwaltung prüft den Antrag; den Stand sehen Sie in der Zeiterfassung im Tab Anträge.',
  },
  'cr-update': {
    book: 'mitarbeitende',
    anchor: 'aenderungsantrag-stellen',
    title: 'Älteren Eintrag korrigieren',
    text:
      'Tragen Sie die richtigen Werte ein und begründen Sie den Antrag. ' +
      'Der Eintrag bleibt unverändert, bis die Verwaltung den Antrag genehmigt.',
  },
  'cr-delete': {
    book: 'mitarbeitende',
    anchor: 'loeschantrag-stellen',
    title: 'Falschen Eintrag entfernen',
    text:
      'Prüfen Sie, ob es der richtige Eintrag ist, und begründen Sie den Antrag. ' +
      'Gelöscht wird erst, wenn die Verwaltung genehmigt.',
  },
} satisfies Record<string, HandbookHintEntry>;

export type HintId = keyof typeof HINTS;

export const handbookHints: Record<HintId, HandbookHintEntry> = HINTS;
