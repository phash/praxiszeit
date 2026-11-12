import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

/**
 * Review 2026-11-11 (ui-01, ui-02, ui-04, ui-10, ui-11, ui-12, ui-22): Verhalten des
 * Plan-Editors bei Teilfehlern, Löschen/Deaktivieren, veralteten Antworten.
 */
const h = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  get: vi.fn(),
  api: {} as Record<string, ReturnType<typeof vi.fn>>,
}));
vi.mock('../../api/client', () => ({ default: { get: h.get } }));
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => h.toast }));
vi.mock('../../api/shiftPlanning', async (importActual) => {
  const actual = await importActual<typeof import('../../api/shiftPlanning')>();
  for (const k of [
    'listLocations', 'listWorkstations', 'listPlans', 'getPlan', 'getQualifications',
    'createSlot', 'updateSlot', 'deleteSlot', 'setAssignments', 'activatePlan', 'deactivatePlan',
  ]) h.api[k] = vi.fn();
  return { ...actual, ...h.api };
});

import AdminShiftPlanning from './ShiftPlanning';

const slot = (over: Record<string, unknown> = {}) => ({
  id: 's1', workstation_id: 'ws1', workstation_name: 'Tresen', color: null, weekday: 0,
  start_time: '08:00', end_time: '12:00', min_staff: 1, note: null, understaffed: false,
  unqualified: [], assignments: [{ user_id: 'u1', first_name: 'Anna', last_name: 'A' }], ...over,
});
const plan = (over: Record<string, unknown> = {}) => ({
  id: 'p1', name: 'Wochenplan', description: null, is_active: true,
  active_from_date: null, active_until_date: null, active_today: true,
  visible_to_employees: false, slots: [slot()],
  validation: { is_valid: true, understaffed_slot_ids: [] }, ...over,
});

beforeEach(() => {
  Object.values(h.toast).forEach((f) => f.mockReset());
  Object.values(h.api).forEach((f) => f.mockReset());
  h.get.mockReset().mockResolvedValue({ data: [
    { id: 'u1', first_name: 'Anna', last_name: 'A', weekly_hours: 20, is_active: true, is_hidden: false },
  ] });
  h.api.listLocations.mockResolvedValue([]);
  h.api.listWorkstations.mockResolvedValue([
    { id: 'ws1', name: 'Tresen', color: '#FF8800', location_id: null, location_name: null },
  ]);
  h.api.listPlans.mockResolvedValue([{ ...plan(), slot_count: 1, is_valid: true }]);
  h.api.getPlan.mockResolvedValue(plan());
  h.api.getQualifications.mockResolvedValue({ users: [], workstations: [], qualifications: [] });
});

async function open() {
  render(<AdminShiftPlanning />);
  await screen.findByRole('heading', { name: 'Wochenplan' });
}

