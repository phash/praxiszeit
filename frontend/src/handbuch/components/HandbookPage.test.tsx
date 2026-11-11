import { describe, it, expect } from 'vitest';
import { renderToString } from 'react-dom/server';
import { render, fireEvent } from '@testing-library/react';
import HandbookPage from './HandbookPage';
import type { Handbook, Manifest } from '../types';

const handbook: Handbook = {
  id: 'mitarbeitende', title: 'Handbuch', lead: 'Lead mit [[Heute]]',
  shots: [{
    id: 's1', persona: 'maria', viewport: 'desktop', route: '/time',
    markers: [
      { n: 1, id: 'a', locator: { css: '#a' } },
      { n: 2, id: 'b', locator: { css: '#b' } },
      { n: 3, id: 'c', locator: { css: '#c' } },
    ],
    alt: 'Zeiterfassung mit drei Markierungen im Monatsüberblick der Demo',
  }],
  chapters: [{
    id: 'zeit', title: 'Zeiterfassung',
    blocks: [
      { kind: 'task', id: 'ueberblick', title: 'Überblick', shot: 's1', steps: [
        { n: 1, text: 'Eins' }, { n: 2, text: 'Zwei' }, { n: 3, text: 'Drei' }] },
      { kind: 'task', id: 'zweite', title: 'Zweite', steps: [{ text: 'Ohne Nummer' }] },
      { kind: 'tip', tone: 'info', text: 'Tipp **fett**' },
      { kind: 'comic', scene: 'vergessen', text: 'Comic Text' },
      { kind: 'diagram', diagram: 'd1', caption: 'Bildunterschrift' },
      { kind: 'table', head: ['A', 'B'], rows: [['1', '2']] },
      { kind: 'prose', text: 'Fließtext' },
    ],
  }],
};
const manifest: Manifest = {
  s1: {
    file: 's1.webp', width: 1440, height: 900, pxWidth: 2880, pxHeight: 1800,
    crop: { x: 262, y: 6, w: 1170, h: 440 },
    markers: {
      a: { x: 284, y: 160, w: 360, h: 48 }, b: { x: 660, y: 96, w: 376, h: 44 },
      c: { x: 1244, y: 28, w: 168, h: 48 },
    },
  },
};
const Comic = () => <svg data-testid="comic" />;
const Diagram = () => <svg data-testid="diagram" />;
const props = { handbook, manifest, imgBase: '/help/img', linkBase: '/handbuch', variant: 'wide' as const,
  comics: { vergessen: Comic }, diagrams: { d1: Diagram } };

