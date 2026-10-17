import { describe, it, expect } from 'vitest';
import {
  blocksOf, blocksSpan, deriveTargets, emptyWeek, formatBlocksText, formatWeekBlocks, gapSegments, hhmmToMinutes, hullClamp,
  isInBlockGap, isLegacyWeek, minutesToHm, notCreditedMinutes, parseHhmm, runningCreditedMinutes, stampNoteProps, sumBlocks,
  validateWeekBlocks,
} from './workBlocks';
import { K_CASES_FE } from './workBlocksCases';
import type { WeekBlocks } from '../types/workBlocks';

const EMPTY_NEW = { blocks: [], pause_minutes: 0 };
const EMPTY_LEGACY = { blocks: [], pause_minutes: null };

const NEW_WEEK: WeekBlocks = [
  { blocks: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }], pause_minutes: 30 },
  { blocks: [{ start: '08:00', end: '13:00' }], pause_minutes: 0 },
  EMPTY_NEW, EMPTY_NEW, EMPTY_NEW,
];

const LEGACY_WEEK: WeekBlocks = [
  { blocks: [{ start: '07:37', end: '16:30' }], pause_minutes: null },
  EMPTY_LEGACY, EMPTY_LEGACY, EMPTY_LEGACY,
  { blocks: [{ start: '07:30', end: '23:59' }], pause_minutes: null },
];

describe('formatWeekBlocks (Spec 12.2)', () => {
  it('nennt nur Tage mit Blöcken, Pause nur wenn > 0', () => {
    expect(formatWeekBlocks(NEW_WEEK)).toBe('Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Di 08:00–13:00');
  });

  it('zeigt Altwerte und Platzhalter unverändert', () => {
    expect(formatWeekBlocks(LEGACY_WEEK)).toBe('Mo 07:37–16:30 · Fr 07:30–23:59');
  });

  it('liefert null ohne Blöcke', () => {
    expect(formatWeekBlocks(null)).toBeNull();
    expect(formatWeekBlocks(undefined)).toBeNull();
    expect(formatWeekBlocks([EMPTY_NEW, EMPTY_NEW, EMPTY_NEW, EMPTY_NEW, EMPTY_NEW])).toBeNull();
  });
});

describe('isLegacyWeek (Spec 3.3)', () => {
  it('erkennt Altzeilen an pause_minutes null', () => {
    expect(isLegacyWeek(LEGACY_WEEK)).toBe(true);
    expect(isLegacyWeek(NEW_WEEK)).toBe(false);
    expect(isLegacyWeek(null)).toBe(false);
  });
});

describe('notCreditedMinutes — Zwilling von not_credited_minutes (Spec 6.3, P19)', () => {
  it.each(K_CASES_FE.map((k) => [k.id, k] as const))('%s', (_id, k) => {
    expect(notCreditedMinutes(k.stored)).toBe(k.notCredited);
  });
});

// Ultrareview: wortgleich zu backend/tests/test_ultrareview_not_credited_collapse.py —
// jede Hüllen-Seite endet an der Rohspanne (Kollaps nach gekapptem Beginn:
// Einstempeln 05:00 → 07:45, Ausstempeln 06:00 → 07:45–07:45, anwesend 60 Min.).
describe('notCreditedMinutes — Kollaps nach gekapptem Beginn (Ultrareview)', () => {
  const cases: [string, string, string, string | null, string, number, boolean, number][] = [
    ['N1', '07:45', '07:45', '05:00', '06:00', 0, false, 60],
    ['N2', '07:45', '07:45', '07:00', '07:30', 0, false, 30],
    ['N3', '07:45', '18:15', '07:00', '19:00', 150, false, 240],
    ['N4', '19:00', '19:00', null, '20:00', 0, false, 60],
  ];
  it.each(cases)('%s', (_id, s, e, rs, re, unc, ac, exp) => {
    expect(notCreditedMinutes({
      start_time: s, end_time: e, raw_start_time: rs, raw_end_time: re,
      uncredited_minutes: unc, auto_closed: ac,
    })).toBe(exp);
  });
});

