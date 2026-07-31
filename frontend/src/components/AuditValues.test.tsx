import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import AuditValues, { auditPillText, formatAuditNote } from './AuditValues';

describe('formatAuditNote', () => {
  it('übersetzt den internen Abwesenheits-Marker in deutschen Klartext', () => {
    expect(formatAuditNote('absence:sick:8.0h')).toBe('Krank 8,0 h');
    expect(formatAuditNote('absence:vacation:4.5h')).toBe('Urlaub 4,5 h');
    // Numeric(4,2): 8,25 h ist ein realer Wert und muss verlustfrei bleiben.
    expect(formatAuditNote('absence:other:8.25h')).toBe('Sonstiges 8,25 h');
  });

  it('entfernt die rohe UUID des Storno-Zusatzes', () => {
    expect(
      formatAuditNote('absence:vacation:8.0h (cancelled vacation_request 3f2a1b4c-0000-4000-8000-000000000001)'),
    ).toBe('Urlaub 8,0 h (Urlaubsantrag storniert)');
  });

  it('übersetzt den link-existing-Zusatz', () => {
    expect(formatAuditNote('absence:sick:4.0h (link-existing)')).toBe(
      'Krank 4,0 h (bestehende Abwesenheit verknüpft)',
    );
  });

  it('reicht unbekannte Marker und normale Notizen unverändert durch', () => {
    expect(formatAuditNote('absence:unbekannt:8.0h')).toBe('absence:unbekannt:8.0h');
    expect(formatAuditNote('absence:sick:achth')).toBe('absence:sick:achth');
    expect(formatAuditNote('Krank 4,0 h — Wochenstunden-Änderung ab 09.03.2026')).toBe(
      'Krank 4,0 h — Wochenstunden-Änderung ab 09.03.2026',
    );
    expect(formatAuditNote('E-Mail geändert: a@x.de → b@x.de')).toBe('E-Mail geändert: a@x.de → b@x.de');
    expect(formatAuditNote(undefined)).toBeUndefined();
    expect(formatAuditNote('')).toBeUndefined();
  });
});

describe('auditPillText', () => {
  it('lässt den hängenden Bindestrich weg, wenn es keine Zeiten gibt', () => {
    expect(auditPillText('2026-03-09')).toBe('2026-03-09');
    expect(auditPillText('2026-03-09', '08:00:00', '16:00:00')).toBe('2026-03-09 08:00 - 16:00');
    expect(auditPillText(undefined, undefined, undefined)).toBe('');
  });
});

describe('AuditValues (Block-Variante, Änderungsprotokoll-Zelle)', () => {
  it('zeigt für eine Zeile ohne Zeiten und ohne Pause keine leeren Angaben', () => {
    // Die Einzelzeile der Stundenrückrechnung: Datum + Freitext, sonst nichts.
    render(<AuditValues date="2026-03-09" note="Krank 4,0 h — Wochenstunden-Änderung ab 09.03.2026" />);
    expect(screen.getByText('2026-03-09')).toBeInTheDocument();
    expect(screen.getByText(/Krank 4,0 h/)).toBeInTheDocument();
    expect(screen.queryByText(/Pause/)).not.toBeInTheDocument();
  });

  it('zeigt den Freitext auch dann, wenn es gar kein Datum gibt', () => {
    // Die Sammelzeile: der ganze Inhalt steckt im Freitext.
    render(<AuditValues note="Wochenstunden-Änderung zum 2026-03-09: 2 Abwesenheit(en) nachgezogen" />);
    expect(screen.getByText(/2 Abwesenheit\(en\)/)).toBeInTheDocument();
  });

  it('rendert einen vollständigen Zeiteintrag unverändert vollständig', () => {
    render(
      <AuditValues date="2026-03-09" start="08:00:00" end="16:00:00" breakMinutes={30} />,
    );
    expect(screen.getByText('2026-03-09')).toBeInTheDocument();
    expect(screen.getByText('08:00 - 16:00')).toBeInTheDocument();
    expect(screen.getByText('Pause: 30 min')).toBeInTheDocument();
  });

  it('zeigt einen Strich, wenn die Seite komplett leer ist', () => {
    render(<AuditValues />);
    expect(screen.getByText('-')).toBeInTheDocument();
  });
});

describe('AuditValues (Inline-Variante, Detail-Modal)', () => {
  it('setzt das Präfix und lässt fehlende Teilangaben weg', () => {
    render(<AuditValues prefix="Neu" date="2026-03-09" note="absence:sick:8.0h" />);
    expect(screen.getByText('Neu: 2026-03-09 Krank 8,0 h')).toBeInTheDocument();
  });

  it('rendert nichts für eine leere Seite', () => {
    const { container } = render(<AuditValues prefix="Alt" />);
    expect(container).toBeEmptyDOMElement();
  });
});
