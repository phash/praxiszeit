import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { RawStampNote } from './RawStampNote';
import { stampNoteProps } from '../utils/workBlocks';
import { K_CASES_FE } from '../utils/workBlocksCases';

function kNote(id: string, extra: { onRequestCredit?: () => void } = {}) {
  const k = K_CASES_FE.find((c) => c.id === id)!;
  return render(
    <RawStampNote {...stampNoteProps({ ...k.stored, credit_override: k.creditOverride })} {...extra} />,
  );
}

describe('RawStampNote — Spec 13.1 (PR2)', () => {
  it.each([
    ['K1', 'gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet'],
    ['K7', 'gestempelt 07:00–19:00 · angerechnet 8:00 h (07:45–18:15) · 4:00 h nicht angerechnet, davon 2:30 h zwischen den Blöcken'],
    ['K9', 'gestempelt 08:00–18:00 · angerechnet 7:00 h nach 0:30 h Pause · 2:30 h zwischen den Blöcken nicht angerechnet'],
    ['K15', 'eingestempelt 08:00, nicht ausgestempelt – automatisch geschlossen · angerechnet 7:45 h (08:00–18:15) · 2:30 h zwischen den Blöcken nicht angerechnet'],
    ['K20', 'gestempelt 07:00–18:00 · angerechnet 7:45 h (07:45–18:00) · 3:15 h nicht angerechnet, davon 2:30 h zwischen den Blöcken'],
  ])('%s', (id, text) => {
    kNote(id);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it('nur Hülle: Wortlaut je Seite unverändert (Handbuch und Cheat-Sheet zitieren ihn)', () => {
    render(<RawStampNote {...stampNoteProps({
      start_time: '07:45:00', end_time: '17:15:00', raw_start_time: '07:37:00', raw_end_time: '18:20:00',
      break_minutes: 30, net_hours: 9, uncredited_minutes: 0,
    })} />);
    expect(screen.getByText('gestempelt 07:37 · angerechnet ab 07:45')).toBeInTheDocument();
    expect(screen.getByText('gestempelt 18:20 · angerechnet bis 17:15')).toBeInTheDocument();
  });

  it('Kollaps vor der Hülle (K8): nur die Endseite, wie bisher', () => {
    kNote('K8');
    expect(screen.getByText('gestempelt 07:00 · angerechnet bis 05:00')).toBeInTheDocument();
  });

  it('nichts gekappt (K4): keine Zeile', () => {
    const { container } = kNote('K4');
    expect(container).toBeEmptyDOMElement();
  });

  // Review Focus 2
  it('offener Eintrag mit Beginn vor der Hülle (K20 nach dem Einstempeln)', () => {
    render(<RawStampNote {...stampNoteProps({
      start_time: '07:45:00', end_time: null, raw_start_time: '07:00:00',
      break_minutes: 0, net_hours: 0, uncredited_minutes: 0,
    })} />);
    expect(screen.getByText('gestempelt 07:00 · angerechnet ab 07:45')).toBeInTheDocument();
    expect(screen.queryByText(/angerechnet \d+:\d\d h/)).not.toBeInTheDocument();
  });

  it('automatisch geschlossen ohne Blöcke: „… um 23:59"', () => {
    render(<RawStampNote {...stampNoteProps({
      start_time: '08:00:00', end_time: '23:59:00', break_minutes: 0, net_hours: 15.98,
      uncredited_minutes: 0, auto_closed: true,
    })} />);
    expect(screen.getByText('eingestempelt 08:00, nicht ausgestempelt – automatisch geschlossen um 23:59')).toBeInTheDocument();
  });

  // Orchestrator-Hinweis (3): der Text hängt an auto_closed + end_time, nicht an
  // „raw_end_time ist leer" — ein auf einen Tag ohne Blöcke verschobener
  // Auto-Close-Eintrag trägt end_time 18:15 und KEIN Rohende (end_input_for).
  it('verschobener automatisch geschlossener Eintrag (Rohende leer, Ende 18:15): kein „um 18:15"', () => {
    render(<RawStampNote {...stampNoteProps({
      start_time: '08:00:00', end_time: '18:15:00', raw_end_time: null, break_minutes: 0, net_hours: 10.25,
      uncredited_minutes: 0, auto_closed: true,
    })} />);
    expect(screen.getByText(
      'eingestempelt 08:00, nicht ausgestempelt – automatisch geschlossen · angerechnet 10:15 h (08:00–18:15)',
    )).toBeInTheDocument();
    expect(screen.queryByText(/um 18:15/)).not.toBeInTheDocument();
  });

  it('verschobener automatisch geschlossener Eintrag (Rohende 18:15, Ende 16:15)', () => {
    render(<RawStampNote {...stampNoteProps({
      start_time: '08:00:00', end_time: '16:15:00', raw_end_time: '18:15:00', break_minutes: 0, net_hours: 8.25,
      uncredited_minutes: 0, auto_closed: true,
    })} />);
    expect(screen.getByText(
      'eingestempelt 08:00, nicht ausgestempelt – automatisch geschlossen · angerechnet 8:15 h (08:00–16:15)',
    )).toBeInTheDocument();
  });

  // Halboffenes Altfenster (Spec 5.3): Ende-Platzhalter 23:59, Beginn gekappt —
  // die Beginn-Kappung bleibt sichtbar (#462), auch neben „um 23:59".
  it('automatisch geschlossen um 23:59 mit gekapptem Beginn: Beginn-Zeile bleibt', () => {
    render(<RawStampNote {...stampNoteProps({
      start_time: '07:45:00', end_time: '23:59:00', raw_start_time: '07:00:00', break_minutes: 0,
      net_hours: 16.23, uncredited_minutes: 0, auto_closed: true,
    })} />);
    expect(screen.getByText('eingestempelt 07:00, nicht ausgestempelt – automatisch geschlossen um 23:59')).toBeInTheDocument();
    expect(screen.getByText('gestempelt 07:00 · angerechnet ab 07:45')).toBeInTheDocument();
  });

  it('anerkannt: Kennzeichen statt Kappungszeile', () => {
    render(<RawStampNote {...stampNoteProps({
      start_time: '07:00:00', end_time: '19:00:00', break_minutes: 0, net_hours: 12,
      uncredited_minutes: 0, credit_override: true,
    })} />);
    expect(screen.getByText('anerkannt')).toBeInTheDocument();
    expect(screen.queryByText(/gestempelt/)).not.toBeInTheDocument();
  });

  it('„Anrechnung beantragen" nur mit onRequestCredit (Mitarbeiter-Ansicht, P21)', () => {
    const { unmount } = kNote('K1');
    expect(screen.queryByRole('button', { name: 'Anrechnung beantragen' })).not.toBeInTheDocument();
    unmount();
    const onRequestCredit = vi.fn();
    kNote('K1', { onRequestCredit });
    fireEvent.click(screen.getByRole('button', { name: 'Anrechnung beantragen' }));
    expect(onRequestCredit).toHaveBeenCalled();
  });

  it('„Anrechnung beantragen" nicht an offenen Einträgen (Spec 14: nur geschlossene)', () => {
    render(<RawStampNote {...stampNoteProps({
      start_time: '07:45:00', end_time: null, raw_start_time: '07:00:00',
      break_minutes: 0, net_hours: 0, uncredited_minutes: 0,
    })} onRequestCredit={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Anrechnung beantragen' })).not.toBeInTheDocument();
  });
});
