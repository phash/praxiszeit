/**
 * Hinweiszeile zu einem gekappten bzw. nicht vollständig angerechneten
 * Zeiteintrag (#201/#462, Spec 2026-10-08 Abschnitt 13.1).
 *
 * DIE eine Quelle des Textes für Admin-Dashboard, Monatsjournal und
 * Zeiterfassung (Tabelle UND Mobilkarte). „angerechnet" ist immer `net_hours`
 * (nach Pause und Lücke), „nicht angerechnet" = Lücke + Hülle
 * (`not_credited_minutes`, P19). Der Hülle-Wortlaut „gestempelt 07:30 ·
 * angerechnet ab 07:45" wird in Handbuch und Cheat-Sheet wörtlich zitiert und
 * bleibt deshalb unverändert — die Nutzer-Doku hat fünf Sync-Flächen.
 */
import { formatHoursHM } from '../utils/formatters';
import type { StampNoteData } from '../utils/workBlocks';

interface RawStampNoteProps extends StampNoteData {
  /** P21: nur die Mitarbeiter-Ansicht übergibt das — Aktion „Anrechnung beantragen". */
  onRequestCredit?: () => void;
  className?: string;
}

/** Ende eines automatisch geschlossenen Eintrags, solange nichts es kappt (P18). */
const AUTO_CLOSE_END = '23:59';

function hm(minutes: number): string {
  return formatHoursHM(minutes / 60);
}

export function RawStampNote({
  uncreditedMinutes, notCreditedMinutes, rawSpan, effSpan, creditedHours, breakMinutes,
  autoClosed, creditOverride, onRequestCredit, className,
}: RawStampNoteProps) {
  const cls = className ?? 'text-xs text-gray-500 mt-0.5';
  if (creditOverride) {
    return (
      <div className={cls}>
        <span
          className="inline-flex items-center px-1.5 py-0.5 rounded-sm text-xs font-medium bg-gray-100 text-gray-600"
          title="Von der Verwaltung anerkannt – die gesamte gestempelte Zeit wird angerechnet"
        >
          anerkannt
        </span>
      </div>
    );
  }

  const [rawStart, rawEnd] = rawSpan.split('–');
  const [effStart, effEnd] = effSpan.split('–');
  const credited = `angerechnet ${formatHoursHM(creditedHours)} h${breakMinutes > 0 ? ` nach ${hm(breakMinutes)} h Pause` : ''}`;
  const gapTail = uncreditedMinutes > 0 ? ` · ${hm(uncreditedMinutes)} h zwischen den Blöcken nicht angerechnet` : '';
  const startLine = rawStart && rawStart !== effStart ? `gestempelt ${rawStart} · angerechnet ab ${effStart}` : null;
  const lines: string[] = [];

  if (autoClosed) {
    // Der Text hängt am wirksamen Ende, NICHT an „Rohende leer": ein auf einen
    // anderen Tag verschobener Eintrag trägt 18:15 ohne Rohende bzw. ein
    // Rohende 18:15 (work_window_service.end_input_for) — „um 18:15" hieße,
    // das System hätte um 18:15 geschlossen.
    const base = `eingestempelt ${rawStart}, nicht ausgestempelt – automatisch geschlossen`;
    if (effEnd === AUTO_CLOSE_END) {
      // ungekappt: ohne Blöcke bzw. Ende-Platzhalter eines halboffenen Altfensters
      lines.push(`${base} um ${effEnd}${gapTail}`);
      if (startLine) lines.push(startLine);
    } else {
      lines.push(`${base} · ${credited} (${effSpan})${gapTail}`);
    }
  } else if (!effEnd) {
    // offener Eintrag: nur die Hülle des Beginns (P17, K20 nach dem Einstempeln)
    if (startLine) lines.push(startLine);
  } else if (notCreditedMinutes > 0) {
    if (uncreditedMinutes === 0) {
      if (startLine) lines.push(startLine);
      if (rawEnd !== effEnd) lines.push(`gestempelt ${rawEnd} · angerechnet bis ${effEnd}`);
    } else if (uncreditedMinutes === notCreditedMinutes) {
      lines.push(`gestempelt ${rawSpan} · ${credited}${gapTail}`);
    } else {
      lines.push(
        `gestempelt ${rawSpan} · ${credited} (${effSpan}) · ${hm(notCreditedMinutes)} h nicht angerechnet, `
        + `davon ${hm(uncreditedMinutes)} h zwischen den Blöcken`,
      );
    }
  }

  // Spec 14: nur an geschlossenen Einträgen; ob der Tag vorbei ist und der
  // Eintrag der Person gehört, entscheidet der Aufrufer.
  const offer = !!onRequestCredit && !!effEnd && notCreditedMinutes > 0;
  if (lines.length === 0 && !offer) return null;
  return (
    <div className={cls}>
      {lines.map((line) => <div key={line}>{line}</div>)}
      {offer && (
        <button
          type="button"
          onClick={onRequestCredit}
          className="mt-0.5 text-amber-700 underline hover:text-amber-900"
        >
          Anrechnung beantragen
        </button>
      )}
    </div>
  );
}
