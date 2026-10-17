"""Spec 2026-10-08, Abschnitt 10: Protokoll der Arbeitszeit-Änderungen.

Schreiben UND Lesen der Sammelzeile leben hier (P7) — ein Format, ein Parser,
Round-Trip-Test in ``tests/test_reclamp_audit.py``. Keine neue gehashte Spalte:
alles steht in festen Notiz-Bausteinen von ``new_note`` (10.3).

Die Notiz-Präfixe der Grundtypen sind EINGEFROREN (19.1 Nr. 7) — Protokoll und
Parser lesen sie. Die Oberfläche und der Dashboard-Hinweis zeigen ausschließlich
die Beschriftung aus :data:`REASON_TYPES`, nie das Präfix und nie den Freitext (P12).

Feste Notizteile enthalten keine Typlabels („Krank ", „Sonstiges ",
„Bez. Freistellung "), damit ``admin_time_entries._audit_note_is_health_sensitive``
nicht anschlägt (10.1). Das Präfix „[Sonstiges]" entgeht dem Token „Sonstiges "
nur durch die schließende Klammer — Test in ``test_reclamp_audit.py``.
"""
import re
from datetime import date, datetime, timedelta, timezone
from typing import List, NamedTuple, Optional

from app.services import calculation_service, timezone_service, work_blocks_service
from app.services.export_service import format_day_plan, format_hours_de

AUDIT_SOURCE = "wh_reclamp"  # 10 Zeichen, varchar(40)
NOTE_MAX_LENGTH = 500
NOTE_TOO_LONG_DETAIL = "Notiz und Begründung zusammen höchstens 500 Zeichen."
# Review Task 3: ohne Begründung steht die Notiz allein in der Spalte — „und
# Begründung" wäre dort ein Satz über ein Feld, das niemand ausgefüllt hat.
NOTE_ONLY_TOO_LONG_DETAIL = "Die Notiz darf höchstens 500 Zeichen lang sein."


class ReasonType(NamedTuple):
    key: str
    prefix: str
    label: str


REASON_TYPES = {
    "erfassungsfehler": ReasonType(
        "erfassungsfehler", "[Erfassungsfehler korrigiert]",
        "Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)"),
    "einvernehmlich": ReasonType(
        "einvernehmlich", "[Einvernehmlich vereinbart]",
        "Mit der beschäftigten Person vereinbart"),
    "sonstiges": ReasonType("sonstiges", "[Sonstiges]", "Sonstiges"),
}

# ReclampSkip.reason → Wort in Sammelzeile und Vorschau (keine Typlabels, 10.1).
# Frontend-Zwilling: ``pages/admin/users/workingHoursTexts.ts::SKIP_LABELS``.
SKIP_LABELS = {
    "credit_override": "anerkannt",
    "open": "offen",
    "soll_free_day": "Sonn-/Feiertag",
    "track_hours_off": "ohne Stundenzählung",
    "outside_employment": "außerhalb der Beschäftigung",
    "unique_collision": "Überschneidung",
}

_HEAD = re.compile(
    r"^Arbeitszeit-Änderung ab (\d{2}\.\d{2}\.\d{4})( gelöscht)?: (\d+) Eintr(?:ag|äge) neu berechnet, "
    r"Δ ([+-]\d+) Min, Saldo Δ ([+-]\d+) Min"
)
_RESET = re.compile(r" · Rücksetzung der Änderung ab (\d{2}\.\d{2}\.\d{4}) · ")
_GRUND = " · Grund: "
_VERTRAG = " · Vertrag: "


class SummaryNote(NamedTuple):
    effective_from: date
    deleted: bool
    count: int
    delta_minutes: int
    saldo_delta_minutes: int
    shortening: bool
    reason_type: Optional[str]
    reset_of: Optional[date]


def reason_text(reason_type: str, text: Optional[str]) -> str:
    """„[Erfassungsfehler korrigiert] <Begründung>" — Präfix unverändert (9.5)."""
    prefix = REASON_TYPES[reason_type].prefix
    text = (text or "").strip()
    return f"{prefix} {text}" if text else prefix


