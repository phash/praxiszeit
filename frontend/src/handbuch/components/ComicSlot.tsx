import type { ComponentType } from 'react';
import { renderInline } from '../inline';
import type { InlineOpts } from '../inline';

export default function ComicSlot({ Scene, text, opts }: { Scene?: ComponentType; text: string; opts: InlineOpts }) {
  return (
    <section className="mb-7 grid items-center gap-5 rounded-2xl bg-gradient-to-br from-[#fff7e6] to-[#eaf3f9] px-6 py-4 sm:grid-cols-[220px_minmax(0,1fr)]">
      <div className="mx-auto w-full max-w-[220px]">{Scene ? <Scene /> : null}</div>
      <p className="m-0 text-base leading-normal">{renderInline(text, opts)}</p>
    </section>
  );
}
