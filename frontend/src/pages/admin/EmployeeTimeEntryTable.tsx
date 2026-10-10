import { format } from 'date-fns';
import { Edit2, Trash2 } from 'lucide-react';
import { RawStampNote } from '../../components/RawStampNote';
import { formatClockTime, formatHoursHM } from '../../utils/formatters';
import { stampNoteProps, type StampEntry } from '../../utils/workBlocks';

/**
 * Detailtabelle der Zeiteinträge im Admin-Dashboard (Spec 2026-10-08, 12.3):
 * Netto-Spalte und die Zeile „nicht angerechnet" (RawStampNote). Aus
 * AdminDashboard.tsx herausgelöst, damit sie für sich testbar ist.
 */
export interface EmployeeTimeEntry extends StampEntry {
  id: string;
  date: string;
  start_time: string;
  end_time: string | null; // #382: null bei offenem Eintrag — Deref nur über formatClockTime
  break_minutes: number;
  net_hours: number;
  note?: string;
}

interface EmployeeTimeEntryTableProps {
  entries: EmployeeTimeEntry[];
  onEdit: (entry: EmployeeTimeEntry) => void;
  onDelete: (entryId: string) => void;
}

export default function EmployeeTimeEntryTable({ entries, onEdit, onDelete }: EmployeeTimeEntryTableProps) {
  return (
    <table className="w-full">
      <thead className="bg-gray-50 sticky top-0">
        <tr>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Datum</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Von</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Bis</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Pause</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Netto</th>
          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Notiz</th>
          <th className="px-4 py-2 text-right text-xs font-medium text-gray-500">Aktionen</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-200">
        {entries.map((entry) => (
          <tr key={entry.id} className="hover:bg-gray-50 align-top">
            <td className="px-4 py-2 text-sm">{format(new Date(entry.date), 'dd.MM.yyyy')}</td>
            <td className="px-4 py-2 text-sm">
              {formatClockTime(entry.start_time)}
              <RawStampNote {...stampNoteProps(entry)} />
            </td>
            <td className="px-4 py-2 text-sm">{formatClockTime(entry.end_time, 'offen')}</td>
            <td className="px-4 py-2 text-sm">{entry.break_minutes} min</td>
            <td className="px-4 py-2 text-sm">{formatHoursHM(entry.net_hours)} h</td>
            <td className="px-4 py-2 text-sm text-gray-500">{entry.note || '-'}</td>
            <td className="px-4 py-2 text-right text-sm space-x-1">
              <button
                onClick={() => onEdit(entry)}
                className="text-primary hover:text-primary-dark p-1 rounded-sm"
                aria-label={`Eintrag vom ${format(new Date(entry.date), 'dd.MM.yyyy')} bearbeiten`}
              >
                <Edit2 size={14} aria-hidden="true" />
              </button>
              <button
                onClick={() => onDelete(entry.id)}
                className="text-red-600 hover:text-red-800 p-1 rounded-sm"
                aria-label={`Eintrag vom ${format(new Date(entry.date), 'dd.MM.yyyy')} löschen`}
              >
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
