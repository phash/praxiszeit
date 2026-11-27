import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import VacationPlanningCard from './VacationPlanningCard';

const getMock = vi.fn();
vi.mock('../api/client', () => ({
  default: { get: (...a: unknown[]) => getMock(...a) },
}));

const nextYear = new Date().getFullYear() + 1;
const account = {
  year: nextYear,
  budget_days: 30,
  used_days: 3,
  remaining_days: 27,
  entitlement_days: 30,
  carryover_days: 0,
  closure_days: 2,
  pending_days: 3,
  plannable_days: 24,
};

beforeEach(() => {
  getMock.mockReset();
  getMock.mockResolvedValue({ data: account });
});

describe('VacationPlanningCard (#585)', () => {
  it('lädt das Konto des angezeigten Jahres und zeigt die Planungszahlen', async () => {
    render(<VacationPlanningCard year={nextYear} />);

    expect(await screen.findByTestId('vacation-plannable')).toHaveTextContent('24 Tage');
    expect(getMock).toHaveBeenCalledWith(`/dashboard/vacation?year=${nextYear}`);
    expect(screen.getByText('davon 2 Tage Betriebsferien')).toBeInTheDocument();
    expect(screen.getByText('Beantragt (offen)').nextElementSibling).toHaveTextContent('3 Tage');
    expect(screen.getByText('Rest nach Buchungen').nextElementSibling).toHaveTextContent('27 Tage');
  });

  it('weist für ein künftiges Jahr ohne Übertrag auf den Jahresabschluss hin', async () => {
    render(<VacationPlanningCard year={nextYear} />);

    expect(await screen.findByText(`Resturlaub aus ${nextYear - 1} kommt erst mit dem Jahresabschluss dazu.`))
      .toBeInTheDocument();
  });

  it('zeigt einen vorhandenen Übertrag und keinen Hinweis', async () => {
    getMock.mockResolvedValue({ data: { ...account, budget_days: 34.5, carryover_days: 4.5, plannable_days: 28.5 } });
    render(<VacationPlanningCard year={nextYear} />);

    expect(await screen.findByText('+ 4,5 Tage Übertrag')).toBeInTheDocument();
    expect(screen.queryByText(/kommt erst mit dem Jahresabschluss/)).not.toBeInTheDocument();
  });

  it('markiert eine Überplanung rot', async () => {
    getMock.mockResolvedValue({ data: { ...account, plannable_days: -1.5 } });
    render(<VacationPlanningCard year={nextYear} />);

    const value = await screen.findByTestId('vacation-plannable');
    expect(value).toHaveTextContent('-1,5 Tage');
    expect(value.className).toContain('text-red-600');
  });

  it('lädt bei neuer Abwesenheitsliste neu und blendet sich bei Fehler aus', async () => {
    const { rerender, container } = render(<VacationPlanningCard year={nextYear} absences={[]} />);
    await screen.findByTestId('vacation-plannable');

    getMock.mockRejectedValue(new Error('offline'));
    rerender(<VacationPlanningCard year={nextYear} absences={[]} />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(getMock).toHaveBeenCalledTimes(2);
  });
});
