/**
 * API client for Schichtplanung (#305).
 *
 * Thin typed wrappers over the `/api/shift-planning` endpoints. When the feature
 * flag is off, every endpoint answers 404 — callers should gate on
 * `systemStore.isShiftPlanningEnabled()` before rendering shift-planning UI.
 */
import apiClient from './client';

export interface Location {
  id: string;
  name: string;
  sort_order: number;
}

export interface Workstation {
  id: string;
  name: string;
  location_id: string | null;
  location_name: string | null;
  color: string | null;
  sort_order: number;
}

export interface ShiftAssignment {
  id: string;
  user_id: string;
  user_name: string;
  qualified?: boolean; // #305 M2d: trained for this slot's workstation
}

export interface ShiftSlot {
  id: string;
  workstation_id: string;
  workstation_name: string | null;
  color: string | null;
  weekday: number; // 0 = Mon … 6 = Sun
  start_time: string; // "HH:MM"
  end_time: string; // "HH:MM"
  min_staff: number;
  understaffed: boolean;
  unqualified?: boolean; // #305 M2d: ≥1 assigned person not trained for the workstation
  assignments: ShiftAssignment[];
}

export interface PlanSummary {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  active_from_date: string | null; // ISO date, #305 M2 KW-Planung
  active_until_date: string | null;
  active_today: boolean; // is_active OR window covers today
  slot_count: number;
  is_valid: boolean;
}

export interface PlanDetail {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  active_from_date: string | null;
  active_until_date: string | null;
  active_today: boolean;
  slots: ShiftSlot[];
  validation: { is_valid: boolean; understaffed_slot_ids: string[]; unqualified_slot_ids?: string[] };
}

// ─── Einweisungen / Skill-Matrix (#305 M2d) ───
export interface QualUser {
  id: string;
  first_name: string;
  last_name: string;
}
export interface QualificationMatrix {
  workstations: Workstation[];
  users: QualUser[];
  qualifications: { user_id: string; workstation_id: string }[];
}
export interface MyQualifications {
  workstations: Workstation[];
}

export interface MyTodayEntry {
  plan_id: string;
  plan_name: string;
  workstation_name: string | null;
  location_name: string | null;
  start_time: string;
  end_time: string;
}

export interface MyToday {
  date: string;
  weekday: number;
  entries: MyTodayEntry[];
}

export interface SlotInput {
  workstation_id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  min_staff: number;
}

const BASE = '/shift-planning';

// ─── locations ───
export const listLocations = () => apiClient.get<Location[]>(`${BASE}/locations`).then((r) => r.data);
export const createLocation = (name: string, sort_order = 0) =>
  apiClient.post<Location>(`${BASE}/locations`, { name, sort_order }).then((r) => r.data);
export const updateLocation = (id: string, name: string, sort_order: number) =>
  apiClient.put<Location>(`${BASE}/locations/${id}`, { name, sort_order }).then((r) => r.data);
export const deleteLocation = (id: string) => apiClient.delete(`${BASE}/locations/${id}`);

// ─── workstations ───
export const listWorkstations = () =>
  apiClient.get<Workstation[]>(`${BASE}/workstations`).then((r) => r.data);
export const createWorkstation = (body: {
  name: string;
  location_id?: string | null;
  color?: string | null;
  sort_order?: number;
}) => apiClient.post<Workstation>(`${BASE}/workstations`, body).then((r) => r.data);
export const updateWorkstation = (
  id: string,
  body: { name: string; location_id?: string | null; color?: string | null; sort_order?: number },
) => apiClient.put<Workstation>(`${BASE}/workstations/${id}`, body).then((r) => r.data);
export const deleteWorkstation = (id: string) => apiClient.delete(`${BASE}/workstations/${id}`);

// ─── plans ───
export const listPlans = () => apiClient.get<PlanSummary[]>(`${BASE}/plans`).then((r) => r.data);
export const getPlan = (id: string) => apiClient.get<PlanDetail>(`${BASE}/plans/${id}`).then((r) => r.data);
export const createPlan = (name: string, description?: string) =>
  apiClient.post<PlanSummary>(`${BASE}/plans`, { name, description: description || null }).then((r) => r.data);
export interface PlanUpdateBody {
  name: string;
  description?: string | null;
  active_from_date?: string | null;
  active_until_date?: string | null;
}
export const updatePlan = (id: string, body: PlanUpdateBody) =>
  apiClient
    .put<PlanSummary>(`${BASE}/plans/${id}`, {
      name: body.name,
      description: body.description ?? null,
      active_from_date: body.active_from_date ?? null,
      active_until_date: body.active_until_date ?? null,
    })
    .then((r) => r.data);
export const deletePlan = (id: string) => apiClient.delete(`${BASE}/plans/${id}`);

export interface GenerationResult {
  plan: PlanDetail;
  generation: { assigned: number; unfilled_slot_ids: string[] };
}
export const generatePlan = (id: string, body: { target_monday: string; mode: 'replace' | 'fill_gaps' }) =>
  apiClient.post<GenerationResult>(`${BASE}/plans/${id}/generate`, body).then((r) => r.data);
export const activatePlan = (id: string) =>
  apiClient.post<PlanSummary>(`${BASE}/plans/${id}/activate`).then((r) => r.data);
export const deactivatePlan = (id: string) =>
  apiClient.post<PlanSummary>(`${BASE}/plans/${id}/deactivate`).then((r) => r.data);

// ─── slots ───
export const createSlot = (planId: string, body: SlotInput) =>
  apiClient.post<ShiftSlot>(`${BASE}/plans/${planId}/slots`, body).then((r) => r.data);
export const updateSlot = (slotId: string, body: SlotInput) =>
  apiClient.put<ShiftSlot>(`${BASE}/slots/${slotId}`, body).then((r) => r.data);
export const deleteSlot = (slotId: string) => apiClient.delete(`${BASE}/slots/${slotId}`);

// ─── assignments ───
export const setAssignments = (slotId: string, userIds: string[]) =>
  apiClient
    .put<{ slot_id: string; assignments: ShiftAssignment[] }>(`${BASE}/slots/${slotId}/assignments`, {
      user_ids: userIds,
    })
    .then((r) => r.data);

// ─── qualifications / Einweisungen (#305 M2d) ───
export const getQualifications = () =>
  apiClient.get<QualificationMatrix>(`${BASE}/qualifications`).then((r) => r.data);
export const setUserQualifications = (userId: string, workstationIds: string[]) =>
  apiClient
    .put<{ user_id: string; workstation_ids: string[] }>(`${BASE}/qualifications/${userId}`, {
      workstation_ids: workstationIds,
    })
    .then((r) => r.data);
export const getMyQualifications = () =>
  apiClient.get<MyQualifications>(`${BASE}/me/qualifications`).then((r) => r.data);

// ─── dashboard ───
export const getMyToday = () => apiClient.get<MyToday>(`${BASE}/my-today`).then((r) => r.data);

export const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
export const WEEKDAY_LABELS_LONG = [
  'Montag',
  'Dienstag',
  'Mittwoch',
  'Donnerstag',
  'Freitag',
  'Samstag',
  'Sonntag',
];