// Ultrareview: wortgleich zu backend/tests/test_ultrareview_clock_status.py —
// der laufende Eintrag zählt wie beim Ausstempeln (Hülle + Lücke, Pause ab).
describe('runningCreditedMinutes — laufender Eintrag wie clock_out (Ultrareview)', () => {
  const BLOCKS = [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }];
  const cases: [string, string, number, boolean, number][] = [
    ['16:00', '08:00', 0, false, 330],
    ['13:00', '08:00', 0, false, 255],
    ['19:00', '07:45', 0, false, 480],
    ['16:00', '08:00', 30, false, 300],
    ['07:30', '07:45', 0, false, 0],
    ['16:00', '08:00', 0, true, 480],
  ];
  it.each(cases)('jetzt %s, Beginn %s, Pause %i, anerkannt %s → %i', (now, start, brk, override, exp) => {
    expect(runningCreditedMinutes(BLOCKS, 15, start, hhmmToMinutes(now), brk, override)).toBe(exp);
  });
  it('ohne Blöcke: Wanduhrzeit minus Pause, nie negativ', () => {
    expect(runningCreditedMinutes([], 15, '14:17', hhmmToMinutes('15:27'), 0, false)).toBe(70);
    expect(runningCreditedMinutes(undefined, 15, '15:07', hhmmToMinutes('15:27'), 30, false)).toBe(0);
  });
});

describe('gapSegments — Zwilling von gap_segments (Σ = uncredited_minutes)', () => {
  const closed = K_CASES_FE.filter((k) => k.end !== null && !k.creditOverride);
  it.each(closed.map((k) => [k.id, k] as const))('%s', (_id, k) => {
    const sum = gapSegments(k.dayBlocks, 15, k.start, k.end!).reduce((a, b) => a + b, 0);
    expect(sum).toBe(k.stored.uncredited_minutes);
  });

  it('liefert die Segmente je Lücke (K17)', () => {
    const k17 = K_CASES_FE.find((k) => k.id === 'K17')!;
    expect(gapSegments(k17.dayBlocks, 15, '07:00', '19:00')).toEqual([30, 150]);
  });

  it('eine Lücke ≤ 2 × Puffer verschwindet (K6)', () => {
    const k6 = K_CASES_FE.find((k) => k.id === 'K6')!;
    expect(gapSegments(k6.dayBlocks, 15, '08:00', '16:00')).toEqual([]);
  });

  it('akzeptiert Zeiten mit Sekunden aus der API', () => {
    const k1 = K_CASES_FE.find((k) => k.id === 'K1')!;
    expect(gapSegments(k1.dayBlocks, 15, '08:00:00', '18:00:00')).toEqual([150]);
  });

  // E80: der Puffer ist die variable Eingabe (gespeicherter Puffer des offenen
  // Eintrags bzw. Mandanten-Puffer, clamp_grace_minutes je Eintrag) — Werte wie
  // work_window_service.credit_gaps (test_clamp_grace.py: Puffer 0/10/120).
  it('rechnet mit dem übergebenen Puffer (E80), nicht mit festen 15', () => {
    const B = K_CASES_FE.find((k) => k.id === 'K1')!.dayBlocks;
    expect(gapSegments(B, 0, '08:00', '18:00')).toEqual([180]);
    expect(gapSegments(B, 30, '08:00', '18:00')).toEqual([120]);
    expect(gapSegments(B, 90, '08:00', '18:00')).toEqual([]); // Lücke 180 ≤ 2 × 90
  });
});

// Gesamtreview PR2 (Fund 13): der Server prüft §4 auf der GEKAPPTEN Zeit (E43).
// Die Vorprüfung im Browser zog bis dahin nur die Lückensegmente ab und zählte
// Stempelzeit außerhalb der Hülle als Arbeitszeit — Altfenster = alle Bestandskunden.
describe('hullClamp — Zwilling der Hülle in clamp (Spec 6.1)', () => {
  const closed = K_CASES_FE.filter((k) => k.end !== null && !k.creditOverride);
  it.each(closed.map((k) => [k.id, k] as const))('%s: gespeicherte wirksame Zeiten', (_id, k) => {
    expect(hullClamp(k.dayBlocks, 15, k.start, k.end!)).toEqual({
      start: k.stored.start_time.substring(0, 5),
      end: k.stored.end_time!.substring(0, 5),
    });
  });

  it('Altfenster 08:00–13:30, gestempelt 07:45–14:30 → 07:45–13:45 (6:00 h)', () => {
    expect(hullClamp([{ start: '08:00', end: '13:30' }], 15, '07:45', '14:30'))
      .toEqual({ start: '07:45', end: '13:45' });
  });

  it('Platzhalter 23:59 (halboffenes Altfenster) kappt das Ende nicht', () => {
    expect(hullClamp([{ start: '07:30', end: '23:59' }], 15, '07:00', '23:30'))
      .toEqual({ start: '07:15', end: '23:30' });
  });

  it('ohne Blöcke, über Mitternacht und mit Sekunden', () => {
    expect(hullClamp([], 15, '07:00', '19:00')).toEqual({ start: '07:00', end: '19:00' });
    expect(hullClamp([{ start: '08:00', end: '16:00' }], 15, '22:00', '06:00'))
      .toEqual({ start: '22:00', end: '06:00' });
    expect(hullClamp([{ start: '08:00', end: '16:00' }], 15, '07:00:00', '17:00:00'))
      .toEqual({ start: '07:45', end: '16:15' });
  });
});

