import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react';
import { format, addWeeks, subWeeks, parseISO, startOfWeek, endOfWeek, getISOWeek } from 'date-fns';
import { de } from 'date-fns/locale';

interface WeekSelectorProps {
  value: string; // Monday of the week, format "YYYY-MM-DD"
  onChange: (mondayIso: string) => void;
  className?: string;
}

/** Returns the Monday (YYYY-MM-DD) of the ISO week containing `d` (default: today). */
export function isoWeekMonday(d: Date = new Date()): string {
  return format(startOfWeek(d, { weekStartsOn: 1 }), 'yyyy-MM-dd');
}

/** Human label like "22.–28.06.2026 (KW 26)" (drops the redundant first month within one month). */
export function weekLabel(mondayIso: string): string {
  const monday = parseISO(mondayIso);
  const sunday = endOfWeek(monday, { weekStartsOn: 1 });
  const kw = getISOWeek(monday);
  const sameMonth = format(monday, 'MM.yyyy') === format(sunday, 'MM.yyyy');
  const startStr = sameMonth
    ? format(monday, 'dd.', { locale: de })
    : format(monday, 'dd.MM.yyyy', { locale: de });
  const endStr = format(sunday, 'dd.MM.yyyy', { locale: de });
  return `${startStr}–${endStr} (KW ${kw})`;
}

export default function WeekSelector({ value, onChange, className = '' }: WeekSelectorProps) {
  const monday = parseISO(value);
  const thisMonday = startOfWeek(new Date(), { weekStartsOn: 1 });
  const isCurrentWeek = format(monday, 'yyyy-MM-dd') === format(thisMonday, 'yyyy-MM-dd');

  const handlePrevious = () => onChange(format(subWeeks(monday, 1), 'yyyy-MM-dd'));
  const handleNext = () => onChange(format(addWeeks(monday, 1), 'yyyy-MM-dd'));
  const handleToday = () => onChange(format(thisMonday, 'yyyy-MM-dd'));

  return (
    <div className={`flex items-center space-x-2 ${className}`}>
      {/* Previous Week Button */}
      <button
        onClick={handlePrevious}
        className="p-2.5 rounded-xl hover:bg-muted transition"
        aria-label="Vorherige Woche"
        title="Vorherige Woche"
      >
        <ChevronLeft size={20} />
      </button>

      {/* Current Week Display */}
      <div className="flex items-center space-x-2 px-4 py-2 bg-muted rounded-xl min-w-[220px] justify-center">
        <Calendar size={18} className="text-text-secondary" />
        <span className="font-semibold text-text-primary">{weekLabel(value)}</span>
      </div>

      {/* Next Week Button */}
      <button
        onClick={handleNext}
        className="p-2.5 rounded-xl hover:bg-muted transition"
        aria-label="Nächste Woche"
        title="Nächste Woche"
      >
        <ChevronRight size={20} />
      </button>

      {/* Today Button (only show if not current week) */}
      {!isCurrentWeek && (
        <button
          onClick={handleToday}
          className="px-3 py-2 text-sm font-medium text-primary hover:bg-primary-light rounded-xl transition"
          title="Zur aktuellen Woche springen"
        >
          Heute
        </button>
      )}
    </div>
  );
}
