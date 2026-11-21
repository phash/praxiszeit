import { describe, it, expect } from 'vitest';
import { bulkConfirmText, canRecognizeNow, isRecognizable } from './creditOverride';

// Plan 2026-11-21 Task 10: wann ein Eintrag anerkannt werden kann (Knopf im
// Eintrag und Häkchen im Monatsjournal teilen dieselbe Regel).

const gapped = {
  start_time: '08:00', end_time: '12:00', raw_start_time: '07:00', raw_end_time: null,
  uncredited_minutes: 0, not_credited_minutes: 60, credit_override: false, auto_closed: false,
};

describe('isRecognizable / canRecognizeNow', () => {
  it('Eintrag mit nicht angerechneter Zeit: anerkennbar', () => {
    expect(isRecognizable(gapped)).toBe(true);
    expect(canRecognizeNow(gapped)).toBe(true);
  });

  it('offener Eintrag: nicht anerkennbar', () => {
    const open = { ...gapped, end_time: null };
    expect(isRecognizable(open)).toBe(false);
    expect(canRecognizeNow(open)).toBe(false);
  });

  it('automatisch geschlossen: Knopf sichtbar (gesperrt), aber kein Häkchen', () => {
    const auto = { ...gapped, auto_closed: true };
    expect(isRecognizable(auto)).toBe(true);
    expect(canRecognizeNow(auto)).toBe(false);
  });

  it('schon anerkannt: nicht anerkennbar', () => {
    const done = { ...gapped, credit_override: true };
    expect(isRecognizable(done)).toBe(false);
    expect(canRecognizeNow(done)).toBe(false);
  });

  it('0 Minuten nicht angerechnet: nicht anerkennbar', () => {
    const full = { ...gapped, raw_start_time: null, not_credited_minutes: 0 };
    expect(isRecognizable(full)).toBe(false);
    expect(canRecognizeNow(full)).toBe(false);
  });

  it('ohne not_credited_minutes rechnet die Regel selbst (Lücke + Hülle)', () => {
    const { not_credited_minutes: _omit, ...noField } = gapped;
    void _omit;
    expect(isRecognizable(noField)).toBe(true);
  });
});

describe('bulkConfirmText', () => {
  it('Mehrzahl', () => {
    expect(bulkConfirmText(2, 512)).toBe(
      '2 Einträge werden mit der ganzen gestempelten Zeit angerechnet (zusätzlich 8:32 h). '
      + 'Anerkennen lässt sich nicht zurücknehmen. Der Vorgang wird protokolliert.',
    );
  });

  it('Einzahl', () => {
    expect(bulkConfirmText(1, 60)).toBe(
      '1 Eintrag wird mit der ganzen gestempelten Zeit angerechnet (zusätzlich 1:00 h). '
      + 'Anerkennen lässt sich nicht zurücknehmen. Der Vorgang wird protokolliert.',
    );
  });
});
