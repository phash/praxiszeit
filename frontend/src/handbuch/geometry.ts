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
