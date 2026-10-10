import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import MyWorkScheduleCard from './MyWorkScheduleCard';

// Spec 2026-10-08, Abschnitt 14 / E67: Profilkarte „Meine Arbeitszeit".

const getMock = vi.fn();
vi.mock('../api/client', () => ({ default: { get: (...a: unknown[]) => getMock(...a) } }));

const NONE = { blocks: [], pause_minutes: 0 };
const WEEK = [
  { blocks: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }], pause_minutes: 30 },
  { blocks: [{ start: '08:00', end: '13:00' }], pause_minutes: 0 },
  NONE,
  { blocks: [{ start: '08:00', end: '12:00' }], pause_minutes: 0 },
  NONE,
];

beforeEach(() => {
  getMock.mockReset();
});

describe('<MyWorkScheduleCard />', () => {
  it('zeigt je Wochentag die heutigen Blöcke mit Tagessoll und den Verlauf', async () => {
    getMock.mockResolvedValue({
      data: {
        today: { date: '2026-10-08', blocks: WEEK, day_targets: [6.5, 5, 0, 4, 0], weekly_hours: 15.5 },
        history: [
          { effective_from: '2026-01-01', effective_until: '2026-08-31', blocks: null,
            day_targets: [8, 8, 8, 8, 8], weekly_hours: 40 },
          { effective_from: '2026-09-01', effective_until: null, blocks: WEEK,
            day_targets: [6.5, 5, 0, 4, 0], weekly_hours: 15.5 },
        ],
      },
    });
    render(<MyWorkScheduleCard />);
    const today = await screen.findByRole('list', { name: 'Arbeitszeit heute' });
    expect(within(today).getByText('Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Tagessoll 6:30 h')).toBeInTheDocument();
    expect(within(today).getByText('Mi – · Tagessoll 0:00 h')).toBeInTheDocument();
    expect(screen.getByText('Wochenstunden: 15:30 h')).toBeInTheDocument();
    const history = screen.getByRole('list', { name: 'Verlauf der Arbeitszeit' });
    expect(within(history).getByText('ab 01.01.2026 bis 31.08.2026: keine Arbeitszeit-Blöcke · 40:00 h/Woche')).toBeInTheDocument();
    expect(within(history).getByText(
      'ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Di 08:00–13:00 · Do 08:00–12:00 · 15:30 h/Woche',
    )).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith('/auth/me/work-schedule');
  });

  it('kennzeichnet ein Altfenster (nur Anrechnung, kein Tagessoll)', async () => {
    const legacy = [
      { blocks: [{ start: '07:30', end: '16:30' }], pause_minutes: null },
      { blocks: [], pause_minutes: null }, { blocks: [], pause_minutes: null },
      { blocks: [], pause_minutes: null }, { blocks: [], pause_minutes: null },
    ];
    getMock.mockResolvedValue({
      data: { today: { date: '2026-10-08', blocks: legacy, day_targets: [8, 8, 8, 8, 8], weekly_hours: 40 }, history: [] },
    });
    render(<MyWorkScheduleCard />);
    expect(await screen.findByText(/begrenzen nur die Anrechnung/)).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Verlauf der Arbeitszeit' })).not.toBeInTheDocument();
  });

  it('rendert nichts, wenn der Abruf scheitert', async () => {
    getMock.mockRejectedValue(new Error('offline'));
    const { container } = render(<MyWorkScheduleCard />);
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
