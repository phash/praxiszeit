/**
 * API client for #312 custom absence reasons.
 *
 * Admin CRUD under /admin/absence-reasons; every authenticated user can read
 * the active list (/absence-reasons) for the booking picker. A reason's
 * base_behavior maps to a built-in absence type at booking time (backend).
 */
import apiClient from './client';

export type AbsenceReasonBehavior = 'worked' | 'paid_free' | 'overtime_comp';

export interface AbsenceReason {
  id: string;
  name: string;
  color: string | null;
  base_behavior: AbsenceReasonBehavior;
  is_active: boolean;
  sort_order: number;
}

export const BEHAVIOR_LABELS: Record<AbsenceReasonBehavior, string> = {
  worked: 'Zählt als gearbeitet',
  paid_free: 'Bezahlt frei',
  overtime_comp: 'Überstundenabbau',
};

export const BEHAVIOR_HINTS: Record<AbsenceReasonBehavior, string> = {
  worked: 'Wird als Arbeitszeit gutgeschrieben (z. B. Berufsschule für Azubis) — keine Stundenverluste.',
  paid_free: 'Bezahlt frei: Soll wird auf 0 gesetzt, saldoneutral, kein Urlaubsabzug.',
  overtime_comp: 'Überstundenabbau: das Überstundenkonto sinkt um das Tagessoll.',
};

const ADMIN = '/admin/absence-reasons';
const READ = '/absence-reasons';

export const listReasons = (includeInactive = false) =>
  apiClient.get<AbsenceReason[]>(`${ADMIN}?include_inactive=${includeInactive}`).then((r) => r.data);

export const createReason = (body: {
  name: string;
  color?: string | null;
  base_behavior: AbsenceReasonBehavior;
  sort_order?: number;
}) => apiClient.post<AbsenceReason>(ADMIN, body).then((r) => r.data);

export const updateReason = (
  id: string,
  body: Partial<{ name: string; color: string | null; is_active: boolean; sort_order: number }>,
) => apiClient.put<AbsenceReason>(`${ADMIN}/${id}`, body).then((r) => r.data);

export const deleteReason = (id: string) => apiClient.delete(`${ADMIN}/${id}`);

/** Active reasons for the booking picker (any authenticated user). */
export const myReasons = () => apiClient.get<AbsenceReason[]>(READ).then((r) => r.data);
