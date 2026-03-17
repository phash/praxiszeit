import { useEffect, useState, useCallback } from 'react';
import { LogIn, LogOut, Play, Square, Check } from 'lucide-react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { useAuthStore } from '../stores/authStore';
import { getErrorMessage } from '../utils/errorMessage';

interface ClockStatus {
  is_clocked_in: boolean;
  current_entry?: {
    id: string;
    start_time: string;
    note?: string;
  } | null;
  elapsed_minutes?: number | null;
}

interface StampWidgetProps {
  variant?: 'inline' | 'sheet';
  onSuccess?: () => void;
}

function formatTimer(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.floor(minutes % 60);
  const s = Math.round((minutes % 1) * 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export default function StampWidget({ variant = 'inline', onSuccess }: StampWidgetProps) {
  const toast = useToast();
  const { user } = useAuthStore();
  const [status, setStatus] = useState<ClockStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [showBreakInput, setShowBreakInput] = useState(false);
  const [breakMinutes, setBreakMinutes] = useState(0);
  const [showSuccess, setShowSuccess] = useState(false);

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

  // Live elapsed timer
  useEffect(() => {
    if (!status?.is_clocked_in) return;
    const interval = setInterval(() => {
      setElapsed((prev) => prev + (variant === 'sheet' ? 1 / 60 : 1));
    }, variant === 'sheet' ? 1000 : 60_000);
    return () => clearInterval(interval);
  }, [status?.is_clocked_in, variant]);

  const handleClockIn = async () => {
    setActing(true);
    try {
      await apiClient.post('/time-entries/clock-in', {});
      toast.success('Erfolgreich eingestempelt');
      await fetchStatus();
      if (variant === 'sheet') {
        setShowSuccess(true);
        setTimeout(() => {
          setShowSuccess(false);
          onSuccess?.();
        }, 600);
      }
    } catch (err: any) {
      toast.error(getErrorMessage(err, 'Fehler beim Einstempeln'));
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
      if (variant === 'sheet') {
        setShowSuccess(true);
        setTimeout(() => {
          setShowSuccess(false);
          onSuccess?.();
        }, 600);
      }
    } catch (err: any) {
      toast.error(getErrorMessage(err, 'Fehler beim Ausstempeln'));
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
    const m = Math.floor(minutes % 60);
    return `${h}h ${m.toString().padStart(2, '0')}min`;
  };

  // Don't show stamp widget if time tracking is inactive for this user
  if (user && user.track_hours === false) return null;

  if (loading) {
    if (variant === 'sheet') {
      return <div className="h-48 flex items-center justify-center"><div className="skeleton h-8 w-32" /></div>;
    }
    return (
      <div className="bg-surface rounded-2xl shadow-card border border-border p-6 mb-8 animate-pulse">
        <div className="h-16 bg-muted rounded-xl" />
      </div>
    );
  }

  if (!status) return null;

  const isClockedIn = status.is_clocked_in;
  const startTime = status.current_entry?.start_time;

  // ─── Sheet variant (mobile bottom-sheet hero) ───
  if (variant === 'sheet') {
    return (
      <div className="text-center relative">
        {/* Success overlay */}
        {showSuccess && (
          <div className="absolute inset-0 flex items-center justify-center z-10 bg-surface/80 rounded-2xl">
            <Check size={48} className="text-success" style={{ animation: 'stampSuccess 400ms ease-out' }} />
          </div>
        )}

        {/* Large Timer */}
        <div className={`text-[40px] font-bold tabular-nums leading-none mb-1 ${isClockedIn ? 'text-text-primary' : 'text-text-secondary'}`}>
          {isClockedIn ? formatTimer(elapsed) : '00:00:00'}
        </div>
        <p className="text-sm text-text-secondary mb-6">Arbeitszeit heute</p>

        {/* Info Pills */}
        <div className="flex justify-center gap-3 mb-6">
          <div className="bg-muted rounded-full px-4 py-2 text-center">
            <div className="text-sm font-semibold tabular-nums">
              {startTime ? (startTime.includes('T') ? startTime.split('T')[1] : startTime).substring(0, 5) : '—'}
            </div>
            <div className="text-xs text-text-secondary">Start</div>
          </div>
          <div className="bg-muted rounded-full px-4 py-2 text-center">
            <div className="text-sm font-semibold tabular-nums">
              {breakMinutes > 0 ? `${breakMinutes} min` : '—'}
            </div>
            <div className="text-xs text-text-secondary">Pause</div>
          </div>
        </div>

        {/* Break Input */}
        {showBreakInput && (
          <div className="mb-4">
            <label className="block text-sm text-text-secondary mb-1">Pause (Minuten)</label>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              max={480}
              value={breakMinutes}
              onChange={(e) => setBreakMinutes(parseInt(e.target.value) || 0)}
              className="w-full border border-gray-200 rounded-xl px-4 py-3 text-center text-lg focus:ring-2 focus:ring-primary focus:border-transparent"
              autoFocus
            />
            <button onClick={cancelClockOut} className="text-sm text-text-secondary hover:text-text-primary mt-2 transition">
              Abbrechen
            </button>
          </div>
        )}

        {/* Action Button */}
        {isClockedIn ? (
          <button
            onClick={handleClockOut}
            disabled={acting}
            className="w-full h-14 rounded-2xl bg-danger text-white font-semibold text-lg flex items-center justify-center gap-2 active:scale-[0.97] transition-all disabled:opacity-50"
          >
            <Square size={20} />
            {showBreakInput ? 'Jetzt ausstempeln' : 'Ausstempeln'}
          </button>
        ) : (
          <button
            onClick={handleClockIn}
            disabled={acting}
            className="w-full h-14 rounded-2xl bg-gradient-to-r from-primary to-primary-dark text-white font-semibold text-lg flex items-center justify-center gap-2 active:scale-[0.97] transition-all disabled:opacity-50"
          >
            <Play size={20} />
            Einstempeln
          </button>
        )}
      </div>
    );
  }

  // ─── Inline variant (desktop dashboard) ───
  return (
    <div className={`rounded-2xl shadow-card border p-6 mb-8 transition-colors ${
      isClockedIn
        ? 'bg-success/10 border-success/30'
        : 'bg-muted border-border'
    }`}>
      <div className="flex flex-col sm:flex-row items-center gap-4">
        {/* Status info */}
        <div className="flex-1 text-center sm:text-left">
          {isClockedIn ? (
            <>
              <p className="text-sm text-success font-medium">Eingestempelt seit {startTime?.substring(0, 5)}</p>
              <p className="text-3xl font-bold text-text-primary">{formatElapsed(elapsed)}</p>
            </>
          ) : (
            <p className="text-sm text-text-secondary">Nicht eingestempelt</p>
          )}
        </div>

        {/* Break input (shown before clock-out) */}
        {showBreakInput && (
          <div className="flex items-center gap-2">
            <label className="text-sm text-text-secondary whitespace-nowrap">Pause (Min.):</label>
            <input
              type="number"
              inputMode="numeric"
              min="0"
              max="480"
              value={breakMinutes}
              onChange={(e) => setBreakMinutes(parseInt(e.target.value) || 0)}
              className="w-20 px-2 py-2 border border-gray-200 rounded-xl text-center focus:ring-2 focus:ring-primary"
              autoFocus
            />
            <button
              onClick={cancelClockOut}
              className="text-sm text-text-secondary hover:text-text-primary px-2 py-2 transition"
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
            className="flex items-center gap-2 px-8 py-4 bg-danger hover:bg-red-700 disabled:opacity-50 text-white font-semibold rounded-2xl transition-all active:scale-[0.97] text-xl shadow-soft"
          >
            <LogOut size={24} />
            <span>{showBreakInput ? 'Jetzt ausstempeln' : 'Ausstempeln'}</span>
          </button>
        ) : (
          <button
            onClick={handleClockIn}
            disabled={acting}
            className="flex items-center gap-2 px-8 py-4 bg-success hover:bg-green-700 disabled:opacity-50 text-white font-semibold rounded-2xl transition-all active:scale-[0.97] text-xl shadow-soft"
          >
            <LogIn size={24} />
            <span>Einstempeln</span>
          </button>
        )}
      </div>
    </div>
  );
}
