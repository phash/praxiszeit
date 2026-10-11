import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import WorkBlocksEditor from './WorkBlocksEditor';
import { emptyWeek } from '../utils/workBlocks';
import type { WeekBlocks } from '../types/workBlocks';

function Harness({ initial }: { initial: WeekBlocks }) {
  const [week, setWeek] = useState(initial);
  return <WorkBlocksEditor value={week} onChange={setWeek} idPrefix="t" />;
}

const E = { blocks: [], pause_minutes: 0 };

describe('WorkBlocksEditor (Spec 12.1)', () => {
  it('leere Woche: kein Arbeitstag, Block anlegen, Fehlertext beim leeren Block', () => {
    render(<Harness initial={emptyWeek()} />);
    expect(screen.getAllByText('kein Arbeitstag')).toHaveLength(5);
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    expect(screen.getByLabelText('Mo Block 1 von')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Mo, Block 1: Uhrzeit im Format HH:MM angeben.');
  });

  it('zeigt live Gesamtzeit, Pause, Tagessoll und die Wochensumme', () => {
    render(<Harness initial={emptyWeek()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    fireEvent.change(screen.getByLabelText('Mo Block 1 von'), { target: { value: '08:00' } });
    fireEvent.change(screen.getByLabelText('Mo Block 1 bis'), { target: { value: '12:00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Mo: Block hinzufügen' }));
    fireEvent.change(screen.getByLabelText('Mo Block 2 von'), { target: { value: '15:00' } });
    fireEvent.change(screen.getByLabelText('Mo Block 2 bis'), { target: { value: '18:00' } });
    fireEvent.change(screen.getByLabelText('Mo Pause innerhalb der Blöcke (Min)'), { target: { value: '30' } });
    expect(screen.getByTestId('t-day-0')).toHaveTextContent('Gesamtzeit 7:00 h · Pause 0:30 h · Tagessoll 6:30 h');
    expect(screen.getByTestId('t-week')).toHaveTextContent(
      'Woche: Gesamtzeit 7:00 h · Pause 0:30 h · Wochensoll 6:30 h · 1 Arbeitstag');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('Tagessoll minutengenau (Review Focus 5: 7:55 h, nicht 7,92)', () => {
    const week: WeekBlocks = [
      { blocks: [{ start: '07:30', end: '12:00' }, { start: '13:00', end: '16:25' }], pause_minutes: 0 }, E, E, E, E,
    ];
    render(<Harness initial={week} />);
    expect(screen.getByTestId('t-day-0')).toHaveTextContent('Tagessoll 7:55 h');
  });

  it('höchstens drei Blöcke, Entfernen setzt die Pause eines leeren Tages auf 0', () => {
    render(<Harness initial={emptyWeek()} />);
    const add = screen.getByRole('button', { name: 'Di: Block hinzufügen' });
    fireEvent.click(add);
    fireEvent.click(add);
    fireEvent.click(add);
    expect(add).toBeDisabled();
    // „+ Block“ setzt die Pause eines leeren Tages schon auf 0 — erst eine Pause ≠ 0 zeigt,
    // dass das Entfernen des letzten Blocks sie zurücksetzt. Sonst stünde „Di: Pause nur an
    // Tagen mit Blöcken.“ da, ohne dass es für Di noch ein Pausenfeld gibt.
    fireEvent.change(screen.getByLabelText('Di Pause innerhalb der Blöcke (Min)'), { target: { value: '30' } });
    for (const n of [3, 2, 1]) fireEvent.click(screen.getByRole('button', { name: `Di Block ${n} entfernen` }));
    expect(screen.getAllByText('kein Arbeitstag')).toHaveLength(5);
    expect(screen.queryByRole('alert')).toHaveTextContent('Mindestens ein Wochentag braucht einen Block.');
  });

  it('leere Pause verlangt eine Angabe, Altwerte melden das Raster (Review Focus 4)', () => {
    const legacy: WeekBlocks = [{ blocks: [{ start: '07:37', end: '23:59' }], pause_minutes: null }, E, E, E, E];
    render(<Harness initial={legacy} />);
    expect(screen.getByLabelText('Mo Block 1 von')).toHaveValue('07:37');
    expect(screen.getByRole('alert')).toHaveTextContent('Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05).');
    fireEvent.change(screen.getByLabelText('Mo Block 1 von'), { target: { value: '07:35' } });
    fireEvent.change(screen.getByLabelText('Mo Block 1 bis'), { target: { value: '16:30' } });
    expect(screen.getByRole('alert')).toHaveTextContent('Mo: Pause angeben (0, wenn keine).');
  });

  it('Bearbeiten eines anderen Tages lässt Altwerte unverändert und liefert immer fünf Tage', () => {
    const onChange = vi.fn();
    const legacyMonday = { blocks: [{ start: '07:37', end: '23:59' }], pause_minutes: null };
    render(<WorkBlocksEditor value={[legacyMonday]} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Di: Block hinzufügen' }));
    expect(onChange).toHaveBeenCalledWith([
      legacyMonday,
      { blocks: [{ start: '', end: '' }], pause_minutes: 0 },
      E, E, E,
    ]);
  });
});
