from pydantic import BaseModel, ConfigDict, Field
from datetime import date
from decimal import Decimal
from typing import List, Optional


class MonthlyDashboard(BaseModel):
    """Dashboard data for current month."""
    year: int
    month: int
    target_hours: float
    actual_hours: float
    balance: float


class OvertimeHistory(BaseModel):
    """Overtime history by month."""
    year: int
    month: int
    target: float
    actual: float
    balance: float
    cumulative: float


class OvertimeAccount(BaseModel):
    """Complete overtime account."""
    current_balance: float
    history: List[OvertimeHistory]
    milog_warnings: List[str] = []  # #377 §2 Abs.2 MiLoG (self-scoped; leer wenn Flag aus)
    # #402: bereits feststehender künftiger Freizeitausgleich (Σ Tages-Soll der
    # OVERTIME-Abwesenheiten bis 31.12.) + projizierter Saldo am Jahresende.
    # projected_year_end ist None, wenn kein künftiger Freizeitausgleich existiert
    # (Frontend blendet die Zeile dann aus).
    future_comp_hours: float = 0.0
    projected_year_end: Optional[float] = None


class YtdOvertime(BaseModel):
    """Year-to-date overtime summary (Jan 1 to today)."""
    year: int
    target_hours: float
    actual_hours: float
    overtime: float
    carryover_hours: float = 0.0


class VacationAccount(BaseModel):
    """Vacation account for a year."""
    year: int
    budget_hours: float
    budget_days: float
    used_hours: float
    used_days: float
    remaining_hours: float
    remaining_days: float
    # Year-end warning info
    carryover_deadline: Optional[date] = None  # Deadline to use remaining vacation
    has_carryover_warning: bool = False  # True if remaining vacation at year end


class AdminUserOverview(BaseModel):
    """#194: per-user vacation account + YTD overtime for the admin user list.

    Bulk-served by GET /api/admin/users-overview so the frontend needs a
    single request instead of the former per-user N+1 vacation fetch.
    """
    user_id: str
    first_name: str
    last_name: str
    track_hours: bool
    vacation: VacationAccount
    overtime: YtdOvertime
    child_sick_used: float = 0.0   # #376 §45 SGB V: verbrauchte Kind-krank-Tage im Jahr
    child_sick_cap: int = 15       # #376: persönlicher Cap (MA-Feld → Tenant-Default → 15)
    milog_warnings: List[str] = [] # #377 §2 Abs.2 MiLoG (leer wenn Flag aus / nichts überschritten)


