/**
 * Hinweiszeile zu einem gekappten Zeiteintrag (#201/#462).
 *
 * Wird eine Zeit auf das hinterlegte Arbeitszeit-Fenster gekappt, merkt sich das
 * Backend den Rohwert in `raw_start_time`/`raw_end_time`. Ohne diese Zeile sieht
 * der Betrachter nur die gekappte Zeit — genau die stille Änderung, die der
 * Melder in #462 beanstandet hat.
 *
 * DIE eine Quelle des Textes: die Zeile stand vorher in zwei Fassungen in
 * MonthlyJournal ("gestempelt 07:30 · ab 07:45") und TimeTracking, und im
 * Admin-Dashboard (der vom Melder zuerst genannten Fläche) gar nicht. Verbindlich
 * ist die Fassung, die im Handbuch und im Cheat-Sheet wörtlich zitiert wird:
 * "gestempelt 07:30 · angerechnet ab 07:45" — die Nutzer-Doku hat fünf
 * Sync-Flächen, eine dritte Formulierung hier hieße, sie alle nachzuziehen.
 */
interface RawStampNoteProps {
  raw?: string | null;
  effective?: string | null;
  side: 'start' | 'end';
  className?: string;
}

export function RawStampNote({ raw, effective, side, className }: RawStampNoteProps) {
  if (!raw || !effective) return null;
  return (
    <div className={className ?? 'text-xs text-gray-500 mt-0.5'}>
      gestempelt {raw.substring(0, 5)} · angerechnet {side === 'start' ? 'ab' : 'bis'}{' '}
      {effective.substring(0, 5)}
    </div>
  );
}
