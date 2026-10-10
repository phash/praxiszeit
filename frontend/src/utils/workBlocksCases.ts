// Spec 2026-10-08, 6.3: Falltabelle K1–K21 — Zwilling von
// backend/tests/work_blocks_cases.py (gleiche IDs, gleiche Werte, Puffer 15).
// `dayBlocks` = was GET /time-entries/clock-status als `blocks_today` für den
// Falltag liefert (Feiertag/Sonntag/track_hours=false → []); `stored` = der
// Eintrag, wie das Backend ihn speichert.
import type { TimeBlock } from '../types/workBlocks';

export interface KCaseFE {
  id: string;
  dayBlocks: TimeBlock[];
  start: string;
  end: string | null;
  creditOverride: boolean;
  stored: {
    start_time: string;
    end_time: string | null;
    raw_start_time: string | null;
    raw_end_time: string | null;
    break_minutes: number;
    uncredited_minutes: number;
    auto_closed: boolean;
    net_hours: number;
  };
  notCredited: number;
}

type Stored = Partial<KCaseFE['stored']> & { start_time: string; end_time: string | null };

const K: TimeBlock[] = [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }];
const K6: TimeBlock[] = [{ start: '08:00', end: '12:00' }, { start: '12:30', end: '16:00' }];
const K17: TimeBlock[] = [
  { start: '07:00', end: '10:00' }, { start: '11:00', end: '13:00' }, { start: '16:00', end: '19:00' },
];
const K19: TimeBlock[] = [{ start: '08:00', end: '10:00' }, { start: '15:00', end: '18:00' }];

function c(
  id: string, dayBlocks: TimeBlock[], start: string, end: string | null,
  stored: Stored, notCredited: number, creditOverride = false,
): KCaseFE {
  return {
    id, dayBlocks, start, end, creditOverride, notCredited,
    stored: {
      raw_start_time: null, raw_end_time: null, break_minutes: 0, uncredited_minutes: 0,
      auto_closed: false, net_hours: 0, ...stored,
    },
  };
}

const DAY_10H_P45: Stored = { start_time: '08:00', end_time: '18:00', break_minutes: 45, net_hours: 9.25 };

export const K_CASES_FE: KCaseFE[] = [
  c('K1', K, '08:00', '18:00', { start_time: '08:00', end_time: '18:00', uncredited_minutes: 150, net_hours: 7.5 }, 150),
  c('K2', K, '13:00', null, { start_time: '13:00', end_time: null }, 0),
  c('K2b', K, '13:00', '18:00', { start_time: '13:00', end_time: '18:00', uncredited_minutes: 105, net_hours: 3.25 }, 105),
  c('K3', K, '12:30', '14:30', { start_time: '12:30', end_time: '14:30', uncredited_minutes: 120 }, 120),
  c('K4', K, '08:00', '12:05', { start_time: '08:00', end_time: '12:05', net_hours: 4.08 }, 0),
  c('K5', K, '08:00', '12:30', { start_time: '08:00', end_time: '12:30', uncredited_minutes: 15, net_hours: 4.25 }, 15),
  c('K6', K6, '08:00', '16:00', { start_time: '08:00', end_time: '16:00', net_hours: 8 }, 0),
  c('K7', K, '07:00', '19:00', {
    start_time: '07:45', end_time: '18:15', raw_start_time: '07:00', raw_end_time: '19:00',
    uncredited_minutes: 150, net_hours: 8,
  }, 240),
  c('K8', K, '05:00', '07:00', {
    start_time: '05:00', end_time: '05:00', raw_start_time: '05:00', raw_end_time: '07:00',
  }, 120),
  c('K9', K, '08:00', '18:00', { start_time: '08:00', end_time: '18:00', break_minutes: 30, uncredited_minutes: 150, net_hours: 7 }, 150),
  c('K10', K, '08:00', '18:00', DAY_10H_P45, 0, true),
  c('K11', [], '08:00', '18:00', DAY_10H_P45, 0),
  c('K12', [], '08:00', '18:00', DAY_10H_P45, 0),
  c('K13', [], '08:00', '18:00', DAY_10H_P45, 0),
  c('K14', K, '08:00', null, { start_time: '08:00', end_time: null }, 0),
  c('K15', K, '08:00', '23:59', {
    start_time: '08:00', end_time: '18:15', raw_end_time: '23:59', uncredited_minutes: 150,
    auto_closed: true, net_hours: 7.75,
  }, 150),
  c('K16', K, '14:30', '18:00', { start_time: '14:30', end_time: '18:00', uncredited_minutes: 15, net_hours: 3.25 }, 15),
  c('K17', K17, '07:00', '19:00', { start_time: '07:00', end_time: '19:00', uncredited_minutes: 180, net_hours: 9 }, 180),
  c('K18', K, '08:00', '18:00', { start_time: '08:00', end_time: '18:00', uncredited_minutes: 150, net_hours: 7.5 }, 150),
  c('K19', K19, '08:00', '18:00', { start_time: '08:00', end_time: '18:00', uncredited_minutes: 270, net_hours: 5.5 }, 270),
  c('K20', K, '07:00', '18:00', {
    start_time: '07:45', end_time: '18:00', raw_start_time: '07:00', uncredited_minutes: 150, net_hours: 7.75,
  }, 195),
  c('K21', K, '08:00', '18:00', { start_time: '08:00', end_time: '18:00', break_minutes: 45, uncredited_minutes: 150, net_hours: 6.75 }, 150),
];
