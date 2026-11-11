import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

/**
 * Handbuch-Fund P5.4: „Sicherung läuft um HH:30“ stand ohne Einschränkung auf der
 * Seite, gilt aber nur für Docker; nativ sichert der Zeitplan des Betriebssystems
 * (docs/BACKUP.md). Das Frontend kennt den Betriebsweg nicht (kein Feld in
 * /api/system/info, Leak-Guard test_deployment_mode) — der Text nennt daher beide.
 */
vi.mock('../../api/client', () => ({
  default: {
    get: vi.fn(async () => ({
      data: { backups: [], config: { enabled: false, hour: 2, retention_days: 30, location: '' } },
    })),
  },
}));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

import Backups from './Backups';

describe('Backups: Hinweis zur geplanten Sicherung', () => {
  it('nennt Docker (HH:30) und native Installationen (OS-Zeitplan 02:00/03:00)', async () => {
    render(<Backups />);
    const hint = await screen.findByTestId('backup-schedule-hint');
    expect(hint.textContent).toMatch(/Docker/);
    expect(hint.textContent).toMatch(/native/i);
    expect(hint.textContent).toMatch(/02:00/);
    expect(hint.textContent).toMatch(/03:00/);
    expect(screen.getByText(/Nur Docker: lokale Zeit.*HH:30/)).toBeInTheDocument();
  });
});
