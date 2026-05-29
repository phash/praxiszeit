import { describe, it, expect } from 'vitest';
import { DEFAULT_TYPE_COLORS, pickTextColor, useTypeColorsStore } from './typeColorsStore';

describe('typeColorsStore defaults', () => {
  it('has all seven type keys', () => {
    expect(Object.keys(DEFAULT_TYPE_COLORS).sort()).toEqual(
      ['other', 'overtime', 'paid_leave', 'sick', 'training', 'vacation', 'work'].sort(),
    );
  });

  it('all defaults are valid #RRGGBB', () => {
    for (const v of Object.values(DEFAULT_TYPE_COLORS)) {
      expect(v).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });
});

describe('pickTextColor', () => {
  it('returns dark text on a light background', () => {
    expect(pickTextColor('#FFEB3B')).toBe('#111827'); // yellow → dark
    expect(pickTextColor('#FFFFFF')).toBe('#111827');
  });

  it('returns white text on a dark background', () => {
    expect(pickTextColor('#2563EB')).toBe('#FFFFFF'); // blue → white
    expect(pickTextColor('#111827')).toBe('#FFFFFF');
  });

  it('falls back to dark for malformed input', () => {
    expect(pickTextColor('nope')).toBe('#111827');
  });
});

describe('colorFor', () => {
  it('returns the configured/default colour for a known type', () => {
    expect(useTypeColorsStore.getState().colorFor('vacation')).toBe(DEFAULT_TYPE_COLORS.vacation);
  });

  it('falls back to a neutral grey for an unknown type', () => {
    expect(useTypeColorsStore.getState().colorFor('does-not-exist')).toBe('#6B7280');
  });
});
