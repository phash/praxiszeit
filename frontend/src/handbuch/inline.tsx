import { Fragment } from 'react';
import type { MouseEvent, ReactNode } from 'react';
import type { HandbookId, Inline } from './types';

export type InlineOpts = {
  linkBase: string;
  slugs?: Partial<Record<HandbookId, string>>;
  /** Optional: Klick auf einen internen Link (nicht https://). Ohne Handler bleibt es ein einfaches <a href>. */
  onInternalLink?: (href: string, e: MouseEvent<HTMLAnchorElement>) => void;
};

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

function InternalLink({ href, onInternalLink, children }: {
  href: string; onInternalLink?: InlineOpts['onInternalLink']; children: ReactNode;
}) {
  return onInternalLink
    ? <a href={href} onClick={(e) => onInternalLink(href, e)}>{children}</a>
    : <a href={href}>{children}</a>;
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
          <InternalLink key={i} href={resolveHref(tok.href, opts)} onInternalLink={opts.onInternalLink}>{tok.v}</InternalLink>
        );
      }
      case 'badlink':
        return <Fragment key={i}>{tok.raw}</Fragment>;
      default:
        return <Fragment key={i}>{tok.v}</Fragment>;
    }
  });
}

/** Maskiert Markdown-Sonderzeichen in Klartext; `atStart`: auch Blockauslöser am Zeilenanfang. */
export function escapeMd(v: string, atStart = false): string {
  let out = v.replace(/[\\*_[\]<>&`|]/g, (c) => `\\${c}`);
  if (atStart) out = out.replace(/^(\s*)(?:([#>+-])|(\d+)\.)/, (_m, ws: string, ch?: string, num?: string) => (ch ? `${ws}\\${ch}` : `${ws}${num}\\.`));
  return out;
}

/** `table: true` = Ausgabe in einer GFM-Tabellenzelle (`|` auch im Code-Span maskieren). */
export function inlineToMarkdown(text: Inline, opts: InlineOpts & { table?: boolean }): string {
  return tokenize(text)
    .map((tok, i) => {
      const start = i === 0;
      switch (tok.t) {
        case 'bold': return `**${escapeMd(tok.v)}**`;
        case 'ui': return `\`${opts.table ? tok.v.replace(/\|/g, '\\|') : tok.v}\``;
        case 'link': {
          const hb = parseHandbookLink(tok.href);
          const target = hb ? `${MD_FILES[hb.id as HandbookId] ?? hb.id}${hb.anchor}` : tok.href;
          return `[${escapeMd(tok.v)}](${target})`;
        }
        case 'badlink': return escapeMd(tok.raw, start);
        default: return escapeMd(tok.v, start);
      }
    })
    .join('');
}
