from datetime import date, datetime, timedelta
from app.services.timezone_service import today_local
from app.services.date_filters import date_in_year, date_in_month, date_in_range
from decimal import Decimal
from calendar import monthrange
from typing import Any, Dict, List, NamedTuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from app.models import User, TimeEntry, Absence, AbsenceReason, PublicHoliday, AbsenceType, WorkingHoursChange, YearCarryover
from app.services import special_days_service, settings_service


class Schedule(NamedTuple):
    """#431: der vollstaendige Vertrags-Snapshot fuer EIN Datum.

    Aufgeloest aus der jeweils juengsten ``WorkingHoursChange`` mit
    ``effective_from <= target_date``; gibt es keine, aus den aktuellen
    User-Feldern (der Rueckfallwert fuer die Zeit vor der ersten erfassten
    Aenderung — dieselbe Semantik wie ``user.weekly_hours`` seit #415).
    """

    weekly_hours: Decimal
    use_daily_schedule: bool
    day_hours: tuple          # (Mo, Di, Mi, Do, Fr), je Optional[Decimal]
    work_days_per_week: int


def _latest_change(
    db: Session,
    user: User,
    target_date: date,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> Optional[WorkingHoursChange]:
    """Juengste Aenderung mit ``effective_from <= target_date``. Query-Pfad und
    In-Memory-Pfad mit identischer Semantik (``ORDER BY effective_from DESC
    LIMIT 1``)."""
    if wh_changes is None:
        return db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user.id,
            WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
            WorkingHoursChange.effective_from <= target_date,
        ).order_by(WorkingHoursChange.effective_from.desc()).first()
    change = None
    for c in wh_changes:
        if c.effective_from <= target_date and (
            change is None or c.effective_from > change.effective_from
        ):
            change = c
    return change


def _dec_or_none(value) -> Optional[Decimal]:
    return None if value is None else Decimal(str(value))


def get_schedule_for_date(
    db: Session,
    user: User,
    target_date: date,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> Schedule:
    """#431: DIE eine Aufloesung des Vertragszustands zu einem Datum.

    Vor #431 war nur ``weekly_hours`` historisiert; Modus, Tageswerte und
    Arbeitstage kamen live von der User-Zeile — jede Aenderung verschob damit
    still das Soll der gesamten Vergangenheit. Alle vier Werte stecken jetzt in
    derselben Snapshot-Zeile, deshalb genuegt EIN Lookup (und der bereits
    vorhandene ``wh_changes``-Preload der Hot-Loops).
    """
    change = _latest_change(db, user, target_date, wh_changes)
    if change is not None:
        return Schedule(
            weekly_hours=Decimal(str(change.weekly_hours)),
            use_daily_schedule=bool(change.use_daily_schedule),
            day_hours=(
                _dec_or_none(change.hours_monday),
                _dec_or_none(change.hours_tuesday),
                _dec_or_none(change.hours_wednesday),
                _dec_or_none(change.hours_thursday),
                _dec_or_none(change.hours_friday),
            ),
            work_days_per_week=int(
                change.work_days_per_week
                if change.work_days_per_week is not None
                else user.work_days_per_week
            ),
        )
    # Kein Eintrag → aktuelle User-Felder. Dies ist die EINZIGE Stelle im Code,
    # die user.weekly_hours / user.hours_* / user.work_days_per_week direkt
    # lesen darf.
    return Schedule(
        weekly_hours=Decimal(str(user.weekly_hours)),
        use_daily_schedule=bool(getattr(user, 'use_daily_schedule', False)),
        day_hours=(
            _dec_or_none(user.hours_monday),
            _dec_or_none(user.hours_tuesday),
            _dec_or_none(user.hours_wednesday),
            _dec_or_none(user.hours_thursday),
            _dec_or_none(user.hours_friday),
        ),
        work_days_per_week=int(user.work_days_per_week),
    )


def get_weekly_hours_for_date(
    db: Session,
    user: User,
    target_date: date,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> Decimal:
    """
    Get the weekly hours that were valid for a specific date.
    Considers historical working hours changes.

    This is the SINGLE authoritative lookup — other call-sites must NEVER
    read ``user.weekly_hours`` directly (CLAUDE.md rule). Hot-path callers
    that need many lookups per request may pass a pre-loaded ``wh_changes``
    list to avoid one SELECT per day; the change-search is then performed
    in memory with identical semantics.

    Args:
        db: Database session (unused when wh_changes is provided)
        user: User object
        target_date: Date to get hours for
        wh_changes: Optional pre-loaded list of WorkingHoursChange for this
            user. When supplied, no DB query is issued. Must be filtered to
            ``user_id == user.id`` by the caller — this function does not
            re-filter.

    Returns:
        Weekly hours as Decimal

    #431: thin wrapper around ``get_schedule_for_date`` — the resolver above
    is now the single place that reads ``user.weekly_hours`` directly.
    """
    return get_schedule_for_date(db, user, target_date, wh_changes).weekly_hours


class ScheduleSegment(NamedTuple):
    """#415/#431: ein zusammenhaengender Zeitraum KONSTANTEN Vertragszustands.

    Bis #431 war das ein 3er-Tupel ``(von, bis, wochenstunden)``. Fuer
    Mitarbeitende mit individuellem Tagesplan sagte das nichts Brauchbares:
    ``weekly_hours`` ist dort nur die Summe der fuenf Tageswerte und steuert kein
    einziges Tagessoll — die sechs §16-Flaechen zeigten eine Zahl ohne Bezug zu
    ihren eigenen Soll-Spalten. Und zwei Zeilen mit gleicher Wochensumme, aber
    verschobenem Tagesplan (Mo 8/Di 5/Mi 4 → Mo 4/Di 5/Mi 8) verschmolzen zu
    EINEM Segment: der Bericht behauptete „keine Aenderung", obwohl sich jedes
    Tagessoll verschoben hatte.

    ``day_hours`` ist im gleichmaessigen Modus IMMER ``(None,) * 5``, auch wenn
    die Zeile Reste traegt: ``get_daily_target_for_date`` liest die Tageswerte
    dort gar nicht, und ``update_user`` raeumt sie beim Abschalten des Tagesplans
    nicht ab. Solche inerten Reste duerfen weder eine Pseudo-Aenderung erzeugen
    noch in einem Bericht auftauchen — dieselbe Maskierung wie in
    ``admin_users._comparable_snapshot``.
    """

    start: date
    end: date
    weekly_hours: Decimal
    use_daily_schedule: bool
    day_hours: tuple          # (Mo, Di, Mi, Do, Fr), je Optional[Decimal]
    work_days_per_week: int


def weekly_hours_segments(
    db: Session,
    user: User,
    start: date,
    end: date,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> List[ScheduleSegment]:
    """#415: die Vertragshistorie eines Zeitraums als zusammenhaengende
    :class:`ScheduleSegment`, lueckenlos ueber ``[start, end]``.

    DIE eine Quelle fuer die Darstellung von Stundenaenderungen in Berichten und
    Exporten. Vorher zeigten die Kopfzeilen/Spalten „Wochenstunden" den
    AKTUELLEN Vertragswert (``user.weekly_hours``), waehrend die Tageszeilen
    darunter historisch korrekt ueber ``get_weekly_hours_for_date`` rechneten —
    ein in sich widerspruechlicher §16-Beleg.

    Semantik:

    * Aenderungen VOR ``start`` gelten fuer den gesamten Zeitraum (ein Segment).
    * Aenderungen NACH ``end`` sind unsichtbar.
    * Eine Aenderung, die am Vertragszustand nichts aendert, erzeugt KEIN neues
      Segment — sie ist im Bericht keine sichtbare Aenderung.
    * ``start > end`` → ``[]``.

    Verglichen wird der VOLLSTAENDIGE Snapshot (Wochenstunden, Modus, Tageswerte,
    Arbeitstage), nicht mehr nur ``weekly_hours``: sonst bliebe genau der
    Tagesplan-Fall unsichtbar, fuer den #431 die Historie ueberhaupt erweitert
    hat (gleiche Wochensumme, anderes Tagessoll).

    Die Werte kommen ausschliesslich aus ``get_schedule_for_date``, damit
    Darstellung und Berechnung nie auseinanderlaufen koennen. ``wh_changes`` ist
    der Preload fuer Hot-Loops (identische Semantik, keine Query) und muss — wie
    dort — bereits auf diesen User gefiltert sein.
    """
    if start > end:
        return []

    if wh_changes is None:
        wh_changes = (
            db.query(WorkingHoursChange)
            .filter(
                WorkingHoursChange.user_id == user.id,
                WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
            )
            .order_by(WorkingHoursChange.effective_from)
            .all()
        )

    boundaries = [start]
    for change in sorted(wh_changes, key=lambda c: c.effective_from):
        if start < change.effective_from <= end and change.effective_from not in boundaries:
            boundaries.append(change.effective_from)

    segments: List[ScheduleSegment] = []
    for i, boundary in enumerate(boundaries):
        seg_end = boundaries[i + 1] - timedelta(days=1) if i + 1 < len(boundaries) else end
        schedule = get_schedule_for_date(db, user, boundary, wh_changes=wh_changes)
        segment = ScheduleSegment(
            start=boundary,
            end=seg_end,
            weekly_hours=schedule.weekly_hours,
            use_daily_schedule=schedule.use_daily_schedule,
            day_hours=schedule.day_hours if schedule.use_daily_schedule else (None,) * 5,
            work_days_per_week=schedule.work_days_per_week,
        )
        # Ab Feld 2 stehen genau die Snapshot-Werte — der Vergleich deckt damit
        # automatisch jedes kuenftige Feld mit ab.
        if segments and segments[-1][2:] == segment[2:]:
            segments[-1] = segments[-1]._replace(end=seg_end)
        else:
            segments.append(segment)
    return segments


def work_days_changed(previous, segment) -> bool:
    """#431: Aendert dieses Segment die ARBEITSTAGE gegenueber dem
    vorhergehenden?

    DIE eine Definition dieser Frage — genutzt vom Datei-Export
    (``export_service._format_segment_change``) und vom API-Schema
    (``schemas.reports.WeeklyHoursChangeInPeriod.from_segment``, das den Befund
    als ``work_days_changed`` an den Frontend-Zwilling weiterreicht). Der
    Bildschirm sieht nur die Aenderungen (``segments[1:]``), nicht das
    Basissegment davor — ohne diesen mitgelieferten Befund koennte er die Frage
    fuer die ERSTE Aenderung eines Zeitraums gar nicht beantworten und muesste
    einen anderen Satz schreiben als die Datei.

    Hintergrund: ``weekly_hours_segments`` splittet auf dem VOLLSTAENDIGEN
    Snapshot, die #415-Formulierung des gleichmaessigen Modus nennt aber nur die
    Wochenstunden. Ein Wechsel „40 h auf 5 Tage" → „40 h auf 4 Tage" erzeugte so
    eine Aenderungszeile, die zeichengleich zur Kopfzeile war — waehrend das
    Tagessoll derselben Tageszeilen von 8,00 h auf 10,00 h sprang.

    ``previous is None`` (das erste Segment, oder eine Altantwort ohne Vorgaenger)
    → ``False``: ohne Vergleichspunkt wird nichts behauptet.
    """
    if previous is None:
        return False
    before = getattr(previous, "work_days_per_week", None)
    after = getattr(segment, "work_days_per_week", None)
    if before is None or after is None:
        return False
    return int(before) != int(after)


class RetargetWindow(NamedTuple):
    """Der WIRKUNGSBEREICH einer ``WorkingHoursChange`` — siehe
    ``retarget_window``."""

    start: date
    """``effective_from`` der betrachteten Aenderung."""

    end: date
    """Letzter Tag des Wirkungsbereichs (immer konkret, nie offen)."""

    last_absence: Optional[date]
    """Spaetestes Abwesenheitsdatum im Bereich; ``None`` = keine vorhanden."""

    @property
    def has_absences(self) -> bool:
        """Der AUSLOESER fuer das Nachziehen: gibt es ueberhaupt eine bereits
        gebuchte Abwesenheit im Wirkungsbereich? (NICHT „liegt das Datum in der
        Vergangenheit" — siehe ``retarget_window``.)"""
        return self.last_absence is not None


def retarget_window(db: Session, user: User, effective_from: date) -> RetargetWindow:
    """Bestimmt den Wirkungsbereich einer ``WorkingHoursChange`` zum
    ``effective_from``: ab diesem Tag bis zum Tag VOR der naechsten Aenderung
    mit groesserem ``effective_from`` — gibt es keine, ist der Bereich offen und
    wird praktisch auf die spaeteste bereits gebuchte Abwesenheit (mindestens
    aber heute bzw. das Wirkungsdatum selbst) begrenzt.

    DIE eine Stelle, die dieses Fenster kennt — Anlegen, Loeschen und Vorschau
    fragen alle hier (Release-Review 1.17.0; vorher klemmte jeder Aufrufer das
    Fenster selbst auf ``[effective_from, heute]``).

    Warum NICHT „bis heute": ``create_absence`` hat keinerlei Zukunftssperre.
    Genehmigte Urlaubsantraege, Betriebsferien und geplante Fortbildungen werden
    routinemaessig im Voraus gebucht — mit ``hours`` = Tagessoll ZUM
    Buchungszeitpunkt. Das Soll dieser Tage folgt einer spaeteren
    Wochenstunden-Aenderung datumsbasiert automatisch, die gespeicherten Stunden
    nicht. Bei ``SICK``/``TRAINING`` ist das ein direkter Saldo-Fehler (die
    ``hours`` sind dort die Ist-Gutschrift), bei ``VACATION``/``PAID_LEAVE``/
    ``OTHER`` ein in sich widerspruechlicher §16-Beleg. Und der REGELFALL des
    Dialogs ist ein Wirkungsdatum in der ZUKUNFT („ab dem 1.9. arbeitet sie 20
    Stunden") — dort griffe ein „nur rueckwirkend"-Trigger nie.

    Warum die Obergrenze an der naechsten Aenderung: was danach liegt, gehoert
    bereits einem anderen Vertragswert. Diese Zeile darf es nicht mit
    umschreiben.

    ``OVERTIME`` bleibt bei der Abwesenheits-Suche aussen vor — genau wie in
    ``retarget_absence_hours``, damit der Ausloeser nicht fuer Zeilen feuert,
    die ohnehin nie angefasst wuerden.
    """
    next_change = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
        WorkingHoursChange.effective_from > effective_from,
    ).order_by(WorkingHoursChange.effective_from.asc()).first()
    hard_end = (next_change.effective_from - timedelta(days=1)) if next_change else None

    absence_q = db.query(func.max(Absence.date)).filter(
        Absence.user_id == user.id,
        Absence.tenant_id == user.tenant_id,  # F-026
        Absence.date >= effective_from,
        Absence.type != AbsenceType.OVERTIME,
    )
    if hard_end is not None:
        absence_q = absence_q.filter(Absence.date <= hard_end)
    last_absence = absence_q.scalar()

    if hard_end is not None:
        end = hard_end
    else:
        # Offener Bereich: praktisch bis zur spaetesten gebuchten Abwesenheit —
        # weiter zu laufen brauechte niemand. Mindestens bis heute (bzw. bis zum
        # Wirkungsdatum, wenn das in der Zukunft liegt), damit das Fenster auch
        # ohne Abwesenheiten einen sinnvollen Anzeigewert hat.
        end = max(d for d in (effective_from, today_local(), last_absence) if d is not None)

    return RetargetWindow(start=effective_from, end=end, last_absence=last_absence)


class AbsenceRetarget(NamedTuple):
    """Task 15: EINE tatsaechlich nachgezogene Abwesenheit.

    ``retarget_absence_hours`` gab frueher nur die ANZAHL zurueck — welche Zeile
    von welchem Wert auf welchen ging, wusste danach niemand mehr, obwohl genau
    das der Weg zurueck ist, wenn sich eine Berechnung als falsch herausstellt.
    Der Aufrufer schreibt daraus das Einzelprotokoll (die Audit-Zeilen gehoeren
    in den Router, nicht hierher: die Vorschau ruft dieselbe Funktion und rollt
    danach zurueck — sie darf nichts protokollieren).

    ``absence_type`` ist mit dabei, damit der Router das deutsche Klartext-Label
    bilden kann, ohne die eben gelesenen Zeilen ein zweites Mal zu holen.
    """

    absence_id: Any           # UUID (auf SQLite ggf. str — nie selbst parsen)
    date: date
    old_hours: Decimal
    new_hours: Decimal
    absence_type: AbsenceType


def retarget_absence_hours(
    db: Session,
    user: User,
    start: date,
    end: date,
    *,
    dry_run: bool = False,
) -> List[AbsenceRetarget]:
    """Setzt ``Absence.hours`` im Fenster ``[start, end]`` auf das Tagessoll des
    jeweiligen Tages. Gibt die tatsaechlich abweichenden Zeilen zurueck (die
    frueher zurueckgegebene Anzahl ist ``len(...)``).
    Das Fenster liefert ``retarget_window`` (DIE eine Stelle dafuer).

    Warum es das braucht: das SOLL rechnet datumsbasiert automatisch neu
    (``get_weekly_hours_for_date``), die beim Buchen festgeschriebenen ``hours``
    einer Abwesenheit tun das NICHT. Nach einer Wochenstunden-Aenderung von 40
    auf 20 h/Woche schriebe ein Krankentag weiterhin 8 h dem Ist gut, waehrend
    das Soll desselben Tages nur noch 4 h betraegt — Soll und Ist widersprechen
    sich dann im selben Monat und im selben §16-Beleg.

    Das gilt fuer rueckwirkende UND fuer zukunftsdatierte Aenderungen: bereits
    gebuchte kuenftige Abwesenheiten (genehmigter Urlaub, Betriebsferien,
    geplante Fortbildung) tragen die Stunden des alten Vertrags. Der Auf- und
    Abbau des Fensters gehoert deshalb ausschliesslich ``retarget_window``.

    Bewusst ausgenommen:

    * ``OVERTIME`` — Freizeitausgleich traegt explizit beantragte Stunden, kein
      abgeleitetes Tagessoll (CLAUDE.md: Soll bleibt, Ist = 0).
    * ``track_hours = False`` — dort zaehlt ausschliesslich die Tageszaehlung;
      die Stunden zu bewegen erzeugt nur Rauschen in den Belegen.
    * Wochenenden, Feiertage und Tage ohne Soll (freier Wochentag im Tagesplan)
      — sie werden uebersprungen, NICHT auf 0 gesetzt.
    * Tage ausserhalb des Beschaeftigungsfensters (#193).
    * ``half_day IS NULL`` (Legacy-Zeilen von vor #205) — siehe Begruendung in
      der Schleife.
    * #431: Tagesplan-Mitarbeitende sind NICHT mehr ausgenommen. Ihr Tagessoll
      kommt jetzt ebenfalls aus der Historien-Zeile; aendert eine Aenderung nur
      einen Wochentag, ueberspringt die Gleichheitspruefung die uebrigen Tage
      von selbst — es braucht keinen Wochentagsfilter.

    ``half_day`` halbiert, der #146/#394-Sondertagsfaktor (24./31.12.) wird
    angewandt. Die Abwesenheits-TAGE aendern sich dadurch nie — die sind
    tagebasiert (§3 BUrlG) und haengen nicht an ``hours``.

    ``Absence.raw_hours`` bleibt BEWUSST unberuehrt (Task 15): das ist der beim
    Buchen festgeschriebene Wert und damit die einzige Rueckversicherung, falls
    sich diese Rechnung als falsch herausstellt. Diese Funktion ist der einzige
    ``hours``-Schreiber, der ihn nicht mitzieht — jeder menschliche Schreiber
    setzt beide. Siehe den Kommentar an ``Absence.raw_hours``.

    ``dry_run=True`` ermittelt nur (fuer die Vorschau vor dem Speichern).

    DIE eine Stelle, die Abwesenheits-Stunden nachzieht — Anlegen, Loeschen und
    Vorschau rufen alle hier hinein.
    """
    if start > end or not user.track_hours:
        return []

    holidays = {
        h.date for h in db.query(PublicHoliday).filter(
            PublicHoliday.tenant_id == user.tenant_id,  # F-026
            PublicHoliday.date >= start,
            PublicHoliday.date <= end,
        ).all()
    }
    # Die Sondertags-Konfiguration wird hier NICHT geladen — siehe die
    # Begruendung an ``target`` in der Schleife (Fund A): der Faktor gehoert auf
    # die Leseseite, nicht in den gespeicherten Wert.
    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
    ).order_by(WorkingHoursChange.effective_from).all()

    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.tenant_id == user.tenant_id,  # F-026
        Absence.date >= start,
        Absence.date <= end,
        Absence.type != AbsenceType.OVERTIME,
    ).all()

    changed: List[AbsenceRetarget] = []
    for a in absences:
        d = a.date
        if d.weekday() >= 5 or d in holidays:
            continue
        if not _within_employment_window(user, d):
            continue
        # C1 (Abschluss-Review): Legacy-Zeilen ohne Halbtags-Information
        # (``half_day IS NULL``, gebucht vor #205) NIE anfassen. Genau fuer
        # diese Zeilen zaehlen ``get_vacation_account`` und ``absence_days``
        # die TAGE stundenbasiert (``hours / Tagessoll``) — ein Retarget auf
        # das volle Tagessoll wuerde also den Urlaubs-TAGE-Verbrauch
        # verschieben (ein Legacy-Halbtag: 0,5 -> 1,0) und dabei die einzige
        # verbliebene Spur davon, dass es ein halber Tag war (die ``hours``
        # selbst), unwiederbringlich ueberschreiben — auch das Loeschen der
        # Aenderung stellt sie nicht wieder her. Die tagebasierte Invariante
        # (§3 BUrlG) ist unantastbar; dieselbe Begruendung wie das bewusste
        # "kein unzuverlaessiges Raten" in ``get_vacation_account``.
        # Alle vier heutigen Buchungspfade setzen ``half_day`` explizit — es
        # entstehen keine neuen NULL-Zeilen, der Ausschluss laeuft aus.
        if a.half_day is None:
            continue

        schedule = get_schedule_for_date(db, user, d, wh_changes=wh_changes)
        # Audit 2026-07-31 (Fund A): BEWUSST das UNGEWICHTETE Tagessoll — der
        # #146/#394-Sondertagsfaktor (24./31.12.) gehoert NICHT in den
        # gespeicherten Wert. ``Absence.hours`` traegt in dieser Anwendung das
        # volle Tagessoll des Tages; der Faktor lebt auf der LESESEITE
        # (``_day_soll_contribution`` fuers Soll, :func:`credit_day_weight` fuers
        # Ist, :func:`half_special_day_weight` fuer die Urlaubstage) — genau so
        # buchen auch die beiden menschlichen Schreiber
        # (``absences.create_absence``, ``admin_change_requests``).
        #
        # Solange die Leseseite den Faktor nicht anwandte, war das Hineinrechnen
        # hier zufaellig richtig. Seit ``credit_day_weight`` (Fund K) ist es
        # doppelt: ein halber 24.12. mit Krankmeldung stand danach mit 2,00 Soll
        # gegen 1,00 Ist — ein stilles Defizit an einem Tag, der nach § 3 EntgFG
        # saldo-neutral sein MUSS. Verschaerfend wich der gespeicherte Wert am
        # Sondertag dadurch IMMER vom neu berechneten ab, sodass die
        # Gleichheitspruefung unten bei JEDEM Lauf ansprang (nicht idempotent).
        target = get_daily_target_for_date(user, d, schedule)
        if target <= 0:
            continue

        new_hours = (target / 2) if a.half_day else target
        new_hours = Decimal(str(new_hours)).quantize(Decimal('0.01'))
        old_hours = Decimal(str(a.hours)).quantize(Decimal('0.01'))
        if old_hours == new_hours:
            continue

        # KEINE stille Obergrenze (CLAUDE.md „no silent caps"): beruehrt ein
        # Vorgang viele Zeilen, stehen sie alle in der Liste — und damit alle im
        # Protokoll.
        changed.append(AbsenceRetarget(
            absence_id=a.id, date=d, old_hours=old_hours,
            new_hours=new_hours, absence_type=a.type,
        ))
        if not dry_run:
            # NUR ``hours``. ``raw_hours`` bleibt stehen — siehe Docstring.
            a.hours = float(new_hours)

    if changed and not dry_run:
        db.flush()
    return changed


