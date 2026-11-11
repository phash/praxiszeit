import { renderInline } from '../inline';
import type { InlineOpts } from '../inline';
import type { Step } from '../types';

export interface StepListProps {
  steps: Step[];
  opts: InlineOpts;
  onActive?: (n: number | null) => void;
  active?: number | null;
}

export default function StepList({ steps, opts, onActive, active = null }: StepListProps) {
  return (
    <ol role="list" className="m-0 list-none p-0">
      {steps.map((s, i) => {
        const n = s.n;
        const on = n !== undefined ? () => onActive?.(n) : undefined;
        const off = n !== undefined ? () => onActive?.(null) : undefined;
        return (
          <li
            key={i}
            data-n={n}
            tabIndex={n !== undefined ? 0 : undefined}
            onMouseEnter={on}
            onMouseLeave={off}
            onFocus={on}
            onBlur={off}
            className={`flex gap-3 rounded-lg p-2.5 text-[15px] leading-snug hover:bg-amber-50 focus:bg-amber-50 focus:outline-none ${
              n !== undefined && active === n ? 'bg-amber-50' : ''
            }`}
          >
            {n !== undefined && (
              <b className="grid h-7 w-7 flex-none place-items-center rounded-full bg-amber-500 text-sm text-white">{n}</b>
            )}
            <span>{renderInline(s.text, opts)}</span>
          </li>
        );
      })}
    </ol>
  );
}
