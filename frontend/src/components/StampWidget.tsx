import { useEffect, useState, useCallback } from 'react';
import { LogIn, LogOut, Play, Square, Check } from 'lucide-react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { useAuthStore } from '../stores/authStore';
import { getErrorMessage } from '../utils/errorMessage';
import { showArbzgWarnings } from '../utils/arbzgWarnings';
import { computeBreakError } from '../utils/breakValidation';
import { isBreakExceptionDisabledMessage } from '../utils/breakWaiverRetry';
import { useSystemStore } from '../stores/systemStore';
import { gapSegments } from '../utils/workBlocks';
import type { TimeBlock } from '../types/workBlocks';

interface ClockStatus {
  is_clocked_in: boolean;
  current_entry?: {
    id: string;
    start_time: string;
    note?: string;
  } | null;
  elapsed_minutes?: number | null;
  // Spec 2026-10-08 (8.4): Blöcke von heute und der Puffer des Ausstempelns (E80).
  blocks_today?: TimeBlock[];
  grace_minutes?: number;
}

interface StampWidgetProps {
  variant?: 'inline' | 'sheet';
  onSuccess?: () => void;
}

function formatTimer(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.floor(minutes % 60);
  let s = Math.round((minutes % 1) * 60);
  if (s === 60) s = 0;
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
  // #199: §4-Pausenpflicht beim Ausstempeln — Warnung + Pflicht-Begründung.
  const [breakWarn, setBreakWarn] = useState<string | null>(null);
  const [breakWaiverReason, setBreakWaiverReason] = useState('');
  // #499: Die Praxis kann die Ausnahme „Pflicht-Pause war nicht möglich"
  // abschalten — dann bleibt nur, die Pause nachzutragen.
  const breakExceptionAllowed = useSystemStore((s) => s.isBreakExceptionAllowed());

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
    if (acting) return;  // synchroner Doppelklick-Schutz (setActing ist async, disabled greift zu spät)
    setActing(true);
    try {
      const res = await apiClient.post('/time-entries/clock-in', {});
      toast.success('Erfolgreich eingestempelt');
      showArbzgWarnings(toast, res.data?.warnings);
      await fetchStatus();
      if (variant === 'sheet') {
        setShowSuccess(true);
        setTimeout(() => {
          setShowSuccess(false);
          onSuccess?.();
        }, 600);
      } else {
        // Cross-page refresh (CLAUDE.md): the inline (Dashboard) variant must
        // also notify so the overtime/saldo tiles + recent entries re-fetch.
        onSuccess?.();
      }
    } catch (err: any) {
      toast.error(getErrorMessage(err, 'Fehler beim Einstempeln'));
    } finally {
      setActing(false);
    }
  };

  // #499-Review F2: Die §4-Sperre steht im Dialog — schließt jemand danach das
  // Sheet oder verlässt die Seite, bliebe er unbemerkt eingestempelt, und am
  // Folgetag schlösse der Server den Eintrag auf 23:59 ohne Pause. Deshalb
  // zusätzlich ein Fehler-Toast, der den Dialog überlebt.
  const notifyStillClockedIn = (msg: string) => {
    const canWaive = breakExceptionAllowed && !isBreakExceptionDisabledMessage(msg);
    toast.error(
      `Noch NICHT ausgestempelt – die Pause des Tages reicht nicht (§4 ArbZG). ` +
        `Bitte Pause nachtragen${canWaive ? ' oder begründen' : ''}.`,
    );
  };

  const handleClockOut = async () => {
    if (!showBreakInput) {
      setShowBreakInput(true);
      return;
    }
    if (acting) return;  // synchroner Doppelklick-Schutz (setActing ist async)
    // #199: §4-Pausenpflicht — bei >6h Netto und unzureichender Pause die Pause
    // nacherfassen ODER eine dokumentierte Ausnahme verlangen, statt still mit
    // Warn-Toast durchzuwinken. Die Vorprüfung hier sieht nur den laufenden
    // Block; den ganzen TAG (mehrere aneinandergereihte Einträge) prüft der
    // Server und lehnt seit #499 mit 400 ab — die Meldung landet unten im
    // selben Dialog (catch).
    const waiver = breakExceptionAllowed ? breakWaiverReason.trim() : '';
    const st = status?.current_entry?.start_time;
    if (st && !user?.exempt_from_arbzg) {
      const startHHMM = st.includes('T') ? st.split('T')[1].substring(0, 5) : st.substring(0, 5);
      const now = new Date();
      const endHHMM = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
      // Spec 8.4: eine Lücke zwischen den Arbeitsblöcken (Segment ≥ 15 Min) deckt
      // §4 — dann keine Pausenabfrage; der Server rechnet genauso (E43).
      const segs = gapSegments(status?.blocks_today ?? [], status?.grace_minutes ?? 15, startHHMM, endHHMM);
      const breakErr = computeBreakError([], startHHMM, endHHMM, breakMinutes, false, segs);
      if (breakErr && !waiver) {
        setBreakWarn(breakErr);
        notifyStillClockedIn(breakErr);
        return; // Eingabe (Pause erhöhen oder — falls erlaubt — Begründung) erforderlich
      }
    }
    setActing(true);
    try {
      const res = await apiClient.post('/time-entries/clock-out', {
        break_minutes: breakMinutes,
        break_waiver_reason: waiver || undefined,
      });
      toast.success('Erfolgreich ausgestempelt');
      showArbzgWarnings(toast, res.data?.warnings);
      setShowBreakInput(false);
      setBreakMinutes(0);
      setBreakWarn(null);
      setBreakWaiverReason('');
      await fetchStatus();
      if (variant === 'sheet') {
        setShowSuccess(true);
        setTimeout(() => {
          setShowSuccess(false);
          onSuccess?.();
        }, 600);
      } else {
        // Cross-page refresh (CLAUDE.md): the inline (Dashboard) variant must
        // also notify so the overtime/saldo tiles + recent entries re-fetch.
        onSuccess?.();
      }
    } catch (err: any) {
      const msg = getErrorMessage(err, 'Fehler beim Ausstempeln');
      if (err?.response?.status === 400 && msg.includes('Pause')) {
        // #499: §4-Verstoß über den ganzen Tag — im Dialog zeigen, damit Pause
        // bzw. Begründung direkt nachgetragen werden kann; der Toast meldet
        // zusätzlich, dass NICHT ausgestempelt wurde.
        setBreakWarn(msg);
        notifyStillClockedIn(msg);
      } else {
        toast.error(msg);
      }
    } finally {
      setActing(false);
    }
  };

  // #499: Begründungsfeld nur, wenn die Praxis die Ausnahme erlaubt (und der
  // Server sie nicht ausdrücklich als abgeschaltet gemeldet hat).
  const offerWaiver = breakExceptionAllowed && !!breakWarn && !isBreakExceptionDisabledMessage(breakWarn);

  const cancelClockOut = () => {
    setShowBreakInput(false);
    setBreakMinutes(0);
    setBreakWarn(null);
    setBreakWaiverReason('');
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
            <label htmlFor="break-minutes-sheet" className="block text-sm text-text-secondary mb-1">Pause (Minuten)</label>
            <input
              id="break-minutes-sheet"
              type="number"
              inputMode="numeric"
              min={0}
              max={480}
              value={breakMinutes}
              onChange={(e) => { setBreakMinutes(parseInt(e.target.value) || 0); setBreakWarn(null); }}
              className="w-full border border-gray-200 rounded-xl px-4 py-3 text-center text-lg focus:ring-2 focus:ring-primary focus:border-transparent"
              autoFocus
            />
            {breakWarn && (
              <div className="mt-3 text-left bg-amber-50 border border-amber-200 rounded-xl p-3">
                <p className="text-sm text-amber-800">{breakWarn}</p>
                {offerWaiver ? (
                  <>
                    <p className="text-xs text-amber-700 mt-1">Pause oben nachtragen <strong>oder</strong> begründen, warum sie nicht möglich war:</p>
                    <textarea
                      value={breakWaiverReason}
                      onChange={(e) => setBreakWaiverReason(e.target.value)}
                      rows={2}
                      placeholder="z. B. Notfall, keine Vertretung"
                      className="w-full mt-2 border border-amber-300 rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-amber-500"
                    />
                  </>
                ) : (
                  <p className="text-xs text-amber-700 mt-1">Bitte die Pause oben nachtragen.</p>
                )}
              </div>
            )}
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
            className="w-full h-14 rounded-2xl bg-linear-to-r from-primary to-primary-dark text-white font-semibold text-lg flex items-center justify-center gap-2 active:scale-[0.97] transition-all disabled:opacity-50"
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
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <label htmlFor="break-minutes-inline" className="text-sm text-text-secondary whitespace-nowrap">Pause (Min.):</label>
              <input
                id="break-minutes-inline"
                type="number"
                inputMode="numeric"
                min="0"
                max="480"
                value={breakMinutes}
                onChange={(e) => { setBreakMinutes(parseInt(e.target.value) || 0); setBreakWarn(null); }}
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
            {breakWarn && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 max-w-md">
                <p className="text-sm text-amber-800">{breakWarn}</p>
                {offerWaiver ? (
                  <>
                    <p className="text-xs text-amber-700 mt-1">Pause nachtragen <strong>oder</strong> Ausnahme begründen:</p>
                    <textarea
                      value={breakWaiverReason}
                      onChange={(e) => setBreakWaiverReason(e.target.value)}
                      rows={2}
                      placeholder="z. B. Notfall, keine Vertretung"
                      className="w-full mt-2 border border-amber-300 rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-amber-500"
                    />
                  </>
                ) : (
                  <p className="text-xs text-amber-700 mt-1">Bitte die Pause nachtragen.</p>
                )}
              </div>
            )}
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
