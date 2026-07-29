"""#431: working_hours_changes wird ein vollstaendiger Vertrags-Snapshot

Mitarbeitende mit individuellem Tagesplan hatten bisher keine Stundenhistorie —
ihr Tagessoll kam live aus users.hours_monday…friday, jede Aenderung verschob
still das Soll der gesamten Vergangenheit. Die Historien-Zeile traegt jetzt
Modus, Tageswerte und Arbeitstage mit.

Backfill: jede BESTEHENDE Zeile bekommt den heutigen Zustand ihres Users. Damit
bleibt das Verhalten nach der Migration byte-identisch — insbesondere im
Mischfall (Tagesplan-MA mit Alt-Zeilen aus der Zeit davor: diese Zeilen sind
heute wirkungslos und wuerden ohne Backfill schlagartig als gleichmaessige
Zeilen scharf geschaltet).

Im Tagesplan-Modus wird dabei AUCH ``weekly_hours`` auf die Summe der
uebernommenen Tageswerte gezogen. Ohne das behielte die Alt-Zeile ihren
historischen Skalar neben einem fremden Tagesplan — eine Zeile, die sich selbst
widerspricht. Sichtbar wurde das in den #415-Berichtskoepfen: eine Mitarbeiterin
mit der Alt-Zeile ``2026-03-15 → 30 h``, spaeter auf Mo 8 / Di 5 / Mi 4
umgestellt, bekam den Satz „ab 15.03.2026: Mo 8,0 / Di 5,0 / Mi 4,0 =
30,0 h/Woche" — die genannten Tage summieren sich auf 17. Zwei solche Alt-Zeilen
verschmolzen zusaetzlich NICHT (ihre Skalare unterscheiden sich), der Bericht
behauptete also eine Planaenderung, die es nie gab. Fuer diese Gruppe treibt der
Skalar keine Berechnung — das Tagessoll kommt aus den Tageswerten
(``get_daily_target_for_date``) —, er ist reine Anzeige, und die soll stimmen.
Zeilen mit leerem Tagesplan (Summe 0) bleiben unangetastet: dort faellt die
Darstellung auf den Skalar zurueck, der dann der einzige verbliebene Beleg ist.

KEIN neuer Index: der Resolver-Zugriff (juengste Zeile eines Users bis zu einem
Datum, ``ORDER BY effective_from DESC LIMIT 1``) laeuft ueber
``(user_id, effective_from)`` — genau diese Spaltenkombination deckt
``ix_wh_changes_user_effective_from`` aus Migration 031 bereits ab. Ein zweiter,
deckungsgleicher Index kostet Schreiblast und Platz, ohne je gewaehlt zu werden.
"""
from alembic import op
import sqlalchemy as sa

revision = "067_schedule_history"
down_revision = "066_vacation_days_decimal"
branch_labels = None
depends_on = None


def upgrade():
    # weekly_hours ist im Tagesplan-Modus die ABGELEITETE Summe der fuenf
    # Tageswerte (je Numeric(4,2)). Mit nur einer Nachkommastelle rundete
    # Postgres 8,25 + 5,00 + 4,50 = 17,75 auf 17,8 — der gespeicherte Wert
    # widerspraeche damit den Tageswerten derselben Zeile. Bestehende Werte
    # sind API-seitig seit jeher auf 0..60 begrenzt und passen unveraendert in
    # numeric(4,2); die Verbreiterung der Skala ist verlustfrei.
    op.alter_column(
        "working_hours_changes", "weekly_hours",
        existing_type=sa.Numeric(4, 1), type_=sa.Numeric(4, 2),
        existing_nullable=False,
    )
    op.add_column("working_hours_changes", sa.Column(
        "use_daily_schedule", sa.Boolean(), nullable=False, server_default="false"))
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        op.add_column("working_hours_changes", sa.Column(
            f"hours_{day}", sa.Numeric(4, 2), nullable=True))
    op.add_column("working_hours_changes", sa.Column(
        "work_days_per_week", sa.Integer(), nullable=True))

    # Backfill aus der zugehoerigen User-Zeile.
    #
    # `weekly_hours` wird NUR im Tagesplan-Modus und NUR bei einer Summe > 0
    # ueberschrieben (siehe Modul-Docstring): sonst stuende der historische
    # Skalar neben einem fremden Tagesplan und die #415-Kopfzeile widerspraeche
    # den Tageswerten derselben Zeile. Im gleichmaessigen Modus bleibt der Wert
    # unangetastet — dort treibt er das Tagessoll.
    op.execute("""
        UPDATE working_hours_changes AS w
        SET use_daily_schedule = u.use_daily_schedule,
            hours_monday = CASE WHEN u.use_daily_schedule THEN u.hours_monday END,
            hours_tuesday = CASE WHEN u.use_daily_schedule THEN u.hours_tuesday END,
            hours_wednesday = CASE WHEN u.use_daily_schedule THEN u.hours_wednesday END,
            hours_thursday = CASE WHEN u.use_daily_schedule THEN u.hours_thursday END,
            hours_friday = CASE WHEN u.use_daily_schedule THEN u.hours_friday END,
            work_days_per_week = u.work_days_per_week,
            weekly_hours = CASE
                WHEN u.use_daily_schedule
                 AND (COALESCE(u.hours_monday, 0) + COALESCE(u.hours_tuesday, 0)
                    + COALESCE(u.hours_wednesday, 0) + COALESCE(u.hours_thursday, 0)
                    + COALESCE(u.hours_friday, 0)) > 0
                THEN (COALESCE(u.hours_monday, 0) + COALESCE(u.hours_tuesday, 0)
                    + COALESCE(u.hours_wednesday, 0) + COALESCE(u.hours_thursday, 0)
                    + COALESCE(u.hours_friday, 0))
                ELSE w.weekly_hours
            END
        FROM users AS u
        WHERE w.user_id = u.id
    """)


def downgrade():
    """NICHT verlustfrei — und das laesst sich nicht reparieren.

    Der ``upgrade`` ueberschreibt ``weekly_hours`` von Tagesplan-Zeilen mit der
    Summe ihrer Tageswerte. Der alte Skalar ist danach nirgends mehr abgelegt
    (die Spalte ist die einzige Quelle), ein ``downgrade`` kann ihn also nicht
    rekonstruieren. Fuer diese Zeilen war er im Alt-Modell allerdings ohnehin
    wirkungslos: das Tagessoll kam schon vor #431 aus ``users.hours_monday…friday``.
    Wer den Vorzustand exakt braucht, spielt ein Backup ein.
    """
    op.drop_column("working_hours_changes", "work_days_per_week")
    for day in ("friday", "thursday", "wednesday", "tuesday", "monday"):
        op.drop_column("working_hours_changes", f"hours_{day}")
    op.drop_column("working_hours_changes", "use_daily_schedule")
    # Zurueck auf eine Nachkommastelle. Krumme Summen (17,75) runden dabei auf
    # 17,8 — ohne die Tageswerte gibt es sie im Alt-Modell ohnehin nicht.
    op.alter_column(
        "working_hours_changes", "weekly_hours",
        existing_type=sa.Numeric(4, 2), type_=sa.Numeric(4, 1),
        existing_nullable=False,
    )
