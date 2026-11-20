import { create } from 'zustand';
import type { ServerErrorHint } from '../api/feedback';

/**
 * #557: Merker für den jüngsten Serverfehler (5xx) und die offene
 * Problemmeldung aus dem Fehler-Toast. Der Antwort-Interceptor in
 * `api/client.ts` schreibt den Merker, `ToastContext.error()` holt ihn genau
 * einmal ab; `ReportDialogHost` öffnet den Dialog, solange `request` gesetzt ist.
 */
export const RECENT_SERVER_ERROR_WINDOW_MS = 5000;

export interface ReportRequest {
  serverError: ServerErrorHint;
  initialTitle: string;
}

interface ReportState {
  lastServerError: (ServerErrorHint & { at: number }) | null;
  recordServerError: (hint: ServerErrorHint, at?: number) => void;
  /** Liefert den Hinweis nur, wenn er höchstens `windowMs` alt ist — und nur einmal. */
  takeRecentServerError: (now?: number, windowMs?: number) => ServerErrorHint | null;
  request: ReportRequest | null;
  /** false = es ist schon eine Meldung offen (wird nicht ersetzt, Eingabe bleibt). */
  openReport: (r: ReportRequest) => boolean;
  closeReport: () => void;
}

export const useReportStore = create<ReportState>()((set, get) => ({
  lastServerError: null,
  recordServerError: (hint, at = Date.now()) =>
    set({ lastServerError: { status: hint.status, method: hint.method, path: hint.path, at } }),
  takeRecentServerError: (now = Date.now(), windowMs = RECENT_SERVER_ERROR_WINDOW_MS) => {
    const last = get().lastServerError;
    if (!last) return null;
    set({ lastServerError: null });
    if (now - last.at > windowMs || now < last.at) return null;
    return { status: last.status, method: last.method, path: last.path };
  },
  request: null,
  openReport: (r) => {
    if (get().request) return false;
    set({ request: r });
    return true;
  },
  closeReport: () => set({ request: null }),
}));
