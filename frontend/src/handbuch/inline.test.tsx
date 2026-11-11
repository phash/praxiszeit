import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { renderInline, inlineToMarkdown } from './inline';

const opts = { linkBase: '/help' };
const html = (t: string, o = opts) => renderToStaticMarkup(<>{renderInline(t, o)}</>);

describe('renderInline', () => {
  it('renders bold as strong', () => {
    expect(html('**a**')).toBe('<strong>a</strong>');
  });
  it('renders UI term as pill', () => {
    expect(html('[[Neuer Eintrag]]')).toBe('<span class="hb-ui">Neuer Eintrag</span>');
  });
  it('links to other handbook with linkBase', () => {
    expect(html('[x](handbuch:so-rechnet#ist)')).toContain('href="/help/so-rechnet#ist"');
  });
  it('uses slug override', () => {
    expect(html('[x](handbuch:so-rechnet#ist)', { linkBase: '/anleitung', slugs: { 'so-rechnet': 'so-rechnet-praxiszeit' } }))
      .toContain('href="/anleitung/so-rechnet-praxiszeit#ist"');
  });
  it('keeps anchor and route links as is', () => {
    expect(html('[a](#x)')).toContain('href="#x"');
    expect(html('[r](/time-tracking)')).toContain('href="/time-tracking"');
  });
  it('opens https links in new tab', () => {
    const out = html('[g](https://example.org/a#b)');
    expect(out).toContain('href="https://example.org/a#b"');
    expect(out).toContain('target="_blank"');
    expect(out).toContain('rel="noopener"');
  });
  it('keeps html as text', () => {
    expect(html('<b>x</b>')).toBe('&lt;b&gt;x&lt;/b&gt;');
  });
});

describe('unsafe and malformed markup', () => {
  it.each(['javascript:alert1', 'data:text/html,x', '//evil.com', '/\\evil.com'])('renders %s link as plain text', (h) => {
    const out = html(`[x](${h})`);
    expect(out).not.toContain('<a');
    expect(out).not.toContain('href');
    expect(inlineToMarkdown(`[x](${h})`, opts)).not.toContain('[x](');
  });
  it('keeps unbalanced bold literal', () => {
    expect(html('**a')).toBe('**a');
  });
  it('keeps empty UI pill literal', () => {
    expect(html('[[]]')).toBe('[[]]');
  });
});

describe('inlineToMarkdown escaping', () => {
  it('escapes plain text specials', () => {
    expect(inlineToMarkdown('a * b _c_ <b> & d', opts)).toBe('a \\* b \\_c\\_ \\<b\\> \\& d');
  });
  it('escapes block triggers at the start', () => {
    expect(inlineToMarkdown('# Titel', opts)).toBe('\\# Titel');
    expect(inlineToMarkdown('- Punkt', opts)).toBe('\\- Punkt');
    expect(inlineToMarkdown('> Zitat', opts)).toBe('\\> Zitat');
    expect(inlineToMarkdown('1. Eins', opts)).toBe('1\\. Eins');
    expect(inlineToMarkdown('a # b', opts)).toBe('a # b');
  });
  it('escapes pipes in text, and in code spans only for tables', () => {
    expect(inlineToMarkdown('a|b [[c|d]]', opts)).toBe('a\\|b `c|d`');
    expect(inlineToMarkdown('a|b [[c|d]]', { ...opts, table: true })).toBe('a\\|b `c\\|d`');
  });
  it('keeps code span content unescaped otherwise', () => {
    expect(inlineToMarkdown('[[a*b_c]]', opts)).toBe('`a*b_c`');
  });
});

describe('inlineToMarkdown', () => {
  it('maps markup', () => {
    expect(inlineToMarkdown('**a** [[Neuer Eintrag]]', opts)).toBe('**a** `Neuer Eintrag`');
  });
  it('maps handbook links to md files', () => {
    expect(inlineToMarkdown('[x](handbuch:so-rechnet#ist)', opts)).toBe('[x](SO-RECHNET-PRAXISZEIT.md#ist)');
    expect(inlineToMarkdown('[x](handbuch:praxisleitung#a)', opts)).toBe('[x](HANDBUCH-ADMIN.md#a)');
    expect(inlineToMarkdown('[x](handbuch:mitarbeitende)', opts)).toBe('[x](HANDBUCH-MITARBEITER.md)');
  });
  it('keeps anchor, route, https', () => {
    expect(inlineToMarkdown('[a](#x) [r](/route) [g](https://e.org/#y)', opts)).toBe('[a](#x) [r](/route) [g](https://e.org/#y)');
  });
});
