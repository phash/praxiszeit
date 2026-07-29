from sqlalchemy import Column, Date, Time, Text, DateTime, Numeric, ForeignKey, Enum, UniqueConstraint, Boolean, String, Integer, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from app.database import Base


class AbsenceType(str, enum.Enum):
    """Absence type enumeration.

    Business rules (enforced in calculation_service.get_monthly_target /
    get_monthly_actual — any change here also needs a change there):

    - VACATION:  reduces monthly TARGET, adds 0 to ACTUAL. Decreases the
                 vacation budget. Net effect on overtime balance: 0.
    - SICK:      neutral to TARGET (§3 EntgFG — credited as if worked).
                 Adds the planned hours to ACTUAL. No effect on balance.
    - TRAINING:  same as SICK — treated as worked time (außer Haus).
    - OVERTIME:  Überstundenausgleich. TARGET stays as on a normal workday,
                 ACTUAL is 0, so the balance drops by one day's target —
                 which is exactly the intended "cash-out" of overtime.
    - OTHER:     UNPAID leave / Sonderurlaub-ohne-Bezug. Reduces TARGET
                 AND adds 0 to ACTUAL (no effect on balance, hours drop
                 out of both sides). Explicitly NOT paid leave. If you
                 need paid "Sonderurlaub", use VACATION and track the
                 reason in the note field.
    - PAID_LEAVE: PAID Freistellung (e.g. Betriebsferien als bezahlte
                 Freistellung statt Urlaub, #145). Rechen-mechanik is
                 IDENTICAL to OTHER — reduces TARGET, adds 0 to ACTUAL,
                 balance-neutral, and crucially does NOT deduct the
                 vacation budget (get_vacation_account sums only VACATION).
                 The difference to OTHER is purely the reporting category:
                 PAID_LEAVE is a PAID, own-category leave, whereas OTHER is
                 explicitly UNPAID. Both fall through the
                 ``notin_([TRAINING, SICK, OVERTIME])`` filter in
                 calculation_service, so PAID_LEAVE is handled the same way
                 as OTHER without an explicit branch.
    """
    VACATION = "vacation"
    SICK = "sick"
    TRAINING = "training"
    OVERTIME = "overtime"
    OTHER = "other"
    PAID_LEAVE = "paid_leave"


class AbsenceReasonBehavior(str, enum.Enum):
    """#312: how a custom absence reason behaves in the Soll/Ist calculation.

    Each value maps to an EXISTING ``AbsenceType`` so the audited calculation
    model stays frozen — a custom reason is only a label+colour overlay; the
    Absence keeps a built-in ``type`` (driven by this behaviour) that the calc
    runs on. See ``BEHAVIOR_TO_ABSENCE_TYPE``.
    """
    WORKED = "worked"            # zählt als gearbeitet (wie Fortbildung, §3) → z. B. Schule/Azubi
    PAID_FREE = "paid_free"      # bezahlt frei (wie PAID_LEAVE: Soll→0, saldo-neutral, kein Urlaub)
    OVERTIME_COMP = "overtime_comp"  # Überstundenabbau (wie OVERTIME)
    UNPAID_FREE = "unpaid_free"  # #376 entschuldigt UNBEZAHLT (Kind krank, unbez. Sonderurlaub) → OTHER


# #312: the single source of truth mapping a reason behaviour to the built-in
# AbsenceType that drives the calculation. Changing a mapping changes calc
# semantics — keep in sync with the AbsenceType business rules above.
BEHAVIOR_TO_ABSENCE_TYPE = {
    AbsenceReasonBehavior.WORKED: AbsenceType.TRAINING,
    AbsenceReasonBehavior.PAID_FREE: AbsenceType.PAID_LEAVE,
    AbsenceReasonBehavior.OVERTIME_COMP: AbsenceType.OVERTIME,
    AbsenceReasonBehavior.UNPAID_FREE: AbsenceType.OTHER,  # #376
}


class AbsenceReason(Base):
    """#312: tenant-defined custom absence reason (free text + colour + behaviour).

    Admins create/rename these in Settings. An Absence may reference one via
    ``reason_id`` for its display label/colour; the absence's ``type`` is set
    from ``base_behavior`` so the calculation is unchanged.
    """

    __tablename__ = "absence_reasons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    color = Column(String(7), nullable=True)  # #RRGGBB
    base_behavior = Column(String(20), nullable=False)  # AbsenceReasonBehavior value
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    # #376: markiert DEN Kind-krank-Grund → zählt gegen das §45-SGB-V-Jahreslimit.
    # Generisch (v1 nur von "Kind krank" genutzt); nur ein Label-Flag, die
    # Calc-Mechanik kommt allein aus base_behavior/type.
    tracks_child_sick_limit = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_absence_reason_tenant_name"),
    )

    def __repr__(self):
        return f"<AbsenceReason(id={self.id}, name={self.name}, behavior={self.base_behavior})>"


