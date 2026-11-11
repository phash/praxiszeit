/**
 * Handbuch-Aufnahme: echte Screenshots aus der Wegwerf-Instanz (pzhandbuch),
 * Markierungen per Locator vermessen, WebP + manifest.json + Kontaktseite.
 *
 * Aufruf (Instanz vorher: bash e2e/handbuch/run.sh up && bash e2e/handbuch/run.sh seed):
 *   cd e2e && npx tsx handbuch/capture.ts [--only <shotId,…>]
 *
 * Grundsaetze:
 * - Ein Locator muss genau EIN sichtbares Element treffen (assertSingleVisible),
 *   sonst bricht der ganze Lauf ab. Geschrieben wird erst, wenn alle Shots gelungen sind.
 * - Die App scrollt in <main>, nicht im Dokument. Boxen werden nach allen
 *   Vorbereitungsschritten in Fenster-Koordinaten gemessen; zwischen Messen und
 *   Aufnahme aendert sich das Layout nicht (Kontrollmessung nach der Aufnahme).
 * - Der Ausschnitt (crop) wird nicht ins Bild geschnitten, er wirkt nur ueber die viewBox.
 */
import { chromium, request, type Browser, type BrowserContext, type Locator, type Page } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { resolve, sep } from 'path';
import sharp from 'sharp';
import { ALL_SHOTS } from '../../frontend/src/handbuch/content/index';
import { assertSingleVisible, boxInside, computeCrop, type Box } from '../../frontend/src/handbuch/geometry';
import type { LocatorSpec, Manifest, ManifestShot, Persona, PrepareStep, ShotDef } from '../../frontend/src/handbuch/types';
import { planSettingsRestore } from '../../frontend/src/handbuch/settingsRestore';
import { expandDateTokens } from '../../frontend/src/handbuch/dates';
import { writeContactSheet } from './contact-sheet';

const ROOT = resolve(__dirname, '../..');
const STATE_FILE = resolve(__dirname, '.state');
export const IMG_DIR = resolve(ROOT, 'frontend/public/help/img');
export const MANIFEST_FILE = resolve(ROOT, 'frontend/src/handbuch/manifest.json');

const PASSWORD = 'Handbuch2026!';
const TZ = 'Europe/Berlin';
const CLOCK_TIME = '10:30:00';
const WEBP_QUALITY = 85;
const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  mobile: { width: 390, height: 844 },
} as const;

/** Nur fuer die Aufnahme: keine Animationen, kein Cursor, keine Fokusringe, keine Toasts. */
const CAPTURE_CSS = [
  '*,*::before,*::after{transition:none!important;animation:none!important;caret-color:transparent!important}',
  ':focus,:focus-visible{outline:none!important}',
  // Toast-Container (ToastContext.tsx: fixed top-4 right-4, Eintraege role=alert)
  'div.fixed.top-4.right-4 > [role="alert"]{display:none!important}',
].join('\n');

/**
 * Offene Dialoge. Die Dokumentations-Schublade (DocDrawer) steht geschlossen mit
 * aria-hidden ausserhalb des Fensters im DOM und gilt fuer Playwright als sichtbar.
 */
const OPEN_DIALOG = '[role="dialog"]:not([aria-hidden="true"])';

/** Haengt CAPTURE_CSS als <style data-handbuch-capture> in jedes Dokument. */
const CAPTURE_INIT_SCRIPT = `(() => {
  const add = () => {
    const s = document.createElement('style');
    s.setAttribute('data-handbuch-capture', '');
    s.textContent = ${JSON.stringify(CAPTURE_CSS)};
    document.head.appendChild(s);
  };
  if (document.head) add();
  else document.addEventListener('DOMContentLoaded', add);
})();`;

// ── Hilfen ──────────────────────────────────────────────────────────────────

