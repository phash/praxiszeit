import { renderInline } from '../inline';
import type { InlineOpts } from '../inline';

export default function TipBox({ tone, text, opts }: { tone: 'info' | 'warn'; text: string; opts: InlineOpts }) {
  const cls =
    tone === 'warn'
      ? 'border-amber-500 bg-amber-50'
      : 'border-[#3d8bbd] bg-[#eaf3f9]';
  return (
    <div role="note" className={`my-4 flex gap-3 rounded-lg border-l-4 px-3.5 py-3 text-sm leading-snug ${cls}`}>
      <span aria-hidden="true">{tone === 'warn' ? '⚠️' : '💡'}</span>
      <span>{renderInline(text, opts)}</span>
    </div>
  );
}
