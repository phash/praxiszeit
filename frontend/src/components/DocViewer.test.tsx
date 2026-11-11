import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import {
  CheatsheetAdmin,
  CheatsheetMitarbeiter,
  SchnellstartAdmin,
} from './DocViewer';
import { getFallbackHelp, helpContent } from '../constants/helpContent';
import HandbookPage from '../handbuch/components/HandbookPage';
import { HANDBOOKS } from '../handbuch/content/index';
import { FORBIDDEN_TERMS } from '../handbuch/content/forbiddenTerms';
import manifestJson from '../handbuch/manifest.json';
import type { HandbookId, Manifest } from '../handbuch/types';

// Sichtbarer Text einer Doku-Fläche, Leerraum zusammengefasst.
function textOf(node: ReactNode): string {
  const { container, unmount } = render(<div>{node}</div>);
  const text = (container.textContent ?? '').replace(/\s+/g, ' ');
  unmount();
  return text;
}

// Sichtbarer Text eines Handbuchs (Inhalt unter frontend/src/handbuch), wie ihn
// die Hilfeseite zeigt. Die Pflichtwörter dieser Datei gelten seit der Umstellung
// auf das grafische Handbuch dem Inhalt, nicht mehr DocViewer.tsx.
function handbookText(id: HandbookId): string {
  return textOf(
    <HandbookPage
      handbook={HANDBOOKS[id]}
      manifest={manifestJson as Manifest}
      imgBase="/help/img"
      linkBase="/help"
      variant="wide"
    />,
  );
}

// Sichtbarer Text eines einzelnen Kapitels – damit eine Prüfung nicht an einer Stelle
// eines anderen Kapitels „erfüllt" wird.
function chapterText(id: HandbookId, chapterId: string): string {
  const book = HANDBOOKS[id];
  const chapters = book.chapters.filter((c) => c.id === chapterId);
  if (chapters.length !== 1) throw new Error(`Kapitel ${chapterId} nicht in ${id}`);
  return textOf(
    <HandbookPage
      handbook={{ ...book, chapters }}
      manifest={manifestJson as Manifest}
      imgBase="/help/img"
      linkBase="/help"
      variant="wide"
    />,
  );
}

// Bedienung und Begriffe, die es seit 1.20.0 nicht mehr gibt (Spec E58, 12.2, 15.1):
// Quelle ist handbuch/content/forbiddenTerms.ts (dort auch gegen den Inhalt geprüft).
const VERALTET = FORBIDDEN_TERMS;

function expectNoStaleTerms(text: string) {
  for (const stale of VERALTET) expect(text).not.toContain(stale);
}

