// Issue #151: Eine gemeinsame User-Definition statt drei-/vierfacher Duplikate
// (authStore, UserForm, Users, ImportXls). Superset passend zum Backend
// UserListResponse/UserResponse (backend/app/schemas/user.py). Felder, die nicht
// in JEDER Response enthalten sind (Login liefert z. B. kein profile_picture),
// sind optional markiert.
import type { WeekBlocks } from './workBlocks';

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
  first_work_day: string | null;
  last_work_day: string | null;
  deactivated_at: string | null;
  created_at: string;
  // Nicht in jeder Response enthalten:
  suggested_vacation_days?: number;
  department?: string | null;
  child_sick_days_per_year?: number | null; // #376 §45 SGB V; null = Tenant-Default
  milog_working_time_account?: boolean; // #377 §2 Abs.2 MiLoG: Arbeitszeitkonto-Prüfungen
  agreed_monthly_hours?: number | null; // #377 Baustein 2a: vereinbarte Monatszeit; null = aus weekly_hours
  use_fixed_monthly_target?: boolean; // #377 Baustein 2b: festes Monats-Soll = agreed_monthly_hours
  profile_picture?: string | null; // aus Login-Response ausgeschlossen (~690 KB)
  onboarding_completed_at?: string | null; // NULL = Onboarding noch nicht gesehen
  vacation_carryover_deadline?: string | null;
  // Spec 2026-10-08 (11.1/11.5): Rohwert der User-Zeile und die für HEUTE
  // datumsaufgelösten Blöcke (Admin-Liste/-Detail, Login). Nur Anzeige — die
  // Blöcke ändern sich ausschließlich über den Verlauf mit Wirkungsdatum.
  work_blocks?: WeekBlocks | null;
  work_blocks_today?: WeekBlocks | null;
}