class Absence(Base):
    """Absence model for tracking vacation, sick days, etc."""

    __tablename__ = "absences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)  # Start date (or single day if end_date is NULL)
    end_date = Column(Date, nullable=True, index=True)  # End date for date ranges (NULL for single day)
    type = Column(Enum(AbsenceType), nullable=False)
    hours = Column(Numeric(4, 2), nullable=False)  # Hours absent per day
    # Task 15: der beim BUCHEN festgeschriebene Stundenwert — die
    # Rueckversicherung gegen eine falsche Rueckrechnung, im selben Geist wie
    # ``TimeEntry.raw_start_time``/``raw_end_time`` (#201): dort bleiben die
    # Rohstempel erhalten, gekappt wird nur der gerechnete Wert.
    #
    # Die Regel, an der alles haengt:
    #
    # * ``calculation_service.retarget_absence_hours`` ist der EINZIGE Schreiber
    #   von ``hours``, der ``raw_hours`` NICHT anfasst. Nur so bleibt der
    #   Ursprungszustand rekonstruierbar, egal wie oft nachgerechnet wurde.
    # * Jeder andere Schreiber (Neu-Buchung, menschliche Korrektur,
    #   Aenderungsantrag-Genehmigung) setzt beide Werte gleich — dort IST der
    #   neue Wert der gebuchte.
    # * Beim Anlegen erledigt das der ``before_insert``-Listener unten, damit
    #   die vielen Buchungspfade (Direkt-Buchung, Antrags-Genehmigung,
    #   CR-Genehmigung, Betriebsferien, Re-Split, Import …) und auch kuenftige
    #   automatisch mitgedeckt sind.
    # * Es gibt BEWUSST KEINEN ``before_update``-Listener: der wuerde die
    #   Rueckrechnung mitnehmen und das Feld genau dann entwerten, wenn man es
    #   braucht.
    #
    # ``raw_hours`` fliesst in KEINE Berechnung ein (Soll/Ist/Urlaub bleiben
    # unveraendert) — es ist reine Rueckversicherung. Nullable: vor der
    # Migration 068 geschriebene Rows haetten sonst keinen Wert; die Migration
    # backfillt sie mit ``hours`` (der bestmoegliche bekannte Ursprungswert).
    raw_hours = Column(Numeric(4, 2), nullable=True)
    start_time = Column(Time, nullable=True)  # NULL = ganzer Tag
    end_time = Column(Time, nullable=True)    # NULL = ganzer Tag
    # #205: halber Urlaubstag (0,5). NULLABLE — vor #205 geschriebene Rows sind
    # NULL und werden im Urlaubsverbrauch mit der Legacy-Stundenlogik gezaehlt;
    # neue Rows tragen True/False und werden tagebasiert gezaehlt.
    half_day = Column(Boolean, nullable=True)
    note = Column(Text, nullable=True)
    # Link to the CompanyClosure (Betriebsferien) that generated this absence.
    # NULL for manually created absences. ON DELETE SET NULL — the closure
    # router deletes linked absences explicitly (tenant-scoped); this guards
    # against orphaned FK references if a closure is removed by other means.
    closure_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_closures.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # #312: optional custom absence reason (label + colour overlay). The absence
    # ``type`` still drives ALL calculation; reason_id only carries the display
    # label/colour. ON DELETE SET NULL — deleting a reason keeps the absence (it
    # falls back to its base-type label).
    reason_id = Column(
        UUID(as_uuid=True),
        ForeignKey("absence_reasons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'user_id', 'date', 'type', name='uq_tenant_user_date_type'),
    )

    def __repr__(self):
        return f"<Absence(id={self.id}, user_id={self.user_id}, date={self.date}, type={self.type}, hours={self.hours})>"


@event.listens_for(Absence, "before_insert")
def _absence_set_raw_hours(mapper, connection, target):
    """Task 15: beim Anlegen ``raw_hours`` aus ``hours`` uebernehmen.

    Zentral hier statt an den Buchungspfaden (``absences.create_absence``,
    ``admin_vacations.review_vacation_request``,
    ``admin_change_requests.review_change_request``,
    ``company_closures._create_closure_absences``, XLS-Import …): ein Listener
    deckt alle ab, auch kuenftige. Muster: der ``before_insert``-Hook auf
    ``TimeEntryAuditLog`` (#121).

    Ein explizit gesetzter Wert bleibt stehen — der Listener ergaenzt nur, was
    fehlt. Ein ``before_update``-Gegenstueck gibt es BEWUSST nicht (siehe den
    Kommentar an der Spalte).
    """
    if target.raw_hours is None:
        target.raw_hours = target.hours
