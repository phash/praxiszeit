import { describe, it, expect } from 'vitest';
import { BEHAVIOR_LABELS, BEHAVIOR_HINTS, ABSENCE_REASON_PRESETS } from './absenceReasons';

describe('#376 absence reason behavior + presets', () => {
  it('exposes an unpaid_free label + hint', () => {
    expect(BEHAVIOR_LABELS.unpaid_free).toBe('Unbezahlt frei');
    expect(BEHAVIOR_HINTS.unpaid_free).toMatch(/§45 SGB V/);
  });

  it('ships a Kind-krank preset that tracks the child-sick limit', () => {
    const kk = ABSENCE_REASON_PRESETS.find((p) => p.name === 'Kind krank');
    expect(kk).toBeTruthy();
    expect(kk!.base_behavior).toBe('unpaid_free');
    expect(kk!.tracks_child_sick_limit).toBe(true);
  });

  it('only the Kind-krank preset tracks the limit', () => {
    const tracking = ABSENCE_REASON_PRESETS.filter((p) => p.tracks_child_sick_limit);
    expect(tracking.map((p) => p.name)).toEqual(['Kind krank']);
  });
});
