/**
 * Erzeugt die Markdown-Handbuecher aus frontend/src/handbuch.
 *   npm run handbuch:md            schreibt docs/handbuch/*.md, public/help/*.md, docs/handbuch/img/*
 *   npm run handbuch:md -- --check vergleicht nur (Exit 1 bei Abweichung)
 * Handbuecher ohne Kapitel werden uebersprungen (bestehende Dateien bleiben).
 */
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { HANDBOOKS } from '../src/handbuch/content/index';
import manifestJson from '../src/handbuch/manifest.json';
import { mdFileName, toMarkdown } from '../src/handbuch/render/toMarkdown';
import type { Handbook, HandbookId, Manifest } from '../src/handbuch/types';

export interface Output { path: string; text?: string; copyFrom?: string }

export function generateAll(
  handbooks: Partial<Record<HandbookId, Handbook>>,
  manifest: Manifest,
  version: string,
  root: string,
): Output[] {
  const outs: Output[] = [];
  const images = new Set<string>();
  for (const h of Object.values(handbooks)) {
    if (!h || h.chapters.length === 0) continue;
    const file = mdFileName(h.id);
    outs.push({ path: join(root, 'docs/handbuch', file), text: toMarkdown(h, manifest, 'docs', version) });
    outs.push({ path: join(root, 'frontend/public/help', file), text: toMarkdown(h, manifest, 'download', version) });
    for (const ch of h.chapters)
      for (const b of ch.blocks)
        if (b.kind === 'task' && b.shot && manifest[b.shot]) images.add(manifest[b.shot].file);
  }
  for (const img of [...images].sort())
    outs.push({ path: join(root, 'docs/handbuch/img', img), copyFrom: join(root, 'frontend/public/help/img', img) });
  return outs;
}

function differs(o: Output): boolean {
  if (!existsSync(o.path)) return true;
  if (o.text !== undefined) return readFileSync(o.path, 'utf-8') !== o.text;
  return !readFileSync(o.path).equals(readFileSync(o.copyFrom!));
}

function main(): number {
  const check = process.argv.includes('--check');
  const here = dirname(fileURLToPath(import.meta.url));
  const root = resolve(here, '../..');
  const version = (JSON.parse(readFileSync(join(here, '../package.json'), 'utf-8')) as { version: string }).version;
  const outs = generateAll(HANDBOOKS, manifestJson as Manifest, version, root);
  const stale = outs.filter(differs);
  if (check) {
    for (const o of stale) console.error(`VERALTET  ${o.path.replace(root + '/', '')}`);
    if (stale.length) console.error('Handbuch-Markdown veraltet: cd frontend && npm run handbuch:md, dann committen.');
    else console.log(`handbuch:md ok (${outs.length} Dateien)`);
    return stale.length ? 1 : 0;
  }
  for (const o of stale) {
    mkdirSync(dirname(o.path), { recursive: true });
    if (o.text !== undefined) writeFileSync(o.path, o.text);
    else copyFileSync(o.copyFrom!, o.path);
    console.log(`geschrieben ${o.path.replace(root + '/', '')}`);
  }
  if (!outs.length) console.log('Keine Handbuecher mit Kapiteln — nichts erzeugt.');
  return 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) process.exit(main());
