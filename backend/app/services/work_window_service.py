"""Arbeitszeit-Blöcke (Spec 2026-10-08, Abschnitt 6) — kappt das Ist beim Schreiben.

Quelle sind die Blöcke des DATUMSAUFGELÖSTEN Vertrags-Snapshots
(``calculation_service.get_schedule_for_date``), nie ein Live-Feld der
User-Zeile. Altfenster aus Migration 073 sind Einblock-Tage und kappen exakt wie
die früheren #201-Fenster (Hülle). Zeit zwischen zwei Blöcken wird nicht
angerechnet (``uncredited_minutes``); der Beginn wird nie in eine Lücke
verschoben (E33), nur die Hülle verschiebt Beginn/Ende und bewahrt den
Rohstempel (§16, §5).

Keine Kappung an Wochenenden, Feiertagen und freien Sondertagen (#484), bei
``track_hours=False`` und für anerkannte Einträge (``credit_override``).
"""
from datetime import date, time
from decimal import Decimal
from typing import Any, NamedTuple, Optional

from sqlalchemy.orm import Session

from app.models import TimeEntry, WorkingHoursChange
from app.models.system_setting import SystemSetting
from app.services import calculation_service

DEFAULT_GRACE_MINUTES = 15
_LAST_MINUTE = 23 * 60 + 59
# Gesamtreview 1.20 (Fund 11): Obergrenze des Puffers = ein ganzer Tag. Ab hier
# reicht die Hülle von 00:00 bis 23:59 und jede Lücke verschwindet; ein größerer
# Puffer kappt nicht anders. Er sprengte aber die int4-Spalte
# ``time_entries.clamp_grace_minutes`` (PG 22003 → 500 bei jedem Stempeln).
MAX_GRACE_MINUTES = _LAST_MINUTE
# #462: Kennung der weichen Warnung ("CODE: Text", läuft durch showArbzgWarnings).
CLAMP_WARNING_CODE = "WORK_WINDOW_CLAMPED"
# P18: Ende, mit dem der Auto-Close einen offenen Eintrag schließt — ein
# synthetischer Wert, nie ein Stempel (``time_entries._close_stale_entry``,
# ``end_input_for``).
AUTO_CLOSE_RAW_END = time(23, 59)
# Spec 6.2 / P21: nur Mitarbeiterpfade, nur an Lückentexten geschlossener Einträge.
EMPLOYEE_CREDIT_HINT = (
    " Haben Sie in dieser Zeit gearbeitet, beantragen Sie die Anrechnung "
    "(Zeiterfassung → Eintrag → „Anrechnung beantragen“)."
)


class ClampResult(NamedTuple):
    eff_start: Optional[time]
    eff_end: Optional[time]
    raw_start: Optional[time]
    raw_end: Optional[time]
    uncredited_minutes: int
    grace_minutes: Optional[int]   # angewandter Puffer; None = nicht gegen Blöcke gekappt (E79)


def get_grace_minutes(db: Session, tenant_id) -> int:
    """work_window_grace_minutes aus system_settings (Default 15, 0 bis
    ``MAX_GRACE_MINUTES``). Die Obergrenze greift auch für einen vor der
    Eingabeprüfung gespeicherten Altwert – er kappt wie ein ganzer Tag."""
    s = db.query(SystemSetting).filter(
        SystemSetting.key == "work_window_grace_minutes",
        SystemSetting.tenant_id == tenant_id,
    ).first()
    if not s:
        return DEFAULT_GRACE_MINUTES
    try:
        return min(max(0, int(s.value)), MAX_GRACE_MINUTES)
    except (TypeError, ValueError):
        return DEFAULT_GRACE_MINUTES


def grace_for_entry(db: Session, entry) -> int:
    """Puffer für die Einzel-Neukappung eines GESPEICHERTEN Eintrags (E80): der
    bei der letzten Kappung gespeicherte Wert, sonst (Bestand vor 073 / nie
    gegen Blöcke gekappt) der aktuelle Mandanten-Puffer."""
    if entry.clamp_grace_minutes is not None:
        return entry.clamp_grace_minutes
    return get_grace_minutes(db, entry.tenant_id)


def _is_soll_free_weekday(db: Session, user, d: date) -> bool:
    """#484: Feiertag des Mandanten oder als ``free`` konfigurierter Sondertag."""
    from app.services.holiday_service import is_holiday
    from app.services.special_days_service import free_special_days_in_range

    tenant_id = getattr(user, "tenant_id", None)
    if is_holiday(db, d, tenant_id=tenant_id):
        return True
    return d in free_special_days_in_range(db, tenant_id, d, d)


def _min(t: time) -> int:
    return t.hour * 60 + t.minute


def same_minute(a: Optional[time], b: Optional[time]) -> bool:
    """Minutengenauer Vergleich zweier Uhrzeiten (``None`` gleicht nur ``None``).

    Alle Zeitrechnungen arbeiten minutengenau (``_min``). Review Task 6 (PR2):
    ein exakter Vergleich ließ „23:59:30" — in der Oberfläche „23:59" — an
    jeder Sperre für das synthetische 23:59 vorbei (``end_is_correction``,
    ``end_input_for``, ``credit_override_service.lacks_actual_end``);
    Anerkennen rechnete danach bis 23:59:30 an. Seit dem Gesamtreview 1.20
    (B1) schneiden die Eingangsschemata Sekunden ab
    (``schemas.validators.MinuteTime``); der minutengenaue Vergleich bleibt für
    gespeicherte Altwerte (z. B. Anträge vor 1.20)."""
    if a is None or b is None:
        return a is b
    return _min(a) == _min(b)


