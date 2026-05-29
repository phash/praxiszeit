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

  it('picks dark text on mid-tone colours for WCAG-AA contrast', () => {
    // Regression for the 0.5-threshold bug: these mid-tone defaults previously
    // got white text below 4.5:1. The 0.179 WCAG flip-point gives dark text.
    expect(pickTextColor('#0D9488')).toBe('#111827'); // paid_leave teal
    expect(pickTextColor('#16A34A')).toBe('#111827'); // work green
    expect(pickTextColor('#E5A50A')).toBe('#111827'); // amber
  });

  it('still picks white on genuinely dark colours', () => {
    expect(pickTextColor('#15803D')).toBe('#FFFFFF'); // dark green (training)
    expect(pickTextColor('#7C3AED')).toBe('#FFFFFF'); // purple (overtime)
    expect(pickTextColor('#DC2626')).toBe('#FFFFFF'); // red (sick)
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
