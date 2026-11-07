import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AuditIntegrityCard, { integritySummary, type IntegrityResult } from './AuditIntegrityCard';

const getMock = vi.fn();
const postMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));
const toast = { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock('../contexts/ToastContext', () => ({ useToast: () => toast }));

const ok: IntegrityResult = {
  checked: 12, tampered: 0, missing_links: 0, broken_links: 0, head_ok: true,
  legacy_unhashed: 0, legacy_entry_deleted: 0, intact: true,
};

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  toast.error.mockReset();
});

describe('integritySummary (#537)', () => {
  it('meldet ein intaktes Protokoll', () => {
    expect(integritySummary(ok)).toBe('In Ordnung: 12 Zeilen geprüft, keine Veränderung.');
  });

  it('zählt Altbestand getrennt, ohne Alarm', () => {
    expect(integritySummary({ ...ok, legacy_unhashed: 2, legacy_entry_deleted: 1 }))
      .toContain('3 ältere Zeilen (Altbestand)');
  });

  it('nennt jede Art der Abweichung', () => {
    const text = integritySummary({ ...ok, intact: false, tampered: 1, missing_links: 2, head_ok: false });
    expect(text).toBe('Abweichung gefunden: 1 veränderte Zeile(n), 2 fehlende Zeile(n), Kettenende passt nicht — von 12 geprüften Zeilen.');
  });
});

describe('<AuditIntegrityCard />', () => {
  it('zeigt die letzte Prüfung und prüft auf Knopfdruck', async () => {
    getMock.mockResolvedValue({ data: { last_check: { checked_at: '2026-11-07T02:15:00Z', intact: true, checked: 12, tampered: 0, missing_links: 0 } } });
    postMock.mockResolvedValue({ data: { ...ok, intact: false, tampered: 1 } });
    render(<AuditIntegrityCard />);
    expect(await screen.findByText(/in Ordnung/)).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith('/admin/audit/integrity-status');
    fireEvent.click(screen.getByRole('button', { name: 'Jetzt prüfen' }));
    expect(await screen.findByText(/Abweichung gefunden: 1 veränderte Zeile/)).toBeInTheDocument();
    expect(postMock).toHaveBeenCalledWith('/admin/audit/verify-integrity');
    expect(screen.getByText(/Datensicherung aufbewahren/)).toBeInTheDocument();
  });

  it('ohne bisherige Prüfung', async () => {
    getMock.mockResolvedValue({ data: { last_check: null } });
    render(<AuditIntegrityCard />);
    expect(await screen.findByText('Noch keine Prüfung gelaufen.')).toBeInTheDocument();
  });
});
