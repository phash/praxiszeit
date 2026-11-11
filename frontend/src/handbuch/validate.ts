import type { Block, BroschuereShot, Handbook, HandbookId, Inline, Manifest } from './types';
import { HANDBOOK_IDS, parseHandbookLink, tokenize } from './inline';

const MIN_ALT = 40;
const MAX_BROSCHUERE_MARKERS = 3;

function inlinesOf(b: Block): Inline[] {
  switch (b.kind) {
    case 'task': return [...(b.intro ? [b.intro] : []), ...b.steps.map((s) => s.text)];
    case 'tip': case 'comic': case 'prose': return [b.text];
    case 'diagram': return [b.caption];
    case 'table': return b.rows.flat();
  }
}

function blockLabel(b: Block): string {
  return b.kind === 'task' ? `task ${b.id}` : b.kind;
}

/** Sprungmarken eines Handbuchs: Kapitel- und Aufgaben-IDs (ohne `#`). */
export function anchorsOf(h: Handbook): Set<string> {
  const out = new Set<string>();
  for (const ch of h.chapters) {
    out.add(ch.id);
    for (const b of ch.blocks) if (b.kind === 'task') out.add(b.id);
  }
  return out;
}

/**
 * `books`: alle Handbücher, damit Links `handbuch:<id>#anker` auf andere Bücher geprüft werden
 * (Anker = Kapitel- oder Aufgaben-ID des Ziels). Ohne `books` entfällt nur diese Prüfung;
 * Anker im eigenen Buch (`#anker`) und die Buch-ID werden immer geprüft.
 */
export function validateHandbook(
  h: Handbook,
  m: Manifest,
  books?: Partial<Record<HandbookId, Handbook>>,
): string[] {
  const errors: string[] = [];
  const ownAnchors = anchorsOf(h);
  const seen = new Set<string>();
  const shotIds = new Set<string>();
  const shotsById = new Map(h.shots.map((s) => [s.id, s]));

  const checkLinks = (where: string, text: Inline) => {
    for (const tok of tokenize(text)) {
      if (tok.t === 'badlink') {
        errors.push(`${where}: ungültiges Link-Ziel "${tok.href}"`);
        continue;
      }
      if (tok.t !== 'link') continue;
      if (tok.href.startsWith('#')) {
        if (!ownAnchors.has(tok.href.slice(1))) errors.push(`${where}: Anker "${tok.href}" hat kein Ziel`);
        continue;
      }
      const hb = parseHandbookLink(tok.href);
      if (!hb) continue;
      if (!(HANDBOOK_IDS as string[]).includes(hb.id)) {
        errors.push(`${where}: unbekanntes Handbuch "${hb.id}" im Link`);
        continue;
      }
      const target = hb.id === h.id ? h : books?.[hb.id as HandbookId];
      if (hb.anchor && target && !anchorsOf(target).has(hb.anchor.slice(1))) {
        errors.push(`${where}: Anker "${hb.anchor}" fehlt im Handbuch "${hb.id}"`);
      }
    }
  };
  const claim = (label: string, id: string) => {
    if (seen.has(id)) errors.push(`${label} ${id}: doppelte ID`);
    seen.add(id);
  };

  checkLinks('lead', h.lead);
  for (const ch of h.chapters) {
    claim('chapter', ch.id);
    for (const b of ch.blocks) {
      if (b.kind === 'task') claim('task', b.id);
      for (const t of inlinesOf(b)) checkLinks(blockLabel(b), t);

      if (b.kind === 'task' && b.shot) {
        const shot = shotsById.get(b.shot);
        if (!shot) {
          errors.push(`task ${b.id}: Aufnahme "${b.shot}" nicht definiert`);
          continue;
        }
        const markerNs = new Set(shot.markers.map((mk) => mk.n));
        const stepNs = new Set(b.steps.filter((s) => s.n !== undefined).map((s) => s.n as number));
        for (const n of [...stepNs].sort((a, c) => a - c)) {
          if (!markerNs.has(n)) errors.push(`task ${b.id}: Schritt ${n} ohne Markierung`);
        }
        for (const n of [...markerNs].sort((a, c) => a - c)) {
          if (!stepNs.has(n)) errors.push(`task ${b.id}: Markierung ${n} ohne Schritt`);
        }
      }
    }
  }

  for (const s of h.shots) {
    if (shotIds.has(s.id)) errors.push(`shot ${s.id}: doppelte ID`);
    shotIds.add(s.id);
    if (s.alt.trim().length < MIN_ALT) errors.push(`shot ${s.id}: Alt-Text kürzer als ${MIN_ALT} Zeichen`);
    const entry = m[s.id];
    if (!entry) {
      errors.push(`shot ${s.id}: fehlt im Manifest`);
      continue;
    }
    for (const mk of s.markers) {
      if (!entry.markers[mk.id]) errors.push(`shot ${s.id}: Markierung ${mk.n} (${mk.id}) fehlt im Manifest`);
    }
  }
  return errors;
}

/** Broschüren-Aufnahmen: im Manifest, höchstens 3 Markierungen, Alt-Text ausreichend lang. */
export function validateBroschuere(list: BroschuereShot[], m: Manifest): string[] {
  const errors: string[] = [];
  const seen = new Set<string>();
  for (const { shot, caption } of list) {
    if (seen.has(shot.id)) errors.push(`shot ${shot.id}: doppelte ID`);
    seen.add(shot.id);
    if (shot.markers.length > MAX_BROSCHUERE_MARKERS) {
      errors.push(`shot ${shot.id}: höchstens ${MAX_BROSCHUERE_MARKERS} Markierungen erlaubt, ${shot.markers.length} gefunden`);
    }
    if (shot.alt.trim().length < MIN_ALT) errors.push(`shot ${shot.id}: Alt-Text kürzer als ${MIN_ALT} Zeichen`);
    if (!caption.trim()) errors.push(`shot ${shot.id}: Bildunterschrift fehlt`);
    const entry = m[shot.id];
    if (!entry) {
      errors.push(`shot ${shot.id}: fehlt im Manifest`);
      continue;
    }
    for (const mk of shot.markers) {
      if (!entry.markers[mk.id]) errors.push(`shot ${shot.id}: Markierung ${mk.n} (${mk.id}) fehlt im Manifest`);
    }
  }
  return errors;
}
