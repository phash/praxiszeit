import { describe, expect, it } from 'vitest';
import { assertSingleVisible, boxInside, computeCrop, markerBadgePosition, paddedMarkerBox } from './geometry';

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

describe('markerBadgePosition (R18)', () => {
  const crop = { x: 0, y: 0, w: 1440, h: 900 };
  const r = 20;
  const b = { x: 300, y: 100, w: 160, h: 60 };

  it('default: left of the frame, vertically centred', () => {
    expect(markerBadgePosition(b, r, crop)).toEqual({ cx: 274, cy: 130 });
    expect(markerBadgePosition(b, r, crop, 'left')).toEqual({ cx: 274, cy: 130 });
  });

  it('right: right of the frame, vertically centred', () => {
    expect(markerBadgePosition(b, r, crop, 'right')).toEqual({ cx: 486, cy: 130 });
  });

  it('top: above the centre of the frame', () => {
    expect(markerBadgePosition(b, r, crop, 'top')).toEqual({ cx: 380, cy: 74 });
  });

  it('corner: top-left corner shifted outward by 0.6 r (R15)', () => {
    expect(markerBadgePosition(b, r, crop, 'corner')).toEqual({ cx: 288, cy: 88 });
  });

  it('falls back to the corner when the circle does not fit at the wanted place', () => {
    const c = { x: 256, y: 0, w: 1184, h: 900 };
    // links ist kein Platz (x − 1,3 r − r < crop.x)
    expect(markerBadgePosition({ x: 270, y: 100, w: 40, h: 40 }, r, c)).toEqual({ cx: 276, cy: 88 });
    // rechts ist kein Platz
    expect(markerBadgePosition({ x: 1380, y: 100, w: 50, h: 40 }, r, c, 'right')).toEqual({ cx: 1368, cy: 88 });
    // oben ist kein Platz
    expect(markerBadgePosition({ x: 600, y: 10, w: 100, h: 40 }, r, c, 'top')).toEqual({ cx: 588, cy: 20 });
  });

  it('corner fallback is clamped so the whole circle stays inside', () => {
    const c = { x: 256, y: 0, w: 1184, h: 900 };
    expect(markerBadgePosition({ x: 270, y: 10, w: 40, h: 40 }, r, c)).toEqual({ cx: 276, cy: 20 });
    expect(markerBadgePosition({ x: 1436, y: 895, w: 4, h: 5 }, r, c)).toEqual({ cx: 1420, cy: 880 });
  });
});

describe('paddedMarkerBox (R20)', () => {
  const crop = { x: 256, y: 0, w: 1184, h: 900 };
  it('vergrößert die Box um 4·k nach allen Seiten', () => {
    expect(paddedMarkerBox({ x: 400, y: 100, w: 200, h: 40 }, 2, crop)).toEqual({ x: 392, y: 92, w: 216, h: 56 });
  });
  it('klemmt den Rahmen in den Ausschnitt', () => {
    expect(paddedMarkerBox({ x: 258, y: 2, w: 100, h: 40 }, 2, crop)).toEqual({ x: 256, y: 0, w: 110, h: 50 });
    expect(paddedMarkerBox({ x: 1400, y: 880, w: 40, h: 20 }, 2, crop)).toEqual({ x: 1392, y: 872, w: 48, h: 28 });
  });
});
