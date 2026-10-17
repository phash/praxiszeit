import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import WhImpactBox from './WhImpactBox';
import type { WorkingHoursChangePreview } from './workingHoursTypes';

const BASE: WorkingHoursChangePreview = {
  is_retroactive: true, period_start: '2026-09-01', period_end: '2026-10-08',
  current_daily_target: 7, new_daily_target: 6,
  day_targets_current: [7, 4, 0, 4, 0], day_targets_new: [6, 4, 0, 4, 0],
  overtime_before: 12.5, overtime_after: 14.25, vacation_days_before: 10, vacation_days_after: 10,
  affected_absences: 1, blocked_reason: null, closed_years: [], closed_year_warning: null,
};

// Spec 12.1, erster Zustand (Mo-Nachmittag 15–18 → 15–17 ab 01.09.2026).
const FIRST_STATE: WorkingHoursChangePreview = {
  ...BASE,
  grace_minutes: 15,
  changed_weekdays: [0],
  affected_time_entries: 3,
  time_entry_months: [
    { month: '2026-09', entries: 2, net_before: 6, net_after: 4.5 },
    { month: '2026-10', entries: 1, net_before: 3, net_after: 2.25 },
  ],
  time_entry_changes: [{
    entry_id: 'e1', date: '2026-09-14', old_start: '15:00:00', old_end: '18:00:00', old_uncredited: 0, old_net: 3,
    new_start: '15:00:00', new_end: '17:15:00', new_uncredited: 0, new_net: 2.25, not_extendable: null,
  }],
  skipped_time_entries: [{ entry_id: 'e9', date: '2026-09-28', reason: 'credit_override' }],
  not_extendable_count: 0,
  not_extendable_entries: [],
  target_delta_hours: -4,
  credited_delta_hours: -2.25,
  saldo_delta_hours: 1.75,
  absence_f1_adjustments: 0,
  absence_credit_reductions: [],
  stale_entries_closed: 0,
};

