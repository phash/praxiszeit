import { useEffect, useId, useLayoutEffect, useRef, useState, type FocusEvent } from 'react';
import { Link } from 'react-router-dom';
import { HelpCircle } from 'lucide-react';
import { handbookHints, type HintId } from '../constants/handbookHints';

interface HandbookHintProps {
  hintId: HintId;
  /**
   * Ab 640 px: Popover links bündig unter dem Knopf (`start`, Standard) oder rechts bündig (`end`).
   * Das ist nur die Vorzugsrichtung: reicht der Platz nicht, schiebt die Kurzhilfe das Popover
   * beim Öffnen in den sichtbaren Bereich (Bildschirm und abschneidende Vorfahren).
   */
  align?: 'start' | 'end';
  /**
   * Handbuch-Link in neuem Tab öffnen. Ohne Angabe automatisch, sobald die Kurzhilfe in einem
   * modalen Dialog (`aria-modal="true"`) steht – ein Seitenwechsel würde den Dialog samt
   * ungespeicherter Eingaben schließen.
   */
  newTab?: boolean;
}

/** Abstand des Popovers zum Rand des sichtbaren Bereichs (px). */
const EDGE_MARGIN = 8;

/**
 * Sichtbarer horizontaler Bereich für ein Element: Bildschirm, geschnitten mit jedem Vorfahren,
 * der waagerecht abschneidet oder scrollt (`overflow-x` ≠ visible, z. B. `<main
 * class="overflow-x-hidden">` oder ein Dialog mit `overflow-y-auto`).
 */
function visibleHorizontalBounds(el: HTMLElement): { left: number; right: number } {
  let left = 0;
  let right = document.documentElement.clientWidth || window.innerWidth;
  for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
    const ox = window.getComputedStyle(p).overflowX;
    if (ox && ox !== 'visible') {
      const r = p.getBoundingClientRect();
      if (r.right > r.left) {
        left = Math.max(left, r.left);
        right = Math.min(right, r.right);
      }
    }
  }
  return { left, right };
}

/**
 * „?“-Kurzhilfe neben einem Feld: Knopf mit Popover (Titel, Kurztext, Link ins Handbuch).
 * Schließt mit Esc, mit Klick daneben und wenn der Fokus das Popover verlässt.
 * Unter 640 px erscheint das Popover als Bottom-Sheet.
 */
export default function HandbookHint({ hintId, align = 'start', newTab }: HandbookHintProps) {
  const hint = handbookHints[hintId];
  const [open, setOpen] = useState(false);
  const [inModal, setInModal] = useState(false);
  const [offset, setOffset] = useState<number | null>(null);
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) setOpen(false);
    };
    // Esc in der Capture-Phase am window: läuft vor jedem Listener auf document (focus-trap,
    // ChangeRequestForm) und unabhängig davon, wo der Fokus steht (Safari fokussiert Knöpfe beim
    // Klick nicht). Schließt nur die Kurzhilfe, der umgebende Dialog sieht dieses Esc nicht.
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.isComposing) return;
      e.preventDefault();
      e.stopPropagation();
      const focusInside = !!wrapperRef.current?.contains(document.activeElement);
      setOpen(false);
      if (focusInside) btnRef.current?.focus();
    };
    document.addEventListener('mousedown', onMouseDown);
    window.addEventListener('keydown', onEsc, true);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('keydown', onEsc, true);
    };
  }, [open]);

  // Ab 640 px in den sichtbaren Bereich schieben (vor dem Zeichnen, kein Flackern).
  useLayoutEffect(() => {
    if (!open) {
      setOffset(null);
      return;
    }
    const place = () => {
      const wrapper = wrapperRef.current;
      const pop = popRef.current;
      // Unter 640 px (Bottom-Sheet) oder ohne Messwerte: Klassen allein entscheiden.
      if (!wrapper || !pop || typeof window.matchMedia !== 'function' || !window.matchMedia('(min-width: 640px)').matches) {
        setOffset(null);
        return;
      }
      const width = pop.offsetWidth;
      const w = wrapper.getBoundingClientRect();
      if (!width || w.right <= w.left) {
        setOffset(null);
        return;
      }
      const bounds = visibleHorizontalBounds(wrapper);
      const desired = align === 'end' ? w.width - width : 0;
      const min = bounds.left + EDGE_MARGIN - w.left;
      const max = bounds.right - EDGE_MARGIN - width - w.left;
      // Schmaler als das Popover: am linken Rand ausrichten, damit der Textanfang lesbar bleibt.
      setOffset(max < min ? min : Math.min(Math.max(desired, min), max));
    };
    place();
    window.addEventListener('resize', place);
    return () => window.removeEventListener('resize', place);
  }, [open, align]);

  const onBlur = (e: FocusEvent<HTMLSpanElement>) => {
    // Ohne Ziel (Klick auf nicht fokussierbare Fläche) entscheidet der Klick-daneben-Handler,
    // sonst ginge ein Klick auf den Link verloren, bevor er ankommt.
    const next = e.relatedTarget as Node | null;
    if (next && !wrapperRef.current?.contains(next)) setOpen(false);
  };

  const toggle = () => {
    // Safari/Firefox (macOS) fokussieren Knöpfe beim Klick nicht – sonst liefe ein Klick ins
    // Popover am Fokus-Handling vorbei.
    btnRef.current?.focus();
    if (!open) setInModal(!!wrapperRef.current?.parentElement?.closest('[aria-modal="true"]'));
    setOpen((v) => !v);
  };

  const openInNewTab = newTab ?? inModal;

  return (
    <span ref={wrapperRef} className="relative inline-flex align-middle" onBlur={onBlur}>
      <button
        ref={btnRef}
        type="button"
        aria-label={`Hilfe: ${hint.title}`}
        aria-expanded={open}
        onClick={toggle}
        className="inline-flex items-center text-gray-400 hover:text-primary focus:outline-hidden focus-visible:ring-2 focus-visible:ring-primary rounded-full"
      >
        <HelpCircle size={16} aria-hidden="true" />
      </button>
      {open && (
        <div
          ref={popRef}
          role="dialog"
          aria-labelledby={titleId}
          // Fokussierbar (nicht in der Tab-Reihenfolge): ein Klick auf Text im Popover gibt den Fokus
          // hierher statt an `<main tabIndex=-1>` bzw. den Dialog-Container – sonst schlösse onBlur.
          tabIndex={-1}
          style={offset === null ? undefined : { left: `${offset}px`, right: 'auto' }}
          className={`fixed inset-x-0 bottom-0 z-50 rounded-t-lg border border-gray-200 bg-white p-4 shadow-lg focus:outline-hidden sm:absolute sm:inset-x-auto sm:bottom-auto ${
            align === 'end' ? 'sm:right-0' : 'sm:left-0'
          } sm:top-full sm:mt-1 sm:w-72 sm:rounded-lg sm:p-3 text-left font-normal normal-case`}
        >
          <p id={titleId} className="text-sm font-semibold text-gray-900">
            {hint.title}
          </p>
          <p className="mt-1 text-sm text-gray-700">{hint.text}</p>
          <Link
            to={`/help/${hint.book}#${hint.anchor}`}
            onClick={() => setOpen(false)}
            {...(openInNewTab ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
            className="mt-2 inline-block text-sm font-medium text-primary hover:text-primary-dark"
          >
            Mehr im Handbuch →{openInNewTab && <span className="sr-only"> (öffnet in neuem Tab)</span>}
          </Link>
        </div>
      )}
    </span>
  );
}