function readState(): { baseUrl: string; stichtag: string } {
  if (!existsSync(STATE_FILE)) throw new Error(`${STATE_FILE} fehlt — erst run.sh up && run.sh seed`);
  const kv: Record<string, string> = {};
  for (const line of readFileSync(STATE_FILE, 'utf8').split('\n')) {
    const m = line.match(/^([A-Z_]+)=(.*)$/);
    if (m) kv[m[1]] = m[2].trim();
  }
  if (!kv.BASE_URL) throw new Error('.state: BASE_URL fehlt');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(kv.STICHTAG ?? '')) throw new Error('.state: STICHTAG fehlt — run.sh seed ausfuehren');
  return { baseUrl: kv.BASE_URL.replace(/\/$/, ''), stichtag: kv.STICHTAG };
}

/** Zeitpunkt „<day>T<time>“ in der Zeitzone `tz` als absoluter Date-Wert. */
export function zonedInstant(day: string, time: string, tz: string): Date {
  const naiveUtc = Date.parse(`${day}T${time}Z`);
  const offsetAt = (ms: number) => {
    const name = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'longOffset' })
      .formatToParts(new Date(ms)).find((p) => p.type === 'timeZoneName')?.value ?? 'GMT';
    const m = name.match(/GMT([+-])(\d{2}):(\d{2})/);
    return m ? (m[1] === '+' ? 1 : -1) * (Number(m[2]) * 60 + Number(m[3])) : 0;
  };
  let ms = naiveUtc - offsetAt(naiveUtc) * 60_000;
  ms = naiveUtc - offsetAt(ms) * 60_000; // zweiter Schritt fuer Tage mit Zeitumstellung
  return new Date(ms);
}

const r1 = (v: number) => Math.round(v * 10) / 10;
const roundBox = (b: Box): Box => ({ x: r1(b.x), y: r1(b.y), w: r1(b.w), h: r1(b.h) });

function parseArgs(argv: string[]): { only: string[] | null } {
  const i = argv.indexOf('--only');
  if (i === -1) return { only: null };
  const v = argv[i + 1];
  if (!v) throw new Error('--only braucht eine Liste von Shot-IDs');
  return { only: v.split(',').map((s) => s.trim()).filter(Boolean) };
}

// ── Locator ────────────────────────────────────────────────────────────────

function scope(page: Page, within: 'main' | 'dialog' | 'nav' | undefined): Page | Locator {
  if (within === 'main') return page.locator('main');
  // Mehrere Dialoge/Navigationsleisten im DOM (Sidebar + mobile Leiste): nur die sichtbaren.
  if (within === 'dialog') return page.locator(OPEN_DIALOG).filter({ visible: true });
  if (within === 'nav') return page.locator('nav').filter({ visible: true });
  return page;
}

export function buildLocator(page: Page, spec: LocatorSpec): Locator {
  if ('css' in spec) return page.locator(spec.css);
  if ('role' in spec) {
    return scope(page, spec.within).getByRole(spec.role as Parameters<Page['getByRole']>[0], {
      name: spec.name,
      exact: spec.exact ?? false,
    });
  }
  if ('label' in spec) return scope(page, spec.within).getByLabel(spec.label);
  return scope(page, spec.within).getByText(spec.text);
}

function describe(spec: LocatorSpec): string {
  return JSON.stringify(spec);
}

/** Genau ein sichtbares Element, sonst Abbruch mit Shot- und Marker-/Schritt-Kontext. */
async function single(page: Page, spec: LocatorSpec, ctx: string): Promise<Locator> {
  const loc = buildLocator(page, spec);
  const count = await loc.count();
  let visible = 0;
  for (let i = 0; i < count; i++) if (await loc.nth(i).isVisible()) visible++;
  assertSingleVisible(count, visible, `${ctx} ${describe(spec)}`);
  return loc;
}

// ── Login, Einstellungen ────────────────────────────────────────────────────

async function login(page: Page, baseUrl: string, username: string) {
  await page.goto(`${baseUrl}/login`);
  await page.waitForLoadState('networkidle');
  await page.getByRole('textbox', { name: 'Benutzername' }).fill(username);
  await page.getByRole('textbox', { name: 'Passwort', exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: /anmelden/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15_000 });
  await page.waitForLoadState('networkidle');
  // #132: Willkommens-Fenster beim ersten Login schliessen (dauerhaft per
  // POST /auth/onboarding/complete) und auf die Antwort warten, sonst bricht
  // das naechste goto() den POST ab und das Fenster steht wieder da.
  const welcome = page.getByRole('button', { name: "Los geht's" });
  if (await welcome.waitFor({ state: 'visible', timeout: 3000 }).then(() => true).catch(() => false)) {
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('/auth/onboarding/complete'), { timeout: 5000 }),
      welcome.click(),
    ]);
  }
}

