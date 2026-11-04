"""Teil A (Vertragsverlauf), Task 16: Bit-Identität über Migration 075.

Migration 075 schreibt die heutigen Werte von ``vacation_days``, ``track_hours``,
``milog_working_time_account``, ``agreed_monthly_hours`` und
``use_fixed_monthly_target`` in jede Verlaufszeile; der Teil-A-Code liest sie
ab dann aus dem Vertrags-Snapshot. Anti-Ziel (Spec Abschnitt 4): kein
vergangenes Ergebnis ändert sich. Diese Probe hält das auf einer Prod-Kopie fest.

Schreibt je Person (sortiertes JSON nach stdout), je Jahr vom ersten Eintrag
bzw. der ersten Abwesenheit — frühestens ab ``BOOKING_FLOOR`` (01.01.2000) —
bis ``PROBE_TODAY`` + 1 Jahr:
  - ``get_vacation_account`` (alle Schlüssel außer dem neuen ``entitlement_days``)
  - je Monat ``get_monthly_target``, ``get_monthly_actual`` und
    ``get_overtime_account`` (voller Monat)
  - ``get_ytd_summary`` und ``get_overtime_account`` zum Saldo-Stichtag (#313)
  - ``get_overtime_history_detailed`` bis Dezember des Folgejahres (Stichtag)
  - ``milog_service.settlement_aging`` zum ``PROBE_TODAY`` (``None`` ohne Konto)

Nutzt nur Aufrufe, die es vor Teil A (Code-Stand 4198bf08, Migration 074) und
danach gleichlautend gibt.

Ablauf:
  1. Prod-Sicherung in ein Wegwerf-PostgreSQL 18 einspielen (Rolle
     ``praxiszeit_app`` vorher anlegen), mit dem Code VOR Teil A auf 074 heben.
  2. Code vor Teil A auf 074 laufen lassen → ``a.json``.
  3. Mit dem Teil-A-Code auf 075 heben
     (``python -c "from alembic.config import main; main(['upgrade', 'head'])"``).
  4. Teil-A-Code laufen lassen → ``b.json``.
  5. ``diff a.json b.json`` muss leer sein.

Aufruf im Backend-Image, Arbeitsverzeichnis = Backend der jeweiligen Version:
    PROBE_TODAY=2026-11-04 python /probe/probe_075.py > /out/<name>.json

``PROBE_TODAY`` (ISO-Datum) hält „heute" für beide Läufe fest: die Probe ersetzt
dafür jedes ``today_local`` im geladenen ``app``-Code (auch das von
``timezone_service`` selbst, also auch ``timezone_service.today_local()``);
``now_local`` bleibt ungefroren — die probierten Aufrufe lesen es nicht. Ausgaben enthalten echte
Personendaten (Kennungen und Salden) — nie ins Repository legen.
"""
import json
import os
import sys
import time
from datetime import date

sys.path.insert(0, ".")

from app.database import SessionLocal, set_superadmin_context  # noqa: E402
from app.models import Absence, TimeEntry, User  # noqa: E402
from app.services import calculation_service as cs  # noqa: E402
from app.services import milog_service  # noqa: E402
from app.services import timezone_service  # noqa: E402

NEW_VACATION_KEYS = {"entitlement_days"}
# Untergrenze für den BEGINN des Probe-Zeitraums: die Prod-Sicherung vom
# 2026-10-09 enthält einen Zeiteintrag mit Tippfehler-Jahr (0026-05-19). Ohne
# Grenze liefe die Probe je Monat über rund 2000 Jahre (Abbruch nach 2 h).
# Die Berechnungen selbst bleiben ungefiltert (der Eintrag zählt dort wie im
# Betrieb), nur die abgefragten Jahre/Monate beginnen nicht vor der Grenze.
BOOKING_FLOOR = date(2000, 1, 1)


def _freeze_today(today: date) -> None:
    original = timezone_service.today_local
    for name, mod in list(sys.modules.items()):
        if (name == "app" or name.startswith("app.")) and getattr(mod, "today_local", None) is original:
            setattr(mod, "today_local", lambda: today)


def _months(first: date, last: date):
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def _plain(value):
    """Decimal/date/NamedTuple → JSON-stabile Strings (Typ bleibt erkennbar)."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if value is None or isinstance(value, (bool, str)):
        return value
    return f"{type(value).__name__}:{value}"


def _first_booking(db, user, today: date) -> date:
    dates = [d for (d,) in db.query(TimeEntry.date).filter(
        TimeEntry.user_id == user.id, TimeEntry.tenant_id == user.tenant_id).all()]
    dates += [d for (d,) in db.query(Absence.date).filter(
        Absence.user_id == user.id, Absence.tenant_id == user.tenant_id).all()]
    return min((d for d in dates if d >= BOOKING_FLOOR), default=today)


def _progress(row: int, step: str, started: float) -> None:
    """Fortschritt nach stderr — Zeilennummer statt Personenkennung."""
    print(f"person {row}: {step} ({time.monotonic() - started:.1f}s)", file=sys.stderr, flush=True)


def probe_user(db, user, today: date, row: int = 0) -> dict:
    started = time.monotonic()
    first = _first_booking(db, user, today)
    last = date(today.year + 1, 12, 31)
    cutoff = cs.get_soll_cutoff_date(db, user, today=today)
    _progress(row, f"{first.year}-{last.year}", started)

    vacation = {}
    ytd = {}
    for year in range(first.year, last.year + 1):
        account = cs.get_vacation_account(db, user, year)
        vacation[year] = {k: v for k, v in account.items() if k not in NEW_VACATION_KEYS}
        ytd[year] = cs.get_ytd_summary(db, user, year, cutoff_date=cutoff)
    _progress(row, "vacation+ytd", started)

    months = {
        f"{y}-{m:02d}": [cs.get_monthly_target(db, user, y, m),
                         cs.get_monthly_actual(db, user, y, m),
                         cs.get_overtime_account(db, user, y, m)]
        for y, m in _months(first, last)
    }
    _progress(row, "months", started)
    history = cs.get_overtime_history_detailed(db, user, last.year, last.month, cutoff_date=cutoff)
    _progress(row, "history", started)
    aging = milog_service.settlement_aging(db, user, today)
    _progress(row, "done", started)
    return _plain({
        "cutoff": cutoff,
        "vacation": vacation,
        "ytd": ytd,
        "months": months,
        "overtime_cutoff": cs.get_overtime_account(db, user, today.year, today.month, cutoff_date=cutoff),
        "history": {f"{y}-{m:02d}": list(mo) for (y, m), mo in sorted(history.items())},
        "settlement_aging": aging,
    })


def main() -> None:
    today = date.fromisoformat(os.environ["PROBE_TODAY"])
    _freeze_today(today)
    db = SessionLocal()
    set_superadmin_context(db)
    users = db.query(User).filter(User.tenant_id.isnot(None)).order_by(User.id).all()
    result = {str(user.id): probe_user(db, user, today, row) for row, user in enumerate(users, 1)}
    json.dump(result, sys.stdout, sort_keys=True, indent=1)
    db.close()


if __name__ == "__main__":
    main()
