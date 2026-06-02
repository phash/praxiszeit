/**
 * Client-side ArbZG §4 break validation for manual time entries.
 *
 * Mirrors the backend break-validation logic (`break_validation_service.py`):
 * for a working day, breaks of at least 30 min (>6h) resp. 45 min (>9h net)
 * are required. Gaps between separate entries on the same day count as break
 * time only if they are at least 15 min long (§4 Satz 2).
 *
 * §18 ArbZG: leitende Angestellte (`exempt_from_arbzg`) are exempt from these
 * checks — the backend honours the exemption on every write path, so the
 * client must mirror that and skip the validation entirely for exempt users.
 */

/** A closed (start+end) working block on a single day, in minutes-since-midnight. */
export interface BreakBlock {
  start: number;
  end: number;
  /** Declared break minutes for this block. */
  brk: number;
}

/** "HH:MM" → minutes since midnight. */
function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
}

/**
 * Returns the ArbZG §4 break-time error message for the proposed entry, or
 * `null` if the break requirements are satisfied (or no check is required).
 *
 * @param existingBlocks closed entries already on the same day (excluding the
 *   one being edited and any open entries)
 * @param startTime    proposed entry start, "HH:MM"
 * @param endTime      proposed entry end, "HH:MM"
 * @param breakMinutes declared break minutes of the proposed entry
 * @param exempt       §18 ArbZG exemption — when true, no check is performed
 */
export function computeBreakError(
  existingBlocks: BreakBlock[],
  startTime: string,
  endTime: string,
  breakMinutes: number,
  exempt: boolean
): string | null {
  // §18 ArbZG: leitende Angestellte are exempt from break checks.
  if (exempt) return null;

  const start = toMinutes(startTime);
  let end = toMinutes(endTime);
  // Review R3: a shift crossing midnight (e.g. 22:00 → 06:00) has end < start as
  // minutes-since-midnight. Without this the block duration goes negative and
  // the whole §4 break check silently never fires (a night/on-call clock-out
  // bypassed the gate). Treat end < start as the following day.
  if (end < start) end += 24 * 60;

  // Combine the new entry with the other closed entries on the same day, then
  // decide everything on the AGGREGATE — never on the single new entry alone.
  // (NF-2: a single <6h entry can still push an already-worked day over 6h.)
  const allBlocks: BreakBlock[] = [
    ...existingBlocks,
    { start, end, brk: breakMinutes },
  ];
  allBlocks.sort((a, b) => a.start - b.start);

  // §4 Satz 2: only break SEGMENTS of at least 15 min count toward the
  // mandatory break — applies to declared breaks (NF-1, mirrors backend A-M2)
  // and to gaps between entries alike.
  const totalDeclared = allBlocks.reduce((s, b) => s + (b.brk >= 15 ? b.brk : 0), 0);
  let totalGap = 0;
  for (let i = 1; i < allBlocks.length; i++) {
    const gap = allBlocks[i].start - allBlocks[i - 1].end;
    if (gap >= 15) totalGap += gap;
  }
  const totalGross = allBlocks.reduce((s, b) => s + (b.end - b.start), 0);
  const totalNet = totalGross - totalDeclared;
  const totalEffBreak = totalDeclared + totalGap;

  if (totalNet > 540 && totalEffBreak < 45) {
    return 'Bei >9h Arbeitszeit sind mind. 45 Min. Pause erforderlich (ArbZG §4)';
  }
  if (totalNet > 360 && totalEffBreak < 30) {
    return 'Bei >6h Arbeitszeit sind mind. 30 Min. Pause erforderlich (ArbZG §4)';
  }
  // §4 Satz 2: a declared break of 1–14 min is itself an invalid segment. The
  // backend returns a (waiver-able) error here even on short days, so surface
  // it client-side too, so the break-waiver UI gate stays in sync.
  if (breakMinutes > 0 && breakMinutes < 15) {
    return 'Pausenabschnitte müssen mind. 15 Min. betragen (ArbZG §4 Satz 2)';
  }
  return null;
}