def compose_change_note(note: Optional[str], reason_type: Optional[str],
                        text: Optional[str]) -> Optional[str]:
    """Spec 9.5: ``working_hours_changes.note`` = Grund mit Präfix, eine zusätzliche
    Notiz mit „ · " angehängt. Ohne Grund bleibt die Notiz wie eingegeben.

    Die Längenprüfung (> :data:`NOTE_MAX_LENGTH` → 422 :data:`NOTE_TOO_LONG_DETAIL`,
    Notiz allein :data:`NOTE_ONLY_TOO_LONG_DETAIL`) gehört dem Schreibschema —
    hier wird nie still gekürzt."""
    if not reason_type:
        return note
    base = reason_text(reason_type, text)
    extra = (note or "").strip()
    return f"{base} · {extra}" if extra else base


def _days_text(n: int) -> str:
    return "1 Tag" if n == 1 else f"{n} Tage"


def contract_text(schedule, *, compact: bool, previous=None) -> str:
    """Kurztext eines Vertrags-Snapshots (``calculation_service.Schedule``) —
    Sammelzeile „Vertrag:" (``compact``), Dashboard-Hinweis „neu: …" (lang).

    * neue Blöcke: nur die Blöcke (das Soll ist daraus abgeleitet)
    * Tagesplan: „Mo 8,0 / Di 5,0 = 13,0 h/Woche"
    * gleichmäßig, Sammelzeile (10.2): „20,0 h/Woche (gleichmäßig, 5 Tage)"
    * gleichmäßig, Hinweis (Spec 14, Gesamtreview PR3): der #415-Text
      „20,0 h/Woche" ohne Klammerzusatz — er steht selbst in „(neu: …)". Die
      Arbeitstage („ auf 4 Arbeitstage") nur, wenn sie sich gegenüber
      ``previous`` (Snapshot am Vortag) ändern — dieselbe Regel wie
      ``export_service._work_days_suffix``; sonst sagte der Hinweis bei
      „40 h auf 5 Tage" → „40 h auf 4 Tage" nur „neu: 40,0 h/Woche".
    * Altfenster: Soll-Text + „ · <Fenster> (nur Kappung)"."""
    parsed = None
    if schedule.blocks is not None:
        parsed = work_blocks_service.ParsedWeek(schedule.blocks, schedule.block_pauses)
    if parsed is not None and not work_blocks_service.is_legacy_week(parsed):
        return work_blocks_service.blocks_text(parsed.blocks, parsed.pauses, compact=compact)
    plan = format_day_plan(schedule.day_hours) if schedule.use_daily_schedule else ""
    days = int(schedule.work_days_per_week)
    if plan:
        base = f"{plan} = {format_hours_de(schedule.weekly_hours)} h/Woche"
    elif compact:
        base = f"{format_hours_de(schedule.weekly_hours)} h/Woche (gleichmäßig, {_days_text(days)})"
    else:
        base = f"{format_hours_de(schedule.weekly_hours)} h/Woche"
        if calculation_service.work_days_changed(previous, schedule):
            base += f" auf {days} {'Arbeitstag' if days == 1 else 'Arbeitstage'}"
    if parsed is None:
        return base
    window = work_blocks_service.blocks_text(parsed.blocks, parsed.pauses, compact=compact)
    return f"{base} · {window} (nur Kappung)"


def _sign(value: int) -> str:
    """ASCII-Vorzeichen der Sammelzeile (10.2) — auch „+0"."""
    return f"+{value}" if value >= 0 else str(value)