def get_daily_target(user: User, weekly_hours: Decimal = None) -> Decimal:
    """
    Calculate daily target hours based on weekly hours and work days.

    Formula: weekly_hours / work_days_per_week

    Examples:
    - 20h at 2 days → 10h/day
    - 20h at 5 days → 4h/day
    - 40h at 5 days → 8h/day

    NOTE: Does NOT consider per-day schedule. Use get_daily_target_for_date()
    for date-aware calculations.

    #431: kennt keinen Tagesplan und keine Historie. Fuer alles Datumsbezogene
    ``get_daily_target_for_date`` mit ``get_schedule_for_date`` nutzen.

    Args:
        user: User object
        weekly_hours: Optional weekly hours to use (if None, uses user.weekly_hours)

    Returns:
        Daily target hours as Decimal (0 if track_hours is False)
    """
    if not user.track_hours:
        return Decimal('0')

    if weekly_hours is None:
        weekly_hours = Decimal(str(user.weekly_hours))

    # Use work_days_per_week instead of hardcoded 5
    work_days = Decimal(str(user.work_days_per_week))

    if work_days == 0:  # Safety check
        return Decimal('0')

    return (weekly_hours / work_days).quantize(Decimal('0.01'))


def get_daily_target_for_date(user: User, target_date: date, schedule: Schedule) -> Decimal:
    """Tagessoll fuer ein konkretes Datum aus dem aufgeloesten Vertrags-Snapshot.

    ``schedule`` ist PFLICHT (#431): frueher las der Tagesplan-Zweig live
    ``user.hours_monday…friday`` und verwarf dabei das datumsaufgeloeste
    ``weekly_hours`` — eine Historien-Zeile hatte fuer Tagesplan-Mitarbeitende
    also keinerlei Wirkung aufs Soll. Ohne Pflichtparameter bliebe eine
    uebersehene Call-Site lautlos auf dem AKTUELLEN Plan stehen und erzeugte ein
    halb-historisches §16-Dokument (Abwesenheitstage historisch gerechnet,
    regulaere Arbeitstage nicht). Den Snapshot liefert
    ``get_schedule_for_date`` — in Tagesschleifen mit dem vorhandenen
    ``wh_changes``-Preload.

    Wochenende ist immer 0; ``track_hours=False`` ebenfalls.
    """
    if not user.track_hours:
        return Decimal('0')

    weekday = target_date.weekday()  # 0=Mo, 4=Fr, 5=Sa, 6=So
    if weekday >= 5:
        return Decimal('0')

    if schedule.use_daily_schedule:
        day_hours = schedule.day_hours[weekday]
        if day_hours is None:
            return Decimal('0')
        return Decimal(str(day_hours)).quantize(Decimal('0.01'))

    work_days = Decimal(str(schedule.work_days_per_week))
    if work_days == 0:
        return Decimal('0')
    return (schedule.weekly_hours / work_days).quantize(Decimal('0.01'))


