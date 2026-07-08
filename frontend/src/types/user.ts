// Issue #151: Eine gemeinsame User-Definition statt drei-/vierfacher Duplikate
// (authStore, UserForm, Users, ImportXls). Superset passend zum Backend
// UserListResponse/UserResponse (backend/app/schemas/user.py). Felder, die nicht
// in JEDER Response enthalten sind (Login liefert z. B. kein profile_picture),
// sind optional markiert.
export interface User {
  id: string;
  username: string;
  email: string | null;
  first_name: string;
  last_name: string;
  role: 'admin' | 'employee';
  weekly_hours: number;
  vacation_days: number;
  work_days_per_week: number;
  track_hours: boolean;
  exempt_from_arbzg: boolean; // §18 ArbZG: leitende Angestellte
  is_night_worker: boolean;
  receives_company_closures: boolean;
  is_active: boolean;
  is_hidden: boolean;
  calendar_color: string;
  totp_enabled: boolean;
  use_daily_schedule: boolean;
  hours_monday: number | null;
  hours_tuesday: number | null;
  hours_wednesday: number | null;
  hours_thursday: number | null;
  hours_friday: number | null;
  scheduled_start_monday: string | null;
  scheduled_end_monday: string | null;
  scheduled_start_tuesday: string | null;
  scheduled_end_tuesday: string | null;
  scheduled_start_wednesday: string | null;
  scheduled_end_wednesday: string | null;
  scheduled_start_thursday: string | null;
  scheduled_end_thursday: string | null;
  scheduled_start_friday: string | null;
  scheduled_end_friday: string | null;
  first_work_day: string | null;
  last_work_day: string | null;
  deactivated_at: string | null;
  created_at: string;
  // Nicht in jeder Response enthalten:
  suggested_vacation_days?: number;
  department?: string | null;
  child_sick_days_per_year?: number | null; // #376 §45 SGB V; null = Tenant-Default
  milog_working_time_account?: boolean; // #377 §2 Abs.2 MiLoG: Arbeitszeitkonto-Prüfungen
  profile_picture?: string | null; // aus Login-Response ausgeschlossen (~690 KB)
  onboarding_completed_at?: string | null; // NULL = Onboarding noch nicht gesehen
  vacation_carryover_deadline?: string | null;
}