describe('isInBlockGap — ungeschrumpfte Lücke (Spec 14, E69)', () => {
  const B = [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }];
  it.each([
    ['07:30', false], ['11:59', false], ['12:00', true], ['12:05', true],
    ['13:00', true], ['14:59', true], ['15:00', false], ['18:30', false],
  ] as const)('%s → %s', (t, expected) => {
    expect(isInBlockGap(B, hhmmToMinutes(t))).toBe(expected);
  });

  it('ohne zweiten Block gibt es keine Lücke', () => {
    expect(isInBlockGap([{ start: '08:00', end: '16:00' }], hhmmToMinutes('12:00'))).toBe(false);
    expect(isInBlockGap(undefined, 600)).toBe(false);
  });
});

describe('blocksSpan', () => {
  it('erster Beginn bis letztes Ende', () => {
    expect(blocksSpan([{ start: '15:00', end: '18:00' }, { start: '08:00', end: '12:00' }]))
      .toEqual({ start: '08:00', end: '18:00' });
    expect(blocksSpan([])).toBeNull();
  });

  // Spec 5.3/3.5: 23:59 als Ende bzw. 00:00 als Beginn sind die Platzhalter
  // halboffener Altfenster aus Migration 073 („kein Ende"/„kein Beginn") —
  // keine Uhrzeit für die Vorbelegung (sonst 07:30–23:59 → DAILY_HOURS_HARD).
  it('liefert null für die Platzhalter halboffener Altfenster', () => {
    expect(blocksSpan([{ start: '07:30', end: '23:59' }])).toBeNull();
    expect(blocksSpan([{ start: '00:00', end: '16:30' }])).toBeNull();
  });
});

describe('stampNoteProps', () => {
  it('baut Roh- und angerechnete Spanne (K7) und nimmt den Serverwert, wenn vorhanden', () => {
    const k7 = K_CASES_FE.find((k) => k.id === 'K7')!;
    const props = stampNoteProps(k7.stored);
    expect(props).toMatchObject({
      rawSpan: '07:00–19:00', effSpan: '07:45–18:15', uncreditedMinutes: 150,
      notCreditedMinutes: 240, creditedHours: 8, breakMinutes: 0, autoClosed: false, creditOverride: false,
    });
    expect(stampNoteProps({ ...k7.stored, not_credited_minutes: 241 }).notCreditedMinutes).toBe(241);
  });
});

describe('formatBlocksText (Spec 15.2, Zwilling von work_blocks_service.blocks_text)', () => {
  const week: WeekBlocks = [
    { blocks: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }], pause_minutes: 30 },
    { blocks: [{ start: '08:00', end: '13:00' }], pause_minutes: 0 },
    EMPTY_NEW, EMPTY_NEW, EMPTY_NEW,
  ];

  it('lang und kurz wie das Backend', () => {
    expect(formatBlocksText(week)).toBe('Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00');
    expect(formatBlocksText(week, { compact: true })).toBe('Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00');
  });

  it('Altwerte ohne Pausenangabe, null ohne Blöcke', () => {
    expect(formatBlocksText(LEGACY_WEEK)).toBe('Mo 07:37–16:30 / Fr 07:30–23:59');
    expect(formatBlocksText(null)).toBeNull();
  });
});

const day = (blocks: [string, string][], pause: number | null = 0) => ({
  blocks: blocks.map(([start, end]) => ({ start, end })), pause_minutes: pause,
});
const E = { blocks: [], pause_minutes: 0 };
const W = (mon: ReturnType<typeof day>, tue: ReturnType<typeof day> | typeof E = E): WeekBlocks => [mon, tue, E, E, E];