type SettingsValues = Record<string, boolean | string | number>;

/** Setzt Mandanten-Einstellungen als Admin; liefert eine Funktion, die den Vorzustand wiederherstellt. */
export async function applySettings(baseUrl: string, settings: SettingsValues): Promise<() => Promise<void>> {
  const api = await request.newContext({ baseURL: baseUrl });
  let handedOver = false;
  try {
    const res = await api.post('/api/auth/login', { data: { username: 'admin', password: PASSWORD } });
    if (!res.ok()) throw new Error(`Admin-Login fuer Einstellungen: HTTP ${res.status()}`);
    const token = (await res.json()).access_token as string;
    const headers = async () => {
      const csrf = (await api.storageState()).cookies.find((c) => c.name === 'csrf_token')?.value;
      return { Authorization: `Bearer ${token}`, ...(csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf) } : {}) };
    };
    const listRes = await api.get('/api/admin/settings', { headers: await headers() });
    if (!listRes.ok()) throw new Error(`GET /api/admin/settings: HTTP ${listRes.status()}`);
    const stored: Record<string, string> = {};
    for (const r of (await listRes.json()) as { key: string; value: string }[]) stored[r.key] = r.value;
    // Vor der ersten Aenderung: Rueckstellwert je Schluessel (gespeichert oder App-Default),
    // sonst Abbruch — nie einen Schluessel setzen, der sich nicht zuruecksetzen laesst.
    const plan = planSettingsRestore(settings, stored);

    const put = async (key: string, value: string) => {
      const r = await api.put(`/api/admin/settings/${encodeURIComponent(key)}`, {
        headers: await headers(),
        data: { value },
      });
      if (!r.ok()) throw new Error(`PUT /api/admin/settings/${key}: HTTP ${r.status()} ${await r.text()}`);
    };
    // Auch der Schluessel, dessen PUT scheiterte, wird zurueckgestellt (Zustand unbekannt).
    const touched: string[] = [];
    const restore = async () => {
      const errors: string[] = [];
      try {
        for (const key of touched) {
          try {
            await put(key, plan[key]);
          } catch (e) {
            errors.push(e instanceof Error ? e.message : String(e));
          }
        }
      } finally {
        await api.dispose();
      }
      if (errors.length) throw new Error(`Einstellungen nicht zurueckgestellt: ${errors.join('; ')}`);
    };
    try {
      for (const [key, value] of Object.entries(settings)) {
        touched.push(key);
        await put(key, String(value));
      }
    } catch (e) {
      handedOver = true; // restore() raeumt api auf
      await restore().catch((r) => console.error(`  ! ${r instanceof Error ? r.message : r}`));
      throw e;
    }
    handedOver = true;
    return restore;
  } finally {
    if (!handedOver) await api.dispose();
  }
}

// ── Vorbereitung ────────────────────────────────────────────────────────────

async function settle(page: Page) {
  await page.waitForLoadState('networkidle');
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
}

