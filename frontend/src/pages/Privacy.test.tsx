import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import Privacy from './Privacy';

describe('<Privacy /> Arbeitszeit-Blöcke (Spec 14, Art. 13 Abs. 2 lit. f DSGVO)', () => {
  it('nennt die Kategorie und beschreibt die Logik der Nichtanrechnung', () => {
    render(<MemoryRouter><Privacy /></MemoryRouter>);
    expect(screen.getByText('Soll-Arbeitszeiten (Arbeitszeit-Blöcke, Pause) und nicht angerechnete Zeit:')).toBeInTheDocument();
    expect(screen.getByText(new RegExp(
      'Ihre Arbeitszeit wird in Blöcken hinterlegt\\. Gestempelte Zeit vor dem ersten Block, nach dem letzten Block '
      + 'und zwischen den Blöcken wird – abzüglich eines Puffers – automatisch nicht angerechnet; die Stempelzeiten '
      + 'bleiben gespeichert\\. Die Verwaltung kann nicht angerechnete Zeit anerkennen; Sie können die Anrechnung per '
      + 'Änderungsantrag beantragen\\.',
    ))).toBeInTheDocument();
  });
});
