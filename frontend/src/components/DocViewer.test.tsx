import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import {
  CheatsheetAdmin,
  CheatsheetMitarbeiter,
  SchnellstartAdmin,
  handbuchAdminSections,
  handbuchMitarbeiterSections,
  type AccordionItem,
} from './DocViewer';
import { getFallbackHelp, helpContent } from '../constants/helpContent';

// Sichtbarer Text einer Doku-Fläche, Leerraum zusammengefasst.
function textOf(node: ReactNode): string {
  const { container, unmount } = render(<div>{node}</div>);
  const text = (container.textContent ?? '').replace(/\s+/g, ' ');
  unmount();
  return text;
}

function sectionsText(items: AccordionItem[]): string {
  return textOf(
    items.map((item) => (
      <section key={item.title}>
        <h2>{item.title}</h2>
        {item.content}
      </section>
    )),
  );
}

// Bedienung und Begriffe, die es seit 1.20.0 nicht mehr gibt (Spec E58, 12.2, 15.1).
const VERALTET = [
  'Wochenstunden anpassen…',
  'Wochenstunden & Tagesplan',
  'Soll-Beginn und Soll-Ende hinterlegen',
  'Soll-Beginn/-Ende je Wochentag',
  'erfassten Blöcke',
  'aller Blöcke des Tages',
  'vergessener Nachmittagsblock',
  'Fehlende Blöcke',
  'Spalte „Arbeitsblöcke"',
  'Änderung beantragen',
  // Über den Plan hinaus (Reviews der Markdown-Tasks 2–6): der Bereich im
  // Bearbeiten-Formular heißt „Arbeitszeit heute" (ohne Doppelpunkt), der
  // Anlegen-Knopf „Neue:r Mitarbeiter:in", und die Erwachsenen-Grenzen gelten
  // auch für Jugendliche – nur §§ 11, 12 JArbSchG prüft PraxisZeit nicht.
  'Arbeitszeit heute: …',
  'Neuer Benutzer',
  'prüft PraxisZeit nichts davon',
  // Review Task 8: gestempelte Einträge heißen nie „Block" (Begriffsregel des
  // Plans), und „Nicht angerechnet (Min)" führen nur die Tageszeilen von
  // Monatsreport und Jahresreport Detailliert – der Jahresreport Classic nicht.
  'durchgehender Block',
  'Spalte aller Formate',
];

function expectNoStaleTerms(text: string) {
  for (const stale of VERALTET) expect(text).not.toContain(stale);
}

