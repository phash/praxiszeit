import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/shiftPlanning', async () => {
  const actual = await vi.importActual<typeof import('../api/shiftPlanning')>('../api/shiftPlanning');
  return { ...actual, listPlans: vi.fn(), getPlan: vi.fn(), downloadPlanPdf: vi.fn() };
});
// N-2: `toastError` bleibt über den Modul-Mock hinweg dieselbe Spy-Instanz
// (via `vi.hoisted`, damit sie im gehoisteten `vi.mock`-Factory verfügbar
// ist) — so kann ein Test direkt prüfen, ob ein Fehler gemeldet wurde, ohne
// den Toast-Mock pro Test neu zu verdrahten.
const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: toastError, warning: vi.fn(), info: vi.fn() }),
}));
vi.mock('../stores/systemStore', () => ({
  useSystemStore: (sel: (s: unknown) => unknown) =>
    sel({ getShiftPlanningWeekdays: () => [0, 1, 2, 3, 4] }),
}));

import * as api from '../api/shiftPlanning';
import ShiftPlanning from './ShiftPlanning';

const summary = (over: Record<string, unknown> = {}) => ({
  id: 'p1', name: 'Aktueller Plan', description: null, is_active: true,
  active_from_date: null, active_until_date: null, active_today: true,
  visible_to_employees: false, slot_count: 1, is_valid: true, ...over,
});

const detail = (over: Record<string, unknown> = {}) => ({
  ...summary(), slots: [],
  validation: { is_valid: true, understaffed_slot_ids: [] }, ...over,
});

describe('Mitarbeiteransicht Schichtplan', () => {
  beforeEach(() => vi.clearAllMocks());

  it('zeigt einen freigegebenen Zukunftsplan, der heute NICHT gilt', async () => {
    const future = summary({
      id: 'p2', name: 'Ab September', is_active: false, active_today: false,
      visible_to_employees: true, active_from_date: '2026-09-01',
    });
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([future]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockResolvedValue(detail(future));

    render(<ShiftPlanning />);

    await waitFor(() => expect(api.getPlan).toHaveBeenCalledWith('p2'));
    expect(screen.getByText('Ab September')).toBeInTheDocument();
  });

  it('bietet eine Auswahl, sobald mehr als ein Plan sichtbar ist', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([
      summary(),
      summary({ id: 'p2', name: 'Ab September', is_active: false, active_today: false, visible_to_employees: true }),
    ]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockResolvedValue(detail());

    render(<ShiftPlanning />);

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());
    expect(screen.getByRole('option', { name: /Ab September/ })).toBeInTheDocument();
  });

  it('wählt den heute geltenden Plan vor', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([
      summary({ id: 'p2', name: 'Ab September', is_active: false, active_today: false, visible_to_employees: true }),
      summary({ id: 'p1', name: 'Aktueller Plan', active_today: true }),
    ]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockResolvedValue(detail());

    render(<ShiftPlanning />);
    await waitFor(() => expect(api.getPlan).toHaveBeenCalledWith('p1'));
  });

  // #443 F-2 (Prüfrunde 2): früher belegte dieser Test, dass NUR der
  // vorausgewählte Plan geladen wird ("nicht alle") — genau das war der Bug:
  // gelten mehrere Pläne gleichzeitig, sah die Belegschaft nur den
  // (alphabetisch) ersten. Umgestellt auf die neue Regel: alle heute
  // geltenden Pläne laden ja, ein zusätzlich freigegebener Vorschau-Plan
  // bleibt bis zur Auswahl ungeladen.
  it('lädt ALLE heute geltenden Pläne — ein Vorschau-Plan bleibt bis zur Auswahl ungeladen', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([
      summary({ id: 'p1', name: 'Erster', active_today: true }),
      summary({ id: 'p2', name: 'Zweiter', active_today: true }),
      summary({ id: 'p3', name: 'Vorschau-Plan', active_today: false, visible_to_employees: true }),
    ]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockResolvedValue(detail());

    render(<ShiftPlanning />);

    await waitFor(() => {
      expect(api.getPlan).toHaveBeenCalledWith('p1');
      expect(api.getPlan).toHaveBeenCalledWith('p2');
    });
    expect(
      (api.getPlan as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]),
    ).not.toContain('p3');
    // Der Vorschau-Plan bleibt wählbar, ohne dass sein Detail schon geladen wäre.
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  // #443 F-2 Schadensfall: eine Mitarbeiterin mit Einträgen in zwei parallel
  // gültigen Plänen (z. B. je ein Plan pro Standort) muss BEIDE sehen — vorher
  // zeigte die Vorbelegung nur den alphabetisch ersten ("Plan Filiale" vor
  // "Plan Hauptstelle"), der Montags-Eintrag im anderen Plan blieb unsichtbar.
  it('Schadensfall: zwei heute geltende Pläne (zwei Standorte) sind BEIDE sichtbar', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([
      summary({ id: 'p1', name: 'Plan Hauptstelle', active_today: true }),
      summary({ id: 'p2', name: 'Plan Filiale', active_today: true }),
    ]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockImplementation((id: string) =>
      Promise.resolve(detail({ id, name: id === 'p1' ? 'Plan Hauptstelle' : 'Plan Filiale' })),
    );

    render(<ShiftPlanning />);

    await waitFor(() => expect(screen.getByText('Plan Hauptstelle')).toBeInTheDocument());
    expect(screen.getByText('Plan Filiale')).toBeInTheDocument();
    expect((api.getPlan as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(2);
  });

  // N-2 (Prüfrunde 2 der Nachprüfung): vorher liess `Promise.all` EINEN
  // fehlgeschlagenen Detail-Abruf die gesamte Zuweisung scheitern — dann
  // blieben ALLE heute geltenden Pläne als nackte Überschrift ohne Inhalt
  // stehen. `Promise.allSettled` lässt jeden Plan für sich fehlschlagen: der
  // gescheiterte Plan verschwindet ganz, der erfolgreiche bleibt vollständig
  // (Überschrift + PDF-Knopf + Wochenraster) sichtbar.
  it('ein fehlgeschlagener Plan-Abruf lässt die übrigen weiterhin vollständig sichtbar', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([
      summary({ id: 'p1', name: 'Erster', active_today: true }),
      summary({ id: 'p2', name: 'Zweiter', active_today: true }),
    ]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockImplementation((id: string) =>
      id === 'p2'
        ? Promise.reject(new Error('Plan wurde gelöscht'))
        : Promise.resolve(detail({ id, name: 'Erster' })),
    );

    render(<ShiftPlanning />);

    // Erst auf den Toast warten: der markiert zuverlässig, dass BEIDE Abrufe
    // (der erfolgreiche und der gescheiterte) settled sind — vorher stehen
    // während des Ladens beide Überschriften (samt Spinner) noch nebeneinander,
    // ein verfrühter Check auf "Erster" träfe also auch im Fehlerfall zu.
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(screen.getByText('Erster')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'PDF' })).toBeInTheDocument();
    expect(screen.queryByText('Zweiter')).not.toBeInTheDocument();
  });

  it('zeigt den leeren Zustand, wenn nichts sichtbar ist', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    render(<ShiftPlanning />);
    await waitFor(() => expect(screen.getByText(/Kein Schichtplan/i)).toBeInTheDocument());
    expect(api.getPlan).not.toHaveBeenCalled();
  });
});