def is_vacation_billable_day(
    db: Session,
    user: User,
    target_date: date,
    schedule: Optional['Schedule'] = None,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> bool:
    """#431: zaehlt ``target_date`` in einer Urlaubs-VORPRUEFUNG als Urlaubstag?

    DIE eine Antwort fuer alle Budget-Vorpruefungen (Direkt-Buchung, Antrags-
    Genehmigung, Antrag anlegen/bearbeiten, CR-Genehmigung). Sie muss exakt das
    sagen, was die zugehoerige Buchungsschleife danach tut — laufen die beiden
    auseinander, lehnt der Check eine Buchung mit 400 ab, die nachher weniger
    Budget verbraucht haette (oder laesst eine durch, die mehr kostet).

    Der Modus wird zum DATUM aufgeloest, nicht von der User-Zeile gelesen: seit
    #431 ist ``use_daily_schedule`` Teil des historisierten Vertrags-Snapshots,
    die User-Zeile traegt nur den HEUTE gueltigen Wert. Eine rueckwirkende (oder
    zukunftsdatierte) Buchung in einen Zeitraum mit abweichendem Modus rechnete
    sonst mit dem falschen Zweig, waehrend der Filterwert daneben — das
    Tagessoll — laengst datumsaufgeloest war. Vor #431 konnten die beiden nie
    divergieren, deshalb war der Live-Zugriff damals korrekt.

    ``track_hours=False`` (leitende Angestellte, #191) zaehlt JEDEN Werktag:
    deren Tagessoll ist immer 0, tagebasiert kostet der Tag trotzdem 1 — sie
    duerfen hier nie mitgefiltert werden.

    Das #193-Beschaeftigungsfenster gehoert bewusst NICHT hierher, obwohl die
    Verbrauchs-Seite (``get_vacation_account``) es seit dem Audit 2026-07-31
    anwendet (Release-Review 1.18.1 geprueft): jeder der vier Aufrufer sperrt
    Tage ausserhalb des Fensters VORHER mit einer eigenen, praeziseren 400
    ("Datum liegt nach dem letzten Arbeitstag") — ``absences.create_absence``,
    ``admin_vacations.review_vacation_request`` und ``vacation_requests``
    ueber einen Bereichs-Guard auf Start/Ende, ``admin_change_requests`` ueber
    ``proposed_date``. Da das Fenster ein zusammenhaengender Zeitraum ist,
    folgt aus "ein Tag des Bereichs liegt draussen" zwingend "Start < Eintritt
    ODER Ende > Austritt"; ein solcher Tag erreicht diese Funktion also nie.
    Ein Filter hier waere tot und wuerde die Reihenfolge verschleiern.
    Faellt einer der Guards weg, muss er hier nachgezogen werden — festgenagelt
    in ``tests/test_vacation_precheck_employment_window.py``.
    """
    if not user.track_hours:
        return True
    if schedule is None:
        schedule = get_schedule_for_date(db, user, target_date, wh_changes=wh_changes)
    # Nur der Tagesplan kennt echte 0-Stunden-Werktage. Im gleichmaessigen Modus
    # traegt jeder Werktag weekly_hours/work_days_per_week > 0 — der Zweig ist
    # dort also wirkungslos, wird aber bewusst beibehalten (Byte-Identitaet).
    if not schedule.use_daily_schedule:
        return True
    return get_daily_target_for_date(user, target_date, schedule) > 0


def fixed_monthly_target(user: User, year: int, month: int) -> Decimal:
    """#377 Baustein 2b: festes Monats-Soll = agreed_monthly_hours, anteilig bei
    Eintritt/Austritt (Kalendertag-Bruchteil des Beschäftigungsfensters im Monat).
    Gibt 0, wenn der Modus aus ist oder agreed fehlt (Caller → wie Modus aus)."""
    agreed = getattr(user, "agreed_monthly_hours", None)
    if not getattr(user, "use_fixed_monthly_target", False) or not agreed or Decimal(str(agreed)) <= 0:
        return Decimal('0')
    agreed = Decimal(str(agreed))
    days_in_month = monthrange(year, month)[1]
    in_window = sum(
        1 for day in range(1, days_in_month + 1)
        if _within_employment_window(user, date(year, month, day))
    )
    if in_window == 0:
        return Decimal('0')
    if in_window == days_in_month:
        return agreed.quantize(Decimal('0.01'))
    return (agreed * Decimal(in_window) / Decimal(days_in_month)).quantize(Decimal('0.01'))


# #377 Baustein 2b: bezahlte Fehltag-Typen, die im Fix-Modus geplante Stunden dem
# Ist gutschreiben. SICK/TRAINING NICHT hier — die laufen über credited_absences
# (get_range_actual); erneut addieren wäre Doppelgutschrift.
_FIXED_PAID_CREDIT_TYPES = frozenset({AbsenceType.VACATION, AbsenceType.PAID_LEAVE})
# unbezahlt entschuldigt → mindert das feste Soll.
_FIXED_UNPAID_TYPES = frozenset({AbsenceType.OTHER})


def _fixed_planned_hours(
    db: Session, user: User, d: date, special_cfg: dict,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> Decimal:
    """Geplante Tagesstunden an ``d`` (0 an ungeplanten Tagen/Wochenende), inkl.
    #394-Sondertags-/Halbtags-Faktor. Nur im use_daily_schedule-Sinn sinnvoll.

    #431: der Plan wird zum Datum aufgeloest. Ohne das schriebe der Fix-Modus
    einem vergangenen Urlaubs-/Feiertag die HEUTIGEN Planstunden gut.
    ``wh_changes`` ist der optionale Preload der aufrufenden Tagesschleife."""
    schedule = get_schedule_for_date(db, user, d, wh_changes=wh_changes)
    planned = get_daily_target_for_date(user, d, schedule)
    if planned <= 0:
        return Decimal('0')
    return (planned * half_special_day_weight(d, special_cfg))


def fixed_day_covered_hours(planned: Decimal, day_absences, worked: Decimal,
                            is_holiday: bool) -> Decimal:
    """Die geplanten Stunden eines Tages, die ein bezahlter Fehltag abdeckt (#377 2b).

    DIE eine Quelle der Regel — genutzt von der Monatsschleife
    (:func:`_fixed_month_absence_hours`) UND von den Tageszeilen des
    Monatsjournals (#463). Ein zweiter Nachbau ist im Projekt schon mehrfach
    auseinandergelaufen; hier faellt das sofort auf, weil beide Zahlen im
    SELBEN Bildschirm nebeneinander stehen.

    ``day_absences`` sind die bereits gefilterten **ganztaegigen** Abwesenheiten
    der passenden Typen (``start_time IS NULL``). Halbtage decken 0,5 ab; mehr
    als ein voller Tag wird nie gutgeschrieben. ``worked`` (L1, Audit
    2026-07-31) geht zuerst gegen den NICHT abgedeckten Teil des Tages, nur der
    Ueberhang zehrt an der Gutschrift.
    """
    coverage = Decimal('1') if is_holiday else Decimal('0')
    for a in day_absences:
        coverage += Decimal('0.5') if a.half_day else Decimal('1')
    coverage = min(coverage, Decimal('1'))  # nie mehr als ein voller Tag
    if coverage <= 0:
        return Decimal('0')
    covered = planned * coverage
    if worked > 0:
        rest = max(Decimal('0'), worked - (planned - covered))
        covered = max(Decimal('0'), covered - rest)
    return covered


def _fixed_month_absence_hours(db, user, year, month, types, up_to_date, include_holidays,
                                from_date=None):
    """Gemeinsame Schleife: Σ geplante Stunden für Tage mit einem passenden
    ganztägigen Absence-Typ (bzw. Feiertag, wenn include_holidays), im Fenster,
    ≥ from_date (falls gesetzt) und ≤ up_to_date.

    L1 (Audit 2026-07-31): Ein TimeEntry am selben Tag ließ den Tag früher
    KOMPLETT ausfallen („reale Erfassung gewinnt"). Das feste Monats-Soll bleibt
    aber flach ``agreed_monthly_hours`` — wer an einem Feiertag zwei Stunden
    arbeitete, hatte am Monatsende WENIGER Ist als wer gar nicht arbeitete
    (2,00 statt 3,00 Planstunden), und das Phantom-Defizit zehrte im FIFO von
    ``milog_service.settlement_aging`` die älteste Einlage auf und unterdrückte
    ``MILOG_SETTLEMENT_DUE``. Erreichbar über den „+"-Knopf im Monatsjournal
    (``keep_time_entries``, seit 1.18.0 der Regelweg) UND über normales Stempeln
    an einem Feiertag/Urlaubstag (dort gibt es keinen Guard).

    Statt des Skips wird jetzt geklemmt — deckungsgleich mit
    :func:`_day_soll_contribution` (dort bleibt ``min(Tagessoll, gearbeitete
    Stunden)`` als Rest-Soll stehen): die erfassten Stunden füllen zuerst den von
    der Abwesenheit NICHT abgedeckten Teil des Tages, nur der Überhang zehrt an
    der Gutschrift bzw. an der unbezahlten Minderung. Bei voller Abdeckung
    (``coverage == 1``, der beschriebene Fall) ist das exakt
    ``max(0, geplant − gearbeitet)``; bei einem Halbtag bleibt die Gutschrift der
    freien Hälfte erhalten, wenn nur die Arbeitshälfte gestempelt wurde (sonst
    wäre der Halbtag dieselbe Falle in klein).

    Byte-identisch für alle Tage OHNE Zeiteintrag (``worked == 0``) und für
    ``gearbeitet ≥ geplant`` (dort war der Skip schon das richtige Ergebnis)."""
    days_in_month = monthrange(year, month)[1]
    cfg = special_days_service.get_special_day_config(db, user.tenant_id, year)
    # Finding 2 (Whole-Branch-Review, cross-set double-count guard): holiday
    # dates are needed on BOTH paths now — on the paid-credit path to grant the
    # credit (unchanged), on the unpaid path to SKIP a day that is already
    # handled by the credit side. Without this, a day that is both a public
    # holiday and carries a full-day OTHER/UNPAID_FREE absence would get
    # +planned (holiday credit) AND −planned (unpaid reduction) = +2×planned
    # net balance movement instead of the correct +1×planned.
    holiday_dates = {h.date for h in db.query(PublicHoliday).filter(
        date_in_month(PublicHoliday.date, year, month),
        PublicHoliday.tenant_id == user.tenant_id,
    ).all()}
    by_date = {}
    for a in db.query(Absence).filter(
        Absence.user_id == user.id, Absence.tenant_id == user.tenant_id,
        date_in_month(Absence.date, year, month),
        Absence.type.in_(list(types)), Absence.start_time.is_(None),  # nur ganztägig
    ).all():
        by_date.setdefault(a.date, []).append(a)  # Liste: Misch-Tag ½+½ nicht verlieren
    # L1: die erfassten Netto-Stunden je Tag (nicht mehr nur „hat einen Eintrag").
    worked_by_date: Dict[date, Decimal] = {}
    for e in db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id, TimeEntry.tenant_id == user.tenant_id,
        date_in_month(TimeEntry.date, year, month),
    ).all():
        worked_by_date[e.date] = worked_by_date.get(e.date, Decimal('0')) + e.net_hours
    # #431: EIN Preload für die ganze Monatsschleife statt einer Query je Tag —
    # _fixed_planned_hours löst den Vertrags-Snapshot jetzt pro Datum auf.
    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
    ).order_by(WorkingHoursChange.effective_from).all()
    total = Decimal('0')
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        if up_to_date is not None and d > up_to_date:
            continue
        if from_date is not None and d < from_date:
            continue
        if not _within_employment_window(user, d):
            continue
        if not include_holidays and d in holiday_dates:
            continue  # Finding 2: Feiertag bereits über die Credit-Seite abgedeckt
        day_absences = by_date.get(d, [])
        is_holiday_day = bool(include_holidays and d in holiday_dates)
        if not is_holiday_day and not day_absences:
            continue  # nichts abzudecken — spart das Aufloesen der Planstunden
        planned = _fixed_planned_hours(db, user, d, cfg, wh_changes=wh_changes)
        # Die Deckungs-/Klemm-Regel steht in fixed_day_covered_hours — dieselbe
        # Funktion nutzt journal_service fuer die Tageszeile (#463).
        total += fixed_day_covered_hours(
            planned, day_absences, worked_by_date.get(d, Decimal('0')), is_holiday_day,
        )
    return total.quantize(Decimal('0.01'))


def fixed_month_credit(db: Session, user: User, year: int, month: int, up_to_date: date = None,
                        from_date: date = None) -> Decimal:
    """#377 Baustein 2b: geplante Stunden, die BEZAHLTE Fehltage (Feiertag +
    VACATION/PAID_LEAVE) dem Ist gutschreiben. SICK/TRAINING NICHT (Doppelguard).
    ``from_date`` (Review-Medium): optionale Untergrenze für Range-genaue Aufrufe
    — None (Default) = ganzer Monat, unverändertes Verhalten."""
    if not getattr(user, "use_fixed_monthly_target", False):
        return Decimal('0')
    return _fixed_month_absence_hours(db, user, year, month, _FIXED_PAID_CREDIT_TYPES,
                                      up_to_date, include_holidays=True, from_date=from_date)


def fixed_month_unpaid_reduction(db: Session, user: User, year: int, month: int, up_to_date: date = None,
                                  from_date: date = None) -> Decimal:
    """#377 Baustein 2b: geplante Stunden UNBEZAHLTER Fehltage (OTHER), die das
    feste Monats-Soll mindern (statt Ist+). ``from_date`` (Review-Medium):
    optionale Untergrenze für Range-genaue Aufrufe — None (Default) = ganzer
    Monat, unverändertes Verhalten."""
    if not getattr(user, "use_fixed_monthly_target", False):
        return Decimal('0')
    return _fixed_month_absence_hours(db, user, year, month, _FIXED_UNPAID_TYPES,
                                      up_to_date, include_holidays=False, from_date=from_date)


def get_working_days_in_month(db: Session, year: int, month: int) -> int:
    """
    Calculate number of working days (Mon-Fri) in a month.
    Excludes weekends but does NOT exclude holidays or absences.

    Args:
        db: Database session (unused, kept for consistency)
        year: Year
        month: Month (1-12)

    Returns:
        Number of working days (weekdays)
    """
    _, last_day = monthrange(year, month)
    working_days = 0

    for day in range(1, last_day + 1):
        d = date(year, month, day)
        # Count only weekdays (Mon-Fri)
        if d.weekday() < 5:
            working_days += 1

    return working_days


# NOTE: §3 ArbZG allows extending daily work to 10h if compensated to 8h average
# within 6 calendar months / 24 weeks. This averaging period is not tracked
# automatically — it requires manual monitoring by the employer.


def _within_employment_window(user: User, d: date) -> bool:
    """#193: True if ``d`` lies within the user's employment window.

    Days before ``first_work_day`` or after ``last_work_day`` contribute no
    target — the user was not employed then. Mirrors the pro-rata logic already
    used in get_vacation_account so Soll- and Urlaubsberechnung stay consistent.
    Open bounds when the respective field is unset.
    """
    if user.first_work_day and d < user.first_work_day:
        return False
    if user.last_work_day and d > user.last_work_day:
        return False
    return True


def credit_day_weight(d: date, holiday_dates: set, special_cfg: Optional[dict] = None) -> Decimal:
    """Audit 2026-07-31 (Fund K): Gewicht, mit dem eine ist-gutgeschriebene
    Abwesenheit (TRAINING/SICK) an ``d`` ins Ist eingeht.

    TRAINING/SICK reduzieren das Soll NICHT — stattdessen bekommt die Ist-Seite
    die Stunden der Abwesenheit gutgeschrieben (``credited_absences``). Der Sinn
    dieser Konstruktion ist **Saldo-Neutralitaet**: das Soll des Tages bleibt
    stehen, die Gutschrift gleicht es aus, der Saldo bewegt sich nicht. Das
    funktioniert nur, solange die Gutschrift denselben strukturellen Regeln folgt
    wie das Soll. Genau das tat sie nicht — die vier Gutschrift-Schleifen
    summierten ``Absence.hours`` roh, waehrend :func:`_day_soll_contribution`
    daneben Feiertage auf 0 setzt, die Aufrufer Wochenenden ueberspringen und der
    #146-Sondertagsfaktor das Tagessoll skaliert.

    Diese Funktion ist der **Spiegel** dieser strukturellen Regeln — dieselbe
    Reihenfolge, dieselben Quellen:

    * **Wochenende / gesetzlicher Feiertag → 0.** An einem Tag ohne
      Arbeitspflicht kann keine Arbeitspflicht ausfallen; es gibt kein Soll, das
      auszugleichen waere. Vorher machte die Gutschrift aus einer Krankmeldung
      ein volles Tagessoll **Ueberstunden** — wer ueber Weihnachten
      krankgeschrieben war, sammelte je Feiertag +8 h. Auch rechtlich falsch:
      fuer den Feiertag gilt die Feiertagsverguetung (§ 2 EntgFG), nicht
      zusaetzlich eine Entgeltfortzahlung wegen Krankheit (§ 3 EntgFG) — § 4
      Abs. 2 EntgFG ordnet den Feiertag ausdruecklich § 2 zu.
    * **Sondertag 24./31.12. → derselbe Faktor wie das Soll** (``half_day`` 0,5,
      ``free`` 0). ``create_absence`` bucht dort das VOLLE Tagessoll als
      ``hours`` (der Faktor lebt allein auf der Soll-Seite), also standen an
      einem halben 24.12. 8 h Gutschrift gegen 4 h Soll = +4 h aus dem Nichts.
      Der Faktor kommt aus ``special_days_service.special_day_target_factor`` —
      derselben Quelle, die auch ``_day_soll_contribution`` benutzt.

    Bewusst NICHT abgedeckt (die Regel lautet „die Gutschrift folgt der
    Soll-STRUKTUR des Tages", nicht „Gutschrift = Soll"):

    * ``hours > Tagessoll`` an einem regulaeren Arbeitstag bleibt unangetastet —
      eine Fortbildung, die laenger dauerte als der Arbeitstag, ist echte
      Mehrarbeit. Ein Deckel darauf waere eine andere Regel mit anderer
      fachlicher Begruendung.
    * Ein **0-Stunden-Wochentag** im Tagesplan-Modus traegt zwar kein Soll,
      braucht hier aber keinen Zweig: dort bucht ``create_absence`` ``hours=0``,
      die Gutschrift ist also von sich aus 0 (und eine Buchung, die an allen
      Zieltagen 0 waere, lehnt der Endpunkt seit 1.18.0 mit 400 ab).
    * Das **Beschaeftigungsfenster** (#195) filtern alle Aufrufstellen bereits
      selbst — wie auf der Soll-Seite auch.

    ``special_cfg`` darf ``None``/``{}`` sein, wenn der Aufrufer weiss, dass ``d``
    kein Sondertag sein kann: ``get_special_day_config`` legt ausschliesslich die
    Schluessel 24.12. und 31.12. des Jahres an, fuer jedes andere Datum liefert
    ``special_day_target_factor`` also ohnehin ``None`` (Gewicht 1).
    """
    if d.weekday() >= 5 or d in holiday_dates:
        return Decimal('0')
    factor = special_days_service.special_day_target_factor(d, special_cfg or {})
    return Decimal('1') if factor is None else Decimal(str(factor))