def _t(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def _shift_min(minutes: int, delta: int) -> int:
    """Auf [00:00, 23:59] des Tages begrenzt (wie das frühere ``_shift``)."""
    return max(0, min(minutes + delta, _LAST_MINUTE))


def _hhmm(t: Optional[time]) -> str:
    return t.strftime("%H:%M") if t else "?"


def _mm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _hm(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def _overlap(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def get_scheduled_blocks(db: Session, user, d: date, *, wh_changes=None,
                         soll_free_dates=None) -> list:
    """Blöcke des Datums in Minuten seit Mitternacht, sortiert.

    ``[]`` am Wochenende, ohne Blöcke im datumsaufgelösten Snapshot, an
    Feiertagen und an freien Sondertagen (#484). Arbeit dort ist eine Ausnahme
    (§10 ArbZG, z. B. Notdienst), keine verschobene Regelarbeitszeit — bis 1.19.2
    bekam ein Feiertag auf einem Werktag das Fenster seines Wochentags, und ein
    KV-Dienst am Ostermontag wurde gekappt, derselbe Dienst am Sonntag nicht.
    Ein ``half_day``-Sondertag hat ein Soll und behält seine Blöcke.

    ``db`` ist Pflicht, damit eine übersehene Aufrufstelle laut scheitert,
    statt Feiertage still weiter zu kappen. ``wh_changes`` /
    ``soll_free_dates``: optional vorgeladen (Muster #449); ohne sie fragt die
    Funktion je Aufruf den Resolver bzw. die Feiertage ab."""
    if d.weekday() > 4:
        return []
    sched = calculation_service.get_schedule_for_date(db, user, d, wh_changes)
    if sched.blocks is None or not sched.blocks[d.weekday()]:
        return []
    if soll_free_dates is not None:
        if d in soll_free_dates:
            return []
    elif _is_soll_free_weekday(db, user, d):
        return []
    return list(sched.blocks[d.weekday()])


def has_blocks(db: Session, user, d: date, **preload) -> bool:
    return bool(get_scheduled_blocks(db, user, d, **preload))


def clamp_applies(db: Session, user, d: date, *, credit_override: bool, **preload) -> bool:
    """Kappt ``clamp`` an diesem Tag überhaupt? (XLS-Gate, E38 — statt
    ``has_blocks`` allein, sonst löschte ``track_hours=False`` + Blöcke ein
    mitgeliefertes ``raw_*``.)"""
    return (
        user is not None
        and bool(getattr(user, "track_hours", True))
        and not credit_override
        and has_blocks(db, user, d, **preload)
    )


def credit_gaps(blocks, grace: int) -> list:
    """Innere Lücken, um den Puffer an BEIDEN Rändern geschrumpft (E5).
    Eine Lücke ≤ 2 × Puffer verschwindet."""
    gaps = []
    for (_, end_a), (start_b, _) in zip(blocks, blocks[1:]):
        gs, ge = end_a + grace, start_b - grace
        if ge > gs:
            gaps.append((gs, ge))
    return gaps


def _clamp_core(db, user, d, start, end, grace, *, credit_override, wh_changes, soll_free_dates):
    if credit_override or user is None or not getattr(user, "track_hours", True):
        return ClampResult(start, end, None, None, 0, None), []
    blocks = get_scheduled_blocks(db, user, d, wh_changes=wh_changes, soll_free_dates=soll_free_dates)
    if not blocks:
        return ClampResult(start, end, None, None, 0, None), []

    floor = _t(_shift_min(blocks[0][0], -grace))
    ceil = _t(_shift_min(blocks[-1][1], grace))
    eff_start, eff_end, raw_start, raw_end = start, end, None, None
    # Vergleich als Uhrzeit (nicht in Minuten): exakt das Verhalten von 072
    # auch für Eingaben mit Sekunden (Kappungsparität, Spec 17.1).
    if start is not None and start < floor:
        eff_start, raw_start = floor, start
    # Platzhalter 23:59 aus 073 = kein Ende (Spec 5.3, „Kappung unverändert"):
    # unter 072 gab es ohne Soll-Ende keine Ende-Kappung, auch nicht für ein Ende
    # mit Sekunden (23:59:30). Neue Blöcke enden spätestens 23:55 (Spec 3.5) —
    # ein letzter Block bis 23:59 ist immer eine Altzeile.
    if end is not None and blocks[-1][1] < _LAST_MINUTE and end > ceil:
        eff_end, raw_end = ceil, end

    # Kollaps außerhalb der Hülle — unverändert seit #201: liegt der Eintrag ganz
    # vor [erster Block − Puffer] bzw. ganz hinter [letzter Block + Puffer],
    # werden 0 Stunden angerechnet, der Rohstempel bleibt (§16) — sonst ließe
    # sich Arbeitszeit außerhalb der Blöcke „erarbeiten" (Anti-Abuse). Punkt =
    # ``start``, damit auch ``clock_out`` (schreibt nur ``end_time``) auf 0 h
    # kommt; §5 rechnet weiter gegen die Rohstempel (``raw_* or <gekappt>``).
    if eff_start is not None and eff_end is not None and eff_start >= eff_end:
        return ClampResult(start, start, start, end, 0, grace), []
    # Offener Eintrag (P17: Hülle gilt) bzw. Teil-Update ohne Beginn: keine Lücke.
    if eff_start is None or eff_end is None:
        return ClampResult(eff_start, eff_end, raw_start, raw_end, 0, grace), []

    s, e = _min(eff_start), _min(eff_end)
    segments = [o for o in (_overlap(s, e, gs, ge) for gs, ge in credit_gaps(blocks, grace)) if o > 0]
    return ClampResult(eff_start, eff_end, raw_start, raw_end, sum(segments), grace), segments


def clamp(db: Session, user, d: date, start: Optional[time], end: Optional[time], grace: int,
          *, credit_override: bool, wh_changes=None, soll_free_dates=None) -> ClampResult:
    """Spec 6.1. ``credit_override`` ist pflichtiges Schlüsselwort (P6): jede
    Aufrufstelle entscheidet ausdrücklich. Der Aufrufer bestimmt ``grace``
    (E80): aktueller Mandanten-Puffer bei Neuanlage, ``grace_for_entry`` bei
    Einzel-Neukappung eines gespeicherten Eintrags."""
    return _clamp_core(db, user, d, start, end, grace, credit_override=credit_override,
                       wh_changes=wh_changes, soll_free_dates=soll_free_dates)[0]


def gap_segments(db: Session, user, d: date, start: Optional[time], end: Optional[time], grace: int,
                 *, credit_override: bool, wh_changes=None, soll_free_dates=None) -> list:
    """Die Überlappungen mit den Lücken je Lücke (für §4, XLS-Auto-Pause).
    Invariante: ``sum(gap_segments(...)) == clamp(...).uncredited_minutes``."""
    return _clamp_core(db, user, d, start, end, grace, credit_override=credit_override,
                       wh_changes=wh_changes, soll_free_dates=soll_free_dates)[1]


def _hull_sentence(teile, grace) -> str:
    # Byte-identisch zu 1.19 (in der Doku zitiert) — ASCII-Umschrift bleibt.
    return (
        f"Die eingetragene Zeit wurde auf das hinterlegte Arbeitszeit-Fenster "
        f"gekappt ({', '.join(teile)}; Puffer {grace} Minuten). "
        f"Angerechnet wird die gekappte Zeit; die urspruengliche Eingabe bleibt "
        f"als Rohstempel gespeichert."
    )


def clamp_warning_text(db: Session, user, d: date, result: ClampResult, *,
                       for_employee: bool) -> Optional[str]:
    """Klartext der Kappungs-Warnung (Spec 6.2) — oder None.

    DIE eine Quelle des Textes (#462): ``clamp`` wird an vielen Stellen
    aufgerufen (Stempeln, manuelles Anlegen/Bearbeiten in beiden Rollen,
    Genehmigung eines Änderungsantrags, XLS-Import) — ein zweiter Nachbau je
    Aufrufer wäre genau das Muster, das in diesem Projekt schon mehrfach
    auseinandergelaufen ist. Der genannte Puffer ist der tatsächlich
    angewandte (``result.grace_minutes``, E80). ``db``/``user``/``d`` werden nur
    gelesen, wenn eine Lücke aufzulösen ist. Ohne Code-Präfix, weil die
    Zeilen-Warnungen der XLS-Vorschau als Klartext im Tooltip stehen."""
    if result.grace_minutes is None:
        return None
    g = result.grace_minutes
    es, ee, rs, re_ = result.eff_start, result.eff_end, result.raw_start, result.raw_end

    # Nur Seiten nennen, die sich tatsächlich verschoben haben. Im Kollaps-Fall
    # ist raw_start == eff_start — „Beginn 05:00 → 05:00" wäre eine Kappung, die
    # es nicht gab (Release-Review 1.19.1).
    teile = []
    if rs is not None and es is not None and rs != es:
        teile.append(f"Beginn {_hhmm(rs)} → {_hhmm(es)}")
    if re_ is not None and ee is not None and re_ != ee:
        teile.append(f"Ende {_hhmm(re_)} → {_hhmm(ee)}")

    if es is not None and ee is not None and es == ee:
        roh_start, roh_end = rs or es, re_ or ee
        return (
            f"Die eingetragene Zeit ({_hhmm(roh_start)}–{_hhmm(roh_end)}) liegt "
            f"vollstaendig ausserhalb des hinterlegten Arbeitszeit-Fensters "
            f"(Puffer {g} Minuten) — angerechnet werden 0 Stunden. "
            f"Die urspruengliche Eingabe bleibt als Rohstempel gespeichert."
        )

    if ee is None:  # offener Eintrag
        if teile:
            return _hull_sentence(teile, g)
        if es is None:
            return None
        s = _min(es)
        for gs, ge in credit_gaps(get_scheduled_blocks(db, user, d), g):
            if gs <= s < ge:
                return (
                    f"Eingestempelt zwischen zwei Arbeitsblöcken (Lücke {_mm(gs)}–{_mm(ge)}, "
                    f"Puffer {g} Minuten) — angerechnet wird erst ab {_mm(ge)}."
                )
        return None

    hull = _hull_sentence(teile, g) if teile else None
    if result.uncredited_minutes <= 0:
        return hull

    s, e = _min(es), _min(ee)
    hit = [(gs, ge) for gs, ge in credit_gaps(get_scheduled_blocks(db, user, d), g)
           if _overlap(s, e, gs, ge) > 0]
    spans = ", ".join(f"{_mm(gs)}–{_mm(ge)}" for gs, ge in hit)
    u = _hm(result.uncredited_minutes)
    if hit and result.uncredited_minutes >= e - s:
        gs, ge = hit[0]
        text = (
            f"Die eingetragene Zeit ({_hhmm(es)}–{_hhmm(ee)}) liegt vollständig zwischen "
            f"zwei Arbeitsblöcken (Lücke {_mm(gs)}–{_mm(ge)}, Puffer {g} Minuten) — "
            f"angerechnet werden 0 Stunden. Die gestempelte Zeit bleibt gespeichert."
        )
    elif hull:
        text = hull + f" Zusätzlich werden zwischen den Arbeitsblöcken ({spans}) {u} h nicht angerechnet."
    else:
        text = (
            f"Zwischen den Arbeitsblöcken ({spans}, Puffer {g} Minuten eingerechnet) werden "
            f"{u} h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert."
        )
    if for_employee:
        text += EMPLOYEE_CREDIT_HINT
    return text


def clamp_warning(db: Session, user, d: date, result: ClampResult, *,
                  for_employee: bool) -> Optional[str]:
    """Wie ``clamp_warning_text``, mit Code-Präfix für die ``warnings``-Fläche."""
    text = clamp_warning_text(db, user, d, result, for_employee=for_employee)
    return f"{CLAMP_WARNING_CODE}: {text}" if text else None


def unclamp_input(
    incoming: Optional[time], prev_eff: Optional[time], prev_raw: Optional[time],
) -> Optional[time]:
    """Schickt ein Formular die zuvor GEKAPPTE Zeit unveraendert zurueck, ist das
    keine Eingabe — sondern derselbe Eintrag. Dann mit dem Rohwert weiterrechnen.

    Release-Review 1.19.1: Das Bearbeiten-Formular füllt sich mit der
    angerechneten Zeit (07:45). Wer nur Notiz oder Pause ändert, schickt 07:45
    als ``start_time`` mit; ``clamp`` sah darin eine neue, bereits konforme
    Eingabe und setzte ``raw_start_time`` auf None — der echte Stempel (§16,
    Grundlage der §5-Ruhezeit) war weg. Ein echter Wechsel läuft unverändert durch."""
    if incoming is not None and prev_raw is not None and incoming == prev_eff:
        return prev_raw
    return incoming


def end_is_correction(incoming: Optional[time], prev_eff: Optional[time]) -> bool:
    """P18: Liefert eine Eingabe ein tatsächliches Ende, das das Kennzeichen
    ``auto_closed`` aufhebt? Ja, außer sie schickt das gespeicherte WIRKSAME Ende
    unverändert zurück (Formular, siehe ``unclamp_input``) — sonst höbe schon
    das Speichern einer Pause das Kennzeichen auf.

    **Entschieden 2026-10-11 (Produktinhaber):** Ein echtes Ende 23:59 muss
    eintragbar sein. Die Formulare zeigen und schicken bei ``auto_closed`` das
    wirksame Ende (z. B. 18:15), und kein Pfad füllt ein fehlendes Ende mit dem
    Rohende auf (MA-Route: Waiver-Antrag mit dem wirksamen Ende, Review Task 8;
    Verwaltungsroute: Rückfall auf das wirksame Ende). Ein 23:59 — wie jedes
    andere Ende, auch das übernommene Rohende nach einem Verschieben — kommt
    also nur aus echter Eingabe und ist eine Korrektur: das Kennzeichen fällt,
    23:59 wird ein echter Stempel (``raw_end_time``) und gegen die Hülle gekappt
    wie jedes andere Ende. Bis dahin galt ein eingereichtes Rohende pauschal als
    Echo (Review Task 8), ein echtes Ende um 23:59 ließ sich nicht eintragen.

    Grenzfall: kappt der Auto-Close das 23:59 nicht, ist das wirksame Ende
    selbst 23:59 — Tag ohne Blöcke (auch Wochenende, Feiertag, freier
    Sondertag), ``track_hours=False`` (auch mit Blöcken), halboffenes
    Altfenster (Ende-Platzhalter 23:59) oder Hülle bis 23:59 (letzter Block +
    Puffer, ``_shift_min``). Dort ist ein zurückgeschicktes 23:59 vom Echo nicht
    zu unterscheiden und bleibt Echo; ebenso ein eingetragenes Ende genau auf
    dem wirksamen Ende (z. B. 18:15). Maßgeblich ist allein „wirksames Ende
    minutengleich 23:59", nicht die Ursache (Review V1).
    Ein ``None``-Ende gilt hier als Änderung; ob ein fehlendes bzw.
    ``None``-Ende überhaupt geprüft wird, entscheidet der Aufrufer. Dieselbe
    Regel gilt in allen drei Schreibpfaden (MA-Route, Admin-Bearbeitung,
    Antragsgenehmigung) und für ``credit_override_service.lacks_actual_end``.
    Verglichen wird minutengenau (``same_minute``, Review Task 6): ein
    18:15:30 ist das wirksame Ende 18:15.

    Für die Genehmigung eines Antrags liefert ``request_end_for_approval`` die
    Eingabe: Echo ist dort auch das wirksame Ende ZUM ZEITPUNKT DES ANTRAGS."""
    return not same_minute(incoming, prev_eff)


def _request_input_for_approval(
    proposed: Optional[time], original: Optional[time], current: Optional[time],
) -> Optional[time]:
    """Echo des Antrags → aktueller wirksamer Wert (siehe
    ``request_end_for_approval``); jeder andere Wert bleibt, wie beantragt."""
    if (
        proposed is not None
        and original is not None
        and current is not None
        and same_minute(proposed, original)
    ):
        return current
    return proposed


def request_end_for_approval(
    entry, proposed_end: Optional[time], original_end: Optional[time],
) -> Optional[time]:
    """P18 (Review V1, Folgefund): das beantragte Ende eines UPDATE-Antrags, wie
    die Genehmigung es liest — Eingabe für ``lacks_actual_end`` (Vorprüfung
    „genehmigen und anerkennen"), ``end_input_for`` und ``end_is_correction``.

    Ein offener Antrag trägt das Formular-Echo des wirksamen Endes ZUM
    ZEITPUNKT DES ANTRAGS; beide Antragswege halten es als
    ``original_end_time`` fest (``change_requests.create_change_request`` und
    die §4-Rückfrage in ``time_entries.update_time_entry``). Ändert eine
    Neukappung (9.2) das wirksame Ende vor der Genehmigung, ist das Echo nicht
    mehr minutengleich mit ``entry.end_time`` — die Genehmigung hielt es für ein
    eingetragenes Ende: das Protokoll-23:59 (Grenzfall ohne Blöcke → danach
    Blöcke) bzw. das frühere wirksame Ende wurde zum Stempel, das Kennzeichen
    fiel und „genehmigen und anerkennen" rechnete bis dorthin an (Schlupfloch
    E36/E42). Deshalb gilt ein Ende minutengleich mit ``original_end`` als Echo
    und wird durch das AKTUELLE wirksame Ende ersetzt; jedes andere Ende
    bleibt, wie es beantragt wurde. Echo = wirksames Ende zum Zeitpunkt des
    Antrags ODER aktuelles wirksames Ende (das prüft ``end_is_correction``).

    Gesamtreview 1.20 (B2): gilt für JEDEN Eintrag, nicht nur beim automatisch
    geschlossenen. Ohne Kennzeichen hielt ``unclamp_input`` das veraltete Echo
    (18:15, Rohstempel 19:00, seither auf 17:15 neu gekappt) für eine neue
    Eingabe, und ``clamp`` legte 18:15 als Rohende ab — der Stempel 19:00 (§16)
    war weg. Jetzt rechnet ``end_input_for`` mit dem gespeicherten Paar weiter.
    Den Beginn liest ``request_start_for_approval`` nach derselben Regel.

    Ohne beantragtes Ende oder ohne Vorher-Wert (Antrag zu einem damals offenen
    Eintrag) unverändert."""
    return _request_input_for_approval(proposed_end, original_end, entry.end_time)


def request_start_for_approval(
    entry, proposed_start: Optional[time], original_start: Optional[time],
) -> Optional[time]:
    """Gesamtreview 1.20 (B2): der beantragte Beginn eines UPDATE-Antrags, wie
    die Genehmigung ihn liest — dieselbe Regel wie ``request_end_for_approval``.
    Ein Beginn minutengleich mit dem angerechneten Beginn ZUM ZEITPUNKT DES
    ANTRAGS (``original_start_time``) ist Echo und wird durch den aktuellen
    angerechneten Beginn ersetzt; ``unclamp_input`` stellt daraus den
    Rohstempel her. Sonst hielt die Genehmigung nach einer Neukappung (Hülle
    beginnt später) den alten Beginn 07:45 für eine Eingabe und legte ihn als
    Rohbeginn ab — der Stempel 07:00 war weg."""
    return _request_input_for_approval(proposed_start, original_start, entry.start_time)


def end_input_for(
    incoming: Optional[time], prev_eff: Optional[time], prev_raw: Optional[time],
    *, auto_closed: bool, prev_date: date, target_date: date,
) -> Optional[time]:
    """Kappungseingabe für das Ende eines GESPEICHERTEN Eintrags — DIE eine
    Stelle für alle Pfade, die ein bestehendes Ende neu kappen und dabei das
    Datum wechseln können (MA-Antrag E40, Antragsgenehmigung UPDATE samt
    Vorprüfung, Admin-Bearbeitung, Bearbeiten-Route der Beschäftigten).

    Grundsätzlich ``unclamp_input``. Ausnahme (PR1-Review, Sicherheitsfund F1;
    P18): ein automatisch geschlossener Eintrag wird auf einen ANDEREN Tag
    verschoben und das eingereichte Ende ist keine Korrektur
    (``end_is_correction``: das wirksame Ende kommt zurück — vom Formular oder
    als Rückfall eines Teil-Updates ohne Ende, der seit 2026-10-11 an jedem Pfad
    das wirksame Ende einsetzt). Dann ist das
    gespeicherte Rohende die Eingabe, sofern es nicht das synthetische 23:59
    ist, sonst das gespeicherte WIRKSAME Ende — 23:59 ist kein Stempel. Bis zum
    Fix stellte ``unclamp_input`` das synthetische 23:59 wieder her, und am
    Zieltag ohne Blöcke (Samstag, Feiertag, freier Tag) blieb es ungekappt:
    15:00–23:59 ≈ 9 h statt 3,25 h; an einem Tag mit späterer Hülle wurde bis
    zu ihr angerechnet. Bei gleichem Datum bleibt alles wie in P18 (das Rohende
    wird gegen dieselben Blöcke wieder auf dieselbe Hülle gekappt).

    Ein anderes Rohende als 23:59 trägt ein automatisch geschlossener Eintrag
    nur nach einem früheren Verschieben auf einen Tag mit früherer Hülle: dort
    wurde das übernommene wirksame Ende gekappt und als Rohende abgelegt (nie
    später als das ursprüngliche wirksame Ende). PR1-Review N2: mit dem schon
    gekürzten wirksamen Ende weiterzurechnen machte das Ergebnis von der
    Reihenfolge der Verschiebungen abhängig — Montag (Hülle 18:15) → Freitag
    (Hülle 16:15) → nächster Montag landete still bei 16:15 statt 18:15.

    **Entschieden 2026-10-11 (Produktinhaber):** ein eingetragenes 23:59 (oder
    das eingetippte übernommene Rohende) ist eine Korrektur und damit eine
    normale Eingabe — auch beim Verschieben (``unclamp_input`` reicht es durch,
    die Kappung des Zieltags entscheidet).

    Review Task 6 (PR2): ``end_is_correction`` vergleicht minutengenau. Ist die
    Eingabe keine Korrektur, rechnet auch der gleiche Tag mit dem GESPEICHERTEN
    Paar weiter (``unclamp_input`` mit dem wirksamen Ende als Eingabe) statt mit
    der Eingabe — sonst landete ein 18:15:30 als Eingabe statt des Rohendes. Für
    sekundenfreie Eingaben ist das dasselbe Ergebnis. Ebenso gilt ein
    gespeichertes Rohende 23:59:xx beim Verschieben als synthetisch."""
    if auto_closed and not end_is_correction(incoming, prev_eff):
        if target_date == prev_date:
            return unclamp_input(prev_eff, prev_eff, prev_raw)
        return _auto_closed_end_input(prev_eff, prev_raw)
    return unclamp_input(incoming, prev_eff, prev_raw)


def _auto_closed_end_input(prev_eff: Optional[time], prev_raw: Optional[time]) -> Optional[time]:
    """P18: Kappungseingabe für das Ende eines automatisch geschlossenen
    Eintrags, wenn sich das Raster ändert, gegen das er gekappt wird
    (Verschieben auf einen anderen Tag, Massen-Neukappung 9.2) — das
    gespeicherte Rohende, sofern es nicht das synthetische 23:59 ist (nach einem
    früheren Verschieben bzw. einer kürzeren Hülle trägt es das zuvor
    angerechnete Ende), sonst das gespeicherte WIRKSAME Ende. Nie 23:59: eine
    spätere Hülle verlängert sonst die Anrechnung eines Eintrags, an dem nie
    jemand ausgestempelt hat (PR1-Review F1/N2)."""
    if prev_raw is not None and not same_minute(prev_raw, AUTO_CLOSE_RAW_END):
        return prev_raw
    return prev_eff


ORDER_ERROR_DETAIL = "Endzeit muss nach Startzeit liegen"


def input_order_error(
    start: Optional[time], end: Optional[time], *, auto_closed: bool,
) -> Optional[str]:
    """Reihenfolge der TATSÄCHLICHEN Kappungseingaben — nach ``unclamp_input`` /
    ``end_input_for``, direkt vor ``clamp``. ``None`` = in Ordnung.

    PR1-Review (Nachzug N2): Die Prüfung „Endzeit muss nach Startzeit liegen"
    läuft in allen Pfaden auf der rohen Eingabe. ``end_input_for`` ersetzt das
    Rohende 23:59 beim Verschieben eines automatisch geschlossenen Eintrags
    ohne Korrektur durch dessen wirksames Ende — mit einem späteren Beginn lag
    das Ende dann VOR dem Beginn (Samstag 20:00–18:15, ``net_hours`` 0 über den
    Floor, ohne Warnung):
    genau der Zustand, den der Release-Review 1.16.0 ausschließt. Deshalb jeder
    Pfad ein zweites Mal hier. ``unclamp_input`` allein dreht die Reihenfolge
    nie um (``clamp`` legt den Rohbeginn nie nach den wirksamen, das Rohende nie
    vor das wirksame — auch beim Kollaps nicht): ist sie beim automatisch
    geschlossenen Eintrag verkehrt, war es ``end_input_for``, und der Hinweis
    nennt diese Ursache. Ohne Kennzeichen bleibt die Prüfung reine Absicherung.
    Seit 2026-10-11 ist ein eingetipptes 23:59 eine Korrektur und kommt hier
    unverändert an; greifen kann die Prüfung nur noch, wenn kein Ende mitkam
    oder das wirksame Ende zurückkam. Beim Antrag hat die Prüfung der rohen
    Eingabe diesen Fall schon abgelehnt (hier bleibt es Absicherung); die
    Genehmigung prüft die rohe Eingabe nicht und fängt so ältere Anträge."""
    if start is None or end is None or end > start:
        return None
    if not auto_closed:
        return ORDER_ERROR_DETAIL
    return (
        f"{ORDER_ERROR_DETAIL}. Der Eintrag wurde automatisch geschlossen — "
        f"23:59 ist kein Stempel, es gilt das Ende {end:%H:%M}. "
        "Bitte das tatsächliche Ende eintragen."
    )


def not_credited_minutes(entry) -> int:
    """P19: nicht angerechnete Anwesenheit eines Eintrags = ``uncredited_minutes``
    + von der Hülle gekappte Minuten (``eff_start − raw_start``,
    ``raw_end − eff_end``; 0 ohne ``raw_*``; Endseite bei ``auto_closed``
    ausgenommen, dort ist 23:59 kein Stempel, P18). Frontend-Zwilling (PR2):
    ``utils/workBlocks.ts::notCreditedMinutes``."""
    total = int(getattr(entry, "uncredited_minutes", 0) or 0)
    if entry.start_time is not None and entry.raw_start_time is not None:
        total += max(0, _min(entry.start_time) - _min(entry.raw_start_time))
    if (entry.end_time is not None and entry.raw_end_time is not None
            and not getattr(entry, "auto_closed", False)):
        total += max(0, _min(entry.raw_end_time) - _min(entry.end_time))
    return total


def presence_end(entry) -> Optional[time]:
    """Ende der tatsächlichen Anwesenheit eines Eintrags — DIE eine Regel für die
    Anwesenheit laut Stempel (Spec 8.3) und die §5-Ruhezeit (``clock_in``,
    ``rest_time_service``, XLS-Vorschau): der Rohstempel, sonst das wirksame
    Ende; beim automatisch geschlossenen Eintrag (P18) das wirksame Ende. Dessen
    Rohende ist nie ein Stempel — das synthetische 23:59 bzw. nach einem
    Verschieben das zuvor angerechnete Ende (``_auto_closed_end_input``).

    Gesamtreview 1.20 (B1): §5 las ``raw_end_time or end_time`` und meldete am
    Morgen nach einem Auto-Close eine Ruhezeit ab 23:59 („Nur 7.5h") — für
    eine Zeit, in der niemand gestempelt hat. Ein eingetragenes Ende (auch
    23:59, das Kennzeichen fällt dann) bleibt maßgeblich. ``None`` = offen."""
    if getattr(entry, "auto_closed", False):
        return entry.end_time
    return entry.raw_end_time or entry.end_time


def presence_minutes(entry) -> int:
    """Spec 8.3: Anwesenheit laut Stempel = (raw_end oder end) − (raw_start oder
    start) − erfasste Pause; bei ``auto_closed`` bis zum wirksamen Ende
    (``presence_end``); offene Einträge zählen nicht."""
    if entry.end_time is None:
        return 0
    start = entry.raw_start_time or entry.start_time
    return max(0, _min(presence_end(entry)) - _min(start) - int(entry.break_minutes or 0))


def credit_summary_text(entry) -> str:
    """Spec 10.1 / 13.3: Klartext für Protokollnotizen — EINE Quelle
    („Anerkennen" in PR2, Neukappung in PR3).

    „angerechnet" = ``net_hours`` (nach Pause und Lücke), „nicht angerechnet" =
    ``not_credited_minutes`` (Lücke + Hülle, P19), „davon … zwischen den
    Blöcken" = ``uncredited_minutes`` (entfällt bei 0), bei Pause > 0 folgt
    „, Pause H:MM h". Bewusst ohne Typlabels („Krank " …) — sonst schlüge
    ``admin_time_entries._audit_note_is_health_sensitive`` an (Spec 10.1).

    Auslegung (Spec 10.1 widerspricht sich): die Kurzregel lässt „davon …"
    auch entfallen, wenn es gleich der Gesamtzahl ist; die wörtlichen
    Beispiele (10.1 ``old_note``, 13.3 Schritt 5) zeigen es für K1 (nur
    Lücke) aber — der Zusatz nennt die Ursache. Es gelten die Beispiele."""
    credited = int(round(float(entry.net_hours or 0) * 60))
    parts = [f"angerechnet {_hm(credited)} h"]
    total = not_credited_minutes(entry)
    gap = int(getattr(entry, "uncredited_minutes", 0) or 0)
    if total > 0:
        text = f"nicht angerechnet {_hm(total)} h"
        if gap > 0:
            text += f", davon {_hm(gap)} h zwischen den Blöcken"
        parts.append(text)
    brk = int(entry.break_minutes or 0)
    if brk > 0:
        parts.append(f"Pause {_hm(brk)} h")
    return ", ".join(parts)


# ── Spec 9.2: Massen-Neukappung einer Arbeitszeit-Änderung ─────────────────


class ReclampChange(NamedTuple):
    entry_id: Any
    date: date
    old_start: Optional[time]
    old_end: Optional[time]
    old_uncredited: int
    old_net: Decimal
    new_start: Optional[time]
    new_end: Optional[time]
    new_uncredited: int
    new_net: Decimal
    not_extendable: Optional[str]      # None | "start" | "end" | "both" (E50)
    old_grace: Optional[int]           # clamp_grace_minutes vorher (E79); neu = grace


class ReclampSkip(NamedTuple):
    entry_id: Any
    date: date
    reason: str   # open | soll_free_day | track_hours_off | outside_employment
                  # | credit_override | unique_collision


class ReclampResult(NamedTuple):
    changed: list
    skipped: list
    flagged: list      # nicht erweiterbar, auch wenn unverändert (E50)


def _soll_free_dates(db: Session, tenant_id, start: date, end: date) -> set:
    """Feiertage + freie Sondertage des Fensters — EIN Vorladen für die
    Neukappung (6.1-Vorladeparameter von ``clamp``)."""
    from app.models.public_holiday import PublicHoliday
    from app.services.special_days_service import free_special_days_in_range

    holidays = {
        h.date for h in db.query(PublicHoliday).filter(
            PublicHoliday.tenant_id == tenant_id,  # F-026
            PublicHoliday.date >= start,
            PublicHoliday.date <= end,
        ).all()
    }
    return holidays | set(free_special_days_in_range(db, tenant_id, start, end))


def _not_extendable(entry, old_day: list, new_day: list, grace: int,
                    old_grace: Optional[int]) -> Optional[str]:
    """E50: Seite ohne Rohstempel, gespeicherte Zeit exakt auf der ALTEN
    Hüllenkante (mit dem gespeicherten Puffer, sonst dem aktuellen) und die neue
    Hülle ist auf dieser Seite weiter → der Eintrag kann nicht erweitert werden,
    weil der echte Stempel vor 1.19.1 verloren ging.

    Review Task 7: ein Tag OHNE neue Blöcke hat keine Hülle — die weiteste
    mögliche, also auf beiden Seiten „weiter" (Hauptfall: ein Altfenster aus
    #201 wird entfernt). Und das Rohende 23:59 eines automatisch geschlossenen
    Eintrags ist kein Stempel (P18): sein Ende ist „ohne Rohstempel", die
    Neukappung verlängert es nie. Ein übernommenes echtes Rohende nach einem
    Verschieben (``end_input_for``) bleibt die Grenze, bis zu der erweitert
    wird — kein Hinweis.

    Nur eine Kante, an der ``_clamp_core`` tatsächlich gekappt hat, zählt: die
    offene Seite eines halboffenen #201-Fensters (Platzhalter-Ende 23:59 = kein
    Ende, Spec 5.3; Beginn-Untergrenze 00:00, vor der nichts liegt) hat nie
    gekappt — eine Zeit dort ist kein verlorener Stempel."""
    if not old_day:
        return None
    g_old = old_grace if old_grace is not None else grace
    sides = []
    if entry.raw_start_time is None and entry.start_time is not None and entry.start_time.second == 0:
        old_floor = _shift_min(old_day[0][0], -g_old)
        if old_floor > 0 and _min(entry.start_time) == old_floor and (
                not new_day or _shift_min(new_day[0][0], -grace) < old_floor):
            sides.append("start")
    end_unstamped = entry.raw_end_time is None or (
        entry.auto_closed and same_minute(entry.raw_end_time, AUTO_CLOSE_RAW_END))
    if end_unstamped and entry.end_time is not None and entry.end_time.second == 0:
        old_ceil = _shift_min(old_day[-1][1], g_old)
        if old_day[-1][1] < _LAST_MINUTE and _min(entry.end_time) == old_ceil and (
                not new_day or _shift_min(new_day[-1][1], grace) > old_ceil):
            sides.append("end")
    if not sides:
        return None
    return sides[0] if len(sides) == 1 else "both"


def reclamp_time_entries(db: Session, user, start: date, end: date, weekdays: set,
                         prev_blocks_by_weekday: Optional[tuple], grace: int) -> ReclampResult:
    """Spec 9.2 — kappt die Einträge in ``[start, end]`` an den geänderten
    ``weekdays`` gegen den NEUEN Snapshot (der Aufrufer hat ihn bereits
    geflusht). Quelle ist der Rohstempel, sonst die gespeicherte Zeit (E48).
    Aktueller Mandanten-Puffer ``grace`` (E47), geschrieben in jeden geprüften
    Eintrag (E79, auch ohne Zeitänderung, ohne Eintrag in ``changed``).
    Setzt ORM-Attribute (kein ``query.update``) und flusht jeden neuen Beginn
    sofort (Schritt 11, Unique-Index); kein commit, kein Protokoll — beides
    gehört dem Router; die Vorschau rollt zurück. Idempotent.

    Automatisch geschlossene Einträge (P18): Eingabe für das Ende ist nie das
    synthetische 23:59, sondern ``_auto_closed_end_input`` (wie beim
    Verschieben) — sonst verlängerte eine spätere Hülle die Anrechnung eines
    Eintrags, an dem nie ausgestempelt wurde. Das Kennzeichen bleibt; wird das
    Ende nicht gekappt, kehrt das Rohende zum Protokollwert 23:59 zurück, sofern
    der Eintrag eines trug (Rücknahme einer Änderung stellt den Zustand des
    Auto-Close byte-gleich wieder her, 17.5 „Reversibilität")."""
    weekdays = set(weekdays)
    if not weekdays or start > end:
        return ReclampResult([], [], [])
    entries = [
        e for e in db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id,
            TimeEntry.tenant_id == user.tenant_id,  # F-026
            TimeEntry.date >= start,
            TimeEntry.date <= end,
        ).order_by(TimeEntry.date, TimeEntry.start_time).all()
        if e.date.weekday() in weekdays
    ]
    if not entries:
        return ReclampResult([], [], [])
    if not getattr(user, "track_hours", True):  # Schritt 1
        return ReclampResult([], [ReclampSkip(e.id, e.date, "track_hours_off") for e in entries], [])

    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
    ).all()
    soll_free = _soll_free_dates(db, user.tenant_id, start, end)
    planned_start = {e.id: e.start_time for e in entries}
    same_day: dict = {}
    for e in entries:
        same_day.setdefault(e.date, []).append(e)

    changed, skipped, flagged = [], [], []
    for e in entries:
        wd = e.date.weekday()
        if e.end_time is None:                                            # Schritt 2
            skipped.append(ReclampSkip(e.id, e.date, "open"))
            continue
        if not calculation_service._within_employment_window(user, e.date):  # Schritt 3
            skipped.append(ReclampSkip(e.id, e.date, "outside_employment"))
            continue
        if e.credit_override:                                              # Schritt 4
            skipped.append(ReclampSkip(e.id, e.date, "credit_override"))
            continue
        new_sched = calculation_service.get_schedule_for_date(db, user, e.date, wh_changes)
        day_has_blocks = wd < 5 and bool(new_sched.blocks) and bool(new_sched.blocks[wd])
        if day_has_blocks and e.date in soll_free:                         # Schritt 5
            skipped.append(ReclampSkip(e.id, e.date, "soll_free_day"))
            continue
        src_start = e.raw_start_time or e.start_time                      # Schritt 6 (E48)
        if e.auto_closed:                                                  # P18: nie 23:59
            src_end = _auto_closed_end_input(e.end_time, e.raw_end_time)
        else:
            src_end = e.raw_end_time or e.end_time
        r = clamp(db, user, e.date, src_start, src_end, grace, credit_override=False,
                  wh_changes=wh_changes, soll_free_dates=soll_free)       # Schritt 7
        if r.eff_start in {planned_start[o.id] for o in same_day[e.date] if o.id != e.id}:  # Schritt 8
            skipped.append(ReclampSkip(e.id, e.date, "unique_collision"))
            continue
        old_grace = e.clamp_grace_minutes                                  # Schritt 9
        # Am Feiertag/freien Sondertag kappte auch der alte Snapshot nicht (#484):
        # eine Zeit auf seiner Wochentagskante wäre dort Zufall, kein verlorener
        # Stempel (Schritt 12, Review Task 7).
        old_day = (list(prev_blocks_by_weekday[wd])
                   if prev_blocks_by_weekday and e.date not in soll_free else [])
        new_day = get_scheduled_blocks(db, user, e.date, wh_changes=wh_changes, soll_free_dates=soll_free)
        flag = _not_extendable(e, old_day, new_day, grace, old_grace)    # Schritt 12 (vor dem Setzen)
        if r.grace_minutes is not None:
            e.clamp_grace_minutes = r.grace_minutes
        new_raw_end = r.raw_end
        # P18: Protokollwert bleibt, solange das Ende nicht gekappt wurde — auch
        # beim schon kollabierten Eintrag (19:00–19:00), für den ``clamp`` die
        # Eingabe als Rohende zurückgibt (Review Task 7).
        if e.auto_closed and e.raw_end_time is not None and r.eff_end == src_end:
            new_raw_end = AUTO_CLOSE_RAW_END
        old_vals = (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time, int(e.uncredited_minutes or 0))
        new_vals = (r.eff_start, r.eff_end, r.raw_start, new_raw_end, int(r.uncredited_minutes))
        old_net = Decimal(str(e.net_hours))
        if old_vals == new_vals:                                           # Schritt 10
            if flag:
                flagged.append(ReclampChange(e.id, e.date, e.start_time, e.end_time, old_vals[4], old_net,
                                             e.start_time, e.end_time, old_vals[4], old_net, flag, old_grace))
            continue
        (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time, e.uncredited_minutes) = new_vals  # Schritt 11
        if r.eff_start != old_vals[0]:
            # Gesamtreview PR3: ein neuer Beginn sofort in die Datenbank, damit sie
            # nach jedem Schritt ``planned_start`` entspricht. Schritt 8 erlaubt,
            # dass ein später bearbeiteter Eintrag den in DIESEM Lauf frei
            # gewordenen Beginn eines anderen übernimmt; ein gemeinsamer Flush am
            # Ende ordnete die UPDATEs aber nach Primärschlüssel, und der nicht
            # verzögerbare Index ``uq_tenant_user_date_start`` (PG wie SQLite, je
            # Anweisung geprüft) scheiterte dann je nach ID (IntegrityError → 500).
            db.flush()
        planned_start[e.id] = r.eff_start
        change = ReclampChange(e.id, e.date, old_vals[0], old_vals[1], old_vals[4], old_net,
                               r.eff_start, r.eff_end, new_vals[4], Decimal(str(e.net_hours)), flag, old_grace)
        changed.append(change)
        if flag:
            flagged.append(change)
    return ReclampResult(changed, skipped, flagged)


STALE_CLAMP_MAX_DATES = 5


def stale_clamp_entries(db: Session, tenant_id, dates) -> list:
    """Gesamtreview 1.20: geschlossene Einträge an ``dates``, deren gespeicherte
    Anrechnung (Beginn, Ende, ``uncredited_minutes``) nicht mehr der Kappung
    entspricht, die ``clamp`` heute ergäbe.

    Aufrufer sind die Wege, die nachträglich ändern, ob ein Tag soll-frei ist
    (E35/#484): eigener Feiertag anlegen/verschieben/löschen, Bundesland-Wechsel,
    Sondertag 24./31.12. zwischen „frei" und Arbeitstag. Sie schreiben nichts an
    den Einträgen — eine stille Neukappung wäre eine rückwirkende Verkürzung
    ohne Vorschau und Grund (Spec 9.5) — und melden nur, was die Verwaltung per
    unverändertem Speichern neu berechnen lässt. Ausgenommen wie bei der
    Neukappung (E49): offene Einträge, ohne Stundenzählung, außerhalb des
    Beschäftigungsfensters, anerkannte Einträge. Eingaben wie
    ``reclamp_time_entries`` (Rohstempel, bei ``auto_closed`` nie 23:59),
    Puffer je Eintrag (``grace_for_entry``, E80)."""
    from app.models import User

    dates = set(dates or ())
    if not dates:
        return []
    entries = db.query(TimeEntry).filter(
        TimeEntry.tenant_id == tenant_id,  # F-026
        TimeEntry.date.in_(dates),
        TimeEntry.end_time.isnot(None),
    ).order_by(TimeEntry.date, TimeEntry.start_time).all()
    entries = [e for e in entries if not e.credit_override]
    if not entries:
        return []
    users = {
        u.id: u for u in db.query(User).filter(
            User.tenant_id == tenant_id,  # F-026
            User.id.in_({e.user_id for e in entries}),
        ).all()
    }
    soll_free = _soll_free_dates(db, tenant_id, min(dates), max(dates))
    stale = []
    for e in entries:
        user = users.get(e.user_id)
        if user is None or not getattr(user, "track_hours", True):
            continue
        if not calculation_service._within_employment_window(user, e.date):
            continue
        src_start = e.raw_start_time or e.start_time
        if e.auto_closed:
            src_end = _auto_closed_end_input(e.end_time, e.raw_end_time)
        else:
            src_end = e.raw_end_time or e.end_time
        r = clamp(db, user, e.date, src_start, src_end, grace_for_entry(db, e),
                  credit_override=False, soll_free_dates=soll_free)
        if (r.eff_start, r.eff_end, int(r.uncredited_minutes)) != (
                e.start_time, e.end_time, int(e.uncredited_minutes or 0)):
            stale.append(e)
    return stale


def stale_clamp_hint(db: Session, tenant_id, dates) -> Optional[str]:
    """Hinweistext zu ``stale_clamp_entries`` (None = nichts betroffen)."""
    stale = stale_clamp_entries(db, tenant_id, dates)
    if not stale:
        return None
    days = sorted({e.date for e in stale})
    shown = ", ".join(d.strftime("%d.%m.%Y") for d in days[:STALE_CLAMP_MAX_DATES])
    if len(days) > STALE_CLAMP_MAX_DATES:
        shown += ", …"
    n = len(stale)
    count = "1 Eintrag" if n == 1 else f"{n} Einträge"
    return (
        "Zeiteinträge an geänderten Tagen behalten ihre bisherige Anrechnung gegen "
        f"die Arbeitszeit-Blöcke ({count}: {shown}). Neu berechnet wird ein Eintrag, "
        "wenn Sie ihn im Admin-Dashboard oder Monatsjournal öffnen und unverändert speichern "
        "(fehlt dann eine gesetzliche Pause, ergänzen Sie sie)."
    )


def join_warnings(*warnings: Optional[str]) -> Optional[str]:
    """Mehrere Hinweise einer Antwort zu EINEM ``warning`` (None = keiner)."""
    parts = [w for w in warnings if w]
    return " ".join(parts) if parts else None


def credited_minutes_for(blocks: list, grace: int, start_min: int, end_min: int) -> int:
    """Angerechnete Minuten (ohne Pause) eines Eintrags ``start``–``end`` gegen
    die Blöcke EINES Tages — dieselbe Regel wie ``_clamp_core``, rein in Minuten
    und ohne Datenbank (für die P1-Knickstellen-Prüfung)."""
    if not blocks:
        return max(0, end_min - start_min)
    s = max(start_min, _shift_min(blocks[0][0], -grace))
    e = min(end_min, _shift_min(blocks[-1][1], grace))
    if s >= e:
        return 0
    return e - s - sum(_overlap(s, e, gs, ge) for gs, ge in credit_gaps(blocks, grace))


def open_entry_loses(old_blocks: list, new_blocks: list, grace: int, start: time, now: time) -> bool:
    """P1: verliert der offene Eintrag von heute für IRGENDEIN mögliches Ende ≥
    jetzt? ``angerechnet_neu(Ende) − angerechnet_alt(Ende)`` ist stückweise linear
    mit Knicken an Hüllen- und Lückenkanten beider Snapshots — geprüft wird an
    ``max(jetzt, Beginn)``, an jeder Knickstelle danach und an 23:59. Gleicher
    Puffer für beide Seiten: das Ausstempeln kappt mit dem gespeicherten
    Puffer des Eintrags (E80)."""
    s = _min(start)
    lo = max(_min(now), s)
    points = {lo, _LAST_MINUTE}
    for blocks in (old_blocks, new_blocks):
        if blocks:
            points.update({_shift_min(blocks[0][0], -grace), _shift_min(blocks[-1][1], grace)})
            for gs, ge in credit_gaps(blocks, grace):
                points.update({gs, ge})
    for p in sorted(x for x in points if lo <= x <= _LAST_MINUTE):
        if credited_minutes_for(new_blocks, grace, s, p) < credited_minutes_for(old_blocks, grace, s, p):
            return True
    return False
