import { useEffect, useState, useCallback } from 'react';
import { LogIn, LogOut } from 'lucide-react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';

interface ClockStatus {
  is_clocked_in: boolean;
  current_entry?: {
    id: string;
    start_time: string;
    note?: string;
  } | null;
  elapsed_minutes?: number | null;
}

export default function StampWidget() {
  const toast = useToast();
  const [status, setStatus] = useState<ClockStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [showBreakInput, setShowBreakInput] = useState(false);
  const [breakMinutes, setBreakMinutes] = useState(0);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiClient.get('/time-entries/clock-status');
      setStatus(res.data);
      setElapsed(res.data.elapsed_minutes ?? 0);
    } catch {
      // Silently fail - widget is non-critical
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Live elapsed timer - update every 60 seconds
  useEffect(() => {
    if (!status?.is_clocked_in) return;
    const interval = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 60_000);
    return () => clearInterval(interval);
  }, [status?.is_clocked_in]);

  const handleClockIn = async () => {
    setActing(true);
    try {
      await apiClient.post('/time-entries/clock-in', {});
      toast.success('Erfolgreich eingestempelt');
      await fetchStatus();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Fehler beim Einstempeln');
    } finally {
      setActing(false);
    }
  };

  const handleClockOut = async () => {
    if (!showBreakInput) {
      setShowBreakInput(true);
      return;
    }
    setActing(true);
    try {
      await apiClient.post('/time-entries/clock-out', { break_minutes: breakMinutes });
      toast.success('Erfolgreich ausgestempelt');
      setShowBreakInput(false);
      setBreakMinutes(0);
      await fetchStatus();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Fehler beim Ausstempeln');
    } finally {
      setActing(false);
    }
  };

  const cancelClockOut = () => {
    setShowBreakInput(false);
    setBreakMinutes(0);
  };

  const formatElapsed = (minutes: number) => {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}h ${m.toString().padStart(2, '0')}min`;
  };

  if (loading) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8 animate-pulse">
        <div className="h-16 bg-gray-100 rounded-lg" />
      </div>
    );
  }

  if (!status) return null;

  const isClockedIn = status.is_clocked_in;
  const startTime = status.current_entry?.start_time?.substring(0, 5);

  return (
    <div className={`rounded-xl shadow-sm border p-6 mb-8 ${
      isClockedIn
        ? 'bg-green-50 border-green-200'
        : 'bg-white border-gray-200'
    }`}>
      <div className="flex flex-col sm:flex-row items-center gap-4">
        {/* Status info */}
        <div className="flex-1 text-center sm:text-left">
          {isClockedIn ? (
            <>
              <p className="text-sm text-green-700 font-medium">Eingestempelt seit {startTime}</p>
              <p className="text-2xl font-bold text-green-800">{formatElapsed(elapsed)}</p>
            </>
          ) : (
            <p className="text-sm text-gray-600">Nicht eingestempelt</p>
          )}
        </div>

        {/* Break input (shown before clock-out) */}
        {showBreakInput && (
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-700 whitespace-nowrap">Pause (Min.):</label>
            <input
              type="number"
              min="0"
              max="480"
              value={breakMinutes}
              onChange={(e) => setBreakMinutes(parseInt(e.target.value) || 0)}
              className="w-20 px-2 py-2 border border-gray-300 rounded-lg text-center focus:ring-2 focus:ring-red-300"
              autoFocus
            />
            <button
              onClick={cancelClockOut}
              className="text-sm text-gray-500 hover:text-gray-700 px-2 py-2"
            >
              Abbrechen
            </button>
          </div>
        )}

        {/* Action button */}
        {isClockedIn ? (
          <button
            onClick={handleClockOut}
            disabled={acting}
            className="flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold rounded-xl transition text-lg shadow-sm"
          >
            <LogOut size={22} />
            <span>{showBreakInput ? 'Jetzt ausstempeln' : 'Ausstempeln'}</span>
          </button>
        ) : (
          <button
            onClick={handleClockIn}
            disabled={acting}
            className="flex items-center gap-2 px-6 py-3 bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white font-semibold rounded-xl transition text-lg shadow-sm"
          >
            <LogIn size={22} />
            <span>Einstempeln</span>
          </button>
        )}
      </div>
    </div>
  );
}