describe('ui-01 Slot speichern ohne halb gespeicherten Zustand', () => {
  it('nach fehlgeschlagener Zuweisung aktualisiert Speichern den Slot statt einen zweiten anzulegen', async () => {
    h.api.createSlot.mockResolvedValue({ id: 'new1' });
    h.api.setAssignments.mockRejectedValueOnce(new Error('409')).mockResolvedValue([]);
    h.api.updateSlot.mockResolvedValue({});
    await open();
    fireEvent.click(screen.getByRole('button', { name: 'Slot', exact: true }));
    const dialog = await screen.findByRole('dialog', { name: 'Neuer Zeitslot' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Speichern' }));
    await waitFor(() => expect(h.toast.error).toHaveBeenCalled());
    expect(String(h.toast.error.mock.calls[0][0])).toContain('Slot wurde angelegt');
    // Dialog bleibt, ist aber im Bearbeiten-Modus
    const edit = await screen.findByRole('dialog', { name: 'Zeitslot bearbeiten' });
    fireEvent.click(within(edit).getByRole('button', { name: 'Speichern' }));
    await waitFor(() => expect(h.toast.success).toHaveBeenCalledWith('Slot gespeichert'));
    expect(h.api.createSlot).toHaveBeenCalledTimes(1);
    expect(h.api.updateSlot).toHaveBeenCalledWith('new1', expect.anything());
  });
});

describe('ui-02 Slot löschen mit Bestätigung', () => {
  it('löscht erst nach Bestätigung und nennt die Zahl der Zuweisungen', async () => {
    h.api.deleteSlot.mockResolvedValue({});
    await open();
    fireEvent.click(screen.getByText('Tresen'));
    const dialog = await screen.findByRole('dialog', { name: 'Zeitslot bearbeiten' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Löschen' }));
    expect(h.api.deleteSlot).not.toHaveBeenCalled();
    expect(await screen.findByText(/1 Zuweisung wird entfernt/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Löschen' })[0]);
    await waitFor(() => expect(h.api.deleteSlot).toHaveBeenCalledWith('s1'));
  });
});

describe('ui-04 veraltete Plan-Antwort', () => {
  it('ein Fehler beim Laden räumt den Editor, statt den alten Plan stehen zu lassen', async () => {
    h.api.listPlans.mockResolvedValue([
      { ...plan(), slot_count: 1, is_valid: true },
      { ...plan({ id: 'p2', name: 'Sommer', is_active: false, active_today: false }), slot_count: 0, is_valid: true },
    ]);
    await open();
    h.api.getPlan.mockRejectedValueOnce(new Error('500'));
    fireEvent.click(screen.getByRole('button', { name: /Sommer/ }));
    await screen.findByText('Kein Plan ausgewählt');
  });

  it('die langsame Antwort des alten Plans überschreibt den neu gewählten nicht', async () => {
    h.api.listPlans.mockResolvedValue([
      { ...plan({ active_today: false, is_active: false }), slot_count: 1, is_valid: true },
      { ...plan({ id: 'p2', name: 'Sommer', is_active: false, active_today: false }), slot_count: 0, is_valid: true },
    ]);
    let resolveA!: (v: unknown) => void;
    h.api.getPlan.mockImplementation((id: string) =>
      id === 'p1' ? new Promise((r) => { resolveA = r; }) : Promise.resolve(plan({ id: 'p2', name: 'Sommer' })),
    );
    render(<AdminShiftPlanning />);
    await screen.findByRole('button', { name: /Wochenplan/ });
    fireEvent.click(screen.getByRole('button', { name: /Wochenplan/ }));
    fireEvent.click(screen.getByRole('button', { name: /Sommer/ }));
    await screen.findByRole('heading', { name: 'Sommer' });
    resolveA(plan());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByRole('heading', { name: 'Sommer' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Wochenplan' })).toBeNull();
  });
});

describe('ui-10/ui-11 Datumsformat und Aktivieren/Deaktivieren', () => {
  it('zeigt das Aktiv-Fenster als TT.MM.JJJJ und bietet „Dauerhaft aktiv schalten“ bei Fenster-Aktivität', async () => {
    h.api.getPlan.mockResolvedValue(
      plan({ is_active: false, active_today: true, active_from_date: '2026-03-01', active_until_date: '2026-05-31' }),
    );
    await open();
    expect(screen.getByText(/ab 01\.03\.2026/)).toBeInTheDocument();
    expect(screen.getByText(/bis 31\.05\.2026/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dauerhaft aktiv schalten' })).toBeInTheDocument();
  });

  it('Deaktivieren eines laufenden Plans fragt nach', async () => {
    h.api.deactivatePlan.mockResolvedValue({});
    await open();
    fireEvent.click(screen.getByRole('button', { name: 'Deaktivieren' }));
    expect(h.api.deactivatePlan).not.toHaveBeenCalled();
    await screen.findByText('Schichtplan deaktivieren');
    // ConfirmDialog steht im DOM vor dem Seitenknopf
    fireEvent.click(screen.getAllByRole('button', { name: 'Deaktivieren' })[0]);
    await waitFor(() => expect(h.api.deactivatePlan).toHaveBeenCalledWith('p1'));
  });
});

describe('ui-12 Tabs mit ARIA', () => {
  it('Reiter tragen role=tab/aria-selected, Woche/Tag aria-pressed, die gewählte Planzeile aria-current', async () => {
    await open();
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.getAttribute('aria-selected'))).toEqual(['true', 'false', 'false']);
    expect(screen.getByRole('button', { name: 'Woche' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Tag' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: /Wochenplan/ })).toHaveAttribute('aria-current', 'true');
    fireEvent.click(screen.getByRole('tab', { name: /Stammdaten/ }));
    expect(screen.getByRole('tab', { name: /Stammdaten/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toBeInTheDocument();
  });
});

describe('ui-22 Ladefehler der Mitarbeiter', () => {
  it('meldet den Fehler statt „Keine Mitarbeiter“', async () => {
    h.get.mockRejectedValue(new Error('boom'));
    await open();
    expect(await screen.findByText(/Mitarbeiter konnten nicht geladen werden/)).toBeInTheDocument();
    expect(screen.queryByText('Keine Mitarbeiter.')).toBeNull();
    expect(h.toast.error).toHaveBeenCalled();
  });
});
