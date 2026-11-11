import type { Chapter } from '../types';

function links(chapters: Chapter[]) {
  return chapters.map((c) => (
    <div key={c.id}>
      <a href={`#${c.id}`} className="block rounded-lg px-2.5 py-1.5 text-slate-800 no-underline hover:bg-[#eaf3f9]">
        {c.title}
      </a>
      {c.blocks.map((b) =>
        b.kind === 'task' ? (
          <a
            key={b.id}
            href={`#${b.id}`}
            className="block rounded-lg py-1 pl-6 pr-2.5 text-[13px] text-slate-500 no-underline hover:bg-[#eaf3f9]"
          >
            {b.title}
          </a>
        ) : null,
      )}
    </div>
  ));
}

export default function Toc({ title, chapters, variant }: { title: string; chapters: Chapter[]; variant: 'wide' | 'narrow' }) {
  if (variant === 'narrow') {
    return (
      <details className="mb-4 rounded-xl border border-slate-200 bg-white p-3 text-sm">
        <summary className="cursor-pointer font-semibold">Inhalt</summary>
        <nav aria-label="Kapitelverzeichnis" className="mt-2">{links(chapters)}</nav>
      </details>
    );
  }
  return (
    <nav aria-label="Kapitelverzeichnis" className="sticky top-5 self-start text-sm">
      <h4 className="m-0 mb-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</h4>
      {links(chapters)}
    </nav>
  );
}
