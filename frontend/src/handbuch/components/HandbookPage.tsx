import type { ComponentType } from 'react';
import { renderInline } from '../inline';
import type { InlineOpts } from '../inline';
import type { Block, Handbook, Manifest } from '../types';
import ComicSlot from './ComicSlot';
import TaskCard from './TaskCard';
import TipBox from './TipBox';
import Toc from './Toc';

export interface HandbookPageProps {
  handbook: Handbook;
  manifest: Manifest;
  imgBase: string;
  linkBase: string;
  variant: 'wide' | 'narrow';
  comics?: Record<string, ComponentType>;
  diagrams?: Record<string, ComponentType>;
}

export default function HandbookPage({
  handbook, manifest, imgBase, linkBase, variant, comics, diagrams,
}: HandbookPageProps) {
  const opts: InlineOpts = { linkBase };

  const renderBlock = (b: Block, key: string) => {
    switch (b.kind) {
      case 'task': {
        const def = b.shot ? handbook.shots.find((s) => s.id === b.shot) : undefined;
        const m = b.shot ? manifest[b.shot] : undefined;
        return (
          <TaskCard
            key={key}
            id={b.id}
            title={b.title}
            intro={b.intro}
            steps={b.steps}
            shot={b.shot && def && m ? { shotId: b.shot, def, m } : undefined}
            imgBase={imgBase}
            opts={opts}
            variant={variant}
          />
        );
      }
      case 'tip':
        return <TipBox key={key} tone={b.tone} text={b.text} opts={opts} />;
      case 'comic':
        return <ComicSlot key={key} Scene={comics?.[b.scene]} text={b.text} opts={opts} />;
      case 'diagram': {
        const D = diagrams?.[b.diagram];
        return (
          <figure key={key} className="my-6">
            {D ? <D /> : null}
            <figcaption className="mt-2 text-sm text-slate-500">{renderInline(b.caption, opts)}</figcaption>
          </figure>
        );
      }
      case 'table':
        return (
          <div key={key} className="my-4 overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr>
                  {b.head.map((h, i) => (
                    <th key={i} className="border-b border-slate-300 px-3 py-2 font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {b.rows.map((r, i) => (
                  <tr key={i}>
                    {r.map((c, j) => (
                      <td key={j} className="border-b border-slate-200 px-3 py-2 align-top">{renderInline(c, opts)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      case 'prose':
        return <p key={key} className="my-4 leading-relaxed">{renderInline(b.text, opts)}</p>;
    }
  };

  const content = (
    <div className="min-w-0">
      <h1 className="m-0 mb-2 text-3xl font-bold">{handbook.title}</h1>
      <p className="m-0 mb-6 max-w-3xl text-lg leading-normal text-slate-700">{renderInline(handbook.lead, opts)}</p>
      {handbook.chapters.map((c) => (
        <div key={c.id}>
          <h2 id={c.id} className="mb-4 mt-8 scroll-mt-5 text-2xl font-bold">{c.title}</h2>
          {c.blocks.map((b, i) => renderBlock(b, `${c.id}-${i}`))}
        </div>
      ))}
    </div>
  );

  return (
    <div className={variant === 'wide' ? 'hb-root lg:grid lg:grid-cols-[250px_minmax(0,1fr)] lg:gap-9' : 'hb-root'}>
      <Toc title={handbook.title} chapters={handbook.chapters} variant={variant} />
      {content}
    </div>
  );
}