def _credited_day_context(db: Session, user: User, credited_absences: List[Absence]):
    """Feiertage + Sondertags-Konfiguration fuer :func:`get_range_actual`.

    Die drei anderen Gutschrift-Stellen laden beides ohnehin schon fuer ihre
    Soll-Schleife; ``get_range_actual`` (und damit ``get_monthly_actual``) tut das
    nicht und ist eine heisse Fläche. Deshalb wird hier **nur** geladen, was die
    vorhandenen Abwesenheiten wirklich brauchen:

    * Feiertage nur an den Werktagen mit einer solchen Abwesenheit,
    * die Sondertags-Konfiguration nur fuer Jahre, in denen eine solche
      Abwesenheit tatsaechlich auf den 24. oder 31.12. faellt.

    Ohne TRAINING/SICK-Abwesenheit im Zeitraum (der Regelfall) entsteht **keine**
    zusaetzliche Query — ``get_monthly_actual`` bleibt unveraendert schnell.
    """
    weekday_dates = sorted({a.date for a in credited_absences if a.date.weekday() < 5})
    if not weekday_dates:
        return set(), {}
    holiday_dates = {h.date for h in db.query(PublicHoliday).filter(
        PublicHoliday.date.in_(weekday_dates),
        PublicHoliday.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
    ).all()}
    special_years = {d.year for d in weekday_dates if (d.month, d.day) in ((12, 24), (12, 31))}
    special_cfgs = {
        yr: special_days_service.get_special_day_config(db, user.tenant_id, yr)
        for yr in special_years
    }
    return holiday_dates, special_cfgs


def _soll_reducing_absence_half_map(absences: List[Absence]) -> Dict[date, bool]:
    """Fix #1: map each soll-reducing absence (VACATION/OTHER/PAID_LEAVE) date to
    whether it is a HALF day, for the shared per-day Soll helper below.

    Value semantics:

    * date NOT in map → no soll-reducing absence that day (full Tagessoll counts)
    * value ``False`` → full-day absence → the whole day's Soll is removed
    * value ``True``  → half-day absence → only 0,5 × Tagessoll is removed
                        (half the Soll remains so the worked half still counts)

    ``half_day`` only counts as half when explicitly ``True``; legacy rows
    (``None``) and full-day rows (``False``) keep the historic full-skip
    behaviour. If two rows ever shared a date (the unique constraint normally
    prevents it), a full day wins (more Soll removed = conservative).
    """
    m: Dict[date, bool] = {}
    for a in absences:
        is_half = a.half_day is True
        m[a.date] = (m[a.date] and is_half) if a.date in m else is_half
    return m


def worked_hours_map(
    db: Session, user: User, absence_half_map: Dict[date, bool]
) -> Dict[date, Decimal]:
    """F1 (1.18.0): erfasste Netto-Stunden je Tag mit GANZTÄGIGER soll-reduzierender
    Abwesenheit — die einzige Konstellation, in der ``_day_soll_contribution`` sie
    braucht.

    Bleibt beim Buchen einer Abwesenheit ein Zeiteintrag stehen
    (``keep_time_entries``, Regelfall über den „+"-Knopf im Monatsjournal), zählte
    der Tag bisher die gearbeiteten Stunden im Ist UND verlor sein ganzes Soll →
    Phantom-Überstunden in Höhe der gearbeiteten Zeit. Die Abwesenheit darf nur
    den NICHT gearbeiteten Teil des Tages streichen.

    Bewusst nur für ``half is False``-Tage geladen: ohne solchen Tag entsteht
    keine Query (der Normalfall bleibt unverändert schnell), und Tage ohne
    Zeiteintrag liefern keinen Eintrag → das Verhalten bleibt dort byte-identisch.
    Halbtage (``half is True``) sind bereits korrekt (0,5 × Soll bleibt stehen)
    und werden hier absichtlich NICHT angefasst.
    """
    full_days = [d for d, half in absence_half_map.items() if half is False]
    if not full_days:
        return {}
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
        TimeEntry.date.in_(full_days),
    ).all()
    worked: Dict[date, Decimal] = {}
    for e in entries:
        worked[e.date] = worked.get(e.date, Decimal('0')) + e.net_hours
    return worked


def _day_soll_contribution(
    db: Session,
    user: User,
    d: date,
    *,
    holiday_dates: set,
    absence_half_map: Dict[date, bool],
    wh_changes: Optional[List[WorkingHoursChange]],
    special_cfg: dict,
    worked_map: Optional[Dict[date, Decimal]] = None,
) -> Decimal:
    """Fix #1: single source of truth for ONE weekday's Soll contribution, shared
    by all four per-day Soll loops (get_range_target, get_overtime_account,
    get_overtime_history, get_ytd_summary) so half-day handling never diverges.

    The CALLER is responsible for the weekend / employment-window / up_to_date
    cutoff skips. This helper handles, in order: holidays, soll-reducing
    absences (full vs. half day), the per-date weekly-hours lookup, the #146
    special-day factor and finally the half-day halving — special-day factor
    FIRST, then ×0,5 for a half day. Returns 0 for a holiday or a full-day
    soll-reducing absence.

    F1 (1.18.0): ``worked_map`` (aus :func:`worked_hours_map`) hält die erfassten
    Netto-Stunden der Tage mit GANZTÄGIGER soll-reduzierender Abwesenheit. Wurde
    an so einem Tag gearbeitet (Abwesenheit über ``keep_time_entries`` gebucht,
    ohne den Zeiteintrag zu löschen), streicht die Abwesenheit nur den nicht
    gearbeiteten Teil: ``min(Tagessoll, gearbeitete Stunden)`` bleibt Soll stehen,
    sonst stünde die gearbeitete Zeit als Phantom-Überstunde im Saldo. Ohne
    Zeiteintrag (Normalfall) ist das Ergebnis unverändert 0.
    """
    if d in holiday_dates:
        return Decimal('0')
    half = absence_half_map.get(d)
    worked = (worked_map or {}).get(d) or Decimal('0')
    if half is False and worked <= 0:
        return Decimal('0')  # full-day soll-reducing absence → no Soll this day
    schedule = get_schedule_for_date(db, user, d, wh_changes=wh_changes)
    daily_target = get_daily_target_for_date(user, d, schedule)
    factor = special_days_service.special_day_target_factor(d, special_cfg)
    if factor is not None:
        daily_target = daily_target * factor
    if half is True:
        daily_target = daily_target * Decimal('0.5')
    elif half is False:
        # F1: nur der NICHT gearbeitete Teil des Tages fällt weg.
        daily_target = min(daily_target, worked)
    return daily_target


def get_soll_cutoff_date(db: Session, user: User, today: date = None) -> date:
    """#313: last date (inclusive) that counts toward the running Soll/Ist.

    ``today`` counts only once it is a *completed* workday — i.e. a clocked-out
    ``TimeEntry`` exists for today; otherwise the cutoff is *yesterday*. This way
    the running month no longer starts on the 1st with the whole month's Soll as
    a deficit; the balance is built up to the last finished working day.
    """
    if today is None:
        today = today_local()
    has_completed_today = db.query(TimeEntry.id).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
        TimeEntry.date == today,
        TimeEntry.end_time.isnot(None),
    ).first() is not None
    return today if has_completed_today else today - timedelta(days=1)


def future_freizeitausgleich_impact(
    db: Session, user: User, *, cutoff_date: date = None, today: date = None
) -> Decimal:
    """#402: Σ Tages-Soll der bereits FESTSTEHENDEN künftigen Freizeitausgleich-Tage.

    Summiert das Tages-Soll aller OVERTIME-Abwesenheiten ab dem Tag NACH dem
    Saldo-Stichtag (#313) bis zum 31.12. des laufenden Jahres — im Beschäftigungs-
    fenster, ohne Wochenende/Feiertag. Genau um diesen Betrag wird das Über-
    stundenkonto durch die schon geplanten Freizeitausgleich-Tage noch sinken
    (bei OVERTIME bleibt das Soll stehen, das Ist ist 0 → Konto −= Tages-Soll).

    Bewusst **Soll-basiert** (dieselbe Quelle `_day_soll_contribution` wie
    `get_overtime_account`), NICHT das `hours`-Feld — so wird die Projektion im
    Dezember bitgleich zum dann tatsächlich gebuchten Saldo. `> cutoff_date`
    verhindert Doppelzählung mit dem aktuellen (bis-heute-)Saldo.
    """
    if not user.track_hours:
        return Decimal('0')
    # #377 Baustein 2b — Fix-Soll-Modus. Release-Review 1.16.0: die frühere
    # Begründung („OVERTIME steht in keinem _FIXED_*_TYPES, bewegt das Konto also
    # nicht") war genau verkehrt herum. Dass OVERTIME weder in
    # _FIXED_PAID_CREDIT_TYPES noch in _FIXED_UNPAID_TYPES steht, heißt: es gibt
    # (a) KEINE Ist-Gutschrift über fixed_month_credit und (b) KEINE Soll-Minderung
    # über fixed_month_unpaid_reduction. Das Soll bleibt das volle flache
    # agreed_monthly_hours, das Ist zählt für den Ausgleichstag 0 — der Saldo sinkt
    # also um exakt die GEPLANTEN Stunden des Tages, genau wie im Tages-Modell.
    # Die Projektion war damit ausgerechnet für die Gruppe dunkel, deren Konto nach
    # § 2 Abs. 2 MiLoG binnen 12 Monaten ausgeglichen sein muss.
    #
    # Im Fix-Modus ist die maßgebliche Größe die geplante Tagesarbeitszeit
    # (_fixed_planned_hours), nicht das aus den Wochenstunden abgeleitete Tages-Soll.
    _fixed_mode = bool(
        getattr(user, "use_fixed_monthly_target", False)
        and getattr(user, "agreed_monthly_hours", None)
    )
    if today is None:
        today = today_local()
    if cutoff_date is None:
        cutoff_date = get_soll_cutoff_date(db, user, today)
    year_end = date(today.year, 12, 31)
    if cutoff_date >= year_end:
        return Decimal('0')

    overtime_abs = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
        Absence.type == AbsenceType.OVERTIME,
        Absence.date > cutoff_date,
        Absence.date <= year_end,
    ).all()
    if not overtime_abs:
        return Decimal('0')

    holiday_dates = {
        h.date for h in db.query(PublicHoliday).filter(
            PublicHoliday.tenant_id == user.tenant_id,
            PublicHoliday.date > cutoff_date,
            PublicHoliday.date <= year_end,
        ).all()
    }
    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,
    ).order_by(WorkingHoursChange.effective_from).all()
    special_cfg = special_days_service.get_special_day_config(db, user.tenant_id, today.year)

    total = Decimal('0')
    for a in overtime_abs:
        d = a.date
        if d.weekday() >= 5:  # Wochenende → 0 Soll
            continue
        if not _within_employment_window(user, d):
            continue
        if _fixed_mode:
            # Fix-Soll: das Monats-Soll ist flach und wird von einem OVERTIME-Tag
            # nicht gemindert; das Ist bekommt für ihn nichts gutgeschrieben. Der
            # Saldo sinkt also um die GEPLANTEN Stunden dieses Tages. An einem
            # Feiertag ist die geplante Zeit ohnehin nicht zu leisten → 0.
            if d in holiday_dates:
                continue
            total += _fixed_planned_hours(db, user, d, special_cfg, wh_changes=wh_changes)
            continue
        # OVERTIME ist NICHT soll-reduzierend → leere half_map → volles Tages-Soll
        # (× #146-Sondertag-Faktor). Exakt der Betrag, um den dieser Tag später
        # den Saldo senkt.
        total += _day_soll_contribution(
            db, user, d,
            holiday_dates=holiday_dates,
            absence_half_map={},
            wh_changes=wh_changes,
            special_cfg=special_cfg,
        )
    return total.quantize(Decimal('0.01'))


