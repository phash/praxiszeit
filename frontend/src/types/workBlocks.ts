// Spec 2026-10-08, Abschnitt 3.1: kanonische JSON-Form der Arbeitszeit-Blöcke
// (users.work_blocks / working_hours_changes.blocks). Genau fünf Einträge,
// Index 0 = Montag … 4 = Freitag; Zeiten als "HH:MM".
export interface TimeBlock {
  start: string;
  end: string;
}

export interface DayBlocks {
  blocks: TimeBlock[];
  // null = Altfenster aus Migration 073: kappt nur, treibt kein Tagessoll.
  pause_minutes: number | null;
}

export type WeekBlocks = DayBlocks[];
