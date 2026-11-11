import type { ComponentType } from 'react';
import { DayTimeline } from './DayTimeline';
import { SollIstScale } from './SollIstScale';
import { MonthBalanceBars } from './MonthBalanceBars';
import { VacationPot } from './VacationPot';
import { ClosureSplit } from './ClosureSplit';

/** Diagramme „So rechnet PraxisZeit", adressiert über den Schlüssel `diagram` der Handbuch-Inhalte. */
export const DIAGRAMS: Record<string, ComponentType> = {
  'tag-zeitstrahl': DayTimeline,
  'soll-ist': SollIstScale,
  'saldo-monat': MonthBalanceBars,
  'urlaubskonto': VacationPot,
  'betriebsferien-split': ClosureSplit,
};