def get_range_target(
    db: Session, user: User, start: date, end: date, up_to_date: date = None
) -> Decimal:
    """Soll hours for an arbitrary inclusive ``[start, end]`` range.

    Same per-day logic as :func:`get_monthly_target` (skip weekends / public
    holidays / soll-reducing absences, respect the employment window #193 and the
    #313 ``up_to_date`` cutoff, apply the #146 special-day factor), but over a
    range that may cross a month or year boundary. ``get_monthly_target``
    delegates here so there is a single source of truth.

    Absences REDUCE the target (the employee need not work those days), except
    TRAINING/SICK/OVERTIME (credited / Überstundenausgleich — see
    get_monthly_target's original note). The special-day config is fetched per
    year so a range spanning Dec/Jan stays correct.

    Returns 0 if ``track_hours`` is False or the range is empty.
    """
    if not user.track_hours or end < start:
        return Decimal('0')

    # #377 Baustein 2b: fester Monats-Soll-Modus — statt der Per-Tag-Summe die
    # (pro-rata + unpaid-geminderten) festen Monats-Solls über die Range summieren.
    if getattr(user, "use_fixed_monthly_target", False) and getattr(user, "agreed_monthly_hours", None):
        total_fixed = Decimal('0')
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            first = date(y, m, 1)
            last = date(y, m, monthrange(y, m)[1])
            month_start = max(first, start)
            month_end = min(last, end if up_to_date is None else min(end, up_to_date))
            if month_end >= month_start:
                # Review-Medium: NUR das Ziel wird über den Range-Anteil skaliert;
                # die unbezahlte Reduktion wird direkt für [month_start,month_end]
                # ermittelt (from_date=month_start) statt whole-month-dann-skaliert
                # — sonst "smeart" eine einzelne Abwesenheit über jede Woche des
                # Monats, auch Wochen, die den Abwesenheitstag gar nicht enthalten.
                mt = fixed_monthly_target(user, y, m)
                # Range-/cutoff-Skalierung: Anteil der in [month_start,month_end] ∩ Fenster
                # liegenden Kalendertage an den Fenster-Tagen des Monats.
                win_days = sum(1 for dd in range(1, monthrange(y, m)[1] + 1)
                               if _within_employment_window(user, date(y, m, dd)))
                in_days = sum(1 for dd in range(month_start.day, month_end.day + 1)
                              if _within_employment_window(user, date(y, m, dd)))
                if win_days > 0 and in_days < win_days:
                    mt = (mt * Decimal(in_days) / Decimal(win_days))
                # L4 (Audit 2026-07-31): Untergrenze 0 je Monatsscheibe. Ziel und
                # Minderung haben unterschiedliche Basen — das Ziel ist
                # KALENDERTAG-anteilig (agreed × Fenstertage), die Minderung ist
                # die Summe der PLANSTUNDEN der unbezahlten Fehltage. Ein Monat
                # kann mehr Planstunden tragen als `agreed` (22 Werktage sind
                # 4,4 Wochen, mehr als die 13/3 der Ableitung), ebenso eine
                # Wochenscheibe mehr als ihr Kalendertag-Anteil. Ohne Klemmung
                # ergab ein voller Monat unbezahlt frei ein NEGATIVES Soll und
                # damit Phantom-Überstunden in genau dieser Höhe (Monat −2,00 h,
                # Wochenbericht −0,65 h). Mehr als das ganze Soll kann eine
                # unbezahlte Freistellung nie streichen.
                mt = max(Decimal('0'), mt - fixed_month_unpaid_reduction(
                    db, user, y, m, from_date=month_start, up_to_date=month_end))
                total_fixed += mt
            m += 1
            if m > 12:
                m = 1
                y += 1
        return total_fixed.quantize(Decimal('0.01'))

    # F-033: sargable date range.
    holidays = db.query(PublicHoliday).filter(
        date_in_range(PublicHoliday.date, start, end),
        PublicHoliday.tenant_id == user.tenant_id,
    ).all()
    holiday_dates = {h.date for h in holidays}

    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
        date_in_range(Absence.date, start, end),
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME]),
    ).all()
    # Fix #1: half-day-aware map (full day → skip, half day → halve Soll).
    absence_half_map = _soll_reducing_absence_half_map(absences)
    # F1 (1.18.0): erfasste Arbeitszeit auf Ganztags-Abwesenheitstagen (nur dann
    # eine Query) — die Abwesenheit darf nur den nicht gearbeiteten Teil streichen.
    worked_map = worked_hours_map(db, user, absence_half_map)

    # Preload the user's WorkingHoursChange rows ONCE and resolve the per-day
    # weekly hours in memory (avoids one SELECT per day — N+1 — for a multi-day
    # range; mirrors get_overtime_account). F-026: tenant-scoped.
    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,
    ).order_by(WorkingHoursChange.effective_from).all()

    # #146: special-day config can differ per year (a week may cross Dec/Jan).
    _special_cfg_cache: dict = {}

    def _special_cfg(yr: int) -> dict:
        if yr not in _special_cfg_cache:
            _special_cfg_cache[yr] = special_days_service.get_special_day_config(
                db, user.tenant_id, yr
            )
        return _special_cfg_cache[yr]

    total = Decimal('0')
    d = start
    while d <= end:
        # Skip weekends
        if d.weekday() >= 5:  # Saturday or Sunday
            d += timedelta(days=1)
            continue
        # #313: only count up to the running cutoff (e.g. last finished workday)
        if up_to_date is not None and d > up_to_date:
            d += timedelta(days=1)
            continue
        # #193: skip days outside the employment window (before entry / after exit)
        if not _within_employment_window(user, d):
            d += timedelta(days=1)
            continue

        # Fix #1: holidays / soll-reducing absences (full vs. half day) + the #146
        # special-day factor live in the shared per-day helper so all four Soll
        # loops behave identically (full-day absence → 0; half-day → 0,5×Soll).
        total += _day_soll_contribution(
            db, user, d,
            holiday_dates=holiday_dates,
            absence_half_map=absence_half_map,
            wh_changes=wh_changes,
            special_cfg=_special_cfg(d.year),
            worked_map=worked_map,
        )
        d += timedelta(days=1)

    return total.quantize(Decimal('0.01'))


def get_range_actual(
    db: Session, user: User, start: date, end: date, up_to_date: date = None
) -> Decimal:
    """Ist hours worked in an arbitrary inclusive ``[start, end]`` range.

    Sum of TimeEntry net_hours + credited TRAINING/SICK hours, both windowed by
    the employment window (#195) and the optional ``up_to_date`` cutoff.
    ``get_monthly_actual`` delegates here.
    """
    if end < start:
        return Decimal('0')

    # F-033: sargable date range. The Python-level Decimal sum is kept because
    # the SQL @expression for net_hours relies on Postgres EXTRACT(EPOCH ...)
    # semantics that do not port to the SQLite test suite.
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        date_in_range(TimeEntry.date, start, end),
    ).all()
    # #195: only count Ist within the employment window — symmetric to the Soll
    # guard. A TimeEntry before first_work_day / after last_work_day must
    # contribute neither Soll nor Ist, otherwise the balance shows phantom overtime.
    total = sum((entry.net_hours for entry in entries
                 if _within_employment_window(user, entry.date)
                 and (up_to_date is None or entry.date <= up_to_date)), start=Decimal('0'))

    # Training and sick hours count as actual worked hours (außer Haus / §3 EntgFG).
    credited_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
        date_in_range(Absence.date, start, end),
    ).all()
    # Audit 2026-07-31 (Fund K): die Gutschrift folgt der Soll-Struktur des Tages
    # — Wochenende/Feiertag 0, Sondertag mit dem #146-Faktor. Siehe
    # :func:`credit_day_weight`. Ohne solche Abwesenheit im Zeitraum ist der
    # Kontext leer und es entsteht keine zusaetzliche Query.
    credit_holidays, credit_cfgs = _credited_day_context(db, user, credited_absences)
    credited_hours = sum((Decimal(str(a.hours))
                          * credit_day_weight(a.date, credit_holidays, credit_cfgs.get(a.date.year))
                          for a in credited_absences
                          if _within_employment_window(user, a.date)
                          and (up_to_date is None or a.date <= up_to_date)), Decimal('0'))

    # #377 Baustein 2b: fester Monats-Soll-Modus — Feiertage/VACATION/PAID_LEAVE
    # auf geplanten Tagen schreiben dem Ist die geplanten Stunden gut (statt
    # Ist=0 auf einem bezahlten Fehltag). Monatsweise, da fixed_month_credit
    # monatsweise arbeitet; from_date=month_start hält es range-genau (mirror
    # von get_range_target — eine Gutschrift in Woche A darf nicht in eine
    # Abfrage für Woche B desselben Monats durchsickern).
    fixed_credit = Decimal('0')
    if getattr(user, "use_fixed_monthly_target", False) and getattr(user, "agreed_monthly_hours", None):
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            first = date(y, m, 1)
            last = date(y, m, monthrange(y, m)[1])
            month_start = max(first, start)
            month_end = min(last, end if up_to_date is None else min(end, up_to_date))
            if month_end >= month_start:
                fixed_credit += fixed_month_credit(db, user, y, m, from_date=month_start, up_to_date=month_end)
            m += 1
            if m > 12:
                m = 1
                y += 1

    return (Decimal(str(total)) + credited_hours + fixed_credit).quantize(Decimal('0.01'))


def get_monthly_target(
    db: Session, user: User, year: int, month: int, up_to_date: date = None
) -> Decimal:
    """
    Calculate monthly target hours (thin wrapper over :func:`get_range_target`).

    For each weekday (Mon-Fri) in the month: skip public holidays + soll-reducing
    absences, add the daily target (based on the weekly hours valid for that date,
    so a mid-month WorkingHoursChange is handled correctly). Absences REDUCE the
    target. Returns 0 if track_hours is False.
    """
    _, last_day = monthrange(year, month)
    return get_range_target(
        db, user, date(year, month, 1), date(year, month, last_day), up_to_date=up_to_date
    )


def get_monthly_actual(
    db: Session, user: User, year: int, month: int, up_to_date: date = None
) -> Decimal:
    """
    Calculate actual hours worked in a month (thin wrapper over
    :func:`get_range_actual`). Sum of TimeEntry net_hours + credited
    TRAINING/SICK hours (§3 EntgFG / Fortbildung außer Haus).
    """
    _, last_day = monthrange(year, month)
    return get_range_actual(
        db, user, date(year, month, 1), date(year, month, last_day), up_to_date=up_to_date
    )


def get_gross_monthly_target(db: Session, user: User, year: int, month: int) -> Decimal:
    """Gross monthly target — like get_monthly_target but WITHOUT subtracting the
    soll-reducing absence days (VACATION/OTHER/PAID_LEAVE). Weekend, holiday,
    employment-window (#193) and special-day factor (#146) are still applied.

    Used ONLY by the classic yearly report, which presents the traditional
    "Brutto-Soll − Krank − Urlaub = bereinigtes Soll" layout: the explicit
    "minus" rows are the ones that reduce the soll there, so row 7 must be the
    gross value (get_monthly_target already nets vacation/other/paid_leave out).
    """
    if not user.track_hours:
        return Decimal('0')

    holiday_dates = {h.date for h in db.query(PublicHoliday).filter(
        date_in_month(PublicHoliday.date, year, month),
        PublicHoliday.tenant_id == user.tenant_id,
    ).all()}
    special_day_config = special_days_service.get_special_day_config(db, user.tenant_id, year)
    # #431: EIN Preload für die Monatsschleife (Muster wie get_range_target).
    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
    ).order_by(WorkingHoursChange.effective_from).all()

    _, last_day = monthrange(year, month)
    gross = Decimal('0')
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        if d.weekday() >= 5:
            continue
        if not _within_employment_window(user, d):
            continue
        if d in holiday_dates:
            continue
        schedule = get_schedule_for_date(db, user, d, wh_changes=wh_changes)
        daily_target = get_daily_target_for_date(user, d, schedule)
        factor = special_days_service.special_day_target_factor(d, special_day_config)
        if factor is not None:
            daily_target = daily_target * factor
        gross += daily_target

    return gross.quantize(Decimal('0.01'))


def get_monthly_worked_hours(db: Session, user: User, year: int, month: int) -> Decimal:
    """Hours physically WORKED (Σ net_hours of time entries, employment-windowed)
    — WITHOUT the credited TRAINING/SICK hours that get_monthly_actual adds.

    Used by the classic yearly report's "erbrachte Stunden" row, whose
    traditional gross-model balance compares worked-only against the
    absence-reduced soll. NOT a substitute for get_monthly_actual anywhere else.
    """
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        date_in_month(TimeEntry.date, year, month),
    ).all()
    total = sum((entry.net_hours for entry in entries
                 if _within_employment_window(user, entry.date)), start=Decimal('0'))
    return Decimal(str(total)).quantize(Decimal('0.01'))


def get_monthly_balance(
    db: Session, user: User, year: int, month: int, up_to_date: date = None
) -> Decimal:
    """
    Calculate monthly balance (Actual - Target).

    Args:
        db: Database session
        user: User object
        year: Year
        month: Month (1-12)

    Returns:
        Monthly balance as Decimal (positive = overtime, negative = deficit)
    """
    target = get_monthly_target(db, user, year, month, up_to_date=up_to_date)
    actual = get_monthly_actual(db, user, year, month, up_to_date=up_to_date)

    balance = actual - target

    return balance.quantize(Decimal('0.01'))


