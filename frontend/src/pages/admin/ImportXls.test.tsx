import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ImportXls from './ImportXls';

// Spec 2026-10-08, 7.4: die Vorschau zeigt das Netto des Servers (nach nicht
// angerechneter Lücke und Auto-Pause) statt es im Browser nachzurechnen.
// P19: „nicht angerechnet" ist Lücke + Hülle (not_credited_minutes vom Server),
// nie uncredited_minutes allein.

const getMock = vi.fn();
const postMock = vi.fn();
vi.mock('../../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
  },
}));
const toastError = vi.hoisted(() => vi.fn());
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ error: toastError, success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  toastError.mockReset();
});

async function analyze(entry: Record<string, unknown>, summary: Record<string, unknown> = {}) {
  getMock.mockResolvedValue({
    data: [{ id: 'u1', first_name: 'Jane', last_name: 'Doe', username: 'jd', is_active: true }],
  });
  postMock.mockResolvedValue({
    data: {
      total: 1, conflicts: 0, arbzg_warnings: 0,
      ...summary,
      entries: [{
        date: '2026-06-01', break_minutes: 0, note: null, has_conflict: false,
        arbzg_warnings: [], raw_start_time: null, raw_end_time: null,
        ...entry,
      }],
    },
  });
  const { container } = render(<ImportXls />);
  const select = screen.getByRole('combobox');
  fireEvent.focus(select);
  await screen.findByRole('option', { name: 'Jane Doe (jd)' });
  fireEvent.change(select, { target: { value: 'u1' } });
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(['x'], 'zeit.xls')] } });
  fireEvent.click(screen.getByRole('button', { name: 'Datei analysieren →' }));
}

describe('<ImportXls /> Vorschau-Netto (Spec 7.4)', () => {
  it('zeigt net_hours vom Server und die nicht angerechnete Lücke', async () => {
    await analyze({
      start_time: '08:00:00', end_time: '18:00:00',
      uncredited_minutes: 150, not_credited_minutes: 150, net_hours: 7.5,
    });
    expect(await screen.findByText('7:30')).toBeInTheDocument();
    expect(screen.getByText('2:30 h nicht angerechnet')).toBeInTheDocument();
  });

  it('weist auch die von der Hülle gekappte Anwesenheit aus (P19)', async () => {
    // Altfenster 08:00–17:00, gestempelt 07:00–17:00: angerechnet ab 07:45,
    // keine Lücke — 0:45 h nicht angerechnet, obwohl uncredited_minutes 0 ist.
    await analyze({
      start_time: '07:45:00', end_time: '17:00:00', raw_start_time: '07:00:00', break_minutes: 45,
      uncredited_minutes: 0, not_credited_minutes: 45, net_hours: 8.5,
    });
    expect(await screen.findByText('8:30')).toBeInTheDocument();
    expect(screen.getByText('0:45 h nicht angerechnet')).toBeInTheDocument();
  });

  it('zeigt ohne Kappung keine Zeile „nicht angerechnet"', async () => {
    await analyze({
      start_time: '08:00:00', end_time: '16:30:00', break_minutes: 30,
      uncredited_minutes: 0, not_credited_minutes: 0, net_hours: 8,
    });
    expect(await screen.findByText('8:00')).toBeInTheDocument();
    expect(screen.queryByText(/nicht angerechnet/)).not.toBeInTheDocument();
  });
});

// Review Task 12: eine Konfliktzeile (Überschreib-Import) darf ihre Hinweise nicht
// verstecken — der Hinweis aus P3 („Eintrag ist anerkannt …") entsteht NUR auf
// Konfliktzeilen, und die Zusammenfassung „N Hinweise" zählt sie mit.
describe('<ImportXls /> Hinweise auf Konfliktzeilen (Spec P3, 8.3)', () => {
  const P3 = 'Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet.';
  const PRESENCE = '§3 ArbZG: Laut Stempel 12:00 h anwesend – mehr als 10 Stunden.';

  it('zeigt neben „Konflikt" die Hinweise der Zeile', async () => {
    await analyze(
      {
        start_time: '06:00:00', end_time: '18:00:00', has_conflict: true,
        arbzg_warnings: [PRESENCE, P3], net_hours: 9,
      },
      { conflicts: 1, arbzg_warnings: 2 },
    );
    expect(await screen.findByText('Konflikt')).toBeInTheDocument();
    const hint = screen.getByTitle(/Laut Stempel 12:00 h anwesend/);
    expect(hint).toHaveTextContent('Hinweis');
    expect(hint).toHaveAttribute('title', `${PRESENCE}\n${P3}`);
  });

  it('zeigt auf einer Konfliktzeile ohne Hinweise kein Hinweis-Kennzeichen', async () => {
    await analyze(
      { start_time: '08:00:00', end_time: '16:30:00', has_conflict: true, net_hours: 8 },
      { conflicts: 1 },
    );
    expect(await screen.findByText('Konflikt')).toBeInTheDocument();
    expect(screen.queryByText('Hinweis')).not.toBeInTheDocument();
  });
});

