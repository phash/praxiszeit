/**
 * API client for #312 custom absence reasons.
 *
 * Admin CRUD under /admin/absence-reasons; every authenticated user can read
 * the active list (/absence-reasons) for the booking picker. A reason's
 * base_behavior maps to a built-in absence type at booking time (backend).
 */
import apiClient from './client';

export type AbsenceReasonBehavior = 'worked' | 'paid_free' | 'overtime_comp' | 'unpaid_free';

export interface AbsenceReason {
  id: string;
  name: string;
  color: string | null;
  base_behavior: AbsenceReasonBehavior;
  is_active: boolean;
  sort_order: number;
  tracks_child_sick_limit: boolean; // #376
}

export const BEHAVIOR_LABELS: Record<AbsenceReasonBehavior, string> = {
  worked: 'Zählt als gearbeitet',
  paid_free: 'Bezahlt frei',
  overtime_comp: 'Überstundenabbau',
  unpaid_free: 'Unbezahlt frei', // #376
};

export const BEHAVIOR_HINTS: Record<AbsenceReasonBehavior, string> = {
  worked: 'Wird als Arbeitszeit gutgeschrieben (z. B. Berufsschule für Azubis) — keine Stundenverluste.',
  paid_free: 'Bezahlt frei: Soll wird auf 0 gesetzt, saldoneutral, kein Urlaubsabzug.',
  overtime_comp: 'Überstundenabbau: das Überstundenkonto sinkt um das Tagessoll.',
  unpaid_free:
    'Unbezahlt frei: Soll auf 0, saldoneutral, kein Urlaubsabzug, aber unbezahlt (Lohn gekürzt) — z. B. Kind krank (§45 SGB V).', // #376
};

export interface AbsenceReasonPreset {
  name: string;
  color: string;
  base_behavior: AbsenceReasonBehavior;
  tracks_child_sick_limit: boolean;
}

// #376: kuratierte Vorlagen zum 1-Klick-Aktivieren (kein DB-Seed). Verhalten je
// Grund im Betrieb frei änderbar — dies sind sinnvolle Defaults.
export const ABSENCE_REASON_PRESETS: AbsenceReasonPreset[] = [
  { name: 'Kind krank', color: '#e67e22', base_behavior: 'unpaid_free', tracks_child_sick_limit: true },
  { name: 'Todesfall naher Angehöriger', color: '#7f8c8d', base_behavior: 'paid_free', tracks_child_sick_limit: false },
  { name: 'Eigene Hochzeit', color: '#d35400', base_behavior: 'paid_free', tracks_child_sick_limit: false },
  { name: 'Geburt eines Kindes', color: '#16a085', base_behavior: 'paid_free', tracks_child_sick_limit: false },
  { name: 'Umzug (betrieblich)', color: '#2980b9', base_behavior: 'paid_free', tracks_child_sick_limit: false },
  { name: 'Arztbesuch (unvermeidbar)', color: '#8e44ad', base_behavior: 'paid_free', tracks_child_sick_limit: false },
  { name: 'Pflege naher Angehöriger', color: '#c0392b', base_behavior: 'unpaid_free', tracks_child_sick_limit: false },
];

const ADMIN = '/admin/absence-reasons';
const READ = '/absence-reasons';

export const listReasons = (includeInactive = false) =>
  apiClient.get<AbsenceReason[]>(`${ADMIN}?include_inactive=${includeInactive}`).then((r) => r.data);

export const createReason = (body: {
  name: string;
  color?: string | null;
  base_behavior: AbsenceReasonBehavior;
  sort_order?: number;
  tracks_child_sick_limit?: boolean; // #376
}) => apiClient.post<AbsenceReason>(ADMIN, body).then((r) => r.data);

export const updateReason = (
  id: string,
  body: Partial<{ name: string; color: string | null; is_active: boolean; sort_order: number }>,
) => apiClient.put<AbsenceReason>(`${ADMIN}/${id}`, body).then((r) => r.data);

export const deleteReason = (id: string) => apiClient.delete(`${ADMIN}/${id}`);

/** Active reasons for the booking picker (any authenticated user). */
export const myReasons = () => apiClient.get<AbsenceReason[]>(READ).then((r) => r.data);
