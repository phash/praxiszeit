import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ToastProvider } from '../contexts/ToastContext';
import AbsenceReasonsManager from './AbsenceReasonsManager';
import * as api from '../api/absenceReasons';

// #376: keine Netz-Calls im Test — listReasons liefert leer, so dass alle
// Presets als "noch nicht aktiviert" gerendert werden.
beforeEach(() => {
  vi.spyOn(api, 'listReasons').mockResolvedValue([]);
});

describe('AbsenceReasonsManager (#376 presets)', () => {
  it('offers the Kind-krank preset button', async () => {
    render(
      <ToastProvider>
        <AbsenceReasonsManager />
      </ToastProvider>,
    );
    expect(await screen.findByText('+ Kind krank')).toBeInTheDocument();
  });
});

describe('AbsenceReasonsManager Eingabefelder (P4.1)', () => {
  it('zeigt Rahmen an Bezeichnung und Verhalten (border + border-gray-300)', async () => {
    render(
      <ToastProvider>
        <AbsenceReasonsManager />
      </ToastProvider>,
    );
    const name = await screen.findByPlaceholderText('z. B. Schule');
    const behavior = screen.getByRole('combobox');
    for (const el of [name, behavior]) {
      expect(el.classList.contains('border')).toBe(true);
      expect(el.classList.contains('border-gray-300')).toBe(true);
    }
  });
});
