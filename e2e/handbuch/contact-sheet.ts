/**
 * Kontaktseite zur Sichtpruefung der Aufnahmen: jedes Bild im Ausschnitt mit
 * seinen Markierungen (wie ShotFigure), dazu ein PNG der Seite fuer Reviewer.
 * Lokales Werkzeug, gitignored (contact-sheet.html, contact-sheet.png).
 *
 * Einzeln: cd e2e && npx tsx handbuch/contact-sheet.ts   (aus dem aktuellen manifest.json)
 */
import { chromium } from '@playwright/test';
import { existsSync, readFileSync, writeFileSync } from 'fs';
import { relative, resolve } from 'path';
import { pathToFileURL } from 'url';
import { ALL_SHOTS } from '../../frontend/src/handbuch/content/index';
import type { Manifest, ShotDef } from '../../frontend/src/handbuch/types';

const ROOT = resolve(__dirname, '../..');
const IMG_DIR = resolve(ROOT, 'frontend/public/help/img');
const MANIFEST_FILE = resolve(ROOT, 'frontend/src/handbuch/manifest.json');
export const SHEET_HTML = resolve(__dirname, 'contact-sheet.html');
export const SHEET_PNG = resolve(__dirname, 'contact-sheet.png');

const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function figure(def: ShotDef, man: Manifest, fresh: boolean): string {
  const m = man[def.id];
  if (!m) {
    return `<section><h2>${esc(def.id)}</h2><p style="color:#b91c1c">nicht im Manifest — noch nicht aufgenommen</p></section>`;
  }
  const src = relative(__dirname, resolve(IMG_DIR, m.file)).split('\\').join('/');
  const { x, y, w, h } = m.crop;
  const k = w / 700;
  const marks = def.markers
    .map((mk) => {
      const r = m.markers[mk.id];
      if (!r) return `<!-- ${esc(mk.id)} fehlt -->`;
      return `<g>
  <rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" rx="${8 * k}" fill="rgba(239,68,68,0.12)" stroke="#ef4444" stroke-width="${3 * k}"/>
  <circle cx="${r.x}" cy="${r.y}" r="${17 * k}" fill="#ef4444" stroke="#fff" stroke-width="${4 * k}"/>
  <text x="${r.x}" y="${r.y}" font-size="${22 * k}" fill="#fff" font-family="sans-serif" font-weight="700" text-anchor="middle" dominant-baseline="central">${mk.n}</text>
</g>`;
    })
    .join('\n');
  const missing = def.markers.filter((mk) => !m.markers[mk.id]).map((mk) => mk.id);
  const rows = def.markers
    .map((mk) => {
      const r = m.markers[mk.id];
      return `<tr><td>${mk.n}</td><td>${esc(mk.id)}</td><td><code>${esc(JSON.stringify(mk.locator))}</code></td><td>${r ? `${r.x}, ${r.y}, ${r.w}×${r.h}` : '<b style="color:#b91c1c">fehlt</b>'}</td></tr>`;
    })
    .join('');
  return `<section>
<h2>${esc(def.id)} ${fresh ? '<small style="color:#15803d">(neu aufgenommen)</small>' : ''}</h2>
<p class="meta">${esc(def.persona)} · ${esc(def.viewport)} · ${esc(def.route)} · Bild ${m.width}×${m.height} CSS px (${m.pxWidth}×${m.pxHeight} px) · Ausschnitt ${x}, ${y}, ${w}×${h}${missing.length ? ` · <b style="color:#b91c1c">Marker fehlen: ${esc(missing.join(', '))}</b>` : ''}</p>
<svg viewBox="${x} ${y} ${w} ${h}" style="display:block;width:100%;height:auto;border:1px solid #cbd5e1;border-radius:8px;background:#fff">
<image href="${esc(src)}" x="0" y="0" width="${m.width}" height="${m.height}"/>
${marks}
</svg>
<p class="alt">Alt: ${esc(def.alt)}</p>
<table>${rows}</table>
</section>`;
}

export function contactSheetHtml(man: Manifest, shots: ShotDef[], fresh: string[] = []): string {
  const body = shots.map((s) => figure(s, man, fresh.includes(s.id))).join('\n');
  return `<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>Handbuch-Kontaktseite</title>
<style>
body{font-family:system-ui,sans-serif;margin:24px;background:#f1f5f9;color:#0f172a}
section{background:#fff;border-radius:12px;padding:16px;margin:0 0 24px;box-shadow:0 1px 3px rgba(0,0,0,.1)}
h2{margin:0 0 4px;font-size:18px}.meta,.alt{font-size:13px;color:#475569;margin:4px 0 8px}
table{font-size:12px;border-collapse:collapse;margin-top:8px}td{border-top:1px solid #e2e8f0;padding:3px 8px;vertical-align:top}
</style></head><body>
<h1 style="font-size:22px">Handbuch-Kontaktseite (${shots.length} Shots)</h1>
${body}
</body></html>
`;
}

/** Schreibt contact-sheet.html und rendert davon ein PNG (fuer das Read-Werkzeug). */
export async function writeContactSheet(
  man: Manifest,
  shots: ShotDef[],
  fresh: string[] = [],
): Promise<{ html: string; png: string }> {
  writeFileSync(SHEET_HTML, contactSheetHtml(man, shots, fresh));
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
    await page.goto(pathToFileURL(SHEET_HTML).href);
    await page.waitForLoadState('load');
    await page.screenshot({ path: SHEET_PNG, fullPage: true });
  } finally {
    await browser.close();
  }
  return { html: SHEET_HTML, png: SHEET_PNG };
}

if (require.main === module) {
  const man: Manifest = existsSync(MANIFEST_FILE) ? JSON.parse(readFileSync(MANIFEST_FILE, 'utf8')) : {};
  writeContactSheet(man, ALL_SHOTS).then(
    (r) => console.log(`Kontaktseite: ${r.html}\nKontaktseite (PNG): ${r.png}`),
    (e) => {
      console.error(e);
      process.exit(1);
    },
  );
}