def get_overtime_account(
    db: Session, user: User, up_to_year: int, up_to_month: int, cutoff_date: date = None
) -> Decimal:
    """
    Calculate cumulative overtime account up to specified month.

    If a YearCarryover exists, uses it as the starting balance and only
    iterates months from that year forward (avoids double-counting).
    Otherwise falls back to calculating from the first time entry.

    Args:
        db: Database session
        user: User object
        up_to_year: Year to calculate up to (inclusive)
        up_to_month: Month to calculate up to (inclusive)

    Returns:
        Cumulative overtime as Decimal
    """
    if not user.track_hours:
        return Decimal('0.00')

    up_to_date = date(up_to_year, up_to_month, monthrange(up_to_year, up_to_month)[1])

    # --- determine starting point ---
    # Find the most recent carryover at or before up_to_year
    latest_carryover = db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id,
        YearCarryover.year <= up_to_year,
    ).order_by(YearCarryover.year.desc()).first()

    if latest_carryover:
        # Start from Jan of the carryover year with the carryover value
        start_year = latest_carryover.year
        start_month = 1
        initial_balance = Decimal(str(latest_carryover.overtime_hours))
        start_date = date(start_year, 1, 1)
    else:
        # No carryover: start from first time entry
        first_entry = db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id
        ).order_by(TimeEntry.date).first()

        if not first_entry:
            return Decimal('0.00')

        start_year = first_entry.date.year
        start_month = first_entry.date.month
        initial_balance = Decimal('0.00')
        start_date = date(start_year, start_month, 1)

    # --- single-pass bulk fetches ---
    # All time entries in range (group by month in memory)
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.date >= start_date,
        TimeEntry.date <= up_to_date,
    ).all()
    # #195: skip Ist outside the employment window (symmetric to the Soll guard
    # in the month loop below) so out-of-window entries don't create phantom
    # overtime.
    actual_by_month: Dict[tuple, Decimal] = {}
    for e in entries:
        if not _within_employment_window(user, e.date):
            continue
        if cutoff_date is not None and e.date > cutoff_date:  # #313
            continue
        key = (e.date.year, e.date.month)
        actual_by_month[key] = actual_by_month.get(key, Decimal('0')) + Decimal(str(e.net_hours))

    # All public holidays in range
    # Audit 2026-07-31 (Fund K): VOR die Gutschrift-Schleife gezogen — die
    # braucht das Set jetzt ebenfalls (credit_day_weight), nicht mehr nur die
    # Soll-Schleife weiter unten.
    holidays = db.query(PublicHoliday).filter(
        PublicHoliday.date >= start_date,
        PublicHoliday.date <= up_to_date,
        PublicHoliday.tenant_id == user.tenant_id,
    ).all()
    holiday_dates: set[date] = {h.date for h in holidays}

    # #146: special-day configs are per-year; cache them across the month loop
    # so a multi-year overtime calculation issues one settings query per year.
    # Audit 2026-07-31 (Fund K): ebenfalls vorgezogen, aus demselben Grund.
    special_day_configs: Dict[int, dict] = {}

    def _special_day_config(yr: int) -> dict:
        cfg = special_day_configs.get(yr)
        if cfg is None:
            cfg = special_days_service.get_special_day_config(db, user.tenant_id, yr)
            special_day_configs[yr] = cfg
        return cfg

    # Training and sick hours count as actual worked hours (§3 EntgFG)
    credited_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
        Absence.date >= start_date,
        Absence.date <= up_to_date,
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
    ).all()
    for ca in credited_absences:
        if not _within_employment_window(user, ca.date):
            continue
        if cutoff_date is not None and ca.date > cutoff_date:  # #313
            continue
        # Audit 2026-07-31 (Fund K): die Gutschrift folgt der Soll-Struktur des
        # Tages (Wochenende/Feiertag 0, Sondertag mit dem #146-Faktor).
        weight = credit_day_weight(ca.date, holiday_dates, _special_day_config(ca.date.year))
        if weight <= 0:
            continue
        key = (ca.date.year, ca.date.month)
        actual_by_month[key] = actual_by_month.get(key, Decimal('0')) + Decimal(str(ca.hours)) * weight

    # All absences in range (exclude TRAINING, SICK, OVERTIME — same rule as
    # get_monthly_target). VACATION/OTHER/PAID_LEAVE reduce the target and are
    # therefore balance-neutral (target drops, actual unaffected). PAID_LEAVE
    # (#145) is intentionally treated exactly like OTHER here.
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start_date,
        Absence.date <= up_to_date,
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME]),
    ).all()
    # Fix #1: half-day-aware map (full day → skip, half day → halve Soll).
    absence_half_map: Dict[date, bool] = _soll_reducing_absence_half_map(absences)
    # F1 (1.18.0): siehe worked_hours_map — Ganztags-Abwesenheit auf einem Tag mit
    # erfasster Arbeitszeit streicht nur den nicht gearbeiteten Teil des Solls.
    worked_map = worked_hours_map(db, user, absence_half_map)

    # All working-hours changes for this user (pre-loaded for the hot loop).
    # F-027: routed through get_weekly_hours_for_date() with in-memory path
    # to satisfy the CLAUDE.md invariant "never read user.weekly_hours
    # directly" without paying the per-day DB-query cost.
    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
    ).order_by(WorkingHoursChange.effective_from).all()

    # --- iterate months and compute balance in memory ---
    total_balance = initial_balance
    current_year, current_month = start_year, start_month

    while (current_year < up_to_year) or (current_year == up_to_year and current_month <= up_to_month):
        key = (current_year, current_month)

        # #377 Baustein 2b: fest-Monats-Soll-Modus — statt die per-Tag-Summe
        # unten neu zu rekonstruieren (Risiko, die SICK/TRAINING-Gutschrift +
        # den unbezahlt-Abzug/Fix-Credit zu vergessen/zu duplizieren), an die
        # bereits modus-korrekten Wrapper (Tasks 3+4) delegieren — Single
        # Source of Truth. `cutoff_date` (#313, "bis heute") ist derselbe Wert,
        # den der nicht-modus-Pfad unten pro Tag gegen `d` prüft; get_range_target/
        # get_range_actual clampen intern selbst gegen das jeweilige Monatsende
        # (`min(end, up_to_date)`), daher hier unverändert durchreichen — NICHT
        # die oben berechnete `up_to_date` (= Monatsende des ANGEFRAGTEN
        # up_to_year/up_to_month, nur für den Bulk-Fetch-Query-Bound gedacht).
        if getattr(user, "use_fixed_monthly_target", False) and getattr(user, "agreed_monthly_hours", None):
            monthly_target = get_monthly_target(db, user, current_year, current_month, up_to_date=cutoff_date)
            monthly_actual = get_monthly_actual(db, user, current_year, current_month, up_to_date=cutoff_date)
            total_balance += (monthly_actual - monthly_target)

            if current_month == 12:
                current_month = 1
                current_year += 1
            else:
                current_month += 1
            continue

        # Monthly target (mirrors get_monthly_target logic)
        _, last_day = monthrange(current_year, current_month)
        cfg = _special_day_config(current_year)
        monthly_target = Decimal('0')
        for day in range(1, last_day + 1):
            d = date(current_year, current_month, day)
            if d.weekday() >= 5:
                continue
            # #313: only count Soll up to the running cutoff (last finished workday)
            if cutoff_date is not None and d > cutoff_date:
                continue
            # #193: skip days outside the employment window (before entry / after exit)
            if not _within_employment_window(user, d):
                continue
            # Fix #1: shared per-day helper (full-day absence → 0; half-day →
            # 0,5×Soll; holiday → 0; #146 special-day factor applied first).
            monthly_target += _day_soll_contribution(
                db, user, d,
                holiday_dates=holiday_dates,
                absence_half_map=absence_half_map,
                wh_changes=wh_changes,
                special_cfg=cfg,
                worked_map=worked_map,
            )

        monthly_actual = actual_by_month.get(key, Decimal('0'))
        total_balance += (monthly_actual - monthly_target)

        if current_month == 12:
            current_month = 1
            current_year += 1
        else:
            current_month += 1

    return total_balance.quantize(Decimal('0.01'))


class MonthlyOvertime(NamedTuple):
    """Per-Monat-Aufschlüsselung aus :func:`get_overtime_history_detailed`.

    ``target``/``actual`` sind auf 0.01 quantisiert und damit bitgleich zu
    :func:`get_monthly_target` / :func:`get_monthly_actual` (gleicher cutoff);
    ``cumulative`` ist bitgleich zu :func:`get_overtime_account`.
    """
    target: Decimal
    actual: Decimal
    cumulative: Decimal


def get_overtime_history_detailed(
    db: Session, user: User, up_to_year: int, up_to_month: int, cutoff_date: date = None
) -> Dict[tuple, "MonthlyOvertime"]:
    """Soll/Ist/Konto NACH jedem Monat (Start..up_to) in EINEM Pass.

    Liefert je Monat (y, m) ein :class:`MonthlyOvertime` mit ``target``,
    ``actual`` und ``cumulative``. Invarianten (gepinnt):
        detailed[(y, m)].cumulative == get_overtime_account(db, user, y, m)
        detailed[(y, m)].target     == get_monthly_target(db, user, y, m)
        detailed[(y, m)].actual     == get_monthly_actual(db, user, y, m)
    (jeweils mit demselben cutoff_date).

    #150 / Fix #3: damit baut das Dashboard Soll/Ist/Saldo/Konto je Monat aus
    EINEM Single-Pass — statt get_monthly_target + get_monthly_actual ZUSÄTZLICH
    pro Monat zu rufen (jede Einzelrufung iteriert neu -> O(Monate²)).
    :func:`get_overtime_history` ist ein dünner Wrapper, der nur ``cumulative``
    zurückgibt (alter Vertrag + Invariante unverändert). Leeres Dict bei
    track_hours=False / keinen Daten.

    Wie get_overtime_account ist ein YearCarryover ein Reset-Punkt: im Januar
    eines Jahres MIT eigenem Carryover startet der laufende Saldo neu vom
    Carryover-Wert (spiegelt die "latest carryover <= year"-Auswahl der
    Einzelfunktion).
    """
    if not user.track_hours:
        return {}

    up_to_date = date(up_to_year, up_to_month, monthrange(up_to_year, up_to_month)[1])

    carryovers: Dict[int, Decimal] = {
        c.year: Decimal(str(c.overtime_hours))
        for c in db.query(YearCarryover).filter(YearCarryover.user_id == user.id).all()
    }

    first_entry = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id
    ).order_by(TimeEntry.date).first()
    if first_entry is None and not carryovers:
        return {}

    if first_entry is not None:
        fe_year, fe_month = first_entry.date.year, first_entry.date.month
    else:
        fe_year, fe_month = min(carryovers), 1

    # Start-Punkt = der Carryover, den get_overtime_account fuer den ersten Monat
    # waehlen wuerde (latest <= fe_year), sonst der erste Time-Entry.
    applicable = [y for y in carryovers if y <= fe_year]
    if applicable:
        start_year, start_month = max(applicable), 1
        initial_balance = carryovers[start_year]
    else:
        start_year, start_month = fe_year, fe_month
        initial_balance = Decimal('0.00')

    start_date = date(start_year, start_month, 1)

    # --- ein Bulk-Fetch ueber den ganzen Bereich (wie get_overtime_account) ---
    actual_by_month: Dict[tuple, Decimal] = {}
    for e in db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.date >= start_date,
        TimeEntry.date <= up_to_date,
    ).all():
        if not _within_employment_window(user, e.date):
            continue
        if cutoff_date is not None and e.date > cutoff_date:  # #313
            continue
        k = (e.date.year, e.date.month)
        actual_by_month[k] = actual_by_month.get(k, Decimal('0')) + Decimal(str(e.net_hours))

    # Audit 2026-07-31 (Fund K): Feiertags-Set + Sondertags-Cache VOR die
    # Gutschrift-Schleife gezogen (Parität zu get_overtime_account) — die
    # Gutschrift folgt jetzt der Soll-Struktur des Tages.
    holiday_dates = {h.date for h in db.query(PublicHoliday).filter(
        PublicHoliday.date >= start_date,
        PublicHoliday.date <= up_to_date,
        PublicHoliday.tenant_id == user.tenant_id,
    ).all()}

    special_day_configs: Dict[int, dict] = {}

    def _cfg(yr: int) -> dict:
        c = special_day_configs.get(yr)
        if c is None:
            c = special_days_service.get_special_day_config(db, user.tenant_id, yr)
            special_day_configs[yr] = c
        return c

    for ca in db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
        Absence.date >= start_date,
        Absence.date <= up_to_date,
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
    ).all():
        if not _within_employment_window(user, ca.date):
            continue
        if cutoff_date is not None and ca.date > cutoff_date:  # #313
            continue
        weight = credit_day_weight(ca.date, holiday_dates, _cfg(ca.date.year))
        if weight <= 0:
            continue
        k = (ca.date.year, ca.date.month)
        actual_by_month[k] = actual_by_month.get(k, Decimal('0')) + Decimal(str(ca.hours)) * weight

    # Fix #1: half-day-aware map (full day → skip, half day → halve Soll).
    absence_half_map = _soll_reducing_absence_half_map(db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start_date,
        Absence.date <= up_to_date,
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME]),
    ).all())
    # F1 (1.18.0): siehe worked_hours_map.
    worked_map = worked_hours_map(db, user, absence_half_map)

    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
    ).order_by(WorkingHoursChange.effective_from).all()

    history: Dict[tuple, MonthlyOvertime] = {}
    total_balance = initial_balance
    cy, cm = start_year, start_month

    while (cy < up_to_year) or (cy == up_to_year and cm <= up_to_month):
        # Reset im Januar eines Jahres mit eigenem Carryover (ausser dem Start).
        if cm == 1 and cy in carryovers and (cy, cm) != (start_year, start_month):
            total_balance = carryovers[cy]

        # #377 Baustein 2b (Task 8): fest-Monats-Soll-Modus — wie im Task-5-Branch
        # von get_overtime_account an die bereits modus-korrekten Wrapper
        # (get_monthly_target/get_monthly_actual, Tasks 3+4) delegieren statt die
        # Per-Tag-Summe unten neu zu rekonstruieren. Das hält die in der
        # MonthlyOvertime-Docstring gepinnte Invariante
        # (detailed[(y,m)].target == get_monthly_target(...) / .actual ==
        # get_monthly_actual(...)) auch für Modus-MA — und macht die von
        # settlement_aging konsumierten Monats-Deltas (actual − target)
        # modus-korrekt (kein Phantom-Defizit durch gutgeschriebene
        # Feiertage/Urlaub). `cutoff_date` unveraendert durchreichen (wie
        # Task 5) — get_range_target/get_range_actual clampen intern selbst
        # gegen das jeweilige Monatsende.
        if getattr(user, "use_fixed_monthly_target", False) and getattr(user, "agreed_monthly_hours", None):
            monthly_target = get_monthly_target(db, user, cy, cm, up_to_date=cutoff_date)
            monthly_actual = get_monthly_actual(db, user, cy, cm, up_to_date=cutoff_date)
            total_balance += (monthly_actual - monthly_target)
            history[(cy, cm)] = MonthlyOvertime(
                target=monthly_target.quantize(Decimal('0.01')),
                actual=monthly_actual.quantize(Decimal('0.01')),
                cumulative=total_balance.quantize(Decimal('0.01')),
            )
            if cm == 12:
                cm = 1
                cy += 1
            else:
                cm += 1
            continue

        _, last_day = monthrange(cy, cm)
        cfg = _cfg(cy)
        monthly_target = Decimal('0')
        for day in range(1, last_day + 1):
            d = date(cy, cm, day)
            if d.weekday() >= 5:
                continue
            if cutoff_date is not None and d > cutoff_date:  # #313
                continue
            if not _within_employment_window(user, d):
                continue
            # Fix #1: shared per-day helper (kept bit-identical with
            # get_overtime_account so the history invariant holds).
            monthly_target += _day_soll_contribution(
                db, user, d,
                holiday_dates=holiday_dates,
                absence_half_map=absence_half_map,
                wh_changes=wh_changes,
                special_cfg=cfg,
                worked_map=worked_map,
            )

        monthly_actual = actual_by_month.get((cy, cm), Decimal('0'))
        total_balance += (monthly_actual - monthly_target)
        # cumulative wird (wie zuvor) aus den UNquantisierten Monatswerten
        # akkumuliert und erst beim Speichern quantisiert -> bitgleich zu
        # get_overtime_account. target/actual zusätzlich auf 0.01 quantisiert,
        # damit sie get_monthly_target/get_monthly_actual exakt entsprechen.
        history[(cy, cm)] = MonthlyOvertime(
            target=monthly_target.quantize(Decimal('0.01')),
            actual=monthly_actual.quantize(Decimal('0.01')),
            cumulative=total_balance.quantize(Decimal('0.01')),
        )

        if cm == 12:
            cm = 1
            cy += 1
        else:
            cm += 1

    return history


def get_overtime_history(
    db: Session, user: User, up_to_year: int, up_to_month: int, cutoff_date: date = None
) -> Dict[tuple, Decimal]:
    """Kumulatives Überstundenkonto NACH jedem Monat (Start..up_to) in EINEM Pass.

    Invariante: für jeden Monat (y, m) im Bereich gilt
        get_overtime_history(...)[(y, m)] == get_overtime_account(db, user, y, m)
    (gepinnt durch test_overtime_history_matches_account). Dünner Wrapper um
    :func:`get_overtime_history_detailed` — gibt nur den kumulativen Saldo
    zurück (alter Vertrag unverändert).
    """
    return {
        k: v.cumulative
        for k, v in get_overtime_history_detailed(
            db, user, up_to_year, up_to_month, cutoff_date=cutoff_date
        ).items()
    }


