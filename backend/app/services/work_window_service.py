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
from typing import NamedTuple, Optional

from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting
from app.services import calculation_service

DEFAULT_GRACE_MINUTES = 15
# #462: Kennung der weichen Warnung ("CODE: Text", läuft durch showArbzgWarnings).
CLAMP_WARNING_CODE = "WORK_WINDOW_CLAMPED"
_LAST_MINUTE = 23 * 60 + 59
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
    """work_window_grace_minutes aus system_settings (Default 15, >= 0)."""
    s = db.query(SystemSetting).filter(
        SystemSetting.key == "work_window_grace_minutes",
        SystemSetting.tenant_id == tenant_id,
    ).first()
    if not s:
        return DEFAULT_GRACE_MINUTES
    try:
        return max(0, int(s.value))
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


def end_is_correction(
    incoming: Optional[time], prev_eff: Optional[time], prev_raw: Optional[time],
    auto_closed: bool,
) -> bool:
    """P18: Liefert eine Eingabe ein tatsächliches Ende, das das Kennzeichen
    ``auto_closed`` aufhebt?

    Nein, wenn sie das gespeicherte wirksame Ende unverändert zurückschickt
    (Formular, siehe ``unclamp_input``) — und nein, wenn sie bei einem
    automatisch geschlossenen Eintrag dessen Rohende zurückschickt: 23:59 ist
    dort kein Stempel. Review Task 8: die Waiver-Rückfrage der MA-Route füllt
    ein fehlendes Ende mit dem Rohwert auf, die Genehmigung hielt das für ein
    eingetragenes Ende und machte aus dem synthetischen 23:59 einen echten
    Stempel (Hülle bis 23:59 „nicht angerechnet", Anerkennen 08:00–23:59).
    Ein Eintrag ohne Blöcke (``raw`` None, Ende 23:59) fällt schon unter den
    ersten Vergleich. Ein ``None``-Ende gilt hier als Änderung; ob ein
    fehlendes bzw. ``None``-Ende überhaupt geprüft wird, entscheidet der
    Aufrufer. Dieselbe Regel gilt in allen drei Schreibpfaden (MA-Route,
    Admin-Bearbeitung, Antragsgenehmigung)."""
    if incoming == prev_eff:
        return False
    if auto_closed and prev_raw is not None and incoming == prev_raw:
        return False
    return True


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
    (``end_is_correction``: das wirksame Ende oder das Rohende 23:59 kommt
    zurück, auch als Rückfall eines Teil-Updates ohne Ende). Dann ist das
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
    (Hülle 16:15) → nächster Montag landete still bei 16:15 statt 18:15."""
    if (auto_closed and target_date != prev_date
            and not end_is_correction(incoming, prev_eff, prev_raw, auto_closed)):
        if prev_raw is not None and prev_raw != AUTO_CLOSE_RAW_END:
            return prev_raw
        return prev_eff
    return unclamp_input(incoming, prev_eff, prev_raw)


ORDER_ERROR_DETAIL = "Endzeit muss nach Startzeit liegen"


def input_order_error(
    start: Optional[time], end: Optional[time], *, auto_closed: bool,
) -> Optional[str]:
    """Reihenfolge der TATSÄCHLICHEN Kappungseingaben — nach ``unclamp_input`` /
    ``end_input_for``, direkt vor ``clamp``. ``None`` = in Ordnung.

    PR1-Review (Nachzug N2): Die Prüfung „Endzeit muss nach Startzeit liegen"
    läuft in allen Pfaden auf der rohen Eingabe (das eingetippte oder als
    Rückfall eingesetzte Rohende 23:59). ``end_input_for`` ersetzt 23:59 beim
    Verschieben eines automatisch geschlossenen Eintrags durch dessen
    wirksames Ende — mit einem späteren Beginn lag das Ende dann VOR dem
    Beginn (Samstag 20:00–18:15, ``net_hours`` 0 über den Floor, ohne Warnung):
    genau der Zustand, den der Release-Review 1.16.0 ausschließt. Deshalb jeder
    Pfad ein zweites Mal hier. ``unclamp_input`` allein dreht die Reihenfolge
    nie um (``clamp`` legt den Rohbeginn nie nach den wirksamen, das Rohende nie
    vor das wirksame — auch beim Kollaps nicht): ist sie beim automatisch
    geschlossenen Eintrag verkehrt, war es ``end_input_for``, und der Hinweis
    nennt diese Ursache. Ohne Kennzeichen bleibt die Prüfung reine Absicherung."""
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


def presence_minutes(entry) -> int:
    """Spec 8.3: Anwesenheit laut Stempel = (raw_end oder end) − (raw_start oder
    start) − erfasste Pause; bei ``auto_closed`` bis zum wirksamen Ende; offene
    Einträge zählen nicht."""
    if entry.end_time is None:
        return 0
    start = entry.raw_start_time or entry.start_time
    end = entry.end_time if getattr(entry, "auto_closed", False) else (entry.raw_end_time or entry.end_time)
    return max(0, _min(end) - _min(start) - int(entry.break_minutes or 0))