describe('In-App-Doku: Arbeitszeit-Blöcke (1.20.0)', () => {
  it('Admin-Handbuch beschreibt Dialog, Blöcke, Schutzpaket und Rechtshinweise', () => {
    const text = sectionsText(handbuchAdminSections);
    for (const expected of [
      '3. Arbeitszeit-Blöcke, Rückwirkung & Anerkennen',
      '15. Admin-Passwort verloren',
      'Arbeitszeit anpassen…',
      'Arbeitszeit & Wochenstunden',
      'Nach Arbeitsblöcken',
      'Pause innerhalb der Blöcke',
      'Tagessoll = Summe der Blockdauern − Pause innerhalb der Blöcke',
      '08:00–12:15 und 14:45–18:00 = 7:30 h',
      'Anerkennen',
      'Anrechnung anerkannt',
      'Neukappung (Arbeitszeit-Änderung)',
      'Nicht angerechnet (Min)',
      'Genehmigen und anerkennen',
      'Ohne Anerkennen genehmigen',
      'Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit.',
      'Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)',
      'Mit der beschäftigten Person vereinbart',
      '[Erfassungsfehler korrigiert]',
      'auf den vorherigen Stand zurücksetzen',
      'Eine Änderung des Puffers wirkt auf neue Einträge.',
      'Nichtanrechnung ersetzt keine Vergütungsentscheidung.',
      '§ 87 Abs. 1 Nr. 2 BetrVG',
      'PraxisZeit prüft das nicht.',
      'Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln',
      'Details in Abschnitt 9',
      // Löschen nur an der jüngsten Zeile, 409 bei einer Zwischenzeile,
      // begrenztes Notizfeld (PR3), echtes Ende 23:59 (V1/P18), P23/P24.
      'nur an der jüngsten Zeile',
      'Rückwirkend löschen mit Neuberechnung',
      'Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden.',
      'Notiz und Begründung zusammen höchstens 500 Zeichen.',
      'Auch ein tatsächliches Ende um 23:59',
      'vorher automatisch geschlossen',
      'beendet die Blöcke ab dem Wirkungsdatum',
      'Unterbrechung (Min) und Zeiteinträge',
      'Anwesenheit laut Stempel',
      // Puffer-Wortlaut wie Settings.tsx (Spec 16.1/12.3): Bestand ohne
      // gespeicherten Puffer nimmt beim Bearbeiten den aktuellen (grace_for_entry).
      'Einträge aus der Zeit vor Version 1.20.0 tragen keinen gespeicherten Puffer und werden bei einer Bearbeitung mit dem aktuellen Puffer gekappt.',
      // Review Task 8: der XLS-Import zeigt die Kappung schon in der Vorschau
      // (HANDBUCH-ADMIN.md Abschnitt 3/12, ImportXls.tsx).
      'XLS-Import – dort schon in der Vorschau sichtbar',
      // Gesamtreview PR4/V1: Grenzfall P18 – ein eingetragenes Ende genau auf
      // dem wirksamen Ende bleibt Echo (end_is_correction, lacks_actual_end).
      'Ebenso bleibt die Kennzeichnung, wenn das eingetragene Ende genau dem angerechneten Ende entspricht (z. B. 18:15)',
    ]) {
      expect(text).toContain(expected);
    }
    expectNoStaleTerms(text);
  });

  it('Mitarbeiter-Handbuch erklärt nicht angerechnete Zeit, Antrag und Profilkarte', () => {
    const text = sectionsText(handbuchMitarbeiterSections);
    for (const expected of [
      '5. Arbeitszeit-Blöcke & Anrechnung',
      '2:30 h zwischen den Blöcken nicht angerechnet',
      'Anrechnung beantragen',
      'Anerkannter Eintrag – Änderung ab morgen per Änderungsantrag oder über die Verwaltung',
      'erst nach Arbeitsende',
      'Pause zwischen den Arbeitsblöcken',
      'Meine Arbeitszeit',
      'Ihre Arbeitszeit wurde ab 01.09.2026 geändert',
      'Nicht angerechnet heißt nicht unbezahlt',
      // Dashboard-Hinweis wie im Code (reclamp_audit.notice_text), Datum
      // beim Bearbeiten gesperrt (#502), echtes Ende 23:59 (V1/P18).
      'Hinweis zu Ihrer Arbeitszeit',
      '(neu: 40,0 h/Woche auf 4 Arbeitstage)',
      'Das Datum bleibt beim Bearbeiten fest.',
      'Auch ein tatsächliches Ende um 23:59',
      // Gesamtreview PR4/V1: beide Grenzfälle P18 (wirksames Ende 23:59 bzw.
      // genau das angerechnete Ende) wie HANDBUCH-MITARBEITER.md Abschnitt 3.3,
      // und der 409 der Abwesenheitsbuchung an einem anerkannten Tag
      // (absences.create_absence, CREDIT_OVERRIDE_ABSENCE_DETAIL — eigener Text
      // seit Gesamtreview 1.20 B1).
      'Ist das angerechnete Ende bereits 23:59 – etwa an einem Tag ohne Arbeitszeit-Blöcke –, bleibt die Kennzeichnung „automatisch geschlossen" stehen; angerechnet wird dann ohnehin bis 23:59.',
      'Ebenso bleibt die Kennzeichnung, wenn das eingetragene Ende genau dem angerechneten Ende entspricht (z. B. 18:15)',
      'gibt es einen anerkannten Zeiteintrag – bitte an die Verwaltung wenden.',
    ]) {
      expect(text).toContain(expected);
    }
    expectNoStaleTerms(text);
  });

  it('Kurzanleitungen und Schnellstart nennen Knopf, Modus und Anrechnung', () => {
    const admin = textOf(<CheatsheetAdmin />);
    for (const expected of [
      'Arbeitszeit anpassen…',
      'Nach Arbeitsblöcken',
      'Anerkennen',
      'Nicht angerechnet (Min)',
      'Neue:r Mitarbeiter:in',
      'nur an der jüngsten Zeile',
      // Gesamtreview PR4/V1: Auto-Close wie CHEATSHEET-ADMIN.md (Arbeitszeit-Blöcke).
      'rechnet nur bis zum letzten Block + Puffer an',
      'auch ein echtes Ende 23:59 ist eintragbar',
    ]) {
      expect(admin).toContain(expected);
    }
    expectNoStaleTerms(admin);

    const ma = textOf(<CheatsheetMitarbeiter />);
    for (const expected of [
      'zwischen den Blöcken nicht angerechnet',
      'Anrechnung beantragen',
      'Meine Arbeitszeit',
      'nur für heute',
      'Pause in der Lücke wird zusätzlich abgezogen',
    ]) {
      expect(ma).toContain(expected);
    }
    expectNoStaleTerms(ma);

    const start = textOf(<SchnellstartAdmin />);
    expect(start).toContain('Arbeitszeit anpassen…');
    expect(start).toContain('Nach Arbeitsblöcken');
    expectNoStaleTerms(start);
  });

  it('Kontexthilfe zu Benutzerverwaltung, Zeiterfassung, Profil und Anträgen ist nachgezogen', () => {
    const users = textOf(helpContent['/admin/users'].content);
    expect(users).toContain('Arbeitszeit anpassen…');
    expect(users).toContain('Neue:r Mitarbeiter:in');
    expectNoStaleTerms(users);
    // Review Task 8: HelpPanel zeigt die Kontexthilfe allen Rollen — „nur für
    // heute", „Antrag" und das gesperrte Datum gelten nur für Mitarbeitende
    // (TimeTracking.tsx: Knopf „Antrag" nur !isAdmin, dateLocked nur !isAdmin).
    const tracking = textOf(helpContent['/time-tracking'].content);
    expect(tracking).toContain('Anrechnung beantragen');
    expect(tracking).toContain('(Mitarbeitende: nur für heute;');
    expect(tracking).toContain('Für Mitarbeitende ist beim Bearbeiten das Datum gesperrt.');
    expect(tracking).toContain('Admins ändern das Datum direkt.');
    expect(tracking).not.toContain('Beim Bearbeiten ist das Datum gesperrt.');
    expect(textOf(helpContent['/profile'].content)).toContain('Meine Arbeitszeit');
    expect(textOf(helpContent['/admin/change-requests'].content)).toContain('Genehmigen und anerkennen');
    expect(textOf(helpContent['/admin/change-requests'].content)).toContain('Ohne Anerkennen genehmigen');
    const reports = textOf(helpContent['/admin/reports'].content);
    expect(reports).toContain('Nicht angerechnet (Min)');
    expect(reports).toContain('Monatsreport und Jahresreport Detailliert');
    expectNoStaleTerms(reports);
  });
});

