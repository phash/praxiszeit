/**
 * Begriffe und Bedienung, die es seit 1.20.0 nicht mehr gibt (Spec E58, 12.2, 15.1).
 * Kopie von `VERALTET` aus `frontend/src/components/DocViewer.test.tsx`; ab Task 8
 * ist diese Datei die Quelle, DocViewer.test.tsx behält bis Task 16 seine eigene Kopie.
 */
export const FORBIDDEN_TERMS: readonly string[] = [
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
