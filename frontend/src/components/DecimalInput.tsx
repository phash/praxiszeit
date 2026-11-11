import { useEffect, useRef, useState } from 'react';
import type { InputHTMLAttributes } from 'react';

/**
 * Zahlenfeld mit rohem Text-Zustand (Review 2026-11-11, user-05/user-17).
 *
 * Ein `type="number"`-Feld liefert beim Tippen von „-“ oder „0,“ einen leeren
 * bzw. unfertigen Wert; `parseFloat(...) || 0` im onChange schrieb dann sofort
 * „0“ zurück — Minuswerte waren kaum eintippbar, das Feld ließ sich nicht leeren.
 * Hier hält das Feld den getippten Text selbst und meldet nur die geparste Zahl;
 * von außen geänderte Werte (Laden, „Empfehlung übernehmen") ersetzen den Text.
 *
 * `emptyAs`: Wert für ein leeres/unfertiges Feld (Default `null`, z. B. `0`).
 */
type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type'> & {
  value: number | null | undefined;
  onValue: (n: number | null) => void;
  emptyAs?: number | null;
};

const norm = (v: number | null | undefined): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v : null;

export default function DecimalInput({ value, onValue, emptyAs = null, ...rest }: Props) {
  const parse = (t: string): number | null => {
    const n = parseFloat(t);
    return t.trim() === '' || !Number.isFinite(n) ? emptyAs : n;
  };
  const [text, setText] = useState(() => (norm(value) === null ? '' : String(value)));
  const own = useRef(false);

  useEffect(() => {
    if (own.current) return;            // Echo der eigenen Eingabe
    if (parse(text) !== norm(value)) setText(norm(value) === null ? '' : String(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  useEffect(() => { own.current = false; });

  return (
    <input
      {...rest}
      type="number"
      value={text}
      onChange={(e) => {
        own.current = true;
        setText(e.target.value);
        onValue(parse(e.target.value));
      }}
    />
  );
}
