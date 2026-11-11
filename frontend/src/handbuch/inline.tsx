import { Fragment } from 'react';
import type { ReactNode } from 'react';
import type { HandbookId, Inline } from './types';

export type InlineOpts = { linkBase: string; slugs?: Partial<Record<HandbookId, string>> };

export const MD_FILES: Record<HandbookId, string> = {
  mitarbeitende: 'HANDBUCH-MITARBEITER.md',
  praxisleitung: 'HANDBUCH-ADMIN.md',
  'so-rechnet': 'SO-RECHNET-PRAXISZEIT.md',
};

export const HANDBOOK_IDS = Object.keys(MD_FILES) as HandbookId[];

type Token =
  | { t: 'text'; v: string }
  | { t: 'bold'; v: string }
  | { t: 'ui'; v: string }
  | { t: 'link'; v: string; href: string }
  | { t: 'badlink'; v: string; href: string; raw: string };

/** Erlaubte Link-Ziele: #anker, /route (nicht //), handbuch:<id>..., http(s)://. */
export function isAllowedHref(href: string): boolean {
  return /^#/.test(href) || (/^\/(?!\/)/.test(href) && !href.includes('\\')) || /^handbuch:/.test(href) || /^https?:\/\//i.test(href);
}

const TOKEN_RE = /\*\*(.+?)\*\*|\[\[(.+?)\]\]|\[([^\]]+)\]\(([^)\s]+)\)/g;

export function tokenize(text: Inline): Token[] {
  const out: Token[] = [];
  let last = 0;
  for (const m of text.matchAll(TOKEN_RE)) {
    const idx = m.index ?? 0;
    if (idx > last) out.push({ t: 'text', v: text.slice(last, idx) });
    if (m[1] !== undefined) out.push({ t: 'bold', v: m[1] });
    else if (m[2] !== undefined) out.push({ t: 'ui', v: m[2] });
    else if (isAllowedHref(m[4])) out.push({ t: 'link', v: m[3], href: m[4] });
    else out.push({ t: 'badlink', v: m[3], href: m[4], raw: m[0] });
    last = idx + m[0].length;
  }
  if (last < text.length) out.push({ t: 'text', v: text.slice(last) });
  return out;
}

/** `handbuch:<id>#anker` -> { id, anchor } oder null. */
export function parseHandbookLink(href: string): { id: string; anchor: string } | null {
  if (!href.startsWith('handbuch:')) return null;
  const rest = href.slice('handbuch:'.length);
  const hash = rest.indexOf('#');
  return hash < 0 ? { id: rest, anchor: '' } : { id: rest.slice(0, hash), anchor: rest.slice(hash) };
}

function resolveHref(href: string, opts: InlineOpts): string {
  const hb = parseHandbookLink(href);
  if (!hb) return href;
  const slug = opts.slugs?.[hb.id as HandbookId] ?? hb.id;
  return `${opts.linkBase}/${slug}${hb.anchor}`;
}

export function renderInline(text: Inline, opts: InlineOpts): ReactNode {
  return tokenize(text).map((tok, i) => {
    switch (tok.t) {
      case 'bold':
        return <strong key={i}>{tok.v}</strong>;
      case 'ui':
        return <span key={i} className="hb-ui">{tok.v}</span>;
      case 'link': {
        const external = /^https?:\/\//i.test(tok.href);
        return external ? (
          <a key={i} href={tok.href} target="_blank" rel="noopener">{tok.v}</a>
        ) : (
          <a key={i} href={resolveHref(tok.href, opts)}>{tok.v}</a>
        );
      }
      case 'badlink':
        return <Fragment key={i}>{tok.raw}</Fragment>;
      default:
        return <Fragment key={i}>{tok.v}</Fragment>;
    }
  });
}

export function inlineToMarkdown(text: Inline, _opts: InlineOpts): string {
  void _opts;
  return tokenize(text)
    .map((tok) => {
      switch (tok.t) {
        case 'bold': return `**${tok.v}**`;
        case 'ui': return `\`${tok.v}\``;
        case 'link': {
          const hb = parseHandbookLink(tok.href);
          const target = hb ? `${MD_FILES[hb.id as HandbookId] ?? hb.id}${hb.anchor}` : tok.href;
          return `[${tok.v}](${target})`;
        }
        case 'badlink': return tok.raw;
        default: return tok.v;
      }
    })
    .join('');
}
