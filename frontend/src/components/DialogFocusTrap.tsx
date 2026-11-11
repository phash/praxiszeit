import { Children, cloneElement, isValidElement, type ReactElement } from 'react';
import FocusTrap, { type FocusTrapProps } from 'focus-trap-react';

/**
 * Fokusfalle für Dialoge — EINZIGER Weg zu `focus-trap-react` im Frontend
 * (Guard-Test `DialogFocusTrap.test.tsx`).
 *
 * Macht das umschlossene Element (den Dialog-Container) mit `tabIndex={-1}`
 * selbst fokussierbar, ohne es in die Tab-Reihenfolge aufzunehmen.
 *
 * Warum (Handbuch-Funde P1.6/P2.1): Ein Mausdruck auf nicht fokussierbaren
 * Inhalt (Text eines Labels, Überschrift, Absatz) gibt den Fokus an den
 * nächsten fokussierbaren Vorfahren. Das war `<main id="main-content"
 * tabIndex={-1}>` aus dem Layout — außerhalb der Falle. focus-trap holte den
 * Fokus darauf auf das zuletzt fokussierte Feld zurück und scrollte den Dialog
 * dorthin; der Klick landete neben dem Label (Radio/Checkbox nicht gewählt).
 * Ist der Container selbst fokussierbar, bleibt der Fokus in der Falle.
 *
 * Tastatur bleibt unverändert: `tabIndex=-1` ist nicht tabbable (Anfangsfokus
 * und Tab-Reihenfolge wie bisher), Escape regelt `focusTrapOptions`.
 */
export default function DialogFocusTrap({ children, ...props }: FocusTrapProps) {
  const child = Children.only(children);
  const focusable = isValidElement(child)
    ? cloneElement(child as ReactElement<{ tabIndex?: number; className?: string }>, {
        tabIndex: (child.props as { tabIndex?: number }).tabIndex ?? -1,
        className: [(child.props as { className?: string }).className, 'focus:outline-hidden']
          .filter(Boolean)
          .join(' '),
      })
    : child;
  return <FocusTrap {...props}>{focusable}</FocusTrap>;
}
