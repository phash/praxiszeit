import { describe, it, expect } from 'vitest';
import type { TimeEntryChange } from './workingHoursTypes';
import { defaultSelection, losingEntries, pruneSelection, recognizableLosingIds, recognizeRowText } from './recognizeSelection';

// Plan 2026-11-21 Task 6: Kundenfall — Blöcke nur noch Mo + Di ab 01.10.2026.
const change = (over: Partial<TimeEntryChange> & { entry_id: string; date: string }): TimeEntryChange => ({
  old_start: '07:50:00', old_end: '12:05:00', old_uncredited: 0, old_net: 4.25,
  new_start: '07:50:00', new_end: '07:50:00', new_uncredited: 0, new_net: 0, not_extendable: null,
  recognizable: true, recognized: false, blockless_workday: false, newly_clamped: false,
  ...over,
});

const BLOCKLESS = change({ entry_id: 'wed', date: '2026-10-07', blockless_workday: true });
const NEWLY = change({ entry_id: 'mon', date: '2026-10-05', newly_clamped: true, new_net: 3.5 });
const EDGE = change({ entry_id: 'edge', date: '2026-10-12', new_net: 4, new_start: '07:55:00' });
const AUTO = change({ entry_id: 'auto', date: '2026-10-08', blockless_workday: true, recognizable: false });
const GAIN = change({ entry_id: 'gain', date: '2026-10-13', old_net: 3, new_net: 3.5, blockless_workday: true });

describe('recognizeSelection (Plan 2026-11-21 Task 6)', () => {
  it('losingEntries keeps only entries that lose credited time', () => {
    expect(losingEntries([BLOCKLESS, GAIN, EDGE]).map((c) => c.entry_id)).toEqual(['wed', 'edge']);
  });

  it('Vorauswahl nimmt den Tag ohne Block und den neu gekappten Eintrag', () => {
    expect([...defaultSelection([BLOCKLESS, NEWLY, EDGE])].sort()).toEqual(['mon', 'wed']);
  });

  it('ein am Rand eines bestehenden Blocks gekappter Eintrag wird nicht gewählt', () => {
    expect(defaultSelection([EDGE]).size).toBe(0);
  });

  it('ein nicht anerkennbarer Eintrag wird nie gewählt', () => {
    expect(defaultSelection([AUTO]).size).toBe(0);
    expect(recognizableLosingIds([AUTO, BLOCKLESS, EDGE])).toEqual(['edge', 'wed']);
    expect(pruneSelection(['auto', 'wed'], [AUTO, BLOCKLESS])).toEqual(['wed']);
  });

  it('a gaining entry is never preselected (it loses nothing)', () => {
    expect(defaultSelection([GAIN]).size).toBe(0);
  });

  it('pruneSelection drops IDs missing from the new preview and keeps a sorted list', () => {
    expect(pruneSelection(['wed', 'gone', 'edge'], [BLOCKLESS, EDGE])).toEqual(['edge', 'wed']);
  });

  it('row text: weekday, date, stamped span, before → after in H:MM', () => {
    expect(recognizeRowText(BLOCKLESS)).toBe('Mi 07.10. · gestempelt 07:50–12:05 · bisher 4:15 h → neu 0:00 h');
  });
});