async function runPrepare(page: Page, baseUrl: string, steps: PrepareStep[], shotId: string, stichtag: string) {
  for (const [i, step] of steps.entries()) {
    const ctx = `${shotId} prepare[${i}]`;
    if ('goto' in step) {
      await page.goto(`${baseUrl}${step.goto}`);
    } else if ('click' in step) {
      await (await single(page, step.click, ctx)).click();
    } else if ('fill' in step) {
      await (await single(page, step.fill, ctx)).fill(expandDateTokens(step.value, stichtag));
    } else if ('monthBack' in step) {
      for (let k = 0; k < step.monthBack; k++) {
        await (await single(page, { role: 'button', name: 'Vorheriger Monat', exact: true }, ctx)).click();
        await settle(page);
      }
    } else if ('waitFor' in step) {
      await buildLocator(page, step.waitFor).waitFor({ state: 'visible', timeout: 15_000 });
      await single(page, step.waitFor, ctx);
    } else if ('scrollTo' in step) {
      await (await single(page, step.scrollTo, ctx)).scrollIntoViewIfNeeded();
    } else if ('select' in step) {
      const sel = await single(page, step.select, ctx);
      await sel.focus(); // manche Auswahllisten laden ihre Optionen erst beim Fokus (Import: Benutzerliste)
      await sel.selectOption({ label: step.value });
    } else if ('upload' in step) {
      // Dateifelder sind oft versteckt (`hidden`): genau EIN Treffer im DOM genuegt (sichtbar muss es nicht sein).
      const file = resolve(ROOT, step.file);
      if (!file.startsWith(ROOT + sep)) throw new Error(`${ctx}: Datei ausserhalb des Repos: ${step.file}`);
      if (!existsSync(file)) throw new Error(`${ctx}: Datei fehlt: ${step.file}`);
      const input = buildLocator(page, step.upload);
      const n = await input.count();
      if (n !== 1) throw new Error(`${ctx} ${describe(step.upload)}: ${n} Treffer — Locator muss genau ein Dateifeld treffen`);
      await input.setInputFiles(file);
    }
    await settle(page);
  }
}

/** Fokus weg, Maus aus dem Bild, sichtbare Toasts abwarten (sie sind zusaetzlich per CSS ausgeblendet). */
async function calm(page: Page) {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur?.());
  const vp = page.viewportSize()!;
  await page.mouse.move(vp.width - 1, vp.height - 1);
  await page
    .waitForFunction(() => !document.querySelector('div.fixed.top-4.right-4 > [role="alert"]'), undefined, { timeout: 10_000 })
    .catch(() => undefined);
  await page.waitForTimeout(150);
}

/** Lange Dialoge: Fenster strecken, bis der Dialog ganz hineinpasst (Muster shotUntil). */
async function stretchForDialog(page: Page, shotId: string) {
  const dlg = page.locator(OPEN_DIALOG).filter({ visible: true });
  if ((await dlg.count()) !== 1) throw new Error(`${shotId}: crop 'dialog' braucht genau einen sichtbaren Dialog, gefunden ${await dlg.count()}`);
  for (let round = 0; round < 6; round++) {
    const overflow = await dlg.evaluate((el) => {
      let extra = 0;
      for (const n of [el, ...Array.from(el.querySelectorAll<HTMLElement>('*'))] as HTMLElement[]) {
        const st = getComputedStyle(n);
        if (/(auto|scroll)/.test(st.overflowY) && n.scrollHeight > n.clientHeight + 1) {
          n.scrollTop = 0;
          extra = Math.max(extra, n.scrollHeight - n.clientHeight);
        }
      }
      for (let p = el.parentElement; p; p = p.parentElement) p.scrollTop = 0;
      const r = el.getBoundingClientRect();
      return { extra, bottom: r.bottom, top: r.top };
    });
    const vp = page.viewportSize()!;
    let need = vp.height;
    if (overflow.extra > 0) need = vp.height + overflow.extra + 24;
    else if (overflow.bottom > vp.height) need = overflow.bottom + 24;
    need = Math.ceil(need);
    if (need <= vp.height) return;
    await page.setViewportSize({ width: vp.width, height: need });
    await page.waitForTimeout(300);
  }
}

// ── Vermessen ───────────────────────────────────────────────────────────────

interface Measured { markers: Record<string, Box>; main?: Box; dialog?: Box }