// Gesamtreview 1.20 B6: die Kontexthilfe der im Zweig geänderten Seiten gegen
// die echte Oberfläche geprüft. Jeder Fall nennt, was die Seite wirklich zeigt
// (Knopf-/Abschnittsname), und was die alte Hilfe fälschlich versprach.
describe('Kontexthilfe entspricht der Oberfläche (Gesamtreview B6)', () => {
  const help = (path: string) => textOf(helpContent[path].content);

  it('Zeiterfassung: ein Monat mit Monatspfeilen, keine Wochenansicht', () => {
    const t = help('/time-tracking');
    expect(t).toContain('„Vorheriger Monat"');
    expect(t).toContain('Wochenleiste');
    expect(t).not.toContain('zwischen Wochen navigieren');
    expect(t).not.toContain('Die aktuelle Woche ist vorausgewählt');
    // Pause ist nicht immer Pflicht — erst ab 6 h, und eine Lücke zwischen den Blöcken zählt.
    expect(t).not.toContain('(Pflicht!)');
  });

  it('Benutzerverwaltung: der Knopf heißt „Deaktivieren", kein Status „Inaktiv" zum Setzen', () => {
    const t = help('/admin/users');
    expect(t).toContain('„Deaktivieren"');
    expect(t).toContain('„Reaktivieren"');
    expect(t).not.toContain('Status auf „Inaktiv" setzen');
    expect(t).toContain('Rolle: Mitarbeiter:in oder Administrator');
  });

  it('Dashboard: Monats-/Wochenübersicht statt Diagramm, keine Karte „heutige Einträge"', () => {
    const t = help('/');
    for (const card of ['Monatssaldo', 'Überstundenkonto', 'Urlaubskonto', 'Urlaubscountdown', 'Letzte Einträge']) {
      expect(t).toContain(card);
    }
    expect(t).toContain('„Monat"/„Woche"');
    expect(t).not.toContain('Balkendiagramm');
    expect(t).not.toContain('Meine heutigen Einträge');
  });

  it('Admin-Dashboard: Ampel nach Resturlaub-Tagen, Umschalter und Soll-Basis', () => {
    const t = help('/admin');
    expect(t).toContain('mehr als 5 Tage');
    expect(t).not.toContain('≥ 50%');
    expect(t).toContain('„bis heute"');
    expect(t).toContain('Anerkennen');
  });

  it('Abwesenheiten (Admin): Betriebsferien mit Verrechnung, keine Mitarbeiterfarben', () => {
    const t = help('/admin/absences');
    expect(t).toContain('„Als Urlaub werten"');
    expect(t).toContain('„Bezahlte Freistellung"');
    expect(t).toContain('„Betriebsferien erstellen"');
    expect(t).not.toContain('Betriebsferien ziehen keine Urlaubstage ab');
    expect(t).not.toContain('Jeder MA hat eine eigene Farbe');
  });

  it('Abwesenheiten (MA): löschen in „Meine Abwesenheiten", Halbtag, eigene Gründe, Anträge', () => {
    const t = help('/absences');
    expect(t).toContain('„Meine Abwesenheiten"');
    expect(t).toContain('Halber Tag');
    expect(t).toContain('Eigene Gründe');
    expect(t).toContain('„Meine Anträge"');
    expect(t).not.toContain('Im Kalender auf den farbigen Eintrag klicken');
  });

  it('Änderungsprotokoll: Monat + Mitarbeitende, Karte „Konto-Vorgänge"', () => {
    const t = help('/admin/audit-log');
    expect(t).toContain('Konto-Vorgänge');
    expect(t).toContain('Anrechnung anerkannt');
    expect(t).not.toContain('Aktionstyp');
  });

  it('Änderungsanträge: Titel wie die Seite, MA verfolgen den Stand im Tab „Anträge"', () => {
    expect(helpContent['/admin/change-requests'].title).toBe('Änderungsanträge');
    const t = help('/admin/change-requests');
    expect(t).toContain('Tab „Anträge"');
    expect(t).toContain('„Alle … auswählen"');
    expect(t).not.toContain('Bereich „Korrekturanträge"');
  });

  it('Profil: Name und E-Mail ändert man selbst; 2FA und Datenexport sind erwähnt', () => {
    const t = help('/profile');
    expect(t).not.toContain('Persönliche Daten (Name, Wochenstunden) können nur vom Admin geändert werden');
    expect(t).toContain('„Bearbeiten"');
    expect(t).toContain('„Aktuelles Passwort"');
    expect(t).toContain('Zwei-Faktor');
    expect(t).toContain('„Meine Daten exportieren"');
  });

  it('Berichte: Formate je Export', () => {
    const t = help('/admin/reports');
    expect(t).toContain('Excel, ODS oder PDF');
  });

  it('Fallback und tote Route: kein Knopf „Neuer Antrag"', () => {
    expect(textOf(getFallbackHelp().content)).not.toContain('Neuer Antrag');
    // /change-requests leitet auf /time-tracking?tab=requests um — die Hilfe
    // dort sieht nie jemand (HelpPanel schlägt den Pfad nach).
    expect(helpContent['/change-requests']).toBeUndefined();
  });
});
