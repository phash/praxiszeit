import { describe, it, expect } from 'vitest';
import { DEFAULT_TYPE_COLORS, chipStyle, useTypeColorsStore } from './typeColorsStore';

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

describe('chipStyle', () => {
  it('derives a tinted background, coloured text and border from a hex', () => {
    const s = chipStyle('#2563EB');
    expect(s.color).toBe('#2563EB');
    expect(s.backgroundColor).toBe('#2563EB1A');
    expect(s.borderColor).toBe('#2563EB55');
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
