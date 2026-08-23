import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import WeekGrid from './WeekGrid';
import type { ShiftSlot } from '../../api/shiftPlanning';

const slot = (over: Partial<ShiftSlot> = {}): ShiftSlot => ({
  id: 's1',
  workstation_id: 'w1',
  workstation_name: 'Anmeldung und Tresen',
  color: '#2563eb',
  weekday: 0,
  start_time: '08:00',
  end_time: '12:00',
  min_staff: 1,
  understaffed: false,
  note: null,
  assignments: [
    { id: 'a1', user_id: 'u1', user_name: 'Annemarie Kettenhofen' },
    { id: 'a2', user_id: 'u2', user_name: 'Carla Dornbusch' },
  ],
  ...over,
});

describe('WeekGrid', () => {
  it('zeigt den vollen Arbeitsplatznamen ohne truncate-Klasse', () => {
    render(<WeekGrid slots={[slot()]} weekdays={[0, 1, 2, 3, 4]} />);
    const label = screen.getByText('Anmeldung und Tresen');
    expect(label.className).not.toContain('truncate');
  });

  it('zeigt alle zugewiesenen Namen', () => {
    render(<WeekGrid slots={[slot()]} weekdays={[0, 1, 2, 3, 4]} />);
    expect(screen.getByText(/Annemarie Kettenhofen/)).toBeInTheDocument();
    expect(screen.getByText(/Carla Dornbusch/)).toBeInTheDocument();
  });

  it('zeigt den Hinweis, wenn einer gesetzt ist', () => {
    render(<WeekGrid slots={[slot({ note: 'Einarbeitung Azubi' })]} weekdays={[0, 1, 2, 3, 4]} />);
    expect(screen.getByText(/Einarbeitung Azubi/)).toBeInTheDocument();
  });

  it('zeigt keine Hinweiszeile ohne Hinweis', () => {
    render(<WeekGrid slots={[slot()]} weekdays={[0, 1, 2, 3, 4]} />);
    expect(screen.queryByText(/↳/)).not.toBeInTheDocument();
  });

  it('markiert einen Block, dessen Inhalt über das Zeitfenster reicht', () => {
    const tight = slot({
      start_time: '08:00',
      end_time: '08:30',
      assignments: [
        { id: 'a1', user_id: 'u1', user_name: 'Eins' },
        { id: 'a2', user_id: 'u2', user_name: 'Zwei' },
        { id: 'a3', user_id: 'u3', user_name: 'Drei' },
        { id: 'a4', user_id: 'u4', user_name: 'Vier' },
      ],
    });
    render(<WeekGrid slots={[tight]} weekdays={[0, 1, 2, 3, 4]} />);
    expect(screen.getByTitle(/über das Zeitfenster hinaus/i)).toBeInTheDocument();
  });

  it('markiert einen ausreichend langen Block nicht', () => {
    render(<WeekGrid slots={[slot()]} weekdays={[0, 1, 2, 3, 4]} />);
    expect(screen.queryByTitle(/über das Zeitfenster hinaus/i)).not.toBeInTheDocument();
  });
});
