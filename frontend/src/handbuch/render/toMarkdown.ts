import { inlineToMarkdown, MD_FILES } from '../inline';
import type { Block, Handbook, HandbookId, Manifest } from '../types';

export type MdTarget = 'docs' | 'download';

export const MARKER = '<!-- Erzeugt aus frontend/src/handbuch — nicht von Hand bearbeiten -->';

/** Dateiname je Handbuch (eine Quelle: MD_FILES aus inline.tsx). */
export function mdFileName(id: HandbookId): string {
  return MD_FILES[id];
}

export function imagePath(file: string, target: MdTarget): string {
  return target === 'docs' ? `img/${file}` : `/help/img/${file}`;
}

/**
 * Markdown eines Handbuchs. `version` = App-Version (frontend/package.json);
 * die Versionszeile nennt nur sie (kein Monat -> `--check` kippt nicht von selbst).
 */
export function toMarkdown(h: Handbook, m: Manifest, target: MdTarget, version = ''): string {
  const opts = { linkBase: '' };
  const inl = (t: string) => inlineToMarkdown(t, opts);
  const out: string[] = [MARKER, '', `# ${h.title}`, ''];
  if (version) out.push(`**Stand:** PraxisZeit ${version}`, '');
  out.push(inl(h.lead), '');

  const alt = (id: string | undefined, fallback: string) =>
    (id && h.shots.find((s) => s.id === id)?.alt) || fallback;

  const block = (b: Block): string[] => {
    switch (b.kind) {
      case 'task': {
        const lines = [`<a id="${b.id}"></a>`, `### ${b.title}`, ''];
        if (b.intro) lines.push(inl(b.intro), '');
        const shot = b.shot ? m[b.shot] : undefined;
        if (b.shot && shot) lines.push(`![${alt(b.shot, b.title)}](${imagePath(shot.file, target)})`, '');
        b.steps.forEach((s, i) => lines.push(`${i + 1}. ${inl(s.text)}`));
        lines.push('');
        return lines;
      }
      case 'tip':
        return [`> **${b.tone === 'warn' ? 'Achtung:' : 'Gut zu wissen:'}** ${inl(b.text)}`, ''];
      case 'comic':
        return [`*${inl(b.text)}*`, ''];
      case 'diagram':
        return [`*${inl(b.caption)}*`, ''];
      case 'table': {
        const cell = (c: string) => inlineToMarkdown(c, { ...opts, table: true }).replace(/\n/g, ' ');
        return [
          `| ${b.head.map(cell).join(' | ')} |`,
          `| ${b.head.map(() => '---').join(' | ')} |`,
          ...b.rows.map((r) => `| ${r.map(cell).join(' | ')} |`),
          '',
        ];
      }
      default:
        return [inl(b.text), ''];
    }
  };

  for (const ch of h.chapters) {
    out.push(`<a id="${ch.id}"></a>`, `## ${ch.title}`, '');
    for (const b of ch.blocks) out.push(...block(b));
  }
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trimEnd() + '\n';
}
