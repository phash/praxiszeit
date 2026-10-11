import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import ScheduleChangeNotices from './ScheduleChangeNotices';

const RESET = 'Die Arbeitszeit-Änderung ab 01.09.2026 wurde ab 09.10.2026 auf den vorherigen Stand zurückgesetzt (neu: 25,0 h/Woche).';
const CHANGE = 'Ihre Arbeitszeit wurde ab 01.09.2026 geändert (neu: Mo 08:00–12:00). 3 Einträge neu berechnet, angerechnete Zeit −2:15 h. Überstundenkonto im Zeitraum −3:45 h. Rückwirkende Verkürzung – Grund: Arbeitszeit war falsch hinterlegt (Fehlerkorrektur).';
const FUTURE = 'Ihre Arbeitszeit ändert sich ab 02.11.2026 (neu: 25,0 h/Woche).';
const DELETE = 'Die Arbeitszeit-Änderung ab 01.09.2026 wurde zurückgenommen. 1 Eintrag neu berechnet, angerechnete Zeit +0:15 h. Überstundenkonto im Zeitraum +0:15 h.';

function renderNotices(notices: unknown) {
  return render(<MemoryRouter><ScheduleChangeNotices notices={notices as never} /></MemoryRouter>);
}

describe('ScheduleChangeNotices (Spec 14, P20)', () => {
  it('zeigt jeden Hinweis und den Link aufs Profil', () => {
    renderNotices([
      { created_at: '2026-10-09T08:00:00Z', effective_from: '2026-10-09', kind: 'reset', text: RESET },
      { created_at: '2026-10-08T08:00:00Z', effective_from: '2026-09-01', kind: 'change', text: CHANGE },
    ]);
    expect(screen.getByRole('heading', { name: 'Hinweis zu Ihrer Arbeitszeit' })).toBeInTheDocument();
    expect(screen.getByText(RESET)).toBeInTheDocument();
    expect(screen.getByText(CHANGE)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Arbeitszeit im Profil ansehen/ })).toHaveAttribute('href', '/profile');
  });

  it('zeigt alle Arten in der Server-Reihenfolge (jüngste zuerst), ohne umzusortieren oder zu filtern (17.7)', () => {
    // Bewusst so gewählt, dass weder eine Sortierung nach kind noch nach
    // effective_from noch nach created_at aufsteigend dieselbe Folge ergäbe.
    renderNotices([
      { created_at: '2026-10-10T09:00:00Z', effective_from: '2026-09-01', kind: 'delete', text: DELETE },
      { created_at: '2026-10-09T08:00:00Z', effective_from: '2026-10-09', kind: 'reset', text: RESET },
      { created_at: '2026-10-08T10:00:00Z', effective_from: '2026-11-02', kind: 'change', text: FUTURE },
      { created_at: '2026-10-08T08:00:00Z', effective_from: '2026-09-01', kind: 'change', text: CHANGE },
    ]);
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual([DELETE, RESET, FUTURE, CHANGE]);
  });

  it('rendert nichts ohne Hinweise', () => {
    const { container } = renderNotices([]);
    expect(container).toBeEmptyDOMElement();
    expect(renderNotices(undefined).container).toBeEmptyDOMElement();
  });
});