describe('In-App-Doku: Arbeitszeit-Blöcke (1.20.0)', () => {
  it('Praxisleitungs-Handbuch beschreibt Dialog, Blöcke, Schutzpaket und Anerkennen', () => {
    const text = handbookText('praxisleitung');
    for (const expected of [
      'Admin-Passwort',
      'reset-admin-password',
      'Arbeitszeit anpassen…',
      'Arbeitszeit & Wochenstunden',
      'Nach Arbeitsblöcken',
      'Pause innerhalb der Blöcke',
      'Tagessoll = Summe der Blöcke minus diese Pause',
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
      'auf den vorherigen Stand zurück',
      'Jeder gekappte Eintrag merkt sich seinen Puffer und behält ihn',
      'Nichtanrechnung ersetzt keine Vergütungsentscheidung',
      'Rückwirkend ab … mit Neuberechnung',
      'nur an der jüngsten Zeile',
      'Unterbrechung (Min), Zeiteinträge',
      'Anwesenheit laut Stempel',
      // Puffer-Wortlaut wie Settings.tsx (Spec 16.1/12.3): Bestand ohne
      // gespeicherten Puffer nimmt beim Bearbeiten den aktuellen (grace_for_entry).
      'Einträge aus der Zeit vor Version 1.20.0 tragen keinen gespeicherten Puffer',
      // XLS-Import zeigt die Kappung schon in der Vorschau (ImportXls.tsx).
      'Unter Netto steht bei gekappten Zeilen die nicht angerechnete Zeit',
      'Werktag ohne Block = 0 Stunden',
      // Wiederhergestellte Hinweise (Task C1): Recht, Altfenster, Rücksetzung, Protokoll, Lücke.
      'Ändert sich durch die Blöcke der Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine Vertragsänderung',
      'mitbestimmungspflichtig; ohne Zustimmung ist die Maßnahme gegenüber den Beschäftigten unwirksam. PraxisZeit prüft das nicht.',
      'Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln (§§ 11, 12 JArbSchG',
      'PraxisZeit prüft nur die Grenzen für Erwachsene',
      'Arbeitszeit-Fenster (Altbestand, nur Kappung)',
      'Bis Version 1.19.2 wurde außerdem ein Feiertag auf einem Werktag wie ein normaler Arbeitstag gekappt',
      'Am 05.10.2026 gibt es einen anerkannten Zeiteintrag – bitte an die Verwaltung wenden.',
      'Auch ein tatsächliches Ende um 23:59',
      'Ebenso bleibt die Kennzeichnung, wenn das eingetragene Ende genau dem angerechneten Ende entspricht (z. B. 18:15)',
      'Eine Änderung, die erst nach heute beginnt, verkürzt beim Löschen nichts',
      'meist heute, morgen, wenn die Person heute schon gestempelt hat oder eingestempelt ist',
      'Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden.',
      'weil in einem zweiten Fenster eine weitere Änderung dazwischen angelegt wurde',
      'Grund, Begründung und Notiz speichert PraxisZeit zusammen im Notizfeld der Änderung, höchstens 500 Zeichen',
      'Notiz und Begründung zusammen höchstens 500 Zeichen.',
      '[Erfassungsfehler korrigiert]',
      '[Einvernehmlich vereinbart]',
      'eine Sammelzeile „Stundenänderung“ ohne Datum',
      'enden die Arbeitszeit-Blöcke mit dieser Änderung',
      'steht im Dialog „geplant“ statt „Tagessoll“ bzw. „Wochensoll“',
      'heute gültigen Stand, auch nach dem Wirkungsdatum einer zukunftsdatierten Änderung',
      'Auch ohne Stundenzählung zählt ein halber freier Tag (Option „Halber Tag“) 0,5 Urlaubstage',
      'Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt',
      'Pause in der Lücke wird zusätzlich abgezogen',
    ]) {
      expect(text).toContain(expected);
    }
    expectNoStaleTerms(text);
  });

  it('Mitarbeitenden-Handbuch erklärt nicht angerechnete Zeit, Antrag und Profilkarte', () => {
    const text = handbookText('mitarbeitende');
    for (const expected of [
      '2:30 h zwischen den Blöcken nicht angerechnet',
      'Anrechnung beantragen',
      'Anerkannter Eintrag – Änderung per Änderungsantrag oder über die Verwaltung',
      'Meine Arbeitszeit',
      'Nicht angerechnet heißt nicht unbezahlt',
      // Dashboard-Hinweis (reclamp_audit.notice_text), Datum beim Bearbeiten
      // gesperrt (#502), Werktag ohne Block = 0 h (1.21).
      'Hinweis zu Ihrer Arbeitszeit',
      'Beim Bearbeiten bleibt das Datum fest.',
      'Es darf nicht in der Zukunft liegen',
      'Werktag ohne Block = freier Tag',
      'Arbeitsende per Antrag nachtragen',
      // Wiederhergestellte Hinweise (Task C1): automatisch geschlossen, 23:59, Lücke, 409 bei Abwesenheit.
      'Auch ein tatsächliches Ende um 23:59',
      'Ebenso bleibt die Kennzeichnung, wenn Sie genau das angerechnete Ende (z. B. 18:15) eintragen',
      'Anerkennen kann die Verwaltung einen solchen Eintrag erst, wenn das tatsächliche Ende eingetragen ist',
      'Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt – eine Ruhepause ist nicht erfasst',
      'Pause in der Lücke wird zusätzlich abgezogen',
      'Am 05.10.2026 gibt es einen anerkannten Zeiteintrag – bitte an die Verwaltung wenden.',
    ]) {
      expect(text).toContain(expected);
    }
    expectNoStaleTerms(text);
  });

  it('Vertragsverlauf: Urlaubsanspruch, Stundenzählung und Minijob gelten ab Datum (Teil A)', () => {
    const handbuch = handbookText('praxisleitung');
    for (const expected of [
      'Urlaub und Abrechnung',
      'Urlaubsanspruch pro Jahr ab diesem Datum',
      'Vorschlag übernehmen',
      'Änderungen an Minijob-Einstellungen gelten immer ab dem Monatsersten.',
    ]) {
      expect(handbuch).toContain(expected);
    }
    expect(textOf(<CheatsheetAdmin />)).toContain('Urlaub und Abrechnung');
    expect(textOf(<SchnellstartAdmin />)).toContain('Urlaubsanspruch pro Jahr ab diesem Datum');
  });

  it('Mitarbeitenden-Handbuch: Name und E-Mail ändert man im Profil selbst (Gesamtreview 1.20)', () => {
    // Profile.tsx zeigt „Bearbeiten" für jede Rolle (PUT /auth/profile, Art. 16
    // DSGVO) — nur Arbeitszeit, Rolle und Urlaubsanspruch legt die Verwaltung fest.
    const text = handbookText('mitarbeitende');
    expect(text).not.toContain('Persönliche Daten wie Name und Wochenstunden können nur vom Administrator geändert werden');
    expect(text).toContain('Vorname, Nachname und E-Mail ändern');
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
    // Gesamtreview 1.20 (Fund 14) wie HANDBUCH-ADMIN.md (Feste Monatsarbeitszeit).
    expect(start).toContain('Mit Arbeitszeit-Blöcken gilt dasselbe: der Block-Editor beschriftet die Werte je Tag und Woche als „geplant".');
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

  // Gesamtreview B6 (Nachzug): der Kasten „Buchung fehlt" steht in Dashboard.tsx
  // ohne md:hidden ÜBER der Stempelkarte — also auch am Computer, und auf dem
  // Smartphone ist dann nicht mehr die Stempelkarte oben.
  it('Dashboard: „Buchung fehlt" ist ein eigener Abschnitt, nicht nur Smartphone', () => {
    const sections = (() => {
      const { container, unmount } = render(<div>{helpContent['/'].content}</div>);
      const byHeading = new Map<string, string>();
      container.querySelectorAll('section').forEach((s) => {
        const heading = s.querySelector('h3')?.textContent ?? '';
        byHeading.set(heading, (s.textContent ?? '').replace(/\s+/g, ' '));
      });
      unmount();
      return byHeading;
    })();
    const missing = sections.get('Buchung fehlt');
    expect(missing).toBeDefined();
    expect(missing).toContain('„Zur Zeiterfassung →"');
    expect(missing).toContain('am Computer wie auf dem Smartphone');
    const phone = sections.get('Auf dem Smartphone') ?? '';
    expect(phone).toContain('„Letzte Einträge"');
    expect(phone).not.toContain('Buchung fehlt');
    expect(phone).not.toContain('Oben die Stempelkarte');
  });

  // Gesamtreview B6 (Nachzug): die Summe steht auch mobil unter den Karten
  // (TimeTracking.tsx, md:hidden-Block „Summe").
  it('Zeiterfassung: die Netto-Summe steht nicht nur am Computer', () => {
    const t = help('/time-tracking');
    expect(t).toContain('(unten mit der Summe der Netto-Stunden)');
    expect(t).not.toContain('am Computer unten mit der Summe');
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
    // Gesamtreview B6 (Nachzug): ein selbst geändertes Passwort steht dort NICHT
    // (security_events kennt nur admin_set_password und die Kommandozeile,
    // SecurityEventsCard.EVENT_LABELS) — „Passwortänderungen" versprach mehr.
    expect(t).toContain('von der Verwaltung gesetzte Passwörter');
    expect(t).toContain('Notfall-Vorgänge per Kommandozeile');
    expect(t).not.toContain('Rollen- und Passwortänderungen');
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
    // Gesamtreview B6 (Nachzug): der Jahresreport Classic hat in Excel die
    // Monate als Spalten (export_service._create_employee_classic_sheet), in ODS
    // eine Zeile je Monat (ods_export_service._classic_sheet). Die Hilfe sagte
    // beides – jeweils für beide Formate.
    expect(t).toContain('als Excel (Monate als Spalten) oder ODS (eine Zeile je Monat)');
    expect(t).toContain('Der Jahresreport Classic (nur Monatswerte, keine Tageszeilen)');
    expect(t).not.toContain('12 Monate kompakt (Monate als Spalten), als Excel oder ODS');
    expect(t).not.toContain('Classic (eine Zeile je Monat)');
  });

  it('Admin-Kurzanleitung: Classic formatgenau, Änderungsanträge wie Menü und Filter', () => {
    const t = textOf(<CheatsheetAdmin />);
    expect(t).toContain('Der Jahresreport Classic (nur Monatswerte, keine Tageszeilen)');
    expect(t).not.toContain('Classic (eine Zeile je Monat)');
    // Menüpunkt „Änderungsanträge" (Layout.tsx), Filter „Offen"
    // (admin/ChangeRequests.tsx); einen Knopf „Prüfen" gibt es nicht.
    expect(t).toContain('Änderungsanträge prüfen');
    expect(t).toContain('Änderungsanträge → Filter „Offen"');
    expect(t).not.toContain('offene Anträge → Prüfen');
  });

  it('Fallback und tote Route: kein Knopf „Neuer Antrag"', () => {
    expect(textOf(getFallbackHelp().content)).not.toContain('Neuer Antrag');
    // /change-requests leitet auf /time-tracking?tab=requests um — die Hilfe
    // dort sieht nie jemand (HelpPanel schlägt den Pfad nach).
    expect(helpContent['/change-requests']).toBeUndefined();
  });
});

// Gesamtreview 1.20 (migration-native): das Praxisleitungs-Handbuch nennt seit dem
// Docker-Restore-Fix restore.sh bzw. praxiszeit-server.py restore — die frühere
// In-App-Fassung versprach einen „idempotenten" Restore dank --clean --if-exists.
// Genau das stimmte nicht: ein älteres Backup bricht an Tabellen ab, die erst
// eine neuere Version angelegt hat, und ohne Neustart migriert nichts.
describe('Datensicherung: Wiederherstellung wie im Praxisleitungs-Handbuch', () => {
  it('nennt Script, nativen Befehl und den Neustart statt „idempotent"', () => {
    const t = chapterText('praxisleitung', 'datensicherung');
    expect(t).not.toContain('idempotent');
    expect(t).toContain('bash restore.sh');
    expect(t).toContain('praxiszeit-server.py restore');
    expect(t).toContain('restore-backup.bat');
    expect(t).toContain('erst dieser Start');
    expect(t).toContain('docs/BACKUP.md');
  });

  // Audit 2026-11-07, Fix-Runde: signierte Sicherungen und Backup-Ort.
  it('nennt die Signatur, --force-unverified und dass bestehende Ordner unverändert bleiben', () => {
    const t = chapterText('praxisleitung', 'datensicherung');
    expect(t).toContain('Signatur');
    expect(t).toContain('--force-unverified');
    expect(t).toContain('ändert PraxisZeit nicht');
    expect(t).not.toContain('bekommt der gewählte Ordner die Rechte');
  });
});