def get_ytd_summary(
    db: Session,
    user: User,
    year: int = None,
    cutoff_date: date = None,
    holidays: Optional[set] = None,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> Dict:
    """
    Calculate year-to-date summary from Jan 1 to today.

    #204: ``holidays`` (tenant+year-Set) und ``wh_changes`` (dieses Users) sind
    optionale Preloads für den users-overview-Hot-Loop; Default ``None`` = wie
    bisher querien (byte-identisch, Test ``test_calc_preload``). Der YTD-Range
    liegt immer im Jahr ``year`` → das Jahres-Holiday-Set ist ein deckungsgleicher
    Superset für die Membership-Tests.

    Sums daily targets and actual hours for all working days from Jan 1
    of the given year up to and including today.

    Args:
        db: Database session
        user: User object
        year: Year (default: current year)

    Returns:
        Dict with target_hours, actual_hours, overtime
    """
    if not user.track_hours:
        return {"target_hours": 0.0, "actual_hours": 0.0, "overtime": 0.0}

    today = today_local()
    if year is None:
        year = today.year

    # End date: today if current year, else Dec 31.
    # #313: when a cutoff is given, the running year ends at the cutoff (= last
    # finished workday) instead of always "today", so the YTD-Soll doesn't
    # include today before it's a completed workday.
    if year == today.year:
        end = cutoff_date if cutoff_date is not None else today
    else:
        end = date(year, 12, 31)
    start = date(year, 1, 1)

    if start > end:
        return {"target_hours": 0.0, "actual_hours": 0.0, "overtime": 0.0}

    # #377 Baustein 2b: fest-Monats-Soll-Modus — analog Task 5 (get_overtime_
    # account) an die bereits modus-korrekten Wrapper (Tasks 3+4) delegieren,
    # statt die Per-Tag-Schleife unten (_day_soll_contribution + Inline-Ist)
    # zu duplizieren. `end` (oben aus year/today/cutoff_date hergeleitet)
    # ist bereits die korrekte YTD-Obergrenze für BEIDE Fälle (laufendes Jahr
    # mit/ohne #313-cutoff, oder Vorjahr = 31.12.) — get_monthly_target/
    # get_monthly_actual clampen intern selbst gegen das jeweilige Monatsende
    # (min(Monatsende, up_to_date)), daher hier unverändert durchreichen.
    if getattr(user, "use_fixed_monthly_target", False) and getattr(user, "agreed_monthly_hours", None):
        total_target = Decimal('0')
        total_actual = Decimal('0')
        for m in range(1, end.month + 1):
            total_target += get_monthly_target(db, user, year, m, up_to_date=end)
            total_actual += get_monthly_actual(db, user, year, m, up_to_date=end)

        carryover = db.query(YearCarryover).filter(
            YearCarryover.user_id == user.id,
            YearCarryover.year == year,
        ).first()
        carryover_hours = Decimal(str(carryover.overtime_hours)) if carryover else Decimal('0')

        overtime = total_actual - total_target + carryover_hours

        return {
            "target_hours": float(total_target.quantize(Decimal('0.01'))),
            "actual_hours": float(total_actual.quantize(Decimal('0.01'))),
            "overtime": float(overtime.quantize(Decimal('0.01'))),
            "carryover_hours": float(carryover_hours.quantize(Decimal('0.01'))),
        }

    # Fetch holidays in range (#204: use the preloaded tenant+year set if given).
    if holidays is not None:
        holiday_dates: set = holidays
    else:
        holiday_dates = {
            h.date for h in db.query(PublicHoliday).filter(
                PublicHoliday.date >= start,
                PublicHoliday.date <= end,
                PublicHoliday.tenant_id == user.tenant_id,
            ).all()
        }

    # Fetch absences in range (exclude TRAINING, SICK, OVERTIME - same as
    # get_monthly_target). PAID_LEAVE (#145) is treated like OTHER and falls
    # through this filter, so it reduces the target like a normal absence day.
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.date >= start,
        Absence.date <= end,
        Absence.type.notin_([AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME]),
    ).all()
    # Fix #1: half-day-aware map (full day → skip, half day → halve Soll).
    absence_half_map: Dict[date, bool] = _soll_reducing_absence_half_map(absences)
    # F1 (1.18.0): siehe worked_hours_map (Parität zu get_overtime_account — die
    # History muss bitgleich zum Konto bleiben).
    worked_map = worked_hours_map(db, user, absence_half_map)

    # Fetch working hours changes (pre-loaded for the per-day loop).
    # F-027: routed through get_weekly_hours_for_date() with in-memory path.
    # #204: use the passed-in list if given (users-overview preload).
    if wh_changes is None:
        wh_changes = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user.id,
            WorkingHoursChange.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
        ).order_by(WorkingHoursChange.effective_from).all()

    # #146: special-day config for the YTD year (24./31.12. always fall in
    # the same `year`, so a single lookup suffices).
    special_day_config = special_days_service.get_special_day_config(
        db, user.tenant_id, year
    )

    # Sum daily targets
    total_target = Decimal('0')
    current = start
    while current <= end:
        if (current.weekday() < 5
                and _within_employment_window(user, current)):  # #193
            # Fix #1: holiday / soll-reducing absence (full vs. half day) + #146
            # special-day factor via the shared per-day helper.
            total_target += _day_soll_contribution(
                db, user, current,
                holiday_dates=holiday_dates,
                absence_half_map=absence_half_map,
                wh_changes=wh_changes,
                special_cfg=special_day_config,
                worked_map=worked_map,
            )
        current += timedelta(days=1)

    # Sum actual hours (time entries + credited absence hours: training + sick)
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.date >= start,
        TimeEntry.date <= end,
    ).all()
    # #195: count Ist only within the employment window (symmetric to the Soll
    # loop above) — avoids phantom YTD overtime from out-of-window entries.
    total_actual = sum((Decimal(str(e.net_hours)) for e in entries
                        if _within_employment_window(user, e.date)), start=Decimal('0'))

    credited_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
        Absence.date >= start,
        Absence.date <= end,
        Absence.type.in_([AbsenceType.TRAINING, AbsenceType.SICK]),
    ).all()
    # Audit 2026-07-31 (Fund K): die Gutschrift folgt der Soll-Struktur des Tages
    # (Wochenende/Feiertag 0, Sondertag mit dem #146-Faktor) — dieselbe
    # ``holiday_dates``/``special_day_config``-Quelle wie die Soll-Schleife oben.
    total_actual += sum((Decimal(str(a.hours))
                         * credit_day_weight(a.date, holiday_dates, special_day_config)
                         for a in credited_absences
                         if _within_employment_window(user, a.date)), start=Decimal('0'))

    # Include overtime carryover for this year
    carryover = db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id,
        YearCarryover.year == year,
    ).first()
    carryover_hours = Decimal(str(carryover.overtime_hours)) if carryover else Decimal('0')

    overtime = total_actual - total_target + carryover_hours

    return {
        "target_hours": float(total_target.quantize(Decimal('0.01'))),
        "actual_hours": float(total_actual.quantize(Decimal('0.01'))),
        "overtime": float(overtime.quantize(Decimal('0.01'))),
        "carryover_hours": float(carryover_hours.quantize(Decimal('0.01'))),
    }


def half_special_day_weight(d: date, special_cfg: dict) -> Decimal:
    """#394: Tage-Kosten-Gewicht EINES Tages für die tagebasierte Urlaubs-/Absenz-
    Zählung. ``Decimal('0.5')`` wenn ``d`` als „halber Feiertag" (24./31.12.,
    ``special_day_target_factor == 0,5``) konfiguriert ist, sonst ``Decimal('1')``.

    DIE eine Quelle für alle tagebasierten Urlaubs-/Absenz-Kosten — ``get_vacation_
    account``, ``absence_days``, ``closure_split_service`` UND die Budget-Pre-Checks
    (absences/admin_vacations/vacation_requests/admin_change_requests). So kann die
    #394-Halbtags-Regel nie wieder zwischen den Buchungspfaden divergieren (der
    Re-Split + die Pre-Checks hatten den Faktor zunächst NICHT — Release-Review 1.14.3).
    ``special_cfg`` ist die je Jahr geladene ``get_special_day_config``-Map.
    """
    f = special_days_service.special_day_target_factor(d, special_cfg)
    return Decimal('0.5') if (f is not None and f == Decimal('0.5')) else Decimal('1')


def absence_days(db: Session, user: User, absences: list,
                 wh_changes: Optional[List[WorkingHoursChange]] = None) -> Decimal:
    """Zähle Abwesenheiten TAGEBASIERT (Tagesprinzip §3 BUrlG, #156/#205) — exakt
    nach derselben Regel wie ``used_days`` in ``get_vacation_account``: voller Tag
    = 1,0, ``half_day=True`` = 0,5, Legacy-Row (``half_day=None``) = Stunden ÷
    Tagessoll DES TAGES. Ein Tag mit Tagessoll 0 (Urlaub an einem Nicht-Arbeitstag)
    zählt 0. Untracked-MA (``get_daily_target<=0``, leitende Angestellte): rein
    tagebasiert (Halbtag 0,5, sonst 1,0). Quelle für die Tage-Anzeige in den
    Reports — NICHT die naive Σh ÷ Ø-Tagessoll (die für ungleichmäßige Tagespläne
    bzw. Halbtage falsch ist)."""
    tracked = get_daily_target(user) > 0
    total = Decimal('0')
    # #394: Halbtags-Sondertag (24./31.12.) → ein Absenz-Tag darauf zählt 0,5
    # (halber Arbeitstag). Config lazy je Jahr (Liste kann jahresübergreifend sein).
    _sd_cfg: dict = {}

    def _weight(d: date) -> Decimal:
        cfg = _sd_cfg.get(d.year)
        if cfg is None:
            cfg = special_days_service.get_special_day_config(db, user.tenant_id, d.year)
            _sd_cfg[d.year] = cfg
        return half_special_day_weight(d, cfg)

    for a in absences:
        if not tracked:
            base = Decimal('0.5') if a.half_day else Decimal('1')
            total += base * _weight(a.date)
            continue
        dt_day = get_daily_target_for_date(user, a.date, get_schedule_for_date(db, user, a.date, wh_changes=wh_changes))
        if dt_day > 0:
            if a.half_day is None:
                total += Decimal(str(a.hours)) / Decimal(str(dt_day))
            else:
                base = Decimal('0.5') if a.half_day else Decimal('1')
                total += base * _weight(a.date)
    return total


def child_sick_cap(db: Session, user: User) -> int:
    """#376 §45 SGB V: persönlicher Kind-krank-Jahresanspruch in Tagen.
    per-MA-Feld → Tenant-Setting child_sick_days_default → 15."""
    if user.child_sick_days_per_year is not None:
        return int(user.child_sick_days_per_year)
    return settings_service.get_int_setting(db, "child_sick_days_default", user.tenant_id, 15)


def child_sick_days_used(db: Session, user: User, year: int,
                         wh_changes: Optional[List[WorkingHoursChange]] = None) -> Decimal:
    """#376: tagebasierte Summe (Tagesprinzip) der Kind-krank-Absencen im
    Kalenderjahr — nur Absencen, deren Grund tracks_child_sick_limit trägt.
    Beschäftigungsfenster wird respektiert; Zählregel identisch zu absence_days."""
    rows = (
        db.query(Absence)
        .join(AbsenceReason, Absence.reason_id == AbsenceReason.id)
        .filter(
            Absence.tenant_id == user.tenant_id,          # F-026
            Absence.user_id == user.id,
            AbsenceReason.tenant_id == user.tenant_id,     # F-026 (Join)
            AbsenceReason.tracks_child_sick_limit.is_(True),
            Absence.date >= date(year, 1, 1),
            Absence.date <= date(year, 12, 31),
        )
        .all()
    )
    windowed = [a for a in rows if _within_employment_window(user, a.date)]
    return absence_days(db, user, windowed, wh_changes=wh_changes)