describe('deriveTargets (Spec 4.1, wortgleiche Fälle zu test_derive_targets.py)', () => {
  it.each([
    [[['08:00', '12:00'], ['15:00', '18:00']], 30, 6.5],
    [[['08:00', '12:05']], 0, 4.08],
    [[['07:30', '12:00'], ['13:00', '16:25']], 0, 7.92],
  ] as [[string, string][], number, number][])('%j, Pause %i → %f h', (blocks, pause, expected) => {
    const d = deriveTargets(W(day(blocks, pause)));
    expect(d.hours).toEqual([expected, 0, 0, 0, 0]);
    expect([d.weeklyHours, d.workDays]).toEqual([expected, 1]);
  });

  it('drei Blöcke zu 55 Minuten', () => {
    expect(deriveTargets(W(day([['08:00', '08:55'], ['09:00', '09:55'], ['10:00', '10:55']]))).hours[0]).toBe(2.75);
  });

  it('Wochensumme und Arbeitstage (test_week_sum_and_work_days)', () => {
    const d = deriveTargets([day([['08:00', '12:00']]), day([['08:00', '13:00']]), E, day([['08:00', '12:00']]), E]);
    expect([d.weeklyHours, d.workDays, d.hours[2]]).toEqual([13, 3, 0]);
  });
});

describe('validateWeekBlocks (Spec 3.4, wortgleiche Texte zu test_work_blocks_validation.py)', () => {
  const ADJ = 'Mo: Block 2 muss nach dem Ende von Block 1 beginnen; aneinandergrenzende Blöcke bitte als einen Block erfassen.';
  const RASTER = 'Mo: Pause in Minuten im 5-Minuten-Raster angeben.';
  const SHAPE = 'Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet.';
  const withPause = (pause: unknown) => W({ ...day([['08:00', '12:00']]), pause_minutes: pause as number });
  it.each([
    [W(day([['06:00', '07:00'], ['08:00', '09:00'], ['10:00', '11:00'], ['12:00', '13:00']])), 'Mo: höchstens drei Blöcke je Tag.'],
    [W(day([['8:00', '12:00']])), 'Mo, Block 1: Uhrzeit im Format HH:MM angeben.'],
    [W(day([['', '12:00']])), 'Mo, Block 1: Uhrzeit im Format HH:MM angeben.'],
    [W(day([['08:07', '12:00']])), 'Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05).'],
    [W(day([['08:00', '23:59']])), 'Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05).'],
    [W(E, day([['08:00', '12:00'], ['13:00', '12:30']])), 'Di, Block 2: Beginn muss vor dem Ende liegen.'],
    [W(day([['08:00', '12:00'], ['12:00', '13:00']])), ADJ],
    [W(day([['13:00', '14:00'], ['08:00', '12:00']])), ADJ],
    [W(day([['08:00', '12:00'], ['11:00', '14:00']])), ADJ],
    [W(day([['08:00', '12:00']], 240)), 'Mo: Pause muss kürzer sein als die Gesamtzeit der Blöcke.'],
    [W(day([['08:00', '12:00']], null)), 'Mo: Pause angeben (0, wenn keine).'],
    [W(day([['08:00', '12:00']], 7)), RASTER],
    [W(day([['08:00', '12:00']], -5)), RASTER],
    // Spec 3.4 „ganzzahlig": keine Zeichenkette, kein bool (wie das Backend)
    [withPause('30'), RASTER],
    [withPause(true), RASTER],
    [[day([['08:00', '12:00']]), E, { blocks: [], pause_minutes: 15 }, E, E], 'Mi: Pause nur an Tagen mit Blöcken.'],
    [[E, E, E, E, E], 'Mindestens ein Wochentag braucht einen Block.'],
    [Array(5).fill(day([['00:00', '12:05']])), 'Die Wochensumme darf 60 Stunden nicht überschreiten.'],
    // Wortgleich zu ROUNDED_OVER_60 (test_work_blocks_validation.py): 60:00 h
    // Blockzeit, gerundete Σ Tagessoll 11,42 + 11,42 + 12,17 + 12,50 + 12,50 = 60,01 h.
    [[day([['00:00', '11:25']]), day([['00:00', '11:25']]), day([['00:00', '12:10']]),
      day([['00:00', '12:30']]), day([['00:00', '12:30']])], 'Die Wochensumme darf 60 Stunden nicht überschreiten.'],
    [[E, E, E, E], SHAPE],
  ] as [WeekBlocks, string][])('%#: %s', (week, message) => {
    expect(validateWeekBlocks(week)).toBe(message);
  });

  it('kaputte Formen enden in einer Meldung wie im Backend, nie in einem TypeError', () => {
    expect(validateWeekBlocks(null)).toBe(SHAPE);
    expect(validateWeekBlocks('kaputt' as unknown as WeekBlocks)).toBe(SHAPE);
    expect(validateWeekBlocks([null, E, E, E, E] as unknown as WeekBlocks)).toBe(SHAPE);
    for (const blocks of [5, { start: '08:00', end: '12:00' }, '08:00-12:00']) {
      expect(validateWeekBlocks([{ blocks, pause_minutes: 0 }, E, E, E, E] as unknown as WeekBlocks))
        .toBe('Mo: Tag nicht in der Form {blocks, pause_minutes}.');
    }
    expect(validateWeekBlocks([{ blocks: [null], pause_minutes: 0 }, E, E, E, E] as unknown as WeekBlocks))
      .toBe('Mo, Block 1: Uhrzeit im Format HH:MM angeben.');
    // Wie `day.get("blocks") or []` auch dann, wenn ein ANDERER Tag Blöcke hat —
    // die Wochensumme (deriveTargets) liest dann ebenfalls „keine Blöcke".
    const mo = day([['08:00', '12:00']]);
    expect(validateWeekBlocks([mo, { blocks: null, pause_minutes: 0 }, E, E, E] as unknown as WeekBlocks)).toBeNull();
    expect(validateWeekBlocks([mo, { pause_minutes: 0 }, E, E, E] as unknown as WeekBlocks)).toBeNull();
    // Ein leeres Objekt ist in Python falsy (`{} or []` → []), in JS truthy —
    // das Backend liest es als „keine Blöcke", nicht als kaputte Form.
    expect(validateWeekBlocks([{ blocks: {}, pause_minutes: 15 }, mo, E, E, E] as unknown as WeekBlocks))
      .toBe('Mo: Pause nur an Tagen mit Blöcken.');
    expect(validateWeekBlocks([mo, E, E, E, { blocks: {}, pause_minutes: 0 }] as unknown as WeekBlocks)).toBeNull();
  });

  it('Grenzwerte sind gültig', () => {
    expect(validateWeekBlocks(W(day([['06:00', '07:00'], ['08:00', '09:00'], ['10:00', '11:00']])))).toBeNull();
    // Wie test_boundaries_are_valid: Raster 08:05 und Pause = Σ − 5 als zwei getrennte Fälle.
    expect(validateWeekBlocks(W(day([['08:05', '12:00']])))).toBeNull();
    expect(validateWeekBlocks(W(day([['08:00', '12:00']], 235)))).toBeNull();
    expect(validateWeekBlocks(Array(5).fill(day([['00:00', '12:00']])))).toBeNull();
    expect(validateWeekBlocks(W(day([['08:00', '23:55']])))).toBeNull();
  });
});

