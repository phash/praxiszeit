import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import RecognizeEntriesList from './RecognizeEntriesList';
import type { TimeEntryChange } from './workingHoursTypes';
import { AUTO_CLOSED_HINT, OPEN_ENTRY_HINT } from '../../../utils/creditOverride';
import { RECOGNIZE_LOSSLESS_NOTE, RECOGNIZE_NOTE } from './workingHoursTexts';

const change = (over: Partial<TimeEntryChange> & { entry_id: string; date: string }): TimeEntryChange => ({
  old_start: '07:50:00', old_end: '12:05:00', old_uncredited: 0, old_net: 4.25,
  new_start: '07:50:00', new_end: '07:50:00', new_uncredited: 0, new_net: 0, not_extendable: null,
  recognizable: true, recognized: false, blockless_workday: false, newly_clamped: false,
  ...over,
});

const WED = change({ entry_id: 'wed', date: '2026-10-07', blockless_workday: true });
const THU = change({
  entry_id: 'thu', date: '2026-10-08', old_end: '12:35:00', old_net: 4.75, blockless_workday: true, recognizable: false,
});
const MON = change({ entry_id: 'mon', date: '2026-10-12', old_start: '07:45:00', old_end: '12:00:00', old_net: 4.25, new_net: 4.08 });
const GAIN = change({ entry_id: 'gain', date: '2026-10-13', old_net: 3, new_net: 3.5 });

describe('RecognizeEntriesList (Plan 2026-11-21 Task 6)', () => {
  it('zeigt je verlierendem Eintrag die Zeile, das Kennzeichen und den Hinweis', () => {
    render(<RecognizeEntriesList changes={[WED, MON, GAIN]} selected={new Set(['wed'])} onChange={() => {}} />);
    expect(screen.getByText('Mi 07.10. · gestempelt 07:50–12:05 · bisher 4:15 h → neu 0:00 h')).toBeInTheDocument();
    expect(screen.getByText('Mo 12.10. · gestempelt 07:45–12:00 · bisher 4:15 h → neu 4:05 h')).toBeInTheDocument();
    // Gewinnt ein Eintrag, verliert er nichts — keine Zeile.
    expect(screen.queryByText(/13\.10\./)).not.toBeInTheDocument();
    expect(screen.getAllByText('Tag ohne Block')).toHaveLength(1);
    expect(screen.getByRole('checkbox', { name: /Mi 07\.10\./ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Mo 12\.10\./ })).not.toBeChecked();
    expect(screen.getByText(RECOGNIZE_NOTE)).toBeInTheDocument();
  });

  it('ein nicht anerkennbarer Eintrag hat ein deaktiviertes Häkchen mit Hinweis', () => {
    render(<RecognizeEntriesList changes={[WED, THU]} selected={new Set()} onChange={() => {}} />);
    const box = screen.getByRole('checkbox', { name: /Do 08\.10\./ });
    expect(box).toBeDisabled();
    expect(box).toHaveAccessibleDescription(AUTO_CLOSED_HINT);
    expect(screen.getByRole('checkbox', { name: /Mi 07\.10\./ })).toBeEnabled();
  });

  it('„Alle auswählen" wählt nur anerkennbare, „Keine" leert die Auswahl', () => {
    const onChange = vi.fn();
    render(<RecognizeEntriesList changes={[WED, THU, MON]} selected={new Set(['wed'])} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Alle auswählen' }));
    expect([...onChange.mock.calls.at(-1)![0]].sort()).toEqual(['mon', 'wed']);
    fireEvent.click(screen.getByRole('button', { name: 'Keine' }));
    expect([...onChange.mock.calls.at(-1)![0]]).toEqual([]);
  });

  it('Häkchen setzen und entfernen meldet die neue Auswahl', () => {
    const onChange = vi.fn();
    render(<RecognizeEntriesList changes={[WED, MON]} selected={new Set(['wed'])} onChange={onChange} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /Mo 12\.10\./ }));
    expect([...onChange.mock.calls.at(-1)![0]].sort()).toEqual(['mon', 'wed']);
    fireEvent.click(screen.getByRole('checkbox', { name: /Mi 07\.10\./ }));
    expect([...onChange.mock.calls.at(-1)![0]]).toEqual([]);
  });

  it('ein offener Eintrag nennt den Grund „offen", nicht „automatisch geschlossen"', () => {
    const OPEN = change({ entry_id: 'open', date: '2026-10-09', old_end: null, recognizable: false });
    render(<RecognizeEntriesList changes={[WED, OPEN]} selected={new Set()} onChange={() => {}} />);
    expect(screen.getByRole('checkbox', { name: /Fr 09\.10\./ })).toHaveAccessibleDescription(OPEN_ENTRY_HINT);
  });

  it('ist nichts anerkennbar, bleibt die Liste mit Hinweis, aber ohne „Alle auswählen"', () => {
    render(<RecognizeEntriesList changes={[THU]} selected={new Set()} onChange={() => {}} />);
    expect(screen.getByRole('checkbox', { name: /Do 08\.10\./ })).toBeDisabled();
    expect(screen.getByText(AUTO_CLOSED_HINT)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Alle auswählen' })).not.toBeInTheDocument();
  });

  it('gesperrt (Option 1): Häkchen deaktiviert, Auswahl sichtbar, Hinweis', () => {
    render(<RecognizeEntriesList changes={[WED, MON]} selected={new Set(['wed'])} onChange={() => {}} disabled />);
    const wed = screen.getByRole('checkbox', { name: /Mi 07\.10\./ });
    expect(wed).toBeDisabled();
    expect(wed).toBeChecked();
    expect(screen.getByText(RECOGNIZE_LOSSLESS_NOTE)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Alle auswählen' })).not.toBeInTheDocument();
  });
});