def get_vacation_account(
    db: Session,
    user: User,
    year: int,
    holidays: Optional[set] = None,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> Dict:
    """
    Calculate vacation account for a given year.

    #204: ``holidays`` (das tenant+year-PublicHoliday-Datumsset) und ``wh_changes``
    (die WorkingHoursChange-Liste DIESES Users) sind optionale Preloads für den
    users-overview-Hot-Loop. Default ``None`` = wie bisher pro Aufruf querien →
    byte-identische Ergebnisse (Test ``test_calc_preload``).

    Returns:
        budget_hours: Total vacation budget in hours (vacation_days × daily_target)
        budget_days: Total vacation days from user config
        used_hours: Hours of vacation taken
        used_days: Days of vacation taken (used_hours / daily_target)
        remaining_hours: Remaining vacation hours
        remaining_days: Remaining vacation days

    NOTE: Uses CURRENT weekly hours for conversion between days and hours.
    This ensures consistent display even if hours changed during the year.

    Args:
        db: Database session
        user: User object
        year: Year to calculate for

    Returns:
        Dict with vacation account details
    """
    # daily_target == 0 means the user has no Soll/Ist tracking
    # (track_hours=False, e.g. leitende Angestellte) or work_days_per_week == 0.
    # Such users still get a DAY-BASED vacation account — they are NOT shortcut
    # here. The pure day count happens further down (reine Tageszählung, hours
    # stay 0); the day-based budget below is shared with tracked users.
    # (Replaces the old F-046 "not applicable" zero shape, which made the
    # tagebasierte Budget-Check ins Leere laufen — Über-Buchung war möglich.)
    daily_target = get_daily_target(user)

    # Calculate budget in hours, pro-rated for first/last work day
    budget_days = Decimal(str(user.vacation_days))
    first_in_year = user.first_work_day and user.first_work_day.year == year
    last_in_year = user.last_work_day and user.last_work_day.year == year
    # Fix #1: a year that lies ENTIRELY outside the employment window grants no
    # budget. The pro-rata branches below only cover the entry/exit YEAR and have
    # no `else`, so without this guard a departed employee kept the full
    # `vacation_days` in every year AFTER last_work_day (and a future hire in
    # every year BEFORE first_work_day) — phantom budget that even flowed into
    # the carryover (double entitlement).
    year_outside_window = bool(
        (user.last_work_day and user.last_work_day.year < year)
        or (user.first_work_day and user.first_work_day.year > year)
    )
    if year_outside_window:
        budget_days = Decimal('0')
    elif first_in_year and last_in_year:
        # Eintritt UND Austritt im selben Jahr: Beschäftigungsdauer ist die echte
        # Überlappung beider Grenzen (nicht min() zweier einseitiger Pro-Ratas).
        # employed_months = months_remaining + months_worked − 12  (≥ 0)
        fwd = user.first_work_day
        fwd_days_in_month = monthrange(fwd.year, fwd.month)[1]
        fwd_days_remaining = fwd_days_in_month - fwd.day + 1  # inklusive Starttag
        months_remaining = (Decimal(str(12 - fwd.month))
                            + Decimal(str(fwd_days_remaining)) / Decimal(str(fwd_days_in_month)))
        lwd = user.last_work_day
        lwd_days_in_month = monthrange(lwd.year, lwd.month)[1]
        lwd_days_worked = lwd.day  # inklusive letzten Tag
        months_worked = (Decimal(str(lwd.month - 1))
                         + Decimal(str(lwd_days_worked)) / Decimal(str(lwd_days_in_month)))
        employed_months = max(Decimal('0'), months_remaining + months_worked - Decimal('12'))
        budget_days = (Decimal(str(user.vacation_days)) * employed_months / Decimal('12')).quantize(Decimal('0.1'))
    elif first_in_year:
        fwd = user.first_work_day
        days_in_month = monthrange(fwd.year, fwd.month)[1]
        days_remaining = days_in_month - fwd.day + 1  # inklusive Starttag
        # Vollständige Monate nach Startmonat + Anteil des Startmonats
        months_remaining = Decimal(str(12 - fwd.month)) + Decimal(str(days_remaining)) / Decimal(str(days_in_month))
        budget_days = (Decimal(str(user.vacation_days)) * months_remaining / Decimal('12')).quantize(Decimal('0.1'))
    elif last_in_year:
        lwd = user.last_work_day
        days_in_month = monthrange(lwd.year, lwd.month)[1]
        days_worked = lwd.day  # inklusive letzten Tag
        # Vollständige Monate vor Endmonat + Anteil des Endmonats
        months_worked = Decimal(str(lwd.month - 1)) + Decimal(str(days_worked)) / Decimal(str(days_in_month))
        budget_days = (Decimal(str(user.vacation_days)) * months_worked / Decimal('12')).quantize(Decimal('0.1'))
    # Add carryover vacation days from previous year — but only for a year the
    # employee was (at least partly) employed. An out-of-window year gets zero
    # budget and must not inherit a carryover either (Fix #1).
    if not year_outside_window:
        carryover = db.query(YearCarryover).filter(
            YearCarryover.user_id == user.id,
            YearCarryover.year == year,
        ).first()
        carryover_days = Decimal(str(carryover.vacation_days)) if carryover else Decimal('0')
        budget_days += carryover_days

    budget_hours = budget_days * daily_target

    # Calculate used vacation hours (F-033: sargable date range).
    # Only VACATION deducts the budget. PAID_LEAVE (#145) is paid leave like a
    # holiday and is intentionally NOT counted here, so a Betriebsferien booked
    # as bezahlte Freistellung leaves the vacation budget untouched.
    vacation_absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.type == AbsenceType.VACATION,
        date_in_year(Absence.date, year),
    ).all()
    # Audit 2026-07-31 (Fund B): #193-Beschaeftigungsfenster — dieselbe Funktion
    # wandte es bis hier DREIMAL an (Budget-Pro-rata oben, freie Sondertage in
    # beiden Zweigen unten) und auf der Schleife ueber die echten Urlaubszeilen
    # NICHT. Erreichbar im Regelbetrieb: ``admin_users.update_user`` setzt
    # ``last_work_day`` und raeumt KEINE Abwesenheiten ab — im Maerz Urlaub fuer
    # Juli genehmigt, im Mai Kuendigung zum 30.06. Das Budget wurde dann korrekt
    # auf 15 Tage anteilig gekuerzt, die fuenf Juli-Tage aber trotzdem als
    # verbraucht gezaehlt: Resturlaub 10 statt 15. Das ist die Grundlage der
    # Urlaubsabgeltung (§ 7 Abs. 4 BUrlG, also Geld) und geht ueber den
    # Jahresabschluss in den Uebertrag. Die Soll-Seite
    # (``get_monthly_target``) kannte das Fenster laengst — ein Monat, fuer den
    # gar kein Soll mehr entsteht, kann keinen Urlaub verbrauchen.
    # Der Filter steht VOR beiden Verbrauchszweigen (tracked + untracked/#191)
    # und speist auch ``existing_vacation_dates``; die Sondertags-Schleifen
    # darunter blenden dieselben Daten ueber ihre eigenen Fenster-Guards aus,
    # die Entdopplung bleibt also intakt.
    vacation_absences = [a for a in vacation_absences if _within_employment_window(user, a.date)]

    # #156/T2 — Tagesprinzip (§3 BUrlG, BAG): der Urlaubsverbrauch wird in
    # TAGEN gezählt, nicht als Stundensumme ÷ Durchschnitts-Tagessoll. Jeder
    # Urlaubstag zählt als Anteil seines EIGENEN Tagessolls (voller Tag = 1,0;
    # Halbtag = 0,5) — unabhängig vom Wochentag. Das verhindert, dass ein
    # Montag-Urlaub (z. B. 8h) mehr kostet als ein Dienstag-Urlaub (z. B. 3h)
    # bei ungleichmäßigem Tagesplan. Die Stundensumme bleibt nur informativ.
    # #394: config der Halbtags-Sondertage (24./31.12.) — ein Urlaubstag an einem
    # solchen Tag ist nur ein halber Arbeitstag und kostet daher 0,5 (§3 BUrlG).
    # Für alle anderen Tage bleibt der Faktor 1,0 → byte-identisch zur Altlogik.
    special_cfg_vac = special_days_service.get_special_day_config(db, user.tenant_id, year)
    used_hours = Decimal('0')
    used_days = Decimal('0')
    for a in vacation_absences:
        h = Decimal(str(a.hours))
        used_hours += h
        dt_day = get_daily_target_for_date(user, a.date, get_schedule_for_date(db, user, a.date, wh_changes=wh_changes))
        # §3 BUrlG / Tagesprinzip: Urlaub an einem NICHT-Arbeitstag des MA
        # (dt_day == 0, z. B. Di/Do bei einer Mo/Mi/Fr-Kraft) verbraucht 0 Urlaubs-
        # tage — das Überspringen ist gewollt, KEIN Buchungsverlust (Funktions-
        # Review 2026-06-17 verifiziert).
        if dt_day > 0:
            if a.half_day is None:
                # #205: Legacy-Row (vor dem half_day-Feld) — tagebasierte Info
                # fehlt, daher wie bisher Stunden ÷ (live) Tagessoll. Das driftet
                # nur im seltenen Fall einer NACHTRAEGLICHEN WorkingHoursChange auf
                # ein bereits gebuchtes Datum (ohne gespeicherte Buchungszeit nicht
                # rekonstruierbar — bewusst kein unzuverlaessiges Raten).
                used_days += (h / Decimal(str(dt_day)))
            else:
                # #205: tagebasiert (Voll-Tag 1,0; Halbtag 0,5) — unabhaengig von
                # spaeteren Aenderungen des Tagessolls (kein Drift mehr).
                # #394: × 0,5 an einem Halbtags-Sondertag (zentraler Helper).
                base = Decimal('0.5') if a.half_day else Decimal('1')
                used_days += base * half_special_day_weight(a.date, special_cfg_vac)

    # #146: a special day (24./31.12.) configured as `free` + counts_as_vacation
    # consumes one vacation day too. We account for it non-invasively here
    # (no generated Absence rows): each such day is one full vacation day,
    # unless the employee already has a real VACATION absence on that day
    # (already counted above) or it falls outside their employment window.
    # Weekends / existing holidays are excluded inside the helper.
    holiday_dates_year = holidays if holidays is not None else {
        h.date for h in db.query(PublicHoliday).filter(
            date_in_year(PublicHoliday.date, year),
            PublicHoliday.tenant_id == user.tenant_id,
        ).all()
    }
    deduction_dates = special_days_service.vacation_deduction_dates_for_year(
        db, user.tenant_id, year, holiday_dates_year
    )
    existing_vacation_dates = {a.date for a in vacation_absences}

    # #189 / leitende Angestellte: a user without hours tracking
    # (daily_target == 0) gets a pure DAY count — each VACATION absence day is
    # one vacation day, each 'free'+counts_as_vacation special day (24./31.12.)
    # is one vacation day, and all hour figures stay 0. Budget (budget_days)
    # follows the normal pro-rata + carryover logic above — "sonst wie ein
    # normaler MA".
    # #205: Halbtage werden jetzt unterschieden — half_day=True zaehlt 0,5 (passt
    # zum 0,5-Vorab-Budgetcheck). Legacy-Rows (half_day=None, vor dem Feld) und
    # Voll-Tage zaehlen 1,0 wie bisher.
    if daily_target <= 0:
        # #394: halber Feiertag (24./31.12.) → 0,5 (auch für untracked/leitende).
        used_days = sum(
            ((Decimal('0.5') if a.half_day else Decimal('1'))
             * half_special_day_weight(a.date, special_cfg_vac)
             for a in vacation_absences),
            Decimal('0'),
        )
        for d in deduction_dates:
            if d in existing_vacation_dates:
                continue
            if user.first_work_day and d < user.first_work_day:
                continue
            if user.last_work_day and d > user.last_work_day:
                continue
            used_days += Decimal('1')
        return {
            "budget_hours": 0.0,
            "budget_days": float(budget_days),
            "used_hours": 0.0,
            "used_days": float(used_days.quantize(Decimal('0.1'))),
            "remaining_hours": 0.0,
            "remaining_days": float((budget_days - used_days).quantize(Decimal('0.1'))),
            "track_hours": False,  # sentinel for callers (hide hours columns)
        }

    for d in deduction_dates:
        if d in existing_vacation_dates:
            continue  # already counted via a real VACATION absence
        if user.first_work_day and d < user.first_work_day:
            continue
        if user.last_work_day and d > user.last_work_day:
            continue
        schedule = get_schedule_for_date(db, user, d, wh_changes=wh_changes)
        dt_day = get_daily_target_for_date(user, d, schedule)
        if dt_day <= 0:
            continue
        used_hours += Decimal(str(dt_day))
        used_days += Decimal('1')  # ein freier Sondertag = 1 Urlaubstag

    # Calculate remaining — days are authoritative (Tagesprinzip); hours informativ.
    remaining_days = budget_days - used_days
    remaining_hours = budget_hours - used_hours

    return {
        "budget_hours": float(budget_hours.quantize(Decimal('0.01'))),
        "budget_days": float(budget_days),
        "used_hours": float(used_hours.quantize(Decimal('0.01'))),
        "used_days": float(used_days.quantize(Decimal('0.1'))),
        "remaining_hours": float(remaining_hours.quantize(Decimal('0.01'))),
        "remaining_days": float(remaining_days.quantize(Decimal('0.1'))),
        "track_hours": True,
    }


def count_workdays(db: Session, start: date, end: date, tenant_id=None) -> int:
    """Count weekdays (Mon-Fri) excluding public holidays between start and end (inclusive).

    F-026: pass ``tenant_id`` to scope the holiday lookup explicitly (belt-and-
    suspenders on top of RLS). When omitted the query relies on RLS alone.
    """
    years: set = set()
    cur = start
    while cur <= end:
        years.add(cur.year)
        cur += timedelta(days=1)

    holidays: set = set()
    for year in years:
        q = db.query(PublicHoliday).filter(PublicHoliday.year == year)
        if tenant_id is not None:
            q = q.filter(PublicHoliday.tenant_id == tenant_id)
        year_holidays = q.all()
        holidays.update(h.date for h in year_holidays)

    count = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5 and cur not in holidays:
            count += 1
        cur += timedelta(days=1)
    return count


def closed_years_in_range(db: Session, tenant_id, years) -> List[int]:
    """Return, ascending, every year Y in ``years`` whose Jahresabschluss was
    already done — i.e. a ``YearCarryover`` for Y+1 exists in the tenant.

    This is THE definition of "closed year" shared by ``stale_year_closing_warning``
    (single-year warning text) and any caller that needs the full list (e.g. the
    working-hours-change preview's ``closed_years`` field) — kept in one place so
    both stay consistent.
    """
    return sorted({
        y for y in years
        if db.query(YearCarryover.id).filter(
            YearCarryover.tenant_id == tenant_id,
            YearCarryover.year == y + 1,
        ).first() is not None
    })


def closed_year_warning_text(closed_years: List[int]) -> Optional[str]:
    """Build the German warning string naming the EARLIEST year in
    ``closed_years`` (empty/falsy -> no warning). Pure/no DB access — split out
    of ``stale_year_closing_warning`` so callers that already computed the full
    list via ``closed_years_in_range`` don't need a second DB round-trip to get
    the display text.
    """
    if not closed_years:
        return None
    y = closed_years[0]
    return (
        f"Jahresabschluss {y} bereits erfolgt — Carryover {y + 1} ist nun "
        f"veraltet, bitte Jahresabschluss erneut ausführen."
    )


def stale_year_closing_warning(db: Session, tenant_id, years) -> Optional[str]:
    """Fix #5: warn (non-destructively) when a retroactive change touches a year
    whose Jahresabschluss was already done.

    A year ``Y`` counts as closed when a ``YearCarryover`` for ``Y+1`` exists in
    the tenant (see ``closed_years_in_range``). After a retroactive storno /
    closure deletion the frozen carryover ``Y+1`` is now stale. We deliberately
    do NOT recompute it (that could overwrite manual adjustments) — we only
    return a German warning string naming the EARLIEST affected closed year so
    the caller can surface it. Returns None when no touched year was closed.
    """
    return closed_year_warning_text(closed_years_in_range(db, tenant_id, years))


def create_year_closing(db: Session, year: int, users: list) -> list:
    """
    Create year-end closing for all given users.

    For each user, calculates the cumulative overtime balance at Dec 31
    and the remaining vacation days, then creates/updates a YearCarryover
    record for year+1.

    Args:
        db: Database session
        year: The year being closed (carryovers are created for year+1)
        users: List of User objects

    Returns:
        List of dicts with user info and carryover values
    """
    next_year = year + 1
    results = []

    for user in users:
        # Calculate overtime balance at end of year
        overtime_balance = get_overtime_account(db, user, year, 12)

        # Calculate remaining vacation days
        vacation_account = get_vacation_account(db, user, year)
        remaining_vacation = Decimal(str(vacation_account['remaining_days']))

        # Create or update carryover for next year (F-026: explicit tenant scope)
        carryover = db.query(YearCarryover).filter(
            YearCarryover.user_id == user.id,
            YearCarryover.tenant_id == user.tenant_id,
            YearCarryover.year == next_year,
        ).first()

        if carryover:
            carryover.overtime_hours = overtime_balance
            carryover.vacation_days = remaining_vacation
            # Fix #7: the year-closing owns this row (so delete_year_closing may
            # remove it) — even if it previously existed as a manual entry.
            carryover.source = "year_closing"
        else:
            carryover = YearCarryover(
                user_id=user.id,
                tenant_id=user.tenant_id,
                year=next_year,
                overtime_hours=overtime_balance,
                vacation_days=remaining_vacation,
                source="year_closing",  # Fix #7
            )
            db.add(carryover)

        results.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "overtime_hours": float(overtime_balance),
            "vacation_days": float(remaining_vacation.quantize(Decimal('0.1'))),
        })

    db.commit()
    return results