class WeeklyHoursChangeInPeriod(BaseModel):
    """#415: eine Vertragsänderung, die INNERHALB des Berichtszeitraums wirksam
    wird. Änderungen davor stecken bereits im Startwert.

    #431: die Zeile trägt den vollständigen Snapshot. Für Mitarbeitende mit
    individuellem Tagesplan ist `weekly_hours` nur die Summe der Tageswerte und
    steuert kein einziges Tagessoll — ohne `day_hours` könnte die Oberfläche
    dieselbe nichtssagende Zahl zeigen wie vor #431, und eine Umverteilung bei
    gleicher Wochensumme sähe aus wie „keine Änderung".

    `work_days_per_week` ist Teil des Snapshots: eine Änderung von 40 h/5 Tage
    auf 40 h/4 Tage verschiebt das Tagessoll und erzeugt genau deshalb ein
    eigenes Segment. Gerendert wird der Wert nur, wenn er sich gegenüber dem
    vorhergehenden Segment ändert — siehe `work_days_changed`.
    """
    effective_from: date
    weekly_hours: float
    use_daily_schedule: bool = False
    # Immer fünf Einträge, Index 0 = Montag; `None` = kein geplanter Arbeitstag.
    # Im gleichmäßigen Modus durchgehend `None` (dort sind die Tageswerte inert).
    day_hours: List[Optional[float]] = Field(default_factory=lambda: [None] * 5)
    work_days_per_week: Optional[int] = None
    # Abschluss-Review #431, Fund 1: ändert diese Zeile die ARBEITSTAGE
    # gegenüber dem unmittelbar davor gültigen Zustand? Der Befund kommt vom
    # Server, weil die Antwort nur die Änderungen trägt (`segments[1:]`) — das
    # Basissegment davor sieht der Bildschirm nie und könnte die Frage für die
    # ERSTE Änderung eines Zeitraums gar nicht beantworten. Genau die Frage
    # entscheidet in beiden Zwillingen über den Zusatz „auf 4 Arbeitstage";
    # ein serverseitig berechnetes Ja/Nein kann zwischen Datei und Bildschirm
    # nicht auseinanderlaufen. Default `False` = nichts behaupten.
    work_days_changed: bool = False

    @classmethod
    def from_segment(cls, segment, previous=None) -> "WeeklyHoursChangeInPeriod":
        """DIE eine Übersetzung eines `calculation_service.ScheduleSegment` in die
        API-Form — genutzt vom Monats- UND vom Wochenbericht. Zwei getrennte
        Umwandlungen wären zwei Stellen, die auseinanderlaufen können.

        `previous` ist das unmittelbar davor gültige Segment (`None` = keins);
        daraus entsteht `work_days_changed`, über dieselbe Regel, die auch der
        Datei-Export benutzt (`calculation_service.work_days_changed`).

        `float`-Cast wie überall bei Response-Schemas (CLAUDE.md: `float` statt
        `Decimal`)."""
        # Lokaler Import: die Schema-Schicht soll den Service nicht schon beim
        # Modul-Laden ziehen (die Router importieren beide, aber in eigener
        # Reihenfolge) — die Regel selbst darf trotzdem nur EINMAL existieren.
        from app.services.calculation_service import work_days_changed
        return cls(
            effective_from=segment.start,
            weekly_hours=float(segment.weekly_hours),
            use_daily_schedule=bool(segment.use_daily_schedule),
            day_hours=[None if h is None else float(h) for h in segment.day_hours],
            work_days_per_week=segment.work_days_per_week,
            work_days_changed=work_days_changed(previous, segment),
        )


class EmployeeMonthlyReport(BaseModel):
    """Monthly report for a single employee."""
    user_id: str
    first_name: str
    last_name: str
    weekly_hours: float
    target_hours: float
    actual_hours: float
    balance: float
    overtime_cumulative: float
    # #402: projizierter Überstundensaldo am 31.12. = overtime_cumulative − bereits
    # feststehender künftiger Freizeitausgleich. None, wenn kein künftiger
    # Freizeitausgleich existiert (Admin-Spalte zeigt dann „—").
    future_comp_hours: float = 0.0
    projected_year_end_overtime: Optional[float] = None
    vacation_used_hours: float
    vacation_used_days: float   # Tagesprinzip: Stunden ÷ Tagessoll (für die Anzeige)
    sick_hours: float
    sick_days: float            # 0 ohne include_health_data (DSGVO Art. 9)
    exempt_from_arbzg: bool = False  # #159: leitende Angestellte (§18) — Filter im Dashboard-Schnitt
    track_hours: bool = True    # Finding 14: #191-untracked MA aus "Ø Saldo" ausschließbar
    # #415: Stundenänderungen INNERHALB des Berichtsmonats. `weekly_hours` oben ist
    # der zum Monatsbeginn gültige Wert; ohne diese Liste zeigt die UI eine
    # Wochenstundenzahl, die für den halben Monat nicht galt.
    weekly_hours_changes: List["WeeklyHoursChangeInPeriod"] = []


class PublicHolidayResponse(BaseModel):
    """Public holiday response."""
    model_config = ConfigDict(from_attributes=True)

    date: date
    name: str
    year: int


class MissingBookingEntry(BaseModel):
    """A single missing or incomplete booking."""
    date: date
    type: str  # "open" (end_time NULL) or "missing" (no entry on workday)
    start_time: Optional[str] = None  # For open entries

class MissingBookings(BaseModel):
    """Missing bookings for a single user."""
    user_id: str
    first_name: str
    last_name: str
    entries: List[MissingBookingEntry]

class EmployeeYearlyAbsences(BaseModel):
    """Yearly absence summary for a single employee."""
    user_id: str
    first_name: str
    last_name: str
    vacation_days: float
    remaining_vacation_days: float
    sick_days: float
    training_days: float
    overtime_comp_days: float = 0.0
    other_days: float
    paid_leave_days: float = 0.0
    overtime_year: float
    total_days: float
