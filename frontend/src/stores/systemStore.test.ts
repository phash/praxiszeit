import { describe, it, expect, beforeEach } from 'vitest';
import { useSystemStore, DEFAULT_SHIFT_WEEKDAYS } from './systemStore';

function setInfo(partial: Record<string, unknown>) {
  useSystemStore.setState({
    info: { deployment_mode: 'onprem', version: '', ...partial } as any,
    isLoaded: true,
  });
}

describe('systemStore.getShiftPlanningWeekdays (#371)', () => {
  beforeEach(() => {
    useSystemStore.setState({ info: null, isLoaded: false });
  });

  it('defaults to Mo–Fr when info is not loaded', () => {
    expect(useSystemStore.getState().getShiftPlanningWeekdays()).toEqual(DEFAULT_SHIFT_WEEKDAYS);
    expect(DEFAULT_SHIFT_WEEKDAYS).toEqual([0, 1, 2, 3, 4]);
  });

  it('defaults to Mo–Fr when the field is missing or empty', () => {
    setInfo({});
    expect(useSystemStore.getState().getShiftPlanningWeekdays()).toEqual([0, 1, 2, 3, 4]);
    setInfo({ shift_planning_weekdays: [] });
    expect(useSystemStore.getState().getShiftPlanningWeekdays()).toEqual([0, 1, 2, 3, 4]);
  });

  it('returns the configured weekdays, sorted', () => {
    setInfo({ shift_planning_weekdays: [4, 0, 2] });
    expect(useSystemStore.getState().getShiftPlanningWeekdays()).toEqual([0, 2, 4]);
  });

  it('supports a weekend-only configuration', () => {
    setInfo({ shift_planning_weekdays: [5, 6] });
    expect(useSystemStore.getState().getShiftPlanningWeekdays()).toEqual([5, 6]);
  });
});
