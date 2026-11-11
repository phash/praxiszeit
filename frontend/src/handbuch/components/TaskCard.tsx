import { useState } from 'react';
import { renderInline } from '../inline';
import type { InlineOpts } from '../inline';
import type { ManifestShot, ShotDef, Step } from '../types';
import ShotFigure from './ShotFigure';
import StepList from './StepList';

export interface TaskCardProps {
  id: string;
  title: string;
  intro?: string;
  steps: Step[];
  shot?: { shotId: string; def: ShotDef; m: ManifestShot };
  imgBase: string;
  opts: InlineOpts;
  variant: 'wide' | 'narrow';
}

export default function TaskCard({ id, title, intro, steps, shot, imgBase, opts, variant }: TaskCardProps) {
  const [active, setActive] = useState<number | null>(null);
  const layout =
    shot && variant === 'wide' ? 'grid items-start gap-6 grid-cols-[minmax(0,1fr)_300px]' : 'flex flex-col gap-4';
  return (
    <section id={id} className="mb-7 scroll-mt-5 rounded-2xl border border-slate-200 bg-white p-4 sm:p-6">
      <h2 className="m-0 mb-1 text-[22px] font-bold">{title}</h2>
      {intro && <p className="m-0 mb-4 text-slate-500">{renderInline(intro, opts)}</p>}
      <div className={layout}>
        {shot && (
          <ShotFigure shotId={shot.shotId} def={shot.def} m={shot.m} imgBase={imgBase} active={active} />
        )}
        <StepList steps={steps} opts={opts} active={active} onActive={setActive} />
      </div>
    </section>
  );
}