async function measure(page: Page, def: ShotDef): Promise<Measured> {
  const vp = page.viewportSize()!;
  const markers: Record<string, Box> = {};
  for (const mk of def.markers) {
    const ctx = `${def.id} Marker ${mk.n} (${mk.id})`;
    const loc = await single(page, mk.locator, ctx);
    const bb = await loc.boundingBox();
    if (!bb) throw new Error(`${ctx}: keine Box`);
    const box = { x: bb.x, y: bb.y, w: bb.width, h: bb.height };
    if (box.w < 1 || box.h < 1) throw new Error(`${ctx}: Box ist leer (${JSON.stringify(roundBox(box))})`);
    if (box.x < -0.5 || box.y < -0.5 || box.x + box.w > vp.width + 0.5 || box.y + box.h > vp.height + 0.5) {
      throw new Error(`${ctx}: liegt ausserhalb des Fensters ${JSON.stringify(roundBox(box))} — scrollTo ergaenzen`);
    }
    // Verdeckt? Der Mittelpunkt muss das Element selbst (oder ein Kind) treffen.
    const hit = await loc.evaluate((el) => {
      const r = el.getBoundingClientRect();
      const h = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return !!h && (el === h || el.contains(h) || h.contains(el));
    });
    if (!hit) throw new Error(`${ctx}: Element ist verdeckt (anderes Element liegt darueber)`);
    markers[mk.id] = box;
  }
  const out: Measured = { markers };
  const main = await page.locator('main').filter({ visible: true }).first().boundingBox().catch(() => null);
  if (main) out.main = { x: main.x, y: main.y, w: main.width, h: main.height };
  const dlg = page.locator(OPEN_DIALOG).filter({ visible: true });
  if ((await dlg.count()) === 1) {
    const d = await dlg.boundingBox();
    if (d) out.dialog = { x: d.x, y: d.y, w: d.width, h: d.height };
  }
  return out;
}

function sameBoxes(a: Record<string, Box>, b: Record<string, Box>): string | null {
  for (const id of Object.keys(a)) {
    const p = a[id], q = b[id];
    if (!q || Math.abs(p.x - q.x) > 0.5 || Math.abs(p.y - q.y) > 0.5 || Math.abs(p.w - q.w) > 0.5 || Math.abs(p.h - q.h) > 0.5) return id;
  }
  return null;
}

// ── Ein Shot ────────────────────────────────────────────────────────────────

export interface Captured { id: string; webp: Buffer; entry: ManifestShot }

async function newContext(browser: Browser, def: ShotDef, stichtag: string): Promise<BrowserContext> {
  const vp = VIEWPORTS[def.viewport];
  const ctx = await browser.newContext({
    viewport: { ...vp },
    deviceScaleFactor: 2,
    locale: 'de-DE',
    timezoneId: TZ,
    isMobile: def.viewport === 'mobile',
    hasTouch: def.viewport === 'mobile',
  });
  // Als Zeichenkette, nicht als Funktion: tsx/esbuild umhuellt benannte
  // Pfeilfunktionen mit `__name(...)`, das es im Browser nicht gibt — die
  // Funktion warf dort still, und das Aufnahme-CSS fehlte in jedem Bild.
  await ctx.addInitScript(CAPTURE_INIT_SCRIPT);
  await ctx.clock.setFixedTime(zonedInstant(stichtag, CLOCK_TIME, TZ));
  return ctx;
}

async function captureShot(browser: Browser, def: ShotDef, baseUrl: string, stichtag: string): Promise<Captured> {
  const context = await newContext(browser, def, stichtag);
  let restore: (() => Promise<void>) | null = null;
  let firstError: unknown;
  let shotFailed = false;
  try {
    const page = await context.newPage();
    if ((def.persona as Persona) !== 'anon') await login(page, baseUrl, def.persona);
    if (def.settings && Object.keys(def.settings).length) restore = await applySettings(baseUrl, def.settings);
    await page.goto(`${baseUrl}${def.route}`);
    await settle(page);
    await runPrepare(page, baseUrl, def.prepare ?? [], def.id, stichtag);
    await calm(page);
    if (def.crop === 'dialog') {
      await stretchForDialog(page, def.id);
      await calm(page);
    }

    const m = await measure(page, def);
    const vp = page.viewportSize()!;
    const crop = computeCrop(def.crop, { w: vp.width, h: vp.height }, m);
    for (const mk of def.markers) {
      if (!boxInside(m.markers[mk.id], crop)) {
        throw new Error(
          `${def.id} Marker ${mk.n} (${mk.id}): liegt nicht im Ausschnitt ${JSON.stringify(roundBox(crop))} ` +
            `(Box ${JSON.stringify(roundBox(m.markers[mk.id]))}) — crop oder scrollTo anpassen`,
        );
      }
    }
    const png = await page.screenshot({ type: 'png', scale: 'device', animations: 'disabled', caret: 'hide' });
    const again = await measure(page, def);
    const moved = sameBoxes(m.markers, again.markers);
    if (moved) throw new Error(`${def.id}: Marker ${moved} hat sich waehrend der Aufnahme verschoben`);

    const webp = await sharp(png).webp({ quality: WEBP_QUALITY }).toBuffer();
    const meta = await sharp(webp).metadata();
    const markers: Record<string, Box> = {};
    for (const id of Object.keys(m.markers).sort()) markers[id] = roundBox(m.markers[id]);
    return {
      id: def.id,
      webp,
      entry: {
        file: `${def.id}.webp`,
        width: vp.width,
        height: vp.height,
        pxWidth: meta.width!,
        pxHeight: meta.height!,
        crop: roundBox(crop),
        markers,
      },
    };
  } catch (e) {
    firstError = e;
    shotFailed = true;
    throw e;
  } finally {
    // Jeder Schritt fuer sich: ein scheiternder restore() darf weder context.close()
    // ueberspringen noch den urspruenglichen Fehler verdecken.
    const cleanup: [string, () => Promise<void>][] = [];
    if (restore) cleanup.push(['Einstellungen zuruecksetzen', restore]);
    cleanup.push(['Kontext schliessen', () => context.close()]);
    for (const [what, fn] of cleanup) {
      try {
        await fn();
      } catch (e) {
        if (firstError === undefined) firstError = e;
        else console.error(`  ! ${def.id}: ${what} gescheitert: ${e instanceof Error ? e.message : e}`);
      }
    }
    if (firstError !== undefined && !shotFailed) throw firstError;
  }
}