def summary_note(*, effective_from: date, deleted: bool, count: int, delta_minutes: int,
                 saldo_delta_minutes: int, skipped: dict, grace: int, credit_reductions: int,
                 reset_of: Optional[date], shortening: bool, reason_type: Optional[str],
                 reason_text_value: Optional[str], contract_before: str, contract_after: str) -> str:
    """Spec 10.2 — die Sammelzeile (genau eine je Anlegen/Löschen, P20).

    ``skipped`` zählt je ``ReclampSkip.reason``; ein Grund ohne Wort in
    :data:`SKIP_LABELS` scheitert laut (sonst fiele er still aus der Aufzählung,
    während die Gesamtzahl ihn mitzählt)."""
    unknown = sorted(set(skipped) - set(SKIP_LABELS))
    if unknown:
        raise ValueError(f"Übersprungen-Grund ohne Beschriftung in SKIP_LABELS: {unknown}")
    head = (
        f"Arbeitszeit-Änderung ab {effective_from:%d.%m.%Y}{' gelöscht' if deleted else ''}: "
        f"{count} {'Eintrag' if count == 1 else 'Einträge'} neu berechnet, "
        f"Δ {_sign(delta_minutes)} Min, Saldo Δ {_sign(saldo_delta_minutes)} Min"
    )
    total_skipped = sum(skipped.values())
    if total_skipped:
        details = ", ".join(f"{skipped[k]} {SKIP_LABELS[k]}" for k in SKIP_LABELS if skipped.get(k))
        head += f", {total_skipped} übersprungen ({details})"
    parts = [head, f"Puffer {grace} Min"]
    if credit_reductions:
        noun = "Abwesenheits-Gutschrift" if credit_reductions == 1 else "Abwesenheits-Gutschriften"
        parts.append(f"{credit_reductions} {noun} gesenkt")
    if reset_of is not None:
        parts.append(f"Rücksetzung der Änderung ab {reset_of:%d.%m.%Y}")
    if shortening:
        parts.append("Verkürzung")
    if shortening and reason_type:
        parts.append(f"Grund: {reason_text(reason_type, reason_text_value)}")
    parts.append(f"Vertrag: {contract_before} → {contract_after}")
    return " · ".join(parts)


def parse_summary_note(note: Optional[str]) -> Optional[SummaryNote]:
    """Liest die festen Bausteine einer Sammelzeile. Der Freitext nach „Grund:"
    wird nie gelesen (P12): Kennzeichen werden nur VOR „ · Grund: " bzw.
    „ · Vertrag: " gesucht. Keine Sammelzeile → ``None``.

    Der feste Teil behält das führende „ · " des abgeschnittenen Bausteins
    (``cut + 3``), damit „ · Verkürzung · " und „ · Rücksetzung … · " auch direkt
    vor „Grund:"/„Vertrag:" erkannt werden."""
    if not note:
        return None
    m = _HEAD.match(note)
    if m is None:
        return None
    grund = note.find(_GRUND)
    cut = grund if grund != -1 else note.find(_VERTRAG)
    fixed = note[: cut + 3] if cut != -1 else note
    reset = _RESET.search(fixed)
    reason_type = None
    if grund != -1:
        rest = note[grund + len(_GRUND):]
        for key, rt in REASON_TYPES.items():
            if rest.startswith(rt.prefix):
                reason_type = key
                break
    return SummaryNote(
        effective_from=datetime.strptime(m.group(1), "%d.%m.%Y").date(),
        deleted=bool(m.group(2)),
        count=int(m.group(3)),
        delta_minutes=int(m.group(4)),
        saldo_delta_minutes=int(m.group(5)),
        shortening=" · Verkürzung · " in fixed,
        reason_type=reason_type,
        reset_of=datetime.strptime(reset.group(1), "%d.%m.%Y").date() if reset else None,
    )


def entry_new_note(after_text: str, *, effective_from: date, deleted: bool, old_grace: Optional[int],
                   grace: int, shortening: bool, reason_type: Optional[str],
                   reason_text_value: Optional[str]) -> str:
    """Spec 10.1 — ``new_note`` der Einzelzeile: Anrechnung nachher
    (``work_window_service.credit_summary_text``) + Auslöser, bei abweichendem
    gespeichertem Puffer „ · Puffer 15 → 10 Min" (E80; bei NULL kein Zusatz), bei
    Verkürzung der Grund mit unverändertem Präfix."""
    trigger = "Löschung der Arbeitszeit-Änderung" if deleted else "Arbeitszeit-Änderung"
    text = f"{after_text} — {trigger} ab {effective_from:%d.%m.%Y}"
    if old_grace is not None and old_grace != grace:
        text += f" · Puffer {old_grace} → {grace} Min"
    if shortening and reason_type:
        text += f" · Grund: {reason_text(reason_type, reason_text_value)}"
    return text


