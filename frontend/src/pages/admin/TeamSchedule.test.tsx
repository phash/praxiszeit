import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ToastProvider } from '../../contexts/ToastContext';
import TeamSchedule from './TeamSchedule';
import type { WeekBlocks } from '../../types/workBlocks';

const getMock = vi.fn();
vi.mock('../../api/client', () => ({
  default: { get: (url: string, config?: unknown) => getMock(url, config) },
}));

// Der Dialog „Arbeitszeit anpassen…" ist eigens getestet — hier zählt nur,
// womit die Übersicht ihn öffnet.
const modalProps: Record<string, unknown>[] = [];
vi.mock('./users/WorkingHoursModal', () => ({
  default: (props: Record<string, unknown>) => {
    modalProps.push(props);
    return <div data-testid="wh-modal">Dialog {String(props.userName)}</div>;
  },
}));

const day = (blocks: [string, string][] = []) => ({
  blocks: blocks.map(([start, end]) => ({ start, end })), pause_minutes: 0,
});
const ANNA: WeekBlocks = [day([['07:30', '13:00'], ['15:00', '18:00']]), day(), day(), day(), day()];
const BERT: WeekBlocks = [day(), day([['08:00', '12:00']]), day(), day([['08:00', '12:00']]), day()];

const schedule = { weekly_hours: 8.5, use_daily_schedule: true, hours_monday: 8.5, hours_tuesday: 0,
  hours_wednesday: 0, hours_thursday: 0, hours_friday: 0, work_days_per_week: 1 };

function rows() {
  return [
    { user_id: 'a', first_name: 'Anna', last_name: 'Arzt', department: 'Ärzte', calendar_color: '#93C5FD',
      track_hours: true, use_fixed_monthly_target: false, blocks: ANNA, legacy: false, schedule,
      next_change: { effective_from: '2026-11-02', blocks: BERT } },
    { user_id: 'b', first_name: 'Bert', last_name: 'Berg', department: 'MFA', calendar_color: '#FCA5A5',
      track_hours: true, use_fixed_monthly_target: false, blocks: BERT, legacy: false, schedule, next_change: null },
    { user_id: 'c', first_name: 'Clara', last_name: 'Clausen', department: 'MFA', calendar_color: '#86EFAC',
      track_hours: true, use_fixed_monthly_target: false, blocks: null, legacy: false, schedule, next_change: null },
  ];
}

function renderPage() {
  return render(<ToastProvider><TeamSchedule /></ToastProvider>);
}

beforeEach(() => {
  modalProps.length = 0;
  getMock.mockReset().mockResolvedValue({ data: rows() });
});

