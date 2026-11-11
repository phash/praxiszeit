/**
 * Reine Geometrie fuer die Screenshot-Aufnahme (e2e/handbuch/capture.ts).
 * Alle Werte in CSS-Pixeln des Fensters (Viewport). Keine Imports ausser Typen
 * aus diesem Verzeichnis (R4).
 */
import type { ShotDef } from './types';

export interface Box { x: number; y: number; w: number; h: number }
export interface Viewport { w: number; h: number }

/** Mindestbreite eines `{around}`-Ausschnitts (CSS px). */
export const MIN_AROUND_WIDTH = 480;

function clampToViewport(b: Box, vp: Viewport): Box {
  const x1 = Math.max(0, b.x);
  const y1 = Math.max(0, b.y);
  const x2 = Math.min(vp.w, b.x + b.w);
  const y2 = Math.min(vp.h, b.y + b.h);
  return { x: x1, y: y1, w: Math.max(0, x2 - x1), h: Math.max(0, y2 - y1) };
}

/** Verbreitert `b` symmetrisch auf mindestens `min` und schiebt es ins Fenster. */
function widen(b: Box, min: number, vp: Viewport): Box {
  if (b.w >= min) return b;
  const w = Math.min(min, vp.w);
  let x = b.x + b.w / 2 - w / 2;
  x = Math.min(Math.max(0, x), vp.w - w);
  return { x, y: b.y, w, h: b.h };
}

export function computeCrop(
  kind: ShotDef['crop'],
  viewport: Viewport,
  boxes: { main?: Box; dialog?: Box; markers: Record<string, Box> },
): Box {
  const full: Box = { x: 0, y: 0, w: viewport.w, h: viewport.h };
  if (kind === undefined || kind === 'full') return full;
  if (kind === 'main' || kind === 'dialog') {
    const b = boxes[kind];
    if (!b) throw new Error(`Ausschnitt '${kind}': keine Box fuer ${kind}`);
    return clampToViewport(b, viewport);
  }
  if ('mainTo' in kind) {
    // Breite und Oberkante des Hauptbereichs, unten bei der Unterkante des untersten Markers + pad
    if (!boxes.main) throw new Error("Ausschnitt mainTo: keine Box fuer main");
    if (kind.mainTo.length === 0) throw new Error('Ausschnitt mainTo: keine Marker angegeben');
    let bottom = -Infinity;
    for (const id of kind.mainTo) {
      const b = boxes.markers[id];
      if (!b) throw new Error(`Ausschnitt mainTo: unbekannter Marker '${id}'`);
      bottom = Math.max(bottom, b.y + b.h);
    }
    const m = boxes.main;
    return clampToViewport({ x: m.x, y: m.y, w: m.w, h: bottom + kind.pad - m.y }, viewport);
  }
  if (kind.around.length === 0) throw new Error('Ausschnitt around: keine Marker angegeben');
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
  for (const id of kind.around) {
    const b = boxes.markers[id];
    if (!b) throw new Error(`Ausschnitt around: unbekannter Marker '${id}'`);
    x1 = Math.min(x1, b.x); y1 = Math.min(y1, b.y);
    x2 = Math.max(x2, b.x + b.w); y2 = Math.max(y2, b.y + b.h);
  }
  const p = kind.pad;
  const padded = clampToViewport({ x: x1 - p, y: y1 - p, w: x2 - x1 + 2 * p, h: y2 - y1 + 2 * p }, viewport);
  return widen(padded, MIN_AROUND_WIDTH, viewport);
}

export function assertSingleVisible(count: number, visible: number, ctx: string): void {
  if (count !== 1 || visible !== 1) {
    throw new Error(
      `${ctx}: ${count} Treffer, ${visible} sichtbar — Locator muss genau ein sichtbares Element treffen`,
    );
  }
}

/** Liegt `inner` (mit Toleranz `tol` CSS px) ganz in `outer`? */
export function boxInside(inner: Box, outer: Box, tol = 0.5): boolean {
  return (
    inner.x >= outer.x - tol &&
    inner.y >= outer.y - tol &&
    inner.x + inner.w <= outer.x + outer.w + tol &&
    inner.y + inner.h <= outer.y + outer.h + tol
  );
}

/** Abstand des Markierungsrahmens zum vermessenen Element (R20), in Einheiten von k = Ausschnittbreite / 700. */
export const MARKER_FRAME_PAD = 4;

/**
 * Gezeichneter Markierungsrahmen (Ruling R20): die vermessene Box um p = 4·k nach
 * außen vergrößert, damit die Linie nie Text des Elements überdeckt; in den
 * Ausschnitt geklemmt. Aus diesem Rahmen rechnet auch `markerBadgePosition`.
 * Eine Regel für ShotFigure und die Kontaktseite.
 */
export function paddedMarkerBox(box: Box, k: number, crop: Box): Box {
  const p = MARKER_FRAME_PAD * k;
  const x1 = Math.max(crop.x, box.x - p);
  const y1 = Math.max(crop.y, box.y - p);
  const x2 = Math.min(crop.x + crop.w, box.x + box.w + p);
  const y2 = Math.min(crop.y + crop.h, box.y + box.h + p);
  return { x: x1, y: y1, w: Math.max(0, x2 - x1), h: Math.max(0, y2 - y1) };
}

/** Lage des Nummernkreises zum Rahmen (Ruling R18). */
export type BadgePlacement = 'left' | 'corner' | 'right' | 'top';

/**
 * Mittelpunkt des Nummernkreises (Radius `r`) zu einer Marker-Box (Ruling R18,
 * ersetzt R15). Standard `left`: links neben dem Rahmen, senkrecht mittig
 * (cx = x − 1,3 r, cy = y + h/2). `right`: rechts daneben, mittig; `top`: über
 * der Mitte (cy = y − 1,3 r). Passt der ganze Kreis an dieser Stelle nicht in
 * den Ausschnitt `crop`, gilt die Ecke aus R15: obere linke Ecke um 0,6 r nach
 * außen, in den Ausschnitt geklemmt (`corner` erzwingt sie).
 * Eine Regel für ShotFigure und die Kontaktseite.
 */
export function markerBadgePosition(
  box: Box, r: number, crop: Box, badge: BadgePlacement = 'left',
): { cx: number; cy: number } {
  const fits = (cx: number, cy: number) =>
    cx - r >= crop.x - 0.01 && cx + r <= crop.x + crop.w + 0.01 &&
    cy - r >= crop.y - 0.01 && cy + r <= crop.y + crop.h + 0.01;
  const mid = box.y + box.h / 2;
  const wanted =
    badge === 'left' ? { cx: box.x - 1.3 * r, cy: mid }
      : badge === 'right' ? { cx: box.x + box.w + 1.3 * r, cy: mid }
        : badge === 'top' ? { cx: box.x + box.w / 2, cy: box.y - 1.3 * r }
          : null;
  if (wanted && fits(wanted.cx, wanted.cy)) return wanted;
  const clamp = (v: number, lo: number, hi: number) => (hi < lo ? (lo + hi) / 2 : Math.min(Math.max(v, lo), hi));
  return {
    cx: clamp(box.x - 0.6 * r, crop.x + r, crop.x + crop.w - r),
    cy: clamp(box.y - 0.6 * r, crop.y + r, crop.y + crop.h - r),
  };
}