// Gesamtreview 1.20: die Ergebnisliste trägt nicht nur ArbZG-Warnungen, sondern
// auch Kappungs-/Anwesenheits-Hinweise, die angepasste Tagespause und die Gründe
// übersprungener Zeilen (Beschäftigungszeitraum, Ende ≤ Beginn) — wie in der
// Vorschau (#462) heißt sie deshalb neutral „Hinweise".
describe('<ImportXls /> Ergebnis: Hinweise statt „ArbZG-Warnungen"', () => {
  const SKIP = '29.09.2026: übersprungen — Datum liegt nach dem letzten Arbeitstag (25.09.2026).';

  it('nennt die Liste „Hinweis(e)" und verweist für übersprungene Zeilen darauf', async () => {
    await analyze({ start_time: '08:00:00', end_time: '16:30:00', break_minutes: 30, net_hours: 8 });
    postMock.mockResolvedValueOnce({
      data: { imported: 0, overwritten: 0, skipped: 1, warnings: [SKIP] },
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Import bestätigen →' }));
    expect(await screen.findByText('Import abgeschlossen')).toBeInTheDocument();

    expect(screen.getByText(
      '1 Eintrag übersprungen (nicht überschriebene Konflikte; weitere Gründe bei den Hinweisen).',
    )).toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: /1 Hinweis\(e\)/ });
    fireEvent.click(toggle);
    expect(screen.getByText(SKIP)).toBeInTheDocument();
    expect(screen.queryByText(/ArbZG-Warn/)).not.toBeInTheDocument();
    expect(screen.queryByText(/bei den Warnungen/)).not.toBeInTheDocument();
  });
});

// P4.2: Einzahl bei genau einem Eintrag / Konflikt / Hinweis.
describe('<ImportXls /> Zähler in Einzahl (P4.2)', () => {
  it('schreibt „1 Eintrag gefunden", „1 Konflikt", „1 Hinweis", „(1 Eintrag)"', async () => {
    await analyze(
      { start_time: '08:00:00', end_time: '16:30:00', has_conflict: true, net_hours: 8 },
      { total: 1, conflicts: 1, arbzg_warnings: 1 },
    );
    expect(await screen.findByText(/Eintrag gefunden/)).toBeInTheDocument();
    expect(screen.getByText(/1 Konflikt$/)).toBeInTheDocument();
    expect(screen.getByText(/1 Hinweis$/)).toBeInTheDocument();
    expect(screen.getByText('Konflikte überschreiben (1 Eintrag)')).toBeInTheDocument();
  });
});

// Code-Review 2026-11-11: ops-04 (Überspringen sichtbar), ops-05 (422-Array), ops-18 (Tastatur, Labels, Laden beim Öffnen).
describe('<ImportXls /> Überspringen, Fehlertexte, Tastatur (Review 2026-11-11)', () => {
  it('ops-04: übersprungene Zeile mit rotem Kennzeichen, sichtbarem Grund und Zusammenfassung', async () => {
    await analyze(
      {
        start_time: '08:00:00', end_time: '16:30:00', net_hours: 0,
        arbzg_warnings: ['Wird übersprungen — Datum liegt nach dem letzten Arbeitstag (25.09.2026).'],
        skip_reason: 'Datum liegt nach dem letzten Arbeitstag (25.09.2026).',
      },
      { total: 1, arbzg_warnings: 1, will_skip: 1 },
    );
    expect(await screen.findByText('Wird übersprungen')).toBeInTheDocument();
    expect(screen.getByTestId('import-skip-reason')).toHaveTextContent('Datum liegt nach dem letzten Arbeitstag');
    expect(screen.getByTestId('import-skip-summary')).toHaveTextContent('0 Einträge werden importiert, 1 übersprungen');
    expect(screen.queryByText(/^1 Hinweis$/)).not.toBeInTheDocument();
  });

  it('ops-05: 422-detail als Array wird als Text gemeldet, nicht als Objekt gerendert', async () => {
    await analyze({ start_time: '08:00:00', end_time: '16:30:00', net_hours: 8 });
    postMock.mockRejectedValueOnce({
      response: { status: 422, data: { detail: [{ msg: 'Zeit ungültig', loc: ['body', 'entries', 0] }] } },
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Import bestätigen →' }));
    await vi.waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError).toHaveBeenCalledWith('Zeit ungültig');
  });

  it('ops-18: Benutzer werden beim Öffnen geladen, Labels sind verknüpft, Dropzone per Tastatur bedienbar', async () => {
    getMock.mockResolvedValue({
      data: [{ id: 'u1', first_name: 'Jane', last_name: 'Doe', username: 'jd', is_active: true }],
    });
    const { container } = render(<ImportXls />);
    expect(await screen.findByRole('option', { name: 'Jane Doe (jd)' })).toBeInTheDocument();
    expect(screen.getByLabelText(/Benutzer/)).toBeInTheDocument();
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const clickSpy = vi.spyOn(input, 'click');
    const zone = screen.getByRole('button', { name: 'XLS-Datei auswählen' });
    fireEvent.keyDown(zone, { key: 'Enter' });
    fireEvent.keyDown(zone, { key: ' ' });
    expect(clickSpy).toHaveBeenCalledTimes(2);
  });
});
