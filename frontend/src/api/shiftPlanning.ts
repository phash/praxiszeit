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
  assignments: ShiftAssignment[];
}

export interface PlanSummary {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  slot_count: number;
  is_valid: boolean;
}

export interface PlanDetail {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  slots: ShiftSlot[];
  validation: { is_valid: boolean; understaffed_slot_ids: string[] };
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
export const updatePlan = (id: string, name: string, description?: string) =>
  apiClient.put<PlanSummary>(`${BASE}/plans/${id}`, { name, description: description || null }).then((r) => r.data);
export const deletePlan = (id: string) => apiClient.delete(`${BASE}/plans/${id}`);
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
