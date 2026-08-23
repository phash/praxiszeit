import { beforeEach, describe, expect, it, vi } from 'vitest';

// Beide Nachbarmodule ersetzen, NICHT per vi.spyOn auf den Namensraum: ein
// ES-Modul-Export ist nicht schreibbar, und der Import in shiftPlanning.ts ist
// bereits gebunden — ein Spion darauf griffe nie.
vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));
vi.mock('../utils/downloadBlob', () => ({ downloadBlob: vi.fn() }));

import apiClient from './client';
import { downloadBlob } from '../utils/downloadBlob';
import { downloadPlanPdf } from './shiftPlanning';

const getMock = apiClient.get as ReturnType<typeof vi.fn>;
const dlMock = downloadBlob as ReturnType<typeof vi.fn>;

describe('downloadPlanPdf', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fordert den Plan als Blob an und stoesst den Download an', async () => {
    getMock.mockResolvedValue({ data: new Blob(['%PDF-1.4'], { type: 'application/pdf' }) });

    await downloadPlanPdf('plan-1', 'Normalzustand');

    expect(getMock).toHaveBeenCalledWith('/shift-planning/plans/plan-1/export.pdf', {
      responseType: 'blob',
    });
    expect(dlMock).toHaveBeenCalledTimes(1);
    expect(dlMock.mock.calls[0][1]).toContain('Normalzustand');
    expect(dlMock.mock.calls[0][1]).toMatch(/\.pdf$/);
    expect(dlMock.mock.calls[0][2]).toBe('application/pdf');
  });

  it('bereinigt Sonderzeichen im Dateinamen', async () => {
    getMock.mockResolvedValue({ data: new Blob([]) });

    await downloadPlanPdf('plan-2', 'Sommer "2026"/KW30');

    const filename = dlMock.mock.calls[0][1] as string;
    expect(filename).not.toContain('/');
    expect(filename).not.toContain('"');
    expect(filename).toContain('Sommer');
  });

  it('faellt auf einen Ersatznamen zurueck, wenn nichts uebrig bleibt', async () => {
    getMock.mockResolvedValue({ data: new Blob([]) });

    await downloadPlanPdf('plan-3', '///');

    // #443 F-7: Stand-Datum (lokal, YYYY-MM-DD) haengt am Dateinamen, damit
    // zwei Ausdrucke desselben Plans an verschiedenen Tagen nicht kollidieren.
    expect(dlMock.mock.calls[0][1]).toMatch(/^Schichtplan_Schichtplan_\d{4}-\d{2}-\d{2}\.pdf$/);
  });

  it('#443 F-7: haengt das heutige lokale Datum an den Dateinamen an', async () => {
    getMock.mockResolvedValue({ data: new Blob([]) });

    await downloadPlanPdf('plan-4', 'Normalzustand');

    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, '0');
    const todayIso = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    expect(dlMock.mock.calls[0][1]).toBe(`Schichtplan_Normalzustand_${todayIso}.pdf`);
  });
});
