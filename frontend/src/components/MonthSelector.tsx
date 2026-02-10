import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react';
import { format, addMonths, subMonths, parseISO, startOfMonth } from 'date-fns';
import { de } from 'date-fns/locale';

interface MonthSelectorProps {
  value: string; // Format: "YYYY-MM"
  onChange: (value: string) => void;
  className?: string;
}

export default function MonthSelector({ value, onChange, className = '' }: MonthSelectorProps) {
  const currentDate = parseISO(value + '-01');
  const today = startOfMonth(new Date());
  const isCurrentMonth = format(currentDate, 'yyyy-MM') === format(today, 'yyyy-MM');

  const handlePrevious = () => {
    const prev = subMonths(currentDate, 1);
    onChange(format(prev, 'yyyy-MM'));
  };

  const handleNext = () => {
    const next = addMonths(currentDate, 1);
    onChange(format(next, 'yyyy-MM'));
  };

  const handleToday = () => {
    onChange(format(today, 'yyyy-MM'));
  };

  return (
    <div className={`flex items-center space-x-2 ${className}`}>
      {/* Previous Month Button */}
      <button
        onClick={handlePrevious}
        className="p-2 rounded-lg hover:bg-gray-100 transition"
        aria-label="Vorheriger Monat"
        title="Vorheriger Monat"
      >
        <ChevronLeft size={20} />
      </button>

      {/* Current Month/Year Display */}
      <div className="flex items-center space-x-2 px-4 py-2 bg-gray-50 rounded-lg min-w-[180px] justify-center">
        <Calendar size={18} className="text-gray-500" />
        <span className="font-medium text-gray-900">
          {format(currentDate, 'MMMM yyyy', { locale: de })}
        </span>
      </div>

      {/* Next Month Button */}
      <button
        onClick={handleNext}
        className="p-2 rounded-lg hover:bg-gray-100 transition"
        aria-label="Nächster Monat"
        title="Nächster Monat"
      >
        <ChevronRight size={20} />
      </button>

      {/* Today Button (only show if not current month) */}
      {!isCurrentMonth && (
        <button
          onClick={handleToday}
          className="px-3 py-2 text-sm font-medium text-primary hover:bg-blue-50 rounded-lg transition"
          title="Zum aktuellen Monat springen"
        >
          Heute
        </button>
      )}
    </div>
  );
}