describe('HandbookPage', () => {
  it('renders via renderToString without effects', () => {
    const html = renderToString(<HandbookPage {...props} />);
    expect(html).toContain('Überblick');
    expect(html).toContain('Bildunterschrift');
  });
  it('no element has a style attribute', () => {
    const { container } = render(<HandbookPage {...props} />);
    expect(container.querySelectorAll('[style]').length).toBe(0);
    const n = render(<HandbookPage {...props} variant="narrow" />);
    expect(n.container.querySelectorAll('[style]').length).toBe(0);
  });
  it('marker numbers in svg match step numbers', () => {
    const { container } = render(<HandbookPage {...props} />);
    const marks = [...container.querySelectorAll('svg text')].map((t) => t.textContent);
    expect(marks).toEqual(['1', '2', '3']);
    const steps = [...container.querySelectorAll('li[data-n]')].map((l) => l.getAttribute('data-n'));
    expect(steps).toEqual(['1', '2', '3']);
  });
  it('hovering step 2 adds hb-act to marker 2 and hb-dim to others', () => {
    const { container } = render(<HandbookPage {...props} />);
    fireEvent.mouseEnter(container.querySelector('li[data-n="2"]')!);
    const g = (n: string) => container.querySelector(`g[data-marker="${n}"]`)!;
    expect(g('2').getAttribute('class')).toContain('hb-act');
    expect(g('1').getAttribute('class')).toContain('hb-dim');
    expect(g('3').getAttribute('class')).toContain('hb-dim');
    fireEvent.mouseLeave(container.querySelector('li[data-n="2"]')!);
    expect(g('1').getAttribute('class') ?? '').not.toContain('hb-dim');
  });
  it('narrow variant puts steps after figure in DOM order', () => {
    const { container } = render(<HandbookPage {...props} variant="narrow" />);
    const svg = container.querySelector('svg[role="img"]')!;
    const ol = container.querySelector('ol')!;
    expect(svg.compareDocumentPosition(ol) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector('details')).not.toBeNull();
  });
  it('each task has id anchor equal to task id', () => {
    const { container } = render(<HandbookPage {...props} />);
    expect(container.querySelector('section#ueberblick')).not.toBeNull();
    expect(container.querySelector('section#zweite')).not.toBeNull();
  });
  it('wide variant renders each chapter/task id exactly once', () => {
    const { container } = render(<HandbookPage {...props} />);
    for (const id of ['zeit', 'ueberblick', 'zweite']) {
      expect(container.querySelectorAll(`[id="${id}"]`).length).toBe(1);
    }
    expect(container.querySelectorAll('main').length).toBe(0);
    const svg = container.querySelector('svg[role="img"]')!;
    expect(svg.compareDocumentPosition(container.querySelector('ol')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
  it('marker radius doubles when crop width doubles', () => {
    const r = (w: number) => {
      const mf = { ...manifest, s1: { ...manifest.s1, crop: { ...manifest.s1.crop, w } } };
      const { container } = render(<HandbookPage {...props} manifest={mf} />);
      return Number(container.querySelector('circle')!.getAttribute('r'));
    };
    expect(r(1400)).toBeCloseTo(2 * r(700));
    expect(r(700)).toBeCloseTo(17);
  });
  it('number circle sits left of the frame, vertically centred (R18)', () => {
    const mf = { ...manifest, s1: { ...manifest.s1, crop: { x: 256, y: 0, w: 1184, h: 900 },
      markers: { ...manifest.s1.markers, b: { x: 600, y: 164, w: 40, h: 40 } } } };
    const { container } = render(<HandbookPage {...props} manifest={mf} />);
    const g = container.querySelector('g[data-marker="2"]')!;
    const rect = g.querySelector('rect')!;
    const circle = g.querySelector('circle')!;
    const [x, y, h] = ['x', 'y', 'height'].map((a) => Number(rect.getAttribute(a)));
    const [cx, cy, r] = ['cx', 'cy', 'r'].map((a) => Number(circle.getAttribute(a)));
    // R20: Rahmen mit Abstand 4·k um die vermessene Box (k = 1184 / 700), Kreis aus dem Rahmen
    const k = 1184 / 700;
    expect(x).toBeCloseTo(600 - 4 * k);
    expect(y).toBeCloseTo(164 - 4 * k);
    expect(Number(rect.getAttribute('width'))).toBeCloseTo(40 + 8 * k);
    expect(cx).toBeCloseTo(x - 1.3 * r);
    expect(cy).toBeCloseTo(y + h / 2);
    expect(Number(g.querySelector('text')!.getAttribute('x'))).toBe(cx);
    expect(Number(g.querySelector('text')!.getAttribute('y'))).toBe(cy);
  });
  it('image href uses imgBase', () => {
    const { container } = render(<HandbookPage {...props} />);
    expect(container.querySelector('image')!.getAttribute('href')).toBe('/help/img/s1.webp');
    expect(container.querySelector('a[target="_blank"]')!.getAttribute('href')).toBe('/help/img/s1.webp');
    expect(container.querySelector('svg[role="img"]')!.getAttribute('aria-label')).toContain('Zeiterfassung');
  });
  it('renders comics and diagrams by key, unknown diagram renders no figure content', () => {
    const { container, queryByTestId } = render(<HandbookPage {...props} />);
    expect(queryByTestId('comic')).not.toBeNull();
    expect(queryByTestId('diagram')).not.toBeNull();
    const u = render(<HandbookPage {...props} diagrams={{}} />);
    expect(u.container.querySelector('[data-testid="diagram"]')).toBeNull();
    expect(container.querySelector('table')).not.toBeNull();
  });
});

describe('HandbookPage internal link handler', () => {
  const linked: Handbook = {
    ...handbook,
    lead: 'Siehe [Kapitel](handbuch:praxisleitung#pl-x) und [extern](https://example.org/)',
  };
  it('renders a plain anchor without a handler', () => {
    const { container } = render(<HandbookPage {...props} handbook={linked} />);
    const a = container.querySelector('a[href="/handbuch/praxisleitung#pl-x"]');
    expect(a).not.toBeNull();
  });
  it('calls the handler with the resolved href for internal links and prevents default', () => {
    const calls: string[] = [];
    const { container } = render(
      <HandbookPage {...props} handbook={linked} onInternalLink={(href, e) => { calls.push(href); e.preventDefault(); }} />,
    );
    const a = container.querySelector('a[href="/handbuch/praxisleitung#pl-x"]')!;
    const notPrevented = fireEvent.click(a);
    expect(calls).toEqual(['/handbuch/praxisleitung#pl-x']);
    expect(notPrevented).toBe(false);
  });
  it('does not route external links through the handler', () => {
    const calls: string[] = [];
    const { container } = render(
      <HandbookPage {...props} handbook={linked} onInternalLink={(href) => { calls.push(href); }} />,
    );
    fireEvent.click(container.querySelector('a[href="https://example.org/"]')!);
    expect(calls).toEqual([]);
  });
});
