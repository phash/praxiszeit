import { useEffect, useId, useRef, useState, type FocusEvent, type KeyboardEvent } from 'react';
import { Link } from 'react-router-dom';
import { HelpCircle } from 'lucide-react';
import { handbookHints, type HintId } from '../constants/handbookHints';

interface HandbookHintProps {
  hintId: HintId;
}

/**
 * „?“-Kurzhilfe neben einem Feld: Knopf mit Popover (Titel, Kurztext, Link ins Handbuch).
 * Schließt mit Esc, mit Klick daneben und wenn der Fokus das Popover verlässt.
 * Unter 640 px erscheint das Popover als Bottom-Sheet.
 */
export default function HandbookHint({ hintId }: HandbookHintProps) {
  const hint = handbookHints[hintId];
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) setOpen(false);
    };
    // Rückfall, falls der Fokus nicht im Popover liegt (z. B. Safari fokussiert Knöpfe beim Klick nicht).
    const onDocKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape' && !e.defaultPrevented) setOpen(false);
    };
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onDocKey);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onDocKey);
    };
  }, [open]);

  const onKeyDown = (e: KeyboardEvent<HTMLSpanElement>) => {
    if (open && e.key === 'Escape') {
      // Nur die Kurzhilfe schließen, nicht einen umgebenden Dialog.
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
    }
  };

  const onBlur = (e: FocusEvent<HTMLSpanElement>) => {
    // Ohne Ziel (Klick auf nicht fokussierbare Fläche) entscheidet der Klick-daneben-Handler,
    // sonst ginge ein Klick auf den Link verloren, bevor er ankommt.
    const next = e.relatedTarget as Node | null;
    if (next && !wrapperRef.current?.contains(next)) setOpen(false);
  };

  return (
    <span ref={wrapperRef} className="relative inline-flex align-middle" onKeyDown={onKeyDown} onBlur={onBlur}>
      <button
        type="button"
        aria-label={`Hilfe: ${hint.title}`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center text-gray-400 hover:text-primary focus:outline-hidden focus-visible:ring-2 focus-visible:ring-primary rounded-full"
      >
        <HelpCircle size={16} aria-hidden="true" />
      </button>
      {open && (
        <div
          role="dialog"
          aria-labelledby={titleId}
          className="fixed inset-x-0 bottom-0 z-50 rounded-t-lg border border-gray-200 bg-white p-4 shadow-lg sm:absolute sm:inset-x-auto sm:bottom-auto sm:left-0 sm:top-full sm:mt-1 sm:w-72 sm:rounded-lg sm:p-3 text-left font-normal normal-case"
        >
          <p id={titleId} className="text-sm font-semibold text-gray-900">
            {hint.title}
          </p>
          <p className="mt-1 text-sm text-gray-700">{hint.text}</p>
          <Link
            to={`/help/${hint.book}#${hint.anchor}`}
            onClick={() => setOpen(false)}
            className="mt-2 inline-block text-sm font-medium text-primary hover:text-primary-dark"
          >
            Mehr im Handbuch →
          </Link>
        </div>
      )}
    </span>
  );
}
