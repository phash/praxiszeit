import type { Handbook, ShotDef } from '../types';

/**
 * Handbuch für Mitarbeitende (Kapitel 1–4; Task 8b ergänzt 5–9).
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
    crop: { around: ['status', 'einstempeln'], pad: 56 },
    markers: [
      { n: 1, id: 'status', locator: { css: 'main >> text=Nicht eingestempelt >> visible=true' } },
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
    persona: 'maria',
    viewport: 'desktop',
    route: '/time-tracking',
    prepare: [
      { click: { role: 'button', name: 'Antrag', exact: true, within: 'main' } },
      // Seed: an diesem Werktag hat Maria keinen Eintrag (MARIA_FORGOTTEN_WORKDAY)
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
      { n: 1, id: 'ansicht', locator: { css: "xpath=//main//div[button[normalize-space()='Monat'] and button[normalize-space()='Jahr']]" } },
      { n: 2, id: 'monat', locator: { role: 'button', name: 'Nächster Monat', exact: true, within: 'main' }, badge: 'right' },
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
    alt: 'Formular „Abwesenheit eintragen“ mit Zeitraum, Halber Tag, Datum, Typ Urlaub, Stunden und dem Knopf „Speichern“',
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
    alt: 'Formular „Abwesenheit eintragen“ mit Haken bei „Halber Tag (zählt als 0,5 Tag)“ und gesperrtem Stundenfeld',
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
            '**Roter Kasten „Buchung fehlt“:** An einem vergangenen Werktag fehlt ein Zeiteintrag. Tragen Sie den Tag per Antrag nach – ' +
            'siehe [Vergangenen Tag nachtragen](#vergangenen-tag-nachtragen).',
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
            { n: 1, text: 'Mit [[Monat]] und [[Jahr]] wechseln Sie die Ansicht.' },
            { n: 2, text: 'Mit den Pfeilen neben dem Monatsnamen blättern Sie weiter. Die **Legende** unter dem Kalender erklärt die Farben.' },
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
            { n: 4, text: 'Klicken Sie auf [[Speichern]]. Urlaubstage gehen automatisch von Ihrem Budget ab – verlangt Ihre Praxis eine Genehmigung, erst nachdem die Verwaltung den Antrag genehmigt hat.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'info',
          text:
            '**Stunden** sind vorausgefüllt und werden ohnehin durch Ihr Tagessoll ersetzt. Nur bei **Überstundenausgleich** zählt ' +
            'der eingetragene Wert – er wird von Ihrem Überstundenkonto abgezogen.',
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
            { n: 2, text: 'Das Feld **Stunden** ist dann gesperrt: Gebucht wird automatisch das halbe Tagessoll.' },
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
          intro: 'Unter dem Kalender stehen Ihre Abwesenheiten des Jahres als Liste.',
          steps: [
            { n: 1, text: 'Klicken Sie in der Zeile der Abwesenheit auf [[Löschen]].' },
            { n: 2, text: 'Bestätigen Sie im Dialog.' },
          ],
        },
        {
          kind: 'tip',
          tone: 'warn',
          text:
            'Nicht selbst löschen können Sie Betriebsferien-Tage, genehmigten Urlaub (dafür [[Urlaub stornieren]]), Abwesenheiten an vergangenen Tagen ' +
            'und Abwesenheiten, die die Verwaltung für Sie eingetragen hat. Wenden Sie sich in diesen Fällen an Ihre Verwaltung.',
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
  ],
  shots,
};
