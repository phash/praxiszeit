import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CreditOverrideButton, { AUTO_CLOSED_HINT } from './CreditOverrideButton';

const postMock = vi.fn();
vi.mock('../api/client', () => ({ default: { post: (...a: unknown[]) => postMock(...a) } }));
const toast = { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() };
vi.mock('../contexts/ToastContext', () => ({ useToast: () => toast }));

const K7 = {
  id: 'e1', start_time: '07:45:00', end_time: '18:15:00', raw_start_time: '07:00:00',
  raw_end_time: '19:00:00', uncredited_minutes: 150, not_credited_minutes: 240,
  credit_override: false, auto_closed: false,
};

beforeEach(() => {
  postMock.mockReset();
  Object.values(toast).forEach((f) => f.mockReset());
});

describe('<CreditOverrideButton /> (Spec 13.3)', () => {
  it('bestätigt mit dem Wortlaut aus 13.3, ruft den Endpunkt und zeigt die weichen Warnungen', async () => {
    postMock.mockResolvedValue({ data: { warnings: ['DAILY_HOURS_HARD: Tagesarbeitszeit beträgt 12.0h …'] } });
    const onDone = vi.fn();
    render(<CreditOverrideButton entry={K7} onDone={onDone} />);
    fireEvent.click(screen.getByRole('button', { name: 'Anerkennen' }));
    expect(screen.getByText(/^Die gesamte gestempelte Zeit \(07:00–19:00\) wird angerechnet\./)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Zeit anerkennen' }));
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/admin/time-entries/e1/credit-override'));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith('Zeit anerkannt');
    expect(toast.warning).toHaveBeenCalled();
  });

  it('meldet einen Fehler und lädt nicht neu, wenn der Server ablehnt', async () => {
    postMock.mockRejectedValue({ response: { status: 409, data: { detail: 'Ein anderer Eintrag an diesem Tag beginnt bereits um 18:30.' } } });
    const onDone = vi.fn();
    render(<CreditOverrideButton entry={K7} onDone={onDone} />);
    fireEvent.click(screen.getByRole('button', { name: 'Anerkennen' }));
    fireEvent.click(screen.getByRole('button', { name: 'Zeit anerkennen' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(onDone).not.toHaveBeenCalled();
  });

  // Review Task 15: der Knopf sitzt in Tabellenzellen (Aktionen-Spalte mit
  // text-right/space-x-1, Journal-Zeitspalte mit whitespace-nowrap). Im Zellbaum
  // erbte der Dialog diese Stile — rechtsbündiger Pflichttext aus 13.3, ein
  // 4-px-Streifen ohne Abdunklung, kein Umbruch im Titel.
  it('rendert den Bestätigungsdialog außerhalb der Tabellenzelle (keine Zell-Stile)', () => {
    render(
      <table><tbody><tr>
        <td data-testid="zelle" className="text-right text-sm space-x-1 whitespace-nowrap">
          <CreditOverrideButton entry={K7} onDone={vi.fn()} />
        </td>
      </tr></tbody></table>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Anerkennen' }));
    const dialog = screen.getByRole('alertdialog');
    expect(screen.getByTestId('zelle')).not.toContainElement(dialog);
    expect(dialog.closest('td')).toBeNull();
  });

  it('ist bei automatisch geschlossenen Einträgen deaktiviert und nennt den Grund (P18)', () => {
    render(<CreditOverrideButton entry={{ ...K7, auto_closed: true }} onDone={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Anerkennen' })).toBeDisabled();
    expect(screen.getByText(AUTO_CLOSED_HINT)).toBeInTheDocument();
  });

  it('fehlt ohne nicht angerechnete Zeit, bei anerkannten und bei offenen Einträgen', () => {
    const { container, rerender } = render(
      <CreditOverrideButton entry={{ ...K7, not_credited_minutes: 0, uncredited_minutes: 0, raw_start_time: null, raw_end_time: null }} onDone={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
    rerender(<CreditOverrideButton entry={{ ...K7, credit_override: true }} onDone={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<CreditOverrideButton entry={{ ...K7, end_time: null }} onDone={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