// ── Manifest ────────────────────────────────────────────────────────────────

export function readManifest(): Manifest {
  return existsSync(MANIFEST_FILE) ? (JSON.parse(readFileSync(MANIFEST_FILE, 'utf8')) as Manifest) : {};
}

export function stableManifestJson(man: Manifest): string {
  const sorted: Manifest = {};
  for (const k of Object.keys(man).sort()) sorted[k] = man[k];
  return JSON.stringify(sorted, null, 2) + '\n';
}

// ── Lauf ────────────────────────────────────────────────────────────────────

async function main() {
  const { only } = parseArgs(process.argv.slice(2));
  const { baseUrl, stichtag } = readState();
  const ids = new Set(ALL_SHOTS.map((s) => s.id));
  if (ids.size !== ALL_SHOTS.length) throw new Error('Doppelte Shot-IDs in ALL_SHOTS');
  if (only) {
    const unknown = only.filter((id) => !ids.has(id));
    if (unknown.length) throw new Error(`Unbekannte Shot-IDs: ${unknown.join(', ')}`);
  }
  const defs = only ? ALL_SHOTS.filter((s) => only.includes(s.id)) : ALL_SHOTS;
  console.log(`Aufnahme: ${defs.length} Shot(s) gegen ${baseUrl}, Stichtag ${stichtag} ${CLOCK_TIME} ${TZ}`);

  const browser = await chromium.launch();
  const results: Captured[] = [];
  try {
    for (const def of defs) {
      const c = await captureShot(browser, def, baseUrl, stichtag);
      console.log(`  ✓ ${def.id} ${c.entry.pxWidth}×${c.entry.pxHeight}px, ${Object.keys(c.entry.markers).length} Marker`);
      results.push(c);
    }
  } finally {
    await browser.close();
  }

  // Erst schreiben, wenn alle Shots gelungen sind.
  mkdirSync(IMG_DIR, { recursive: true });
  const man = readManifest();
  for (const c of results) {
    writeFileSync(resolve(IMG_DIR, c.entry.file), c.webp);
    man[c.id] = c.entry;
  }
  writeFileSync(MANIFEST_FILE, stableManifestJson(man));
  console.log(`Manifest: ${MANIFEST_FILE}`);

  const sheet = await writeContactSheet(man, ALL_SHOTS, results.map((r) => r.id));
  console.log(`Kontaktseite: ${sheet.html}`);
  console.log(`Kontaktseite (PNG): ${sheet.png}`);
}

if (require.main === module) {
  main().catch((e) => {
    console.error(`\nAufnahme abgebrochen: ${e instanceof Error ? e.message : e}`);
    process.exit(1);
  });
}