describe('WhImpactBox (Spec 12.1)', () => {
  it('zeigt Puffer, geänderte Tage, Einträge je Monat und Übersprungene', () => {
    render(<WhImpactBox preview={FIRST_STATE} />);
    expect(screen.getByText('Auswirkung (Puffer 15 Min) · geänderte Tage: Mo')).toBeInTheDocument();
    expect(screen.getByText('Zeiteinträge: 3 neu berechnet · 1 übersprungen (1 anerkannt)')).toBeInTheDocument();
    expect(screen.getByText('Sep 2026 · 2 Einträge · 6:00 h → 4:30 h')).toBeInTheDocument();
    expect(screen.getByText('Okt 2026 · 1 Eintrag · 3:00 h → 2:15 h')).toBeInTheDocument();
    // Tagessoll in H:MM wie im Block-Editor darüber („Tagessoll 6:00 h") — ein
    // 7:55-h-Tag (gespeichert 7,92) darf hier nicht als „7,92" erscheinen.
    expect(screen.getByText('Tagessoll je Wochentag: Mo 7:00 h → 6:00 h · Di 4:00 h → 4:00 h · Do 4:00 h → 4:00 h'))
      .toBeInTheDocument();
  });

  // Gesamtreview 1.20 (Fund 14, Nachzug): bei fester Monatsarbeitszeit (#377 2b)
  // sind die Tageswerte geplante Anwesenheit — wie der Block-Editor darüber
  // („geplant 6:30 h") und die Fußnote des Dialogs. Ohne den Modus bleibt der
  // Wortlaut „Tagessoll je Wochentag" (E2E, Spickzettel, Handbuch).
  it('feste Monatsarbeitszeit: „Geplante Anwesenheit je Wochentag" statt Tagessoll', () => {
    render(<WhImpactBox preview={FIRST_STATE} plannedPresence />);
    expect(screen.getByText('Geplante Anwesenheit je Wochentag: Mo 7:00 h → 6:00 h · Di 4:00 h → 4:00 h · Do 4:00 h → 4:00 h'))
      .toBeInTheDocument();
    expect(screen.queryByText(/Tagessoll/)).not.toBeInTheDocument();
  });

  it('Kontrolle: plannedPresence={false} lässt „Tagessoll je Wochentag" stehen', () => {
    render(<WhImpactBox preview={FIRST_STATE} plannedPresence={false} />);
    expect(screen.getByText(/^Tagessoll je Wochentag: Mo 7:00 h → 6:00 h/)).toBeInTheDocument();
    expect(screen.queryByText(/Geplante Anwesenheit/)).not.toBeInTheDocument();
  });

  it('Tagessoll mit Rundung: 7,92 h erscheint minutengenau als 7:55 h (Review-Fokus 5)', () => {
    render(<WhImpactBox preview={{ ...FIRST_STATE, day_targets_current: [7, 0, 0, 0, 0], day_targets_new: [7.92, 0, 0, 0, 0] }} />);
    expect(screen.getByText('Tagessoll je Wochentag: Mo 7:00 h → 7:55 h')).toBeInTheDocument();
  });

  it('trennt Soll und angerechnete Zeit (9.4) und zeigt Überstunden in H:MM', () => {
    render(<WhImpactBox preview={FIRST_STATE} />);
    const soll = screen.getByRole('row', { name: /Soll im Zeitraum/ });
    expect(soll).toHaveTextContent('−4:00 h');
    expect(screen.getByRole('row', { name: /Angerechnet/ })).toHaveTextContent('−2:15 h');
    const over = screen.getByRole('row', { name: /Überstunden/ });
    expect(over).toHaveTextContent('+12:30 h');
    expect(over).toHaveTextContent('+14:15 h');
    expect(over).toHaveTextContent('+1:45 h');
  });

  it('Urlaub in Tagen wie im Rest der App (formatDayCount), mit Jahr des Wirkungszeitraums', () => {
    // Zellen einzeln vergleichen: `toHaveTextContent` prüft nur Teilstrings —
    // „0 Tage" stünde schon in „10 Tage", eine doppelte Einheit („−0,5 Tage
    // Tage", `signedDays` liefert die Einheit bereits mit) fiele nicht auf.
    const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((c) => c.textContent);
    const { unmount } = render(<WhImpactBox preview={FIRST_STATE} />);
    expect(cells(screen.getByRole('row', { name: /Urlaub 2026/ }))).toEqual(['10 Tage', '10 Tage', '0 Tage']);
    unmount();

    render(<WhImpactBox preview={{ ...FIRST_STATE, vacation_days_before: 10, vacation_days_after: 9.5 }} />);
    expect(cells(screen.getByRole('row', { name: /Urlaub 2026/ }))).toEqual(['10 Tage', '9,5 Tage', '−0,5 Tage']);
  });

  it('breite Tabelle scrollt auf dem Handy quer statt abgeschnitten zu werden', () => {
    render(<WhImpactBox preview={FIRST_STATE} />);
    expect(screen.getByRole('table').parentElement).toHaveClass('overflow-x-auto');
  });

  it('nennt nicht erweiterbare Einträge mit Datum und Seite (zweiter Zustand)', () => {
    const change = {
      entry_id: 'e2', date: '2026-09-14', old_start: '15:00:00', old_end: '18:15:00', old_uncredited: 0, old_net: 3.25,
      new_start: '15:00:00', new_end: '18:15:00', new_uncredited: 0, new_net: 3.25, not_extendable: 'end' as const,
    };
    render(<WhImpactBox preview={{ ...FIRST_STATE, not_extendable_count: 1, not_extendable_entries: [change] }} />);
    expect(screen.getByText('1 Eintrag ohne Rohstempel – nicht erweiterbar (14.09.2026, Ende 18:15)')).toBeInTheDocument();
  });

  it('meldet geschlossene Alteinträge, F1-Angleichungen (P27) und ArbZG-Befunde', () => {
    const { unmount } = render(<WhImpactBox preview={{
      ...FIRST_STATE, stale_entries_closed: 2, affected_absences: 2, absence_f1_adjustments: 2,
      arbzg_findings: {
        days_over_10_credited_before: 0, days_over_10_credited_after: 0, days_over_10_presence: 1,
        weeks_over_48_credited_before: 3, weeks_over_48_credited_after: 0, weeks_over_48_presence: 3,
      },
    }} />);
    expect(screen.getByText('2 offene Einträge vergangener Tage werden vorher automatisch geschlossen.')).toBeInTheDocument();
    expect(screen.getByText('2 Abwesenheit(en) betroffen.')).toBeInTheDocument();
    // Spec 9.6 (Wortlaut der Zeile aus P27 mit Erklärung): „Misch-Tag" ist sonst
    // nirgends in der Oberfläche erklärt.
    expect(screen.getByText('2 Abwesenheiten an Misch-Tagen angeglichen (Arbeit und Gutschrift am selben Tag)'))
      .toBeInTheDocument();
    expect(screen.getByText('Wochen > 48 h: angerechnet bisher 3, neu 0 · laut Stempel 3')).toBeInTheDocument();
    expect(screen.queryByText(/Tage > 10 h/)).not.toBeInTheDocument();
    unmount();

    render(<WhImpactBox preview={{ ...FIRST_STATE, stale_entries_closed: 1, absence_f1_adjustments: 1 }} />);
    expect(screen.getByText('1 offener Eintrag eines vergangenen Tages wird vorher automatisch geschlossen.')).toBeInTheDocument();
    expect(screen.getByText('1 Abwesenheit an einem Misch-Tag angeglichen (Arbeit und Gutschrift am selben Tag)'))
      .toBeInTheDocument();
  });

  it('ohne F1-Angleichung keine Misch-Tag-Zeile', () => {
    render(<WhImpactBox preview={FIRST_STATE} />);
    expect(screen.queryByText(/Misch-Tag/)).not.toBeInTheDocument();
  });

  it('Einzelheiten: Einträge alt → neu, Übersprungene, gesenkte Gutschriften', () => {
    render(<WhImpactBox preview={{
      ...FIRST_STATE,
      absence_credit_reductions: [{ absence_id: 'a1', date: '2026-09-21', old_hours: 8, new_hours: 4 }],
    }} />);
    expect(screen.queryByText(/14\.09\.2026 15:00–18:00/)).not.toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: 'Einzelheiten' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('14.09.2026 15:00–18:00 → 15:00–17:15 (3:00 h → 2:15 h)')).toBeInTheDocument();
    expect(screen.getByText('28.09.2026 übersprungen: anerkannt')).toBeInTheDocument();
    expect(screen.getByText('Gutschrift 21.09.2026: 8:00 h → 4:00 h')).toBeInTheDocument();
  });

  it('Bestandsantwort ohne neue Felder: nur Abwesenheiten und Tabelle', () => {
    render(<WhImpactBox preview={BASE} />);
    expect(screen.getByText('1 Abwesenheit(en) betroffen.')).toBeInTheDocument();
    expect(screen.queryByText(/Auswirkung \(Puffer/)).not.toBeInTheDocument();
    expect(screen.queryByRole('row', { name: /Soll im Zeitraum/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Einzelheiten' })).not.toBeInTheDocument();
  });
});