describe('Teamübersicht der Arbeitszeiten', () => {
  it('zeigt alle Personen mit ihren Blöcken und die nächste Änderung', async () => {
    renderPage();
    expect(await screen.findByText('Arzt, Anna')).toBeInTheDocument();
    expect(screen.getByText('Berg, Bert')).toBeInTheDocument();
    expect(screen.getByTitle('Arzt, Anna · Mo 07:30–13:00')).toBeInTheDocument();
    expect(screen.getByText('ab 02.11.2026 neu')).toBeInTheDocument();
    expect(screen.getByText('keine Arbeitszeit-Blöcke')).toBeInTheDocument();
  });

  it('filtert nach Abteilung: Alle / Ärzte / MFA', async () => {
    renderPage();
    await screen.findByText('Arzt, Anna');
    fireEvent.click(screen.getByRole('button', { name: 'MFA' }));
    expect(screen.queryByText('Arzt, Anna')).toBeNull();
    expect(screen.getByText('Berg, Bert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Alle' }));
    expect(screen.getByText('Arzt, Anna')).toBeInTheDocument();
  });

  it('lädt den Stand zum gewählten Datum', async () => {
    renderPage();
    await screen.findByText('Arzt, Anna');
    fireEvent.change(screen.getByLabelText('Stand am'), { target: { value: '2026-11-02' } });
    await waitFor(() => expect(getMock).toHaveBeenLastCalledWith(
      '/admin/team-schedule', { params: { date: '2026-11-02' } }));
  });

  it('ohne Bearbeiten-Schieber lässt sich nichts verschieben', async () => {
    renderPage();
    await screen.findByText('Arzt, Anna');
    expect(screen.getByRole('switch', { name: 'Bearbeiten' })).toHaveAttribute('aria-checked', 'false');
    const block = screen.getByTitle('Arzt, Anna · Mo 07:30–13:00');
    fireEvent.keyDown(block, { key: 'ArrowRight' });
    expect(screen.getByTitle('Arzt, Anna · Mo 07:30–13:00')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Änderung speichern/ })).toBeNull();
  });

  it('mit Bearbeiten: Block verschieben und den Entwurf im Dialog mit Stichtag öffnen', async () => {
    renderPage();
    await screen.findByText('Arzt, Anna');
    fireEvent.click(screen.getByRole('switch', { name: 'Bearbeiten' }));
    const block = screen.getByRole('button', { name: /Arzt, Anna · Mo 15:00–18:00/ });
    fireEvent.keyDown(block, { key: 'ArrowRight' });        // +15 Min
    fireEvent.keyDown(screen.getByRole('button', { name: /Mo 15:15–18:15/ }), { key: 'ArrowRight', shiftKey: true }); // Ende +15
    expect(screen.getByRole('button', { name: /Arzt, Anna · Mo 15:15–18:30/ })).toBeInTheDocument();

    const row = screen.getByTestId('team-row-a');
    fireEvent.click(within(row).getByRole('button', { name: 'Änderung speichern…' }));
    expect(screen.getByTestId('wh-modal')).toHaveTextContent('Anna Arzt');
    const props = modalProps[modalProps.length - 1];
    expect((props.initialBlocks as WeekBlocks)[0].blocks).toEqual([
      { start: '07:30', end: '13:00' }, { start: '15:15', end: '18:30' }]);
    expect(props.userId).toBe('a');
    expect(typeof props.initialEffectiveFrom).toBe('string');
  });

  it('nach einer Tastatur-Verschiebung holt die Seite den Fokus nicht ständig zurück', async () => {
    renderPage();
    await screen.findByText('Arzt, Anna');
    fireEvent.click(screen.getByRole('switch', { name: 'Bearbeiten' }));
    fireEvent.keyDown(screen.getByRole('button', { name: /Arzt, Anna · Mo 07:30–13:00/ }), { key: 'ArrowRight' });
    const chip = screen.getByRole('button', { name: 'Ärzte' });
    chip.focus();
    fireEvent.click(chip);   // neues Rendern
    expect(document.activeElement).toBe(chip);
  });

  it('Verwerfen setzt den Entwurf zurück', async () => {
    renderPage();
    await screen.findByText('Arzt, Anna');
    fireEvent.click(screen.getByRole('switch', { name: 'Bearbeiten' }));
    fireEvent.keyDown(screen.getByRole('button', { name: /Arzt, Anna · Mo 07:30–13:00/ }), { key: 'ArrowLeft' });
    expect(screen.getByRole('button', { name: /Arzt, Anna · Mo 07:15–12:45/ })).toBeInTheDocument();
    fireEvent.click(within(screen.getByTestId('team-row-a')).getByRole('button', { name: 'Verwerfen' }));
    expect(screen.getByRole('button', { name: /Arzt, Anna · Mo 07:30–13:00/ })).toBeInTheDocument();
  });

  it('Personen ohne Blöcke öffnen im Bearbeiten-Modus den Dialog ohne Entwurf', async () => {
    renderPage();
    await screen.findByText('Clausen, Clara');
    fireEvent.click(screen.getByRole('switch', { name: 'Bearbeiten' }));
    fireEvent.click(within(screen.getByTestId('team-row-c')).getByRole('button', { name: 'Ändern…' }));
    expect(modalProps[modalProps.length - 1].initialBlocks).toBeNull();
  });

  it('Altfenster (nur Kappung) zählen weder für die Achse noch für die Besetzung', async () => {
    const legacyWeek: WeekBlocks = [{ blocks: [{ start: '00:00', end: '23:59' }], pause_minutes: null },
      day(), day(), day(), day()];
    getMock.mockResolvedValue({ data: [...rows(), {
      user_id: 'l', first_name: 'Leo', last_name: 'Legacy', department: 'MFA', calendar_color: '#000000',
      track_hours: true, use_fixed_monthly_target: false, blocks: legacyWeek, legacy: true, schedule,
      next_change: null }] });
    renderPage();
    await screen.findByText('Legacy, Leo');
    // Achse bleibt 7–19 Uhr: kein Besetzungsfeld um Mitternacht, Mo 07:00 nur Anna
    expect(screen.queryByTitle('Mo 00:00–00:30: 1 Person')).toBeNull();
    expect(screen.getByTitle('Mo 07:30–08:00: 1 Person')).toBeInTheDocument();
  });

  it('zeigt eine Besetzungszeile je Tag', async () => {
    renderPage();
    await screen.findByText('Arzt, Anna');
    // Di 08:00–08:30: nur Bert
    expect(screen.getByTitle('Di 08:00–08:30: 1 Person')).toBeInTheDocument();
  });
});
