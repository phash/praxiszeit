import { describe, expect, it } from 'vitest';
import { assertSingleVisible, boxInside, computeCrop, markerBadgePosition } from './geometry';

const VP = { w: 1440, h: 900 };

describe('computeCrop', () => {
  it('main crop equals main box clamped to viewport', () => {
    const crop = computeCrop('main', VP, { main: { x: 256, y: -10, w: 1300, h: 1200 }, markers: {} });
    expect(crop).toEqual({ x: 256, y: 0, w: 1184, h: 900 });
  });

  it('around crop unions marker boxes plus pad', () => {
    const crop = computeCrop({ around: ['a', 'b'], pad: 20 }, VP, {
      markers: {
        a: { x: 300, y: 100, w: 200, h: 40 },
        b: { x: 600, y: 300, w: 300, h: 50 },
        c: { x: 0, y: 0, w: 10, h: 10 },
      },
    });
    expect(crop).toEqual({ x: 280, y: 80, w: 640, h: 290 });
  });

  it('around crop is at least 480 wide', () => {
    const crop = computeCrop({ around: ['a'], pad: 10 }, VP, {
      markers: { a: { x: 700, y: 200, w: 100, h: 30 } },
    });
    expect(crop.w).toBe(480);
    // zentriert um die Marker-Box
    expect(crop.x + crop.w / 2).toBeCloseTo(750);
    expect(crop.y).toBe(190);
    expect(crop.h).toBe(50);
  });

  it('around crop stays inside the viewport when widened at the edge', () => {
    const crop = computeCrop({ around: ['a'], pad: 0 }, VP, {
      markers: { a: { x: 10, y: 10, w: 50, h: 20 } },
    });
    expect(crop).toEqual({ x: 0, y: 10, w: 480, h: 20 });
  });

  it('full crop is the viewport', () => {
    expect(computeCrop('full', VP, { markers: {} })).toEqual({ x: 0, y: 0, w: 1440, h: 900 });
    expect(computeCrop(undefined, VP, { markers: {} })).toEqual({ x: 0, y: 0, w: 1440, h: 900 });
  });

  it('dialog crop is the dialog box clamped to viewport', () => {
    const crop = computeCrop('dialog', VP, { dialog: { x: 400, y: 50, w: 640, h: 1000 }, markers: {} });
    expect(crop).toEqual({ x: 400, y: 50, w: 640, h: 850 });
  });

  it('throws when an around marker is unknown or the box is missing', () => {
    expect(() => computeCrop({ around: ['x'], pad: 0 }, VP, { markers: {} })).toThrow(/x/);
    expect(() => computeCrop('main', VP, { markers: {} })).toThrow(/main/);
  });
});

describe('assertSingleVisible', () => {
  it('passes on exactly one visible match', () => {
    expect(() => assertSingleVisible(1, 1, 'shot/m')).not.toThrow();
  });

  it('assertSingleVisible throws on 2 matches', () => {
    expect(() => assertSingleVisible(2, 2, 'probe/neu')).toThrow(
      'probe/neu: 2 Treffer, 2 sichtbar — Locator muss genau ein sichtbares Element treffen',
    );
    expect(() => assertSingleVisible(2, 1, 'probe/neu')).toThrow('probe/neu: 2 Treffer, 1 sichtbar');
  });

  it('assertSingleVisible throws on 1 match hidden', () => {
    expect(() => assertSingleVisible(1, 0, 'probe/monat')).toThrow(
      'probe/monat: 1 Treffer, 0 sichtbar — Locator muss genau ein sichtbares Element treffen',
    );
  });

  it('throws on 0 matches', () => {
    expect(() => assertSingleVisible(0, 0, 'x')).toThrow('x: 0 Treffer, 0 sichtbar');
  });
});

describe('boxInside', () => {
  it('accepts a box inside and rejects one crossing the edge', () => {
    const crop = { x: 256, y: 0, w: 1184, h: 900 };
    expect(boxInside({ x: 288, y: 164, w: 40, h: 40 }, crop)).toBe(true);
    expect(boxInside({ x: 200, y: 164, w: 40, h: 40 }, crop)).toBe(false);
    expect(boxInside({ x: 256.3, y: 0, w: 1184, h: 900 }, crop)).toBe(true); // Toleranz 0,5
  });
});

describe('markerBadgePosition', () => {
  const crop = { x: 0, y: 0, w: 1440, h: 900 };
  const r = 17;
  const outside = (p: { cx: number; cy: number }, b: { x: number; y: number; w: number; h: number }) =>
    p.cx + r <= b.x || p.cx - r >= b.x + b.w || p.cy + r <= b.y || p.cy - r >= b.y + b.h;

  it('large element keeps the badge on the top-left corner', () => {
    expect(markerBadgePosition({ x: 300, y: 100, w: 160, h: 60 }, r, crop)).toEqual({ cx: 300, cy: 100 });
  });

  it('small element puts the badge left of the frame, vertically centred', () => {
    const b = { x: 288, y: 164, w: 40, h: 40 };
    const p = markerBadgePosition(b, r, crop);
    expect(p.cy).toBe(184);
    expect(p.cx).toBeLessThan(b.x - r);
    expect(outside(p, b)).toBe(true);
  });

  it('small element at the left crop edge puts the badge above', () => {
    const b = { x: 10, y: 200, w: 40, h: 40 };
    const p = markerBadgePosition(b, r, { x: 0, y: 0, w: 600, h: 400 });
    expect(p.cx).toBe(30);
    expect(p.cy).toBeLessThan(200 - r);
    expect(outside(p, b)).toBe(true);
  });

  it('badge is always clamped inside the crop', () => {
    const c = { x: 100, y: 50, w: 600, h: 400 };
    for (const b of [
      { x: 100, y: 50, w: 20, h: 20 },
      { x: 680, y: 430, w: 20, h: 20 },
      { x: 100, y: 50, w: 300, h: 200 },
    ]) {
      const p = markerBadgePosition(b, r, c);
      expect(p.cx - r).toBeGreaterThanOrEqual(c.x);
      expect(p.cy - r).toBeGreaterThanOrEqual(c.y);
      expect(p.cx + r).toBeLessThanOrEqual(c.x + c.w);
      expect(p.cy + r).toBeLessThanOrEqual(c.y + c.h);
    }
  });
});
