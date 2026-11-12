import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

const h = vi.hoisted(() => ({
  getQualifications: vi.fn(),
  generatePlan: vi.fn(),
  updateLocation: vi.fn(),
  deleteWorkstation: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));
vi.mock('../../api/shiftPlanning', async (importActual) => {
  const actual = await importActual<typeof import('../../api/shiftPlanning')>();
  return {
    ...actual,
    getQualifications: h.getQualifications,
    generatePlan: h.generatePlan,
    updateLocation: h.updateLocation,
    deleteWorkstation: h.deleteWorkstation,
  };
});
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => h.toast }));

import SlotDialog from './SlotDialog';
import GenerateDialog from './GenerateDialog';
import LocationManager from './LocationManager';
import WorkstationManager from './WorkstationManager';
import YearTimeline from './YearTimeline';

const ws = { id: 'w1', name: 'Tresen', location_id: null, location_name: null, color: null, sort_order: 0 };
const slotProps = {
  isOpen: true,
  mode: 'create' as const,
  workstations: [ws],
  employees: [{ id: 'u1', first_name: 'Anna', last_name: 'A' }],
  initial: { workstation_id: 'w1', weekday: 0, start_time: '08:00', end_time: '12:00', min_staff: 1, userIds: [], note: '' },
  onSubmit: vi.fn(),
  onClose: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  h.getQualifications.mockReset();
  h.generatePlan.mockReset();
});

describe('ui-05 SlotDialog: Einweisungen unbekannt ≠ nicht eingewiesen', () => {
  it('zeigt vor der Antwort und bei Ladefehler kein „nicht eingewiesen“ (bei Fehler Hinweis)', async () => {
    h.getQualifications.mockReturnValue(new Promise(() => {}));
    const { unmount } = render(<SlotDialog {...slotProps} />);
    expect(screen.queryByText('nicht eingewiesen')).toBeNull();
    unmount();

    h.getQualifications.mockRejectedValue(new Error('net'));
    render(<SlotDialog {...slotProps} />);
    await screen.findByText(/Einweisungen konnten nicht geladen werden/);
    expect(screen.queryByText('nicht eingewiesen')).toBeNull();
  });

  it('zeigt das Badge, sobald die Matrix geladen ist und die Person fehlt', async () => {
    h.getQualifications.mockResolvedValue({ users: [], workstations: [], qualifications: [] });
    render(<SlotDialog {...slotProps} />);
    await screen.findByText('nicht eingewiesen');
  });
});

describe('ui-03 GenerateDialog: überschreibender Modus', () => {
  it('Standard ist „Nur Lücken auffüllen“ und der Text nennt das Löschen', () => {
    render(<GenerateDialog planId="p1" assignmentCount={4} onGenerated={() => {}} onClose={() => {}} />);
    expect(screen.getByLabelText(/Nur Lücken auffüllen/)).toBeChecked();
    expect(screen.getByText(/bestehende Zuweisungen gelöscht/)).toBeInTheDocument();
  });

  it('„Neu verteilen“ verlangt eine Bestätigung mit der Zahl der Zuweisungen', async () => {
    h.generatePlan.mockResolvedValue({ generation: { assigned: 3, unfilled_slot_ids: [] } });
    render(<GenerateDialog planId="p1" assignmentCount={4} onGenerated={() => {}} onClose={() => {}} />);
    fireEvent.click(screen.getByLabelText(/Alle Zuweisungen neu verteilen/));
    fireEvent.click(screen.getByRole('button', { name: 'Generieren' }));
    expect(h.generatePlan).not.toHaveBeenCalled();
    await screen.findByText(/Die 4 vorhandenen Zuweisungen/);
    fireEvent.click(screen.getByRole('button', { name: 'Neu verteilen' }));
    await waitFor(() => expect(h.generatePlan).toHaveBeenCalledWith('p1', expect.objectContaining({ mode: 'replace' })));
  });

  it('„Lücken auffüllen“ läuft ohne Rückfrage', async () => {
    h.generatePlan.mockResolvedValue({ generation: { assigned: 1, unfilled_slot_ids: [] } });
    render(<GenerateDialog planId="p1" assignmentCount={4} onGenerated={() => {}} onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Generieren' }));
    await waitFor(() => expect(h.generatePlan).toHaveBeenCalledWith('p1', expect.objectContaining({ mode: 'fill_gaps' })));
  });
});

describe('ui-14 Standort umbenennen per Tastatur', () => {
  const locs = [{ id: 'l1', name: 'Praxis Nord', sort_order: 3 }];
  it('Enter speichert, Escape bricht ab', async () => {
    h.updateLocation.mockResolvedValue({});
    render(<LocationManager locations={locs as never} onChanged={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Bearbeiten' }));
    const input = screen.getByLabelText('Name des Standorts');
    fireEvent.change(input, { target: { value: 'Praxis Süd' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(h.updateLocation).toHaveBeenCalledWith('l1', 'Praxis Süd', 3));

    fireEvent.click(screen.getByRole('button', { name: 'Bearbeiten' }));
    fireEvent.keyDown(screen.getByLabelText('Name des Standorts'), { key: 'Escape' });
    expect(screen.queryByLabelText('Name des Standorts')).toBeNull();
  });
});

describe('ui-14 Arbeitsplatz löschen, der gerade bearbeitet wird', () => {
  it('setzt das Formular zurück (kein „Speichern“ auf gelöschter ID)', async () => {
    h.deleteWorkstation.mockResolvedValue({});
    render(<WorkstationManager workstations={[ws as never]} locations={[]} onChanged={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Bearbeiten/ }));
    expect(screen.getByRole('button', { name: 'Speichern' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Löschen/ }));
    const confirmBtns = screen.getAllByRole('button', { name: 'Löschen' });
    fireEvent.click(confirmBtns[0]);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Hinzufügen' })).toBeInTheDocument());
  });
});

describe('ui-10/ui-23 YearTimeline', () => {
  const year = new Date().getFullYear();
  const mk = (over: Record<string, unknown>) => ({
    id: 'p1', name: 'Sommer', description: null, is_active: false, active_from_date: null,
    active_until_date: null, active_today: false, visible_to_employees: false, slot_count: 0, is_valid: true, ...over,
  });
  it('aria-expanded am Schalter, Daten als TT.MM.JJJJ im sichtbaren Text, Sie-Form', () => {
    render(<YearTimeline plans={[mk({ active_from_date: `${year}-06-01`, active_until_date: `${year}-08-31` }) as never]} />);
    const toggle = screen.getByRole('button', { name: /Jahresübersicht/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(`01.06.${year} – 31.08.${year}`)).toBeInTheDocument();
  });
  it('manuell aktiv mit Fenster gilt als dauerhaft aktiv', () => {
    render(<YearTimeline plans={[mk({ is_active: true, active_from_date: `${year}-06-01`, active_until_date: `${year}-08-31` }) as never]} />);
    fireEvent.click(screen.getByRole('button', { name: /Jahresübersicht/ }));
    expect(screen.getByText(/dauerhaft aktiv/)).toBeInTheDocument();
  });
  it('Leerhinweis siezt', () => {
    render(<YearTimeline plans={[]} />);
    fireEvent.click(screen.getByRole('button', { name: /Jahresübersicht/ }));
    expect(screen.getByText(/Legen Sie im Plan/)).toBeInTheDocument();
  });
});