NOTICE_DAYS = 30


def _signed_hm(minutes: int) -> str:
    """Anzeige-Vorzeichen des Dashboard-Hinweises: U+2212 „−" bzw. „+" vor ``H:MM``
    (die Sammelzeile selbst trägt ASCII, 10.2)."""
    sign = "−" if minutes < 0 else "+"
    m = abs(int(minutes))
    return f"{sign}{m // 60}:{m % 60:02d}"


def notice_text(db, user, parsed: SummaryNote, today: date) -> str:
    """Spec 14 — Text je Sammelzeile. „neu: …" ist der Kurztext des HEUTE für
    ``effective_from`` aufgelösten Snapshots (``get_schedule_for_date``), nie
    ``users.work_blocks``; der Grund erscheint nur als Beschriftung des
    Grundtyps (P12, 19.1 Nr. 7)."""
    eff = parsed.effective_from.strftime("%d.%m.%Y")
    if parsed.deleted:
        text = f"Die Arbeitszeit-Änderung ab {eff} wurde zurückgenommen."
    else:
        neu = contract_text(
            calculation_service.get_schedule_for_date(db, user, parsed.effective_from), compact=False,
            previous=calculation_service.get_schedule_for_date(db, user, parsed.effective_from - timedelta(days=1)))
        if parsed.reset_of is not None:
            verb = "wurde" if parsed.effective_from <= today else "wird"
            text = (f"Die Arbeitszeit-Änderung ab {parsed.reset_of:%d.%m.%Y} {verb} ab {eff} "
                    f"auf den vorherigen Stand zurückgesetzt (neu: {neu}).")
        elif parsed.effective_from <= today:
            text = f"Ihre Arbeitszeit wurde ab {eff} geändert (neu: {neu})."
        else:
            text = f"Ihre Arbeitszeit ändert sich ab {eff} (neu: {neu})."
    if parsed.count > 0:
        noun = "Eintrag" if parsed.count == 1 else "Einträge"
        text += f" {parsed.count} {noun} neu berechnet, angerechnete Zeit {_signed_hm(parsed.delta_minutes)} h."
    if parsed.saldo_delta_minutes != 0:
        text += f" Überstundenkonto im Zeitraum {_signed_hm(parsed.saldo_delta_minutes)} h."
    if parsed.shortening:
        label = REASON_TYPES[parsed.reason_type].label if parsed.reason_type else None
        text += f" Rückwirkende Verkürzung – Grund: {label}." if label else " Rückwirkende Verkürzung."
    return text


def schedule_change_notices(db, user, *, now: Optional[datetime] = None) -> List[dict]:
    """Spec 14/P20 — alle Sammelzeilen der Person der letzten 30 Tage, jüngste
    zuerst, nur die, die ``parse_summary_note`` liest (eine Einzelzeile, deren
    Eintrag gelöscht wurde, verdrängt so keinen Hinweis). Keine
    Bestätigungstabelle. Die 30-Tage-Grenze wird in Python geprüft: SQLite
    liefert ``created_at`` ohne Zeitzone (dort UTC)."""
    from app.models import TimeEntryAuditLog

    now = now or timezone_service.now_local()
    since = now - timedelta(days=NOTICE_DAYS)
    rows = db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.user_id == user.id,
        TimeEntryAuditLog.tenant_id == user.tenant_id,  # F-026
        TimeEntryAuditLog.source == AUDIT_SOURCE,
        TimeEntryAuditLog.time_entry_id.is_(None),
        TimeEntryAuditLog.old_date.is_(None),
        TimeEntryAuditLog.new_date.is_(None),
    ).order_by(TimeEntryAuditLog.created_at.desc()).all()
    today = timezone_service.today_local()
    notices = []
    for row in rows:
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
        if created < since:
            continue
        parsed = parse_summary_note(row.new_note)
        if parsed is None:
            continue
        kind = "delete" if parsed.deleted else ("reset" if parsed.reset_of is not None else "change")
        notices.append({"created_at": created, "effective_from": parsed.effective_from, "kind": kind,
                        "text": notice_text(db, user, parsed, today)})
    return notices
