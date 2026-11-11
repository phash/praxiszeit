import { useEffect, useState, useCallback, useRef } from 'react';
import { LogIn, LogOut, Play, Square, Check } from 'lucide-react';
import apiClient from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { useAuthStore } from '../stores/authStore';
import { trackHoursToday } from '../utils/contractToday';
import { getErrorMessage } from '../utils/errorMessage';
import { showArbzgWarnings } from '../utils/arbzgWarnings';
import { computeBreakError } from '../utils/breakValidation';
import { breakWaiverReasonError, isBreakExceptionDisabledMessage } from '../utils/breakWaiverRetry';
import { useSystemStore } from '../stores/systemStore';
import { useUIStore } from '../stores/uiStore';
import { gapSegments, hullClamp } from '../utils/workBlocks';
import { stripWarningCode } from '../utils/arbzgWarnings';
import { useSundayOrHoliday } from '../hooks/useSundayOrHoliday';
import ChangeRequestForm from './ChangeRequestForm';
import type { TimeBlock } from '../types/workBlocks';

/** #540 (A1-04/A2-7): automatisch geschlossener Eintrag ohne tatsächliches Ende. */
interface AutoClosedEntry {
  id: string;
  date: string;
  start_time: string;
  end_time: string | null;
  break_minutes: number;
  note?: string;
  raw_start_time?: string | null;
  raw_end_time?: string | null;
  auto_closed?: boolean | null;
  warnings?: string[];
}

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
  blockless_workday?: boolean; // Werktag ohne Blöcke → nichts angerechnet
  grace_minutes?: number;
  auto_closed_entries?: AutoClosedEntry[];
}

function localIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function formatDE(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

// Zugänglicher Name des §4-Begründungsfelds (beide Varianten).
const BREAK_WAIVER_FIELD_LABEL = 'Begründung, warum die Pflicht-Pause nicht möglich war';

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
  // zeit-04: Anzeige aus Zeitstempel ableiten, nicht per Tick hochzählen
  // (Hintergrund-Tabs drosseln Timer).
  const elapsedBase = useRef({ minutes: 0, at: Date.now() });
  const stampVersion = useUIStore((s) => s.stampVersion);
  const [showBreakInput, setShowBreakInput] = useState(false);
  const [breakMinutes, setBreakMinutes] = useState(0);
  const [showSuccess, setShowSuccess] = useState(false);
  // #199: §4-Pausenpflicht beim Ausstempeln — Warnung + Pflicht-Begründung.
  const [breakWarn, setBreakWarn] = useState<string | null>(null);
  const [breakWaiverReason, setBreakWaiverReason] = useState('');
  // #499: Die Praxis kann die Ausnahme „Pflicht-Pause war nicht möglich"
  // abschalten — dann bleibt nur, die Pause nachzutragen.
  const breakExceptionAllowed = useSystemStore((s) => s.isBreakExceptionAllowed());
  // #538 (A1-02): Sperre beim Einstempeln (Überschneidung) am Widget zeigen.
  const [clockInError, setClockInError] = useState<string | null>(null);
  // #540 (A1-11): §10-Ausnahmegrund beim Ausstempeln an Sonn-/Feiertagen.
  const [sundayReason, setSundayReason] = useState('');
  const showSundayReason = useSundayOrHoliday(localIso(new Date()), null, showBreakInput);
  // #540 (A2-7): Antrag für das tatsächliche Ende eines automatisch geschlossenen Eintrags.
  const [crEntry, setCrEntry] = useState<AutoClosedEntry | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiClient.get('/time-entries/clock-status');
      setStatus(res.data);
      const base = res.data.elapsed_minutes ?? 0;
      elapsedBase.current = { minutes: base, at: Date.now() };
      setElapsed(base);
    } catch {
      // Silently fail - widget is non-critical
    } finally {
      setLoading(false);
    }
  }, []);

  // zeit-03: beim Mount, nach Stempeln auf anderer Seite/Gerät-Wechsel
  // (stampVersion) und bei Rückkehr in den Tab neu laden.
  useEffect(() => {
    fetchStatus();
  }, [fetchStatus, stampVersion]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') fetchStatus();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [fetchStatus]);

  // Live elapsed timer
  useEffect(() => {
    if (!status?.is_clocked_in) return;
    const interval = setInterval(() => {
      const { minutes, at } = elapsedBase.current;
      const diff = (Date.now() - at) / 60_000;
      setElapsed(variant === 'sheet' ? minutes + diff : minutes + Math.floor(diff));
    }, variant === 'sheet' ? 1000 : 60_000);
    return () => clearInterval(interval);
  }, [status?.is_clocked_in, variant]);

  const handleClockIn = async () => {
    if (acting) return;  // synchroner Doppelklick-Schutz (setActing ist async, disabled greift zu spät)
    setActing(true);
    setClockInError(null);
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
      const msg = getErrorMessage(err, 'Fehler beim Einstempeln');
      if (err?.response?.status === 409) {
        // #538: Überschneidung / belegter Beginn — Hinweis am Widget, nicht nur als Toast.
        setClockInError(msg);
      } else {
        toast.error(msg);
        // zeit-03: Zustandsfehler (z. B. „Bereits eingestempelt“) → Status neu laden.
        if (err?.response?.status === 400) void fetchStatus();
      }
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
    // #540 (A1-05): eine begonnene, aber zu kurze Begründung lehnt der Server ab.
    if (waiver && breakWaiverReasonError(waiver)) {
      setBreakWarn(`${breakWarn ?? ''} ${breakWaiverReasonError(waiver)}`.trim());
      return;
    }
    const st = status?.current_entry?.start_time;
    if (st && !user?.exempt_from_arbzg) {
      const startHHMM = st.includes('T') ? st.split('T')[1].substring(0, 5) : st.substring(0, 5);
      const now = new Date();
      const endHHMM = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
      // Spec 8.4: eine Lücke zwischen den Arbeitsblöcken (Segment ≥ 15 Min) deckt
      // §4 — dann keine Pausenabfrage; der Server rechnet genauso (E43).
      // Gesamtreview PR2 (Fund 13): auch die Hülle — §4 gilt der ANGERECHNETEN
      // Zeit, Stempelzeit nach [letzter Block + Puffer] ist keine Arbeitszeit.
      const blocks = status?.blocks_today ?? [];
      const grace = status?.grace_minutes ?? 15;
      const credited = hullClamp(blocks, grace, startHHMM, endHHMM, status?.blockless_workday ?? false);
      const segs = gapSegments(blocks, grace, credited.start, credited.end);
      const breakErr = computeBreakError([], credited.start, credited.end, breakMinutes, false, segs);
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
        sunday_exception_reason: showSundayReason && sundayReason.trim() ? sundayReason.trim() : undefined,
      });
      // #540 (A2-7): war der offene Eintrag von einem früheren Tag, schließt der
      // Server ihn automatisch und vermerkt den Ausstempelversuch — das ist kein
      // normales Ausstempeln; der Hinweis (Warnung) und der Antrags-Knopf unten
      // führen weiter.
      if (res.data?.auto_closed) {
        toast.warning('Der offene Eintrag eines früheren Tages wurde automatisch geschlossen.');
      } else {
        toast.success('Erfolgreich ausgestempelt');
      }
      showArbzgWarnings(toast, res.data?.warnings);
      setShowBreakInput(false);
      setBreakMinutes(0);
      setBreakWarn(null);
      setBreakWaiverReason('');
      setSundayReason('');
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
        // zeit-03: Zustandsfehler (z. B. „Kein offener Eintrag“) → Status neu laden.
        const code = err?.response?.status;
        if (code === 400 || code === 404 || code === 409) void fetchStatus();
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
    setSundayReason('');
  };

  // #540 (A1-11): Feld für den §10-Grund im Ausstempel-Dialog (Sonn-/Feiertag).
  const sundayReasonField = showSundayReason ? (
    <div className="mt-3 text-left">
      <label htmlFor="stamp-sunday-reason" className="block text-sm text-text-secondary mb-1">
        Ausnahmegrund (§10 ArbZG) – Sonn-/Feiertagsarbeit
      </label>
      <input
        id="stamp-sunday-reason"
        type="text"
        value={sundayReason}
        maxLength={2000}
        onChange={(e) => setSundayReason(e.target.value)}
        placeholder="z. B. Notdienst, Patientenversorgung"
        className="w-full border border-amber-300 rounded-xl px-3 py-2 text-sm bg-amber-50 focus:ring-2 focus:ring-amber-400"
      />
    </div>
  ) : null;

  // #538 / #540: Hinweise, die das Widget selbst trägt (nicht nur als Toast).
  const autoClosed = status?.auto_closed_entries?.[0] ?? null;
  const notices = (
    <>
      {clockInError && (
        <div role="alert" className="mt-3 text-left bg-red-50 border border-red-200 rounded-xl p-3">
          <p className="text-sm text-red-800">{clockInError}</p>
        </div>
      )}
      {autoClosed && (
        <div role="status" className="mt-3 text-left bg-amber-50 border border-amber-200 rounded-xl p-3">
          <p className="text-sm text-amber-900">
            Ihr Eintrag vom {formatDE(autoClosed.date)} (ab {(autoClosed.raw_start_time || autoClosed.start_time).substring(0, 5)}) wurde
            automatisch geschlossen, weil das Ausstempeln fehlte. Bitte tragen Sie das tatsächliche Arbeitsende nach.
          </p>
          {autoClosed.warnings?.[0] && (
            <p className="text-xs text-amber-800 mt-1">{stripWarningCode(autoClosed.warnings[0])}</p>
          )}
          <button
            type="button"
            onClick={() => setCrEntry(autoClosed)}
            className="mt-2 px-3 py-1.5 text-sm rounded-lg bg-amber-600 text-white hover:bg-amber-700"
          >
            Arbeitsende per Antrag nachtragen
          </button>
        </div>
      )}
      {crEntry && (
        <ChangeRequestForm
          entry={crEntry}
          requestType="update"
          actualEndRequired
          onClose={() => setCrEntry(null)}
          onSuccess={() => {
            setCrEntry(null);
            toast.success('Änderungsantrag eingereicht');
            fetchStatus();
          }}
        />
      )}
    </>
  );

  const formatElapsed = (minutes: number) => {
    const h = Math.floor(minutes / 60);
    const m = Math.floor(minutes % 60);
    return `${h}h ${m.toString().padStart(2, '0')}min`;
  };

  // Don't show stamp widget if time tracking is inactive for this user
  if (user && trackHoursToday(user) === false) return null; // F011: Vertrag von heute

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
                      // Gesamtreview 1.20 (Fund 19): eigener Name — der Platzhalter
                      // ist nur ein Beispiel (wie TimeTracking: „Begründung …").
                      aria-label={BREAK_WAIVER_FIELD_LABEL}
                      placeholder="z. B. Notfall, keine Vertretung"
                      className="w-full mt-2 border border-amber-300 rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-amber-500"
                    />
                  </>
                ) : (
                  <p className="text-xs text-amber-700 mt-1">Bitte die Pause oben nachtragen.</p>
                )}
              </div>
            )}
            {sundayReasonField}
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
        {notices}
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
                      // Gesamtreview 1.20 (Fund 19): eigener Name — der Platzhalter
                      // ist nur ein Beispiel (wie TimeTracking: „Begründung …").
                      aria-label={BREAK_WAIVER_FIELD_LABEL}
                      placeholder="z. B. Notfall, keine Vertretung"
                      className="w-full mt-2 border border-amber-300 rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-amber-500"
                    />
                  </>
                ) : (
                  <p className="text-xs text-amber-700 mt-1">Bitte die Pause nachtragen.</p>
                )}
              </div>
            )}
            {sundayReasonField}
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
      {notices}
    </div>
  );
}