describe('blocksOf — „keine Blöcke" wie `day.get("blocks") or []` (eine Quelle für Editor und Rechnung)', () => {
  it('eine Blockliste kommt unverändert zurück', () => {
    const mo = day([['08:00', '12:00']]);
    expect(blocksOf(mo)).toBe(mo.blocks);
  });

  it('fehlender Tag, fehlende/leere Blöcke und ein leeres Objekt sind „keine Blöcke"', () => {
    for (const d of [null, undefined, { pause_minutes: 0 }, { blocks: null, pause_minutes: 0 }, { blocks: {}, pause_minutes: 0 }]) {
      expect(blocksOf(d as unknown as WeekBlocks[number])).toEqual([]);
    }
  });
});

describe('parseHhmm (streng, Zwilling von work_blocks_service.hhmm_to_minutes)', () => {
  it('nur HH:MM mit ASCII-Ziffern im Bereich 00:00–23:59', () => {
    expect([parseHhmm('00:00'), parseHhmm('08:05'), parseHhmm('23:59')]).toEqual([0, 485, 1439]);
    for (const bad of ['8:00', '08:00:00', '24:00', '12:60', '', '０８:００', null, undefined]) {
      expect(parseHhmm(bad)).toBeNull();
    }
  });
});

describe('sumBlocks / minutesToHm / emptyWeek', () => {
  it('7:55 h bleibt Minuten-genau (Review Focus 5)', () => {
    const totals = sumBlocks(day([['07:30', '12:00'], ['13:00', '16:25']]));
    expect([totals.grossMinutes, totals.pauseMinutes, totals.netMinutes]).toEqual([475, 0, 475]);
    expect(minutesToHm(475)).toBe('7:55');
  });

  it('unvollständige Blöcke zählen nicht, eine leere Pause zählt 0', () => {
    expect(sumBlocks(day([['08:00', '']], null))).toEqual({ grossMinutes: 0, pauseMinutes: 0, netMinutes: 0 });
  });

  it('leere Woche hat fünf Tage ohne Blöcke mit Pause 0', () => {
    expect(emptyWeek()).toEqual([E, E, E, E, E]);
  });
});
